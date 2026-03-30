"""
Bot — 回调处理 Mixin
包含 Telegram 回调按钮和内联命令的处理方法。
从 message_mixin.py 拆分以改善可维护性。

> 最后更新: 2026-03-29
"""
import logging

from src.bot.globals import (
    send_long_message,
    get_trading_pipeline,
    execute_trade_via_pipeline,
    get_stock_quote,
)
from src.bot.message_mixin import _build_smart_reply_keyboard

logger = logging.getLogger(__name__)


class CallbackMixin:
    """回调处理 Mixin — Telegram 按钮和交易回调"""

    async def _cmd_smart_shop(self, update, context, product=""):
        """自然语言购物比价: 用户说"帮我找便宜的AirPods" → 多平台比价

        三级降级: Tavily (实时搜索) → crawl4ai (JD/SMZDM) → Jina+LLM → 纯LLM
        """
        if not product:
            await update.message.reply_text("请告诉我你想买什么，例如: 帮我找便宜的AirPods Pro")
            return

        await update.message.reply_text(f"🔍 正在为你搜索「{product}」的最佳价格...\n多平台比价中，请稍候...")

        try:
            # 尝试 Brain 的智能购物 (三级降级链)
            from src.core.brain import OmegaBrain
            brain = OmegaBrain()
            result = await brain._exec_smart_shopping({"product": product})
            if result and result.get("success") and result.get("data"):
                data = result["data"]
                # 格式化输出
                lines = [f"🛒 <b>{product} 比价结果</b>\n"]
                products = data.get("products", [])
                if products:
                    for i, p in enumerate(products[:8], 1):
                        name = p.get("name", p.get("title", ""))[:40]
                        price = p.get("price", "N/A")
                        platform = p.get("platform", p.get("source", ""))
                        url = p.get("url", "")
                        line = f"{i}. <b>{name}</b>"
                        if price:
                            line += f" — ¥{price}"
                        if platform:
                            line += f" ({platform})"
                        lines.append(line)
                        if url:
                            lines.append(f"   🔗 <a href='{url}'>链接</a>")

                best = data.get("best_deal") or data.get("recommendation", "")
                if best:
                    lines.append(f"\n💡 <b>推荐:</b> {best}")

                tips = data.get("tips", [])
                if tips:
                    lines.append("\n📌 <b>省钱技巧:</b>")
                    for tip in tips[:3]:
                        lines.append(f"  • {tip}")

                msg = "\n".join(lines)
                await send_long_message(update.effective_chat.id, msg, parse_mode="HTML",
                                       context=context)
                return

            # 降级到纯文本
            summary = result.get("data", {}).get("raw", "") if result else ""
            if summary:
                await send_long_message(update.effective_chat.id,
                                       f"🛒 <b>{product} 比价</b>\n\n{summary}",
                                       parse_mode="HTML", context=context)
                return

        except Exception as e:
            logger.warning("[SmartShop] Brain 购物失败, 降级到 LLM: %s", e)

        # 最终降级: 让当前 Bot 的 LLM 回答
        prompt = (
            f"用户想买「{product}」，请帮忙做一个简洁的多平台价格对比。"
            f"包括京东、淘宝、拼多多等主流平台的价格范围和购买建议。"
            f"如果有优惠券或促销活动也请提及。"
        )
        context.args = []
        # 走标准 LLM 流式响应
        async for content, status in self._call_api_stream(
            update.effective_chat.id, prompt, save_history=False
        ):
            if status == "done" and content:
                await send_long_message(update.effective_chat.id, content, context=context)
                return

    async def handle_suggest_callback(self, update, context):
        """处理智能追问建议按钮点击 — 将建议文本当作用户消息重新处理

        callback_data 格式: suggest:{建议文本}
        用户点击后，等同于直接发送该建议文本给 Bot。
        搬运灵感: ChatGPT Suggested Replies / Google Gemini Quick Actions
        """
        query = update.callback_query
        await query.answer()

        # 认证检查
        if not self._is_authorized(update.effective_user.id):
            await query.answer("⛔ 未授权操作", show_alert=True)
            return

        data = query.data
        if not data.startswith("suggest:"):
            return

        # 提取建议文本
        suggest_text = data[8:].strip()  # 去掉 "suggest:" 前缀
        if not suggest_text:
            return

        chat_id = update.effective_chat.id

        try:
            # 显示正在处理的提示
            await query.edit_message_reply_markup(reply_markup=None)

            # 将建议文本路由到 Brain 处理（与正常消息相同路径）
            from src.core.brain import get_brain
            brain = get_brain()
            result = await brain.process_message(
                source="telegram",
                message=suggest_text,
                context={
                    "user_id": update.effective_user.id,
                    "chat_id": chat_id,
                    "bot_id": self.bot_id,
                },
            )

            if result.success and result.final_result:
                user_msg = result.to_user_message()
                if user_msg:
                    # 提取追问建议（如果有）
                    _suggestions = result.extra_data.get("followup_suggestions", [])
                    reply_markup = None
                    try:
                        reply_markup = _build_smart_reply_keyboard(
                            user_msg, self.bot_id,
                            getattr(self, 'model', ''), chat_id,
                            ai_suggestions=_suggestions,
                        )
                    except Exception as e:
                        logger.debug("静默异常: %s", e)

                    try:
                        from src.telegram_markdown import md_to_html
                        safe = md_to_html(user_msg)
                        await query.message.reply_text(
                            safe, parse_mode="HTML",
                            reply_markup=reply_markup,
                        )
                    except Exception as e:  # noqa: F841
                        await query.message.reply_text(
                            user_msg, reply_markup=reply_markup,
                        )
                    return

            # Brain 未能处理 → 降级: 当作普通文本消息重新走流式路径
            # 伪造文本消息让 handle_message 处理
            await query.message.reply_text(f"🔍 正在处理「{suggest_text}」...")
            update.message = query.message
            update.message.text = suggest_text
            await self.handle_message(update, context)

        except Exception as e:
            logger.debug(f"处理追问建议按钮失败: {e}")
            try:
                await query.message.reply_text(f"❌ 处理失败，请直接发送: {suggest_text}")
            except Exception as e:
                logger.debug("静默异常: %s", e)

    async def handle_trade_callback(self, update, context):
        '''处理投资分析会议后的一键下单按钮回调
        callback_data 格式:
          itrade:{trade_key}:{idx}     — 执行单笔交易
          itrade_all:{trade_key}       — 执行全部交易
          itrade_cancel:{trade_key}    — 取消全部
        '''
        from src.bot.globals import _pending_trades
        from src.broker_selector import ibkr

        query = update.callback_query
        await query.answer()

        # 认证: 仅授权用户可操作
        if not self._is_authorized(update.effective_user.id):
            await query.answer("⛔ 未授权操作", show_alert=True)
            return

        data = query.data

        if data.startswith("itrade_cancel:"):
            trade_key = data.split(":")[1]
            _pending_trades.pop(trade_key, None)
            await query.edit_message_text("❌ 已取消全部交易。")
            return

        if data.startswith("itrade_all:"):
            trade_key = data.split(":")[1]
            pending = _pending_trades.pop(trade_key, None)
            if not pending:
                await query.edit_message_text("⚠️ 交易已过期，请重新执行 /invest")
                return
            trades = pending.get("trades", [])
            results = []
            pipeline = get_trading_pipeline()
            for t in trades:
                try:
                    if pipeline:
                        res = await execute_trade_via_pipeline(
                            t, pipeline=pipeline, get_quote_func=get_stock_quote,
                        )
                        if res.startswith("[OK]"):
                            emoji = "✅"
                        elif res.startswith("[RISK REJECTED]"):
                            emoji = "🛡️"
                        elif res.startswith("[SKIP]"):
                            emoji = "⏭️"
                        else:
                            emoji = "❌"
                        results.append(f"{emoji} {res}")
                    else:
                        # Fallback: pipeline not initialized, use direct broker
                        # FIX 4: ibkr has no place_order(); use buy()/sell()
                        if t["action"].upper() == "BUY":
                            ret = await ibkr.buy(t["symbol"], t["qty"], decided_by="itrade_fallback", reason="itrade确认")
                        else:
                            ret = await ibkr.sell(t["symbol"], t["qty"], decided_by="itrade_fallback", reason="itrade确认")
                        emoji = "✅" if "error" not in ret else "❌"
                        results.append(f"{emoji} {t['action']} {t['symbol']} x{t['qty']}: {ret.get('message', ret.get('error', 'OK'))}")
                except Exception as e:
                    results.append(f"❌ {t['symbol']}: {e}")
            await query.edit_message_text("📋 执行结果:\n\n" + "\n".join(results))
            return

        if data.startswith("itrade:"):
            parts = data.split(":")
            if len(parts) < 3:
                return
            trade_key = parts[1]
            idx = int(parts[2])
            pending = _pending_trades.get(trade_key)
            if not pending:
                await query.edit_message_text("⚠️ 交易已过期，请重新执行 /invest")
                return
            trades = pending.get("trades", [])
            if idx >= len(trades):
                return
            t = trades[idx]
            try:
                pipeline = get_trading_pipeline()
                if pipeline:
                    res = await execute_trade_via_pipeline(
                        t, pipeline=pipeline, get_quote_func=get_stock_quote,
                    )
                    if res.startswith("[OK]"):
                        emoji = "✅"
                    elif res.startswith("[RISK REJECTED]"):
                        emoji = "🛡️"
                    elif res.startswith("[SKIP]"):
                        emoji = "⏭️"
                    else:
                        emoji = "❌"
                    await query.message.reply_text(f"{emoji} {res}")
                else:
                    # Fallback: pipeline not initialized, use direct broker
                    # FIX 4: ibkr has no place_order(); use buy()/sell()
                    if t["action"].upper() == "BUY":
                        ret = await ibkr.buy(t["symbol"], t["qty"], decided_by="itrade_fallback", reason="itrade确认")
                    else:
                        ret = await ibkr.sell(t["symbol"], t["qty"], decided_by="itrade_fallback", reason="itrade确认")
                    emoji = "✅" if "error" not in ret else "❌"
                    await query.message.reply_text(
                        f"{emoji} {t['action']} {t['symbol']} x{t['qty']}: {ret.get('message', ret.get('error', 'OK'))}")
            except Exception as e:
                await query.message.reply_text(f"❌ {t['symbol']} 执行失败: {e}")

