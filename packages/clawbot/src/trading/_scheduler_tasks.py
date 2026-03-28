"""
Trading — 定时调度任务（重型）
IBKR 成交回写、待成交撤单、重入队列提交
"""
import asyncio
import logging
from collections import OrderedDict
from datetime import timedelta
from typing import Dict, List

from src.notify_style import (
    format_notice,
    format_pending_reentry,
    format_trade_fill_reconciled,
    kv,
)
from src.utils import env_bool, env_int
from src.trading._helpers import (
    _is_us_market_open_now,
    _parse_datetime,
    _queue_reentry_from_trade,
    _ensure_monitor_position_from_trade,
)

logger = logging.getLogger(__name__)


# ============ IBKR 成交回写 ============


async def _reconcile_ibkr_entry_fills():
    """定期将 IBKR 成交回报回写到 trading_journal"""
    import src.trading_system as _ts

    if not env_bool("IBKR_FILL_RECONCILE_ENABLED", True):
        return
    if not _ts._trading_pipeline or not _ts._trading_pipeline.broker:
        return

    broker = _ts._trading_pipeline.broker
    if not hasattr(broker, "get_recent_fills"):
        return

    from src.trading_journal import journal as tj
    pending = tj.get_pending_trades(
        limit=env_int("IBKR_PENDING_RECONCILE_LIMIT", 300, minimum=50)
    )
    open_with_order = [
        t for t in tj.get_open_trades()
        if str(t.get("entry_order_id", "") or "").strip()
    ]

    if not pending and not open_with_order:
        return

    fills = await broker.get_recent_fills(
        lookback_hours=env_int("IBKR_FILL_LOOKBACK_HOURS", 48, minimum=1)
    )
    fills = fills or []

    aggregated: Dict = {}
    new_exec = 0
    for fill in fills:
        exec_id = str(fill.get("exec_id", "") or "")
        if not exec_id or exec_id in _ts._processed_fill_exec_ids:
            continue

        _ts._processed_fill_exec_ids[exec_id] = True
        new_exec += 1

        order_id = str(fill.get("order_id", "") or "").strip()
        shares = float(fill.get("shares", 0) or 0)
        price = float(fill.get("price", 0) or 0)
        if not order_id or shares <= 0 or price <= 0:
            continue

        item = aggregated.setdefault(order_id, {
            "shares": 0.0,
            "notional": 0.0,
            "symbol": str(fill.get("symbol", "") or "").upper(),
            "latest_time": str(fill.get("time", "") or ""),
        })
        item["shares"] += shares
        item["notional"] += shares * price
        if fill.get("time"):
            item["latest_time"] = str(fill.get("time"))

    # 截断缓存，保留最近 4000 条
    if len(_ts._processed_fill_exec_ids) > 8000:
        keys = list(_ts._processed_fill_exec_ids.keys())
        _ts._processed_fill_exec_ids = OrderedDict.fromkeys(keys[-4000:], True)

    pending_by_order: Dict = {}
    for trade in pending:
        oid = str(trade.get("entry_order_id", "") or "").strip()
        if oid:
            pending_by_order[oid] = trade

    for order_id, fill_info in aggregated.items():
        trade = pending_by_order.get(order_id)
        if not trade:
            continue

        shares = float(fill_info.get("shares", 0) or 0)
        notional = float(fill_info.get("notional", 0) or 0)
        avg_price = notional / shares if shares > 0 else 0
        if shares <= 0 or avg_price <= 0:
            continue

        trade_id = int(float(trade.get("id", 0) or 0))
        update = tj.mark_trade_entry_filled(
            trade_id=trade_id,
            filled_qty=shares,
            fill_price=avg_price,
            entry_order_id=order_id,
            fill_time=str(fill_info.get("latest_time", "") or ""),
        )
        if "error" in update:
            logger.warning("[Reconcile] 回写失败 trade#%s: %s", trade_id, update["error"])
            continue

        refreshed = tj.get_trade(trade_id)
        if refreshed:
            _ensure_monitor_position_from_trade(refreshed)

        logger.info(
            "[Reconcile] 成交回写成功 trade#%d order#%s qty=%.4f @ %.4f",
            trade_id,
            order_id,
            shares,
            avg_price,
        )

        if _ts._auto_trader and _ts._auto_trader.notify:
            try:
                await _ts._auto_trader._safe_notify(
                    format_trade_fill_reconciled(
                        trade_id,
                        order_id,
                        str(trade.get("symbol", "?") or "?").upper(),
                        shares,
                        avg_price,
                    )
                )
            except Exception as e:
                logger.debug("[Reconcile] 成交通知失败: %s", e)

    # 兼容旧逻辑：open + entry_order_id 但无持仓/无挂单时，自动修正状态
    if open_with_order:
        open_orders = await broker.get_open_orders() if hasattr(broker, "get_open_orders") else []
        open_order_ids = {
            str(o.get("order_id", "") or "")
            for o in open_orders
            if o.get("order_id") is not None
        }
        snapshots = await broker.get_trade_snapshots() if hasattr(broker, "get_trade_snapshots") else []
        snapshot_map = {
            str(o.get("order_id", "") or ""): o
            for o in snapshots
            if o.get("order_id") is not None
        }
        positions = await broker.get_positions() if hasattr(broker, "get_positions") else []
        pos_symbols = {
            str(p.get("symbol", "") or "").upper(): abs(float(p.get("quantity", 0) or 0))
            for p in positions
        }
        grace_minutes = env_int("IBKR_LEGACY_ORDER_RECONCILE_GRACE_MIN", 30, minimum=5)

        for trade in open_with_order:
            trade_id = int(float(trade.get("id", 0) or 0))
            order_id = str(trade.get("entry_order_id", "") or "").strip()
            symbol = str(trade.get("symbol", "") or "").upper().strip()
            if trade_id <= 0 or not order_id or not symbol:
                continue

            # 如果有真实持仓，视为已成交，无需处理
            if pos_symbols.get(symbol, 0) > 0:
                continue

            entry_dt = _parse_datetime(str(trade.get("entry_time", "") or ""))
            age_min = 0
            if entry_dt is not None:
                from src.utils import now_et
                age_min = int(max(0, (now_et().replace(tzinfo=None) - entry_dt.replace(tzinfo=None)).total_seconds() / 60))

            if order_id in open_order_ids:
                # 旧记录修正为 pending，避免被误当成已持仓
                if age_min >= grace_minutes:
                    tj.set_trade_status(trade_id, "pending", reason="legacy_open_order_pending")
                    if _ts._position_monitor:
                        _ts._position_monitor.remove_position(trade_id)
                    logger.info("[Reconcile] trade#%d 状态修正为 pending (order#%s)", trade_id, order_id)
                continue

            snap_status = str(snapshot_map.get(order_id, {}).get("status", "") or "")
            # 既无持仓也无挂单，且过了宽限期 -> 取消旧记录
            if age_min >= grace_minutes and snap_status in ("", "Cancelled", "ApiCancelled", "Inactive"):
                tj.cancel_trade(trade_id, reason="reconcile_no_fill_no_position")
                if _ts._position_monitor:
                    _ts._position_monitor.remove_position(trade_id)
                logger.info(
                    "[Reconcile] trade#%d 无成交且无持仓，已取消 (order#%s)",
                    trade_id,
                    order_id,
                )

    if new_exec > 0:
        logger.info("[Reconcile] 本轮处理新成交回报: %d 条", new_exec)


