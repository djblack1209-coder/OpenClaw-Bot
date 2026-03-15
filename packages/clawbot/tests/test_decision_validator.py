"""
Tests for DecisionValidator v2.0 — new checks:
- decision_frequency (check 8)
- extreme_volatility (check 9)
- confidence_level (check 10)
"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock

from src.decision_validator import DecisionValidator, ValidationResult
from src.models import TradeProposal


@pytest.fixture
def mock_quote():
    f = AsyncMock()
    f.return_value = {"price": 150.0, "change_pct": 2.5}
    return f


@pytest.fixture
def validator(mock_quote):
    return DecisionValidator(
        get_quote_func=mock_quote,
        min_decision_interval_seconds=60,
        extreme_volatility_pct=0.08,
        min_confidence_threshold=0.3,
    )


def _make_proposal(**overrides):
    defaults = dict(
        symbol="AAPL", action="BUY", quantity=5,
        entry_price=150.0, stop_loss=145.0, take_profit=162.0,
        signal_score=50, confidence=0.7,
        reason="test", decided_by="TestBot",
    )
    defaults.update(overrides)
    return TradeProposal(**defaults)


# ============ Check 8: Decision Frequency ============


class TestDecisionFrequency:

    def test_first_decision_passes(self, validator):
        proposal = _make_proposal()
        issues, warnings = validator._check_decision_frequency(proposal)
        assert len(issues) == 0

    def test_rapid_repeat_blocked(self, validator):
        """Same symbol within interval should be rejected."""
        validator._recent_decisions["AAPL"] = time.time()
        proposal = _make_proposal()
        issues, warnings = validator._check_decision_frequency(proposal)
        assert len(issues) == 1
        assert "距上次决策" in issues[0]

    def test_expired_decision_allowed(self, validator):
        """Decision older than interval should pass."""
        validator._recent_decisions["AAPL"] = time.time() - 120
        proposal = _make_proposal()
        issues, warnings = validator._check_decision_frequency(proposal)
        assert len(issues) == 0

    def test_different_symbol_allowed(self, validator):
        """Different symbol should not be blocked."""
        validator._recent_decisions["MSFT"] = time.time()
        proposal = _make_proposal(symbol="AAPL")
        issues, warnings = validator._check_decision_frequency(proposal)
        assert len(issues) == 0

    def test_hold_skipped(self, validator):
        """HOLD action should skip frequency check."""
        validator._recent_decisions["AAPL"] = time.time()
        proposal = _make_proposal(action="HOLD")
        issues, warnings = validator._check_decision_frequency(proposal)
        assert len(issues) == 0

    def test_old_records_cleaned(self, validator):
        """Records older than 1 hour should be cleaned."""
        validator._recent_decisions["OLD"] = time.time() - 7200
        validator._recent_decisions["AAPL"] = time.time() - 120
        proposal = _make_proposal()
        validator._check_decision_frequency(proposal)
        assert "OLD" not in validator._recent_decisions


# ============ Check 9: Extreme Volatility ============


class TestExtremeVolatility:

    def test_normal_volatility_passes(self, validator):
        quote = {"price": 150.0, "change_pct": 2.5}
        proposal = _make_proposal()
        issues, warnings = validator._check_extreme_volatility(proposal, quote)
        assert len(issues) == 0

    def test_extreme_up_blocked(self, validator):
        """8%+ daily gain should be rejected."""
        quote = {"price": 162.0, "change_pct": 10.0}
        proposal = _make_proposal()
        issues, warnings = validator._check_extreme_volatility(proposal, quote)
        assert len(issues) == 1
        assert "暴涨" in issues[0]

    def test_extreme_down_blocked(self, validator):
        """8%+ daily drop should be rejected."""
        quote = {"price": 135.0, "change_pct": -9.5}
        proposal = _make_proposal()
        issues, warnings = validator._check_extreme_volatility(proposal, quote)
        assert len(issues) == 1
        assert "暴跌" in issues[0]

    def test_near_threshold_warns(self, validator):
        """Near threshold (70%+) should warn."""
        quote = {"price": 150.0, "change_pct": 6.0}  # 6% > 8*0.7=5.6%
        proposal = _make_proposal()
        issues, warnings = validator._check_extreme_volatility(proposal, quote)
        assert len(issues) == 0
        assert len(warnings) == 1
        assert "接近极端波动阈值" in warnings[0]

    def test_no_quote_skipped(self, validator):
        proposal = _make_proposal()
        issues, warnings = validator._check_extreme_volatility(proposal, None)
        assert len(issues) == 0
        assert len(warnings) == 0

    def test_calculated_from_prev_close(self, validator):
        """Should calculate change_pct from price and previousClose."""
        quote = {"price": 165.0, "previousClose": 150.0}  # +10%
        proposal = _make_proposal()
        issues, warnings = validator._check_extreme_volatility(proposal, quote)
        assert len(issues) == 1

    def test_hold_skipped(self, validator):
        quote = {"price": 150.0, "change_pct": 15.0}
        proposal = _make_proposal(action="HOLD")
        issues, warnings = validator._check_extreme_volatility(proposal, quote)
        assert len(issues) == 0


# ============ Check 10: Confidence Level ============


class TestConfidenceLevel:

    def test_high_confidence_passes(self, validator):
        proposal = _make_proposal(confidence=0.8)
        issues, warnings = validator._check_confidence_level(proposal)
        assert len(issues) == 0
        assert len(warnings) == 0

    def test_low_confidence_rejected(self, validator):
        """Confidence below threshold should be rejected."""
        proposal = _make_proposal(confidence=0.2)
        issues, warnings = validator._check_confidence_level(proposal)
        assert len(issues) == 1
        assert "置信度" in issues[0]

    def test_borderline_confidence_warns(self, validator):
        """Confidence between threshold and 1.5x threshold should warn."""
        proposal = _make_proposal(confidence=0.35)  # > 0.3 but < 0.45
        issues, warnings = validator._check_confidence_level(proposal)
        assert len(issues) == 0
        assert len(warnings) == 1
        assert "偏低" in warnings[0]

    def test_zero_confidence_warns(self, validator):
        """Zero confidence means not provided."""
        proposal = _make_proposal(confidence=0)
        issues, warnings = validator._check_confidence_level(proposal)
        assert len(issues) == 0
        assert len(warnings) == 1
        assert "未提供" in warnings[0]

    def test_hold_skipped(self, validator):
        proposal = _make_proposal(action="HOLD", confidence=0.1)
        issues, warnings = validator._check_confidence_level(proposal)
        assert len(issues) == 0


# ============ Integration: Full validate() with new checks ============


class TestValidateIntegration:

    @pytest.mark.asyncio
    async def test_extreme_volatility_rejects_full_validate(self, mock_quote):
        """Extreme volatility should cause full validate() to reject."""
        mock_quote.return_value = {"price": 150.0, "change_pct": 12.0}
        validator = DecisionValidator(
            get_quote_func=mock_quote,
            extreme_volatility_pct=0.08,
        )
        proposal = _make_proposal()
        with pytest.importorskip("unittest.mock").patch(
            "src.ta_engine.get_full_analysis", new_callable=AsyncMock
        ) as mock_ta:
            mock_ta.return_value = {"signal": {"signal": "BUY", "score": 50}}
            result = await validator.validate(proposal)
        assert result.approved is False
        assert any("暴涨" in i for i in result.issues)

    @pytest.mark.asyncio
    async def test_low_confidence_rejects_full_validate(self, mock_quote):
        """Low confidence should cause full validate() to reject."""
        mock_quote.return_value = {"price": 150.0, "change_pct": 1.0}
        validator = DecisionValidator(
            get_quote_func=mock_quote,
            min_confidence_threshold=0.5,
        )
        proposal = _make_proposal(confidence=0.2)
        with pytest.importorskip("unittest.mock").patch(
            "src.ta_engine.get_full_analysis", new_callable=AsyncMock
        ) as mock_ta:
            mock_ta.return_value = {"signal": {"signal": "BUY", "score": 50}}
            result = await validator.validate(proposal)
        assert result.approved is False
        assert any("置信度" in i for i in result.issues)

    @pytest.mark.asyncio
    async def test_frequency_limit_records_timestamp(self, mock_quote):
        """Successful validate should record decision timestamp."""
        mock_quote.return_value = {"price": 150.0, "change_pct": 1.0}
        validator = DecisionValidator(
            get_quote_func=mock_quote,
            min_decision_interval_seconds=60,
        )
        proposal = _make_proposal()
        with pytest.importorskip("unittest.mock").patch(
            "src.ta_engine.get_full_analysis", new_callable=AsyncMock
        ) as mock_ta:
            mock_ta.return_value = {"signal": {"signal": "BUY", "score": 50}}
            result = await validator.validate(proposal)
        if result.approved:
            assert "AAPL" in validator._recent_decisions
