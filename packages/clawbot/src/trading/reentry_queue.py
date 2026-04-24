"""
Trading — 重入队列管理 v2.0
管理因盘后取消/异常而需要下一交易日重新提交的交易。

持久化到 TradingJournal 的 config 存储。
每条记录包含完整的交易参数（symbol/quantity/stop_loss/take_profit 等）。

> 最后更新: 2026-03-26
"""
import json
import logging

logger = logging.getLogger(__name__)

_PENDING_REENTRY_CONFIG_KEY = "pending_reentry_queue_json"


def _normalize_item(item: dict) -> dict | None:
    """规范化单条 reentry 记录，验证必要字段。"""
    if not isinstance(item, dict):
        return None
    symbol = str(item.get("symbol", "") or "").upper().strip()
    qty = int(float(item.get("quantity", 0) or 0))
    if not symbol or qty <= 0:
        return None
    return {
        "symbol": symbol,
        "quantity": qty,
        "stop_loss": float(item.get("stop_loss", 0) or 0),
        "take_profit": float(item.get("take_profit", 0) or 0),
        "signal_score": int(float(item.get("signal_score", 0) or 0)),
        "entry_reason": str(item.get("entry_reason", "") or ""),
        "decided_by": str(item.get("decided_by", "") or "AutoTrader"),
        "source_trade_id": int(float(item.get("source_trade_id", 0) or 0)),
        "retry_count": int(float(item.get("retry_count", 0) or 0)),
        "queued_at": str(item.get("queued_at", "") or ""),
        "next_retry_at": str(item.get("next_retry_at", "") or ""),
    }


def load_pending_reentry_queue(journal=None) -> list[dict]:
    """从 trading_journal 配置中加载并规范化重入队列。

    Args:
        journal: TradingJournal 实例。为 None 时延迟导入全局实例。
    """
    if journal is None:
        try:
            from src.trading_journal import journal as tj
            journal = tj
        except ImportError:
            return []

    try:
        raw = journal.get_config(_PENDING_REENTRY_CONFIG_KEY, "[]")
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(payload, list):
            return []
    except Exception as e:
        logger.warning("[ReentryQueue] 解析失败: %s", e)
        return []

    normalized = []
    for item in payload:
        n = _normalize_item(item)
        if n:
            normalized.append(n)
    return normalized


def save_pending_reentry_queue(journal=None, queue: list[dict] = None) -> None:
    """持久化重入队列到 trading_journal 配置。"""
    if queue is None:
        queue = []
    if journal is None:
        try:
            from src.trading_journal import journal as tj
            journal = tj
        except ImportError:
            return

    safe_queue = []
    for item in queue:
        n = _normalize_item(item)
        if n:
            safe_queue.append(n)
    journal.set_config(_PENDING_REENTRY_CONFIG_KEY, json.dumps(safe_queue, ensure_ascii=False))


def queue_reentry_from_trade(
    queue: list[dict], trade: dict, reason: str = ""
) -> tuple[list[dict], bool]:
    """将取消的交易加入重入队列。

    Args:
        queue: 当前队列
        trade: 交易记录 dict
        reason: 重入原因

    Returns:
        (更新后的队列, 是否成功入队)
    """
    symbol = str(trade.get("symbol", "") or "").upper().strip()
    quantity = int(float(trade.get("quantity", 0) or 0))
    source_trade_id = int(float(trade.get("id", 0) or 0))
    if not symbol or quantity <= 0:
        return queue, False

    # 去重: 同一 source_trade_id 不重复入队
    for item in queue:
        if int(item.get("source_trade_id", 0) or 0) == source_trade_id:
            return queue, False

    from src.utils import now_et
    now = now_et().isoformat()
    entry_reason = str(trade.get("entry_reason", "") or "")
    if reason:
        entry_reason = f"{entry_reason} | 重挂原因: {reason}".strip(" |")

    queue.append({
        "symbol": symbol,
        "quantity": quantity,
        "stop_loss": float(trade.get("stop_loss", 0) or 0),
        "take_profit": float(trade.get("take_profit", 0) or 0),
        "signal_score": int(float(trade.get("signal_score", 0) or 0)),
        "entry_reason": entry_reason,
        "decided_by": str(trade.get("decided_by", "") or "AutoTrader"),
        "source_trade_id": source_trade_id,
        "retry_count": 0,
        "queued_at": now,
        "next_retry_at": now,
    })
    logger.info(f"[ReentryQueue] 入队 {symbol} qty={quantity}: {reason}")
    return queue, True
