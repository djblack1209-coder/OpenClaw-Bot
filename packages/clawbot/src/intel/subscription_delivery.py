"""Subscription-filtered Intel Brief delivery helpers.

This module delivers a summary only to active, non-expired subscribers whose
source preferences match categories present in the summary evidence.  It keeps
raw channel ids out of returned evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import Counter
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.constants import TG_SAFE_LENGTH
from src.intel.db.store import (
    claim_delivery,
    delivered_event_keys,
    finalize_delivery_claim,
    has_successful_delivery_for_date,
    initialize_intel_db,
    invalidate_telegram_media_asset,
    put_telegram_media_asset,
    record_content_delivery_attempts,
    record_delivery_artifact,
    save_intel_brief,
    save_intel_brief_localization,
)
from src.intel.subscriptions import (
    eligible_subscribers_for_categories,
    grant_subscription,
    set_source_preferences,
    upsert_subscription_plan,
    upsert_telegram_subscriber,
)
from src.intel.telegram_brief_renderer import build_brief_envelope, event_key_for_item
from src.intel.telegram_delivery import send_delivery_envelope
from src.intel.telegram_media_store import SqliteTelegramMediaStore, TelegramMediaStoreError
from src.intel.translation_service import CCSwitchTranslationProvider, localize_brief_payload


class SummarySender(Protocol):
    network_calls: int

    def send(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send summary text and return a redacted send result."""


class FakeSubscriptionDeliverySender:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.network_calls = 0

    def send(self, chat_id: str, text: str, *, parse_mode: str = "HTML") -> dict[str, Any]:
        self.sent.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
        return {
            "success": True,
            "network": "fake_sender",
            "network_calls": 0,
            "chat_id_present": bool(str(chat_id or "").strip()),
            "message_id": f"fake-{len(self.sent)}",
            "endpoint": "fake://telegram/sendMessage",
            "text_chars": len(str(text or "")),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _telegram_bot_fingerprint(env: dict[str, str], sender: SummarySender) -> str:
    """用脱敏 Bot 身份隔离 file_id 缓存，Token 轮换不暴露凭据。"""
    token = _clean(env.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN") or getattr(sender, "token", ""))
    bot_identity = token.split(":", 1)[0] if ":" in token else token
    if not bot_identity:
        return "unscoped"
    return hashlib.sha256(bot_identity.encode("utf-8")).hexdigest()[:12]


def _source_categories(summary_payload: dict[str, Any]) -> list[str]:
    categories: set[str] = set()
    for item in summary_payload.get("items", []):
        if not isinstance(item, dict):
            continue
        aliases = item.get("category_aliases")
        if isinstance(aliases, list):
            categories.update(_clean(alias) for alias in aliases if _clean(alias))
        for key in ("source", "source_name", "category"):
            value = _clean(item.get(key))
            if value:
                categories.add(value)
    return sorted(categories)


def _recipient_due(recipient: dict[str, Any], now: str, *, grace_minutes: int = 90) -> bool:
    """按订阅者时区判断当前周期是否处于其投递窗口。"""
    preferences = recipient.get("delivery_preferences")
    prefs = preferences if isinstance(preferences, dict) else {}
    try:
        current = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
    except ValueError:
        return False
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)  # noqa: UP017
    timezone_name = _clean(prefs.get("timezone")) or "Asia/Singapore"
    try:
        local = current.astimezone(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError:
        return False
    delivery_time = _clean(prefs.get("delivery_time")) or "08:30"
    try:
        hour_text, minute_text = delivery_time.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return False
    except (TypeError, ValueError):
        return False
    start = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if not start <= local <= start + timedelta(minutes=max(1, grace_minutes)):
        return False
    frequency = _clean(prefs.get("frequency")) or "daily"
    return frequency != "weekly" or local.weekday() == 0


def _item_categories(item: dict[str, Any]) -> set[str]:
    categories = {_clean(item.get(key)) for key in ("source", "source_name", "category") if _clean(item.get(key))}
    aliases = item.get("category_aliases")
    if isinstance(aliases, list):
        categories.update(_clean(alias) for alias in aliases if _clean(alias))
    return categories


def _clip_title(value: Any, limit: int = 42) -> str:
    """裁剪重点标题，避免总览段落过长。"""
    cleaned = _clean(value)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 1)].rstrip() + "…"


