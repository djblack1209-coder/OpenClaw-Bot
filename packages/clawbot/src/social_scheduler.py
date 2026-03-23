"""
Social Autopilot Scheduler
搬运 APScheduler 3.x (6.3k stars, MIT) + SKILL.md 日程设计

5 个定时任务 (北京时间):
  09:00 — 热点扫描 + 选题 + 简报
  12:30 — 评论互动 + 蹭评
  19:00 — 内容生产 + 预检
  20:30 — 自动发布 (双平台)
  22:00 — 数据统计 + 复盘

用法:
    from src.social_scheduler import SocialAutopilot
    autopilot = SocialAutopilot()
    autopilot.start()   # 启动 APScheduler + 5 个 cron job
    autopilot.stop()    # 优雅关闭
"""

import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# packages/clawbot/  (three parents up from src/social_scheduler.py)
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_STATE_FILE = _PACKAGE_ROOT / "data" / "social_autopilot_state.json"
_TIMEZONE = "Asia/Shanghai"

# Thread-safety lock for state file reads/writes.
# APScheduler's BackgroundScheduler runs jobs in a thread pool, so concurrent
# access to the state file is possible.
_state_lock = threading.Lock()


# ─── State persistence ────────────────────────────────────────

def _load_state() -> Dict[str, Any]:
    """Load autopilot state from disk. Returns defaults if missing.

    Thread-safe: guarded by ``_state_lock``.
    """
    defaults: Dict[str, Any] = {
        "enabled": False,
        "last_scan_topics": [],
        "drafts": [],
        "today_published": [],
        "last_review": "",
        "stats": {"posts_today": 0, "engagement_today": 0},
    }
    with _state_lock:
        try:
            if _STATE_FILE.exists():
                data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    defaults.update(data)
        except Exception as e:
            logger.warning("[Autopilot] 状态读取失败, 使用默认值: %s", e)
    return defaults


