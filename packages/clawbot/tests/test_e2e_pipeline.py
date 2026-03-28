"""
端到端集成测试 - 完整交易管道
测试从 TradeProposal 到 Journal 记录的完整流程
"""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.utils import now_et

from src.models import TradeProposal
from src.auto_trader import TradingPipeline, AutoTrader
from src.risk_config import RiskConfig, RiskCheckResult
from src.risk_manager import RiskManager
from src.decision_validator import DecisionValidator, ValidationResult
from src.position_monitor import PositionMonitor, MonitoredPosition


# ============ Fixtures ============


@pytest.fixture
def risk_manager():
    """Fresh RiskManager with test config (capital=10000)."""
    config = RiskConfig(
        total_capital=10000.0,
        max_risk_per_trade_pct=0.02,
        daily_loss_limit=200.0,
        max_position_pct=0.30,
        max_total_exposure_pct=0.80,
        max_open_positions=5,
        min_risk_reward_ratio=2.0,
        min_signal_score=20,
        max_consecutive_losses=3,
        cooldown_minutes=30,
        trading_hours_enabled=False,
        blacklist=["SCAM"],
        extreme_market_cooldown_minutes=60,
    )
    rm = RiskManager(config=config, journal=None)
    # Pin the date so _refresh_today_pnl doesn't hit a real journal
    rm._last_pnl_update = now_et().strftime("%Y-%m-%d")
    rm._last_refresh_ts = now_et()
    return rm


@pytest.fixture
def mock_journal():
    """Mocked TradingJournal."""
    j = MagicMock()
    j.get_today_pnl.return_value = {"pnl": 0.0, "trades": 0}
    j.open_trade.return_value = 42
    j.close_trade.return_value = {"trade_id": 42, "pnl": 10.0}
    j.get_open_trades.return_value = []
    return j


@pytest.fixture
def mock_portfolio():
    """Mocked portfolio with get_positions, buy, sell."""
    p = MagicMock()
    p.get_positions.return_value = []
    p.buy.return_value = {"status": "ok", "symbol": "AAPL", "quantity": 5}
    p.sell.return_value = {"status": "ok", "symbol": "AAPL", "quantity": 5}
    return p


@pytest.fixture
def mock_broker():
    """AsyncMock broker with buy/sell."""
    b = AsyncMock()
    b.buy.return_value = {"status": "filled", "avg_price": 150.0, "quantity": 5}
    b.sell.return_value = {"status": "filled", "avg_price": 155.0, "quantity": 5}
    # is_connected is a sync method on the real broker — use MagicMock to avoid
    # returning a coroutine (which is always truthy and triggers RuntimeWarning).
    b.is_connected = MagicMock(return_value=True)
    return b


@pytest.fixture
def mock_monitor():
    """Mocked PositionMonitor."""
    m = MagicMock()
    m.add_position.return_value = None
    m.positions = {}
    return m


@pytest.fixture
def mock_notify():
    """Async notification function mock."""
    return AsyncMock()


@pytest.fixture
def pipeline(risk_manager, mock_broker, mock_journal, mock_portfolio, mock_monitor, mock_notify):
    """TradingPipeline with all mocked dependencies."""
    return TradingPipeline(
        risk_manager=risk_manager,
        broker=mock_broker,
        journal=mock_journal,
        portfolio=mock_portfolio,
        monitor=mock_monitor,
        notify_func=mock_notify,
    )


@pytest.fixture
def validator(mock_portfolio):
    """DecisionValidator with mocked quote function and portfolio."""
    async def mock_get_quote(symbol):
        return {"price": 150.0, "timestamp": time.time()}

    return DecisionValidator(
        get_quote_func=mock_get_quote,
        portfolio=mock_portfolio,
        price_tolerance_pct=0.05,
        max_price_age_seconds=300,
    )


# ============ Test 1: Full Pipeline BUY Success ============


