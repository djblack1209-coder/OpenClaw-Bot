"""
ClawBot 插件化策略引擎 v3.0（对标 freqtrade 36k⭐）

v3.0 — 2026-03-24:
  - 新增 DRLStrategy (搬运自 FinRL 11k⭐) — PPO/A2C 强化学习交易策略
  - 新增 FactorStrategy (搬运自 Qlib 18k⭐) — 16 Alpha 因子 + LightGBM ML 信号
  - 最多 7 策略加权投票组合 (5 TA + 1 DRL + 1 因子)
  - 所有新策略支持 graceful degradation (缺依赖自动跳过)

v2.0 — 2026-03-22:
  - 用 pandas-ta (5k⭐) 替换手写 RSI/MA/Volume 指标
  - 指标值与标准交易平台一致（Wilder's RSI, EMA/SMA 标准实现）
  - 新增 MACD 策略 + 布林带策略
  - 保持原有 BaseStrategy 抽象 + 加权投票架构

支持：
- 策略基类 + 插件化注册
- 多时间框架分析
- 回测集成接口
- 信号强度评分（与现有 AI 团队投票兼容）
- 策略组合（多策略加权投票）
- 实时 + 历史数据适配器
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd

from src.utils import now_et, scrub_secrets

try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False

logger = logging.getLogger(__name__)


# ============ 信号定义 ============

class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    STRONG_BUY = "strong_buy"
    STRONG_SELL = "strong_sell"


@dataclass
class TradeSignal:
    """交易信号（策略输出）"""
    symbol: str
    signal: SignalType
    score: float              # -100 (强烈卖出) 到 +100 (强烈买入)
    strategy_name: str
    timeframe: str = "1d"
    confidence: float = 0.5   # 0-1 置信度
    reason: str = ""
    indicators: dict[str, float] = field(default_factory=dict)
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0
    timestamp: str = field(default_factory=lambda: now_et().isoformat())


@dataclass
class MarketData:
    """市场数据（策略输入）"""
    symbol: str
    timeframe: str
    closes: list[float]
    opens: list[float] = field(default_factory=list)
    highs: list[float] = field(default_factory=list)
    lows: list[float] = field(default_factory=list)
    volumes: list[float] = field(default_factory=list)
    timestamps: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def last_close(self) -> float:
        return self.closes[-1] if self.closes else 0.0

    @property
    def length(self) -> int:
        return len(self.closes)

    def to_dataframe(self) -> pd.DataFrame:
        """转为 pandas DataFrame（供 pandas-ta 使用）"""
        data = {"close": self.closes}
        if self.opens:
            data["open"] = self.opens
        if self.highs:
            data["high"] = self.highs
        if self.lows:
            data["low"] = self.lows
        if self.volumes:
            data["volume"] = self.volumes
        df = pd.DataFrame(data)
        if self.timestamps:
            df.index = pd.to_datetime(self.timestamps[:len(df)])
        return df


# ============ 策略基类（对标 freqtrade IStrategy） ============

class BaseStrategy(ABC):
    """策略基类 — 所有自定义策略必须继承此类

    对标 freqtrade 的 IStrategy 接口：
    - analyze() 分析市场数据并生成信号
    - 支持多时间框架
    - 支持自定义指标
    """

    # 子类必须设置
    name: str = "base"
    version: str = "1.0"
    timeframes: list[str] = ["1d"]       # 支持的时间框架
    min_data_points: int = 30            # 最少需要的数据点数
    weight: float = 1.0                  # 在策略组合中的权重

    @abstractmethod
    def analyze(self, data: MarketData) -> TradeSignal:
        """分析市场数据，返回交易信号

        子类必须实现此方法。
        """
        ...

    def should_exit(self, data: MarketData, entry_price: float,
                    current_pnl_pct: float) -> TradeSignal | None:
        """判断是否应该退出持仓（可选覆盖）"""
        return None

    def validate_data(self, data: MarketData) -> bool:
        """验证数据是否满足策略要求"""
        return data.length >= self.min_data_points


# ============ 内置策略 ============

class MACrossStrategy(BaseStrategy):
    """均线交叉策略（经典）— v2.0: 使用 pandas-ta 标准 SMA/EMA"""
    name = "ma_cross"
    version = "2.0"
    timeframes = ["1d", "4h"]
    min_data_points = 50

    def __init__(self, fast_period: int = 10, slow_period: int = 30, use_ema: bool = False):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.use_ema = use_ema

    def analyze(self, data: MarketData) -> TradeSignal:
        if not self.validate_data(data):
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name, reason="Insufficient data")

        df = data.to_dataframe()

        if HAS_PANDAS_TA:
            # 使用 pandas-ta 标准指标
            if self.use_ema:
                fast_series = ta.ema(df["close"], length=self.fast_period)
                slow_series = ta.ema(df["close"], length=self.slow_period)
            else:
                fast_series = ta.sma(df["close"], length=self.fast_period)
                slow_series = ta.sma(df["close"], length=self.slow_period)
            fast_ma = fast_series.iloc[-1]
            slow_ma = slow_series.iloc[-1]
            prev_fast = fast_series.iloc[-2]
            prev_slow = slow_series.iloc[-2]
        else:
            # 降级: 手动计算 SMA
            closes = data.closes
            fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
            slow_ma = sum(closes[-self.slow_period:]) / self.slow_period
            prev_fast = sum(closes[-self.fast_period-1:-1]) / self.fast_period
            prev_slow = sum(closes[-self.slow_period-1:-1]) / self.slow_period

        indicators = {"fast_ma": round(fast_ma, 2), "slow_ma": round(slow_ma, 2),
                       "price": data.closes[-1]}

        # 金叉
        if prev_fast <= prev_slow and fast_ma > slow_ma:
            spread_pct = (fast_ma - slow_ma) / slow_ma * 100
            score = min(80, 50 + spread_pct * 10)
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.BUY, score=score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=0.6, reason=f"Golden cross: MA{self.fast_period} > MA{self.slow_period}",
                indicators=indicators, stop_loss_pct=3.0, take_profit_pct=8.0,
            )
        # 死叉
        elif prev_fast >= prev_slow and fast_ma < slow_ma:
            spread_pct = (slow_ma - fast_ma) / slow_ma * 100
            score = max(-80, -50 - spread_pct * 10)
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.SELL, score=score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=0.6, reason=f"Death cross: MA{self.fast_period} < MA{self.slow_period}",
                indicators=indicators,
            )

        # 趋势方向
        trend_score = 20 if fast_ma > slow_ma else -20
        return TradeSignal(
            symbol=data.symbol, signal=SignalType.HOLD, score=trend_score,
            strategy_name=self.name, timeframe=data.timeframe,
            confidence=0.3, reason="No crossover", indicators=indicators,
        )


class RSIMomentumStrategy(BaseStrategy):
    """RSI 动量策略 — v2.0: 使用 pandas-ta 标准 Wilder RSI"""
    name = "rsi_momentum"
    version = "2.0"
    timeframes = ["1d"]
    min_data_points = 20

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def _calc_rsi(self, data: MarketData) -> float:
        """计算 RSI — 优先 pandas-ta（Wilder 标准），降级手动 SMA-RSI"""
        if HAS_PANDAS_TA:
            df = data.to_dataframe()
            rsi_series = ta.rsi(df["close"], length=self.period)
            val = rsi_series.iloc[-1]
            return float(val) if pd.notna(val) else 50.0

        # 降级: SMA-based RSI（与标准值可能有偏差）
        closes = data.closes
        if len(closes) < self.period + 1:
            return 50.0
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        recent = deltas[-self.period:]
        gains = [d for d in recent if d > 0]
        losses = [-d for d in recent if d < 0]
        avg_gain = sum(gains) / self.period if gains else 0
        avg_loss = sum(losses) / self.period if losses else 0.001
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def analyze(self, data: MarketData) -> TradeSignal:
        if not self.validate_data(data):
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name, reason="Insufficient data")

        rsi = self._calc_rsi(data)
        indicators = {"rsi": round(rsi, 1), "price": data.last_close}

        if rsi < self.oversold:
            score = min(90, 50 + (self.oversold - rsi) * 2)
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.BUY, score=score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=0.65, reason=f"RSI oversold: {rsi:.1f}",
                indicators=indicators, stop_loss_pct=2.5, take_profit_pct=6.0,
            )
        elif rsi > self.overbought:
            score = max(-90, -50 - (rsi - self.overbought) * 2)
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.SELL, score=score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=0.65, reason=f"RSI overbought: {rsi:.1f}",
                indicators=indicators,
            )

        return TradeSignal(
            symbol=data.symbol, signal=SignalType.HOLD, score=0,
            strategy_name=self.name, timeframe=data.timeframe,
            confidence=0.3, reason=f"RSI neutral: {rsi:.1f}", indicators=indicators,
        )


class VolumeBreakoutStrategy(BaseStrategy):
    """成交量突破策略 — v2.0: 使用 pandas-ta SMA 计算平均成交量"""
    name = "volume_breakout"
    version = "2.0"
    min_data_points = 20

    def __init__(self, vol_multiplier: float = 2.0, price_change_pct: float = 2.0):
        self.vol_multiplier = vol_multiplier
        self.price_change_pct = price_change_pct

    def analyze(self, data: MarketData) -> TradeSignal:
        if not self.validate_data(data) or not data.volumes or len(data.volumes) < 20:
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name, reason="Insufficient data")

        if HAS_PANDAS_TA:
            df = data.to_dataframe()
            vol_sma = ta.sma(df["volume"], length=20)
            avg_vol = float(vol_sma.iloc[-1]) if pd.notna(vol_sma.iloc[-1]) else 1
        else:
            avg_vol = sum(data.volumes[-20:]) / 20

        current_vol = data.volumes[-1]
        price_change = (data.closes[-1] - data.closes[-2]) / data.closes[-2] * 100

        vol_ratio = current_vol / max(avg_vol, 1)
        indicators = {"volume_ratio": round(vol_ratio, 2),
                       "price_change_pct": round(price_change, 2)}

        if vol_ratio > self.vol_multiplier:
            if price_change > self.price_change_pct:
                score = min(85, 60 + price_change * 5)
                return TradeSignal(
                    symbol=data.symbol, signal=SignalType.STRONG_BUY, score=score,
                    strategy_name=self.name, confidence=0.7,
                    reason=f"Volume breakout UP: vol {vol_ratio:.1f}x, price +{price_change:.1f}%",
                    indicators=indicators, stop_loss_pct=3.0, take_profit_pct=10.0,
                )
            elif price_change < -self.price_change_pct:
                score = max(-85, -60 + price_change * 5)
                return TradeSignal(
                    symbol=data.symbol, signal=SignalType.STRONG_SELL, score=score,
                    strategy_name=self.name, confidence=0.7,
                    reason=f"Volume breakout DOWN: vol {vol_ratio:.1f}x, price {price_change:.1f}%",
                    indicators=indicators,
                )

        return TradeSignal(
            symbol=data.symbol, signal=SignalType.HOLD, score=0,
            strategy_name=self.name, confidence=0.2,
            reason="No volume breakout", indicators=indicators,
        )


class MACDStrategy(BaseStrategy):
    """MACD 策略 — 使用 pandas-ta 标准 MACD（新增 v2.0）"""
    name = "macd"
    version = "2.0"
    timeframes = ["1d"]
    min_data_points = 35
    weight = 1.0

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal_period = signal

    def analyze(self, data: MarketData) -> TradeSignal:
        if not self.validate_data(data):
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name, reason="Insufficient data")

        if not HAS_PANDAS_TA:
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name,
                               reason="pandas-ta not installed, MACD unavailable")

        df = data.to_dataframe()
        macd_df = ta.macd(df["close"], fast=self.fast, slow=self.slow, signal=self.signal_period)
        if macd_df is None or macd_df.empty:
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name, reason="MACD calculation failed")

        # pandas-ta MACD columns: MACD_{f}_{s}_{sig}, MACDh_{f}_{s}_{sig}, MACDs_{f}_{s}_{sig}
        col_prefix = f"MACD_{self.fast}_{self.slow}_{self.signal_period}"
        col_hist = f"MACDh_{self.fast}_{self.slow}_{self.signal_period}"
        col_signal = f"MACDs_{self.fast}_{self.slow}_{self.signal_period}"

        macd_line = float(macd_df[col_prefix].iloc[-1])
        macd_hist = float(macd_df[col_hist].iloc[-1])
        macd_signal = float(macd_df[col_signal].iloc[-1])
        prev_hist = float(macd_df[col_hist].iloc[-2])

        indicators = {
            "macd": round(macd_line, 4),
            "signal": round(macd_signal, 4),
            "histogram": round(macd_hist, 4),
            "price": data.last_close,
        }

        # MACD 柱状图从负转正 → 看涨
        if prev_hist < 0 and macd_hist > 0:
            score = min(75, 45 + abs(macd_hist) * 500)
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.BUY, score=score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=0.6, reason="MACD histogram crossed above zero",
                indicators=indicators, stop_loss_pct=3.0, take_profit_pct=7.0,
            )
        # MACD 柱状图从正转负 → 看跌
        elif prev_hist > 0 and macd_hist < 0:
            score = max(-75, -45 - abs(macd_hist) * 500)
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.SELL, score=score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=0.6, reason="MACD histogram crossed below zero",
                indicators=indicators,
            )

        # 趋势方向
        trend_score = 15 if macd_hist > 0 else -15
        return TradeSignal(
            symbol=data.symbol, signal=SignalType.HOLD, score=trend_score,
            strategy_name=self.name, timeframe=data.timeframe,
            confidence=0.3, reason=f"MACD histogram: {macd_hist:+.4f}",
            indicators=indicators,
        )


class BollingerBandStrategy(BaseStrategy):
    """布林带策略 — 使用 pandas-ta 标准布林带（新增 v2.0）"""
    name = "bollinger"
    version = "2.0"
    timeframes = ["1d"]
    min_data_points = 25
    weight = 0.8

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        self.period = period
        self.std_dev = std_dev

    def analyze(self, data: MarketData) -> TradeSignal:
        if not self.validate_data(data):
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name, reason="Insufficient data")

        if not HAS_PANDAS_TA:
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name,
                               reason="pandas-ta not installed, Bollinger unavailable")

        df = data.to_dataframe()
        bb = ta.bbands(df["close"], length=self.period, std=self.std_dev)
        if bb is None or bb.empty:
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name, reason="BB calculation failed")

        # pandas-ta bbands columns: BBL, BBM, BBU, BBB, BBP
        bbl = float(bb[f"BBL_{self.period}_{self.std_dev}"].iloc[-1])
        bbm = float(bb[f"BBM_{self.period}_{self.std_dev}"].iloc[-1])
        bbu = float(bb[f"BBU_{self.period}_{self.std_dev}"].iloc[-1])
        price = data.last_close

        # %B 位置: (price - lower) / (upper - lower)
        bb_width = bbu - bbl
        pct_b = (price - bbl) / bb_width if bb_width > 0 else 0.5

        indicators = {
            "bb_upper": round(bbu, 2),
            "bb_middle": round(bbm, 2),
            "bb_lower": round(bbl, 2),
            "pct_b": round(pct_b, 3),
            "price": price,
        }

        # 价格跌破下轨 → 超卖
        if price < bbl:
            score = min(80, 50 + (bbl - price) / price * 1000)
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.BUY, score=score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=0.6, reason=f"Price below lower BB ({price:.2f} < {bbl:.2f})",
                indicators=indicators, stop_loss_pct=3.0, take_profit_pct=5.0,
            )
        # 价格突破上轨 → 超买
        elif price > bbu:
            score = max(-80, -50 - (price - bbu) / price * 1000)
            return TradeSignal(
                symbol=data.symbol, signal=SignalType.SELL, score=score,
                strategy_name=self.name, timeframe=data.timeframe,
                confidence=0.6, reason=f"Price above upper BB ({price:.2f} > {bbu:.2f})",
                indicators=indicators,
            )

        return TradeSignal(
            symbol=data.symbol, signal=SignalType.HOLD, score=0,
            strategy_name=self.name, timeframe=data.timeframe,
            confidence=0.25, reason=f"Price within BB (%B: {pct_b:.1%})",
            indicators=indicators,
        )


# ============ 策略引擎（对标 freqtrade StrategyResolver） ============

class StrategyEngine:
    """策略引擎 — 管理多策略组合 + 加权投票

    对标 freqtrade 的策略管理：
    - 注册/注销策略
    - 多策略并行分析
    - 加权投票合并信号
    - 与现有 AI 团队投票系统兼容
    """

    def __init__(self):
        self._strategies: dict[str, BaseStrategy] = {}
        self._results_history: list[dict] = []

    def register(self, strategy: BaseStrategy):
        """注册策略"""
        self._strategies[strategy.name] = strategy
        logger.info(f"[StrategyEngine] 注册策略: {strategy.name} v{strategy.version} (weight={strategy.weight})")

    def unregister(self, name: str):
        """注销策略"""
        self._strategies.pop(name, None)

    def list_strategies(self) -> list[dict[str, Any]]:
        """列出所有已注册策略"""
        return [
            {"name": s.name, "version": s.version, "weight": s.weight,
             "timeframes": s.timeframes, "min_data": s.min_data_points}
            for s in self._strategies.values()
        ]

    def analyze(self, data: MarketData, strategies: list[str] | None = None) -> dict[str, Any]:
        """运行所有（或指定）策略并返回加权合并结果

        Returns:
            {
                "symbol": str,
                "consensus_signal": SignalType,
                "consensus_score": float,
                "confidence": float,
                "signals": [TradeSignal, ...],
                "recommendation": str,
            }
        """
        active = self._strategies
        if strategies:
            active = {k: v for k, v in active.items() if k in strategies}

        if not active:
            return {"symbol": data.symbol, "consensus_signal": SignalType.HOLD,
                    "consensus_score": 0, "confidence": 0, "signals": [],
                    "recommendation": "No strategies registered"}

        signals: list[TradeSignal] = []
        for strategy in active.values():
            try:
                sig = strategy.analyze(data)
                signals.append(sig)
            except Exception as e:
                logger.warning(f"[StrategyEngine] {strategy.name} 分析失败: {scrub_secrets(str(e))}")

        if not signals:
            return {"symbol": data.symbol, "consensus_signal": SignalType.HOLD,
                    "consensus_score": 0, "confidence": 0, "signals": [],
                    "recommendation": "All strategies failed"}

        # 加权投票
        total_weight = sum(
            self._strategies[s.strategy_name].weight
            for s in signals if s.strategy_name in self._strategies
        )
        if total_weight == 0:
            total_weight = len(signals)

        weighted_score = sum(
            s.score * self._strategies[s.strategy_name].weight
            for s in signals if s.strategy_name in self._strategies
        ) / total_weight if total_weight > 0 else 0

        avg_confidence = sum(s.confidence for s in signals) / len(signals)

        # 确定共识信号
        if weighted_score >= 60:
            consensus = SignalType.STRONG_BUY
        elif weighted_score >= 25:
            consensus = SignalType.BUY
        elif weighted_score <= -60:
            consensus = SignalType.STRONG_SELL
        elif weighted_score <= -25:
            consensus = SignalType.SELL
        else:
            consensus = SignalType.HOLD

        # 生成推荐文本
        buy_count = sum(1 for s in signals if s.score > 20)
        sell_count = sum(1 for s in signals if s.score < -20)
        recommendation = (
            f"{len(signals)} strategies: {buy_count} buy, {sell_count} sell. "
            f"Weighted score: {weighted_score:+.1f}, confidence: {avg_confidence:.0%}"
        )

        result = {
            "symbol": data.symbol,
            "consensus_signal": consensus,
            "consensus_score": round(weighted_score, 1),
            "confidence": round(avg_confidence, 2),
            "signals": signals,
            "recommendation": recommendation,
            "timestamp": now_et().isoformat(),
        }

        self._results_history.append({
            "symbol": data.symbol, "score": result["consensus_score"],
            "signal": consensus.value, "ts": result["timestamp"],
        })
        if len(self._results_history) > 500:
            self._results_history = self._results_history[-250:]

        return result

    def get_history(self, symbol: str | None = None, limit: int = 20) -> list[dict]:
        """获取分析历史"""
        history = self._results_history
        if symbol:
            history = [h for h in history if h["symbol"] == symbol]
        return history[-limit:]

    async def backtest_all(
        self,
        symbol: str,
        period: str = "2y",
    ) -> dict[str, Any]:
        """
        所有已注册策略 × VectorBT 回测 — 一键对比。

        搬运自 finlab_crypto (1.2k⭐) 的多策略对比框架思路。
        将 strategy_engine 的策略信号与 VectorBT 的 Portfolio.from_signals 打通。

        Returns:
            {
                "symbol": str,
                "period": str,
                "results": [BacktestResult, ...],
                "best_strategy": str,
                "best_sharpe": float,
                "telegram_text": str,  # 可直接发送到 Telegram 的排名表
            }
        """
        try:
            from src.modules.investment.backtester_vbt import get_backtester
            bt = get_backtester()
            if not bt.available:
                return {"error": "vectorbt 未安装", "symbol": symbol}
        except ImportError:
            return {"error": "backtester_vbt 模块不可用", "symbol": symbol}

        comparison = await bt.run_multi_strategy_comparison(symbol, period=period)

        if not comparison.results:
            return {
                "symbol": symbol, "period": period,
                "results": [], "best_strategy": "N/A",
                "telegram_text": f"❌ {symbol} 无回测数据",
            }

        return {
            "symbol": symbol,
            "period": period,
            "results": [r.to_dict() for r in comparison.results],
            "best_strategy": comparison.best_strategy,
            "best_sharpe": max(r.sharpe_ratio for r in comparison.results),
            "telegram_text": comparison.to_telegram_text(),
        }


# ============ 默认引擎实例 ============

def create_default_engine() -> StrategyEngine:
    """创建带有内置策略的默认引擎（v3.0: 最多 7 策略组合）

    v3.0 新增:
      - DRLStrategy (FinRL 11k⭐) — PPO 强化学习交易 (需 gymnasium + stable-baselines3)
      - FactorStrategy (Qlib 18k⭐) — Alpha 因子 + LightGBM (需 lightgbm 可选)
    """
    engine = StrategyEngine()
    engine.register(MACrossStrategy(fast_period=10, slow_period=30))
    engine.register(RSIMomentumStrategy())
    engine.register(VolumeBreakoutStrategy())
    if HAS_PANDAS_TA:
        engine.register(MACDStrategy())
        engine.register(BollingerBandStrategy())
    else:
        logger.warning("[StrategyEngine] pandas-ta 未安装，MACD 和布林带策略不可用。"
                       "安装: pip install pandas-ta")

    # v3.0: DRL 强化学习策略 (搬运自 FinRL, 可选依赖)
    try:
        from src.strategies.drl_strategy import DRLStrategy
        drl = DRLStrategy(algorithm="ppo", train_timesteps=50_000)
        if drl.available:
            engine.register(drl)
            logger.info("[StrategyEngine] DRL-PPO 策略已注册 (FinRL)")
        else:
            logger.info("[StrategyEngine] DRL 依赖未安装，跳过。"
                        "安装: pip install gymnasium stable-baselines3")
    except ImportError:
        logger.debug("[StrategyEngine] drl_strategy 模块不可用")

    # v3.0: Alpha 因子策略 (搬运自 Qlib, 始终可用; ML 路径需 lightgbm)
    try:
        from src.strategies.factor_strategy import FactorStrategy
        factor = FactorStrategy(use_ml=True, n_future_days=5)
        engine.register(factor)
        if factor.ml_available:
            logger.info("[StrategyEngine] Alpha因子+ML 策略已注册 (Qlib)")
        else:
            logger.info("[StrategyEngine] Alpha因子策略已注册 (纯规则模式, "
                        "安装 lightgbm 可启用 ML)")
    except ImportError:
        logger.debug("[StrategyEngine] factor_strategy 模块不可用")

    return engine
