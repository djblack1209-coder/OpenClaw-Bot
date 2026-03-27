"""
RiskManager v2 高优先级测试 — 极端行情检测 + 凯利公式仓位计算

覆盖场景：
  - check_extreme_market: ATR 飙升 / 闪崩 / VIX 熔断 / 正常行情
  - calc_kelly_quantity: 历史充足 / 不足回退 / 负期望值
"""
import pytest
from unittest.mock import MagicMock

from src.risk_manager import RiskManager, RiskConfig
from src.utils import now_et


# ============ 极端行情检测 (check_extreme_market) ============

class TestCheckExtremeMarket:
    """检测极端行情条件: ATR 飙升、闪崩、VIX 熔断"""

    @pytest.fixture
    def rm(self, risk_config, mock_journal):
        """复用 conftest 中的 risk_config 和 mock_journal"""
        mgr = RiskManager(config=risk_config, journal=mock_journal)
        mgr._last_pnl_update = now_et().strftime('%Y-%m-%d')
        mgr._last_refresh_ts = now_et()
        return mgr

    def test_check_extreme_market_atr_spike(self, rm):
        """当前 ATR > 阈值倍数 * 均值 ATR → 返回 "extreme"

        默认阈值 volatility_spike_threshold=3.0（conftest 里可能不同，
        但 RiskConfig 默认是 3.0）。
        这里用 current_atr=0.10, avg_atr=0.03 → 3.33x > 3.0x 阈值。
        """
        condition, warnings = rm.check_extreme_market(
            symbol="AAPL",
            current_atr=0.10,
            avg_atr=0.03,
        )
        assert condition == "extreme"
        assert len(warnings) > 0
        assert "波动率飙升" in warnings[0]

    def test_check_extreme_market_flash_crash(self, rm):
        """单根 K 线跌幅超过 flash_crash_pct (默认 5%) → 返回 "extreme"

        注意: 代码比较的是 abs(price_change_pct) > flash_crash_pct * 100
        所以传 price_change_pct=-6.0 表示跌 6%，阈值 5*100=5% → 6>5 触发。
        """
        condition, warnings = rm.check_extreme_market(
            symbol="AAPL",
            price_change_pct=-6.0,  # 跌 6%
        )
        assert condition == "extreme"
        assert any("闪崩" in w for w in warnings)

    def test_check_extreme_market_vix_high(self, rm):
        """VIX 超过 circuit_breaker_vix_level (默认 35) → 返回 "halted" """
        condition, warnings = rm.check_extreme_market(
            symbol="AAPL",
            vix=40.0,
        )
        assert condition == "halted"
        assert any("VIX" in w for w in warnings)

    def test_check_extreme_market_normal(self, rm):
        """所有指标正常 → 返回 "normal"，无警告"""
        condition, warnings = rm.check_extreme_market(
            symbol="AAPL",
            current_atr=0.02,
            avg_atr=0.02,
            price_change_pct=-0.5,
            vix=20.0,
            spread_pct=0.001,
        )
        assert condition == "normal"
        assert len(warnings) == 0


# ============ 凯利公式仓位计算 (calc_kelly_quantity) ============

class TestCalcKellyQuantity:
    """凯利公式仓位计算: 历史充足时使用凯利，不足时回退固定比例"""

    @pytest.fixture
    def rm_with_history(self, risk_config, mock_journal):
        """创建有充足交易历史的 RiskManager (>10 笔)"""
        config = RiskConfig(
            total_capital=10000.0,
            max_risk_per_trade_pct=0.02,
            max_position_pct=0.30,
            kelly_enabled=True,
            kelly_fraction=0.25,
            kelly_min_trades=10,
        )
        rm = RiskManager(config=config, journal=mock_journal)
        rm._last_pnl_update = now_et().strftime('%Y-%m-%d')
        rm._last_refresh_ts = now_et()
        return rm

    def _seed_trades(self, rm, wins: int, losses: int, avg_win: float = 20.0, avg_loss: float = -10.0):
        """填充交易历史"""
        for _ in range(wins):
            rm._trade_history.append({"pnl": avg_win, "symbol": "TEST", "time": now_et().isoformat()})
        for _ in range(losses):
            rm._trade_history.append({"pnl": avg_loss, "symbol": "TEST", "time": now_et().isoformat()})

    def test_calc_kelly_quantity_sufficient_history(self, rm_with_history):
        """有 >10 笔交易历史 → 使用凯利公式计算仓位

        8 胜 4 负 (胜率 66.7%), 均盈 $20, 均亏 $10, R=2.0
        Kelly% = 0.667 - 0.333/2.0 = 0.667 - 0.167 = 0.5
        Fractional Kelly (0.25系数): 0.5 * 0.25 = 0.125 = 12.5%
        但上限 max_risk_per_trade_pct * 2 = 0.04 → 实际使用 0.04
        """
        self._seed_trades(rm_with_history, wins=8, losses=4)

        result = rm_with_history.calc_kelly_quantity(
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
        )

        assert "error" not in result
        assert result["shares"] > 0
        assert "kelly_pct" in result
        assert "win_rate" in result
        assert result["total_trades_used"] == 12

    def test_calc_kelly_quantity_insufficient_history(self, rm_with_history):
        """交易历史不足 (<10 笔) → 回退到 calc_safe_quantity

        回退结果不含 kelly_pct 字段，且格式与 calc_safe_quantity 一致。
        """
        # 只填充 5 笔交易 (< kelly_min_trades=10)
        self._seed_trades(rm_with_history, wins=3, losses=2)
        assert len(rm_with_history._trade_history) < 10

        result = rm_with_history.calc_kelly_quantity(
            entry_price=100.0,
            stop_loss=95.0,
        )

        assert "error" not in result
        assert result["shares"] > 0
        # 回退到 calc_safe_quantity 时不含凯利专有字段
        assert "kelly_pct" not in result

    def test_calc_kelly_quantity_negative_expectancy(self, rm_with_history):
        """胜率极低 (< 33%) → 凯利建议不交易，返回 shares=0

        3 胜 12 负 (胜率 20%), 均盈 $10, 均亏 $10, R=1.0
        Kelly% = 0.2 - 0.8/1.0 = 0.2 - 0.8 = -0.6 → max(0, ...) = 0
        """
        self._seed_trades(rm_with_history, wins=3, losses=12, avg_win=10.0, avg_loss=-10.0)

        result = rm_with_history.calc_kelly_quantity(
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
        )

        assert result["shares"] == 0
        assert "recommendation" in result or result.get("kelly_pct", 0) == 0
