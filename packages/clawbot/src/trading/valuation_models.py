"""投资估值模型 — 搬运自 ai-hedge-fund (56K★)

4 种估值模型用于判断股票是否被低估/高估:
1. DCF 三场景（牛/中/熊概率加权折现现金流）
2. Owner Earnings（巴菲特持有人收益法）
3. EV/EBITDA（企业价值倍数隐含估值）
4. 残余收入模型（ROE vs 资本成本差异估值）

使用方式:
    from src.trading.valuation_models import get_valuation_summary
    summary = get_valuation_summary(...)
"""

from __future__ import annotations


def calculate_intrinsic_value_dcf(
    free_cash_flow: float,
    revenue_growth_rate: float,
    discount_rate: float,
    terminal_growth: float = 0.03,
) -> dict[str, float]:
    """DCF 三场景折现现金流估值（牛/中/熊概率加权）.

    参数:
        free_cash_flow: 当前自由现金流
        revenue_growth_rate: 预期收入增长率
        discount_rate: 折现率（WACC）
        terminal_growth: 永续增长率，默认 3%

    返回:
        包含 bull_value / base_value / bear_value / weighted_value / margin_of_safety 的字典
    """
    # 三种情景的增长倍数
    scenarios = {
        "bull": 1.2,   # 牛市：增长率 × 1.2
        "base": 1.0,   # 基准：增长率 × 1.0
        "bear": 0.8,   # 熊市：增长率 × 0.8
    }
    # 概率权重
    weights = {"bull": 0.25, "base": 0.50, "bear": 0.25}
    projection_years = 5

    values: dict[str, float] = {}

    for scenario, multiplier in scenarios.items():
        # 该场景的增长率
        growth = revenue_growth_rate * multiplier
        # 5 年现金流折现
        total_pv = 0.0
        projected_fcf = free_cash_flow
        for year in range(1, projection_years + 1):
            projected_fcf = projected_fcf * (1 + growth)
            pv = projected_fcf / ((1 + discount_rate) ** year)
            total_pv += pv
        # 终值：使用 Gordon 增长模型
        terminal_value = projected_fcf * (1 + terminal_growth) / (discount_rate - terminal_growth)
        terminal_pv = terminal_value / ((1 + discount_rate) ** projection_years)
        values[f"{scenario}_value"] = total_pv + terminal_pv

    # 概率加权平均
    weighted = sum(
        values[f"{s}_value"] * w for s, w in weights.items()
    )
    values["weighted_value"] = weighted

    # 安全边际：熊市估值占加权估值的比例（越高越安全）
    # 定义为 1 - (熊市/加权)，范围 [0, 1]
    if weighted != 0:
        ratio = values["bear_value"] / weighted
        margin = max(0.0, min(1.0, 1.0 - ratio))
    else:
        margin = 0.0
    values["margin_of_safety"] = margin

    return values


def calculate_owner_earnings(
    net_income: float,
    depreciation: float,
    capex: float,
    working_capital_change: float,
) -> float:
    """巴菲特持有人收益法.

    公式: 净利润 + 折旧 - 资本支出 - 营运资金变动

    参数:
        net_income: 净利润
        depreciation: 折旧与摊销
        capex: 资本支出
        working_capital_change: 营运资金变动（增加为正）

    返回:
        持有人收益值
    """
    return net_income + depreciation - capex - working_capital_change


def calculate_ev_ebitda_value(
    ebitda: float,
    enterprise_value: float,
    sector_median_multiple: float = 12.0,
) -> dict[str, float]:
    """企业价值倍数隐含估值.

    参数:
        ebitda: 息税折旧摊销前利润
        enterprise_value: 当前企业价值
        sector_median_multiple: 行业中位数 EV/EBITDA 倍数，默认 12

    返回:
        包含 current_multiple / implied_value / upside_percent 的字典
    """
    # 当前倍数
    current_multiple = enterprise_value / ebitda if ebitda != 0 else float("inf")
    # 隐含价值 = EBITDA × 行业中位数倍数
    implied_value = ebitda * sector_median_multiple
    # 上行/下行空间百分比
    if enterprise_value != 0:
        upside_percent = (implied_value - enterprise_value) / enterprise_value * 100
    else:
        upside_percent = 0.0

    return {
        "current_multiple": current_multiple,
        "implied_value": implied_value,
        "upside_percent": upside_percent,
    }


def calculate_residual_income_value(
    book_value: float,
    roe: float,
    cost_of_equity: float,
    growth_rate: float = 0.03,
) -> float:
    """残余收入模型（ROE vs 权益资本成本差异估值）.

    残余收入 = 账面价值 × (ROE - 权益成本)
    内在价值 = 账面价值 + 残余收入的永续折现值

    参数:
        book_value: 每股账面价值
        roe: 净资产收益率
        cost_of_equity: 权益资本成本
        growth_rate: 残余收入的永续增长率，默认 3%

    返回:
        估计的内在价值
    """
    # 残余收入 = 账面价值 × (ROE - 资本成本)
    residual_income = book_value * (roe - cost_of_equity)
    # 永续增长折现：RI / (资本成本 - 增长率)
    denominator = cost_of_equity - growth_rate
    if denominator <= 0:
        # 增长率 >= 资本成本时模型不适用，返回账面价值
        return book_value
    terminal_value = residual_income / denominator
    return book_value + terminal_value


