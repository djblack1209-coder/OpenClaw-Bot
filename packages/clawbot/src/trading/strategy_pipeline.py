"""
Trading — 策略管道连接器

将 StrategyEngine、AI 团队投票、保护系统、回测引擎串联起来。
这是 Phase 3 的核心 — 填补原有模块之间的断裂。

数据流:
  ta_engine.scan_market() → StrategyEngine.analyze() → AI Team Vote → Protections → Execute

原有问题: auto_trader 直接用 ta_engine 的原始信号，跳过了 StrategyEngine。
修复: 插入 StrategyPipeline 作为中间层。
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class PipelineCandidate:
    """经过策略引擎评估的候选标的"""
    symbol: str
    strategy_score: float       # 策略引擎综合评分 (-100 ~ +100)
    strategy_signal: str        # BUY / SELL / HOLD
    strategy_confidence: float  # 0-1
    strategy_reasons: List[str] = field(default_factory=list)
    indicators: Dict[str, float] = field(default_factory=dict)
    # AI 团队投票结果（投票后填充）
    ai_decision: str = ""
    ai_avg_confidence: float = 0.0
    ai_buy_votes: int = 0
    ai_entry: float = 0.0
    ai_stop: float = 0.0
    ai_target: float = 0.0
    # 保护系统结果
    protection_allowed: bool = True
    protection_reason: str = ""
    # 原始 ta_engine 数据（透传）
    raw_analysis: Dict[str, Any] = field(default_factory=dict)


class StrategyPipeline:
    """
    策略管道 — 串联所有交易决策组件。

    使用方式:
        pipeline = StrategyPipeline(strategy_engine, protection_mgr)
        candidates = await pipeline.evaluate(symbols, scan_results)
        approved = await pipeline.vote_and_filter(candidates, ai_team_fn)
    """

    def __init__(
        self,
        strategy_engine=None,
        protection_manager=None,
        min_strategy_score: float = 30.0,
        require_strategy_buy: bool = True,
    ):
        self.strategy_engine = strategy_engine
        self.protection_manager = protection_manager
        self.min_strategy_score = min_strategy_score
        self.require_strategy_buy = require_strategy_buy
        self._stats = {"evaluated": 0, "passed_strategy": 0, "passed_protection": 0, "voted": 0}

    def evaluate_candidates(
        self,
        scan_results: List[Dict],
        trade_history: List[Dict] = None,
    ) -> List[PipelineCandidate]:
        """
        Phase 1: 策略引擎评估 + 保护系统过滤

        Args:
            scan_results: ta_engine.scan_market() 的输出
            trade_history: 最近交易记录（给保护系统用）
        """
        candidates = []

        for item in scan_results:
            symbol = item.get("symbol", "")
            if not symbol:
                continue
            self._stats["evaluated"] += 1

            # 1. 策略引擎评估
            strategy_score = 0.0
            strategy_signal = "HOLD"
            strategy_confidence = 0.0
            strategy_reasons = []

            if self.strategy_engine:
                try:
                    # 从 scan_results 构建 MarketData
                    md = _build_market_data(symbol, item)
                    result = self.strategy_engine.analyze(md)
                    if result:
                        strategy_score = result.get("score", 0)
                        strategy_signal = result.get("signal", "HOLD")
                        strategy_confidence = result.get("confidence", 0)
                        strategy_reasons = result.get("reasons", [])
                except Exception as e:
                    logger.debug(f"[StrategyPipeline] {symbol} 策略评估失败: {e}")
                    # 回退: 使用 ta_engine 的原始信号
                    strategy_score = float(item.get("score", 0))
                    strategy_signal = "BUY" if strategy_score >= self.min_strategy_score else "HOLD"
            else:
                # 无策略引擎: 直接用 ta_engine 信号（向后兼容）
                strategy_score = float(item.get("score", 0))
                strategy_signal = "BUY" if strategy_score >= self.min_strategy_score else "HOLD"
                strategy_confidence = min(1.0, strategy_score / 100.0)

            # 2. 策略过滤
            if self.require_strategy_buy and strategy_signal not in ("BUY", "STRONG_BUY", "buy", "strong_buy"):
                continue
            if strategy_score < self.min_strategy_score:
                continue
            self._stats["passed_strategy"] += 1

            # 3. 保护系统检查
            protection_allowed = True
            protection_reason = ""
            if self.protection_manager:
                result = self.protection_manager.check_all(
                    symbol=symbol, trade_history=trade_history or []
                )
                protection_allowed = result.allowed
                protection_reason = result.reason

            if not protection_allowed:
                logger.info(f"[StrategyPipeline] {symbol} 被保护系统拦截: {protection_reason}")
                continue
            self._stats["passed_protection"] += 1

            candidates.append(PipelineCandidate(
                symbol=symbol,
                strategy_score=strategy_score,
                strategy_signal=strategy_signal,
                strategy_confidence=strategy_confidence,
                strategy_reasons=strategy_reasons,
                indicators=item.get("indicators", {}),
                protection_allowed=protection_allowed,
                protection_reason=protection_reason,
                raw_analysis=item,
            ))

        # 按策略评分排序
        candidates.sort(key=lambda c: -c.strategy_score)
        return candidates

    async def vote_and_filter(
        self,
        candidates: List[PipelineCandidate],
        ai_team_vote_fn: Callable = None,
        max_candidates: int = 5,
    ) -> List[PipelineCandidate]:
        """
        Phase 2: AI 团队投票

        Args:
            candidates: evaluate_candidates() 的输出
            ai_team_vote_fn: AI 团队投票函数 (async)
            max_candidates: 最多提交投票的候选数
        """
        if not ai_team_vote_fn or not candidates:
            return candidates[:max_candidates]

        # 只对 top N 候选进行投票（节省 API 调用）
        to_vote = candidates[:max_candidates]

        for candidate in to_vote:
            try:
                # 构建投票输入（与 ai_team_voter 兼容）
                vote_input = {
                    "symbol": candidate.symbol,
                    "score": candidate.strategy_score,
                    "strategy_signal": candidate.strategy_signal,
                    "strategy_confidence": candidate.strategy_confidence,
                    "strategy_reasons": candidate.strategy_reasons,
                    **candidate.raw_analysis,
                }
                result = await ai_team_vote_fn(vote_input)
                if result:
                    candidate.ai_decision = result.get("decision", "HOLD")
                    candidate.ai_avg_confidence = float(result.get("avg_confidence", 0))
                    candidate.ai_buy_votes = int(result.get("buy_votes", 0))
                    candidate.ai_entry = float(result.get("entry", 0))
                    candidate.ai_stop = float(result.get("stop_loss", 0))
                    candidate.ai_target = float(result.get("take_profit", 0))
                    self._stats["voted"] += 1
            except Exception as e:
                logger.warning(f"[StrategyPipeline] {candidate.symbol} AI 投票失败: {e}")
                candidate.ai_decision = "HOLD"

        # 过滤: 只保留 AI 团队也同意 BUY 的
        approved = [c for c in to_vote if c.ai_decision == "BUY"]
        return approved

    def get_stats(self) -> Dict:
        return dict(self._stats)

    def reset_stats(self):
        self._stats = {"evaluated": 0, "passed_strategy": 0, "passed_protection": 0, "voted": 0}


def _build_market_data(symbol: str, scan_item: Dict):
    """从 ta_engine scan 结果构建 StrategyEngine 的 MarketData"""
    from src.strategy_engine import MarketData
    indicators = scan_item.get("indicators", {})
    closes = scan_item.get("closes", [])
    if not closes:
        price = float(scan_item.get("price", 0) or indicators.get("close", 0))
        closes = [price] if price > 0 else []
    return MarketData(
        symbol=symbol,
        timeframe="1d",
        closes=closes,
        opens=scan_item.get("opens", []),
        highs=scan_item.get("highs", []),
        lows=scan_item.get("lows", []),
        volumes=scan_item.get("volumes", []),
        extra=indicators,
    )
