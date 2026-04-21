"""
OpenClaw — PyBroker 回测引擎集成

搬运整合自:
  - PyBroker (3.3k⭐)    — Numba加速 + Bootstrap统计验证 + Walk-Forward分析
  - 设计模式参照 backtester_vbt.py (vectorbt 桥接)

核心优势（相比自研和vectorbt）:
  1. Bootstrap 统计验证: p-value 判断回测结果是否有统计意义
  2. Walk-Forward 分析: 内置前进分析防过拟合（比自研 backtester_advanced 更成熟）
  3. Numba 加速: 比纯 pandas 快 10-50 倍
  4. 止损/仓位管理: 内置支持，无需手动实现

调用入口:
  - Telegram: /backtest AAPL --pb
  - API: GET /api/v1/omega/investment/backtest?engine=pybroker
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from src.utils import now_et, scrub_secrets

logger = logging.getLogger(__name__)

# 可选依赖优雅降级
try:
    import pybroker
    from pybroker import Strategy, StrategyConfig, YFinance

    HAS_PYBROKER = True
except ImportError:
    pybroker = None
    HAS_PYBROKER = False
    logger.info("pybroker 未安装 (pip install lib-pybroker)")

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    pd = None
    HAS_PANDAS = False

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False


# ── 数据类 ──────────────────────────────────────────────


@dataclass
class PyBrokerResult:
    """PyBroker 回测结果 — 复用 BacktestResult 接口"""

    symbol: str
    strategy: str
    period: str
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    annual_return: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0
    benchmark_return: float = 0.0
    alpha: float = 0.0
    # PyBroker 特有指标
    bootstrap_p_value: Optional[float] = None  # Bootstrap 统计验证 p-value
    profit_factor: float = 0.0
    avg_pnl: float = 0.0
    initial_capital: float = 10000.0
    final_equity: float = 0.0
    details: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: now_et().isoformat())

    def to_dict(self) -> Dict:
        """转为字典（API 返回用）"""
        d = {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "period": self.period,
            "engine": "pybroker",
            "total_return": round(self.total_return, 4),
            "total_return_pct": f"{self.total_return * 100:.2f}%",
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "max_drawdown": round(self.max_drawdown, 4),
            "win_rate": round(self.win_rate, 4),
            "num_trades": self.num_trades,
            "annual_return": round(self.annual_return, 4),
            "benchmark_return": round(self.benchmark_return, 4),
            "alpha": round(self.alpha, 4),
            "profit_factor": round(self.profit_factor, 3),
            "avg_pnl": round(self.avg_pnl, 2),
            "initial_capital": self.initial_capital,
            "final_equity": round(self.final_equity, 2),
            "timestamp": self.timestamp,
        }
        if self.bootstrap_p_value is not None:
            d["bootstrap_p_value"] = round(self.bootstrap_p_value, 4)
            d["statistically_significant"] = self.bootstrap_p_value < 0.05
        return d

    def to_telegram_text(self) -> str:
        """生成 Telegram 展示文本"""
        ret_emoji = "📈" if self.total_return > 0 else "📉"
        lines = [
            f"{ret_emoji} *{self.symbol} | {self.strategy}* ({self.period})",
            "🔬 引擎: PyBroker (Numba加速)",
            "─" * 28,
            f"💰 总回报: `{self.total_return * 100:+.2f}%`",
            f"📊 年化收益: `{self.annual_return * 100:+.2f}%`",
            f"⚡ 夏普比率: `{self.sharpe_ratio:.3f}`",
            f"🛡️ 索提诺: `{self.sortino_ratio:.3f}`",
            f"📉 最大回撤: `{self.max_drawdown * 100:.2f}%`",
            f"✅ 胜率: `{self.win_rate * 100:.1f}%`",
            f"🔄 交易次数: `{self.num_trades}`",
            f"💵 盈利因子: `{self.profit_factor:.2f}`",
            f"📌 基准回报: `{self.benchmark_return * 100:+.2f}%`",
            f"⭐ Alpha: `{self.alpha * 100:+.2f}%`",
        ]
        # Bootstrap 统计验证 — PyBroker 核心优势
        if self.bootstrap_p_value is not None:
            sig = "✅ 有统计意义" if self.bootstrap_p_value < 0.05 else "⚠️ 无统计意义"
            lines.append(f"🔬 Bootstrap p值: `{self.bootstrap_p_value:.4f}` {sig}")

        if self.details.get("error"):
            lines.append(f"\n⚠️ {self.details['error']}")
        return "\n".join(lines)


# ── 策略定义 ──────────────────────────────────────────


def _ma_cross_strategy(ctx):
    """均线交叉策略 — 20日/50日 MA"""
    close = ctx.close
    if len(close) < 50:
        return
    ma_short = close[-20:].mean()
    ma_long = close[-50:].mean()
    if not ctx.long_pos():
        if ma_short > ma_long:
            ctx.buy_shares = ctx.calc_target_shares(1.0)
    else:
        if ma_short < ma_long:
            ctx.sell_all_shares()


def _rsi_strategy(ctx):
    """RSI 均值回归策略"""
    close = ctx.close
    if len(close) < 14:
        return
    # 手动计算 RSI 避免额外依赖
    deltas = [close[i] - close[i - 1] for i in range(-13, 0)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    if not ctx.long_pos():
        if rsi < 30:
            ctx.buy_shares = ctx.calc_target_shares(1.0)
    else:
        if rsi > 70:
            ctx.sell_all_shares()


def _momentum_strategy(ctx):
    """动量策略 — 20日回报率"""
    close = ctx.close
    if len(close) < 21:
        return
    momentum = (close[-1] - close[-21]) / close[-21]
    if not ctx.long_pos():
        if momentum > 0.05:  # 20日涨幅超5%
            ctx.buy_shares = ctx.calc_target_shares(1.0)
    else:
        if momentum < -0.03:  # 回撤超3%
            ctx.sell_all_shares()


# 策略注册表
PYBROKER_STRATEGIES = {
    "pb_ma_cross": ("均线交叉 (PyBroker)", _ma_cross_strategy),
    "pb_rsi": ("RSI均值回归 (PyBroker)", _rsi_strategy),
    "pb_momentum": ("动量策略 (PyBroker)", _momentum_strategy),
}


# ── 回测引擎类 ──────────────────────────────────────────


class PyBrokerBacktester:
    """PyBroker 回测引擎封装"""

    def __init__(self, initial_capital: float = 10000.0):
        """初始化回测器"""
        if not HAS_PYBROKER:
            raise ImportError("PyBroker 未安装: pip install lib-pybroker")
        self._initial_capital = initial_capital

    async def run_backtest(
        self,
        symbol: str,
        strategy_name: str = "pb_ma_cross",
        period: str = "1y",
        initial_capital: float = None,
    ) -> PyBrokerResult:
        """
        运行单策略回测

        参数:
            symbol: 标的代码 (如 AAPL)
            strategy_name: 策略名 (pb_ma_cross / pb_rsi / pb_momentum)
            period: 回测周期 (1mo/3mo/6mo/1y/2y/5y)
            initial_capital: 初始资金

        返回:
            PyBrokerResult 回测结果
        """
        capital = initial_capital or self._initial_capital

        if strategy_name not in PYBROKER_STRATEGIES:
            return PyBrokerResult(
                symbol=symbol,
                strategy=strategy_name,
                period=period,
                details={"error": f"未知策略: {strategy_name}，可选: {', '.join(PYBROKER_STRATEGIES.keys())}"},
            )

        # 在线程中运行（PyBroker 是同步的）
        return await asyncio.to_thread(self._run_sync, symbol, strategy_name, period, capital)

    def _run_sync(
        self,
        symbol: str,
        strategy_name: str,
        period: str,
        capital: float,
    ) -> PyBrokerResult:
        """同步执行回测（在线程中调用）"""
        display_name, strategy_fn = PYBROKER_STRATEGIES[strategy_name]

        try:
            # 计算日期范围
            end_date = now_et().strftime("%Y-%m-%d")
            start_date = self._calc_start_date(period, end_date)

            # 配置 PyBroker
            config = StrategyConfig(
                initial_cash=capital,
                bootstrap_sample_size=100,
                bootstrap_samples=1000,
            )

            # 创建策略
            strategy = Strategy(
                YFinance(),
                start_date,
                end_date,
                config,
            )
            strategy.add_execution(strategy_fn, [symbol])

            # 执行回测
            result = strategy.backtest()

            # 提取结果
            return self._extract_result(
                result, symbol, strategy_name, display_name, period, capital, start_date, end_date
            )

        except Exception as e:
            logger.error(f"[PyBroker] {symbol} 回测失败: {scrub_secrets(str(e))}")
            return PyBrokerResult(
                symbol=symbol,
                strategy=display_name,
                period=period,
                initial_capital=capital,
                details={"error": f"回测执行失败: {str(e)[:200]}"},
            )

    def _extract_result(
        self, result, symbol, strategy_name, display_name, period, capital, start_date, end_date
    ) -> PyBrokerResult:
        """从 PyBroker 结果对象提取标准化指标"""
        try:
            metrics = result.metrics_df
            if metrics is None or metrics.empty:
                return PyBrokerResult(
                    symbol=symbol,
                    strategy=display_name,
                    period=period,
                    initial_capital=capital,
                    details={"error": "无交易信号产生"},
                )

            # 提取核心指标（PyBroker metrics_df 是 DataFrame）
            def _get_metric(name, default=0.0):
                try:
                    if name in metrics.index:
                        val = float(metrics.loc[name, "value"])
                        if pd.isna(val):
                            return default
                        return val
                except Exception:
                    return default
                return default

            total_return = _get_metric("total_return_pct", 0) / 100
            sharpe = _get_metric("sharpe", 0)
            max_dd = abs(_get_metric("max_drawdown_pct", 0)) / 100
            win_rate = _get_metric("win_rate", 0) / 100
            num_trades = int(_get_metric("total_trades", 0))
            profit_factor = _get_metric("profit_factor", 0)
            avg_pnl = _get_metric("avg_pnl", 0)
            final_equity = capital * (1 + total_return)

            # 计算年化收益
            import datetime

            d_start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
            d_end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
            days = max((d_end - d_start).days, 1)
            annual_return = ((1 + total_return) ** (365 / days) - 1) if total_return > -1 else -1

            # Sortino / Calmar（如果PyBroker提供）
            sortino = _get_metric("sortino", 0)
            calmar = annual_return / max_dd if max_dd > 0 else 0

            # 基准收益（买入持有）
            benchmark = _get_metric("buy_and_hold_return_pct", 0) / 100

            # Bootstrap p-value — PyBroker 核心优势
            bootstrap_p = None
            try:
                if hasattr(result, "bootstrap") and result.bootstrap is not None:
                    bootstrap_df = result.bootstrap
                    if not bootstrap_df.empty:
                        bootstrap_p = float(bootstrap_df.iloc[0].get("p_value", None))
            except Exception:
                pass  # Bootstrap 可能未启用

            return PyBrokerResult(
                symbol=symbol,
                strategy=display_name,
                period=period,
                total_return=total_return,
                sharpe_ratio=sharpe,
                max_drawdown=max_dd,
                win_rate=win_rate,
                num_trades=num_trades,
                annual_return=annual_return,
                calmar_ratio=calmar,
                sortino_ratio=sortino,
                benchmark_return=benchmark,
                alpha=total_return - benchmark,
                bootstrap_p_value=bootstrap_p,
                profit_factor=profit_factor,
                avg_pnl=avg_pnl,
                initial_capital=capital,
                final_equity=final_equity,
            )

        except Exception as e:
            logger.error(f"[PyBroker] 结果提取失败: {scrub_secrets(str(e))}")
            return PyBrokerResult(
                symbol=symbol,
                strategy=display_name,
                period=period,
                initial_capital=capital,
                details={"error": f"结果提取失败: {str(e)[:200]}"},
            )

    async def run_compare(
        self,
        symbol: str,
        period: str = "1y",
    ) -> List[PyBrokerResult]:
        """运行所有 PyBroker 策略并对比"""
        results = []
        for name in PYBROKER_STRATEGIES:
            r = await self.run_backtest(symbol, name, period)
            results.append(r)
        return sorted(results, key=lambda r: r.sharpe_ratio, reverse=True)

    @staticmethod
    def _calc_start_date(period: str, end_date: str) -> str:
        """将周期字符串转为开始日期"""
        import datetime

        end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        mapping = {
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365,
            "2y": 730,
            "5y": 1825,
        }
        days = mapping.get(period, 365)
        start = end - datetime.timedelta(days=days)
        return start.strftime("%Y-%m-%d")


# ── 全局单例 ──────────────────────────────────────────

_instance: Optional[PyBrokerBacktester] = None


def get_pybroker_backtester(initial_capital: float = 10000.0) -> Optional[PyBrokerBacktester]:
    """获取 PyBroker 回测器全局单例（不可用时返回 None）"""
    global _instance
    if not HAS_PYBROKER:
        return None
    if _instance is None:
        _instance = PyBrokerBacktester(initial_capital)
    return _instance