class TestFullPipelineBuySuccess:
    """Happy path: valid BUY proposal goes through
    validator -> risk check -> execution -> journal -> monitor."""

    @pytest.mark.asyncio
    async def test_full_pipeline_buy_success(
        self, pipeline, validator, mock_broker, mock_journal, mock_monitor, mock_notify
    ):
        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=162.0,
            signal_score=60,
            confidence=0.7,
            reason="Strong momentum breakout",
            decided_by="TestBot",
        )

        # Step 1: DecisionValidator
        with patch("src.ta_engine.get_full_analysis", new_callable=AsyncMock) as mock_ta:
            mock_ta.return_value = {
                "signal": {"signal": "BUY", "score": 55},
            }
            validation = await validator.validate(proposal)

        assert validation.approved is True
        assert len(validation.issues) == 0

        # Step 2+3+4+5: Pipeline execution (risk -> broker -> journal -> monitor)
        result = await pipeline.execute_proposal(proposal)

        assert result["status"] == "executed"
        assert result["symbol"] == "AAPL"
        assert result["trade_id"] == 42

        # Broker was called
        mock_broker.buy.assert_called_once_with(
            symbol="AAPL", quantity=5, decided_by="TestBot", reason="Strong momentum breakout",
        )

        # Journal recorded the trade
        mock_journal.open_trade.assert_called_once()
        call_kwargs = mock_journal.open_trade.call_args
        assert call_kwargs[1]["symbol"] == "AAPL" or call_kwargs[0][0] == "AAPL"

        # Monitor registered the position
        mock_monitor.add_position.assert_called_once()
        mon_pos = mock_monitor.add_position.call_args[0][0]
        assert isinstance(mon_pos, MonitoredPosition)
        assert mon_pos.symbol == "AAPL"
        assert mon_pos.stop_loss == 145.0
        assert mon_pos.take_profit == 162.0

        # Notification sent
        mock_notify.assert_called()


# ============ Test 2: Full Pipeline SELL Success ============


class TestFullPipelineSellSuccess:
    """Happy path for SELL - skips risk check, executes via broker."""

    @pytest.mark.asyncio
    async def test_full_pipeline_sell_success(
        self, pipeline, mock_broker, mock_journal, mock_monitor
    ):
        proposal = TradeProposal(
            symbol="AAPL",
            action="SELL",
            quantity=5,
            entry_price=155.0,
            decided_by="TestBot",
            reason="Take profit target hit",
        )

        result = await pipeline.execute_proposal(proposal)

        assert result["status"] == "executed"
        assert result["symbol"] == "AAPL"

        # Broker sell was called
        mock_broker.sell.assert_called_once_with(
            symbol="AAPL", quantity=5, decided_by="TestBot", reason="Take profit target hit",
        )

        # SELL does not record to journal (pipeline only journals BUY)
        mock_journal.open_trade.assert_not_called()

        # SELL does not register with monitor (pipeline only monitors BUY)
        mock_monitor.add_position.assert_not_called()


# ============ Test 3: Pipeline Rejected by Validator ============


class TestPipelineRejectedByValidator:
    """Proposal with bad prices rejected by DecisionValidator."""

    @pytest.mark.asyncio
    async def test_pipeline_rejected_by_validator(self, validator, pipeline):
        # Entry price way off from live price ($150) -> validator rejects
        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=200.0,  # 33% deviation from $150 live price
            stop_loss=195.0,
            take_profit=220.0,
            signal_score=50,
            decided_by="TestBot",
        )

        with patch("src.ta_engine.get_full_analysis", new_callable=AsyncMock) as mock_ta:
            mock_ta.return_value = None
            validation = await validator.validate(proposal)

        # Validator should reject due to price deviation > 5%
        assert validation.approved is False
        assert len(validation.issues) > 0
        assert any("偏差" in issue for issue in validation.issues)

        # Since validator rejected, we should NOT send to pipeline
        # (in real code the caller checks validation.approved first)


# ============ Test 4: Pipeline Rejected by Risk Manager ============


