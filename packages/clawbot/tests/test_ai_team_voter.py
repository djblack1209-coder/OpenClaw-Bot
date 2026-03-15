"""
Tests for AI Team Voter module
"""
import pytest
from unittest.mock import AsyncMock
from src.ai_team_voter import (
    _parse_vote, _format_ta_summary, run_team_vote, run_team_vote_batch,
    BotVote, VoteResult, VOTE_ORDER,
)


class TestParseVote:
    def test_valid_json(self):
        text = '{"vote": "BUY", "confidence": 8, "reasoning": "强势突破", "entry_price": 150.0, "stop_loss": 145.0, "take_profit": 162.0}'
        v = _parse_vote(text, "test", "Test", "测试")
        assert v.vote == "BUY"
        assert v.confidence == 8
        assert v.entry_price == 150.0
        assert v.stop_loss == 145.0

    def test_json_in_text(self):
        text = '分析如下：\n{"vote": "HOLD", "confidence": 5, "reasoning": "观望"}\n以上。'
        v = _parse_vote(text, "test", "Test", "测试")
        assert v.vote == "HOLD"
        assert v.confidence == 5

    def test_invalid_json_fallback_buy(self):
        text = "我建议买入这个标的，看好后市"
        v = _parse_vote(text, "test", "Test", "测试")
        assert v.vote == "BUY"

    def test_invalid_json_fallback_skip(self):
        text = "建议跳过，风险太大"
        v = _parse_vote(text, "test", "Test", "测试")
        assert v.vote == "SKIP"

    def test_invalid_json_fallback_hold(self):
        text = "目前没有明确方向"
        v = _parse_vote(text, "test", "Test", "测试")
        assert v.vote == "HOLD"

    def test_confidence_clamped(self):
        text = '{"vote": "BUY", "confidence": 99, "reasoning": "test"}'
        v = _parse_vote(text, "test", "Test", "测试")
        assert v.confidence == 10

    def test_confidence_min(self):
        text = '{"vote": "BUY", "confidence": -5, "reasoning": "test"}'
        v = _parse_vote(text, "test", "Test", "测试")
        assert v.confidence == 1

    def test_invalid_vote_defaults_hold(self):
        text = '{"vote": "MAYBE", "confidence": 5, "reasoning": "test"}'
        v = _parse_vote(text, "test", "Test", "测试")
        assert v.vote == "HOLD"


class TestFormatTaSummary:
    def test_full_data(self):
        data = {
            "symbol": "AAPL", "price": 150.0, "change_pct": 2.5,
            "indicators": {"rsi_6": 55, "rsi_14": 50, "macd": 0.5, "macd_signal": 0.3,
                           "trend": "up", "vol_ratio": 1.5, "atr_pct": 2.1},
            "signal": {"signal_cn": "买入", "score": 45},
            "support_resistance": {"supports": [145.0], "resistances": [155.0]},
        }
        text = _format_ta_summary(data)
        assert "AAPL" in text
        assert "150.00" in text
        assert "RSI6=55" in text

    def test_empty_data(self):
        assert "(无技术数据)" in _format_ta_summary({})
        assert "(无技术数据)" in _format_ta_summary(None)


class TestVoteResult:
    def test_format_telegram_buy(self):
        vr = VoteResult(
            symbol="AAPL", decision="BUY",
            buy_count=3, hold_count=1, skip_count=1,
            avg_confidence=0.7, avg_entry=150.0, avg_stop=145.0, avg_target=162.0,
            votes=[
                BotVote("h", "h", "雷达", "BUY", 8, "强势"),
                BotVote("q", "q", "宏观", "BUY", 7, "板块轮动"),
                BotVote("g", "g", "图表", "BUY", 9, "突破"),
                BotVote("d", "d", "风控", "HOLD", 5, "风险可控"),
                BotVote("c", "c", "指挥", "SKIP", 3, "不确定"),
            ],
        )
        text = vr.format_telegram()
        assert "BUY" in text
        assert "AAPL" in text
        assert "3" in text  # buy count

    def test_format_telegram_vetoed(self):
        vr = VoteResult(
            symbol="TSLA", decision="HOLD", vetoed=True, veto_reason="波动太大",
            buy_count=4, hold_count=0, skip_count=1,
            votes=[],
        )
        text = vr.format_telegram()
        assert "风控否决" in text
        assert "波动太大" in text