def _save_state(state: Dict[str, Any]) -> None:
    """Persist autopilot state to disk.

    Thread-safe: guarded by ``_state_lock``.
    """
    with _state_lock:
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(
                json.dumps(state, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("[Autopilot] 状态保存失败: %s", e)


# ─── WebSocket notification helper ────────────────────────────

def _notify(message: str, data: Optional[Dict] = None) -> None:
    """Push event to connected dashboard clients (best-effort)."""
    try:
        from src.api.routers.ws import push_event
        from src.api.schemas import WSMessageType
        push_event(WSMessageType.AUTOPILOT_EVENT, {
            "message": message,
            **(data or {}),
            "ts": datetime.now().isoformat(),
        })
    except Exception:
        logger.debug("Silenced exception", exc_info=True)
    logger.info("[Autopilot] %s", message)


# ─── Job functions ─────────────────────────────────────────────
# Each job is self-contained with lazy imports.
# They run in APScheduler thread pool.  Each job wraps ALL async work
# inside a single ``async def _run()`` and calls ``asyncio.run(_run())``
# exactly once — one event loop per job execution.

def job_morning_scan() -> None:
    """09:00 — 热点扫描 + 选题 + 简报"""

    async def _run() -> None:
        from src.execution.social.content_strategy import discover_hot_topics

        topics = await discover_hot_topics(count=10)

        # Score and select top topics (score >= 7)
        selected = [t for t in topics if t.get("score", 0) >= 7]
        if not selected:
            # Fallback: take top 3 by score
            selected = sorted(
                topics, key=lambda t: t.get("score", 0), reverse=True,
            )[:3]

        state = _load_state()
        state["last_scan_topics"] = selected
        state["drafts"] = []  # reset daily drafts
        state["today_published"] = []
        state["stats"] = {"posts_today": 0, "engagement_today": 0}
        _save_state(state)

        # Synergy: 社交热点 → 交易标的扫描（通过 EventBus）
        try:
            from src.core.event_bus import get_event_bus, EventType
            bus = get_event_bus()
            await bus.publish(
                EventType.SOCIAL_TRENDING,
                {"topics": selected, "source": "morning_scan"},
                source="social_scheduler",
            )
        except Exception:
            # 降级: 旧 synergy
            try:
                from src.synergy import get_synergy
                await get_synergy().on_social_hotspot(selected)
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

        titles = [t.get("title", "?") for t in selected[:3]]
        _notify(
            f"今日选题: {', '.join(titles)}，预计晚8点发",
            {"topics": selected[:3]},
        )

    logger.info("[Autopilot] === 早间热点扫描 ===")
    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error("[Autopilot] 热点扫描失败: %s", e)
        _notify(f"早扫失败: {e}")


def job_noon_engage() -> None:
    """12:30 — 评论互动 + 蹭评"""
    logger.info("[Autopilot] === 午间互动 ===")

    try:
        from src.execution.social.worker_bridge import run_social_worker

        # Auto-reply to comments on existing posts
        reply_result = run_social_worker("auto_reply", {})
        logger.info("[Autopilot] 自动回复结果: %s", reply_result.get("success"))

        # Scout and comment on trending posts
        scout_result = run_social_worker("scout_comment", {"count": 3})
        logger.info("[Autopilot] 蹭评结果: %s", scout_result.get("success"))

        _notify("午间互动完成", {
            "auto_reply": reply_result.get("success", False),
            "scout_comment": scout_result.get("success", False),
        })
    except Exception as e:
        logger.error("[Autopilot] 午间互动失败: %s", e)
        _notify(f"午间互动失败: {e}")


def job_evening_produce() -> None:
    """19:00 — 内容生产 + 预检"""

    async def _run() -> None:
        from src.execution.social.content_strategy import (
            compose_post,
            derive_content_strategy,
            load_persona,
        )

        state = _load_state()
        topics = state.get("last_scan_topics", [])

        if not topics:
            _notify("跳过内容生产: 无选题 (早扫可能未执行)")
            return

        persona = load_persona(name="default")
        drafts: List[Dict[str, Any]] = []

        for topic_data in topics[:3]:
            title = topic_data.get("title", "")
            if not title:
                continue

            for platform in ("x", "xhs"):
                try:
                    # Derive strategy
                    strategy_result = await derive_content_strategy(
                        topic=title, platform=platform, persona=persona,
                    )
                    strategy = (
                        strategy_result.get("strategy")
                        if strategy_result.get("success") else None
                    )

                    # Compose post
                    max_len = 280 if platform == "x" else 800
                    result = await compose_post(
                        topic=title,
                        platform=platform,
                        strategy=strategy,
                        persona=persona,
                        max_length=max_len,
                    )

                    if result.get("success"):
                        draft = {
                            "id": uuid.uuid4().hex[:8],
                            "platform": platform,
                            "topic": title,
                            "text": result["text"],
                            "strategy": strategy,
                            "status": "ready",
                            "created_at": datetime.now().isoformat(),
                        }
                        drafts.append(draft)
                        logger.info(
                            "[Autopilot] 生成草稿: %s/%s (%d字)",
                            platform, title, len(result["text"]),
                        )
                    else:
                        logger.warning(
                            "[Autopilot] 生成失败 %s/%s: %s",
                            platform, title, result.get("error"),
                        )
                except Exception as e:
                    logger.error(
                        "[Autopilot] 单篇生成异常 %s/%s: %s", platform, title, e,
                    )

        state["drafts"] = drafts
        _save_state(state)
        _notify(
            f"内容生产完成: {len(drafts)} 篇草稿待发",
            {"draft_count": len(drafts)},
        )

    logger.info("[Autopilot] === 晚间内容生产 ===")
    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error("[Autopilot] 内容生产整体失败: %s", e)
        _notify(f"内容生产失败: {e}")


def job_night_publish() -> None:
    """20:30 — 自动发布 (双平台)"""

    async def _run() -> None:
        from src.execution.social.worker_bridge import run_social_worker

        state = _load_state()
        drafts = state.get("drafts", [])

        ready_drafts = [d for d in drafts if d.get("status") == "ready"]
        if not ready_drafts:
            _notify("跳过发布: 无待发草稿")
            return

        published: List[Dict] = []
        failed: List[Dict] = []

        for draft in ready_drafts:
            platform = draft.get("platform", "x")
            text = draft.get("text", "")
            draft_id = draft.get("id", "?")

            if platform == "x":
                result = run_social_worker("publish_x", {"text": text})
            elif platform == "xhs":
                lines = text.strip().splitlines()
                title = lines[0].strip() if lines else "无标题"
                body = "\n".join(lines[1:]).strip() if len(lines) > 1 else text
                result = run_social_worker(
                    "publish_xhs", {"title": title, "body": body},
                )
            else:
                result = {"success": False, "error": f"未知平台: {platform}"}

            if result.get("success"):
                draft["status"] = "published"
                draft["published_at"] = datetime.now().isoformat()
                published.append(draft)
                logger.info("[Autopilot] 发布成功: %s/%s", platform, draft_id)
            else:
                draft["status"] = "failed"
                draft["error"] = result.get("error", "unknown")
                failed.append(draft)
                logger.warning(
                    "[Autopilot] 发布失败: %s/%s - %s",
                    platform, draft_id, result.get("error"),
                )

        state["drafts"] = drafts  # updated statuses
        state["today_published"].extend(published)
        state["stats"]["posts_today"] = len(state["today_published"])
        _save_state(state)

        # EventBus: 社媒发布事件
        if published:
            try:
                from src.core.event_bus import get_event_bus, EventType
                bus = get_event_bus()
                await bus.publish(
                    EventType.SOCIAL_PUBLISHED,
                    {"count": len(published), "platforms": [p.get("platform") for p in published]},
                    source="social_scheduler",
                )
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

        _notify(
            f"发布完成: {len(published)} 成功, {len(failed)} 失败",
            {"published": len(published), "failed": len(failed)},
        )

    logger.info("[Autopilot] === 晚间自动发布 ===")
    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error("[Autopilot] 发布整体失败: %s", e)
        _notify(f"发布失败: {e}")


def job_late_review() -> None:
    """22:00 — 数据统计 + 复盘"""
    logger.info("[Autopilot] === 数据复盘 ===")
    state = _load_state()

    try:
        from src.execution.social.worker_bridge import run_social_worker

        result = run_social_worker("metrics", {})

        kpi_summary = {
            "posts_today": state["stats"].get("posts_today", 0),
            "metrics_raw": result if result.get("success") else {},
            "review_time": datetime.now().isoformat(),
        }

        # KPI check (from SKILL.md: XHS>500 views, X>200 views)
        warnings: List[str] = []
        if result.get("success"):
            x_views = result.get("x", {}).get("views", 0)
            xhs_views = result.get("xhs", {}).get("views", 0)
            if x_views < 200 and state["stats"].get("posts_today", 0) > 0:
                warnings.append(f"X 阅读量 {x_views} 未达标 (目标>200)")
            if xhs_views < 500 and state["stats"].get("posts_today", 0) > 0:
                warnings.append(f"XHS 阅读量 {xhs_views} 未达标 (目标>500)")

        state["last_review"] = datetime.now().isoformat()
        _save_state(state)

        _notify(
            f"复盘完成: 今日发布 {kpi_summary['posts_today']} 篇"
            + (f", 警告: {'; '.join(warnings)}" if warnings else ""),
            {"kpi": kpi_summary, "warnings": warnings},
        )
    except Exception as e:
        logger.error("[Autopilot] 数据复盘失败: %s", e)
        _notify(f"复盘失败: {e}")


# ─── Scheduler class ──────────────────────────────────────────

class SocialAutopilot:
    """Social media autopilot — wraps APScheduler BackgroundScheduler.

    Uses BackgroundScheduler (threaded) to avoid conflicts with the
    existing asyncio event loop. Job functions use asyncio.run() internally
    for async operations — exactly once per job invocation.
    """

    _instance: Optional["SocialAutopilot"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "SocialAutopilot":
        """Singleton — only one autopilot per process."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._scheduler: Optional[BackgroundScheduler] = None
        logger.info("[Autopilot] SocialAutopilot 初始化")

    # ── Public API ────────────────────────────────────────────

    def start(self) -> Dict[str, Any]:
        """Start the scheduler with all 5 daily cron jobs."""
        if self._scheduler and self._scheduler.running:
            return {"status": "already_running"}

        self._scheduler = BackgroundScheduler(timezone=_TIMEZONE)

        # 09:00 — 热点扫描
        self._scheduler.add_job(
            job_morning_scan, CronTrigger(hour=9, minute=0, timezone=_TIMEZONE),
            id="morning_scan", name="社媒早扫",
            replace_existing=True, misfire_grace_time=3600,
        )
        # 12:30 — 评论互动
        self._scheduler.add_job(
            job_noon_engage, CronTrigger(hour=12, minute=30, timezone=_TIMEZONE),
            id="noon_engage", name="社媒午动",
            replace_existing=True, misfire_grace_time=3600,
        )
        # 19:00 — 内容生产
        self._scheduler.add_job(
            job_evening_produce, CronTrigger(hour=19, minute=0, timezone=_TIMEZONE),
            id="evening_produce", name="社媒晚产",
            replace_existing=True, misfire_grace_time=3600,
        )
        # 20:30 — 自动发布
        self._scheduler.add_job(
            job_night_publish, CronTrigger(hour=20, minute=30, timezone=_TIMEZONE),
            id="night_publish", name="社媒晚发",
            replace_existing=True, misfire_grace_time=3600,
        )
        # 22:00 — 数据复盘
        self._scheduler.add_job(
            job_late_review, CronTrigger(hour=22, minute=0, timezone=_TIMEZONE),
            id="late_review", name="社媒复盘",
            replace_existing=True, misfire_grace_time=3600,
        )

        self._scheduler.start()

        # Persist enabled flag
        state = _load_state()
        state["enabled"] = True
        _save_state(state)

        _notify("社交自动驾驶已启动 (5 个日程任务)")
        logger.info("[Autopilot] APScheduler 已启动, %d 个任务", len(self._scheduler.get_jobs()))
        return {"status": "started", "jobs": len(self._scheduler.get_jobs())}

    def stop(self) -> Dict[str, Any]:
        """Graceful shutdown."""
        if not self._scheduler or not self._scheduler.running:
            return {"status": "not_running"}

        self._scheduler.shutdown(wait=False)
        self._scheduler = None

        state = _load_state()
        state["enabled"] = False
        _save_state(state)

        _notify("社交自动驾驶已停止")
        logger.info("[Autopilot] APScheduler 已停止")
        return {"status": "stopped"}

    def status(self) -> Dict[str, Any]:
        """Return current autopilot state + next job schedule."""
        running = bool(self._scheduler and self._scheduler.running)
        state = _load_state()

        jobs: List[Dict[str, Any]] = []
        next_action = ""
        next_time = ""

        if self._scheduler and running:
            for job in self._scheduler.get_jobs():
                next_run = (
                    job.next_run_time.isoformat() if job.next_run_time else ""
                )
                jobs.append({
                    "id": job.id,
                    "name": job.name or job.id,
                    "next_run": next_run,
                })
            # Find soonest job
            upcoming = [j for j in jobs if j["next_run"]]
            if upcoming:
                soonest = min(upcoming, key=lambda j: j["next_run"])
                next_action = soonest["name"]
                next_time = soonest["next_run"]

        return {
            "running": running,
            "enabled": state.get("enabled", False),
            "jobs": jobs,
            "next_action": next_action,
            "next_time": next_time,
            "draft_count": len(state.get("drafts", [])),
            "posts_today": state.get("stats", {}).get("posts_today", 0),
            "last_review": state.get("last_review", ""),
            "topics_selected": len(state.get("last_scan_topics", [])),
        }

    def trigger_job(self, job_id: str) -> Dict[str, Any]:
        """Manually trigger a specific job (for testing / Boss override)."""
        job_map = {
            "morning_scan": job_morning_scan,
            "noon_engage": job_noon_engage,
            "evening_produce": job_evening_produce,
            "night_publish": job_night_publish,
            "late_review": job_late_review,
        }
        func = job_map.get(job_id)
        if not func:
            return {"success": False, "error": f"未知任务: {job_id}"}

        try:
            func()
            return {"success": True, "job_id": job_id}
        except Exception as e:
            logger.error("[Autopilot] 手动触发 %s 失败: %s", job_id, e)
            return {"success": False, "error": str(e)}