def _recipient_summary_text(items: list[dict[str, Any]], language: str = "zh") -> str:
    """基于过滤后的真实条目生成每位订阅者专属总览。"""
    if not items:
        return (
            "No fresh intelligence matched your subscriptions today."
            if language == "en"
            else "今天没有匹配你订阅偏好的新情报。"
        )
    labels = [_clean(item.get("source_label") or item.get("source")) or "其他情报" for item in items]
    counts = Counter(labels)
    coverage = (
        ", ".join(f"{label}: {count}" for label, count in counts.items())
        if language == "en"
        else "、".join(f"{label} {count} 条" for label, count in counts.items())
    )
    highlights = [_clip_title(item.get("title")) for item in items[:3] if _clean(item.get("title"))]
    summary = (
        f"Selected {len(items)} fresh signals across {coverage}."
        if language == "en"
        else f"今天为你筛出 {len(items)} 条，覆盖 {coverage}。"
    )
    if highlights:
        summary += (
            f" Highlights: {'; '.join(highlights)}." if language == "en" else f" 重点包括：{'；'.join(highlights)}。"
        )
    return summary


def _filter_summary_payload_for_categories(summary_payload: dict[str, Any], categories: list[str]) -> dict[str, Any]:
    """Return a per-recipient payload containing only matched source categories."""
    allowed = {_clean(category) for category in categories if _clean(category)}
    copied = json.loads(json.dumps(summary_payload, ensure_ascii=False))
    items = []
    for item in copied.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        if _item_categories(item).intersection(allowed):
            items.append(item)
    copied["items"] = items
    llm = copied.get("llm") if isinstance(copied.get("llm"), dict) else {}
    copied["llm"] = {
        **llm,
        "summary_text": _recipient_summary_text(items, _clean(copied.get("content_language")) or "zh"),
        "personalized_for_recipient": True,
    }
    copied["recipient_filter"] = {
        "matched_categories": sorted(allowed),
        "filtered_item_count": len(items),
    }
    return copied


