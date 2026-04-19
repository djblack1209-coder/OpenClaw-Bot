"""
交易记忆桥接模块

将交易事件（开仓/平仓/复盘）自动写入 SharedMemory，
使 AI 团队在后续决策中能检索到历史交易经验。

从 trading_journal.py 拆分而来，职责单一化。
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.trading_journal import TradingJournal

logger = logging.getLogger(__name__)


class TradingMemoryBridge:
    """将交易事件自动写入 SharedMemory，沉淀交易经验。

    在关键节点（开仓、平仓、复盘）自动生成记忆条目，
    使 AI 团队在后续决策中能检索到历史交易经验。
    """

    def __init__(self, journal: 'TradingJournal', shared_memory=None):
        self.journal = journal
        self._memory = shared_memory
        self._patched = False

    def attach(self, shared_memory=None):
        """挂载到 journal，拦截关键方法自动写入记忆"""
        if shared_memory:
            self._memory = shared_memory
        if not self._memory:
            logger.warning("[TradingMemoryBridge] 未提供 shared_memory，跳过挂载")
            return
        if self._patched:
            return

        original_open = self.journal.open_trade
        original_close = self.journal.close_trade
        original_review = self.journal.save_review_session
        bridge = self

        def patched_open(*args, **kwargs):
            trade_id = original_open(*args, **kwargs)
            try:
                bridge._on_trade_opened(trade_id, args, kwargs)
            except Exception as e:
                logger.debug("[TradingMemoryBridge] 开仓记忆写入失败: %s", e)
            return trade_id

        def patched_close(*args, **kwargs):
            result = original_close(*args, **kwargs)
            try:
                if "error" not in result:
                    bridge._on_trade_closed(result)
            except Exception as e:
                logger.debug("[TradingMemoryBridge] 平仓记忆写入失败: %s", e)
            return result

        def patched_review(*args, **kwargs):
            result = original_review(*args, **kwargs)
            try:
                bridge._on_review_saved(args, kwargs)
            except Exception as e:
                logger.debug("[TradingMemoryBridge] 复盘记忆写入失败: %s", e)
            return result

        self.journal.open_trade = patched_open
        self.journal.close_trade = patched_close
        self.journal.save_review_session = patched_review
        self._patched = True
        logger.info("[TradingMemoryBridge] 已挂载，交易事件将自动写入共享记忆")

    def _on_trade_opened(self, trade_id, args, kwargs):
        """开仓时写入记忆"""
        symbol = args[0] if args else kwargs.get('symbol', '?')
        side = args[1] if len(args) > 1 else kwargs.get('side', '?')
        entry_price = args[3] if len(args) > 3 else kwargs.get('entry_price', 0)
        reason = kwargs.get('entry_reason', '') or (args[9] if len(args) > 9 else '')
        decided_by = kwargs.get('decided_by', '') or (args[10] if len(args) > 10 else '')

        key = f"trade_open_{trade_id}_{symbol}"
        value = (
            f"开仓 #{trade_id}: {side} {symbol} @ ${entry_price}"
            f"{f' | 理由: {reason}' if reason else ''}"
            f"{f' | 决策: {decided_by}' if decided_by else ''}"
        )
        self._memory.remember(
            key=key, value=value,
            category="trading", source_bot="trading_journal",
            importance=3, ttl_hours=24 * 30,
        )

    def _on_trade_closed(self, result):
        """平仓时写入记忆（含亏损教训）"""
        trade_id = result.get("trade_id", 0)
        symbol = result.get("symbol", "?")
        pnl = result.get("pnl", 0)
        pnl_pct = result.get("pnl_pct", 0)
        hold_hours = result.get("hold_hours", 0)

        outcome = "盈利" if pnl >= 0 else "亏损"
        importance = 4 if abs(pnl) > 50 else 3

        key = f"trade_close_{trade_id}_{symbol}"
        value = (
            f"平仓 #{trade_id}: {symbol} PnL=${pnl:+.2f} ({pnl_pct:+.1f}%) "
            f"持仓{hold_hours:.1f}h | {outcome}"
        )
        self._memory.remember(
            key=key, value=value,
            category="trading", source_bot="trading_journal",
            importance=importance, ttl_hours=24 * 90,
            related_keys=[f"trade_open_{trade_id}_{symbol}"],
        )

        # 亏损交易额外写入教训记忆
        if pnl < 0 and abs(pnl) > 20:
            lesson_key = f"trade_lesson_{trade_id}"
            lesson = (
                f"亏损教训 #{trade_id}: {symbol} 亏${abs(pnl):.2f} "
                f"({pnl_pct:.1f}%) 持仓{hold_hours:.1f}h"
            )
            self._memory.remember(
                key=lesson_key, value=lesson,
                category="trading", source_bot="trading_journal",
                importance=5, ttl_hours=24 * 180,
                related_keys=[key],
            )

    def _on_review_saved(self, args, kwargs):
        """复盘会议保存时写入记忆"""
        date = args[0] if args else kwargs.get('date', '')
        session_type = args[1] if len(args) > 1 else kwargs.get('session_type', 'daily')
        lessons = kwargs.get('lessons_learned', '')
        improvements = kwargs.get('improvements', '')

        if not lessons and not improvements:
            return

        key = f"review_{session_type}_{date}"
        parts = []
        if lessons:
            parts.append(f"教训: {lessons[:500]}")
        if improvements:
            parts.append(f"改进: {improvements[:500]}")
        value = f"{session_type}复盘 {date} | {' | '.join(parts)}"

        self._memory.remember(
            key=key, value=value,
            category="trading", source_bot="trading_journal",
            importance=4, ttl_hours=24 * 180,
        )


# 从 trading_journal 导入全局 journal 实例，创建桥接实例
from src.trading_journal import journal  # noqa: E402
trading_memory_bridge = TradingMemoryBridge(journal)
