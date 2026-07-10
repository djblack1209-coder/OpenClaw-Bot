"""Intel Brief delivery sandbox.

This module verifies the subscriber/delivery layer without touching the real
Telegram Bot API. It writes to a sandbox SQLite DB and a JSONL fake outbox, then
produces evidence that can be deleted as rollback.
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.constants import TG_SAFE_LENGTH
from src.intel.db.store import initialize_intel_db

DEFAULT_SANDBOX_USER_ID = "intel-brief-sandbox-user"
DEFAULT_SANDBOX_CHAT_ID = "intel-brief-sandbox-chat"
DEFAULT_PLAN_NAME = "intel-brief-sandbox-plan"
DEFAULT_CATEGORIES = ["senate_trading", "akshare"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _truncate(text: str, max_chars: int) -> str:
    """按完整行截断 Telegram 文本，避免切断 HTML 实体。"""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    marker = "\n…其余内容已省略"
    keep = max(0, max_chars - len(marker))
    candidate = text[:keep].rstrip()
    last_newline = candidate.rfind("\n")
    if last_newline >= int(keep * 0.55):
        candidate = candidate[:last_newline].rstrip()
    if candidate.rfind("&") > candidate.rfind(";"):
        candidate = candidate[: candidate.rfind("&")].rstrip()
    return candidate + marker


def _normalize_summary_text(value: Any) -> str:
    """清理 LLM Markdown 痕迹，输出 Telegram 可直接阅读的纯文本。"""
    cleaned = _clean(value)
    if not cleaned:
        return "本次没有摘要内容。"
    lines: list[str] = []
    for raw_line in cleaned.splitlines():
        line = re.sub(r"^#{1,6}\s*", "", raw_line.strip())
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"^[-*]\s+", "• ", line)
        if line:
            lines.append(line)
    return "\n".join(lines) or "本次没有摘要内容。"


def _display_date(summary_payload: dict[str, Any]) -> str:
    """把证据时间转换成用户友好的月日。"""
    raw = _clean(summary_payload.get("timestamp"))
    if not raw:
        return "今日"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return "今日"
    return f"{parsed.month}月{parsed.day}日"


def _summary_detail(item: dict[str, Any]) -> str:
    """优先展示条目的摘要行，避免把内部链接和 worker 信息塞给用户。"""
    details = item.get("detail_lines") if isinstance(item.get("detail_lines"), list) else []
    for detail in details:
        cleaned = _clean(detail)
        if cleaned.startswith("摘要："):
            return cleaned[:140]
    return ""


def seed_sandbox_subscriber(
    db_path: str | Path,
    *,
    user_id: str = DEFAULT_SANDBOX_USER_ID,
    channel_user_id: str = DEFAULT_SANDBOX_CHAT_ID,
    channel_type: str = "telegram",
    categories: list[str] | None = None,
    plan_name: str = DEFAULT_PLAN_NAME,
) -> dict[str, Any]:
    """Create a sandbox subscriber, plan, active subscription and preferences."""
    initialize_intel_db(db_path)
    categories = categories or DEFAULT_CATEGORIES
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO subscribers (user_id, channel_type, channel_user_id, status, updated_at)
            VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                channel_type=excluded.channel_type,
                channel_user_id=excluded.channel_user_id,
                status='active',
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, channel_type, channel_user_id),
        )
        subscriber_id = int(conn.execute("SELECT id FROM subscribers WHERE user_id=?", (user_id,)).fetchone()[0])
        conn.execute(
            """
            INSERT INTO subscription_plans (plan_name, categories, price_cents, duration_type)
            VALUES (?, ?, 0, 'sandbox')
            ON CONFLICT(plan_name) DO UPDATE SET categories=excluded.categories
            """,
            (plan_name, json.dumps(categories, ensure_ascii=False)),
        )
        plan_id = int(conn.execute("SELECT id FROM subscription_plans WHERE plan_name=?", (plan_name,)).fetchone()[0])
        conn.execute(
            """
            INSERT INTO user_subscriptions (subscriber_id, plan_id, starts_at, status)
            VALUES (?, ?, CURRENT_TIMESTAMP, 'active')
            """,
            (subscriber_id, plan_id),
        )
        for category in categories:
            conn.execute(
                """
                INSERT INTO source_preferences (subscriber_id, category, enabled, updated_at)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(subscriber_id, category) DO UPDATE SET enabled=1, updated_at=CURRENT_TIMESTAMP
                """,
                (subscriber_id, category),
            )
        conn.commit()
    return {
        "subscriber_id": subscriber_id,
        "plan_id": plan_id,
        "user_id": user_id,
        "channel_type": channel_type,
        "channel_user_id": channel_user_id,
        "categories": categories,
    }


def _eligible_subscribers(db_path: str | Path) -> list[dict[str, Any]]:
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT s.id, s.user_id, s.channel_type, s.channel_user_id
            FROM subscribers s
            JOIN user_subscriptions us ON us.subscriber_id=s.id
            WHERE s.status='active'
              AND us.status='active'
              AND s.channel_type='telegram'
              AND (us.expires_at IS NULL OR us.expires_at > CURRENT_TIMESTAMP)
            ORDER BY s.id
            """
        ).fetchall()
    return [
        {
            "subscriber_id": int(row[0]),
            "user_id": str(row[1]),
            "channel_type": str(row[2]),
            "channel_user_id": str(row[3]),
        }
        for row in rows
    ]


