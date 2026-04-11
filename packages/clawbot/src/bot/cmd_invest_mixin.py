"""
投资命令 Mixin — 从 multi_main.py L1037-L1255 提取
/quote, /market, /portfolio, /buy, /sell, /watchlist, /trades, /reset_portfolio
"""
import logging
import time as _time
from typing import Dict

from src.bot.globals import (
    get_stock_quote, send_long_message,
)
# 幻影导入修复: 6 个符号从实际定义模块导入
from src.invest_tools import get_crypto_quote, get_market_summary, format_quote, portfolio
from src.trading._lifecycle import get_risk_manager
from src.broker_selector import ibkr
from src.bot.error_messages import error_service_failed
from src.constants import ERR_RISK_NOT_INIT, ERR_QTY_POSITIVE, ERR_ORDER_PENDING, ERR_LIVE_UNAVAILABLE
from src.bot.auth import requires_auth
from src.telegram_ux import with_typing

logger = logging.getLogger(__name__)

# ── 防重复下单冷却 (FIX 3) ──────────────────────────────────
_trade_cooldown: Dict[str, float] = {}   # key="{user_id}:{symbol}", value=timestamp
_TRADE_COOLDOWN_SEC = 30


class InvestCommandsMixin:
    """投资相关 Telegram 命令"""

    @requires_auth
    @with_typing
    async def cmd_calc(self, update, context):
        """仓位计算器: /calc TSLA 195 190 (代码 入场价 止损价)

        搬运 TradingView Position Size Calculator:
        根据账户大小、风险偏好自动计算该买多少股。
        同时给出固定比例法和凯利公式法两种建议。
        """
        args = context.args
        if not args or len(args) < 3:
            await update.message.reply_text(
                "📐 仓位计算器\n\n"
                "用法: `/calc 代码 入场价 止损价 [目标价]`\n"
                "示例: `/calc TSLA 195 190`\n"
                "示例: `/calc AAPL 180 175 200`\n\n"
                "自动根据你的风控参数计算该买多少股。",
                parse_mode="Markdown",
            )
            return

        symbol = args[0].upper()
        try:
            entry_price = float(args[1])
            stop_loss = float(args[2])
            take_profit = float(args[3]) if len(args) > 3 else 0
        except ValueError as e:  # noqa: F841
            await update.message.reply_text("❌ 价格必须是数字。用法: /calc TSLA 195 190")
            return

        if stop_loss >= entry_price:
            await update.message.reply_text("❌ 止损价必须低于入场价。")
            return

        rm = get_risk_manager()
        if not rm:
            await update.message.reply_text("❌ 风控引擎未就绪。")
            return

        # 固定比例法
        safe = rm.calc_safe_quantity(entry_price, stop_loss)
        # 凯利公式法
        kelly = rm.calc_kelly_quantity(entry_price, stop_loss, take_profit) if hasattr(rm, 'calc_kelly_quantity') else {}

        risk_per_share = entry_price - stop_loss
        risk_pct = (risk_per_share / entry_price) * 100

        lines = [
            f"📐 <b>仓位计算 — {symbol}</b>",
            "",
            f"入场价: ${entry_price:.2f}",
            f"止损价: ${stop_loss:.2f} (风险 {risk_pct:.1f}%)",
        ]
        if take_profit > 0:
            rr = (take_profit - entry_price) / risk_per_share
            lines.append(f"目标价: ${take_profit:.2f} (盈亏比 {rr:.1f}:1)")

        lines.append("")
        lines.append("━━━ 固定比例法 (2%风险) ━━━")
        if safe:
            lines.append(f"建议数量: <b>{safe.get('quantity', 0)}</b> 股")
            lines.append(f"投入金额: ${safe.get('total_cost', 0):,.0f}")
            lines.append(f"最大亏损: ${safe.get('max_loss', 0):,.0f}")

        if kelly and kelly.get("quantity", 0) > 0:
            lines.append("")
            lines.append("━━━ 凯利公式法 (保守1/4) ━━━")
            lines.append(f"建议数量: <b>{kelly.get('quantity', 0)}</b> 股")
            lines.append(f"投入金额: ${kelly.get('total_cost', 0):,.0f}")
            if kelly.get("kelly_pct"):
                lines.append(f"凯利仓位: {kelly['kelly_pct']:.1f}%")

        msg = "\n".join(lines)
        await update.message.reply_text(msg, parse_mode="HTML")

    @requires_auth
    @with_typing
    async def cmd_quote(self, update, context):
        """查询行情: /quote AAPL 或 /quote BTC — 富卡片格式 + 错误恢复"""
        args = context.args
        if not args:
            await update.message.reply_text("用法: `/quote AAPL` 或 `/quote BTC`", parse_mode="Markdown")
            return
        symbol = args[0].upper()
        await update.message.reply_text(f"{self.emoji} 查询 {symbol} 行情中...")
        crypto_symbols = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "DOT", "AVAX", "MATIC", "LINK"}
        try:
            if symbol in crypto_symbols:
                quote = await get_crypto_quote(symbol)
            else:
                quote = await get_stock_quote(symbol)

            # 优先使用富卡片格式
            if isinstance(quote, dict) and "price" in quote and not quote.get("error"):
                from src.telegram_ux import format_quote_card
                from telegram.constants import ParseMode
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                card = format_quote_card(quote)
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📊 技术分析", callback_data=f"ta_{symbol}"),
                    InlineKeyboardButton("🟢 买入", callback_data=f"buy_{symbol}"),
                    InlineKeyboardButton("⭐ 加自选", callback_data=f"watch_{symbol}"),
                ]])
                await update.message.reply_text(
                    card, parse_mode=ParseMode.HTML,
                    reply_to_message_id=update.message.message_id,
                    reply_markup=keyboard,
                )
            else:
                # 降级到原有格式
                text = format_quote(quote)
                await send_long_message(
                    update.effective_chat.id, text, context,
                    reply_to_message_id=update.message.message_id,
                )
        except Exception as e:
            from src.telegram_ux import send_error_with_retry
            await send_error_with_retry(update, context, e, retry_command=f"/quote {symbol}")

    @requires_auth
    @with_typing
    async def cmd_market(self, update, context):
        """市场概览: /market"""
        await update.message.reply_text(f"{self.emoji} 获取市场概览中（约10秒）...")
        try:
            text = await get_market_summary()
            await send_long_message(update.effective_chat.id, text, context, reply_to_message_id=update.message.message_id)
        except Exception as e:
            from src.telegram_ux import send_error_with_retry
            await send_error_with_retry(update, context, e, retry_command="/market")

    @requires_auth
    @with_typing
    async def cmd_portfolio(self, update, context):
        """查看投资组合: /portfolio"""
        await update.message.reply_text(f"{self.emoji} 计算投资组合中...")

        # 获取结构化持仓数据用于富卡片
        positions_raw = portfolio.get_positions()
        cash = portfolio.get_cash()

        if positions_raw:
            # 并行查询行情，构建 format_portfolio_card 所需数据
            from src.bot.globals import get_stock_quote
            import asyncio
            quotes = await asyncio.gather(
                *[get_stock_quote(p["symbol"]) for p in positions_raw],
                return_exceptions=True,
            )
            enriched = []
            for pos, quote in zip(positions_raw, quotes):
                if isinstance(quote, Exception) or (isinstance(quote, dict) and "error" in quote):
                    current_price = pos["avg_price"]
                else:
                    current_price = quote.get("price", pos["avg_price"])
                market_value = pos["quantity"] * current_price
                cost = pos["quantity"] * pos["avg_price"]
                pnl_pct = ((current_price / pos["avg_price"]) - 1) * 100 if pos["avg_price"] else 0
                enriched.append({
                    "symbol": pos["symbol"],
                    "quantity": pos["quantity"],
                    "avg_cost": pos["avg_price"],
                    "market_value": market_value,
                    "pnl_pct": pnl_pct,
                })

            from src.telegram_ux import format_portfolio_card, generate_portfolio_pie, send_chart
            card = format_portfolio_card(enriched, cash=cash)
            await update.message.reply_text(card, parse_mode="HTML",
                                            reply_to_message_id=update.message.message_id)

            # ── 风险敞口文本（新增） ──────────────────────────
            try:
                rm = get_risk_manager()
                if rm:
                    exposure = rm.get_risk_exposure_summary(enriched, cash)
                    risk_lines = [
                        "⚠️ <b>风险敞口</b>",
                        "━━━━━━━━━━━━━━━",
                        f"单只最大: {exposure['max_single_symbol']} "
                        f"{exposure['max_single_pct']}% "
                        f"(阈值 {exposure['max_single_threshold']:.0f}%)",
                        f"同行业最大: {exposure['max_sector_name']} "
                        f"{exposure['max_sector_pct']}% "
                        f"(阈值 {exposure['max_sector_threshold']:.0f}%)",
                        f"总仓位: {exposure['total_position_pct']}% "
                        f"(阈值 {exposure['total_position_threshold']:.0f}%)",
                        f"日亏限额: 已用 ${exposure['daily_loss_used']:.0f} "
                        f"/ ${exposure['daily_loss_limit']:.0f}",
                    ]
                    await update.message.reply_text(
                        "\n".join(risk_lines), parse_mode="HTML",
                        reply_to_message_id=update.message.message_id,
                    )
            except Exception as e:
                logger.debug("风险敞口展示失败: %s", e)

            # ── SPY Benchmark 对比（新增） ──────────────────
            try:
                import yfinance as yf
                from datetime import datetime, timedelta
                # 计算组合近30天收益
                total_value = sum(abs(p.get("market_value", 0)) for p in enriched) + cash
                total_cost = sum(p.get("quantity", 0) * p.get("avg_cost", 0) for p in enriched) + cash
                portfolio_return = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

                # 获取 SPY 近30天收益
                end_date = datetime.now()
                start_date = end_date - timedelta(days=35)
                spy_data = yf.download(
                    "SPY", start=start_date.strftime("%Y-%m-%d"),
                    end=end_date.strftime("%Y-%m-%d"), progress=False
                )
                if spy_data is not None and len(spy_data) >= 2:
                    # 取近30个交易日的首尾计算涨跌幅
                    spy_close = spy_data["Close"]
                    if hasattr(spy_close, "iloc"):
                        spy_start = float(spy_close.iloc[-min(22, len(spy_close))])
                        spy_end = float(spy_close.iloc[-1])
                        spy_return = ((spy_end / spy_start) - 1) * 100
                        alpha = portfolio_return - spy_return
                        alpha_emoji = "🟢" if alpha >= 0 else "🔴"
                        spy_line = (
                            f"📈 近30天: 你的组合 {portfolio_return:+.1f}% "
                            f"| SPY {spy_return:+.1f}% "
                            f"| {alpha_emoji} 超额 {alpha:+.1f}%"
                        )
                        await update.message.reply_text(
                            spy_line,
                            reply_to_message_id=update.message.message_id,
                        )
            except Exception as e:
                logger.debug("SPY对标展示失败: %s", e)

            # 发送持仓饼图（已有）
            try:
                chart = generate_portfolio_pie(enriched, "资产配置")
                await send_chart(update, context, chart, caption="")
            except Exception as e:
                logger.debug("Portfolio pie chart failed: %s", e)

            # ── 行业分布饼图（新增） ──────────────────────────
            try:
                rm = get_risk_manager()
                if rm:
                    # 复用风险敞口计算中已缓存的 sector 数据
                    symbols = [p.get("symbol", "") for p in enriched]
                    sector_map = rm.lookup_sectors(symbols)
                    sector_values = {}
                    for p in enriched:
                        sym = p.get("symbol", "").upper()
                        sector = sector_map.get(sym, "未知")
                        mv = abs(p.get("market_value", 0))
                        sector_values[sector] = sector_values.get(sector, 0) + mv
                    # 至少有2个行业才值得画饼图
                    if len(sector_values) >= 2 or (
                        len(sector_values) == 1 and "未知" not in sector_values
                    ):
                        from src.telegram_ux import generate_sector_pie
                        sector_chart = generate_sector_pie(sector_values, "行业分布")
                        await send_chart(update, context, sector_chart, caption="")
            except Exception as e:
                logger.debug("行业分布饼图失败: %s", e)
        else:
            from src.telegram_ux import format_portfolio_card
            card = format_portfolio_card([], cash=cash)
            await update.message.reply_text(card, parse_mode="HTML",
                                            reply_to_message_id=update.message.message_id)

        # 当 IBKR 已连接时，追加实盘持仓
        if ibkr.is_connected():
            try:
                ibkr_text = await ibkr.get_positions_text()
                if ibkr_text.strip():
                    ibkr_msg = "━━━ 实盘持仓 ━━━\n" + ibkr_text
                    ibkr_msg += "\n" + ibkr.get_budget_status()
                    await update.message.reply_text(ibkr_msg,
                                                    reply_to_message_id=update.message.message_id)
            except Exception as e:
                logger.warning("获取盈透券商持仓失败: %s", e, exc_info=True)
                await update.message.reply_text("⚠️ 严总，实盘持仓暂时拉不到，请稍后再试",
                                                reply_to_message_id=update.message.message_id)

    @requires_auth
    @with_typing
    async def cmd_buy(self, update, context):
        """模拟买入: /buy AAPL 10 或 /buy AAPL 10 150.5"""
        args = context.args
        if not args or len(args) < 2:
            await update.message.reply_text(
                "用法: `/buy 代码 数量 [价格]`\n"
                "示例: `/buy AAPL 10` (按当前价)\n"
                "示例: `/buy AAPL 10 150.5` (指定价格)",
                parse_mode="Markdown"
            )
            return
        symbol = args[0].upper()
        try:
            quantity = float(args[1])
        except ValueError as e:  # noqa: F841
            await update.message.reply_text("数量必须是数字")
            return
        # FIX 2: 校验正数
        if quantity <= 0:
            await update.message.reply_text(ERR_QTY_POSITIVE)
            return
        if len(args) >= 3:
            try:
                price = float(args[2])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("价格必须是数字")
                return
        else:
            await update.message.reply_text(f"{self.emoji} 获取 {symbol} 当前价格...")
            quote = await get_stock_quote(symbol)
            if "error" in quote:
                await update.message.reply_text(error_service_failed("行情查询", quote.get('error', '')))
                return
            price = quote["price"]

        # FIX 3: 防重复下单冷却
        user_id = update.effective_user.id if update.effective_user else 0
        dedup_key = f"{user_id}:{symbol}"
        now_ts = _time.time()
        last_trade_ts = _trade_cooldown.get(dedup_key, 0)
        if now_ts - last_trade_ts < _TRADE_COOLDOWN_SEC:
            remaining = int(_TRADE_COOLDOWN_SEC - (now_ts - last_trade_ts))
            await update.message.reply_text(f"⚠️ 请勿重复下单，{remaining}秒后可再次交易 {symbol}。")
            return

        # FIX 6: 风控系统必须初始化（实盘场景）
        rm = get_risk_manager()
        if rm is None and ibkr.is_connected():
            await update.message.reply_text(ERR_RISK_NOT_INIT)
            return
        # 风控检查
        if rm and price > 0:
            # 动态止损: 波动率大的标的用更宽止损，小盘股/加密货币 5%，大盘蓝筹 3%
            sl_pct = 0.05 if price < 10 or symbol.endswith("USD") else 0.03
            sl = round(price * (1 - sl_pct), 2)
            # 传入当前持仓，启用总敞口和最大持仓数检查
            current_positions = []
            try:
                positions = portfolio.get_positions() if hasattr(portfolio, 'get_positions') else portfolio.positions
                if isinstance(positions, dict):
                    current_positions = [{"symbol": k, "quantity": v.get("quantity", 0), "avg_price": v.get("avg_price", 0)} for k, v in positions.items()]
                elif isinstance(positions, list):
                    current_positions = positions
            except Exception as e:
                logger.debug("静默异常: %s", e)
            check = rm.check_trade(symbol=symbol, side="BUY", quantity=quantity,
                                   entry_price=price, stop_loss=sl,
                                   current_positions=current_positions)
            if not check.approved:
                await update.message.reply_text(f"风控拒绝: {check.reason}")
                return
            if check.adjusted_quantity is not None:
                quantity = check.adjusted_quantity
        # 优先走 IBKR 实盘，失败降级模拟
        ibkr_ok = False
        if ibkr.is_connected():
            ibkr_result = await ibkr.buy(symbol, quantity, decided_by=self.name, reason="手动买入")
            if "error" not in ibkr_result:
                ibkr_ok = True
                fill_price = ibkr_result.get("avg_price", 0) or price
                fill_qty = ibkr_result.get("filled_qty", 0) or quantity
                # FIX 5: 零成交不入持仓
                if fill_qty <= 0:
                    await update.message.reply_text(ERR_ORDER_PENDING)
                    _trade_cooldown[dedup_key] = now_ts
                    return
                # 同步更新模拟组合
                portfolio.buy(symbol, fill_qty, fill_price, decided_by=self.name, reason="手动买入(IBKR同步)")
                from src.telegram_ux import format_trade_card
                card = format_trade_card({
                    "symbol": ibkr_result['symbol'],
                    "action": "BUY",
                    "quantity": fill_qty,
                    "price": fill_price,
                    "total": fill_qty * fill_price,
                    "reason": f"IBKR实盘 | {ibkr_result.get('status', 'N/A')} | OID:{ibkr_result.get('order_id', 'N/A')} | {ibkr.get_budget_status()}",
                })
                await update.message.reply_text(card, parse_mode="HTML", reply_to_message_id=update.message.message_id)
            else:
                await update.message.reply_text(ERR_LIVE_UNAVAILABLE)
        if not ibkr_ok:
            result = portfolio.buy(symbol, quantity, price, decided_by=self.name, reason="手动买入")
            if "error" in result:
                await update.message.reply_text(error_service_failed("买入", result.get('error', '')))
            else:
                from src.telegram_ux import format_trade_card
                card = format_trade_card({
                    "symbol": result['symbol'],
                    "action": "BUY",
                    "quantity": result['quantity'],
                    "price": result['price'],
                    "total": result['total'],
                    "remaining_cash": result['remaining_cash'],
                    "reason": "模拟买入",
                })
                await update.message.reply_text(card, parse_mode="HTML", reply_to_message_id=update.message.message_id)
        # FIX 3: 记录冷却时间戳
        _trade_cooldown[dedup_key] = _time.time()

        # 补齐交易闭环: 记录交易日志 + 仓位监控 + 发布 EventBus 事件
        try:
            trade_data = {
                "symbol": symbol, "action": "BUY", "quantity": quantity,
                "price": price, "decided_by": self.name, "reason": "手动买入",
                "ibkr": ibkr_ok,
            }
            # 交易日志
            try:
                from src.trading_journal import journal
                if journal:
                    journal.open_trade(symbol, "BUY", quantity, price, stop_loss=round(price * 0.97, 2))
            except Exception as e:
                logger.debug("交易日志记录失败: %s", e)
            # 仓位监控
            try:
                from src.position_monitor import get_position_monitor
                pm = get_position_monitor()
                if pm:
                    pm.add_position(symbol, quantity, price)
            except Exception as e:
                logger.debug("仓位监控添加失败: %s", e)
            # EventBus 事件 — 触发多渠道通知 + 社媒联动
            try:
                from src.core.event_bus import get_event_bus
                bus = get_event_bus()
                if bus:
                    await bus.publish("trade.executed", trade_data)
            except Exception as e:
                logger.debug("交易事件发布失败: %s", e)
        except Exception as e:
            pass  # 闭环增强不影响主流程
            logger.debug("静默异常: %s", e)

    @requires_auth
    @with_typing
    async def cmd_sell(self, update, context):
        """模拟卖出: /sell AAPL 10 或 /sell AAPL 10 160.5"""
        args = context.args
        if not args or len(args) < 2:
            await update.message.reply_text(
                "用法: `/sell 代码 数量 [价格]`\n"
                "示例: `/sell AAPL 10` (按当前价)\n"
                "示例: `/sell AAPL 10 160.5` (指定价格)",
                parse_mode="Markdown"
            )
            return
        symbol = args[0].upper()
        try:
            quantity = float(args[1])
        except ValueError as e:  # noqa: F841
            await update.message.reply_text("数量必须是数字")
            return
        # FIX 2: 校验正数
        if quantity <= 0:
            await update.message.reply_text(ERR_QTY_POSITIVE)
            return
        if len(args) >= 3:
            try:
                price = float(args[2])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("价格必须是数字")
                return
        else:
            await update.message.reply_text(f"{self.emoji} 获取 {symbol} 当前价格...")
            quote = await get_stock_quote(symbol)
            if "error" in quote:
                await update.message.reply_text(error_service_failed("行情查询", quote.get('error', '')))
                return
            price = quote["price"]

        # FIX 3: 防重复下单冷却
        user_id = update.effective_user.id if update.effective_user else 0
        dedup_key = f"{user_id}:{symbol}"
        now_ts = _time.time()
        last_trade_ts = _trade_cooldown.get(dedup_key, 0)
        if now_ts - last_trade_ts < _TRADE_COOLDOWN_SEC:
            remaining = int(_TRADE_COOLDOWN_SEC - (now_ts - last_trade_ts))
            await update.message.reply_text(f"⚠️ 请勿重复下单，{remaining}秒后可再次交易 {symbol}。")
            return

        # FIX 1 + FIX 6: 风控检查（sell 路径原本完全跳过了风控）
        rm = get_risk_manager()
        if rm is None and ibkr.is_connected():
            await update.message.reply_text(ERR_RISK_NOT_INIT)
            return
        if rm and price > 0:
            # 检查熔断冷却
            if hasattr(rm, 'check_cooldown'):
                cooldown_ok = rm.check_cooldown()
                if not cooldown_ok:
                    await update.message.reply_text("⚠️ 风控熔断中，暂停交易。")
                    return
            # 验证持仓存在且数量合法
            positions = portfolio.get_positions()
            pos = next((p for p in positions if p["symbol"] == symbol), None)
            if pos is None:
                await update.message.reply_text(f"⚠️ 没有 {symbol} 的持仓，无法卖出。")
                return
            if quantity > pos["quantity"]:
                await update.message.reply_text(f"⚠️ 持仓不足: 持有{pos['quantity']}股, 要卖{quantity}股。")
                return

        # 优先走 IBKR 实盘，失败降级模拟
        ibkr_ok = False
        if ibkr.is_connected():
            ibkr_result = await ibkr.sell(symbol, quantity, decided_by=self.name, reason="手动卖出")
            if "error" not in ibkr_result:
                ibkr_ok = True
                fill_price = ibkr_result.get("avg_price", 0) or price
                fill_qty = ibkr_result.get("filled_qty", 0) or quantity
                # FIX 5: 零成交不入持仓
                if fill_qty <= 0:
                    await update.message.reply_text(ERR_ORDER_PENDING)
                    _trade_cooldown[dedup_key] = now_ts
                    return
                # 同步更新模拟组合
                sim_result = portfolio.sell(symbol, fill_qty, fill_price, decided_by=self.name, reason="手动卖出(IBKR同步)")
                profit = sim_result.get("profit", 0) if "error" not in sim_result else 0
                from src.telegram_ux import format_trade_card
                card = format_trade_card({
                    "symbol": ibkr_result['symbol'],
                    "action": "SELL",
                    "quantity": fill_qty,
                    "price": fill_price,
                    "total": fill_qty * fill_price,
                    "profit": profit,
                    "reason": f"IBKR实盘 | {ibkr_result.get('status', 'N/A')} | OID:{ibkr_result.get('order_id', 'N/A')} | {ibkr.get_budget_status()}",
                })
                await update.message.reply_text(card, parse_mode="HTML", reply_to_message_id=update.message.message_id)
            else:
                await update.message.reply_text(ERR_LIVE_UNAVAILABLE)
        if not ibkr_ok:
            result = portfolio.sell(symbol, quantity, price, decided_by=self.name, reason="手动卖出")
            if "error" in result:
                await update.message.reply_text(error_service_failed("卖出", result.get('error', '')))
            else:
                from src.telegram_ux import format_trade_card
                card = format_trade_card({
                    "symbol": result['symbol'],
                    "action": "SELL",
                    "quantity": result['quantity'],
                    "price": result['price'],
                    "total": result['total'],
                    "profit": result['profit'],
                    "remaining_cash": result['remaining_cash'],
                    "reason": "模拟卖出",
                })
                await update.message.reply_text(card, parse_mode="HTML", reply_to_message_id=update.message.message_id)
        # FIX 3: 记录冷却时间戳
        _trade_cooldown[dedup_key] = _time.time()

    @requires_auth
    @with_typing
    async def cmd_watchlist(self, update, context):
        """自选股: /watchlist 或 /watchlist add AAPL 理由"""
        args = context.args
        if args and args[0].lower() == "add" and len(args) >= 2:
            symbol = args[1].upper()
            reason = " ".join(args[2:]) if len(args) > 2 else ""
            result = portfolio.add_watchlist(symbol, added_by=self.name, reason=reason)
            if "error" in result:
                await update.message.reply_text(error_service_failed("自选股", result.get('error', '')))
            else:
                await update.message.reply_text(f"已添加 {symbol} 到自选股")
            return
        items = portfolio.get_watchlist()
        if not items:
            await update.message.reply_text("自选股为空\n\n添加: `/watchlist add AAPL 看好AI概念`", parse_mode="Markdown")
            return
        lines = ["自选股列表\n"]
        for item in items:
            line = f"- {item['symbol']}"
            if item.get("reason"):
                line += f" ({item['reason']})"
            if item.get("added_by"):
                line += f" [来自 {item['added_by']}]"
            lines.append(line)
        await send_long_message(update.effective_chat.id, "\n".join(lines), context, reply_to_message_id=update.message.message_id)

    @requires_auth
    @with_typing
    async def cmd_trades(self, update, context):
        """交易记录: /trades 或 /trades 20"""
        args = context.args
        limit = 10
        if args:
            try:
                limit = int(args[0])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("⚠️ 数量参数无效 '%s'，使用默认值10" % args[0])
        trades = portfolio.get_trades(limit=limit)
        if not trades:
            await update.message.reply_text("暂无交易记录\n\n使用 /buy 或 /sell 开始交易")
            return
        lines = [f"最近 {len(trades)} 笔交易\n"]
        for t in trades:
            action_icon = "买" if t["action"] == "BUY" else "卖"
            lines.append(
                f"{action_icon} {t['symbol']} {t['quantity']}股 @ ${t['price']:.2f}"
                f" (${t['total']:.2f}) {t['executed_at'][:10]}"
            )
        summary = portfolio.get_trade_summary()
        lines.append(f"\n统计: {summary['total_trades']}笔交易 | "
                     f"买{summary['buy_count']}笔 ${summary['total_buy_amount']:,.0f} | "
                     f"卖{summary['sell_count']}笔 ${summary['total_sell_amount']:,.0f} | "
                     f"持仓{summary['open_positions']}只")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context, reply_to_message_id=update.message.message_id)

        # 发送 PnL 柱状图（仅含卖出交易的盈亏）
        sell_trades = [t for t in trades if t["action"] == "SELL"]
        if sell_trades:
            try:
                from src.telegram_ux import generate_pnl_chart, send_chart
                pnl_data = [{"symbol": t["symbol"], "pnl": t["total"]} for t in sell_trades]
                chart = generate_pnl_chart(pnl_data, "卖出交易金额分布")
                await send_chart(update, context, chart)
            except Exception as e:
                logger.debug("PnL chart failed: %s", e)

    @requires_auth
    @with_typing
    async def cmd_export(self, update, context):
        """导出数据为 Excel: /export [trades|watchlist|portfolio|expenses|xianyu] [天数] [csv]"""
        args = context.args or []
        target = args[0].lower() if args else "trades"
        # 检测 csv 格式标记 (可能在任意位置)
        fmt = "xlsx"
        for a in args[1:]:
            if a.lower() == "csv":
                fmt = "csv"
                break

        # 检查 openpyxl 可用性
        from src.tools.export_service import HAS_OPENPYXL
        if fmt == "xlsx" and not HAS_OPENPYXL:
            fmt = "csv"
            await update.message.reply_text("openpyxl 未安装，降级为 CSV 格式")

        await update.message.reply_text(f"{self.emoji} 正在生成导出文件...")

        try:
            if target == "watchlist":
                items = portfolio.get_watchlist()
                if not items:
                    await update.message.reply_text("自选股为空，无法导出")
                    return
                from src.tools.export_service import export_watchlist
                buf = export_watchlist(items, format=fmt)
                filename = f"watchlist.{fmt}"
                caption = f"自选股列表 ({len(items)} 只)"

            elif target == "portfolio":
                positions_raw = portfolio.get_positions()
                cash = portfolio.get_cash()
                if not positions_raw:
                    await update.message.reply_text("投资组合为空，无法导出")
                    return
                # 获取行情计算市值
                import asyncio
                quotes = await asyncio.gather(
                    *[get_stock_quote(p["symbol"]) for p in positions_raw],
                    return_exceptions=True,
                )
                enriched = []
                total_value = cash
                for pos, quote in zip(positions_raw, quotes):
                    if isinstance(quote, Exception) or (isinstance(quote, dict) and "error" in quote):
                        current_price = pos["avg_price"]
                    else:
                        current_price = quote.get("price", pos["avg_price"])
                    market_value = pos["quantity"] * current_price
                    pnl_pct = ((current_price / pos["avg_price"]) - 1) * 100 if pos["avg_price"] else 0
                    total_value += market_value
                    enriched.append({
                        "symbol": pos["symbol"],
                        "quantity": pos["quantity"],
                        "avg_cost": pos["avg_price"],
                        "market_value": market_value,
                        "pnl_pct": pnl_pct,
                    })
                from src.tools.export_service import export_portfolio
                buf = export_portfolio(
                    enriched,
                    summary={"cash": cash, "total_value": total_value},
                    format=fmt,
                )
                filename = f"portfolio.{fmt}"
                caption = f"投资组合 ({len(enriched)} 只持仓)"

            elif target == "expenses":
                # 导出记账数据: /export expenses [天数]
                user_id = update.effective_user.id if update.effective_user else 0
                days = 30
                for a in args[1:]:
                    if a.isdigit():
                        days = int(a)
                        break
                from src.execution.life_automation import get_all_expenses, get_monthly_summary
                expenses = get_all_expenses(user_id, days=days)
                if not expenses:
                    await update.message.reply_text("暂无记账数据，无法导出")
                    return
                # 构建月度汇总数据
                summary_data = None
                try:
                    from datetime import datetime as _dt
                    now = _dt.now()
                    months = []
                    # 获取最近 3 个月的汇总
                    for offset in range(3):
                        month = now.month - offset
                        year = now.year
                        if month <= 0:
                            month += 12
                            year -= 1
                        ym = f"{year}-{month:02d}"
                        ms = get_monthly_summary(user_id, year_month=ym)
                        if ms.get("success") and (ms.get("total_expense", 0) > 0 or ms.get("total_income", 0) > 0):
                            months.append({
                                "month": ym,
                                "total_expense": ms["total_expense"],
                                "total_income": ms["total_income"],
                                "net": ms["net"],
                                "budget": ms.get("budget", 0),
                                "budget_pct": ms.get("budget_pct", 0),
                            })
                    if months:
                        summary_data = {"months": months}
                except Exception as e:
                    pass  # 汇总获取失败不影响明细导出
                    logger.debug("静默异常: %s", e)
                from src.tools.export_service import export_expenses
                buf = export_expenses(expenses, summary=summary_data, format=fmt)
                filename = f"expenses_{days}d.{fmt}"
                caption = f"记账数据 (近{days}天, {len(expenses)} 条)"

            elif target == "xianyu":
                # 导出闲鱼订单: /export xianyu [天数]
                days = 90
                for a in args[1:]:
                    if a.isdigit():
                        days = int(a)
                        break
                try:
                    from src.xianyu.xianyu_context import XianyuContextManager
                    ctx = XianyuContextManager()
                    orders = ctx.get_all_orders(days=days)
                    if not orders:
                        await update.message.reply_text("暂无闲鱼订单，无法导出")
                        return
                    # 获取利润汇总
                    ps = ctx.get_profit_summary(days=days)
                    profit_summary = {
                        "total_orders": ps.get("orders", 0),
                        "total_revenue": ps.get("revenue", 0),
                        "total_cost": ps.get("cost", 0),
                        "total_commission": ps.get("total_commission", 0),
                        "net_profit": ps.get("profit", 0),
                    }
                except ImportError:
                    await update.message.reply_text("闲鱼模块未加载")
                    return
                from src.tools.export_service import export_xianyu_orders
                buf = export_xianyu_orders(orders, profit_summary=profit_summary, format=fmt)
                filename = f"xianyu_orders_{days}d.{fmt}"
                caption = f"闲鱼订单 (近{days}天, {len(orders)} 笔)"

            else:
                # 默认导出交易记录
                limit = 100
                if len(args) >= 2:
                    try:
                        limit = int(args[1])
                    except ValueError as e:  # noqa: F841
                        pass
                trades = portfolio.get_trades(limit=limit)
                if not trades:
                    await update.message.reply_text("暂无交易记录，无法导出")
                    return
                from src.tools.export_service import export_trades
                buf = export_trades(trades, format=fmt)
                filename = f"trades.{fmt}"
                caption = f"交易记录 ({len(trades)} 笔)"

            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=buf,
                filename=filename,
                caption=caption,
                reply_to_message_id=update.message.message_id,
            )

        except Exception as e:
            logger.error("导出失败: %s", e, exc_info=True)
            await update.message.reply_text(
                "❌ 严总，导出失败了，请稍后再试\n\n"
                "用法: `/export [trades|watchlist|portfolio|expenses|xianyu] [天数] [csv]`",
                parse_mode="Markdown",
            )

    async def handle_quote_action_callback(self, update, context):
        """处理行情卡片操作按钮 (ta_, buy_, watch_)"""
        query = update.callback_query
        await query.answer()

        # 认证: 仅授权用户可操作
        if not self._is_authorized(update.effective_user.id):
            await query.answer("⛔ 未授权操作", show_alert=True)
            return

        data = query.data

        if data.startswith("ta_"):
            symbol = data[3:]
            context.args = [symbol]
            await self.cmd_ta(update, context)
        elif data.startswith("buy_"):
            symbol = data[4:]
            await query.message.reply_text(f"💡 请使用命令: /buy {symbol} 数量\n例如: /buy {symbol} 10")
        elif data.startswith("watch_"):
            symbol = data[6:]
            context.args = ["add", symbol]
            await self.cmd_watchlist(update, context)

    @requires_auth
    @with_typing
    async def cmd_reset_portfolio(self, update, context):
        """重置投资组合: /reset_portfolio"""
        args = context.args
        capital = 100000
        if args:
            try:
                capital = float(args[0])
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("⚠️ 资金参数无效 '%s'，使用默认值$100,000" % args[0])
        result = portfolio.reset_portfolio(initial_capital=capital)
        await update.message.reply_text(
            f"投资组合已重置\n\n"
            f"初始资金: ${result['initial_capital']:,.2f}\n"
            f"现金: ${result['cash']:,.2f}\n"
            f"交易记录已清空"
        )
