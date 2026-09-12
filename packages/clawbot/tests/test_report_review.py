"""Review regressions use actual preference code and temporary cost ledgers."""
import ast
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from src.core.cost_control import CostController
from src.execution.report_delivery import ReportPreferences
from src.execution.scheduler import ExecutionScheduler

pytest_plugins = ['tests.test_report_delivery']

ET = ZoneInfo('America/New_York')


def actual_preferences(directory):
    # Execute the unmodified class AST without constructing unrelated global bots.
    source = Path(__file__).parents[1] / 'src/bot/globals.py'
    tree = ast.parse(source.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'UserPreferencesManager')
    namespace = {'Path': Path, '_json': json, 'logger': logging.getLogger(__name__)}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['UserPreferencesManager'](str(directory))


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['{', '[]', '{"456": []}', '{"456": {"daily_report": "false"}}', 'permission'])
async def test_actual_preference_failure_blocks_then_recovers(rig, tmp_path, monkeypatch, bad):
    service, store, _, calls, _, now, _ = rig
    prefs = actual_preferences(tmp_path)
    prefs._filepath.write_text(bad if bad != 'permission' else '{}')
    monkeypatch.setenv('OPS_BRIEF_ENABLED', '1')
    service.allowed = ReportPreferences(tmp_path / 'controls.json', prefs, lambda: 456, lambda: 456)
    generate = AsyncMock(return_value='Synthetic report after preferences become readable.')
    planned = datetime.fromtimestamp(now[0], ET)
    original_open = Path.open
    def checked_open(path, *args, **kwargs):
        if path == prefs._filepath and bad == 'permission':
            raise PermissionError('synthetic file permission failure')
        return original_open(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'open', checked_open)
        ident = await service.run('daily_brief', planned, generate)
    assert store.get(ident)['state'] == 'blocked'
    assert store.get(ident)['generation_attempts'] == 0
    assert not calls and generate.await_count == 0
    prefs._filepath.write_text('{}')
    now[0] += 61
    assert await service.run('daily_brief', planned, generate) == ident
    assert store.get(ident)['state'] == 'sent'
    assert generate.await_count == len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('explicit', [False, None])
