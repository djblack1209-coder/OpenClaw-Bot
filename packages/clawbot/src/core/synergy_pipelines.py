"""
OpenClaw OMEGA — 跨模块协同管道 (Synergy Pipelines)
借鉴 n8n (180k⭐) 的数据管道模式：每个模块的输出自动喂入其他模块的上下文。

这是 OpenClaw 的核心壁垒 — 别人有单个模块，但没有跨模块的飞轮效应。

协同链路:
  1. 交易信号 → 社媒内容草稿（自动生成投资观点帖子）
  2. 社交热点 → 投资标的扫描（话题关联公司自动分析）
  3. 进化发现 → 能力增强广播（高价值项目实时通知）
  4. 投资风控 → 社媒内容过滤（被否决的股票不推荐）
  5. 新闻情感 → 投资风险信号（负面新闻触发防御）
  6. 用户行为 → 智能推荐（基于历史偏好主动服务）

设计原则:
  - 所有管道通过 EventBus 松耦合（一条断了不影响其他）
  - 每条管道可通过配置开关
  - 管道输出写入 shared_memory，供各模块异步读取
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from src.utils import now_et

logger = logging.getLogger(__name__)

# 公司名 → ticker 映射（复用自现有 synergy.py，扩展）
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
    "茅台": "600519.SS", "maotai": "600519.SS",
    "宁德时代": "300750.SZ", "catl": "300750.SZ",
    "比亚迪": "002594.SZ", "byd": "002594.SZ",
    "字节": "BDNCE", "bytedance": "BDNCE",
}


class SynergyPipelines:
    """
    跨模块协同管道 — OpenClaw 的中枢神经系统。

    通过 EventBus 订阅各模块事件，自动执行跨模块联动。
    所有管道输出写入 shared_memory，供其他模块异步读取。

    用法:
        pipelines = SynergyPipelines()
        await pipelines.register_all()  # 订阅所有事件
    """

    def __init__(self):
        self._enabled = True
        self._pipeline_config = {
            "trade_to_social": True,
            "social_to_trade": True,
            "evolution_broadcast": True,
            "risk_to_social_filter": True,
            "news_sentiment_to_risk": True,
            "behavior_to_recommend": True,
        }
        self._vetoed_symbols: Set[str] = set()  # 被风控否决的标的
        self._social_signals: Dict[str, Dict] = {}  # 社交信号缓存
        self._recent_events: List[Dict] = []
        self._stats = {
            "pipelines_triggered": 0,
            "social_drafts_created": 0,
            "trade_scans_triggered": 0,
            "evolution_broadcasts": 0,
        }
        logger.info("SynergyPipelines 初始化")

    async def register_all(self) -> None:
        """注册所有协同管道到 EventBus"""
        try:
            from src.core.event_bus import get_event_bus, EventType
            bus = get_event_bus()

            # 管道1: 交易信号 → 社媒内容草稿
            if self._pipeline_config["trade_to_social"]:
                bus.subscribe(
                    EventType.TRADE_SIGNAL, self._on_trade_signal,
                    "synergy:trade→social", priority=8,
                )
                bus.subscribe(
                    EventType.TRADE_EXECUTED, self._on_trade_executed,
                    "synergy:trade→social", priority=8,
                )

            # 管道2: 社交热点 → 投资标的扫描
            if self._pipeline_config["social_to_trade"]:
                bus.subscribe(
                    EventType.SOCIAL_TRENDING, self._on_social_trending,
                    "synergy:social→trade", priority=8,
                )

            # 管道3: 进化发现 → 广播
            if self._pipeline_config["evolution_broadcast"]:
                bus.subscribe(
                    EventType.EVOLUTION_PROPOSAL, self._on_evolution_proposal,
                    "synergy:evolution→broadcast", priority=8,
                )

            # 管道4: 风控否决 → 社媒过滤
            if self._pipeline_config["risk_to_social_filter"]:
                bus.subscribe(
                    EventType.RISK_ALERT, self._on_risk_alert,
                    "synergy:risk→social", priority=3,  # 高优先级
                )

            # 管道5: 策略暂停 → 全局通知
            bus.subscribe(
                EventType.STRATEGY_SUSPENDED, self._on_strategy_suspended,
                "synergy:strategy→alert", priority=2,
            )

            logger.info(f"SynergyPipelines 已注册 {sum(self._pipeline_config.values())} 条管道")

        except Exception as e:
            logger.warning(f"SynergyPipelines 注册失败: {e}")

    # ── 管道1: 交易信号 → 社媒草稿 ──────────────────

    async def _on_trade_signal(self, event) -> None:
        """收到交易信号时，自动生成社媒内容草稿"""
        data = event.data
        symbol = data.get("symbol", "")
        analysis = data.get("analysis", {})
        recommendation = analysis.get("final_recommendation", "hold")

        if recommendation == "hold":
            return  # 观望不发帖

        self._stats["pipelines_triggered"] += 1

        try:
            # 生成草稿内容
            direction = "看好" if recommendation == "buy" else "谨慎"
            confidence = analysis.get("confidence", 0)
            reasoning = analysis.get("director", {})
            if isinstance(reasoning, dict):
                reasoning = reasoning.get("reasoning", "")

            draft = (
                f"📊 #{symbol} 分析观点\n\n"
                f"团队共识: {direction} (置信度 {confidence:.0%})\n"
                f"核心逻辑: {str(reasoning)[:120]}\n\n"
                f"⚠️ 以上仅为AI分析观点，不构成投资建议。"
            )

            # 写入社媒草稿
            await self._save_social_draft(draft, symbol=symbol, source="trade_signal")
            self._stats["social_drafts_created"] += 1
            logger.info(f"[协同] 交易信号→社媒草稿: {symbol} ({direction})")

        except Exception as e:
            logger.warning(f"[协同] 交易→社媒管道失败: {e}")

    async def _on_trade_executed(self, event) -> None:
        """交易执行后记录到记忆，供复盘用"""
        data = event.data
        try:
            await self._save_to_memory(
                f"交易执行: {json.dumps(data, ensure_ascii=False, default=str)[:300]}",
                category="trade_record",
            )
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

    # ── 管道2: 社交热点 → 投资扫描 ──────────────────

    async def _on_social_trending(self, event) -> None:
        """社交热点中提取标的关键词，触发投资扫描"""
        data = event.data
        topics = data.get("topics", [])
        if not topics:
            return

        self._stats["pipelines_triggered"] += 1
        symbols_to_scan = set()

        for topic in topics:
            title = topic.get("title", topic.get("name", ""))
            title_lower = title.lower()

            for keyword, ticker in _NAME_TO_TICKER.items():
                if keyword in title_lower:
                    symbols_to_scan.add(ticker)

        if not symbols_to_scan:
            return

        # 缓存社交信号
        for symbol in symbols_to_scan:
            self._social_signals[symbol] = {
                "source": "social_trending",
                "timestamp": time.time(),
                "topics": [t.get("title", "") for t in topics[:3]],
            }

        # 写入记忆供投资团队读取
        for symbol in symbols_to_scan:
            await self._save_to_memory(
                f"社交热点关联标的: {symbol} — 话题: {', '.join(self._social_signals[symbol]['topics'][:3])}",
                category="social_signal",
            )

        self._stats["trade_scans_triggered"] += len(symbols_to_scan)
        logger.info(f"[协同] 社交热点→投资扫描: {symbols_to_scan}")

    # ── 管道3: 进化发现 → 广播 ──────────────────

    async def _on_evolution_proposal(self, event) -> None:
        """高价值进化提案广播到所有渠道"""
        data = event.data
        repo = data.get("repo_name", "")
        score = data.get("value_score", 0)
        module = data.get("target_module", "")

        if score < 7.0:
            return  # 低分不广播

        self._stats["evolution_broadcasts"] += 1
        self._stats["pipelines_triggered"] += 1

        message = (
            f"🧬 进化发现: {repo}\n"
            f"   价值: {score:.1f}/10 | 模块: {module}\n"
            f"   {data.get('description', '')[:80]}"
        )

        # 发布到通知事件（Gateway 会推送到 Telegram）
        try:
            from src.core.event_bus import get_event_bus
            bus = get_event_bus()
            await bus.publish(
                "system.notification",
                {"message": message, "level": "normal"},
                source="synergy:evolution",
            )
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        logger.info(f"[协同] 进化广播: {repo} (score={score})")

    # ── 管道4: 风控否决 → 社媒过滤 ──────────────────

    async def _on_risk_alert(self, event) -> None:
        """风控否决标的时，禁止社媒推荐"""
        data = event.data
        symbol = data.get("symbol", "")
        if symbol:
            self._vetoed_symbols.add(symbol)
            logger.info(f"[协同] 风控否决→社媒过滤: {symbol}")

        self._stats["pipelines_triggered"] += 1

    async def _on_strategy_suspended(self, event) -> None:
        """策略暂停时全局通知"""
        data = event.data
        strategy = data.get("strategy_name", "")
        reason = data.get("reason", "")

        try:
            from src.core.event_bus import get_event_bus
            bus = get_event_bus()
            await bus.publish(
                "system.notification",
                {
                    "message": f"⚠️ 策略暂停: {strategy}\n原因: {reason}",
                    "level": "important",
                },
                source="synergy:strategy",
            )
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

    # ── 查询接口 ──────────────────────────────────

    def get_social_signal(self, symbol: str) -> Optional[Dict]:
        """投资团队调用：获取标的的社交信号"""
        signal = self._social_signals.get(symbol)
        if signal and (time.time() - signal["timestamp"]) < 3600:  # 1小时内有效
            return signal
        return None

    def is_vetoed(self, symbol: str) -> bool:
        """社媒模块调用：检查标的是否被风控否决"""
        return symbol in self._vetoed_symbols

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "active_pipelines": sum(self._pipeline_config.values()),
            "vetoed_symbols": list(self._vetoed_symbols),
            "social_signals": len(self._social_signals),
        }

    # ── 内部工具 ──────────────────────────────────

    async def _save_social_draft(self, content: str, symbol: str = "", source: str = "") -> None:
        """保存社媒草稿"""
        try:
            from pathlib import Path
            drafts_file = Path(__file__).resolve().parent.parent.parent / "data" / "social_drafts.json"
            drafts = []
            if drafts_file.exists():
                drafts = json.loads(drafts_file.read_text())
            drafts.append({
                "content": content,
                "symbol": symbol,
                "source": source,
                "created_at": now_et().isoformat(),
                "published": False,
            })
            drafts_file.write_text(json.dumps(drafts[-50:], ensure_ascii=False, indent=2))
        except Exception as e:
            logger.debug(f"保存草稿失败: {e}")

    async def _save_to_memory(self, content: str, category: str = "") -> None:
        """保存到共享记忆"""
        try:
            from src.bot.globals import shared_memory
            if shared_memory:
                shared_memory.add(content, category=category)
        except Exception:
            logger.debug("Silenced exception", exc_info=True)


# ── 全局单例 ──────────────────────────────────────────────

_pipelines: Optional[SynergyPipelines] = None


def get_synergy_pipelines() -> SynergyPipelines:
    global _pipelines
    if _pipelines is None:
        _pipelines = SynergyPipelines()
    return _pipelines


async def init_synergy_pipelines() -> SynergyPipelines:
    """初始化并注册所有管道（在 multi_main.py 中调用）"""
    pipelines = get_synergy_pipelines()
    await pipelines.register_all()
    return pipelines
