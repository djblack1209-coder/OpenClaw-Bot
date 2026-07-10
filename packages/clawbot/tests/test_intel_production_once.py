from __future__ import annotations

import json
from datetime import UTC, datetime

from src.execution.intel_brief import PRODUCTION_ACK_VALUE
from src.intel.db.store import initialize_intel_db
from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE


def _write_summary(path):
    path.write_text(
        json.dumps(
            {
                "status": "partial_fallback",
                "llm": {"summary_text": "Intel Brief production smoke", "usage": {"total_tokens": 0}},
                "items": [{"source_label": "国会持仓", "title": "Ron L Wyden Sale BYND"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_production_once_blocks_without_gates_and_makes_no_network(tmp_path):
    from src.intel.production_once import run_intel_production_once

    summary = tmp_path / "summary.json"
    evidence = tmp_path / "production-once.json"
    _write_summary(summary)

    result = run_intel_production_once(
        summary_evidence_path=summary,
        evidence_path=evidence,
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env={"INTEL_BRIEF_ENABLED": "true", "INTEL_BRIEF_MODE": "production"},
    )

    assert result["status"] == "blocked"
    assert result["network_calls"] == 0
    assert "telegram_bot_token_missing" in result["gate"]["missing_gates"]
    saved = json.loads(evidence.read_text(encoding="utf-8"))
    assert saved["limits"][0] == "Production-once runner; no scheduler installation or persistent worker creation."


def test_production_once_calls_sender_when_gates_ready_with_injected_runner(tmp_path):
    from src.intel.production_once import run_intel_production_once

    summary = tmp_path / "summary.json"
    evidence = tmp_path / "production-once-success.json"
    _write_summary(summary)
    calls = []

    def runner(**kwargs):
        calls.append(kwargs)
        return {"status": "success", "send_result": {"success": True, "message_id": "42"}, "network_calls": 1}

    result = run_intel_production_once(
        summary_evidence_path=summary,
        evidence_path=evidence,
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654321",
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        },
        delivery_runner=runner,
    )

    assert result["status"] == "success"
    assert result["network_calls"] == 1
    assert len(calls) == 1
    saved_text = evidence.read_text(encoding="utf-8")
    assert "SECRET" not in saved_text
    assert "987654321" not in saved_text


def test_production_once_cli_writes_blocked_evidence(tmp_path, monkeypatch):
    from scripts.intel_production_once import main

    summary = tmp_path / "summary.json"
    evidence = tmp_path / "production-cli.json"
    _write_summary(summary)
    monkeypatch.delenv("INTEL_BRIEF_TELEGRAM_BOT_TOKEN", raising=False)

    exit_code = main(["--summary-evidence", str(summary), "--evidence", str(evidence), "--now", "2026-07-07T08:31:00+00:00"])

    assert exit_code == 2
    saved = json.loads(evidence.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["network_calls"] == 0


def test_production_once_loads_private_env_for_real_delivery_runner(tmp_path):
    from src.intel.production_once import run_intel_production_once

    summary = tmp_path / "summary.json"
    evidence = tmp_path / "production-once-private-env.json"
    private_env = tmp_path / ".openclaw" / "intel-brief.production.env"
    _write_summary(summary)
    private_env.parent.mkdir(parents=True)
    private_env.write_text(
        "\n".join(
            [
                "INTEL_BRIEF_TELEGRAM_BOT_TOKEN='123456:PRIVATE-ENV-SECRET'",
                "INTEL_BRIEF_TELEGRAM_CHAT_ID='123456789'",
                f"INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK='{TELEGRAM_SANDBOX_ACK_VALUE}'",
                "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    def runner(**kwargs):
        calls.append(kwargs)
        return {"status": "success", "send_result": {"success": True, "message_id": "84"}, "network_calls": 1}

    result = run_intel_production_once(
        summary_evidence_path=summary,
        evidence_path=evidence,
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_PRIVATE_ENV": str(private_env),
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        },
        project_root=tmp_path,
        delivery_runner=runner,
    )

    assert result["status"] == "success"
    assert len(calls) == 1
    delivery_env = calls[0]["env"]
    assert delivery_env["INTEL_BRIEF_TELEGRAM_BOT_TOKEN"] == "123456:PRIVATE-ENV-SECRET"
    assert delivery_env["INTEL_BRIEF_TELEGRAM_CHAT_ID"] == "123456789"
    saved_text = evidence.read_text(encoding="utf-8")
    assert "PRIVATE-ENV-SECRET" not in saved_text
    assert "123456789" not in saved_text



def test_production_once_defaults_to_fixed_chat_delivery_when_subscription_delivery_disabled(tmp_path):
    from src.intel.production_once import run_intel_production_once

    summary = tmp_path / "summary.json"
    evidence = tmp_path / "production-once-fixed-chat.json"
    _write_summary(summary)
    fixed_calls = []
    subscription_calls = []

    def fixed_runner(**kwargs):
        fixed_calls.append(kwargs)
        return {"status": "success", "send_result": {"success": True, "message_id": "fixed-1"}, "network_calls": 1}

    def subscription_runner(**kwargs):  # pragma: no cover - must not be called
        subscription_calls.append(kwargs)
        raise AssertionError("subscription delivery must be explicitly enabled")

    result = run_intel_production_once(
        summary_evidence_path=summary,
        evidence_path=evidence,
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654321",
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        },
        delivery_runner=fixed_runner,
        subscription_delivery_runner=subscription_runner,
    )

    assert result["status"] == "success"
    assert result["delivery_mode"] == "fixed_chat"
    assert len(fixed_calls) == 1
    assert subscription_calls == []


def test_production_once_uses_subscription_filtered_delivery_when_enabled(tmp_path):
    from src.intel.production_once import run_intel_production_once

    summary = tmp_path / "summary.json"
    evidence = tmp_path / "production-once-subscription.json"
    db_path = tmp_path / "intel_brief.db"
    initialize_intel_db(db_path)
    _write_summary(summary)
    fixed_calls = []
    subscription_calls = []

    def fixed_runner(**kwargs):  # pragma: no cover - must not be called
        fixed_calls.append(kwargs)
        raise AssertionError("fixed chat delivery should not run in subscription mode")

    def subscription_runner(**kwargs):
        subscription_calls.append(kwargs)
        return {
            "status": "success",
            "summary": {"eligible": 2, "sent": 2, "failed": 0},
            "network_calls": 2,
            "source_categories": ["akshare", "senate_trading"],
        }

    result = run_intel_production_once(
        summary_evidence_path=summary,
        evidence_path=evidence,
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654321",
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
            "INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED": "true",
            "INTEL_BRIEF_DB_PATH": str(db_path),
        },
        delivery_runner=fixed_runner,
        subscription_delivery_runner=subscription_runner,
    )

    assert result["status"] == "success"
    assert result["delivery_mode"] == "subscription_filtered"
    assert result["network_calls"] == 2
    assert len(subscription_calls) == 1
    assert subscription_calls[0]["db_path"] == db_path
    assert subscription_calls[0]["summary_evidence_path"] == summary
    assert subscription_calls[0]["now"] == "2026-07-07T08:31:00+00:00"
    assert fixed_calls == []
    saved_text = evidence.read_text(encoding="utf-8")
    assert "SECRET" not in saved_text
    assert "987654321" not in saved_text


def test_production_once_blocks_subscription_delivery_without_db_path(tmp_path):
    from src.intel.production_once import run_intel_production_once

    summary = tmp_path / "summary.json"
    evidence = tmp_path / "production-once-subscription-no-db.json"
    _write_summary(summary)
    calls = []

    def runner(**kwargs):  # pragma: no cover - must not be called
        calls.append(kwargs)
        raise AssertionError("subscription runner should not run without db path")

    result = run_intel_production_once(
        summary_evidence_path=summary,
        evidence_path=evidence,
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654321",
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
            "INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED": "true",
        },
        subscription_delivery_runner=runner,
    )

    assert result["status"] == "blocked"
    assert result["delivery_mode"] == "subscription_filtered"
    assert result["network_calls"] == 0
    assert result["subscription_delivery_gate"]["ready"] is False
    assert "intel_brief_db_path_missing" in result["subscription_delivery_gate"]["missing_gates"]
    assert calls == []


def test_production_once_blocks_subscription_delivery_when_db_path_missing_file(tmp_path):
    from src.intel.production_once import run_intel_production_once

    summary = tmp_path / "summary.json"
    evidence = tmp_path / "production-once-subscription-missing-db-file.json"
    missing_db_path = tmp_path / "missing" / "intel_brief.db"
    _write_summary(summary)
    calls = []

    def runner(**kwargs):  # pragma: no cover - must not be called
        calls.append(kwargs)
        raise AssertionError("subscription runner should not run when db path does not exist")

    result = run_intel_production_once(
        summary_evidence_path=summary,
        evidence_path=evidence,
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654321",
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
            "INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED": "true",
            "INTEL_BRIEF_DB_PATH": str(missing_db_path),
        },
        subscription_delivery_runner=runner,
    )

    assert result["status"] == "blocked"
    assert result["delivery_mode"] == "subscription_filtered"
    assert result["network_calls"] == 0
    assert result["subscription_delivery_gate"]["ready"] is False
    assert "intel_brief_db_path_not_found" in result["subscription_delivery_gate"]["missing_gates"]
    assert result["subscription_delivery_gate"]["redacted_env"]["INTEL_BRIEF_DB_PATH_EXISTS"] is False
    assert calls == []
