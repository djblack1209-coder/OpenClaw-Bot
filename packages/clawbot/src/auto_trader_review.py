"""
AutoTrader 收盘复盘 Mixin
从 auto_trader.py 拆分，负责每日收盘复盘、教训持久化
"""
import logging

from src.trading_pipeline import TraderState

logger = logging.getLogger(__name__)


class AutoTraderReviewMixin:
    """收盘复盘能力，由 AutoTrader 通过 Mixin 继承"""

    async def _run_review(self) -> None:
        """收盘自动复盘 — 生成当日交易总结、持久化教训、通知"""
        self.state = TraderState.REVIEWING
        logger.info("[AutoTrader] 开始收盘复盘")
        try:
            from src.trading_journal import journal as tj
            today_pnl = tj.get_today_pnl()
            open_trades = tj.get_open_trades()
            closed = tj.get_closed_trades(days=1, limit=20)

            lines = ["-- AutoTrader 收盘复盘 --\n"]
            lines.append("今日盈亏: $%.2f (%d笔交易)" % (
                today_pnl.get("pnl", 0), today_pnl.get("trades", 0)))
            lines.append("扫描循环: %d次" % self._cycle_count)

            wins = 0
            losses = 0
            if closed:
                wins = sum(1 for t in closed if t.get("pnl", 0) >= 0)
                losses = len(closed) - wins
                lines.append("\n已平仓: %d笔 (盈%d 亏%d)" % (len(closed), wins, losses))
                for t in closed:
                    sign = "+" if t.get("pnl", 0) >= 0 else ""
                    lines.append("  %s %s %s$%.2f" % (
                        t.get("side", "?"), t.get("symbol", "?"),
                        sign, t.get("pnl", 0)))

            if open_trades:
                lines.append("\n持仓中: %d笔" % len(open_trades))
                for t in open_trades:
                    lines.append("  %s x%s @ $%s 止损$%s" % (
                        t.get("symbol", "?"), t.get("quantity", "?"),
                        t.get("entry_price", "?"), t.get("stop_loss", "无")))

            # 闭环学习：持久化复盘教训到 trading_journal
            lessons = ""
            try:
                trade_count = today_pnl.get("trades", 0)
                win_rate = round(wins / max(trade_count, 1) * 100, 1)

                # 生成迭代报告提取失败模式
                iteration = {}
                if hasattr(tj, 'generate_iteration_report'):
                    iteration = tj.generate_iteration_report(days=7)
                suggestions = iteration.get("improvement_suggestions", []) if isinstance(iteration, dict) else []
                lessons = "; ".join(str(s) for s in suggestions[:3])

                if hasattr(tj, 'save_review_session'):
                    from src.utils import today_et_str
                    tj.save_review_session(
                        date=today_et_str(),
                        session_type='daily',
                        trades_reviewed=trade_count,
                        total_pnl=today_pnl.get("pnl", 0),
                        win_rate=win_rate,
                        lessons_learned=lessons,
                        improvements="",
                    )
                    logger.info("[AutoTrader] 复盘教训已持久化")

                if lessons:
                    lines.append("\n📝 教训: " + lessons)
            except Exception as e:
                logger.warning("[AutoTrader] 复盘持久化失败(非致命): %s", e)

            lines.append("\n明日将自动继续交易。")

            await self._safe_notify("\n".join(lines))
        except Exception as e:
            logger.error("[AutoTrader] 复盘失败: %s", e)
            await self._safe_notify("收盘复盘生成失败: %s" % e)
        self.state = TraderState.IDLE
