"""
Social — 小红书 (Xiaohongshu) 集成层

基于现有 social_browser_worker.py 的小红书平台操作封装。
将 execution_hub.py 中散落的 XHS 相关方法统一到此模块。

支持:
- 发布笔记 (通过 browser worker)
- 回复评论
- 更新个人资料
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


async def publish_xhs_article(
    title: str,
    body: str,
    worker_fn=None,
    image_path: str = None,
) -> Dict:
    """发布小红书笔记"""
    if not title or not body:
        return {"success": False, "error": "标题和正文不能为空"}
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置"}
    try:
        payload = {"title": title, "body": body}
        if image_path:
            payload["image"] = image_path
        result = worker_fn("publish_xhs", payload)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"[XHS.publish] failed: {e}")
        return {"success": False, "error": str(e)}


async def reply_to_xhs_comment(
    note_url: str,
    reply_text: str,
    worker_fn=None,
) -> Dict:
    """回复小红书评论"""
    if not note_url or not reply_text:
        return {"success": False, "error": "URL 和回复内容不能为空"}
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置"}
    try:
        result = worker_fn("reply_xhs", {
            "url": note_url,
            "text": reply_text,
        })
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"[XHS.reply] failed: {e}")
        return {"success": False, "error": str(e)}


async def update_xhs_profile(
    bio: str = None,
    worker_fn=None,
) -> Dict:
    """更新小红书个人资料"""
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置"}
    try:
        payload = {}
        if bio:
            payload["bio"] = bio
        result = worker_fn("update_xhs_profile", payload)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"[XHS.profile] failed: {e}")
        return {"success": False, "error": str(e)}
