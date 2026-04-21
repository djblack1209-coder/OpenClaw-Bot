"""
OpenClaw — vectorbt 回测引擎集成 v3.0
搬运整合自:
  - vectorbt (6.9k⭐)    — 向量化快速回测核心
  - quantstats (4.8k⭐)   — HTML 绩效报告 + Tearsheet
  - finlab_crypto (1.2k⭐) — Portfolio.from_signals 最佳实践
  - bt (1.7k⭐)           — 多策略对比框架思路
  - FinRL (11k⭐)         — DRL 强化学习交易策略 (v3.0 新增)
  - Qlib (18k⭐)          — Alpha 因子 + ML 信号策略 (v3.0 新增)

v3.0 新增:
  - DRL 策略回测 (PPO/A2C via stable-baselines3)
  - Alpha 因子策略回测 (16 因子 + LightGBM)
  - 多策略对比扩展至最多 8 策略 (5 TA + 1 DRL + 2 因子)

v2.0 功能:
  - 5 策略内置 (MA交叉 / RSI / MACD / 布林带 / 成交量突破)
  - 止损 / 止盈 / 手续费 / 滑点参数
  - 多策略并行对比 + Telegram 排名表
  - Optuna 超参数自动优化
  - QuantStats HTML 完整报告
  - 基准收益 + Alpha 计算

与现有系统整合:
  - API: GET /api/v1/omega/investment/backtest
  - strategy 参数: ma_cross / rsi / macd / bbands / volume / drl / factor / compare
"""
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from src.execution._utils import safe_float
from src.utils import now_et, scrub_secrets

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
        logger.warning(f"[backtester] 数据下载失败 {symbol}: {scrub_secrets(str(e))}")
    return None


def _fetch_ohlcv(symbol: str, period: str):
    """下载 OHLCV 完整数据"""
    try:
        import yfinance as yf
        df = yf.download(symbol, period=period, progress=False, auto_adjust=True)
        if not df.empty:
            return df
    except Exception as e:
        logger.warning(f"[backtester] OHLCV下载失败 {symbol}: {scrub_secrets(str(e))}")
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

        total_return = safe_float(s.get("Total Return [%]")) / 100
        sharpe = safe_float(s.get("Sharpe Ratio"))
        sortino = safe_float(s.get("Sortino Ratio"))
        calmar = safe_float(s.get("Calmar Ratio"))
        max_dd = abs(safe_float(s.get("Max Drawdown [%]"))) / 100
        win_rate = safe_float(s.get("Win Rate [%]")) / 100
        num_trades = int(safe_float(s.get("Total Trades")))
        ann_return = safe_float(s.get("Annualized Return [%]", total_return * 52)) / 100

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
        logger.warning(f"[backtester] stats 提取失败: {scrub_secrets(str(e))}")
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
                return safe_float(s.get("Sharpe Ratio"))

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

    # ── 策略6: DRL 强化学习 (搬运自 FinRL) ─────────────────

    async def run_drl_strategy(
        self,
        symbol: str,
        period: str = "2y",
        algorithm: str = "ppo",
        train_timesteps: int = 50_000,
    ) -> BacktestResult:
        """DRL 强化学习策略回测 — 搬运自 FinRL (11k⭐)

        使用 stable-baselines3 PPO/A2C 在前 80% 数据上训练，
        后 20% 数据上验证收益表现。
        """
        strategy_name = f"DRL-{algorithm.upper()}"

        def _run():
            try:
                from src.strategies.drl_strategy import StockTradingEnv, HAS_GYM, HAS_SB3
            except ImportError:
                return BacktestResult(symbol=symbol, strategy=strategy_name,
                                      period=period, details={"error": "drl_strategy 模块不可用"})

            if not HAS_GYM or not HAS_SB3:
                return BacktestResult(symbol=symbol, strategy=strategy_name,
                                      period=period,
                                      details={"error": "需要 gymnasium + stable-baselines3"})

            df = _fetch_ohlcv(symbol, period)
            if df is None or df.empty:
                return BacktestResult(symbol=symbol, strategy=strategy_name,
                                      period=period, details={"error": "无价格数据"})

            # 准备数据
            import numpy as np
            ohlcv = pd.DataFrame({
                "open": df["Open"].squeeze() if "Open" in df.columns else df["Close"].squeeze(),
                "high": df["High"].squeeze() if "High" in df.columns else df["Close"].squeeze() * 1.01,
                "low": df["Low"].squeeze() if "Low" in df.columns else df["Close"].squeeze() * 0.99,
                "close": df["Close"].squeeze(),
                "volume": df["Volume"].squeeze() if "Volume" in df.columns else 1_000_000,
            })

            # 前 80% 训练，后 20% 验证
            split = int(len(ohlcv) * 0.8)
            train_df = ohlcv.iloc[:split].reset_index(drop=True)
            test_df = ohlcv.iloc[split:].reset_index(drop=True)

            if len(train_df) < 30 or len(test_df) < 10:
                return BacktestResult(symbol=symbol, strategy=strategy_name,
                                      period=period, details={"error": "数据不足以训练+测试"})

            try:
                from stable_baselines3 import PPO, A2C
                from stable_baselines3.common.vec_env import DummyVecEnv

                # 训练
                train_env = DummyVecEnv([lambda: StockTradingEnv(df=train_df)])
                if algorithm.lower() == "a2c":
                    model = A2C("MlpPolicy", train_env, verbose=0, seed=42)
                else:
                    model = PPO("MlpPolicy", train_env, verbose=0, seed=42,
                                n_steps=128, batch_size=64)
                model.learn(total_timesteps=train_timesteps)

                # 测试
                test_env = StockTradingEnv(df=test_df, initial_amount=self.init_cash)
                obs, _ = test_env.reset()
                portfolio_values = [self.init_cash]

                for _ in range(len(test_df) - 1):
                    action, _ = model.predict(obs, deterministic=True)
                    obs, reward, done, truncated, info = test_env.step(action)
                    portfolio_values.append(test_env.portfolio_value)
                    if done:
                        break

                # 计算指标
                pv = np.array(portfolio_values)
                total_return = (pv[-1] - pv[0]) / pv[0]
                daily_returns = np.diff(pv) / pv[:-1]
                sharpe = (np.mean(daily_returns) / max(np.std(daily_returns), 1e-10)) * np.sqrt(252)
                max_dd = np.max(1 - pv / np.maximum.accumulate(pv))

                # 下行波动率 → Sortino
                downside = daily_returns[daily_returns < 0]
                downside_std = np.std(downside) if len(downside) > 0 else 1e-10
                sortino = (np.mean(daily_returns) / downside_std) * np.sqrt(252)

                calmar = (total_return / max(max_dd, 1e-10)) if max_dd > 0 else 0

                # 基准 (买入持有)
                bm_return = (float(test_df["close"].iloc[-1]) - float(test_df["close"].iloc[0])) / float(test_df["close"].iloc[0])

                return BacktestResult(
                    symbol=symbol, strategy=strategy_name, period=period,
                    total_return=float(total_return),
                    sharpe_ratio=float(sharpe),
                    sortino_ratio=float(sortino),
                    calmar_ratio=float(calmar),
                    max_drawdown=float(max_dd),
                    win_rate=float(np.sum(daily_returns > 0) / max(len(daily_returns), 1)),
                    num_trades=len(test_df),
                    annual_return=float(total_return * 252 / max(len(test_df), 1)),
                    benchmark_return=float(bm_return),
                    alpha=float(total_return - bm_return),
                    best_params={"algorithm": algorithm, "timesteps": train_timesteps},
                    details={"final_value": round(float(pv[-1]), 2),
                             "test_bars": len(test_df)},
                )

            except Exception as e:
                logger.warning(f"[backtester] DRL 回测失败: {scrub_secrets(str(e))}")
                return BacktestResult(symbol=symbol, strategy=strategy_name,
                                      period=period, details={"error": str(e)})

        return await asyncio.to_thread(_run)

    # ── 策略7: Alpha 因子 + ML (搬运自 Qlib) ─────────────

    async def run_factor_strategy(
        self,
        symbol: str,
        period: str = "2y",
        use_ml: bool = True,
    ) -> BacktestResult:
        """Alpha 因子策略回测 — 搬运自 Qlib (Microsoft, 18k⭐)

        使用 16 个 Alpha 因子 + 可选 LightGBM 生成买卖信号，
        通过 vectorbt Portfolio.from_signals 回测。
        """
        strategy_name = "Alpha因子" + ("+ML" if use_ml else "")

        if not self._available:
            return BacktestResult(symbol=symbol, strategy=strategy_name,
                                  period=period, details={"error": "vectorbt 未安装"})

        def _run():
            try:
                from src.strategies.factor_strategy import AlphaFactors, FactorScorer, FactorMLModel, HAS_LGB
            except ImportError:
                return BacktestResult(symbol=symbol, strategy=strategy_name,
                                      period=period, details={"error": "factor_strategy 模块不可用"})

            df = _fetch_ohlcv(symbol, period)
            if df is None or df.empty:
                return BacktestResult(symbol=symbol, strategy=strategy_name,
                                      period=period, details={"error": "无价格数据"})

            import numpy as np

            ohlcv = pd.DataFrame({
                "open": df["Open"].squeeze() if "Open" in df.columns else df["Close"].squeeze(),
                "high": df["High"].squeeze() if "High" in df.columns else df["Close"].squeeze() * 1.01,
                "low": df["Low"].squeeze() if "Low" in df.columns else df["Close"].squeeze() * 0.99,
                "close": df["Close"].squeeze(),
                "volume": df["Volume"].squeeze() if "Volume" in df.columns else 1_000_000,
            })

            price = df["Close"].squeeze()

            # 计算因子
            factors = AlphaFactors.compute_all(ohlcv)

            if use_ml and HAS_LGB:
                # ML 路径: 训练 LightGBM 并生成预测信号
                ml_model = FactorMLModel(symbol)
                if ml_model.train(ohlcv):
                    # 用模型预测每天的得分
                    scores = []
                    for i in range(len(factors)):
                        if i < 60:  # 因子需要预热
                            scores.append(0.0)
                        else:
                            sub = factors.iloc[:i+1]
                            scores.append(ml_model.predict(sub))
                    scores = np.array(scores)
                    entries = pd.Series(scores > 0.3, index=price.index[:len(scores)])
                    exits = pd.Series(scores < -0.3, index=price.index[:len(scores)])
                else:
                    # ML 训练失败，降级到规则
                    scores = factors.apply(lambda row: FactorScorer.score(row) / 100, axis=1)
                    entries = scores > 0.3
                    exits = scores < -0.3
            else:
                # 纯规则路径
                scores = factors.apply(lambda row: FactorScorer.score(row) / 100, axis=1)
                entries = scores > 0.3
                exits = scores < -0.3

            # 对齐长度
            min_len = min(len(price), len(entries), len(exits))
            price = price.iloc[:min_len]
            entries = entries.iloc[:min_len]
            exits = exits.iloc[:min_len]

            try:
                pf = vbt.Portfolio.from_signals(price, entries, exits, **self._pf_kwargs())
                return _extract_stats(pf, symbol, strategy_name, period,
                                      benchmark_close=price)
            except Exception as e:
                logger.warning(f"[backtester] Factor 回测 Portfolio 构建失败: {scrub_secrets(str(e))}")
                return BacktestResult(symbol=symbol, strategy=strategy_name,
                                      period=period, details={"error": str(e)})

        return await asyncio.to_thread(_run)

    # ── 多策略对比 ────────────────────────────────────────

    async def run_multi_strategy_comparison(
        self,
        symbol: str,
        period: str = "2y",
    ) -> ComparisonResult:
        """并行运行所有可用策略并排名（含 DRL 和因子策略）"""
        tasks = [
            self.run_ma_cross(symbol, fast=10, slow=30, period=period),
            self.run_rsi_strategy(symbol, period=period),
            self.run_macd_strategy(symbol, period=period),
            self.run_bbands_strategy(symbol, period=period),
            self.run_volume_strategy(symbol, period=period),
            self.run_factor_strategy(symbol, period=period, use_ml=False),
        ]
        # DRL 和 ML 因子策略仅在依赖可用时加入
        try:
            from src.strategies.drl_strategy import HAS_GYM, HAS_SB3
            if HAS_GYM and HAS_SB3:
                tasks.append(self.run_drl_strategy(symbol, period=period))
        except ImportError:
            pass
        try:
            from src.strategies.factor_strategy import HAS_LGB
            if HAS_LGB:
                tasks.append(self.run_factor_strategy(symbol, period=period, use_ml=True))
        except ImportError:
            pass
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
        returns_series=None,
        benchmark_symbol: str = "SPY",
    ) -> Optional[str]:
        """生成 QuantStats HTML 完整报告（Tearsheet）

        支持两种模式:
        1. 传入 returns_series（推荐）— 直接用已有回测收益率序列
        2. 不传 returns_series — 从 vectorbt 运行策略获取收益率

        参数:
            symbol: 标的代码
            period: 回测周期
            strategy: 策略名称（用于报告标题）
            returns_series: pandas Series 日收益率序列（可选）
            benchmark_symbol: 基准标的代码（默认 SPY，用于对比）

        返回:
            HTML 报告文件路径，失败返回 None
        """
        if not HAS_QS:
            logger.info("quantstats 未安装，跳过 HTML 报告生成")
            return None

        def _run():
            import pandas as pd
            try:
                # 模式1: 使用传入的收益率序列（来自任何回测引擎）
                if returns_series is not None:
                    if isinstance(returns_series, (list, tuple)):
                        returns = pd.Series(returns_series, dtype=float)
                    else:
                        returns = returns_series

                    # 列表形式的日收益率可能是百分比(如 2.5)，需要转换为小数(0.025)
                    if returns.abs().max() > 1.0:
                        returns = returns / 100.0

                # 模式2: 从 vectorbt 运行策略获取
                elif self._available:
                    price = _fetch_price(symbol, period)
                    if price is None or price.empty:
                        return None

                    # 支持所有策略
                    entries, exits = self._get_strategy_signals(strategy, price, symbol, period)
                    if entries is None:
                        return None

                    pf = vbt.Portfolio.from_signals(price, entries, exits, **self._pf_kwargs())
                    returns = pf.returns()
                else:
                    logger.info("vectorbt 未安装且未提供收益率数据")
                    return None

                # 过滤掉 NaN 和无效值
                returns = returns.dropna()
                if len(returns) < 5:
                    logger.warning("[backtester] 收益率数据不足，跳过报告")
                    return None

                # 尝试下载基准收益率（非致命，失败则不对比）
                benchmark = None
                try:
                    import yfinance as yf
                    bm_data = yf.download(
                        benchmark_symbol, period=period,
                        progress=False, auto_adjust=True
                    )
                    if not bm_data.empty:
                        bm_close = bm_data["Close"].squeeze()
                        benchmark = bm_close.pct_change().dropna()
                        # 对齐长度
                        min_len = min(len(returns), len(benchmark))
                        returns = returns.iloc[:min_len]
                        benchmark = benchmark.iloc[:min_len]
                except Exception as bm_err:
                    logger.debug("[backtester] 基准数据下载失败(非致命): %s", bm_err)

                # 生成 HTML 报告
                report_dir = Path(__file__).resolve().parent.parent.parent / "data" / "reports"
                report_dir.mkdir(parents=True, exist_ok=True)
                # 安全文件名
                safe_strategy = strategy.replace("/", "-").replace("\\", "-")
                report_path = report_dir / f"{symbol}_{safe_strategy}_{period}_tearsheet.html"

                title = f"{symbol} {strategy} ({period})"
                if benchmark is not None:
                    qs.reports.html(
                        returns, benchmark=benchmark,
                        output=str(report_path), title=title,
                        download_filename=f"{symbol}_tearsheet.html",
                    )
                else:
                    qs.reports.html(
                        returns, output=str(report_path), title=title,
                        download_filename=f"{symbol}_tearsheet.html",
                    )
                logger.info("[backtester] QuantStats 报告已生成: %s", report_path)
                return str(report_path)
            except Exception as e:
                logger.warning("[backtester] QuantStats 报告生成失败: %s", e)
                return None

        return await asyncio.to_thread(_run)

    def _get_strategy_signals(self, strategy: str, price, symbol: str, period: str):
        """根据策略名称获取买卖信号（供 QuantStats 报告用）

        返回:
            (entries, exits) 元组，失败返回 (None, None)
        """
        if not self._available:
            return None, None

        try:
            if strategy in ("ma_cross", "MA交叉", "MA(10/30)交叉"):
                fast_ma = vbt.MA.run(price, 10)
                slow_ma = vbt.MA.run(price, 30)
                return fast_ma.ma_crossed_above(slow_ma), fast_ma.ma_crossed_below(slow_ma)
            elif strategy in ("rsi", "RSI"):
                rsi = vbt.RSI.run(price, 14)
                return rsi.rsi_below(30), rsi.rsi_above(70)
            elif strategy in ("macd", "MACD"):
                macd = vbt.MACD.run(price, fast_window=12, slow_window=26, signal_window=9)
                entries = macd.macd_above(0) & macd.signal_above(0)
                exits = macd.macd_below(0) | macd.signal_below(0)
                return entries, exits
            elif strategy in ("bbands", "BBands", "布林带"):
                bb = vbt.BBANDS.run(price, window=20, alpha=2.0)
                return price < bb.lower, price > bb.upper
            elif strategy in ("volume", "Volume突破", "成交量突破"):
                df = _fetch_ohlcv(symbol, period)
                if df is not None and "Volume" in df.columns:
                    volume = df["Volume"].squeeze()
                    vol_ma = volume.rolling(20).mean()
                    price_change = price.pct_change() * 100
                    entries = (volume > vol_ma * 2.0) & (price_change > 2.0)
                    exits = price_change < -2.0
                    return entries, exits
                return None, None
            else:
                # 未知策略，使用默认 MA 交叉
                fast_ma = vbt.MA.run(price, 10)
                slow_ma = vbt.MA.run(price, 30)
                return fast_ma.ma_crossed_above(slow_ma), fast_ma.ma_crossed_below(slow_ma)
        except Exception as e:
            logger.warning("[backtester] 策略信号获取失败: %s", e)
            return None, None


# ── 全局单例 ──────────────────────────────────────────────

_backtester: Optional[VectorbtBacktester] = None


def get_backtester() -> VectorbtBacktester:
    """获取全局回测器单例"""
    global _backtester
    if _backtester is None:
        _backtester = VectorbtBacktester()
    return _backtester


# ── 快速信号验证（供投资团队调用）────────────────────────────

async def quick_signal_validation(symbol: str, period: str = "6mo") -> Dict:
    """快速信号验证 — 为投资决策提供历史胜率参考。

    运行 3 个核心策略(MA/RSI/MACD)的简化回测,返回汇总结果。
    设计目标: 5秒内完成,给投资团队提供"信心参考"而非精确回测。

    Args:
        symbol: 股票代码 (如 "AAPL")
        period: 回测周期 (默认 6 个月)

    Returns:
        {
            "symbol": "AAPL",
            "period": "6mo",
            "strategies": [
                {"name": "MA(10/30)交叉", "win_rate": 0.67, "trades": 12, "sharpe": 1.2},
                ...
            ],
            "avg_win_rate": 0.62,
            "best_strategy": "RSI",
            "best_win_rate": 0.72,
            "confidence_label": "中等可信",  # <50% 低 / 50-65% 中等 / >65% 高
            "available": True,
        }
    """
    bt = get_backtester()
    if not bt.available:
        return {
            "symbol": symbol, "period": period, "available": False,
            "strategies": [], "avg_win_rate": 0, "best_strategy": "",
            "best_win_rate": 0, "confidence_label": "无法验证",
        }

    try:
        # 只跑 3 个核心策略(快速), 不跑 DRL/因子(太慢)
        results = await asyncio.gather(
            bt.run_ma_cross(symbol, fast=10, slow=30, period=period),
            bt.run_rsi_strategy(symbol, period=period),
            bt.run_macd_strategy(symbol, period=period),
            return_exceptions=True,
        )

        strategies = []
        for r in results:
            if isinstance(r, BacktestResult) and not r.details.get("error"):
                strategies.append({
                    "name": r.strategy,
                    "win_rate": round(r.win_rate, 3),
                    "trades": r.num_trades,
                    "sharpe": round(r.sharpe_ratio, 2),
                    "total_return": round(r.total_return, 4),
                })

        if not strategies:
            return {
                "symbol": symbol, "period": period, "available": True,
                "strategies": [], "avg_win_rate": 0, "best_strategy": "",
                "best_win_rate": 0, "confidence_label": "数据不足",
            }

        avg_wr = sum(s["win_rate"] for s in strategies) / len(strategies)
        best = max(strategies, key=lambda s: s["win_rate"])

        if avg_wr >= 0.65:
            label = "高可信"
        elif avg_wr >= 0.50:
            label = "中等可信"
        else:
            label = "低可信"

        return {
            "symbol": symbol,
            "period": period,
            "available": True,
            "strategies": strategies,
            "avg_win_rate": round(avg_wr, 3),
            "best_strategy": best["name"],
            "best_win_rate": best["win_rate"],
            "confidence_label": label,
        }

    except Exception as e:
        logger.warning(f"[QuickBacktest] {symbol} 信号验证失败: {scrub_secrets(str(e))}")
        return {
            "symbol": symbol, "period": period, "available": False,
            "strategies": [], "avg_win_rate": 0, "best_strategy": "",
            "best_win_rate": 0, "confidence_label": "验证失败",
        }
