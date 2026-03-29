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
import time
from datetime import datetime
from typing import Dict, List, Optional, Set
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
            "profit_celebration": True,
        }
        self._vetoed_symbols: Set[str] = set()  # 被风控否决的标的
        self._social_signals: Dict[str, Dict] = {}  # 社交信号缓存
        self._recent_events: List[Dict] = []
        self._last_news_scan_ts: float = 0.0       # 上次新闻情感扫描时间戳
        self._news_scan_task: Optional[asyncio.Task] = None  # 管道5定时扫描后台任务
        self._stats = {
            "pipelines_triggered": 0,
            "social_drafts_created": 0,
            "trade_scans_triggered": 0,
            "evolution_broadcasts": 0,
            "news_risk_alerts": 0,
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

            # 管道5: 新闻情感 → 投资风险信号（每4小时定时扫描持仓相关新闻）
            if self._pipeline_config["news_sentiment_to_risk"]:
                self._news_scan_task = asyncio.ensure_future(
                    self._news_sentiment_loop()
                )
                logger.info("[协同] 管道5已启动: 新闻情感→风控 (每4小时)")

            # 策略暂停 → 全局通知
            bus.subscribe(
                EventType.STRATEGY_SUSPENDED, self._on_strategy_suspended,
                "synergy:strategy→alert", priority=2,
            )

            # 管道6: 盈利庆祝 — 平仓盈利 > 10% 时自动生成社媒草稿
            if self._pipeline_config["profit_celebration"]:
                bus.subscribe(
                    EventType.TRADE_EXECUTED, self._on_profit_celebration,
                    "synergy:profit→celebration", priority=9,
                )

            logger.info(f"SynergyPipelines 已注册 {sum(self._pipeline_config.values())} 条管道（含盈利庆祝）")

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
        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)

    # ── 管道5: 新闻情感 → 投资风险信号 ──────────────

    async def _news_sentiment_loop(self) -> None:
        """后台循环: 每4小时执行一次新闻情感扫描

        首次延迟90秒启动，避免影响 Bot 主启动流程。
        之后每4小时扫描一次，失败不影响其他管道。
        """
        await asyncio.sleep(90)  # 首次延迟，等 Bot 完全启动
        while self._enabled:
            try:
                await self.run_news_sentiment_scan()
            except Exception as e:
                logger.warning(f"[协同] 新闻情感循环异常: {e}")
            await asyncio.sleep(4 * 3600)  # 每4小时

    async def run_news_sentiment_scan(self) -> int:
        """管道5实装: 扫描最新新闻，对持仓相关标的的负面新闻发出 RISK_ALERT

        流程:
          1. 获取用户当前持仓标的列表（trading_journal.get_open_trades）
          2. 抓取多源最新新闻（RSS 三级降级，不调 LLM）
          3. 对每条新闻做零成本情感分析（snownlp/textblob/词袋）
          4. 匹配新闻标题中的持仓标的（ticker + 公司名双匹配）
          5. 强负面新闻（sentiment < -0.5）→ 发布 RISK_ALERT + 通知用户

        Returns:
            检测到的风险警报数量
        """
        if not self._pipeline_config.get("news_sentiment_to_risk"):
            return 0

        risk_count = 0

        try:
            # 步骤1: 获取用户当前持仓标的
            held_symbols: Set[str] = set()
            try:
                from src.trading_journal import journal as tj
                if tj:
                    open_trades = tj.get_open_trades()
                    for t in open_trades:
                        sym = str(t.get("symbol", "")).upper().strip()
                        if sym:
                            held_symbols.add(sym)
            except Exception as e:
                logger.debug("[协同] 获取持仓失败", exc_info=True)

            if not held_symbols:
                logger.debug("[协同] 新闻情感扫描: 无持仓标的，跳过")
                return 0

            # 步骤2: 构建反向映射 ticker→公司名集合（用于匹配新闻标题）
            ticker_to_names: Dict[str, Set[str]] = {}
            for name, ticker in _NAME_TO_TICKER.items():
                ticker_to_names.setdefault(ticker, set()).add(name.lower())

            # 步骤3: 抓取多源最新新闻（RSS 三级降级，不调 LLM）
            from src.news_fetcher import NewsFetcher
            fetcher = NewsFetcher()
            all_news: List[Dict] = []
            for category in ("finance", "tech_en", "tech_cn"):
                try:
                    items = await fetcher.fetch_by_category(category, count=10)
                    all_news.extend(items)
                except Exception as e:
                    logger.debug(f"抓取 {category} 类别新闻失败: {e}")
                await asyncio.sleep(1)  # 避免请求过快

            if not all_news:
                logger.debug("[协同] 新闻情感扫描: 未获取到新闻")
                return 0

            # 步骤4: 对每条新闻做情感分析 + 持仓匹配
            from src.social_tools import analyze_sentiment

            for item in all_news:
                title = item.get("title", "")
                if not title:
                    continue

                title_lower = title.lower()

                # 匹配持仓标的（ticker 直匹配 + 公司名匹配）
                matched_symbols: Set[str] = set()
                for sym in held_symbols:
                    # 直接 ticker 匹配（如 "NVDA" 出现在标题中）
                    if sym.lower() in title_lower:
                        matched_symbols.add(sym)
                    # 公司名匹配（如 "英伟达"、"nvidia" 出现在标题中）
                    names = ticker_to_names.get(sym, set())
                    for name in names:
                        if name in title_lower:
                            matched_symbols.add(sym)
                            break

                if not matched_symbols:
                    continue

                # 零成本情感分析（snownlp/textblob/词袋，不调 LLM）
                sentiment = analyze_sentiment(title)

                # 步骤5: 强负面新闻触发风险警报
                if sentiment.score < -0.5:
                    for sym in matched_symbols:
                        risk_count += 1

                        # 发布 RISK_ALERT 事件到 EventBus（管道4会自动禁止社媒推荐）
                        try:
                            from src.core.event_bus import get_event_bus, EventType
                            bus = get_event_bus()
                            await bus.publish(
                                EventType.RISK_ALERT,
                                {
                                    "symbol": sym,
                                    "source": "news_sentiment",
                                    "news_title": title[:120],
                                    "sentiment_score": sentiment.score,
                                    "sentiment_label": sentiment.label,
                                    "reason": f"负面新闻情感分数 {sentiment.score:.2f}",
                                },
                                source="synergy:news→risk",
                            )
                        except Exception as e:
                            logger.debug("RISK_ALERT 发布失败", exc_info=True)

                        # 通过通知事件推送给用户
                        try:
                            bus = get_event_bus()
                            alert_msg = (
                                f"⚠️ {sym} 出现负面新闻: "
                                f"'{title[:80]}'\n"
                                f"情感分数: {sentiment.score:.2f} — 建议关注风险"
                            )
                            await bus.publish(
                                "system.notification",
                                {"message": alert_msg, "level": "important"},
                                source="synergy:news→risk",
                            )
                        except Exception as e:
                            logger.debug("风险通知发送失败", exc_info=True)

                        logger.warning(
                            f"[协同] 负面新闻风险: {sym} ← "
                            f"'{title[:60]}' (score={sentiment.score:.2f})"
                        )

            self._stats["pipelines_triggered"] += 1
            self._stats["news_risk_alerts"] += risk_count
            self._last_news_scan_ts = time.time()

            logger.info(
                f"[协同] 新闻情感扫描完成: {len(all_news)}条新闻, "
                f"{risk_count}个风险警报, 持仓标的: {held_symbols}"
            )
            return risk_count

        except Exception as e:
            logger.warning(f"[协同] 新闻情感扫描异常: {e}")
            return 0

    # ── 管道6: 盈利庆祝 → 社媒草稿 ──────────────────

    async def _on_profit_celebration(self, event) -> None:
        """盈利庆祝 — PnL > 10% 时自动生成社媒草稿（模板，不调LLM省成本）"""
        data = event.data
        pnl_pct = data.get("pnl_pct", 0)
        if pnl_pct < 10:
            return  # 小赚不发

        symbol = data.get("symbol", "")
        pnl = data.get("pnl", 0)

        self._stats["pipelines_triggered"] += 1

        try:
            # 生成庆祝内容（简单模板，不调LLM省成本）
            content = (
                f"🎯 {symbol} 止盈平仓 +{pnl_pct:.1f}%\n\n"
                f"这次交易的关键：严格执行止盈纪律，不贪不恋。\n"
                f"收益: ${pnl:+.2f}\n\n"
                f"#投资日记 #交易心得"
            )

            # 存为草稿
            try:
                from src.execution.social.drafts import save_social_draft
                save_social_draft(
                    platform="both", title="", body=content, topic="投资分享",
                )
            except Exception as e:
                logger.debug("[协同] 庆祝帖草稿保存失败: %s", e)

            # 同时写入 synergy 草稿文件（双保险）
            await self._save_social_draft(content, symbol=symbol, source="profit_celebration")
            self._stats["social_drafts_created"] += 1
            logger.info(f"[协同] 盈利庆祝→社媒草稿: {symbol} +{pnl_pct:.1f}%")

        except Exception as e:
            logger.warning(f"[协同] 盈利庆祝管道失败: {e}")

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
            "last_news_scan": datetime.fromtimestamp(self._last_news_scan_ts).isoformat()
                if self._last_news_scan_ts > 0 else "未扫描",
        }

    def get_context_enrichment(self) -> str:
        """供 Brain 注入的跨域信号摘要 — 搬运 omi cross-context awareness 模式

        将投资/社媒/风控等领域的最新信号聚合为一段简短文本，
        让 Brain 在处理任何请求时都能"联想"到其他领域的相关信息。
        """
        parts = []

        # 1. 社交热点信号（可能影响投资决策）
        if self._social_signals:
            fresh = []
            now = time.time()
            for sym, sig in self._social_signals.items():
                if (now - sig.get("timestamp", 0)) < 3600:  # 1小时内
                    sentiment = sig.get("sentiment", "")
                    fresh.append(f"{sym}({sentiment})" if sentiment else sym)
            if fresh:
                parts.append(f"社交热点标的: {', '.join(fresh[:5])}")

        # 2. 风控否决标的（避免推荐已被否决的）
        if self._vetoed_symbols:
            parts.append(f"风控否决标的: {', '.join(list(self._vetoed_symbols)[:5])}")

        # 3. 最近跨域事件（从统计中提取）
        total = self._stats.get("total_events", 0)
        if total > 0:
            parts.append(f"今日跨域事件: {total}条")

        return "\n".join(parts) if parts else ""

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
        except Exception as e:
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
