from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.intel.subscriptions import (
    grant_subscription,
    set_delivery_preferences,
    set_source_preferences,
    upsert_subscription_plan,
    upsert_telegram_subscriber,
)

NOW = "2026-07-07T21:40:00+00:00"
EXPECTED_SIX_SOURCES = [
    "senate_trading",
    "akshare",
    "github_trending",
    "ai_model_updates",
    "institutional_13f",
    "weather",
]


def _seed_db(db_path: Path, *, content: str) -> None:
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare", "senate_trading"])
    subscriber = upsert_telegram_subscriber(db_path, telegram_user_id="e2e-user", chat_id="e2e-chat")
    grant_subscription(
        db_path,
        user_id=subscriber["user_id"],
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at="2026-08-07T00:00:00+00:00",
        source="e2e_test",
    )
    set_source_preferences(db_path, user_id=subscriber["user_id"], enabled_categories=["akshare", "senate_trading"])
    set_delivery_preferences(db_path, user_id=subscriber["user_id"], frequency="daily", delivery_time="08:30", timezone="America/Denver")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO delivery_log (subscriber_id, content_summary, channel_type, success, error_message)
            VALUES (?, ?, 'telegram', 1, NULL)
            """,
            (subscriber["subscriber_id"], content),
        )
        conn.commit()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _readiness(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "ready",
            "expected_sources": ["senate_trading", "akshare", "github_trending", "ai_model_updates", "institutional_13f", "weather"],
            "missing": [],
            "network_calls": 0,
        },
    )


def _delivery_evidence(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "success",
            "delivery_mode": "subscription_filtered",
            "delivery": {"summary": {"eligible": 1, "sent": 1, "failed": 0}},
            "network_calls": 1,
        },
    )


def _natural_launchagent_audit(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "verified_success",
            "verification": {
                "expected_sources_checked": True,
                "artifact_source_success": True,
            },
            "run_evidence": {
                "sources": EXPECTED_SIX_SOURCES,
                "expected_sources": EXPECTED_SIX_SOURCES,
                "sources_match_expected": True,
                "collect_success_matches_expected": True,
                "missing_expected_sources": [],
                "unexpected_sources": [],
                "collect_summary": {"success": 6, "failed": 0},
            },
            "network_calls": 0,
        },
    )


def test_e2e_status_audit_verifies_real_subscriber_filtered_delivery(tmp_path):
    from src.intel.e2e_status_audit import build_intel_e2e_status_audit

    db = tmp_path / "intel.db"
    readiness = tmp_path / "readiness.json"
    delivery = tmp_path / "delivery.json"
    launchagent_audit = tmp_path / "launchagent-natural-six-source-audit.json"
    _seed_db(
        db,
        content=(
            "🧭 情报简报\n已按你的订阅偏好筛选 2 条情报。\n"
            "- [国会持仓] Ron L Wyden Sale BYND\n"
            "- [A股龙虎榜] 深科技机构买入\n"
            "提示：内容来自公开来源自动汇总，不构成投资建议。"
        ),
    )
    _readiness(readiness)
    _delivery_evidence(delivery)
    _natural_launchagent_audit(launchagent_audit)

    report = build_intel_e2e_status_audit(
        db_path=db,
        now=NOW,
        readiness_evidence_path=readiness,
        latest_delivery_evidence_path=delivery,
        launchagent_audit_evidence_path=launchagent_audit,
    )

    assert report["status"] == "verified"
    assert report["checks"] == {
        "has_active_eligible_subscriber": True,
        "subscriber_has_preferences": True,
        "latest_delivery_success": True,
        "latest_delivery_user_facing_copy": True,
        "latest_delivery_filtered_to_preferences": True,
        "next_run_readiness_ready": True,
        "latest_production_delivery_evidence_success": True,
        "natural_six_source_launchagent_verified": True,
    }
    assert report["launchagent_audit_evidence"]["status"] == "verified_success"
    dumped = json.dumps(report, ensure_ascii=False)
    assert "e2e-chat" not in dumped
    assert "tg:e2e-user" not in dumped
    assert "Ron L Wyden" not in dumped


def test_e2e_status_audit_flags_sandbox_copy(tmp_path):
    from src.intel.e2e_status_audit import build_intel_e2e_status_audit

    db = tmp_path / "intel.db"
    readiness = tmp_path / "readiness.json"
    delivery = tmp_path / "delivery.json"
    _seed_db(db, content="🧭 Intel Brief 摘要沙盒\n边界：sandbox fake Telegram sender；未调用真实 Bot API。")
    _readiness(readiness)
    _delivery_evidence(delivery)

    report = build_intel_e2e_status_audit(
        db_path=db,
        now=NOW,
        readiness_evidence_path=readiness,
        latest_delivery_evidence_path=delivery,
        launchagent_audit_evidence_path=tmp_path / "missing-launchagent-audit.json",
    )

    assert report["status"] == "needs_attention"
    assert report["checks"]["latest_delivery_user_facing_copy"] is False
    assert report["checks"]["natural_six_source_launchagent_verified"] is False


def test_e2e_status_audit_requires_natural_six_source_launchagent_audit(tmp_path):
    from src.intel.e2e_status_audit import build_intel_e2e_status_audit

    db = tmp_path / "intel.db"
    readiness = tmp_path / "readiness.json"
    delivery = tmp_path / "delivery.json"
    missing_launchagent_audit = tmp_path / "missing-launchagent-audit.json"
    _seed_db(
        db,
        content=(
            "🧭 情报简报\n已按你的订阅偏好筛选 2 条情报。\n"
            "提示：内容来自公开来源自动汇总，不构成投资建议。"
        ),
    )
    _readiness(readiness)
    _delivery_evidence(delivery)

    report = build_intel_e2e_status_audit(
        db_path=db,
        now=NOW,
        readiness_evidence_path=readiness,
        latest_delivery_evidence_path=delivery,
        launchagent_audit_evidence_path=missing_launchagent_audit,
    )

    assert report["status"] == "needs_attention"
    assert report["checks"]["natural_six_source_launchagent_verified"] is False
    assert report["launchagent_audit_evidence"] == {
        "path": str(missing_launchagent_audit),
        "exists": False,
        "state": "not_found",
    }


def test_e2e_status_audit_cli_writes_evidence(tmp_path):
    from scripts.intel_e2e_status_audit import main

    db = tmp_path / "intel.db"
    readiness = tmp_path / "readiness.json"
    delivery = tmp_path / "delivery.json"
    launchagent_audit = tmp_path / "launchagent-natural-six-source-audit.json"
    output = tmp_path / "e2e.json"
    _seed_db(
        db,
        content="🧭 情报简报\n已按你的订阅偏好筛选 2 条情报。\n提示：内容来自公开来源自动汇总，不构成投资建议。",
    )
    _readiness(readiness)
    _delivery_evidence(delivery)
    _natural_launchagent_audit(launchagent_audit)

    exit_code = main([
        "--db",
        str(db),
        "--now",
        NOW,
        "--readiness-evidence",
        str(readiness),
        "--delivery-evidence",
        str(delivery),
        "--launchagent-audit-evidence",
        str(launchagent_audit),
        "--output",
        str(output),
    ])

    assert exit_code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "verified"
