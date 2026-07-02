"""Social media endpoints — status, topics, compose, publish, autopilot"""

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Path, Query

from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC
from ..schemas import SocialPublishRequest, SocialStatus, WSMessageType
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


@router.get("/social/browser-status", response_model=dict[str, Any])
def get_social_browser_status():
    """获取 X / 小红书浏览器会话状态"""
    try:
        return ClawBotRPC._rpc_social_browser_status()
    except Exception as e:
        logger.exception("获取社媒浏览器状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/browser-control", response_model=dict[str, Any])
def control_social_browser(
    action: str,
    platform: str = "all",
):
    """执行安全浏览器控制动作：打开/登录/刷新状态，不允许发布或回复。"""
    try:
        return ClawBotRPC._rpc_social_browser_control(action=action, platform=platform)
    except Exception as e:
        logger.exception("社媒浏览器控制失败 (action=%s, platform=%s)", action, platform)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/ops-workspace", response_model=dict[str, Any])
def get_social_ops_workspace():
    """获取 X / 小红书 / 闲鱼统一浏览器运营工作台。"""
    try:
        return ClawBotRPC._rpc_social_ops_workspace()
    except Exception as e:
        logger.exception("获取社媒运营工作台失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/persona-review", response_model=dict[str, Any])
def get_social_persona_review():
    """获取热点抽象号人设提案与确认状态。"""
    try:
        return ClawBotRPC._rpc_social_persona_review()
    except Exception as e:
        logger.exception("获取社媒人设确认状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/persona-review", response_model=dict[str, Any])
def review_social_persona(
    payload: dict[str, Any] | None = Body(default=None),
    approved: bool = True,
    reviewer: str = "owner",
    notes: str = "",
):
    """确认或打回热点抽象号人设；优先读取 JSON body，不触发任何发布。"""
    try:
        body = payload if isinstance(payload, dict) else {}
        return ClawBotRPC._rpc_social_persona_review_update(
            approved=bool(body.get("approved", approved)),
            reviewer=str(body.get("reviewer", reviewer) or "owner"),
            notes=str(body.get("notes", notes) or ""),
        )
    except Exception as e:
        logger.exception("更新社媒人设确认状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/review-pack", response_model=dict[str, Any])
def get_social_review_pack(limit: int = Query(default=8, ge=1, le=12)):
    """获取待确认的人设 + X/小红书样稿包；只读，不发布。"""
    try:
        return ClawBotRPC._rpc_social_review_pack(limit=limit)
    except Exception as e:
        logger.exception("获取社媒审核包失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/extension/status", response_model=dict[str, Any])
def get_social_extension_status():
    """获取 Chrome 社媒运营插件状态，供 App/Telegram 中控展示。"""
    try:
        return ClawBotRPC._rpc_social_extension_status()
    except Exception as e:
        logger.exception("获取 Chrome 社媒插件状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/extension/status", response_model=dict[str, Any])