def build_delivery_message(
    summary_payload: dict[str, Any],
    *,
    max_chars: int = TG_SAFE_LENGTH,
    delivery_context: str = "production",
) -> str:
    """把摘要证据渲染为用户可扫读、可降级的 Telegram 简报。"""
    llm = summary_payload.get("llm", {}) if isinstance(summary_payload.get("llm"), dict) else {}
    usage = llm.get("usage", {}) if isinstance(llm.get("usage"), dict) else {}
    summary_text = _normalize_summary_text(llm.get("summary_text"))
    family = _clean(llm.get("model_family")) or "unknown"
    status = _clean(summary_payload.get("status")) or "unknown"
    items = [item for item in summary_payload.get("items", []) if isinstance(item, dict)]
    item_lines: list[str] = []
    for index, item in enumerate(items[:8], start=1):
        label = html.escape(_clean(item.get("source_label") or item.get("source")) or "情报")
        title = html.escape(_clean(item.get("title")) or "未命名情报")
        item_lines.append(f"{index}. 【{label}】{title}")
        detail = _summary_detail(item)
        if detail:
            item_lines.append(f"   ↳ {html.escape(detail)}")
    hidden_count = max(0, len(items) - 8)
    if hidden_count:
        item_lines.append(f"另有 {hidden_count} 条未展开，可回复 700 查看最近简报。")

    sandbox = _clean(delivery_context).lower() == "sandbox"
    if sandbox:
        message = "\n".join(
            [
                "🧭 Intel Brief 摘要沙盒",
                f"状态：{status}；LLM：{family}；tokens={usage.get('total_tokens', 0)}",
                "",
                html.escape(summary_text),
                "",
                "输入条目：",
                *(item_lines or ["- 无"]),
                "",
                "边界：sandbox fake Telegram sender；未调用真实 Bot API。",
            ]
        )
        return _truncate(message, min(max_chars, TG_SAFE_LENGTH))

    fallback_active = status == "partial_fallback" or llm.get("llm_success") is False
    footer_lines = []
    if fallback_active:
        footer_lines.append("ℹ️ AI精炼暂时不可用，已切换稳定整理模式；来源和筛选结果不受影响。")
    footer_lines.extend(
        [
            "回复 706 + 名称添加追踪｜回复 701 查看订阅",
            "提示：内容来自公开来源自动汇总，不构成投资建议。",
        ]
    )
    message = "\n".join(
        [
            "🧭 今日情报简报",
            f"{_display_date(summary_payload)} · 为你精选 {len(items)} 条",
            "",
            "今日重点",
            html.escape(summary_text),
            "",
            f"📌 精选情报（{len(items)}条）",
            *(item_lines or ["今天没有匹配你订阅偏好的新情报。"]),
            "",
            *footer_lines,
        ]
    )
    return _truncate(message, min(max_chars, TG_SAFE_LENGTH))


