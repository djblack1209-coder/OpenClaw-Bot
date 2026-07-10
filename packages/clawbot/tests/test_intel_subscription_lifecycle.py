from __future__ import annotations

import json
import sqlite3

from src.intel.subscription_lifecycle import FakeLifecycleSender, audit_subscription_lifecycle
from src.intel.subscriptions import grant_subscription, upsert_subscription_plan, upsert_telegram_subscriber

NOW = "2026-07-07T18:30:00+00:00"


def _seed(db_path):
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare"], duration_type="monthly")
    active = upsert_telegram_subscriber(db_path, telegram_user_id="active-user", chat_id="chat-active")
    expiring = upsert_telegram_subscriber(db_path, telegram_user_id="expiring-user", chat_id="chat-expiring")
    expired = upsert_telegram_subscriber(db_path, telegram_user_id="expired-user", chat_id="chat-expired")
    grant_subscription(
        db_path,
        user_id=active["user_id"],
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-01T00:00:00+00:00",
        expires_at="2026-08-01T00:00:00+00:00",
        source="lifecycle_test",
    )
    grant_subscription(
        db_path,
        user_id=expiring["user_id"],
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-01T00:00:00+00:00",
        expires_at="2026-07-10T00:00:00+00:00",
        source="lifecycle_test",
    )
    grant_subscription(
        db_path,
        user_id=expired["user_id"],
        plan_name="intel_mvp_monthly",
        starts_at="2026-06-01T00:00:00+00:00",
        expires_at="2026-07-01T00:00:00+00:00",
        source="lifecycle_test",
    )


def test_subscription_lifecycle_default_audit_is_read_only_and_redacted(tmp_path):
    db_path = tmp_path / "lifecycle.db"
    _seed(db_path)

    result = audit_subscription_lifecycle(db_path=db_path, now=NOW, reminder_days=7)

    assert result["status"] == "success"
    assert result["summary"] == {
        "expired_active_found": 1,
        "expiring_active_found": 1,
        "reminder_candidates": 1,
        "marked_expired": 0,
        "reminders_sent": 0,
        "reminders_skipped": 1,
        "audit_events_written": 0,
    }
    public_text = json.dumps(result, ensure_ascii=False)
    assert "chat-expiring" not in public_text
    assert "tg:expiring-user" not in public_text
    assert result["expired"][0]["channel_user_id_present"] is True
    assert result["expiring"][0]["user_id_present"] is True

    with sqlite3.connect(db_path) as conn:
        statuses = [row[0] for row in conn.execute("SELECT status FROM user_subscriptions ORDER BY id")]
        lifecycle_audits = conn.execute(
            "SELECT COUNT(*) FROM subscription_audit_log WHERE event_type IN ('expired', 'expiry_reminder_7d')"
        ).fetchone()[0]
    assert statuses == ["active", "active", "active"]
    assert lifecycle_audits == 0


def test_subscription_lifecycle_can_mark_expired_and_send_deduped_reminder(tmp_path):
    db_path = tmp_path / "lifecycle.db"
    _seed(db_path)
    sender = FakeLifecycleSender()

    first = audit_subscription_lifecycle(
        db_path=db_path,
        now=NOW,
        reminder_days=7,
        apply_expiry=True,
        send_reminders=True,
        sender=sender,
        source="lifecycle_test",
    )
    second = audit_subscription_lifecycle(
        db_path=db_path,
        now=NOW,
        reminder_days=7,
        apply_expiry=True,
        send_reminders=True,
        sender=sender,
        source="lifecycle_test",
    )

    assert first["summary"]["marked_expired"] == 1
    assert first["summary"]["reminders_sent"] == 1
    assert first["summary"]["audit_events_written"] == 2
    assert first["network_calls"] == 0
    assert len(sender.sent) == 1
    assert sender.sent[0]["chat_id"] == "chat-expiring"
    assert "即将到期" in sender.sent[0]["text"]
    assert second["summary"]["marked_expired"] == 0
    assert second["summary"]["reminders_sent"] == 0
    assert second["summary"]["reminders_skipped"] == 1
    assert len(sender.sent) == 1

    with sqlite3.connect(db_path) as conn:
        statuses = [row[0] for row in conn.execute("SELECT status FROM user_subscriptions ORDER BY id")]
        audit_rows = conn.execute(
            "SELECT event_type, COUNT(*) FROM subscription_audit_log WHERE event_type IN ('expired', 'expiry_reminder_7d') GROUP BY event_type ORDER BY event_type"
        ).fetchall()
    assert statuses == ["active", "active", "expired"]
    assert audit_rows == [("expired", 1), ("expiry_reminder_7d", 1)]