class TestPipelineRejectedByRisk:
    """Proposal rejected by RiskManager (daily loss limit hit)."""

    @pytest.mark.asyncio
    async def test_pipeline_rejected_by_risk_daily_loss(self, pipeline, risk_manager):
        # Simulate daily loss limit already hit
        risk_manager._today_pnl = -200.0  # At the limit

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

        assert result["status"] == "rejected"
        assert "日亏损限额" in result["reason"]

    @pytest.mark.asyncio
    async def test_pipeline_rejected_no_stop_loss(self, pipeline):
        """BUY without stop loss is rejected by risk manager."""
        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=150.0,
            stop_loss=0,  # No stop loss
            take_profit=162.0,
            signal_score=50,
        )

        result = await pipeline.execute_proposal(proposal)

        assert result["status"] == "rejected"
        assert "止损" in result["reason"]

    @pytest.mark.asyncio
    async def test_pipeline_rejected_bad_risk_reward(self, pipeline):
        """Risk/reward ratio below 2:1 is rejected."""
        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=150.0,
            stop_loss=145.0,   # risk = $5
            take_profit=153.0,  # reward = $3 -> RR = 0.6:1
            signal_score=50,
        )

        result = await pipeline.execute_proposal(proposal)

        assert result["status"] == "rejected"
        assert "风险收益比" in result["reason"]


# ============ Test 5: Pipeline Duplicate Position Warning ============


class TestPipelineDuplicatePositionWarning:
    """Validator warns about duplicate but allows the trade."""

    @pytest.mark.asyncio
    async def test_pipeline_duplicate_position_warning(self, validator, mock_portfolio):
        # Portfolio already holds AAPL
        mock_portfolio.get_positions.return_value = [
            {"symbol": "AAPL", "quantity": 10, "status": "open", "avg_price": 148.0},
        ]

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

        with patch("src.ta_engine.get_full_analysis", new_callable=AsyncMock) as mock_ta:
            mock_ta.return_value = None
            validation = await validator.validate(proposal)

        # Should still be approved (duplicate is a warning, not an issue)
        assert validation.approved is True
        # But should have a warning about existing position
        assert any("已持有" in w for w in validation.warnings)


# ============ Test 6: Pipeline Extreme Market Halt ============


class TestPipelineExtremeMarketHalt:
    """Risk manager in extreme cooldown rejects all trades."""

    @pytest.mark.asyncio
    async def test_pipeline_extreme_market_halt(self, pipeline, risk_manager):
        # Trigger extreme market event
        risk_manager.record_extreme_event(
            event_type="extreme",
            details="VIX spike detected",
        )

        assert risk_manager.is_in_extreme_cooldown() is True

        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=162.0,
            signal_score=60,
            decided_by="TestBot",
        )

        result = await pipeline.execute_proposal(proposal)

        assert result["status"] == "rejected"
        assert "极端行情" in result["reason"]

    @pytest.mark.asyncio
    async def test_extreme_cooldown_expires(self, pipeline, risk_manager):
        """After cooldown period, trades should be allowed again."""
        # Set extreme event in the past (beyond cooldown)
        risk_manager._last_extreme_time = now_et() - timedelta(minutes=61)

        assert risk_manager.is_in_extreme_cooldown() is False

        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=162.0,
            signal_score=60,
            decided_by="TestBot",
        )

        result = await pipeline.execute_proposal(proposal)
        assert result["status"] == "executed"


# ============ Test 7: Pipeline Logical Inconsistency ============


class TestPipelineLogicalInconsistency:
    """SL > entry price for BUY rejected by validator."""

    @pytest.mark.asyncio
    async def test_pipeline_logical_inconsistency_sl_above_entry(self, validator):
        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=150.0,
            stop_loss=155.0,  # SL above entry for BUY -> logical error
            take_profit=162.0,
            signal_score=50,
        )

        with patch("src.ta_engine.get_full_analysis", new_callable=AsyncMock) as mock_ta:
            mock_ta.return_value = None
            validation = await validator.validate(proposal)

        assert validation.approved is False
        assert any("止损" in issue and "入场价" in issue for issue in validation.issues)

    @pytest.mark.asyncio
    async def test_pipeline_logical_inconsistency_tp_below_entry(self, validator):
        """Take profit below entry for BUY is rejected."""
        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=148.0,  # TP below entry for BUY -> logical error
            signal_score=50,
        )

        with patch("src.ta_engine.get_full_analysis", new_callable=AsyncMock) as mock_ta:
            mock_ta.return_value = None
            validation = await validator.validate(proposal)

        assert validation.approved is False
        assert any("止盈" in issue for issue in validation.issues)

    @pytest.mark.asyncio
    async def test_pipeline_logical_inconsistency_sell_sl_below_entry(self, validator):
        """For SELL, stop loss below entry is a logical error."""
        proposal = TradeProposal(
            symbol="AAPL",
            action="SELL",
            quantity=5,
            entry_price=150.0,
            stop_loss=145.0,  # SL below entry for SELL -> logical error
            take_profit=140.0,
            signal_score=50,
        )

        with patch("src.ta_engine.get_full_analysis", new_callable=AsyncMock) as mock_ta:
            mock_ta.return_value = None
            validation = await validator.validate(proposal)

        assert validation.approved is False
        assert any("做空" in issue and "止损" in issue for issue in validation.issues)


