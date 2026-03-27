"""
ClawBot 组合再平衡引擎 v2.0
目标配置 + 漂移检测 + 自动调仓建议

v2.0 新增 (2026-03-23):
  - 搬运 PyPortfolioOpt (4.6k⭐) 有效前沿优化
  - `optimize_weights()` — 根据历史数据自动计算最优权重 (最大夏普/最小波动)
  - 离散分配 (DiscreteAllocation) — 精确到整数股数
  - PyPortfolioOpt 不可用时自动降级到等权重/手动目标

核心功能：
1. 目标配置：定义每个标的的目标权重
2. 漂移检测：实时计算当前权重 vs 目标权重的偏差
3. 调仓建议：生成买入/卖出建议以回归目标配置
4. 阈值控制：仅在漂移超过阈值时触发调仓
5. 风控集成：调仓建议经过 RiskManager 审核
6. [NEW] 有效前沿优化：PyPortfolioOpt 自动计算最优权重
"""
import logging
from typing import Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── PyPortfolioOpt 有效前沿 (可选) ──────────────────────────
_HAS_PYPFOPT = False
try:
    from pypfopt import EfficientFrontier, expected_returns, risk_models
    from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices
    _HAS_PYPFOPT = True
    logger.debug("[rebalancer] PyPortfolioOpt 已加载")
except ImportError:
    EfficientFrontier = None  # type: ignore[assignment,misc]
    expected_returns = None   # type: ignore[assignment]
    risk_models = None        # type: ignore[assignment]
    logger.info("[rebalancer] PyPortfolioOpt 未安装，有效前沿优化不可用 (pip install pyportfolioopt)")


# ============ 数据结构 ============

@dataclass
class AllocationTarget:
    """单个标的的目标配置"""
    symbol: str
    target_pct: float       # 目标权重百分比 (0-100)
    min_pct: float = 0      # 最低权重（低于此触发买入）
    max_pct: float = 100    # 最高权重（高于此触发卖出）


@dataclass
class PositionDrift:
    """单个标的的漂移信息"""
    symbol: str
    target_pct: float       # 目标权重
    current_pct: float      # 当前权重
    drift_pct: float        # 漂移 = current - target
    current_value: float    # 当前市值
    target_value: float     # 目标市值
    action: str             # BUY / SELL / HOLD
    shares_delta: int       # 需要买入(+)或卖出(-)的股数
    value_delta: float      # 需要调整的金额


@dataclass
class RebalanceConfig:
    """再平衡配置"""
    drift_threshold_pct: float = 3.0    # 漂移阈值：超过3%才触发
    min_trade_value: float = 50.0       # 最小交易金额（避免碎片交易）
    cash_reserve_pct: float = 5.0       # 现金保留比例
    max_single_trade_pct: float = 20.0  # 单笔调仓不超过组合的20%


@dataclass
class RebalancePlan:
    """再平衡计划"""
    total_value: float = 0              # 组合总价值
    cash: float = 0                     # 当前现金
    target_cash_pct: float = 5.0        # 目标现金比例
    drifts: List[PositionDrift] = field(default_factory=list)
    trades_needed: List[PositionDrift] = field(default_factory=list)  # 需要执行的调仓
    is_balanced: bool = True            # 是否已平衡
    max_drift: float = 0               # 最大漂移

    def format(self) -> str:
        """格式化再平衡计划"""
        lines = [
            "组合再平衡分析",
            "",
            "组合总价值: $%.2f" % self.total_value,
            "现金: $%.2f (%.1f%%)" % (self.cash, self.cash / self.total_value * 100 if self.total_value > 0 else 0),
            "最大漂移: %.1f%%" % self.max_drift,
            "状态: %s" % ("已平衡" if self.is_balanced else "需要调仓"),
            "",
        ]

        if self.drifts:
            lines.append("-- 持仓漂移 --")
            lines.append("%-6s %6s %6s %7s %10s" % ("标的", "目标", "当前", "漂移", "调整"))
            lines.append("-" * 42)
            for d in sorted(self.drifts, key=lambda x: abs(x.drift_pct), reverse=True):
                action_text = ""
                if d.action == "BUY":
                    action_text = "+%d股" % d.shares_delta
                elif d.action == "SELL":
                    action_text = "%d股" % d.shares_delta
                else:
                    action_text = "持有"
                lines.append(
                    "%-6s %5.1f%% %5.1f%% %+6.1f%% %10s"
                    % (d.symbol, d.target_pct, d.current_pct, d.drift_pct, action_text)
                )

        if self.trades_needed:
            lines.append("")
            lines.append("-- 调仓建议 --")
            for t in self.trades_needed:
                if t.action == "BUY":
                    lines.append(
                        "  BUY  %s x%d ($%.2f)" % (t.symbol, t.shares_delta, t.value_delta)
                    )
                elif t.action == "SELL":
                    lines.append(
                        "  SELL %s x%d ($%.2f)" % (t.symbol, abs(t.shares_delta), abs(t.value_delta))
                    )
        elif not self.is_balanced:
            lines.append("")
            lines.append("漂移在阈值内，暂不需要调仓")

        return "\n".join(lines)


