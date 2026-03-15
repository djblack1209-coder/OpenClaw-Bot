"""
Tests for pipeline_helper.execute_trade_via_pipeline().
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.pipeline_helper import execute_trade_via_pipeline, DEFAULT_SL_PCT, DEFAULT_TP_PCT, MIN_RR_RATIO


@pytest.fixture
def mock_pipeline():
    """Mock TradingPipeline for pipeline_helper tests."""
    p = AsyncMock()
    p.execute_proposal.return_value = {
        "status": "executed",
        "trade_id": 99,
        "quantity": 5,
        "symbol": "AAPL",
    }
    return p


@pytest.fixture
def mock_quote_func():
    f = AsyncMock()
    f.return_value = {"price": 150.0}
    return f


class TestExecuteTradeViaPipeline:
    """Main function tests."""

    @pytest.mark.asyncio
    async def test_successful_execution(self, mock_pipeline, mock_quote_func):
        trade = {"action": "BUY", "symbol": "AAPL", "qty": 5, "reason": "test",
                 "entry_price": 150.0, "stop_loss": 145.0, "take_profit": 162.0}
        result = await execute_trade_via_pipeline(trade, mock_pipeline, mock_quote_func)
        assert "[OK]" in result
        assert "AAPL" in result
        mock_pipeline.execute_proposal.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_pipeline_returns_error(self, mock_quote_func):
        trade = {"action": "BUY", "symbol": "AAPL", "qty": 5}
        result = await execute_trade_via_pipeline(trade, None, mock_quote_func)
        assert "not initialized" in result

    @pytest.mark.asyncio
    async def test_rejected_trade(self, mock_pipeline, mock_quote_func):
        mock_pipeline.execute_proposal.return_value = {
            "status": "rejected", "reason": "daily limit"
        }
        trade = {"action": "BUY", "symbol": "AAPL", "qty": 5,
                 "entry_price": 150.0, "stop_loss": 145.0, "take_profit": 162.0}
        result = await execute_trade_via_pipeline(trade, mock_pipeline, mock_quote_func)
        assert "RISK REJECTED" in result

    @pytest.mark.asyncio
    async def test_skipped_trade(self, mock_pipeline, mock_quote_func):
        mock_pipeline.execute_proposal.return_value = {
            "status": "skipped", "reason": "AI hold"
        }
        trade = {"action": "HOLD", "symbol": "AAPL", "qty": 0}
        result = await execute_trade_via_pipeline(trade, mock_pipeline, mock_quote_func)
        assert "SKIP" in result


class TestAutoFillEntryPrice:
    """Auto-fill entry price from live quote."""

    @pytest.mark.asyncio
    async def test_zero_entry_fetches_quote(self, mock_pipeline, mock_quote_func):
        trade = {"action": "BUY", "symbol": "AAPL", "qty": 5,
                 "entry_price": 0, "stop_loss": 0, "take_profit": 0}
        await execute_trade_via_pipeline(trade, mock_pipeline, mock_quote_func)
        mock_quote_func.assert_called_once_with("AAPL")
        # Verify the proposal got the price
        call_args = mock_pipeline.execute_proposal.call_args
        proposal = call_args[0][0]
        assert proposal.entry_price == 150.0

    @pytest.mark.asyncio
    async def test_nonzero_entry_skips_quote(self, mock_pipeline, mock_quote_func):
        trade = {"action": "BUY", "symbol": "AAPL", "qty": 5,
                 "entry_price": 155.0, "stop_loss": 150.0, "take_profit": 168.0}
        await execute_trade_via_pipeline(trade, mock_pipeline, mock_quote_func)
        mock_quote_func.assert_not_called()


class TestAutoFillStopLoss:
    """Auto-fill SL/TP when missing."""

    @pytest.mark.asyncio
    @patch("src.pipeline_helper._get_atr_based_levels")
    async def test_atr_fills_sl_tp(self, mock_atr, mock_pipeline, mock_quote_func):
        mock_atr.return_value = {"stop_loss": 145.0, "take_profit": 162.0, "source": "ATR"}
        trade = {"action": "BUY", "symbol": "AAPL", "qty": 5,
                 "entry_price": 150.0, "stop_loss": 0, "take_profit": 0}
        await execute_trade_via_pipeline(trade, mock_pipeline, mock_quote_func)
        call_args = mock_pipeline.execute_proposal.call_args
        proposal = call_args[0][0]
        assert proposal.stop_loss == 145.0
        assert proposal.take_profit == 162.0

    @pytest.mark.asyncio
    @patch("src.pipeline_helper._get_atr_based_levels")
    async def test_default_pct_when_no_atr(self, mock_atr, mock_pipeline, mock_quote_func):
        mock_atr.return_value = {}  # ATR failed
        trade = {"action": "BUY", "symbol": "AAPL", "qty": 5,
                 "entry_price": 150.0, "stop_loss": 0, "take_profit": 0}
        await execute_trade_via_pipeline(trade, mock_pipeline, mock_quote_func)
        call_args = mock_pipeline.execute_proposal.call_args
        proposal = call_args[0][0]
        expected_sl = round(150.0 * (1 - DEFAULT_SL_PCT), 2)
        expected_tp = round(150.0 * (1 + DEFAULT_TP_PCT), 2)
        assert proposal.stop_loss == expected_sl
        assert proposal.take_profit == expected_tp


class TestRiskRewardAdjustment:
    """Auto-adjust TP to meet minimum R:R ratio."""

    @pytest.mark.asyncio
    @patch("src.pipeline_helper._get_atr_based_levels")
    async def test_tp_adjusted_for_min_rr(self, mock_atr, mock_pipeline, mock_quote_func):
        # SL=$145 -> risk=$5. TP=$152 -> reward=$2 -> RR=0.4 < 2.0
        # Should adjust TP to 150 + 5*2 = $160
        mock_atr.return_value = {}
        trade = {"action": "BUY", "symbol": "AAPL", "qty": 5,
                 "entry_price": 150.0, "stop_loss": 145.0, "take_profit": 152.0}
        await execute_trade_via_pipeline(trade, mock_pipeline, mock_quote_func)
        call_args = mock_pipeline.execute_proposal.call_args
        proposal = call_args[0][0]
        assert proposal.take_profit == 160.0  # 150 + 5*2.0

    @pytest.mark.asyncio
    @patch("src.pipeline_helper._get_atr_based_levels")
    async def test_good_rr_not_adjusted(self, mock_atr, mock_pipeline, mock_quote_func):
        mock_atr.return_value = {}
        trade = {"action": "BUY", "symbol": "AAPL", "qty": 5,
                 "entry_price": 150.0, "stop_loss": 145.0, "take_profit": 165.0}
        await execute_trade_via_pipeline(trade, mock_pipeline, mock_quote_func)
        call_args = mock_pipeline.execute_proposal.call_args
        proposal = call_args[0][0]
        assert proposal.take_profit == 165.0  # Unchanged