# ============ Test 8: Full Cycle Scan to Execution ============


class TestFullCycleScanToExecution:
    """Simulates AutoTrader.run_cycle_once with mocked market data."""

    @pytest.mark.asyncio
    async def test_full_cycle_scan_to_execution(
        self, pipeline, risk_manager, mock_notify
    ):
        # Mock scan function returning market signals
        async def mock_scan():
            return [
                {
                    "symbol": "AAPL",
                    "score": 65,
                    "price": 150.0,
                    "trend": "up",
                    "rsi_6": 55,
                    "atr_pct": 2.5,
                    "reasons": ["MACD bullish crossover", "Volume surge"],
                },
                {
                    "symbol": "MSFT",
                    "score": 45,
                    "price": 400.0,
                    "trend": "sideways",
                    "rsi_6": 50,
                    "atr_pct": 1.8,
                    "reasons": ["RSI bounce"],
                },
                {
                    "symbol": "JUNK",
                    "score": 10,  # Below threshold, should be filtered
                    "price": 5.0,
                    "trend": "down",
                    "rsi_6": 80,
                    "atr_pct": 5.0,
                },
            ]

        trader = AutoTrader(
            pipeline=pipeline,
            scan_func=mock_scan,
            risk_manager=risk_manager,
            notify_func=mock_notify,
            max_trades_per_cycle=2,
            auto_mode=True,
        )

        cycle_result = await trader.run_cycle_once()

        # Should have scanned 3 signals
        assert cycle_result["scanned"] == 3

        # JUNK filtered out (score < 30), so 2 candidates
        assert cycle_result["candidates"] == 2

        # Proposals generated for top candidates
        assert cycle_result["proposals"] >= 1

        # At least one trade executed (auto_mode=True)
        assert cycle_result["executed"] >= 1

    @pytest.mark.asyncio
    async def test_full_cycle_no_signals(self, pipeline, risk_manager):
        """Cycle with no scan results ends gracefully."""
        async def empty_scan():
            return []

        trader = AutoTrader(
            pipeline=pipeline,
            scan_func=empty_scan,
            risk_manager=risk_manager,
            auto_mode=True,
        )

        cycle_result = await trader.run_cycle_once()

        assert cycle_result["scanned"] == 0
        assert cycle_result["executed"] == 0

    @pytest.mark.asyncio
    async def test_full_cycle_all_filtered(self, pipeline, risk_manager):
        """All signals below threshold are filtered out."""
        async def weak_scan():
            return [
                {"symbol": "X", "score": 10, "price": 5.0, "trend": "down", "rsi_6": 80},
                {"symbol": "Y", "score": 15, "price": 3.0, "trend": "strong_down", "rsi_6": 40},
            ]

        trader = AutoTrader(
            pipeline=pipeline,
            scan_func=weak_scan,
            risk_manager=risk_manager,
            auto_mode=True,
        )

        cycle_result = await trader.run_cycle_once()

        assert cycle_result["scanned"] == 2
        assert cycle_result["candidates"] == 0
        assert cycle_result["executed"] == 0


# ============ Additional Integration Scenarios ============


class TestPipelineQuantityAdjustment:
    """Risk manager adjusts quantity to stay within risk limits."""

    @pytest.mark.asyncio
    async def test_quantity_adjusted_down(
        self, pipeline, mock_broker, mock_journal, mock_monitor
    ):
        # quantity=100, risk_per_share=$5, max_risk=$200 -> adjusted to 40
        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=100,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=162.0,
            signal_score=50,
            decided_by="TestBot",
        )

        result = await pipeline.execute_proposal(proposal)

        assert result["status"] == "executed"
        # max_risk = 10000 * 0.02 = 200, risk_per_share = 5 -> max 40 shares
        assert result["quantity"] <= 40


