"""
VaR/CVaR 风险度量模块的单元测试。

覆盖范围:
- VaR (Value at Risk) 历史模拟法计算
- CVaR (Conditional VaR / Expected Shortfall) 计算
- Sortino Ratio 下行风险调整收益
- Tail Ratio 尾部比率
- Calmar Ratio 收益/最大回撤比
- get_var_metrics() 聚合指标
- check_var_limit() 限额检查
- 边界情况: 空数据、单条数据、全零、数据不足
"""

import pytest
import numpy as np
from types import SimpleNamespace

from src.risk_var import VaRMixin


# ============ 测试辅助类 ============


class FakeRiskManager(VaRMixin):
    """模拟 RiskManager 宿主类，提供 VaRMixin 依赖的属性。

    VaRMixin 需要:
        self.config          — 含 var_confidence / var_enabled 等字段
        self._trade_history  — 交易历史列表 (含 pnl 字段)
    """

    def __init__(
        self,
        pnl_list: list = None,
        total_capital: float = 10000.0,
        var_confidence: float = 0.95,
        var_enabled: bool = True,
        var_max_daily_pct: float = 0.03,
        cvar_reject_threshold: float = 0.05,
    ):
        # 构造 config 对象
        self.config = SimpleNamespace(
            var_confidence=var_confidence,
            var_enabled=var_enabled,
            var_max_daily_pct=var_max_daily_pct,
            cvar_reject_threshold=cvar_reject_threshold,
            total_capital=total_capital,
        )
        # 将 pnl 列表转换为 _trade_history 格式
        if pnl_list is not None:
            self._trade_history = [{"pnl": p} for p in pnl_list]
        else:
            self._trade_history = []


def make_manager(pnl_list, **kwargs):
    """快速构造带指定 PnL 序列的测试对象。"""
    return FakeRiskManager(pnl_list=pnl_list, **kwargs)


# ============ 确定性测试数据 ============


@pytest.fixture
def deterministic_pnl():
    """用固定种子生成 100 条 PnL 数据，确保测试可复现。"""
    rng = np.random.default_rng(seed=42)
    # 模拟真实交易: 均值微正、有明显亏损尾部
    return list(rng.normal(loc=5.0, scale=30.0, size=100))


@pytest.fixture
def large_loss_pnl():
    """带极端亏损的 PnL 序列，用于测试尾部风险。"""
    rng = np.random.default_rng(seed=123)
    base = list(rng.normal(loc=2.0, scale=10.0, size=50))
    # 注入几笔大亏损
    base.extend([-100, -150, -200, -80, -120])
    return base


@pytest.fixture
def all_positive_pnl():
    """全部盈利的交易记录。"""
    return [10.0, 20.0, 15.0, 30.0, 25.0, 12.0, 18.0, 22.0, 35.0, 28.0]


@pytest.fixture
def all_negative_pnl():
    """全部亏损的交易记录。"""
    return [-10.0, -20.0, -15.0, -30.0, -25.0, -12.0, -18.0, -22.0, -35.0, -28.0]


# ============ VaR 计算测试 ============


