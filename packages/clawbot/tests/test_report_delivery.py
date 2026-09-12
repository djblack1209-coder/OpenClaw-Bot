"""Exercise the real Telegram SDK with a local HTTP transport, never a server."""
import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from telegram import Bot
from telegram.request import HTTPXRequest

from src.execution.report_delivery import (
    Receipt,
    ReportDeliveryService,
    ReportPreferences,
    Target,
    TelegramTransport,
    split_report,
)
from src.execution.report_delivery_store import ReportDeliveryStore

ET = ZoneInfo('America/New_York')


@pytest_asyncio.fixture
async def rig(tmp_path):
    calls, outcomes = [], []
    async def handler(request):
        if request.url.path.endswith('/getMe'):
            return httpx.Response(200, json={'ok': True, 'result': {'id': 123, 'is_bot': True, 'first_name': 'Synthetic'}})
        calls.append(json.loads(request.content) if request.headers.get('content-type') == 'application/json' else request.content.decode())
        outcome = outcomes.pop(0) if outcomes else 200
        if callable(outcome):
            outcome = outcome()
        if outcome == 'timeout':
            raise httpx.ReadTimeout('synthetic', request=request)
        if outcome == 'cancel':
            raise asyncio.CancelledError()
        if outcome != 200:
            return httpx.Response(outcome, json={'ok': False, 'error_code': outcome,
                'description': 'synthetic rejection', 'parameters': {'retry_after': 90} if outcome == 429 else {}})
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': len(calls), 'date': 1,
            'chat': {'id': 456, 'type': 'private'}, 'text': 'accepted'}})
    bot = Bot('123:synthetic', request=HTTPXRequest(httpx_kwargs={'transport': httpx.MockTransport(handler)}))
    await bot.initialize()
    now = [datetime(2026, 9, 10, 8, tzinfo=ET).timestamp()]
    store = ReportDeliveryStore(tmp_path / 'reports.db', clock=lambda: now[0], coverage_start=now[0]-1)
    transport = TelegramTransport(lambda: bot, lambda: 456, lambda: 456)
    enabled = [True]
    service = ReportDeliveryService(store, transport, allowed=lambda *_: enabled[0])
    yield service, store, transport, calls, outcomes, now, enabled
    await bot.shutdown()


