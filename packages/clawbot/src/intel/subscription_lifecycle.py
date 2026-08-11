"""Subscription lifecycle audit helpers for Intel Brief.

This module covers the commercial-MVP gap between entitlement grants and
recurring delivery: expiring subscription reminders and expired subscription
status updates.  It is intentionally opt-in for mutations and network sends so
it can be audited safely in production.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from src.intel.db.store import initialize_intel_db
from src.intel.private_env import load_private_env_file
from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE, TelegramBotApiSender, TelegramTransport

LIFECYCLE_APPLY_ACK_VALUE = "I_UNDERSTAND_INTEL_BRIEF_LIFECYCLE_APPLY"


class ReminderSender(Protocol):
    network_calls: int

    def send(self, chat_id: str, text: str, *, parse_mode: str = "HTML") -> dict[str, Any]:
        """Send one reminder and return a redacted send result."""


class FakeLifecycleSender:
    """Network-free sender for tests and evidence sandboxes."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.network_calls = 0

    def send(self, chat_id: str, text: str, *, parse_mode: str = "HTML") -> dict[str, Any]:
        self.sent.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
        return {
            "success": True,
            "network": "fake_sender",
            "network_calls": 0,
            "endpoint": "fake://telegram/sendMessage",
            "chat_id_present": bool(_clean(chat_id)),
            "message_id": f"fake-lifecycle-{len(self.sent)}",
            "text_chars": len(text),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _redacted_lifecycle_env(env: dict[str, str]) -> dict[str, bool]:
    return {
        "INTEL_BRIEF_DB_PATH": bool(_clean(env.get("INTEL_BRIEF_DB_PATH"))),
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": bool(_clean(env.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN"))),
        "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": _clean(env.get("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK"))
        == TELEGRAM_SANDBOX_ACK_VALUE,
        "INTEL_BRIEF_SUBSCRIPTION_LIFECYCLE_APPLY_ACK": _clean(
            env.get("INTEL_BRIEF_SUBSCRIPTION_LIFECYCLE_APPLY_ACK")
        )
        == LIFECYCLE_APPLY_ACK_VALUE,
    }


def _load_env_map(env: dict[str, str] | None, *, env_path: str | Path | None = None) -> dict[str, str]:
    values = dict(env or {})
    if env_path:
        values = {**load_private_env_file(env_path), **values}
    return values


def _resolve_db_path(db_path: str | Path, *, env: dict[str, str], project_root: str | Path | None = None) -> Path:
    selected = _clean(db_path) or _clean(env.get("INTEL_BRIEF_DB_PATH"))
    if not selected:
        selected = "packages/clawbot/data/intel_brief.db"
    path = Path(selected)
    if not path.is_absolute() and project_root is not None:
        path = Path(project_root) / path
    return path


def _lifecycle_gate(
    *,
    env: dict[str, str],
    apply_expiry: bool,
    send_reminders: bool,
    allow_real_network: bool,
) -> dict[str, Any]:
    redacted = _redacted_lifecycle_env(env)
    missing: list[str] = []
    if apply_expiry and not redacted["INTEL_BRIEF_SUBSCRIPTION_LIFECYCLE_APPLY_ACK"]:
        missing.append("lifecycle_apply_ack_missing")
    if send_reminders:
        if not redacted["INTEL_BRIEF_TELEGRAM_BOT_TOKEN"]:
            missing.append("telegram_bot_token_missing")
        if not redacted["INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK"]:
            missing.append("telegram_runtime_ack_missing")
        if not allow_real_network:
            missing.append("real_network_not_allowed")
    return {
        "status": "ready" if not missing else "blocked",
        "ready": not missing,
        "missing_gates": missing,
        "redacted_env": {
            **redacted,
            "allow_real_network": bool(allow_real_network),
        },
    }


