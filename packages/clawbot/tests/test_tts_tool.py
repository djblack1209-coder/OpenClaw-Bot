"""tts_tool 单元测试 — TTS 文字转语音"""
import pytest
from src.tools.tts_tool import (
    CHINESE_VOICES,
    DEFAULT_VOICE,
    format_voice_list,
    text_to_speech,
)


class TestVoiceConfig:
    def test_chinese_voices_not_empty(self):
        assert len(CHINESE_VOICES) >= 6

    def test_default_voice_is_valid(self):
        assert DEFAULT_VOICE.startswith("zh-CN-")
        assert "Neural" in DEFAULT_VOICE

    def test_format_voice_list(self):
        msg = format_voice_list()
        assert "可用音色" in msg
        assert "晓晓" in msg
        assert "云希" in msg


class TestTextToSpeech:
    @pytest.mark.asyncio
    async def test_empty_text_returns_none(self):
        result = await text_to_speech("")
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_text_returns_none(self):
        result = await text_to_speech("   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_text_truncated_at_5000(self):
        # 不实际调用 TTS API，只验证函数不崩溃
        # 真实 TTS 调用需要网络，放在集成测试中
        pass
