"""
Tests for PositionMonitor - exit condition checks (stop-loss, take-profit, trailing, time-stop).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta

from src.position_monitor import (
    PositionMonitor, MonitoredPosition, ExitReason, ExitSignal,
)


# ============ MonitoredPosition.update_price ============

class TestMonitoredPositionUpdatePrice:
    """Unit tests for price update logic."""

    def test_buy_unrealized_pnl_positive(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
        )
        pos.highest_price = 150.0
        pos.update_price(155.0)
        assert pos.current_price == 155.0
        assert pos.unrealized_pnl == 50.0  # (155-150)*10
        assert pos.unrealized_pnl_pct == pytest.approx(3.33, abs=0.1)

    def test_buy_unrealized_pnl_negative(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
        )
        pos.highest_price = 150.0
        pos.update_price(145.0)
        assert pos.unrealized_pnl == -50.0

    def test_sell_unrealized_pnl(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="SELL", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
        )
        pos.highest_price = 150.0
        pos.update_price(145.0)
        assert pos.unrealized_pnl == 50.0  # (150-145)*10

    def test_highest_price_tracked(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
        )
        pos.highest_price = 150.0
        pos.update_price(160.0)
        assert pos.highest_price == 160.0
        pos.update_price(155.0)
        assert pos.highest_price == 160.0  # Doesn't decrease

    def test_trailing_stop_moves_up(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
            trailing_stop_pct=0.05,  # 5%
        )
        pos.highest_price = 150.0
        pos.trailing_stop_price = 142.50  # 150 * 0.95
        pos.update_price(160.0)
        # New trailing: 160 * 0.95 = 152.0
        assert pos.trailing_stop_price == 152.0

    def test_trailing_stop_never_moves_down(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
            trailing_stop_pct=0.05,
        )
        pos.highest_price = 160.0
        pos.trailing_stop_price = 152.0
        pos.update_price(155.0)  # Price drops but still above trailing
        assert pos.trailing_stop_price == 152.0  # Unchanged


# ============ _check_exit_conditions ============

class TestCheckExitConditions:
    """Test the exit condition detection logic."""

    def _make_monitor(self):
        return PositionMonitor(check_interval=30)

    def _make_pos(self, **kwargs):
        defaults = dict(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
        )
        defaults.update(kwargs)
        return MonitoredPosition(**defaults)

    def test_stop_loss_triggered(self):
        mon = self._make_monitor()
        pos = self._make_pos(stop_loss=145.0)
        pos.update_price(144.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is not None
        assert signal.reason == ExitReason.STOP_LOSS

    def test_stop_loss_not_triggered(self):
        mon = self._make_monitor()
        pos = self._make_pos(stop_loss=145.0)
        pos.update_price(146.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is None

    def test_stop_loss_exact_price(self):
        mon = self._make_monitor()
        pos = self._make_pos(stop_loss=145.0)
        pos.update_price(145.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is not None
        assert signal.reason == ExitReason.STOP_LOSS

    def test_take_profit_triggered(self):
        mon = self._make_monitor()
        pos = self._make_pos(take_profit=160.0)
        pos.update_price(161.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is not None
        assert signal.reason == ExitReason.TAKE_PROFIT

    def test_take_profit_not_triggered(self):
        mon = self._make_monitor()
        pos = self._make_pos(take_profit=160.0)
        pos.update_price(159.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is None

    def test_trailing_stop_triggered(self):
        mon = self._make_monitor()
        pos = self._make_pos(trailing_stop_pct=0.05)
        pos.trailing_stop_price = 152.0
        pos.highest_price = 160.0
        pos.update_price(151.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is not None
        assert signal.reason == ExitReason.TRAILING_STOP

    def test_trailing_stop_not_triggered(self):
        mon = self._make_monitor()
        pos = self._make_pos(trailing_stop_pct=0.05)
        pos.trailing_stop_price = 152.0
        pos.highest_price = 160.0
        pos.update_price(153.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is None

    def test_time_stop_triggered(self):
        mon = self._make_monitor()
        pos = self._make_pos(
            max_hold_hours=24,
            entry_time=datetime.now() - timedelta(hours=25),
        )
        pos.update_price(150.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is not None
        assert signal.reason == ExitReason.TIME_STOP

    def test_time_stop_not_triggered(self):
        mon = self._make_monitor()
        pos = self._make_pos(
            max_hold_hours=24,
            entry_time=datetime.now() - timedelta(hours=10),
        )
        pos.update_price(150.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is None

    def test_stop_loss_priority_over_take_profit(self):
        """If price somehow triggers both, stop-loss is checked first."""
        mon = self._make_monitor()
        # Weird scenario: SL=145, TP=140 (misconfigured)
        pos = self._make_pos(stop_loss=145.0, take_profit=140.0)
        pos.update_price(139.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is not None
        assert signal.reason == ExitReason.STOP_LOSS

    def test_no_exit_conditions_set(self):
        mon = self._make_monitor()
        pos = self._make_pos()  # No SL, TP, trailing, time
        pos.update_price(140.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is None


# ============ add_position / remove_position ============

class TestPositionManagement:

    def test_add_position(self):
        mon = PositionMonitor(check_interval=30)
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
            trailing_stop_pct=0.05,
        )
        mon.add_position(pos)
        assert 1 in mon.positions
        assert pos.highest_price == 150.0
        assert pos.trailing_stop_price == 142.50

    def test_remove_position(self):
        mon = PositionMonitor(check_interval=30)
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
        )
        mon.add_position(pos)
        mon.remove_position(1)
        assert 1 not in mon.positions

    def test_remove_nonexistent_no_error(self):
        mon = PositionMonitor(check_interval=30)
        mon.remove_position(999)  # Should not raise


# ============ check_once (bug fix verification) ============

class TestCheckOnce:
    """Verify the check_once bug fix returns only new exits."""

    @pytest.mark.asyncio
    async def test_check_once_returns_only_new_exits(self):
        mock_quote = AsyncMock(return_value={"price": 140.0})
        mock_sell = AsyncMock(return_value={"status": "filled"})
        mock_notify = AsyncMock()

        mon = PositionMonitor(
            check_interval=30,
            get_quote_func=mock_quote,
            execute_sell_func=mock_sell,
            notify_func=mock_notify,
        )

        # Add a position that will trigger stop-loss
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
            stop_loss=145.0,
        )
        mon.add_position(pos)

        exits = await mon.check_once()
        assert len(exits) == 1
        assert exits[0].reason == ExitReason.STOP_LOSS

    @pytest.mark.asyncio
    async def test_check_once_empty_when_no_exits(self):
        mock_quote = AsyncMock(return_value={"price": 155.0})
        mon = PositionMonitor(
            check_interval=30,
            get_quote_func=mock_quote,
        )
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=datetime.now(),
            stop_loss=145.0, take_profit=165.0,
        )
        mon.add_position(pos)
        exits = await mon.check_once()
        assert len(exits) == 0
