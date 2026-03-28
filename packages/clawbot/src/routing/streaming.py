"""
StreamingResponse — 流式传输支持
从 chat_router.py 拆分而来，对标 LiteLLM 的 streaming 支持。
让 Telegram bot 可以逐步更新消息而不是等待完整响应。
"""
import time
import logging
import asyncio
from typing import List, Callable

logger = logging.getLogger(__name__)


class StreamingResponse:
    """流式响应包装器 — 支持 SSE 风格的逐 chunk 传输"""

    def __init__(self):
        self._chunks: List[str] = []
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._done = False
        self._full_text = ""
        self._start_time = time.time()

    async def add_chunk(self, text: str):
        """添加一个文本 chunk"""
        self._chunks.append(text)
        self._full_text += text
        await self._queue.put(text)

    async def finish(self):
        """标记流结束"""
        self._done = True
        await self._queue.put(None)

    async def __aiter__(self):
        """异步迭代 chunks"""
        while True:
            try:
                chunk = await asyncio.wait_for(self._queue.get(), timeout=60)
            except asyncio.TimeoutError:
                logger.warning("[Streaming] Queue read timeout — producer may have crashed")
                break
            if chunk is None:
                break
            yield chunk

    @property
    def full_text(self) -> str:
        return self._full_text

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self._start_time) * 1000

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)


async def stream_llm_to_telegram(
    llm_stream_func: Callable,
    send_func: Callable,
    chat_id: int,
    edit_interval: float = 1.0,
    min_chars_per_edit: int = 50,
):
    """将 LLM 流式输出实时推送到 Telegram 消息

    Args:
        llm_stream_func: async generator，yield 文本 chunks
        send_func: async (chat_id, text) -> message_id，发送/编辑消息
        chat_id: Telegram chat ID
        edit_interval: 最小编辑间隔（秒），避免 Telegram rate limit
        min_chars_per_edit: 每次编辑的最小新增字符数
    """
    full_text = ""
    message_id = None
    last_edit_time = 0
    pending_chars = 0

    try:
        async for chunk in llm_stream_func():
            full_text += chunk
            pending_chars += len(chunk)
            now = time.time()

            should_edit = (
                now - last_edit_time >= edit_interval
                and pending_chars >= min_chars_per_edit
            )

            if message_id is None:
                # 首次发送
                if len(full_text) >= 10:
                    message_id = await send_func(chat_id, full_text + " ▌")
                    last_edit_time = now
                    pending_chars = 0
            elif should_edit:
                try:
                    await send_func(chat_id, full_text + " ▌", edit_message_id=message_id)
                    last_edit_time = now
                    pending_chars = 0
                except Exception as e:
                    logger.warning(f"[Streaming] Telegram edit failed (mid-stream): {e}")

        # 最终更新（去掉光标）
        if message_id and full_text:
            try:
                await send_func(chat_id, full_text, edit_message_id=message_id)
            except Exception as e:
                logger.warning(f"[Streaming] Final Telegram edit failed: {e}")

    except Exception as e:
        logger.error(f"[Streaming] 流式传输失败: {e}")
        if full_text and message_id:
            try:
                await send_func(chat_id, full_text + "\n\n⚠️ 流式传输中断",
                                edit_message_id=message_id)
            except Exception as e:
                logger.warning(f"[Streaming] Failed to send interruption notice: {e}")

    return full_text
