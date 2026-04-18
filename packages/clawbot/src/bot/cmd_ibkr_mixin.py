"""
IBKR 实盘命令 Mixin — 从 multi_main.py L1488-L1649 提取
/ibuy, /isell, /ipositions, /iorders, /iaccount, /icancel
"""
import logging

from src.trading_journal import TradingJournal
from src.bot.auth import requires_auth
from src.bot.error_messages import error_service_failed
from src.constants import ERR_LIMIT_PRICE_INVALID
from src.telegram_ux import with_typing
from src.bot.globals import (
    get_stock_quote,
    send_long_message,
)
# 幻影导入修复: ibkr/get_risk_manager 从实际定义模块导入
from src.broker_selector import ibkr
from src.trading._lifecycle import get_risk_manager

logger = logging.getLogger(__name__)


class IBKRCommandsMixin:
    """IBKR 实盘交易命令"""

    @requires_auth
    @with_typing
    async def cmd_ibuy(self, update, context):
        """IBKR买入: /ibuy AAPL 5 或 /ibuy AAPL 5 150.5"""
        args = context.args
        if not args or len(args) < 2:
            await update.message.reply_text(
                "IBKR买入（真实模拟账户下单）\n\n"
                "用法: /ibuy 代码 数量 [限价]\n"
                "示例: /ibuy AAPL 5 (市价)\n"
                "示例: /ibuy AAPL 5 150.5 (限价)\n\n"
                "预算: $2000"
            )
            return
        symbol = args[0].upper()
        try:
            qty = float(args[1])
        except ValueError as e:  # noqa: F841
            await update.message.reply_text("数量必须是数字")
            return
        limit_price = 0
        order_type = 'MKT'
        if len(args) >= 3:
            try:
                limit_price = float(args[2])
                order_type = 'LMT'
            except ValueError as e:
                await update.message.reply_text(ERR_LIMIT_PRICE_INVALID.format(price=args[2]))
                logger.warning("[IBKR] BUY限价解析失败: '%s'，回退为市价单", args[2])
        await update.message.reply_text(
            "%s IBKR下单中: BUY %s x%.0f %s..." % (
                self.emoji, symbol, qty,
                ("限价$%.2f" % limit_price) if order_type == 'LMT' else "市价"))
        rm = get_risk_manager()
        if rm:
            quote = await get_stock_quote(symbol)
            ep = quote.get("price", 0) if isinstance(quote, dict) else 0
            if ep > 0:
                sl = round(ep * 0.97, 2)
                check = rm.check_trade(symbol=symbol, side="BUY", quantity=qty,
                                       entry_price=ep, stop_loss=sl)
                if not check.approved:
                    await update.message.reply_text("风控拒绝: %s" % check.reason)
                    return
                if check.adjusted_quantity is not None:
                    qty = check.adjusted_quantity
        result = await ibkr.buy(symbol, qty, order_type, limit_price,
                                decided_by=self.name, reason="Telegram手动下单")
        if "error" in result:
            await update.message.reply_text(error_service_failed("IBKR买入"))
        else:
            price_info = "$%.2f" % result["avg_price"] if result["avg_price"] > 0 else "待成交"
            text = (
                "IBKR 买入订单\n\n"
                "标的: %s\n数量: %.0f\n类型: %s\n状态: %s\n成交: %s @ %s\n订单号: #%s\n\n%s"
            ) % (result["symbol"], result["quantity"],
                 "市价" if order_type == 'MKT' else "限价$%.2f" % limit_price,
                 result["status"], result["filled_qty"], price_info,
                 result["order_id"], ibkr.get_budget_status())
            await send_long_message(update.effective_chat.id, text, context,
                                    reply_to_message_id=update.message.message_id)
            # HI-575: 手动交易也记录到 journal，确保交易历史完整
            try:
                journal = TradingJournal()
                journal.open_trade(
                    symbol=result["symbol"],
                    side="BUY",
                    quantity=result["quantity"],
                    entry_price=result["avg_price"] if result["avg_price"] > 0 else limit_price,
                    decided_by=self.name,
                    entry_reason="Telegram手动下单 /ibuy",
                    entry_order_id=str(result["order_id"]),
                )
            except Exception as e:
                logger.warning("[IBKR] 手动交易记录失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_isell(self, update, context):
        """IBKR卖出: /isell AAPL 5"""
        args = context.args
        if not args or len(args) < 2:
            await update.message.reply_text(
                "IBKR卖出（真实模拟账户下单）\n\n"
                "用法: /isell 代码 数量 [限价]\n"
                "示例: /isell AAPL 5 (市价)\n"
                "示例: /isell AAPL 5 160.5 (限价)"
            )
            return
        symbol = args[0].upper()
        try:
            qty = float(args[1])
        except ValueError as e:  # noqa: F841
            await update.message.reply_text("数量必须是数字")
            return
        limit_price = 0
        order_type = 'MKT'
        if len(args) >= 3:
            try:
                limit_price = float(args[2])
                order_type = 'LMT'
            except ValueError as e:
                await update.message.reply_text(ERR_LIMIT_PRICE_INVALID.format(price=args[2]))
                logger.warning("[IBKR] SELL限价解析失败: '%s'，回退为市价单", args[2])
        await update.message.reply_text(
            "%s IBKR下单中: SELL %s x%.0f..." % (self.emoji, symbol, qty))
        result = await ibkr.sell(symbol, qty, order_type, limit_price,
                                 decided_by=self.name, reason="Telegram手动下单")
        if "error" in result:
            await update.message.reply_text(error_service_failed("IBKR卖出"))
        else:
            price_info = "$%.2f" % result["avg_price"] if result["avg_price"] > 0 else "待成交"
            text = (
                "IBKR 卖出订单\n\n"
                "标的: %s\n数量: %.0f\n状态: %s\n成交: %s @ %s\n订单号: #%s"
            ) % (result["symbol"], result["quantity"],
                 result["status"], result["filled_qty"], price_info,
                 result["order_id"])
            await send_long_message(update.effective_chat.id, text, context,
                                    reply_to_message_id=update.message.message_id)
            # HI-575: 手动卖出也记录到 journal
            try:
                journal = TradingJournal()
                journal.open_trade(
                    symbol=result["symbol"],
                    side="SELL",
                    quantity=result["quantity"],
                    entry_price=result["avg_price"] if result["avg_price"] > 0 else limit_price,
                    decided_by=self.name,
                    entry_reason="Telegram手动下单 /isell",
                    entry_order_id=str(result["order_id"]),
                )
            except Exception as e:
                logger.warning("[IBKR] 手动交易记录失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_ipositions(self, update, context):
        await update.message.reply_text("%s 查询IBKR持仓..." % self.emoji)
        text = await ibkr.get_positions_text()
        await send_long_message(update.effective_chat.id, text, context,
                                reply_to_message_id=update.message.message_id)

    @requires_auth
    @with_typing
    async def cmd_iorders(self, update, context):
        text = await ibkr.get_orders_text()
        await send_long_message(update.effective_chat.id, text, context,
                                reply_to_message_id=update.message.message_id)

    @requires_auth
    @with_typing
    async def cmd_iaccount(self, update, context):
        await update.message.reply_text("%s 查询IBKR账户..." % self.emoji)
        text = await ibkr.get_account_value()
        text += "\n\n" + ibkr.get_budget_status()
        await send_long_message(update.effective_chat.id, text, context,
                                reply_to_message_id=update.message.message_id)

    @requires_auth
    @with_typing
    async def cmd_icancel(self, update, context):
        args = context.args
        if args:
            try:
                order_id = int(args[0])
                result = await ibkr.cancel_order(order_id)
            except ValueError as e:  # noqa: F841
                await update.message.reply_text("订单号必须是数字")
                return
        else:
            result = await ibkr.cancel_all_orders()
        if "error" in result:
            await update.message.reply_text(error_service_failed("IBKR取消订单"))
        else:
            await update.message.reply_text("订单已取消")
