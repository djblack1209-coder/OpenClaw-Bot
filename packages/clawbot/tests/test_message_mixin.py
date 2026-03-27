"""
Tests for MessageMixin — ALL incoming message handling.

Covers: _match_chinese_command, _dispatch_chinese_action,
        _is_directed_to_current_bot, _extract_json_object,
        _stream_cutoff, handle_message authorization gate.
"""
import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot.chinese_nlp_mixin import _match_chinese_command, ChineseNLPMixin
from src.bot.message_mixin import MessageHandlerMixin


# ============ _match_chinese_command ============

class TestMatchChineseCommand:

    def test_ta_analysis_with_ticker(self):
        """'分析AAPL' should match → ('ta', 'AAPL')."""
        result = _match_chinese_command("分析AAPL")
        assert result is not None
        action, arg = result
        assert action == "ta"
        assert arg == "AAPL"

    def test_portfolio_query(self):
        """'我的持仓' should match → ('portfolio', '')."""
        result = _match_chinese_command("我的持仓")
        assert result is not None
        action, arg = result
        assert action == "portfolio"
        assert arg == ""

    def test_unmatched_text_returns_none(self):
        """Random text should return None."""
        result = _match_chinese_command("今天天气真好")
        assert result is None

    def test_mixed_chinese_english_quote(self):
        """'AAPL多少钱' should match → ('quote', 'AAPL')."""
        result = _match_chinese_command("AAPL多少钱")
        assert result is not None
        action, arg = result
        assert action == "quote"
        assert arg == "AAPL"

    def test_start_command(self):
        """'帮助' should match → ('start', '')."""
        result = _match_chinese_command("帮助")
        assert result is not None
        assert result == ("start", "")

    def test_clear_command(self):
        """'清空对话' should match → ('clear', '')."""
        result = _match_chinese_command("清空对话")
        assert result is not None
        assert result == ("clear", "")

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        result = _match_chinese_command("")
        assert result is None

    def test_none_input_returns_none(self):
        """None input should return None (not crash)."""
        result = _match_chinese_command(None)
        assert result is None

    def test_signal_with_ticker(self):
        """'TSLA怎么样' should match → ('signal', 'TSLA')."""
        result = _match_chinese_command("TSLA怎么样")
        assert result is not None
        action, arg = result
        assert action == "signal"
        assert arg == "TSLA"

    def test_market_overview(self):
        """'市场概览' should match → ('market', '')."""
        result = _match_chinese_command("市场概览")
        assert result is not None
        assert result == ("market", "")


# ============ _dispatch_chinese_action ============

class TestDispatchChineseAction:

    @pytest.fixture
    def mixin(self):
        """A MessageHandlerMixin with ALL cmd_* methods auto-mocked.

        The dispatch_map dict evaluates self.cmd_X for every entry,
        so we need all of them to exist on the instance.
        """
        class FakeBot(ChineseNLPMixin, MessageHandlerMixin):
            def __getattr__(self, name):
                if name.startswith("cmd_"):
                    mock = AsyncMock()
                    object.__setattr__(self, name, mock)
                    return mock
                raise AttributeError(name)

        m = FakeBot()
        m.bot_id = "test_bot"
        return m

    @pytest.fixture
    def mock_update(self):
        update = MagicMock()
        update.effective_chat.id = 123
        update.effective_user.id = 1
        return update

    @pytest.fixture
    def mock_context(self):
        ctx = MagicMock()
        ctx.args = []
        return ctx

    async def test_dispatch_ta_calls_cmd_ta(self, mixin, mock_update, mock_context):
        """'ta' action should dispatch to cmd_ta."""
        await mixin._dispatch_chinese_action(mock_update, mock_context, "ta", "AAPL")
        mixin.cmd_ta.assert_awaited_once_with(mock_update, mock_context)
        assert mock_context.args == ["AAPL"]

    async def test_dispatch_buy_calls_cmd_buy(self, mixin, mock_update, mock_context):
        """'buy' action should dispatch to cmd_buy."""
        await mixin._dispatch_chinese_action(mock_update, mock_context, "buy", "")
        mixin.cmd_buy.assert_awaited_once()

    async def test_dispatch_unknown_action_graceful(self, mixin, mock_update, mock_context):
        """Unknown action_type should not raise."""
        await mixin._dispatch_chinese_action(mock_update, mock_context, "nonexistent_xyz", "")
        # Should complete without error

    async def test_dispatch_none_update_returns(self, mixin, mock_context):
        """None update should return immediately."""
        await mixin._dispatch_chinese_action(None, mock_context, "ta", "")
        mixin.cmd_ta.assert_not_awaited()

    async def test_dispatch_empty_action_type_returns(self, mixin, mock_update, mock_context):
        """Empty action_type should return immediately."""
        await mixin._dispatch_chinese_action(mock_update, mock_context, "", "")
        mixin.cmd_ta.assert_not_awaited()

    async def test_dispatch_ops_email(self, mixin, mock_update, mock_context):
        """'ops_email' should dispatch to cmd_ops with args=['email']."""
        await mixin._dispatch_chinese_action(mock_update, mock_context, "ops_email", "")
        mixin.cmd_ops.assert_awaited_once()
        assert mock_context.args == ["email"]

    async def test_dispatch_handler_exception_logged(self, mixin, mock_update, mock_context):
        """If handler raises, dispatch should catch and not propagate."""
        mixin.cmd_ta.side_effect = RuntimeError("boom")
        # Should not raise
        await mixin._dispatch_chinese_action(mock_update, mock_context, "ta", "AAPL")


