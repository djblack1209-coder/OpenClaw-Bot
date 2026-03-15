"""
Tests for Rebalancer - target allocation, drift detection, trade generation.
"""
import pytest

from src.rebalancer import (
    Rebalancer, RebalanceConfig, RebalancePlan,
    AllocationTarget, PositionDrift,
    PRESET_ALLOCATIONS, TECH_GROWTH_ALLOCATION, BALANCED_ALLOCATION,
)


@pytest.fixture
def rebalancer():
    return Rebalancer(config=RebalanceConfig(
        drift_threshold_pct=3.0,
        min_trade_value=50.0,
        cash_reserve_pct=5.0,
        max_single_trade_pct=20.0,
    ))


@pytest.fixture
def simple_targets():
    return [
        AllocationTarget("AAPL", 40.0),
        AllocationTarget("MSFT", 30.0),
        AllocationTarget("NVDA", 25.0),
        # 5% cash reserve
    ]


@pytest.fixture
def positions_balanced():
    """Positions roughly matching 40/30/25 allocation on $10000."""
    return [
        {"symbol": "AAPL", "quantity": 25, "avg_price": 152.0},  # ~3800
        {"symbol": "MSFT", "quantity": 7, "avg_price": 410.0},   # ~2870
        {"symbol": "NVDA", "quantity": 18, "avg_price": 130.0},  # ~2340
    ]


@pytest.fixture
def quotes():
    return {"AAPL": 152.0, "MSFT": 410.0, "NVDA": 130.0, "GOOGL": 175.0}


class TestSetTargets:

    def test_set_targets(self, rebalancer, simple_targets):
        rebalancer.set_targets(simple_targets)
        assert len(rebalancer.get_targets()) == 3

    def test_targets_over_100_scaled(self, rebalancer):
        targets = [
            AllocationTarget("AAPL", 60.0),
            AllocationTarget("MSFT", 60.0),
        ]
        rebalancer.set_targets(targets)
        total = sum(t.target_pct for t in rebalancer.get_targets())
        assert total == pytest.approx(100.0, abs=0.1)

    def test_format_targets(self, rebalancer, simple_targets):
        rebalancer.set_targets(simple_targets)
        text = rebalancer.format_targets()
        assert "AAPL" in text
        assert "40.0%" in text

    def test_format_no_targets(self, rebalancer):
        text = rebalancer.format_targets()
        assert "未设置" in text


class TestAnalyzeBalanced:
    """When portfolio is roughly balanced, no trades needed."""

    def test_balanced_portfolio(self, rebalancer, simple_targets, positions_balanced, quotes):
        rebalancer.set_targets(simple_targets)
        cash = 990.0  # ~10% cash
        plan = rebalancer.analyze(positions_balanced, quotes, cash)
        assert plan.total_value > 0
        assert plan.max_drift < 10  # Roughly balanced

    def test_no_targets_returns_balanced(self, rebalancer, positions_balanced, quotes):
        plan = rebalancer.analyze(positions_balanced, quotes, 1000.0)
        assert plan.is_balanced is True


class TestAnalyzeDrifted:
    """When portfolio has significant drift, trades are generated."""

    def test_overweight_generates_sell(self, rebalancer, quotes):
        targets = [
            AllocationTarget("AAPL", 50.0),
            AllocationTarget("MSFT", 45.0),
        ]
        rebalancer.set_targets(targets)
        # AAPL is 80% of portfolio -> overweight
        positions = [
            {"symbol": "AAPL", "quantity": 50, "avg_price": 152.0},  # 7600
            {"symbol": "MSFT", "quantity": 2, "avg_price": 410.0},   # 820
        ]
        plan = rebalancer.analyze(positions, quotes, 500.0)
        sells = [t for t in plan.trades_needed if t.action == "SELL"]
        buys = [t for t in plan.trades_needed if t.action == "BUY"]
        assert len(sells) > 0  # Should sell AAPL
        assert sells[0].symbol == "AAPL"
        assert len(buys) > 0   # Should buy MSFT

    def test_underweight_generates_buy(self, rebalancer, quotes):
        targets = [
            AllocationTarget("AAPL", 30.0),
            AllocationTarget("MSFT", 30.0),
            AllocationTarget("NVDA", 35.0),
        ]
        rebalancer.set_targets(targets)
        # Only AAPL, missing MSFT and NVDA
        positions = [
            {"symbol": "AAPL", "quantity": 60, "avg_price": 152.0},  # 9120
        ]
        plan = rebalancer.analyze(positions, quotes, 1000.0)
        buys = [t for t in plan.trades_needed if t.action == "BUY"]
        buy_symbols = {t.symbol for t in buys}
        assert "MSFT" in buy_symbols or "NVDA" in buy_symbols

    def test_empty_portfolio_all_buys(self, rebalancer, quotes):
        targets = [
            AllocationTarget("AAPL", 50.0),
            AllocationTarget("MSFT", 45.0),
        ]
        rebalancer.set_targets(targets)
        plan = rebalancer.analyze([], quotes, 10000.0)
        assert not plan.is_balanced
        buys = [t for t in plan.trades_needed if t.action == "BUY"]
        assert len(buys) == 2


