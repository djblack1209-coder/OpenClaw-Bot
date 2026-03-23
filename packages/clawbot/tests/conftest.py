"""
Shared fixtures for ClawBot tests.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.risk_manager import RiskManager, RiskConfig, RiskCheckResult
from src.models import TradeProposal
from src.auto_trader import TradingPipeline
from src.position_monitor import PositionMonitor, MonitoredPosition, ExitReason
from src.utils import now_et


# ============ RiskManager Fixtures ============

@pytest.fixture
def risk_config():
    """Standard risk config for testing."""
    return RiskConfig(
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
        blacklist=["SCAM", "JUNK"],
    )


@pytest.fixture
def mock_journal():
    """Mock TradingJournal."""
    j = MagicMock()
    j.get_today_pnl.return_value = {"pnl": 0.0, "trades": 0}
    j.open_trade.return_value = 42  # trade_id
    j.close_trade.return_value = {"trade_id": 42, "symbol": "AAPL", "pnl": 10.0, "pnl_pct": 1.33, "hold_hours": 4.5}
    j.get_open_trades.return_value = []
    return j


@pytest.fixture
def risk_manager(risk_config, mock_journal):
    """RiskManager with known config and mocked journal."""
    rm = RiskManager(config=risk_config, journal=mock_journal)
    rm._last_pnl_update = now_et().strftime('%Y-%m-%d')
    rm._last_refresh_ts = now_et()
    return rm


# ============ Broker / Portfolio Mocks ============

@pytest.fixture
def mock_broker():
    """Mock IBKR broker."""
    b = AsyncMock()
    b.buy.return_value = {"status": "filled", "avg_price": 150.0, "quantity": 10}
    b.sell.return_value = {"status": "filled", "avg_price": 155.0, "quantity": 10}
    # is_connected is a sync method on the real broker — use MagicMock to avoid
    # returning a coroutine (which is always truthy and triggers RuntimeWarning).
    b.is_connected = MagicMock(return_value=True)
    return b


@pytest.fixture
def mock_portfolio():
    """Mock simulation portfolio."""
    p = MagicMock()
    p.get_positions.return_value = []
    p.buy.return_value = {"status": "ok", "symbol": "AAPL", "quantity": 10}
    p.sell.return_value = {"status": "ok", "symbol": "AAPL", "quantity": 10}
    return p


@pytest.fixture
def mock_monitor():
    """Mock PositionMonitor."""
    m = MagicMock()
    m.add_position.return_value = None
    return m


@pytest.fixture
def mock_notify():
    """Mock async notification function."""
    return AsyncMock()


@pytest.fixture
def mock_get_quote():
    """Mock async quote function."""
    f = AsyncMock()
    f.return_value = {"price": 150.0}
    return f


# ============ TradingPipeline Fixture ============

@pytest.fixture
def pipeline(risk_manager, mock_broker, mock_journal, mock_portfolio, mock_monitor, mock_notify):
    """Fully wired TradingPipeline."""
    return TradingPipeline(
        risk_manager=risk_manager,
        broker=mock_broker,
        journal=mock_journal,
        portfolio=mock_portfolio,
        monitor=mock_monitor,
        notify_func=mock_notify,
    )


# ============ Sample Data ============

@pytest.fixture
def sample_proposal():
    """A valid BUY proposal that should pass risk checks."""
    return TradeProposal(
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


@pytest.fixture
def sample_positions():
    """Sample current positions for risk checks."""
    return [
        {"symbol": "MSFT", "quantity": 10, "avg_price": 400.0, "status": "open"},
        {"symbol": "GOOG", "quantity": 5, "avg_price": 170.0, "status": "open"},
    ]
