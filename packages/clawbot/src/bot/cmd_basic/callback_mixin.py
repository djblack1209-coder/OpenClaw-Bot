"""
回调处理 Mixin — 通知操作按钮, 卡片操作按钮, 追问按钮
"""
import logging

from src.message_format import format_error

logger = logging.getLogger(__name__)


async def _safe_cmd_from_callback(query, handler, update, context, cmd_name: str):
    """在回调上下文中安全执行 cmd_ 命令函数

    回调上下文中 update.message 为 None，而大部分 cmd_ 函数使用
    update.message.reply_text()，会抛 AttributeError。
    本辅助函数用 try/except 捕获异常，用 query.message 回复错误。
    """
    try:
        await handler(update, context)
    except AttributeError as e:
        if "'NoneType'" in str(e) and "reply" in str(e):
            # update.message 为 None 导致的崩溃 — 用 query.message 回复
            logger.warning("回调调用 /%s 时 update.message 为 None，降级到 query.message 回复", cmd_name)
            try:
                await query.message.reply_text(f"✅ 已执行 /{cmd_name}（回调模式）")
            except Exception as e:
                logger.warning("[Callback] 回调回复失败: %s", e)
        else:
            logger.error("回调执行 /%s 异常: %s", cmd_name, e)
            try:
                await query.message.reply_text(f"⚠️ 执行 /{cmd_name} 时出错，请直接输入命令重试。")
            except Exception as e:
                logger.warning("[Callback] 回调回复失败: %s", e)
    except Exception as e:
        logger.error("回调执行 /%s 异常: %s", cmd_name, e)
        try:
            await query.message.reply_text(format_error(e, f"执行 /{cmd_name}"))
        except Exception as e:
            logger.warning("[Callback] 回调回复失败: %s", e)


class _CallbackMixin:
    """Inline 回调按钮分发处理"""

    async def handle_notify_action_callback(self, update, context):
        """处理交易通知中的 actionable 按钮 — 搬运 freqtrade 的 inline command 模式

        callback_data 格式: cmd:/command [args]
        点击按钮等同于执行对应命令，结果直接回复在通知下方。
        """
        query = update.callback_query
        await query.answer()

        # 认证: 仅授权用户可操作
        if not self._is_authorized(update.effective_user.id):
            await query.answer("⛔ 未授权操作", show_alert=True)
            return

        data = query.data
        if not data.startswith("cmd:"):
            return

        cmd_str = data[4:].strip()  # 去掉 "cmd:" 前缀
        if not cmd_str.startswith("/"):
            cmd_str = "/" + cmd_str  # Normalize: add / prefix if missing

        # 解析命令和参数
        parts = cmd_str.split()
        cmd_name = parts[0][1:]  # 去掉 "/"
        cmd_args = parts[1:]

        # 映射到对应的命令处理函数
        cmd_map = {
            "monitor": self.cmd_monitor,
            "risk": self.cmd_risk,
            "tradingsystem": self.cmd_tradingsystem,
            "brief": self.cmd_brief,
            "status": self.cmd_status,
            "autotrader": self.cmd_autotrader,
            "portfolio": self.cmd_portfolio,
            "cost": self.cmd_cost,
            "help": self.cmd_start,
            "quote": self.cmd_quote,
            "market": self.cmd_market,
            "backtest": self.cmd_backtest,
            "ta": self.cmd_ta,
            # v3.0: 扩展 cmd_map 支持智能行动建议按钮
            "sell": self.cmd_sell,
            "buy": self.cmd_buy,
            "performance": self.cmd_performance,
            "hotpost": self.cmd_hotpost,
            "social_plan": self.cmd_social_plan,
            "signal": self.cmd_signal,
            "journal": self.cmd_journal,
            "review": self.cmd_review,
            "invest": self.cmd_invest,
            "evolve": self.cmd_status,
            "tasks": self.cmd_ops,
            "bill": self.cmd_bill,
            "xianyu": self.cmd_xianyu,
        }

        handler = cmd_map.get(cmd_name)
        if not handler:
            await query.message.reply_text(f"未知命令: /{cmd_name}")
            return

        # 构造 context.args 并执行命令
        context.args = cmd_args
        await _safe_cmd_from_callback(query, handler, update, context, cmd_name)

    async def handle_card_action_callback(self, update, context):
        """处理 OMEGA 响应卡片上的操作按钮（response_cards.py 生成的 callback_data）"""
        query = update.callback_query
        await query.answer()
        data = query.data

        if data.startswith("trade:buy:"):
            symbol = data.split(":")[-1]
            await query.message.reply_text(f"💡 请使用: /buy {symbol} 数量")
        elif data.startswith("trade:size:"):
            symbol = data.split(":")[-1]
            await query.message.reply_text(
                f"💡 调整仓位: /buy {symbol} 数量\n"
                f"例如: /buy {symbol} 100"
            )
        elif data.startswith("bt:"):
            parts = data.split(":")
            symbol = parts[-1] if len(parts) > 2 else ""
            context.args = [symbol] if symbol else []
            await _safe_cmd_from_callback(query, self.cmd_backtest, update, context, "backtest")
        elif data.startswith("ta:detail:") or data.startswith("analyze:"):
            symbol = data.split(":")[-1]
            context.args = [symbol]
            await _safe_cmd_from_callback(query, self.cmd_ta, update, context, "ta")
        elif data.startswith("news:"):
            symbol = data.split(":")[-1]
            context.args = [symbol]
            await _safe_cmd_from_callback(query, self.cmd_news, update, context, "news")
        elif data.startswith("evo:approve:") or data.startswith("evo:reject:"):
            action = "approve" if "approve" in data else "reject"
            pid = data.split(":")[-1]
            await query.message.reply_text(f"📋 进化提案 {pid} 已标记为 {action}")
        elif data.startswith("retry:"):
            await query.message.reply_text("🔄 请重试您之前的操作")
        elif data.startswith("shop:refresh:"):
            product = data.split(":", 2)[-1]
            await query.message.reply_text(f"🔄 正在刷新 {product} 的价格...")
        elif data.startswith("post:"):
            topic = data.split(":", 1)[-1]
            context.args = [topic]
            await _safe_cmd_from_callback(query, self.cmd_post, update, context, "post")
        else:
            await query.message.reply_text("💡 此操作暂不支持")

    async def handle_clarification_callback(self, update, context):
        """处理 ClarificationCard 追问按钮的回调 (callback_data: {tid}:{param}:{value})"""
        query = update.callback_query
        await query.answer()
        data = query.data or ""

        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.message.reply_text("⚠️ 按钮数据格式异常，请重新提问。")
            return

        _tid, param, value = parts[0], parts[1], parts[2]

        # 取消操作
        if param == "cancel":
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("❌ 已取消。")
            return

        # 需要用户手动输入
        if value == "ask":
            await query.message.reply_text(f"请补充「{param}」信息，直接回复即可。")
            return

        # 用按钮值作为追加输入发送回 handle_message
        display = value
        if param and param != value:
            display = f"{param}: {value}"

        await query.message.reply_text(f"✅ 已选择: {display}\n请稍候，正在继续处理...")
