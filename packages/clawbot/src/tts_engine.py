"""
OpenClaw TTS 引擎 — 搬运 edge-tts (10.3k⭐)
零成本文本转语音，微软 Edge TTS 引擎。
300+ 声音，40+ 语言，无需 API Key。

Usage:
    from src.tts_engine import text_to_voice, get_available_voices
    audio = await text_to_voice("你好，我是 OpenClaw")
    # Returns bytes (MP3), ready for bot.send_voice()
"""
import io
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Graceful degradation: edge-tts is optional
try:
    import edge_tts
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False
    logger.warning(
        "[TTS] edge-tts not installed. Voice features disabled. "
        "Install with: pip install edge-tts>=6.0.0"
    )

# ── 默认配置 ──────────────────────────────────────────────────
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"       # 自然女声
MALE_VOICE = "zh-CN-YunxiNeural"             # 自然男声
MAX_TEXT_LENGTH = 5000
TRUNCATION_SUFFIX = "...详细内容请查看文字消息"

# ── Voice list cache ──────────────────────────────────────────
_voice_cache: Optional[List[dict]] = None


async def text_to_voice(
    text: str,
    voice: str = DEFAULT_VOICE,
) -> Optional[bytes]:
    """将文本转换为 MP3 语音。

    Args:
        text: 要转换的文本
        voice: edge-tts voice ID (默认 zh-CN-XiaoxiaoNeural)

    Returns:
        MP3 bytes on success, None on failure or if edge-tts unavailable
    """
    if not _EDGE_TTS_AVAILABLE:
        logger.debug("[TTS] edge-tts not available, skipping")
        return None

    if not text or not text.strip():
        return None

    # 截断过长文本
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + TRUNCATION_SUFFIX

    try:
        communicate = edge_tts.Communicate(text, voice)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        audio_bytes = buf.getvalue()
        if not audio_bytes:
            logger.warning("[TTS] edge-tts returned empty audio")
            return None
        return audio_bytes
    except Exception as e:
        logger.error("[TTS] text_to_voice failed: %s", e)
        return None


async def get_available_voices(language: str = "zh") -> List[dict]:
    """获取可用语音列表（按语言筛选，首次获取后缓存）。

    Args:
        language: 语言前缀过滤 (如 "zh", "en", "ja")

    Returns:
        语音列表 [{"Name": "...", "ShortName": "...", "Gender": "...", ...}]
        edge-tts 不可用时返回空列表
    """
    global _voice_cache

    if not _EDGE_TTS_AVAILABLE:
        return []

    # 使用缓存
    if _voice_cache is not None:
        return [v for v in _voice_cache if v.get("Locale", "").startswith(language)]

    try:
        voices = await edge_tts.list_voices()
        _voice_cache = voices
        return [v for v in _voice_cache if v.get("Locale", "").startswith(language)]
    except Exception as e:
        logger.error("[TTS] list_voices failed: %s", e)
        return []
