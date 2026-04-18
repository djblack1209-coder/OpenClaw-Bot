"""
上下文与简单命令 Mixin — /context, /compact, /clear, /voice, /lanes
"""
import logging

from src.bot.globals import history_store, context_manager
from src.telegram_ux import with_typing
from src.bot.auth import requires_auth

logger = logging.getLogger(__name__)


class _ContextMixin:
    """上下文管理与简单开关命令"""

    @requires_auth
    @with_typing
    async def cmd_lanes(self, update, context):
        """查看群聊显式分流标签"""
        try:
            await update.message.reply_text(
                "🏷  群聊分流标签\n"
                "───────────────────\n"
                "发消息时加标签，强制指定回复Bot：\n\n"
                " [RISK] #风控  → 💎 Sonnet（风险闸门）\n"
                " [ALPHA] #研究  → 🧠 Qwen（研究规划）\n"
                " [EXEC] #执行  → 🐉 DeepSeek（执行技术）\n"
                " [FAST] #快问  → ⚡ GPT-OSS（快速答复）\n"
                " [CN] #中文  → 🐉 DeepSeek（中文表达）\n"
                " [BRAIN] #终极  → 👑 Opus（深度推理）\n"
                " [CREATIVE] #创意  → 🚀 Haiku（文案创意）\n\n"
                "示例：[RISK] 今天持仓有没有超风险？\n"
                "提示：@bot 提及优先级高于标签"
            )
        except Exception as e:
            logger.warning("[cmd_lanes] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception:
                pass

    @requires_auth
    async def cmd_clear(self, update, context):
        try:
            chat_id = update.effective_chat.id
            history_store.clear_messages(self.bot_id, chat_id)
            await update.message.reply_text(f"{self.emoji} 对话已清空")
        except Exception as e:
            logger.warning("[cmd_clear] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception:
                pass

    @requires_auth
    async def cmd_voice(self, update, context):
        """切换语音回复模式 — /voice 开启后短回复自动附带语音"""
        try:
            current = context.user_data.get("voice_reply", False)
            context.user_data["voice_reply"] = not current
            status = "开启" if not current else "关闭"
            await update.message.reply_text(f"语音回复已{status}")
        except Exception as e:
            logger.warning("[cmd_voice] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception:
                pass

    @requires_auth
    @with_typing
    async def cmd_context(self, update, context):
        """查看当前上下文状态"""
        try:
            chat_id = update.effective_chat.id
            messages = history_store.get_messages(self.bot_id, chat_id, limit=100)
            status = context_manager.get_context_status(messages)

            pct = status["usage_percent"]
            bar_len = 20
            filled = int(bar_len * pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)

            warning = ""
            if status["must_compress"]:
                warning = "\n⚠️ 上下文即将溢出，建议 /compact 或 /clear"
            elif status["needs_compression"]:
                warning = "\n💡 上下文较大，下次对话将自动压缩"

            await update.message.reply_text(
                f"{self.emoji} **上下文状态**\n\n"
                f"消息数: {status['message_count']}\n"
                f"Token: {status['estimated_tokens']:,} / {status['max_tokens']:,}\n"
                f"使用率: [{bar}] {pct}%\n"
                f"压缩阈值: {status['compress_threshold']:,}\n"
                f"已有摘要: {'是' if status['has_summary'] else '否'}\n"
                f"关键信息: {status['key_facts_count']} 条{warning}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning("[cmd_context] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception:
                pass

    @requires_auth
    @with_typing
    async def cmd_compact(self, update, context):
        """手动压缩上下文"""
        try:
            chat_id = update.effective_chat.id
            messages = history_store.get_messages(self.bot_id, chat_id, limit=100)

            if len(messages) < 6:
                await update.message.reply_text(f"{self.emoji} 对话太短，无需压缩")
                return

            before_tokens = context_manager.estimate_tokens(messages)
            compressed, summary = context_manager.compress_local(messages)
            after_tokens = context_manager.estimate_tokens(compressed)

            context_manager.update_history_store(
                history_store, self.bot_id, chat_id, compressed
            )

            saved_pct = round((1 - after_tokens / before_tokens) * 100) if before_tokens > 0 else 0

            await update.message.reply_text(
                f"{self.emoji} **上下文已压缩**\n\n"
                f"消息: {len(messages)} -> {len(compressed)}\n"
                f"Token: {before_tokens:,} -> {after_tokens:,}\n"
                f"节省: {saved_pct}%\n\n"
                f"关键信息和最近对话已保留。",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning("[cmd_compact] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception:
                pass
