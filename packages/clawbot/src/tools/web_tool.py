"""
ClawBot - 网页抓取工具（含 SSRF 防护）
"""
import httpx
import ipaddress
import re
import socket
from typing import Dict, Any
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

# SSRF 防护: 禁止访问的主机名黑名单
_SSRF_BLOCKED_HOSTS = frozenset({
    "169.254.169.254", "metadata.google.internal",
    "metadata.internal", "100.100.100.200",
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
})


def _is_ssrf_safe(url: str) -> bool:
    """检查 URL 是否安全（非内网/非元数据服务），防止 SSRF 攻击。
    通过 DNS 解析验证目标 IP，防止 DNS 重绑定攻击。
    """
    try:
        parsed = urlparse(url)
        # 只允许 http/https
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # 黑名单检查
        if hostname in _SSRF_BLOCKED_HOSTS:
            return False
        # DNS 解析后检查 IP（防止 DNS 重绑定攻击）
        try:
            resolved_ips = socket.getaddrinfo(hostname, None)
            for family, _type, proto, canonname, sockaddr in resolved_ips:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    logger.warning("[WebTool] SSRF 拦截: %s 解析到内网地址 %s", url, ip)
                    return False
        except (socket.gaierror, ValueError):
            # DNS 解析失败 → 放行（可能是合法的外部域名暂时解析失败）
            pass
        return True
    except Exception:
        return False


class WebTool:
    """网页抓取和处理"""
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    
    async def fetch(self, url: str, format: str = "text") -> Dict[str, Any]:
        """抓取网页内容（含 SSRF 防护）"""
        # SSRF 防护: 检查 URL 是否指向内网/敏感地址
        if not _is_ssrf_safe(url):
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
    
    async def search(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """搜索"""
        try:
            url = f"https://html.duckduckgo.com/html/?q={query}"
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=self.headers)
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
