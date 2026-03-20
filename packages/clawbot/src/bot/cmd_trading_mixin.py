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
        if not rm:
            await update.message.reply_text("风控系统未初始化")
            return
        
        # 先从 IBKR 拉取实时数据
        from src.bot.globals import ibkr
        status_lines = []
        
        if ibkr and ibkr.is_connected():
            try:
                # 1. 获取账户信息
                account_info = await ibkr.get_account_summary()
                if account_info:
                    status_lines.append("=== IBKR 实时数据 ===")
                    status_lines.append(f"净资产: ${account_info.get('NetLiquidation', 0):,.2f}")
                    status_lines.append(f"现金: ${account_info.get('TotalCashValue', 0):,.2f}")
                    status_lines.append(f"今日PnL: ${account_info.get('DailyPnL', 0):+.2f}")
                    status_lines.append("")
                
                # 2. 获取持仓
                positions = await ibkr.get_positions()
                if positions:
                    status_lines.append(f"当前持仓: {len(positions)}个")
                    total_exposure = 0
                    for pos in positions:
                        market_val = pos.get('market_value', 0)
                        total_exposure += abs(market_val)
                        status_lines.append(
                            f"  {pos['symbol']}: {pos['quantity']:+.0f}股 "
                            f"成本${pos['avg_cost']:.2f} 市值${market_val:,.2f}"
                        )
                    status_lines.append(f"总敞口: ${total_exposure:,.2f}")
                    status_lines.append("")
                else:
                    status_lines.append("当前持仓: 无")
                    status_lines.append("")
            except Exception as e:
                status_lines.append(f"⚠️ IBKR数据拉取失败: {e}")
                status_lines.append("")
        else:
            status_lines.append("⚠️ IBKR未连接，无法获取实时数据")
            status_lines.append("")
        
        # 3. 风控系统状态
        status_lines.append(rm.format_status())
        
        await update.message.reply_text("\n".join(status_lines))

    async def cmd_monitor(self, update, context):
        if not self._is_authorized(update.effective_user.id):
            return
        mon = get_position_monitor()
        if mon:
            # 文字状态
            status_text = mon.format_status()

            # 富卡片格式
            try:
                from src.telegram_ux import format_portfolio_card
                from telegram.constants import ParseMode
                positions = getattr(mon, 'positions', {})
                if positions:
                    pos_list = []
                    for sym, pos in positions.items():
                        pos_list.append({
                            "symbol": sym,
                            "quantity": pos.get("quantity", 0),
                            "avg_cost": pos.get("avg_cost", 0),
                            "market_value": pos.get("market_value", 0),
                            "pnl_pct": pos.get("pnl_pct", 0),
                        })
                    cash = getattr(mon, 'cash', 0) or 0
                    card = format_portfolio_card(pos_list, cash)
                    await update.message.reply_text(card, parse_mode=ParseMode.HTML)

                    # 持仓分布饼图
                    if len(pos_list) >= 2:
                        from src.telegram_ux import generate_portfolio_pie, send_chart
                        pie_data = [{"symbol": p["symbol"], "market_value": p["market_value"]} for p in pos_list]
                        chart = generate_portfolio_pie(pie_data)
                        await send_chart(update, context, chart, caption="📊 持仓分布")
                    return
            except Exception:
                pass  # 降级到原有文字格式

            await update.message.reply_text(status_text)
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
        """/backtest AAPL [period] [--ft|--freqtrade]"""
        if not self._is_authorized(update.effective_user.id):
            return
        args = context.args or []
        if not args:
            await update.message.reply_text(
                "回测策略\n\n用法:\n"
                "  /backtest AAPL        - 回测AAPL最近1年\n"
                "  /backtest NVDA 6mo    - 回测NVDA最近6个月\n"
                "  /backtest list        - 回测默认标的列表\n"
                "  /backtest AAPL --ft   - 使用Freqtrade引擎回测\n\n"
                "支持的周期: 3mo, 6mo, 1y, 2y, 5y\n"
                "引擎选项: --ft / --freqtrade (默认自研引擎)"
            )
            return

        # 解析 --ft / --freqtrade 标志
        use_freqtrade = any(a in ("--ft", "--freqtrade") for a in args)
        clean_args = [a for a in args if a not in ("--ft", "--freqtrade")]

        subcmd = clean_args[0].upper() if clean_args else "LIST"
        period = clean_args[1] if len(clean_args) > 1 else "1y"
        valid_periods = ["1mo", "3mo", "6mo", "1y", "2y", "5y"]
        if period not in valid_periods:
            period = "1y"

        if subcmd == "LIST":
            symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD"]
            progress_msg = await update.message.reply_text(
                "开始回测 %d 个标的 (%s)..." % (len(symbols), period))
            try:
                from src.backtester import run_backtest, format_multi_report
                from src.backtest_reporter import BacktestReporter
                from src.telegram_ux import TelegramProgressBar

                bar = TelegramProgressBar(
                    total=len(symbols), label="📊 回测",
                    message=progress_msg, context=context,
                )
                reports = {}
                for sym in symbols:
                    try:
                        r = await asyncio.to_thread(run_backtest, sym, period=period)
                        reports[sym] = r
                    except Exception as e:
                        logger.error("[Backtest] %s 失败: %s", sym, e)
                    await bar.advance(detail=sym)
                if reports:
                    # 尝试生成 HTML 报告（含图表），降级到纯文本
                    try:
                        reporter = BacktestReporter()
                        html_report = reporter.generate_comparison_report(reports)
                        # 发送纯文本摘要 + 提示有详细报告
                        summary = format_multi_report(reports)
                        summary += "\n\n📊 详细图表报告已生成（含权益曲线、回撤图、策略对比）"
                    except Exception:
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
                from src.telegram_ux import send_error_with_retry
                await send_error_with_retry(update, context, e, retry_command="/backtest list")
        else:
            symbol = subcmd
            engine_label = "Freqtrade" if use_freqtrade else "自研"
            await update.message.reply_text(
                "开始回测 %s (%s) [%s引擎]..." % (symbol, period, engine_label))

            if use_freqtrade:
                # ── Freqtrade 引擎路径 ──
                try:
                    from src.freqtrade_bridge import run_backtest_async
                    chat_id = update.effective_chat.id if update.effective_chat else None
                    result, llm_text = await run_backtest_async(
                        symbol, period=period, chat_id=chat_id, with_llm=True,
                    )
                    result_text = result.format_telegram()
                    if llm_text:
                        result_text += "\n\n🤖 AI 分析:\n" + llm_text
                    if not result.success:
                        result_text = "回测失败: %s" % result.error

                    if len(result_text) > 4000:
                        for part in result_text.split("\n\n"):
                            if part.strip():
                                await update.message.reply_text(part)
                    else:
                        await update.message.reply_text(result_text)
                    # Bokeh 可视化图表（增强）
                    await self._send_bokeh_chart(update, context, symbol, period)
                except Exception as e:
                    from src.telegram_ux import send_error_with_retry
                    await send_error_with_retry(
                        update, context, e,
                        retry_command=f"/backtest {symbol} {period} --ft")
            else:
                # ── 自研引擎路径（原有逻辑） ──
                try:
                    from src.backtester import run_backtest
                    from src.backtest_reporter import BacktestReporter
                    report = await asyncio.to_thread(run_backtest, symbol, period=period)
                    result_text = report.format()
                    if report.total_trades > 0:
                        result_text += "\n\n总交易: %d笔" % report.total_trades
                        try:
                            reporter = BacktestReporter()
                            enhanced = reporter.generate_report(report)
                            result_text += "\n📊 详细图表报告已生成（权益曲线、回撤、交易明细）"
                        except Exception:
                            pass
                        try:
                            from src.telegram_ux import generate_equity_chart, generate_pnl_chart, send_chart
                            equity = getattr(report, 'equity_curve', None)
                            if equity and len(equity) > 2:
                                chart = generate_equity_chart(equity, title=f"{symbol} 回测权益曲线 ({period})")
                                await send_chart(update, context, chart, caption=f"📈 {symbol} 权益曲线 | {report.total_trades}笔交易")
                            trade_list = getattr(report, 'trades', None)
                            if trade_list and len(trade_list) > 0:
                                pnl_data = [{"symbol": t.get("symbol", symbol), "pnl": t.get("pnl", 0)} for t in trade_list[:20]]
                                if any(d["pnl"] != 0 for d in pnl_data):
                                    pnl_chart = generate_pnl_chart(pnl_data, title=f"{symbol} 交易盈亏明细")
                                    await send_chart(update, context, pnl_chart, caption=f"📊 {symbol} 交易盈亏")
                        except Exception as chart_err:
                            logger.debug("[Backtest] 图表生成失败(非致命): %s", chart_err)
                    if len(result_text) > 4000:
                        for part in result_text.split("\n\n"):
                            if part.strip():
                                await update.message.reply_text(part)
                    else:
                        await update.message.reply_text(result_text)
                    # Bokeh 可视化图表（增强）
                    await self._send_bokeh_chart(update, context, symbol, period)
                except Exception as e:
                    from src.telegram_ux import send_error_with_retry
                    await send_error_with_retry(update, context, e, retry_command=f"/backtest {symbol} {period}")

    async def _send_bokeh_chart(self, update, context, symbol: str, period: str):
        """发送 backtesting.py Bokeh 可视化图表（非致命，失败静默）"""
        try:
            from src.backtest_reporter import BokehVisualizer, _bokeh_available
            if not _bokeh_available:
                return
            from src.telegram_ux import send_chart

            viz = await asyncio.to_thread(
                BokehVisualizer.run_and_plot, symbol, period)
            if not viz.get("success"):
                return

            # 发送 PNG 图表
            chart_png = viz.get("chart_png")
            if chart_png:
                await send_chart(update, context, chart_png,
                                 caption=f"📊 {symbol} 回测图表 ({period}) [backtesting.py]")
            else:
                # PNG 不可用，发送 stats 文本增强版
                stats_text = BokehVisualizer.stats_to_text(
                    viz.get("stats"), symbol, period)
                if stats_text:
                    await update.message.reply_text(
                        f"📈 backtesting.py 增强分析:\n\n{stats_text}")
        except Exception as e:
            logger.debug("[Backtest] Bokeh 图表生成失败(非致命): %s", e)

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
