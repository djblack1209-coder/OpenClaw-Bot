"""Subscription-filtered Intel Brief delivery helpers.

This module delivers a summary only to active, non-expired subscribers whose
source preferences match categories present in the summary evidence.  It keeps
raw channel ids out of returned evidence.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from src.constants import TG_SAFE_LENGTH
from src.intel.db.store import initialize_intel_db
from src.intel.delivery import build_delivery_message
from src.intel.subscriptions import (
    eligible_subscribers_for_categories,
    grant_subscription,
    set_source_preferences,
    upsert_subscription_plan,
    upsert_telegram_subscriber,
)


class SummarySender(Protocol):
    network_calls: int

    def send(self, chat_id: str, text: str, *, parse_mode: str = "HTML") -> dict[str, Any]:
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


def _recipient_summary_text(items: list[dict[str, Any]]) -> str:
    """基于过滤后的真实条目生成每位订阅者专属总览。"""
    if not items:
        return "今天没有匹配你订阅偏好的新情报。"
    labels = [
        _clean(item.get("source_label") or item.get("source")) or "其他情报"
        for item in items
    ]
    counts = Counter(labels)
    coverage = "、".join(f"{label} {count} 条" for label, count in counts.items())
    highlights = [_clip_title(item.get("title")) for item in items[:3] if _clean(item.get("title"))]
    summary = f"今天为你筛出 {len(items)} 条，覆盖 {coverage}。"
    if highlights:
        summary += f" 重点包括：{'；'.join(highlights)}。"
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
        "summary_text": _recipient_summary_text(items),
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
) -> None:
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO delivery_log (subscriber_id, content_summary, channel_type, success, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (subscriber_id, content_summary[:1000], channel_type, 1 if success else 0, error_message or None),
        )
        conn.commit()


def _redacted_send(send_result: dict[str, Any], *, network_calls: int) -> dict[str, Any]:
    return {
        "success": bool(send_result.get("success")),
        "network": _clean(send_result.get("network")),
        "network_calls": int(network_calls),
        "endpoint": _clean(send_result.get("endpoint")),
        "chat_id_present": bool(send_result.get("chat_id_present")),
        "message_id_present": bool(_clean(send_result.get("message_id"))),
        "text_chars": int(send_result.get("text_chars", 0) or 0),
        "error_code": _clean(send_result.get("error_code")),
        "error_present": bool(_clean(send_result.get("error"))),
    }


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
) -> dict[str, Any]:
    """Deliver summary to active subscribers matching summary source categories."""
    summary_payload = json.loads(Path(summary_evidence_path).read_text(encoding="utf-8"))
    categories = _source_categories(summary_payload)
    recipients = eligible_subscribers_for_categories(db_path, categories=categories, now=now)
    deliveries: list[dict[str, Any]] = []
    sent = 0
    failed = 0
    network_calls = 0
    message_chars = 0
    for recipient in recipients:
        filtered_payload = _filter_summary_payload_for_categories(
            summary_payload,
            list(recipient.get("matched_categories") or []),
        )
        message = build_delivery_message(filtered_payload, max_chars=max_chars, delivery_context="production")
        message_chars = max(message_chars, len(message))
        before = int(getattr(sender, "network_calls", 0) or 0)
        try:
            send_result = sender.send(str(recipient["channel_user_id"]), message, parse_mode="HTML")
            send_network_calls = _send_delta(sender, before, send_result)
            network_calls += send_network_calls
            success = bool(send_result.get("success"))
            sent += 1 if success else 0
            failed += 0 if success else 1
            _record_delivery_log(
                db_path,
                subscriber_id=int(recipient["subscriber_id"]),
                channel_type=str(recipient["channel_type"]),
                content_summary=message,
                success=success,
                error_message=_clean(send_result.get("error")),
            )
            deliveries.append(
                {
                    "subscriber_id": int(recipient["subscriber_id"]),
                    "user_id_present": bool(_clean(recipient.get("user_id"))),
                    "channel_type": recipient["channel_type"],
                    "channel_user_id_present": bool(_clean(recipient.get("channel_user_id"))),
                    "matched_categories": list(recipient.get("matched_categories") or []),
                    "filtered_item_count": len(filtered_payload.get("items", []) or []),
                    "send_result": _redacted_send(send_result, network_calls=send_network_calls),
                }
            )
        except Exception as exc:
            failed += 1
            _record_delivery_log(
                db_path,
                subscriber_id=int(recipient["subscriber_id"]),
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
    delivery = deliver_summary_to_eligible_subscribers(db_path=db_path, summary_evidence_path=summary_path, sender=sender, now=now)
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