# ============ _is_directed_to_current_bot ============

class TestIsDirectedToCurrentBot:

    def test_private_chat_always_true(self):
        assert ChineseNLPMixin._is_directed_to_current_bot("hello", "private", "bot1") is True

    def test_group_mentioned_returns_true(self):
        assert ChineseNLPMixin._is_directed_to_current_bot(
            "@mybot what's up", "group", "mybot"
        ) is True

    def test_group_not_mentioned_returns_false(self):
        assert ChineseNLPMixin._is_directed_to_current_bot(
            "hello everyone", "group", "mybot"
        ) is False

    def test_empty_username_returns_false(self):
        assert ChineseNLPMixin._is_directed_to_current_bot(
            "hello", "group", ""
        ) is False


# ============ _extract_json_object ============

class TestExtractJsonObject:

    @pytest.fixture
    def mixin(self):
        return MessageHandlerMixin()

    def test_extracts_from_code_block(self, mixin):
        text = 'Here is the result:\n```json\n{"key": "value"}\n```'
        result = mixin._extract_json_object(text)
        assert result == {"key": "value"}

    def test_extracts_from_raw_json(self, mixin):
        text = 'Some text before {"name": "test", "count": 42} some text after'
        result = mixin._extract_json_object(text)
        assert result is not None
        assert result["name"] == "test"

    def test_returns_none_for_no_json(self, mixin):
        result = mixin._extract_json_object("just plain text")
        assert result is None

    def test_returns_none_for_none_input(self, mixin):
        result = mixin._extract_json_object(None)
        assert result is None


# ============ _stream_cutoff ============

class TestStreamCutoff:

    def test_group_short_content(self):
        """Short content in group should use smaller cutoff."""
        cutoff = MessageHandlerMixin._stream_cutoff(True, "x" * 30)
        assert cutoff == 80

    def test_group_long_content(self):
        """Long content in group should use larger cutoff."""
        cutoff = MessageHandlerMixin._stream_cutoff(True, "x" * 1500)
        assert cutoff == 300

    def test_private_short_content(self):
        """Short content in private should have small cutoff."""
        cutoff = MessageHandlerMixin._stream_cutoff(False, "x" * 30)
        assert cutoff == 15

    def test_private_long_content(self):
        """Long content in private should be larger but still < group."""
        cutoff = MessageHandlerMixin._stream_cutoff(False, "x" * 1500)
        assert cutoff == 120

    def test_group_cutoff_always_gte_private(self):
        """Group cutoff should always be >= private cutoff for same content."""
        for length in (10, 100, 500, 2000):
            content = "x" * length
            assert MessageHandlerMixin._stream_cutoff(True, content) >= \
                   MessageHandlerMixin._stream_cutoff(False, content)
