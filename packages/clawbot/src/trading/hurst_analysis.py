"""Hurst 指数分析 — 搬运自 ai-hedge-fund technicals agent

Hurst 指数判断时间序列是趋势/均值回归/随机:
- H > 0.5: 趋势性（应追趋势）
- H = 0.5: 随机游走
- H < 0.5: 均值回归（应逆势交易）

使用方式:
    from src.trading.hurst_analysis import calculate_hurst_exponent, classify_regime
    h = calculate_hurst_exponent(prices)
    regime = classify_regime(h)
"""

from __future__ import annotations

import math
import statistics


def calculate_hurst_exponent(prices: list[float]) -> float:
    """使用 R/S (重标极差) 分析法计算 Hurst 指数.

    参数:
        prices: 价格序列，至少需要 20 个数据点

    返回:
        Hurst 指数 (0-1 之间的浮点数)

    抛出:
        ValueError: 数据点不足时
    """
    n = len(prices)
    if n < 20:
        raise ValueError(f"至少需要 20 个数据点，当前只有 {n} 个")

    # 计算对数收益率
    returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, n) if prices[i - 1] > 0 and prices[i] > 0]
    if len(returns) < 19:
        raise ValueError("有效数据点不足，可能存在零值或负值")

    total_returns = len(returns)

    # 不同子区间长度
    # 选择 2 的幂次方附近的分组大小
    min_size = 10
    max_size = total_returns // 2
    if max_size < min_size:
        min_size = max_size

    sizes: list[int] = []
    s = min_size
    while s <= max_size:
        sizes.append(s)
        s = int(s * 1.5)
        if s == sizes[-1]:
            s += 1

    if not sizes:
        sizes = [min_size]

    log_sizes: list[float] = []
    log_rs: list[float] = []

    for size in sizes:
        # 将收益率序列分成大小为 size 的子区间
        num_segments = total_returns // size
        if num_segments == 0:
            continue

        rs_values: list[float] = []
        for seg in range(num_segments):
            start = seg * size
            end = start + size
            segment = returns[start:end]

            # 均值
            mean_val = sum(segment) / len(segment)

            # 累积偏差序列
            cumulative_dev = []
            cumsum = 0.0
            for r in segment:
                cumsum += (r - mean_val)
                cumulative_dev.append(cumsum)

            # 极差 R
            r_range = max(cumulative_dev) - min(cumulative_dev)

            # 标准差 S
            if len(segment) > 1:
                s_std = statistics.stdev(segment)
            else:
                s_std = 0.0

            # R/S 值
            if s_std > 0:
                rs_values.append(r_range / s_std)

        if rs_values:
            mean_rs = sum(rs_values) / len(rs_values)
            if mean_rs > 0:
                log_sizes.append(math.log(size))
                log_rs.append(math.log(mean_rs))

    if len(log_sizes) < 2:
        # 数据不足以拟合，返回 0.5（随机游走）
        return 0.5

    # 线性回归: log(R/S) = H * log(n) + c
    # 斜率即为 Hurst 指数
    n_points = len(log_sizes)
    sum_x = sum(log_sizes)
    sum_y = sum(log_rs)
    sum_xy = sum(x * y for x, y in zip(log_sizes, log_rs))
    sum_x2 = sum(x * x for x in log_sizes)

    denominator = n_points * sum_x2 - sum_x ** 2
    if denominator == 0:
        return 0.5

    hurst = (n_points * sum_xy - sum_x * sum_y) / denominator

    # 限制在 [0, 1] 范围内
    return max(0.0, min(1.0, hurst))


def classify_regime(hurst: float) -> str:
    """根据 Hurst 指数分类市场机制.

    参数:
        hurst: Hurst 指数值

    返回:
        "trending" (趋势性, H > 0.55)
        "mean_reverting" (均值回归, H < 0.45)
        "random" (随机游走, 0.45 <= H <= 0.55)
    """
    if hurst > 0.55:
        return "trending"
    elif hurst < 0.45:
        return "mean_reverting"
    else:
        return "random"


def calculate_stat_arb_signals(
    prices: list[float],
    lookback: int = 60,
) -> dict[str, float | str]:
    """基于 z-score 的统计套利信号.

    使用回看窗口内的均值和标准差计算当前价格的 z-score，
    当价格偏离均值超过阈值时发出交易信号。

    参数:
        prices: 价格序列
        lookback: 回看窗口大小，默认 60

    返回:
        包含 z_score / signal (buy/sell/hold) / mean / std 的字典
    """
    if len(prices) < 2:
        return {"z_score": 0.0, "signal": "hold", "mean": prices[0] if prices else 0.0, "std": 0.0}

    # 回看窗口：取最后 lookback 个数据（如果不够就用全部）
    window = prices[-min(lookback, len(prices)):]

    mean_val = sum(window) / len(window)

    # 标准差
    if len(window) > 1:
        variance = sum((x - mean_val) ** 2 for x in window) / (len(window) - 1)
        std_val = math.sqrt(variance)
    else:
        std_val = 0.0

    # 当前价格的 z-score
    current_price = prices[-1]
    if std_val > 0:
        z_score = (current_price - mean_val) / std_val
    else:
        z_score = 0.0

    # 信号判断：z-score 超过 ±2 时发出信号
    if z_score < -2.0:
        signal = "buy"     # 价格远低于均值 → 买入（均值回归）
    elif z_score > 2.0:
        signal = "sell"    # 价格远高于均值 → 卖出
    else:
        signal = "hold"    # 正常范围内 → 持有

    return {
        "z_score": z_score,
        "signal": signal,
        "mean": mean_val,
        "std": std_val,
    }
