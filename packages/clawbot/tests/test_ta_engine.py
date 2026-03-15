"""
ta_engine 单元测试 — 覆盖纯逻辑函数（信号评分/趋势判定/仓位计算/格式化）
"""
import pytest
from src.ta_engine import (
    _judge_trend,
    compute_signal_score,
    _score_bar,
    calc_position_size,
    format_analysis,
    format_scan_results,
)


# ============ _judge_trend ============

class TestJudgeTrend:
    def test_strong_up(self):
        ind = {"ema_5": 100, "ema_10": 95, "ema_20": 90, "ema_50": 80}
        assert _judge_trend(ind) == "strong_up"

    def test_up(self):
        ind = {"ema_5": 100, "ema_10": 95, "ema_20": 90, "ema_50": 105}
        assert _judge_trend(ind) == "up"

    def test_strong_down(self):
        ind = {"ema_5": 80, "ema_10": 85, "ema_20": 90, "ema_50": 100}
        assert _judge_trend(ind) == "strong_down"

    def test_down(self):
        ind = {"ema_5": 80, "ema_10": 85, "ema_20": 90, "ema_50": 75}
        assert _judge_trend(ind) == "down"

    def test_sideways(self):
        ind = {"ema_5": 90, "ema_10": 100, "ema_20": 85, "ema_50": 95}
        assert _judge_trend(ind) == "sideways"

    def test_missing_keys_defaults_sideways(self):
        assert _judge_trend({}) == "sideways"

    def test_equal_emas_sideways(self):
        ind = {"ema_5": 100, "ema_10": 100, "ema_20": 100, "ema_50": 100}
        assert _judge_trend(ind) == "sideways"


# ============ compute_signal_score ============

class TestComputeSignalScore:
    def test_neutral_defaults(self):
        result = compute_signal_score({})
        assert result["signal"] == "NEUTRAL"
        assert -10 < result["score"] < 10

    def test_rsi_oversold_positive(self):
        result = compute_signal_score({"rsi_14": 25, "rsi_6": 50})
        assert result["score"] > 0
        assert any("超卖" in r for r in result["reasons"])

    def test_rsi_ovetive(self):
        result = compute_signal_score({"rsi_14": 75, "rsi_6": 50})
        assert result["score"] < 0
        assert any("超买" in r for r in result["reasons"])

    def test_rsi6_extreme_oversold(self):
        result = compute_signal_score({"rsi_14": 50, "rsi_6": 15})
        assert result["score"] > 0
        assert any("RSI6" in r for r in result["reasons"])

    def test_rsi6_extreme_overbought(self):
        result = compute_signal_score({"rsi_14": 50, "rsi_6": 85})
        assert result["score"] < 0

    def test_macd_golden_cross(self):
        result = compute_signal_score({"macd_hist": 0.5, "macd_hist_rising": True})
        assert result["score"] > 0
        assert any("MACD金叉" in r for r in result["reasons"])

    def test_macd_death_cross(self):
        result = compute_signal_score({"macd_hist": -0.5, "macd_hist_rising": False})
        assert result["score"] < 0
        assert any("MACD死叉" in r for r in result["reasons"])

    def test_strong_up_trend(self):
        result = compute_signal_score({"trend": "strong_up"})
        assert result["score"] > 0
        assert any("多头排列" in r for r in result["reasons"])

    def test_strong_down_trend(self):
        result = compute_signal_score({"trend": "strong_down"})
        assert result["score"] < 0
        assert any("空头排列" in r for r in result["reasons"])

    def test_bb_lower_band_positive(self):
        result = compute_signal_score({"bb_position": 0.05})
        assert result["score"] > 0
        assert any("布林下轨" in r for r in result["reasons"])

    def test_bb_upper_band_negative(self):
        result = compute_signal_score({"bb_position": 0.95})
        assert result["score"] < 0
        assert any("布林上轨" in r for r in result["reasons"])

    def test_volume_surge_up(self):
        result = compute_signal_score({
            "volume_surge": True, "vol_ratio": 2.5,
            "price": 150, "ema_5": 145,
        })
        assert result["score"] > 0
        assert any("放量上涨" in r for r in result["reasons"])

    def test_volume_surge_down(self):
        result = compute_signal_score({
            "volume_surge": True, "vol_ratio": 2.5,
            "price": 140, "ema_5": 145,
        })
        assert result["score"] < 0
        assert any("放量下跌" in r for r in result["reasons"])

    def test_adx_strong_trend_up(self):
        result = compute_signal_score({"adx": 45, "trend": "strong_up"})
        assert result["score"] > 0
        assert any("ADX" in r for r in result["reasons"])

    def test_adx_low_sideways(self):
        result = compute_signal_score({"adx": 15, "trend": "sideways"})
        assert any("震荡市" in r for r in result["reasons"])

    def test_score_clamped_max(self):
        # 所有极端看多信号叠加
        ind = {
            "rsi_14": 20, "rsi_6": 15,
            "macd_hist": 1.0, "macd_hist_rising": True,
            "trend": "strong_up",
            "bb_position": 0.05,
            "volume_surge": True, "vol_ratio": 3.0,
            "price": 150, "ema_5": 140,
            "adx": 50,
        }
        result = compute_signal_score(ind)
        assert result["score"] <= 100

    def test_score_clamped_min(self):
        ind = {
            "rsi_14": 80, "rsi_6": 90,
            "macd_hist": -1.0, "macd_hist_rising": False,
            "trend": "strong_down",
            "bb_position": 0.95,
            "volume_surge": True, "vol_ratio": 3.0,
            "price": 130, "ema_5": 140,
            "adx": 50,
        }
        result = compute_signal_score(ind)
        assert result["score"] >= -100

    def test_signal_labels(self):
        """验证所有信号标签映射"""
        # STRONG_BUY: score >= 60
        r = compute_signal_score({
            "rsi_14": 25, "rsi_6": 15,
            "macd_hist": 1.0, "macd_hist_rising": True,
            "trend": "strong_up", "bb_position": 0.05,
        })
        assert r["signal"] == "STRONG_BUY"
        assert r["signal_cn"] == "强烈买入"

    def test_signal_strong_sell(self):
        r = compute_signal_score({
            "rsi_14": 80, "rsi_6": 90,
            "macd_hist": -1.0, "macd_hist_rising": False,
            "trend": "strong_down", "bb_position": 0.95,
        })
        assert r["signal"] == "STRONG_SELL"


