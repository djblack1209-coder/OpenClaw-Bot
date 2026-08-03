"""Telegram runtime adapter for Intel Brief command handlers.

The adapter bridges Telegram-shaped updates to the menu handler contract and a
reply sender.  It is transport-agnostic: tests and evidence can inject a fake
sender, while production can later pass ``TelegramBotApiSender``.  Returned
runtime evidence is redacted and never includes raw chat ids or Bot API tokens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from src.intel.db.store import (
    get_intel_brief,
    save_intel_brief_localization,
)
from src.intel.subscriptions import (
    get_subscription_profile,
    set_content_language,
    upsert_telegram_subscriber,
)
from src.intel.telegram_brief_renderer import build_brief_envelope
from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command
from src.intel.translation_service import CCSwitchTranslationProvider, localize_brief_payload


class TelegramReplySender(Protocol):
    def send(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a reply to Telegram and return a redacted send result."""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _message_from_update(update: dict[str, Any]) -> tuple[dict[str, Any], str]:
    for key in ("message", "edited_message"):
        message = update.get(key)
        if isinstance(message, dict):
            return message, key
    return {}, ""


def _callback_from_update(update: dict[str, Any]) -> dict[str, Any]:
    callback = update.get("callback_query")
    return callback if isinstance(callback, dict) else {}


def _parse_command_text(text: str) -> tuple[str, list[str]]:
    cleaned = _clean(text)
    if cleaned and not cleaned.startswith("/"):
        return cleaned, []
    parts = cleaned.split()
    if not parts:
        return "", []
    command = parts[0]
    if command.startswith("/"):
        command = command[1:]
    command = command.split("@", 1)[0].lower()
    return command, parts[1:]


def parse_telegram_command_update(update: dict[str, Any]) -> dict[str, Any]:
    """Extract command/user context from one Telegram update.

    The returned mapping contains raw ``chat_id`` so callers can send replies;
    do not write it directly to evidence.
    """
    callback = _callback_from_update(update)
    if callback:
        data = _clean(callback.get("data"))
        message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        from_user = callback.get("from") if isinstance(callback.get("from"), dict) else {}
        chat_id = _clean(chat.get("id") if isinstance(chat, dict) else "")
        telegram_user_id = _clean(from_user.get("id") if isinstance(from_user, dict) else "") or chat_id
        if not data or not chat_id or not telegram_user_id:
            return {}
        return {
            "update_id": update.get("update_id"),
            "message_key": "callback_query",
            "callback_query_id": _clean(callback.get("id")),
            "telegram_user_id": telegram_user_id,
            "chat_id": chat_id,
            "username": _clean(from_user.get("username") if isinstance(from_user, dict) else ""),
            "command": data,
            "args": [],
            "text_kind": "callback_query",
        }

    message, message_key = _message_from_update(update)
    if not message:
        return {}
    text = _clean(message.get("text"))
    command, args = _parse_command_text(text)
    if not command:
        return {}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    from_user = message.get("from") if isinstance(message.get("from"), dict) else {}
    chat_id = _clean(chat.get("id") if isinstance(chat, dict) else "")
    telegram_user_id = _clean(from_user.get("id") if isinstance(from_user, dict) else "") or chat_id
    if not chat_id or not telegram_user_id:
        return {}
    return {
        "update_id": update.get("update_id"),
        "message_key": message_key,
        "callback_query_id": "",
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "username": _clean(from_user.get("username") if isinstance(from_user, dict) else ""),
        "command": command,
        "args": args,
        "text_kind": "command" if text.startswith("/") else "text",
    }


def _send_delta(sender: TelegramReplySender, before: int, send_result: dict[str, Any]) -> int:
    after = int(getattr(sender, "network_calls", before) or before)
    if after > before:
        return after - before
    return int(send_result.get("network_calls", 0) or 0)


