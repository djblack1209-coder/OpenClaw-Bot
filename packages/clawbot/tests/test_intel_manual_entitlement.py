from __future__ import annotations

import json
import sqlite3

from src.intel.manual_entitlement import build_manual_entitlement_sandbox, grant_manual_entitlement
from src.intel.subscriptions import get_subscription_profile


def _counts(db_path):
    with sqlite3.connect(db_path) as conn:
        return {
            "subscribers": conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0],
            "subscription_plans": conn.execute("SELECT COUNT(*) FROM subscription_plans").fetchone()[0],
            "user_subscriptions": conn.execute("SELECT COUNT(*) FROM user_subscriptions").fetchone()[0],
            "source_preferences": conn.execute("SELECT COUNT(*) FROM source_preferences").fetchone()[0],
            "delivery_preferences": conn.execute("SELECT COUNT(*) FROM delivery_preferences").fetchone()[0],
            "subscription_audit_log": conn.execute("SELECT COUNT(*) FROM subscription_audit_log").fetchone()[0],
        }


def test_manual_entitlement_dry_run_does_not_write_business_rows(tmp_path):
    db_path = tmp_path / "manual.db"

    result = grant_manual_entitlement(
        db_path=db_path,
        telegram_user_id="manual-user",
        chat_id="manual-chat",
        order_ref="xianyu-order-001",
        duration_days=30,
        categories=["akshare", "senate_trading"],
        starts_at="2026-07-07T00:00:00+00:00",
        apply=False,
    )

    assert result["status"] == "dry_run"
    assert result["applied"] is False
    assert result["planned"]["expires_at"] == "2026-08-06T00:00:00+00:00"
    assert result["planned"]["categories"] == ["akshare", "senate_trading"]
    assert _counts(db_path) == {
        "subscribers": 0,
        "subscription_plans": 0,
        "user_subscriptions": 0,
        "source_preferences": 0,
        "delivery_preferences": 0,
        "subscription_audit_log": 0,
    }
    public_text = json.dumps(result, ensure_ascii=False)
    assert "manual-chat" not in public_text
    assert "manual-user" not in public_text
    assert "xianyu-order-001" not in public_text


def test_manual_entitlement_apply_and_renewal_extend_from_existing_expiry(tmp_path):
    db_path = tmp_path / "manual.db"

    first = grant_manual_entitlement(
        db_path=db_path,
        telegram_user_id="manual-user",
        chat_id="manual-chat",
        order_ref="xianyu-order-001",
        duration_days=30,
        categories=["akshare", "senate_trading"],
        starts_at="2026-07-07T00:00:00+00:00",
        source="manual_xianyu_sale",
        apply=True,
    )
    renewal = grant_manual_entitlement(
        db_path=db_path,
        telegram_user_id="manual-user",
        chat_id="manual-chat",
        order_ref="xianyu-order-002-renewal",
        duration_days=30,
        categories=["akshare", "senate_trading"],
        starts_at="2026-07-08T00:00:00+00:00",
        source="manual_xianyu_sale",
        apply=True,
    )

    assert first["status"] == "success"
    assert first["subscription"]["expires_at"] == "2026-08-06T00:00:00+00:00"
    assert renewal["status"] == "success"
    assert renewal["planned"]["existing_active_expires_at"] == "2026-08-06T00:00:00+00:00"
    assert renewal["subscription"]["starts_at"] == "2026-08-06T00:00:00+00:00"
    assert renewal["subscription"]["expires_at"] == "2026-09-05T00:00:00+00:00"
    assert renewal["profile_after"]["eligible"] is True
    assert renewal["profile_after"]["enabled_categories"] == ["akshare", "senate_trading"]

    profile = get_subscription_profile(db_path, user_id="tg:manual-user", now="2026-08-07T00:00:00+00:00")
    assert profile["eligible"] is True
    assert profile["expires_at"] == "2026-09-05T00:00:00+00:00"

    with sqlite3.connect(db_path) as conn:
        statuses = [row[0] for row in conn.execute("SELECT status FROM user_subscriptions ORDER BY id")]
        audit_sources = [row[0] for row in conn.execute("SELECT source FROM subscription_audit_log ORDER BY id")]
    assert statuses == ["superseded", "active"]
    assert len(audit_sources) == 2
    assert all("xianyu-order" not in source for source in audit_sources)
    assert all("order_ref_sha256" in source for source in audit_sources)

    public_text = json.dumps(renewal, ensure_ascii=False)
    assert "manual-chat" not in public_text
    assert "manual-user" not in public_text
    assert "xianyu-order-002-renewal" not in public_text


def test_manual_entitlement_cli_dry_run_and_apply_write_evidence(tmp_path):
    from scripts.intel_manual_entitlement import main

    db_path = tmp_path / "manual.db"
    dry_evidence = tmp_path / "dry.json"
    apply_evidence = tmp_path / "apply.json"

    dry_exit = main(
        [
            "--db",
            str(db_path),
            "--telegram-user-id",
            "manual-user",
            "--chat-id",
            "manual-chat",
            "--order-ref",
            "xianyu-order-cli-001",
            "--category",
            "akshare",
            "--starts-at",
            "2026-07-07T00:00:00+00:00",
            "--evidence",
            str(dry_evidence),
        ]
    )
    apply_exit = main(
        [
            "--db",
            str(db_path),
            "--telegram-user-id",
            "manual-user",
            "--chat-id",
            "manual-chat",
            "--order-ref",
            "xianyu-order-cli-001",
            "--category",
            "akshare",
            "--starts-at",
            "2026-07-07T00:00:00+00:00",
            "--apply",
            "--evidence",
            str(apply_evidence),
        ]
    )

    assert dry_exit == 0
    assert apply_exit == 0
    dry_payload = json.loads(dry_evidence.read_text(encoding="utf-8"))
    apply_payload = json.loads(apply_evidence.read_text(encoding="utf-8"))
    assert dry_payload["status"] == "dry_run"
    assert apply_payload["status"] == "success"
    saved = dry_evidence.read_text(encoding="utf-8") + apply_evidence.read_text(encoding="utf-8")
    assert "manual-chat" not in saved
    assert "manual-user" not in saved
    assert "xianyu-order-cli-001" not in saved


def test_manual_entitlement_sandbox_evidence_is_redacted(tmp_path):
    evidence = build_manual_entitlement_sandbox(tmp_path / "evidence")

    assert evidence["status"] == "success"
    assert evidence["dry_run"]["status"] == "dry_run"
    assert evidence["applied"]["status"] == "success"
    assert evidence["renewed"]["status"] == "success"
    assert evidence["network_calls"] == 0
    saved = (tmp_path / "evidence" / "evidence.json").read_text(encoding="utf-8")
    assert "manual-chat" not in saved
    assert "manual-user" not in saved
    assert "xianyu-order-001" not in saved
    assert "xianyu-order-002-renewal" not in saved
