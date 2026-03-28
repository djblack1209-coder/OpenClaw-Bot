"""
PriorityMessageQueue — 优先级消息队列
从 chat_router.py 拆分而来，确保高优先级消息（@bot、风控告警）优先处理。
"""
import asyncio
from typing import Dict, Any

from src.routing.constants import CHAIN_DISCUSS_TRIGGERS
from src.routing.models import MessagePriority, PrioritizedMessage


class PriorityMessageQueue:
    """优先级消息队列 — 确保高优先级消息优先处理

    解决问题：当多个群同时发消息时，确保 @bot 的直接请求
    和风控告警优先于普通群聊消息被处理。
    """

    def __init__(self, max_size: int = 1000):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        self._stats = {
            "total_enqueued": 0,
            "total_processed": 0,
            "by_priority": {p.name: 0 for p in MessagePriority},
        }

    async def enqueue(self, msg: PrioritizedMessage):
        """入队"""
        await self._queue.put(msg)
        self._stats["total_enqueued"] += 1
        for p in MessagePriority:
            if p.value == msg.priority:
                self._stats["by_priority"][p.name] += 1
                break

    async def dequeue(self) -> PrioritizedMessage:
        """出队（阻塞等待）"""
        msg = await self._queue.get()
        self._stats["total_processed"] += 1
        return msg

    def classify_priority(self, text: str, chat_id: int, user_id: int,
                          is_private: bool = False, is_mentioned: bool = False) -> MessagePriority:
        """自动分类消息优先级"""
        text_lower = text.lower()

        # 风控/告警关键词
        if any(kw in text_lower for kw in ["止损", "爆仓", "风控", "紧急", "urgent", "alert"]):
            return MessagePriority.CRITICAL

        # 私聊或直接 @
        if is_private or is_mentioned:
            return MessagePriority.HIGH

        # 命令
        if text.startswith("/"):
            return MessagePriority.HIGH

        # 链式讨论触发
        if any(trigger in text_lower for trigger in CHAIN_DISCUSS_TRIGGERS[:5]):
            return MessagePriority.HIGH

        return MessagePriority.NORMAL

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "pending": self.pending,
        }
