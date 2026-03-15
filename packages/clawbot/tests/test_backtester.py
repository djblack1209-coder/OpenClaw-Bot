"""
Tests for Backtester - using synthetic data (no yfinance dependency).
"""
import pytest
from datetime import datetime, timedelta

from src.backtester import (
    Backtester, BacktestConfig, BacktestTrade, Bar, PerformanceReport,
    bars_to_dataframe,
)
from src.risk_manager import RiskConfig


def _make_bars(prices, start=None, volume=1000000):
    """Generate synthetic bars from a list of close prices."""
    if start is None:
        start = datetime(2025, 1, 2, 9, 30)
    bars = []
    for i, p in enumerate(prices):
        t = start + timedelta(days=i)
        # Skip weekends
        while t.weekday() >= 5:
            t += timedelta(days=1)
        bars.append(Bar(
            timestamp=t,
            open=p * 0.998,
            high=p * 1.01,
            low=p * 0.99,
            close=p,
            volume=volume,
        ))
        start = t
    return bars


def _make_trending_bars(start_price, num_bars, trend_pct=0.005):
    """Generate bars with a consistent uptrend."""
    prices = []
    p = start_price
    for _ in range(num_bars):
        p *= (1 + trend_pct)
        prices.append(round(p, 2))
    return _make_bars(prices)


def _make_volatile_bars(start_price, num_bars, swing_pct=0.03):
    """Generate bars that swing up and down."""
    prices = []
    p = start_price
    for i in range(num_bars):
        if i % 2 == 0:
            p *= (1 + swing_pct)
        else:
            p *= (1 - swing_pct)
        prices.append(round(p, 2))
    return _make_bars(prices)


class TestBar:
    def test_bar_creation(self):
        b = Bar(datetime.now(), 100.0, 105.0, 95.0, 102.0, 1000)
        assert b.close == 102.0
        assert b.high == 105.0


class TestBarsToDataframe:
    def test_conversion(self):
        bars = _make_bars([100, 101, 102])
        df = bars_to_dataframe(bars)
        assert len(df) == 3
        assert "Close" in df.columns
        assert "Volume" in df.columns
        assert float(df["Close"].iloc[-1]) == 102.0


class TestBacktestConfig:
    def test_defaults(self):
        c = BacktestConfig()
        assert c.initial_capital == 10000.0
        assert c.min_score == 30
        assert c.max_concurrent == 5


class TestPerformanceReport:
    def test_format_no_trades(self):
        r = PerformanceReport()
        text = r.format()
        assert "回测绩效报告" in text
        assert "0" in text

    def test_format_with_data(self):
        r = PerformanceReport(
            total_trades=10, winning_trades=6, losing_trades=4,
            win_rate=60.0, total_pnl=150.0, total_pnl_pct=1.5,
            avg_win=50.0, avg_loss=-25.0, profit_factor=2.0,
            max_drawdown=80.0, max_drawdown_pct=0.8,
            sharpe_ratio=1.5, avg_hold_bars=3.2,
            start_date="2025-01-01", end_date="2025-12-31",
            trading_days=252,
        )
        text = r.format()
        assert "60.0%" in text
        assert "$+150.00" in text


class TestBacktesterShouldEnter:
    """Test the _should_enter filter logic."""

    def test_high_score_uptrend_enters(self):
        bt = Backtester()
        assert bt._should_enter(60, "up", 50) is True

    def test_low_score_filtered(self):
        bt = Backtester()
        assert bt._should_enter(20, "up", 50) is False

    def test_downtrend_filtered(self):
        bt = Backtester()
        assert bt._should_enter(60, "strong_down", 50) is False

    def test_overbought_filtered(self):
        bt = Backtester()
        assert bt._should_enter(60, "up", 80) is False

    def test_max_concurrent_reached(self):
        bt = Backtester(config=BacktestConfig(max_concurrent=2))
        # Simulate 2 open trades
        bt._open_trades = [BacktestTrade(1, "A", "BUY", 1, 100, datetime.now()),
                           BacktestTrade(2, "B", "BUY", 1, 100, datetime.now())]
        assert bt._should_enter(60, "up", 50) is False

    def test_max_trades_per_day_reached(self):
        bt = Backtester(config=BacktestConfig(max_trades_per_day=1))
        bt._trades_today = 1
        assert bt._should_enter(60, "up", 50) is False


class TestBacktesterTradeManagement:
    """Test open/close trade mechanics."""

    def test_open_trade_deducts_capital(self):
        bt = Backtester(config=BacktestConfig(initial_capital=10000, commission_per_trade=1.0))
        bt._open_trade("AAPL", 10, 150.0, datetime.now(), 145.0, 162.0, 60)
        # Cost = 10*150 + 1 = 1501
        assert bt._capital == pytest.approx(10000 - 1501, abs=0.01)
        assert len(bt._open_trades) == 1
        assert bt._trades_today == 1

    def test_close_trade_returns_capital(self):
        bt = Backtester(config=BacktestConfig(initial_capital=10000, commission_per_trade=1.0))
        bt._open_trade("AAPL", 10, 150.0, datetime.now(), 145.0, 162.0, 60)
        trade = bt._open_trades[0]
        bt._close_trade(trade, 155.0, datetime.now(), "take_profit")
        # Returns: 10*155 - 1 = 1549
        # PnL: (155-150)*10 - 1 = 49
        assert trade.pnl == pytest.approx(49.0, abs=0.01)
        assert len(bt._open_trades) == 0
        assert len(bt._closed_trades) == 1

    def test_close_trade_loss(self):
        bt = Backtester(config=BacktestConfig(initial_capital=10000, commission_per_trade=1.0))
        bt._open_trade("AAPL", 10, 150.0, datetime.now(), 145.0, 162.0, 60)
        trade = bt._open_trades[0]
        bt._close_trade(trade, 145.0, datetime.now(), "stop_loss")
        # PnL: (145-150)*10 - 1 = -51
        assert trade.pnl == pytest.approx(-51.0, abs=0.01)


