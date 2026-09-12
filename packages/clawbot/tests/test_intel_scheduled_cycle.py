"""Exercise scheduled dispatch with synthetic clocks and no external transports."""

from __future__ import annotations

import json
import multiprocessing
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from src.intel.scheduled_cycle import STATE_DIRECTORY, run_scheduled_intel_cycle

SINGAPORE = ZoneInfo("Asia/Singapore")
NEW_YORK = ZoneInfo("America/New_York")


def _time(day=12, hour=8, minute=30):
    return datetime(2026, 9, day, hour, minute, tzinfo=SINGAPORE)


@pytest.mark.parametrize("host_time", [
    datetime(2026, 7, 6, 20, 30, tzinfo=NEW_YORK),
    datetime(2026, 1, 6, 19, 30, tzinfo=NEW_YORK),
])
def test_new_york_summer_and_winter_wake_at_singapore_0830(tmp_path, host_time):
    calls = []

    def runner(**kwargs):
        calls.append(kwargs)
        state = tmp_path / STATE_DIRECTORY
        claim = state / f"{host_time.astimezone(SINGAPORE).date().isoformat()}.json"
        assert json.loads(claim.read_text())["status"] == "claimed"
        assert state.stat().st_mode & 0o777 == 0o700
        assert claim.stat().st_mode & 0o777 == 0o600
        assert (state / "dispatch.lock").stat().st_mode & 0o777 == 0o600
        return {"status": "success", "network_calls": 0}

    result = run_scheduled_intel_cycle(
        output_dir=tmp_path, evidence_path=tmp_path / "latest.json", clock=lambda: host_time,
        cycle_runner=runner, env={"INTEL_BRIEF_SCHEDULER_TIMEZONE": "America/New_York"},
    )
    assert result["status"] == "success"
    assert result["scheduler"]["business_date"] == host_time.astimezone(SINGAPORE).date().isoformat()
    assert calls[0]["now"] == host_time
    assert calls[0]["scheduled_time"] == "08:30"
    assert calls[0]["env"]["INTEL_BRIEF_SCHEDULER_TIMEZONE"] == "Asia/Singapore"
    assert calls[0]["env"]["INTEL_BRIEF_SCHEDULER_WINDOW_END"] == "10:00"
    assert calls[0]["delivery_clock"]() == host_time


@pytest.mark.parametrize(("hour", "minute", "reason"), [
    (8, 29, "skipped_before_window"),
    (10, 1, "skipped_late_trigger"),
    (20, 30, "skipped_late_trigger"),
])
def test_outside_window_skips_without_touching_cycle_evidence(tmp_path, hour, minute, reason):
    evidence = tmp_path / "latest.json"
    evidence.write_text('{"status":"previous_real_cycle"}')
    runner = Mock(side_effect=AssertionError("outside-window wake must not collect or send"))
    result = run_scheduled_intel_cycle(
        output_dir=tmp_path, evidence_path=evidence, clock=lambda: _time(hour=hour, minute=minute), cycle_runner=runner,
    )
    assert result["status"] == "skipped" and result["reason"] == reason
    assert result["network_calls"] == 0
    assert evidence.read_text() == '{"status":"previous_real_cycle"}'
    assert not (tmp_path / STATE_DIRECTORY).exists()
    runner.assert_not_called()


def test_window_catchup_once_per_singapore_date_across_restarts_and_days(tmp_path):
    runner = Mock(return_value={"status": "success", "network_calls": 0})
    kwargs = {"output_dir": tmp_path, "evidence_path": tmp_path / "latest.json", "cycle_runner": runner}
    first = run_scheduled_intel_cycle(**kwargs, clock=lambda: _time(hour=9, minute=12))
    repeated = run_scheduled_intel_cycle(**kwargs, clock=lambda: _time(hour=9, minute=30))
    boundary = run_scheduled_intel_cycle(**kwargs, clock=lambda: _time(hour=10, minute=0))
    tomorrow = run_scheduled_intel_cycle(**kwargs, clock=lambda: _time(day=13))
    assert first["status"] == tomorrow["status"] == "success"
    assert repeated["reason"] == boundary["reason"] == "business_date_already_claimed"
    assert runner.call_count == 2
    assert sorted(path.name for path in (tmp_path / STATE_DIRECTORY).glob("*.json")) == [
        "2026-09-12.json", "2026-09-13.json",
    ]


