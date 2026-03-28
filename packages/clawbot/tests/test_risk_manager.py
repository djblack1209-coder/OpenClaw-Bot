"""
Tests for RiskManager - 12 risk checks + calc_safe_quantity.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from src.risk_config import RiskConfig, RiskCheckResult
from src.risk_manager import RiskManager
from src.utils import now_et


class TestRiskCheckBlacklist:
    """Check 0: Blacklisted symbols are rejected."""

    def test_blacklisted_symbol_rejected(self, risk_manager):
        result = risk_manager.check_trade("SCAM", "BUY", 10, 100.0, 95.0, 110.0)
        assert not result.approved
        assert "黑名单" in result.reason

    def test_non_blacklisted_passes(self, risk_manager):
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=50)
        assert result.approved


class TestRiskCheckCooldown:
    """Check 1: Circuit breaker / cooldown."""

    def test_cooldown_blocks_trade(self, risk_manager):
        risk_manager._cooldown_until = now_et() + timedelta(minutes=15)
        risk_manager._consecutive_losses = 3
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0)
        assert not result.approved
        assert "熔断" in result.reason

    def test_expired_cooldown_allows_trade(self, risk_manager):
        risk_manager._cooldown_until = now_et() - timedelta(minutes=1)
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=50)
        assert result.approved


class TestRiskCheckDailyLoss:
    """Check 2: Daily loss limit."""

    def test_daily_loss_exceeded_blocks(self, risk_manager):
        risk_manager._today_pnl = -200.0  # At limit
        risk_manager._last_refresh_ts = now_et()  # Prevent refresh
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0)
        assert not result.approved
        assert "日亏损限额" in result.reason

    def test_within_daily_limit_passes(self, risk_manager):
        risk_manager._today_pnl = -50.0
        risk_manager._last_refresh_ts = now_et()
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=50)
        assert result.approved


class TestRiskCheckTradingHours:
    """Check 3: Trading hours enforcement."""

    def test_outside_hours_blocked_when_enabled(self, risk_manager):
        risk_manager.config.trading_hours_enabled = True
        # Force a time outside trading hours (3 AM ET)
        fake_now = now_et().replace(hour=3, minute=0, second=0)
        with patch("src.risk_manager.now_et", return_value=fake_now):
            result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0)
        assert not result.approved
        assert "非交易时段" in result.reason

    def test_disabled_hours_always_passes(self, risk_manager):
        risk_manager.config.trading_hours_enabled = False
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=50)
        assert result.approved


class TestRiskCheckStopLoss:
    """Check 4 & 5: Stop-loss required and direction."""

    def test_buy_without_stop_loss_rejected(self, risk_manager):
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 0, 162.0)
        assert not result.approved
        assert "止损" in result.reason

    def test_stop_loss_above_entry_rejected(self, risk_manager):
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 155.0, 162.0)
        assert not result.approved
        assert "止损价" in result.reason and "低于" in result.reason

    def test_valid_stop_loss_passes(self, risk_manager):
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=50)
        assert result.approved

    def test_wide_stop_loss_warns(self, risk_manager):
        # 15% stop loss
        result = risk_manager.check_trade("AAPL", "BUY", 1, 150.0, 127.0, 200.0, signal_score=50)
        assert result.approved
        assert any("止损幅度" in w for w in result.warnings)


class TestRiskCheckRiskReward:
    """Check 6: Risk-reward ratio."""

    def test_bad_rr_ratio_rejected(self, risk_manager):
        # Risk $5, Reward $3 -> RR = 0.6 < 2.0
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 153.0, signal_score=50)
        assert not result.approved
        assert "风险收益比" in result.reason

    def test_good_rr_ratio_passes(self, risk_manager):
        # Risk $5, Reward $12 -> RR = 2.4 >= 2.0
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=50)
        assert result.approved

    def test_exact_min_rr_passes(self, risk_manager):
        # Risk $5, Reward $10 -> RR = 2.0 exactly
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 160.0, signal_score=50)
        assert result.approved

    def test_no_take_profit_warns(self, risk_manager):
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 0, signal_score=50)
        assert result.approved
        assert any("止盈" in w for w in result.warnings)


class TestRiskCheckPerTradeRisk:
    """Check 7: Single trade risk amount."""

    def test_excessive_risk_adjusts_quantity(self, risk_manager):
        # Capital=10000, max_risk=2%=200. Risk per share=$5, qty=100 -> risk=$500 > $200
        result = risk_manager.check_trade("AAPL", "BUY", 100, 150.0, 145.0, 162.0, signal_score=50)
        assert result.approved
        assert result.adjusted_quantity is not None
        assert result.adjusted_quantity <= 40  # 200/5 = 40

    def test_small_position_no_adjustment(self, risk_manager):
        # qty=5, risk per share=$5, total risk=$25 < $200
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=50)
        assert result.approved
        assert result.adjusted_quantity is None


class TestRiskCheckConcentration:
    """Check 8: Position concentration limit."""

    def test_position_too_large_warns(self, risk_manager):
        # max_position = 10000 * 0.30 = 3000. qty=25 * $150 = $3750 > $3000
        result = risk_manager.check_trade("AAPL", "BUY", 25, 150.0, 145.0, 162.0, signal_score=50)
        assert result.approved
        assert result.adjusted_quantity is not None
        assert result.adjusted_quantity <= 20  # 3000/150 = 20


class TestRiskCheckTotalExposure:
    """Check 9: Total portfolio exposure."""

    def test_total_exposure_exceeded_rejected(self, risk_manager):
        # Existing: MSFT 10*400=4000, GOOG 5*170=850 = 4850
        # New: AAPL 5*150=750 -> total=5600. Max=10000*0.80=8000 -> OK
        # But if existing is larger...
        big_positions = [
            {"symbol": "MSFT", "quantity": 10, "avg_price": 400.0},
            {"symbol": "GOOG", "quantity": 20, "avg_price": 170.0},
        ]
        # Existing = 4000+3400=7400. New=750 -> 8150 > 8000
        result = risk_manager.check_trade(
            "AAPL", "BUY", 5, 150.0, 145.0, 162.0,
            signal_score=50, current_positions=big_positions,
        )
        assert not result.approved
        assert "总敞口" in result.reason


class TestRiskCheckMaxPositions:
    """Check 10: Maximum open positions."""

    def test_max_positions_reached_rejected(self, risk_manager):
        positions = [
            {"symbol": f"SYM{i}", "quantity": 1, "avg_price": 10.0, "status": "open"}
            for i in range(5)
        ]
        result = risk_manager.check_trade(
            "NEWSTOCK", "BUY", 1, 10.0, 9.0, 14.0,
            signal_score=50, current_positions=positions,
        )
        assert not result.approved
        assert "持仓" in result.reason and "上限" in result.reason

    def test_adding_to_existing_position_allowed(self, risk_manager):
        positions = [
            {"symbol": f"SYM{i}", "quantity": 1, "avg_price": 10.0, "status": "open"}
            for i in range(5)
        ]
        # Adding to SYM0 which already exists
        result = risk_manager.check_trade(
            "SYM0", "BUY", 1, 10.0, 9.0, 14.0,
            signal_score=50, current_positions=positions,
        )
        assert result.approved


class TestRiskCheckSignalStrength:
    """Check 11: Signal score warning."""

    def test_weak_signal_warns(self, risk_manager):
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=10)
        assert result.approved
        assert any("信号评分" in w for w in result.warnings)

    def test_strong_signal_no_warning(self, risk_manager):
        result = risk_manager.check_trade("AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=60)
        assert result.approved
        signal_warnings = [w for w in result.warnings if "信号评分" in w]
        assert len(signal_warnings) == 0


class TestCalcSafeQuantity:
    """calc_safe_quantity() - pure math."""

    def test_basic_calculation(self, risk_manager):
        # Capital=10000, max_risk=2%=200, risk_per_share=$5
        # shares_by_risk = 200/5 = 40
        # max_position = 10000*0.30 = 3000, shares_by_position = 3000/150 = 20
        # min(40, 20) = 20 (capped by position limit)
        result = risk_manager.calc_safe_quantity(150.0, 145.0)
        assert "shares" in result
        assert result["shares"] == 20
        assert result["max_loss"] <= 200.0

    def test_position_limit_caps_quantity(self, risk_manager):
        # Very tight stop: risk_per_share=$0.10, shares_by_risk=2000
        # But max_position=3000, shares_by_position=3000/150=20
        result = risk_manager.calc_safe_quantity(150.0, 149.90)
        assert result["shares"] == 20  # Capped by position limit

    def test_equal_prices_returns_error(self, risk_manager):
        result = risk_manager.calc_safe_quantity(150.0, 150.0)
        assert "error" in result

    def test_custom_capital(self, risk_manager):
        # max_risk = 5000*0.02=100, risk_per_share=5, shares_by_risk=20
        # max_position = 5000*0.30=1500, shares_by_position=1500/100=15
        # min(20, 15) = 15 (capped by position limit)
        result = risk_manager.calc_safe_quantity(100.0, 95.0, capital=5000.0)
        assert result["shares"] == 15


class TestRecordTradeResult:
    """record_trade_result() - state mutations."""

    def test_loss_increments_consecutive(self, risk_manager):
        risk_manager.record_trade_result(-50.0)
        assert risk_manager._consecutive_losses == 1
        assert risk_manager._today_pnl == -50.0

    def test_win_resets_consecutive(self, risk_manager):
        risk_manager._consecutive_losses = 2
        risk_manager.record_trade_result(30.0)
        assert risk_manager._consecutive_losses == 0

    def test_three_losses_trigger_cooldown(self, risk_manager):
        for _ in range(3):
            risk_manager.record_trade_result(-20.0)
        assert risk_manager._cooldown_until is not None
        assert risk_manager._consecutive_losses == 3

    def test_daily_pnl_accumulates(self, risk_manager):
        risk_manager.record_trade_result(-30.0)
        risk_manager.record_trade_result(50.0)
        risk_manager.record_trade_result(-10.0)
        assert risk_manager._today_pnl == pytest.approx(10.0)


class TestResetDaily:
    """reset_daily() - state reset."""

    def test_reset_clears_all_state(self, risk_manager):
        risk_manager._today_pnl = -150.0
        risk_manager._today_trades = 5
        risk_manager._consecutive_losses = 2
        risk_manager._cooldown_until = now_et() + timedelta(minutes=10)
        risk_manager.reset_daily()
        assert risk_manager._today_pnl == 0.0
        assert risk_manager._today_trades == 0
        assert risk_manager._consecutive_losses == 0
        assert risk_manager._cooldown_until is None


class TestRiskScore:
    """_calc_risk_score() - scoring logic."""

    def test_low_risk_trade(self, risk_manager):
        score = risk_manager._calc_risk_score(
            "AAPL", "BUY", 5, 150.0, 145.0, 162.0, 60, []
        )
        assert 0 <= score <= 100
        assert score < 50  # Should be relatively low risk

    def test_high_risk_no_stop(self, risk_manager):
        score = risk_manager._calc_risk_score(
            "AAPL", "BUY", 50, 150.0, 0, 0, 0, []
        )
        assert score > 30  # No stop + no signal = higher risk

    def test_consecutive_losses_increase_score(self, risk_manager):
        score_clean = risk_manager._calc_risk_score(
            "AAPL", "BUY", 5, 150.0, 145.0, 162.0, 50, []
        )
        risk_manager._consecutive_losses = 2
        score_losing = risk_manager._calc_risk_score(
            "AAPL", "BUY", 5, 150.0, 145.0, 162.0, 50, []
        )
        assert score_losing > score_clean


# ============ 边界测试 (Boundary Tests) ============


class TestCalcSafeQuantityBoundaries:
    """Boundary tests for calc_safe_quantity edge cases."""

    def test_entry_price_zero(self, risk_manager):
        """entry_price=0 now returns error dict instead of ZeroDivisionError.

        After fix HI-036: calc_safe_quantity guards against entry_price <= 0.
        """
        result = risk_manager.calc_safe_quantity(entry_price=0.0, stop_loss=5.0)
        assert "error" in result
        assert result["shares"] == 0

    def test_capital_zero(self):
        """total_capital=0 → returns error dict with shares=0.

        After fix HI-036: early guard catches capital <= 0.
        """
        config = RiskConfig(total_capital=0.0)
        rm = RiskManager(config=config)
        result = rm.calc_safe_quantity(
            entry_price=150.0, stop_loss=145.0,
        )
        assert "error" in result
        assert result["shares"] == 0

    def test_stop_loss_none_returns_error(self, risk_manager):
        """stop_loss=None now returns error dict instead of TypeError.

        After fix HI-036: calc_safe_quantity guards against None stop_loss.
        """
        result = risk_manager.calc_safe_quantity(entry_price=150.0, stop_loss=None)
        assert "error" in result
        assert result["shares"] == 0

    def test_stop_loss_zero_returns_valid_result(self, risk_manager):
        """stop_loss=0 → risk_per_share=150, shares_by_risk=1 (capped by risk).

        Unlike stop_loss=None, zero is valid arithmetic and returns a result.
        Capital=10000, max_risk=200, risk_per_share=150, shares_by_risk=1,
        shares_by_position=int(3000/150)=20, min(1,20)=1.
        """
        result = risk_manager.calc_safe_quantity(
            entry_price=150.0, stop_loss=0.0,
        )
        assert "shares" in result
        assert result["shares"] == 1
        assert result["max_loss"] == pytest.approx(150.0)


class TestConsecutiveLossesCircuitBreaker:
    """Consecutive losses trigger tiered cooldown and block trades."""

    def test_consecutive_losses_circuit_breaker(self):
        """3 consecutive losses → Tier2 cooldown → check_trade rejected.

        RiskConfig defaults: tier2_losses=3, tiered_cooldown_enabled=True.
        After 3 losses, _cooldown_until is set and all trades are blocked.
        """
        config = RiskConfig(
            total_capital=10000.0,
            daily_loss_limit=500.0,       # high limit so it doesn't interfere
            tiered_cooldown_enabled=True,
            tier2_losses=3,
            tier2_cooldown_minutes=15,
            trading_hours_enabled=False,
            blacklist=[],
        )
        rm = RiskManager(config=config)
        rm._last_pnl_update = now_et().strftime("%Y-%m-%d")
        rm._last_refresh_ts = now_et()

        # Record exactly 3 consecutive losses
        rm.record_trade_result(-10.0, "AAPL")
        rm.record_trade_result(-15.0, "MSFT")
        rm.record_trade_result(-20.0, "GOOG")

        assert rm._consecutive_losses == 3
        assert rm._cooldown_until is not None

        # check_trade must be rejected
        result = rm.check_trade(
            "TSLA", "BUY", 5, 200.0, 190.0, 224.0, signal_score=60,
        )
        assert result.approved is False
        assert "熔断" in result.reason


class TestDailyLossLimitExactBoundary:
    """Daily loss limit behavior at exact boundary value."""

    def test_daily_loss_limit_exact_boundary(self):
        """PnL exactly at -$100 with limit=$100 → trade blocked.

        The check is `_today_pnl <= -daily_loss_limit`, so -100 <= -100 is True.
        """
        config = RiskConfig(
            total_capital=10000.0,
            daily_loss_limit=100.0,
            trading_hours_enabled=False,
            blacklist=[],
        )
        rm = RiskManager(config=config)
        rm._last_pnl_update = now_et().strftime("%Y-%m-%d")
        rm._last_refresh_ts = now_et()
        rm._today_pnl = -100.0  # exactly at limit

        result = rm.check_trade(
            "AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=50,
        )
        assert result.approved is False
        assert "日亏损限额" in result.reason

    def test_daily_loss_limit_one_cent_below_boundary(self):
        """PnL at -$99.99 with limit=$100 → trade allowed.

        -99.99 <= -100 is False, so trade passes the daily loss check.
        """
        config = RiskConfig(
            total_capital=10000.0,
            daily_loss_limit=100.0,
            trading_hours_enabled=False,
            blacklist=[],
        )
        rm = RiskManager(config=config)
        rm._last_pnl_update = now_et().strftime("%Y-%m-%d")
        rm._last_refresh_ts = now_et()
        rm._today_pnl = -99.99

        result = rm.check_trade(
            "AAPL", "BUY", 5, 150.0, 145.0, 162.0, signal_score=50,
        )
        assert result.approved is True
