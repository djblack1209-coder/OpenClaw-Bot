"""
MediaCrawler 集成桥接层 — 搬运自 MediaCrawler (46.2k⭐)

通过 Docker/subprocess 调用 MediaCrawler 服务，获取多平台社交数据。
支持平台：小红书、抖音、微博、B站、快手、贴吧、知乎

集成方式：
  1. Docker 部署 MediaCrawler（独立服务，端口 8080）
  2. 本模块通过 HTTP API 与其 FastAPI WebUI 交互
  3. 爬取结果写入 SharedMemory，供 AI 团队做内容策略参考
"""
import logging
import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
from src.utils import now_et

logger = logging.getLogger(__name__)

CRAWLER_BASE_URL = os.getenv("MEDIACRAWLER_URL", "http://localhost:8080")
CRAWLER_DIR = os.getenv("MEDIACRAWLER_DIR", "")

PLATFORM_MAP = {
    "xhs": "xhs", "xiaohongshu": "xhs", "小红书": "xhs",
    "douyin": "dy", "抖音": "dy", "dy": "dy",
    "weibo": "wb", "微博": "wb", "wb": "wb",
    "bilibili": "bili", "b站": "bili", "bili": "bili",
    "kuaishou": "ks", "快手": "ks", "ks": "ks",
    "tieba": "tieba", "贴吧": "tieba",
    "zhihu": "zhihu", "知乎": "zhihu",
}


