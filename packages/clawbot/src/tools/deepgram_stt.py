"""
OpenClaw — Deepgram STT (语音转文字)
搬运 deepgram-python-sdk (410⭐) 的核心模式。

零配置: 只需 DEEPGRAM_API_KEY 环境变量。
用途: Telegram 语音消息 → 文字 → 交给 Brain 处理。

用法:
    text = await transcribe_audio(audio_bytes)
    text = await transcribe_file("/path/to/audio.ogg")
"""
import logging
import os
from pathlib import Path
from typing import Optional

from src.utils import scrub_secrets
from src.http_client import ResilientHTTPClient

logger = logging.getLogger(__name__)

# 模块级 HTTP 客户端（带重试 + 熔断）
_http = ResilientHTTPClient(timeout=30.0, name="deepgram_stt")


async def transcribe_audio(
    audio_data: bytes,
    language: str = "zh",
    model: str = "nova-3",
) -> Optional[str]:
    """
    语音转文字 — Deepgram Nova-3。

    Args:
        audio_data: 音频二进制数据 (支持 ogg/wav/mp3/m4a)
        language: 语言代码 (zh/en/ja)
        model: Deepgram 模型 (nova-3 最强)

    Returns:
        识别的文字，失败返回 None
    """
    api_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not api_key:
        logger.warning("DEEPGRAM_API_KEY 未设置")
        return None

    # 优先用 SDK
    try:
        from deepgram import DeepgramClient, PrerecordedOptions
        client = DeepgramClient(api_key)
        options = PrerecordedOptions(
            model=model,
            language=language,
            smart_format=True,
            punctuate=True,
        )
        response = client.listen.rest.v("1").transcribe_file(
            {"buffer": audio_data}, options
        )
        transcript = response.results.channels[0].alternatives[0].transcript
        if transcript:
            logger.info(f"Deepgram STT: {len(transcript)} chars ({language})")
            return transcript
        return None
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Deepgram SDK 失败: {scrub_secrets(str(e))}")

    # 降级: 直接 HTTP 调用
    try:
        resp = await _http.post(
            f"https://api.deepgram.com/v1/listen?model={model}&language={language}&smart_format=true",
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "audio/ogg",
            },
            content=audio_data,
        )
        if resp.status_code == 200:
            data = resp.json()
            transcript = (
                data.get("results", {})
                .get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("transcript", "")
            )
            if transcript:
                logger.info(f"Deepgram HTTP STT: {len(transcript)} chars")
                return transcript
        else:
            logger.warning(f"Deepgram HTTP {resp.status_code}: {scrub_secrets(resp.text[:200])}")
    except Exception as e:
        logger.warning(f"Deepgram HTTP 失败: {scrub_secrets(str(e))}")

    return None


async def transcribe_file(file_path: str, language: str = "zh") -> Optional[str]:
    """从文件转录"""
    path = Path(file_path)
    if not path.exists():
        return None
    audio_data = path.read_bytes()
    return await transcribe_audio(audio_data, language=language)
