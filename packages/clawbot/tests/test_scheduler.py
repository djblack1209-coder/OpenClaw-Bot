"""
Tests for src/scheduler.py — _now_et, Task, Scheduler.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, time, timedelta

from zoneinfo import ZoneInfo

from src.scheduler import _now_et, Task, Scheduler, ET

FAKE_NOW = datetime(2026, 2, 11, 10, 0, tzinfo=ET)


# ── _now_et ───────────────────────────────────────────────────────────

def test_now_et_returns_aware_datetime_in_et():
    dt = _now_et()
    assert dt.tzinfo is not None
    # Should resolve to America/New_York (ET or ZoneInfo key)
    assert "America/New_York" in str(dt.tzinfo) or dt.tzinfo == ET


# ── Task._calculate_next_run (schedule_time) ─────────────────────────

@patch("src.scheduler._now_et")
def test_calculate_next_run_schedule_before(mock_now):
    """schedule_time is later today → next_run is today."""
    mock_now.return_value = FAKE_NOW  # 10:00
    task = Task("t", AsyncMock(), schedule_time=time(12, 0))
    assert task.next_run == datetime(2026, 2, 11, 12, 0, tzinfo=ET)


@patch("src.scheduler._now_et")
def test_calculate_next_run_schedule_after(mock_now):
    """schedule_time already passed today → next_run is tomorrow."""
    mock_now.return_value = FAKE_NOW  # 10:00
    task = Task("t", AsyncMock(), schedule_time=time(8, 0))
    assert task.next_run == datetime(2026, 2, 12, 8, 0, tzinfo=ET)


# ── Task._calculate_next_run (interval_minutes) ──────────────────────

@patch("src.scheduler._now_et")
def test_calculate_next_run_interval_no_last_run(mock_now):
    """First run → next_run == now."""
    mock_now.return_value = FAKE_NOW
    task = Task("t", AsyncMock(), interval_minutes=5)
    assert task.next_run == FAKE_NOW


@patch("src.scheduler._now_et")
def test_calculate_next_run_interval_with_last_run(mock_now):
    """Has last_run → next_run == last_run + interval."""
    mock_now.return_value = FAKE_NOW
    task = Task("t", AsyncMock(), interval_minutes=10)
    task.last_run = FAKE_NOW - timedelta(minutes=3)
    task._calculate_next_run()
    assert task.next_run == task.last_run + timedelta(minutes=10)


# ── Task.should_run ──────────────────────────────────────────────────

@patch("src.scheduler._now_et")
def test_should_run_disabled(mock_now):
    mock_now.return_value = FAKE_NOW
    task = Task("t", AsyncMock(), interval_minutes=1, enabled=False)
    assert task.should_run() is False


@patch("src.scheduler._now_et")
def test_should_run_no_next_run(mock_now):
    mock_now.return_value = FAKE_NOW
    task = Task("t", AsyncMock())  # no schedule_time or interval
    assert task.next_run is None
    assert task.should_run() is False


@patch("src.scheduler._now_et")
def test_should_run_time_reached(mock_now):
    mock_now.return_value = FAKE_NOW
    task = Task("t", AsyncMock(), interval_minutes=1)
    # next_run == FAKE_NOW, so should_run is True
    assert task.should_run() is True


@patch("src.scheduler._now_et")
def test_should_run_time_not_reached(mock_now):
    mock_now.return_value = FAKE_NOW
    task = Task("t", AsyncMock(), schedule_time=time(12, 0))
    # next_run is 12:00, now is 10:00
    assert task.should_run() is False


# ── Task.run ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.scheduler._now_et")
async def test_task_run_success(mock_now):
    mock_now.return_value = FAKE_NOW
    func = AsyncMock(return_value="ok")
    task = Task("t", func, interval_minutes=5)

    result = await task.run()

    assert result == "ok"
    func.assert_awaited_once()
    assert task.last_run == FAKE_NOW
    assert task.next_run is not None


@pytest.mark.asyncio
@patch("src.scheduler._now_et")
async def test_task_run_exception_still_recalculates(mock_now):
    mock_now.return_value = FAKE_NOW
    func = AsyncMock(side_effect=RuntimeError("boom"))
    task = Task("t", func, interval_minutes=5)

    with pytest.raises(RuntimeError, match="boom"):
        await task.run()

    # next_run should still be recalculated despite the error
    assert task.next_run is not None


# ── Scheduler.add_task / remove_task ─────────────────────────────────

@patch("src.scheduler._now_et", return_value=FAKE_NOW)
def test_add_and_remove_task(_mock):
    s = Scheduler()
    s.add_task("a", AsyncMock(), interval_minutes=1)
    assert "a" in s.tasks

    s.remove_task("a")
    assert "a" not in s.tasks

    # removing non-existent key is a no-op
    s.remove_task("nonexistent")


# ── Scheduler.enable_task / disable_task ─────────────────────────────

@patch("src.scheduler._now_et", return_value=FAKE_NOW)
def test_enable_disable_task(_mock):
    s = Scheduler()
    s.add_task("a", AsyncMock(), interval_minutes=1)

    s.disable_task("a")
    assert s.tasks["a"].enabled is False

    s.enable_task("a")
    assert s.tasks["a"].enabled is True

    # no-op for unknown task names
    s.disable_task("nonexistent")
    s.enable_task("nonexistent")


# ── Scheduler.get_status ─────────────────────────────────────────────

@patch("src.scheduler._now_et", return_value=FAKE_NOW)
def test_get_status(_mock):
    s = Scheduler()
    s.add_task("a", AsyncMock(), interval_minutes=5)
    s.add_task("b", AsyncMock(), schedule_time=time(14, 0))

    status = s.get_status()
    assert len(status) == 2
    names = {d["name"] for d in status}
    assert names == {"a", "b"}
    for d in status:
        assert "enabled" in d
        assert "last_run" in d
        assert "next_run" in d


# ── Scheduler.start / stop ───────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.scheduler._now_et", return_value=FAKE_NOW)
async def test_start_stop(_mock):
    s = Scheduler()
    s.start()
    assert s._running is True

    # idempotent start — should not create a second task
    first_task = s._task
    s.start()
    assert s._task is first_task

    s.stop()
    assert s._running is False


# ── Scheduler._safe_run_task ─────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.scheduler._now_et", return_value=FAKE_NOW)
async def test_safe_run_task_catches_exception(_mock):
    s = Scheduler()
    func = AsyncMock(side_effect=RuntimeError("fail"))
    task = Task("t", func, interval_minutes=1)

    # _safe_run_task should swallow the exception
    await s._safe_run_task(task)
    func.assert_awaited_once()
