"""
AutoTrader 候选筛选与提案生成 Mixin
从 auto_trader.py 拆分，负责候选标的过滤、实时报价刷新、交易提案生成
"""
import asyncio
import logging

from src.models import TradeProposal
from src.utils import env_bool, env_int

logger = logging.getLogger(__name__)


class AutoTraderFiltersMixin:
    """候选筛选与提案生成能力，由 AutoTrader 通过 Mixin 继承"""

    def _filter_candidates(self, signals: list[dict]) -> list[dict]:
        """从扫描结果中筛选候选标的（自适应阈值）

        过滤条件（根据市场环境动态调整）:
        - score >= 15（市场冷清时）或 >= 25（市场火热时）
        - trend 非 strong_down
        - RSI6 <= 85（极端超买才过滤）
        - 价格 > $2（允许更多标的）
        - 20日均量 > 5万（降低流动性门槛）
        - ADX > 12（震荡市也可能有机会）
        """
        candidates = []
        _rejected = {"score": 0, "trend": 0, "rsi": 0, "price": 0, "volume": 0, "adx": 0}

        # 自适应评分阈值：根据信号数量动态调整
        high_score_count = sum(1 for s in signals if s.get("score", 0) >= 40)
        score_threshold = 25 if high_score_count >= 3 else 15

        for s in signals:
            score = s.get("score", 0)
            if score < score_threshold:
                _rejected["score"] += 1
                continue
            trend = s.get("trend", "sideways")
            if trend == "strong_down":
                _rejected["trend"] += 1
                continue
            rsi6 = s.get("rsi_6", 50)
            if rsi6 > 85:
                _rejected["rsi"] += 1
                continue
            price = s.get("price", 0)
            if price > 0 and price < 2:
                logger.debug("[Filter] %s 价格$%.2f < $2，跳过", s.get("symbol"), price)
                _rejected["price"] += 1
                continue
            vol_avg = s.get("vol_avg_20", 0)
            if vol_avg > 0 and vol_avg < 50_000:
                logger.debug("[Filter] %s 20日均量%d < 5万，跳过", s.get("symbol"), vol_avg)
                _rejected["volume"] += 1
                continue
            adx = s.get("adx", 0)
            if adx > 0 and adx < 12:
                logger.debug("[Filter] %s ADX=%.1f < 12 震荡市，跳过", s.get("symbol"), adx)
                _rejected["adx"] += 1
                continue
            candidates.append(s)

        # 统计日志：帮助诊断过滤是否过严
        total = len(signals)
        passed = len(candidates)
        logger.info(
            "[Filter] %d/%d 通过筛选 (阈值score>=%d) | 淘汰: score=%d trend=%d rsi=%d price=%d vol=%d adx=%d",
            passed, total, score_threshold, _rejected["score"], _rejected["trend"],
            _rejected["rsi"], _rejected["price"], _rejected["volume"], _rejected["adx"],
        )

        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        return candidates

    async def _generate_proposal(self, candidate: dict) -> TradeProposal | None:
        """为候选标的生成交易提案"""
        symbol = candidate.get("symbol", "")
        score = candidate.get("score", 0)
        price = candidate.get("price", 0)
        atr_pct = candidate.get("atr_pct", 2.0)

        if price <= 0:
            return None

        atr_mult = max(atr_pct / 100, 0.02)
        stop_loss = round(price * (1 - atr_mult * 1.5), 2)
        take_profit = round(price * (1 + atr_mult * 3), 2)

        quantity = 0
        if self.risk_manager:
            sizing = self.risk_manager.calc_safe_quantity(
                entry_price=price,
                stop_loss=stop_loss,
            )
            if "error" not in sizing:
                quantity = sizing["shares"]

        if quantity <= 0:
            # 根据总资金的20%计算单笔最大成本
            capital = self._get_capital()
            max_cost = capital * 0.20  # 单笔不超过总资金20%
            quantity = max(1, int(max_cost / price))

        reasons = candidate.get("reasons", [])
        reason_text = " | ".join(reasons) if reasons else ("信号评分%d" % score)

        return TradeProposal(
            symbol=symbol,
            action="BUY",
            quantity=quantity,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_score=score,
            confidence=min(abs(score) / 100, 1.0),
            reason=reason_text,
            decided_by="AutoTrader",
            atr=atr_mult * price,
        )

    async def _enrich_candidates_with_broker_quotes(self, candidates: list[dict]) -> None:
        """用 IBKR 实时快照刷新候选现价，减少数据滞后"""
        if not candidates:
            return
        if not env_bool("ENRICH_CANDIDATES_WITH_IBKR_QUOTES", True):
            return
        if not self.pipeline or not self.pipeline.broker:
            return
        broker = self.pipeline.broker
        if not hasattr(broker, "get_realtime_snapshot"):
            return

        limit = min(len(candidates), env_int("IBKR_QUOTE_ENRICH_TOP", 12, minimum=1))
        sem = asyncio.Semaphore(4)

        async def _fetch_and_apply(item: dict):
            symbol = item.get("symbol", "")
            if not symbol:
                return
            async with sem:
                try:
                    snap = await broker.get_realtime_snapshot(symbol)
                    if not isinstance(snap, dict) or "error" in snap:
                        return
                    price = float(snap.get("price", 0) or 0)
                    if price <= 0:
                        return
                    item["price"] = round(price, 2)
                    if "change_pct" in snap:
                        item["change_pct"] = round(float(snap.get("change_pct", 0) or 0), 2)
                except Exception as e:
                    logger.debug("[AutoTrader] 实时报价刷新失败 %s: %s", symbol, e)

        await asyncio.gather(*[_fetch_and_apply(c) for c in candidates[:limit]], return_exceptions=True)
