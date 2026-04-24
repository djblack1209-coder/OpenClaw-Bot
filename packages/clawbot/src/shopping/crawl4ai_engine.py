"""
crawl4ai-powered Shopping Price Engine
搬运 crawl4ai (62.4k⭐) 的结构化网页抽取能力，替代 httpx+bs4 的脆弱爬虫方案。

三级降级链:
  1. crawl4ai JsonCssExtractionStrategy — CSS 选择器结构化抽取（最快、最可靠）
  2. crawl4ai LlmExtractionStrategy  — LLM 从 markdown 中提取（CSS 失败时）
  3. 回退到 brain.py 现有 Jina+LLM 方案 （crawl4ai 完全不可用时）

用法:
    from src.shopping.crawl4ai_engine import smart_compare, HAS_CRAWL4AI
    if HAS_CRAWL4AI:
        result = await smart_compare("iPhone 16 128GB")

Layer 4 (商务层) — OMEGA blueprint gap fill.
"""

import asyncio
import logging
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from typing import Any

from src.utils import scrub_secrets

logger = logging.getLogger(__name__)

# ── crawl4ai 可选导入（graceful degradation）──────────────

HAS_CRAWL4AI = False
AsyncWebCrawler = None
BrowserConfig = None
CrawlerRunConfig = None
CacheMode = None
JsonCssExtractionStrategy = None
LlmExtractionStrategy = None

try:
    from crawl4ai import AsyncWebCrawler as _AsyncWebCrawler
    from crawl4ai import BrowserConfig as _BrowserConfig
    from crawl4ai import CacheMode as _CacheMode
    from crawl4ai import CrawlerRunConfig as _CrawlerRunConfig
    from crawl4ai.extraction_strategy import (
        JsonCssExtractionStrategy as _JsonCssExtractionStrategy,
    )
    from crawl4ai.extraction_strategy import (
        LlmExtractionStrategy as _LlmExtractionStrategy,
    )

    AsyncWebCrawler = _AsyncWebCrawler
    BrowserConfig = _BrowserConfig
    CrawlerRunConfig = _CrawlerRunConfig
    CacheMode = _CacheMode
    JsonCssExtractionStrategy = _JsonCssExtractionStrategy
    LlmExtractionStrategy = _LlmExtractionStrategy
    HAS_CRAWL4AI = True
    logger.info("crawl4ai 已加载 — 结构化比价引擎就绪")
except ImportError:
    logger.info("crawl4ai 未安装 — 将降级到 Jina+LLM 比价方案")
except Exception as e:
    logger.warning(f"crawl4ai 加载异常: {scrub_secrets(str(e))} — 将降级到 Jina+LLM 比价方案")


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class ProductPrice:
    """单个商品价格条目"""

    name: str
    price: float
    platform: str  # "京东" / "淘宝" / "拼多多" / "什么值得买"
    url: str = ""
    shop: str = ""
    original_price: float = 0.0
    coupon: str = ""
    sales: str = ""
    source: str = ""  # 抽取来源标记: "css" / "llm" / "jina"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PriceCompareResult:
    """比价结果汇总"""

    products: list[ProductPrice] = field(default_factory=list)
    best_deal: str = ""
    recommendation: str = ""
    source: str = ""  # "crawl4ai_css" / "crawl4ai_llm" / "jina_llm"
    query: str = ""
    platforms_searched: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "products": [p.to_dict() for p in self.products],
            "best_deal": self.best_deal,
            "recommendation": self.recommendation,
            "source": self.source,
            "query": self.query,
            "platforms_searched": self.platforms_searched,
            "error": self.error,
        }


# ── 平台 CSS 抽取 Schema ────────────────────────────────

# 每个平台的 CSS 选择器配置。crawl4ai 的 JsonCssExtractionStrategy
# 会用这些选择器从 DOM 中结构化提取 JSON 数组。
# 注意: 电商平台频繁改版，选择器需要定期维护。

