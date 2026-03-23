"""
Cross-Module Synergy Engine
OpenClaw 跨模块联动系统 — 别人抄不走的核心壁垒

联动链路:
  交易信号 → 社交内容自动生成 (强信号自动转为草稿)
  社交热点 → 交易标的扫描 (话题关联公司自动 TA)
  进化发现 → 能力增强广播 (高价值 Repo 实时通知)

设计原则:
  1. 事件驱动，不是轮询
  2. 每条链路独立，一条断了不影响其他
  3. 所有联动可通过 config 开关
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Company name → ticker mapping ──────────────────────
_NAME_TO_TICKER = {
    "苹果": "AAPL", "apple": "AAPL",
    "特斯拉": "TSLA", "tesla": "TSLA",
    "英伟达": "NVDA", "nvidia": "NVDA",
    "微软": "MSFT", "microsoft": "MSFT",
    "谷歌": "GOOGL", "google": "GOOGL",
    "亚马逊": "AMZN", "amazon": "AMZN",
    "meta": "META", "脸书": "META",
    "比特币": "BTC-USD", "bitcoin": "BTC-USD",
    "以太坊": "ETH-USD", "ethereum": "ETH-USD",
    "台积电": "TSM", "tsmc": "TSM",
    "腾讯": "0700.HK", "阿里": "BABA",
    "字节": "BDNCE", "bytedance": "BDNCE",
}


class SynergyEngine:
    """跨模块联动协调器 — OpenClaw 的复合效应引擎"""

    def __init__(self):
        self._enabled = True
        self._chains = {
            "trading_to_social": True,
            "social_to_trading": True,
            "evolution_broadcast": True,
        }
        self._recent: List[str] = []  # dedup buffer

    # ─── Chain 1: Trading Signal → Social Draft ──────────

    async def on_trade_signal(self, signal: dict):
        """强交易信号自动转化为社交草稿供审阅。"""
        if not self._chains.get("trading_to_social"):
            return

        symbol = signal.get("symbol", "")
        direction = signal.get("signal", "")
        score = signal.get("score", 0)
        reason = signal.get("reason", "")

        if direction == "HOLD" or abs(score) < 60:
            return

        key = f"{symbol}_{direction}"
        if key in self._recent:
            return
        self._recent.append(key)
        if len(self._recent) > 50:
            self._recent = self._recent[-50:]

        try:
            from src.execution.social.content_strategy import compose_post

            topic = f"{symbol} {'看多' if direction == 'BUY' else '看空'}信号: {reason}"
            result = await compose_post(topic=topic, platform="x", max_length=280)

            if result.get("success"):
                from src.social_scheduler import _load_state, _save_state

                state = _load_state()
                drafts = state.get("drafts", [])
                drafts.append({
                    "text": result["text"],
                    "platform": "x",
                    "status": "auto_generated",
                    "source": "trading_synergy",
                    "created_at": datetime.now().isoformat(),
                    "metadata": {"symbol": symbol, "signal": direction, "score": score},
                })
                state["drafts"] = drafts
                _save_state(state)
                logger.info("[Synergy] 交易→社交: %s %s 草稿已生成", symbol, direction)
                _push("social_published", f"交易信号→社交草稿: {symbol} {direction}")
        except Exception as e:
            logger.debug("[Synergy] 交易→社交异常: %s", e)

    # ─── Chain 2: Social Hotspot → Trading Scan ──────────

    async def on_social_hotspot(self, topics: list):
        """社交热点话题自动关联交易标的并扫描。"""
        if not self._chains.get("social_to_trading"):
            return

        tickers: set = set()
        for t in topics:
            text = (t.get("title", "") + " " + t.get("summary", "")).lower()
            for name, ticker in _NAME_TO_TICKER.items():
                if name in text:
                    tickers.add(ticker)

        if not tickers:
            return

        logger.info("[Synergy] 社交→交易: 关联标的 %s", tickers)

        try:
            from src.ta_engine import get_full_analysis

            for ticker in list(tickers)[:3]:
                try:
                    analysis = await get_full_analysis(ticker, period="1mo")
                    if analysis and not analysis.get("error"):
                        score = analysis.get("signal_score", 0)
                        if abs(score) >= 50:
                            _push("trade_signal", f"热点关联: {ticker} 信号{score}")
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)
        except Exception as e:
            logger.debug("[Synergy] 社交→交易异常: %s", e)

    # ─── Chain 3: Evolution → Broadcast ──────────────────

    async def on_evolution_proposal(self, proposal: dict):
        """高价值进化提案广播通知。"""
        if not self._chains.get("evolution_broadcast"):
            return

        value = proposal.get("value_score", 0)
        if value < 7:
            return

        name = proposal.get("repo_name", "")
        module = proposal.get("target_module", "")
        stars = proposal.get("stars", 0)
        logger.info("[Synergy] 进化广播: %s (%.1f分→%s)", name, value, module)
        _push("status", f"进化发现: {name} ({stars}⭐) → {module}")


# ─── Helper ──────────────────────────────────────────────

def _push(event_type: str, message: str):
    """Best-effort WebSocket push."""
    try:
        from src.api.routers.ws import push_event
        from src.api.schemas import WSMessageType

        type_map = {
            "trade_signal": WSMessageType.TRADE_SIGNAL,
            "social_published": WSMessageType.SOCIAL_PUBLISHED,
            "status": WSMessageType.STATUS,
        }
        push_event(type_map.get(event_type, WSMessageType.STATUS), {
            "message": message,
            "source": "synergy",
            "ts": datetime.now().isoformat(),
        })
    except Exception:
        logger.debug("Silenced exception", exc_info=True)


# ─── Singleton ───────────────────────────────────────────

_synergy = SynergyEngine()


def get_synergy() -> SynergyEngine:
    return _synergy
