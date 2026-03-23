"""
ClawBot - 新闻抓取模块 v2.0
抓取 Google、Nvidia、Claude、马斯克相关新闻

v2.0 变更 (2026-03-23):
  - 搬运 feedparser (9.8k⭐) 替代 regex XML 解析 (更鲁棒，支持 Atom/RSS 1.0/RSS 2.0)
  - 新增 RSS 源: TechCrunch / Hacker News / 36氪 / 少数派
  - 三级降级: feedparser RSS → Google News RSS (regex) → Bing 搜索
"""
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

from src.notify_style import format_digest

# ── feedparser 可选依赖 ──
_HAS_FEEDPARSER = False
try:
    import feedparser
    _HAS_FEEDPARSER = True
except ImportError:
    feedparser = None  # type: ignore[assignment]

import logging
from src.utils import now_et
logger = logging.getLogger(__name__)

# ── 内置 RSS 源（无需 API Key）──
RSS_FEEDS: Dict[str, List[str]] = {
    "tech_en": [
        "https://hnrss.org/newest?points=100",                # Hacker News 100+ 分
        "https://feeds.feedburner.com/TechCrunch/",            # TechCrunch
        "https://www.theverge.com/rss/index.xml",              # The Verge
    ],
    "tech_cn": [
        "https://36kr.com/feed",                               # 36氪
        "https://sspai.com/feed",                              # 少数派
    ],
    "ai": [
        "https://blog.google/technology/ai/rss/",             # Google AI Blog
        "https://openai.com/blog/rss/",                        # OpenAI Blog
    ],
    "finance": [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",  # S&P 500
    ],
}