def _redacted_send_result(send_result: dict[str, Any], *, network_calls: int) -> dict[str, Any]:
    return {
        "success": bool(send_result.get("success")),
        "ambiguous_delivery": bool(send_result.get("ambiguous_delivery")),
        "network": _clean(send_result.get("network")),
        "network_calls": int(network_calls),
        "endpoint": _clean(send_result.get("endpoint")),
        "chat_id_present": bool(send_result.get("chat_id_present")),
        "message_id_present": bool(_clean(send_result.get("message_id"))),
        "reply_markup_present": bool(send_result.get("reply_markup_present")),
        "error_code": _clean(send_result.get("error_code")),
        "error_present": bool(_clean(send_result.get("error"))),
    }


def _reply_items(handler_result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    prelude = handler_result.get("prelude_replies")
    if isinstance(prelude, list):
        for item in prelude:
            if isinstance(item, dict):
                items.append(
                    {
                        "text": _clean(item.get("text")),
                        "reply_markup": item.get("reply_markup")
                        if isinstance(item.get("reply_markup"), dict)
                        else None,
                    }
                )
    items.append(
        {
            "text": _clean(handler_result.get("reply_text")),
            "reply_markup": handler_result.get("reply_markup")
            if isinstance(handler_result.get("reply_markup"), dict)
            else None,
        }
    )
    return [item for item in items if _clean(item.get("text"))]


def _answer_callback(sender: TelegramReplySender, callback_query_id: str) -> dict[str, Any]:
    if not callback_query_id or not hasattr(sender, "answer_callback_query"):
        return {"success": True, "callback_query_id_present": bool(callback_query_id), "network_calls": 0}
    try:
        result = sender.answer_callback_query(callback_query_id, text="已收到")  # type: ignore[attr-defined]
    except Exception as exc:
        return {
            "success": False,
            "callback_query_id_present": True,
            "network_calls": 0,
            "error_type": type(exc).__name__,
        }
    return (
        result if isinstance(result, dict) else {"success": False, "callback_query_id_present": bool(callback_query_id)}
    )


def _ambiguous_send_exception(exc: Exception) -> dict[str, Any]:
    """把网络边界异常转成不自动重试的投递未知态。"""
    return {
        "success": False,
        "ambiguous_delivery": True,
        "network": "sender_exception",
        "network_calls": 0,
        "chat_id_present": True,
        "message_id": "",
        "endpoint": "",
        "reply_markup_present": False,
        "error": type(exc).__name__,
    }


def _brief_category_match(item: dict[str, Any], view: str) -> bool:
    """判断条目是否属于简报按钮请求的大类。"""
    if view == "all":
        return True
    values = {
        _clean(item.get(key)).lower()
        for key in ("source", "source_name", "category", "source_label")
        if _clean(item.get(key))
    }
    aliases = item.get("category_aliases")
    if isinstance(aliases, list):
        values.update(_clean(value).lower() for value in aliases if _clean(value))
    groups = {
        "market": {"market", "akshare", "senate_trading", "institutional_13f", "市场", "a股龙虎榜", "国会持仓"},
        "ai": {"ai", "technology", "tech", "ai_model_updates", "github_trending", "ai模型动态", "趋势"},
        "weather": {"weather", "temperature", "rainfall", "humidity", "air_quality", "天气", "天气监测"},
    }
    return bool(values.intersection(groups.get(view, {view})))


def _handle_brief_callback(
    db_path: str | Path,
    *,
    parsed: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    """回放指定 brief_ref 的完整内容、分类视图或语言版本。"""
    parts = _clean(parsed.get("command")).split(":")
    user = TelegramUserContext(
        telegram_user_id=_clean(parsed.get("telegram_user_id")),
        chat_id=_clean(parsed.get("chat_id")),
        username=_clean(parsed.get("username")),
    )
    subscriber = upsert_telegram_subscriber(
        db_path,
        telegram_user_id=user.telegram_user_id,
        chat_id=user.chat_id,
        reactivate=False,
    )
    profile = get_subscription_profile(db_path, user_id=subscriber["user_id"], now=now)
    current_language = _clean((profile.get("delivery_preferences") or {}).get("content_language")) or "zh"
    if len(parts) != 4 or parts[0] != "ib1" or parts[1] not in {"l", "v"}:
        return {
            "command": "brief_callback",
            "status": "error",
            "reply_text": "该简报按钮已失效，请发送 /today 获取最近一期。",
            "subscriber": subscriber,
        }
    action, value, brief_ref = parts[1], parts[2], parts[3]
    if action == "l" and value in {"zh", "en"}:
        current_language = value
        set_content_language(db_path, user_id=subscriber["user_id"], content_language=value)
    brief = get_intel_brief(db_path, public_ref=brief_ref, language=current_language)
    if not brief:
        return {
            "command": "brief_callback",
            "status": "not_found",
            "reply_text": "这期简报已不在本机，请发送 /today 获取最近一期。",
            "subscriber": subscriber,
        }
    payload = dict(brief["payload"])
    if action == "l" and brief.get("localization_status") in {"source", "partial_source_fallback"}:
        provider = CCSwitchTranslationProvider()
        localized, evidence = localize_brief_payload(
            payload,
            target_language=current_language,
            db_path=db_path,
            provider=provider if provider.ready else None,
        )
        payload = localized
        save_intel_brief_localization(
            db_path,
            brief_id=int(brief["id"]),
            language=current_language,
            translator_version=provider.provider_version if provider.ready else "source-v1",
            status=str(evidence.get("status") or "source"),
            payload=payload,
        )
    if action == "v":
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        payload["items"] = [item for item in items if isinstance(item, dict) and _brief_category_match(item, value)]
    envelope = build_brief_envelope(
        payload,
        brief_ref=brief_ref,
        language=current_language,
        cover_path="",
    )
    return {
        "command": "brief_callback",
        "status": "success",
        "reply_text": envelope.full_text_html,
        "reply_markup": envelope.reply_markup,
        "subscriber": subscriber,
        "brief_ref": brief_ref,
        "content_language": current_language,
        "filtered_item_count": len(payload.get("items", []) or []),
    }


def process_intel_telegram_updates(
    db_path: str | Path,
    *,
    updates: list[dict[str, Any]],
    sender: TelegramReplySender,
    now: str = "9999-12-31T00:00:00+00:00",
) -> dict[str, Any]:
    """Process Telegram updates through Intel Brief handlers and reply sender."""
    handled_updates: list[dict[str, Any]] = []
    replies: list[dict[str, Any]] = []
    skipped_updates: list[dict[str, Any]] = []
    tracking_targets: list[dict[str, Any]] = []
    network_calls = 0
    send_success_count = 0
    delivery_terminal_count = 0
    delivery_unknown_count = 0
    callback_answer_failure_count = 0

    for update in updates:
        parsed = parse_telegram_command_update(update)
        if not parsed:
            skipped_updates.append(
                {
                    "update_id_present": update.get("update_id") not in (None, ""),
                    "reason": "not_a_supported_text_command",
                }
            )
            continue
        callback_before = int(getattr(sender, "network_calls", 0) or 0)
        callback_answer = (
            _answer_callback(sender, _clean(parsed.get("callback_query_id")))
            if parsed.get("message_key") == "callback_query"
            else {"success": True, "network_calls": 0}
        )
        callback_network_calls = _send_delta(sender, callback_before, callback_answer)
        callback_ok = bool(callback_answer.get("success", True))
        user = TelegramUserContext(
            telegram_user_id=parsed["telegram_user_id"],
            chat_id=parsed["chat_id"],
            username=parsed["username"],
        )
        if _clean(parsed.get("command")).startswith("ib1:"):
            handler_result = _handle_brief_callback(db_path, parsed=parsed, now=now)
        else:
            handler_result = handle_intel_telegram_command(
                db_path,
                user=user,
                command=parsed["command"],
                args=parsed["args"],
                now=now,
            )
        reply_text = _clean(handler_result.get("reply_text"))
        reply_items = _reply_items(handler_result)
        update_reply_results: list[dict[str, Any]] = []
        send_network_calls = 0
        inline_keyboard_sent = False
        persistent_keyboard_sent = False
        successful_reply_count = 0
        ambiguous_reply = False
        for item in reply_items:
            before = int(getattr(sender, "network_calls", 0) or 0)
            reply_markup = item.get("reply_markup") if isinstance(item.get("reply_markup"), dict) else None
            try:
                if reply_markup:
                    send_result = sender.send(parsed["chat_id"], _clean(item.get("text")), reply_markup=reply_markup)
                    inline_keyboard_sent = inline_keyboard_sent or bool(reply_markup.get("inline_keyboard"))
                    persistent_keyboard_sent = persistent_keyboard_sent or bool(reply_markup.get("keyboard"))
                else:
                    send_result = sender.send(parsed["chat_id"], _clean(item.get("text")))
            except (TimeoutError, ConnectionError, OSError) as exc:
                send_result = _ambiguous_send_exception(exc)
            delta = _send_delta(sender, before, send_result)
            send_network_calls += delta
            redacted_send = _redacted_send_result(send_result, network_calls=delta)
            update_reply_results.append(redacted_send)
            if redacted_send["success"]:
                successful_reply_count += 1
                continue
            ambiguous_reply = bool(redacted_send["ambiguous_delivery"])
            break
        all_replies_success = successful_reply_count == len(reply_items)
        if all_replies_success:
            body_delivery_state = "sent"
        elif ambiguous_reply:
            body_delivery_state = "unknown"
        elif successful_reply_count:
            body_delivery_state = "partial"
        else:
            body_delivery_state = "failed"
        body_delivery_terminal = body_delivery_state in {"sent", "partial", "unknown"}
        network_calls += int(handler_result.get("network_calls", 0) or 0) + send_network_calls + callback_network_calls
        if all_replies_success:
            send_success_count += 1
        if body_delivery_terminal:
            delivery_terminal_count += 1
        if body_delivery_state in {"partial", "unknown"}:
            delivery_unknown_count += 1
        if not callback_ok:
            callback_answer_failure_count += 1
        subscriber = handler_result.get("subscriber") if isinstance(handler_result.get("subscriber"), dict) else {}
        handled_updates.append(
            {
                "update_id_present": parsed.get("update_id") not in (None, ""),
                "message_key": parsed["message_key"],
                "callback_query_id_present": bool(_clean(parsed.get("callback_query_id"))),
                "callback_answer_success": callback_ok,
                "command": handler_result.get("command", parsed["command"]),
                "handler_status": handler_result.get("status"),
                "subscriber_user_id": subscriber.get("user_id", ""),
                "subscriber_user_id_present": bool(_clean(subscriber.get("user_id", ""))),
                "reply_message_count": len(update_reply_results),
                "reply_success_count": successful_reply_count,
                "reply_markup_present": inline_keyboard_sent or persistent_keyboard_sent,
                "inline_keyboard_sent": inline_keyboard_sent,
                "persistent_keyboard_sent": persistent_keyboard_sent,
                "reply_text_present": bool(reply_text),
                "send_success": all_replies_success,
                "body_delivery_state": body_delivery_state,
                "body_delivery_terminal": body_delivery_terminal,
            }
        )
        replies.extend(update_reply_results)
        tracking = handler_result.get("tracking_target")
        if isinstance(tracking, dict):
            tracking_targets.append(
                {
                    "name": _clean(tracking.get("name")),
                    "active_subscription_count": int(tracking.get("active_subscription_count", 0) or 0),
                }
            )

    handled_count = len(handled_updates)
    status = "success" if handled_count == send_success_count and handled_count > 0 else "partial_or_empty"
    if (
        handled_count
        and delivery_terminal_count == handled_count
        and (delivery_unknown_count or callback_answer_failure_count)
    ):
        status = "completed_with_warnings"
    elif handled_count and delivery_terminal_count < handled_count:
        status = "partial_failed_send"
    return {
        "status": status,
        "updates_seen": len(updates),
        "handled_count": handled_count,
        "skipped_count": len(skipped_updates),
        "send_success_count": send_success_count,
        "delivery_terminal_count": delivery_terminal_count,
        "delivery_unknown_count": delivery_unknown_count,
        "callback_answer_failure_count": callback_answer_failure_count,
        "handled_updates": handled_updates,
        "skipped_updates": skipped_updates,
        "replies": replies,
        "tracking_targets": tracking_targets,
        "network_calls": network_calls,
        "limits": [
            "Raw Telegram chat ids are used only in-memory for sender calls and are not returned in runtime evidence.",
            "Runtime adapter does not poll Telegram by itself; callers provide updates and sender implementation.",
        ],
    }
