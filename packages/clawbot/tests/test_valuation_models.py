"""估值模型单元测试 — 覆盖 DCF / 持有人收益 / EV-EBITDA / 残余收入 / WACC / 综合汇总."""

import pytest
from src.trading.valuation_models import (
    calculate_intrinsic_value_dcf,
    calculate_owner_earnings,
    calculate_ev_ebitda_value,
    calculate_residual_income_value,
    calculate_wacc,
    get_valuation_summary,
)


# ==================== DCF 三场景 ====================

class TestDCF:
    """折现现金流模型（牛/中/熊概率加权）."""

    def test_returns_dict_with_required_keys(self):
        """返回值必须包含牛/中/熊/加权/安全边际."""
        result = calculate_intrinsic_value_dcf(
            free_cash_flow=1_000_000,
            revenue_growth_rate=0.10,
            discount_rate=0.10,
        )
        assert isinstance(result, dict)
        for key in ("bull_value", "base_value", "bear_value",
                     "weighted_value", "margin_of_safety"):
            assert key in result, f"缺少键: {key}"

    def test_bull_greater_than_base_greater_than_bear(self):
        """牛市估值 > 基准 > 熊市."""
        result = calculate_intrinsic_value_dcf(
            free_cash_flow=1_000_000,
            revenue_growth_rate=0.10,
            discount_rate=0.10,
        )
        assert result["bull_value"] > result["base_value"]
        assert result["base_value"] > result["bear_value"]

    def test_weighted_value_between_bull_and_bear(self):
        """加权值必须介于牛市和熊市之间."""
        result = calculate_intrinsic_value_dcf(
            free_cash_flow=1_000_000,
            revenue_growth_rate=0.10,
            discount_rate=0.10,
        )
        assert result["bear_value"] <= result["weighted_value"] <= result["bull_value"]

    def test_zero_growth_still_positive(self):
        """零增长时仍有正值（来自现有现金流）."""
        result = calculate_intrinsic_value_dcf(
            free_cash_flow=500_000,
            revenue_growth_rate=0.0,
            discount_rate=0.10,
        )
        assert result["weighted_value"] > 0

    def test_custom_terminal_growth(self):
        """自定义永续增长率."""
        r1 = calculate_intrinsic_value_dcf(
            free_cash_flow=1_000_000,
            revenue_growth_rate=0.10,
            discount_rate=0.10,
            terminal_growth=0.02,
        )
        r2 = calculate_intrinsic_value_dcf(
            free_cash_flow=1_000_000,
            revenue_growth_rate=0.10,
            discount_rate=0.10,
            terminal_growth=0.04,
        )
        # 更高的永续增长率 → 更高的估值
        assert r2["weighted_value"] > r1["weighted_value"]

    def test_negative_fcf_gives_negative_values(self):
        """负自由现金流时估值为负."""
        result = calculate_intrinsic_value_dcf(
            free_cash_flow=-500_000,
            revenue_growth_rate=0.10,
            discount_rate=0.10,
        )
        assert result["weighted_value"] < 0

    def test_margin_of_safety_reasonable(self):
        """安全边际在 0-1 范围内."""
        result = calculate_intrinsic_value_dcf(
            free_cash_flow=1_000_000,
            revenue_growth_rate=0.10,
            discount_rate=0.10,
        )
        assert 0 <= result["margin_of_safety"] <= 1


# ==================== Owner Earnings ====================