def calculate_wacc(
    market_cap: float,
    total_debt: float,
    tax_rate: float,
    cost_of_equity: float,
    cost_of_debt: float,
) -> float:
    """加权平均资本成本 (WACC).

    公式: WACC = (E/V) × Re + (D/V) × Rd × (1 - T)

    参数:
        market_cap: 市值（权益价值）
        total_debt: 总债务
        tax_rate: 企业税率
        cost_of_equity: 权益成本 Re
        cost_of_debt: 债务成本 Rd

    返回:
        WACC 百分比（如 0.10 表示 10%）
    """
    total_value = market_cap + total_debt
    if total_value == 0:
        return 0.0
    equity_weight = market_cap / total_value
    debt_weight = total_debt / total_value
    return equity_weight * cost_of_equity + debt_weight * cost_of_debt * (1 - tax_rate)


def get_valuation_summary(
    *,
    free_cash_flow: float,
    revenue_growth_rate: float,
    discount_rate: float,
    net_income: float,
    depreciation: float,
    capex: float,
    working_capital_change: float,
    ebitda: float,
    enterprise_value: float,
    book_value_per_share: float,
    roe: float,
    cost_of_equity: float,
    current_price: float,
    terminal_growth: float = 0.03,
    sector_median_multiple: float = 12.0,
) -> dict:
    """运行全部 4 大估值模型并返回综合信号.

    参数:
        所有子模型需要的输入参数
        current_price: 当前股价，用于判断低估/高估

    返回:
        包含 signal (bullish/bearish/neutral)、confidence、各模型结果的字典
    """
    # 1. DCF
    dcf = calculate_intrinsic_value_dcf(
        free_cash_flow=free_cash_flow,
        revenue_growth_rate=revenue_growth_rate,
        discount_rate=discount_rate,
        terminal_growth=terminal_growth,
    )
    # 2. 持有人收益
    owner_earnings = calculate_owner_earnings(
        net_income=net_income,
        depreciation=depreciation,
        capex=capex,
        working_capital_change=working_capital_change,
    )
    # 3. EV/EBITDA
    ev_ebitda = calculate_ev_ebitda_value(
        ebitda=ebitda,
        enterprise_value=enterprise_value,
        sector_median_multiple=sector_median_multiple,
    )
    # 4. 残余收入
    residual_income = calculate_residual_income_value(
        book_value=book_value_per_share,
        roe=roe,
        cost_of_equity=cost_of_equity,
    )

    # ---- 信号聚合 ----
    # 收集各模型的方向信号（+1 看涨, -1 看跌, 0 中性）
    signals: list[int] = []

    # DCF: 加权估值 vs 当前价格（按每股估算简化处理）
    if dcf["weighted_value"] > 0 and current_price > 0:
        dcf_ratio = dcf["weighted_value"] / current_price
        # 估值比当前价格高 20% 以上 → 看涨
        if dcf_ratio > 1.2:
            signals.append(1)
        elif dcf_ratio < 0.8:
            signals.append(-1)
        else:
            signals.append(0)
    else:
        signals.append(0)

    # 持有人收益: 正值看涨，负值看跌
    if owner_earnings > 0:
        signals.append(1)
    elif owner_earnings < 0:
        signals.append(-1)
    else:
        signals.append(0)

    # EV/EBITDA: 上行空间
    if ev_ebitda["upside_percent"] > 20:
        signals.append(1)
    elif ev_ebitda["upside_percent"] < -20:
        signals.append(-1)
    else:
        signals.append(0)

    # 残余收入: 估值 vs 当前价格
    if current_price > 0:
        ri_ratio = residual_income / current_price
        if ri_ratio > 1.2:
            signals.append(1)
        elif ri_ratio < 0.8:
            signals.append(-1)
        else:
            signals.append(0)
    else:
        signals.append(0)

    # 加总信号
    total_signal = sum(signals)
    # 至少 2 个模型同向 → 给出方向性信号
    if total_signal >= 2:
        signal = "bullish"
    elif total_signal <= -2:
        signal = "bearish"
    else:
        signal = "neutral"

    # 置信度 = 同向信号比例
    if signals:
        agreement = sum(1 for s in signals if s == (1 if total_signal > 0 else -1 if total_signal < 0 else 0))
        confidence = agreement / len(signals)
    else:
        confidence = 0.0

    return {
        "signal": signal,
        "confidence": confidence,
        "dcf": dcf,
        "owner_earnings": owner_earnings,
        "ev_ebitda": ev_ebitda,
        "residual_income": residual_income,
    }