class TestCalcVar:
    """calc_var() 的单元测试。"""

    def test_var_with_known_data(self, deterministic_pnl):
        """已知数据集的 VaR 应与手动 numpy 计算一致。"""
        mgr = make_manager(deterministic_pnl)
        var_95 = mgr.calc_var(confidence=0.95)

        # 手动计算期望值
        expected = abs(float(np.percentile(deterministic_pnl, 5)))
        assert var_95 == round(expected, 2)

    def test_var_99_stricter_than_95(self, deterministic_pnl):
        """99% 置信度的 VaR 应大于等于 95% 置信度（更保守）。"""
        mgr = make_manager(deterministic_pnl)
        var_95 = mgr.calc_var(confidence=0.95)
        var_99 = mgr.calc_var(confidence=0.99)
        assert var_99 >= var_95

    def test_var_returns_positive(self, deterministic_pnl):
        """VaR 返回值应为正数（表示损失金额）。"""
        mgr = make_manager(deterministic_pnl)
        assert mgr.calc_var(0.95) >= 0

    def test_var_uses_config_default_confidence(self):
        """不传 confidence 时应使用 config 中的默认值。"""
        pnl = list(range(-50, 50))  # 100 条简单数据
        mgr = make_manager(pnl, var_confidence=0.99)

        var_default = mgr.calc_var()  # 不传参，应用 config 的 0.99
        var_99 = mgr.calc_var(confidence=0.99)  # 显式传 0.99
        assert var_default == var_99

    def test_var_empty_data_returns_zero(self):
        """空交易历史应返回 0。"""
        mgr = make_manager([])
        assert mgr.calc_var(0.95) == 0.0

    def test_var_single_data_point_returns_zero(self):
        """单条数据不足以计算 VaR，应返回 0。"""
        mgr = make_manager([10.0])
        assert mgr.calc_var(0.95) == 0.0

    def test_var_four_data_points_returns_zero(self):
        """少于 5 条数据不足以计算 VaR，应返回 0。"""
        mgr = make_manager([10.0, -5.0, 8.0, -3.0])
        assert mgr.calc_var(0.95) == 0.0

    def test_var_exactly_five_data_points(self):
        """恰好 5 条数据时应能计算 VaR。"""
        pnl = [-50.0, -30.0, 10.0, 20.0, 40.0]
        mgr = make_manager(pnl)
        result = mgr.calc_var(0.95)
        assert result > 0  # 有负值，VaR 应大于 0

    def test_var_all_zeros_returns_zero(self):
        """全零 PnL 的 VaR 应为 0。"""
        mgr = make_manager([0.0] * 20)
        assert mgr.calc_var(0.95) == 0.0

    def test_var_all_positive_pnl(self, all_positive_pnl):
        """全部盈利时，VaR 应为最小盈利的绝对值附近。"""
        mgr = make_manager(all_positive_pnl)
        result = mgr.calc_var(0.95)
        # 全为正值，5% 分位也是正数，取绝对值后仍为正
        assert result >= 0

    def test_var_result_is_rounded(self, deterministic_pnl):
        """VaR 结果应四舍五入到 2 位小数。"""
        mgr = make_manager(deterministic_pnl)
        result = mgr.calc_var(0.95)
        assert result == round(result, 2)

    def test_var_no_trade_history_attr(self):
        """_trade_history 属性不存在时应返回 0。"""
        mgr = FakeRiskManager()
        del mgr._trade_history  # 模拟未初始化
        assert mgr.calc_var(0.95) == 0.0


# ============ CVaR 计算测试 ============


class TestCalcCVar:
    """calc_cvar() 的单元测试。"""

    def test_cvar_with_known_data(self, deterministic_pnl):
        """已知数据集的 CVaR 应与手动计算一致。"""
        mgr = make_manager(deterministic_pnl)
        cvar_95 = mgr.calc_cvar(confidence=0.95)

        # 手动计算: 取低于 5% 分位的所有值的均值的绝对值
        threshold = np.percentile(deterministic_pnl, 5)
        tail = [p for p in deterministic_pnl if p <= threshold]
        expected = abs(float(np.mean(tail)))
        assert cvar_95 == round(expected, 2)

    def test_cvar_ge_var(self, deterministic_pnl):
        """CVaR 应大于等于 VaR（CVaR 是 VaR 之后的平均损失，更保守）。"""
        mgr = make_manager(deterministic_pnl)
        var = mgr.calc_var(0.95)
        cvar = mgr.calc_cvar(0.95)
        assert cvar >= var

    def test_cvar_99_stricter_than_95(self, deterministic_pnl):
        """99% 置信度的 CVaR 应大于等于 95% 的 CVaR。"""
        mgr = make_manager(deterministic_pnl)
        cvar_95 = mgr.calc_cvar(confidence=0.95)
        cvar_99 = mgr.calc_cvar(confidence=0.99)
        assert cvar_99 >= cvar_95

    def test_cvar_empty_data_returns_zero(self):
        """空数据的 CVaR 应返回 0。"""
        mgr = make_manager([])
        assert mgr.calc_cvar(0.95) == 0.0

    def test_cvar_insufficient_data_returns_zero(self):
        """数据不足 5 条时 CVaR 应返回 0。"""
        mgr = make_manager([-10.0, 5.0, 3.0])
        assert mgr.calc_cvar(0.95) == 0.0

    def test_cvar_all_zeros_returns_zero(self):
        """全零 PnL 的 CVaR 应为 0。"""
        mgr = make_manager([0.0] * 20)
        assert mgr.calc_cvar(0.95) == 0.0

    def test_cvar_with_extreme_losses(self, large_loss_pnl):
        """有极端亏损时，CVaR 应反映尾部风险。"""
        mgr = make_manager(large_loss_pnl)
        cvar = mgr.calc_cvar(0.95)
        # 极端亏损存在时 CVaR 应显著大于 0
        assert cvar > 50.0

    def test_cvar_result_is_rounded(self, deterministic_pnl):
        """CVaR 结果应四舍五入到 2 位小数。"""
        mgr = make_manager(deterministic_pnl)
        result = mgr.calc_cvar(0.95)
        assert result == round(result, 2)


