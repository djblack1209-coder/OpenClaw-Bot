"""Manual requests through real ASGI routes and IBKRBridge; only IB transport is fake."""

import asyncio
import copy
import multiprocessing
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from src.trading.manual_trade_service import ManualTradeService, normalize_order
from src.trading.manual_trade_store import PROTOCOL, ManualTradeError, ManualTradeStore

TOKEN = 'synthetic-api-token'
ACCOUNT = 'DU1234567'


class FakeIB:
    def __init__(self):
        self.connected = True
        self.accounts = [ACCOUNT]
        self.client = SimpleNamespace(serverVersion=lambda: 190)
        self.calls, self.trades = [], []
        self.fault = None
        self.status = 'Filled'
        self.filled = None
        self.snapshot_empty = False
        self.qualify_hook = None

    def isConnected(self):
        return self.connected

    def managedAccounts(self):
        return list(self.accounts)

    async def qualifyContractsAsync(self, contract):
        contract.conId = 123
        if self.qualify_hook:
            self.qualify_hook()
        return [contract]

    def positions(self, account=None):
        return [SimpleNamespace(contract=SimpleNamespace(symbol='AAPL'), position=100, avgCost=100)]

    def openTrades(self):
        return []

    def placeOrder(self, contract, order):
        self.calls.append((contract, order))
        order.orderId, order.permId, order.clientId = len(self.calls), 1000 + len(self.calls), 7
        trade = SimpleNamespace(contract=contract, order=order,
                                orderStatus=SimpleNamespace(status=self.status,
                                                            filled=order.totalQuantity if self.filled is None else self.filled,
                                                            avgFillPrice=100 if self.filled != 0 else 0))
        self.trades.append(trade)
        if self.fault:
            raise self.fault
        return trade

    async def reqAllOpenOrdersAsync(self):
        return []

    async def reqCompletedOrdersAsync(self, apiOnly=False):
        return [] if self.snapshot_empty else list(self.trades)


def make_bridge(directory):
    import src.broker_bridge as module
    module.BUDGET_STATE_FILE = Path(directory) / 'budget.json'
    module.IBKR_ORDER_POLL_INTERVAL = 0
    bridge = module.IBKRBridge(account=ACCOUNT, client_id=7)
    bridge.ib = FakeIB()
    bridge.ensure_connected = AsyncMock(return_value=True)
    bridge._loop_owner.bind_current()
    return bridge


@pytest.fixture
async def api(tmp_path, monkeypatch):
    import src.broker_bridge as bridge_module
    import src.broker_selector as selector
    from src.api.routers import system, trading
    from src.api.server import APIServer
    monkeypatch.setattr(bridge_module, 'BUDGET_STATE_FILE', tmp_path / 'budget.json')
    monkeypatch.setattr(bridge_module, 'IBKR_ORDER_POLL_INTERVAL', 0)
    bridge = make_bridge(tmp_path)
    monkeypatch.setenv('OPENCLAW_MANUAL_TRADING_ENABLED', 'true')
    monkeypatch.setenv('OPENCLAW_MANUAL_TRADING_ENVIRONMENT', 'paper')
    store = ManualTradeStore(tmp_path / 'manual' / 'requests.sqlite3')
    monkeypatch.setattr(selector, 'get_ibkr', lambda: bridge)
    notifications, events = [], []
    monkeypatch.setattr(system, 'push_notification', lambda **kwargs: notifications.append(kwargs))
    monkeypatch.setattr(trading, 'push_event', lambda *args: events.append(args))
    app = APIServer(api_token=TOKEN).app
    app.state.manual_trade_store = store
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture',
                                 headers={'x-api-token': TOKEN}) as client:
        yield SimpleNamespace(client=client, app=app, store=store, bridge=bridge,
                              notifications=notifications, events=events)


def order(request_id=None, **changes):
    return {'request_id': request_id or str(uuid4()), 'symbol': 'AAPL', 'quantity': 10,
            'order_type': 'MKT', **changes}


async def prepare(api, payload=None):
    payload = payload or order()
    response = await api.client.post('/api/v1/trading/sell/prepare', json=payload)
    assert response.status_code == 200, response.text
    return payload, response.json()


