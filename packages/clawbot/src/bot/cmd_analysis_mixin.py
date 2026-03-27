"""
技术分析 & 绩效命令 Mixin — 从 multi_main.py L1258-L1485 提取
/ta, /scan, /signal, /performance, /review, /journal
"""
import asyncio
import logging

from src.bot.auth import requires_auth
from src.bot.error_messages import error_service_failed
from src.telegram_ux import with_typing
from src.bot.globals import (
    get_full_analysis, scan_market, format_analysis, format_scan_results,
    journal, chat_router, collab_orchestrator, bot_registry,
    send_long_message, safe_edit,
)

logger = logging.getLogger(__name__)


class AnalysisCommandsMixin:
    """技术分析 & 绩效命令"""

    @requires_auth
    @with_typing
    async def cmd_ta(self, update, context):
        """技术分析: /ta NVDA"""
        args = context.args
        if not args:
            await update.message.reply_text(
                "技术分析 - 全套超短线指标\n\n"
                "用法: /ta 代码\n"
                "示例: /ta NVDA\n"
                "示例: /ta BTC-USD\n\n"
                "包含: RSI/MACD/布林带/EMA/ATR/VWAP/量比/支撑阻力/综合评分"
            )
            return
        symbol = args[0].upper()
        msg = await update.message.reply_text(f"{self.emoji} 正在分析 {symbol} ...")
        try:
            data = await get_full_analysis(symbol)
            text = format_analysis(data)
            await safe_edit(msg, text)
        except Exception as e:
            await safe_edit(msg, error_service_failed("技术分析"))

    @requires_auth
    @with_typing
    async def cmd_scan(self, update, context):
        """市场扫描: /scan"""
        args = context.args
        custom_symbols = [a.upper() for a in args] if args else None
        count = len(custom_symbols) if custom_symbols else 27
        msg = await update.message.reply_text(
            f"{self.emoji} 正在扫描 {count} 个标的，请稍候...")
        try:
            signals = await scan_market(custom_symbols)
            text = format_scan_results(signals)
            await safe_edit(msg, text)
        except Exception as e:
            await safe_edit(msg, error_service_failed("市场扫描"))

    @requires_auth
    @with_typing
    async def cmd_signal(self, update, context):
        """快速信号: /signal NVDA"""
        args = context.args
        if not args:
            await update.message.reply_text(
                "快速信号 - 一秒看买卖\n\n"
                "用法: /signal 代码 [代码2] [代码3]\n"
                "示例: /signal NVDA\n"
                "示例: /signal NVDA AAPL TSLA AMD"
            )
            return
        symbols = [a.upper() for a in args[:8]]
        msg = await update.message.reply_text(f"{self.emoji} 正在分析 {', '.join(symbols)} ...")
        try:
            from src.ta_engine import _score_bar
            results = await asyncio.gather(
                *[get_full_analysis(sym) for sym in symbols],
                return_exceptions=True
            )
            lines = ["快速信号\n"]
            for sym, data in zip(symbols, results):
                if isinstance(data, Exception) or (isinstance(data, dict) and "error" in data):
                    err = data.get("error", str(data)) if isinstance(data, dict) else str(data)
                    lines.append(f"{sym}: 分析失败 - {err}")
                    continue
                sig = data.get("signal", {})
                ind = data.get("indicators", {})
                sr = data.get("support_resistance", {})
                score = sig.get("score", 0)
                bar = _score_bar(score)
                arrow = "+" if data.get("change_pct", 0) >= 0 else ""
                lines.append(
                    f"{sym} ${data['price']} ({arrow}{data['change_pct']}%)\n"
                    f"  {bar} {score:+d} {sig.get('signal_cn', '中性')}\n"
                    f"  RSI6={ind.get('rsi_6',0):.0f} RSI14={ind.get('rsi_14',0):.0f} "
                    f"量比={ind.get('vol_ratio',0):.1f}x "
                    f"趋势={ind.get('trend','?')}"
                )
                if sr.get('supports'):
                    lines.append(f"  支撑: {sr['supports'][0]}")
                if sr.get('resistances'):
                    lines.append(f"  阻力: {sr['resistances'][0]}")
            await safe_edit(msg, "\n".join(lines))
        except Exception as e:
            await safe_edit(msg, error_service_failed("信号分析"))

    @requires_auth
    @with_typing
    async def cmd_performance(self, update, context):
        """绩效仪表盘: /performance"""
        days = 30
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError:
                await update.message.reply_text("⚠️ 天数参数无效 '%s'，使用默认值30天" % context.args[0])
        text = journal.format_performance(days)
        await send_long_message(update.effective_chat.id, text, context,
                                reply_to_message_id=update.message.message_id)

    @requires_auth
    @with_typing
    async def cmd_review(self, update, context):
        """复盘: /review — AI团队复盘今日交易"""
        if chat_router.get_discuss_session(update.effective_chat.id):
            await update.message.reply_text("已有会议进行中")
            return

        chat_id = update.effective_chat.id
        message_id = update.message.message_id

        review_data = journal.generate_review_data()
        if review_data['trade_count'] == 0 and not review_data['open_trades']:
            await update.message.reply_text(
                "今日暂无交易记录，无需复盘。\n\n"
                "说「开始投资」启动AI团队寻找机会。"
            )
            return

        msg = await update.message.reply_text(f"{self.emoji} 正在召开复盘会议...")

        review_prompt = journal.format_review_prompt()
        review_order = ["claude_haiku", "deepseek_v3", "claude_sonnet"]
        info = await chat_router.start_discuss(chat_id, "每日复盘", 1, review_order, discuss_type="invest")
        if "已有进行中" in info:
            await safe_edit(msg, info)
            return

        from src.message_sender import _clean_for_telegram, _split_message

        review_roles = {
            "claude_haiku": ("复盘记录员", f"你是交易团队的复盘记录员。请基于以下交易数据，快速整理：\n1. 今日交易概况\n2. 每笔交易的简要回顾\n3. 市场环境总结\n\n{review_prompt}"),
            "deepseek_v3": ("风控审计", f"你是交易团队的风控审计。请审查今日交易：\n1. 哪些交易遵守了风控规则（止损、仓位）\n2. 哪些交易违反了规则\n3. 风险敞口是否合理\n4. 改进建议\n\n{review_prompt}"),
            "claude_sonnet": ("首席复盘官", f"你是交易团队的首席复盘官。请做最终复盘总结：\n1. 今日做得好的地方（具体到哪笔交易）\n2. 今日做得差的地方（具体到哪笔交易）\n3. 经验教训（可复用的规则）\n4. 明日交易计划和关注点\n5. 团队整体评分(1-10)\n\n{review_prompt}"),
        }

        previous = []
        full_report_parts = []
        for bot_id in review_order:
            if not chat_router.get_discuss_session(chat_id):
                break
            caller = collab_orchestrator._api_callers.get(bot_id)
            target_bot = bot_registry.get(bot_id)
            if not caller or not target_bot or not target_bot.app:
                continue

            role_name, role_prompt = review_roles.get(bot_id, ("分析师", "请复盘"))
            prompt = f"【每日复盘会议】\n{role_prompt}\n"
            if previous:
                prompt += "\n前面的复盘意见:\n" + "\n---\n".join(previous) + "\n"

            try:
                response = await asyncio.wait_for(caller(chat_id, prompt), timeout=120)
                previous.append(f"[{role_name}] {response[:600]}")
                full_report_parts.append(f"[{role_name}]\n{response}")

                cleaned = _clean_for_telegram(response)
                parts = _split_message(cleaned, 4000)
                bot_tg = target_bot.app.bot
                for pi, part in enumerate(parts):
                    try:
                        await bot_tg.send_message(chat_id=chat_id, text=part, parse_mode="Markdown")
                    except Exception:
                        await bot_tg.send_message(chat_id=chat_id, text=part)
                    if pi < len(parts) - 1:
                        await asyncio.sleep(0.3)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"[Review] {bot_id} 复盘失败: {e}")

        await chat_router.stop_discuss(chat_id)

        try:
            journal.save_review_session(
                date=review_data['date'],
                session_type='daily',
                trades_reviewed=review_data['trade_count'],
                total_pnl=review_data['total_pnl'],
                win_rate=review_data['win_rate'],
                full_report="\n\n".join(full_report_parts),
                participants=",".join(review_order),
            )
        except Exception as e:
            logger.warning(f"[Review] 保存复盘记录失败: {e}")

        await context.bot.send_message(
            chat_id=chat_id,
            text="-- 复盘会议结束 --\n复盘记录已保存。",
            reply_to_message_id=message_id,
        )

    @requires_auth
    @with_typing
    async def cmd_journal(self, update, context):
        """交易日志: /journal"""
        open_trades = journal.get_open_trades()
        closed = journal.get_closed_trades(days=7, limit=10)

        lines = ["交易日志\n"]
        if open_trades:
            lines.append(f"-- 持仓中 ({len(open_trades)}笔) --")
            for t in open_trades:
                lines.append(
                    f"#{t['id']} {t['side']} {t['symbol']} x{t['quantity']} "
                    f"入:{t['entry_price']} 止损:{t['stop_loss'] or '无'} "
                    f"理由:{(t['entry_reason'] or '无')[:30]} "
                    f"[🤖 {t.get('decided_by', '未知')}]"
                )
        else:
            lines.append("持仓: 无")

        if closed:
            lines.append(f"\n-- 近期已平仓 ({len(closed)}笔) --")
            for t in closed:
                sign = "+" if t['pnl'] >= 0 else ""
                lines.append(
                    f"#{t['id']} {t['side']} {t['symbol']} "
                    f"PnL:{sign}${t['pnl']:.2f}({sign}{t['pnl_pct']:.1f}%) "
                    f"持仓:{t['hold_duration_hours'] or 0:.0f}h "
                    f"[🤖 {t.get('decided_by', '未知')}]"
                )

        await send_long_message(update.effective_chat.id, "\n".join(lines), context,
                                reply_to_message_id=update.message.message_id)

    # ============ 新增: AI预测准确率 / 权益曲线 / 盈利目标进度 ============

    @requires_auth
    @with_typing
    async def cmd_accuracy(self, update, context):
        """AI预测准确率面板 — 展示每个AI的历史预测表现"""
        # 支持自定义天数，默认30天
        days = 30
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError:
                await update.message.reply_text(
                    "⚠️ 天数参数无效 '%s'，使用默认值30天" % context.args[0])

        try:
            data = journal.get_prediction_accuracy(days)

            # 没有预测数据时的友好提示
            if data['total_predictions'] == 0:
                await update.message.reply_text(
                    "📊 AI预测准确率面板\n\n"
                    "暂无预测记录。\n"
                    "AI团队在投资决策时会自动记录预测，"
                    "收盘后系统会验证准确率。\n\n"
                    "说「开始投资」启动AI团队。"
                )
                return

            # 按准确率降序排列各AI
            sorted_ai = sorted(
                data['by_ai'].items(),
                key=lambda x: x[1]['accuracy'],
                reverse=True,
            )

            lines = [
                f"📊 AI预测准确率面板 (近{days}天)",
                "━━━━━━━━━━━━━━━━━━━━━━",
            ]
            for ai_name, stats in sorted_ai:
                lines.append(
                    f"🤖 {ai_name}: {stats['accuracy']}% ({stats['total']}次)\n"
                    f"   平均偏差: {stats['avg_deviation']}%"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(
                f"📈 总体: {data['overall_accuracy']}% "
                f"({data['total_predictions']}次)"
            )

            await send_long_message(
                update.effective_chat.id, "\n".join(lines), context,
                reply_to_message_id=update.message.message_id,
            )
        except Exception as e:
            logger.error("[Accuracy] 获取预测准确率失败: %s", e)
            await update.message.reply_text(error_service_failed("预测准确率"))

    @requires_auth
    @with_typing
    async def cmd_equity(self, update, context):
        """权益曲线 — 展示投资收益随时间的变化图表"""
        # 支持自定义天数，默认30天
        days = 30
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError:
                await update.message.reply_text(
                    "⚠️ 天数参数无效 '%s'，使用默认值30天" % context.args[0])

        try:
            equity_values, date_labels = journal.get_equity_curve(days)

            # 没有交易数据时的友好提示
            if not equity_values:
                await update.message.reply_text(
                    "📈 权益曲线\n\n"
                    "暂无已平仓交易记录，无法生成权益曲线。\n"
                    "说「开始投资」启动AI团队。"
                )
                return

            # 生成图表并发送
            from src.telegram_ux import generate_equity_chart, send_chart
            chart = generate_equity_chart(
                equity_values,
                title=f"权益曲线 (近{days}天)",
            )

            # 构建摘要文字作为图片说明
            start_val = equity_values[0]
            end_val = equity_values[-1]
            change = end_val - start_val
            change_pct = (change / start_val * 100) if start_val != 0 else 0
            sign = "+" if change >= 0 else ""
            caption = (
                f"📈 权益曲线 (近{days}天)\n"
                f"起始: ${start_val:,.2f} → 当前: ${end_val:,.2f}\n"
                f"变动: {sign}${change:,.2f} ({sign}{change_pct:.1f}%)"
            )

            await send_chart(update, context, chart, caption=caption)
        except Exception as e:
            logger.error("[Equity] 生成权益曲线失败: %s", e)
            await update.message.reply_text(error_service_failed("权益曲线"))

    @requires_auth
    @with_typing
    async def cmd_targets(self, update, context):
        """盈利目标进度 — 展示各目标达成百分比"""
        try:
            text = journal.format_target_progress()
            await send_long_message(
                update.effective_chat.id, text, context,
                reply_to_message_id=update.message.message_id,
            )
        except Exception as e:
            logger.error("[Targets] 获取盈利目标失败: %s", e)
            await update.message.reply_text(error_service_failed("盈利目标进度"))

    @requires_auth
    @with_typing
    async def cmd_weekly(self, update, context):
        """手动触发综合周报 — 聚合投资+社媒+闲鱼+成本 7 天数据"""
        msg = await update.message.reply_text(f"{self.emoji} 正在生成综合周报，请稍候...")
        try:
            from src.execution.daily_brief import weekly_report
            result = await weekly_report()
            if result and len(result.strip()) > 20:
                await safe_edit(msg, result)
            else:
                await safe_edit(msg, "📋 本周暂无可汇总的数据")
        except Exception as e:
            logger.warning("[Weekly] 周报生成失败: %s", e)
            await safe_edit(msg, "⚠️ 周报生成失败，请稍后再试")

    @requires_auth
    @with_typing
    async def cmd_review_history(self, update, context):
        """复盘历史 — 查看过往复盘记录和教训"""
        limit = 5
        if context.args:
            try:
                limit = int(context.args[0])
            except ValueError:
                pass

        try:
            records = journal.get_review_history(limit)
            if not records:
                await update.message.reply_text(
                    "📋 暂无复盘记录\n\n"
                    "说「复盘」启动AI团队复盘会议。"
                )
                return

            lines = [f"📋 复盘历史 (近{len(records)}次)", "━━━━━━━━━━━━━━━"]
            for i, r in enumerate(records, 1):
                # 日期格式化: "03-27 20:30"
                created = r.get("created_at", "")
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created)
                    date_str = dt.strftime("%m-%d %H:%M")
                except Exception:
                    date_str = created[:16] if created else "未知"

                # 星级评分 (基于 win_rate)
                win_rate = r.get("win_rate", 0) or 0
                if win_rate >= 80:
                    stars = "★★★★★"
                elif win_rate >= 60:
                    stars = "★★★★☆"
                elif win_rate >= 40:
                    stars = "★★★☆☆"
                elif win_rate >= 20:
                    stars = "★★☆☆☆"
                else:
                    stars = "★☆☆☆☆"

                lesson = r.get("lessons_learned", "") or ""
                lesson_short = lesson[:40] + "..." if len(lesson) > 40 else lesson

                pnl = r.get("total_pnl", 0) or 0
                trades_count = r.get("trades_reviewed", 0) or 0

                lines.append(
                    f"\n{i}. [{date_str}] {stars}"
                    f"\n   盈亏: ${pnl:+.2f} | {trades_count}笔交易"
                )
                if lesson_short:
                    lines.append(f"   教训: {lesson_short}")

            await send_long_message(
                update.effective_chat.id, "\n".join(lines), context,
                reply_to_message_id=update.message.message_id,
            )
        except Exception as e:
            logger.error("[ReviewHistory] 获取复盘历史失败: %s", e)
            await update.message.reply_text("⚠️ 获取复盘历史失败，请稍后再试")

    @requires_auth
    @with_typing
    async def cmd_chart(self, update, context):
        """K线图表: /chart NVDA — 生成K线图"""
        args = context.args
        if not args:
            await update.message.reply_text(
                "📈 K线图表\n\n"
                "用法: /chart 代码\n"
                "示例: /chart NVDA\n"
                "示例: /chart BTC-USD\n\n"
                "也可以说「苹果的K线」「看看TSLA图」"
            )
            return
        symbol = args[0].upper()
        msg = await update.message.reply_text(f"{self.emoji} 正在生成 {symbol} K线图...")
        try:
            from src.data_providers import get_history_sync
            df = get_history_sync(symbol, period="3mo", interval="1d")
            if df is None or df.empty:
                await safe_edit(msg, f"⚠️ 未找到 {symbol} 的历史数据")
                return

            # 转换为 charts.py 需要的格式
            ohlcv = []
            for idx, row in df.iterrows():
                ohlcv.append({
                    "date": str(idx.date()) if hasattr(idx, 'date') else str(idx),
                    "open": float(row.get("Open", 0)),
                    "high": float(row.get("High", 0)),
                    "low": float(row.get("Low", 0)),
                    "close": float(row.get("Close", 0)),
                    "volume": float(row.get("Volume", 0)),
                })

            from src.charts import generate_candlestick
            png_bytes = generate_candlestick(ohlcv, symbol=symbol)
            if not png_bytes:
                await safe_edit(msg, f"⚠️ {symbol} K线图生成失败（图表引擎不可用）")
                return

            # 发送图片
            import io as _io
            await update.message.reply_photo(
                photo=_io.BytesIO(png_bytes),
                caption=f"📈 {symbol} K线图 (近3个月)",
            )
            await msg.delete()
        except Exception as e:
            logger.error("[Chart] 生成K线图失败: %s", e)
            await safe_edit(msg, f"⚠️ {symbol} K线图生成失败，请稍后再试")
