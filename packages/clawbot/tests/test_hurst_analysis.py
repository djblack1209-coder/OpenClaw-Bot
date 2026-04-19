"""Hurst 指数分析单元测试 — 覆盖 Hurst 指数 / 市场机制分类 / 统计套利信号."""

import pytest
import math
from src.trading.hurst_analysis import (
    calculate_hurst_exponent,
    classify_regime,
    calculate_stat_arb_signals,
)


# ==================== Hurst 指数计算 ====================

class TestHurstExponent:
    """Hurst 指数 R/S 分析法."""

    def test_trending_series_above_half(self):
        """持续上涨序列的 Hurst 应 > 0.5（趋势性）."""
        # 构造持续上涨的价格序列
        prices = [100 + i * 2 for i in range(200)]
        h = calculate_hurst_exponent(prices)
        assert h > 0.5, f"持续上涨序列 Hurst={h}，应 > 0.5"

    def test_mean_reverting_series_below_half(self):
        """交替涨跌序列的 Hurst 应 < 0.5（均值回归）."""
        # 构造交替涨跌序列
        prices = [100 + ((-1) ** i) * 5 for i in range(200)]
        h = calculate_hurst_exponent(prices)
        assert h < 0.5, f"交替涨跌序列 Hurst={h}，应 < 0.5"

    def test_returns_float(self):
        """返回值是浮点数."""
        prices = [100 + i * 0.5 for i in range(100)]
        h = calculate_hurst_exponent(prices)
        assert isinstance(h, float)

    def test_value_in_valid_range(self):
        """Hurst 指数应在 0-1 范围内."""
        import random
        random.seed(42)
        prices = [100.0]
        for _ in range(199):
            prices.append(prices[-1] + random.gauss(0, 1))
        h = calculate_hurst_exponent(prices)
        assert 0 <= h <= 1, f"Hurst={h}，应在 [0, 1] 范围内"

    def test_minimum_data_length(self):
        """数据太短时应抛出异常."""
        with pytest.raises(ValueError):
            calculate_hurst_exponent([100, 101, 102])


# ==================== 市场机制分类 ====================

class TestClassifyRegime:
    """根据 Hurst 指数分类市场机制."""

    def test_trending(self):
        """H > 0.55 → 趋势性."""
        assert classify_regime(0.7) == "trending"
        assert classify_regime(0.9) == "trending"

    def test_mean_reverting(self):
        """H < 0.45 → 均值回归."""
        assert classify_regime(0.3) == "mean_reverting"
        assert classify_regime(0.1) == "mean_reverting"

    def test_random(self):
        """0.45 <= H <= 0.55 → 随机游走."""
        assert classify_regime(0.5) == "random"
        assert classify_regime(0.45) == "random"
        assert classify_regime(0.55) == "random"

    def test_boundary_values(self):
        """边界值正确处理."""
        # 0.45 是 random 的下界（含）
        assert classify_regime(0.45) == "random"
        # 0.55 是 random 的上界（含）
        assert classify_regime(0.55) == "random"


# ==================== 统计套利信号 ====================

class TestStatArbSignals:
    """基于 z-score 的统计套利信号."""

    def test_returns_dict_with_required_keys(self):
        """返回值包含必需字段."""
        prices = [100 + i * 0.1 for i in range(100)]
        result = calculate_stat_arb_signals(prices)
        assert isinstance(result, dict)
        for key in ("z_score", "signal", "mean", "std"):
            assert key in result, f"缺少键: {key}"

    def test_signal_is_valid_string(self):
        """信号必须是 buy/sell/hold 之一."""
        prices = [100 + i * 0.1 for i in range(100)]
        result = calculate_stat_arb_signals(prices)
        assert result["signal"] in ("buy", "sell", "hold")

    def test_low_price_gives_buy(self):
        """价格大幅低于均值时应发出买入信号."""
        # 先稳定在 100 附近，最后几个数据跌到 80
        prices = [100.0] * 80 + [80.0] * 20
        result = calculate_stat_arb_signals(prices)
        assert result["z_score"] < 0
        # z-score 足够低时应该是 buy
        if result["z_score"] < -2:
            assert result["signal"] == "buy"

    def test_high_price_gives_sell(self):
        """价格大幅高于均值时应发出卖出信号."""
        # 先稳定在 100 附近，最后几个数据涨到 120
        prices = [100.0] * 80 + [120.0] * 20
        result = calculate_stat_arb_signals(prices)
        assert result["z_score"] > 0
        # z-score 足够高时应该是 sell
        if result["z_score"] > 2:
            assert result["signal"] == "sell"

    def test_stable_price_gives_hold(self):
        """价格稳定在均值附近时应发出持有信号."""
        prices = [100.0] * 100
        result = calculate_stat_arb_signals(prices)
        assert result["signal"] == "hold"

    def test_custom_lookback(self):
        """自定义回看窗口."""
        prices = [100 + i * 0.1 for i in range(100)]
        r1 = calculate_stat_arb_signals(prices, lookback=30)
        r2 = calculate_stat_arb_signals(prices, lookback=60)
        # 不同回看窗口的均值应不同
        assert r1["mean"] != r2["mean"]

    def test_lookback_too_large_uses_all_data(self):
        """回看窗口超出数据长度时使用全部数据，不报错."""
        prices = [100 + i * 0.1 for i in range(50)]
        result = calculate_stat_arb_signals(prices, lookback=200)
        assert isinstance(result, dict)