class TestBacktesterCheckExits:
    """Test exit condition checking on bars."""

    def test_stop_loss_triggered(self):
        bt = Backtester()
        bt._open_trade("AAPL", 10, 150.0, datetime.now(), 145.0, 162.0, 60)
        bar = Bar(datetime.now(), 146, 147, 144, 145, 1000000)  # low=144 < SL=145
        bt._check_exits(bar)
        assert len(bt._open_trades) == 0
        assert bt._closed_trades[0].exit_reason == "stop_loss"

    def test_take_profit_triggered(self):
        bt = Backtester()
        bt._open_trade("AAPL", 10, 150.0, datetime.now(), 145.0, 162.0, 60)
        bar = Bar(datetime.now(), 160, 163, 159, 161, 1000000)  # high=163 > TP=162
        bt._check_exits(bar)
        assert len(bt._open_trades) == 0
        assert bt._closed_trades[0].exit_reason == "take_profit"

    def test_trailing_stop_updates_and_triggers(self):
        bt = Backtester(config=BacktestConfig(trailing_stop_pct=0.05))
        bt._open_trade("AAPL", 10, 100.0, datetime.now(), 90.0, 120.0, 60)
        trade = bt._open_trades[0]
        # Initial trailing: 100 * 0.95 = 95.0

        # Price rises to 110 -> trailing moves to 110*0.95=104.5
        bar1 = Bar(datetime.now(), 108, 110, 107, 109, 1000000)
        bt._check_exits(bar1)
        assert trade.trailing_stop_price == 104.5
        assert len(bt._open_trades) == 1  # Still open

        # Price drops to 104 -> triggers trailing stop at 104.5
        bar2 = Bar(datetime.now(), 106, 107, 104, 105, 1000000)
        bt._check_exits(bar2)
        assert len(bt._open_trades) == 0
        assert bt._closed_trades[0].exit_reason == "trailing_stop"

    def test_no_exit_when_price_in_range(self):
        bt = Backtester()
        bt._open_trade("AAPL", 10, 150.0, datetime.now(), 145.0, 162.0, 60)
        # high=153 -> trailing moves to 153*0.97=148.41, low=149 > 148.41 -> no trigger
        bar = Bar(datetime.now(), 150, 153, 149, 152, 1000000)
        bt._check_exits(bar)
        assert len(bt._open_trades) == 1  # Still open


class TestBacktesterEquity:
    """Test equity tracking and drawdown."""

    def test_equity_recorded(self):
        bt = Backtester(config=BacktestConfig(initial_capital=10000))
        bar = Bar(datetime.now(), 100, 101, 99, 100, 1000000)
        bt._record_equity(bar)
        assert len(bt._equity_curve) == 1
        assert bt._equity_curve[0] == 10000.0

    def test_drawdown_tracked(self):
        bt = Backtester(config=BacktestConfig(initial_capital=10000))
        bt._peak_equity = 10000
        # Simulate capital drop
        bt._capital = 9500
        bar = Bar(datetime.now(), 100, 101, 99, 100, 1000000)
        bt._record_equity(bar)
        assert bt._max_drawdown == 500.0
        assert bt._max_drawdown_pct == pytest.approx(5.0, abs=0.1)


class TestBacktesterReport:
    """Test report generation."""

    def test_empty_report(self):
        bt = Backtester()
        report = bt._generate_report([])
        assert report.total_trades == 0

    def test_report_with_trades(self):
        bt = Backtester(config=BacktestConfig(initial_capital=10000))
        # Manually add closed trades
        bt._closed_trades = [
            BacktestTrade(1, "AAPL", "BUY", 10, 150.0, datetime(2025, 1, 2),
                          exit_price=155.0, pnl=49.0, pnl_pct=3.27, bars_held=3),
            BacktestTrade(2, "AAPL", "BUY", 10, 152.0, datetime(2025, 1, 5),
                          exit_price=148.0, pnl=-41.0, pnl_pct=-2.63, bars_held=2),
            BacktestTrade(3, "AAPL", "BUY", 10, 149.0, datetime(2025, 1, 8),
                          exit_price=156.0, pnl=69.0, pnl_pct=4.70, bars_held=4),
        ]
        bars = _make_bars([150] * 60)
        report = bt._generate_report(bars)
        assert report.total_trades == 3
        assert report.winning_trades == 2
        assert report.losing_trades == 1
        assert report.win_rate == pytest.approx(66.67, abs=0.1)
        assert report.total_pnl == pytest.approx(77.0, abs=0.1)
        assert report.profit_factor > 1.0
        assert report.avg_hold_bars == 3.0
