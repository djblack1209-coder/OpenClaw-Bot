"""
Price Comparison Engine MVP v1.1
搬运 什么值得买 + 京东公开搜索 + AI 分析模式

v1.1 变更 (2026-03-23):
  - 搬运 price-parser (4.2k⭐) 替代手写 regex 价格提取
  - 支持全球货币格式: $19.99 / ¥5,999 / €12,50 / £29.99
  - 自动识别货币符号 + 千分位分隔符
  - price-parser 不可用时降级到原有 regex

Layer 4 (商务层) — OMEGA blueprint gap fill.
No login required: uses only public search pages.

用法:
  from src.shopping.price_engine import compare_prices
  result = await compare_prices("iPhone 16 128GB")
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from src.constants import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

# ── price-parser (4.2k⭐) — 从文本中智能提取价格 ──────────
_HAS_PRICE_PARSER = False
try:
    from price_parser import Price as _PriceParser
    _HAS_PRICE_PARSER = True
    logger.debug("[price_engine] price-parser 已加载")
except ImportError:
    _PriceParser = None  # type: ignore[assignment,misc]
    logger.info("[price_engine] price-parser 未安装，使用 regex 降级 (pip install price-parser)")

# ──────────────────────────────────────────────
#  Data Models
# ──────────────────────────────────────────────


@dataclass
class PriceResult:
    """Single product price entry from any platform."""

    title: str
    price: float
    platform: str       # "京东" / "淘宝" / "拼多多" etc.
    url: str
    shop: str = ""
    historical_low: float = 0.0
    is_deal: bool = False
    source: str = ""     # "smzdm" / "jd" / "taobao" etc.


@dataclass
class ComparisonReport:
    """Aggregated comparison report across platforms."""

    query: str
    results: List[dict] = field(default_factory=list)
    best_deal: Optional[dict] = None
    ai_summary: str = ""
    searched_platforms: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────

_DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_REQUEST_TIMEOUT = 15  # seconds


# ──────────────────────────────────────────────
#  Platform: 什么值得买 (SMZDM)
# ──────────────────────────────────────────────


async def search_smzdm(keyword: str, limit: int = 10) -> List[PriceResult]:
    """Search 什么值得买 for deals — the best Chinese deal aggregator.

    No login required, public search.
    URL pattern: https://search.smzdm.com/?c=faxian&s=关键词&order=score
    """
    results: List[PriceResult] = []
    url = "https://search.smzdm.com/"
    params = {"c": "faxian", "s": keyword, "order": "score"}

    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, params=params, headers=_DEFAULT_HEADERS)
            if resp.status_code != 200:
                logger.debug("SMZDM search returned %d", resp.status_code)
                return results

            soup = BeautifulSoup(resp.text, "html.parser")

            # SMZDM search results use multiple possible CSS selectors
            # depending on page version / A-B testing.
            selectors = ".feed-row-wide, .search-result-item, .list_feed_row"
            for item in soup.select(selectors)[:limit]:
                try:
                    result = _parse_smzdm_item(item)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.debug("SMZDM parse item error: %s", e)
                    continue

    except httpx.TimeoutException as e:
        logger.warning("SMZDM search timed out for '%s'", keyword)
    except Exception as e:
        logger.warning("SMZDM search failed: %s", e)

    return results


def _parse_smzdm_item(item) -> Optional[PriceResult]:
    """Extract a PriceResult from a single SMZDM search result element."""
    # Title
    title_el = item.select_one("h5 a, .feed-block-title a, a.feed-nowrap")
    if not title_el:
        return None
    title = title_el.text.strip()
    if not title:
        return None
    link = title_el.get("href", "")

    # Price — look for highlighted price text
    price_el = item.select_one(
        ".z-highlight, .feed-block-text-top span, .red-price"
    )
    price = _extract_price(price_el.text if price_el else "")

    # Platform / Mall name
    mall_el = item.select_one(".feed-block-extras a, .search-result-mall")
    platform = mall_el.text.strip() if mall_el else "未知平台"

    # Normalize URL
    if link and not link.startswith("http"):
        link = f"https:{link}" if link.startswith("//") else f"https://www.smzdm.com{link}"

    return PriceResult(
        title=title[:100],
        price=price,
        platform=platform,
        url=link,
        is_deal=True,
        source="smzdm",
    )


# ──────────────────────────────────────────────
#  Platform: 京东 (JD.com)
# ──────────────────────────────────────────────


async def search_jd(keyword: str, limit: int = 10) -> List[PriceResult]:
    """Search JD.com for products — public search, no login.

    URL pattern: https://search.jd.com/Search?keyword=xxx&enc=utf-8
    Note: JD may return JS-rendered pages; we parse whatever HTML is available.
    """
    results: List[PriceResult] = []
    url = "https://search.jd.com/Search"
    params = {"keyword": keyword, "enc": "utf-8"}

    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, params=params, headers=_DEFAULT_HEADERS)
            if resp.status_code != 200:
                logger.debug("JD search returned %d", resp.status_code)
                return results

            soup = BeautifulSoup(resp.text, "html.parser")

            for item in soup.select(".gl-item, .J_goodsList li")[:limit]:
                try:
                    result = _parse_jd_item(item)
                    if result:
                        results.append(result)
                except Exception as e:  # noqa: F841
                    continue

    except httpx.TimeoutException as e:
        logger.warning("JD search timed out for '%s'", keyword)
    except Exception as e:
        logger.warning("JD search failed: %s", e)

    return results


def _parse_jd_item(item) -> Optional[PriceResult]:
    """Extract a PriceResult from a single JD search result element."""
    title_el = item.select_one(".p-name em, .p-name a")
    price_el = item.select_one(".p-price strong i, .p-price i")
    link_el = item.select_one(".p-name a")
    shop_el = item.select_one(".p-shop a, .p-shopnum a")

    title = title_el.text.strip() if title_el else ""
    if not title:
        return None

    price = 0.0
    if price_el:
        try:
            price = float(price_el.text.strip())
        except (ValueError, AttributeError) as e:  # noqa: F841
            pass

    if price <= 0:
        return None

    href = link_el.get("href", "") if link_el else ""
    if href and not href.startswith("http"):
        href = f"https:{href}" if href.startswith("//") else f"https://item.jd.com{href}"

    shop = shop_el.text.strip() if shop_el else "京东自营"

    return PriceResult(
        title=title[:100],
        price=price,
        platform="京东",
        url=href,
        shop=shop,
        source="jd",
    )


# ──────────────────────────────────────────────
#  Utility helpers
# ──────────────────────────────────────────────


_PRICE_RE = re.compile(r"[\d]+(?:\.[\d]+)?")


def _extract_price(text: str) -> float:
    """Extract a float price from noisy text like '¥5,999.00元'.

    v1.1: 搬运 price-parser (4.2k⭐) 替代手写 regex。
    支持全球货币: ¥/$/ /€ + 千分位/小数位自动识别。
    不可用时降级到原有 regex 逻辑。
    """
    if not text:
        return 0.0

    # 路径1: price-parser (精准)
    if _HAS_PRICE_PARSER:
        try:
            parsed = _PriceParser.fromstring(text)
            if parsed.amount is not None:
                return float(parsed.amount)
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)

    # 路径2: regex 降级
    cleaned = text.replace(",", "").replace(" ", "")
    match = _PRICE_RE.search(cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError as e:  # noqa: F841
            pass
    return 0.0


def _build_ai_prompt(query: str, priced: List[PriceResult]) -> str:
    """Build AI analysis prompt from comparison results."""
    items_text = "\n".join(
        f"- {r.title}: ¥{r.price} ({r.platform})"
        + (f" [{r.shop}]" if r.shop else "")
        + f" {r.url}"
        for r in priced[:10]
    )
    return (
        f"用户想买: {query}\n\n"
        f"以下是各平台搜索结果（按价格排序）:\n{items_text}\n\n"
        f"请给出简洁的购买建议（3-5行），包括:\n"
        f"1. 哪个最便宜\n"
        f"2. 性价比推荐\n"
        f"3. 购买注意事项（如有）"
    )


async def _generate_ai_summary(query: str, priced: List[PriceResult]) -> str:
    """Generate AI-powered deal analysis summary.

    Uses the project's shared AI pool (LiteLLM router) if available.
    Gracefully returns empty string on failure.
    """
    if not priced:
        return ""

    try:
        from src.execution._ai import ai_pool

        prompt = _build_ai_prompt(query, priced)
        result = await ai_pool.call(prompt)
        if result.get("success"):
            return result.get("raw", "").strip()
    except ImportError:
        logger.debug("AI pool not available — skipping AI summary")
    except Exception as e:
        logger.debug("AI summary failed: %s", e)

    return ""


# ──────────────────────────────────────────────
#  Platform: SMZDM RSS (不会被反爬拦截)
# ──────────────────────────────────────────────


async def search_smzdm_rss(keyword: str, limit: int = 10) -> List[PriceResult]:
    """通过 SMZDM RSS feed 获取优惠信息 — 比 HTML 爬取更可靠。

    RSS 不走搜索页面，不触发反爬机制。
    使用分类 RSS + 关键词过滤。
    """
    results: List[PriceResult] = []
    # SMZDM 各品类 RSS feed
    rss_urls = [
        "https://www.smzdm.com/feed",                    # 全站优惠
        "https://www.smzdm.com/fenlei/shuma/feed",       # 数码
        "https://www.smzdm.com/fenlei/diannaoshebei/feed",  # 电脑
        "https://www.smzdm.com/fenlei/shouji/feed",      # 手机
    ]
    keyword_lower = keyword.lower()

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
            for rss_url in rss_urls:
                if len(results) >= limit:
                    break
                try:
                    resp = await client.get(rss_url, headers={
                        "User-Agent": _DEFAULT_HEADERS["User-Agent"],
                        "Accept": "application/rss+xml, application/xml, text/xml",
                    })
                    if resp.status_code != 200:
                        continue

                    # 简单 XML 解析（不依赖 feedparser）
                    from bs4 import BeautifulSoup as BS
                    soup = BS(resp.text, "html.parser")

                    for item in soup.find_all("item"):
                        title_el = item.find("title")
                        link_el = item.find("link")
                        desc_el = item.find("description")

                        title = title_el.text.strip() if title_el else ""
                        if not title:
                            continue

                        # 关键词匹配
                        if keyword_lower not in title.lower():
                            continue

                        link = ""
                        if link_el:
                            link = link_el.text.strip() if link_el.string else link_el.next_sibling
                            if not isinstance(link, str):
                                link = str(link_el)
                            link = link.strip()

                        # 从标题或描述中提取价格
                        price = _extract_rss_price(title + " " + (desc_el.text if desc_el else ""))

                        results.append(PriceResult(
                            title=title[:120],
                            price=price,
                            platform="什么值得买",
                            url=link if link.startswith("http") else "",
                            is_deal=True,
                            source="smzdm_rss",
                        ))

                        if len(results) >= limit:
                            break
                except Exception as e:
                    logger.debug("[PriceEngine] RSS feed %s error: %s", rss_url, e)
                    continue
    except Exception as e:
        logger.debug("[PriceEngine] SMZDM RSS failed: %s", e)

    return results


def _extract_rss_price(text: str) -> float:
    """从文本中提取价格数字"""
    import re
    patterns = [
        r'(\d+\.?\d*)\s*元',
        r'¥\s*(\d+\.?\d*)',
        r'(\d+\.?\d*)\s*到手',
        r'(\d{2,}\.?\d*)',  # 两位以上数字
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            try:
                val = float(match.group(1))
                if 1 < val < 100000:  # 合理价格范围
                    return val
            except ValueError as e:  # noqa: F841
                continue
    return 0.0


# ──────────────────────────────────────────────
#  Main entry: compare_prices()
# ──────────────────────────────────────────────


async def compare_prices(
    query: str,
    use_ai_summary: bool = True,
    limit_per_platform: int = 5,
) -> ComparisonReport:
    """Search multiple platforms, compare prices, generate report.

    搬运 什么值得买 的比价逻辑 + AI 分析总结模式。

    Args:
        query: Product search keyword (e.g. "iPhone 16 128GB").
        use_ai_summary: Whether to generate AI-powered buying advice.
        limit_per_platform: Max results per platform.

    Returns:
        ComparisonReport with aggregated results, best deal, and AI summary.
    """
    # Search all platforms in parallel (RSS 优先，不被反爬)
    smzdm_rss_results, smzdm_results, jd_results = await asyncio.gather(
        search_smzdm_rss(query, limit=limit_per_platform),
        search_smzdm(query, limit=limit_per_platform),
        search_jd(query, limit=limit_per_platform),
        return_exceptions=True,
    )

    # Flatten results, ignoring exceptions
    all_results: List[PriceResult] = []
    platforms: List[str] = []

    # RSS 优先（最可靠，不被反爬）
    if isinstance(smzdm_rss_results, list) and smzdm_rss_results:
        all_results.extend(smzdm_rss_results)
        if "什么值得买(RSS)" not in platforms:
            platforms.append("什么值得买(RSS)")

    if isinstance(smzdm_results, list) and smzdm_results:
        all_results.extend(smzdm_results)
        if "什么值得买" not in platforms:
            platforms.append("什么值得买")
    elif isinstance(smzdm_results, Exception):
        logger.debug("SMZDM HTML search exception: %s", smzdm_results)

    if isinstance(jd_results, list) and jd_results:
        all_results.extend(jd_results)
        platforms.append("京东")
    elif isinstance(jd_results, Exception):
        logger.debug("JD search exception: %s", jd_results)

    # Sort by price (lowest first, skip zero-price items)
    priced = [r for r in all_results if r.price > 0]
    priced.sort(key=lambda r: r.price)

    best = priced[0] if priced else None

    # AI summary (non-blocking — failure is OK)
    ai_summary = ""
    if use_ai_summary and priced:
        ai_summary = await _generate_ai_summary(query, priced)

    return ComparisonReport(
        query=query,
        results=[asdict(r) for r in all_results],
        best_deal=asdict(best) if best else None,
        ai_summary=ai_summary,
        searched_platforms=platforms,
    )