def test_subscription_lifecycle_sandbox_evidence_is_redacted(tmp_path):
    from src.intel.subscription_lifecycle import build_subscription_lifecycle_sandbox

    evidence = build_subscription_lifecycle_sandbox(tmp_path / "evidence", now=NOW)

    assert evidence["status"] == "success"
    assert evidence["audit"]["summary"]["marked_expired"] == 1
    assert evidence["audit"]["summary"]["reminders_sent"] == 1
    assert evidence["replay_summary"]["reminders_sent"] == 0
    saved = (tmp_path / "evidence" / "evidence.json").read_text(encoding="utf-8")
    assert "chat-expiring" not in saved
    assert "chat-expired" not in saved
    assert "tg:expiring-user" not in saved
    assert "tg:expired-user" not in saved


def test_subscription_lifecycle_maintenance_defaults_to_read_only(tmp_path):
    from src.intel.subscription_lifecycle import run_subscription_lifecycle_maintenance

    db_path = tmp_path / "lifecycle.db"
    _seed(db_path)

    result = run_subscription_lifecycle_maintenance(db_path=db_path, env={}, now=NOW)

    assert result["status"] == "success"
    assert result["gate"]["status"] == "ready"
    assert result["requested"] == {"apply_expiry": False, "send_reminders": False, "reminder_days": 7}
    assert result["audit"]["summary"]["expired_active_found"] == 1
    assert result["audit"]["summary"]["marked_expired"] == 0
    assert result["audit"]["summary"]["reminders_sent"] == 0

    with sqlite3.connect(db_path) as conn:
        statuses = [row[0] for row in conn.execute("SELECT status FROM user_subscriptions ORDER BY id")]
    assert statuses == ["active", "active", "active"]


def test_subscription_lifecycle_maintenance_blocks_apply_without_ack(tmp_path):
    from src.intel.subscription_lifecycle import run_subscription_lifecycle_maintenance

    db_path = tmp_path / "lifecycle.db"
    _seed(db_path)

    result = run_subscription_lifecycle_maintenance(db_path=db_path, env={}, now=NOW, apply_expiry=True)

    assert result["status"] == "blocked"
    assert result["gate"]["missing_gates"] == ["lifecycle_apply_ack_missing"]
    assert result["audit"] is None

    with sqlite3.connect(db_path) as conn:
        statuses = [row[0] for row in conn.execute("SELECT status FROM user_subscriptions ORDER BY id")]
    assert statuses == ["active", "active", "active"]


def test_subscription_lifecycle_maintenance_can_apply_with_ack(tmp_path):
    from src.intel.subscription_lifecycle import LIFECYCLE_APPLY_ACK_VALUE, run_subscription_lifecycle_maintenance

    db_path = tmp_path / "lifecycle.db"
    _seed(db_path)

    result = run_subscription_lifecycle_maintenance(
        db_path=db_path,
        env={"INTEL_BRIEF_SUBSCRIPTION_LIFECYCLE_APPLY_ACK": LIFECYCLE_APPLY_ACK_VALUE},
        now=NOW,
        apply_expiry=True,
    )

    assert result["status"] == "success"
    assert result["audit"]["summary"]["marked_expired"] == 1
    assert result["network_calls"] == 0

    with sqlite3.connect(db_path) as conn:
        statuses = [row[0] for row in conn.execute("SELECT status FROM user_subscriptions ORDER BY id")]
    assert statuses == ["active", "active", "expired"]


def test_subscription_lifecycle_maintenance_sends_reminders_with_injected_transport(tmp_path):
    from src.intel.subscription_lifecycle import run_subscription_lifecycle_maintenance
    from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE

    db_path = tmp_path / "lifecycle.db"
    _seed(db_path)
    calls: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        return {"ok": True, "result": {"message_id": 7001}}

    result = run_subscription_lifecycle_maintenance(
        db_path=db_path,
        env={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "fake-lifecycle-token",
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        },
        now=NOW,
        send_reminders=True,
        allow_real_network=True,
        transport=transport,
    )

    assert result["status"] == "success"
    assert result["audit"]["summary"]["reminders_sent"] == 1
    assert result["network_calls"] == 1
    assert calls[0]["payload"]["chat_id"] == "chat-expiring"
    public_text = json.dumps(result, ensure_ascii=False)
    assert "chat-expiring" not in public_text
    assert "fake-lifecycle-token" not in public_text


def test_subscription_lifecycle_cli_writes_readonly_evidence(tmp_path):
    from scripts.intel_subscription_lifecycle import main

    db_path = tmp_path / "lifecycle.db"
    evidence = tmp_path / "lifecycle-evidence.json"
    _seed(db_path)

    exit_code = main(
        [
            "--db",
            str(db_path),
            "--env-path",
            "",
            "--now",
            NOW,
            "--evidence",
            str(evidence),
        ]
    )

    assert exit_code == 0
    saved = json.loads(evidence.read_text(encoding="utf-8"))
    assert saved["status"] == "success"
    assert saved["requested"] == {"apply_expiry": False, "send_reminders": False, "reminder_days": 7}
    assert saved["audit"]["summary"]["marked_expired"] == 0
