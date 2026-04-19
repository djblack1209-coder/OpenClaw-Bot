# stream_manager.py — 流式输出管理：编辑频率控制 + 持续 typing 指示器
# 从 message_mixin.py 拆分而来

import asyncio
import logging

logger = logging.getLogger(__name__)


class StreamManagerMixin:
    """流式输出管理 Mixin — 提供编辑频率控制和 typing 指示器。"""

    @staticmethod
    def _stream_cutoff(is_group: bool, content: str) -> int:
        """自适应编辑频率 — 搬运自 n3d1117/chatgpt-telegram-bot

        群聊更保守（Telegram 对群聊有更严格的 flood 限制），
        私聊更激进（用户体验优先）。

        HI-011 根治: 群聊 cutoff 全面提升，配合时间门控使用。
        """
        content_len = len(content)
        if is_group:
            if content_len > 1000:
                return 300  # was 180
            if content_len > 200:
                return 200  # was 120
            if content_len > 50:
                return 150  # was 90
            return 80  # was 50
        else:
            if content_len > 1000:
                return 120  # was 90
            if content_len > 200:
                return 60  # was 45
            if content_len > 50:
                return 30  # was 25
            return 15

    async def _keep_typing(self, chat_id: int, context):
        """持续发送 typing 指示器 — 搬运自 n3d1117 的 wrap_with_indicator"""
        from telegram.constants import ChatAction

        try:
            while True:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(4.5)
        except asyncio.CancelledError as e:  # noqa: F841
            raise  # 让 finally 正常处理
        except Exception as e:
            # 网络错误等 — 静默退出但记录，不影响主流程
            logger.debug(f"[typing] chat={chat_id} 停止: {e}")