class TestOwnerEarnings:
    """巴菲特持有人收益法."""

    def test_basic_calculation(self):
        """基本计算: 净利润 + 折旧 - 资本支出 - 营运资金变动."""
        result = calculate_owner_earnings(
            net_income=1_000_000,
            depreciation=200_000,
            capex=300_000,
            working_capital_change=50_000,
        )
        # 1_000_000 + 200_000 - 300_000 - 50_000 = 850_000
        assert result == 850_000

    def test_negative_working_capital_change(self):
        """营运资金减少时（释放现金）收益更高."""
        result = calculate_owner_earnings(
            net_income=1_000_000,
            depreciation=200_000,
            capex=300_000,
            working_capital_change=-100_000,
        )
        # 1_000_000 + 200_000 - 300_000 - (-100_000) = 1_000_000
        assert result == 1_000_000

    def test_zero_inputs(self):
        """全部为零时结果为零."""
        result = calculate_owner_earnings(0, 0, 0, 0)
        assert result == 0

    def test_high_capex_can_make_negative(self):
        """资本支出超高时收益为负."""
        result = calculate_owner_earnings(
            net_income=500_000,
            depreciation=100_000,
            capex=1_000_000,
            working_capital_change=0,
        )
        assert result < 0


# ==================== EV/EBITDA ====================

class TestEvEbitda:
    """企业价值倍数隐含估值."""

    def test_returns_required_keys(self):
        """返回值包含当前倍数、隐含价值、上行空间."""
        result = calculate_ev_ebitda_value(
            ebitda=10_000_000,
            enterprise_value=100_000_000,
        )
        assert isinstance(result, dict)
        for key in ("current_multiple", "implied_value", "upside_percent"):
            assert key in result

    def test_current_multiple_calculation(self):
        """当前倍数 = EV / EBITDA."""
        result = calculate_ev_ebitda_value(
            ebitda=10_000_000,
            enterprise_value=120_000_000,
        )
        assert abs(result["current_multiple"] - 12.0) < 0.01

    def test_implied_value_uses_sector_median(self):
        """隐含价值 = EBITDA * 行业中位数倍数."""
        result = calculate_ev_ebitda_value(
            ebitda=10_000_000,
            enterprise_value=100_000_000,
            sector_median_multiple=15.0,
        )
        assert abs(result["implied_value"] - 150_000_000) < 0.01

    def test_upside_percent_positive_when_undervalued(self):
        """低估时上行空间为正."""
        result = calculate_ev_ebitda_value(
            ebitda=10_000_000,
            enterprise_value=80_000_000,
            sector_median_multiple=12.0,
        )
        # 隐含价值 120M vs 当前 80M → 上行 50%
        assert result["upside_percent"] > 0

    def test_upside_percent_negative_when_overvalued(self):
        """高估时上行空间为负."""
        result = calculate_ev_ebitda_value(
            ebitda=10_000_000,
            enterprise_value=200_000_000,
            sector_median_multiple=12.0,
        )
        assert result["upside_percent"] < 0

    def test_default_sector_median_is_12(self):
        """默认行业中位数倍数为 12."""
        result = calculate_ev_ebitda_value(
            ebitda=10_000_000,
            enterprise_value=120_000_000,
        )
        # 隐含价值应等于当前EV，上行为0
        assert abs(result["upside_percent"]) < 0.01


# ==================== 残余收入 ====================

class TestResidualIncome:
    """残余收入模型（ROE vs 权益资本成本）."""

    def test_positive_spread_gives_premium(self):
        """ROE > 资本成本时，估值高于账面."""
        result = calculate_residual_income_value(
            book_value=100,
            roe=0.15,
            cost_of_equity=0.10,
        )
        assert result > 100  # 应大于账面价值

    def test_negative_spread_gives_discount(self):
        """ROE < 资本成本时，估值低于账面."""
        result = calculate_residual_income_value(
            book_value=100,
            roe=0.05,
            cost_of_equity=0.10,
        )
        assert result < 100

    def test_zero_spread_equals_book(self):
        """ROE = 资本成本时，估值等于账面."""
        result = calculate_residual_income_value(
            book_value=100,
            roe=0.10,
            cost_of_equity=0.10,
        )
        assert abs(result - 100) < 0.01

    def test_higher_growth_increases_value(self):
        """更高的增长率 → 更高的估值."""
        v1 = calculate_residual_income_value(
            book_value=100, roe=0.15, cost_of_equity=0.10, growth_rate=0.02,
        )
        v2 = calculate_residual_income_value(
            book_value=100, roe=0.15, cost_of_equity=0.10, growth_rate=0.04,
        )
        assert v2 > v1


