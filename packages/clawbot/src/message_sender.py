"""
ClawBot - Telegram 消息发送工具
统一的长消息分片、格式清理、安全发送
适配 Telegram iOS 客户端显示（避免过多 markdown 符号）
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
    Telegram 只支持有限的 Markdown：*bold* _italic_ `code` ```pre```
    不支持：## 标题、表格、---分隔线 等。
    """
    # 移除 ### / ## / # 标题符号，保留文字
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # 移除 **bold** 中多余的星号，Telegram Markdown 用单个 * 即可
    # 但 MarkdownV2 不好用，直接去掉所有 ** 让文字更干净
    text = text.replace('**', '')

    # 移除 markdown 表格的 |---|---| 分隔行
    text = re.sub(r'^\|[-:\s|]+\|\s*$', '', text, flags=re.MULTILINE)

    # 简化表格：把 | col1 | col2 | 转为 "col1 / col2" 格式
    def simplify_table_row(match):
        row = match.group(0)
        cells = [c.strip() for c in row.strip('|').split('|')]
        cells = [c for c in cells if c]
        if cells:
            return '  '.join(cells)
        return ''
    text = re.sub(r'^\|(.+)\|\s*$', simplify_table_row, text, flags=re.MULTILINE)

    # 移除 --- 或 *** 分隔线
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
    """按换行符智能分片"""
    if len(text) <= max_length:
        return [text]

    parts = []
    remaining = text
    while remaining:
        if len(remaining) <= max_length:
            parts.append(remaining)
            break
        # 优先在换行处分割
        split_pos = remaining.rfind('\n', 0, max_length)
        if split_pos == -1 or split_pos < max_length // 2:
            # 没有合适的换行，在空格处分割
            split_pos = remaining.rfind(' ', 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        parts.append(remaining[:split_pos])
        remaining = remaining[split_pos:].lstrip()

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
    except Exception:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
            )
        except Exception:
            # reply_to 消息不存在时，去掉回复直接发送
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                )
            except Exception as e:
                logger.error(f"发送消息失败 (chat_id={chat_id}): {e}")
