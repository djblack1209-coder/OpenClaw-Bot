"""
ClawBot - 网页抓取工具（含 SSRF 防护）
"""
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

# 从统一的安全模块导入 SSRF 检查函数
from src.core.security import check_ssrf
from src.http_client import ResilientHTTPClient

logger = logging.getLogger(__name__)

# 模块级 HTTP 客户端（带重试 + 熔断）— 仅用于搜索
_http = ResilientHTTPClient(timeout=30, name="web_search")


class WebTool:
    """网页抓取和处理"""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

    async def fetch(self, url: str, format: str = "text") -> dict[str, Any]:
        """抓取网页内容（含 SSRF 防护）"""
        # SSRF 防护: 检查 URL 是否指向内网/敏感地址
        if not check_ssrf(url):
            return {"success": False, "error": "URL 安全检查未通过（禁止访问内网地址）"}
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()

                html = response.text
                soup = BeautifulSoup(html, 'html.parser')

                for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                    tag.decompose()

                title = soup.title.string if soup.title else ""

                if format == "html":
                    return {"success": True, "url": url, "title": title, "content": str(soup)[:10000]}
                else:
                    text = soup.get_text(separator='\n', strip=True)
                    text = re.sub(r'\n{3,}', '\n\n', text)
                    return {"success": True, "url": url, "title": title, "content": text[:10000]}

        except httpx.TimeoutException as e:  # noqa: F841
            return {"success": False, "error": "请求超时"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def search(self, query: str, num_results: int = 5) -> dict[str, Any]:
        """搜索"""
        try:
            url = f"https://html.duckduckgo.com/html/?q={query}"
            response = await _http.get(url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')

            results = []
            for result in soup.find_all('div', class_='result')[:num_results]:
                title_tag = result.find('a', class_='result__a')
                snippet_tag = result.find('a', class_='result__snippet')
                if title_tag:
                    results.append({
                        "title": title_tag.get_text(strip=True),
                        "url": title_tag.get('href', ''),
                        "snippet": snippet_tag.get_text(strip=True) if snippet_tag else ""
                    })

            return {"success": True, "query": query, "results": results, "count": len(results)}
        except Exception as e:
            return {"success": False, "error": str(e)}
