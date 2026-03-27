"""
ClawBot - Telegram 消息发送工具 v2.0
统一的长消息分片、格式清理、安全发送
支持新排版系统的视觉元素（分隔线、emoji锚点等）
"""
import asyncio
import logging
import re
from typing import Optional

from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def _clean_for_telegram(text: str) -> str:
    """
    清理 AI 回复中对 Telegram 不友好的 markdown 格式。
    保留新排版系统的视觉元素（─── 分隔线、emoji、▸ 等）。
    """
    # 移除 ### / ## / # 标题符号，保留文字
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # 移除 **bold** 中多余的星号
    text = text.replace('**', '')

    # 移除 markdown 表格的 |---|---| 分隔行
    text = re.sub(r'^\|[-:\s|]+\|\s*$', '', text, flags=re.MULTILINE)

    # 简化表格：把 | col1 | col2 | 转为紧凑格式
    def simplify_table_row(match):
        row = match.group(0)
        cells = [c.strip() for c in row.strip('|').split('|')]
        cells = [c for c in cells if c]
        if cells:
            return '  '.join(cells)
        return ''
    text = re.sub(r'^\|(.+)\|\s*$', simplify_table_row, text, flags=re.MULTILINE)

    # 移除 --- 或 *** 分隔线（但保留 ─── 和 ═══ 新排版分隔线）
    text = re.sub(r'^[-*]{3,}\s*$', '', text, flags=re.MULTILINE)

    # 移除连续空行（超过2个换行变为2个）
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


async def send_long_message(
    chat_id: int,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
    reply_to_message_id: Optional[int] = None,
    max_length: int = 4000,
    chunk_delay: float = 0.3,
):
    """
    发送长消息，自动清理格式 + 分片，失败时回退纯文本。
    """
    if not text:
        return

    # 先清理格式
    text = _clean_for_telegram(text)

    parts = _split_message(text, max_length)

    for i, part in enumerate(parts):
        reply_id = reply_to_message_id if i == 0 else None
        await _send_safe(context, chat_id, part, reply_id)
        if i < len(parts) - 1:
            await asyncio.sleep(chunk_delay)


def _split_message(text: str, max_length: int) -> list:
    """按分隔线和换行符智能分片，优先在视觉断点处切割"""
    if len(text) <= max_length:
        return [text]

    parts = []
    remaining = text
    while remaining:
        if len(remaining) <= max_length:
            parts.append(remaining)
            break
        # 优先在分隔线处分割（新排版的 ─── 或 ═══）
        split_pos = remaining.rfind('───', 0, max_length)
        if split_pos > max_length // 3:
            # 在分隔线之前切割
            split_pos = remaining.rfind('\n', 0, split_pos)
        if split_pos == -1 or split_pos < max_length // 3:
            # 其次在换行处分割
            split_pos = remaining.rfind('\n', 0, max_length)
        if split_pos == -1 or split_pos < max_length // 2:
            # 最后在空格处分割
            split_pos = remaining.rfind(' ', 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        parts.append(remaining[:split_pos])
        remaining = remaining[split_pos:].lstrip('\n')

    return parts


async def _send_safe(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_to_message_id: Optional[int] = None,
):
    """安全发送消息，Markdown 失败时回退纯文本，reply失败时去掉回复"""
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_to_message_id=reply_to_message_id,
        )
    except Exception as e:
        logger.debug("[MessageSender] 异常: %s", e)
        try:
            # Markdown 失败，回退纯文本
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
            )
        except Exception as e:
            logger.debug("[MessageSender] 异常: %s", e)
            try:
                # reply_to 消息不存在时，去掉回复直接发送
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                )
            except Exception as e:
                logger.error(f"发送消息失败 (chat_id={chat_id}): {e}")
