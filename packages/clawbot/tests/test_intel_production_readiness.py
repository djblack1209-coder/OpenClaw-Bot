from __future__ import annotations

import json
from pathlib import Path

from src.execution.intel_brief import PRODUCTION_ACK_VALUE
from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE

FAKE_TOKEN = "123456:SECRET-DO-NOT-LEAK"
FAKE_CHAT_ID = "987654321"


def _write_collect(path: Path, *, success: int = 2, failed: int = 0) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "success" if failed == 0 else "partial_failed",
                "summary": {"success": success, "failed": failed},
                "runs": [
                    {"source": "senate_trading", "status": "success", "worker": "oracle-arm1-overseas-fallback"},
                    {"source": "akshare", "status": "success", "worker": "yanhuoyun-domestic"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_summary(path: Path, *, item_count: int = 2) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "partial_fallback",
                "items": [{"title": f"item {idx}"} for idx in range(item_count)],
                "llm": {"llm_attempted": False, "llm_success": False},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_production_readiness_report_blocks_missing_external_gates(tmp_path):
    from src.intel.production_readiness import build_intel_production_readiness_report

    collect = tmp_path / "collect.json"
    summary = tmp_path / "summary.json"
    _write_collect(collect)
    _write_summary(summary)

    report = build_intel_production_readiness_report(
        collect_evidence_path=collect,
        summary_evidence_path=summary,
        now_iso="2026-07-07T08:31:00+00:00",
        env={"INTEL_BRIEF_ENABLED": "true", "INTEL_BRIEF_MODE": "production"},
        project_root=tmp_path,
    )

    assert report["status"] == "blocked"
    assert report["checks"]["collect_evidence"]["ready"] is True
    assert report["checks"]["summary_evidence"]["ready"] is True
    assert report["checks"]["telegram_sandbox_gate"]["ready"] is False
    assert report["checks"]["scheduler_production_gate"]["ready"] is False
    assert "telegram_bot_token_missing" in report["missing_gates"]
    assert "worker_placement_not_confirmed" in report["missing_gates"]
    assert report["network_calls"] == 0


def test_production_readiness_report_blocks_when_production_summary_file_missing_even_if_secrets_present(tmp_path):
    from src.intel.production_readiness import build_intel_production_readiness_report

    collect = tmp_path / "collect.json"
    summary = tmp_path / "missing-summary.json"
    _write_collect(collect)

    report = build_intel_production_readiness_report(
        collect_evidence_path=collect,
        summary_evidence_path=summary,
        now_iso="2026-07-07T08:31:00+00:00",
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": FAKE_CHAT_ID,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        },
        project_root=tmp_path,
    )

    dumped = json.dumps(report, ensure_ascii=False)
    assert report["status"] == "blocked"
    assert report["checks"]["telegram_sandbox_gate"]["ready"] is True
    assert report["checks"]["worker_placement"]["ready"] is True
    assert report["checks"]["scheduler_production_gate"]["ready"] is False
    assert "summary_evidence_not_found" in report["missing_gates"]
    assert "SECRET" not in dumped
    assert FAKE_CHAT_ID not in dumped


def test_production_readiness_report_marks_missing_summary_as_not_ready(tmp_path):
    from src.intel.production_readiness import build_intel_production_readiness_report

    collect = tmp_path / "collect.json"
    _write_collect(collect)

    report = build_intel_production_readiness_report(
        collect_evidence_path=collect,
        summary_evidence_path=tmp_path / "missing-summary.json",
        now_iso="2026-07-07T08:31:00+00:00",
        env={},
        project_root=tmp_path,
    )

    assert report["status"] == "blocked"
    assert report["checks"]["summary_evidence"]["ready"] is False
    assert "summary_evidence_not_found" in report["missing_gates"]


def test_production_readiness_report_scheduler_gate_is_ready_when_all_runtime_gates_present(tmp_path):
    from src.intel.production_readiness import build_intel_production_readiness_report

    collect = tmp_path / "collect.json"
    summary = tmp_path / "summary.json"
    _write_collect(collect)
    _write_summary(summary)

    report = build_intel_production_readiness_report(
        collect_evidence_path=collect,
        summary_evidence_path=summary,
        now_iso="2026-07-07T08:31:00+00:00",
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": FAKE_CHAT_ID,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        },
        project_root=tmp_path,
    )

    assert report["status"] == "ready"
    assert report["checks"]["scheduler_production_gate"]["ready"] is True
    assert report["checks"]["telegram_sandbox_gate"]["ready"] is True
    assert report["missing_gates"] == []
    dumped = json.dumps(report, ensure_ascii=False)
    assert "SECRET" not in dumped
    assert FAKE_CHAT_ID not in dumped


def test_production_readiness_report_loads_private_env_for_all_gates(tmp_path):
    from src.intel.production_readiness import build_intel_production_readiness_report

    collect = tmp_path / "collect.json"
    summary = tmp_path / "summary.json"
    private_env = tmp_path / ".openclaw" / "intel-brief.production.env"
    _write_collect(collect)
    _write_summary(summary)
    private_env.parent.mkdir(parents=True)
    private_env.write_text(
        "\n".join(
            [
                f"INTEL_BRIEF_TELEGRAM_BOT_TOKEN='{FAKE_TOKEN}'",
                f"INTEL_BRIEF_TELEGRAM_CHAT_ID='{FAKE_CHAT_ID}'",
                f"INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK='{TELEGRAM_SANDBOX_ACK_VALUE}'",
                "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_intel_production_readiness_report(
        collect_evidence_path=collect,
        summary_evidence_path=summary,
        now_iso="2026-07-07T08:31:00+00:00",
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_PRIVATE_ENV": str(private_env),
        },
        project_root=tmp_path,
    )

    assert report["status"] == "blocked"
    assert report["checks"]["telegram_sandbox_gate"]["ready"] is True
    assert report["checks"]["worker_placement"]["ready"] is True
    assert report["missing_gates"] == ["production_ack_missing"]
    dumped = json.dumps(report, ensure_ascii=False)
    assert "SECRET" not in dumped
    assert FAKE_CHAT_ID not in dumped


def test_intel_production_readiness_audit_cli_writes_evidence(tmp_path):
    from scripts.intel_production_readiness_audit import main

    collect = tmp_path / "collect.json"
    summary = tmp_path / "summary.json"
    output = tmp_path / "readiness.json"
    _write_collect(collect)
    _write_summary(summary)

    exit_code = main(
        [
            "--collect-evidence",
            str(collect),
            "--summary-evidence",
            str(summary),
            "--output",
            str(output),
            "--now",
            "2026-07-07T08:31:00+00:00",
        ]
    )

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["network_calls"] == 0
    assert saved["limits"][0] == "Read-only production readiness audit; no deployment or external network calls."


def test_intel_production_readiness_audit_cli_resolves_relative_paths_from_cwd(tmp_path, monkeypatch):
    from scripts.intel_production_readiness_audit import main

    collect = tmp_path / "evidence" / "collect.json"
    summary = tmp_path / "evidence" / "summary.json"
    output = tmp_path / "out" / "readiness.json"
    collect.parent.mkdir(parents=True)
    _write_collect(collect)
    _write_summary(summary)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "--collect-evidence",
            "evidence/collect.json",
            "--summary-evidence",
            "evidence/summary.json",
            "--output",
            "out/readiness.json",
            "--now",
            "2026-07-07T08:31:00+00:00",
        ]
    )

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["checks"]["collect_evidence"]["ready"] is True
    assert saved["checks"]["summary_evidence"]["ready"] is True
