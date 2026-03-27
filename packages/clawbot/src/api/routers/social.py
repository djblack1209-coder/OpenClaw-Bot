"""Social media endpoints — status, topics, compose, publish, autopilot"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Query
from ..rpc import ClawBotRPC
from ..schemas import SocialStatus, SocialPublishRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/social/status", response_model=SocialStatus)
def get_social_status():
    return ClawBotRPC._rpc_social_status()


@router.post("/social/topics", response_model=Dict[str, Any])
async def discover_topics(count: int = Query(default=10, ge=1, le=50)):
    return await ClawBotRPC._rpc_social_discover_topics(count=count)


@router.post("/social/compose", response_model=Dict[str, Any])
async def compose_content(
    topic: str,
    platform: str = "x",
    persona: str = "default",
):
    """AI content generation — returns ready-to-publish text for review.

    Full pipeline: persona loading → strategy derivation → content composition.
    搬运 content_strategy.py 的三步管道。
    """
    return await ClawBotRPC._rpc_social_compose(
        topic=topic,
        platform=platform,
        persona_name=persona,
    )


@router.post("/social/publish", response_model=Dict[str, Any])
async def publish_content(req: SocialPublishRequest):
    """Publish content to social platform via browser worker.

    Note: Requires browser worker to be configured. Returns error
    with clear message if worker is not available.
    """
    return await ClawBotRPC._rpc_social_publish(
        platform=req.platform,
        content=req.content,
    )


@router.post("/social/research", response_model=Dict[str, Any])
async def deep_research(topic: str, count: int = Query(default=10, ge=1, le=50)):
    """Deep topic research — scrapes platform data and aggregates insights."""
    return await ClawBotRPC._rpc_social_research(topic=topic, count=count)


@router.get("/social/metrics", response_model=Dict[str, Any])
async def get_metrics():
    """Social metrics/analytics — follower counts, engagement stats."""
    return await ClawBotRPC._rpc_social_metrics()


@router.get("/social/personas", response_model=Dict[str, Any])
def list_personas():
    """List available social personas from data/social_personas/."""
    return ClawBotRPC._rpc_social_personas()


@router.get("/social/calendar", response_model=Dict[str, Any])
async def get_calendar(days: int = Query(default=7, ge=1, le=30)):
    """Content calendar generation — trending topics mapped to a day-by-day plan."""
    return await ClawBotRPC._rpc_social_calendar(days=days)


@router.post("/social/generate-image", response_model=Dict[str, Any])
async def gen_image(prompt: str):
    """Generate image via ComfyUI (local) or cloud fallback."""
    return await ClawBotRPC._rpc_generate_image(prompt)


@router.post("/social/generate-persona-photo", response_model=Dict[str, Any])
async def gen_persona_photo(
    persona: str = "default",
    scenario: str = "working in a cafe",
    mood: str = "natural",
):
    """Generate persona-consistent photo for social media content."""
    return await ClawBotRPC._rpc_generate_persona_photo(persona, scenario, mood)


# ──────────────────────────────────────────────
#  Autopilot — 社交自动驾驶
# ──────────────────────────────────────────────

@router.get("/social/autopilot/status", response_model=Dict[str, Any])
def autopilot_status():
    """Get autopilot scheduler status — running, jobs, next action."""
    return ClawBotRPC._rpc_autopilot_status()


@router.post("/social/autopilot/start", response_model=Dict[str, Any])
def autopilot_start():
    """Start the social autopilot scheduler (5 daily cron jobs)."""
    return ClawBotRPC._rpc_autopilot_start()


@router.post("/social/autopilot/stop", response_model=Dict[str, Any])
def autopilot_stop():
    """Stop the social autopilot scheduler."""
    return ClawBotRPC._rpc_autopilot_stop()


@router.post("/social/autopilot/trigger/{job_id}", response_model=Dict[str, Any])
def autopilot_trigger(job_id: str):
    """Manually trigger a specific autopilot job.

    Valid job_ids: morning_scan, noon_engage, evening_produce,
    night_publish, late_review.
    """
    return ClawBotRPC._rpc_autopilot_trigger(job_id)


# ──────────────────────────────────────────────
#  Drafts — 草稿管理
# ──────────────────────────────────────────────

@router.get("/social/drafts", response_model=Dict[str, Any])
def list_drafts():
    """List all drafts from autopilot state."""
    return ClawBotRPC._rpc_social_drafts()


@router.patch("/social/drafts/{index}", response_model=Dict[str, Any])
def update_draft(index: int, text: str):
    """Update a draft's text content."""
    return ClawBotRPC._rpc_social_draft_update(index, text)


@router.delete("/social/drafts/{index}", response_model=Dict[str, Any])
def delete_draft(index: int):
    """Delete a draft by index."""
    return ClawBotRPC._rpc_social_draft_delete(index)


@router.post("/social/drafts/{index}/publish", response_model=Dict[str, Any])
async def publish_draft(index: int):
    """Publish a draft immediately."""
    return await ClawBotRPC._rpc_social_draft_publish(index)
