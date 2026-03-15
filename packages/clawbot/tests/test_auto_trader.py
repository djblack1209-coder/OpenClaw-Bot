"""
Tests for AutoTrader._filter_candidates and _generate_proposal.
"""
import pytest
from unittest.mock import MagicMock

from src.auto_trader import AutoTrader
from src.models import TradeProposal


class TestFilterCandidates:
    """AutoTrader._filter_candidates - pure filtering logic."""

    def _make_trader(self):
        return AutoTrader()

    def test_high_score_passes(self):
        trader = self._make_trader()
        signals = [{"symbol": "AAPL", "score": 60, "trend": "up", "rsi_6": 50}]
        result = trader._filter_candidates(signals)
        assert len(result) == 1

    def test_low_score_filtered(self):
        trader = self._make_trader()
        signals = [{"symbol": "AAPL", "score": 15, "trend": "up", "rsi_6": 50}]
        result = trader._filter_candidates(signals)
        assert len(result) == 0

    def test_score_threshold_20(self):
        trader = self._make_trader()
        signals = [
            {"symbol": "A", "score": 19, "trend": "up", "rsi_6": 50},
            {"symbol": "B", "score": 20, "trend": "up", "rsi_6": 50},
            {"symbol": "C", "score": 21, "trend": "up", "rsi_6": 50},
        ]
        result = trader._filter_candidates(signals)
        assert len(result) == 2
        assert result[0]["symbol"] == "C"  # Sorted by score desc

    def test_strong_downtrend_filtered(self):
        trader = self._make_trader()
        signals = [
            {"symbol": "A", "score": 60, "trend": "strong_down", "rsi_6": 50},
        ]
        result = trader._filter_candidates(signals)
        assert len(result) == 0

    def test_down_trend_passes(self):
        """down trend is now allowed (only strong_down is filtered)"""
        trader = self._make_trader()
        signals = [
            {"symbol": "B", "score": 60, "trend": "down", "rsi_6": 50},
        ]
        result = trader._filter_candidates(signals)
        assert len(result) == 1

    def test_uptrend_passes(self):
        trader = self._make_trader()
        signals = [
            {"symbol": "A", "score": 60, "trend": "strong_up", "rsi_6": 50},
            {"symbol": "B", "score": 60, "trend": "up", "rsi_6": 50},
            {"symbol": "C", "score": 60, "trend": "sideways", "rsi_6": 50},
        ]
        result = trader._filter_candidates(signals)
        assert len(result) == 3

    def test_overbought_rsi_filtered(self):
        trader = self._make_trader()
        signals = [{"symbol": "AAPL", "score": 60, "trend": "up", "rsi_6": 85}]
        result = trader._filter_candidates(signals)
        assert len(result) == 0

    def test_rsi_threshold_80(self):
        trader = self._make_trader()
        signals = [
            {"symbol": "A", "score": 60, "trend": "up", "rsi_6": 79},
            {"symbol": "B", "score": 60, "trend": "up", "rsi_6": 80},
            {"symbol": "C", "score": 60, "trend": "up", "rsi_6": 81},
        ]
        result = trader._filter_candidates(signals)
        # 80 is not > 80, so passes; 81 > 80, filtered
        assert len(result) == 2

    def test_sorted_by_score_descending(self):
        trader = self._make_trader()
        signals = [
            {"symbol": "A", "score": 40, "trend": "up", "rsi_6": 50},
            {"symbol": "B", "score": 80, "trend": "up", "rsi_6": 50},
            {"symbol": "C", "score": 60, "trend": "up", "rsi_6": 50},
        ]
        result = trader._filter_candidates(signals)
        assert [r["symbol"] for r in result] == ["B", "C", "A"]

    def test_empty_signals(self):
        trader = self._make_trader()
        result = trader._filter_candidates([])
        assert result == []

    def test_missing_fields_use_defaults(self):
        trader = self._make_trader()
        signals = [{"symbol": "AAPL"}]  # Missing score, trend, rsi_6
        result = trader._filter_candidates(signals)
        # score=0 < 20 -> filtered
        assert len(result) == 0


class TestGenerateProposal:
    """AutoTrader._generate_proposal - proposal generation."""

    @pytest.mark.asyncio
    async def test_basic_proposal(self):
        rm = MagicMock()
        rm.calc_safe_quantity.return_value = {"shares": 10}
        trader = AutoTrader(risk_manager=rm)
        candidate = {
            "symbol": "AAPL", "score": 60, "price": 150.0, "atr_pct": 2.0,
            "reasons": ["MACD bullish", "Volume surge"],
        }
        proposal = await trader._generate_proposal(candidate)
        assert proposal is not None
        assert proposal.symbol == "AAPL"
        assert proposal.action == "BUY"
        assert proposal.quantity == 10
        assert proposal.stop_loss > 0
        assert proposal.take_profit > proposal.entry_price

    @pytest.mark.asyncio
    async def test_zero_price_returns_none(self):
        trader = AutoTrader()
        candidate = {"symbol": "AAPL", "score": 60, "price": 0}
        proposal = await trader._generate_proposal(candidate)
        assert proposal is None

    @pytest.mark.asyncio
    async def test_no_risk_manager_uses_fallback_qty(self):
        trader = AutoTrader(risk_manager=None)
        candidate = {"symbol": "AAPL", "score": 60, "price": 150.0, "atr_pct": 2.0}
        proposal = await trader._generate_proposal(candidate)
        assert proposal is not None
        assert proposal.quantity >= 1  # Fallback: max(1, int(400/150)) = 2

    @pytest.mark.asyncio
    async def test_atr_affects_stop_loss(self):
        rm = MagicMock()
        rm.calc_safe_quantity.return_value = {"shares": 5}
        trader = AutoTrader(risk_manager=rm)

        # Low ATR
        c1 = {"symbol": "AAPL", "score": 60, "price": 100.0, "atr_pct": 1.0}
        p1 = await trader._generate_proposal(c1)

        # High ATR
        c2 = {"symbol": "AAPL", "score": 60, "price": 100.0, "atr_pct": 5.0}
        p2 = await trader._generate_proposal(c2)

        # Higher ATR -> wider stop loss (lower SL price)
        assert p2.stop_loss < p1.stop_loss
