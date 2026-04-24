"""
记忆管理 Mixin — /memory, 记忆分页/清除回调, 反馈回调
"""
import logging

from src.bot.auth import requires_auth
from src.telegram_ux import with_typing

logger = logging.getLogger(__name__)


class _MemoryMixin:
    """用户记忆管理与反馈处理"""

    # ── /memory 命令 — 搬运自 mem0 的用户记忆管理 + karfly 的分页模式 ──

    MEMORIES_PER_PAGE = 5

    @requires_auth
    @with_typing
    async def cmd_memory(self, update, context):
        """查看/管理 Bot 记住的关于你的信息"""
        try:
            return await self._cmd_memory_inner(update, context)
        except Exception as e:
            logger.exception("[Memory] 命令执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 记忆管理操作失败，请稍后重试")
            except Exception as e:
                logger.warning("[Memory] 记忆命令回复失败: %s", e)

    async def _cmd_memory_inner(self, update, context):
        """记忆管理 — 内部实现"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode

        from src.smart_memory import get_smart_memory

        user_id = update.effective_user.id
        sm = get_smart_memory()
        if not sm:
            await update.message.reply_text("记忆系统未启用")
            return

        # 获取用户相关记忆
        search_result = sm.memory.search(f"auto_{user_id}", limit=50)
        results = search_result.get("results", []) if isinstance(search_result, dict) else []

        # 也获取用户画像
        profile = sm.get_user_profile(user_id)

        if not results and not profile:
            await update.message.reply_text(
                "📭 还没有记住关于你的任何信息。\n"
                "和我聊天后，我会自动记住重要的事情。"
            )
            return

        text = "🧠 <b>我记住的关于你的信息</b>\n\n"

        if profile:
            text += "<b>用户画像:</b>\n"
            if profile.get("summary"):
                text += f"  {profile['summary']}\n"
            if profile.get("interests"):
                text += f"  兴趣: {', '.join(profile['interests'][:5])}\n"
            text += "\n"

        if results:
            text += f"<b>记忆 ({len(results)} 条):</b>\n\n"
            for i, mem in enumerate(results[:self.MEMORIES_PER_PAGE], 1):
                val = mem.get("value", "")[:100]
                text += f"{i}. {val}\n\n"

        keyboard = []
        if len(results) > self.MEMORIES_PER_PAGE:
            keyboard.append([InlineKeyboardButton("下一页 »", callback_data=f"mem_page|{user_id}|1")])
        keyboard.append([
            InlineKeyboardButton("🗑 清除所有记忆", callback_data=f"mem_clear|{user_id}"),
        ])

        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        )

    async def handle_feedback_callback(self, update, context):
        """处理 反馈按钮 — 搬运自 karfly 的 callback 模式"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        from src.feedback import get_feedback_store, parse_feedback_data
        from src.litellm_router import adaptive_router

        query = update.callback_query
        await query.answer()  # 立即响应，消除加载动画（karfly 关键模式）

        data = parse_feedback_data(query.data)
        if not data:
            return

        user_id = query.from_user.id
        action = data["action"]
        model = data["model"]
        bot_id = data["bot_id"]

        if action == "retry":
            # 移除按钮，提示重新生成
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("🔄 请重新发送你的问题")
            return

        # 记录反馈
        rating = 1 if action == "up" else -1
        store = get_feedback_store()
        store.record(user_id, data["chat_id"], bot_id, model, rating)

        # 联动 AdaptiveRouter 质量评分（闭环）
        if adaptive_router:
            quality = 0.8 if rating > 0 else 0.2
            adaptive_router.record_result(model, "general", success=True, quality=quality)

        # 替换按钮为确认（karfly 模式）
        emoji = "👍" if action == "up" else "👎"
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"{emoji} 已收到反馈", callback_data="noop")
            ]])
        )

    async def handle_memory_callback(self, update, context):
        """处理记忆管理的分页/删除回调"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode

        from src.smart_memory import get_smart_memory

        query = update.callback_query
        await query.answer()

        parts = query.data.split("|")
        action = parts[0]

        if action == "mem_clear":
            user_id = int(parts[1])
            # 安全校验: 只允许操作自己的记忆，防止跨用户删除
            if query.from_user.id != user_id:
                logger.warning("跨用户记忆操作被拒绝: from=%s target=%s", query.from_user.id, user_id)
                return
            sm = get_smart_memory()
            if sm:
                # 删除该用户的所有自动记忆
                search_result = sm.memory.search(f"auto_{user_id}", limit=100)
                results = search_result.get("results", []) if isinstance(search_result, dict) else []
                for mem in results:
                    key = mem.get("key", "")
                    if key:
                        sm.memory.forget(key)
                # 也删除画像
                sm.memory.forget(f"user_profile_{user_id}")
            await query.edit_message_text("✅ 所有记忆已清除。")

        elif action == "mem_page":
            user_id = int(parts[1])
            # 安全校验: 只允许查看自己的记忆
            if query.from_user.id != user_id:
                return
            page = int(parts[2])
            sm = get_smart_memory()
            if not sm:
                return

            search_result = sm.memory.search(f"auto_{user_id}", limit=50)
            results = search_result.get("results", []) if isinstance(search_result, dict) else []

            start = page * self.MEMORIES_PER_PAGE
            end = min(start + self.MEMORIES_PER_PAGE, len(results))
            page_items = results[start:end]

            text = f"🧠 <b>记忆 ({len(results)} 条) - 第 {page + 1} 页</b>\n\n"
            for i, mem in enumerate(page_items, start=start + 1):
                val = mem.get("value", "")[:100]
                text += f"{i}. {val}\n\n"

            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("« 上一页", callback_data=f"mem_page|{user_id}|{page - 1}"))
            if end < len(results):
                nav.append(InlineKeyboardButton("下一页 »", callback_data=f"mem_page|{user_id}|{page + 1}"))
            keyboard = [nav] if nav else []
            keyboard.append([InlineKeyboardButton("🗑 清除所有", callback_data=f"mem_clear|{user_id}")])

            try:
                await query.edit_message_text(
                    text, parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            except Exception:
                logger.debug("Silenced exception", exc_info=True)