class MediaCrawlerBridge:
    """
    MediaCrawler 集成客户端

    两种模式：
    1. API 模式：通过 HTTP 调用 MediaCrawler 的 FastAPI 服务
    2. CLI 模式：直接调用 MediaCrawler 的 Python 脚本（需本地安装）
    """

    def __init__(self, base_url: str = CRAWLER_BASE_URL, shared_memory=None):
        self.base_url = base_url.rstrip("/")
        self.memory = shared_memory
        self._session = None

    async def _get_session(self):
        if self._session is None:
            try:
                import httpx
                self._session = httpx.AsyncClient(timeout=120.0)
            except ImportError:
                logger.error("[MediaCrawler] httpx 未安装")
                return None
        return self._session

    async def close(self):
        """关闭 httpx 会话，防止连接泄漏"""
        if self._session:
            await self._session.aclose()
            self._session = None

    def _normalize_platform(self, platform: str) -> str:
        return PLATFORM_MAP.get(platform.lower().strip(), platform.lower().strip())

    async def search_platform(
        self, platform: str, keywords: List[str], limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """搜索指定平台的内容"""
        plat = self._normalize_platform(platform)
        session = await self._get_session()
        if not session:
            return await self._cli_search(plat, keywords, limit)

        try:
            resp = await session.post(
                f"{self.base_url}/api/crawl",
                json={
                    "platform": plat,
                    "crawler_type": "search",
                    "keywords": ",".join(keywords),
                    "max_notes": limit,
                },
            )
            if resp.status_code == 200:
                results = resp.json()
                items = results if isinstance(results, list) else results.get("data", [])
                self._save_to_memory(plat, "search", keywords, items)
                return items
        except Exception as e:
            logger.warning("[MediaCrawler] API 搜索失败: %s，尝试 CLI 模式", e)

        return await self._cli_search(plat, keywords, limit)

    async def get_creator_posts(
        self, platform: str, creator_id: str, limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """获取创作者的帖子列表"""
        plat = self._normalize_platform(platform)
        session = await self._get_session()
        if not session:
            return []

        try:
            resp = await session.post(
                f"{self.base_url}/api/crawl",
                json={
                    "platform": plat,
                    "crawler_type": "creator",
                    "creator_ids": [creator_id],
                    "max_notes": limit,
                },
            )
            if resp.status_code == 200:
                results = resp.json()
                items = results if isinstance(results, list) else results.get("data", [])
                self._save_to_memory(plat, "creator", [creator_id], items)
                return items
        except Exception as e:
            logger.warning("[MediaCrawler] 获取创作者帖子失败: %s", e)
        return []

    async def get_post_comments(
        self, platform: str, post_id: str, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """获取帖子评论"""
        plat = self._normalize_platform(platform)
        session = await self._get_session()
        if not session:
            return []

        try:
            resp = await session.post(
                f"{self.base_url}/api/crawl",
                json={
                    "platform": plat,
                    "crawler_type": "detail",
                    "note_ids": [post_id],
                    "enable_comments": True,
                    "max_comments": limit,
                },
            )
            if resp.status_code == 200:
                results = resp.json()
                return results if isinstance(results, list) else results.get("comments", [])
        except Exception as e:
            logger.warning("[MediaCrawler] 获取评论失败: %s", e)
        return []

    async def get_trending(self, platform: str) -> List[Dict[str, Any]]:
        """获取平台热门话题（通过搜索热门关键词实现）"""
        plat = self._normalize_platform(platform)
        trending_keywords = {
            "xhs": ["热门", "爆款", "种草"],
            "dy": ["热门", "挑战", "热搜"],
            "wb": ["热搜", "热门话题"],
            "bili": ["热门", "排行榜"],
        }
        keywords = trending_keywords.get(plat, ["热门"])
        return await self.search_platform(platform, keywords, limit=10)

    async def analyze_competitors(
        self, platform: str, competitor_ids: List[str],
    ) -> Dict[str, Any]:
        """分析竞品账号"""
        results = {}
        for cid in competitor_ids[:5]:  # 限制最多 5 个
            posts = await self.get_creator_posts(platform, cid, limit=10)
            if posts:
                results[cid] = {
                    "post_count": len(posts),
                    "avg_likes": _avg_field(posts, "liked_count"),
                    "avg_comments": _avg_field(posts, "comment_count"),
                    "avg_shares": _avg_field(posts, "share_count"),
                    "top_post": max(posts, key=lambda p: p.get("liked_count", 0), default={}),
                    "recent_topics": [p.get("title", "")[:50] for p in posts[:5]],
                }
            await asyncio.sleep(2)  # 礼貌间隔

        if self.memory and results:
            summary = json.dumps(
                {k: {**v, "top_post": v.get("top_post", {}).get("title", "")}
                 for k, v in results.items()},
                ensure_ascii=False,
            )[:2000]
            self.memory.remember(
                key=f"competitor_analysis_{platform}_{now_et():%m%d}",
                value=summary,
                category="social_research",
                source_bot="media_crawler",
                importance=3,
                ttl_hours=48,
            )
        return results

    async def health_check(self) -> Dict[str, Any]:
        session = await self._get_session()
        if not session:
            return {"status": "error", "message": "httpx 未安装"}
        try:
            resp = await session.get(f"{self.base_url}/", timeout=5.0)
            return {"status": "ok" if resp.status_code == 200 else "error",
                    "url": self.base_url}
        except Exception as e:
            return {"status": "offline", "message": str(e)}

    # ── CLI 回退模式 ──

    async def _cli_search(
        self, platform: str, keywords: List[str], limit: int,
    ) -> List[Dict[str, Any]]:
        """通过 CLI 调用 MediaCrawler（本地安装模式）"""
        crawler_dir = CRAWLER_DIR
        if not crawler_dir or not Path(crawler_dir).exists():
            logger.debug("[MediaCrawler] CLI 模式不可用：MEDIACRAWLER_DIR 未设置")
            return []

        try:
            env = os.environ.copy()
            env["PLATFORM"] = platform
            env["KEYWORDS"] = ",".join(keywords)
            env["CRAWLER_TYPE"] = "search"
            env["CRAWLER_MAX_NOTES_COUNT"] = str(limit)
            env["SAVE_DATA_OPTION"] = "json"
            env["HEADLESS"] = "true"

            proc = await asyncio.create_subprocess_exec(
                "python3", "main.py",
                cwd=crawler_dir,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

            if proc.returncode == 0:
                # 尝试读取输出的 JSON 文件
                data_dir = Path(crawler_dir) / "data" / platform
                json_files = sorted(data_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
                if json_files:
                    with open(json_files[0]) as f:
                        items = json.load(f)
                    self._save_to_memory(platform, "search", keywords, items)
                    return items if isinstance(items, list) else []
            else:
                logger.warning("[MediaCrawler] CLI 执行失败: %s", stderr.decode()[:200])
        except asyncio.TimeoutError:
            logger.warning("[MediaCrawler] CLI 执行超时")
        except Exception as e:
            logger.warning("[MediaCrawler] CLI 执行异常: %s", e)
        return []

    # ── 内部方法 ──

    def _save_to_memory(self, platform: str, mode: str, keywords: List[str], items: List[Dict]):
        """将爬取结果写入 SharedMemory"""
        if not self.memory or not items:
            return
        kw = ",".join(keywords)[:30]
        summary_parts = []
        for item in items[:5]:
            title = item.get("title", item.get("desc", ""))[:60]
            likes = item.get("liked_count", 0)
            summary_parts.append(f"{title} (👍{likes})")
        summary = " | ".join(summary_parts)
        self.memory.remember(
            key=f"crawl_{platform}_{mode}_{kw}_{now_et():%H%M}",
            value=f"[{platform}] {mode} '{kw}': {summary}",
            category="social_research",
            source_bot="media_crawler",
            importance=2,
            ttl_hours=24,
        )


def _avg_field(items: List[Dict], field: str) -> float:
    vals = [item.get(field, 0) for item in items if isinstance(item.get(field, 0), (int, float))]
    return round(sum(vals) / max(len(vals), 1), 1)


# ── 全局实例 ──

_bridge: Optional[MediaCrawlerBridge] = None


def init_media_crawler(shared_memory=None) -> MediaCrawlerBridge:
    global _bridge
    _bridge = MediaCrawlerBridge(shared_memory=shared_memory)
    logger.info("[MediaCrawler] 桥接层初始化完成 (服务地址: %s)", _bridge.base_url)
    return _bridge


def get_media_crawler() -> Optional[MediaCrawlerBridge]:
    return _bridge
