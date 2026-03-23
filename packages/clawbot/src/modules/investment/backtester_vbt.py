"""
OpenClaw — vectorbt 回测引擎集成 v2.0
搬运整合自:
  - vectorbt (6.9k⭐)    — 向量化快速回测核心
  - quantstats (4.8k⭐)   — HTML 绩效报告 + Tearsheet
  - finlab_crypto (1.2k⭐) — Portfolio.from_signals 最佳实践
  - bt (1.7k⭐)           — 多策略对比框架思路

新增 v2.0 功能:
  - 5 策略内置 (MA交叉 / RSI / MACD / 布林带 / 成交量突破)
  - 止损 / 止盈 / 手续费 / 滑点参数
  - 多策略并行对比 + Telegram 排名表
  - Optuna 超参数自动优化
  - QuantStats HTML 完整报告
  - 基准收益 + Alpha 计算

与现有系统整合:
  - API: GET /api/v1/omega/investment/backtest
  - strategy 参数: ma_cross / rsi / macd / bbands / volume / compare
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from src.utils import now_et

logger = logging.getLogger(__name__)

# ── 可选依赖优雅降级 ──────────────────────────────────────
try:
    import vectorbt as vbt
    HAS_VBT = True
except ImportError:
    vbt = None
    HAS_VBT = False
    logger.info("vectorbt 未安装 (pip install 'vectorbt[full]')")

try:
    import quantstats as qs
    HAS_QS = True
except ImportError:
    qs = None
    HAS_QS = False

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAS_OPTUNA = True
except ImportError:
    optuna = None
    HAS_OPTUNA = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    pd = None
    HAS_PANDAS = False

try:
    import pandas_ta as pandas_ta_lib
    HAS_TA = True
except ImportError:
    pandas_ta_lib = None
    HAS_TA = False


# ── 数据类 ────────────────────────────────────────────────

@dataclass
class BacktestResult:
    """单次回测结果 — 兼容原有接口"""
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
    best_params: Dict = field(default_factory=dict)
    details: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: now_et().isoformat())

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "period": self.period,
            "total_return": round(self.total_return, 4),
            "total_return_pct": f"{self.total_return*100:.2f}%",
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_pct": f"{self.max_drawdown*100:.2f}%",
            "win_rate": round(self.win_rate, 4),
            "win_rate_pct": f"{self.win_rate*100:.1f}%",
            "num_trades": self.num_trades,
            "annual_return": round(self.annual_return, 4),
            "benchmark_return": round(self.benchmark_return, 4),
            "alpha": round(self.alpha, 4),
            "best_params": self.best_params,
            "details": self.details,
            "timestamp": self.timestamp,
        }

    def to_telegram_text(self) -> str:
        ret_emoji = "📈" if self.total_return > 0 else "📉"
        sharpe_stars = min(5, max(0, int(self.sharpe_ratio)))
        bar = "★" * sharpe_stars + "☆" * (5 - sharpe_stars)
        lines = [
            f"{ret_emoji} *{self.symbol} | {self.strategy}* ({self.period})",
            "─" * 28,
            f"💰 总回报: `{self.total_return*100:+.2f}%`",
            f"📊 年化收益: `{self.annual_return*100:+.2f}%`",
            f"⚡ 夏普比率: `{self.sharpe_ratio:.3f}` {bar}",
            f"🛡️ 索提诺: `{self.sortino_ratio:.3f}`",
            f"🎯 卡玛比率: `{self.calmar_ratio:.3f}`",
            f"📉 最大回撤: `{self.max_drawdown*100:.2f}%`",
            f"✅ 胜率: `{self.win_rate*100:.1f}%`",
            f"🔄 交易次数: `{self.num_trades}`",
            f"📌 基准回报: `{self.benchmark_return*100:+.2f}%`",
            f"⭐ Alpha: `{self.alpha*100:+.2f}%`",
        ]
        if self.best_params:
            lines.append(f"🔧 最优参数: `{self.best_params}`")
        if self.details.get("error"):
            lines.append(f"\n⚠️ {self.details['error']}")
        return "\n".join(lines)


@dataclass
class ComparisonResult:
    """多策略对比结果"""
    symbol: str
    period: str
    results: List[BacktestResult] = field(default_factory=list)
    best_strategy: str = ""
    timestamp: str = field(default_factory=lambda: now_et().isoformat())

    def to_telegram_text(self) -> str:
        if not self.results:
            return f"❌ {self.symbol} 无回测结果"
        sorted_r = sorted(self.results, key=lambda r: r.sharpe_ratio, reverse=True)
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"🏆 *{self.symbol} 策略对比* ({self.period})", "─" * 28]
        for i, r in enumerate(sorted_r):
            medal = medals[i] if i < 3 else f"{i+1}."
            lines.append(
                f"{medal} *{r.strategy}*\n"
                f"   回报:`{r.total_return*100:+.2f}%` "
                f"夏普:`{r.sharpe_ratio:.2f}` "
                f"回撤:`{r.max_drawdown*100:.1f}%`"
            )
        lines.append(f"\n🔬 最佳策略: *{self.best_strategy}*")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "period": self.period,
            "best_strategy": self.best_strategy,
            "results": [r.to_dict() for r in self.results],
            "timestamp": self.timestamp,
        }


# ── 工具函数 ──────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _fetch_price(symbol: str, period: str):
    """下载收盘价 — 优先 vectorbt YFData，回退 yfinance"""
    if HAS_VBT:
        try:
            data = vbt.YFData.download(symbol, period=period)
            close = data.get("Close")
            if close is not None and not close.empty:
                return close
        except Exception:
            logger.debug("Silenced exception", exc_info=True)
    try:
        import yfinance as yf
        df = yf.download(symbol, period=period, progress=False, auto_adjust=True)
        if not df.empty:
            return df["Close"].squeeze()
    except Exception as e:
        logger.warning(f"[backtester] 数据下载失败 {symbol}: {e}")
    return None


def _fetch_ohlcv(symbol: str, period: str):
    """下载 OHLCV 完整数据"""
    try:
        import yfinance as yf
        df = yf.download(symbol, period=period, progress=False, auto_adjust=True)
        if not df.empty:
            return df
    except Exception as e:
        logger.warning(f"[backtester] OHLCV下载失败 {symbol}: {e}")
    return None


def _extract_stats(
    pf,
    symbol: str,
    strategy: str,
    period: str,
    benchmark_close=None,
    best_params: Optional[Dict] = None,
) -> BacktestResult:
    """从 vectorbt Portfolio 提取统一统计指标"""
    try:
        stats = pf.stats()
        s = stats.to_dict() if hasattr(stats, "to_dict") else {}

        total_return = _safe_float(s.get("Total Return [%]")) / 100
        sharpe = _safe_float(s.get("Sharpe Ratio"))
        sortino = _safe_float(s.get("Sortino Ratio"))
        calmar = _safe_float(s.get("Calmar Ratio"))
        max_dd = abs(_safe_float(s.get("Max Drawdown [%]"))) / 100
        win_rate = _safe_float(s.get("Win Rate [%]")) / 100
        num_trades = int(_safe_float(s.get("Total Trades")))
        ann_return = _safe_float(s.get("Annualized Return [%]", total_return * 52)) / 100

        bm_return = 0.0
        alpha = total_return
        if benchmark_close is not None and len(benchmark_close) > 1:
            bm_return = float(
                (benchmark_close.iloc[-1] - benchmark_close.iloc[0])
                / benchmark_close.iloc[0]
            )
            alpha = total_return - bm_return

        return BacktestResult(
            symbol=symbol,
            strategy=strategy,
            period=period,
            total_return=total_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            win_rate=win_rate,
            num_trades=num_trades,
            annual_return=ann_return,
            benchmark_return=bm_return,
            alpha=alpha,
            best_params=best_params or {},
            details={k: str(v) for k, v in list(s.items())[:30]},
        )
    except Exception as e:
        logger.warning(f"[backtester] stats 提取失败: {e}")
        return BacktestResult(
            symbol=symbol, strategy=strategy, period=period,
            details={"error": str(e)}
        )


# ── 主回测器 ──────────────────────────────────────────────

class VectorbtBacktester:
    """
    vectorbt 回测引擎 v2.0
    搬运自 vectorbt (6.9k⭐) 官方示例 + finlab_crypto 最佳实践

    内置5策略: MA交叉 / RSI / MACD / 布林带 / 成交量突破
    支持 Optuna 自动优化 + QuantStats 报告 + 多策略对比
    """

    def __init__(
        self,
        init_cash: float = 100_000,
        fees: float = 0.001,
        slippage: float = 0.0005,
    ):
        self._available = HAS_VBT
        self.init_cash = init_cash
        self.fees = fees
        self.slippage = slippage
        if HAS_VBT:
            logger.info("vectorbt 回测引擎就绪 v2.0")

    @property
    def available(self) -> bool:
        return self._available

    def _pf_kwargs(self) -> Dict:
        return {
            "init_cash": self.init_cash,
            "fees": self.fees,
            "slippage": self.slippage,
        }

    # ── 策略1: MA 均线交叉 ────────────────────────────────

    async def run_ma_cross(
        self,
        symbol: str,
        fast: int = 10,
        slow: int = 30,
        period: str = "2y",
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
    ) -> BacktestResult:
        """均线交叉策略 — vectorbt MA.run 向量化"""
        if not self._available:
            return BacktestResult(symbol=symbol, strategy="MA交叉",
                                  period=period, details={"error": "vectorbt 未安装"})

        def _run():
            price = _fetch_price(symbol, period)
            if price is None or price.empty:
                return BacktestResult(symbol=symbol, strategy=f"MA({fast}/{slow})交叉",
                                      period=period, details={"error": "无价格数据"})
            fast_ma = vbt.MA.run(price, fast)
            slow_ma = vbt.MA.run(price, slow)
            entries = fast_ma.ma_crossed_above(slow_ma)
            exits = fast_ma.ma_crossed_below(slow_ma)
            kw = self._pf_kwargs()
            if stop_loss > 0:
                kw["sl_stop"] = stop_loss
            if take_profit > 0:
                kw["tp_stop"] = take_profit
            pf = vbt.Portfolio.from_signals(price, entries, exits, **kw)
            return _extract_stats(pf, symbol, f"MA({fast}/{slow})交叉", period,
                                  benchmark_close=price)

        return await asyncio.to_thread(_run)

    async def run_ma_cross_optimized(
        self,
        symbol: str,
        period: str = "2y",
        n_trials: int = 50,
    ) -> BacktestResult:
        """MA交叉 + Optuna 超参数优化"""
        if not self._available:
            return BacktestResult(symbol=symbol, strategy="MA交叉(优化)",
                                  period=period, details={"error": "vectorbt 未安装"})
        if not HAS_OPTUNA:
            logger.warning("optuna 未安装，回退默认参数")
            return await self.run_ma_cross(symbol, period=period)

        def _run():
            price = _fetch_price(symbol, period)
            if price is None or price.empty:
                return BacktestResult(symbol=symbol, strategy="MA交叉(优化)",
                                      period=period, details={"error": "无价格数据"})

            def objective(trial):
                fast = trial.suggest_int("fast", 3, 30)
                slow = trial.suggest_int("slow", fast + 5, 80)
                fast_ma = vbt.MA.run(price, fast)
                slow_ma = vbt.MA.run(price, slow)
                entries = fast_ma.ma_crossed_above(slow_ma)
                exits = fast_ma.ma_crossed_below(slow_ma)
                pf = vbt.Portfolio.from_signals(price, entries, exits, **self._pf_kwargs())
                s = pf.stats().to_dict() if hasattr(pf.stats(), "to_dict") else {}
                return _safe_float(s.get("Sharpe Ratio"))

            study = optuna.create_study(direction="maximize")
            study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
            best = study.best_params
            fast, slow = best["fast"], best["slow"]
            fast_ma = vbt.MA.run(price, fast)
            slow_ma = vbt.MA.run(price, slow)
            entries = fast_ma.ma_crossed_above(slow_ma)
            exits = fast_ma.ma_crossed_below(slow_ma)
            pf = vbt.Portfolio.from_signals(price, entries, exits, **self._pf_kwargs())
            return _extract_stats(pf, symbol, f"MA({fast}/{slow})交叉[优化]", period,
                                  benchmark_close=price, best_params=best)

        return await asyncio.to_thread(_run)

    # ── 策略2: RSI 超买超卖 ───────────────────────────────

    async def run_rsi_strategy(
        self,
        symbol: str,
        period: str = "2y",
        rsi_window: int = 14,
        oversold: int = 30,
        overbought: int = 70,
    ) -> BacktestResult:
        """RSI 均值回归策略 — 超卖买入 / 超买卖出"""
        if not self._available:
            return BacktestResult(symbol=symbol, strategy="RSI",
                                  period=period, details={"error": "vectorbt 未安装"})

        def _run():
            price = _fetch_price(symbol, period)
            if price is None or price.empty:
                return BacktestResult(symbol=symbol, strategy=f"RSI({rsi_window})",
                                      period=period, details={"error": "无价格数据"})
            rsi = vbt.RSI.run(price, rsi_window)
            entries = rsi.rsi_below(oversold)
            exits = rsi.rsi_above(overbought)
            pf = vbt.Portfolio.from_signals(price, entries, exits, **self._pf_kwargs())
            return _extract_stats(pf, symbol, f"RSI({rsi_window},{oversold}/{overbought})",
                                  period, benchmark_close=price)

        return await asyncio.to_thread(_run)

    # ── 策略3: MACD 动量 ──────────────────────────────────

    async def run_macd_strategy(
        self,
        symbol: str,
        period: str = "2y",
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> BacktestResult:
        """MACD 柱状图穿越零轴策略"""
        if not self._available:
            return BacktestResult(symbol=symbol, strategy="MACD",
                                  period=period, details={"error": "vectorbt 未安装"})

        def _run():
            price = _fetch_price(symbol, period)
            if price is None or price.empty:
                return BacktestResult(symbol=symbol, strategy=f"MACD({fast},{slow},{signal})",
                                      period=period, details={"error": "无价格数据"})
            macd = vbt.MACD.run(price, fast_window=fast, slow_window=slow, signal_window=signal)
            entries = macd.macd_above(0) & macd.signal_above(0)
            exits = macd.macd_below(0) | macd.signal_below(0)
            pf = vbt.Portfolio.from_signals(price, entries, exits, **self._pf_kwargs())
            return _extract_stats(pf, symbol, f"MACD({fast},{slow},{signal})",
                                  period, benchmark_close=price)

        return await asyncio.to_thread(_run)

    # ── 策略4: 布林带突破 ─────────────────────────────────

    async def run_bbands_strategy(
        self,
        symbol: str,
        period: str = "2y",
        window: int = 20,
        std: float = 2.0,
    ) -> BacktestResult:
        """布林带均值回归策略 — 跌破下轨买入 / 突破上轨卖出"""
        if not self._available:
            return BacktestResult(symbol=symbol, strategy="BBands",
                                  period=period, details={"error": "vectorbt 未安装"})

        def _run():
            price = _fetch_price(symbol, period)
            if price is None or price.empty:
                return BacktestResult(symbol=symbol, strategy=f"BBands({window},{std})",
                                      period=period, details={"error": "无价格数据"})
            bb = vbt.BBANDS.run(price, window=window, alpha=std)
            entries = price < bb.lower
            exits = price > bb.upper
            pf = vbt.Portfolio.from_signals(price, entries, exits, **self._pf_kwargs())
            return _extract_stats(pf, symbol, f"BBands({window},{std}σ)",
                                  period, benchmark_close=price)

        return await asyncio.to_thread(_run)

    # ── 策略5: 成交量突破 ─────────────────────────────────

    async def run_volume_strategy(
        self,
        symbol: str,
        period: str = "2y",
        vol_window: int = 20,
        vol_threshold: float = 2.0,
        price_change_pct: float = 2.0,
    ) -> BacktestResult:
        """成交量突破策略 — 放量上涨买入"""
        if not self._available:
            return BacktestResult(symbol=symbol, strategy="Volume",
                                  period=period, details={"error": "vectorbt 未安装"})

        def _run():
            df = _fetch_ohlcv(symbol, period)
            if df is None or df.empty or "Volume" not in df.columns:
                return BacktestResult(symbol=symbol, strategy="Volume突破",
                                      period=period, details={"error": "无成交量数据"})
            price = df["Close"].squeeze()
            volume = df["Volume"].squeeze()
            vol_ma = volume.rolling(vol_window).mean()
            price_change = price.pct_change() * 100
            entries = (volume > vol_ma * vol_threshold) & (price_change > price_change_pct)
            exits = price_change < -price_change_pct
            pf = vbt.Portfolio.from_signals(price, entries, exits, **self._pf_kwargs())
            return _extract_stats(pf, symbol, f"Volume({vol_window},{vol_threshold}x)",
                                  period, benchmark_close=price)

        return await asyncio.to_thread(_run)

    # ── 多策略对比 ────────────────────────────────────────

    async def run_multi_strategy_comparison(
        self,
        symbol: str,
        period: str = "2y",
    ) -> ComparisonResult:
        """并行运行5个策略并排名"""
        tasks = [
            self.run_ma_cross(symbol, fast=10, slow=30, period=period),
            self.run_rsi_strategy(symbol, period=period),
            self.run_macd_strategy(symbol, period=period),
            self.run_bbands_strategy(symbol, period=period),
            self.run_volume_strategy(symbol, period=period),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if isinstance(r, BacktestResult) and not r.details.get("error")]
        if not valid:
            return ComparisonResult(symbol=symbol, period=period, results=[])
        best = max(valid, key=lambda r: r.sharpe_ratio)
        return ComparisonResult(
            symbol=symbol,
            period=period,
            results=valid,
            best_strategy=best.strategy,
        )

    # ── QuantStats 报告 ───────────────────────────────────

    async def generate_quantstats_report(
        self,
        symbol: str,
        period: str = "1y",
        strategy: str = "ma_cross",
    ) -> Optional[str]:
        """生成 QuantStats HTML 完整报告（Tearsheet）"""
        if not self._available or not HAS_QS:
            logger.info("quantstats 或 vectorbt 未安装")
            return None

        def _run():
            try:
                import yfinance as yf
                df = yf.download(symbol, period=period, progress=False, auto_adjust=True)
                if df.empty:
                    return None
                price = df["Close"].squeeze()
                
                # 运行策略获取信号
                if strategy == "ma_cross":
                    fast_ma = vbt.MA.run(price, 10)
                    slow_ma = vbt.MA.run(price, 30)
                    entries = fast_ma.ma_crossed_above(slow_ma)
                    exits = fast_ma.ma_crossed_below(slow_ma)
                elif strategy == "rsi":
                    rsi = vbt.RSI.run(price, 14)
                    entries = rsi.rsi_below(30)
                    exits = rsi.rsi_above(70)
                else:
                    return None

                pf = vbt.Portfolio.from_signals(price, entries, exits, **self._pf_kwargs())
                returns = pf.returns()

                # 生成 HTML 报告
                report_dir = Path(__file__).resolve().parent.parent.parent / "data" / "reports"
                report_dir.mkdir(parents=True, exist_ok=True)
                report_path = report_dir / f"{symbol}_{strategy}_{period}_tearsheet.html"
                qs.reports.html(returns, output=str(report_path), title=f"{symbol} {strategy.upper()}")
                logger.info(f"[backtester] QuantStats 报告已生成: {report_path}")
                return str(report_path)
            except Exception as e:
                logger.warning(f"[backtester] QuantStats 报告生成失败: {e}")
                return None

        return await asyncio.to_thread(_run)


# ── 全局单例 ──────────────────────────────────────────────

_backtester: Optional[VectorbtBacktester] = None


def get_backtester() -> VectorbtBacktester:
    """获取全局回测器单例"""
    global _backtester
    if _backtester is None:
        _backtester = VectorbtBacktester()
    return _backtester