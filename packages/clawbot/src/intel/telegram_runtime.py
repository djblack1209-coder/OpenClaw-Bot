"""Telegram runtime adapter for Intel Brief command handlers.

The adapter bridges Telegram-shaped updates to the menu handler contract and a
reply sender.  It is transport-agnostic: tests and evidence can inject a fake
sender, while production can later pass ``TelegramBotApiSender``.  Returned
runtime evidence is redacted and never includes raw chat ids or Bot API tokens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command


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
                        "reply_markup": item.get("reply_markup") if isinstance(item.get("reply_markup"), dict) else None,
                    }
                )
    items.append(
        {
            "text": _clean(handler_result.get("reply_text")),
            "reply_markup": handler_result.get("reply_markup") if isinstance(handler_result.get("reply_markup"), dict) else None,
        }
    )
    return [item for item in items if _clean(item.get("text"))]


def _answer_callback(sender: TelegramReplySender, callback_query_id: str) -> dict[str, Any]:
    if not callback_query_id or not hasattr(sender, "answer_callback_query"):
        return {"success": True, "callback_query_id_present": bool(callback_query_id), "network_calls": 0}
    result = sender.answer_callback_query(callback_query_id, text="已收到")  # type: ignore[attr-defined]
    return result if isinstance(result, dict) else {"success": False, "callback_query_id_present": bool(callback_query_id)}


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
        user = TelegramUserContext(
            telegram_user_id=parsed["telegram_user_id"],
            chat_id=parsed["chat_id"],
            username=parsed["username"],
        )
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
        all_replies_success = True
        for item in reply_items:
            before = int(getattr(sender, "network_calls", 0) or 0)
            reply_markup = item.get("reply_markup") if isinstance(item.get("reply_markup"), dict) else None
            if reply_markup:
                send_result = sender.send(parsed["chat_id"], _clean(item.get("text")), reply_markup=reply_markup)
                inline_keyboard_sent = inline_keyboard_sent or bool(reply_markup.get("inline_keyboard"))
                persistent_keyboard_sent = persistent_keyboard_sent or bool(reply_markup.get("keyboard"))
            else:
                send_result = sender.send(parsed["chat_id"], _clean(item.get("text")))
            delta = _send_delta(sender, before, send_result)
            send_network_calls += delta
            redacted_send = _redacted_send_result(send_result, network_calls=delta)
            update_reply_results.append(redacted_send)
            all_replies_success = all_replies_success and redacted_send["success"]
        callback_answer = _answer_callback(sender, _clean(parsed.get("callback_query_id"))) if parsed.get("message_key") == "callback_query" else {"success": True, "network_calls": 0}
        callback_network_calls = int(callback_answer.get("network_calls", 0) or 0)
        network_calls += int(handler_result.get("network_calls", 0) or 0) + send_network_calls + callback_network_calls
        callback_ok = bool(callback_answer.get("success", True))
        if all_replies_success and callback_ok:
            send_success_count += 1
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
                "reply_markup_present": inline_keyboard_sent or persistent_keyboard_sent,
                "inline_keyboard_sent": inline_keyboard_sent,
                "persistent_keyboard_sent": persistent_keyboard_sent,
                "reply_text_present": bool(reply_text),
                "send_success": all_replies_success,
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
    if handled_count and send_success_count < handled_count:
        status = "partial_failed_send"
    return {
        "status": status,
        "updates_seen": len(updates),
        "handled_count": handled_count,
        "skipped_count": len(skipped_updates),
        "send_success_count": send_success_count,
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
