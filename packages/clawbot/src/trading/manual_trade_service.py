"""Two-stage manual stock sells with broker-loop dispatch authority."""

import asyncio
import json
import math
import os
import re
from decimal import Decimal, InvalidOperation

from src.trading.manual_trade_store import PROTOCOL, ManualTradeError, ManualTradeStore


def _number(value, *, optional=False):
    if optional and value is None:
        return None
    try:
        if type(value) not in {str, int, float, Decimal} or isinstance(value, bool):
            raise ValueError
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0 or number > 10**9 or number.as_tuple().exponent < -8:
            raise ValueError
        return format(number.normalize(), 'f')
    except (ValueError, InvalidOperation):
        raise ManualTradeError('invalid_order_number', 422) from None


def normalize_order(symbol, quantity, order_type='MKT', limit_price=None):
    symbol = symbol.strip().upper() if type(symbol) is str else ''
    kind = order_type.strip().upper() if type(order_type) is str else ''
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.-]{0,9}', symbol) or kind not in {'MKT', 'LMT'}:
        raise ManualTradeError('invalid_order_parameters', 422)
    quantity = _number(quantity)
    price = _number(limit_price, optional=kind == 'MKT')
    if kind == 'MKT' and price is not None:
        raise ManualTradeError('market_order_must_not_have_limit_price', 422)
    return {'symbol': symbol, 'quantity': quantity, 'order_type': kind, 'limit_price': price}


def require_manual_enabled():
    if os.getenv('OPENCLAW_MANUAL_TRADING_ENABLED', '').strip().casefold() != 'true':
        raise ManualTradeError('manual_trading_disabled', 403)


def verified_broker_scope(bridge):
    """Use the authenticated managed account, never port/class/default-account."""
    if bridge.ib is None or not bridge.is_connected():
        raise ManualTradeError('broker_not_connected', 503)
    account = bridge.account
    if type(account) is not str or not re.fullmatch(r'(?:DU|U)\d{5,12}', account):
        raise ManualTradeError('explicit_supported_account_required', 503)
    accounts = bridge.ib.managedAccounts()
    if type(accounts) is not list or account not in accounts:
        raise ManualTradeError('broker_account_not_verified', 503)
    # IBKR documents DU as paper account identifiers. Other account families
    # remain unsupported instead of being guessed from a TWS port number.
    environment = 'paper' if account.startswith('DU') else 'live'
    expected = os.getenv('OPENCLAW_MANUAL_TRADING_ENVIRONMENT', '').strip().casefold()
    if expected not in {'paper', 'live'} or expected != environment:
        raise ManualTradeError('broker_environment_not_verified', 503)
    version = bridge.ib.client.serverVersion()
    if type(version) is not int or version <= 0:
        raise ManualTradeError('broker_protocol_not_verified', 503)
    return {'broker': 'ibkr', 'account': account, 'environment': environment,
            'broker_protocol': 'tws-api', 'server_version': version}


def contract_identity(contract):
    if (getattr(contract, 'secType', None) != 'STK' or type(getattr(contract, 'conId', None)) is not int
            or contract.conId <= 0):
        raise ManualTradeError('verified_stock_contract_required', 503)
    result = {'con_id': contract.conId}
    for key, attr in [('contract_symbol', 'symbol'), ('currency', 'currency'), ('exchange', 'exchange')]:
        value = getattr(contract, attr, None)
        if type(value) is not str or not re.fullmatch(r'[A-Z0-9._ -]{1,32}', value):
            raise ManualTradeError('verified_stock_contract_required', 503)
        result[key] = value
    return result


def broker_result(trade, payload, order_ref):
    """Validate stable order identity and bounded quantities before classification."""
    order = trade.order
    status = trade.orderStatus
    if (order.account != payload['account'] or order.orderRef != order_ref
            or contract_identity(trade.contract) != {key: payload[key] for key in contract_identity(trade.contract)}
            or order.action != 'SELL' or order.orderType != payload['order_type']
            or _number(order.totalQuantity) != payload['quantity']
            or (payload['order_type'] == 'LMT' and _number(order.lmtPrice) != payload['limit_price'])):
        raise ManualTradeError('broker_order_identity_mismatch')
    order_id, perm_id = order.orderId, order.permId
    if type(order_id) is not int or order_id <= 0 or type(perm_id) is not int or perm_id < 0:
        raise ManualTradeError('broker_order_identity_missing')
    filled, price = float(status.filled), float(status.avgFillPrice)
    if (not math.isfinite(filled) or not 0 <= filled <= float(payload['quantity'])
            or not math.isfinite(price) or price < 0):
        raise ManualTradeError('invalid_broker_fill')
    normalized = str(status.status).casefold()
    if normalized == 'filled' and filled == float(payload['quantity']) and price > 0:
        state = 'filled'
    elif normalized in {'cancelled', 'apicancelled'}:
        state = 'cancelled'
    elif normalized == 'inactive' and filled == 0:
        state = 'rejected'
    elif 0 < filled < float(payload['quantity']) and normalized in {'submitted', 'presubmitted', 'filled'}:
        state = 'partially_filled'
    elif filled == 0 and normalized in {'submitted', 'presubmitted', 'pendingsubmit', 'apipending'}:
        state = 'submitted'
    else:
        raise ManualTradeError('inconclusive_broker_status')
    return {'state': state, 'order_id': str(order_id), 'perm_id': perm_id,
            'filled_qty': filled, 'avg_price': price, 'broker_status': status.status}


