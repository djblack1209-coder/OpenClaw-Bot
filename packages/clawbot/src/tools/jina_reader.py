"""
OpenClaw — Jina Reader 集成
零依赖的网页内容提取和搜索（10.3k⭐, 免费API）

使用方式:
    content = await jina_read("https://example.com")
    results = await jina_search("Python error ConnectionRefusedError")

集成点:
    1. self_heal.py — 替代 Tavily 做 Web 搜索
    2. investment/team.py — 研究员获取新闻/财报
    3. brain.py — 通用信息查询
"""
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_JINA_READ_BASE = "https://r.jina.ai/"
_JINA_SEARCH_BASE = "https://s.jina.ai/"
_TIMEOUT = 15.0
_HEADERS = {
    "Accept": "text/plain",
}


async def jina_read(url: str, max_length: int = 5000) -> Optional[str]:
    """
    读取任意URL的内容，返回干净的 Markdown 文本。
    处理 SPA、PDF、JS渲染页面，无需浏览器。

    Args:
        url: 目标URL
        max_length: 返回内容的最大字符数

    Returns:
        Markdown 格式的页面内容，失败返回 None
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_JINA_READ_BASE}{url}",
                headers=_HEADERS,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                text = resp.text.strip()
                return text[:max_length] if text else None
            logger.debug(f"Jina Reader 返回 {resp.status_code}: {url}")
    except Exception as e:
        logger.debug(f"Jina Reader 失败: {e}")
    return None


async def jina_search(query: str, max_results: int = 5) -> Optional[str]:
    """
    搜索并返回结果摘要（需要 JINA_API_KEY 环境变量）。
    免费额度: https://jina.ai/reader

    Args:
        query: 搜索关键词
        max_results: 最大结果数

    Returns:
        搜索结果的 Markdown 文本，失败返回 None
    """
    import os
    api_key = os.environ.get("JINA_API_KEY", "")
    headers = dict(_HEADERS)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        # 无 API key 时降级：用 Jina Read 读取搜索引擎结果页
        try:
            return await jina_read(f"https://www.google.com/search?q={query}", max_length=5000)
        except Exception:
            return None

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_JINA_SEARCH_BASE}{query}",
                headers=headers,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                text = resp.text.strip()
                return text[:8000] if text else None
            logger.debug(f"Jina Search 返回 {resp.status_code}")
    except Exception as e:
        logger.debug(f"Jina Search 失败: {e}")
    return None


async def fetch_news_about(topic: str, max_length: int = 3000) -> str:
    """
    获取关于某个主题的最新新闻/信息。
    投资研究员和社媒内容策划的核心工具。

    Args:
        topic: 主题（如 "茅台 财报" 或 "AAPL earnings"）
        max_length: 最大返回长度

    Returns:
        新闻摘要文本
    """
    result = await jina_search(topic)
    if result:
        return result[:max_length]
    return f"未找到关于 '{topic}' 的最新信息"
