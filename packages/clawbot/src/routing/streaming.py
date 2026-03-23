"""
Routing — 流式传输
LLM 流式输出到 Telegram 的包装器
"""
import time
import asyncio
import logging
from typing import Callable, AsyncIterator

logger = logging.getLogger(__name__)


class StreamingResponse:
    """异步流式响应包装器"""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._chunks: list = []
        self._done = False
        self._start_ts = time.time()

    async def add_chunk(self, chunk: str):
        self._chunks.append(chunk)
        await self._queue.put(chunk)

    async def finish(self):
        self._done = True
        await self._queue.put(None)

    async def __aiter__(self):
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            yield chunk

    @property
    def full_text(self) -> str:
        return "".join(self._chunks)

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self._start_ts) * 1000

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)


async def stream_llm_to_telegram(
    llm_stream_func: Callable,
    send_func: Callable,
    chat_id: int,
    edit_interval: float = 1.0,
    min_chars_per_edit: int = 50,
) -> str:
    """
    将 LLM 流式输出实时推送到 Telegram 消息。

    Args:
        llm_stream_func: 异步生成器，yield 文本 chunk
        send_func: async (chat_id, text, message_id=None) -> message_id
        chat_id: Telegram chat ID
        edit_interval: 最小编辑间隔（秒）
        min_chars_per_edit: 每次编辑最少新增字符数
    """
    full_text = ""
    message_id = None
    last_edit_ts = 0.0
    last_edit_len = 0
    cursor = " ▌"

    try:
        async for chunk in llm_stream_func():
            full_text += chunk
            now = time.time()
            new_chars = len(full_text) - last_edit_len

            if new_chars >= min_chars_per_edit and (now - last_edit_ts) >= edit_interval:
                display = full_text + cursor
                try:
                    result = await send_func(chat_id, display, message_id)
                    if result and not message_id:
                        message_id = result
                    last_edit_ts = now
                    last_edit_len = len(full_text)
                except Exception as e:
                    logger.debug(f"[StreamLLM] edit failed: {e}")

        # 最终更新（去掉光标）
        if full_text and message_id:
            try:
                await send_func(chat_id, full_text, message_id)
            except Exception:
                logger.debug("Silenced exception", exc_info=True)
        elif full_text and not message_id:
            try:
                await send_func(chat_id, full_text, None)
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

    except Exception as e:
        logger.error(f"[StreamLLM] stream failed: {e}")
        if not full_text:
            full_text = f"流式传输失败: {e}"

    return full_text
