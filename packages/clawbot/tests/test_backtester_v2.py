"""
Backtester v2 测试 — 覆盖 R16 审计中发现的测试缺口。
聚焦: Monte Carlo 模拟 + 增强指标 + run() 集成测试。

> 最后更新: 2026-03-28
"""
import pytest
import math
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.backtester import (
    Bar, BacktestConfig, PerformanceReport, Backtester,
    run_monte_carlo, calc_enhanced_metrics, format_monte_carlo,
    format_optimization_result,
)
from src.risk_config import RiskConfig


# ============ 辅助函数 ============

def _make_bars(start_price=100.0, num_bars=100, trend="up"):
    """生成合成K线数据用于回测测试"""
    bars = []
    price = start_price
    base_time = datetime(2024, 1, 1, 9, 30)
    for i in range(num_bars):
        if trend == "up":
            change = 0.5 + (i % 5) * 0.1  # 逐步上涨
        elif trend == "down":
            change = -(0.5 + (i % 5) * 0.1)  # 逐步下跌
        else:  # sideways
            change = 0.3 * (1 if i % 2 == 0 else -1)

        o = price
        h = price + abs(change) + 0.5
        l = price - abs(change) - 0.3
        c = price + change
        price = c
        bars.append(Bar(
            timestamp=base_time + timedelta(hours=i),
            open=round(o, 2), high=round(h, 2),
            low=round(l, 2), close=round(c, 2),
            volume=1000000
        ))
    return bars


def _make_report_with_equity(equity_curve, total_pnl=None, total_trades=None,
                              max_drawdown_pct=0, max_drawdown=0):
    """用给定的权益曲线构建 PerformanceReport"""
    daily_returns = []
    if len(equity_curve) >= 2:
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            if prev > 0:
                daily_returns.append((equity_curve[i] - prev) / prev * 100)

    if total_pnl is None:
        total_pnl = equity_curve[-1] - equity_curve[0] if equity_curve else 0
    if total_trades is None:
        total_trades = max(len(equity_curve) - 1, 0)

    return PerformanceReport(
        total_trades=total_trades,
        total_pnl=total_pnl,
        max_drawdown_pct=max_drawdown_pct,
        max_drawdown=max_drawdown,
        equity_curve=equity_curve,
        daily_returns=daily_returns,
    )


# ============ 蒙特卡洛模拟测试 ============

class TestRunMonteCarlo:
    """run_monte_carlo 函数的单元测试"""

    def test_monte_carlo_basic(self):
        """基本功能：正常权益曲线产出完整结果"""
        equity = [10000, 10100, 10050, 10200, 10300]
        report = _make_report_with_equity(equity, total_pnl=300)
        result = run_monte_carlo(report, initial_capital=10000, simulations=100)

        # 不应返回错误
        assert "error" not in result
        # 必须包含关键字段
        assert "median_pnl" in result
        assert "worst_5pct_pnl" in result
        assert "best_5pct_pnl" in result
        assert "ruin_probability" in result
        assert "simulations" in result
        assert result["simulations"] == 100

    def test_monte_carlo_empty_curve(self):
        """空权益曲线 → 返回错误字典"""
        report = _make_report_with_equity([], total_trades=0, total_pnl=0)
        result = run_monte_carlo(report, simulations=50)
        assert "error" in result

    def test_monte_carlo_single_point(self):
        """单点权益曲线 → 数据不足，返回错误"""
        report = _make_report_with_equity([10000], total_trades=0, total_pnl=0)
        result = run_monte_carlo(report, simulations=50)
        # 只有1个点无法计算收益率，应返回错误
        assert "error" in result

    def test_monte_carlo_ruin_detection(self):
        """持续暴跌的权益曲线 → 破产概率应大于等于0"""
        # 构造一个从10000暴跌到500的曲线
        equity = [10000]
        price = 10000
        for _ in range(50):
            price *= 0.90  # 每步跌10%
            equity.append(round(price, 2))
        report = _make_report_with_equity(equity, total_pnl=equity[-1] - 10000)

        result = run_monte_carlo(report, initial_capital=10000, simulations=200)
        assert "error" not in result
        # 破产概率是一个合法的非负数
        assert result["ruin_probability"] >= 0

    def test_monte_carlo_percentiles_ordered(self):
        """百分位数有序：worst_5pct <= median <= best_5pct"""
        # 使用有一定波动的权益曲线
        equity = [10000]
        price = 10000
        for i in range(80):
            change = 50 * (1 if i % 3 != 0 else -1.5)
            price += change
            equity.append(round(price, 2))
        report = _make_report_with_equity(equity, total_pnl=equity[-1] - 10000)

        result = run_monte_carlo(report, initial_capital=10000, simulations=500)
        assert "error" not in result
        # worst_5pct_pnl <= median_pnl <= best_5pct_pnl
        assert result["worst_5pct_pnl"] <= result["median_pnl"]
        assert result["median_pnl"] <= result["best_5pct_pnl"]


