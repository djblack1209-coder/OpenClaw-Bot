"""
Routing — 优先级消息队列
按优先级排序的异步消息队列
"""
import re
import time
import asyncio
import logging
from typing import Dict

from src.routing.models import MessagePriority, PrioritizedMessage

logger = logging.getLogger(__name__)

# 关键词 -> 优先级
_CRITICAL_KEYWORDS = re.compile(
    r"止损|爆仓|风控|紧急|urgent|alert|kill.?switch|liquidat",
    re.IGNORECASE,
)


class PriorityMessageQueue:
    """按优先级排序的异步消息队列"""

    def __init__(self, max_size=1000):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        self._stats = {
            "total_enqueued": 0,
            "total_processed": 0,
            "by_priority": {p.name: 0 for p in MessagePriority},
        }

    async def enqueue(self, msg: PrioritizedMessage):
        await self._queue.put(msg)
        self._stats["total_enqueued"] += 1
        for p in MessagePriority:
            if p.value == msg.priority:
                self._stats["by_priority"][p.name] += 1
                break

    async def dequeue(self) -> PrioritizedMessage:
        msg = await self._queue.get()
        self._stats["total_processed"] += 1
        return msg

    def classify_priority(
        self, text: str, chat_id: int = 0, user_id: int = 0,
        is_private: bool = False, is_mentioned: bool = False,
    ) -> MessagePriority:
        """根据消息内容和上下文自动分类优先级"""
        if _CRITICAL_KEYWORDS.search(text or ""):
            return MessagePriority.CRITICAL
        if is_private or is_mentioned:
            return MessagePriority.HIGH
        if text and text.startswith("/"):
            return MessagePriority.HIGH
        return MessagePriority.NORMAL

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "pending": self.pending,
        }