async def test_actual_preference_disabled_and_normal_default(rig, tmp_path, monkeypatch, explicit):
    service, store, _, calls, _, now, _ = rig
    prefs = actual_preferences(tmp_path)
    if explicit is not None:
        prefs.set(456, 'daily_report', explicit)
    monkeypatch.setenv('OPS_BRIEF_ENABLED', '1')
    service.allowed = ReportPreferences(tmp_path / 'controls.json', prefs, lambda: 456, lambda: 456)
    generate = AsyncMock(return_value='Synthetic report with explicit default contract.')
    ident = await service.run('daily_brief', datetime.fromtimestamp(now[0], ET), generate)
    assert store.get(ident)['state'] == ('disabled' if explicit is False else 'sent')
    assert len(calls) == generate.await_count == (0 if explicit is False else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('expiry', [False, True])
async def test_maintenance_resume_or_expire_with_actual_preferences(rig, tmp_path, monkeypatch, expiry):
    service, store, _, calls, _, now, _ = rig
    path = tmp_path / 'controls.json'
    path.write_text('{"scheduler": {"maintenance_mode": true}}')
    service.allowed = ReportPreferences(path, actual_preferences(tmp_path), lambda: 456, lambda: 456)
    monkeypatch.setenv('OPS_BRIEF_ENABLED', '1')
    generate = AsyncMock(return_value='Synthetic report resumes inside its bounded window.')
    planned = datetime.fromtimestamp(now[0], ET)
    ident = await service.run('daily_brief', planned, generate)
    assert store.get(ident)['state'] == 'blocked'
    assert not calls and not generate.await_count
    path.write_text('{}')
    now[0] += 7201 if expiry else 61
    await service.run('daily_brief', planned, generate)
    assert store.get(ident)['state'] == ('expired' if expiry else 'sent')
    assert len(calls) == generate.await_count == (0 if expiry else 1)


@pytest.mark.asyncio
async def test_maintenance_after_first_receipt_resumes_only_remaining_parts(rig, tmp_path, monkeypatch):
    service, store, _, calls, outcomes, now, _ = rig
    path = tmp_path / 'controls.json'
    service.allowed = ReportPreferences(path, actual_preferences(tmp_path), lambda: 456, lambda: 456)
    monkeypatch.setenv('OPS_BRIEF_ENABLED', '1')
    def begin_maintenance():
        path.write_text('{"global_settings": {"maintenance_mode": true}}')
        return 200
    outcomes.append(begin_maintenance)
    generate = AsyncMock(return_value='😀' * 3000)
    planned = datetime.fromtimestamp(now[0], ET)
    ident = await service.run('daily_brief', planned, generate)
    assert store.get(ident)['state'] == 'blocked' and len(calls) == 1
    path.write_text('{}')
    now[0] += 61
    await service.run('daily_brief', planned, generate)
    assert store.get(ident)['state'] == 'sent'
    assert len(calls) == 2 and generate.await_count == 1


@pytest.mark.asyncio
async def test_actual_missing_private_target_has_distinct_reason(rig, tmp_path):
    service, store, transport, calls, _, now, _ = rig
    transport.private_target = lambda: None
    service.allowed = ReportPreferences(tmp_path / 'controls.json', actual_preferences(tmp_path), lambda: 456, lambda: None)
    generate = AsyncMock()
    ident = await service.run('weekly_report', datetime.fromtimestamp(now[0], ET), generate)
    assert store.get(ident)['state'] == 'blocked'
    assert store.get(ident)['reason'] == 'target_unavailable'
    assert not calls and not generate.await_count


def test_saved_preferences_disappearing_are_not_normal_defaults(tmp_path):
    prefs = actual_preferences(tmp_path)
    assert prefs.report_enabled(456) is True
    prefs.set(456, 'daily_report', False)
    prefs._filepath.unlink()
    with pytest.raises(ValueError, match='missing'):
        prefs.report_enabled(456)


@pytest.mark.asyncio
async def test_cancelled_stop_still_waits_before_start_can_replace_task():
    cancelling, release = asyncio.Event(), asyncio.Event()
    async def loop():
        try:
            await asyncio.Event().wait()
        finally:
            cancelling.set()
            await release.wait()
    scheduler = ExecutionScheduler()
    scheduler._loop = loop
    await scheduler.start()
    old = scheduler._task
    await asyncio.sleep(0)
    stop = asyncio.create_task(scheduler.stop())
    await cancelling.wait()
    stop.cancel()
    start = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0)
    assert scheduler._task is old and not old.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await stop
    await start
    assert scheduler.is_running and old.done()
    await scheduler.stop()


@pytest.mark.asyncio
async def test_stop_start_interleaving_retains_owned_task():
    entered, cancelling, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def loop():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelling.set()
            await release.wait()
    scheduler = ExecutionScheduler()
    scheduler._loop = loop
    await scheduler.start()
    old = scheduler._task
    await entered.wait()
    stop = asyncio.create_task(scheduler.stop())
    await cancelling.wait()
    start = asyncio.create_task(scheduler.start())
    await asyncio.sleep(0)
    leaked = scheduler._task if scheduler._task is not old else None
    release.set()
    await stop
    await start
    try:
        assert scheduler.is_running and scheduler._task is not old
        assert old.done()
    finally:
        await scheduler.stop()
        if leaked and not leaked.done():
            leaked.cancel()
            await asyncio.gather(leaked, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['positive', 'zero', 'inactive', 'pending', 'short_history'])
