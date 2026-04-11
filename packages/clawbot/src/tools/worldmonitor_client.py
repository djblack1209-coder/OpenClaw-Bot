"""Worldmonitor 全球情报系统 API 客户端

集成 worldmonitor.app 的公开 API，提供按行业/地区分类的全球新闻情报聚合。
数据源涵盖 435+ 新闻源，覆盖地缘政治、军事、金融、能源、气候、网络安全等 15 个分类。

参考: https://github.com/koala73/worldmonitor
"""

import asyncio
import os
import time
from typing import Dict, List, Optional, Any, Tuple

import httpx

import logging

logger = logging.getLogger(__name__)

# --- 常量 ---
_BASE_URL = os.getenv("WORLDMONITOR_API_URL", "https://worldmonitor.app/api")
_TIMEOUT = 15.0
_CACHE_TTL = 600  # 10分钟缓存
_MAX_ITEMS = 8  # 每个分类最多返回条数
_HEADERS = {
    "User-Agent": "OpenClaw-Bot/1.0",
    "Accept": "application/json",
}

# --- 行业分类 → API 端点映射 ---
INDUSTRY_CATEGORIES: Dict[str, dict] = {
    "finance": {
        "name": "金融经济",
        "emoji": "🏦",
        "endpoints": ["/market/overview", "/economic/indicators"],
    },
    "military": {
        "name": "军事安全",
        "emoji": "🛡️",
        "endpoints": ["/military/activity", "/conflict/events"],
    },
    "tech": {
        "name": "科技网络",
        "emoji": "💻",
        "endpoints": ["/news/tech"],
    },
    "energy": {
        "name": "能源气候",
        "emoji": "⚡",
        "endpoints": ["/eia/overview"],
    },
    "cyber": {
        "name": "网络安全",
        "emoji": "🔒",
        "endpoints": ["/cyber/threats"],
    },
    "natural": {
        "name": "自然灾害",
        "emoji": "🌊",
        "endpoints": ["/natural/events", "/climate/alerts"],
    },
    "geopolitics": {
        "name": "地缘政治",
        "emoji": "🌍",
        "endpoints": ["/intelligence/briefs"],
    },
}

# --- 地区分类 ---
REGION_CATEGORIES: Dict[str, dict] = {
    "north_america": {
        "name": "北美",
        "emoji": "🇺🇸",
        "keywords": ["US", "USA", "United States", "Canada"],
    },
    "europe": {
        "name": "欧洲",
        "emoji": "🇪🇺",
        "keywords": ["EU", "Europe", "UK", "Germany", "France"],
    },
    "asia_pacific": {
        "name": "亚太",
        "emoji": "🇨🇳",
        "keywords": ["China", "Japan", "Korea", "India", "Australia"],
    },
    "middle_east": {
        "name": "中东",
        "emoji": "🌍",
        "keywords": ["Middle East", "Israel", "Iran", "Saudi"],
    },
    "global": {
        "name": "全球",
        "emoji": "🌐",
        "keywords": [],
    },
}


# ── 内存缓存 ──────────────────────────────────────────

# 缓存结构: {缓存键: (写入时间戳, 数据)}
_cache: Dict[str, Tuple[float, Any]] = {}


def _get_cached(key: str) -> Optional[Any]:
    """从缓存读取数据，超过 TTL 则返回 None"""
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, data = entry
    if time.time() - ts > _CACHE_TTL:
        # 过期，清除该键
        _cache.pop(key, None)
        return None
    return data


def _set_cached(key: str, data: Any) -> None:
    """写入缓存，附带当前时间戳"""
    _cache[key] = (time.time(), data)


# ── 响应解析 ──────────────────────────────────────────

# Worldmonitor API 可能返回多种数据结构，以下键名都会尝试提取
_LIST_KEYS = ("data", "items", "events", "articles", "results")
_TITLE_KEYS = ("title", "headline", "name")
_SUMMARY_KEYS = ("summary", "description", "content")
_SOURCE_KEYS = ("source", "provider")
_URL_KEYS = ("url", "link")
_TIME_KEYS = ("published_at", "date", "timestamp", "published", "updated")


