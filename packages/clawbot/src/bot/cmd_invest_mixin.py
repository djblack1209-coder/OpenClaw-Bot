"""
投资命令 Mixin — 从 multi_main.py L1037-L1255 提取
/quote, /market, /portfolio, /buy, /sell, /watchlist, /trades, /reset_portfolio
"""
import logging

from src.bot.globals import (
    get_stock_quote, get_crypto_quote, get_market_summary,
    format_quote, portfolio, send_long_message,
    get_risk_manager, ibkr,
)
from src.message_format import format_error

logger = logging.getLogger(__name__)


class InvestCommandsMixin:
    """投资相关 Telegram 命令"""

    async def cmd_quote(self, update, context):
        """查询行情: /quote AAPL 或 /quote BTC — 富卡片格式 + 错误恢复"""
        if not self._is_authorized(update.effective_user.id):
            return
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

    async def cmd_market(self, update, context):
        """市场概览: /market"""
        if not self._is_authorized(update.effective_user.id):
            return
        await update.message.reply_text(f"{self.emoji} 获取市场概览中（约10秒）...")
        try:
            text = await get_market_summary()
            await send_long_message(update.effective_chat.id, text, context, reply_to_message_id=update.message.message_id)
        except Exception as e:
            from src.telegram_ux import send_error_with_retry
            await send_error_with_retry(update, context, e, retry_command="/market")

    async def cmd_portfolio(self, update, context):
        """查看投资组合: /portfolio"""
        if not self._is_authorized(update.effective_user.id):
            return
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
            # 发送饼图
            try:
                chart = generate_portfolio_pie(enriched, "资产配置")
                await send_chart(update, context, chart, caption="")
            except Exception as e:
                logger.debug("Portfolio pie chart failed: %s", e)
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
                    ibkr_msg = "━━━ IBKR 实盘持仓 ━━━\n" + ibkr_text
                    ibkr_msg += "\n" + ibkr.get_budget_status()
                    await update.message.reply_text(ibkr_msg,
                                                    reply_to_message_id=update.message.message_id)
            except Exception as e:
                await update.message.reply_text(format_error(e, "获取IBKR持仓"),
                                                reply_to_message_id=update.message.message_id)

    async def cmd_buy(self, update, context):
        """模拟买入: /buy AAPL 10 或 /buy AAPL 10 150.5"""
        if not self._is_authorized(update.effective_user.id):
            return
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
        except ValueError:
            await update.message.reply_text("数量必须是数字")
            return
        if len(args) >= 3:
            try:
                price = float(args[2])
            except ValueError:
                await update.message.reply_text("价格必须是数字")
                return
        else:
            await update.message.reply_text(f"{self.emoji} 获取 {symbol} 当前价格...")
            quote = await get_stock_quote(symbol)
            if "error" in quote:
                await update.message.reply_text(f"获取价格失败: {quote['error']}")
                return
            price = quote["price"]
        # 风控检查
        rm = get_risk_manager()
        if rm and price > 0:
            sl = round(price * 0.97, 2)
            check = rm.check_trade(symbol=symbol, side="BUY", quantity=quantity,
                                   entry_price=price, stop_loss=sl)
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
                await update.message.reply_text(f"IBKR下单失败: {ibkr_result['error']}\n降级到模拟组合...")
        if not ibkr_ok:
            result = portfolio.buy(symbol, quantity, price, decided_by=self.name, reason="手动买入")
            if "error" in result:
                await update.message.reply_text(f"买入失败: {result['error']}")
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

    async def cmd_sell(self, update, context):
        """模拟卖出: /sell AAPL 10 或 /sell AAPL 10 160.5"""
        if not self._is_authorized(update.effective_user.id):
            return
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
        except ValueError:
            await update.message.reply_text("数量必须是数字")
            return
        if len(args) >= 3:
            try:
                price = float(args[2])
            except ValueError:
                await update.message.reply_text("价格必须是数字")
                return
        else:
            await update.message.reply_text(f"{self.emoji} 获取 {symbol} 当前价格...")
            quote = await get_stock_quote(symbol)
            if "error" in quote:
                await update.message.reply_text(f"获取价格失败: {quote['error']}")
                return
            price = quote["price"]
        # 优先走 IBKR 实盘，失败降级模拟
        ibkr_ok = False
        if ibkr.is_connected():
            ibkr_result = await ibkr.sell(symbol, quantity, decided_by=self.name, reason="手动卖出")
            if "error" not in ibkr_result:
                ibkr_ok = True
                fill_price = ibkr_result.get("avg_price", 0) or price
                fill_qty = ibkr_result.get("filled_qty", 0) or quantity
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
                await update.message.reply_text(f"IBKR下单失败: {ibkr_result['error']}\n降级到模拟组合...")
        if not ibkr_ok:
            result = portfolio.sell(symbol, quantity, price, decided_by=self.name, reason="手动卖出")
            if "error" in result:
                await update.message.reply_text(f"卖出失败: {result['error']}")
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

    async def cmd_watchlist(self, update, context):
        """自选股: /watchlist 或 /watchlist add AAPL 理由"""
        if not self._is_authorized(update.effective_user.id):
            return
        args = context.args
        if args and args[0].lower() == "add" and len(args) >= 2:
            symbol = args[1].upper()
            reason = " ".join(args[2:]) if len(args) > 2 else ""
            result = portfolio.add_watchlist(symbol, added_by=self.name, reason=reason)
            if "error" in result:
                await update.message.reply_text(f"添加失败: {result['error']}")
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
                line += f" [by {item['added_by']}]"
            lines.append(line)
        await send_long_message(update.effective_chat.id, "\n".join(lines), context, reply_to_message_id=update.message.message_id)

    async def cmd_trades(self, update, context):
        """交易记录: /trades 或 /trades 20"""
        if not self._is_authorized(update.effective_user.id):
            return
        args = context.args
        limit = 10
        if args:
            try:
                limit = int(args[0])
            except ValueError:
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

    async def cmd_export(self, update, context):
        """导出交易数据为 Excel: /export [trades|watchlist|portfolio] [csv]"""
        if not self._is_authorized(update.effective_user.id):
            return

        args = context.args or []
        target = args[0].lower() if args else "trades"
        fmt = "csv" if (len(args) >= 2 and args[1].lower() == "csv") else "xlsx"

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

            else:
                # 默认导出交易记录
                limit = 100
                if len(args) >= 2:
                    try:
                        limit = int(args[1])
                    except ValueError:
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
                f"导出失败: {e}\n\n"
                "用法: `/export [trades|watchlist|portfolio] [csv]`",
                parse_mode="Markdown",
            )

    async def handle_quote_action_callback(self, update, context):
        """处理行情卡片操作按钮 (ta_, buy_, watch_)"""
        query = update.callback_query
        await query.answer()
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

    async def cmd_reset_portfolio(self, update, context):
        """重置投资组合: /reset_portfolio"""
        if not self._is_authorized(update.effective_user.id):
            return
        args = context.args
        capital = 100000
        if args:
            try:
                capital = float(args[0])
            except ValueError:
                await update.message.reply_text("⚠️ 资金参数无效 '%s'，使用默认值$100,000" % args[0])
        result = portfolio.reset_portfolio(initial_capital=capital)
        await update.message.reply_text(
            f"投资组合已重置\n\n"
            f"初始资金: ${result['initial_capital']:,.2f}\n"
            f"现金: ${result['cash']:,.2f}\n"
            f"交易记录已清空"
        )
