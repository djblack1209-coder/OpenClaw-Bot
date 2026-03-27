"""
Execution Hub — 信息监控
场景7: 关键词监控、新闻/X动态追踪、告警格式化
"""
import os
import logging
import sqlite3

from src.execution._utils import normalize_monitor_text
from src.notify_style import format_announcement

logger = logging.getLogger(__name__)

# 内存上限
MAX_MONITORS = 200
MAX_SEEN_DIGESTS = 5000


class MonitorManager:
    """信息监控管理器"""

    def __init__(self, news_fetcher=None, db_path=None):
        self.news_fetcher = news_fetcher
        self.db_path = db_path
        self._monitors: list = []
        self._seen_digests: set = set()

    def add_monitor(self, keyword=None, source="news") -> dict:
        k = str(keyword or "").strip()
        if not k:
            return {"success": False, "error": "关键词不能为空"}
        self._monitors.append({"keyword": k, "source": source})
        if len(self._monitors) > MAX_MONITORS:
            self._monitors = self._monitors[-MAX_MONITORS:]
        return {"success": True, "keyword": k, "source": source}

    def list_monitors(self) -> list:
        try:
            from src.execution._db import get_conn
            with get_conn(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM monitors ORDER BY id DESC").fetchall()
                return [dict(r) for r in rows]
        except Exception as e:  # noqa: F841
            return []

    def remove_monitor(self, keyword=None) -> dict:
        k = str(keyword or "").strip()
        if not k:
            return {"success": False, "error": "关键词不能为空"}
        before = len(self._monitors)
        self._monitors = [m for m in self._monitors if m.get("keyword") != k]
        removed = before - len(self._monitors)
        return {"success": True, "removed": removed}

    def _is_low_value_item(self, title, source="") -> bool:
        """过滤低价值监控项"""
        t = str(title or "").lower()
        low_value_patterns = ["广告", "推广", "sponsored", "ad ", "promo"]
        return any(p in t for p in low_value_patterns)

    def _clean_title(self, title, source="") -> str:
        return str(title or "").strip()

    def _curate_items(self, items=None, limit=10) -> list:
        curated = []
        seen_titles = set()
        for item in (items or []):
            title = item.get("title", "")
            source = item.get("source", "")
            url = item.get("url", "")
            clean_title = self._clean_title(title, source)
            normalized = normalize_monitor_text(clean_title)
            if not normalized or normalized in seen_titles:
                continue
            seen_titles.add(normalized)
            if self._is_low_value_item(title, source):
                continue
            curated.append({
                "title": clean_title,
                "source": source,
                "url": url,
                "digest_key": normalized,
            })
            if len(curated) >= limit:
                break
        return curated

    async def run_monitors_once(self) -> list:
        """执行一轮监控检查，返回告警列表"""
        alerts = []
        fetch_count = int(os.getenv("OPS_MONITOR_FETCH_COUNT", "8"))
        alert_limit = int(os.getenv("OPS_MONITOR_ALERT_LIMIT", "3"))
        for monitor in self._monitors:
            keyword = monitor.get("keyword", "")
            source = monitor.get("source", "news")
            if source == "x_profile":
                # X profile 监控需要外部方法
                items = []
            elif self.news_fetcher:
                items = await self.news_fetcher.fetch_from_google_news_rss(
                    keyword, count=fetch_count
                )
            else:
                items = []
            curated = self._curate_items(items or [], limit=alert_limit)
            new_items = []
            for item in curated:
                digest_key = item.get("digest_key", "")
                if digest_key and digest_key not in self._seen_digests:
                    self._seen_digests.add(digest_key)
                    if len(self._seen_digests) > MAX_SEEN_DIGESTS:
                        to_keep = list(self._seen_digests)[-MAX_SEEN_DIGESTS // 2:]
                        self._seen_digests = set(to_keep)
                    new_items.append(item)
            if new_items:
                alerts.append({
                    "keyword": keyword,
                    "source": source,
                    "items": new_items,
                })
        return alerts

    @staticmethod
    def format_alert(alert: dict) -> str:
        """格式化单条监控告警"""
        source = alert.get("source", "news")
        keyword = alert.get("keyword", "")
        items = alert.get("items", [])
        if source == "x_profile":
            sections = []
            for idx, item in enumerate(items[:2], 1):
                title = item.get("title", "")
                entries = [f"{idx}. {title}"]
                url = item.get("url", "")
                if url:
                    entries.append(f"详情：{url}")
                sections.append((f"【@{keyword}】", entries))
            return format_announcement(
                title="OpenClaw「X 快讯」",
                intro=f"检测到 @{keyword} 有新的公开动态。",
                sections=sections,
            )
        sections = []
        for idx, item in enumerate(items[:3], 1):
            source_name = item.get("source", "")
            title = item.get("title", "")
            entry = f"{idx}. {title}"
            if source_name:
                entry += f"（来源：{source_name}）"
            entries = [entry]
            url = item.get("url", "")
            if url:
                entries.append(f"详情：{url}")
            sections.append((f"【第 {idx} 条】", entries))
        return format_announcement(
            title=f"OpenClaw「资讯快讯」{keyword}",
            intro=f"本轮监控命中 {len(items[:3])} 条新增资讯。",
            sections=sections,
        )
