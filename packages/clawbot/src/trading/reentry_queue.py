"""
Trading — 重入队列管理
管理因盘后取消而需要下一交易日重新提交的交易
"""
import json
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

_PENDING_REENTRY_CONFIG_KEY = "pending_reentry_queue_json"


def load_pending_reentry_queue(journal) -> List[Dict]:
    """从 trading_journal 配置中加载持久化的重入队列"""
    if not journal:
        return []
    try:
        raw = journal.get_config(_PENDING_REENTRY_CONFIG_KEY, "[]")
        items = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(items, list):
            return []
        return items
    except Exception as e:
        logger.warning(f"[ReentryQueue] load failed: {e}")
        return []


def save_pending_reentry_queue(journal, queue: List[Dict]):
    """持久化重入队列到 trading_journal 配置"""
    if not journal:
        return
    try:
        journal.set_config(_PENDING_REENTRY_CONFIG_KEY, json.dumps(queue, default=str))
    except Exception as e:
        logger.warning(f"[ReentryQueue] save failed: {e}")


def queue_reentry_from_trade(
    queue: List[Dict], trade: dict, reason: str = ""
) -> List[Dict]:
    """将取消的交易加入重入队列"""
    symbol = trade.get("symbol", "")
    if not symbol:
        return queue
    entry = {
        "symbol": symbol,
        "side": trade.get("side", "BUY"),
        "quantity": trade.get("quantity", 0),
        "entry_price": trade.get("entry_price", 0),
        "stop_loss": trade.get("stop_loss", 0),
        "take_profit": trade.get("take_profit", 0),
        "reason": reason,
        "original_trade_id": trade.get("id", ""),
    }
    # 去重
    existing_symbols = {item.get("symbol") for item in queue}
    if symbol not in existing_symbols:
        queue.append(entry)
        logger.info(f"[ReentryQueue] queued {symbol}: {reason}")
    return queue