class TestAnalyzeExtraPositions:
    """Positions not in target allocation should be flagged."""

    def test_extra_position_flagged(self, rebalancer, quotes):
        targets = [AllocationTarget("AAPL", 95.0)]
        rebalancer.set_targets(targets)
        positions = [
            {"symbol": "AAPL", "quantity": 50, "avg_price": 152.0},
            {"symbol": "GOOGL", "quantity": 30, "avg_price": 175.0},  # Not in targets
        ]
        plan = rebalancer.analyze(positions, quotes, 500.0)
        googl_drift = [d for d in plan.drifts if d.symbol == "GOOGL"]
        assert len(googl_drift) == 1
        assert googl_drift[0].target_pct == 0


class TestDriftThreshold:
    """Trades only generated when drift exceeds threshold."""

    def test_small_drift_no_trades(self, rebalancer, quotes):
        targets = [
            AllocationTarget("AAPL", 50.0),
            AllocationTarget("MSFT", 45.0),
        ]
        rebalancer.set_targets(targets)
        # Nearly perfect allocation
        positions = [
            {"symbol": "AAPL", "quantity": 31, "avg_price": 152.0},  # 4712 ~49.5%
            {"symbol": "MSFT", "quantity": 10, "avg_price": 410.0},  # 4100 ~43.1%
        ]
        plan = rebalancer.analyze(positions, quotes, 700.0)
        # Drift should be small
        for d in plan.drifts:
            if d.action != "HOLD":
                # If there are trades, drift must exceed threshold
                assert abs(d.drift_pct) >= rebalancer.config.drift_threshold_pct


class TestMinTradeValue:
    """Trades below min_trade_value are skipped."""

    def test_tiny_drift_skipped(self):
        rb = Rebalancer(config=RebalanceConfig(
            drift_threshold_pct=1.0,  # Very sensitive
            min_trade_value=500.0,    # But high min trade
        ))
        targets = [AllocationTarget("AAPL", 95.0)]
        rb.set_targets(targets)
        positions = [
            {"symbol": "AAPL", "quantity": 60, "avg_price": 152.0},  # 9120
        ]
        quotes = {"AAPL": 152.0}
        plan = rb.analyze(positions, quotes, 1000.0)
        # Even if drift > 1%, trade value might be < $500
        for t in plan.trades_needed:
            assert abs(t.value_delta) >= 500.0 or t.action == "HOLD"


class TestSellBeforeBuy:
    """Trades should be ordered: sells first, then buys."""

    def test_sell_before_buy_ordering(self, rebalancer, quotes):
        targets = [
            AllocationTarget("AAPL", 30.0),
            AllocationTarget("MSFT", 65.0),
        ]
        rebalancer.set_targets(targets)
        positions = [
            {"symbol": "AAPL", "quantity": 50, "avg_price": 152.0},  # 7600 overweight
            {"symbol": "MSFT", "quantity": 2, "avg_price": 410.0},   # 820 underweight
        ]
        plan = rebalancer.analyze(positions, quotes, 500.0)
        if len(plan.trades_needed) >= 2:
            # First trade should be SELL
            assert plan.trades_needed[0].action == "SELL"


class TestRebalancePlanFormat:

    def test_format_balanced(self):
        plan = RebalancePlan(
            total_value=10000.0, cash=500.0,
            is_balanced=True, max_drift=1.5,
        )
        text = plan.format()
        assert "已平衡" in text

    def test_format_with_trades(self):
        plan = RebalancePlan(
            total_value=10000.0, cash=500.0,
            is_balanced=False, max_drift=8.0,
            drifts=[
                PositionDrift("AAPL", 50.0, 58.0, 8.0, 5800, 5000, "SELL", -5, -760.0),
                PositionDrift("MSFT", 45.0, 37.0, -8.0, 3700, 4500, "BUY", 2, 800.0),
            ],
            trades_needed=[
                PositionDrift("AAPL", 50.0, 58.0, 8.0, 5800, 5000, "SELL", -5, -760.0),
                PositionDrift("MSFT", 45.0, 37.0, -8.0, 3700, 4500, "BUY", 2, 800.0),
            ],
        )
        text = plan.format()
        assert "需要调仓" in text
        assert "SELL" in text
        assert "BUY" in text


class TestPresetAllocations:

    def test_presets_exist(self):
        assert "conservative" in PRESET_ALLOCATIONS
        assert "tech" in PRESET_ALLOCATIONS
        assert "balanced" in PRESET_ALLOCATIONS

    def test_preset_weights_under_100(self):
        for name, (label, targets) in PRESET_ALLOCATIONS.items():
            total = sum(t.target_pct for t in targets)
            assert total <= 100, "%s total weight %s > 100" % (name, total)

    def test_tech_has_expected_symbols(self):
        symbols = {t.symbol for t in TECH_GROWTH_ALLOCATION}
        assert "AAPL" in symbols
        assert "NVDA" in symbols
        assert "MSFT" in symbols


class TestIBKRFieldCompatibility:
    """Verify rebalancer handles both avg_price and avg_cost fields."""

    def test_avg_cost_field(self, rebalancer, quotes):
        targets = [AllocationTarget("AAPL", 95.0)]
        rebalancer.set_targets(targets)
        # IBKR uses avg_cost instead of avg_price
        positions = [
            {"symbol": "AAPL", "quantity": 50, "avg_cost": 152.0},
        ]
        plan = rebalancer.analyze(positions, quotes, 500.0)
        aapl = [d for d in plan.drifts if d.symbol == "AAPL"]
        assert len(aapl) == 1
        assert aapl[0].current_value > 0  # Should have computed value