@pytest.mark.parametrize("outcome", ["failed", "blocked", "unknown", "exception", "invalid"])
def test_failed_or_unknown_run_is_not_automatically_replayed(tmp_path, outcome):
    def runner(**_kwargs):
        if outcome == "exception":
            raise RuntimeError("synthetic uncertain external outcome")
        if outcome == "invalid":
            return None
        return {"status": outcome, "network_calls": 0}

    first = run_scheduled_intel_cycle(
        output_dir=tmp_path, evidence_path=tmp_path / "latest.json", clock=_time, cycle_runner=runner,
    )
    second_runner = Mock(side_effect=AssertionError("a claimed day must require review"))
    repeated = run_scheduled_intel_cycle(
        output_dir=tmp_path, evidence_path=tmp_path / "latest.json", clock=_time, cycle_runner=second_runner,
    )
    expected_status = outcome if outcome in {"failed", "blocked", "unknown"} else "unknown"
    assert first["status"] == expected_status
    assert json.loads((tmp_path / STATE_DIRECTORY / "2026-09-12.json").read_text())["status"] == expected_status
    assert repeated["reason"] == "business_date_already_claimed"
    second_runner.assert_not_called()


def _concurrent_dispatch(output_dir, started, release):
    def runner(**_kwargs):
        started.set()
        assert release.wait(10)
        return {"status": "success", "network_calls": 0}

    run_scheduled_intel_cycle(
        output_dir=output_dir, evidence_path=Path(output_dir) / "latest.json", clock=_time, cycle_runner=runner,
    )


def test_separate_process_cannot_enter_an_active_cycle(tmp_path):
    context = multiprocessing.get_context("fork")
    started, release = context.Event(), context.Event()
    process = context.Process(target=_concurrent_dispatch, args=(str(tmp_path), started, release))
    process.start()
    try:
        assert started.wait(5)
        runner = Mock(side_effect=AssertionError("concurrent process must not enter the cycle"))
        result = run_scheduled_intel_cycle(
            output_dir=tmp_path, evidence_path=tmp_path / "latest.json", clock=_time, cycle_runner=runner,
        )
        assert result["reason"] == "scheduler_running"
        assert result["network_calls"] == 0
        runner.assert_not_called()
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
    assert process.exitcode == 0


def _crashed_dispatch(output_dir):
    def runner(**_kwargs):
        os._exit(23)

    run_scheduled_intel_cycle(
        output_dir=output_dir, evidence_path=Path(output_dir) / "latest.json", clock=_time, cycle_runner=runner,
    )


def test_process_death_keeps_claim_and_cannot_cause_duplicate_delivery(tmp_path):
    process = multiprocessing.get_context("fork").Process(target=_crashed_dispatch, args=(str(tmp_path),))
    process.start()
    process.join(5)
    if process.is_alive():
        process.terminate()
        process.join(5)
    assert process.exitcode == 23
    claim = json.loads((tmp_path / STATE_DIRECTORY / "2026-09-12.json").read_text())
    assert claim["status"] == "claimed"
    runner = Mock(side_effect=AssertionError("process death is an uncertain outcome"))
    result = run_scheduled_intel_cycle(
        output_dir=tmp_path, evidence_path=tmp_path / "latest.json", clock=_time, cycle_runner=runner,
    )
    assert result["reason"] == "business_date_already_claimed"
    runner.assert_not_called()


@pytest.mark.parametrize("symlink_target", ["output", "state", "lock"])
def test_symlinked_state_paths_block_before_cycle(tmp_path, symlink_target):
    output = tmp_path / "runs"
    output.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    if symlink_target == "output":
        output.rmdir()
        output.symlink_to(outside, target_is_directory=True)
    elif symlink_target == "state":
        (output / STATE_DIRECTORY).symlink_to(outside, target_is_directory=True)
    else:
        state = output / STATE_DIRECTORY
        state.mkdir()
        private = outside / "private.txt"
        private.write_text("must remain unchanged")
        (state / "dispatch.lock").symlink_to(private)
    runner = Mock(side_effect=AssertionError("untrusted paths must not run a cycle"))
    result = run_scheduled_intel_cycle(
        output_dir=output, evidence_path=output / "latest.json", clock=_time, cycle_runner=runner,
    )
    assert result["status"] == "blocked" and result["network_calls"] == 0
    runner.assert_not_called()
    if symlink_target == "lock":
        assert private.read_text() == "must remain unchanged"