# ============ 预设配置模板 ============

# 保守型：大盘ETF为主
CONSERVATIVE_ALLOCATION = [
    AllocationTarget("SPY", 40.0),
    AllocationTarget("QQQ", 25.0),
    AllocationTarget("IWM", 10.0),
    AllocationTarget("BND", 20.0),  # 债券ETF
    # 5% cash reserve
]

# 科技成长型
TECH_GROWTH_ALLOCATION = [
    AllocationTarget("AAPL", 15.0),
    AllocationTarget("MSFT", 15.0),
    AllocationTarget("NVDA", 15.0),
    AllocationTarget("GOOGL", 12.0),
    AllocationTarget("AMZN", 12.0),
    AllocationTarget("META", 10.0),
    AllocationTarget("TSLA", 8.0),
    AllocationTarget("AMD", 8.0),
    # 5% cash reserve
]

# 均衡型
BALANCED_ALLOCATION = [
    AllocationTarget("SPY", 30.0),
    AllocationTarget("QQQ", 20.0),
    AllocationTarget("AAPL", 10.0),
    AllocationTarget("MSFT", 10.0),
    AllocationTarget("NVDA", 10.0),
    AllocationTarget("GOOGL", 10.0),
    AllocationTarget("IWM", 5.0),
    # 5% cash reserve
]

PRESET_ALLOCATIONS = {
    "conservative": ("保守型", CONSERVATIVE_ALLOCATION),
    "tech": ("科技成长型", TECH_GROWTH_ALLOCATION),
    "balanced": ("均衡型", BALANCED_ALLOCATION),
}


# ============ 再平衡引擎 ============