def _extract_list(payload: Any) -> List[dict]:
    """从 API 响应体中提取条目列表

    按优先级尝试多个常见键名，兼容不同 API 结构。
    """
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in _LIST_KEYS:
            val = payload.get(key)
            if isinstance(val, list):
                return val
        # 如果都没找到，把整个字典当作单条数据
        if any(payload.get(k) for k in _TITLE_KEYS):
            return [payload]

    return []


def _first(d: dict, keys: tuple) -> str:
    """从字典中按键名优先级取第一个非空字符串值"""
    for k in keys:
        val = d.get(k)
        if val and isinstance(val, str):
            return val.strip()
    return ""


def _normalize_item(raw: dict) -> Dict[str, str]:
    """将原始 API 条目统一为标准格式"""
    return {
        "title": _first(raw, _TITLE_KEYS) or "（无标题）",
        "summary": _first(raw, _SUMMARY_KEYS),
        "source": _first(raw, _SOURCE_KEYS),
        "url": _first(raw, _URL_KEYS),
        "published_at": _first(raw, _TIME_KEYS),
    }


# ── 核心抓取 ──────────────────────────────────────────

async def _fetch_endpoint(client: httpx.AsyncClient, endpoint: str) -> List[dict]:
    """请求单个 API 端点并返回标准化条目列表"""
    url = f"{_BASE_URL}{endpoint}"
    try:
        resp = await client.get(url, headers=_HEADERS)
        if resp.status_code != 200:
            logger.debug("Worldmonitor 端点 %s 返回 %s", endpoint, resp.status_code)
            return []
        payload = resp.json()
        raw_items = _extract_list(payload)
        return [_normalize_item(item) for item in raw_items if isinstance(item, dict)]
    except httpx.TimeoutException:
        logger.warning("Worldmonitor 端点 %s 请求超时", endpoint)
        return []
    except Exception as e:
        logger.warning("Worldmonitor 端点 %s 请求异常: %s", endpoint, e)
        return []


async def _fallback_rss_news(query: str, max_items: int = _MAX_ITEMS) -> List[Dict]:
    """降级方案：Worldmonitor 不可用时尝试 Google News RSS

    搬运 news_fetcher 的 RSS 解析逻辑作为兜底数据源。
    """
    import re
    import urllib.parse

    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers={
                "User-Agent": "OpenClaw-Bot/1.0",
            })
            if resp.status_code != 200:
                return []
            items: List[Dict] = []
            raw_items = re.findall(r"<item>(.*?)</item>", resp.text, re.DOTALL)
            for raw in raw_items[:max_items]:
                title_m = re.search(r"<title>(.*?)</title>", raw)
                link_m = re.search(r"<link>(.*?)</link>", raw)
                source_m = re.search(r"<source[^>]*>(.*?)</source>", raw)
                pub_m = re.search(r"<pubDate>(.*?)</pubDate>", raw)
                if title_m and link_m:
                    items.append({
                        "title": title_m.group(1).strip(),
                        "summary": "",
                        "source": source_m.group(1).strip() if source_m else "Google News",
                        "url": link_m.group(1).strip(),
                        "published_at": pub_m.group(1).strip() if pub_m else "",
                    })
            return items
    except Exception as e:
        logger.debug("Google News RSS 降级也失败: %s", e)
        return []


# ── 公开接口 ──────────────────────────────────────────

async def fetch_category_news(
    category: str, max_items: int = _MAX_ITEMS
) -> List[Dict]:
    """获取指定行业分类的情报新闻

    按分类对应的端点列表依次请求，汇总结果并去重。
    使用内存缓存减少重复请求。

    Args:
        category: 行业分类键名，如 "finance", "military" 等
        max_items: 最多返回条目数

    Returns:
        标准化新闻条目列表，每条包含 title/summary/source/url/published_at
    """
    cache_key = f"cat:{category}"
    cached = _get_cached(cache_key)
    if cached is not None:
        logger.debug("命中缓存: %s (%d 条)", cache_key, len(cached))
        return cached[:max_items]

    cat_info = INDUSTRY_CATEGORIES.get(category)
    if not cat_info:
        logger.warning("未知行业分类: %s", category)
        return []

    endpoints = cat_info["endpoints"]
    all_items: List[Dict] = []
    seen_titles: set = set()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # 并行请求该分类下的所有端点
            tasks = [_fetch_endpoint(client, ep) for ep in endpoints]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, list):
                    for item in result:
                        title = item.get("title", "")
                        if title and title not in seen_titles:
                            seen_titles.add(title)
                            all_items.append(item)
                elif isinstance(result, Exception):
                    logger.debug("端点请求异常: %s", result)
    except Exception as e:
        logger.warning("行业分类 %s 请求失败: %s", category, e)

    # Worldmonitor 无数据时降级到 RSS
    if not all_items:
        logger.warning(
            "Worldmonitor 分类 %s 无数据，降级到 Google News RSS",
            category,
        )
        fallback_query = cat_info["name"]
        all_items = await _fallback_rss_news(fallback_query, max_items)

    _set_cached(cache_key, all_items)
    return all_items[:max_items]


