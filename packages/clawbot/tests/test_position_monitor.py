"""
Tests for PositionMonitor - exit condition checks (stop-loss, take-profit, trailing, time-stop).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta

from src.position_monitor import (
    PositionMonitor, MonitoredPosition, ExitReason, ExitSignal,
)
from src.utils import now_et


# ============ MonitoredPosition.update_price ============

class TestMonitoredPositionUpdatePrice:
    """Unit tests for price update logic."""

    def test_buy_unrealized_pnl_positive(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=now_et(),
        )
        pos.highest_price = 150.0
        pos.update_price(155.0)
        assert pos.current_price == 155.0
        assert pos.unrealized_pnl == 50.0  # (155-150)*10
        assert pos.unrealized_pnl_pct == pytest.approx(3.33, abs=0.1)

    def test_buy_unrealized_pnl_negative(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=now_et(),
        )
        pos.highest_price = 150.0
        pos.update_price(145.0)
        assert pos.unrealized_pnl == -50.0

    def test_sell_unrealized_pnl(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="SELL", quantity=10,
            entry_price=150.0, entry_time=now_et(),
        )
        pos.highest_price = 150.0
        pos.update_price(145.0)
        assert pos.unrealized_pnl == 50.0  # (150-145)*10

    def test_highest_price_tracked(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=now_et(),
        )
        pos.highest_price = 150.0
        pos.update_price(160.0)
        assert pos.highest_price == 160.0
        pos.update_price(155.0)
        assert pos.highest_price == 160.0  # Doesn't decrease

    def test_trailing_stop_moves_up(self):
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=now_et(),
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
            entry_price=150.0, entry_time=now_et(),
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
            entry_price=150.0, entry_time=now_et(),
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
            entry_time=now_et() - timedelta(hours=25),
        )
        pos.update_price(150.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is not None
        assert signal.reason == ExitReason.TIME_STOP

    def test_time_stop_not_triggered(self):
        mon = self._make_monitor()
        pos = self._make_pos(
            max_hold_hours=24,
            entry_time=now_et() - timedelta(hours=10),
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
            entry_price=150.0, entry_time=now_et(),
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
            entry_price=150.0, entry_time=now_et(),
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
            entry_price=150.0, entry_time=now_et(),
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
            entry_price=150.0, entry_time=now_et(),
            stop_loss=145.0, take_profit=165.0,
        )
        mon.add_position(pos)
        exits = await mon.check_once()
        assert len(exits) == 0


# ============ 退出条件测试 (Exit Condition Tests) ============


class TestTrailingStopHighwater:
    """Trailing stop high-water mark tracking and updates."""

    def test_trailing_stop_updates_highwater(self):
        """Price rises 150→160→170 → highest_price and trailing_stop both update.

        With trailing_stop_pct=0.05 (5%):
          at 160: trailing = 160*0.95 = 152.0
          at 170: trailing = 170*0.95 = 161.5
        """
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=now_et(),
            trailing_stop_pct=0.05,
        )
        pos.highest_price = 150.0
        pos.trailing_stop_price = round(150.0 * 0.95, 2)  # 142.5

        # Price rises to 160
        pos.update_price(160.0)
        assert pos.highest_price == 160.0
        assert pos.trailing_stop_price == 152.0  # 160 * 0.95

        # Price rises further to 170
        pos.update_price(170.0)
        assert pos.highest_price == 170.0
        assert pos.trailing_stop_price == 161.5  # 170 * 0.95


class TestTrailingStopPullbackTrigger:
    """Trailing stop triggers when price pulls back from high-water mark."""

    def test_trailing_stop_triggers_on_pullback(self):
        """Price rises 150→170 (trailing=161.5), then drops to 161 → triggers.

        Sequence:
          1. Price 150→170: highest=170, trailing=161.5
          2. Price drops to 161: 161 <= 161.5 → TRAILING_STOP fires
        """
        mon = PositionMonitor(check_interval=30)
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=now_et(),
            trailing_stop_pct=0.05,
        )
        pos.highest_price = 150.0
        pos.trailing_stop_price = round(150.0 * 0.95, 2)

        # Rally to 170 → updates high-water
        pos.update_price(170.0)
        assert pos.highest_price == 170.0
        assert pos.trailing_stop_price == 161.5

        # Pullback to 161 → below trailing stop
        pos.update_price(161.0)
        signal = mon._check_exit_conditions(pos)

        assert signal is not None
        assert signal.reason == ExitReason.TRAILING_STOP
        assert signal.trigger_price == 161.0

    def test_trailing_stop_does_not_trigger_above_trailing(self):
        """Price drops but stays above trailing stop → no trigger."""
        mon = PositionMonitor(check_interval=30)
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=now_et(),
            trailing_stop_pct=0.05,
        )
        pos.highest_price = 170.0
        pos.trailing_stop_price = 161.5

        # Price drops to 162 → still above 161.5
        pos.update_price(162.0)
        signal = mon._check_exit_conditions(pos)
        assert signal is None


class TestTimeStopMaxHold:
    """Time stop triggers after max hold duration for losing positions."""

    def test_time_stop_triggers_after_max_hold(self):
        """Position held > max_hold_hours with negative PnL → TIME_STOP.

        Entry 25 hours ago, max_hold=24h, current price below entry → triggers.
        """
        mon = PositionMonitor(check_interval=30)
        entry_time = now_et() - timedelta(hours=25)
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=entry_time,
            max_hold_hours=24,
        )
        # Price below entry → losing position → time stop fires
        pos.update_price(148.0)

        signal = mon._check_exit_conditions(pos)
        assert signal is not None
        assert signal.reason == ExitReason.TIME_STOP

    def test_time_stop_skipped_when_profitable(self):
        """Position held > max_hold_hours but profitable → time stop canceled.

        The code cancels max_hold_hours (sets to 0) and relies on trailing stop.
        """
        mon = PositionMonitor(check_interval=30)
        entry_time = now_et() - timedelta(hours=25)
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=entry_time,
            max_hold_hours=24,
        )
        # Price above entry → profitable → time stop is canceled
        pos.update_price(155.0)

        signal = mon._check_exit_conditions(pos)
        assert signal is None
        # max_hold_hours is zeroed out to prevent future time-stop checks
        assert pos.max_hold_hours == 0


class TestMultipleExitConditionsPriority:
    """When multiple exit conditions trigger simultaneously, priority matters."""

    def test_stop_loss_has_priority_over_trailing_stop(self):
        """Both SL and trailing stop triggered → STOP_LOSS wins (checked first).

        _check_exit_conditions checks in order:
          1. stop_loss  2. trailing_stop  3. partial_tp  4. take_profit  5. time_stop
        """
        mon = PositionMonitor(check_interval=30)
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=now_et(),
            stop_loss=145.0,
            trailing_stop_pct=0.05,
        )
        pos.highest_price = 160.0
        pos.trailing_stop_price = 152.0

        # Price drops to 140 → triggers BOTH stop_loss (<=145) AND trailing (<=152)
        pos.update_price(140.0)
        signal = mon._check_exit_conditions(pos)

        assert signal is not None
        assert signal.reason == ExitReason.STOP_LOSS  # SL wins over trailing

    def test_trailing_stop_priority_over_time_stop(self):
        """Trailing stop and time stop both triggered → TRAILING_STOP wins.

        Trailing stop is checked before time stop in the code.
        """
        mon = PositionMonitor(check_interval=30)
        entry_time = now_et() - timedelta(hours=25)
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=entry_time,
            max_hold_hours=24,
            trailing_stop_pct=0.05,
        )
        pos.highest_price = 160.0
        pos.trailing_stop_price = 152.0

        # Price drops to 148 → triggers trailing (<=152) AND position is overdue
        # But since price is below entry, pnl < 0, so time stop would also fire
        pos.update_price(148.0)
        signal = mon._check_exit_conditions(pos)

        assert signal is not None
        assert signal.reason == ExitReason.TRAILING_STOP  # trailing wins over time

    def test_stop_loss_priority_over_take_profit(self):
        """Misconfigured SL/TP where SL > TP → STOP_LOSS wins.

        This is a degenerate case (SL=145, TP=140) but tests priority.
        """
        mon = PositionMonitor(check_interval=30)
        pos = MonitoredPosition(
            trade_id=1, symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_time=now_et(),
            stop_loss=145.0,
            take_profit=140.0,  # Misconfigured: TP below SL
        )
        # Price at 139 triggers both SL (<=145) and TP (>=140 is false, 139<140)
        # Actually TP check is >= take_profit, so 139 < 140 → TP does NOT trigger
        # Let me use a price that triggers both
        pos.update_price(145.0)
        signal = mon._check_exit_conditions(pos)

        # 145 <= 145 → SL triggers. 145 >= 140 → TP also would trigger.
        # But SL is checked first.
        assert signal is not None
        assert signal.reason == ExitReason.STOP_LOSS