def update_social_extension_status(payload: dict[str, Any]):
    """接收 Chrome 社媒运营插件状态上报；只保存安全摘要，不触发发布。"""
    try:
        return ClawBotRPC._rpc_social_extension_status_update(payload)
    except Exception as e:
        logger.exception("更新 Chrome 社媒插件状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e



@router.post("/social/extension/strategy", response_model=dict[str, Any])
def update_social_extension_strategy(payload: dict[str, Any] | None = Body(default=None)):
    """从 App/Telegram 中控更新 no-code 运营打法；只改设置摘要，不触发发布。"""
    try:
        return ClawBotRPC._rpc_social_extension_strategy_update(payload or {})
    except Exception as e:
        logger.exception("更新 Chrome 插件 no-code 运营打法失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e

@router.post("/social/extension/page-probe", response_model=dict[str, Any])
def update_social_extension_page_probe(payload: dict[str, Any]):
    """保存 Chrome 插件页面填入点探测结果；只登记校准状态，不触发发布。"""
    try:
        return ClawBotRPC._rpc_social_extension_page_probe_update(payload)
    except Exception as e:
        logger.exception("更新 Chrome 插件页面填入点探测失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/extension/trends", response_model=dict[str, Any])
def get_social_extension_trends(
    platform: str = Query(default="x"),
    limit: int = Query(default=8, ge=1, le=12),
):
    """获取 Chrome 插件热点池；只读候选选题，不触发发布或互动。"""
    try:
        return ClawBotRPC._rpc_social_extension_trends(platform=platform, limit=limit)
    except Exception as e:
        logger.exception("获取 Chrome 插件热点池失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/extension/drafts", response_model=dict[str, Any])
def create_social_extension_draft(payload: dict[str, Any]):
    """把 Chrome 插件当前页信号生成待审草稿；只进审核队列，不触发发布。"""
    try:
        return ClawBotRPC._rpc_social_extension_draft_create(payload)
    except Exception as e:
        logger.exception("创建 Chrome 插件待审草稿失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.patch("/social/extension/drafts/{draft_id}", response_model=dict[str, Any])
def update_social_extension_draft(
    draft_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    text: str = "",
    title: str = "",
):
    """插件内编辑待审草稿；优先读取 JSON body，兼容旧 query 参数，不触发发布。"""
    try:
        body = payload if isinstance(payload, dict) else {}
        return ClawBotRPC._rpc_social_extension_draft_update(
            draft_id,
            text=str(body.get("text", text) or ""),
            title=str(body.get("title", title) or ""),
        )
    except Exception as e:
        logger.exception("更新 Chrome 插件待审草稿失败 (draft_id=%s)", draft_id)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/extension/drafts/{draft_id}/review", response_model=dict[str, Any])
def review_social_extension_draft(
    draft_id: str,
    approved: bool = True,
    reviewer: str = "owner",
):
    """插件内确认/打回待审草稿；确认不等于发布。"""
    try:
        return ClawBotRPC._rpc_social_extension_draft_review(draft_id, approved=approved, reviewer=reviewer)
    except Exception as e:
        logger.exception("审核 Chrome 插件待审草稿失败 (draft_id=%s)", draft_id)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/extension/schedule", response_model=dict[str, Any])
def get_social_extension_schedule(limit: int = Query(default=12, ge=1, le=100)):
    """读取 Chrome 插件排程队列；只用于提醒和最终确认，不触发外发。"""
    try:
        return ClawBotRPC._rpc_social_extension_schedule_queue(limit=limit)
    except Exception as e:
        logger.exception("获取 Chrome 插件排程队列失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/extension/drafts/{draft_id}/schedule", response_model=dict[str, Any])
def schedule_social_extension_draft(
    draft_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    scheduled_at: str = "",
    reviewer: str = "owner",
):
    """插件内把已确认草稿加入待发布排程；只排队，不触发外发。"""
    try:
        body = payload if isinstance(payload, dict) else {}
        return ClawBotRPC._rpc_social_extension_draft_schedule(
            draft_id,
            scheduled_at=str(body.get("scheduled_at", scheduled_at) or ""),
            reviewer=str(body.get("reviewer", reviewer) or "owner"),
        )
    except Exception as e:
        logger.exception("排程 Chrome 插件草稿失败 (draft_id=%s)", draft_id)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/extension/drafts/{draft_id}/final-confirm", response_model=dict[str, Any])
def final_confirm_social_extension_draft(
    draft_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    reviewer: str = "owner",
):
    """排程到点后的最终发布确认；只标记可手动发布，不触发外发。"""
    try:
        body = payload if isinstance(payload, dict) else {}
        return ClawBotRPC._rpc_social_extension_schedule_final_confirm(
            draft_id,
            reviewer=str(body.get("reviewer", reviewer) or "owner"),
        )
    except Exception as e:
        logger.exception("最终确认 Chrome 插件排程草稿失败 (draft_id=%s)", draft_id)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e




@router.get("/social/extension/growth-feedback", response_model=dict[str, Any])
def get_social_extension_growth_feedback(
    platform: str = Query(default="x"),
    limit: int = Query(default=6, ge=1, le=12),
):
    """读取 Chrome 插件增长复盘摘要；只读展示，不触发发布/评论/推广。"""
    try:
        return ClawBotRPC._rpc_social_extension_growth_feedback(platform=platform, limit=limit)
    except Exception as e:
        logger.exception("获取 Chrome 插件增长复盘摘要失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/extension/growth-drafts", response_model=dict[str, Any])
def create_social_extension_growth_drafts(payload: dict[str, Any] | None = Body(default=None)):
    """基于增长复盘生成下一批待审草稿；只进入审核队列，不触发发布/评论。"""
    try:
        body = payload if isinstance(payload, dict) else {}
        return ClawBotRPC._rpc_social_extension_growth_draft_batch(
            platform=str(body.get("platform") or "x"),
            limit=int(body.get("limit") or 3),
        )
    except Exception as e:
        logger.exception("基于增长复盘生成 Chrome 插件待审草稿失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/extension/performance", response_model=dict[str, Any])
def record_social_extension_performance(payload: dict[str, Any] | None = Body(default=None)):
    """记录 Chrome 插件只读表现快照；只做复盘，不触发推广/刷量/发布。"""
    try:
        return ClawBotRPC._rpc_social_extension_performance_record(payload or {})
    except Exception as e:
        logger.exception("记录 Chrome 插件表现快照失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/analytics", response_model=dict[str, Any])
def get_social_analytics(days: int = Query(default=7, ge=1, le=30)):
    """获取社媒分析面板数据"""
    try:
        return ClawBotRPC._rpc_social_analytics(days=days)
    except Exception as e:
        logger.exception("获取社媒分析数据失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/topics", response_model=dict[str, Any])
async def discover_topics(count: int = Query(default=10, ge=1, le=50)):
    """发现热门话题"""
    try:
        return await ClawBotRPC._rpc_social_discover_topics(count=count)
    except Exception as e:
        logger.exception("发现话题失败")
        raise HTTPException(status_code=502, detail=_safe_error(e)) from e


@router.post("/social/compose", response_model=dict[str, Any])
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


@router.post("/social/publish", response_model=dict[str, Any])
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


@router.post("/social/research", response_model=dict[str, Any])
async def deep_research(topic: str, count: int = Query(default=10, ge=1, le=50)):
    """深度话题研究 — 抓取平台数据并聚合洞察"""
    try:
        return await ClawBotRPC._rpc_social_research(topic=topic, count=count)
    except Exception as e:
        logger.exception("深度话题研究失败 (topic=%s)", topic)
        raise HTTPException(status_code=502, detail=_safe_error(e)) from e


@router.get("/social/metrics", response_model=dict[str, Any])
async def get_metrics():
    """社交指标/分析 — 粉丝数、互动率等"""
    try:
        return await ClawBotRPC._rpc_social_metrics()
    except Exception as e:
        logger.exception("获取社交指标失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/personas", response_model=dict[str, Any])
def list_personas():
    """列出可用的社交人设（data/social_personas/）"""
    try:
        # RPC 返回 list，需要包裹为 dict 以匹配 response_model
        personas = ClawBotRPC._rpc_social_personas()
        return {"personas": personas if isinstance(personas, list) else []}
    except Exception as e:
        logger.exception("列出社交人设失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/social/calendar", response_model=dict[str, Any])
async def get_calendar(days: int = Query(default=7, ge=1, le=30)):
    """内容日历生成 — 热门话题映射为逐日计划"""
    try:
        return await ClawBotRPC._rpc_social_calendar(days=days)
    except Exception as e:
        logger.exception("内容日历生成失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/generate-image", response_model=dict[str, Any])
async def gen_image(prompt: str):
    """通过 ComfyUI（本地）或云端降级生成图片"""
    try:
        return await ClawBotRPC._rpc_generate_image(prompt)
    except Exception as e:
        logger.exception("图片生成失败")
        raise HTTPException(status_code=502, detail=_safe_error(e)) from e


@router.post("/social/generate-persona-photo", response_model=dict[str, Any])
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


@router.get("/social/autopilot/status", response_model=dict[str, Any])
def autopilot_status():
    """获取自动驾驶调度状态 — 运行中、任务列表、下次动作"""
    try:
        return ClawBotRPC._rpc_autopilot_status()
    except Exception as e:
        logger.exception("获取自动驾驶状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/autopilot/start", response_model=dict[str, Any])
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


@router.post("/social/autopilot/stop", response_model=dict[str, Any])
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


@router.post("/social/autopilot/trigger/{job_id}", response_model=dict[str, Any])
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


@router.get("/social/drafts", response_model=dict[str, Any])
def list_drafts():
    """列出自动驾驶状态中的所有草稿"""
    try:
        return ClawBotRPC._rpc_social_drafts()
    except Exception as e:
        logger.exception("列出草稿失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.patch("/social/drafts/{index}", response_model=dict[str, Any])
def update_draft(index: int = Path(ge=0, description="草稿索引"), text: str = ""):
    """更新草稿文本内容"""
    try:
        return ClawBotRPC._rpc_social_draft_update(index, text)
    except Exception as e:
        logger.exception("更新草稿失败 (index=%d)", index)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.delete("/social/drafts/{index}", response_model=dict[str, Any])
def delete_draft(index: int = Path(ge=0, description="草稿索引")):
    """按索引删除草稿"""
    try:
        return ClawBotRPC._rpc_social_draft_delete(index)
    except Exception as e:
        logger.exception("删除草稿失败 (index=%d)", index)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/drafts/{index}/review", response_model=dict[str, Any])
def review_draft(
    index: int = Path(ge=0, description="草稿索引"),
    approved: bool = True,
    reviewer: str = "owner",
):
    """审核草稿：确认人设/内容后才允许发布。"""
    try:
        return ClawBotRPC._rpc_social_draft_review(index, approved=approved, reviewer=reviewer)
    except Exception as e:
        logger.exception("审核草稿失败 (index=%d)", index)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/social/drafts/{index}/publish", response_model=dict[str, Any])
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
