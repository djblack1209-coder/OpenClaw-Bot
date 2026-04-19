"""
Tests for TradingPipeline.execute_proposal() - full pipeline with mocks.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.auto_trader import TradingPipeline
from src.models import TradeProposal


class TestPipelineSkip:
    """HOLD/WAIT proposals are skipped."""

    @pytest.mark.asyncio
    async def test_hold_skipped(self, pipeline):
        proposal = TradeProposal(symbol="AAPL", action="HOLD", reason="wait")
        result = await pipeline.execute_proposal(proposal)
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_wait_skipped(self, pipeline):
        proposal = TradeProposal(symbol="AAPL", action="WAIT", reason="wait")
        result = await pipeline.execute_proposal(proposal)
        assert result["status"] == "skipped"


class TestPipelineRiskRejection:
    """Risk manager rejects trade."""

    @pytest.mark.asyncio
    async def test_risk_rejected_buy(self, pipeline):
        # Force risk rejection: no stop loss -> rejected
        proposal = TradeProposal(
            symbol="AAPL", action="BUY", quantity=5,
            entry_price=150.0, stop_loss=0, take_profit=162.0,
        )
        result = await pipeline.execute_proposal(proposal)
        assert result["status"] == "rejected"
        assert "止损" in result["reason"]

    @pytest.mark.asyncio
    async def test_zero_quantity_rejected(self, pipeline):
        proposal = TradeProposal(
            symbol="AAPL", action="BUY", quantity=0,
            entry_price=150.0, stop_loss=145.0, take_profit=162.0,
            signal_score=50,
        )
        result = await pipeline.execute_proposal(proposal)
        assert result["status"] == "rejected"
        assert "数量" in result["reason"]


class TestPipelineSuccessfulExecution:
    """Happy path: risk approved -> broker -> journal -> monitor -> notify."""

    @pytest.mark.asyncio
    async def test_buy_full_pipeline(self, pipeline, mock_broker, mock_journal, mock_monitor, mock_notify):
        # 使用较小数量，避免风控自动调整
        proposal = TradeProposal(
            symbol="AAPL", action="BUY", quantity=3,
            entry_price=150.0, stop_loss=145.0, take_profit=162.0,
            signal_score=50, decided_by="TestBot", reason="breakout",
        )
        result = await pipeline.execute_proposal(proposal)
        assert result["status"] == "executed"
        assert result["trade_id"] == 42
        mock_broker.buy.assert_called_once()
        mock_journal.open_trade.assert_called_once()
        mock_monitor.add_position.assert_called_once()
        mock_notify.assert_called()

    @pytest.mark.asyncio
    async def test_sell_executes_without_risk_check(self, pipeline, mock_broker):
        # SELL 现在也需要通过风控检查，需要设置 stop_loss
        proposal = TradeProposal(
            symbol="AAPL", action="SELL", quantity=3,
            entry_price=150.0, stop_loss=155.0, take_profit=140.0,
            decided_by="TestBot", reason="take profit",
        )
        result = await pipeline.execute_proposal(proposal)
        assert result["status"] == "executed"
        mock_broker.sell.assert_called_once()


class TestPipelineQuantityAdjustment:
    """Risk manager adjusts quantity."""

    @pytest.mark.asyncio
    async def test_quantity_adjusted_by_risk(self, pipeline):
        # Large qty that exceeds per-trade risk -> adjusted
        proposal = TradeProposal(
            symbol="AAPL", action="BUY", quantity=100,
            entry_price=150.0, stop_loss=145.0, take_profit=162.0,
            signal_score=50, decided_by="TestBot",
        )
        result = await pipeline.execute_proposal(proposal)
        assert result["status"] == "executed"
        # Quantity should have been adjusted down
        assert result["quantity"] <= 40  # max_risk=200, risk_per_share=5 -> 40


class TestPipelineBrokerFallback:
    """IBKR failure falls back to simulation portfolio."""

    @pytest.mark.asyncio
    async def test_broker_error_falls_back_to_sim(self, pipeline, mock_broker, mock_portfolio):
        mock_broker.buy.return_value = {"error": "connection lost"}
        # 使用较小数量，避免风控自动调整
        proposal = TradeProposal(
            symbol="AAPL", action="BUY", quantity=3,
            entry_price=150.0, stop_loss=145.0, take_profit=162.0,
            signal_score=50, decided_by="TestBot",
        )
        result = await pipeline.execute_proposal(proposal)
        # broker 回退到模拟组合后状态为 "simulated"
        assert result["status"] == "simulated"
        mock_portfolio.buy.assert_called_once()

    @pytest.mark.asyncio
    async def test_broker_exception_falls_back_to_sim(self, pipeline, mock_broker, mock_portfolio):
        mock_broker.buy.side_effect = ConnectionError("IBKR down")
        # 使用较小数量，避免风控自动调整
        proposal = TradeProposal(
            symbol="AAPL", action="BUY", quantity=3,
            entry_price=150.0, stop_loss=145.0, take_profit=162.0,
            signal_score=50, decided_by="TestBot",
        )
        result = await pipeline.execute_proposal(proposal)
        # broker 回退到模拟组合后状态为 "simulated"
        assert result["status"] == "simulated"
        mock_portfolio.buy.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_broker_uses_sim_directly(self, risk_manager, mock_journal, mock_portfolio, mock_monitor, mock_notify):
        pipe = TradingPipeline(
            risk_manager=risk_manager,
            broker=None,
            journal=mock_journal,
            portfolio=mock_portfolio,
            monitor=mock_monitor,
            notify_func=mock_notify,
        )
        # 使用较小数量，避免风控自动调整
        proposal = TradeProposal(
            symbol="AAPL", action="BUY", quantity=3,
            entry_price=150.0, stop_loss=145.0, take_profit=162.0,
            signal_score=50, decided_by="TestBot",
        )
        result = await pipe.execute_proposal(proposal)
        assert result["status"] == "executed"
        mock_portfolio.buy.assert_called_once()