def confirmation(payload, prepared, **changes):
    return {**payload, 'challenge': prepared['challenge'], 'confirmed': True, 'protocol': PROTOCOL, **changes}


@pytest.mark.asyncio
async def test_legacy_request_cannot_reach_place_order(api):
    response = await api.client.post('/api/v1/trading/sell', json={'symbol': 'AAPL', 'quantity': 10})
    assert api.bridge.ib.calls == []
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_valid_confirmation_and_concurrent_replays_place_once(api):
    payload, prepared = await prepare(api)
    assert api.bridge.ib.calls == []
    assert prepared['summary']['account'] == ACCOUNT
    assert prepared['summary']['environment'] == 'paper'
    assert prepared['summary']['con_id'] == 123
    request = confirmation(payload, prepared)
    responses = await asyncio.gather(*[api.client.post('/api/v1/trading/sell', json=request) for _ in range(12)])
    assert all(response.status_code == 200 for response in responses)
    assert len(api.bridge.ib.calls) == 1
    result = (await api.client.get('/api/v1/trading/sell/requests/' + payload['request_id'])).json()
    assert result['state'] == 'filled' and result['success'] is True
    assert len(api.notifications) == len(api.events) == 1
    assert prepared['challenge'].encode() not in api.store.path.read_bytes()
    assert stat.S_IMODE(api.store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(api.store.path.parent.stat().st_mode) == 0o700
    replay = await api.client.post('/api/v1/trading/sell/prepare', json=payload)
    assert replay.status_code == 200 and 'challenge' not in replay.json()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'confirmed': False}, {'confirmed': 'true'}, {'challenge': 'x' * 40},
                                  {'protocol': 'old-v0'}, {'quantity': 11}, {'symbol': 'MSFT'},
                                  {'order_type': 'LMT', 'limit_price': 99}, {'account': 'U7654321'}])
async def test_confirmation_is_bound_to_exact_request(api, change):
    payload, prepared = await prepare(api)
    response = await api.client.post('/api/v1/trading/sell', json=confirmation(payload, prepared, **change))
    assert response.status_code in {403, 409, 422}
    assert api.bridge.ib.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'quantity': True}, {'quantity': 0}, {'quantity': -1},
                                  {'quantity': 1e20}, {'symbol': ' '}, {'order_type': 'INVALID'},
                                  {'order_type': 'LMT'}, {'limit_price': 10}])
async def test_invalid_prepare_has_no_effect(api, change):
    response = await api.client.post('/api/v1/trading/sell/prepare', json=order(**change))
    assert response.status_code == 422
    assert api.bridge.ib.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['disabled', 'account_empty', 'account_changed', 'managed_missing',
                                 'environment_changed', 'port_only', 'expired', 'token_removed'])
async def test_authority_changes_reject_before_place_order(api, monkeypatch, fault):
    payload, prepared = await prepare(api)
    if fault == 'disabled':
        monkeypatch.setenv('OPENCLAW_MANUAL_TRADING_ENABLED', 'false')
    elif fault == 'account_empty':
        api.bridge.account = ''
    elif fault == 'account_changed':
        api.bridge.account = 'U7654321'
        api.bridge.ib.accounts = ['U7654321']
        monkeypatch.setenv('OPENCLAW_MANUAL_TRADING_ENVIRONMENT', 'live')
    elif fault == 'managed_missing':
        api.bridge.ib.accounts = []
    elif fault == 'environment_changed':
        monkeypatch.setenv('OPENCLAW_MANUAL_TRADING_ENVIRONMENT', 'live')
    elif fault == 'port_only':
        api.bridge.port = 4002
        monkeypatch.delenv('OPENCLAW_MANUAL_TRADING_ENVIRONMENT')
    elif fault == 'expired':
        api.store.clock = lambda: prepared['expires_at'] + 1
    else:
        from src.api.auth import APIAuthContext
        api.app.state.api_auth_context = APIAuthContext.resolve(api_token='')
    response = await api.client.post('/api/v1/trading/sell', json=confirmation(payload, prepared))
    assert response.status_code >= 400 or response.json()['success'] is False
    assert api.bridge.ib.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['disable_at_place', 'change_account_at_place', 'expire_claim',
                                 'store_dispatch_failure', 'revoke_after_dispatch'])
