"""
真实热搜数据采集 — 替代 LLM 编造的假热点

数据源（全部免费公开 API，无需登录/Cookie）:
  1. 微博热搜: weibo.com/ajax/side/hotSearch
  2. 百度热搜: top.baidu.com/api/board
  3. 知乎热榜: www.zhihu.com/api/v3/feed/topstory/hot-lists
  4. GitHub Trending: github.com/trending (HTML 解析)

设计原则:
  - 并行请求所有源，任何一个成功就有真实数据
  - 每个源独立 try/except，一个挂了不影响其他
  - 结果去重 + 按热度排序
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional
import httpx

# Resilience integration — auto-retry on network errors
try:
    from src.resilience import retry_network
except ImportError:
    def retry_network(fn):  # type: ignore[misc]
        """No-op fallback when resilience module is unavailable."""
        return fn

logger = logging.getLogger(__name__)

from src.constants import DEFAULT_USER_AGENT

_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "application/json, text/html",
}


@dataclass
class HotTopic:
    title: str
    score: int = 0          # 热度值
    source: str = ""        # weibo / baidu / zhihu / github
    url: str = ""
    category: str = ""      # tech / finance / entertainment / social
    raw_rank: int = 0


# ──── 微博热搜 ────────────────────────────────────────

@retry_network
async def _fetch_weibo(client: httpx.AsyncClient) -> List[HotTopic]:
    """微博热搜 — 公开 AJAX API，无需 Cookie"""
    topics = []
    # Network errors propagate to @retry_network for automatic retry
    resp = await client.get(
        "https://weibo.com/ajax/side/hotSearch",
        headers=_HEADERS,
        timeout=10,
    )
    if resp.status_code != 200:
        return topics
    try:
        data = resp.json()
        for i, item in enumerate(data.get("data", {}).get("realtime", [])[:20]):
            word = item.get("word", "") or item.get("note", "")
            if not word:
                continue
            topics.append(HotTopic(
                title=word,
                score=int(item.get("raw_hot", 0) or item.get("num", 0) or 0),
                source="weibo",
                url=f"https://s.weibo.com/weibo?q=%23{word}%23",
                raw_rank=i + 1,
            ))
    except Exception as e:
        logger.debug("[RealTrending] 微博热搜解析失败: %s", e)
    return topics


# ──── 百度热搜 ────────────────────────────────────────

@retry_network
async def _fetch_baidu(client: httpx.AsyncClient) -> List[HotTopic]:
    """百度热搜 — 公开 API"""
    topics = []
    # Network errors propagate to @retry_network for automatic retry
    resp = await client.get(
        "https://top.baidu.com/api/board?platform=wise&tab=realtime",
        headers=_HEADERS,
        timeout=10,
    )
    if resp.status_code != 200:
        return topics
    try:
        data = resp.json()
        cards = data.get("data", {}).get("cards", [])
        # 百度结构: cards[0].content 可能是嵌套的 [{content:[{word:...}]}] 或扁平的 [{word:...}]
        raw_items = []
        if cards:
            first_content = cards[0].get("content", [])
            if first_content:
                # 检查是否嵌套（first_content[0] 有 content 字段）
                if isinstance(first_content[0], dict) and "content" in first_content[0]:
                    # 嵌套结构: cards[0].content[0].content
                    raw_items = first_content[0].get("content", [])
                else:
                    raw_items = first_content
        for i, item in enumerate(raw_items[:20]):
            word = item.get("word", "") or item.get("query", "")
            if not word:
                continue
            topics.append(HotTopic(
                title=word,
                score=int(item.get("hotScore", 0) or item.get("show", [None, 0])[1] if isinstance(item.get("show"), list) else 0),
                source="baidu",
                url=item.get("url", f"https://www.baidu.com/s?wd={word}"),
                raw_rank=i + 1,
            ))
    except Exception as e:
        logger.debug("[RealTrending] 百度热搜解析失败: %s", e)
    return topics


# ──── 知乎热榜 ────────────────────────────────────────

@retry_network
async def _fetch_zhihu(client: httpx.AsyncClient) -> List[HotTopic]:
    """知乎热榜 — 需要特定 header"""
    topics = []
    headers = {**_HEADERS, "Referer": "https://www.zhihu.com/hot"}
    # Network errors propagate to @retry_network for automatic retry
    resp = await client.get(
        "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=20",
        headers=headers,
        timeout=10,
    )
    if resp.status_code != 200:
        return topics
    try:
        data = resp.json()
        for i, item in enumerate(data.get("data", [])):
            target = item.get("target", {})
            title = target.get("title", "")
            if not title:
                continue
            topics.append(HotTopic(
                title=title,
                score=int(item.get("detail_text", "0").replace("万热度", "0000").replace(" 热度", "") or 0),
                source="zhihu",
                url=f"https://www.zhihu.com/question/{target.get('id', '')}",
                raw_rank=i + 1,
            ))
    except Exception as e:
        logger.debug("[RealTrending] 知乎热榜解析失败: %s", e)
    return topics


# ──── 统一入口 ────────────────────────────────────────

async def fetch_real_trending(
    sources: Optional[List[str]] = None,
    limit: int = 20,
) -> List[dict]:
    """从多个真实平台获取热搜，并行请求，合并去重。

    Args:
        sources: 指定数据源 ["weibo", "baidu", "zhihu"]，默认全部
        limit: 返回数量上限

    Returns:
        [{"title": "...", "score": 12345, "source": "weibo", "url": "...", "rank": 1}, ...]
    """
    if sources is None:
        sources = ["weibo", "baidu", "zhihu"]

    fetchers = {
        "weibo": _fetch_weibo,
        "baidu": _fetch_baidu,
        "zhihu": _fetch_zhihu,
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        tasks = [fetchers[s](client) for s in sources if s in fetchers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_topics: List[HotTopic] = []
    for result in results:
        if isinstance(result, list):
            all_topics.extend(result)

    # 如果主源全部失败，用 free_apis 的多源热榜补充
    if not all_topics:
        try:
            from src.tools.free_apis import get_multi_trending
            fallback = await get_multi_trending()
            for item in fallback:
                all_topics.append(HotTopic(
                    title=item.get("title", ""),
                    score=item.get("hot", 0),
                    source=item.get("source", "free_api"),
                    url="",
                ))
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)

    # 去重（按标题）
    seen = set()
    unique = []
    for t in all_topics:
        key = t.title.strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(t)

    # 按热度排序
    unique.sort(key=lambda t: t.score, reverse=True)

    # 转为 dict 格式（兼容现有 content_strategy 接口）
    return [
        {
            "title": t.title,
            "summary": f"来源: {t.source} | 热度: {t.score:,}",
            "score": min(10, max(1, t.score // 100000 + 5)) if t.score > 0 else 5,
            "source": t.source,
            "url": t.url,
            "raw_score": t.score,
        }
        for t in unique[:limit]
    ]
