"""Ordinary scheduler lifecycle and real tick regressions; all jobs are fake."""
import asyncio
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.execution.scheduler import ExecutionScheduler, report_schedule

ET = ZoneInfo('America/New_York')


@pytest.mark.asyncio
async def test_two_real_ticks_survive_one_job_failure_and_reach_deal_and_budget(monkeypatch):
    ticks = 0

    async def sleep(_seconds):
        nonlocal ticks
        ticks += 1
        if ticks > 2:
            scheduler._running = False

    scheduler = ExecutionScheduler(clock=lambda: datetime(2026, 9, 10, 12, tzinfo=ET), sleep=sleep)
    jobs = ['_run_daily_brief', '_run_intel_brief', '_run_monitors',
            '_run_social_operator', '_run_bounty_scan', '_run_reminders', '_run_bill_checks',
            '_run_weekly_strategy_review', '_run_weekly_report', '_run_price_watch_check', '_run_budget_alert']
    for name in jobs:
        setattr(scheduler, name, AsyncMock())
    scheduler._run_monitors.side_effect = RuntimeError('synthetic failure')
    scheduler._run_cleanup = MagicMock()
    scan = AsyncMock()
    monkeypatch.setitem(sys.modules, 'src.shopping.deal_scanner', SimpleNamespace(scheduled_deal_scan=scan))
    await scheduler.start()
    await scheduler._task
    assert scan.await_count == 1
    assert scheduler._run_budget_alert.await_count == 2
    assert scheduler._run_daily_brief.await_count == 2
    assert not hasattr(scheduler, '_run_morning_news')
    assert scheduler._run_cleanup.call_count == 2
    assert not scheduler.is_running
    assert scheduler.runtime_status()['last_error']['job'] == '_run_monitors'


@pytest.mark.asyncio
async def test_start_is_idempotent_and_stop_waits_for_owned_task():
    gate = asyncio.Event()
    cancelled = asyncio.Event()

    async def sleep(_seconds):
        try:
            await gate.wait()
        finally:
            cancelled.set()

    scheduler = ExecutionScheduler(sleep=sleep)
    await scheduler.start()
    task = scheduler._task
    await asyncio.sleep(0)
    await scheduler.start()
    assert scheduler._task is task
    assert scheduler.is_running
    await scheduler.stop()
    assert task.done() and cancelled.is_set()
    assert not scheduler.is_running
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_crashed_task_is_not_reported_as_running():
    scheduler = ExecutionScheduler()
    scheduler._loop = AsyncMock(side_effect=RuntimeError('synthetic crash'))
    await scheduler.start()
    with pytest.raises(RuntimeError):
        await scheduler._task
    await asyncio.sleep(0)
    assert not scheduler.is_running
    assert scheduler.runtime_status()['last_error']['error_type'] == 'RuntimeError'
    await scheduler.stop()


def test_hub_keeps_news_queries_outside_the_scheduler(monkeypatch, tmp_path):
    import src.execution as execution
    monkeypatch.setattr(execution, 'DB_PATH', tmp_path / 'hub.db')
    monkeypatch.setattr(execution, 'ensure_db_dir', lambda: None)
    monkeypatch.setattr(execution, 'init_db', lambda *_: None)
    news = object()
    hub = execution.ExecutionHub(news_fetcher=news)
    assert hub.news_fetcher is news
    assert hub._monitor_mgr.news_fetcher is news
    assert not hasattr(hub._scheduler, 'news_fetcher')


@pytest.mark.parametrize(('now', 'clock_time', 'expected'), [
    ('2026-09-11T00:30:00-04:00', (23, 45), '2026-09-10T23:45:00-04:00'),
    ('2027-01-01T00:10:00-05:00', (23, 50), '2026-12-31T23:50:00-05:00'),
    ('2026-03-08T03:35:00-04:00', (2, 30), '2026-03-08T03:30:00-04:00'),
    ('2026-11-01T01:45:00-05:00', (1, 30), '2026-11-01T01:30:00-04:00'),
    ('2026-09-10T12:30:00+00:00', (8, 0), '2026-09-10T08:00:00-04:00'),
])
def test_schedule_uses_et_full_dates_dst_and_previous_day(now, clock_time, expected):
    assert report_schedule(datetime.fromisoformat(now), clock_time).isoformat() == expected