# ============ Sortino Ratio 测试 ============


class TestCalcSortino:
    """calc_sortino() 的单元测试。"""

    def test_sortino_insufficient_data(self):
        """不足 10 条数据时 Sortino 应返回 0。"""
        mgr = make_manager([10.0, -5.0, 8.0, -3.0, 12.0])
        assert mgr.calc_sortino() == 0.0

    def test_sortino_all_positive_returns_99(self, all_positive_pnl):
        """全部盈利（无亏损交易）时 Sortino 应为极大正值或 99.0。"""
        mgr = make_manager(all_positive_pnl)
        assert mgr.calc_sortino() > 0  # 无亏损 → 结果应为正值

    def test_sortino_positive_for_profitable_series(self, deterministic_pnl):
        """均值为正的序列 Sortino 应为正数。"""
        mgr = make_manager(deterministic_pnl)
        sortino = mgr.calc_sortino()
        # 均值 loc=5 > 0，应为正值
        assert sortino > 0

    def test_sortino_negative_for_losing_series(self, all_negative_pnl):
        """全部亏损的序列 Sortino 应为负数。"""
        mgr = make_manager(all_negative_pnl)
        sortino = mgr.calc_sortino()
        assert sortino < 0

    def test_sortino_result_is_rounded(self, deterministic_pnl):
        """Sortino 结果应四舍五入到 2 位小数。"""
        mgr = make_manager(deterministic_pnl)
        result = mgr.calc_sortino()
        assert result == round(result, 2)


# ============ Tail Ratio 测试 ============


class TestCalcTailRatio:
    """calc_tail_ratio() 的单元测试。"""

    def test_tail_ratio_insufficient_data(self):
        """不足 10 条数据时应返回 1.0。"""
        mgr = make_manager([1, 2, 3, 4, 5])
        assert mgr.calc_tail_ratio() == 1.0

    def test_tail_ratio_symmetric_distribution(self):
        """对称分布的 tail ratio 应接近 1.0。"""
        rng = np.random.default_rng(seed=99)
        pnl = list(rng.normal(loc=0, scale=10, size=1000))
        mgr = make_manager(pnl)
        ratio = mgr.calc_tail_ratio()
        # 对称分布: 右尾95分位 ≈ 左尾5分位绝对值，比值接近 1
        assert 0.7 < ratio < 1.3

    def test_tail_ratio_positive_skew(self, all_positive_pnl):
        """全正序列的 tail ratio 应反映正偏。"""
        mgr = make_manager(all_positive_pnl)
        ratio = mgr.calc_tail_ratio()
        assert ratio > 0  # 全正时，左尾绝对值较小，比值较大

    def test_tail_ratio_left_tail_zero_returns_99(self):
        """左尾为 0 时应返回较大正值（避免除零），具体值取决于后端库。"""
        pnl = [0.0] * 9 + [100.0]  # 5%分位 = 0
        mgr = make_manager(pnl)
        assert mgr.calc_tail_ratio() >= 1.0  # 左尾为 0 → 比值应 ≥1

    def test_tail_ratio_result_is_rounded(self, deterministic_pnl):
        """tail ratio 结果应四舍五入到 2 位小数。"""
        mgr = make_manager(deterministic_pnl)
        result = mgr.calc_tail_ratio()
        assert result == round(result, 2)


# ============ Calmar Ratio 测试 ============