class FakeTelegramSender:
    """Fake Telegram sender that writes JSONL and never performs network calls."""

    provider = "fake_telegram"

    def __init__(self, outbox_path: str | Path) -> None:
        self.outbox_path = Path(outbox_path)
        self.network_calls = 0

    def send(self, channel_user_id: str, text: str, *, parse_mode: str = "HTML") -> dict[str, Any]:
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": _now_iso(),
            "provider": self.provider,
            "message_id": f"fake-{uuid.uuid4().hex[:12]}",
            "channel_user_id": str(channel_user_id),
            "parse_mode": parse_mode,
            "text": text,
            "text_chars": len(text),
            "network": "not_called",
            "success": True,
        }
        with self.outbox_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return payload


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


def deliver_summary_to_subscribers(
    *,
    db_path: str | Path,
    summary_evidence_path: str | Path,
    sender: FakeTelegramSender,
    max_chars: int = TG_SAFE_LENGTH,
) -> dict[str, Any]:
    """Deliver a summary evidence to active sandbox subscribers through a sender."""
    summary_payload = json.loads(Path(summary_evidence_path).read_text(encoding="utf-8"))
    message = build_delivery_message(summary_payload, max_chars=max_chars, delivery_context="sandbox")
    targets = _eligible_subscribers(db_path)
    deliveries: list[dict[str, Any]] = []
    sent = 0
    failed = 0
    for target in targets:
        try:
            send_result = sender.send(target["channel_user_id"], message, parse_mode="HTML")
            success = bool(send_result.get("success"))
            if success:
                sent += 1
            else:
                failed += 1
            _record_delivery_log(
                db_path,
                subscriber_id=int(target["subscriber_id"]),
                channel_type=target["channel_type"],
                content_summary=message,
                success=success,
                error_message=_clean(send_result.get("error")),
            )
            deliveries.append({"target": target, "send_result": send_result})
        except Exception as exc:  # keep sandbox evidence rather than raising mid-run
            failed += 1
            _record_delivery_log(
                db_path,
                subscriber_id=int(target["subscriber_id"]),
                channel_type=target["channel_type"],
                content_summary=message,
                success=False,
                error_message=str(exc)[:500],
            )
            deliveries.append({"target": target, "send_result": {"success": False, "error": str(exc)[:500]}})
    return {
        "status": "success" if failed == 0 else "partial_failed",
        "summary": {"eligible": len(targets), "sent": sent, "failed": failed},
        "message_chars": len(message),
        "deliveries": deliveries,
    }


def _delivery_log_count(db_path: str | Path) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM delivery_log").fetchone()[0])


def build_delivery_sandbox(
    *,
    summary_evidence_path: str | Path,
    db_path: str | Path,
    outbox_path: str | Path,
    evidence_path: str | Path,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Run subscriber + fake Telegram delivery sandbox and write evidence."""
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017 - Python 3.10 worker compatibility
    subscriber = seed_sandbox_subscriber(db_path)
    sender = FakeTelegramSender(outbox_path)
    delivery = deliver_summary_to_subscribers(
        db_path=db_path,
        summary_evidence_path=summary_evidence_path,
        sender=sender,
    )
    result = {
        "timestamp": _now_iso(),
        "stamp": stamp,
        "phase": "H-delivery-sandbox",
        "scope": "subscriber_fake_telegram_delivery",
        "status": delivery["status"],
        "summary_evidence": str(summary_evidence_path),
        "sandbox_db": str(db_path),
        "fake_outbox": str(outbox_path),
        "evidence_path": str(evidence_path),
        "subscriber": subscriber,
        "delivery": delivery,
        "delivery_log_count": _delivery_log_count(db_path),
        "fake_sender": True,
        "network_calls": sender.network_calls,
        "rollback": [str(db_path), str(outbox_path), str(evidence_path)],
        "limits": [
            "Fake Telegram sender only; real Bot API was not called.",
            "Sandbox SQLite DB only; production DB was not touched.",
            "No scheduler, cron, systemd, or persistent service was registered.",
            "Delete rollback paths to remove all artifacts from this sandbox run.",
        ],
    }
    path = Path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