def test_final_state_write_failure_does_not_erase_the_durable_claim(tmp_path, monkeypatch):
    from src.intel import scheduled_cycle

    monkeypatch.setattr(scheduled_cycle, "_finish_claim", Mock(side_effect=OSError("synthetic disk error")))
    runner = Mock(return_value={"status": "success", "network_calls": 1})
    kwargs = {"output_dir": tmp_path, "evidence_path": tmp_path / "latest.json", "clock": _time, "cycle_runner": runner}
    first = run_scheduled_intel_cycle(**kwargs)
    repeated = run_scheduled_intel_cycle(**kwargs)
    assert first["status"] == "unknown" and first["network_calls"] is None
    assert repeated["reason"] == "business_date_already_claimed"
    assert runner.call_count == 1


def test_scheduled_cli_uses_current_clock_dispatch_and_skip_is_success(tmp_path, monkeypatch):
    from scripts import intel_production_cycle as cli

    runner = Mock(return_value={"status": "skipped", "reason": "skipped_late_trigger", "network_calls": 0})
    monkeypatch.setattr(cli, "run_scheduled_intel_cycle", runner)
    assert cli.main(["--scheduled", "--output-dir", str(tmp_path), "--evidence", str(tmp_path / "latest.json")]) == 0
    assert not {"now", "clock", "stamp", "scheduled_time"}.intersection(runner.call_args.kwargs)
    assert not (tmp_path / "latest.json").exists()


@pytest.mark.parametrize("replay_args", [
    ["--now", "2026-09-12T00:30:00Z"], ["--now=2026-09-12T00:30:00Z"],
    ["--stamp", "synthetic"], ["--stamp=synthetic"], ["--time", "09:30"],
    ["--n", "2026-09-12T00:30:00Z"],
])
def test_scheduled_cli_rejects_replayed_clock_or_custom_window(tmp_path, monkeypatch, replay_args):
    from scripts import intel_production_cycle as cli

    runner = Mock(side_effect=AssertionError("invalid CLI must not dispatch"))
    monkeypatch.setattr(cli, "run_scheduled_intel_cycle", runner)
    with pytest.raises(SystemExit) as error:
        cli.main(["--scheduled", "--output-dir", str(tmp_path), "--evidence", str(tmp_path / "latest.json"), *replay_args])
    assert error.value.code == 2
    runner.assert_not_called()


def test_naive_scheduled_clock_is_rejected_before_state_or_cycle(tmp_path):
    with pytest.raises(ValueError, match="timezone aware"):
        run_scheduled_intel_cycle(
            output_dir=tmp_path, evidence_path=tmp_path / "latest.json", clock=lambda: datetime(2026, 9, 12, 8, 30),
        )
    assert not (tmp_path / STATE_DIRECTORY).exists()


def test_real_cycle_hard_gate_remains_blocked_without_ack_and_is_not_replayed(tmp_path):
    evidence = tmp_path / "latest.json"
    first = run_scheduled_intel_cycle(
        output_dir=tmp_path, evidence_path=evidence, project_root=tmp_path, clock=_time, env={},
    )
    assert first["status"] == "blocked" and first["network_calls"] == 0
    assert "production_ack_missing" in first["preflight"]["missing_gates"]
    assert first["preflight"]["scheduler_timezone"] == "Asia/Singapore"
    previous_evidence = evidence.read_bytes()
    repeated = run_scheduled_intel_cycle(
        output_dir=tmp_path, evidence_path=evidence, project_root=tmp_path, clock=_time, env={},
    )
    assert repeated["reason"] == "business_date_already_claimed"
    assert evidence.read_bytes() == previous_evidence


def test_suspended_cycle_cannot_deliver_on_a_different_business_date(tmp_path):
    readings = iter([_time(), _time(day=13)])
    sends = []

    def runner(**kwargs):
        kwargs["delivery_clock"]()
        sends.append("must not send on another claimed date")
        return {"status": "success", "network_calls": 1}

    result = run_scheduled_intel_cycle(
        output_dir=tmp_path, evidence_path=tmp_path / "latest.json", clock=lambda: next(readings), cycle_runner=runner,
    )
    assert result["status"] == "unknown" and not sends
    assert json.loads((tmp_path / STATE_DIRECTORY / "2026-09-12.json").read_text())["status"] == "unknown"
