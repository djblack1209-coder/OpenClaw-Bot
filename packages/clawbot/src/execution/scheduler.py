"""
Execution Hub — 调度器
统一的定时任务调度，替代原 execution_hub 中的 _scheduler_loop
"""
import os
import time
import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from src.execution._utils import parse_hhmm, safe_int

logger = logging.getLogger(__name__)


class ExecutionScheduler:
    """执行场景调度器"""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._notify_func: Optional[Callable] = None
        self._private_notify_func: Optional[Callable] = None
        # 状态追踪
        self._last_brief_date = ""
        self._last_monitor_ts = 0.0
        self._last_bounty_ts = 0.0
        self._last_social_operator_ts = 0.0
        # 外部依赖（注入）
        self.monitor_manager = None
        self.social_autopilot_func = None
        self.bounty_scan_func = None

    async def start(self, notify_func=None, private_notify_func=None):
        self._notify_func = notify_func
        self._private_notify_func = private_notify_func
        self._running = True
        self._task = asyncio.ensure_future(self._loop())
        logger.info("[ExecutionScheduler] started")

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("[ExecutionScheduler] stopped")

    async def _loop(self):
        brief_time = parse_hhmm(os.getenv("OPS_BRIEF_TIME"), (8, 0))
        monitor_interval = max(1, safe_int(os.getenv("OPS_MONITOR_INTERVAL_MIN"), 15)) * 60
        bounty_interval = max(1, safe_int(os.getenv("OPS_BOUNTY_INTERVAL_MIN"), 45)) * 60
        social_op_interval = safe_int(os.getenv("OPS_SOCIAL_OPERATOR_CHECK_INTERVAL_MIN"), 0) * 60

        while self._running:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break

            now = datetime.now()
            ts = time.time()

            await self._run_daily_brief(now, brief_time)
            await self._run_monitors(ts, monitor_interval)
            await self._run_social_operator(ts, social_op_interval)
            await self._run_bounty_scan(ts, bounty_interval)
            self._run_cleanup(now)

    async def _run_daily_brief(self, now, brief_time):
        if os.getenv("OPS_BRIEF_ENABLED", "").lower() not in ("1", "true", "yes", "on"):
            return
        today = now.strftime("%Y-%m-%d")
        if today == self._last_brief_date:
            return
        if now.hour != brief_time[0] or now.minute < brief_time[1]:
            return

        # 尊重用户偏好 — 如果用户关闭了每日报告则跳过
        try:
            from src.bot.globals import user_prefs
            notify_chat_id = int(os.environ.get("NOTIFY_CHAT_ID", "0"))
            if notify_chat_id and not user_prefs.get(notify_chat_id, "daily_report", True):
                logger.info("[Scheduler] 用户已关闭每日报告，跳过")
                self._last_brief_date = today  # 标记已处理，避免每分钟重试
                return
        except Exception:
            pass  # 偏好系统不可用不影响默认行为

        try:
            from src.execution.daily_brief import generate_daily_brief
            monitors = self.monitor_manager._monitors if self.monitor_manager else None
            result = await generate_daily_brief(monitors=monitors)
            self._last_brief_date = today
            if self._notify_func and result and len(str(result).strip()) > 20:
                await self._notify_func(result)
        except Exception as e:
            logger.error(f"[Scheduler] daily brief failed: {e}")

    async def _run_monitors(self, ts, interval):
        if os.getenv("OPS_MONITOR_ENABLED", "").lower() not in ("1", "true", "yes", "on"):
            return
        if ts - self._last_monitor_ts < interval:
            return
        if not self.monitor_manager:
            return
        try:
            result = await self.monitor_manager.run_monitors_once()
            self._last_monitor_ts = ts
            if self._notify_func and result and isinstance(result, list) and len(result) > 0:
                from src.execution.monitoring import MonitorManager
                formatted = "\n\n".join(
                    MonitorManager.format_alert(al) for al in result if al
                )
                if formatted.strip():
                    await self._notify_func(formatted)
        except Exception as e:
            logger.error(f"[Scheduler] monitor failed: {e}")

    async def _run_social_operator(self, ts, interval):
        if interval <= 0 or not self.social_autopilot_func:
            return
        if ts - self._last_social_operator_ts < interval:
            return
        try:
            await self.social_autopilot_func()
            self._last_social_operator_ts = ts
        except Exception as e:
            logger.error(f"[Scheduler] social operator failed: {e}")

    async def _run_bounty_scan(self, ts, interval):
        if os.getenv("OPS_BOUNTY_ENABLED", "").lower() not in ("1", "true", "yes", "on"):
            return
        if ts - self._last_bounty_ts < interval or not self.bounty_scan_func:
            return
        try:
            result = await self.bounty_scan_func()
            self._last_bounty_ts = ts
            saved = (result or {}).get("saved", {}) if isinstance(result, dict) else {}
            new_count = int(saved.get("inserted", 0) or 0)
            if self._private_notify_func and new_count > 0:
                await self._private_notify_func(
                    f"赏金扫描完成 | 新增 {new_count} 条线索\n"
                    f"入库: {saved.get('total', 0)} (更新{saved.get('updated', 0)})\n"
                    f"下一步: /ops bounty top"
                )
        except Exception as e:
            logger.error(f"[Scheduler] bounty scan failed: {e}")

    @staticmethod
    def _run_cleanup(now):
        if now.minute != 0:
            return
        try:
            from src.bot.globals import _cleanup_pending_trades
            _cleanup_pending_trades()
        except Exception:
            pass
