"""
Tests for APIMixin — LLM API integration layer.

Covers: _call_api success/error paths, _call_api_stream,
        quality_gate rejection, CircuitOpenError handling.
"""
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from src.bot.error_messages import error_generic, error_circuit_open
from src.http_client import CircuitOpenError


# ============ Helpers ============

def _make_mixin():
    """Create an APIMixin instance with all required attributes mocked."""
    from src.bot.api_mixin import APIMixin

    class FakeBot(APIMixin):
        pass

    bot = FakeBot()
    bot.bot_id = "test_bot"
    bot.name = "TestBot"
    bot.model = "test-model-v1"
    bot.system_prompt = "You are a test bot."
    bot.api_type = "free"
    bot.is_claude = False
    bot.http_client = AsyncMock()
    return bot


@pytest.fixture
def mixin():
    return _make_mixin()


@pytest.fixture
def mock_globals():
    """Patch all globals used by APIMixin."""
    with patch("src.bot.api_mixin.rate_limiter") as rl, \
         patch("src.bot.api_mixin.token_budget") as tb, \
         patch("src.bot.api_mixin.quality_gate") as qg, \
         patch("src.bot.api_mixin.history_store") as hs, \
         patch("src.bot.api_mixin.context_manager") as cm, \
         patch("src.bot.api_mixin.metrics") as mt, \
         patch("src.bot.api_mixin.health_checker") as hc, \
         patch("src.bot.api_mixin.free_pool") as fp, \
         patch("src.bot.api_mixin.log_generation", None), \
         patch("src.bot.globals.tiered_context_manager", None):

        rl.check.return_value = (True, "")
        rl.record.return_value = None
        tb.check.return_value = (True, "")
        tb.record.return_value = None
        qg.check_response.return_value = (True, "")
        qg.record_response.return_value = None
        hs.get_messages.return_value = []
        hs.add_message.return_value = None
        cm.prepare_messages_for_api.return_value = (
            [{"role": "user", "content": "test"}], False
        )
        cm.update_history_store.return_value = None
        mt.log_api_call.return_value = None
        hc.record_success.return_value = None
        hc.record_error.return_value = None
        hc.heartbeat.return_value = None

        # free_pool.acompletion returns a mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello, test reply!"
        mock_response.usage = None
        fp.acompletion = AsyncMock(return_value=mock_response)

        yield {
            "rate_limiter": rl,
            "token_budget": tb,
            "quality_gate": qg,
            "history_store": hs,
            "context_manager": cm,
            "metrics": mt,
            "health_checker": hc,
            "free_pool": fp,
        }


# ============ _call_api ============

class TestCallApi:

    async def test_returns_response_on_success(self, mixin, mock_globals):
        """_call_api should return the LLM response text on success."""
        # Need to mock _get_chat_mode_prompt
        mixin._get_chat_mode_prompt = MagicMock(return_value=None)

        result = await mixin._call_api(123, "Hello")
        assert result == "Hello, test reply!"

    async def test_returns_error_generic_on_exception(self, mixin, mock_globals):
        """_call_api should return error_generic on unexpected exception."""
        mixin._get_chat_mode_prompt = MagicMock(return_value=None)
        mock_globals["free_pool"].acompletion.side_effect = Exception("API boom")

        result = await mixin._call_api(123, "Hello")
        assert "没处理成功" in result  # error_generic 包含人性化错误提示

    async def test_returns_error_circuit_open(self, mixin, mock_globals):
        """_call_api should return error_circuit_open on CircuitOpenError."""
        mixin._get_chat_mode_prompt = MagicMock(return_value=None)
        mock_globals["free_pool"].acompletion.side_effect = CircuitOpenError("open")

        result = await mixin._call_api(123, "Hello")
        assert result == error_circuit_open()

    async def test_returns_empty_when_rate_limited(self, mixin, mock_globals):
        """_call_api should return '' when rate limiter rejects."""
        mock_globals["rate_limiter"].check.return_value = (False, "too fast")
        mixin._get_chat_mode_prompt = MagicMock(return_value=None)

        result = await mixin._call_api(123, "Hello")
        assert result == ""

    async def test_returns_budget_message_when_exhausted(self, mixin, mock_globals):
        """_call_api should return budget message when token budget exhausted."""
        mock_globals["token_budget"].check.return_value = (False, "budget gone")
        mixin._get_chat_mode_prompt = MagicMock(return_value=None)

        result = await mixin._call_api(123, "Hello")
        assert "额度" in result

    async def test_quality_gate_rejection(self, mixin, mock_globals):
        """_call_api should return quality reason when quality gate rejects."""
        mixin._get_chat_mode_prompt = MagicMock(return_value=None)
        mock_globals["quality_gate"].check_response.return_value = (False, "too short")

        result = await mixin._call_api(123, "Hello")
        assert "质量检查" in result
        assert "too short" in result

    async def test_metrics_logged_on_success(self, mixin, mock_globals):
        """_call_api should log metrics on successful call."""
        mixin._get_chat_mode_prompt = MagicMock(return_value=None)

        await mixin._call_api(123, "Hello")
        mock_globals["metrics"].log_api_call.assert_called_once()
        args = mock_globals["metrics"].log_api_call.call_args
        assert args[1]["success"] is True or args[0][3] is True

    async def test_history_saved_on_success(self, mixin, mock_globals):
        """_call_api should save history when save_history=True."""
        mixin._get_chat_mode_prompt = MagicMock(return_value=None)

        await mixin._call_api(123, "Hello", save_history=True)
        mock_globals["history_store"].add_message.assert_called()


# ============ _call_api_stream ============

class TestCallApiStream:

    async def test_stream_returns_async_generator(self, mixin, mock_globals):
        """_call_api_stream should yield (content, status) tuples."""
        mixin._get_chat_mode_prompt = MagicMock(return_value=None)

        # Mock streaming response
        async def fake_stream():
            for text in ["Hello", " world", "!"]:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = text
                yield chunk

        mock_globals["free_pool"].acompletion = AsyncMock(return_value=fake_stream())

        results = []
        async for content, status in mixin._call_api_stream(123, "Hi"):
            results.append((content, status))

        assert len(results) >= 1
        # Last item should be "finished"
        assert results[-1][1] == "finished"
        # Final content should contain full text
        assert "Hello" in results[-1][0]