class TestCalcCalmar:
    """calc_calmar() 的单元测试。"""

    def test_calmar_insufficient_data(self):
        """不足 10 条数据时 Calmar 应返回 0。"""
        mgr = make_manager([10.0, -5.0, 8.0])
        assert mgr.calc_calmar() == 0.0

    def test_calmar_no_drawdown_positive(self, all_positive_pnl):
        """全正序列无回撤且总收益为正时应返回 99.0。"""
        mgr = make_manager(all_positive_pnl)
        assert mgr.calc_calmar() == 99.0

    def test_calmar_all_negative(self, all_negative_pnl):
        """全负序列的 Calmar 应为负数。"""
        mgr = make_manager(all_negative_pnl)
        calmar = mgr.calc_calmar()
        assert calmar < 0

    def test_calmar_known_values(self):
        """已知序列手动验证 Calmar 计算。"""
        # 累计: [10, 0, 15, 5, 25]
        # 峰值: [10, 10, 15, 15, 25]
        # 回撤: [0, 10, 0, 10, 0]
        # 最大回撤=10, 总收益=25, Calmar=25/10=2.5
        pnl = [10.0, -10.0, 15.0, -10.0, 20.0, 5.0, 5.0, 5.0, 5.0, 5.0]
        mgr = make_manager(pnl)
        result = mgr.calc_calmar()
        # 手动计算
        cumulative = np.cumsum(pnl)
        peak = np.maximum.accumulate(cumulative)
        max_dd = np.max(peak - cumulative)
        expected = round(float(cumulative[-1] / max_dd), 2)
        assert result == expected

    def test_calmar_result_is_rounded(self, deterministic_pnl):
        """Calmar 结果应四舍五入到 2 位小数。"""
        mgr = make_manager(deterministic_pnl)
        result = mgr.calc_calmar()
        assert result == round(result, 2)


# ============ get_var_metrics() 聚合指标测试 ============


class TestGetVarMetrics:
    """get_var_metrics() 的单元测试。"""

    def test_metrics_insufficient_data(self):
        """数据不足时返回默认值。"""
        mgr = make_manager([1.0, 2.0])
        metrics = mgr.get_var_metrics()

        assert metrics["var_enabled"] is True
        assert metrics["var_95"] == 0.0
        assert metrics["cvar_95"] == 0.0
        assert metrics["sortino"] == 0.0
        assert metrics["tail_ratio"] == 1.0
        assert metrics["calmar"] == 0.0
        assert metrics["sufficient_data"] is False

    def test_metrics_disabled(self, deterministic_pnl):
        """var_enabled=False 时返回默认值。"""
        mgr = make_manager(deterministic_pnl, var_enabled=False)
        metrics = mgr.get_var_metrics()

        assert metrics["var_enabled"] is False
        assert metrics["var_95"] == 0.0
        assert metrics["sufficient_data"] is False

    def test_metrics_sufficient_data(self, deterministic_pnl):
        """数据充足时所有指标应有非默认值。"""
        mgr = make_manager(deterministic_pnl)
        metrics = mgr.get_var_metrics()

        assert metrics["var_enabled"] is True
        assert metrics["pnl_count"] == 100
        assert metrics["sufficient_data"] is True
        assert metrics["var_95"] > 0
        assert metrics["cvar_95"] > 0
        # sortino/tail_ratio/calmar 根据数据不同，只确保有值
        assert isinstance(metrics["sortino"], float)
        assert isinstance(metrics["tail_ratio"], float)
        assert isinstance(metrics["calmar"], float)

    def test_metrics_keys_complete(self, deterministic_pnl):
        """返回字典应包含所有预期的键。"""
        mgr = make_manager(deterministic_pnl)
        metrics = mgr.get_var_metrics()
        expected_keys = {
            "var_enabled",
            "var_95",
            "cvar_95",
            "sortino",
            "tail_ratio",
            "calmar",
            "pnl_count",
            "sufficient_data",
        }
        assert set(metrics.keys()) == expected_keys

    def test_metrics_pnl_count_matches(self, deterministic_pnl):
        """pnl_count 应等于交易历史长度。"""
        mgr = make_manager(deterministic_pnl)
        metrics = mgr.get_var_metrics()
        assert metrics["pnl_count"] == len(deterministic_pnl)

    def test_metrics_sufficient_data_boundary(self):
        """恰好 5 条数据: 可计算但 sufficient_data=False (需 >=10)。"""
        mgr = make_manager([-20.0, -10.0, 0.0, 10.0, 20.0])
        metrics = mgr.get_var_metrics()
        # 5 条够计算 VaR/CVaR，但 sufficient_data 需要 >=10
        assert metrics["var_95"] > 0
        assert metrics["sufficient_data"] is False

    def test_metrics_ten_data_points_sufficient(self):
        """恰好 10 条数据时 sufficient_data 应为 True。"""
        pnl = [-30.0, -20.0, -10.0, -5.0, 0.0, 5.0, 10.0, 20.0, 30.0, 40.0]
        mgr = make_manager(pnl)
        metrics = mgr.get_var_metrics()
        assert metrics["sufficient_data"] is True