async def test_actual_owner_loop_rechecks_immediately_before_place(api, monkeypatch, fault):
    payload, prepared = await prepare(api)
    original = api.bridge.ib.qualifyContractsAsync
    calls = 0

    async def qualify(contract):
        nonlocal calls
        calls += 1
        values = await original(contract)
        if calls == 2:  # submit context has passed; now inside the real _place_order.
            if fault == 'disable_at_place':
                monkeypatch.setenv('OPENCLAW_MANUAL_TRADING_ENABLED', 'false')
            elif fault == 'change_account_at_place':
                api.bridge.account = 'U7654321'
            elif fault == 'expire_claim':
                api.store.clock = lambda: prepared['expires_at'] + 1
            elif fault == 'store_dispatch_failure':
                def broken(*args):
                    raise ManualTradeError('store_unavailable', 503)
                monkeypatch.setattr(api.store, 'dispatch', broken)
            else:
                dispatch = api.store.dispatch
                def revoke(*args):
                    dispatch(*args)
                    monkeypatch.setenv('OPENCLAW_MANUAL_TRADING_ENABLED', 'false')
                monkeypatch.setattr(api.store, 'dispatch', revoke)
        return values

    monkeypatch.setattr(api.bridge.ib, 'qualifyContractsAsync', qualify)
    response = await api.client.post('/api/v1/trading/sell', json=confirmation(payload, prepared))
    assert response.status_code == 200 and response.json()['success'] is False
    assert api.bridge.ib.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['inside_place', 'after_wait', 'cancelled', 'persist_result'])
async def test_possible_broker_effect_is_never_replayed_or_released(api, monkeypatch, fault):
    payload, prepared = await prepare(api)
    if fault == 'inside_place':
        api.bridge.ib.fault = RuntimeError('after transport send')
    elif fault == 'cancelled':
        api.bridge.ib.fault = asyncio.CancelledError()
    elif fault == 'after_wait':
        import src.trading.manual_trade_service as service
        monkeypatch.setattr(service, 'broker_result', lambda *args: (_ for _ in ()).throw(RuntimeError('after wait')))
    else:
        def broken(*args, **kwargs):
            raise ManualTradeError('store_unavailable', 503)
        monkeypatch.setattr(api.store, 'finish', broken)
    api.bridge.ib.snapshot_empty = True
    request = confirmation(payload, prepared)
    if fault == 'cancelled':
        # Starlette's BaseHTTPMiddleware turns a cancelled downstream response
        # into EndOfStream/No response; durable broker state must still survive.
        with pytest.raises(RuntimeError, match='No response returned'):
            await api.client.post('/api/v1/trading/sell', json=request)
    else:
        response = await api.client.post('/api/v1/trading/sell', json=request)
        assert response.status_code == 503 or response.json()['state'] in {'unknown', 'dispatched'}
    assert len(api.bridge.ib.calls) == 1
    # Simulated application restart uses the same durable database and no memory claim.
    api.app.state.manual_trade_store = ManualTradeStore(api.store.path)
    replay = await api.client.post('/api/v1/trading/sell', json=request)
    assert replay.status_code == 200 and replay.json()['requires_reconciliation']
    new_id = await api.client.post('/api/v1/trading/sell/prepare', json=order())
    assert new_id.status_code == 409
    status = await api.client.get('/api/v1/trading/sell/requests/' + payload['request_id'])
    assert status.json()['requires_reconciliation'] and len(api.bridge.ib.calls) == 1


