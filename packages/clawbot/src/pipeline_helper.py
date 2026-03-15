"""
Helper to execute trades through the TradingPipeline from callback handlers.
Bridges the gap between the old dict-based trade format and the new TradeProposal system.
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 默认止损止盈百分比（当AI未提供且无ATR数据时使用）
DEFAULT_SL_PCT = 0.03   # 3%
DEFAULT_TP_PCT = 0.06   # 6%
MIN_RR_RATIO = 2.0      # 最低风险收益比


async def _get_atr_based_levels(symbol: str, entry_price: float) -> dict:
    """尝试用ATR计算更精确的止损止盈"""
    try:
        from src.ta_engine import get_full_analysis
        data = await get_full_analysis(symbol)
        if isinstance(data, dict) and "error" not in data:
            atr_pct = data.get("atr_pct", 0)
            if atr_pct and atr_pct > 0:
                atr_mult = atr_pct / 100
                sl = round(entry_price * (1 - atr_mult * 1.5), 2)
                tp = round(entry_price * (1 + atr_mult * 3.0), 2)
                logger.info("[PipelineHelper] %s ATR止损: SL=$%.2f TP=$%.2f (ATR=%.1f%%)",
                            symbol, sl, tp, atr_pct)
                return {"stop_loss": sl, "take_profit": tp, "source": "ATR"}
    except Exception as e:
        logger.debug("[PipelineHelper] ATR获取失败(%s): %s", symbol, e)
    return {}


async def execute_trade_via_pipeline(trade_dict: dict, pipeline=None, get_quote_func=None) -> str:
    """
    Execute a single trade dict through the TradingPipeline.

    Args:
        trade_dict: {"action": "BUY", "symbol": "AAPL", "qty": 5, "reason": "...",
                     "entry_price": 0, "stop_loss": 0, "take_profit": 0, "signal_score": 0}
        pipeline: TradingPipeline instance (from get_trading_pipeline())
        get_quote_func: async function to get stock quote

    Returns:
        A result string describing what happened
    """
    symbol = trade_dict.get("symbol", "")
    action = trade_dict.get("action", "HOLD")
    qty = trade_dict.get("qty", 0)

    if not pipeline:
        return "X %s %s: TradingPipeline not initialized" % (action, symbol)

    from src.models import TradeProposal

    entry_price = float(trade_dict.get("entry_price", 0) or 0)
    stop_loss = float(trade_dict.get("stop_loss", 0) or 0)
    take_profit = float(trade_dict.get("take_profit", 0) or 0)
    signal_score = int(trade_dict.get("signal_score", 0) or 0)

    # Auto-fill entry price from live quote
    if entry_price <= 0 and get_quote_func:
        try:
            q = await get_quote_func(symbol)
            if isinstance(q, dict) and "price" in q:
                entry_price = q["price"]
                logger.info("[PipelineHelper] %s 自动获取入场价: $%.2f", symbol, entry_price)
        except Exception as e:
            logger.warning("[PipelineHelper] %s 自动获取入场价失败: %s", symbol, e)

    # Auto-fill stop-loss and take-profit for BUY orders
    if action == "BUY" and entry_price > 0:
        if stop_loss <= 0 or take_profit <= 0:
            # 优先尝试ATR计算
            atr_levels = await _get_atr_based_levels(symbol, entry_price)
            if atr_levels:
                if stop_loss <= 0:
                    stop_loss = atr_levels["stop_loss"]
                if take_profit <= 0:
                    take_profit = atr_levels["take_profit"]
            else:
                # 回退到默认百分比
                if stop_loss <= 0:
                    stop_loss = round(entry_price * (1 - DEFAULT_SL_PCT), 2)
                if take_profit <= 0:
                    take_profit = round(entry_price * (1 + DEFAULT_TP_PCT), 2)
                logger.info("[PipelineHelper] %s 使用默认止损: SL=$%.2f TP=$%.2f",
                            symbol, stop_loss, take_profit)

        # 验证风险收益比
        risk = entry_price - stop_loss
        reward = take_profit - entry_price
        if risk > 0 and reward / risk < MIN_RR_RATIO:
            take_profit = round(entry_price + risk * MIN_RR_RATIO, 2)
            logger.info("[PipelineHelper] %s 调整止盈以满足RR>=%.1f: TP=$%.2f",
                        symbol, MIN_RR_RATIO, take_profit)

    proposal = TradeProposal(
        symbol=symbol,
        action=action,
        quantity=int(qty),
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        signal_score=signal_score,
        reason=trade_dict.get("reason", ""),
        decided_by="AI invest team",
    )

    logger.info("[PipelineHelper] %s %s x%d @ $%.2f SL=$%.2f TP=$%.2f -> pipeline",
                action, symbol, int(qty), entry_price, stop_loss, take_profit)

    r = await pipeline.execute_proposal(proposal)
    status = r.get("status", "unknown")

    if status == "executed":
        tid = r.get("trade_id", "?")
        eq = r.get("quantity", qty)
        return "[OK] %s %s x%s @ $%.2f (SL=$%.2f TP=$%.2f) trade#%s" % (
            action, symbol, eq, entry_price, stop_loss, take_profit, tid)
    elif status == "rejected":
        reason = r.get("reason", "")
        return "[RISK REJECTED] %s %s: %s" % (action, symbol, reason)
    elif status == "skipped":
        reason = r.get("reason", "skipped")
        return "[SKIP] %s: %s" % (symbol, reason)
    else:
        reason = r.get("reason", status)
        return "[ERROR] %s %s: %s" % (action, symbol, reason)