def test_split_preserves_unicode_and_whitespace():
    text = ('😀\n汉字 ' * 1700) + '\n'
    parts = split_report(text)
    assert ''.join(parts) == text
    assert all(len(p.encode('utf-16-le')) // 2 <= 4000 for p in parts)


@pytest.mark.asyncio
async def test_success_persisted_once_across_restart(rig):
    service, store, transport, calls, _, now, _ = rig
    planned = datetime.fromtimestamp(now[0], ET)
    generated = []
    async def generate(_):
        generated.append(1)
        return 'A cached report with enough content to send.'
    ident = await service.run('daily_brief', planned, generate)
    restarted = ReportDeliveryService(ReportDeliveryStore(store.path, clock=lambda: now[0]), transport)
    await restarted.run('daily_brief', planned, generate)
    row = store.get(ident)
    assert row['state'] == 'sent' and row['parts'][0]['message_id'] == '1'
    assert row['generation_quality'] == 'unverified'
    assert len(calls) == len(generated) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(('outcome', 'state'), [(400, 'permanent_failure'), (403, 'permanent_failure'),
    (429, 'retryable_failure'), (500, 'unknown'), ('timeout', 'unknown')])
async def test_sdk_outcomes_have_no_hidden_retries(rig, outcome, state):
    service, store, _, calls, outcomes, now, _ = rig
    outcomes.append(outcome)
    async def generate(_):
        return 'Synthetic report that must not be delivered twice.'
    planned = datetime.fromtimestamp(now[0], ET)
    ident = await service.run('daily_brief', planned, generate)
    assert store.get(ident)['state'] == state
    await service.run('daily_brief', planned, generate)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_partial_ack_then_429_reuses_only_remaining_cached_parts(rig):
    service, store, _, calls, outcomes, now, _ = rig
    outcomes.extend([200, 429])
    generated = []
    async def generate(_):
        generated.append(1)
        return '😀' * 4500
    planned = datetime.fromtimestamp(now[0], ET)
    ident = await service.run('daily_brief', planned, generate)
    assert [p['state'] for p in store.get(ident)['parts']] == ['sent', 'retryable_failure', 'ready']
    now[0] += 91
    await service.run('daily_brief', planned, generate)
    assert store.get(ident)['state'] == 'sent'
    assert len(calls) == 4 and len(generated) == 1


@pytest.mark.asyncio
async def test_cancel_after_request_is_unknown_and_propagates(rig):
    service, store, _, calls, outcomes, now, _ = rig
    outcomes.append('cancel')
    async def generate(_):
        return 'Cancellation cannot establish whether Telegram accepted this.'
    planned = datetime.fromtimestamp(now[0], ET)
    with pytest.raises(asyncio.CancelledError):
        await service.run('daily_brief', planned, generate)
    await service.run('daily_brief', planned, generate)
    assert store.summary()['counts'] == {'unknown': 1}
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_failed_receipt_write_is_unknown_on_restart(rig, monkeypatch):
    service, store, _, calls, _, now, _ = rig
    original = store.finish_part
    monkeypatch.setattr(store, 'finish_part', lambda *a, **kw: (_ for _ in ()).throw(OSError('synthetic disk failure')))
    async def generate(_):
        return 'Accepted by API but local receipt write fails.'
    planned = datetime.fromtimestamp(now[0], ET)
    with pytest.raises(OSError):
        await service.run('daily_brief', planned, generate)
    monkeypatch.setattr(store, 'finish_part', original)
    await service.run('daily_brief', planned, generate)
    assert store.summary()['counts'] == {'unknown': 1} and len(calls) == 1


@pytest.mark.asyncio
async def test_missing_private_target_and_preference_stop_generation(rig):
    service, store, transport, calls, _, now, enabled = rig
    transport.private_target = lambda: 0
    async def generate(_):
        pytest.fail('must not generate without target or preference')
    planned = datetime.fromtimestamp(now[0], ET)
    ident = await service.run('weekly_report', planned, generate)
    assert store.get(ident)['state'] == 'blocked'
    enabled[0] = False
    ident = await service.run('daily_brief', planned, generate)
    assert store.get(ident)['state'] == 'disabled' and not calls


@pytest.mark.asyncio
async def test_preference_rechecked_after_generation(rig):
    service, store, _, calls, _, now, enabled = rig
    async def generate(_):
        enabled[0] = False
        return 'User preference changed while generating this report.'
    ident = await service.run('daily_brief', datetime.fromtimestamp(now[0], ET), generate)
    assert store.get(ident)['state'] == 'disabled' and not calls


@pytest.mark.asyncio
async def test_two_service_instances_concurrently_generate_and_send_once(rig):
    service, store, transport, calls, _, now, _ = rig
    entered, finish = asyncio.Event(), asyncio.Event()
    async def generate(_):
        entered.set()
        await finish.wait()
        return 'Concurrent processes share this one cached report.'
    planned = datetime.fromtimestamp(now[0], ET)
    first = asyncio.create_task(service.run('daily_brief', planned, generate))
    await entered.wait()
    other = ReportDeliveryService(ReportDeliveryStore(store.path, clock=lambda: now[0]), transport)
    ident = await other.run('daily_brief', planned, generate)
    finish.set()
    assert await first == ident
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_mirror_unknown_is_independent_and_never_replays_primary(rig):
    service, store, _, calls, _, now, _ = rig
    class Mirror:
        channel = 'wechat'
        sends = 0
        def target(self, _):
            return Target('synthetic-mirror', 'synthetic-user')
        async def send(self, target, text):
            self.sends += 1
            return Receipt('unknown', reason='legacy_mirror_receipt_unverified')
    mirror = Mirror()
    service.mirror = mirror
    async def generate(_):
        return 'Independent mirror delivery from the same stored content.'
    planned = datetime.fromtimestamp(now[0], ET)
    await service.run('daily_brief', planned, generate)
    await service.run('daily_brief', planned, generate)
    assert store.summary()['counts'] == {'sent': 1, 'unknown': 1}
    assert mirror.sends == len(calls) == 1


@pytest.mark.asyncio
async def test_preference_change_between_parts_preserves_first_ack(rig):
    service, store, _, calls, outcomes, now, enabled = rig
    def disable():
        enabled[0] = False
        return 200
    outcomes.append(disable)
    async def generate(_):
        return 'A' * 8000
    ident = await service.run('daily_brief', datetime.fromtimestamp(now[0], ET), generate)
    assert store.get(ident)['state'] == 'disabled'
    assert [part['state'] for part in store.get(ident)['parts']] == ['sent', 'ready']
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_generation_retry_and_window_do_not_send_fallback(rig):
    service, store, _, calls, _, now, _ = rig
    generated = []
    async def generate(_):
        generated.append(1)
        raise RuntimeError('synthetic provider unavailable')
    planned = datetime.fromtimestamp(now[0], ET)
    for _ in range(4):
        ident = await service.run('daily_brief', planned, generate)
        now[0] += 61
    assert store.get(ident)['state'] == 'permanent_failure'
    assert len(generated) == 3 and not calls
    now[0] += 7200
    ident = await service.run('weekly_report', planned, generate)
    assert store.get(ident)['state'] == 'expired'


def test_preferences_honor_controls_flags_and_recipient(tmp_path, monkeypatch):
    from unittest.mock import Mock
    path = tmp_path / 'controls.json'
    prefs = Mock()
    prefs.report_enabled.return_value = True
    allowed = ReportPreferences(path, prefs, lambda: 456, lambda: 789)
    monkeypatch.setenv('OPS_BRIEF_ENABLED', '1')
    assert allowed('daily_brief', None, 'telegram')
    assert allowed('weekly_report', None, 'telegram')
    prefs.report_enabled.assert_called_with(789)
    for state in [{'scheduler': {'enabled': False}}, {'scheduler': {'maintenance_mode': True}},
                  {'global_settings': {'scheduler_enabled': False}}, {'global_settings': {'maintenance_mode': True}},
                  {'scheduler': {'tasks': {'daily_brief': {'enabled': False}}}}]:
        path.write_text(json.dumps(state))
        assert not allowed('daily_brief', None, 'telegram')
    path.write_text('{}')
    monkeypatch.setenv('OPS_BRIEF_ENABLED', '0')
    assert not allowed('daily_brief', None, 'telegram')
    monkeypatch.setenv('WECHAT_NOTIFY_ENABLED', '0')
    assert not allowed('weekly_report', None, 'wechat')


@pytest.mark.parametrize('channel', ['telegram', 'wechat'])
@pytest.mark.parametrize('control_text', ['{}', '{"scheduler":{"tasks":{"morning_news":{"enabled":true}}}}', 'invalid json'])
def test_retired_news_cannot_be_revived_by_legacy_controls_or_env(tmp_path, monkeypatch, channel, control_text):
    from unittest.mock import Mock

    path = tmp_path / 'controls.json'
    path.write_text(control_text)
    prefs = Mock()
    allowed = ReportPreferences(path, prefs, lambda: 456, lambda: 789)
    monkeypatch.setenv('MORNING_NEWS_ENABLED', '1')
    monkeypatch.setenv('WECHAT_NOTIFY_ENABLED', '1')
    decision = allowed('morning_news', None, channel)
    assert not decision
    assert decision.state == 'disabled'
    assert decision.reason == 'retired_to_global_intelligence'
    prefs.report_enabled.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('cached_content', [False, True])
async def test_retired_news_history_is_preserved_without_generation_or_send(rig, tmp_path, monkeypatch, cached_content):
    from unittest.mock import Mock

    service, store, _, calls, _, now, _ = rig
    monkeypatch.setenv('MORNING_NEWS_ENABLED', '1')
    service.allowed = ReportPreferences(tmp_path / 'controls.json', Mock(), lambda: 456, lambda: 456)
    planned = datetime.fromtimestamp(now[0], ET)
    original_id = store.ensure('morning_news', planned.timestamp(), planned.timestamp() + 7200, 'telegram', '123:456')
    if cached_content:
        claim = store.claim(original_id)
        store.begin_generation(original_id, claim['token'])
        text = 'Previously generated legacy news must not be delivered.'
        store.generated(original_id, claim['token'], text, [text])
        store.release(original_id, claim['token'])

    async def generate(_):
        pytest.fail('retired news must not generate content')

    ident = await service.run('morning_news', planned, generate)
    assert ident == original_id
    assert store.get(ident)['state'] == 'disabled'
    assert store.get(ident)['reason'] == 'retired_to_global_intelligence'
    assert not calls
    assert store.summary()['reports'][0]['kind'] == 'morning_news'


@pytest.mark.asyncio
async def test_broken_preferences_block_before_generation(rig):
    service, store, _, calls, _, now, _ = rig
    def unavailable(*_):
        raise OSError('synthetic config read error')
    service.allowed = unavailable
    async def generate(_):
        pytest.fail('configuration read failure must fail closed')
    ident = await service.run('daily_brief', datetime.fromtimestamp(now[0], ET), generate)
    assert store.get(ident)['reason'] == 'preference_unavailable' and not calls


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', [200, 403, 500, 'timeout'])
async def test_legacy_mirror_uses_one_http_attempt_and_never_claims_ack(monkeypatch, outcome):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src import wechat_bridge
    from src.execution.report_delivery import LegacyWechatTransport
    calls = []
    async def handler(request):
        calls.append(request)
        if outcome == 'timeout':
            raise httpx.ReadTimeout('synthetic', request=request)
        return httpx.Response(outcome, json={'errcode': 0})
    monkeypatch.setattr(wechat_bridge, '_WECHAT_ENABLED', True)
    monkeypatch.setattr(wechat_bridge, '_creds', SimpleNamespace(token='synthetic', user_id='synthetic-user',
        warned=False, clear_context=lambda: None))
    monkeypatch.setattr(wechat_bridge, '_get_context_token', AsyncMock(return_value='synthetic-context'))
    monkeypatch.setattr(wechat_bridge._single_http, '_new_client',
                        lambda **_: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    mirror = LegacyWechatTransport()
    receipt = await mirror.send(mirror.target('daily_brief'), 'Synthetic mirror message')
    assert receipt.status == 'unknown' and receipt.message_id is None
    assert len(calls) == 1