@pytest.mark.asyncio
async def test_unknown_only_clears_with_same_account_contract_and_order_reference(api):
    payload, prepared = await prepare(api)
    api.bridge.ib.fault = RuntimeError('effect then failure')
    await api.client.post('/api/v1/trading/sell', json=confirmation(payload, prepared))
    trade = api.bridge.ib.trades[0]
    correct = copy.deepcopy(trade)
    for field, value in [('account', 'U7654321'), ('orderRef', 'another-request')]:
        setattr(trade.order, field, value)
        result = (await api.client.get('/api/v1/trading/sell/requests/' + payload['request_id'])).json()
        assert result['state'] == 'unknown'
        setattr(trade.order, field, getattr(correct.order, field))
    trade.contract.conId = 999
    result = (await api.client.get('/api/v1/trading/sell/requests/' + payload['request_id'])).json()
    assert result['state'] == 'unknown'
    trade.contract.conId = correct.contract.conId
    result = (await api.client.get('/api/v1/trading/sell/requests/' + payload['request_id'])).json()
    assert result['state'] == 'filled' and result['reason'] == 'broker_reconciled'
    assert len(api.bridge.ib.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(('status', 'filled', 'expected'), [('Submitted', 0, 'submitted'),
        ('Submitted', 5, 'partially_filled'), ('Filled', 10, 'filled'), ('Inactive', 0, 'rejected'),
        ('Cancelled', 0, 'cancelled'), ('Cancelled', 5, 'cancelled')])
async def test_order_states_remain_distinct(api, status, filled, expected):
    payload, prepared = await prepare(api)
    api.bridge.ib.status, api.bridge.ib.filled = status, filled
    result = (await api.client.post('/api/v1/trading/sell', json=confirmation(payload, prepared))).json()
    assert result['state'] == expected
    assert result['filled_qty'] == filled
    assert result['success'] is (expected in {'submitted', 'partially_filled', 'filled'})
    assert len(api.bridge.ib.calls) == 1


@pytest.mark.asyncio
async def test_notifications_fail_without_resubmission(api, monkeypatch):
    from src.api.routers import system, trading
    def broken(*args, **kwargs):
        raise RuntimeError('notification unavailable')
    monkeypatch.setattr(system, 'push_notification', broken)
    monkeypatch.setattr(trading, 'push_event', broken)
    payload, prepared = await prepare(api)
    request = confirmation(payload, prepared)
    for _ in range(2):
        result = (await api.client.post('/api/v1/trading/sell', json=request)).json()
        assert result['state'] == 'filled'
    assert len(api.bridge.ib.calls) == 1


@pytest.mark.asyncio
async def test_local_development_still_requires_api_token(api):
    from src.api.auth import APIAuthContext
    api.app.state.api_auth_context = APIAuthContext.resolve(host='127.0.0.1', env_mode='development', api_token='')
    result = await api.client.post('/api/v1/trading/sell/prepare', json=order())
    assert result.status_code == 503
    assert api.bridge.ib.calls == []


def _submit_in_process(directory, request_id, payload, challenge, barrier, results):
    async def run():
        os.environ['OPENCLAW_MANUAL_TRADING_ENABLED'] = 'true'
        os.environ['OPENCLAW_MANUAL_TRADING_ENVIRONMENT'] = 'paper'
        bridge = make_bridge(directory)
        store = ManualTradeStore(Path(directory) / 'manual' / 'requests.sqlite3')
        service = ManualTradeService(store, bridge, lambda: None)
        barrier.wait(timeout=15)
        result, _ = await service.submit(request_id, payload, challenge, True, PROTOCOL)
        results.put((len(bridge.ib.calls), result['state']))
    asyncio.run(run())


@pytest.mark.asyncio
async def test_two_processes_use_real_broker_bridge_but_place_once(api, tmp_path):
    payload, prepared = await prepare(api)
    context = multiprocessing.get_context('spawn')
    barrier, results = context.Barrier(2), context.Queue()
    normalized = normalize_order('AAPL', 10)
    children = [context.Process(target=_submit_in_process,
                args=(str(tmp_path), payload['request_id'], normalized, prepared['challenge'], barrier, results)) for _ in range(2)]
    for child in children:
        child.start()
    for child in children:
        await asyncio.to_thread(child.join, 25)
        assert child.exitcode == 0
    values = [results.get(timeout=5) for _ in children]
    assert sum(count for count, _ in values) == 1
    assert api.store.public(api.store.get(payload['request_id']))['state'] == 'filled'


@pytest.mark.asyncio
async def test_two_apps_and_two_event_loops_share_dispatch_authority(api, tmp_path):
    from src.api.server import APIServer
    app2 = APIServer(api_token=TOKEN).app
    app2.state.manual_trade_store = ManualTradeStore(api.store.path)
    payload, prepared = await prepare(api)
    request = confirmation(payload, prepared)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url='http://fixture',
                                 headers={'x-api-token': TOKEN}) as client2:
        responses = await asyncio.gather(api.client.post('/api/v1/trading/sell', json=request),
                                         client2.post('/api/v1/trading/sell', json=request))
    assert all(response.status_code == 200 for response in responses)
    assert len(api.bridge.ib.calls) == 1
    # Different event loops and different bridge instances must also agree.
    second, ready = await prepare(api)

    def submit_in_thread():
        async def run():
            bridge = make_bridge(tmp_path)
            service = ManualTradeService(ManualTradeStore(api.store.path), bridge, lambda: None)
            result, _ = await service.submit(second['request_id'], normalize_order('AAPL', 10),
                                             ready['challenge'], True, PROTOCOL)
            return len(bridge.ib.calls), result['state']
        return asyncio.run(run())

    def compete():
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda _: submit_in_thread(), range(2)))
    results = await asyncio.to_thread(compete)
    assert sum(count for count, _ in results) == 1


