"""
GitHub Trending 数据采集器

采集方式:
1. 爬取 github.com/trending 页面 (无需 Token)
2. GitHub Search API 查询快速增长的仓库 (需要 Token 获取更高限额)
"""
import asyncio
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import timedelta

from src.utils import now_et
from typing import List, Optional
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Data Model
# ──────────────────────────────────────────────

@dataclass
class TrendingRepo:
    """GitHub 仓库的结构化表示"""
    name: str                        # owner/repo
    url: str                         # https://github.com/owner/repo
    description: str = ""
    language: str = ""
    stars: int = 0
    forks: int = 0
    stars_today: int = 0             # 当日/当周新增 star
    topics: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    readme_url: str = ""             # raw README URL
    source: str = "trending"         # trending / search_api

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────
# 1. 爬取 GitHub Trending 页面
# ──────────────────────────────────────────────

async def fetch_trending(
    language: str = "",
    since: str = "weekly",
    timeout: int = 15,
) -> List[TrendingRepo]:
    """
    爬取 github.com/trending，返回趋势仓库列表。

    Args:
        language: 编程语言过滤 (e.g. "python", "typescript", "")
        since: 时间范围 ("daily", "weekly", "monthly")
        timeout: 请求超时 (秒)

    Returns:
        TrendingRepo 列表 (通常 25 个)
    """
    lang_path = f"/{quote(language)}" if language else ""
    url = f"https://github.com/trending{lang_path}?since={since}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    repos: List[TrendingRepo] = []

    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout, sock_connect=10)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            for attempt in range(3):
                try:
                    async with session.get(url, headers=headers, timeout=timeout_obj) as resp:
                        if resp.status != 200:
                            logger.warning("[trending] HTTP %d for %s", resp.status, url)
                            return repos
                        html = await resp.text()
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt == 2:
                        raise
                    logger.debug("[trending] 请求重试 attempt=%d: %s", attempt + 1, e)
                    await asyncio.sleep(2 ** attempt)
    except aiohttp.ClientError as e:
        logger.error("[trending] Network error: %s", e)
        return repos
    except Exception as e:
        logger.error("[trending] Unexpected error: %s", e)
        return repos

    repos = _parse_trending_html(html, since)
    logger.info("[trending] Parsed %d repos from %s (lang=%s, since=%s)",
                len(repos), url, language or "all", since)
    return repos


def _parse_trending_html(html: str, since: str) -> List[TrendingRepo]:
    """解析 GitHub trending 页面 HTML，提取仓库信息。"""
    repos: List[TrendingRepo] = []

    # 每个仓库在一个 <article class="Box-row"> 块中
    articles = re.split(r'<article\s+class="Box-row"', html)
    if len(articles) < 2:
        # 尝试备用分隔符 (GitHub 偶尔变更 class 名)
        articles = re.split(r'<article\s+class="[^"]*Box-row[^"]*"', html)

    for article in articles[1:]:  # 跳过第一个 (在第一个 article 之前的内容)
        try:
            repo = _parse_single_article(article, since)
            if repo:
                repos.append(repo)
        except Exception as e:
            logger.debug("[trending] Parse error for one article: %s", e)
            continue

    return repos


def _parse_single_article(article: str, since: str) -> Optional[TrendingRepo]:
    """从单个 article HTML 块中提取仓库信息。"""
    # 仓库名: <h2 ...><a href="/owner/repo">
    name_match = re.search(r'href="(/[^/]+/[^/"]+)"', article)
    if not name_match:
        return None
    full_name = name_match.group(1).strip("/")

    # 描述
    desc_match = re.search(r'<p\s+class="[^"]*col-9[^"]*"[^>]*>\s*(.*?)\s*</p>', article, re.DOTALL)
    description = ""
    if desc_match:
        description = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()

    # 编程语言
    lang_match = re.search(r'itemprop="programmingLanguage"[^>]*>\s*([^<]+)', article)
    language = lang_match.group(1).strip() if lang_match else ""

    # 总 star 数
    stars = 0
    star_match = re.search(
        r'href="/' + re.escape(full_name) + r'/stargazers"[^>]*>\s*'
        r'(?:<[^>]*>)*\s*([\d,]+)',
        article,
    )
    if star_match:
        stars = int(star_match.group(1).replace(",", ""))

    # 周期内新增 star
    stars_period = 0
    period_match = re.search(r'([\d,]+)\s+stars?\s+(?:today|this\s+week|this\s+month)', article)
    if period_match:
        stars_period = int(period_match.group(1).replace(",", ""))

    # Fork 数
    forks = 0
    fork_match = re.search(
        r'href="/' + re.escape(full_name) + r'/forks"[^>]*>\s*'
        r'(?:<[^>]*>)*\s*([\d,]+)',
        article,
    )
    if fork_match:
        forks = int(fork_match.group(1).replace(",", ""))

    return TrendingRepo(
        name=full_name,
        url=f"https://github.com/{full_name}",
        description=description,
        language=language,
        stars=stars,
        forks=forks,
        stars_today=stars_period,
        readme_url=f"https://raw.githubusercontent.com/{full_name}/main/README.md",
        source="trending",
    )


