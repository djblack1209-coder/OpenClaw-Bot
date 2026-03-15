"""
自动交易系统命令 Mixin — 从 multi_main.py L1652-L1909 提取
/autotrader, /risk, /monitor, /tradingsystem, /backtest, /rebalance
"""
import asyncio
import logging

from src.bot.globals import (
    get_auto_trader, get_risk_manager, get_position_monitor,
    get_system_status, get_stock_quote, portfolio,
    send_long_message,
)

logger = logging.getLogger(__name__)


class TradingCommandsMixin:
    """自动交易系统命令"""

    async def cmd_autotrader(self, update, context):
        """/autotrader [start|stop|status|auto|manual|cycle]"""
        if not self._is_authorized(update.effective_user.id):
            return
        trader = get_auto_trader()
        if not trader:
            await update.message.reply_text("AutoTrader 未初始化")
            return
        args = context.args
        sub = args[0].lower() if args else "status"
        if sub == "start":
            await trader.start()
            await update.message.reply_text("AutoTrader 已启动 (扫描间隔%d分钟)" % trader.scan_interval)
        elif sub == "stop":
            await trader.stop()
            await update.message.reply_text("AutoTrader 已停止")
        elif sub == "auto":
            trader.set_auto_mode(True)
            await update.message.reply_text("已切换为全自动模式 - 交易将自动执行，无需确认")
        elif sub == "manual":
            trader.set_auto_mode(False)
            await update.message.reply_text("已切换为手动确认模式 - 交易需要确认后执行")
        elif sub == "cycle":
            await update.message.reply_text("手动触发交易循环...")
            result = await trader.run_cycle_once()
            await update.message.reply_text(
                "交易循环完成\n\n扫描信号: %d\n候选标的: %d\n交易提案: %d\n已执行: %d\n被拒绝: %d"
                % (result["scanned"], result["candidates"], result["proposals"],
                   result["executed"], result["rejected"])
            )
        elif sub == "confirm":
            result = await trader.confirm_proposal()
            if result:
                await update.message.reply_text("提案已执行: %s" % result.get("status", "unknown"))
            else:
                await update.message.reply_text("无待确认提案")
        elif sub == "cancel":
            count = trader.cancel_proposals()
            await update.message.reply_text("已取消 %d 个待确认提案" % count)
        else:
            await update.message.reply_text(trader.format_status())

    async def cmd_risk(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        rm = get_risk_manager()
        if rm:
            await update.message.reply_text(rm.format_status())
        else:
            await update.message.reply_text("风控系统未初始化")

    async def cmd_monitor(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        mon = get_position_monitor()
        if mon:
            await update.message.reply_text(mon.format_status())
        else:
            await update.message.reply_text("持仓监控器未初始化")

    async def cmd_tradingsystem(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        status = get_system_status()
        if len(status) > 4000:
            parts = status.split("\n\n")
            for part in parts:
                if part.strip():
                    await update.message.reply_text(part)
        else:
            await update.message.reply_text(status)

    async def cmd_backtest(self, update, context):
        """/backtest AAPL [period]"""
        if not self._is_authorized(update.effective_user.id):
            return
        args = context.args or []
        if not args:
            await update.message.reply_text(
                "回测策略\n\n用法:\n"
                "  /backtest AAPL        - 回测AAPL最近1年\n"
                "  /backtest NVDA 6mo    - 回测NVDA最近6个月\n"
                "  /backtest list        - 回测默认标的列表\n\n"
                "支持的周期: 3mo, 6mo, 1y, 2y, 5y"
            )
            return

        subcmd = args[0].upper()
        period = args[1] if len(args) > 1 else "1y"
        valid_periods = ["1mo", "3mo", "6mo", "1y", "2y", "5y"]
        if period not in valid_periods:
            period = "1y"

        if subcmd == "LIST":
            symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD"]
            await update.message.reply_text(
                "开始回测 %d 个标的 (%s)...\n预计需要几分钟。" % (len(symbols), period))
            try:
                from src.backtester import run_backtest, format_multi_report
                reports = {}
                for sym in symbols:
                    try:
                        r = await asyncio.to_thread(run_backtest, sym, period=period)
                        reports[sym] = r
                    except Exception as e:
                        logger.error("[Backtest] %s 失败: %s", sym, e)
                if reports:
                    summary = format_multi_report(reports)
                    if len(summary) > 4000:
                        for part in summary.split("\n\n"):
                            if part.strip():
                                await update.message.reply_text(part)
                    else:
                        await update.message.reply_text(summary)
                else:
                    await update.message.reply_text("所有标的回测失败。")
            except Exception as e:
                await update.message.reply_text("回测出错: %s" % e)
        else:
            symbol = subcmd
            await update.message.reply_text("开始回测 %s (%s)..." % (symbol, period))
            try:
                from src.backtester import run_backtest
                report = await asyncio.to_thread(run_backtest, symbol, period=period)
                result_text = report.format()
                if report.total_trades > 0:
                    result_text += "\n\n总交易: %d笔" % report.total_trades
                if len(result_text) > 4000:
                    for part in result_text.split("\n\n"):
                        if part.strip():
                            await update.message.reply_text(part)
                else:
                    await update.message.reply_text(result_text)
            except Exception as e:
                await update.message.reply_text("回测 %s 失败: %s" % (symbol, e))

    async def cmd_rebalance(self, update, context):
        """/rebalance [set <preset>|status|run]"""
        if not self._is_authorized(update.effective_user.id):
            return

        from src.rebalancer import rebalancer, PRESET_ALLOCATIONS

        args = context.args or []
        subcmd = args[0].lower() if args else "analyze"

        if subcmd == "set":
            preset_name = args[1].lower() if len(args) > 1 else ""
            if preset_name not in PRESET_ALLOCATIONS:
                names = ", ".join("%s(%s)" % (k, v[0]) for k, v in PRESET_ALLOCATIONS.items())
                await update.message.reply_text("可用预设配置:\n%s\n\n用法: /rebalance set tech" % names)
                return
            label, targets = PRESET_ALLOCATIONS[preset_name]
            rebalancer.set_targets(targets)
            await update.message.reply_text(
                "已设置目标配置: %s\n\n%s" % (label, rebalancer.format_targets()))
            return

        if subcmd == "targets":
            await update.message.reply_text(rebalancer.format_targets())
            return

        if not rebalancer.get_targets():
            await update.message.reply_text(
                "未设置目标配置\n\n请先设置:\n"
                "  /rebalance set tech - 科技成长型\n"
                "  /rebalance set balanced - 均衡型\n"
                "  /rebalance set conservative - 保守型"
            )
            return

        await update.message.reply_text("正在分析组合漂移...")
        try:
            positions = portfolio.get_positions()
            cash = portfolio.get_cash()
            quotes = {}
            all_symbols = [t.symbol for t in rebalancer.get_targets()]
            all_symbols += [p.get("symbol", "") for p in positions]
            all_symbols = list(set(s for s in all_symbols if s))

            results = await asyncio.gather(
                *[get_stock_quote(sym) for sym in all_symbols],
                return_exceptions=True,
            )
            for sym, r in zip(all_symbols, results):
                if isinstance(r, dict) and "price" in r:
                    quotes[sym] = r["price"]

            plan = rebalancer.analyze(positions, quotes, cash)
            text = plan.format()
            if len(text) > 4000:
                for part in text.split("\n\n"):
                    if part.strip():
                        await update.message.reply_text(part)
            else:
                await update.message.reply_text(text)
        except Exception as e:
            await update.message.reply_text("再平衡分析失败: %s" % e)