@pytest.mark.asyncio
async def test_expired_challenge_retains_tombstone_and_cannot_change_parameters(api):
    payload, prepared = await prepare(api)
    api.store.clock = lambda: prepared['expires_at'] + 1
    response = await api.client.post('/api/v1/trading/sell/prepare', json=payload)
    assert response.json()['state'] == 'expired' and 'challenge' not in response.json()
    changed = await api.client.post('/api/v1/trading/sell/prepare', json={**payload, 'quantity': 11})
    assert changed.status_code == 409
    assert api.bridge.ib.calls == []


@pytest.mark.asyncio
async def test_store_failure_before_claim_cannot_submit(api, monkeypatch):
    payload, prepared = await prepare(api)
    def broken(*args, **kwargs):
        raise ManualTradeError('store_unavailable', 503)
    monkeypatch.setattr(api.store, 'claim', broken)
    response = await api.client.post('/api/v1/trading/sell', json=confirmation(payload, prepared))
    assert response.status_code == 503 and api.bridge.ib.calls == []


@pytest.mark.asyncio
async def test_status_read_failure_keeps_unknown_and_preserves_cancellation(api, monkeypatch):
    payload, prepared = await prepare(api)
    failure = asyncio.CancelledError('synthetic cancel')
    api.bridge.ib.fault = failure
    service = ManualTradeService(api.store, api.bridge, lambda: None)
    with pytest.raises(asyncio.CancelledError):
        await service.submit(payload['request_id'], normalize_order('AAPL', 10), prepared['challenge'], True, PROTOCOL)
    monkeypatch.setattr(api.bridge.ib, 'reqCompletedOrdersAsync', AsyncMock(side_effect=RuntimeError('snapshot failure')))
    result = await service.status(payload['request_id'])
    assert result['state'] == 'unknown' and result['requires_reconciliation']
    assert len(api.bridge.ib.calls) == 1


def test_private_store_rejects_symlink_and_invalid_confirmation_lifetime(tmp_path):
    path = tmp_path / 'actual.sqlite3'
    store = ManualTradeStore(path)
    alias = tmp_path / 'alias.sqlite3'
    alias.symlink_to(path)
    with pytest.raises(ManualTradeError):
        ManualTradeStore(alias)
    for ttl in (0, 121, True):
        with pytest.raises(ManualTradeError, match='expiry'):
            store.prepare(str(uuid4()), {}, ttl=ttl)


@pytest.mark.asyncio
async def test_locked_ib_async_serializes_order_reference_and_account_before_transport(monkeypatch):
    from ib_async import MarketOrder, Stock
    from ib_async.client import Client
    client = Client(SimpleNamespace())
    client.connState = Client.CONNECTED
    client._serverVersion = 190
    frames = []
    monkeypatch.setattr(client.conn, 'sendMsg', frames.append)
    contract = Stock('AAPL', 'SMART', 'USD', conId=123)
    broker_order = MarketOrder('SELL', 10, account=ACCOUNT, orderRef='oe' + uuid4().hex)
    client.placeOrder(7, contract, broker_order)
    assert len(frames) == 1
    fields = frames[0][4:].decode().split('\0')
    assert fields.count(broker_order.orderRef) == 1
    assert fields.count(ACCOUNT) == 1
    assert 'SELL' in fields and '123' in fields
