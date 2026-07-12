"""调度器控制开关必须真实生效，并向状态接口暴露脱敏运行健康。"""

from __future__ import annotations

import json
import stat
import sys
import types
from types import SimpleNamespace

from src.api.routers import controls
from src.execution import scheduler as scheduler_module


def test_scheduler_toggles_are_atomic_private_and_consumed_by_runtime(monkeypatch, tmp_path):
    state_file = tmp_path / "data" / "controls_state.json"
    monkeypatch.setattr(controls, "CONTROLS_STATE_FILE", state_file)
    monkeypatch.setenv("OPENCLAW_CONTROLS_STATE_FILE", str(state_file))

    controls.toggle_scheduler(False)
    controls.toggle_task("deal_scan", False)

    payload = json.loads(state_file.read_text(encoding="utf-8"))
    runtime = scheduler_module._load_scheduler_controls()
    assert payload["scheduler"]["enabled"] is False
    assert payload["scheduler"]["tasks"]["deal_scan"]["enabled"] is False
    assert runtime["enabled"] is False
    assert scheduler_module._task_enabled(runtime, "deal_scan") is False
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(state_file.parent.stat().st_mode) == 0o700


def test_scheduler_status_lists_deal_scan_and_live_failure_health(monkeypatch):
    scheduler = scheduler_module.ExecutionScheduler()
    scheduler._running = True
    scheduler._iteration_count = 3
    scheduler._last_loop_at = "2026-07-12T16:00:00+00:00"
    scheduler._last_loop_completed_at = "2026-07-12T16:00:01+00:00"
    scheduler._job_health["deal_scan"] = {
        "status": "failed",
        "last_attempt_at": "2026-07-12T16:00:00+00:00",
        "last_success_at": "",
        "consecutive_failures": 2,
        "error_type": "TimeoutError",
        "duration_seconds": 1.25,
    }
    fake_globals = types.ModuleType("src.bot.globals")
    fake_globals.execution_hub = SimpleNamespace(_scheduler=scheduler)
    monkeypatch.setitem(sys.modules, "src.bot.globals", fake_globals)
    monkeypatch.setattr(controls, "_load_state", lambda: {})

    status = controls.get_scheduler_status()

    deal_scan = next(task for task in status["tasks"] if task["id"] == "deal_scan")
    assert status["scheduler_running"] is True
    assert status["runtime_health"]["iteration_count"] == 3
    assert deal_scan["last_status"] == "failed"
    assert deal_scan["consecutive_failures"] == 2
    assert deal_scan["duration_seconds"] == 1.25
    assert "error_type" not in deal_scan
