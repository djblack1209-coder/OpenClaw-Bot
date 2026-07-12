"""
Execution Hub — 调度器
统一的定时任务调度，替代原 execution_hub 中的 _scheduler_loop
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from src.execution._utils import parse_hhmm, safe_int
from src.utils import now_et

logger = logging.getLogger(__name__)
_CONTROLS_STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "controls_state.json"


def _load_scheduler_controls() -> dict[str, Any]:
    """读取调度器总开关和单项开关；损坏时安全回退为默认启用。"""
    configured = os.getenv("OPENCLAW_CONTROLS_STATE_FILE", "").strip()
    path = Path(configured).expanduser() if configured else _CONTROLS_STATE_FILE
    if not path.exists():
        return {"enabled": True, "maintenance_mode": False, "tasks": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("[ExecutionScheduler] 控制状态损坏，按默认安全配置继续")
        return {"enabled": True, "maintenance_mode": False, "tasks": {}}
    scheduler = payload.get("scheduler") if isinstance(payload, dict) else {}
    if not isinstance(scheduler, dict):
        scheduler = {}
    tasks = scheduler.get("tasks")
    return {
        "enabled": bool(scheduler.get("enabled", True)),
        "maintenance_mode": bool(scheduler.get("maintenance_mode", False)),
        "tasks": tasks if isinstance(tasks, dict) else {},
    }


def _task_enabled(controls: dict[str, Any], task_id: str) -> bool:
    """没有显式关闭的任务保持兼容启用。"""
    tasks = controls.get("tasks") if isinstance(controls.get("tasks"), dict) else {}
    task = tasks.get(task_id) if isinstance(tasks, dict) else None
    return not isinstance(task, dict) or bool(task.get("enabled", True))


class ExecutionScheduler:
    """执行场景调度器"""

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self._notify_func: Callable | None = None
        self._private_notify_func: Callable | None = None
        # 状态追踪
        self._last_brief_date = ""
        self._last_monitor_ts = 0.0
        self._last_bounty_ts = 0.0
        self._last_social_operator_ts = 0.0
        self._last_intel_brief_date = ""
        self._last_stock_check_ts = 0.0
        self._stock_alert_cooldown: dict[str, float] = {}  # 库存预警冷却(每item 24h)
        self._last_price_watch_ts = 0.0  # 降价监控上次检查时间
        self._last_deal_scan_ts = 0.0  # 折扣搜集上次扫描时间
        self._last_backup_alert_date = ""  # 同一天的备份故障只提醒一次
        self._job_health: dict[str, dict[str, Any]] = {}
        self._last_loop_at = ""
        self._last_loop_completed_at = ""
        self._iteration_count = 0
        # 外部依赖（注入）
        self.monitor_manager = None
        self.social_autopilot_func = None
        self.bounty_scan_func = None
        self.intel_brief_sandbox_runner = None
        self.intel_brief_production_runner = None

    async def start(self, notify_func=None, private_notify_func=None) -> bool:
        """幂等启动调度循环；重复调用只更新通知函数，不创建第二个循环。"""
        if notify_func is not None:
            self._notify_func = notify_func
        if private_notify_func is not None:
            self._private_notify_func = private_notify_func
        if self._task and not self._task.done():
            self._running = True
            logger.info("[ExecutionScheduler] already running")
            return False

        self._running = True
        self._task = asyncio.ensure_future(self._loop())

        def _scheduler_done(task: asyncio.Task) -> None:
            if not task.cancelled() and task.exception():
                logger.warning(
                    "[ExecutionScheduler] 循环崩溃: %s",
                    type(task.exception()).__name__,
                )

        self._task.add_done_callback(_scheduler_done)
        logger.info("[ExecutionScheduler] started")
        return True

    async def stop(self) -> None:
        """幂等停止调度循环并等待取消完成。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug("[ExecutionScheduler] cancellation completed")
        self._task = None
        logger.info("[ExecutionScheduler] stopped")

    async def _loop(self) -> None:
        """每分钟运行一轮；单个任务失败或超时不会终止整个调度器。"""
        brief_time = parse_hhmm(os.getenv("OPS_BRIEF_TIME"), (8, 0))
        intel_brief_time = parse_hhmm(os.getenv("INTEL_BRIEF_TIME"), (8, 30))
        monitor_interval = max(1, safe_int(os.getenv("OPS_MONITOR_INTERVAL_MIN"), 15)) * 60
        bounty_interval = max(1, safe_int(os.getenv("OPS_BOUNTY_INTERVAL_MIN"), 45)) * 60
        social_op_interval = safe_int(os.getenv("OPS_SOCIAL_OPERATOR_CHECK_INTERVAL_MIN"), 0) * 60

        while self._running:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            await self._run_iteration(
                now=now_et(),
                ts=time.time(),
                brief_time=brief_time,
                intel_brief_time=intel_brief_time,
                monitor_interval=monitor_interval,
                bounty_interval=bounty_interval,
                social_op_interval=social_op_interval,
            )

    async def _run_iteration(
        self,
        *,
        now: Any,
        ts: float,
        brief_time: tuple[int, int],
        intel_brief_time: tuple[int, int],
        monitor_interval: int,
        bounty_interval: int,
        social_op_interval: int,
    ) -> None:
        """运行一轮完整任务列表，并为每项留下脱敏健康状态。"""
        timeout_seconds = max(5, safe_int(os.getenv("OPS_SCHEDULER_JOB_TIMEOUT_SECONDS"), 180))
        self._last_loop_at = now_et().isoformat()
        controls = _load_scheduler_controls()
        if not controls["enabled"] or controls["maintenance_mode"]:
            status = "maintenance" if controls["maintenance_mode"] else "disabled"
            self._job_health["scheduler"] = {
                "status": status,
                "last_attempt_at": self._last_loop_at,
                "last_success_at": "",
                "consecutive_failures": 0,
                "error_type": "",
                "duration_seconds": 0.0,
            }
            self._iteration_count += 1
            self._last_loop_completed_at = now_et().isoformat()
            return
        jobs: list[tuple[str, Callable[[], Awaitable[Any]]]] = [
            ("daily_brief", lambda: self._run_daily_brief(now, brief_time)),
            ("intel_brief", lambda: self._run_intel_brief(now, intel_brief_time)),
            ("morning_news", lambda: self._run_morning_news(now)),
            ("monitors", lambda: self._run_monitors(ts, monitor_interval)),
            ("social_operator", lambda: self._run_social_operator(ts, social_op_interval)),
            ("bounty_scan", lambda: self._run_bounty_scan(ts, bounty_interval)),
            ("cleanup", lambda: self._run_cleanup(now)),
            ("reminders", self._run_reminders),
            ("bill_checks", lambda: self._run_bill_checks(now)),
            ("xianyu_shipment", self._run_xianyu_shipment_check),
            ("stock_check", lambda: self._run_stock_check(ts)),
            ("weekly_strategy", self._run_weekly_strategy_review),
            ("weekly_report", self._run_weekly_report),
            ("price_watch", lambda: self._run_price_watch_check(now, ts)),
            ("deal_scan", lambda: self._run_deal_scan(ts)),
            ("budget_alert", lambda: self._run_budget_alert(now)),
        ]
        for name, job in jobs:
            if not _task_enabled(controls, name):
                self._job_health[name] = {
                    "status": "disabled",
                    "last_attempt_at": now_et().isoformat(),
                    "last_success_at": self._job_health.get(name, {}).get("last_success_at", ""),
                    "consecutive_failures": 0,
                    "error_type": "",
                    "duration_seconds": 0.0,
                }
                continue
            await self._run_guarded(name, job, timeout_seconds=timeout_seconds)
        self._iteration_count += 1
        self._last_loop_completed_at = now_et().isoformat()

    async def _run_guarded(
        self,
        name: str,
        job: Callable[[], Awaitable[Any]],
        *,
        timeout_seconds: float,
    ) -> Any:
        """隔离一个任务的异常和超时，记录错误类型但不保存敏感正文。"""
        started = time.monotonic()
        previous = self._job_health.get(name, {})
        try:
            result = await asyncio.wait_for(job(), timeout=timeout_seconds)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            failures = int(previous.get("consecutive_failures", 0)) + 1
            self._job_health[name] = {
                "status": "timeout",
                "last_attempt_at": now_et().isoformat(),
                "last_success_at": previous.get("last_success_at", ""),
                "consecutive_failures": failures,
                "error_type": "TimeoutError",
                "duration_seconds": round(time.monotonic() - started, 3),
            }
            logger.warning("[ExecutionScheduler] %s 超过 %.1f 秒，已安全取消", name, timeout_seconds)
            return None
        except Exception as error:
            failures = int(previous.get("consecutive_failures", 0)) + 1
            self._job_health[name] = {
                "status": "failed",
                "last_attempt_at": now_et().isoformat(),
                "last_success_at": previous.get("last_success_at", ""),
                "consecutive_failures": failures,
                "error_type": type(error).__name__,
                "duration_seconds": round(time.monotonic() - started, 3),
            }
            logger.warning("[ExecutionScheduler] %s 失败: %s", name, type(error).__name__)
            return None

        completed_at = now_et().isoformat()
        self._job_health[name] = {
            "status": "ok",
            "last_attempt_at": completed_at,
            "last_success_at": completed_at,
            "consecutive_failures": 0,
            "error_type": "",
            "duration_seconds": round(time.monotonic() - started, 3),
        }
        return result

    def get_health_snapshot(self) -> dict[str, Any]:
        """返回不含任务输出、聊天内容或凭据的调度器健康摘要。"""
        return {
            "running": self._running,
            "iteration_count": self._iteration_count,
            "last_loop_at": self._last_loop_at,
            "last_loop_completed_at": self._last_loop_completed_at,
            "jobs": {name: dict(status) for name, status in self._job_health.items()},
        }

    async def _run_weekly_strategy_review(self):
        """每周日检查策略绩效并推送报告"""
        now = time.localtime()
        # 仅周日 20:00-20:01 执行
        if now.tm_wday != 6 or now.tm_hour != 20 or now.tm_min > 0:
            return
        # 防止重复执行
        if hasattr(self, "_last_strategy_review") and self._last_strategy_review == now.tm_yday:
            return
        self._last_strategy_review = now.tm_yday
        try:
            from src.execution.life_automation import evaluate_strategy_performance

            result = evaluate_strategy_performance()
            if result.get("success") and self._private_notify_func:
                msg = (
                    f"📊 周度策略评估\n"
                    f"近30天: {result['total_trades']}笔交易\n"
                    f"胜率: {result['win_rate'] * 100:.1f}% ({result['wins']}胜/{result['losses']}负)\n"
                    f"累计盈亏: ${result['total_pnl']}\n"
                    f"夏普比率: {result['sharpe']} | 最大回撤: ${result['max_drawdown']}\n"
                    f"💡 {result['suggestion']}"
                )
                await self._private_notify_func(msg)
        except Exception as e:
            logger.warning("[Strategy] 周度评估异常: %s", e)

    async def _run_weekly_report(self):
        """每周日 20:30 推送综合周报 — 聚合投资+社媒+闲鱼+成本"""
        now = time.localtime()
        # 仅周日 20:30-20:31 执行（避开 20:00 的策略评估）
        if now.tm_wday != 6 or now.tm_hour != 20 or now.tm_min != 30:
            return
        # 防止重复执行
        if hasattr(self, "_last_weekly_report") and self._last_weekly_report == now.tm_yday:
            return
        self._last_weekly_report = now.tm_yday
        try:
            from src.execution.daily_brief import weekly_report

            result = await weekly_report()
            if self._private_notify_func and result and len(str(result).strip()) > 20:
                await self._private_notify_func(result)
                logger.info("[Scheduler] 综合周报已推送")
        except Exception as e:
            logger.error("[Scheduler] 综合周报推送失败: %s", e)

    async def _run_morning_news(self, now):
        """每天早上 8:00 自动推送科技早报 — 不需要用户手动发 /news"""
        news_hour = safe_int(os.getenv("MORNING_NEWS_HOUR"), 8)
        news_enabled = os.getenv("MORNING_NEWS_ENABLED", "1").lower() in ("1", "true", "yes", "on")
        if not news_enabled:
            return
        today = now.strftime("%Y-%m-%d")
        # 防重复：每天只推一次
        if hasattr(self, "_last_news_date") and self._last_news_date == today:
            return
        if now.hour != news_hour or now.minute > 1:
            return
        self._last_news_date = today
        try:
            from src.news_fetcher import news_fetcher

            report = await news_fetcher.generate_morning_report()
            if self._private_notify_func and report and len(report.strip()) > 20:
                await self._private_notify_func(f"📰 今日科技早报\n\n{report}")
                logger.info("[Scheduler] 科技早报已自动推送")
        except Exception as e:
            logger.warning("[Scheduler] 科技早报推送失败: %s", e)

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
            logger.debug("Silenced exception", exc_info=True)  # 偏好系统不可用不影响默认行为

        try:
            from src.execution.daily_brief import generate_daily_brief

            monitors = self.monitor_manager._monitors if self.monitor_manager else None
            result = await generate_daily_brief(monitors=monitors)
            self._last_brief_date = today
            if self._notify_func and result and len(str(result).strip()) > 20:
                await self._notify_func(result)
        except Exception as e:
            logger.error("[Scheduler] daily brief failed: %s", e)

    async def _run_intel_brief(self, now, intel_brief_time):
        """Run Intel Brief through the sandbox or production safety gate."""
        from src.execution.intel_brief import build_intel_brief_scheduler_gate
        from src.intel.scheduled_pipeline import run_scheduled_sandbox_pipeline
        from src.intel.telegram_delivery import build_telegram_summary_delivery_probe

        gate = build_intel_brief_scheduler_gate(
            now=now,
            scheduled_time=intel_brief_time,
            last_run_date=self._last_intel_brief_date,
        )
        if gate["reason"] in {"disabled", "before_scheduled_time", "already_ran_today"}:
            return {"status": "skipped", "gate": gate}
        today = str(gate["run_date"])
        if not gate["should_run"]:
            self._last_intel_brief_date = today
            logger.warning("[Scheduler] Intel Brief blocked by safety gate: %s", gate.get("missing_gates", []))
            return {"status": "blocked", "gate": gate}

        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        evidence_dir = Path(str(gate["evidence_dir"]))
        if gate["mode"] == "production":
            evidence_path = evidence_dir / f"{stamp}-telegram-summary-production-delivery.json"
            runner_kwargs = {
                "summary_evidence_path": gate["summary_evidence"],
                "evidence_path": evidence_path,
                "allow_real_network": True,
            }
            if self.intel_brief_production_runner is None:
                result = await asyncio.to_thread(build_telegram_summary_delivery_probe, **runner_kwargs)
            else:
                result = self.intel_brief_production_runner(**runner_kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            self._last_intel_brief_date = today
            return result

        evidence_path = evidence_dir / f"{stamp}-scheduled-sandbox.json"
        runner_kwargs = {
            "collect_evidence_path": gate["collect_evidence"],
            "output_dir": evidence_dir,
            "evidence_path": evidence_path,
            "now_iso": gate["now_iso"],
            "scheduled_time": gate["scheduled_time"],
            "stamp": stamp,
            "llm_mode": os.getenv("INTEL_BRIEF_LLM_MODE", "fallback-only"),
        }
        if self.intel_brief_sandbox_runner is None:
            result = await asyncio.to_thread(run_scheduled_sandbox_pipeline, **runner_kwargs)
        else:
            result = self.intel_brief_sandbox_runner(**runner_kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        self._last_intel_brief_date = today
        return result

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

                formatted = "\n\n".join(MonitorManager.format_alert(al) for al in result if al)
                if formatted.strip():
                    await self._notify_func(formatted)
        except Exception as e:
            logger.error("[Scheduler] monitor failed: %s", e)

    async def _run_social_operator(self, ts, interval):
        if interval <= 0 or not self.social_autopilot_func:
            return
        if ts - self._last_social_operator_ts < interval:
            return
        try:
            await self.social_autopilot_func()
            self._last_social_operator_ts = ts
        except Exception as e:
            logger.error("[Scheduler] social operator failed: %s", e)

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
            logger.error("[Scheduler] bounty scan failed: %s", e)

    async def _run_reminders(self):
        """检查并触发到期的提醒 — 每60秒执行一次"""
        try:
            from src.execution.life_automation import fire_due_reminders

            fired = fire_due_reminders()
            for reminder in fired:
                msg = reminder["message"]
                chat_id = reminder.get("user_chat_id", 0)
                recurrence = reminder.get("recurrence_rule", "")

                # 格式化通知
                if recurrence:
                    repeat_label = f" (重复: {recurrence})"
                else:
                    repeat_label = ""
                notification = f"⏰ 提醒: {msg}{repeat_label}"

                # 发送通知
                if self._notify_func:
                    try:
                        if chat_id:
                            await self._notify_func(notification, chat_id=chat_id)
                        else:
                            await self._notify_func(notification)
                    except Exception as e:
                        logger.warning("[Reminders] 通知发送失败: %s", e)

                logger.info('[Reminders] 已触发: #%s "%s"', reminder["id"], msg)

        except Exception as e:
            logger.warning("[Reminders] 检查异常: %s", e)

    async def _run_bill_checks(self, now):
        """账单低余额告警 + 定期查询提醒

        - 每天 09:00 和 18:00 检查低余额告警
        - 每天 09:00 检查 remind_day 提醒
        """
        # 仅在整点的前 1 分钟执行，避免每分钟重复
        if now.minute > 0:
            return
        is_morning = now.hour == 9
        is_evening = now.hour == 18
        if not is_morning and not is_evening:
            return

        # 防止同一小时重复执行
        check_key = f"{now.strftime('%Y-%m-%d')}_{now.hour}"
        if hasattr(self, "_last_bill_check") and self._last_bill_check == check_key:
            return
        self._last_bill_check = check_key

        try:
            from src.execution.life_automation import (
                BILL_TYPE_EMOJI,
                BILL_TYPE_LABEL,
                check_bill_alerts,
                get_bill_reminders_due,
            )

            # 低余额告警 (09:00 和 18:00)
            alerts = check_bill_alerts()
            for alert in alerts:
                emoji = BILL_TYPE_EMOJI.get(alert["account_type"], "📄")
                label = BILL_TYPE_LABEL.get(alert["account_type"], alert["account_type"])
                name = alert.get("account_name", "")
                msg = (
                    f"⚠️ {emoji} {label}余额不足!\n"
                    f"{f"— {name}{chr(10)}" if name else ''}"
                    f"💰 余额: ¥{alert['balance']:.1f} (阈值: ¥{alert['low_threshold']:.0f})\n"
                    f"请尽快充值!"
                )
                chat_id = int(alert.get("chat_id", 0))
                if self._notify_func:
                    try:
                        if chat_id:
                            await self._notify_func(msg, chat_id=chat_id)
                        else:
                            await self._notify_func(msg)
                    except Exception as e:
                        logger.warning("[Bill] 低余额告警通知失败: %s", e)

                # 发布 BILL_DUE 事件
                try:
                    from src.core.event_bus import EventType, get_event_bus

                    bus = get_event_bus()
                    await bus.publish(
                        EventType.BILL_DUE,
                        {
                            "user_id": alert["user_id"],
                            "chat_id": alert.get("chat_id", ""),
                            "account_type": alert["account_type"],
                            "account_name": name,
                            "balance": alert["balance"],
                            "threshold": alert["low_threshold"],
                        },
                        source="scheduler_bill_alert",
                    )
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)

            # 定期查询提醒 (仅 09:00)
            if is_morning:
                reminders = get_bill_reminders_due()
                for rem in reminders:
                    emoji = BILL_TYPE_EMOJI.get(rem["account_type"], "📄")
                    label = BILL_TYPE_LABEL.get(rem["account_type"], rem["account_type"])
                    name = rem.get("account_name", "")
                    msg = (
                        f"🔔 {emoji} {label}查询提醒\n"
                        f"{f"— {name}{chr(10)}" if name else ''}"
                        f"上次余额: ¥{rem['balance']:.1f}\n"
                        f"请查询最新余额并告诉我"
                    )
                    chat_id = int(rem.get("chat_id", 0))
                    if self._notify_func:
                        try:
                            if chat_id:
                                await self._notify_func(msg, chat_id=chat_id)
                            else:
                                await self._notify_func(msg)
                        except Exception as e:
                            logger.warning("[Bill] 查询提醒通知失败: %s", e)

            if alerts or (is_morning and reminders):
                logger.info(
                    "[Scheduler] 账单检查: %d个低余额告警, %d个查询提醒",
                    len(alerts),
                    len(reminders) if is_morning else 0,
                )
        except Exception as e:
            logger.warning("[Scheduler] 账单检查异常: %s", e)

    async def _run_xianyu_shipment_check(self):
        """检查超时未发货的闲鱼订单并提醒"""
        try:
            from src.xianyu.xianyu_context import XianyuContextManager

            ctx = XianyuContextManager()
            pending = ctx.get_pending_shipments(hours_threshold=4)
            if not pending:
                return
            for order in pending:
                # 计算等待小时数（ts 是 SQLite datetime 文本格式）
                try:
                    from datetime import datetime as _dt

                    order_time = _dt.strptime(order["ts"], "%Y-%m-%d %H:%M:%S")
                    hours_ago = int((time.time() - order_time.timestamp()) / 3600)
                except Exception as e:  # noqa: F841
                    hours_ago = 4  # 解析失败时使用默认值
                msg = f"⚠️ 闲鱼发货提醒\n商品: {order.get('item_id', '未知')}\n已等待发货 {hours_ago} 小时\n请尽快处理！"
                if self._private_notify_func:
                    try:
                        await self._private_notify_func(msg)
                    except Exception as e:
                        logger.warning("[Xianyu] 发货提醒通知失败: %s", e)
                ctx.mark_shipment_reminded(order["id"])
        except ImportError:
            pass  # 闲鱼模块未安装
        except Exception as e:
            logger.warning("[Xianyu] 发货检查异常: %s", e)

    async def _run_stock_check(self, ts):
        """每4小时巡检闲鱼商品库存，低于阈值推送 Telegram 预警"""
        if ts - self._last_stock_check_ts < 14400:  # 4小时
            return
        self._last_stock_check_ts = ts
        try:
            from src.xianyu.auto_shipper import AutoShipper

            low_items = AutoShipper().check_low_stock(threshold=3)
            for item in low_items:
                iid = item["item_id"]
                # 24小时冷却，避免重复通知
                if ts - self._stock_alert_cooldown.get(iid, 0) < 86400:
                    continue
                self._stock_alert_cooldown[iid] = ts
                if self._private_notify_func:
                    await self._private_notify_func(
                        f"⚠️ 库存预警\n商品: {iid}\n剩余: {item['available']} 张\n请及时补货！"
                    )
        except ImportError:
            pass  # 合理保留：可选依赖缺失时继续走后续降级链
        except Exception as e:
            logger.debug("[Scheduler] 库存巡检异常: %s", e)

    async def _run_price_watch_check(self, now, ts):
        """每6小时检查降价监控 — 06:00/12:00/18:00/00:00 ET 各执行一次"""
        # 仅在整点 0/6/12/18 的前2分钟内触发
        if now.hour not in (0, 6, 12, 18) or now.minute > 1:
            return
        # 6小时间隔防重复 (略低于6h，容忍时间漂移)
        if ts - self._last_price_watch_ts < 21000:
            return
        self._last_price_watch_ts = ts
        try:
            from src.execution.life_automation import check_price_watches

            triggered = await check_price_watches(
                notify_func=self._notify_func,
            )
            if triggered > 0:
                logger.info("[Scheduler] 降价监控: %d 个商品达到目标价", triggered)
        except Exception as e:
            logger.warning("[Scheduler] 降价监控检查异常: %s", e)

    async def _run_deal_scan(self, ts: float) -> None:
        """每 4 小时扫描全网折扣；失败后保留冷却，避免反复轰炸外部站点。"""
        interval = max(1, safe_int(os.getenv("OPS_DEAL_SCAN_INTERVAL_MIN", "240"), 240)) * 60
        if ts - self._last_deal_scan_ts < interval:
            return
        self._last_deal_scan_ts = ts

        try:
            from src.shopping.deal_scanner import scheduled_deal_scan

            await scheduled_deal_scan()
        except Exception as error:
            logger.warning("[Scheduler] 折扣扫描失败: %s", type(error).__name__)

    async def _run_budget_alert(self, now):
        """每天 20:00 检查所有用户的月预算使用情况

        超过预算 80% 则推送提醒到用户的私聊
        """
        # 仅在 20:00 的前 1 分钟执行
        if now.hour != 20 or now.minute > 0:
            return
        # 防止同一天重复执行
        today = now.strftime("%Y-%m-%d")
        if hasattr(self, "_last_budget_alert_date") and self._last_budget_alert_date == today:
            return
        self._last_budget_alert_date = today

        try:
            from src.execution._db import get_conn
            from src.execution.life_automation import check_budget_alert

            # 查询所有设有预算的用户
            with get_conn() as conn:
                rows = conn.execute("SELECT user_id, monthly_budget FROM budgets WHERE monthly_budget > 0").fetchall()

            if not rows:
                return

            alert_count = 0
            for user_id_str, _budget in rows:
                try:
                    user_id = int(user_id_str)
                except (ValueError, TypeError) as e:  # noqa: F841
                    continue

                is_over, msg = check_budget_alert(user_id)
                if is_over and self._private_notify_func:
                    try:
                        await self._private_notify_func(msg)
                        alert_count += 1
                    except Exception as e:
                        logger.warning("[Budget] 超支提醒发送失败: %s", e)

            if alert_count > 0:
                logger.info("[Scheduler] 预算检查: 发送 %d 条超支提醒", alert_count)
        except Exception as e:
            logger.warning("[Scheduler] 预算检查异常: %s", e)

    async def _run_cleanup(self, now):
        if now.minute != 0:
            return
        try:
            from src.bot.globals import _cleanup_pending_trades

            _cleanup_pending_trades()
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        controls = _load_scheduler_controls()
        # Daily database cleanup — run once at 03:00 ET to bound DB growth
        if now.hour == 3 and _task_enabled(controls, "db_cleanup"):
            _run_daily_db_cleanup()

        # Daily database backup — run once at 04:00 ET (after cleanup)
        if now.hour == 4 and _task_enabled(controls, "db_backup"):
            summary = _run_daily_db_backup()
            if summary["failed"] > 0 and self._private_notify_func:
                alert_date = now.date().isoformat()
                if self._last_backup_alert_date != alert_date:
                    self._last_backup_alert_date = alert_date
                    try:
                        await self._private_notify_func(
                            "⚠️ 数据库备份失败，系统已保留错误状态且不会自动覆盖生产数据。\n"
                            "请打开老板状态入口查看备份红灯，再运行可丢弃恢复演练。"
                        )
                    except Exception as error:
                        logger.warning("[Scheduler] 备份失败提醒发送失败: %s", error)


def _run_daily_db_cleanup():
    """Purge old records from trading journal, feedback, and cost tracking DBs."""
    # Trading journal: keep 1 year of closed trades
    try:
        from src.trading_journal import journal

        deleted = journal.cleanup(days=365)
        if deleted:
            logger.info("[Scheduler] trading journal cleanup: %d rows", deleted)
    except Exception:
        logger.debug("[Scheduler] trading journal cleanup failed", exc_info=True)

    # Feedback store: keep 90 days
    try:
        from src.feedback import get_feedback_store

        store = get_feedback_store()
        deleted = store.cleanup(days=90)
        if deleted:
            logger.info("[Scheduler] feedback cleanup: %d rows", deleted)
    except Exception:
        logger.debug("[Scheduler] feedback cleanup failed", exc_info=True)

    # Cost analyzer: keep 30 days (method already exists, just never auto-called)
    try:
        from src.monitoring import cost_analyzer

        cost_analyzer.cleanup(days=30)
    except Exception:
        logger.debug("[Scheduler] cost analyzer cleanup failed", exc_info=True)

    # 降价监控 + 账单追踪: 清理过期/已删除数据
    try:
        from src.execution.life_automation import cleanup_stale_watches

        result = cleanup_stale_watches(days_triggered=30, days_expired=90)
        total = sum(result.values())
        if total:
            logger.info("[Scheduler] stale watches cleanup: %s", result)
    except Exception:
        logger.debug("[Scheduler] stale watches cleanup failed", exc_info=True)


def _run_daily_db_backup() -> dict[str, int]:
    """运行 SQLite 在线备份，并返回调度器可告警的脱敏计数。"""
    try:
        from scripts.backup_databases import backup_all

        results = backup_all()
        database_results = {
            key: value
            for key, value in results.items()
            if not str(key).startswith("_")
        }
        ok_count = sum(1 for value in database_results.values() if value.startswith("OK"))
        skip_count = sum(1 for value in database_results.values() if "skipped" in value)
        fail_count = sum(1 for value in results.values() if "FAILED" in str(value))
        logger.info("[Scheduler] DB backup: %d OK, %d skipped, %d failed", ok_count, skip_count, fail_count)
        if fail_count > 0:
            for db, status in results.items():
                if isinstance(status, str) and "FAILED" in status:
                    logger.error("[Scheduler] Backup failed: %s → %s", db, status)
        return {"ok": ok_count, "skipped": skip_count, "failed": fail_count}
    except Exception:
        logger.error("[Scheduler] daily DB backup failed", exc_info=True)
        return {"ok": 0, "skipped": 0, "failed": 1}