# ──────────────────────────────────────────────
# 2. GitHub Search API — 快速增长仓库
# ──────────────────────────────────────────────

async def fetch_fast_growing_repos(
    days_back: int = 7,
    min_stars: int = 500,
    language: str = "",
    token: Optional[str] = None,
    max_results: int = 30,
    timeout: int = 15,
) -> List[TrendingRepo]:
    """
    通过 GitHub Search API 查找近期快速增长的仓库。

    Args:
        days_back: 查找 N 天内创建或更新的仓库
        min_stars: 最少 star 数
        language: 编程语言过滤
        token: GitHub Personal Access Token (可选，提高限额)
        max_results: 最多返回数量
        timeout: 请求超时 (秒)

    Returns:
        TrendingRepo 列表，按 star 降序
    """
    token = token or os.getenv("GITHUB_TOKEN", "")
    cutoff = (now_et() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # 构建搜索查询
    q_parts = [f"stars:>={min_stars}", f"pushed:>={cutoff}"]
    if language:
        q_parts.append(f"language:{language}")
    query = " ".join(q_parts)

    url = "https://api.github.com/search/repositories"
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(max_results, 100),
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "OpenClaw-Evolution/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repos: List[TrendingRepo] = []

    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout, sock_connect=10)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            for attempt in range(3):
                try:
                    async with session.get(
                        url, params=params, headers=headers,
                        timeout=timeout_obj,
                    ) as resp:
                        if resp.status == 403:
                            logger.warning("[search_api] Rate limited (403). Use GITHUB_TOKEN for higher quota.")
                            return repos
                        if resp.status != 200:
                            body = await resp.text()
                            logger.warning("[search_api] HTTP %d: %s", resp.status, body[:200])
                            return repos
                        data = await resp.json()
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt == 2:
                        raise
                    logger.debug("[search_api] 请求重试 attempt=%d: %s", attempt + 1, e)
                    await asyncio.sleep(2 ** attempt)
    except aiohttp.ClientError as e:
        logger.error("[search_api] Network error: %s", e)
        return repos
    except Exception as e:
        logger.error("[search_api] Unexpected error: %s", e)
        return repos

    for item in data.get("items", []):
        try:
            repos.append(TrendingRepo(
                name=item.get("full_name", ""),
                url=item.get("html_url", ""),
                description=item.get("description", "") or "",
                language=item.get("language", "") or "",
                stars=item.get("stargazers_count", 0),
                forks=item.get("forks_count", 0),
                stars_today=0,  # Search API 无此字段
                topics=item.get("topics", []) or [],
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
                readme_url=(
                    f"https://raw.githubusercontent.com/"
                    f"{item.get('full_name', '')}/{item.get('default_branch', 'main')}/README.md"
                ),
                source="search_api",
            ))
        except Exception as e:
            logger.debug("[search_api] Parse error for item: %s", e)
            continue

    logger.info("[search_api] Found %d repos (q=%s)", len(repos), query)
    return repos


# ──────────────────────────────────────────────
# 3. 获取 README 内容
# ──────────────────────────────────────────────

async def fetch_readme(repo_name: str, token: Optional[str] = None, max_chars: int = 8000) -> str:
    """
    获取仓库 README 内容 (截断到 max_chars)。
    先尝试 main 分支，失败后尝试 master。
    """
    token = token or os.getenv("GITHUB_TOKEN", "")
    headers = {"User-Agent": "OpenClaw-Evolution/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for branch in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{repo_name}/{branch}/README.md"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(
                    url, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        return text[:max_chars]
        except Exception as e:  # noqa: F841
            continue

    return ""