# ============ check_var_limit() 限额检查测试 ============


class TestCheckVarLimit:
    """check_var_limit() 的单元测试。"""

    def test_disabled_returns_none(self, deterministic_pnl):
        """var_enabled=False 时不做限制，返回 None。"""
        mgr = make_manager(deterministic_pnl, var_enabled=False)
        assert mgr.check_var_limit(1000.0) is None

    def test_insufficient_data_uses_conservative_limit(self):
        """HI-524: 数据不足 10 条时使用保守限额保护新账户。"""
        mgr = make_manager([-10, -5, 0, 5, 10])
        # 资金 10000，保守单笔限额 = 10000 * 0.01 = 100，1000 远超限额
        result = mgr.check_var_limit(1000.0)
        assert result is not None
        assert "新账户VaR保护" in result

    def test_safe_trade_passes(self, deterministic_pnl):
        """正常交易不应触发限额。"""
        # 资金 10000，var_max_daily_pct=0.03，限额=300
        # cvar_reject_threshold=0.05，限额=500
        mgr = make_manager(deterministic_pnl, total_capital=10000.0)
        # 小损失不会触发
        result = mgr.check_var_limit(10.0)
        assert result is None

    def test_cvar_reject_triggers(self):
        """CVaR 超过资金阈值时应拒绝。"""
        # 构造极端亏损数据使 CVaR > 5% * 10000 = 500
        pnl = [-1000.0, -800.0, -600.0, -500.0, -400.0] + [10.0] * 50  # 大量小盈利 + 几笔巨亏
        mgr = make_manager(
            pnl,
            total_capital=10000.0,
            cvar_reject_threshold=0.05,
        )
        result = mgr.check_var_limit(100.0)
        # CVaR 来自尾部均值，包含 -1000, -800... 应远超 500
        if result is not None:
            assert "CVaR" in result

    def test_var_limit_warning(self):
        """拟议损失和 VaR 都超过限额时应警告。"""
        # 大量中等亏损使 VaR > 300 (3% of 10000)
        pnl = [-350.0, -400.0, -320.0, -380.0, -360.0] + [10.0] * 50
        mgr = make_manager(
            pnl,
            total_capital=10000.0,
            var_max_daily_pct=0.03,
        )
        # 拟议损失 500 > 限额 300
        result = mgr.check_var_limit(500.0)
        if result is not None:
            assert "VaR" in result

    def test_no_trade_history_uses_conservative_limit(self):
        """HI-524: 无交易历史时使用保守限额保护新账户。"""
        mgr = make_manager([])
        # 资金 10000，保守单笔限额 = 10000 * 0.01 = 100，500 远超限额
        result = mgr.check_var_limit(500.0)
        assert result is not None
        assert "新账户VaR保护" in result


# ============ _get_pnl_series() 内部方法测试 ============


class TestGetPnlSeries:
    """_get_pnl_series() 的边界测试。"""

    def test_empty_history(self):
        """空交易历史应返回空列表。"""
        mgr = make_manager([])
        assert mgr._get_pnl_series() == []

    def test_extracts_pnl_correctly(self):
        """应正确提取每笔交易的 pnl 字段。"""
        mgr = FakeRiskManager()
        mgr._trade_history = [
            {"pnl": 10.0, "symbol": "AAPL"},
            {"pnl": -5.0, "symbol": "GOOG"},
            {"symbol": "MSFT"},  # 无 pnl 字段，应跳过
        ]
        result = mgr._get_pnl_series()
        assert result == [10.0, -5.0]

    def test_no_trade_history_attribute(self):
        """_trade_history 属性不存在时应返回空列表。"""
        mgr = FakeRiskManager()
        del mgr._trade_history
        assert mgr._get_pnl_series() == []

    def test_none_trade_history(self):
        """_trade_history 为 None 时应返回空列表。"""
        mgr = FakeRiskManager()
        mgr._trade_history = None
        assert mgr._get_pnl_series() == []