async def test_report_cost_consumers_use_ledger_and_explicit_coverage(tmp_path, monkeypatch, mode):
    from src.execution.daily_brief_data import _brief_api_cost, _collect_brief_metrics
    from src.execution.weekly_report import weekly_report
    now = [datetime(2026, 9, 3, 8, tzinfo=ET)]
    controller = CostController(20, ledger_path=tmp_path / 'cost.db', clock=lambda: now[0])
    if mode != 'inactive':
        if mode == 'short_history':
            now[0] = datetime(2026, 9, 10, 8, tzinfo=ET)
        controller.ledger.activate(opening_spend_usd=0)
    now[0] = datetime(2026, 9, 10, 8, tzinfo=ET)
    if mode in {'positive', 'short_history', 'pending'}:
        controller.record_cost('fixture', 1.25)
    if mode == 'pending':
        controller.ledger.reserve(attempt_id='pending', request_id='request', provider='fixture',
            deployment_id='fixture', model='fixture', price_snapshot='fixture', budget_usd=20, max_cost_usd=.1)
    monkeypatch.setattr('src.core.cost_control.get_cost_controller', lambda: controller)
    import sys
    monkeypatch.setitem(sys.modules, 'src.monitoring', SimpleNamespace(cost_analyzer=SimpleNamespace(
        predict_monthly_cost=lambda: pytest.fail('legacy cost source must not be read'))))
    monkeypatch.setitem(sys.modules, 'src.invest_tools', SimpleNamespace(get_fear_greed_index=AsyncMock(return_value={})))
    sections = []
    await _brief_api_cost(sections)
    text = str(sections)
    assert '已知费用' in text and '覆盖' in text and '截至' in text
    assert ('$1.2500' if mode in {'positive', 'short_history', 'pending'} else '$0.0000') in text
    metrics = await _collect_brief_metrics(db_path=tmp_path / 'brief.db')
    assert metrics['api_daily_cost'] == (None if mode in {'inactive', 'pending'} else (0 if mode == 'zero' else 1.25))
    assert 'api_cost_context' in metrics
    weekly = await weekly_report(planned_at=now[0])
    assert '已知费用' in weekly and '覆盖' in weekly and '截至' in weekly
    assert ('完整费用: 未知' in weekly) == (mode in {'inactive', 'pending', 'short_history'})


@pytest.mark.asyncio
async def test_midnight_catchup_cost_uses_planned_day_and_current_asof(tmp_path, monkeypatch):
    from src.execution.daily_brief_data import _brief_api_cost, _collect_brief_metrics
    from src.execution.weekly_report import weekly_report
    now = [datetime(2026, 9, 10, 8, tzinfo=ET)]
    controller = CostController(20, ledger_path=tmp_path / 'cost.db', clock=lambda: now[0])
    controller.ledger.activate(opening_spend_usd=1.25)
    planned = datetime(2026, 9, 10, 23, 45, tzinfo=ET)
    now[0] = datetime(2026, 9, 11, 0, 30, tzinfo=ET)
    controller.record_cost('fixture', 2.5)
    monkeypatch.setattr('src.core.cost_control.get_cost_controller', lambda: controller)
    sections = []
    await _brief_api_cost(sections, planned_at=planned)
    text = str(sections)
    assert '$1.2500' in text and '$2.5000' not in text
    assert '2026-09-10' in text and '2026-09-11T00:30:00-04:00' in text
    metrics = await _collect_brief_metrics(db_path=tmp_path / 'brief.db', planned_at=planned)
    assert metrics['api_daily_cost'] == 1.25
    weekly = await weekly_report(planned_at=planned.astimezone(ZoneInfo('UTC')))
    assert '2026-09-04 — 2026-09-10' in weekly


@pytest.mark.asyncio
async def test_cost_read_failure_is_unknown_in_actual_consumers(tmp_path, monkeypatch):
    from src.execution.daily_brief_data import _brief_api_cost, _collect_brief_metrics
    from src.execution.weekly_report import weekly_report
    def unavailable():
        raise OSError('synthetic unavailable ledger')
    monkeypatch.setattr('src.core.cost_control.get_cost_controller', unavailable)
    sections = []
    await _brief_api_cost(sections)
    assert '已知费用: 未知' in str(sections) and '$0.0000' not in str(sections)
    metrics = await _collect_brief_metrics(db_path=tmp_path / 'brief.db')
    assert metrics['api_daily_cost'] is None and metrics['known_api_daily_cost'] is None
    assert '已知费用: 未知' in await weekly_report()


@pytest.mark.asyncio
async def test_nullable_cost_reaches_actual_summary_prompt_and_fallback(monkeypatch):
    from src.execution.daily_brief_llm import _generate_daily_recommendations, _generate_executive_summary
    from src.litellm_router import free_pool
    fake = AsyncMock(side_effect=RuntimeError('synthetic model unavailable'))
    monkeypatch.setattr(free_pool, 'acompletion', fake)
    metrics = {'api_daily_cost': None, 'api_cost_context': '已知费用: $1.2500；完整费用: 未知；未决请求: 1'}
    summary = await _generate_executive_summary(metrics)
    await _generate_daily_recommendations(metrics)
    assert fake.await_count == 2
    assert all('完整费用: 未知' in call.kwargs['messages'][0]['content'] for call in fake.await_args_list)
    assert '完整费用: 未知' in summary
