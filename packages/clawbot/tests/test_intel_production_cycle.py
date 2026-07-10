from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.execution.intel_brief import PRODUCTION_ACK_VALUE
from src.intel.db.store import initialize_intel_db
from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE


def _ready_env() -> dict[str, str]:
    return {
        "INTEL_BRIEF_ENABLED": "true",
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
        "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654321",
        "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
    }


def _write_collect_payload(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-07T08:31:00+00:00",
                "status": "success",
                "summary": {"success": 2, "failed": 0},
                "runs": [
                    {
                        "source": "senate_trading",
                        "status": "success",
                        "worker": "oracle-sg-west-preferred-overseas",
                        "evidence_path": "child-senate.json",
                        "response": {
                            "fetched_at": "2026-07-07T08:30:10+00:00",
                            "raw_count": 1,
                            "items": [
                                {
                                    "person": "Ron L Wyden",
                                    "ticker": "BYND",
                                    "transaction_type": "Sale",
                                    "amount": "$15,001 - $50,000",
                                    "transaction_date": "2026-06-30",
                                }
                            ],
                        },
                    },
                    {
                        "source": "akshare",
                        "status": "success",
                        "worker": "yanhuoyun-domestic",
                        "evidence_path": "child-akshare.json",
                        "response": {
                            "fetched_at": "2026-07-07T08:30:20+00:00",
                            "raw_count": 1,
                            "items": [
                                {"code": "000021", "name": "深科技", "reason": "日涨幅偏离值达7%", "close_price": "18.88"}
                            ],
                        },
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_production_cycle_blocks_without_production_ack_before_collection(tmp_path):
    from src.intel.production_cycle import run_intel_production_cycle

    calls: list[str] = []

    def collect_runner(**kwargs):  # pragma: no cover - must not be called
        calls.append("collect")
        raise AssertionError("collect should not run when production ack is missing")

    result = run_intel_production_cycle(
        output_dir=tmp_path / "cycle-artifacts",
        evidence_path=tmp_path / "cycle.json",
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env=_ready_env(),
        collect_runner=collect_runner,
    )

    assert result["status"] == "blocked"
    assert result["network_calls"] == 0
    assert result["steps"] == {}
    assert calls == []
    assert "production_ack_missing" in result["preflight"]["missing_gates"]


def test_production_cycle_default_sources_include_ai_model_updates():
    from src.intel.production_cycle import DEFAULT_PRODUCTION_CYCLE_SOURCES

    assert DEFAULT_PRODUCTION_CYCLE_SOURCES == (
        "senate_trading",
        "akshare",
        "github_trending",
        "ai_model_updates",
        "institutional_13f",
        "weather",
    )


def test_production_cycle_collects_summarizes_and_delivers_with_injected_runners(tmp_path):
    from src.intel.production_cycle import run_intel_production_cycle

    collect_calls = []
    delivery_calls = []

    def collect_runner(**kwargs):
        collect_calls.append(kwargs)
        output_path = Path(kwargs["output_path"])
        _write_collect_payload(output_path)
        return json.loads(output_path.read_text(encoding="utf-8"))

    def production_once_runner(**kwargs):
        delivery_calls.append(kwargs)
        evidence_path = Path(kwargs["evidence_path"])
        payload = {
            "status": "success",
            "gate": {"reason": "production_ready", "missing_gates": []},
            "network_calls": 1,
            "delivery": {"status": "success", "send_result": {"success": True, "message_id": "42"}},
        }
        evidence_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    lifecycle_db = tmp_path / "intel_brief.db"
    initialize_intel_db(lifecycle_db)
    env = {
        **_ready_env(),
        "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        "INTEL_BRIEF_DB_PATH": str(lifecycle_db),
    }
    result = run_intel_production_cycle(
        output_dir=tmp_path / "cycle-artifacts",
        evidence_path=tmp_path / "cycle.json",
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env=env,
        stamp="20260707T083100Z",
        llm_mode="fallback-only",
        collect_runner=collect_runner,
        production_once_runner=production_once_runner,
    )

    assert result["status"] == "success"
    assert len(collect_calls) == 1
    assert len(delivery_calls) == 1
    assert result["steps"]["collect"]["summary"] == {"success": 2, "failed": 0}
    assert result["steps"]["llm_summary"]["llm"]["llm_attempted"] is False
    assert result["steps"]["production_once"]["network_calls"] == 1
    assert result["subscription_lifecycle"]["status"] == "success"
    assert result["subscription_lifecycle"]["reason"] == "readonly_audit_complete"
    assert result["subscription_lifecycle"]["audit"]["summary"]["expired_active_found"] == 0
    assert result["subscription_lifecycle"]["audit"]["summary"]["expiring_active_found"] == 0
    assert result["subscription_lifecycle"]["audit"]["apply_expiry"] is False
    assert result["subscription_lifecycle"]["audit"]["send_reminders"] is False
    assert Path(result["artifacts"]["collect_evidence"]).exists()
    assert Path(result["artifacts"]["llm_summary_json"]).exists()
    saved_text = Path(tmp_path / "cycle.json").read_text(encoding="utf-8")
    assert "SECRET" not in saved_text
    assert "987654321" not in saved_text


def test_intel_production_cycle_cli_writes_blocked_evidence(tmp_path, monkeypatch):
    from scripts.intel_production_cycle import main

    monkeypatch.delenv("INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK", raising=False)
    output = tmp_path / "cycle.json"

    exit_code = main(
        [
            "--output-dir",
            str(tmp_path / "cycle-artifacts"),
            "--evidence",
            str(output),
            "--now",
            "2026-07-07T08:31:00+00:00",
            "--source",
            "senate_trading",
        ]
    )

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["network_calls"] == 0


def test_production_cycle_lifecycle_audit_skips_without_db_path(tmp_path):
    from src.intel.production_cycle import run_intel_production_cycle

    collect_calls = []
    delivery_calls = []

    def collect_runner(**kwargs):
        collect_calls.append(kwargs)
        output_path = Path(kwargs["output_path"])
        _write_collect_payload(output_path)
        return json.loads(output_path.read_text(encoding="utf-8"))

    def production_once_runner(**kwargs):
        delivery_calls.append(kwargs)
        payload = {"status": "success", "network_calls": 0, "delivery": {"status": "success"}}
        Path(kwargs["evidence_path"]).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    result = run_intel_production_cycle(
        output_dir=tmp_path / "cycle-artifacts",
        evidence_path=tmp_path / "cycle.json",
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        env={**_ready_env(), "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE},
        stamp="20260707T083100Z",
        collect_runner=collect_runner,
        production_once_runner=production_once_runner,
    )

    assert result["status"] == "success"
    assert result["subscription_lifecycle"] == {
        "status": "skipped",
        "reason": "intel_brief_db_path_missing",
        "network_calls": 0,
        "redacted_env": {"INTEL_BRIEF_DB_PATH": False},
        "limits": [
            "Lifecycle audit is read-only and skipped when INTEL_BRIEF_DB_PATH is not configured.",
            "No subscription status mutation and no Telegram reminder send.",
        ],
    }
    assert len(collect_calls) == 1
    assert len(delivery_calls) == 1