class TestRunTeamVote:
    @pytest.mark.asyncio
    async def test_majority_buy(self):
        """4+ BUY votes (2/3 majority of 6) should result in BUY decision"""
        callers = {}
        for bot_id in VOTE_ORDER:
            mock = AsyncMock()
            if bot_id in ("claude_haiku", "qwen235b", "gptoss", "claude_sonnet"):
                mock.return_value = '{"vote": "BUY", "confidence": 8, "reasoning": "看好", "entry_price": 150, "stop_loss": 145, "take_profit": 160}'
            else:
                mock.return_value = '{"vote": "HOLD", "confidence": 5, "reasoning": "观望"}'
            callers[bot_id] = mock

        result = await run_team_vote("AAPL", {"symbol": "AAPL", "price": 150}, callers)
        assert result.decision == "BUY"
        assert result.buy_count == 4

    @pytest.mark.asyncio
    async def test_minority_hold(self):
        """< 3 BUY votes should result in HOLD"""
        callers = {}
        for bot_id in VOTE_ORDER:
            mock = AsyncMock()
            if bot_id in ("claude_haiku", "qwen235b"):
                mock.return_value = '{"vote": "BUY", "confidence": 7, "reasoning": "看好"}'
            else:
                mock.return_value = '{"vote": "HOLD", "confidence": 5, "reasoning": "观望"}'
            callers[bot_id] = mock

        result = await run_team_vote("AAPL", {}, callers)
        assert result.decision == "HOLD"
        assert result.buy_count == 2

    @pytest.mark.asyncio
    async def test_risk_veto(self):
        """DeepSeek SKIP should veto even with 4 BUY votes"""
        callers = {}
        for bot_id in VOTE_ORDER:
            mock = AsyncMock()
            if bot_id == "deepseek_v3":
                mock.return_value = '{"vote": "SKIP", "confidence": 9, "reasoning": "风险过高"}'
            else:
                mock.return_value = '{"vote": "BUY", "confidence": 8, "reasoning": "看好"}'
            callers[bot_id] = mock

        result = await run_team_vote("AAPL", {}, callers)
        assert result.decision == "HOLD"
        assert result.vetoed is True
        assert "风险过高" in result.veto_reason

    @pytest.mark.asyncio
    async def test_timeout_defaults_hold(self):
        """Timeout should default to HOLD"""
        callers = {}
        for bot_id in VOTE_ORDER:
            mock = AsyncMock(side_effect=TimeoutError())
            callers[bot_id] = mock

        result = await run_team_vote("AAPL", {}, callers, timeout_per_bot=0.01)
        assert result.decision == "HOLD"
        assert result.buy_count == 0

    @pytest.mark.asyncio
    async def test_notify_called(self):
        """Notify should be called for each vote"""
        callers = {}
        for bot_id in VOTE_ORDER:
            mock = AsyncMock(return_value='{"vote": "HOLD", "confidence": 5, "reasoning": "ok"}')
            callers[bot_id] = mock

        notify = AsyncMock()
        await run_team_vote("AAPL", {}, callers, notify_func=notify)
        assert notify.call_count == len(VOTE_ORDER)


class TestRunTeamVoteBatch:
    @pytest.mark.asyncio
    async def test_batch_sorts_by_buy_count(self):
        callers = {}
        call_count = [0]
        for bot_id in VOTE_ORDER:
            async def _make_mock(bid):
                async def _call(chat_id, prompt):
                    # First symbol gets all BUY, second gets all HOLD
                    if "SYM1" in prompt or call_count[0] < 5:
                        call_count[0] += 1
                        return '{"vote": "BUY", "confidence": 8, "reasoning": "好"}'
                    return '{"vote": "HOLD", "confidence": 5, "reasoning": "观望"}'
                return _call
            callers[bot_id] = await _make_mock(bot_id)

        candidates = [
            {"symbol": "SYM1", "price": 100},
            {"symbol": "SYM2", "price": 200},
        ]
        results = await run_team_vote_batch(candidates, {}, callers, max_candidates=2)
        assert len(results) == 2
        assert results[0].buy_count >= results[1].buy_count