class ManualTradeService:
    def __init__(self, store: ManualTradeStore, broker, authorize):
        self.store, self.broker, self.authorize = store, broker, authorize

    def _authority(self):
        self.authorize()
        require_manual_enabled()

    async def prepare(self, request_id, order):
        self._authority()
        context = await self.broker.manual_sell_context(order['symbol'])
        self._authority()
        payload = {**order, **context, 'action': 'SELL', 'protocol': PROTOCOL}
        result, challenge = self.store.prepare(request_id, payload)
        if challenge is not None:
            result['challenge'] = challenge
        return result

    async def submit(self, request_id, order, challenge, confirmed, protocol):
        self._authority()
        if protocol != PROTOCOL:
            raise ManualTradeError('confirmation_protocol_mismatch', 422)
        existing = self.store.get(request_id)
        payload = json.loads(existing['payload'])
        if order != {key: payload[key] for key in order}:
            raise ManualTradeError('request_payload_conflict')
        if existing['state'] != 'prepared':
            return self.store.public(existing), False
        context = await self.broker.manual_sell_context(order['symbol'])
        if {**order, **context, 'action': 'SELL', 'protocol': PROTOCOL} != payload:
            raise ManualTradeError('broker_scope_changed')
        row, owner = self.store.claim(request_id, payload, challenge, confirmed)
        if owner is None:
            return self.store.public(row), False

        def check_bound(contract, broker_order):
            self._authority()
            current = {**order, **verified_broker_scope(self.broker), **contract_identity(contract),
                       'action': 'SELL', 'protocol': PROTOCOL}
            if current != payload or broker_order.account != payload['account'] or broker_order.orderRef != row['order_ref']:
                raise ManualTradeError('broker_scope_changed')
            actual_order = normalize_order(order['symbol'], broker_order.totalQuantity, broker_order.orderType,
                                           broker_order.lmtPrice if broker_order.orderType == 'LMT' else None)
            if actual_order != order or broker_order.action != 'SELL':
                raise ManualTradeError('order_parameters_changed')

        def before_submit(contract, broker_order):
            check_bound(contract, broker_order)
            self.store.dispatch(request_id, owner)
            try:
                # SQLite admission can wait for another process. Check again
                # after commit, with no await before the caller's placeOrder.
                check_bound(contract, broker_order)
            except Exception:
                self.store.finish(request_id, owner, 'rejected', reason='authority_lost_before_place')
                raise

        try:
            result = await self.broker.sell(symbol=order['symbol'], quantity=float(order['quantity']),
                                            order_type=order['order_type'], limit_price=float(order['limit_price'] or 0),
                                            decided_by='manual_ui', reason='confirmed_manual_sell',
                                            request_ref=row['order_ref'], before_submit=before_submit,
                                            manual_payload=payload)
            state = self.store.get(request_id)['state']
            if state == 'claimed':
                return self.store.finish(request_id, owner, 'rejected', reason='rejected_before_dispatch'), False
            if state != 'dispatched':
                return self.store.public(self.store.get(request_id)), False
            evidence = result.get('manual_result') if type(result) is dict else None
            if (type(evidence) is not dict or result.get('broker_result_ambiguous')
                    or result.get('broker_result_invalid')):
                return self.store.finish(request_id, owner, 'unknown', reason='broker_outcome_unknown'), True
            return self.store.finish(request_id, owner, evidence['state'], evidence), True
        except BaseException as error:
            current = self.store.get(request_id)
            state = 'rejected' if current['state'] == 'claimed' else 'unknown'
            result = self.store.finish(request_id, owner, state, reason='execution_interrupted')
            if isinstance(error, asyncio.CancelledError) or not isinstance(error, Exception):
                raise
            return result, current['state'] == 'dispatched'

    async def status(self, request_id):
        self.authorize()
        row = self.store.get(request_id)
        if row['state'] in {'dispatched', 'unknown', 'submitted', 'partially_filled'}:
            try:
                result = await self.broker.manual_sell_snapshot(json.loads(row['payload']), row['order_ref'])
                if result is not None:
                    return self.store.reconcile(request_id, result)
            except Exception:
                # An unavailable, empty or conflicting snapshot cannot clear the hold.
                pass
        return self.store.public(row)