class NewsFetcher:
    """新闻抓取器"""
    
    # 搜索关键词（扩展覆盖面）
    TOPICS = {
        "google": ["Google AI", "Google Gemini", "谷歌"],
        "nvidia": ["Nvidia", "英伟达", "CUDA", "Jensen Huang"],
        "claude": ["Anthropic", "Claude AI", "Claude 3"],
        "musk": ["Elon Musk", "马斯克", "Tesla AI", "xAI", "Grok"],
        "market": ["stock market today", "S&P 500", "美股行情"],
        "fed": ["Federal Reserve", "美联储", "interest rate decision"],
        "crypto": ["Bitcoin", "比特币", "Ethereum", "加密货币"],
    }
    
    def __init__(self, serpapi_key: Optional[str] = None):
        """
        初始化
        
        Args:
            serpapi_key: SerpAPI key (可选，用于 Google 搜索)
        """
        self.serpapi_key = serpapi_key
        self._seen_titles: set = set()  # 跨主题去重

    async def fetch_rss_feed(self, feed_url: str, count: int = 5) -> List[Dict[str, str]]:
        """feedparser 解析 RSS/Atom feed (v2.0 新增).

        搬运 feedparser (9.8k⭐) — 支持 RSS 0.9/1.0/2.0 + Atom 0.3/1.0
        比 regex XML 解析更鲁棒，能处理 CDATA, namespace, encoding 等边缘情况。
        """
        if not _HAS_FEEDPARSER:
            # 降级: 直接 regex 解析
            return await self._fetch_rss_regex(feed_url, count)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(feed_url, headers={
                    "User-Agent": "OpenClaw-NewsBot/2.0 (feedparser)"
                })
                resp.raise_for_status()

            loop = asyncio.get_event_loop()
            parsed = await loop.run_in_executor(
                None, feedparser.parse, resp.text
            )

            items = []
            for entry in parsed.entries[:count]:
                title = entry.get("title", "").strip()
                url = entry.get("link", "").strip()
                source = parsed.feed.get("title", "").strip()
                published = entry.get("published", entry.get("updated", ""))
                if title and url and title not in self._seen_titles:
                    self._seen_titles.add(title)
                    items.append({
                        "title": title,
                        "url": url,
                        "source": source,
                        "published": published[:16] if published else "",
                    })
            return items
        except Exception as e:
            logger.warning(f"[news_fetcher] feedparser RSS 失败 ({feed_url}): {e}")
            return []

    async def fetch_by_category(self, category: str, count: int = 5) -> List[Dict[str, str]]:
        """按分类抓取 RSS 新闻 (v2.0 新增)

        category: tech_en | tech_cn | ai | finance
        """
        feeds = RSS_FEEDS.get(category, [])
        if not feeds:
            return []
        tasks = [self.fetch_rss_feed(url, count) for url in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        items = []
        for r in results:
            if isinstance(r, list):
                items.extend(r)
        # 去重+截断
        seen = set()
        deduped = []
        for item in items:
            t = item.get("title", "")
            if t and t not in seen:
                seen.add(t)
                deduped.append(item)
        return deduped[:count]

    async def _fetch_rss_regex(self, url: str, count: int = 5) -> List[Dict[str, str]]:
        """feedparser 不可用时的 regex 降级"""
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            items_raw = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
            news = []
            for item in items_raw[:count]:
                t = re.search(r'<title>(.*?)</title>', item)
                l = re.search(r'<link>(.*?)</link>', item)
                s = re.search(r'<source[^>]*>(.*?)</source>', item)
                if t and l:
                    news.append({
                        "title": t.group(1).strip(),
                        "url": l.group(1).strip(),
                        "source": s.group(1) if s else "",
                    })
            return news
        except Exception:
            return []

    @staticmethod
    def format_news_items(items: List[Dict[str, str]], max_items: int = 3, title_max_len: int = 72) -> List[str]:
        """将新闻条目排成更适合消息推送的公告式样式。"""
        lines: List[str] = []
        for idx, item in enumerate(items[:max_items], 1):
            title = re.sub(r"\s+", " ", str(item.get("title", "") or "").strip())
            source = re.sub(r"\s+", " ", str(item.get("source", "") or "").strip())
            url = str(item.get("url", "") or "").strip()

            if len(title) > title_max_len:
                title = title[: title_max_len - 3].rstrip() + "..."

            headline = f"{idx}. {title}"
            if source:
                headline += f"（来源：{source}）"
            lines.append(headline)
            if url:
                lines.append(f"   详情：{url}")

        return lines
    
    async def fetch_from_bing(self, query: str, count: int = 5) -> List[Dict[str, str]]:
        """从 Bing 搜索新闻"""
        try:
            url = "https://www.bing.com/news/search"
            params = {
                "q": query,
                "qft": "interval=7",  # 最近7天
                "form": "PTFTNR"
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, params=params, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                })
                
                if response.status_code != 200:
                    return []
                
                html = response.text
                
                # 简单解析新闻标题和链接
                news = []
                # 匹配新闻卡片
                pattern = r'<a[^>]*class="title"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
                matches = re.findall(pattern, html)
                
                for url, title in matches[:count]:
                    if title.strip():
                        news.append({
                            "title": title.strip(),
                            "url": url,
                            "source": "Bing"
                        })
                
                return news
                
        except Exception as e:
            return []
    
    async def fetch_from_google_news_rss(self, query: str, count: int = 5) -> List[Dict[str, str]]:
        """从 Google News RSS 获取新闻"""
        try:
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                })
                
                if response.status_code != 200:
                    return []
                
                # 解析 RSS
                news = []
                items = re.findall(r'<item>(.*?)</item>', response.text, re.DOTALL)
                
                for item in items[:count]:
                    title_match = re.search(r'<title>(.*?)</title>', item)
                    link_match = re.search(r'<link>(.*?)</link>', item)
                    source_match = re.search(r'<source[^>]*>(.*?)</source>', item)
                    
                    if title_match and link_match:
                        news.append({
                            "title": title_match.group(1).strip(),
                            "url": link_match.group(1).strip(),
                            "source": source_match.group(1) if source_match else "Google News"
                        })
                
                return news
                
        except Exception as e:
            return []
    
    async def fetch_topic_news(self, topic: str, count: int = 3) -> List[Dict[str, str]]:
        """获取特定主题的新闻（跨主题去重）"""
        keywords = self.TOPICS.get(topic, [topic])
        all_news = []
        
        for keyword in keywords[:2]:  # 每个主题取前2个关键词
            # 优先使用 Google News RSS
            news = await self.fetch_from_google_news_rss(keyword, count)
            if not news:
                news = await self.fetch_from_bing(keyword, count)
            
            all_news.extend(news)
            
            if len(all_news) >= count:
                break
            
            await asyncio.sleep(0.5)  # 避免请求过快
        
        # 去重（含跨主题去重）
        unique_news = []
        for item in all_news:
            title = item["title"].strip()
            # 标题相似度去重：取前30字符作为指纹
            fingerprint = re.sub(r'\s+', '', title[:30].lower())
            if fingerprint not in self._seen_titles and title not in {n["title"] for n in unique_news}:
                self._seen_titles.add(fingerprint)
                unique_news.append(item)
        
        # 限制去重缓存大小
        if len(self._seen_titles) > 500:
            self._seen_titles = set(list(self._seen_titles)[-200:])
        
        return unique_news[:count]
    
    async def generate_morning_report(self) -> str:
        """生成早报（含市场/宏观/加密板块）"""
        # 重置跨主题去重缓存
        self._seen_titles.clear()

        section_titles = [
            ("market", "【美股市场】"),
            ("fed", "【美联储 / 宏观】"),
            ("google", "【Google / AI】"),
            ("nvidia", "【Nvidia】"),
            ("claude", "【Anthropic / Claude】"),
            ("musk", "【马斯克 / xAI】"),
            ("crypto", "【加密货币】"),
        ]

        sections = []
        for topic, heading in section_titles:
            news = await self.fetch_topic_news(topic, count=3)
            entries = self.format_news_items(news, max_items=3, title_max_len=74) if news else ["- 暂无新增"]
            sections.append((heading, entries))
            await asyncio.sleep(1)

        return format_digest(
            title=f"OpenClaw「科技早报」{now_et().strftime('%Y年%m月%d日')}",
            intro="今日聚焦美股市场、宏观政策、AI科技、加密货币四大主线，按主题整理如下。",
            sections=sections,
            footer="更多详情可直接回复对应主题，或打开上方链接查看原文。",
        )


# 测试
if __name__ == "__main__":
    async def test():
        fetcher = NewsFetcher()
        report = await fetcher.generate_morning_report()
        print(report)
    
    asyncio.run(test())