class Rebalancer:
    """组合再平衡引擎"""

    def __init__(self, config: RebalanceConfig = None):
        self.config = config or RebalanceConfig()
        self._targets: List[AllocationTarget] = []

    def set_targets(self, targets: List[AllocationTarget]):
        """设置目标配置"""
        total = sum(t.target_pct for t in targets)
        if total > 100:
            logger.warning("[Rebalancer] 目标权重总和%.1f%% > 100%%，将按比例缩放", total)
            for t in targets:
                t.target_pct = t.target_pct / total * 100
        self._targets = targets
        logger.info("[Rebalancer] 设置目标配置: %d个标的, 总权重%.1f%%",
                    len(targets), sum(t.target_pct for t in targets))

    def get_targets(self) -> List[AllocationTarget]:
        return self._targets

    def analyze(
        self,
        positions: List[Dict],
        quotes: Dict[str, float],
        cash: float,
    ) -> RebalancePlan:
        """
        分析当前组合与目标配置的偏差

        Args:
            positions: 当前持仓 [{"symbol": "AAPL", "quantity": 10, "avg_price": 150}]
            quotes: 实时报价 {"AAPL": 155.0, "MSFT": 420.0}
            cash: 当前现金余额
        """
        if not self._targets:
            return RebalancePlan(is_balanced=True)

        # 计算组合总价值
        position_map = {}
        for p in positions:
            sym = p.get("symbol", "").upper()
            qty = p.get("quantity", 0)
            price = quotes.get(sym, p.get("avg_price", 0) or p.get("avg_cost", 0))
            if qty > 0 and price > 0:
                position_map[sym] = {"quantity": qty, "price": price, "value": qty * price}

        total_position_value = sum(v["value"] for v in position_map.values())
        total_value = total_position_value + cash

        if total_value <= 0:
            return RebalancePlan(is_balanced=True)

        # 可投资金额（扣除现金保留）
        investable = total_value * (1 - self.config.cash_reserve_pct / 100)

        # 计算每个目标的漂移
        drifts = []
        max_drift = 0
        for target in self._targets:
            sym = target.symbol.upper()
            pos = position_map.get(sym, {})
            current_value = pos.get("value", 0)
            current_pct = (current_value / total_value * 100) if total_value > 0 else 0
            target_value = investable * target.target_pct / 100
            drift = current_pct - target.target_pct

            # 确定操作
            price = quotes.get(sym, 0)
            value_delta = target_value - current_value
            shares_delta = 0
            action = "HOLD"

            if price > 0:
                shares_delta = int(value_delta / price)
                if abs(drift) >= self.config.drift_threshold_pct:
                    if drift < 0 and abs(value_delta) >= self.config.min_trade_value:
                        action = "BUY"
                        shares_delta = max(1, shares_delta)
                    elif drift > 0 and abs(value_delta) >= self.config.min_trade_value:
                        action = "SELL"
                        # 不能卖超过持有量
                        max_sell = pos.get("quantity", 0)
                        shares_delta = max(-max_sell, shares_delta)

            d = PositionDrift(
                symbol=sym,
                target_pct=target.target_pct,
                current_pct=round(current_pct, 1),
                drift_pct=round(drift, 1),
                current_value=round(current_value, 2),
                target_value=round(target_value, 2),
                action=action,
                shares_delta=shares_delta,
                value_delta=round(value_delta, 2),
            )
            drifts.append(d)
            max_drift = max(max_drift, abs(drift))

        # 检查未在目标中但有持仓的标的
        target_symbols = {t.symbol.upper() for t in self._targets}
        for sym, pos in position_map.items():
            if sym not in target_symbols:
                current_pct = pos["value"] / total_value * 100
                price = quotes.get(sym, 0)
                qty = pos["quantity"]
                drifts.append(PositionDrift(
                    symbol=sym,
                    target_pct=0,
                    current_pct=round(current_pct, 1),
                    drift_pct=round(current_pct, 1),
                    current_value=round(pos["value"], 2),
                    target_value=0,
                    action="SELL" if current_pct >= self.config.drift_threshold_pct else "HOLD",
                    shares_delta=-qty if current_pct >= self.config.drift_threshold_pct else 0,
                    value_delta=round(-pos["value"], 2),
                ))
                max_drift = max(max_drift, current_pct)

        # 筛选需要执行的调仓
        trades_needed = [d for d in drifts if d.action in ("BUY", "SELL")]

        # 限制单笔调仓金额
        max_trade_value = total_value * self.config.max_single_trade_pct / 100
        for t in trades_needed:
            if abs(t.value_delta) > max_trade_value:
                if t.action == "BUY":
                    t.shares_delta = int(max_trade_value / quotes.get(t.symbol, 1))
                    t.value_delta = round(t.shares_delta * quotes.get(t.symbol, 0), 2)
                elif t.action == "SELL":
                    price = quotes.get(t.symbol, 1)
                    t.shares_delta = -int(max_trade_value / price)
                    t.value_delta = round(t.shares_delta * price, 2)

        # 先卖后买排序
        trades_needed.sort(key=lambda x: (0 if x.action == "SELL" else 1, -abs(x.value_delta)))

        is_balanced = max_drift < self.config.drift_threshold_pct

        plan = RebalancePlan(
            total_value=round(total_value, 2),
            cash=round(cash, 2),
            target_cash_pct=self.config.cash_reserve_pct,
            drifts=drifts,
            trades_needed=trades_needed,
            is_balanced=is_balanced,
            max_drift=round(max_drift, 1),
        )

        logger.info("[Rebalancer] 分析完成: 总价值$%.2f, 最大漂移%.1f%%, 需调仓%d笔",
                    total_value, max_drift, len(trades_needed))
        return plan

    def format_targets(self) -> str:
        """格式化当前目标配置"""
        if not self._targets:
            return "未设置目标配置\n\n可用预设: conservative(保守), tech(科技), balanced(均衡)\n用法: /rebalance set tech"

        lines = [
            "当前目标配置",
            "",
            "%-6s %6s" % ("标的", "目标"),
            "-" * 16,
        ]
        total = 0
        for t in self._targets:
            lines.append("%-6s %5.1f%%" % (t.symbol, t.target_pct))
            total += t.target_pct
        lines.append("-" * 16)
        lines.append("%-6s %5.1f%%" % ("合计", total))
        lines.append("%-6s %5.1f%%" % ("现金", 100 - total))
        return "\n".join(lines)

    async def optimize_weights(
        self,
        symbols: List[str],
        portfolio_value: float,
        objective: str = "max_sharpe",
        period: str = "1y",
    ) -> Dict:
        """使用 PyPortfolioOpt 有效前沿计算最优投资组合权重。

        搬运自 PyPortfolioOpt (4.6k⭐, BSD-3) — 全球最流行的 Python 投资组合优化库。
        包含 Markowitz 均值-方差模型 + 离散分配。

        Args:
            symbols: 股票代码列表, 如 ["AAPL", "MSFT", "GOOGL"]
            portfolio_value: 组合总价值 (用于离散分配)
            objective: 优化目标
                - "max_sharpe"   最大化夏普比率 (默认)
                - "min_volatility" 最小化波动率
                - "max_quadratic_utility" 最大化二次效用
            period: 历史数据周期 ("1y", "2y", "5y")

        Returns:
            dict with:
                weights: {symbol: weight_pct}  # 最优权重 (百分比)
                discrete: {symbol: shares}     # 离散分配 (整数股数)
                performance: {sharpe, ret, vol} # 预期绩效
                source: "pypfopt" | "equal_weight"
                error: str (仅失败时)
        """
        if not _HAS_PYPFOPT:
            # 降级: 等权重
            equal_w = round(100 / len(symbols), 2)
            return {
                "weights": {s: equal_w for s in symbols},
                "discrete": {},
                "performance": {},
                "source": "equal_weight",
                "error": "PyPortfolioOpt 未安装，使用等权重降级 (pip install pyportfolioopt)",
            }

        try:
            import asyncio
            import pandas as pd

            def _run_optimization():
                # 1. 获取历史价格
                try:
                    import yfinance as yf
                    raw = yf.download(
                        symbols, period=period, auto_adjust=True, progress=False
                    )
                    if isinstance(raw.columns, pd.MultiIndex):
                        prices = raw["Close"]
                    else:
                        prices = raw[["Close"]]
                    prices = prices.dropna()
                except Exception as e:
                    raise RuntimeError(f"价格数据获取失败: {e}")

                if prices.empty or len(prices) < 30:
                    raise RuntimeError("历史数据不足 (需至少30个交易日)")

                # 2. 计算预期收益 + 协方差矩阵
                mu = expected_returns.mean_historical_return(prices)
                S = risk_models.sample_cov(prices)

                # 3. 有效前沿优化
                ef = EfficientFrontier(mu, S)
                if objective == "min_volatility":
                    ef.min_volatility()
                elif objective == "max_quadratic_utility":
                    ef.max_quadratic_utility()
                else:  # max_sharpe (default)
                    ef.max_sharpe()

                cleaned_weights = ef.clean_weights()
                perf = ef.portfolio_performance(verbose=False)

                # 4. 离散分配
                latest_prices = get_latest_prices(prices)
                da = DiscreteAllocation(
                    cleaned_weights,
                    latest_prices,
                    total_portfolio_value=portfolio_value,
                )
                allocation, leftover = da.greedy_portfolio()

                return {
                    "weights": {k: round(v * 100, 2) for k, v in cleaned_weights.items()},
                    "discrete": allocation,
                    "leftover": round(leftover, 2),
                    "performance": {
                        "expected_annual_return": round(perf[0] * 100, 2),
                        "annual_volatility": round(perf[1] * 100, 2),
                        "sharpe_ratio": round(perf[2], 3),
                    },
                    "source": "pypfopt",
                    "objective": objective,
                }

            result = await asyncio.to_thread(_run_optimization)

            # 同步更新 Rebalancer targets
            targets = [
                AllocationTarget(symbol=sym, target_pct=pct)
                for sym, pct in result["weights"].items()
                if pct > 0
            ]
            self.set_targets(targets)
            logger.info(
                "[Rebalancer] PyPortfolioOpt 优化完成: %s, sharpe=%.3f",
                objective, result["performance"].get("sharpe_ratio", 0),
            )
            return result

        except Exception as e:
            logger.warning("[Rebalancer] PyPortfolioOpt 优化失败: %s，降级等权重", e)
            equal_w = round(100 / len(symbols), 2)
            return {
                "weights": {s: equal_w for s in symbols},
                "discrete": {},
                "performance": {},
                "source": "equal_weight",
                "error": str(e),
            }



# 全局实例
rebalancer = Rebalancer()
