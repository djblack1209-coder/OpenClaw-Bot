from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

EXPECTED_SIX_SOURCES = [
    "senate_trading",
    "akshare",
    "github_trending",
    "ai_model_updates",
    "institutional_13f",
    "weather",
]


def _write_success_cycle(path: Path, *, sources: list[str] | None = None) -> None:
    source_list = sources or ["senate_trading", "akshare"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "success",
                "timestamp": "2026-07-07T14:31:00+00:00",
                "network_calls": 1,
                "sources": source_list,
                "steps": {
                    "collect": {
                        "sources": source_list,
                        "summary": {"success": len(source_list), "failed": 0},
                        "runs": [{"source": source, "status": "success"} for source in source_list],
                    },
                    "production_once": {
                        "status": "success",
                        "network_calls": 1,
                        "delivery": {"send_result": {"success": True, "message_id": "42"}},
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_launchagent_audit_reports_not_triggered_when_no_run_evidence(tmp_path):
    from src.intel.launchagent_audit import build_launchagent_post_run_audit

    report = build_launchagent_post_run_audit(
        label="ai.openclaw.intel-brief.scheduler",
        run_evidence_path=tmp_path / "runs" / "latest-production-cycle.json",
        stdout_path=tmp_path / "logs" / "stdout.log",
        stderr_path=tmp_path / "logs" / "stderr.log",
        launchctl_text="state = not running\nruns = 0\nlast exit code = (never exited)\n",
        now=datetime(2026, 7, 7, 4, 3, tzinfo=UTC),
    )

    assert report["status"] == "pending_calendar_trigger"
    assert report["run_evidence"]["exists"] is False
    assert report["launchctl"]["runs"] == 0
    assert report["network_calls"] == 0


def test_launchagent_audit_verifies_successful_calendar_run(tmp_path):
    from src.intel.launchagent_audit import build_launchagent_post_run_audit

    run_evidence = tmp_path / "runs" / "latest-production-cycle.json"
    _write_success_cycle(run_evidence)
    stdout = tmp_path / "logs" / "stdout.log"
    stderr = tmp_path / "logs" / "stderr.log"
    stdout.parent.mkdir(parents=True, exist_ok=True)
    stdout.write_text('{"status":"success","network_calls":1}\n', encoding="utf-8")
    stderr.write_text("", encoding="utf-8")

    report = build_launchagent_post_run_audit(
        label="ai.openclaw.intel-brief.scheduler",
        run_evidence_path=run_evidence,
        stdout_path=stdout,
        stderr_path=stderr,
        launchctl_text="state = not running\nruns = 1\nlast exit code = 0\n",
        now=datetime(2026, 7, 7, 14, 40, tzinfo=UTC),
    )

    assert report["status"] == "verified_success"
    assert report["run_evidence"]["status"] == "success"
    assert report["run_evidence"]["collect_summary"] == {"success": 2, "failed": 0}
    assert report["run_evidence"]["telegram_send_success"] is True
    assert report["launchctl"]["last_exit_code"] == "0"
    assert report["verification"]["basis"] == "launchctl_counter_and_artifact"
    dumped = json.dumps(report, ensure_ascii=False)
    assert "SECRET" not in dumped


def test_launchagent_audit_accepts_success_artifact_when_launchctl_counter_is_stale(tmp_path):
    from src.intel.launchagent_audit import build_launchagent_post_run_audit

    run_evidence = tmp_path / "runs" / "latest-production-cycle.json"
    _write_success_cycle(run_evidence)
    stdout = tmp_path / "logs" / "stdout.log"
    stderr = tmp_path / "logs" / "stderr.log"
    stdout.parent.mkdir(parents=True, exist_ok=True)
    stdout.write_text('{"status":"success","evidence":"latest-production-cycle.json","network_calls":1}\n', encoding="utf-8")
    stderr.write_text("", encoding="utf-8")

    report = build_launchagent_post_run_audit(
        label="ai.openclaw.intel-brief.scheduler",
        run_evidence_path=run_evidence,
        stdout_path=stdout,
        stderr_path=stderr,
        launchctl_text=(
            "state = not running\n"
            "runs = 0\n"
            "last exit code = (never exited)\n"
            "program = intel_production_cycle.py\n"
            "event triggers = {\n"
            "  com.apple.launchd.calendarinterval = { Hour = 8; Minute = 30; }\n"
            "}\n"
        ),
        now=datetime(2026, 7, 7, 14, 40, tzinfo=UTC),
    )

    assert report["status"] == "verified_success"
    assert report["launchctl"]["counter_mismatch"] is True
    assert report["verification"] == {
        "artifact_success": True,
        "artifact_source_success": True,
        "stdout_success": True,
        "launchctl_counter_success": False,
        "artifact_verified_despite_launchctl_counter": True,
        "expected_sources_checked": False,
        "basis": "artifact_and_standard_output",
    }


def test_launchagent_audit_rejects_two_source_artifact_when_six_sources_are_expected(tmp_path):
    from src.intel.launchagent_audit import build_launchagent_post_run_audit

    run_evidence = tmp_path / "runs" / "latest-production-cycle.json"
    _write_success_cycle(run_evidence, sources=["senate_trading", "akshare"])
    stdout = tmp_path / "logs" / "stdout.log"
    stderr = tmp_path / "logs" / "stderr.log"
    stdout.parent.mkdir(parents=True, exist_ok=True)
    stdout.write_text('{"status":"success","network_calls":1}\n', encoding="utf-8")
    stderr.write_text("", encoding="utf-8")

    report = build_launchagent_post_run_audit(
        label="ai.openclaw.intel-brief.scheduler",
        run_evidence_path=run_evidence,
        stdout_path=stdout,
        stderr_path=stderr,
        launchctl_text="state = not running\nruns = 1\nlast exit code = 0\n",
        expected_sources=EXPECTED_SIX_SOURCES,
        now=datetime(2026, 7, 7, 14, 40, tzinfo=UTC),
    )

    assert report["status"] == "failed_or_incomplete"
    assert report["verification"]["artifact_success"] is True
    assert report["verification"]["expected_sources_checked"] is True
    assert report["verification"]["artifact_source_success"] is False
    assert report["run_evidence"]["sources"] == ["senate_trading", "akshare"]
    assert report["run_evidence"]["expected_sources"] == EXPECTED_SIX_SOURCES
    assert report["run_evidence"]["sources_match_expected"] is False
    assert report["run_evidence"]["collect_success_matches_expected"] is False
    assert report["run_evidence"]["missing_expected_sources"] == [
        "github_trending",
        "ai_model_updates",
        "institutional_13f",
        "weather",
    ]


def test_launchagent_audit_verifies_when_expected_six_sources_all_succeeded(tmp_path):
    from src.intel.launchagent_audit import build_launchagent_post_run_audit

    run_evidence = tmp_path / "runs" / "latest-production-cycle.json"
    _write_success_cycle(run_evidence, sources=EXPECTED_SIX_SOURCES)
    stdout = tmp_path / "logs" / "stdout.log"
    stderr = tmp_path / "logs" / "stderr.log"
    stdout.parent.mkdir(parents=True, exist_ok=True)
    stdout.write_text('{"status":"success","network_calls":1}\n', encoding="utf-8")
    stderr.write_text("", encoding="utf-8")

    report = build_launchagent_post_run_audit(
        label="ai.openclaw.intel-brief.scheduler",
        run_evidence_path=run_evidence,
        stdout_path=stdout,
        stderr_path=stderr,
        launchctl_text=(
            "state = not running\n"
            "runs = 0\n"
            "last exit code = (never exited)\n"
            "program = intel_production_cycle.py\n"
            "event triggers = {\n"
            "  com.apple.launchd.calendarinterval = { Hour = 8; Minute = 30; }\n"
            "}\n"
        ),
        expected_sources=EXPECTED_SIX_SOURCES,
        now=datetime(2026, 7, 7, 14, 40, tzinfo=UTC),
    )

    assert report["status"] == "verified_success"
    assert report["verification"]["expected_sources_checked"] is True
    assert report["verification"]["artifact_source_success"] is True
    assert report["run_evidence"]["sources_match_expected"] is True
    assert report["run_evidence"]["collect_success_matches_expected"] is True
    assert report["run_evidence"]["unexpected_sources"] == []


def test_launchagent_audit_cli_accepts_expected_source_repeated_args(tmp_path):
    from scripts.intel_launchagent_audit import main

    run_evidence = tmp_path / "runs" / "latest-production-cycle.json"
    _write_success_cycle(run_evidence, sources=["senate_trading", "akshare"])
    stdout = tmp_path / "logs" / "stdout.log"
    stderr = tmp_path / "logs" / "stderr.log"
    stdout.parent.mkdir(parents=True, exist_ok=True)
    stdout.write_text('{"status":"success","network_calls":1}\n', encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    output = tmp_path / "audit.json"

    exit_code = main(
        [
            "--run-evidence",
            str(run_evidence),
            "--stdout-log",
            str(stdout),
            "--stderr-log",
            str(stderr),
            "--output",
            str(output),
            "--launchctl-text",
            "state = not running\nruns = 1\nlast exit code = 0\n",
            *[arg for source in EXPECTED_SIX_SOURCES for arg in ("--expected-source", source)],
        ]
    )

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "failed_or_incomplete"
    assert saved["verification"]["expected_sources_checked"] is True
    assert saved["run_evidence"]["missing_expected_sources"] == [
        "github_trending",
        "ai_model_updates",
        "institutional_13f",
        "weather",
    ]


def test_launchagent_audit_cli_writes_evidence(tmp_path):
    from scripts.intel_launchagent_audit import main

    output = tmp_path / "audit.json"
    exit_code = main(
        [
            "--run-evidence",
            str(tmp_path / "runs" / "latest-production-cycle.json"),
            "--stdout-log",
            str(tmp_path / "logs" / "stdout.log"),
            "--stderr-log",
            str(tmp_path / "logs" / "stderr.log"),
            "--output",
            str(output),
            "--launchctl-text",
            "state = not running\nruns = 0\nlast exit code = (never exited)\n",
        ]
    )

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "pending_calendar_trigger"
