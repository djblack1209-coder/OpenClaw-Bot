"""
TTS 文字转语音工具 — 对接 edge-tts (10K星)
零成本使用微软 Edge 在线 TTS，支持多语言多音色

用法:
    from src.tools.tts_tool import text_to_speech, get_voices
    audio_path = await text_to_speech("你好世界", voice="zh-CN-XiaoxiaoNeural")
"""
import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# 推荐中文音色
CHINESE_VOICES = {
    "晓晓": "zh-CN-XiaoxiaoNeural",      # 女声-温柔
    "云希": "zh-CN-YunxiNeural",          # 男声-沉稳  
    "晓萱": "zh-CN-XiaoxuanNeural",      # 女声-活泼
    "云扬": "zh-CN-YunyangNeural",        # 男声-新闻播报
    "晓墨": "zh-CN-XiaomoNeural",        # 女声-知性
    "晓辰": "zh-CN-XiaochenNeural",      # 女声-温暖
}

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+0%"
DEFAULT_VOLUME = "+0%"

# 输出目录
_OUTPUT_DIR = Path(os.getenv("TTS_OUTPUT_DIR", tempfile.gettempdir())) / "openclaw_tts"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def text_to_speech(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    volume: str = DEFAULT_VOLUME,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """将文本转换为语音文件
    
    Args:
        text: 要转换的文本 (最长 5000 字符)
        voice: 音色名称 (如 zh-CN-XiaoxiaoNeural)
        rate: 语速调节 (如 +20%, -10%)
        volume: 音量调节 (如 +50%)
        output_path: 输出文件路径 (默认自动生成)
    
    Returns:
        生成的音频文件路径，失败返回 None
    """
    try:
        import edge_tts
    except ImportError:
        logger.error("[TTS] edge-tts 未安装: pip install edge-tts")
        return None
    
    # 文本长度限制
    if not text or not text.strip():
        logger.warning("[TTS] 文本为空")
        return None
    text = text[:5000]
    
    # 解析音色别名
    if text_voice := CHINESE_VOICES.get(voice):
        voice = text_voice
    
    # 生成输出路径
    if output_path:
        _out = Path(output_path).resolve()
        if not str(_out).startswith(str(_OUTPUT_DIR.resolve())):
            logger.warning("[TTS] 路径越界被拒绝: %s", output_path)
            return None
    else:
        import hashlib
        name_hash = hashlib.sha256(text[:50].encode()).hexdigest()[:8]
        output_path = str(_OUTPUT_DIR / f"tts_{name_hash}.mp3")
    
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        await asyncio.wait_for(communicate.save(output_path), timeout=60)
        
        file_size = Path(output_path).stat().st_size
        logger.info("[TTS] 生成成功: %s (%.1f KB, voice=%s)", output_path, file_size/1024, voice)
        return output_path
    except Exception as e:
        logger.error("[TTS] 生成失败: %s", e)
        return None


async def get_voices(language: str = "zh") -> List[Dict]:
    """获取可用音色列表"""
    try:
        import edge_tts
        voices = await edge_tts.list_voices()
        return [v for v in voices if v.get("Locale", "").startswith(language)]
    except Exception as e:
        logger.error("[TTS] 获取音色列表失败: %s", e)
        return []


def format_voice_list() -> str:
    """格式化音色列表为用户友好消息"""
    lines = ["🎤 可用音色:\n"]
    for alias, voice_id in CHINESE_VOICES.items():
        lines.append(f"  • {alias} ({voice_id})")
    lines.append("\n提示: 使用别名或完整ID均可")
    return "\n".join(lines)