# ============ 待成交订单撤单 ============


async def _cancel_stale_pending_entries():
    """自动撤销超时的待成交入场订单"""
    import src.trading_system as _ts

    if not env_bool("AUTO_CANCEL_PENDING_ENTRY_ORDERS", True):
        return
    if not _ts._trading_pipeline or not _ts._trading_pipeline.broker:
        return

    broker = _ts._trading_pipeline.broker
    if not hasattr(broker, "get_open_orders"):
        return

    from src.trading_journal import journal as tj
    pending = tj.get_pending_trades(
        limit=env_int("PENDING_ENTRY_SCAN_LIMIT", 300, minimum=50)
    )
    if not pending:
        return

    market_open = _is_us_market_open_now()
    stale_minutes = env_int("PENDING_ENTRY_CANCEL_AFTER_MINUTES", 20, minimum=1)
    deep_timeout = max(stale_minutes * 3, 60)

    open_orders = await broker.get_open_orders()
    open_map = {
        str(o.get("order_id", "") or ""): o
        for o in open_orders
        if o.get("order_id") is not None
    }

    snapshots: List = []
    if hasattr(broker, "get_trade_snapshots"):
        snapshots = await broker.get_trade_snapshots()
    snapshot_map = {
        str(o.get("order_id", "") or ""): o
        for o in snapshots
        if o.get("order_id") is not None
    }

    cancelled_statuses = {"Cancelled", "ApiCancelled", "Inactive"}
    from src.utils import now_et
    now = now_et()

    for trade in pending:
        trade_id = int(float(trade.get("id", 0) or 0))
        order_id = str(trade.get("entry_order_id", "") or "").strip()
        if trade_id <= 0 or not order_id:
            continue

        entry_dt = _parse_datetime(str(trade.get("entry_time", "") or ""))
        age_min = 9999
        if entry_dt is not None:
            age_min = max(0, int((now.replace(tzinfo=None) - entry_dt.replace(tzinfo=None)).total_seconds() / 60))

        live_order = open_map.get(order_id)
        snap = snapshot_map.get(order_id, {})
        status = str((live_order or snap).get("status", "") or "")

        need_cancel_api = False
        cancel_reason = ""

        if live_order and (not market_open) and age_min >= stale_minutes:
            need_cancel_api = True
            cancel_reason = f"offhours_pending_timeout_{age_min}m"
        elif (not live_order) and status in cancelled_statuses:
            cancel_reason = f"broker_{status.lower()}"
        elif (not live_order) and (not status) and age_min >= deep_timeout:
            cancel_reason = f"pending_timeout_{age_min}m"

        if need_cancel_api:
            try:
                cancel_ret = await broker.cancel_order(int(float(order_id)))
            except Exception as e:
                logger.warning("[PendingCancel] 订单#%s 撤单异常: %s", order_id, e)
                continue
            if "error" in cancel_ret:
                logger.warning("[PendingCancel] 订单#%s 撤单失败: %s", order_id, cancel_ret["error"])
                continue

        if not cancel_reason:
            continue

        tj.cancel_trade(trade_id, cancel_reason)
        queued = False
        if env_bool("AUTO_RESUBMIT_PENDING_NEXT_SESSION", True):
            queued = _queue_reentry_from_trade(trade, reason=cancel_reason)

        if _ts._position_monitor:
            _ts._position_monitor.remove_position(trade_id)

        logger.info(
            "[PendingCancel] trade#%d order#%s 已取消，原因=%s，重挂=%s",
            trade_id,
            order_id,
            cancel_reason,
            queued,
        )

        if _ts._auto_trader and _ts._auto_trader.notify:
            try:
                await _ts._auto_trader._safe_notify(
                    format_notice(
                        "待成交订单已撤单",
                        bullets=[
                            kv("Trade / Order", f"#{trade_id} / #{order_id}"),
                            kv("原因", cancel_reason),
                            kv("次日重挂", "已加入" if queued else "未加入"),
                        ],
                    )
                )
            except Exception as e:
                logger.debug("[PendingCancel] 通知失败: %s", e)


