"""
主动智能引擎 — 通知发送辅助函数

提供通过 Telegram 发送主动通知的能力，包括纯文本和图片+文字两种形式。
图片发送失败时自动降级为纯文本。

> 从 proactive_engine.py 拆分 (HI-358)
"""

import logging

logger = logging.getLogger(__name__)


async def _send_proactive(user_id: str, text: str):
    """通过 Telegram + 微信发送主动通知。"""
    try:
        from src.bot.globals import bot_registry
        bots = bot_registry
        if not bots:
            return

        # 用第一个可用 bot 发送 Telegram
        bot = next(iter(bots.values()), None)
        if bot and hasattr(bot, "application"):
            admin_chat_id = int(user_id) if user_id.isdigit() else None
            if admin_chat_id:
                await bot.application.bot.send_message(
                    chat_id=admin_chat_id,
                    text=f"💡 {text}",
                )
    except Exception as e:
        logger.debug(f"主动通知发送失败: {e}")

    # 微信镜像推送 — 异动告警/交易跟踪/闲鱼订单等主动通知也要到达微信
    try:
        import asyncio
        from src.wechat_bridge import send_to_wechat
        asyncio.create_task(send_to_wechat(f"💡 {text}"))
    except Exception as e:
        logger.debug("[WeChat] 主动通知镜像失败: %s", e)


async def _send_proactive_photo(user_id: str, photo_bytes: bytes, caption: str):
    """通过 Telegram 发送带图主动通知（异动K线图等）。

    降级: 图片发送失败时自动降级为纯文本通知。
    """
    try:
        import io as _io
        from src.bot.globals import bot_registry
        bots = bot_registry
        if not bots:
            return

        bot = next(iter(bots.values()), None)
        if bot and hasattr(bot, "application"):
            admin_chat_id = int(user_id) if user_id.isdigit() else None
            if admin_chat_id:
                buf = _io.BytesIO(photo_bytes)
                buf.name = "anomaly_chart.png"
                await bot.application.bot.send_photo(
                    chat_id=admin_chat_id,
                    photo=buf,
                    caption=caption,
                    parse_mode="HTML",
                )
    except Exception as e:
        logger.debug(f"主动图表通知发送失败: {e}, 降级到纯文本")
        # 降级到纯文本
        await _send_proactive(user_id, caption)


def _safe_parse_time(iso_str: str):
    """安全解析 ISO 时间字符串"""
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError) as e:  # noqa: F841
        return None
