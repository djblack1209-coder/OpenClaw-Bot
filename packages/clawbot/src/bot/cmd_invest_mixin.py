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

logger = logging.getLogger(__name__)


class InvestCommandsMixin:
    """投资相关 Telegram 命令"""

    async def cmd_quote(self, update, context):
        """查询行情: /quote AAPL 或 /quote BTC"""
        if not self._is_authorized(update.effective_user.id):
            return
        args = context.args
        if not args:
            await update.message.reply_text("用法: `/quote AAPL` 或 `/quote BTC`", parse_mode="Markdown")
            return
        symbol = args[0].upper()
        await update.message.reply_text(f"{self.emoji} 查询 {symbol} 行情中...")
        crypto_symbols = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "DOT", "AVAX", "MATIC", "LINK"}
        if symbol in crypto_symbols:
            quote = await get_crypto_quote(symbol)
        else:
            quote = await get_stock_quote(symbol)
        text = format_quote(quote)
        await send_long_message(update.effective_chat.id, text, context, reply_to_message_id=update.message.message_id)

    async def cmd_market(self, update, context):
        """市场概览: /market"""
        if not self._is_authorized(update.effective_user.id):
            return
        await update.message.reply_text(f"{self.emoji} 获取市场概览中（约10秒）...")
        text = await get_market_summary()
        await send_long_message(update.effective_chat.id, text, context, reply_to_message_id=update.message.message_id)

    async def cmd_portfolio(self, update, context):
        """查看投资组合: /portfolio"""
        if not self._is_authorized(update.effective_user.id):
            return
        await update.message.reply_text(f"{self.emoji} 计算投资组合中...")
        text = await portfolio.get_portfolio_summary()
        # 当 IBKR 已连接时，追加实盘持仓
        if ibkr.is_connected():
            try:
                ibkr_text = await ibkr.get_positions_text()
                if ibkr_text.strip():
                    text += "\n\n━━━ IBKR 实盘持仓 ━━━\n" + ibkr_text
                text += "\n" + ibkr.get_budget_status()
            except Exception as e:
                text += f"\n\n(IBKR持仓获取失败: {e})"
        await send_long_message(update.effective_chat.id, text, context, reply_to_message_id=update.message.message_id)

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
                text = (
                    f"IBKR 买入成功\n\n"
                    f"标的: {ibkr_result['symbol']}\n"
                    f"数量: {fill_qty}\n"
                    f"成交价: ${fill_price:.2f}\n"
                    f"订单状态: {ibkr_result.get('status', 'N/A')}\n"
                    f"Order ID: {ibkr_result.get('order_id', 'N/A')}\n"
                    f"预算剩余: {ibkr.get_budget_status()}"
                )
                await send_long_message(update.effective_chat.id, text, context, reply_to_message_id=update.message.message_id)
            else:
                await update.message.reply_text(f"IBKR下单失败: {ibkr_result['error']}\n降级到模拟组合...")
        if not ibkr_ok:
            result = portfolio.buy(symbol, quantity, price, decided_by=self.name, reason="手动买入")
            if "error" in result:
                await update.message.reply_text(f"买入失败: {result['error']}")
            else:
                text = (
                    f"模拟买入成功\n\n"
                    f"标的: {result['symbol']}\n"
                    f"数量: {result['quantity']}\n"
                    f"价格: ${result['price']:.2f}\n"
                    f"总额: ${result['total']:.2f}\n"
                    f"剩余现金: ${result['remaining_cash']:,.2f}"
                )
                await send_long_message(update.effective_chat.id, text, context, reply_to_message_id=update.message.message_id)

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
                sign = "+" if profit >= 0 else ""
                text = (
                    f"IBKR 卖出成功\n\n"
                    f"标的: {ibkr_result['symbol']}\n"
                    f"数量: {fill_qty}\n"
                    f"成交价: ${fill_price:.2f}\n"
                    f"订单状态: {ibkr_result.get('status', 'N/A')}\n"
                    f"Order ID: {ibkr_result.get('order_id', 'N/A')}\n"
                    f"模拟盈亏: {sign}${profit:.2f}\n"
                    f"预算剩余: {ibkr.get_budget_status()}"
                )
                await send_long_message(update.effective_chat.id, text, context, reply_to_message_id=update.message.message_id)
            else:
                await update.message.reply_text(f"IBKR下单失败: {ibkr_result['error']}\n降级到模拟组合...")
        if not ibkr_ok:
            result = portfolio.sell(symbol, quantity, price, decided_by=self.name, reason="手动卖出")
            if "error" in result:
                await update.message.reply_text(f"卖出失败: {result['error']}")
            else:
                sign = "+" if result['profit'] >= 0 else ""
                text = (
                    f"模拟卖出成功\n\n"
                    f"标的: {result['symbol']}\n"
                    f"数量: {result['quantity']}\n"
                    f"价格: ${result['price']:.2f}\n"
                    f"总额: ${result['total']:.2f}\n"
                    f"盈亏: {sign}${result['profit']:.2f}\n"
                    f"剩余现金: ${result['remaining_cash']:,.2f}"
                )
                await send_long_message(update.effective_chat.id, text, context, reply_to_message_id=update.message.message_id)

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
