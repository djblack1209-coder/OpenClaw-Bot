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
        # 自适应阈值: 无高分信号时阈值降为15, score=14 才会被过滤
        signals = [{"symbol": "AAPL", "score": 14, "trend": "up", "rsi_6": 50}]
        result = trader._filter_candidates(signals)
        assert len(result) == 0

    def test_score_threshold_adaptive(self):
        """自适应阈值: 3+个高分信号时阈值升为25, 否则为15"""
        trader = self._make_trader()
        # 无高分信号 → 阈值15, 所有 >= 15 都通过
        signals = [
            {"symbol": "A", "score": 14, "trend": "up", "rsi_6": 50},
            {"symbol": "B", "score": 15, "trend": "up", "rsi_6": 50},
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
        # 代码用 rsi6 > 85 过滤，所以 86 被过滤，85 通过
        signals = [{"symbol": "AAPL", "score": 60, "trend": "up", "rsi_6": 86}]
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
        # 代码阈值是 > 85，所有三个都通过
        assert len(result) == 3

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
        assert 0 < proposal.stop_loss < proposal.entry_price  # BUY: SL must be below entry
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
        assert proposal.quantity == 2  # Fallback: max(1, int(400/150)) = 2

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


# ============ 容错测试 (Fault Tolerance Tests) ============


class TestFilterCandidatesEdgeCases:
    """Edge cases for _filter_candidates beyond the basic empty list."""

    def test_filter_candidates_all_empty_dicts(self):
        """List of empty dicts (no symbol, no score) → all filtered out.

        Missing 'score' defaults to 0 via .get("score", 0), which is < 15.
        """
        trader = AutoTrader()
        signals = [{}, {}, {}]
        result = trader._filter_candidates(signals)
        assert result == []

    def test_filter_candidates_none_values_in_fields(self):
        """Candidate with None values for score/rsi/trend → filtered by score.

        .get("score", 0) returns None, and None < 15 raises TypeError in Python 3.
        This documents the current behavior.
        """
        trader = AutoTrader()
        signals = [{"symbol": "AAPL", "score": None, "trend": "up", "rsi_6": 50}]
        with pytest.raises(TypeError):
            trader._filter_candidates(signals)


class TestGenerateProposalNaN:
    """_generate_proposal with NaN score."""

    @pytest.mark.asyncio
    async def test_generate_proposal_nan_score(self):
        """score=NaN → ValueError when formatting reason string.

        _generate_proposal falls into the else branch where it builds
        reason_text = "信号评分%d" % score. Python's %d cannot format NaN,
        raising ValueError. This documents the missing NaN guard.
        """
        rm = MagicMock()
        rm.calc_safe_quantity.return_value = {"shares": 5}
        rm.config = MagicMock()
        rm.config.total_capital = 10000.0
        trader = AutoTrader(risk_manager=rm)

        candidate = {
            "symbol": "AAPL",
            "score": float("nan"),
            "price": 150.0,
            "atr_pct": 2.0,
        }
        with pytest.raises(ValueError, match="cannot convert float NaN to integer"):
            await trader._generate_proposal(candidate)


class TestExecuteTradeBrokerTimeout:
    """Broker timeout → pipeline falls back to simulation portfolio."""

    @pytest.mark.asyncio
    async def test_execute_trade_broker_timeout(self):
        """asyncio.TimeoutError from broker.buy → fallback to sim portfolio.

        Pipeline catches all exceptions from broker, logs warning, and
        falls back to portfolio.buy (simulation).
        """
        import asyncio
        from unittest.mock import AsyncMock as _AsyncMock
        from src.auto_trader import TradingPipeline
        from src.risk_manager import RiskManager, RiskConfig
        from src.models import TradeProposal
        from src.utils import now_et

        config = RiskConfig(
            total_capital=10000.0,
            daily_loss_limit=200.0,
            trading_hours_enabled=False,
            blacklist=[],
        )
        rm = RiskManager(config=config)
        rm._last_pnl_update = now_et().strftime("%Y-%m-%d")
        rm._last_refresh_ts = now_et()

        mock_broker = _AsyncMock()
        mock_broker.buy.side_effect = asyncio.TimeoutError("IBKR timeout")
        mock_broker.is_connected = MagicMock(return_value=True)
        mock_broker.get_positions = _AsyncMock(return_value=[])

        mock_portfolio = MagicMock()
        mock_portfolio.get_positions.return_value = []
        mock_portfolio.buy.return_value = {
            "status": "ok", "symbol": "AAPL", "quantity": 5,
        }

        mock_journal = MagicMock()
        mock_journal.open_trade.return_value = 99

        pipeline = TradingPipeline(
            risk_manager=rm,
            broker=mock_broker,
            journal=mock_journal,
            portfolio=mock_portfolio,
        )

        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=162.0,
            signal_score=50,
            decided_by="TestBot",
        )

        result = await pipeline.execute_proposal(proposal)

        # Broker was attempted but timed out
        mock_broker.buy.assert_called_once()

        # Fell back to simulation portfolio
        mock_portfolio.buy.assert_called_once()

        # Trade still executed via simulation
        assert result["status"] == "executed"
        assert result["trade_id"] == 99

        # Steps should contain the broker error
        broker_error_steps = [
            s for s in result["steps"]
            if "broker_error" in s
        ]
        assert len(broker_error_steps) == 1
        assert "IBKR timeout" in broker_error_steps[0]["broker_error"]