def test_weekly_schedule_crosses_year_with_full_sunday_date():
    planned = report_schedule(datetime(2027, 1, 1, tzinfo=UTC), (20, 30), weekday=6)
    assert planned.isoformat() == '2026-12-27T20:30:00-05:00'
    with pytest.raises(ValueError):
        report_schedule(datetime(2026, 9, 10), (8, 0))


@pytest.mark.asyncio
async def test_ordinary_jobs_use_planned_date(monkeypatch):
    now = datetime(2026, 9, 13, 21, tzinfo=ET)
    daily, weekly = AsyncMock(return_value='Daily'), AsyncMock(return_value='Weekly')
    monkeypatch.setitem(sys.modules, 'src.execution.daily_brief',
                        SimpleNamespace(generate_daily_brief=daily, weekly_report=weekly))
    async def run(_kind, planned, generate):
        return await generate(planned)
    delivery = SimpleNamespace(run=AsyncMock(side_effect=run))
    scheduler = ExecutionScheduler(clock=lambda: now, report_delivery=delivery)
    await scheduler._run_daily_brief(now, (8, 15))
    await scheduler._run_weekly_report()
    assert daily.call_args.kwargs['planned_at'].hour == 8
    assert weekly.call_args.kwargs['planned_at'].isoformat() == '2026-09-13T20:30:00-04:00'
    assert delivery.run.await_count == 2
    assert [call.args[0] for call in delivery.run.call_args_list] == ['daily_brief', 'weekly_report']


def test_controls_report_actual_task_state_and_durable_receipts(monkeypatch, tmp_path):
    from src.api.routers import controls
    from src.execution.report_delivery_store import ReportDeliveryStore
    store = ReportDeliveryStore(tmp_path / 'reports.db', clock=lambda: 1000, coverage_start=900)
    ident = store.ensure('daily_brief', 1000, 1200, 'telegram', 'synthetic-private-target')
    lease = store.claim(ident)
    store.begin_generation(ident, lease['token'])
    store.generated(ident, lease['token'], 'Synthetic report with enough content.', ['Synthetic report with enough content.'])
    attempt = store.begin_part(ident, lease['token'], 0)
    store.finish_part(ident, lease['token'], 0, attempt, 'unknown', reason='timeout')
    scheduler = ExecutionScheduler(report_delivery=SimpleNamespace(store=store))
    scheduler._running = True  # stale intent must not claim a live task
    scheduler._last_brief_date = '2026-09-10'
    monkeypatch.setitem(sys.modules, 'src.bot.globals', SimpleNamespace(execution_hub=SimpleNamespace(_scheduler=scheduler)))
    monkeypatch.setattr(controls, 'CONTROLS_STATE_FILE', tmp_path / 'controls.json')
    controls._save_state({'scheduler': {'tasks': {
        'daily_brief': {'last_run': 'fake', 'last_status': 'sent'},
        'morning_news': {'enabled': True, 'last_status': 'sent'},
    }}})
    status = controls.get_scheduler_status()
    daily = next(task for task in status['tasks'] if task['id'] == 'daily_brief')
    assert not status['scheduler_running']
    assert daily['last_status'] == 'unknown' and 'last_run' not in daily
    assert 'synthetic-private-target' not in str(status)
    assert all(task['id'] != 'morning_news' for task in status['tasks'])
    intel_gate = next(task for task in status['tasks'] if task['id'] == 'intel_brief')
    assert intel_gate['cron'] == '08:30 Asia/Singapore'
    assert '沙盒闸门' in intel_gate['name']


@pytest.mark.parametrize('enabled', [True, False])
def test_retired_news_toggle_does_not_modify_controls(monkeypatch, tmp_path, enabled):
    from fastapi import HTTPException

    from src.api.routers import controls

    path = tmp_path / 'controls.json'
    monkeypatch.setattr(controls, 'CONTROLS_STATE_FILE', path)
    with pytest.raises(HTTPException) as error:
        controls.toggle_task('morning_news', enabled)
    assert error.value.status_code == 410
    assert not path.exists()