# ============ 增强指标测试 ============

class TestCalcEnhancedMetrics:
    """calc_enhanced_metrics 函数的单元测试"""

    def test_enhanced_metrics_basic(self):
        """基本功能：含正常数据的报告返回完整指标"""
        # 构造一条有波动的权益曲线
        equity = [10000]
        price = 10000
        for i in range(60):
            change = 20 * (1 if i % 3 != 2 else -2)
            price += change
            equity.append(round(price, 2))

        report = _make_report_with_equity(
            equity,
            total_pnl=500,
            total_trades=30,
            max_drawdown_pct=10.0,
            max_drawdown=1000,
        )

        result = calc_enhanced_metrics(report)
        assert "error" not in result
        # 检查所有必需字段
        assert "sortino_ratio" in result
        assert "calmar_ratio" in result
        assert "sqn" in result
        assert "sqn_rating" in result
        assert "recovery_factor" in result
        assert "max_consecutive_losses" in result
        assert "max_consecutive_wins" in result

    def test_enhanced_metrics_no_drawdown(self):
        """最大回撤为0时 → calmar_ratio = 0（不是无穷大）"""
        equity = [10000, 10100, 10200, 10300, 10400]
        report = _make_report_with_equity(
            equity,
            total_pnl=400,
            total_trades=4,
            max_drawdown_pct=0,
            max_drawdown=0,
        )
        result = calc_enhanced_metrics(report)
        assert "error" not in result
        assert result["calmar_ratio"] == 0

    def test_enhanced_metrics_no_data(self):
        """无权益曲线数据 → 返回错误"""
        report = PerformanceReport(
            total_trades=0,
            total_pnl=0,
            equity_curve=[],
            daily_returns=[],
        )
        result = calc_enhanced_metrics(report)
        assert "error" in result

    def test_sqn_rating_excellent(self):
        """SQN >= 2.5 → 评级为'优秀'"""
        # 构造一条持续稳定上涨的曲线，使 SQN 很高
        equity = [10000]
        for i in range(200):
            # 稳定小幅上涨，偶尔微跌，使 avg_return 高、std 低
            equity.append(equity[-1] * 1.002)

        report = _make_report_with_equity(
            equity,
            total_pnl=equity[-1] - 10000,
            total_trades=200,
            max_drawdown_pct=2.0,
            max_drawdown=200,
        )
        result = calc_enhanced_metrics(report)
        assert "error" not in result
        # 200个数据点、稳定正收益 → SQN 应该很高
        assert result["sqn"] >= 2.5
        assert result["sqn_rating"] == "优秀"

    def test_sortino_positive_with_mixed_returns(self):
        """混合正负收益时 → sortino 应为正数（如果整体上涨）"""
        # 构造正收益为主、偶有下跌的曲线
        equity = [10000]
        for i in range(100):
            if i % 5 == 0:
                equity.append(equity[-1] * 0.995)  # 偶尔微跌
            else:
                equity.append(equity[-1] * 1.004)  # 多数上涨
        report = _make_report_with_equity(
            equity,
            total_pnl=equity[-1] - 10000,
            total_trades=100,
            max_drawdown_pct=5.0,
            max_drawdown=500,
        )
        result = calc_enhanced_metrics(report)
        assert "error" not in result
        assert result["sortino_ratio"] > 0


# ============ 回测引擎 run() 集成测试 ============