PLATFORM_SCHEMAS: dict[str, dict[str, Any]] = {
    "jd": {
        "name": "京东商品列表",
        "search_url": "https://search.jd.com/Search?keyword={query}&enc=utf-8",
        "base_selector": ".gl-item, .J_goodsList li, [data-sku]",
        "fields": [
            {
                "name": "name",
                "selector": ".p-name em, .p-name a, .p-name-type-2 a",
                "type": "text",
            },
            {
                "name": "price",
                "selector": ".p-price strong i, .p-price i, .p-price span",
                "type": "text",
            },
            {
                "name": "shop",
                "selector": ".p-shop a, .p-shopnum a, .p-shop span",
                "type": "text",
            },
            {
                "name": "url",
                "selector": ".p-name a, .p-img a",
                "type": "attribute",
                "attribute": "href",
            },
        ],
        "platform_label": "京东",
    },
    "taobao": {
        "name": "淘宝/天猫商品列表",
        # 淘宝搜索需要登录态，公开搜索已无法正常抓取，暂时禁用
        "enabled": False,
        "search_url": "https://s.taobao.com/search?q={query}",
        "base_selector": "[data-item-id], .Card--doubleCard--, .Content--content--",
        "fields": [
            {
                "name": "name",
                "selector": ".Title--title--, .title, [class*='title'] span, a[role='heading']",
                "type": "text",
            },
            {
                "name": "price",
                "selector": ".Price--priceInt--, .priceInt, [class*='price'] span, .price",
                "type": "text",
            },
            {
                "name": "shop",
                "selector": ".ShopInfo--shopName--, .shopName, [class*='shop'] span",
                "type": "text",
            },
            {
                "name": "url",
                "selector": "a[href*='item.taobao'], a[href*='detail.tmall'], a[class*='Card']",
                "type": "attribute",
                "attribute": "href",
            },
        ],
        "platform_label": "淘宝/天猫",
    },
    "pdd": {
        "name": "拼多多商品列表",
        # 拼多多 mobile search page (更稳定)
        "search_url": "https://mobile.yangkeduo.com/search_result.html?search_key={query}",
        "base_selector": "[data-testid='goods-item'], .goods-list-item, [class*='goodsItem']",
        "fields": [
            {
                "name": "name",
                "selector": "[class*='name'], [class*='title'], .goods-name",
                "type": "text",
            },
            {
                "name": "price",
                "selector": "[class*='price'], .goods-price, span[class*='Price']",
                "type": "text",
            },
            {
                "name": "sales",
                "selector": "[class*='sales'], [class*='sold'], .goods-sales",
                "type": "text",
            },
        ],
        "platform_label": "拼多多",
    },
    "smzdm": {
        "name": "什么值得买优惠列表",
        "search_url": "https://search.smzdm.com/?c=faxian&s={query}&order=score",
        "base_selector": ".feed-row-wide, .search-result-item, .list_feed_row",
        "fields": [
            {
                "name": "name",
                "selector": "h5 a, .feed-block-title a, a.feed-nowrap",
                "type": "text",
            },
            {
                "name": "price",
                "selector": ".z-highlight, .feed-block-text-top span, .red-price",
                "type": "text",
            },
            {
                "name": "shop",
                "selector": ".feed-block-extras a, .search-result-mall",
                "type": "text",
            },
            {
                "name": "url",
                "selector": "h5 a, .feed-block-title a, a.feed-nowrap",
                "type": "attribute",
                "attribute": "href",
            },
        ],
        "platform_label": "什么值得买",
    },
}

# 默认搜索的平台列表
DEFAULT_PLATFORMS = ["jd", "smzdm"]


# ── 价格提取工具 ─────────────────────────────────────────

_PRICE_RE = re.compile(r"[\d]+(?:\.[\d]+)?")


def _extract_price(text: str) -> float:
    """从噪声文本（如 '¥5,999.00元' / '59.9' / '价格: 3999'）中提取浮点价格"""
    if not text:
        return 0.0
    cleaned = text.replace(",", "").replace(" ", "").replace("¥", "").replace("￥", "")
    match = _PRICE_RE.search(cleaned)
    if match:
        try:
            val = float(match.group())
            if 0.01 <= val <= 999999:  # 合理价格范围
                return val
        except ValueError as e:
            logger.debug("价格解析失败: %s", e)
    return 0.0


def _normalize_url(href: str, platform: str) -> str:
    """补全不完整的 URL"""
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return f"https:{href}"

    domain_map = {
        "jd": "https://item.jd.com",
        "taobao": "https://item.taobao.com",
        "pdd": "https://mobile.yangkeduo.com",
        "smzdm": "https://www.smzdm.com",
    }
    base = domain_map.get(platform, "")
    if base:
        return f"{base}{href}" if href.startswith("/") else f"{base}/{href}"
    return href


# ── crawl4ai CSS 结构化抽取 ──────────────────────────────


async def _crawl_platform_css(
    platform_key: str,
    query: str,
    limit: int = 8,
) -> list[ProductPrice]:
    """
    用 crawl4ai 的 JsonCssExtractionStrategy 抽取单个平台的商品列表。
    CSS 选择器方式 — 速度最快，不消耗 LLM token。
    """
    if not HAS_CRAWL4AI:
        return []

    schema = PLATFORM_SCHEMAS.get(platform_key)
    if not schema:
        logger.warning(f"未知平台: {platform_key}")
        return []

    url = schema["search_url"].format(query=urllib.parse.quote(query))

    # 构造 crawl4ai CSS 抽取策略
    extraction_schema = {
        "name": schema["name"],
        "baseSelector": schema["base_selector"],
        "fields": schema["fields"],
    }
    strategy = JsonCssExtractionStrategy(extraction_schema, verbose=False)

    browser_cfg = BrowserConfig(
        headless=True,
        verbose=False,
        # 反检测: crawl4ai 内置 stealth 模式
        text_mode=False,
    )

    crawl_cfg = CrawlerRunConfig(
        extraction_strategy=strategy,
        cache_mode=CacheMode.BYPASS,  # 比价场景需要实时数据
        wait_until="domcontentloaded",
        page_timeout=20000,  # 20 秒超时
    )

    results: list[ProductPrice] = []
    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            crawl_result = await crawler.arun(url=url, config=crawl_cfg)

            if not crawl_result.success:
                logger.debug(f"[crawl4ai] {platform_key} 抓取失败: {crawl_result.error_message}")
                return []

            # 解析抽取出的 JSON
            import json

            extracted = crawl_result.extracted_content
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted)
                except (json.JSONDecodeError, TypeError):
                    logger.debug(f"[crawl4ai] {platform_key} 解析 JSON 失败")
                    return []

            if not isinstance(extracted, list):
                return []

            for item in extracted[:limit]:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or "").strip()
                if not name:
                    continue

                price = _extract_price(str(item.get("price", "")))
                raw_url = (item.get("url") or "").strip()

                results.append(
                    ProductPrice(
                        name=name[:120],
                        price=price,
                        platform=schema["platform_label"],
                        url=_normalize_url(raw_url, platform_key),
                        shop=(item.get("shop") or "").strip(),
                        sales=(item.get("sales") or "").strip(),
                        source="css",
                    )
                )

    except TimeoutError:
        logger.warning(f"[crawl4ai] {platform_key} 超时")
    except Exception as e:
        logger.warning(f"[crawl4ai] {platform_key} CSS 抽取异常: {scrub_secrets(str(e))}")

    return results


# ── crawl4ai LLM 抽取（CSS 失败时的降级）───────────────────


async def _crawl_platform_llm(
    platform_key: str,
    query: str,
    limit: int = 6,
) -> list[ProductPrice]:
    """
    用 crawl4ai 的 LlmExtractionStrategy 从网页 markdown 中抽取商品信息。
    消耗 LLM token，但能应对反爬后页面结构变化的场景。
    """
    if not HAS_CRAWL4AI:
        return []

    schema = PLATFORM_SCHEMAS.get(platform_key)
    if not schema:
        return []

    url = schema["search_url"].format(query=urllib.parse.quote(query))

    # 尝试获取 LLM provider 配置
    llm_provider = None
    try:
        import os

        # 优先用 deepseek（便宜）
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if api_key:
            llm_provider = "deepseek/deepseek-chat"
        else:
            # 回退到 openai 兼容
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if api_key:
                llm_provider = "openai/gpt-4o-mini"
    except Exception:
        logger.debug("Silenced exception", exc_info=True)

    if not llm_provider:
        logger.debug("[crawl4ai] 无 LLM API key，跳过 LLM 抽取")
        return []

    strategy = LlmExtractionStrategy(
        provider=llm_provider,
        schema={
            "type": "object",
            "properties": {
                "products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "price": {"type": "number"},
                            "shop": {"type": "string"},
                        },
                        "required": ["name", "price"],
                    },
                },
            },
        },
        instruction=(
            f"从页面内容中提取与'{query}'相关的商品列表，"
            f"每个商品包含 name(商品名)、price(价格数字)、shop(店铺名)。"
            f"只提取前{limit}个最相关的商品。价格只提取数字，不要货币符号。"
        ),
        verbose=False,
    )

    browser_cfg = BrowserConfig(headless=True, verbose=False)
    crawl_cfg = CrawlerRunConfig(
        extraction_strategy=strategy,
        cache_mode=CacheMode.BYPASS,
        page_timeout=25000,
    )

    results: list[ProductPrice] = []
    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            crawl_result = await crawler.arun(url=url, config=crawl_cfg)

            if not crawl_result.success:
                return []

            import json

            extracted = crawl_result.extracted_content
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted)
                except (json.JSONDecodeError, TypeError) as e:  # noqa: F841
                    return []

            # LLM 可能返回 {"products": [...]} 或直接 [...]
            if isinstance(extracted, dict):
                extracted = extracted.get("products", [])
            if not isinstance(extracted, list):
                return []

            for item in extracted[:limit]:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or "").strip()
                if not name:
                    continue
                price = 0.0
                try:
                    price = float(item.get("price", 0))
                except (ValueError, TypeError) as e:  # noqa: F841
                    price = _extract_price(str(item.get("price", "")))

                results.append(
                    ProductPrice(
                        name=name[:120],
                        price=price,
                        platform=schema["platform_label"],
                        url="",  # LLM 抽取通常不含 URL
                        shop=(item.get("shop") or "").strip(),
                        source="llm",
                    )
                )

    except TimeoutError:
        logger.warning(f"[crawl4ai] {platform_key} LLM 抽取超时")
    except Exception as e:
        logger.warning(f"[crawl4ai] {platform_key} LLM 抽取异常: {scrub_secrets(str(e))}")

    return results


# ── 主入口: smart_compare() ────────────────────────────────


async def smart_compare(
    product: str,
    platforms: list[str] | None = None,
    limit_per_platform: int = 6,
) -> PriceCompareResult:
    """
    crawl4ai 驱动的智能比价。

    三级降级链:
      1. CSS 结构化抽取（快、免费、精确）
      2. LLM 抽取（CSS 失败时，消耗 token）
      3. 返回空结果，让调用方降级到 Jina+LLM

    Args:
        product: 商品搜索关键词 (如 "iPhone 16 128GB")
        platforms: 要搜索的平台列表 (如 ["jd", "smzdm"])，None 则用默认
        limit_per_platform: 每个平台最多返回的商品数

    Returns:
        PriceCompareResult — 结构化比价结果
    """
    if not HAS_CRAWL4AI:
        return PriceCompareResult(
            query=product,
            source="unavailable",
            error="crawl4ai 未安装",
        )

    if not product:
        return PriceCompareResult(
            query=product,
            source="error",
            error="未指定商品",
        )

    platforms = platforms or DEFAULT_PLATFORMS
    all_products: list[ProductPrice] = []
    platforms_searched: list[str] = []
    source_method = "crawl4ai_css"

    # ── 第一级: CSS 结构化抽取（并发所有平台）──
    # 跳过 enabled=False 的平台（如淘宝需要登录态，暂不可用）
    css_tasks = {
        p: _crawl_platform_css(p, product, limit_per_platform)
        for p in platforms
        if p in PLATFORM_SCHEMAS and PLATFORM_SCHEMAS[p].get("enabled", True)
    }
    if css_tasks:
        css_results = await asyncio.gather(*css_tasks.values(), return_exceptions=True)
        for platform_key, result in zip(css_tasks.keys(), css_results):
            label = PLATFORM_SCHEMAS[platform_key]["platform_label"]
            if isinstance(result, list) and result:
                all_products.extend(result)
                platforms_searched.append(label)
                logger.info(f"[crawl4ai] {label} CSS 抽取成功: {len(result)} 个商品")
            elif isinstance(result, Exception):
                logger.debug(f"[crawl4ai] {label} CSS 抽取异常: {result}")

    # ── 第二级: CSS 结果不足时，用 LLM 抽取补充 ──
    css_with_price = [p for p in all_products if p.price > 0]
    if len(css_with_price) < 2:
        logger.info("[crawl4ai] CSS 结果不足，启用 LLM 抽取降级")
        source_method = "crawl4ai_llm"

        # 只对 CSS 失败的平台尝试 LLM
        failed_platforms = [
            p
            for p in platforms
            if p in PLATFORM_SCHEMAS and PLATFORM_SCHEMAS[p]["platform_label"] not in platforms_searched
        ]
        # 也对有结果但无价格的平台重试
        no_price_platforms = [
            p
            for p in platforms
            if p in PLATFORM_SCHEMAS
            and PLATFORM_SCHEMAS[p]["platform_label"] in platforms_searched
            and not any(pp.platform == PLATFORM_SCHEMAS[p]["platform_label"] and pp.price > 0 for pp in all_products)
        ]
        retry_platforms = list(set(failed_platforms + no_price_platforms))

        if retry_platforms:
            llm_tasks = {p: _crawl_platform_llm(p, product, limit_per_platform) for p in retry_platforms}
            llm_results = await asyncio.gather(*llm_tasks.values(), return_exceptions=True)
            for platform_key, result in zip(llm_tasks.keys(), llm_results):
                label = PLATFORM_SCHEMAS[platform_key]["platform_label"]
                if isinstance(result, list) and result:
                    all_products.extend(result)
                    if label not in platforms_searched:
                        platforms_searched.append(label)
                    logger.info(f"[crawl4ai] {label} LLM 抽取成功: {len(result)} 个商品")

    # ── 汇总结果 ──
    if not all_products:
        return PriceCompareResult(
            query=product,
            source=source_method,
            platforms_searched=platforms_searched,
            error="所有平台抽取均无结果",
        )

    # 按价格排序（有价格的优先，价格低的在前）
    priced = [p for p in all_products if p.price > 0]
    priced.sort(key=lambda p: p.price)
    unpriced = [p for p in all_products if p.price <= 0]

    # 找到最佳价格
    best_deal = ""
    if priced:
        best = priced[0]
        best_deal = f"{best.name} — ¥{best.price} ({best.platform})"
        if best.shop:
            best_deal += f" [{best.shop}]"

    # 生成推荐文本
    recommendation = _build_recommendation(product, priced)

    return PriceCompareResult(
        products=priced + unpriced,  # 有价格的排前面
        best_deal=best_deal,
        recommendation=recommendation,
        source=source_method,
        query=product,
        platforms_searched=platforms_searched,
    )


def _build_recommendation(product: str, priced: list[ProductPrice]) -> str:
    """根据比价结果生成简洁推荐文本"""
    if not priced:
        return f"未找到 {product} 的有效价格信息，建议直接在各平台搜索对比。"

    lines = [f"🔍 {product} 比价结果 ({len(priced)} 个商品):\n"]

    # 展示前 5 个最低价
    for i, p in enumerate(priced[:5], 1):
        price_str = f"¥{p.price:.0f}" if p.price == int(p.price) else f"¥{p.price:.2f}"
        line = f"  {i}. {p.name[:50]} — {price_str} ({p.platform})"
        if p.shop:
            line += f" [{p.shop}]"
        lines.append(line)

    if len(priced) > 1:
        lowest = priced[0]
        highest = priced[-1]
        if highest.price > 0 and lowest.price > 0:
            diff = highest.price - lowest.price
            pct = (diff / highest.price) * 100
            lines.append(f"\n💰 价差: ¥{diff:.0f} ({pct:.0f}%)")

    lines.append(f"\n✅ 最低价: {priced[0].name[:40]} — ¥{priced[0].price} ({priced[0].platform})")

    # 标注实际可用的搜索平台
    lines.append("\n📌 已搜索平台：京东、什么值得买 | 淘宝/天猫需登录暂不可用")

    return "\n".join(lines)