# ============ 重入队列提交 ============


async def _submit_pending_reentry_queue():
    """在开盘时段提交重入队列中的订单"""
    import src.trading_system as _ts
    from src.trading._helpers import _save_pending_reentry_queue

    if not env_bool("AUTO_RESUBMIT_PENDING_NEXT_SESSION", True):
        return
    if not _ts._pending_reentry_queue:
        return
    if not _is_us_market_open_now():
        return
    if not _ts._trading_pipeline:
        return

    max_per_cycle = env_int("PENDING_REENTRY_MAX_PER_CYCLE", 1, minimum=1)
    max_retries = env_int("PENDING_REENTRY_MAX_RETRIES", 2, minimum=1)
    retry_interval_min = env_int("PENDING_REENTRY_RETRY_INTERVAL_MIN", 5, minimum=1)

    from src.models import TradeProposal
    from src.utils import now_et
    from src.invest_tools import get_stock_quote

    now_dt = now_et()
    submitted_count = 0
    next_queue: List[Dict] = []

    for item in list(_ts._pending_reentry_queue):
        if submitted_count >= max_per_cycle:
            next_queue.append(item)
            continue

        next_retry_at = _parse_datetime(str(item.get("next_retry_at", "") or ""))
        if next_retry_at and now_dt < next_retry_at:
            next_queue.append(item)
            continue

        symbol = str(item.get("symbol", "") or "").upper().strip()
        qty = int(float(item.get("quantity", 0) or 0))
        if not symbol or qty <= 0:
            continue

        try:
            quote_ret = get_stock_quote(symbol)
            if asyncio.iscoroutine(quote_ret):
                price_data = await quote_ret
            else:
                price_data = quote_ret
        except Exception as e:
            logger.warning("[ReEntry] %s 获取行情失败: %s", symbol, e)
            price_data = {}

        price = float(price_data.get("price", 0) or 0) if isinstance(price_data, dict) else 0
        if price <= 0:
            retry_count = int(float(item.get("retry_count", 0) or 0)) + 1
            if retry_count <= max_retries:
                item["retry_count"] = retry_count
                item["next_retry_at"] = (now_dt + timedelta(minutes=retry_interval_min)).isoformat()
                next_queue.append(item)
            continue

        stop = float(item.get("stop_loss", 0) or 0)
        if stop <= 0 or stop >= price:
            stop = round(price * 0.97, 2)
        target = float(item.get("take_profit", 0) or 0)
        if target <= 0 or target <= price:
            target = round(price * 1.06, 2)

        proposal = TradeProposal(
            symbol=symbol,
            action="BUY",
            quantity=qty,
            entry_price=price,
            stop_loss=stop,
            take_profit=target,
            signal_score=int(float(item.get("signal_score", 0) or 0)),
            confidence=0.55,
            reason=str(item.get("entry_reason", "") or "")[:180] or "次日重挂执行",
            decided_by=f"ReEntry/{str(item.get('decided_by', 'AutoTrader') or 'AutoTrader')}",
        )

        try:
            exec_result = await _ts._trading_pipeline.execute_proposal(proposal)
        except Exception as e:
            logger.warning("[ReEntry] %s 执行异常: %s", symbol, e)
            exec_result = {"status": "error", "reason": str(e)}

        status = str(exec_result.get("status", "") or "")
        if status in ("executed", "submitted"):
            submitted_count += 1
            if _ts._auto_trader and _ts._auto_trader.notify:
                try:
                    await _ts._auto_trader._safe_notify(
                        format_pending_reentry(symbol, qty, price, status)
                    )
                except Exception as e:
                    logger.debug("[TradingSystem] 异常: %s", e)
            continue

        retry_count = int(float(item.get("retry_count", 0) or 0)) + 1
        if retry_count <= max_retries:
            item["retry_count"] = retry_count
            item["next_retry_at"] = (now_dt + timedelta(minutes=retry_interval_min)).isoformat()
            next_queue.append(item)
        else:
            logger.warning("[ReEntry] %s 重挂失败超限，放弃: %s", symbol, exec_result)

    _ts._pending_reentry_queue = next_queue
    _save_pending_reentry_queue(_ts._pending_reentry_queue)

