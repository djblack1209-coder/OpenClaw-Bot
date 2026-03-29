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
from pathlib import Path
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from src.utils import now_et

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
            "ts": now_et().isoformat(),
        })
    except Exception as e:
        logger.debug("[SocialScheduler] 异常: %s", e)
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
        except Exception as e:
            logger.debug("[SocialScheduler] 异常: %s", e)
            # 降级: 旧 synergy
            try:
                from src.synergy import get_synergy
                await get_synergy().on_social_hotspot(selected)
            except Exception as e:
                logger.debug("[SocialScheduler] 异常: %s", e)

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

        # 自动回复评论
        try:
            reply_result = run_social_worker("auto_reply", {})
            logger.info("[Autopilot] 自动回复结果: %s", reply_result.get("success"))
        except Exception as e:
            logger.error("[Autopilot] 自动回复失败: %s", e)
            reply_result = {"success": False, "error": str(e)}

        # 蹭评热门帖子
        try:
            scout_result = run_social_worker("scout_comment", {"count": 3})
            logger.info("[Autopilot] 蹭评结果: %s", scout_result.get("success"))
        except Exception as e:
            logger.error("[Autopilot] 蹭评失败: %s", e)
            scout_result = {"success": False, "error": str(e)}

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
                            "created_at": now_et().isoformat(),
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
        from src.execution.social.worker_bridge import run_social_worker_async

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

            # 防重发: 先标记为 publishing 并持久化
            draft["status"] = "publishing"
            _save_state(state)

            try:
                if platform == "x":
                    result = await run_social_worker_async("publish_x", {"text": text})
                elif platform == "xhs":
                    lines = text.strip().splitlines()
                    title = lines[0].strip() if lines else "无标题"
                    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else text
                    result = await run_social_worker_async(
                        "publish_xhs", {"title": title, "body": body},
                    )
                else:
                    result = {"success": False, "error": f"未知平台: {platform}"}

                if result.get("success"):
                    draft["status"] = "published"
                    draft["published_at"] = now_et().isoformat()
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
            except Exception as e:
                draft["status"] = "failed"
                draft["error"] = str(e)
                failed.append(draft)
                logger.error("[Autopilot] 发布异常: %s/%s - %s", platform, draft_id, e)

            _save_state(state)

        state["drafts"] = drafts  # updated statuses
        state["today_published"].extend(published)
        state["stats"]["posts_today"] = len(state["today_published"])
        _save_state(state)

        # sau_bridge: 将已发布内容同步到抖音/B站等平台（如果 sau 可用）
        try:
            from src.sau_bridge import publish_multi_platform
            # 把已成功发布的内容通过 sau 同步到更多平台
            for draft in published:
                text = draft.get("text", "")
                title = text.strip().splitlines()[0].strip()[:100] if text.strip() else "OpenClaw 自动发布"
                sau_results = await publish_multi_platform(
                    platforms=["douyin", "xiaohongshu"],
                    title=title,
                    description=text[:500],
                )
                sau_ok = sum(1 for r in sau_results.values() if r.get("success"))
                if sau_ok:
                    logger.info("[Autopilot] sau 多平台同步: %d 个平台成功", sau_ok)
        except ImportError:
            logger.info("[SocialAutopilot] sau_bridge 未配置，跳过自动发布")
        except Exception as e:
            logger.warning("[Autopilot] sau 多平台同步异常: %s", e)

        # EventBus: 社媒发布事件（逐篇发射，触发主动引擎 1 小时后跟进）
        if published:
            try:
                from src.core.event_bus import get_event_bus, EventType
                bus = get_event_bus()
                for draft in published:
                    _platform = draft.get("platform", "")
                    _text = draft.get("text", "")
                    _title = _text.strip().splitlines()[0].strip()[:50] if _text.strip() else "无标题"
                    await bus.publish(
                        EventType.SOCIAL_PUBLISHED,
                        {"platform": _platform, "title": _title},
                        source="social_scheduler",
                    )
            except Exception as e:
                logger.debug("[SocialScheduler] 发布事件发射失败: %s", e)

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
            "review_time": now_et().isoformat(),
        }

        # KPI check (from SKILL.md: XHS>500 views, X>200 views)
        warnings: List[str] = []
        if result.get("success"):
            x_stats = result.get("x", {}).get("stats", {})
            xhs_stats = result.get("xiaohongshu", {}).get("stats", {})
            x_views = x_stats.get("latest_like_count", 0) + x_stats.get("latest_repost_count", 0)
            xhs_views = xhs_stats.get("views", 0)
            if x_views < 200 and state["stats"].get("posts_today", 0) > 0:
                warnings.append(f"X 阅读量 {x_views} 未达标 (目标>200)")
            if xhs_views < 500 and state["stats"].get("posts_today", 0) > 0:
                warnings.append(f"XHS 阅读量 {xhs_views} 未达标 (目标>500)")

            # ── 管道接通: 将采集到的互动数据写入 post_engagement 表 ──
            try:
                from src.execution.life_automation import record_post_engagement

                # X 平台数据: 用最新帖子的互动指标
                if x_stats:
                    record_post_engagement(
                        draft_id=0,  # 0 表示 profile 级聚合快照
                        platform="x",
                        likes=x_stats.get("latest_like_count", 0),
                        comments=x_stats.get("latest_reply_count", 0),
                        shares=x_stats.get("latest_repost_count", 0),
                        views=x_stats.get("followers", 0),  # X 无直接浏览量，用粉丝数近似
                        post_url=result.get("x", {}).get("url", ""),
                    )
                    logger.info("[Autopilot] X 互动数据已存入 post_engagement")

                # 小红书数据: 创作者中心有完整指标
                if xhs_stats:
                    record_post_engagement(
                        draft_id=0,
                        platform="xhs",
                        likes=xhs_stats.get("likes", 0),
                        comments=xhs_stats.get("comments", 0),
                        shares=xhs_stats.get("shares", 0),
                        views=xhs_stats.get("views", 0),
                        post_url=result.get("xiaohongshu", {}).get("url", ""),
                    )
                    logger.info("[Autopilot] XHS 互动数据已存入 post_engagement")
            except Exception as e:
                logger.warning("[Autopilot] 存储互动数据失败(不影响主流程): %s", e)

            # ── 管道接通: 将粉丝数存入 follower_snapshots 表供趋势分析 ──
            try:
                from src.execution.life_automation import record_follower_snapshot

                # X 平台: 粉丝数 + 关注数
                if x_stats and x_stats.get("followers"):
                    record_follower_snapshot(
                        platform="x",
                        followers=x_stats.get("followers", 0),
                        following=x_stats.get("following", 0),
                    )

                # 小红书: 粉丝数 + 获赞总数
                if xhs_stats and xhs_stats.get("followers"):
                    record_follower_snapshot(
                        platform="xhs",
                        followers=xhs_stats.get("followers", 0),
                        total_likes=xhs_stats.get("total_likes", 0),
                        total_views=xhs_stats.get("views", 0),
                    )
            except Exception as e:
                logger.warning("[Autopilot] 存储粉丝快照失败(不影响主流程): %s", e)

            # ── 粉丝里程碑检测 — 突破整数关口时发射事件 ──
            _MILESTONES = [100, 500, 1000, 2000, 5000, 10000, 50000, 100000]
            try:
                from src.execution.life_automation import get_follower_growth
                for _plat in ("x", "xhs"):
                    _growth = get_follower_growth(platform=_plat, days=2)
                    if not _growth or not _growth.get("success"):
                        continue
                    _snapshots = _growth.get("snapshots", [])
                    if len(_snapshots) < 2:
                        continue
                    _prev = _snapshots[-2].get("followers", 0)
                    _curr = _snapshots[-1].get("followers", 0)
                    if _curr <= 0 or _prev <= 0:
                        continue
                    # 检查是否跨越了任何里程碑
                    for ms in _MILESTONES:
                        if _prev < ms <= _curr:
                            try:
                                from src.core.event_bus import get_event_bus, EventType
                                _bus = get_event_bus()
                                # job_late_review 在独立线程中用 asyncio.run()
                                # 此处已在同步上下文，需创建临时事件循环发布
                                import asyncio as _aio
                                _loop = _aio.new_event_loop()
                                _loop.run_until_complete(_bus.publish(
                                    EventType.FOLLOWER_MILESTONE,
                                    {"platform": _plat, "count": ms},
                                    source="social_scheduler",
                                ))
                                _loop.close()
                                logger.info("[Autopilot] 粉丝里程碑: %s 突破 %d", _plat, ms)
                            except Exception as _me:
                                logger.debug("[Autopilot] 粉丝里程碑事件发射失败: %s", _me)
                            break  # 一次只触发最近的一个里程碑
            except Exception as e:
                logger.debug("[Autopilot] 粉丝里程碑检测失败(不影响主流程): %s", e)

            # ── 管道接通: 喂数据给 PostTimeOptimizer 学习最佳发布时间 ──
            try:
                from src.social_tools import get_post_time_optimizer

                optimizer = get_post_time_optimizer()
                current_hour = now_et().hour

                # 计算两个平台的综合互动率
                total_engagement = (
                    x_stats.get("latest_like_count", 0)
                    + x_stats.get("latest_reply_count", 0)
                    + x_stats.get("latest_repost_count", 0)
                    + xhs_stats.get("likes", 0)
                    + xhs_stats.get("comments", 0)
                    + xhs_stats.get("shares", 0)
                )
                total_views = max(xhs_stats.get("views", 0) + x_stats.get("followers", 1), 1)
                engagement_rate = round(total_engagement / total_views * 100, 2)

                optimizer.record_engagement(current_hour, engagement_rate)
                logger.info("[Autopilot] PostTimeOptimizer 已记录 hour=%d rate=%.2f%%", current_hour, engagement_rate)
            except Exception as e:
                logger.warning("[Autopilot] PostTimeOptimizer 记录失败(不影响主流程): %s", e)

            # ── 根据今日互动数据更新明日发布时间 ──
            try:
                from src.social_tools import get_post_time_optimizer as _get_optimizer
                _opt = _get_optimizer()
                new_best = _opt.best_hours("twitter", top_n=1)
                if new_best:
                    new_hour = new_best[0]
                    # 通过单例获取 SocialAutopilot 实例的调度器
                    autopilot = SocialAutopilot._instance
                    if autopilot and autopilot._scheduler and autopilot._scheduler.running:
                        current_publish_hour = getattr(autopilot, "_current_publish_hour", 20)
                        if new_hour != current_publish_hour:
                            autopilot._scheduler.reschedule_job(
                                "night_publish",
                                trigger=CronTrigger(hour=new_hour, minute=30, timezone=_TIMEZONE),
                            )
                            logger.info(
                                "[社媒] 明日发布时间调整: %d:30 → %d:30",
                                current_publish_hour, new_hour,
                            )
                            autopilot._current_publish_hour = new_hour
            except Exception as e:
                logger.debug("[社媒] 更新发布时间失败: %s", e)

        state["last_review"] = now_et().isoformat()
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
        # 20:30 — 自动发布（数据驱动：根据历史互动数据选择最佳发布时间）
        try:
            from src.social_tools import get_post_time_optimizer
            optimizer = get_post_time_optimizer()
            best = optimizer.best_hours("twitter", top_n=1)
            publish_hour = best[0] if best else 20  # 默认 20 点（没有数据时）
            if best:
                logger.info("[社媒] 发布时间设定为 %d:30 (数据驱动)", publish_hour)
            else:
                logger.info("[社媒] 发布时间使用默认 20:30")
        except Exception as e:
            publish_hour = 20
            logger.warning("[社媒] 查询最佳发布时间失败, 使用默认 20:30: %s", e)

        # 记录当前发布小时，供 job_late_review 比对和更新
        self._current_publish_hour = publish_hour

        self._scheduler.add_job(
            job_night_publish, CronTrigger(hour=publish_hour, minute=30, timezone=_TIMEZONE),
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
        """Manually trigger a specific job (for testing / 严总 override)."""
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
