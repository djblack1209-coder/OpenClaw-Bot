"""自选股统一访问层 — 桥接 invest_tools.Portfolio 的 watchlist 功能

搬运模式: 无外部依赖，纯内部桥接
提供统一接口供 daily_brief / proactive_engine / watchlist_monitor 调用

> 最后更新: 2026-03-27
"""
from __future__ import annotations

from typing import Dict, List

from loguru import logger


def get_watchlist_symbols() -> List[str]:
    """获取所有自选股代码列表

    Returns:
        股票代码列表，如 ["AAPL", "TSLA", "NVDA"]
    """
    try:
        from src.invest_tools import Portfolio

        portfolio = Portfolio()
        items = portfolio.get_watchlist()
        return [item["symbol"] for item in items if item.get("symbol")]
    except Exception as e:
        logger.debug(f"获取自选股列表失败: {e}")
        return []


def get_watchlist_with_targets() -> List[Dict]:
    """获取自选股完整信息（含目标价和止损价）

    Returns:
        字典列表，每项包含:
        - symbol: 股票代码
        - added_by: 添加来源
        - reason: 添加理由
        - target_price: 目标价（可为 None）
        - stop_loss: 止损价（可为 None）
    """
    try:
        from src.invest_tools import Portfolio

        portfolio = Portfolio()
        return portfolio.get_watchlist()
    except Exception as e:
        logger.debug(f"获取自选股详情失败: {e}")
        return []


def add_watchlist_symbol(
    symbol: str,
    added_by: str = "system",
    reason: str = "",
    target_price: float = None,
    stop_loss: float = None,
) -> Dict:
    """添加自选股（桥接 Portfolio.add_watchlist）"""
    try:
        from src.invest_tools import Portfolio

        portfolio = Portfolio()
        return portfolio.add_watchlist(
            symbol=symbol,
            added_by=added_by,
            reason=reason,
            target_price=target_price,
            stop_loss=stop_loss,
        )
    except Exception as e:
        logger.debug(f"添加自选股失败: {e}")
        return {"error": str(e)}


def remove_watchlist_symbol(symbol: str) -> Dict:
    """移除自选股（桥接 Portfolio.remove_watchlist）"""
    try:
        from src.invest_tools import Portfolio

        portfolio = Portfolio()
        return portfolio.remove_watchlist(symbol)
    except Exception as e:
        logger.debug(f"移除自选股失败: {e}")
        return {"error": str(e)}
