"""
VaR/CVaR 风险度量 Mixin

基于 QuantStats 的专业风险指标，集成到风控引擎：
- VaR (Value at Risk): 在给定置信度下的最大预期损失
- CVaR (Conditional VaR / Expected Shortfall): 超过VaR后的平均损失
- Sortino Ratio: 只惩罚下行波动的风险调整收益
- Tail Ratio: 右尾/左尾比，衡量收益分布偏度
- Calmar Ratio: 年化收益/最大回撤

搬运自: QuantStats (7k⭐, Apache-2.0)
集成方式: Mixin 混入 RiskManager，与 KellyMixin/SectorMixin 平行
"""

import logging
import numpy as np
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 可选依赖：QuantStats 提供更精确的计算
try:
    import quantstats as qs

    HAS_QS = True
except ImportError:
    qs = None
    HAS_QS = False
    logger.info("quantstats 未安装，VaR/CVaR 使用内置简化计算")


class VaRMixin:
    """VaR/CVaR 风险度量混入类

    依赖 RiskManager.__init__ 中初始化的属性:
        self.config          — RiskConfig 实例
        self._trade_history  — 交易历史 deque (含 pnl 字段)
        self._rolling_pnl    — 滚动窗口 PnL deque
    """

    def calc_var(self, confidence: float = None) -> float:
        """
        计算历史模拟法 VaR (Value at Risk)

        含义: 在给定置信度下，单笔交易的最大预期损失
        例: VaR(95%) = $80 表示 "95%的情况下单笔亏损不超过$80"

        参数:
            confidence: 置信度 (默认从 config 读取, 通常 0.95)

        返回:
            VaR 金额 (正数表示损失)。交易历史不足时返回 0
        """
        conf = confidence or getattr(self.config, "var_confidence", 0.95)
        pnl_list = self._get_pnl_series()

        if len(pnl_list) < 5:
            return 0.0

        # 历史模拟法：直接用百分位计算 VaR
        # 注: QuantStats 的 qs.stats.var() 适用于收益率序列，
        # 此处 pnl_list 是金额序列，直接用 numpy 百分位更准确
        var_value = abs(float(np.percentile(pnl_list, (1 - conf) * 100)))

        return round(var_value, 2)

    def calc_cvar(self, confidence: float = None) -> float:
        """
        计算 CVaR / Expected Shortfall (条件风险价值)

        含义: 当损失超过 VaR 时，平均会亏多少
        比 VaR 更保守，更适合极端行情评估

        参数:
            confidence: 置信度 (默认 0.95)

        返回:
            CVaR 金额 (正数表示损失)。交易历史不足时返回 0
        """
        conf = confidence or getattr(self.config, "var_confidence", 0.95)
        pnl_list = self._get_pnl_series()

        if len(pnl_list) < 5:
            return 0.0

        # CVaR = VaR 以下的尾部损失均值
        # 注: QuantStats 的 qs.stats.cvar() 适用于收益率序列，
        # 此处 pnl_list 是金额序列，直接用 numpy 计算更准确
        var_threshold = np.percentile(pnl_list, (1 - conf) * 100)
        tail_losses = [p for p in pnl_list if p <= var_threshold]
        cvar_value = abs(float(np.mean(tail_losses))) if tail_losses else 0.0

        return round(cvar_value, 2)

    def calc_sortino(self) -> float:
        """
        计算 Sortino Ratio (下行风险调整收益)

        含义: 只惩罚亏损波动，不惩罚盈利波动
        比 Sharpe Ratio 更适合交易系统评估

        返回:
            Sortino Ratio。交易历史不足时返回 0
        """
        pnl_list = self._get_pnl_series()
        if len(pnl_list) < 10:
            return 0.0

        if HAS_QS:
            import pandas as pd

            returns = pd.Series(pnl_list)
            sortino = float(qs.stats.sortino(returns))
            if np.isnan(sortino) or np.isinf(sortino):
                sortino = 0.0
            return round(sortino, 2)
        else:
            # 内置简化计算
            mean_return = np.mean(pnl_list)
            downside = [p for p in pnl_list if p < 0]
            if not downside:
                return 99.0  # 无亏损交易
            downside_std = np.std(downside)
            if downside_std == 0:
                return 0.0
            return round(float(mean_return / downside_std), 2)

    def calc_tail_ratio(self) -> float:
        """
        计算 Tail Ratio (尾部比率)

        含义: 右尾95分位 / 左尾5分位的绝对值
        > 1 表示盈利分布优于亏损分布（好事）
        < 1 表示亏损尾部更厚（坏事）

        返回:
            Tail Ratio。交易历史不足时返回 1.0
        """
        pnl_list = self._get_pnl_series()
        if len(pnl_list) < 10:
            return 1.0

        if HAS_QS:
            import pandas as pd

            returns = pd.Series(pnl_list)
            ratio = float(qs.stats.tail_ratio(returns))
            if np.isnan(ratio) or np.isinf(ratio):
                ratio = 1.0
            return round(ratio, 2)
        else:
            right_tail = np.percentile(pnl_list, 95)
            left_tail = abs(np.percentile(pnl_list, 5))
            if left_tail == 0:
                return 99.0
            return round(float(right_tail / left_tail), 2)

    def calc_calmar(self) -> float:
        """
        计算 Calmar Ratio (收益/最大回撤比)

        含义: 每承受1%的最大回撤，能获得多少收益
        越高越好，通常 > 1 为合格

        返回:
            Calmar Ratio。交易历史不足时返回 0
        """
        pnl_list = self._get_pnl_series()
        if len(pnl_list) < 10:
            return 0.0

        # 计算累计收益曲线
        cumulative = np.cumsum(pnl_list)
        total_return = cumulative[-1]

        # 计算最大回撤
        peak = np.maximum.accumulate(cumulative)
        drawdown = peak - cumulative
        max_dd = np.max(drawdown)

        if max_dd == 0:
            return 99.0 if total_return > 0 else 0.0

        return round(float(total_return / max_dd), 2)

    def get_var_metrics(self) -> Dict:
        """
        获取完整的 VaR 风险度量指标集

        返回包含所有风险指标的字典，供 format_status() 和 get_status() 使用
        """
        pnl_count = len(self._get_pnl_series())
        var_enabled = getattr(self.config, "var_enabled", True)

        if not var_enabled or pnl_count < 5:
            return {
                "var_enabled": var_enabled,
                "var_95": 0.0,
                "cvar_95": 0.0,
                "sortino": 0.0,
                "tail_ratio": 1.0,
                "calmar": 0.0,
                "pnl_count": pnl_count,
                "sufficient_data": False,
            }

        return {
            "var_enabled": var_enabled,
            "var_95": self.calc_var(0.95),
            "cvar_95": self.calc_cvar(0.95),
            "sortino": self.calc_sortino(),
            "tail_ratio": self.calc_tail_ratio(),
            "calmar": self.calc_calmar(),
            "pnl_count": pnl_count,
            "sufficient_data": pnl_count >= 10,
        }

    def check_var_limit(self, proposed_loss: float) -> Optional[str]:
        """
        检查拟议交易的最大损失是否超过 VaR 限额

        用于 check_trade() 中作为第18项检查

        参数:
            proposed_loss: 拟议交易的最大可能损失 (正数)

        返回:
            None 表示通过，字符串表示拒绝原因
        """
        var_enabled = getattr(self.config, "var_enabled", True)
        if not var_enabled:
            return None

        pnl_list = self._get_pnl_series()
        if len(pnl_list) < 10:
            return None  # 数据不足，不做限制

        var_max_pct = getattr(self.config, "var_max_daily_pct", 0.03)
        cvar_reject_pct = getattr(self.config, "cvar_reject_threshold", 0.05)
        capital = self.config.total_capital

        # 检查 CVaR 是否超过资金的阈值比例
        cvar = self.calc_cvar()
        if cvar > capital * cvar_reject_pct:
            return (
                f"CVaR风险过高: 尾部平均损失${cvar:.2f}，"
                f"超过资金{cvar_reject_pct * 100}%限额"
                f"(${capital * cvar_reject_pct:.2f})"
            )

        # 检查拟议损失是否超过 VaR 限额
        var = self.calc_var()
        var_limit = capital * var_max_pct
        if proposed_loss > var_limit and var > var_limit:
            return f"VaR限额警告: 拟议最大损失${proposed_loss:.2f}，VaR(95%)=${var:.2f}，超过日限额${var_limit:.2f}"

        return None

    def _get_pnl_series(self) -> list:
        """从交易历史提取 PnL 序列"""
        if not hasattr(self, "_trade_history") or not self._trade_history:
            return []
        return [t["pnl"] for t in self._trade_history if "pnl" in t]