# ==================== WACC ====================

class TestWACC:
    """加权平均资本成本."""

    def test_basic_wacc(self):
        """标准 WACC 计算."""
        result = calculate_wacc(
            market_cap=800_000_000,
            total_debt=200_000_000,
            tax_rate=0.25,
            cost_of_equity=0.10,
            cost_of_debt=0.05,
        )
        # 权益权重 0.8，债务权重 0.2
        # WACC = 0.8 * 0.10 + 0.2 * 0.05 * (1-0.25) = 0.08 + 0.0075 = 0.0875
        assert abs(result - 0.0875) < 0.001

    def test_all_equity(self):
        """全部权益（无债务）时等于权益成本."""
        result = calculate_wacc(
            market_cap=1_000_000_000,
            total_debt=0,
            tax_rate=0.25,
            cost_of_equity=0.12,
            cost_of_debt=0.05,
        )
        assert abs(result - 0.12) < 0.001

    def test_tax_shield_reduces_wacc(self):
        """税率越高（税盾效应）→ WACC 越低."""
        w1 = calculate_wacc(
            market_cap=500_000_000, total_debt=500_000_000,
            tax_rate=0.10, cost_of_equity=0.10, cost_of_debt=0.05,
        )
        w2 = calculate_wacc(
            market_cap=500_000_000, total_debt=500_000_000,
            tax_rate=0.40, cost_of_equity=0.10, cost_of_debt=0.05,
        )
        assert w2 < w1


# ==================== 综合估值汇总 ====================

class TestValuationSummary:
    """估值综合汇总（整合 4 大模型）."""

    def test_returns_required_keys(self):
        """返回值包含信号、置信度和各模型结果."""
        result = get_valuation_summary(
            free_cash_flow=5_000_000,
            revenue_growth_rate=0.10,
            discount_rate=0.10,
            net_income=3_000_000,
            depreciation=500_000,
            capex=800_000,
            working_capital_change=100_000,
            ebitda=6_000_000,
            enterprise_value=60_000_000,
            book_value_per_share=50.0,
            roe=0.15,
            cost_of_equity=0.10,
            current_price=55.0,
        )
        assert isinstance(result, dict)
        assert "signal" in result
        assert result["signal"] in ("bullish", "bearish", "neutral")
        assert "confidence" in result
        assert 0 <= result["confidence"] <= 1
        assert "dcf" in result
        assert "owner_earnings" in result
        assert "ev_ebitda" in result
        assert "residual_income" in result

    def test_undervalued_stock_gives_bullish(self):
        """明显低估的股票应给出看涨信号."""
        result = get_valuation_summary(
            free_cash_flow=10_000_000,
            revenue_growth_rate=0.15,
            discount_rate=0.08,
            net_income=8_000_000,
            depreciation=1_000_000,
            capex=500_000,
            working_capital_change=0,
            ebitda=12_000_000,
            enterprise_value=60_000_000,
            book_value_per_share=100.0,
            roe=0.20,
            cost_of_equity=0.08,
            current_price=50.0,  # 远低于估值
        )
        assert result["signal"] == "bullish"

    def test_overvalued_stock_gives_bearish(self):
        """明显高估的股票应给出看跌信号."""
        result = get_valuation_summary(
            free_cash_flow=1_000_000,
            revenue_growth_rate=0.02,
            discount_rate=0.12,
            net_income=500_000,
            depreciation=100_000,
            capex=800_000,
            working_capital_change=200_000,
            ebitda=2_000_000,
            enterprise_value=200_000_000,
            book_value_per_share=10.0,
            roe=0.05,
            cost_of_equity=0.12,
            current_price=500.0,  # 远高于估值
        )
        assert result["signal"] == "bearish"