class TestPipelineConsecutiveLossCooldown:
    """Consecutive losses trigger cooldown, blocking new trades."""

    @pytest.mark.asyncio
    async def test_consecutive_loss_cooldown(self, pipeline, risk_manager):
        # Record 3 consecutive losses to trigger cooldown
        risk_manager.record_trade_result(-50.0)
        risk_manager.record_trade_result(-30.0)
        risk_manager.record_trade_result(-20.0)

        assert risk_manager._consecutive_losses >= 3
        assert risk_manager._is_in_cooldown() is True

        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=162.0,
            signal_score=60,
        )

        result = await pipeline.execute_proposal(proposal)

        assert result["status"] == "rejected"
        assert "熔断" in result["reason"]


class TestValidatorAndPipelineIntegration:
    """End-to-end: validator approves -> pipeline executes -> all steps verified."""

    @pytest.mark.asyncio
    async def test_validator_approve_then_pipeline_execute(
        self, validator, pipeline, mock_broker, mock_journal, mock_monitor, mock_notify
    ):
        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=162.0,
            signal_score=55,
            confidence=0.7,
            reason="Breakout confirmed",
            decided_by="AI_Team",
        )

        # Phase 1: Validate
        with patch("src.ta_engine.get_full_analysis", new_callable=AsyncMock) as mock_ta:
            mock_ta.return_value = {"signal": {"signal": "BUY", "score": 50}}
            validation = await validator.validate(proposal)

        assert validation.approved is True

        # Phase 2: Execute through pipeline
        result = await pipeline.execute_proposal(proposal)

        assert result["status"] == "executed"
        assert result["trade_id"] == 42

        # Verify full chain
        mock_broker.buy.assert_called_once()
        mock_journal.open_trade.assert_called_once()
        mock_monitor.add_position.assert_called_once()
        mock_notify.assert_called()

        # Verify monitor received correct position data
        mon_pos = mock_monitor.add_position.call_args[0][0]
        assert mon_pos.trade_id == 42
        assert mon_pos.symbol == "AAPL"
        assert mon_pos.side == "BUY"
        assert mon_pos.quantity == 5
        assert mon_pos.entry_price == 150.0
        assert mon_pos.stop_loss == 145.0
        assert mon_pos.take_profit == 162.0

    @pytest.mark.asyncio
    async def test_validator_reject_prevents_pipeline(self, validator, pipeline, mock_broker):
        """When validator rejects, pipeline should not be called."""
        proposal = TradeProposal(
            symbol="AAPL",
            action="BUY",
            quantity=5,
            entry_price=200.0,  # Way off from $150 live price
            stop_loss=195.0,
            take_profit=220.0,
            signal_score=50,
        )

        with patch("src.ta_engine.get_full_analysis", new_callable=AsyncMock) as mock_ta:
            mock_ta.return_value = None
            validation = await validator.validate(proposal)

        assert validation.approved is False

        # In real code, caller checks validation.approved before calling pipeline
        # Verify broker was never called
        mock_broker.buy.assert_not_called()


class TestBrokerFallbackToSimulation:
    """When broker fails, pipeline falls back to simulation portfolio."""

    @pytest.mark.asyncio
    async def test_broker_error_fallback(
        self, pipeline, mock_broker, mock_portfolio, mock_journal
    ):
        mock_broker.buy.return_value = {"error": "IBKR connection lost"}

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

        assert result["status"] == "executed"
        # Broker was attempted
        mock_broker.buy.assert_called_once()
        # Fell back to simulation portfolio
        mock_portfolio.buy.assert_called_once()

    @pytest.mark.asyncio
    async def test_broker_exception_fallback(
        self, pipeline, mock_broker, mock_portfolio
    ):
        mock_broker.buy.side_effect = ConnectionError("Network unreachable")

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

        assert result["status"] == "executed"
        mock_portfolio.buy.assert_called_once()
