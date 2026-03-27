"""
Trading — 仓位同步工具
估算敞口、同步仓位到 PositionMonitor
"""
import logging

logger = logging.getLogger(__name__)


def estimate_open_positions_exposure(portfolio) -> float:
    """估算当前组合已开仓总敞口"""
    if not portfolio:
        return 0.0
    try:
        positions = portfolio.get_positions()
    except Exception:
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


def ensure_monitor_position_from_trade(monitor, trade: dict):
    """将交易记录同步到 PositionMonitor"""
    if not monitor or not trade:
        return
    symbol = trade.get("symbol", "")
    if not symbol:
        return
    try:
        qty = float(trade.get("quantity", 0) or 0)
        entry = float(trade.get("entry_price", 0) or 0)
        sl = float(trade.get("stop_loss", 0) or 0)
        tp = float(trade.get("take_profit", 0) or 0)
        if qty > 0 and entry > 0:
            monitor.upsert_position(
                symbol=symbol,
                quantity=qty,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                trade_id=trade.get("id"),
            )
    except Exception as e:
        logger.warning(f"[PositionSync] {symbol} 同步失败: {e}")