# ============ _score_bar ============

class TestScoreBar:
    def test_zero(self):
        bar = _score_bar(0)
        assert bar == "[=====-----]"

    def test_max(self):
        bar = _score_bar(100)
        assert bar == "[==========]"

    def test_min(self):
        bar = _score_bar(-100)
        assert bar == "[----------]"

    def test_positive(self):
        bar = _score_bar(60)
        assert "=" in bar and "-" in bar


# ============ calc_position_size ============

class TestCalcPositionSize:
    def test_normal_case(self):
        result = calc_position_size(
            capital=100000, risk_pct=0.02,
            entry=150.0, stop_loss=145.0,
        )
        assert result["shares"] == 400  # 2000 / 5 = 400
        assert result["total_cost"] == 60000.0
        assert result["max_loss"] == 2000.0
        assert result["risk_amount"] == 2000.0

    def test_stop_loss_equals_entry(self):
        result = calc_position_size(
            capital=100000, risk_pct=0.02,
            entry=150.0, stop_loss=150.0,
        )
        assert "error" in result

    def test_short_position(self):
        """做空：止损在入场价上方"""
        result = calc_position_size(
            capital=100000, risk_pct=0.01,
            entry=100.0, stop_loss=105.0,
        )
        assert result["shares"] == 200  # 1000 / 5 = 200
        assert result["total_cost"] == 20000.0

    def test_small_capital(self):
        result = calc_position_size(
            capital=1000, risk_pct=0.02,
            entry=500.0, stop_loss=490.0,
        )
        assert result["shares"] == 2  # 20 / 10 = 2


# ============ format_analysis ============

class TestFormatAnalysis:
    def test_error_passthrough(self):
        assert format_analysis({"error": "数据不足"}) == "数据不足"

    def test_normal_output(self):
        data = {
            "name": "Apple Inc.",
            "symbol": "AAPL",
            "price": 150.0,
            "change": 2.5,
            "change_pct": 1.7,
            "indicators": {
                "trend": "up",
                "ema_5": 149, "ema_10": 148, "ema_20": 146,
                "rsi_6": 55, "rsi_14": 52,
                "macd": 0.5, "macd_signal": 0.3, "macd_hist": 0.2,
                "bb_upper": 155, "bb_middle": 150, "bb_lower": 145,
                "bb_position": 0.5,
                "atr_14": 3.2, "atr_pct": 2.1,
            },
            "support_resistance": {"supports": [145.0], "resistances": [155.0]},
            "signal": {"score": 35, "signal_cn": "买入", "reasons": ["EMA多头排列"]},
        }
        text = format_analysis(data)
        assert "Apple Inc." in text
        assert "AAPL" in text
        assert "$150.0" in text
        assert "买入" in text
        assert "阻力位" in text
        assert "支撑位" in text


# ============ format_scan_results ============

class TestFormatScanResults:
    def test_empty(self):
        result = format_scan_results([])
        assert "暂无明显信号" in result

    def test_with_signals(self):
        signals = [
            {
                "symbol": "AAPL", "price": 150.0, "change_pct": 1.5,
                "score": 45, "signal": "BUY", "signal_cn": "买入",
                "reasons": ["RSI超卖"], "rsi_6": 28, "volume_surge": True,
            },
            {
                "symbol": "TSLA", "price": 200.0, "change_pct": -2.0,
                "score": -35, "signal": "SELL", "signal_cn": "卖出",
                "reasons": ["MACD死叉"], "rsi_6": 72, "volume_surge": False,
            },
        ]
        text = format_scan_results(signals)
        assert "AAPL" in text
        assert "TSLA" in text
        assert "买入信号" in text
        assert "卖出信号" in text
        assert "[放量]" in text
