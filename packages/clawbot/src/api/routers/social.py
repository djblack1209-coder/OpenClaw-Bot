"""Social media endpoints — status, topics, compose, publish, autopilot"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Path, Query
from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC
from ..schemas import SocialStatus, SocialPublishRequest, WSMessageType
from .ws import push_event

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/social/status", response_model=SocialStatus)
def get_social_status():
    """获取社交媒体状态"""
    try:
        return ClawBotRPC._rpc_social_status()
    except Exception as e:
        logger.exception("获取社交媒体状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/browser-status", response_model=Dict[str, Any])
def get_social_browser_status():
    """获取 X / 小红书浏览器会话状态"""
    try:
        return ClawBotRPC._rpc_social_browser_status()
    except Exception as e:
        logger.exception("获取社媒浏览器状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/analytics", response_model=Dict[str, Any])
def get_social_analytics(days: int = Query(default=7, ge=1, le=30)):
    """获取社媒分析面板数据"""
    try:
        return ClawBotRPC._rpc_social_analytics(days=days)
    except Exception as e:
        logger.exception("获取社媒分析数据失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/topics", response_model=Dict[str, Any])
async def discover_topics(count: int = Query(default=10, ge=1, le=50)):
    """发现热门话题"""
    try:
        return await ClawBotRPC._rpc_social_discover_topics(count=count)
    except Exception as e:
        logger.exception("发现话题失败")
        raise HTTPException(status_code=502, detail=_safe_error(e)) from e


@router.post("/social/compose", response_model=Dict[str, Any])
async def compose_content(
    topic: str,
    platform: str = "x",
    persona: str = "default",
):
    """AI 内容生成 — 返回可发布的文本供审核。

    完整管道：人设加载 → 策略推导 → 内容创作。
    搬运 content_strategy.py 的三步管道。
    """
    try:
        return await ClawBotRPC._rpc_social_compose(
            topic=topic,
            platform=platform,
            persona_name=persona,
        )
    except Exception as e:
        logger.exception("AI 内容生成失败 (topic=%s, platform=%s)", topic, platform)
        raise HTTPException(status_code=502, detail=_safe_error(e)) from e


@router.post("/social/publish", response_model=Dict[str, Any])
async def publish_content(req: SocialPublishRequest):
    """发布内容到社交平台（通过浏览器 worker）。

    需要浏览器 worker 已配置，否则返回明确的错误消息。
    """
    try:
        result = await ClawBotRPC._rpc_social_publish(
            platform=req.platform,
            content=req.content,
        )

        # Push social published event via WebSocket (best-effort)
        try:
            if result.get("success"):
                push_event(WSMessageType.SOCIAL_PUBLISHED, {
                    "platform": req.platform,
                    "content_preview": req.content[:120],
                    "success": True,
                })
        except Exception as e:
            logger.warning("[Social] 发布结果WS推送失败: %s", e)

        return result
    except Exception as e:
        logger.exception("社交内容发布失败 (platform=%s)", req.platform)
        raise HTTPException(status_code=502, detail=_safe_error(e)) from e


@router.post("/social/research", response_model=Dict[str, Any])
async def deep_research(topic: str, count: int = Query(default=10, ge=1, le=50)):
    """深度话题研究 — 抓取平台数据并聚合洞察"""
    try:
        return await ClawBotRPC._rpc_social_research(topic=topic, count=count)
    except Exception as e:
        logger.exception("深度话题研究失败 (topic=%s)", topic)
        raise HTTPException(status_code=502, detail=_safe_error(e)) from e


@router.get("/social/metrics", response_model=Dict[str, Any])
async def get_metrics():
    """社交指标/分析 — 粉丝数、互动率等"""
    try:
        return await ClawBotRPC._rpc_social_metrics()
    except Exception as e:
        logger.exception("获取社交指标失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/personas", response_model=Dict[str, Any])
def list_personas():
    """列出可用的社交人设（data/social_personas/）"""
    try:
        # RPC 返回 list，需要包裹为 dict 以匹配 response_model
        personas = ClawBotRPC._rpc_social_personas()
        return {"personas": personas if isinstance(personas, list) else []}
    except Exception as e:
        logger.exception("列出社交人设失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/calendar", response_model=Dict[str, Any])
async def get_calendar(days: int = Query(default=7, ge=1, le=30)):
    """内容日历生成 — 热门话题映射为逐日计划"""
    try:
        return await ClawBotRPC._rpc_social_calendar(days=days)
    except Exception as e:
        logger.exception("内容日历生成失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/generate-image", response_model=Dict[str, Any])
async def gen_image(prompt: str):
    """通过 ComfyUI（本地）或云端降级生成图片"""
    try:
        return await ClawBotRPC._rpc_generate_image(prompt)
    except Exception as e:
        logger.exception("图片生成失败")
        raise HTTPException(status_code=502, detail=_safe_error(e)) from e


@router.post("/social/generate-persona-photo", response_model=Dict[str, Any])
async def gen_persona_photo(
    persona: str = "default",
    scenario: str = "working in a cafe",
    mood: str = "natural",
):
    """生成与人设一致的社交媒体照片"""
    try:
        return await ClawBotRPC._rpc_generate_persona_photo(persona, scenario, mood)
    except Exception as e:
        logger.exception("人设照片生成失败 (persona=%s)", persona)
        raise HTTPException(status_code=502, detail=_safe_error(e)) from e


# ──────────────────────────────────────────────
#  Autopilot — 社交自动驾驶
# ──────────────────────────────────────────────


@router.get("/social/autopilot/status", response_model=Dict[str, Any])
def autopilot_status():
    """获取自动驾驶调度状态 — 运行中、任务列表、下次动作"""
    try:
        return ClawBotRPC._rpc_autopilot_status()
    except Exception as e:
        logger.exception("获取自动驾驶状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/autopilot/start", response_model=Dict[str, Any])
def autopilot_start():
    """启动社交自动驾驶调度器（5 个定时任务）"""
    try:
        result = ClawBotRPC._rpc_autopilot_start()

        # Push autopilot event via WebSocket (best-effort)
        try:
            push_event(WSMessageType.AUTOPILOT_EVENT, {
                "action": "start",
                "status": result.get("status", ""),
            })
        except Exception as e:
            logger.warning("[Social] Autopilot启动事件推送失败: %s", e)

        return result
    except Exception as e:
        logger.exception("启动自动驾驶失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/autopilot/stop", response_model=Dict[str, Any])
def autopilot_stop():
    """停止社交自动驾驶调度器"""
    try:
        result = ClawBotRPC._rpc_autopilot_stop()

        # Push autopilot event via WebSocket (best-effort)
        try:
            push_event(WSMessageType.AUTOPILOT_EVENT, {
                "action": "stop",
                "status": result.get("status", ""),
            })
        except Exception as e:
            logger.warning("[Social] Autopilot停止事件推送失败: %s", e)

        return result
    except Exception as e:
        logger.exception("停止自动驾驶失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/autopilot/trigger/{job_id}", response_model=Dict[str, Any])
def autopilot_trigger(job_id: str):
    """手动触发特定的自动驾驶任务。

    有效 job_id: morning_scan, noon_engage, evening_produce,
    night_publish, late_review。
    """
    try:
        result = ClawBotRPC._rpc_autopilot_trigger(job_id)

        # Push autopilot event via WebSocket (best-effort)
        try:
            push_event(WSMessageType.AUTOPILOT_EVENT, {
                "action": "trigger",
                "job_id": job_id,
                "success": result.get("success", not result.get("error")),
            })
        except Exception as e:
            logger.warning("[Social] Autopilot触发事件推送失败: %s", e)

        return result
    except Exception as e:
        logger.exception("手动触发自动驾驶任务失败 (job_id=%s)", job_id)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


# ──────────────────────────────────────────────
#  Drafts — 草稿管理
# ──────────────────────────────────────────────


@router.get("/social/drafts", response_model=Dict[str, Any])
def list_drafts():
    """列出自动驾驶状态中的所有草稿"""
    try:
        return ClawBotRPC._rpc_social_drafts()
    except Exception as e:
        logger.exception("列出草稿失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.patch("/social/drafts/{index}", response_model=Dict[str, Any])
def update_draft(index: int = Path(ge=0, description="草稿索引"), text: str = ""):
    """更新草稿文本内容"""
    try:
        return ClawBotRPC._rpc_social_draft_update(index, text)
    except Exception as e:
        logger.exception("更新草稿失败 (index=%d)", index)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.delete("/social/drafts/{index}", response_model=Dict[str, Any])
def delete_draft(index: int = Path(ge=0, description="草稿索引")):
    """按索引删除草稿"""
    try:
        return ClawBotRPC._rpc_social_draft_delete(index)
    except Exception as e:
        logger.exception("删除草稿失败 (index=%d)", index)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/drafts/{index}/publish", response_model=Dict[str, Any])
async def publish_draft(index: int = Path(ge=0, description="草稿索引")):
    """立即发布指定草稿"""
    try:
        result = await ClawBotRPC._rpc_social_draft_publish(index)

        # Push social published event via WebSocket (best-effort)
        try:
            if result.get("success"):
                push_event(WSMessageType.SOCIAL_PUBLISHED, {
                    "platform": result.get("platform", ""),
                    "draft_index": index,
                    "success": True,
                    "source": "draft",
                })
        except Exception as e:
            logger.warning("[Social] 草稿发布事件推送失败: %s", e)

        return result
    except Exception as e:
        logger.exception("发布草稿失败 (index=%d)", index)
        raise HTTPException(status_code=502, detail=_safe_error(e)) from e


# ──────────────────────────────────────────────
#  Cookie 健康状态
# ──────────────────────────────────────────────


@router.get("/social/cookie-status")
async def get_social_cookie_status():
    """获取社媒平台 Cookie 健康状态"""
    from src.xianyu.cookie_refresher import CookieHealthMonitor
    monitor = CookieHealthMonitor()
    try:
        all_status = await monitor.check_all_cookies()
        return {
            "success": True,
            "data": {
                "x": all_status.get("x", {}),
                "xhs": all_status.get("xhs", {}),
            }
        }
    except Exception as e:
        logger.error("检查社媒 Cookie 状态失败: %s", e)
        return {"success": False, "error": str(e)}
