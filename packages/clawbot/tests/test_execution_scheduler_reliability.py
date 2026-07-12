"""ExecutionScheduler 的单项故障、重复启动和任务开关不得拖垮整个循环。"""

from __future__ import annotations

import ast
import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.execution.scheduler import ExecutionScheduler


@pytest.mark.asyncio
async def test_deal_scan_is_a_real_scheduler_method_with_cooldown(monkeypatch):
    scanner = AsyncMock()
    module = types.SimpleNamespace(scheduled_deal_scan=scanner)
    monkeypatch.setitem(sys.modules, "src.shopping.deal_scanner", module)
    scheduler = ExecutionScheduler()

    await scheduler._run_deal_scan(20_000.0)
    await scheduler._run_deal_scan(20_001.0)

    scanner.assert_awaited_once()
    assert scheduler._last_deal_scan_ts == 20_000.0


@pytest.mark.asyncio
async def test_guarded_job_failure_does_not_block_next_job():
    scheduler = ExecutionScheduler()
    calls: list[str] = []

    async def broken() -> None:
        raise RuntimeError("boom")

    async def healthy() -> None:
        calls.append("healthy")

    await scheduler._run_guarded("broken", broken, timeout_seconds=1)
    await scheduler._run_guarded("healthy", healthy, timeout_seconds=1)

    assert calls == ["healthy"]
    health = scheduler.get_health_snapshot()["jobs"]
    assert health["broken"]["status"] == "failed"
    assert health["broken"]["consecutive_failures"] == 1
    assert health["healthy"]["status"] == "ok"
    assert health["healthy"]["consecutive_failures"] == 0


@pytest.mark.asyncio
async def test_execution_scheduler_start_is_idempotent(monkeypatch):
    scheduler = ExecutionScheduler()
    gate = asyncio.Event()

    async def idle_loop() -> None:
        await gate.wait()

    monkeypatch.setattr(scheduler, "_loop", idle_loop)
    tasks: list[asyncio.Task] = []
    try:
        first_started = await scheduler.start()
        first_task = scheduler._task
        assert first_task is not None
        tasks.append(first_task)

        second_started = await scheduler.start()
        second_task = scheduler._task
        if second_task is not None and second_task not in tasks:
            tasks.append(second_task)

        assert first_started is True
        assert second_started is False
        assert second_task is first_task
    finally:
        gate.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        scheduler._running = False
        scheduler._task = None


@pytest.mark.asyncio
async def test_scheduler_controls_pause_loop_and_disable_individual_job(monkeypatch, tmp_path):
    controls = tmp_path / "controls_state.json"
    monkeypatch.setenv("OPENCLAW_CONTROLS_STATE_FILE", str(controls))
    scheduler = ExecutionScheduler()
    job_names = [
        "_run_daily_brief",
        "_run_intel_brief",
        "_run_morning_news",
        "_run_monitors",
        "_run_social_operator",
        "_run_bounty_scan",
        "_run_cleanup",
        "_run_reminders",
        "_run_bill_checks",
        "_run_xianyu_shipment_check",
        "_run_stock_check",
        "_run_weekly_strategy_review",
        "_run_weekly_report",
        "_run_price_watch_check",
        "_run_deal_scan",
        "_run_budget_alert",
    ]
    mocks = {name: AsyncMock() for name in job_names}
    for name, mock in mocks.items():
        monkeypatch.setattr(scheduler, name, mock)

    controls.write_text('{"scheduler":{"enabled":false}}', encoding="utf-8")
    await scheduler._run_iteration(
        now=types.SimpleNamespace(),
        ts=20_000.0,
        brief_time=(8, 0),
        intel_brief_time=(8, 30),
        monitor_interval=900,
        bounty_interval=2700,
        social_op_interval=0,
    )
    assert all(mock.await_count == 0 for mock in mocks.values())

    controls.write_text(
        '{"scheduler":{"enabled":true,"tasks":{"deal_scan":{"enabled":false}}}}',
        encoding="utf-8",
    )
    await scheduler._run_iteration(
        now=types.SimpleNamespace(),
        ts=40_000.0,
        brief_time=(8, 0),
        intel_brief_time=(8, 30),
        monitor_interval=900,
        bounty_interval=2700,
        social_op_interval=0,
    )
    assert mocks["_run_deal_scan"].await_count == 0
    assert mocks["_run_budget_alert"].await_count == 1
    assert scheduler.get_health_snapshot()["jobs"]["deal_scan"]["status"] == "disabled"


def test_every_scheduler_run_call_resolves_to_a_class_method():
    """防止方法再次因缩进错误变成模块函数或另一个函数的内部函数。"""
    source_path = Path(__file__).resolve().parents[1] / "src" / "execution" / "scheduler.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    scheduler_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ExecutionScheduler"
    )
    methods = {
        node.name
        for node in scheduler_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    called = {
        node.func.attr
        for node in ast.walk(scheduler_class)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr.startswith("_run_")
    }

    assert called <= methods
    assert "_run_deal_scan" in methods