async def fetch_region_news(
    region: str, max_items: int = _MAX_ITEMS
) -> List[Dict]:
    """获取指定地区的情报新闻

    全球分类直接请求通用新闻端点；
    特定地区通过关键词过滤或 API query 参数筛选。

    Args:
        region: 地区键名，如 "north_america", "asia_pacific", "global" 等
        max_items: 最多返回条目数

    Returns:
        标准化新闻条目列表
    """
    cache_key = f"reg:{region}"
    cached = _get_cached(cache_key)
    if cached is not None:
        logger.debug("命中缓存: %s (%d 条)", cache_key, len(cached))
        return cached[:max_items]

    reg_info = REGION_CATEGORIES.get(region)
    if not reg_info:
        logger.warning("未知地区分类: %s", region)
        return []

    all_items: List[Dict] = []

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if region == "global":
                # 全球分类：请求通用新闻端点
                all_items = await _fetch_endpoint(client, "/news/latest")
                if not all_items:
                    all_items = await _fetch_endpoint(client, "/intelligence/briefs")
            else:
                # 特定地区：先尝试带 region 参数的端点
                resp_items = await _fetch_endpoint(
                    client, f"/news/latest?region={region}"
                )
                if resp_items:
                    all_items = resp_items
                else:
                    # 降级：获取全部新闻后按关键词过滤
                    raw_all = await _fetch_endpoint(client, "/news/latest")
                    keywords = [kw.lower() for kw in reg_info.get("keywords", [])]
                    if keywords and raw_all:
                        for item in raw_all:
                            # 在标题和摘要中搜索地区关键词
                            text = (
                                f"{item.get('title', '')} "
                                f"{item.get('summary', '')}"
                            ).lower()
                            if any(kw in text for kw in keywords):
                                all_items.append(item)
    except Exception as e:
        logger.warning("地区 %s 新闻请求失败: %s", region, e)

    # 降级到 RSS
    if not all_items:
        logger.warning(
            "Worldmonitor 地区 %s 无数据，降级到 Google News RSS",
            region,
        )
        fallback_query = reg_info["name"] + " news"
        all_items = await _fallback_rss_news(fallback_query, max_items)

    _set_cached(cache_key, all_items)
    return all_items[:max_items]


async def fetch_news_by_query(
    query: str, max_items: int = _MAX_ITEMS
) -> List[Dict]:
    """按关键词搜索情报新闻

    先尝试 Worldmonitor 的搜索端点，不可用则降级到 Google News RSS。

    Args:
        query: 搜索关键词
        max_items: 最多返回条目数

    Returns:
        标准化新闻条目列表
    """
    if not query or not query.strip():
        return []

    query = query.strip()
    cache_key = f"search:{query}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached[:max_items]

    items: List[Dict] = []

    # 尝试 Worldmonitor 搜索 API
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE_URL}/news/search",
                params={"q": query},
                headers=_HEADERS,
            )
            if resp.status_code == 200:
                payload = resp.json()
                raw_items = _extract_list(payload)
                seen: set = set()
                for raw in raw_items:
                    if isinstance(raw, dict):
                        item = _normalize_item(raw)
                        if item["title"] not in seen:
                            seen.add(item["title"])
                            items.append(item)
    except Exception as e:
        logger.debug("Worldmonitor 搜索失败: %s", e)

    # 数据不足时降级到 Google News RSS
    if len(items) < max_items:
        logger.warning("Worldmonitor 搜索结果不足，补充 Google News RSS")
        rss_items = await _fallback_rss_news(query, max_items - len(items))
        existing_titles = {it["title"] for it in items}
        for rss_item in rss_items:
            if rss_item["title"] not in existing_titles:
                items.append(rss_item)

    _set_cached(cache_key, items)
    return items[:max_items]


