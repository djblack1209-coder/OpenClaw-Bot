"""
ClawBot 插件化策略引擎 v1.0（对标 freqtrade 36k⭐）

支持：
- 策略基类 + 插件化注册
- 多时间框架分析
- 回测集成接口
- 信号强度评分（与现有 AI 团队投票兼容）
- 策略组合（多策略加权投票）
- 实时 + 历史数据适配器
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

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
    indicators: Dict[str, float] = field(default_factory=dict)
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MarketData:
    """市场数据（策略输入）"""
    symbol: str
    timeframe: str
    closes: List[float]
    opens: List[float] = field(default_factory=list)
    highs: List[float] = field(default_factory=list)
    lows: List[float] = field(default_factory=list)
    volumes: List[float] = field(default_factory=list)
    timestamps: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def last_close(self) -> float:
        return self.closes[-1] if self.closes else 0.0

    @property
    def length(self) -> int:
        return len(self.closes)


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
    timeframes: List[str] = ["1d"]       # 支持的时间框架
    min_data_points: int = 30            # 最少需要的数据点数
    weight: float = 1.0                  # 在策略组合中的权重

    @abstractmethod
    def analyze(self, data: MarketData) -> TradeSignal:
        """分析市场数据，返回交易信号
        
        子类必须实现此方法。
        """
        ...

    def should_exit(self, data: MarketData, entry_price: float,
                    current_pnl_pct: float) -> Optional[TradeSignal]:
        """判断是否应该退出持仓（可选覆盖）"""
        return None

    def validate_data(self, data: MarketData) -> bool:
        """验证数据是否满足策略要求"""
        return data.length >= self.min_data_points


# ============ 内置策略 ============

class MACrossStrategy(BaseStrategy):
    """均线交叉策略（经典）"""
    name = "ma_cross"
    version = "1.0"
    timeframes = ["1d", "4h"]
    min_data_points = 50

    def __init__(self, fast_period: int = 10, slow_period: int = 30):
        self.fast_period = fast_period
        self.slow_period = slow_period

    def analyze(self, data: MarketData) -> TradeSignal:
        if not self.validate_data(data):
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name, reason="Insufficient data")

        closes = data.closes
        fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_ma = sum(closes[-self.slow_period:]) / self.slow_period
        prev_fast = sum(closes[-self.fast_period-1:-1]) / self.fast_period
        prev_slow = sum(closes[-self.slow_period-1:-1]) / self.slow_period

        indicators = {"fast_ma": round(fast_ma, 2), "slow_ma": round(slow_ma, 2),
                       "price": closes[-1]}

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
    """RSI 动量策略"""
    name = "rsi_momentum"
    version = "1.0"
    timeframes = ["1d"]
    min_data_points = 20

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def _calc_rsi(self, closes: List[float]) -> float:
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

        rsi = self._calc_rsi(data.closes)
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
    """成交量突破策略"""
    name = "volume_breakout"
    version = "1.0"
    min_data_points = 20

    def __init__(self, vol_multiplier: float = 2.0, price_change_pct: float = 2.0):
        self.vol_multiplier = vol_multiplier
        self.price_change_pct = price_change_pct

    def analyze(self, data: MarketData) -> TradeSignal:
        if not self.validate_data(data) or not data.volumes or len(data.volumes) < 20:
            return TradeSignal(symbol=data.symbol, signal=SignalType.HOLD,
                               score=0, strategy_name=self.name, reason="Insufficient data")

        avg_vol = sum(data.volumes[-20:-1]) / 19
        current_vol = data.volumes[-1]
        price_change = (data.closes[-1] - data.closes[-2]) / data.closes[-2] * 100

        indicators = {"volume_ratio": round(current_vol / max(avg_vol, 1), 2),
                       "price_change_pct": round(price_change, 2)}

        if current_vol > avg_vol * self.vol_multiplier:
            if price_change > self.price_change_pct:
                score = min(85, 60 + price_change * 5)
                return TradeSignal(
                    symbol=data.symbol, signal=SignalType.STRONG_BUY, score=score,
                    strategy_name=self.name, confidence=0.7,
                    reason=f"Volume breakout UP: vol {current_vol/avg_vol:.1f}x, price +{price_change:.1f}%",
                    indicators=indicators, stop_loss_pct=3.0, take_profit_pct=10.0,
                )
            elif price_change < -self.price_change_pct:
                score = max(-85, -60 + price_change * 5)
                return TradeSignal(
                    symbol=data.symbol, signal=SignalType.STRONG_SELL, score=score,
                    strategy_name=self.name, confidence=0.7,
                    reason=f"Volume breakout DOWN: vol {current_vol/avg_vol:.1f}x, price {price_change:.1f}%",
                    indicators=indicators,
                )

        return TradeSignal(
            symbol=data.symbol, signal=SignalType.HOLD, score=0,
            strategy_name=self.name, confidence=0.2,
            reason="No volume breakout", indicators=indicators,
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
        self._strategies: Dict[str, BaseStrategy] = {}
        self._results_history: List[Dict] = []

    def register(self, strategy: BaseStrategy):
        """注册策略"""
        self._strategies[strategy.name] = strategy
        logger.info(f"[StrategyEngine] 注册策略: {strategy.name} v{strategy.version} (weight={strategy.weight})")

    def unregister(self, name: str):
        """注销策略"""
        self._strategies.pop(name, None)

    def list_strategies(self) -> List[Dict[str, Any]]:
        """列出所有已注册策略"""
        return [
            {"name": s.name, "version": s.version, "weight": s.weight,
             "timeframes": s.timeframes, "min_data": s.min_data_points}
            for s in self._strategies.values()
        ]

    def analyze(self, data: MarketData, strategies: Optional[List[str]] = None) -> Dict[str, Any]:
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

        signals: List[TradeSignal] = []
        for strategy in active.values():
            try:
                sig = strategy.analyze(data)
                signals.append(sig)
            except Exception as e:
                logger.warning(f"[StrategyEngine] {strategy.name} 分析失败: {e}")

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
            "timestamp": datetime.now().isoformat(),
        }

        self._results_history.append({
            "symbol": data.symbol, "score": result["consensus_score"],
            "signal": consensus.value, "ts": result["timestamp"],
        })
        if len(self._results_history) > 500:
            self._results_history = self._results_history[-250:]

        return result

    def get_history(self, symbol: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """获取分析历史"""
        history = self._results_history
        if symbol:
            history = [h for h in history if h["symbol"] == symbol]
        return history[-limit:]


# ============ 默认引擎实例 ============

def create_default_engine() -> StrategyEngine:
    """创建带有内置策略的默认引擎"""
    engine = StrategyEngine()
    engine.register(MACrossStrategy(fast_period=10, slow_period=30))
    engine.register(RSIMomentumStrategy())
    engine.register(VolumeBreakoutStrategy())
    return engine
