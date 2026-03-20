"""
Social — X (Twitter) 集成层

基于现有 social_browser_worker.py 的 X 平台操作封装。
将 execution_hub.py 中散落的 X 相关方法统一到此模块。

支持:
- 发布推文 (通过 browser worker)
- 回复推文
- 监控 X 动态 (通过 Jina reader)
- 推文分析和转发策略
"""
import logging
import os
import json
import hashlib
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


async def fetch_x_profile_posts(
    handle: str,
    count: int = 8,
    worker_fn=None,
) -> List[Dict]:
    """获取 X 用户最近的公开动态

    优先使用 Jina reader (免费, 无需登录),
    回退到 browser worker (需要登录态)
    """
    handle = str(handle or "").strip().lstrip("@")
    if not handle:
        return []

    # 方式1: Jina reader (免费)
    items = await _fetch_via_jina(handle, count)
    if items:
        return items

    # 方式2: browser worker
    if worker_fn:
        try:
            result = worker_fn("research", {
                "query": f"from:@{handle}",
                "platform": "x",
                "count": count,
            })
            return result.get("items", []) if isinstance(result, dict) else []
        except Exception as e:
            logger.debug(f"[X.fetch] worker fallback failed: {e}")

    return []


async def _fetch_via_jina(handle: str, count: int) -> List[Dict]:
    """通过 Jina reader 抓取 X 动态"""
    import httpx
    url = f"https://r.jina.ai/https://x.com/{handle}"
    headers = {"Accept": "text/plain"}
    jina_key = os.getenv("JINA_API_KEY", "")
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return []
            text = resp.text
            return _parse_jina_x_output(text, handle, count)
    except Exception as e:
        logger.debug(f"[X.jina] {handle} failed: {e}")
        return []


def _parse_jina_x_output(text: str, handle: str, count: int) -> List[Dict]:
    """解析 Jina reader 返回的 X 页面文本"""
    items = []
    lines = text.strip().splitlines()
    current_text = []

    for line in lines:
        line = line.strip()
        if not line:
            if current_text:
                content = " ".join(current_text)
                if len(content) > 20:
                    items.append({
                        "title": content[:200],
                        "source": f"@{handle}",
                        "url": f"https://x.com/{handle}",
                        "digest_key": hashlib.md5(content[:100].encode()).hexdigest(),
                    })
                current_text = []
            continue
        current_text.append(line)

    if current_text:
        content = " ".join(current_text)
        if len(content) > 20:
            items.append({
                "title": content[:200],
                "source": f"@{handle}",
                "url": f"https://x.com/{handle}",
            })

    return items[:count]


async def publish_x_post(
    content: str,
    worker_fn=None,
    image_path: str = None,
) -> Dict:
    """发布推文"""
    if not content:
        return {"success": False, "error": "内容不能为空"}
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置"}
    try:
        payload = {"text": content}
        if image_path:
            payload["image"] = image_path
        result = worker_fn("publish_x", payload)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"[X.publish] failed: {e}")
        return {"success": False, "error": str(e)}


async def reply_to_x_post(
    tweet_url: str,
    reply_text: str,
    worker_fn=None,
) -> Dict:
    """回复推文"""
    if not tweet_url or not reply_text:
        return {"success": False, "error": "URL 和回复内容不能为空"}
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置"}
    try:
        result = worker_fn("reply_x", {
            "url": tweet_url,
            "text": reply_text,
        })
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"[X.reply] failed: {e}")
        return {"success": False, "error": str(e)}
