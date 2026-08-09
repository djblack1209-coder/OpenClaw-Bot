"""JIYU 补号 Telegram 安全提示：不提供本地批次远程控制。"""

from __future__ import annotations

from src.bot.auth import requires_auth


class JiyuReplenishCommandsMixin:
    """提示本机补号入口，并保护性消费后续一条普通私聊消息。"""

    _LEGACY_REPLENISH_BUTTONS = frozenset({"🧾 一键补号", "📊 补号状态", "⏹ 停止补号", "❌ 取消补号"})
    _LOCAL_ONLY_NOTICE = "Telegram 无法查看或控制本地补号批次。请仅在可信本机界面运行 make jiyu-sub2-replenish。"

    def _jiyu_replenish_waiting(self) -> set[int]:
        """返回一次性保护消费状态；只存 Telegram chat id。"""
        waiting = getattr(self, "_remote_replenish_waiting_chats", None)
        if waiting is None:
            waiting = set()
            self._remote_replenish_waiting_chats = waiting
        return waiting

    async def _jiyu_replenish_start_prompt(self, update) -> None:
        """提示本机可信 UI，并保护性消费同一私聊的下一条普通消息。"""
        self._jiyu_replenish_waiting().add(update.effective_chat.id)
        await update.message.reply_text(
            "远程补号材料提交和远程批次控制均已禁用。\n"
            "请仅在可信本机界面运行 make jiyu-sub2-replenish。",
        )

    @requires_auth
    async def cmd_jiyu_replenish(self, update, context):
        """Telegram 安全提示：/jiyu_replenish 或 /jiyu_replenish cancel。"""
        action = (context.args or [""])[0].casefold()
        if update.effective_chat.type != "private":
            await update.message.reply_text("补号安全门面只允许授权管理员私聊使用。")
            return

        if action in {"status", "状态", "stop", "停止"}:
            await update.message.reply_text(self._LOCAL_ONLY_NOTICE)
            return
        if action in {"cancel", "取消"}:
            self._jiyu_replenish_waiting().discard(update.effective_chat.id)
            await update.message.reply_text("已取消保护等待状态。")
            return
        if action:
            await update.message.reply_text(self._LOCAL_ONLY_NOTICE)
            return
        await self._jiyu_replenish_start_prompt(update)

    async def _handle_jiyu_replenish_text(self, update, raw_text: str) -> bool:
        """拒绝遗留菜单操作，并一次性保护消费提示后的普通文本。"""
        chat = update.effective_chat
        user = update.effective_user
        if chat is None or user is None or chat.type != "private":
            return False
        if raw_text in self._LEGACY_REPLENISH_BUTTONS:
            await update.message.reply_text(self._LOCAL_ONLY_NOTICE)
            return True
        waiting = self._jiyu_replenish_waiting()
        if chat.id not in waiting:
            return False
        waiting.discard(chat.id)
        await update.message.reply_text(
            "远程提交内容不会被读取。请仅在可信本机界面运行 make jiyu-sub2-replenish。",
        )
        return True