def _record_delivery_log(
    db_path: str | Path,
    *,
    subscriber_id: int,
    channel_type: str,
    content_summary: str,
    success: bool,
    error_message: str = "",
) -> int:
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO delivery_log (subscriber_id, content_summary, channel_type, success, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (subscriber_id, content_summary[:1000], channel_type, 1 if success else 0, error_message or None),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _send_delta(sender: SummarySender, before: int, send_result: dict[str, Any]) -> int:
    after = int(getattr(sender, "network_calls", before) or before)
    if after > before:
        return after - before
    return int(send_result.get("network_calls", 0) or 0)


def deliver_summary_to_eligible_subscribers(
    *,
    db_path: str | Path,
    summary_evidence_path: str | Path,
    sender: SummarySender,
    now: str,
    max_chars: int = TG_SAFE_LENGTH,
    env: dict[str, str] | None = None,
    enforce_delivery_window: bool = False,
    translation_provider: Any | None = None,
) -> dict[str, Any]:
    """向匹配订阅者发送可回放、可去重的 Top 3 富媒体简报。"""
    summary_payload = json.loads(Path(summary_evidence_path).read_text(encoding="utf-8"))
    env_map = dict(os.environ if env is None else env)
    categories = _source_categories(summary_payload)
    recipients = eligible_subscribers_for_categories(db_path, categories=categories, now=now)
    not_due_count = 0
    if enforce_delivery_window:
        due_recipients = [recipient for recipient in recipients if _recipient_due(recipient, now)]
        not_due_count = len(recipients) - len(due_recipients)
        recipients = due_recipients
    brief_date = _clean(summary_payload.get("brief_date") or summary_payload.get("date") or now[:10])
    brief_record = save_intel_brief(db_path, brief_date=brief_date, payload=summary_payload)
    translation_enabled = translation_provider is not None or str(
        env_map.get("INTEL_BRIEF_TRANSLATION_ENABLED") or ""
    ).lower() in {"1", "true", "yes", "on"}
    provider = translation_provider
    if provider is None and translation_enabled:
        candidate_provider = CCSwitchTranslationProvider()
        provider = candidate_provider if candidate_provider.ready else None
    requested_languages = {
        _clean(
            (recipient.get("delivery_preferences") or {}).get("content_language")
            if isinstance(recipient.get("delivery_preferences"), dict)
            else "zh"
        )
        or "zh"
        for recipient in recipients
    }
    localized_payloads: dict[str, dict[str, Any]] = {}
    localization_evidence: dict[str, dict[str, Any]] = {}
    for requested_language in sorted(requested_languages or {"zh"}):
        language = requested_language if requested_language in {"zh", "en"} else "zh"
        if translation_enabled:
            localized, evidence = localize_brief_payload(
                summary_payload,
                target_language=language,
                db_path=db_path,
                provider=provider,
            )
        else:
            localized = json.loads(json.dumps(summary_payload, ensure_ascii=False))
            localized["content_language"] = language
            localized["localization"] = {
                "status": "source",
                "target_language": language,
                "translated_field_count": 0,
                "source_fallback": False,
                "provider": "disabled",
            }
            evidence = dict(localized["localization"])
        localized_payloads[language] = localized
        localization_evidence[language] = evidence
        save_intel_brief_localization(
            db_path,
            brief_id=int(brief_record["id"]),
            language=language,
            translator_version=str(getattr(provider, "provider_version", "source-v1") if provider else "source-v1"),
            status=str(evidence.get("status") or "source"),
            payload=localized,
        )
    cover_path = Path(__file__).resolve().parents[2] / "assets" / "intel" / "openclaw-intel-brief-dark.jpg"
    asset_hash = hashlib.sha256(cover_path.read_bytes()).hexdigest() if cover_path.is_file() else ""
    bot_fingerprint = _telegram_bot_fingerprint(env_map, sender)
    asset_key = f"daily-cover:{bot_fingerprint}:terminal-v2:{asset_hash[:16]}" if asset_hash else ""
    photo_reference = ""
    deliveries: list[dict[str, Any]] = []
    sent = 0
    failed = 0
    network_calls = 0
    message_chars = 0
    media_upload_error = ""
    if asset_key and hasattr(sender, "send_photo"):
        before_upload = int(getattr(sender, "network_calls", 0) or 0)
        try:
            media_store = SqliteTelegramMediaStore(db_path=db_path, sender=sender, env=env_map)
            cached_media = media_store.get(asset_key)
            if cached_media is not None:
                photo_reference = cached_media.file_id
            elif env_map.get("INTEL_BRIEF_TELEGRAM_MEDIA_CHAT_ID"):
                photo_reference = media_store.put_photo(asset_key, cover_path).file_id
        except (OSError, sqlite3.Error, TelegramMediaStoreError) as exc:
            media_upload_error = str(exc)[:300]
        network_calls += max(0, int(getattr(sender, "network_calls", before_upload) or before_upload) - before_upload)
    for recipient in recipients:
        if has_successful_delivery_for_date(
            db_path,
            subscriber_id=int(recipient["subscriber_id"]),
            brief_date=brief_date,
        ):
            deliveries.append(
                {
                    "subscriber_id": int(recipient["subscriber_id"]),
                    "user_id_present": bool(_clean(recipient.get("user_id"))),
                    "channel_type": recipient["channel_type"],
                    "channel_user_id_present": bool(_clean(recipient.get("channel_user_id"))),
                    "matched_categories": list(recipient.get("matched_categories") or []),
                    "filtered_item_count": 0,
                    "status": "skipped_already_delivered_today",
                    "send_result": {"success": True, "network_calls": 0, "render_mode": "none"},
                }
            )
            continue
        language = (
            _clean(
                (recipient.get("delivery_preferences") or {}).get("content_language")
                if isinstance(recipient.get("delivery_preferences"), dict)
                else "zh"
            )
            or "zh"
        )
        language = language if language in {"zh", "en"} else "zh"
        filtered_payload = _filter_summary_payload_for_categories(
            localized_payloads.get(language, summary_payload),
            list(recipient.get("matched_categories") or []),
        )
        items = [item for item in filtered_payload.get("items", []) if isinstance(item, dict)]
        candidate_keys = [event_key_for_item(item, index) for index, item in enumerate(items, 1)]
        already_delivered = delivered_event_keys(
            db_path,
            subscriber_id=int(recipient["subscriber_id"]),
            event_keys=candidate_keys,
        )
        if already_delivered:
            filtered_payload["items"] = [
                item for index, item in enumerate(items, 1) if event_key_for_item(item, index) not in already_delivered
            ]
            filtered_payload["llm"] = {
                **(filtered_payload.get("llm") if isinstance(filtered_payload.get("llm"), dict) else {}),
                "summary_text": _recipient_summary_text(filtered_payload["items"], language),
                "personalized_for_recipient": True,
            }
        if not filtered_payload.get("items"):
            deliveries.append(
                {
                    "subscriber_id": int(recipient["subscriber_id"]),
                    "user_id_present": bool(_clean(recipient.get("user_id"))),
                    "channel_type": recipient["channel_type"],
                    "channel_user_id_present": bool(_clean(recipient.get("channel_user_id"))),
                    "matched_categories": list(recipient.get("matched_categories") or []),
                    "filtered_item_count": 0,
                    "language": language,
                    "status": "skipped_duplicate",
                    "send_result": {"success": True, "network_calls": 0, "render_mode": "none"},
                }
            )
            continue
        envelope = build_brief_envelope(
            filtered_payload,
            brief_ref=str(brief_record["public_ref"]),
            language=language,
            cover_path=cover_path,
            max_chars=max_chars,
        )
        message = envelope.full_text_html
        message_chars = max(message_chars, len(message), len(envelope.caption_html))
        event_keys = envelope.item_event_keys
        subscriber_id = int(recipient["subscriber_id"])
        claim = claim_delivery(
            db_path,
            subscriber_id=subscriber_id,
            brief_id=int(brief_record["id"]),
            brief_date=brief_date,
        )
        if not claim["acquired"]:
            deliveries.append(
                {
                    "subscriber_id": subscriber_id,
                    "user_id_present": bool(_clean(recipient.get("user_id"))),
                    "channel_type": recipient["channel_type"],
                    "channel_user_id_present": bool(_clean(recipient.get("channel_user_id"))),
                    "matched_categories": list(recipient.get("matched_categories") or []),
                    "filtered_item_count": len(filtered_payload.get("items", []) or []),
                    "language": language,
                    "brief_ref": str(brief_record["public_ref"]),
                    "status": (
                        "skipped_delivery_finalized"
                        if claim["reason"] == "already_finalized"
                        else "skipped_delivery_in_progress"
                    ),
                    "send_result": {"success": True, "network_calls": 0, "render_mode": "none"},
                }
            )
            continue
        claim_token = str(claim["claim_token"])
        before = int(getattr(sender, "network_calls", 0) or 0)
        send_network_calls = 0
        claim_finalized = False
        try:
            send_result = send_delivery_envelope(
                sender,
                chat_id=str(recipient["channel_user_id"]),
                envelope=envelope,
                photo=photo_reference,
                prefer_rich=str(env_map.get("INTEL_BRIEF_TELEGRAM_RICH_MESSAGE_ENABLED") or "").lower()
                in {"1", "true", "yes", "on"},
            )
            send_network_calls = _send_delta(sender, before, send_result)
            network_calls += send_network_calls
            success = bool(send_result.get("success"))
            sent += 1 if success else 0
            failed += 0 if success else 1
            delivery_state = _clean(send_result.get("delivery_state")) or ("sent" if success else "failed")
            if asset_key and send_result.get("photo_reference_invalid"):
                invalidate_telegram_media_asset(db_path, asset_key)
            if not finalize_delivery_claim(
                db_path,
                subscriber_id=subscriber_id,
                brief_date=brief_date,
                claim_token=claim_token,
                state=delivery_state,
                error=_clean(send_result.get("error")),
            ):
                raise RuntimeError("投递 claim 已失效，拒绝覆盖其他进程的租约")
            claim_finalized = True
            delivery_log_id = _record_delivery_log(
                db_path,
                subscriber_id=subscriber_id,
                channel_type=str(recipient["channel_type"]),
                content_summary=message,
                success=success,
                error_message=_clean(send_result.get("error")),
            )
            record_content_delivery_attempts(
                db_path,
                subscriber_id=subscriber_id,
                brief_id=int(brief_record["id"]),
                event_keys=event_keys,
                state=delivery_state,
                error=_clean(send_result.get("error")),
            )
            record_delivery_artifact(
                db_path,
                delivery_log_id=delivery_log_id,
                subscriber_id=subscriber_id,
                brief_id=int(brief_record["id"]),
                language=language if language in {"zh", "en"} else "zh",
                render_mode=_clean(send_result.get("render_mode")) or "text",
                message_ids=[str(value) for value in send_result.get("message_ids", []) if _clean(value)],
                envelope=envelope.to_dict(),
                media_asset_key=asset_key if send_result.get("render_mode") == "photo" else "",
                delivery_state=delivery_state,
            )
            if success and asset_key and _clean(send_result.get("photo_file_id")) and cover_path.is_file():
                put_telegram_media_asset(
                    db_path,
                    asset_key=asset_key,
                    file_id=_clean(send_result.get("photo_file_id")),
                    file_unique_id=_clean(send_result.get("photo_file_unique_id")),
                    mime_type="image/jpeg",
                    byte_size=cover_path.stat().st_size,
                    content_hash=asset_hash,
                )
                photo_reference = _clean(send_result.get("photo_file_id"))
            deliveries.append(
                {
                    "subscriber_id": int(recipient["subscriber_id"]),
                    "user_id_present": bool(_clean(recipient.get("user_id"))),
                    "channel_type": recipient["channel_type"],
                    "channel_user_id_present": bool(_clean(recipient.get("channel_user_id"))),
                    "matched_categories": list(recipient.get("matched_categories") or []),
                    "filtered_item_count": len(filtered_payload.get("items", []) or []),
                    "language": language,
                    "brief_ref": str(brief_record["public_ref"]),
                    "send_result": {
                        "success": success,
                        "network_calls": send_network_calls,
                        "render_mode": _clean(send_result.get("render_mode")),
                        "delivery_state": delivery_state,
                        "message_id_present": bool(send_result.get("message_ids")),
                        "error_present": bool(_clean(send_result.get("error"))),
                    },
                }
            )
        except Exception as exc:
            if not send_network_calls:
                send_network_calls = max(0, int(getattr(sender, "network_calls", before) or before) - before)
                network_calls += send_network_calls
            if not claim_finalized:
                exception_state = "unknown" if send_network_calls else "failed"
                with suppress(OSError, sqlite3.Error):
                    finalize_delivery_claim(
                        db_path,
                        subscriber_id=subscriber_id,
                        brief_date=brief_date,
                        claim_token=claim_token,
                        state=exception_state,
                        error=str(exc),
                    )
            failed += 1
            _record_delivery_log(
                db_path,
                subscriber_id=subscriber_id,
                channel_type=str(recipient["channel_type"]),
                content_summary=message,
                success=False,
                error_message=str(exc)[:500],
            )
            deliveries.append(
                {
                    "subscriber_id": int(recipient["subscriber_id"]),
                    "user_id_present": bool(_clean(recipient.get("user_id"))),
                    "channel_type": recipient["channel_type"],
                    "channel_user_id_present": bool(_clean(recipient.get("channel_user_id"))),
                    "matched_categories": list(recipient.get("matched_categories") or []),
                    "filtered_item_count": len(filtered_payload.get("items", []) or []),
                    "language": language,
                    "brief_ref": str(brief_record["public_ref"]),
                    "send_result": {"success": False, "error_present": True},
                }
            )
    return {
        "timestamp": _now_iso(),
        "status": "success" if failed == 0 else "partial_failed",
        "summary_evidence": str(summary_evidence_path),
        "source_categories": categories,
        "summary": {"eligible": len(recipients), "sent": sent, "failed": failed},
        "message_chars": message_chars,
        "deliveries": deliveries,
        "network_calls": network_calls,
        "brief_ref": str(brief_record["public_ref"]),
        "media": {
            "asset_key_present": bool(asset_key),
            "file_id_reused": bool(photo_reference),
            "upload_error_present": bool(media_upload_error),
        },
        "schedule": {
            "enforced": enforce_delivery_window,
            "not_due_count": not_due_count,
            "grace_minutes": 90,
        },
        "localization": localization_evidence,
        "limits": [
            "Recipients are filtered by active subscription, expiry, channel_type=telegram, and matching source preferences.",
            "Raw chat ids are used only in-memory for sender calls and are not returned in evidence.",
        ],
    }


def _summary_payload() -> dict[str, Any]:
    return {
        "status": "success",
        "llm": {
            "summary_text": "国会持仓与 A 股资金流摘要。",
            "model_family": "intel_local",
            "usage": {"total_tokens": 128},
        },
        "items": [
            {"source": "senate_trading", "source_label": "国会持仓", "title": "Senator Sale BYND"},
            {"source": "akshare", "source_label": "A股龙虎榜", "title": "深科技机构买入"},
            {"source": "ai_model_updates", "source_label": "AI模型动态", "title": "OpenAI frontier update"},
        ],
    }


def _seed_user(
    db_path: str | Path,
    tg_user_id: str,
    chat_id: str,
    categories: list[str],
    *,
    expires_at: str = "2026-08-07T00:00:00+00:00",
) -> None:
    subscriber = upsert_telegram_subscriber(db_path, telegram_user_id=tg_user_id, chat_id=chat_id)
    grant_subscription(
        db_path,
        user_id=subscriber["user_id"],
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at=expires_at,
        source="subscription_delivery_sandbox",
    )
    set_source_preferences(db_path, user_id=subscriber["user_id"], enabled_categories=categories)


def build_subscription_delivery_sandbox(
    output_dir: str | Path,
    *,
    now: str = "2026-07-07T18:00:00+00:00",
) -> dict[str, Any]:
    """Build sandbox evidence for subscription-filtered delivery."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "intel_subscription_delivery_sandbox.db"
    summary_path = out_dir / "summary.json"
    evidence_path = out_dir / "evidence.json"
    summary_path.write_text(json.dumps(_summary_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    upsert_subscription_plan(
        db_path,
        plan_name="intel_mvp_monthly",
        categories=["senate_trading", "akshare", "ai_model_updates"],
    )
    _seed_user(db_path, "akshare-user", "chat-" + "akshare", ["akshare"])
    _seed_user(db_path, "senate-user", "chat-" + "senate", ["senate_trading"])
    _seed_user(db_path, "ai-user", "chat-" + "ai", ["ai_model_updates"])
    _seed_user(db_path, "expired-user", "chat-" + "expired", ["akshare"], expires_at="2026-07-01T00:00:00+00:00")
    sender = FakeSubscriptionDeliverySender()
    delivery = deliver_summary_to_eligible_subscribers(
        db_path=db_path, summary_evidence_path=summary_path, sender=sender, now=now
    )
    evidence = {
        "timestamp": _now_iso(),
        "phase": "AF-subscription-filtered-delivery-sandbox",
        "scope": "summary_source_categories_to_active_preference_matched_subscribers",
        "status": delivery["status"],
        "sandbox_db": str(db_path),
        "summary_evidence": str(summary_path),
        "delivery": delivery,
        "network_calls": delivery["network_calls"],
        "redaction": {
            "channel_user_id_present_only": True,
            "raw_chat_id_written": False,
            "token_written": False,
        },
        "rollback": [str(db_path), str(summary_path), str(evidence_path)],
        "limits": [
            "Sandbox SQLite only; production intel_brief.db was not touched.",
            "Fake sender only; no Telegram Bot API call.",
            "Expired and non-matching subscribers are excluded.",
        ],
    }
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence
