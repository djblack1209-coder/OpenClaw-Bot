"""
Price Comparison Engine v2.0
搬运 什么值得买 + 京东公开搜索 + AI 分析模式
v2.0 新增统一比价入口 smart_compare_prices()，合并多级降级链

v2.0 变更 (2026-04-19):
  - 新增 smart_compare_prices() — 统一比价入口，4 级降级链
  - 降级顺序: SMZDM+JD 爬取 → Tavily 搜索 → crawl4ai 结构化 → Jina+LLM
  - fast_mode=True 时只走 SMZDM+JD（用于批量价格监控，不消耗 API 额度）
  - 原 compare_prices() 保持不变，确保向后兼容

v1.1 变更 (2026-03-23):
  - 搬运 price-parser (4.2k⭐) 替代手写 regex 价格提取
  - 支持全球货币格式: $19.99 / ¥5,999 / €12,50 / £29.99
  - 自动识别货币符号 + 千分位分隔符
  - price-parser 不可用时降级到原有 regex

Layer 4 (商务层) — OMEGA blueprint gap fill.
No login required: uses only public search pages.

用法:
  from src.shopping.price_engine import compare_prices          # 原有入口
  from src.shopping.price_engine import smart_compare_prices    # 新统一入口
  result = await smart_compare_prices("iPhone 16 128GB")
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

    except httpx.TimeoutException:
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

    except httpx.TimeoutException:
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
        except (ValueError, AttributeError) as e:
            logger.debug("价格解析失败: %s", e)

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
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

    # 路径2: regex 降级
    cleaned = text.replace(",", "").replace(" ", "")
    match = _PRICE_RE.search(cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError as e:
            logger.debug("价格正则匹配结果转换失败: %s", e)
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


# ──────────────────────────────────────────────
#  统一比价入口: smart_compare_prices()
#  合并 Engine A (brain_exec_life) + Engine B (compare_prices) 的降级链
# ──────────────────────────────────────────────


async def smart_compare_prices(
    query: str,
    *,
    use_ai_summary: bool = True,
    fast_mode: bool = False,
    limit_per_platform: int = 5,
) -> ComparisonReport:
    """统一比价入口 — 多级降级链

    降级顺序:
    1. SMZDM+JD 直接爬取（总是尝试，速度最快、零 API 消耗）
    2. Tavily 智能搜索（如果直接爬取结果太少，且 fast_mode=False）
    3. crawl4ai 结构化提取（Tavily 失败时，且 fast_mode=False）
    4. Jina Reader + LLM 分析（最终兜底，且 fast_mode=False）

    多级结果会合并去重后返回统一的 ComparisonReport。

    Args:
        query: 商品名称/搜索关键词
        use_ai_summary: 是否用 LLM 生成购买推荐
        fast_mode: True 时只用直接爬取，不走 Tavily/crawl4ai/Jina
                   （用于批量价格监控，保证速度、不消耗 API 额度）
        limit_per_platform: 每个平台最多返回的商品数

    Returns:
        ComparisonReport — 与 compare_prices() 返回类型完全一致
    """
    if not query:
        return ComparisonReport(query=query, ai_summary="未指定商品")

    all_results: List[PriceResult] = []
    platforms: List[str] = []

    # ── 第一级: SMZDM+JD 直接爬取（总是执行，速度最快） ──
    try:
        base_report = await compare_prices(
            query,
            use_ai_summary=False,  # AI 总结放到最后统一做
            limit_per_platform=limit_per_platform,
        )
        all_results.extend(
            _dicts_to_price_results(base_report.results)
        )
        platforms.extend(base_report.searched_platforms)
    except Exception as e:
        logger.warning("[smart_compare] SMZDM+JD 爬取异常: %s", e)

    # 统计有效价格数量，决定是否需要降级
    priced_count = sum(1 for r in all_results if r.price > 0)

    # fast_mode 下不走后续降级链（批量监控场景，需要速度优先）
    if fast_mode:
        return _build_final_report(query, all_results, platforms, use_ai_summary)

    # ── 第二级: Tavily 智能搜索（爬取结果不足时启用） ──
    if priced_count < 2:
        tavily_results = await _tier_tavily(query)
        if tavily_results:
            all_results.extend(tavily_results)
            if "Tavily" not in platforms:
                platforms.append("Tavily")
            priced_count = sum(1 for r in all_results if r.price > 0)

    # ── 第三级: crawl4ai 结构化提取（Tavily 仍不足时） ──
    if priced_count < 2:
        crawl4ai_results = await _tier_crawl4ai(query, limit_per_platform)
        if crawl4ai_results:
            all_results.extend(crawl4ai_results)
            if "crawl4ai" not in platforms:
                platforms.append("crawl4ai")
            priced_count = sum(1 for r in all_results if r.price > 0)

    # ── 第四级: Jina Reader + LLM 分析（最终兜底） ──
    if priced_count < 2:
        jina_results = await _tier_jina_llm(query)
        if jina_results:
            all_results.extend(jina_results)
            if "Jina+LLM" not in platforms:
                platforms.append("Jina+LLM")

    return _build_final_report(query, all_results, platforms, use_ai_summary)


# ──────────────────────────────────────────────
#  降级链各级实现
# ──────────────────────────────────────────────


def _dicts_to_price_results(result_dicts: List[dict]) -> List[PriceResult]:
    """将 compare_prices 返回的 dict 列表转回 PriceResult 对象"""
    results: List[PriceResult] = []
    for d in result_dicts:
        try:
            results.append(PriceResult(
                title=d.get("title", ""),
                price=float(d.get("price", 0)),
                platform=d.get("platform", ""),
                url=d.get("url", ""),
                shop=d.get("shop", ""),
                historical_low=float(d.get("historical_low", 0)),
                is_deal=bool(d.get("is_deal", False)),
                source=d.get("source", ""),
            ))
        except (ValueError, TypeError):
            continue
    return results


async def _tier_tavily(query: str) -> List[PriceResult]:
    """第二级降级: Tavily 智能搜索 + LLM 分析"""
    try:
        from src.tools.tavily_search import search_context, _HAS_TAVILY

        if not _HAS_TAVILY:
            return []

        logger.info("[smart_compare] 第二级降级: Tavily 搜索 '%s'", query)
        tavily_ctx = await search_context(
            f"{query} 价格对比 京东 淘宝 拼多多", max_results=5
        )
        if not tavily_ctx or len(tavily_ctx) <= 200:
            return []

        # 用 LLM 从 Tavily 搜索结果中提取结构化价格
        return await _llm_extract_prices(query, tavily_ctx[:3000], "tavily")

    except ImportError:
        logger.debug("[smart_compare] tavily_search 不可用")
    except Exception as e:
        logger.warning("[smart_compare] Tavily 搜索异常: %s", e)
    return []


async def _tier_crawl4ai(query: str, limit: int = 5) -> List[PriceResult]:
    """第三级降级: crawl4ai 结构化提取"""
    try:
        from src.shopping.crawl4ai_engine import smart_compare, HAS_CRAWL4AI

        if not HAS_CRAWL4AI:
            return []

        logger.info("[smart_compare] 第三级降级: crawl4ai 引擎 '%s'", query)
        result = await smart_compare(query, limit_per_platform=limit)
        if not result.products:
            return []

        # 将 crawl4ai 的 ProductPrice 转为 PriceResult
        converted: List[PriceResult] = []
        for p in result.products:
            if p.price > 0:
                converted.append(PriceResult(
                    title=p.name,
                    price=p.price,
                    platform=p.platform,
                    url=p.url,
                    shop=p.shop,
                    source=f"crawl4ai_{p.source}",
                ))
        return converted

    except ImportError:
        logger.debug("[smart_compare] crawl4ai_engine 不可用")
    except Exception as e:
        logger.warning("[smart_compare] crawl4ai 引擎异常: %s", e)
    return []


async def _tier_jina_llm(query: str) -> List[PriceResult]:
    """第四级降级: Jina Reader 读取搜索页面 + LLM 提取价格"""
    jina_context = ""
    try:
        from src.tools.jina_reader import jina_read
        import urllib.parse

        q = urllib.parse.quote(f"{query} 价格 对比")
        raw = await jina_read(
            f"https://cn.bing.com/shop?q={q}", max_length=3000
        )
        if raw and len(raw) > 200:
            jina_context = raw[:2000]
    except ImportError:
        logger.debug("[smart_compare] jina_reader 不可用")
    except Exception:
        logger.debug("[smart_compare] Jina 读取异常", exc_info=True)

    if not jina_context:
        return []

    logger.info("[smart_compare] 第四级降级: Jina+LLM '%s'", query)
    return await _llm_extract_prices(query, jina_context, "jina_llm")


async def _llm_extract_prices(
    query: str, context: str, source_tag: str
) -> List[PriceResult]:
    """用 LLM 从文本上下文中提取结构化价格列表"""
    try:
        from src.litellm_router import free_pool
        from src.constants import FAMILY_DEEPSEEK
        from src.resilience import api_limiter
        from config.prompts import SOUL_CORE

        if not free_pool:
            return []

        async with api_limiter("llm"):
            resp = await free_pool.acompletion(
                model_family=FAMILY_DEEPSEEK,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            SOUL_CORE + "\n\n你现在在做购物比价任务。"
                            "根据搜索结果提取各平台价格信息。"
                            '输出JSON格式: {"products":[{"name":"商品名","price":999.0,'
                            '"platform":"平台名","shop":"店铺名"}]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"帮我从以下信息中提取 {query} 的价格数据:\n{context}"
                        ),
                    },
                ],
                max_tokens=600,
                temperature=0.3,
            )

        content = resp.choices[0].message.content
        if not content:
            return []

        import json_repair

        data = json_repair.loads(content)
        if not isinstance(data, dict):
            return []

        products = data.get("products", [])
        if not isinstance(products, list):
            return []

        results: List[PriceResult] = []
        for item in products[:10]:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            if not name:
                continue
            try:
                price = float(item.get("price", 0))
            except (ValueError, TypeError):
                price = _extract_price(str(item.get("price", "")))
            if price <= 0:
                continue
            results.append(PriceResult(
                title=name[:100],
                price=price,
                platform=(item.get("platform") or "").strip() or "未知",
                url="",
                shop=(item.get("shop") or "").strip(),
                source=source_tag,
            ))
        return results

    except ImportError:
        logger.debug("[smart_compare] LLM 依赖不可用 (litellm_router/json_repair)")
    except Exception as e:
        logger.warning("[smart_compare] LLM 提取价格异常: %s", e)
    return []


async def _build_final_report(
    query: str,
    all_results: List[PriceResult],
    platforms: List[str],
    use_ai_summary: bool,
) -> ComparisonReport:
    """汇总所有降级层的结果，构建最终 ComparisonReport"""
    # 按标题去重（保留价格更低的那个）
    seen: dict = {}
    for r in all_results:
        key = r.title.strip().lower()
        if key not in seen or (r.price > 0 and r.price < seen[key].price):
            seen[key] = r
    deduped = list(seen.values())

    # 按价格排序（有价格优先，价格低优先）
    priced = [r for r in deduped if r.price > 0]
    priced.sort(key=lambda r: r.price)
    unpriced = [r for r in deduped if r.price <= 0]
    final = priced + unpriced

    best = priced[0] if priced else None

    # AI 总结
    ai_summary = ""
    if use_ai_summary and priced:
        ai_summary = await _generate_ai_summary(query, priced)

    return ComparisonReport(
        query=query,
        results=[asdict(r) for r in final],
        best_deal=asdict(best) if best else None,
        ai_summary=ai_summary,
        searched_platforms=platforms,
    )