def _parse_dt(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)  # noqa: UP017
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    return parsed.astimezone(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility


def _now_dt(now: str | datetime) -> datetime:
    if isinstance(now, datetime):
        parsed = now
    else:
        parsed = _parse_dt(now)
        if parsed is None:
            raise ValueError(f"invalid_now: {now}")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    return parsed.astimezone(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility


def _active_subscription_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return list(
        conn.execute(
            """
            SELECT
                us.id AS subscription_id,
                us.subscriber_id,
                us.starts_at,
                us.expires_at,
                us.status AS subscription_status,
                sp.plan_name,
                s.user_id,
                s.channel_type,
                s.channel_user_id,
                s.status AS subscriber_status
            FROM user_subscriptions us
            JOIN subscription_plans sp ON sp.id=us.plan_id
            JOIN subscribers s ON s.id=us.subscriber_id
            WHERE us.status='active'
            ORDER BY us.id
            """
        ).fetchall()
    )


def _safe_subscription(row: sqlite3.Row, *, now_value: datetime) -> dict[str, Any]:
    expires_at = _parse_dt(row["expires_at"])
    days_until_expiry = None
    if expires_at is not None:
        days_until_expiry = (expires_at - now_value).days
    return {
        "subscription_id": int(row["subscription_id"]),
        "subscriber_id": int(row["subscriber_id"]),
        "plan_name": str(row["plan_name"]),
        "channel_type": str(row["channel_type"]),
        "channel_user_id_present": bool(_clean(row["channel_user_id"])),
        "user_id_present": bool(_clean(row["user_id"])),
        "starts_at": str(row["starts_at"] or ""),
        "expires_at": str(row["expires_at"] or ""),
        "days_until_expiry": days_until_expiry,
    }


def _audit_exists(
    conn: sqlite3.Connection,
    *,
    subscriber_id: int,
    plan_name: str,
    event_type: str,
    day: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM subscription_audit_log
        WHERE subscriber_id=?
          AND plan_name=?
          AND event_type=?
          AND substr(event_time, 1, 10)=?
        LIMIT 1
        """,
        (subscriber_id, plan_name, event_type, day),
    ).fetchone()
    return row is not None


def _write_audit(
    conn: sqlite3.Connection,
    *,
    subscriber_id: int,
    plan_name: str,
    event_type: str,
    source: str,
    now_value: datetime,
) -> bool:
    day = now_value.date().isoformat()
    if _audit_exists(conn, subscriber_id=subscriber_id, plan_name=plan_name, event_type=event_type, day=day):
        return False
    conn.execute(
        """
        INSERT INTO subscription_audit_log (subscriber_id, plan_name, event_type, source, event_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (subscriber_id, plan_name, event_type, source, now_value.isoformat()),
    )
    return True


def _reminder_text(row: sqlite3.Row, *, now_value: datetime) -> str:
    expires_at = _parse_dt(row["expires_at"])
    days = "未知"
    if expires_at is not None:
        remaining = max(0, (expires_at - now_value).days)
        days = str(remaining)
    return "\n".join(
        [
            "⏰ 情报简报订阅即将到期",
            f"套餐：{row['plan_name']}",
            f"到期时间：{row['expires_at'] or '未设置'}",
            f"剩余天数：{days}",
            "如需续费，请联系运营者或按购买渠道续订。",
        ]
    )


def _send_delta(sender: ReminderSender, before: int, send_result: dict[str, Any]) -> int:
    after = int(getattr(sender, "network_calls", before) or before)
    if after > before:
        return after - before
    return int(send_result.get("network_calls", 0) or 0)


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


def audit_subscription_lifecycle(
    *,
    db_path: str | Path,
    now: str | datetime,
    reminder_days: int = 7,
    apply_expiry: bool = False,
    send_reminders: bool = False,
    sender: ReminderSender | None = None,
    source: str = "subscription_lifecycle",
) -> dict[str, Any]:
    """Audit expiring/expired subscriptions and optionally mutate/send reminders.

    Default behavior is read-only against subscription rows except for no-op DB
    initialization.  Set ``apply_expiry=True`` to mark active expired rows as
    ``expired`` and write audit events.  Set ``send_reminders=True`` with a
    sender to notify expiring Telegram subscribers and write reminder audit
    events once per subscriber/plan/day.
    """
    initialize_intel_db(db_path)
    now_value = _now_dt(now)
    reminder_window_end = now_value + timedelta(days=max(0, int(reminder_days)))
    expired: list[dict[str, Any]] = []
    expiring: list[dict[str, Any]] = []
    marked_expired = 0
    reminder_candidates = 0
    reminders_sent = 0
    reminders_skipped = 0
    audit_events_written = 0
    network_calls = 0
    reminder_deliveries: list[dict[str, Any]] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = _active_subscription_rows(conn)
        for row in rows:
            expires_at = _parse_dt(row["expires_at"])
            if expires_at is None:
                continue
            safe = _safe_subscription(row, now_value=now_value)
            if expires_at <= now_value:
                expired.append(safe)
                if apply_expiry:
                    conn.execute("UPDATE user_subscriptions SET status='expired' WHERE id=?", (row["subscription_id"],))
                    marked_expired += 1
                    if _write_audit(
                        conn,
                        subscriber_id=int(row["subscriber_id"]),
                        plan_name=str(row["plan_name"]),
                        event_type="expired",
                        source=source,
                        now_value=now_value,
                    ):
                        audit_events_written += 1
                continue
            if now_value < expires_at <= reminder_window_end:
                reminder_candidates += 1
                event_type = f"expiry_reminder_{int(reminder_days)}d"
                already_sent = _audit_exists(
                    conn,
                    subscriber_id=int(row["subscriber_id"]),
                    plan_name=str(row["plan_name"]),
                    event_type=event_type,
                    day=now_value.date().isoformat(),
                )
                expiring_item = {**safe, "reminder_already_recorded_today": already_sent}
                expiring.append(expiring_item)
                if already_sent:
                    reminders_skipped += 1
                    continue
                if send_reminders:
                    if sender is None:
                        reminders_skipped += 1
                        reminder_deliveries.append(
                            {
                                "subscriber_id": int(row["subscriber_id"]),
                                "channel_type": str(row["channel_type"]),
                                "channel_user_id_present": bool(_clean(row["channel_user_id"])),
                                "send_result": {"success": False, "error_present": True, "error_code": "sender_missing"},
                            }
                        )
                        continue
                    before = int(getattr(sender, "network_calls", 0) or 0)
                    send_result = sender.send(str(row["channel_user_id"]), _reminder_text(row, now_value=now_value), parse_mode="HTML")
                    delta = _send_delta(sender, before, send_result)
                    network_calls += delta
                    success = bool(send_result.get("success"))
                    if success:
                        reminders_sent += 1
                        if _write_audit(
                            conn,
                            subscriber_id=int(row["subscriber_id"]),
                            plan_name=str(row["plan_name"]),
                            event_type=event_type,
                            source=source,
                            now_value=now_value,
                        ):
                            audit_events_written += 1
                    else:
                        reminders_skipped += 1
                    reminder_deliveries.append(
                        {
                            "subscriber_id": int(row["subscriber_id"]),
                            "channel_type": str(row["channel_type"]),
                            "channel_user_id_present": bool(_clean(row["channel_user_id"])),
                            "send_result": _redacted_send(send_result, network_calls=delta),
                        }
                    )
                else:
                    reminders_skipped += 1
        conn.commit()

    return {
        "timestamp": _now_iso(),
        "status": "success",
        "now": now_value.isoformat(),
        "reminder_days": int(reminder_days),
        "apply_expiry": bool(apply_expiry),
        "send_reminders": bool(send_reminders),
        "summary": {
            "expired_active_found": len(expired),
            "expiring_active_found": len(expiring),
            "reminder_candidates": reminder_candidates,
            "marked_expired": marked_expired,
            "reminders_sent": reminders_sent,
            "reminders_skipped": reminders_skipped,
            "audit_events_written": audit_events_written,
        },
        "expired": expired,
        "expiring": expiring,
        "reminder_deliveries": reminder_deliveries,
        "network_calls": network_calls,
        "limits": [
            "Raw channel ids and user ids are not returned; only presence flags are recorded.",
            "No subscription status is changed unless apply_expiry=True.",
            "No reminder is sent unless send_reminders=True and a sender is provided.",
            "Reminder audit events are de-duplicated per subscriber/plan/day.",
        ],
    }


def run_subscription_lifecycle_maintenance(
    *,
    now: str | datetime,
    db_path: str | Path = "",
    env: dict[str, str] | None = None,
    env_path: str | Path | None = None,
    project_root: str | Path | None = None,
    reminder_days: int = 7,
    apply_expiry: bool = False,
    send_reminders: bool = False,
    allow_real_network: bool = False,
    transport: TelegramTransport | None = None,
    source: str = "subscription_lifecycle_maintenance",
) -> dict[str, Any]:
    """Run production-safe lifecycle maintenance with explicit mutation gates.

    The default mode is read-only.  Expiry mutation requires
    ``INTEL_BRIEF_SUBSCRIPTION_LIFECYCLE_APPLY_ACK``.  Telegram reminders also
    require token + Telegram runtime ack + explicit network allowance.
    """
    env_map = _load_env_map(env, env_path=env_path)
    resolved_db = _resolve_db_path(db_path, env=env_map, project_root=project_root)
    gate = _lifecycle_gate(
        env=env_map,
        apply_expiry=apply_expiry,
        send_reminders=send_reminders,
        allow_real_network=allow_real_network,
    )
    base = {
        "timestamp": _now_iso(),
        "phase": "BC-subscription-lifecycle-maintenance",
        "scope": "production_safe_expiry_marking_and_reminders",
        "db_path": str(resolved_db),
        "gate": gate,
        "requested": {
            "apply_expiry": bool(apply_expiry),
            "send_reminders": bool(send_reminders),
            "reminder_days": int(reminder_days),
        },
    }
    if not gate["ready"]:
        return {
            **base,
            "status": "blocked",
            "audit": None,
            "network_calls": 0,
            "limits": [
                "Blocked before lifecycle audit because a requested mutation/send gate is missing.",
                "Token/chat id values are represented only by presence booleans.",
            ],
        }

    sender: ReminderSender | None = None
    if send_reminders:
        sender = TelegramBotApiSender(token=_clean(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN")), transport=transport)
    audit = audit_subscription_lifecycle(
        db_path=resolved_db,
        now=now,
        reminder_days=reminder_days,
        apply_expiry=apply_expiry,
        send_reminders=send_reminders,
        sender=sender,
        source=source,
    )
    return {
        **base,
        "status": audit.get("status", "success"),
        "audit": audit,
        "network_calls": int(audit.get("network_calls", 0) or 0),
        "limits": [
            "Default run is read-only unless apply_expiry/send_reminders are explicitly requested and gated.",
            "Reminder audit events are de-duplicated per subscriber/plan/day.",
            "No payment provider, marketplace automation, scraper, remote worker, or LaunchAgent operation is performed.",
            "Raw Telegram token/chat id/user id values are not returned.",
        ],
    }


def build_subscription_lifecycle_sandbox(
    output_dir: str | Path,
    *,
    now: str = "2026-07-07T18:30:00+00:00",
) -> dict[str, Any]:
    """Build sandbox evidence for expiry marking and reminder sending."""
    from src.intel.subscriptions import grant_subscription, upsert_subscription_plan, upsert_telegram_subscriber

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "intel_subscription_lifecycle_sandbox.db"
    evidence_path = out_dir / "evidence.json"
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare"], duration_type="monthly")
    active = upsert_telegram_subscriber(db_path, telegram_user_id="active-user", chat_id="chat-active")
    expiring = upsert_telegram_subscriber(db_path, telegram_user_id="expiring-user", chat_id="chat-expiring")
    expired = upsert_telegram_subscriber(db_path, telegram_user_id="expired-user", chat_id="chat-expired")
    grant_subscription(db_path, user_id=active["user_id"], plan_name="intel_mvp_monthly", starts_at="2026-07-01T00:00:00+00:00", expires_at="2026-08-01T00:00:00+00:00")
    grant_subscription(db_path, user_id=expiring["user_id"], plan_name="intel_mvp_monthly", starts_at="2026-07-01T00:00:00+00:00", expires_at="2026-07-10T00:00:00+00:00")
    grant_subscription(db_path, user_id=expired["user_id"], plan_name="intel_mvp_monthly", starts_at="2026-06-01T00:00:00+00:00", expires_at="2026-07-01T00:00:00+00:00")
    sender = FakeLifecycleSender()
    audit = audit_subscription_lifecycle(
        db_path=db_path,
        now=now,
        reminder_days=7,
        apply_expiry=True,
        send_reminders=True,
        sender=sender,
        source="subscription_lifecycle_sandbox",
    )
    replay = audit_subscription_lifecycle(
        db_path=db_path,
        now=now,
        reminder_days=7,
        apply_expiry=True,
        send_reminders=True,
        sender=sender,
        source="subscription_lifecycle_sandbox",
    )
    evidence = {
        "timestamp": _now_iso(),
        "phase": "AN-subscription-lifecycle-sandbox",
        "scope": "expiry_marking_and_deduplicated_expiry_reminder_contract",
        "status": "success" if audit["summary"]["marked_expired"] == 1 and audit["summary"]["reminders_sent"] == 1 else "failed",
        "sandbox_db": str(db_path),
        "audit": audit,
        "replay_summary": replay["summary"],
        "network_calls": audit["network_calls"] + replay["network_calls"],
        "redaction": {
            "raw_chat_id_written": False,
            "raw_user_id_written": False,
            "telegram_token_written": False,
        },
        "rollback": [str(db_path), str(evidence_path)],
        "limits": [
            "Sandbox SQLite only; production intel_brief.db is not touched.",
            "Fake sender only; no Telegram Bot API call.",
            "Replay proves same-day reminder de-duplication.",
        ],
    }
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence
