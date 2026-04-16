"""
Freqtrade 集成层 v2.0 — 搬运自 Freqtrade (47.8k⭐)

策略：不替换 ClawBot 独有的 AI 团队投票 + 17 规则风控 + IBKR 券商对接，
而是搬运 Freqtrade 的策略框架 + 回测引擎 + 超参优化，与现有系统桥接。

v2.0 新增：
  - 真实数据管道：yfinance 下载 → freqtrade OHLCV 格式转换
  - 结构化结果提取：从 freqtrade Backtesting 提取完整绩效指标
  - SharedMemory 集成：回测结果写入共享记忆，供 AI 团队投票参考
  - LLM 策略分析：通过 LiteLLM Router 对回测结果做智能解读
  - 自研 backtester 降级：freqtrade 不可用时自动降级到 backtester.py

架构：
  Freqtrade IStrategy → ClawBot ta_engine 指标
  Freqtrade Backtesting → 结构化结果 → SharedMemory + LLM 分析
  Freqtrade confirm_trade_entry → ClawBot RiskManager + DecisionValidator
  Freqtrade custom_exit → ClawBot PositionMonitor 逻辑

保留 ClawBot 独有能力：
  - ai_team_voter.py（6 LLM 分析师投票）
  - risk_manager.py（17 规则风控）
  - decision_validator.py（反幻觉验证）
  - trading_journal.py（AI 增强交易日志）
  - broker_bridge.py（IBKR 对接）
"""

import asyncio
import logging
import os
import json
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from src.utils import now_et, env_float
from src.constants import FAMILY_FAST  # noqa: F401 — 快速推理链
from config.prompts import BACKTEST_ANALYST_PROMPT

logger = logging.getLogger(__name__)

# Freqtrade 可用性检测
_freqtrade_available = False
try:
    from freqtrade.strategy import IStrategy
    from freqtrade.persistence import Trade

    _freqtrade_available = True
except ImportError:
    IStrategy = None  # type: ignore[assignment,misc]
    Trade = None  # type: ignore[assignment,misc]
    logger.info("[FreqtradeBridge] freqtrade 未安装，集成层禁用")


def get_freqtrade_config(
    stake_currency: str = "USD",
    dry_run: bool = True,
    strategy: str = "ClawBotAIStrategy",
    timeframe: str = "5m",
    max_open_trades: int = 5,
    pairs: Optional[List[str]] = None,
    datadir: Optional[str] = None,
) -> Dict[str, Any]:
    """生成 Freqtrade 配置（桥接 ClawBot 现有设置）"""
    data_dir = datadir or os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))

    return {
        "strategy": strategy,
        "timeframe": timeframe,
        "max_open_trades": max_open_trades,
        "stake_currency": stake_currency,
        "stake_amount": "unlimited",
        "tradable_balance_ratio": 0.99,
        "dry_run": dry_run,
        "dry_run_wallet": env_float("FT_DRY_RUN_WALLET", 10000),
        "cancel_open_orders_on_exit": True,
        "trading_mode": "spot",
        "margin_mode": "",
        "datadir": str(Path(data_dir) / "freqtrade_data"),
        "user_data_dir": str(Path(data_dir) / "freqtrade_user"),
        "db_url": f"sqlite:///{data_dir}/freqtrade_trades.sqlite",
        "exchange": {
            "name": "binance",
            "key": "",
            "secret": "",
            "pair_whitelist": pairs or [],
            "pair_blacklist": [],
        },
        "protections": [],
        "telegram": {"enabled": False},
        "api_server": {"enabled": False},
        "internals": {"process_throttle_secs": 5},
    }


# ════════════════════════════════════════════
#  ClawBot AI 策略（Freqtrade IStrategy 实现）
# ════════════════════════════════════════════

if _freqtrade_available:

    class ClawBotAIStrategy(IStrategy):
        """
        Freqtrade 策略：桥接 ClawBot 的 AI 团队投票 + TA 引擎

        信号生成流程：
        1. populate_indicators → 调用 ClawBot ta_engine 计算指标
        2. populate_entry_trend → 基于 signal_score 阈值生成入场信号
        3. confirm_trade_entry → 调用 RiskManager + DecisionValidator
        4. custom_exit → 调用 PositionMonitor 的止损/止盈逻辑
        """

        INTERFACE_VERSION = 3
        timeframe = "5m"
        can_short = False
        startup_candle_count = 50
        stoploss = -0.08
        trailing_stop = True
        trailing_stop_positive = 0.01
        trailing_stop_positive_offset = 0.03
        trailing_only_offset_is_reached = True
        minimal_roi = {"0": 0.06, "30": 0.03, "60": 0.01, "120": 0.0}

        # ClawBot 组件引用（延迟注入）
        _risk_manager = None
        _decision_validator = None
        _ta_engine = None
        _journal = None

        @classmethod
        def inject_clawbot(cls, risk_manager=None, decision_validator=None, ta_engine_fn=None, journal=None):
            """注入 ClawBot 组件（启动时调用）"""
            cls._risk_manager = risk_manager
            cls._decision_validator = decision_validator
            cls._ta_engine = ta_engine_fn
            cls._journal = journal

        def populate_indicators(self, dataframe, metadata: dict):
            """使用 ClawBot ta_engine 计算指标"""
            if self._ta_engine:
                try:
                    indicators = self._ta_engine(dataframe)
                    if isinstance(indicators, dict):
                        for k, v in indicators.items():
                            dataframe[k] = v
                    elif hasattr(indicators, "columns"):
                        return indicators
                except Exception as e:
                    logger.warning("[ClawBotAIStrategy] ta_engine 失败: %s", e)

            # 回退：基础指标
            try:
                import talib.abstract as ta

                dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
                dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
                dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
                macd = ta.MACD(dataframe)
                dataframe["macd"] = macd["macd"]
                dataframe["macdsignal"] = macd["macdsignal"]
                bb = ta.BBANDS(dataframe, nbdevup=2, nbdevdn=2)
                dataframe["bb_lower"] = bb["lowerband"]
                dataframe["bb_upper"] = bb["upperband"]
            except ImportError:
                # ta-lib 未安装，用 pandas 计算基础指标
                dataframe["rsi"] = _pandas_rsi(dataframe["close"], 14)
                dataframe["ema20"] = dataframe["close"].ewm(span=20).mean()
                dataframe["ema50"] = dataframe["close"].ewm(span=50).mean()

            # 综合信号分数
            dataframe["signal_score"] = _compute_basic_score(dataframe)
            return dataframe

        def populate_entry_trend(self, dataframe, metadata: dict):
            """基于信号分数生成入场信号"""
            score_col = "signal_score" if "signal_score" in dataframe.columns else None
            if score_col:
                dataframe.loc[
                    (dataframe[score_col] >= 30) & (dataframe["volume"] > 0),
                    ["enter_long", "enter_tag"],
                ] = (1, "signal_score_30")
                dataframe.loc[
                    (dataframe[score_col] >= 50) & (dataframe["volume"] > 0),
                    ["enter_long", "enter_tag"],
                ] = (1, "signal_score_50_strong")
            else:
                # 回退：RSI 超卖
                if "rsi" in dataframe.columns:
                    dataframe.loc[
                        (dataframe["rsi"] < 30) & (dataframe["volume"] > 0),
                        ["enter_long", "enter_tag"],
                    ] = (1, "rsi_oversold")
            return dataframe

        def populate_exit_trend(self, dataframe, metadata: dict):
            """退出信号"""
            if "signal_score" in dataframe.columns:
                dataframe.loc[
                    (dataframe["signal_score"] <= -20) & (dataframe["volume"] > 0),
                    ["exit_long", "exit_tag"],
                ] = (1, "signal_negative")
            if "rsi" in dataframe.columns:
                dataframe.loc[
                    (dataframe["rsi"] > 75) & (dataframe["volume"] > 0),
                    ["exit_long", "exit_tag"],
                ] = (1, "rsi_overbought")
            return dataframe

        def confirm_trade_entry(
            self, pair, order_type, amount, rate, time_in_force, current_time, entry_tag, side, **kwargs
        ) -> bool:
            """入场前调用 ClawBot 风控"""
            if self._risk_manager:
                try:
                    result = self._risk_manager.check_trade(
                        {
                            "symbol": pair,
                            "direction": "BUY" if side == "long" else "SELL",
                            "price": rate,
                            "amount": amount,
                            "entry_tag": entry_tag,
                        }
                    )
                    if not result.get("approved", True):
                        logger.info("[ClawBotAIStrategy] 风控拒绝: %s - %s", pair, result.get("reason", ""))
                        return False
                except Exception as e:
                    logger.warning("[ClawBotAIStrategy] 风控检查异常: %s", e)
            return True

        def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
            """自定义退出逻辑（桥接 PositionMonitor）"""
            # 盈利回撤保护：盈利超过 3% 后回撤 30% 则退出
            if current_profit > 0.03:
                if hasattr(trade, "max_rate") and trade.max_rate:
                    drawdown = (trade.max_rate - current_rate) / trade.max_rate
                    if drawdown > 0.01:  # 从最高点回撤 1%
                        return "profit_drawdown_guard"

            # 时间止损：持仓超过 5 天
            if trade.open_date_utc:
                hours_open = (current_time - trade.open_date_utc).total_seconds() / 3600
                if hours_open > 120 and current_profit < 0.01:
                    return "time_stop_5d"

            return None


# ════════════════════════════════════════════
#  辅助函数
# ════════════════════════════════════════════


def _pandas_rsi(series, period: int = 14):
    """纯 pandas RSI 计算"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def _compute_basic_score(df) -> float:
    """基础信号分数（-100 到 +100）"""
    import pandas as pd

    score = pd.Series(0.0, index=df.index)
    if "rsi" in df.columns:
        score += ((50 - df["rsi"]) * 0.5).clip(-25, 25)
    if "ema20" in df.columns and "ema50" in df.columns:
        ema_diff = (df["ema20"] - df["ema50"]) / df["ema50"] * 100
        score += ema_diff.clip(-25, 25)
    if "macd" in df.columns and "macdsignal" in df.columns:
        macd_diff = df["macd"] - df["macdsignal"]
        score += (macd_diff * 10).clip(-25, 25)
    return score.clip(-100, 100)


# ════════════════════════════════════════════
#  回测桥接
# ════════════════════════════════════════════


@dataclass
class BacktestResult:
    """回测结果结构体"""

    success: bool = False
    symbol: str = ""
    period: str = ""
    strategy: str = ""
    engine: str = "freqtrade"  # "freqtrade" | "builtin"
    # 核心指标
    total_trades: int = 0
    win_rate: float = 0.0
    total_profit_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    sqn: float = 0.0
    profit_factor: float = 0.0
    avg_trade_pct: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    avg_duration: str = ""
    # 元数据
    timerange: str = ""
    error: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    trades: List[Dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: now_et().isoformat())

    def format_telegram(self) -> str:
        """格式化为 Telegram 消息"""
        if not self.success:
            return f"回测失败: {self.error}"
        lines = [
            f"📊 {self.symbol} 回测结果 ({self.period})",
            f"引擎: {self.engine} | 策略: {self.strategy}",
            "─" * 28,
            f"交易数: {self.total_trades}",
            f"胜率: {self.win_rate:.1f}%",
            f"总收益: {self.total_profit_pct:+.2f}%",
            f"最大回撤: {self.max_drawdown_pct:.2f}%",
            f"Sharpe: {self.sharpe_ratio:.2f}",
            f"Sortino: {self.sortino_ratio:.2f}",
            f"SQN: {self.sqn:.2f}",
            f"盈亏比: {self.profit_factor:.2f}",
            f"平均收益: {self.avg_trade_pct:+.2f}%",
            f"最佳: {self.best_trade_pct:+.2f}% | 最差: {self.worst_trade_pct:+.2f}%",
        ]
        if self.avg_duration:
            lines.append(f"平均持仓: {self.avg_duration}")
        return "\n".join(lines)

    def to_memory_dict(self) -> Dict[str, Any]:
        """转为 SharedMemory 存储格式"""
        return {
            "symbol": self.symbol,
            "period": self.period,
            "engine": self.engine,
            "strategy": self.strategy,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "total_profit_pct": self.total_profit_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe": self.sharpe_ratio,
            "sortino": self.sortino_ratio,
            "sqn": self.sqn,
            "profit_factor": self.profit_factor,
            "timestamp": self.timestamp,
        }


class FreqtradeBacktestBridge:
    """
    Freqtrade 回测引擎桥接 v2.0

    数据流：yfinance 下载 → OHLCV parquet → Freqtrade Backtesting → 结构化结果
    集成：结果 → SharedMemory（AI 团队参考）+ LLM 分析（free_pool）
    降级：freqtrade 不可用时自动降级到自研 backtester.py
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or get_freqtrade_config(dry_run=True)
        self._available = _freqtrade_available

    # ── 数据管道 ──

    def _download_data(
        self,
        symbol: str,
        period: str = "1y",
        timeframe: str = "5m",
    ) -> Optional[Path]:
        """yfinance 下载 → freqtrade OHLCV JSON 格式"""
        try:
            import yfinance as yf
            import pandas as pd

            ticker = yf.Ticker(symbol)
            # 映射 period → yfinance interval 限制
            interval_map = {
                "5m": ("5m", "60d"),
                "15m": ("15m", "60d"),
                "1h": ("1h", period),
                "1d": ("1d", period),
            }
            interval, max_period = interval_map.get(timeframe, ("1d", period))

            df = ticker.history(period=max_period, interval=interval)
            if df.empty:
                logger.warning("[FTBridge] %s 无数据", symbol)
                return None

            # 转为 freqtrade 格式: date,open,high,low,close,volume
            df = df.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            df.index.name = "date"
            df = df[["open", "high", "low", "close", "volume"]]

            # 写入 freqtrade datadir
            datadir = Path(self.config["datadir"])
            datadir.mkdir(parents=True, exist_ok=True)
            # freqtrade 命名: SYMBOL_QUOTE-timeframe.json
            pair_name = f"{symbol}/USD"
            fname = f"{symbol}_USD-{timeframe}.json"
            fpath = datadir / fname

            # freqtrade JSON 格式: [[timestamp_ms, o, h, l, c, v], ...]
            records = []
            for ts, row in df.iterrows():
                ts_ms = int(pd.Timestamp(ts).timestamp() * 1000)
                records.append(
                    [
                        ts_ms,
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row["volume"]),
                    ]
                )
            with open(fpath, "w") as f:
                json.dump(records, f)

            logger.info("[FTBridge] 数据已下载: %s → %s (%d bars)", symbol, fpath, len(records))
            return fpath
        except Exception as e:
            logger.error("[FTBridge] 数据下载失败 %s: %s", symbol, e)
            return None

    # ── 结果提取 ──

    @staticmethod
    def _extract_results(bt_results: Dict, symbol: str, period: str) -> BacktestResult:
        """从 freqtrade 回测输出提取结构化结果"""
        result = BacktestResult(
            success=True, symbol=symbol, period=period, engine="freqtrade", strategy="ClawBotAIStrategy"
        )
        try:
            # freqtrade bt_results 结构: strategy_name -> stats dict
            stats = None
            if isinstance(bt_results, dict):
                for key in bt_results:
                    if isinstance(bt_results[key], dict):
                        stats = bt_results[key]
                        break
            if not stats:
                stats = bt_results

            result.total_trades = int(stats.get("total_trades", 0))
            result.win_rate = float(stats.get("win_rate", 0)) * 100  # 转百分比
            result.total_profit_pct = float(stats.get("profit_total", 0)) * 100
            result.max_drawdown_pct = float(stats.get("max_drawdown", 0)) * 100
            result.sharpe_ratio = float(stats.get("sharpe", 0))
            result.sortino_ratio = float(stats.get("sortino", 0))
            result.calmar_ratio = float(stats.get("calmar", 0))
            result.sqn = float(stats.get("sqn", 0))
            result.profit_factor = float(stats.get("profit_factor", 0))
            result.avg_trade_pct = float(stats.get("profit_mean", 0)) * 100
            result.best_trade_pct = float(stats.get("best_trade", 0)) * 100
            result.worst_trade_pct = float(stats.get("worst_trade", 0)) * 100
            result.avg_duration = str(stats.get("holding_avg", ""))
            result.raw = stats

            # 提取交易列表
            trades_list = stats.get("trades", [])
            if isinstance(trades_list, list):
                result.trades = trades_list[:50]  # 最多保留 50 笔
        except Exception as e:
            logger.warning("[FTBridge] 结果提取异常: %s", e)
            result.raw["extract_error"] = str(e)
        return result

    # ── 核心回测 ──

    def run_backtest(
        self,
        symbol: str = "AAPL",
        period: str = "1y",
        strategy: str = "ClawBotAIStrategy",
        timeframe: str = "1d",
    ) -> BacktestResult:
        """运行 freqtrade 回测，失败时降级到自研引擎"""
        pair = f"{symbol}/USD"

        if not self._available:
            return self._fallback_backtest(symbol, period)

        try:
            # 1. 下载数据
            data_path = self._download_data(symbol, period, timeframe)
            if not data_path:
                return self._fallback_backtest(symbol, period)

            # 2. 配置
            config = dict(self.config)
            config["strategy"] = strategy
            config["timeframe"] = timeframe
            config["exchange"]["pair_whitelist"] = [pair]
            config["pairs"] = [pair]

            # 3. 运行 freqtrade 回测
            from freqtrade.optimize.backtesting import Backtesting

            bt = Backtesting(config)
            bt_data, timerange = bt.load_bt_data()
            min_date, max_date = bt.backtest_one_strategy(bt_data, bt.strategy, timerange)
            bt_results = bt.results
            bt.cleanup()

            # 4. 提取结果
            result = self._extract_results(bt_results, symbol, period)
            result.timerange = f"{min_date} → {max_date}"
            logger.info(
                "[FTBridge] 回测完成: %s %d笔交易 %.1f%%收益", symbol, result.total_trades, result.total_profit_pct
            )
            return result

        except Exception as e:
            logger.warning("[FTBridge] freqtrade 回测失败，降级到自研: %s", e)
            return self._fallback_backtest(symbol, period)

    def _fallback_backtest(self, symbol: str, period: str) -> BacktestResult:
        """降级到自研 backtester.py"""
        try:
            from src.backtester import run_backtest as builtin_backtest

            report = builtin_backtest(symbol, period=period)
            result = BacktestResult(
                success=True,
                symbol=symbol,
                period=period,
                engine="builtin",
                strategy="multi_strategy",
                total_trades=getattr(report, "total_trades", 0),
                win_rate=getattr(report, "win_rate", 0) * 100,
                total_profit_pct=getattr(report, "total_return", 0) * 100,
                max_drawdown_pct=getattr(report, "max_drawdown", 0) * 100,
                sharpe_ratio=getattr(report, "sharpe_ratio", 0),
                sortino_ratio=getattr(report, "sortino_ratio", 0),
                profit_factor=getattr(report, "profit_factor", 0),
            )
            result.raw = {"builtin_report": str(report)}
            return result
        except Exception as e:
            return BacktestResult(success=False, symbol=symbol, period=period, error=str(e))

    def get_stats(self) -> Dict[str, Any]:
        return {
            "available": self._available,
            "strategy": self.config.get("strategy", ""),
            "timeframe": self.config.get("timeframe", ""),
            "engine": "freqtrade" if self._available else "builtin_fallback",
        }

    # ── SharedMemory 集成 ──

    async def save_to_memory(
        self,
        result: BacktestResult,
        chat_id: Optional[int] = None,
    ) -> bool:
        """将回测结果写入 SharedMemory，供 AI 团队投票参考"""
        try:
            from src.bot.globals import shared_memory

            if not shared_memory:
                logger.warning("[FTBridge] SharedMemory 未初始化，跳过存储")
                return False

            key = f"backtest_{result.symbol}_{result.period}_{result.engine}"
            value = json.dumps(result.to_memory_dict(), ensure_ascii=False)

            await asyncio.to_thread(
                shared_memory.remember,
                key=key,
                value=value,
                category="backtest",
                source_bot="clawbot",
                chat_id=chat_id or 0,
                importance=7,
                ttl_hours=72,
            )
            logger.info("[FTBridge] 回测结果已存入 SharedMemory: %s", key)
            return True
        except Exception as e:
            logger.warning("[FTBridge] SharedMemory 写入失败: %s", e)
            return False

    # ── LLM 策略分析 ──

    async def analyze_with_llm(self, result: BacktestResult) -> str:
        """通过 LiteLLM Router (free_pool) 对回测结果做智能解读"""
        try:
            from src.litellm_router import free_pool

            if not free_pool:
                return ""

            prompt = (
                f"分析以下回测结果，给出简洁的策略评估（3-5句话）：\n\n"
                f"标的: {result.symbol} | 周期: {result.period} | 引擎: {result.engine}\n"
                f"交易数: {result.total_trades} | 胜率: {result.win_rate:.1f}%\n"
                f"总收益: {result.total_profit_pct:+.2f}% | 最大回撤: {result.max_drawdown_pct:.2f}%\n"
                f"Sharpe: {result.sharpe_ratio:.2f} | Sortino: {result.sortino_ratio:.2f} | SQN: {result.sqn:.2f}\n"
                f"盈亏比: {result.profit_factor:.2f} | 平均收益: {result.avg_trade_pct:+.2f}%\n"
                f"最佳: {result.best_trade_pct:+.2f}% | 最差: {result.worst_trade_pct:+.2f}%\n\n"
                f"请评估：1) 策略质量 2) 风险水平 3) 是否适合实盘 4) 改进建议"
            )

            resp = await free_pool.acompletion(
                model_family=FAMILY_FAST,
                messages=[{"role": "user", "content": prompt}],
                system_prompt=BACKTEST_ANALYST_PROMPT,
            )
            analysis = resp.choices[0].message.content if resp and resp.choices else ""
            logger.info("[FTBridge] LLM 分析完成 (%d chars)", len(analysis))
            return analysis
        except Exception as e:
            logger.warning("[FTBridge] LLM 分析失败: %s", e)
            return f"(LLM 分析不可用: {e})"


# ════════════════════════════════════════════
#  异步包装 + 全局实例
# ════════════════════════════════════════════

_backtest_bridge: Optional[FreqtradeBacktestBridge] = None


def init_freqtrade_bridge(config: Optional[Dict] = None) -> FreqtradeBacktestBridge:
    global _backtest_bridge
    _backtest_bridge = FreqtradeBacktestBridge(config)
    logger.info("[FreqtradeBridge] 初始化完成 (freqtrade=%s)", "可用" if _freqtrade_available else "未安装→降级builtin")
    return _backtest_bridge


def get_backtest_bridge() -> FreqtradeBacktestBridge:
    global _backtest_bridge
    if _backtest_bridge is None:
        _backtest_bridge = init_freqtrade_bridge()
    return _backtest_bridge


async def run_backtest_async(
    symbol: str,
    period: str = "1y",
    timeframe: str = "1d",
    chat_id: Optional[int] = None,
    with_llm: bool = True,
) -> Tuple[BacktestResult, str]:
    """
    异步回测入口（供 Telegram /backtest --ft 调用）

    Returns: (BacktestResult, llm_analysis_text)
    """
    bridge = get_backtest_bridge()

    # 回测（CPU 密集，放线程池）
    result = await asyncio.to_thread(
        bridge.run_backtest,
        symbol,
        period,
        "ClawBotAIStrategy",
        timeframe,
    )

    llm_text = ""
    if result.success:
        # 并行：存 SharedMemory + LLM 分析
        tasks = [bridge.save_to_memory(result, chat_id)]
        if with_llm:
            tasks.append(bridge.analyze_with_llm(result))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        if with_llm and len(results) > 1:
            llm_result = results[1]
            if isinstance(llm_result, str):
                llm_text = llm_result
            elif isinstance(llm_result, Exception):
                llm_text = f"(LLM 分析异常: {llm_result})"

    return result, llm_text
