"""
ClawBot - 新闻抓取模块
抓取 Google、Nvidia、Claude、马斯克相关新闻
"""
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

from src.notify_style import format_digest


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
            title=f"OpenClaw「科技早报」{datetime.now().strftime('%Y年%m月%d日')}",
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
