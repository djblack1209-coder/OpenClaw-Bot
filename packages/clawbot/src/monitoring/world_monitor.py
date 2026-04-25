"""
WorldMonitor 全球情报模块 — 搬运自 worldmonitor (koala73/worldmonitor)

核心功能：
1. 新闻聚合 — RSS 多源抓取 + AI 摘要
2. 国家风险指数 (CII) — 12 维度复合风险评分
3. 金融雷达 — 股市、加密货币、大宗商品实时追踪

数据流: RSS/API 拉取 → Redis 缓存 → FastAPI 端点 → 前端展示
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx
import yfinance as yf

from src.utils import scrub_secrets

logger = logging.getLogger(__name__)


# ============================================================
# 1. RSS 新闻聚合
# ============================================================

class NewsCategory(str, Enum):
    """新闻分类 — 参考 worldmonitor 15 大分类"""
    GEOPOLITICS = "geopolitics"
    FINANCE = "finance"
    TECHNOLOGY = "technology"
    MILITARY = "military"
    ENERGY = "energy"
    CLIMATE = "climate"
    CYBER = "cyber"
    TRADE = "trade"
    CRYPTO = "crypto"
    HEALTH = "health"
    INFRASTRUCTURE = "infrastructure"
    CONFLICT = "conflict"
    CHINA = "china"
    COMMODITIES = "commodities"
    GENERAL = "general"


@dataclass
class NewsItem:
    """单条新闻"""
    title: str
    url: str
    source: str
    category: NewsCategory
    published_at: datetime
    summary: str = ""
    thumbnail: str = ""
    threat_level: str = "low"  # low / medium / high / critical
    sentiment: float = 0.0    # -1.0 到 1.0


@dataclass
class RSSFeed:
    """RSS 源定义"""
    name: str
    url: str
    category: NewsCategory
    language: str = "zh"
    priority: int = 1  # 1=高优, 2=中, 3=低


# 内置 RSS 源列表 — 精选中文 + 英文源
DEFAULT_FEEDS: list[RSSFeed] = [
    # 中文财经（原站 RSS 已失效，使用 Google News RSS 代理）
    RSSFeed("华尔街见闻", "https://news.google.com/rss/search?q=site:wallstreetcn.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", NewsCategory.FINANCE, "zh", 1),
    RSSFeed("36氪", "https://36kr.com/feed", NewsCategory.TECHNOLOGY, "zh", 1),
    RSSFeed("财联社", "https://news.google.com/rss/search?q=site:cls.cn&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", NewsCategory.FINANCE, "zh", 1),
    # 中文科技/综合
    RSSFeed("澎湃新闻", "https://feedx.net/rss/thepaper.xml", NewsCategory.GEOPOLITICS, "zh", 1),
    RSSFeed("界面新闻", "https://feedx.net/rss/jiemian.xml", NewsCategory.FINANCE, "zh", 1),
    RSSFeed("知乎热榜", "https://www.zhihu.com/rss", NewsCategory.TECHNOLOGY, "zh", 2),
    # 英文综合
    RSSFeed("Reuters World", "https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en", NewsCategory.GEOPOLITICS, "en", 1),
    RSSFeed("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", NewsCategory.GEOPOLITICS, "en", 1),
    RSSFeed("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", NewsCategory.GEOPOLITICS, "en", 1),
    # 科技
    RSSFeed("TechCrunch", "https://techcrunch.com/feed/", NewsCategory.TECHNOLOGY, "en", 2),
    RSSFeed("Hacker News", "https://hnrss.org/frontpage", NewsCategory.TECHNOLOGY, "en", 2),
    RSSFeed("The Verge", "https://www.theverge.com/rss/index.xml", NewsCategory.TECHNOLOGY, "en", 2),
    # 加密货币
    RSSFeed("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", NewsCategory.CRYPTO, "en", 1),
    RSSFeed("The Block", "https://www.theblock.co/rss.xml", NewsCategory.CRYPTO, "en", 2),
    # 军事/安全
    RSSFeed("Defense One", "https://www.defenseone.com/rss/all/", NewsCategory.MILITARY, "en", 2),
    RSSFeed("CSIS", "https://news.google.com/rss/search?q=site:csis.org&hl=en-US&gl=US&ceid=US:en", NewsCategory.GEOPOLITICS, "en", 2),
    # 能源/大宗
    RSSFeed("OilPrice", "https://oilprice.com/rss/main", NewsCategory.ENERGY, "en", 2),
    # 中国相关
    RSSFeed("SCMP", "https://www.scmp.com/rss/4/feed", NewsCategory.CHINA, "en", 1),
    RSSFeed("Caixin", "https://news.google.com/rss/search?q=site:caixin.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", NewsCategory.CHINA, "en", 2),
]


class NewsFetcher:
    """新闻聚合引擎 — RSS 多源并发抓取 + AI 摘要补全 + 去重"""

    # AI 摘要的系统提示词
    _SUMMARY_SYSTEM_PROMPT = (
        "你是新闻摘要助手。用一句简洁的中文概括以下新闻标题的内容，不超过50字。"
    )

    def __init__(
        self,
        feeds: list[RSSFeed] | None = None,
        max_items_per_feed: int = 20,
        fetch_timeout: float = 15.0,
    ):
        self.feeds = feeds or DEFAULT_FEEDS
        self.max_items_per_feed = max_items_per_feed
        self.fetch_timeout = fetch_timeout
        self._seen_urls: set[str] = set()
        self._cache: dict[str, list[NewsItem]] = {}
        self._cache_time: float = 0
        self._cache_ttl: float = 300  # 5 分钟缓存

    async def fetch_all(self, categories: list[NewsCategory] | None = None) -> list[NewsItem]:
        """并发抓取所有 RSS 源，返回去重后的新闻列表"""
        # 缓存命中
        now = time.time()
        if now - self._cache_time < self._cache_ttl and self._cache:
            all_items = []
            for items in self._cache.values():
                all_items.extend(items)
            if categories:
                all_items = [i for i in all_items if i.category in categories]
            return sorted(all_items, key=lambda x: x.published_at, reverse=True)

        # 筛选需要抓取的源
        target_feeds = self.feeds
        if categories:
            target_feeds = [f for f in self.feeds if f.category in categories]

        # 并发抓取
        results: list[NewsItem] = []
        async with httpx.AsyncClient(timeout=self.fetch_timeout, follow_redirects=True) as client:
            tasks = [self._fetch_feed(client, feed) for feed in target_feeds]
            feed_results = await asyncio.gather(*tasks, return_exceptions=True)

            for feed, result in zip(target_feeds, feed_results):
                if isinstance(result, Exception):
                    logger.warning(f"[WorldMonitor] RSS 抓取失败: {feed.name} — {result}")
                    continue
                for item in result:
                    # 用 URL 哈希去重
                    url_hash = hashlib.md5(item.url.encode()).hexdigest()
                    if url_hash not in self._seen_urls:
                        self._seen_urls.add(url_hash)
                        results.append(item)

        # AI 摘要补全 — 对缺少摘要的新闻调用 LLM 生成中文概括
        results = await self._enrich_summaries(results)

        # 更新缓存
        self._cache.clear()
        for item in results:
            self._cache.setdefault(item.category, []).append(item)
        self._cache_time = now

        return sorted(results, key=lambda x: x.published_at, reverse=True)

    async def _enrich_summaries(self, items: list[NewsItem]) -> list[NewsItem]:
        """为缺少摘要的新闻条目生成 AI 中文摘要

        使用 free_pool (LiteLLM Router) 批量调用 LLM，每批最多 10 条，
        超时 10 秒。任何失败都静默跳过，不影响新闻正常返回。
        """
        # 筛选需要补全摘要的条目（有标题但无摘要）
        need_summary: list[tuple[int, NewsItem]] = [
            (idx, item) for idx, item in enumerate(items)
            if not item.summary and item.title
        ]
        if not need_summary:
            return items

        # 延迟导入，避免循环依赖或模块未初始化时炸掉
        try:
            from src.litellm_router import free_pool
        except Exception:
            logger.debug("[WorldMonitor] litellm_router 不可用，跳过 AI 摘要补全")
            return items

        if not free_pool or not getattr(free_pool, "_router", None):
            logger.debug("[WorldMonitor] free_pool 未初始化，跳过 AI 摘要补全")
            return items

        # 分批处理，每批最多 10 条
        batch_size = 10
        for batch_start in range(0, len(need_summary), batch_size):
            batch = need_summary[batch_start: batch_start + batch_size]

            async def _generate_one(idx: int, item: NewsItem) -> tuple[int, str]:
                """为单条新闻生成摘要，返回 (索引, 摘要文本)"""
                try:
                    resp = await free_pool.acompletion(
                        model_family=None,  # 自动路由选择最优模型
                        messages=[{"role": "user", "content": item.title}],
                        system_prompt=self._SUMMARY_SYSTEM_PROMPT,
                        temperature=0.3,
                        max_tokens=100,
                        cache_ttl=3600,  # 相同标题命中缓存
                    )
                    text = resp.choices[0].message.content.strip()
                    return (idx, text)
                except Exception as e:
                    logger.warning(f"[WorldMonitor] AI 摘要生成失败: {item.title[:30]}… — {scrub_secrets(str(e))}")
                    return (idx, "")

            try:
                # 批量并发调用，整批 10 秒超时
                coros = [_generate_one(idx, item) for idx, item in batch]
                batch_results = await asyncio.wait_for(
                    asyncio.gather(*coros, return_exceptions=True),
                    timeout=10.0,
                )
                # 回填摘要
                for result in batch_results:
                    if isinstance(result, Exception):
                        continue
                    idx, summary_text = result
                    if summary_text:
                        items[idx].summary = summary_text
            except TimeoutError:
                logger.warning(
                    f"[WorldMonitor] AI 摘要批次超时 (batch_start={batch_start}), 跳过剩余"
                )
                break
            except Exception as e:
                logger.warning(f"[WorldMonitor] AI 摘要批次异常: {scrub_secrets(str(e))}")
                continue

        return items

    async def _fetch_feed(self, client: httpx.AsyncClient, feed: RSSFeed) -> list[NewsItem]:
        """抓取单个 RSS 源并解析"""
        try:
            resp = await client.get(feed.url, headers={
                "User-Agent": "OpenClaw-WorldMonitor/2.0",
                "Accept": "application/rss+xml, application/xml, text/xml",
            })
            resp.raise_for_status()
            return self._parse_rss(resp.text, feed)
        except Exception as e:
            logger.debug(f"[WorldMonitor] {feed.name} 抓取异常: {e}")
            raise

    def _parse_rss(self, xml_text: str, feed: RSSFeed) -> list[NewsItem]:
        """解析 RSS XML — 轻量实现，不依赖 feedparser"""
        import xml.etree.ElementTree as ET

        items: list[NewsItem] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return items

        # 支持 RSS 2.0 和 Atom 格式
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for entry in entries[: self.max_items_per_feed]:
            # RSS 2.0 格式
            title_el = entry.find("title")
            link_el = entry.find("link")
            pub_el = entry.find("pubDate")
            desc_el = entry.find("description")

            # Atom 格式
            if title_el is None:
                title_el = entry.find("atom:title", ns)
            if link_el is None:
                link_el = entry.find("atom:link", ns)

            title_raw = (title_el.text or "").strip() if title_el is not None else ""
            import html as html_mod
            title = html_mod.unescape(title_raw)
            if not title:
                continue

            # 链接处理
            url = ""
            if link_el is not None:
                url = link_el.text or link_el.get("href", "") or ""
            url = url.strip()

            # 发布时间
            published_at = datetime.now(UTC)
            if pub_el is not None and pub_el.text:
                try:
                    from email.utils import parsedate_to_datetime
                    published_at = parsedate_to_datetime(pub_el.text)
                except Exception as e:
                    logger.debug("值解析失败: %s", e)

            # 从 RSS description 或 Atom summary/content 提取摘要
            summary = ""
            if desc_el is None or not desc_el.text:
                # Atom 格式: 尝试 <summary> 和 <content>
                atom_ns = "http://www.w3.org/2005/Atom"
                for atom_tag in ["summary", "content"]:
                    desc_el = entry.find(atom_tag)
                    if desc_el is None:
                        desc_el = entry.find(f"{{{atom_ns}}}{atom_tag}")
                    if desc_el is not None and desc_el.text:
                        break
            if desc_el is not None and desc_el.text:
                # 去除 HTML 标签 + 解码 HTML 实体（如 &#039; → '）
                import html as html_mod
                import re
                summary = html_mod.unescape(re.sub(r"<[^>]+>", "", desc_el.text)).strip()[:200]

            items.append(NewsItem(
                title=title,
                url=url,
                source=feed.name,
                category=feed.category,
                published_at=published_at,
                summary=summary,
            ))

        return items


# ============================================================
# 2. 国家风险指数 (Country Intelligence Index)
# ============================================================

class RiskSeverity(str, Enum):
    """风险等级"""
    LOW = "low"           # 0-29
    MODERATE = "moderate"  # 30-49
    ELEVATED = "elevated"  # 50-69
    HIGH = "high"         # 70-84
    CRITICAL = "critical"  # 85-100


@dataclass
class CountryRisk:
    """单个国家的风险评分"""
    country_code: str      # ISO 3166-1 alpha-2
    country_name: str
    composite_score: float  # 0-100 综合评分
    severity: RiskSeverity
    # 子维度评分
    unrest_score: float = 0.0      # 社会动荡
    conflict_score: float = 0.0    # 武装冲突
    economic_score: float = 0.0    # 经济风险
    cyber_score: float = 0.0       # 网络威胁
    climate_score: float = 0.0     # 气候风险
    # 变化趋势
    change_24h: float = 0.0        # 24h 变化
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# 国家基线风险 — 参考 worldmonitor BASELINE_RISK
COUNTRY_BASELINES: dict[str, tuple[str, float]] = {
    "US": ("美国", 5),
    "CN": ("中国", 12),
    "RU": ("俄罗斯", 35),
    "UA": ("乌克兰", 50),
    "IL": ("以色列", 40),
    "PS": ("巴勒斯坦", 55),
    "IR": ("伊朗", 38),
    "KP": ("朝鲜", 42),
    "TW": ("中国台湾", 18),
    "JP": ("日本", 4),
    "KR": ("韩国", 8),
    "IN": ("印度", 15),
    "PK": ("巴基斯坦", 28),
    "SA": ("沙特", 20),
    "TR": ("土耳其", 22),
    "DE": ("德国", 3),
    "FR": ("法国", 5),
    "GB": ("英国", 4),
    "BR": ("巴西", 12),
    "MX": ("墨西哥", 18),
    "NG": ("尼日利亚", 30),
    "EG": ("埃及", 22),
    "TH": ("泰国", 10),
    "VN": ("越南", 8),
    "PH": ("菲律宾", 15),
    "MM": ("缅甸", 45),
    "AF": ("阿富汗", 55),
    "SY": ("叙利亚", 52),
    "YE": ("也门", 50),
    "SD": ("苏丹", 48),
}


class RiskScorer:
    """国家风险指数计算器 — 简化版 worldmonitor CII 算法

    综合评分 = 基线 * 0.4 + 事件分 * 0.6 + 附加分
    事件分 = 动荡 * 0.25 + 冲突 * 0.30 + 安全 * 0.20 + 信息 * 0.25
    """

    def __init__(self):
        self._cache: dict[str, CountryRisk] = {}
        self._cache_time: float = 0
        self._cache_ttl: float = 600  # 10 分钟缓存

    def compute_all(self) -> list[CountryRisk]:
        """计算所有国家的风险评分"""
        now = time.time()
        if now - self._cache_time < self._cache_ttl and self._cache:
            return list(self._cache.values())

        results = []
        for code, (name, baseline) in COUNTRY_BASELINES.items():
            risk = self._compute_country(code, name, baseline)
            results.append(risk)
            self._cache[code] = risk

        self._cache_time = now
        return sorted(results, key=lambda x: x.composite_score, reverse=True)

    def _compute_country(self, code: str, name: str, baseline: float) -> CountryRisk:
        """计算单个国家的综合评分"""
        # 当前简化实现：基于基线 + 随机波动模拟实时事件
        # 后续接入真实 ACLED/GDELT/USGS 等数据源
        import random
        random.seed(hash(code + str(int(time.time() / 3600))))  # 每小时变化一次

        # 子维度评分 — 基于基线的波动
        unrest = min(100, max(0, baseline * 1.2 + random.gauss(0, 5)))
        conflict = min(100, max(0, baseline * 1.5 + random.gauss(0, 8)))
        economic = min(100, max(0, baseline * 0.8 + random.gauss(0, 4)))
        cyber = min(100, max(0, baseline * 0.5 + random.gauss(0, 3)))
        climate = min(100, max(0, 10 + random.gauss(0, 5)))

        # 事件综合分
        event_score = (
            unrest * 0.25
            + conflict * 0.30
            + cyber * 0.20
            + economic * 0.25
        )

        # 综合分 = 基线 * 0.4 + 事件分 * 0.6
        composite = min(100, max(0, baseline * 0.4 + event_score * 0.6 + climate * 0.05))

        # 风险等级
        if composite >= 85:
            severity = RiskSeverity.CRITICAL
        elif composite >= 70:
            severity = RiskSeverity.HIGH
        elif composite >= 50:
            severity = RiskSeverity.ELEVATED
        elif composite >= 30:
            severity = RiskSeverity.MODERATE
        else:
            severity = RiskSeverity.LOW

        return CountryRisk(
            country_code=code,
            country_name=name,
            composite_score=round(composite, 1),
            severity=severity,
            unrest_score=round(unrest, 1),
            conflict_score=round(conflict, 1),
            economic_score=round(economic, 1),
            cyber_score=round(cyber, 1),
            climate_score=round(climate, 1),
            change_24h=round(random.gauss(0, 3), 1),
        )

    def get_global_risk(self) -> dict[str, Any]:
        """全球综合风险评分 — 取 Top-5 国家加权平均"""
        risks = self.compute_all()
        top5 = risks[:5]
        weights = [1.0, 0.85, 0.70, 0.55, 0.40]

        weighted_sum = sum(
            risk.composite_score * w
            for risk, w in zip(top5, weights)
        )
        total_weight = sum(weights[:len(top5)])
        global_score = weighted_sum / total_weight if total_weight > 0 else 0

        if global_score >= 70:
            severity = "HIGH"
        elif global_score >= 40:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        return {
            "global_score": round(global_score, 1),
            "severity": severity,
            "top_risks": [
                {
                    "country": r.country_name,
                    "code": r.country_code,
                    "score": r.composite_score,
                    "severity": r.severity.value,
                    "change_24h": r.change_24h,
                }
                for r in top5
            ],
            "total_countries": len(risks),
            "updated_at": datetime.now(UTC).isoformat(),
        }


# ============================================================
# 3. 金融雷达
# ============================================================

@dataclass
class MarketQuote:
    """市场报价"""
    symbol: str
    name: str
    price: float
    change_pct: float    # 涨跌幅 %
    volume: float = 0
    market_cap: float = 0
    category: str = "stock"  # stock / crypto / commodity / forex
    exchange: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class FinanceRadar:
    """金融雷达 — 全球市场实时追踪

    追踪资产类别:
    - 主要股指 (S&P 500, NASDAQ, 沪深300, 恒生, 日经等)
    - 加密货币 (BTC, ETH, SOL 等 Top 20)
    - 大宗商品 (黄金, 原油, 白银, 铜等)
    - 外汇 (DXY, EUR/USD, USD/CNY 等)
    """

    def __init__(self):
        self._cache: dict[str, list[MarketQuote]] = {}
        self._cache_time: float = 0
        self._cache_ttl: float = 60  # 1 分钟缓存

    async def get_indices(self) -> list[MarketQuote]:
        """获取主要股指报价"""
        # 核心指数列表
        symbols = {
            "^GSPC": ("S&P 500", "NYSE"),
            "^IXIC": ("NASDAQ", "NASDAQ"),
            "^DJI": ("道琼斯", "NYSE"),
            "000300.SS": ("沪深300", "SSE"),
            "^HSI": ("恒生指数", "HKEX"),
            "^N225": ("日经225", "TSE"),
            "^FTSE": ("富时100", "LSE"),
            "^GDAXI": ("德国DAX", "XETRA"),
            "^FCHI": ("法国CAC40", "EPA"),
        }
        return await self._fetch_yahoo_quotes(symbols, "index")

    async def get_crypto(self) -> list[MarketQuote]:
        """获取加密货币报价 — 通过 CoinGecko 公开 API"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.coingecko.com/api/v3/coins/markets",
                    params={
                        "vs_currency": "usd",
                        "order": "market_cap_desc",
                        "per_page": 20,
                        "page": 1,
                        "sparkline": "false",
                    },
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()

                return [
                    MarketQuote(
                        symbol=coin["symbol"].upper(),
                        name=coin["name"],
                        price=coin.get("current_price", 0) or 0,
                        change_pct=coin.get("price_change_percentage_24h", 0) or 0,
                        volume=coin.get("total_volume", 0) or 0,
                        market_cap=coin.get("market_cap", 0) or 0,
                        category="crypto",
                        exchange="Global",
                    )
                    for coin in data
                ]
        except Exception as e:
            logger.warning(f"[WorldMonitor] CoinGecko 请求失败: {scrub_secrets(str(e))}")
            return []

    async def get_commodities(self) -> list[MarketQuote]:
        """获取大宗商品报价"""
        symbols = {
            "GC=F": ("黄金", "COMEX"),
            "SI=F": ("白银", "COMEX"),
            "CL=F": ("WTI 原油", "NYMEX"),
            "BZ=F": ("布伦特原油", "ICE"),
            "HG=F": ("铜", "COMEX"),
            "NG=F": ("天然气", "NYMEX"),
            "ZC=F": ("玉米", "CBOT"),
            "ZS=F": ("大豆", "CBOT"),
        }
        return await self._fetch_yahoo_quotes(symbols, "commodity")

    async def get_forex(self) -> list[MarketQuote]:
        """获取外汇报价"""
        symbols = {
            "DX-Y.NYB": ("美元指数 DXY", "ICE"),
            "EURUSD=X": ("EUR/USD", "FX"),
            "USDJPY=X": ("USD/JPY", "FX"),
            "GBPUSD=X": ("GBP/USD", "FX"),
            "USDCNY=X": ("USD/CNY", "FX"),
            "USDCNH=X": ("USD/CNH", "FX"),
        }
        return await self._fetch_yahoo_quotes(symbols, "forex")

    async def get_all(self) -> dict[str, list[dict]]:
        """获取全部市场数据"""
        now = time.time()
        if now - self._cache_time < self._cache_ttl and self._cache:
            return {
                k: [self._quote_to_dict(q) for q in v]
                for k, v in self._cache.items()
            }

        indices, crypto, commodities, forex = await asyncio.gather(
            self.get_indices(),
            self.get_crypto(),
            self.get_commodities(),
            self.get_forex(),
            return_exceptions=True,
        )

        result: dict[str, list[MarketQuote]] = {
            "indices": indices if isinstance(indices, list) else [],
            "crypto": crypto if isinstance(crypto, list) else [],
            "commodities": commodities if isinstance(commodities, list) else [],
            "forex": forex if isinstance(forex, list) else [],
        }

        self._cache = result
        self._cache_time = now

        return {
            k: [self._quote_to_dict(q) for q in v]
            for k, v in result.items()
        }

    async def _fetch_yahoo_quotes(
        self,
        symbols: dict[str, tuple[str, str]],
        category: str,
    ) -> list[MarketQuote]:
        """通过 yfinance 库获取报价（替代已废弃的 v8 Spark API）"""
        symbol_list = list(symbols.keys())

        def _sync_fetch() -> dict[str, dict]:
            """在线程中同步调用 yfinance，避免阻塞事件循环"""
            result: dict[str, dict] = {}
            try:
                tickers = yf.Tickers(" ".join(symbol_list))
                for sym in symbol_list:
                    try:
                        ticker = tickers.tickers.get(sym)
                        if ticker is None:
                            continue
                        # fast_info 是属性对象，必须用 getattr 而非 dict.get
                        fi = ticker.fast_info
                        price = float(getattr(fi, "last_price", 0) or 0)
                        # 兜底: last_price 为 0 时尝试 previous_close
                        if not price:
                            price = float(getattr(fi, "previous_close", 0) or 0)
                        prev_close = float(getattr(fi, "previous_close", 0) or 0)
                        change_pct = (
                            ((price - prev_close) / prev_close * 100)
                            if prev_close
                            else 0
                        )
                        result[sym] = {
                            "price": round(price, 2),
                            "change_pct": round(change_pct, 2),
                        }
                    except Exception as e:
                        logger.debug(f"[WorldMonitor] yfinance 获取 {sym} 失败: {e}")
            except Exception as e:
                logger.warning(f"[WorldMonitor] yfinance 批量请求失败: {scrub_secrets(str(e))}")
            return result

        try:
            # 在线程池中运行同步的 yfinance 调用，设置 15 秒超时
            loop = asyncio.get_running_loop()
            fetched = await asyncio.wait_for(
                loop.run_in_executor(None, _sync_fetch),
                timeout=15,
            )

            quotes: list[MarketQuote] = []
            for sym, (name, exchange) in symbols.items():
                info = fetched.get(sym)
                if info and info["price"] > 0:
                    quotes.append(MarketQuote(
                        symbol=sym,
                        name=name,
                        price=info["price"],
                        change_pct=info["change_pct"],
                        category=category,
                        exchange=exchange,
                    ))
                else:
                    # 无数据时返回占位
                    quotes.append(MarketQuote(
                        symbol=sym,
                        name=name,
                        price=0,
                        change_pct=0,
                        category=category,
                        exchange=exchange,
                    ))

            return quotes
        except TimeoutError:
            logger.warning("[WorldMonitor] yfinance 请求超时 (15s)")
            return [
                MarketQuote(
                    symbol=sym, name=name, price=0, change_pct=0,
                    category=category, exchange=exchange,
                )
                for sym, (name, exchange) in symbols.items()
            ]
        except Exception as e:
            logger.warning(f"[WorldMonitor] yfinance 请求失败: {scrub_secrets(str(e))}")
            # 返回空占位
            return [
                MarketQuote(
                    symbol=sym, name=name, price=0, change_pct=0,
                    category=category, exchange=exchange,
                )
                for sym, (name, exchange) in symbols.items()
            ]

    @staticmethod
    def _quote_to_dict(q: MarketQuote) -> dict:
        return {
            "symbol": q.symbol,
            "name": q.name,
            "price": q.price,
            "change_pct": q.change_pct,
            "volume": q.volume,
            "market_cap": q.market_cap,
            "category": q.category,
            "exchange": q.exchange,
        }


# ============================================================
# 4. 全局单例
# ============================================================

_news_fetcher: NewsFetcher | None = None
_risk_scorer: RiskScorer | None = None
_finance_radar: FinanceRadar | None = None


def get_news_fetcher() -> NewsFetcher:
    """获取新闻聚合器单例"""
    global _news_fetcher
    if _news_fetcher is None:
        _news_fetcher = NewsFetcher()
    return _news_fetcher


def get_risk_scorer() -> RiskScorer:
    """获取风险评分器单例"""
    global _risk_scorer
    if _risk_scorer is None:
        _risk_scorer = RiskScorer()
    return _risk_scorer


def get_finance_radar() -> FinanceRadar:
    """获取金融雷达单例"""
    global _finance_radar
    if _finance_radar is None:
        _finance_radar = FinanceRadar()
    return _finance_radar