async def generate_intel_brief() -> str:
    """生成综合情报简报

    汇总所有行业分类的头条新闻，格式化为 Telegram 友好的每日速递文本。
    类似 news_fetcher.generate_morning_report() 的排版风格。

    Returns:
        格式化的情报简报文本
    """
    from src.utils import now_et

    # 尝试使用 format_digest 统一排版
    try:
        from src.notify_style import format_digest
        _use_digest = True
    except ImportError:
        _use_digest = False

    date_str = now_et().strftime("%Y年%m月%d日")

    sections: List[Tuple[str, List[str]]] = []

    for cat_key, cat_info in INDUSTRY_CATEGORIES.items():
        emoji = cat_info["emoji"]
        name = cat_info["name"]

        items = await fetch_category_news(cat_key, max_items=3)
        if items:
            entries = []
            for idx, item in enumerate(items[:3], 1):
                title = item.get("title", "")
                source = item.get("source", "")
                line = f"{idx}. {title}"
                if source:
                    line += f"（{source}）"
                entries.append(line)
            sections.append((f"{emoji} {name}", entries))
        else:
            sections.append((f"{emoji} {name}", ["- 暂无情报"]))

        # 控制请求频率
        await asyncio.sleep(0.3)

    if _use_digest:
        return format_digest(
            title=f"🌍 全球情报速递 — {date_str}",
            intro="覆盖金融、军事、科技、能源、网安、自然灾害、地缘政治七大领域。",
            sections=sections,
            footer="数据源: worldmonitor.app | 435+ 全球新闻源 | 每10分钟更新",
        )

    # 手动拼接排版（format_digest 不可用的降级方案）
    lines = [
        f"🌍 全球情报速递 — {date_str}",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "覆盖金融、军事、科技、能源、网安、自然灾害、地缘政治七大领域。",
    ]
    for heading, entries in sections:
        lines.append("")
        lines.append(f"▸ {heading}")
        for entry in entries:
            lines.append(f"  {entry}")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("  数据源: worldmonitor.app | 435+ 全球新闻源 | 每10分钟更新")

    return "\n".join(lines)


def format_intel_items(items: List[Dict], max_items: int = 5) -> str:
    """将新闻条目列表格式化为 Telegram 友好的富文本

    每条格式: • <b>标题</b>
              摘要（截取前80字）
              📎 来源 | 时间

    Args:
        items: 标准化新闻条目列表
        max_items: 最多格式化条目数

    Returns:
        适合 Telegram HTML 模式发送的文本
    """
    if not items:
        return "暂无相关情报。"

    lines: List[str] = []
    for item in items[:max_items]:
        title = item.get("title", "（无标题）")
        summary = item.get("summary", "")
        source = item.get("source", "")
        published = item.get("published_at", "")
        url = item.get("url", "")

        # 标题行（支持 HTML 加粗）
        if url:
            lines.append(f'• <b><a href="{url}">{_escape_html(title)}</a></b>')
        else:
            lines.append(f"• <b>{_escape_html(title)}</b>")

        # 摘要行（截取前80字符）
        if summary:
            short_summary = summary[:80].rstrip()
            if len(summary) > 80:
                short_summary += "..."
            lines.append(f"  {_escape_html(short_summary)}")

        # 来源和时间行
        meta_parts: List[str] = []
        if source:
            meta_parts.append(source)
        if published:
            # 只取日期部分
            meta_parts.append(published[:16])
        if meta_parts:
            lines.append(f"  📎 {' | '.join(meta_parts)}")

        lines.append("")  # 条目间空行

    return "\n".join(lines).strip()


def get_category_list() -> str:
    """返回所有可用分类的格式化列表

    包含行业分类和地区分类，带 emoji 和中文名称。

    Returns:
        格式化的分类列表文本
    """
    lines = ["📂 <b>行业分类</b>"]
    for key, info in INDUSTRY_CATEGORIES.items():
        lines.append(f"  {info['emoji']} {info['name']} ({key})")

    lines.append("")
    lines.append("🗺 <b>地区分类</b>")
    for key, info in REGION_CATEGORIES.items():
        lines.append(f"  {info['emoji']} {info['name']} ({key})")

    return "\n".join(lines)


# ── 工具函数 ──────────────────────────────────────────

def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符，防止 Telegram parse_mode=HTML 报错"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