class TestBacktesterRun:
    """Backtester.run() 集成测试，mock ta_engine 依赖"""

    def _mock_indicators(self, score=60, trend="up", rsi6=50, atr_pct=2.0):
        """构造 mock 的技术指标和信号"""
        indicators = {
            "trend": trend,
            "rsi_6": rsi6,
            "atr_pct": atr_pct,
            "macd": 1.0,
            "macd_signal": 0.5,
        }
        signal = {"score": score, "reasons": ["test"]}
        return indicators, signal

    @patch("src.ta_engine.compute_signal_score")
    @patch("src.ta_engine.compute_indicators")
    def test_run_uptrend_produces_trades(self, mock_indicators, mock_signal):
        """上涨趋势100根K线 → 应产生交易"""
        indicators, signal = self._mock_indicators(score=60, trend="up")
        mock_indicators.return_value = indicators
        mock_signal.return_value = signal

        bars = _make_bars(start_price=100.0, num_bars=100, trend="up")
        config = BacktestConfig(
            initial_capital=100000,
            min_score=30,
            max_concurrent=5,
            max_trades_per_day=10,
        )
        bt = Backtester(config=config)
        report = bt.run("TEST", bars, lookback=5)

        assert report.total_trades > 0

    @patch("src.ta_engine.compute_signal_score")
    @patch("src.ta_engine.compute_indicators")
    def test_run_respects_max_concurrent(self, mock_indicators, mock_signal):
        """max_concurrent_positions=1 → 同一时间最多1个持仓"""
        indicators, signal = self._mock_indicators(score=60, trend="up")
        mock_indicators.return_value = indicators
        mock_signal.return_value = signal

        bars = _make_bars(start_price=100.0, num_bars=100, trend="up")
        config = BacktestConfig(
            initial_capital=100000,
            min_score=30,
            max_concurrent=1,
            max_trades_per_day=10,
        )
        bt = Backtester(config=config)

        # 监控 _open_trade 来记录每次开仓时的持仓数
        max_seen = [0]
        original_open = bt._open_trade

        def tracking_open(*args, **kwargs):
            original_open(*args, **kwargs)
            if len(bt._open_trades) > max_seen[0]:
                max_seen[0] = len(bt._open_trades)

        bt._open_trade = tracking_open
        bt.run("TEST", bars, lookback=5)

        # 同一时间持仓不应超过 max_concurrent=1
        assert max_seen[0] <= 1

    def test_run_empty_bars(self):
        """空K线列表 → total_trades=0"""
        config = BacktestConfig(initial_capital=10000)
        bt = Backtester(config=config)
        report = bt.run("TEST", [], lookback=5)
        assert report.total_trades == 0

    @patch("src.ta_engine.compute_signal_score")
    @patch("src.ta_engine.compute_indicators")
    def test_report_contains_all_fields(self, mock_indicators, mock_signal):
        """run() 返回的报告应包含所有关键字段"""
        indicators, signal = self._mock_indicators(score=60, trend="up")
        mock_indicators.return_value = indicators
        mock_signal.return_value = signal

        bars = _make_bars(start_price=100.0, num_bars=100, trend="up")
        config = BacktestConfig(
            initial_capital=100000,
            min_score=30,
            max_concurrent=5,
            max_trades_per_day=10,
        )
        bt = Backtester(config=config)
        report = bt.run("TEST", bars, lookback=5)

        # 验证报告包含全部关键字段
        assert hasattr(report, "total_trades")
        assert hasattr(report, "total_pnl")
        assert hasattr(report, "win_rate")
        assert hasattr(report, "max_drawdown_pct")
        assert hasattr(report, "sharpe_ratio")
        assert hasattr(report, "equity_curve")
        assert hasattr(report, "daily_returns")
        assert isinstance(report.equity_curve, list)
        assert isinstance(report.daily_returns, list)
        # 权益曲线长度 = 处理的K线数（总K线 - lookback）
        assert len(report.equity_curve) == len(bars) - 5


# ============ 格式化函数测试 ============

class TestFormatters:
    """格式化函数的测试"""

    def test_format_monte_carlo_valid(self):
        """正常蒙特卡洛结果格式化 → 包含关键中文标签"""
        mc_result = {
            "simulations": 1000,
            "original_pnl": 500.0,
            "median_pnl": 480.0,
            "worst_5pct_pnl": -200.0,
            "best_5pct_pnl": 1200.0,
            "ruin_probability": 2.5,
            "median_max_drawdown": 8.5,
            "worst_5pct_max_drawdown": 25.0,
            "confidence_intervals": {
                "5%": {"final_equity": 9800, "pnl": -200, "max_drawdown_pct": 25.0},
                "50%": {"final_equity": 10480, "pnl": 480, "max_drawdown_pct": 8.5},
                "95%": {"final_equity": 11200, "pnl": 1200, "max_drawdown_pct": 3.0},
            },
        }
        text = format_monte_carlo(mc_result)
        assert "蒙特卡洛" in text
        assert "破产概率" in text
        assert "中位数" in text
        assert "1000" in text

    def test_format_monte_carlo_error(self):
        """错误结果格式化 → 包含失败字样"""
        mc_result = {"error": "无交易数据"}
        text = format_monte_carlo(mc_result)
        assert "失败" in text

    def test_format_optimization_result_valid(self):
        """正常优化结果格式化 → 包含关键标签"""
        opt_result = {
            "symbol": "AAPL",
            "total_combinations": 27,
            "optimize_metric": "sharpe_ratio",
            "best_params": {"min_score": 30, "atr_sl_mult": 1.5},
            "best_metric": 2.1,
            "all_results": [
                {
                    "params": {"min_score": 30},
                    "metric": 2.1,
                    "win_rate": 65.0,
                    "sharpe_ratio": 2.1,
                    "total_pnl": 800,
                    "max_drawdown_pct": 5.0,
                },
            ],
        }
        text = format_optimization_result(opt_result)
        assert "参数优化" in text
        assert "AAPL" in text
        assert "最优参数" in text
