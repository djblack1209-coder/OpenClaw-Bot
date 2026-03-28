"""
Trading — 内部工具函数
从 trading_system.py 提取的纯工具函数，不依赖全局状态（或通过延迟导入访问）
"""
import logging
import os
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


# ============ 通用工具 ============


def _estimate_open_positions_exposure(portfolio) -> float:
    """估算当前组合已开仓总敞口（用于风控资金基准校准）"""
    if not portfolio:
        return 0.0
    try:
        positions = portfolio.get_positions()
    except Exception as e:
        logger.debug("[TradingSystem] 获取持仓异常: %s", e)
        return 0.0

    exposure = 0.0
    for p in positions or []:
        status = str(p.get("status", "open") or "open")
        if status != "open":
            continue
        qty = abs(float(p.get("quantity", 0) or 0))
        price = float(p.get("avg_price", 0) or p.get("avg_cost", 0) or 0)
        if qty > 0 and price > 0:
            exposure += qty * price
    return exposure


def _is_us_market_open_now() -> bool:
    """判断当前是否处于美股常规交易时段（美东 09:30-16:00）"""
    from src.utils import now_et
    from src.auto_trader import is_market_holiday

    now = now_et()
    if now.weekday() >= 5:
        return False
    if is_market_holiday(now.strftime("%Y-%m-%d")):
        return False

    hour = now.hour
    minute = now.minute
    market_open = (hour > 9) or (hour == 9 and minute >= 30)
    market_close = hour >= 16
    return market_open and not market_close


def _parse_datetime(value: str) -> Optional[datetime]:
    """解析 ISO 日期字符串，确保返回 timezone-aware datetime (美东时间)"""
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            # naive datetime → 假定为美东时间
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("America/New_York"))
        return dt
    except Exception as e:
        logger.debug("[TradingSystem] 日期解析异常: %s", e)
        return None


# ============ 重入队列代理 ============


def _load_pending_reentry_queue() -> List[Dict]:
    """从 trading_journal 加载重入队列 — 委托到 reentry_queue 模块"""
    from src.trading.reentry_queue import load_pending_reentry_queue
    return load_pending_reentry_queue()


def _save_pending_reentry_queue(queue: List[Dict]) -> None:
    """持久化重入队列 — 委托到 reentry_queue 模块"""
    from src.trading.reentry_queue import save_pending_reentry_queue
    save_pending_reentry_queue(queue=queue)


def _queue_reentry_from_trade(trade: Dict, reason: str = "") -> bool:
    """将撤单后的交易加入次日重挂队列 — 委托到 reentry_queue 模块"""
    import src.trading_system as _ts
    from src.trading.reentry_queue import queue_reentry_from_trade
    _ts._pending_reentry_queue, success = queue_reentry_from_trade(
        _ts._pending_reentry_queue, trade, reason
    )
    if success:
        _save_pending_reentry_queue(_ts._pending_reentry_queue)
    return success


# ============ 持仓同步 ============


def _ensure_monitor_position_from_trade(trade: Dict) -> None:
    """确保指定交易存在于持仓监控器中（用于成交回写后补监控）"""
    import src.trading_system as _ts

    if not _ts._position_monitor or not isinstance(trade, dict):
        return

    trade_id = int(float(trade.get("id", 0) or 0))
    if trade_id <= 0:
        return

    qty = float(trade.get("quantity", 0) or 0)
    entry_price = float(trade.get("entry_price", 0) or 0)
    if qty <= 0 or entry_price <= 0:
        return

    existing = _ts._position_monitor.positions.get(trade_id)
    if existing:
        existing.quantity = qty
        existing.entry_price = entry_price
        existing.stop_loss = float(trade.get("stop_loss", 0) or 0)
        existing.take_profit = float(trade.get("take_profit", 0) or 0)
        return

    from src.position_monitor import MonitoredPosition

    entry_dt = _parse_datetime(str(trade.get("entry_time", "") or ""))
    if entry_dt is None:
        from src.utils import now_et
        entry_dt = now_et()

    mon = MonitoredPosition(
        trade_id=trade_id,
        symbol=str(trade.get("symbol", "") or "").upper(),
        side=str(trade.get("side", "BUY") or "BUY"),
        quantity=qty,
        entry_price=entry_price,
        entry_time=entry_dt,
        stop_loss=float(trade.get("stop_loss", 0) or 0),
        take_profit=float(trade.get("take_profit", 0) or 0),
        trailing_stop_pct=0.03,
        atr=0.0,
    )
    _ts._position_monitor.add_position(mon)
