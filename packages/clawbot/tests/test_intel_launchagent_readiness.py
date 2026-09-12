from __future__ import annotations

import json
import plistlib
from pathlib import Path

import pytest

EXPECTED = [
    "senate_trading",
    "akshare",
    "github_trending",
    "ai_model_updates",
    "institutional_13f",
    "weather",
]


def _write_plist(
    path: Path,
    *,
    source_args: list[str] | None = None,
    scheduled: bool = True,
    calendar: object = None,
    extra_args: list[str] | None = None,
) -> None:
    program_args: list[str] = [
        "/tmp/python",
        "/repo/packages/clawbot/scripts/intel_production_cycle.py",
        "--output-dir",
        "/tmp/runs",
        "--evidence",
        "/tmp/runs/latest-production-cycle.json",
    ]
    if scheduled:
        program_args.append("--scheduled")
    program_args.extend(extra_args or [])
    for source in source_args or []:
        program_args.extend(["--source", source])
    path.write_bytes(
        plistlib.dumps(
            {
                "Label": "ai.openclaw.intel-brief.scheduler",
                "WorkingDirectory": "/repo",
                "EnvironmentVariables": {
                    "INTEL_BRIEF_PRIVATE_ENV": "/repo/.openclaw/intel-brief.production.env",
                    "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": "I_UNDERSTAND_REAL_DELIVERY",
                },
                "ProgramArguments": program_args,
                "StartCalendarInterval": {"Minute": 30} if calendar is None else calendar,
                "RunAtLoad": False,
                "StandardOutPath": "/tmp/stdout.log",
                "StandardErrorPath": "/tmp/stderr.log",
            }
        )
    )


def _write_cycle(path: Path, *, sources: list[str] | None = None, success: int = 6, failed: int = 0) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "success",
                "timestamp": "2026-07-07T20:50:21+00:00",
                "sources": sources or EXPECTED,
                "steps": {
                    "collect": {"summary": {"success": success, "failed": failed}},
                    "production_once": {"status": "success"},
                },
                "network_calls": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_launchagent_next_run_readiness_is_ready_for_default_sources(tmp_path):
    from src.intel.launchagent_readiness import build_launchagent_next_run_readiness

    plist = tmp_path / "agent.plist"
    cycle = tmp_path / "cycle.json"
    _write_plist(plist)
    _write_cycle(cycle)

    report = build_launchagent_next_run_readiness(plist_path=plist, controlled_cycle_path=cycle)

    assert report["status"] == "ready"
    assert report["missing"] == []
    assert report["expected_sources"] == EXPECTED
    assert report["plist"]["uses_default_sources"] is True
    assert report["plist"]["effective_sources"] == EXPECTED
    assert report["plist"]["scheduled_mode_present"] is True
    assert report["plist"]["calendar_is_hourly_half_past"] is True
    assert report["expected_business_schedule"] == {
        "timezone": "Asia/Singapore",
        "delivery_time": "08:30",
    }
    assert report["controlled_cycle"]["collect_success_matches_expected"] is True
    assert report["network_calls"] == 0


def test_launchagent_next_run_readiness_detects_explicit_source_mismatch(tmp_path):
    from src.intel.launchagent_readiness import build_launchagent_next_run_readiness

    plist = tmp_path / "agent.plist"
    cycle = tmp_path / "cycle.json"
    _write_plist(plist, source_args=["senate_trading", "akshare"])
    _write_cycle(cycle)

    report = build_launchagent_next_run_readiness(plist_path=plist, controlled_cycle_path=cycle)

    assert report["status"] == "not_ready"
    assert "plist_effective_sources_not_six_source_default" in report["missing"]
    assert report["plist"]["effective_sources"] == ["senate_trading", "akshare"]


def test_launchagent_next_run_readiness_requires_scheduled_window_guard(tmp_path):
    from src.intel.launchagent_readiness import build_launchagent_next_run_readiness

    plist = tmp_path / "agent.plist"
    cycle = tmp_path / "cycle.json"
    _write_plist(plist, scheduled=False)
    _write_cycle(cycle)

    report = build_launchagent_next_run_readiness(plist_path=plist, controlled_cycle_path=cycle)

    assert report["status"] == "not_ready"
    assert "scheduled_mode_missing" in report["missing"]


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--now", "2026-09-12T00:30:00+00:00"],
        ["--now=2026-09-12T00:30:00+00:00"],
        ["--stamp", "20260912"],
        ["--stamp=20260912"],
        ["--time", "09:30"],
        ["--time=09:30"],
        ["--time", "08:30 "],
        ["--time"],
    ],
)
def test_launchagent_next_run_readiness_rejects_replay_or_altered_business_time(tmp_path, extra_args):
    from src.intel.launchagent_readiness import build_launchagent_next_run_readiness

    plist = tmp_path / "agent.plist"
    cycle = tmp_path / "cycle.json"
    _write_plist(plist, extra_args=extra_args)
    _write_cycle(cycle)

    report = build_launchagent_next_run_readiness(plist_path=plist, controlled_cycle_path=cycle)

    assert report["status"] == "not_ready"
    assert "scheduled_arguments_invalid" in report["missing"]


@pytest.mark.parametrize("extra_args", [["--time", "08:30"], ["--time=08:30"]])
def test_launchagent_next_run_readiness_accepts_explicit_business_time(tmp_path, extra_args):
    from src.intel.launchagent_readiness import build_launchagent_next_run_readiness

    plist = tmp_path / "agent.plist"
    cycle = tmp_path / "cycle.json"
    _write_plist(plist, extra_args=extra_args)
    _write_cycle(cycle)

    report = build_launchagent_next_run_readiness(plist_path=plist, controlled_cycle_path=cycle)

    assert report["status"] == "ready"


@pytest.mark.parametrize(
    "calendar",
    [
        {"Hour": 8, "Minute": 30},
        {"Minute": 0},
        {"Minute": 30, "Weekday": 1},
        {"Minute": "30"},
        {"Minute": 30.0},
        [{"Minute": 30}],
        {},
    ],
)
def test_launchagent_next_run_readiness_rejects_host_time_or_invalid_calendar(tmp_path, calendar):
    from src.intel.launchagent_readiness import build_launchagent_next_run_readiness

    plist = tmp_path / "agent.plist"
    cycle = tmp_path / "cycle.json"
    _write_plist(plist, calendar=calendar)
    _write_cycle(cycle)

    report = build_launchagent_next_run_readiness(plist_path=plist, controlled_cycle_path=cycle)

    assert report["status"] == "not_ready"
    assert "calendar_hourly_half_past_missing" in report["missing"]


def test_launchagent_next_run_readiness_cli_writes_evidence(tmp_path):
    from scripts.intel_launchagent_next_run_readiness import main

    plist = tmp_path / "agent.plist"
    cycle = tmp_path / "cycle.json"
    output = tmp_path / "readiness.json"
    _write_plist(plist)
    _write_cycle(cycle)

    exit_code = main([
        "--plist",
        str(plist),
        "--controlled-cycle",
        str(cycle),
        "--previous-natural-audit",
        "",
        "--output",
        str(output),
    ])

    assert exit_code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "ready"
    assert saved["expected_sources"] == EXPECTED
