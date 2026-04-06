"""
ClawBot 监控 — 健康检查 + 自动恢复

HealthChecker: Bot 心跳 + 错误计数 + 不健康回调
AutoRecovery: 不健康 Bot 自动重启（带冷却 + 计数上限）
"""
import time
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)


class HealthChecker:
    """Bot 健康检查器"""

    def __init__(self):
        self._bot_status: Dict[str, Dict[str, Any]] = {}
        self._callbacks: List[Callable] = []

    def register_bot(self, bot_id: str):
        """注册 bot"""
        self._bot_status[bot_id] = {
            "healthy": True,
            "last_heartbeat": time.time(),
            "consecutive_errors": 0,
            "last_error": None,
            "restart_count": 0,
        }

    def heartbeat(self, bot_id: str):
        """心跳"""
        if bot_id in self._bot_status:
            self._bot_status[bot_id]["last_heartbeat"] = time.time()
            self._bot_status[bot_id]["healthy"] = True

    def record_error(self, bot_id: str, error: str):
        """记录错误"""
        if bot_id not in self._bot_status:
            return
        status = self._bot_status[bot_id]
        status["consecutive_errors"] += 1
        status["last_error"] = error
        if status["consecutive_errors"] >= 5:
            status["healthy"] = False
            # EventBus: Bot 健康状态变更为不健康
            try:
                from src.core.event_bus import get_event_bus
                bus = get_event_bus()
                if bus:
                    import asyncio as _asyncio
                    try:
                        loop = _asyncio.get_running_loop()
                        _t = loop.create_task(bus.publish("system.bot_health", {
                            "bot_id": bot_id, "healthy": False,
                            "consecutive_errors": status["consecutive_errors"],
                            "last_error": error,
                        }))
                        _t.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
                    except RuntimeError as e:  # noqa: F841
                        pass
            except Exception as e:
                logger.debug("静默异常: %s", e)

    def record_success(self, bot_id: str):
        """记录成功"""
        if bot_id in self._bot_status:
            self._bot_status[bot_id]["consecutive_errors"] = 0
            self._bot_status[bot_id]["healthy"] = True

    def on_unhealthy(self, callback: Callable):
        """注册不健康回调"""
        self._callbacks.append(callback)

    def check_all(self) -> Dict[str, bool]:
        """检查所有 bot 健康状态"""
        now = time.time()
        results = {}
        for bot_id, status in self._bot_status.items():
            # 超过5分钟没有心跳视为不健康
            if now - status["last_heartbeat"] > 300:
                status["healthy"] = False
            results[bot_id] = status["healthy"]

            if not status["healthy"]:
                for cb in self._callbacks:
                    try:
                        cb(bot_id, status)
                    except Exception as e:
                        logger.debug("[HealthChecker] 回调执行失败: %s", e)
        return results

    def get_status(self) -> Dict[str, Any]:
        return {
            bot_id: {
                "healthy": s["healthy"],
                "last_heartbeat_ago": round(time.time() - s["last_heartbeat"], 0),
                "consecutive_errors": s["consecutive_errors"],
                "last_error": s["last_error"],
                "restart_count": s["restart_count"],
            }
            for bot_id, s in self._bot_status.items()
        }


class AutoRecovery:
    """Bot 自动恢复管理器"""

    def __init__(
        self,
        health_checker: HealthChecker,
        max_restarts: int = 3,
        restart_cooldown: float = 60.0,
        reset_window: float = 600.0,  # 持续健康10分钟后重置重启计数
        exhausted_cooldown: float = 1800.0,  # 重启次数耗尽后的冷却期（默认30分钟），冷却后重置计数再试
        notify_func: Optional[Callable] = None,  # Telegram 通知函数，崩溃/恢复时主动推送
    ):
        self.health = health_checker
        self.max_restarts = max_restarts
        self.restart_cooldown = restart_cooldown
        self.reset_window = reset_window
        self.exhausted_cooldown = exhausted_cooldown
        self._notify_func = notify_func
        self._restart_funcs: Dict[str, Callable] = {}
        self._stop_funcs: Dict[str, Callable] = {}  # 停止函数（重启前先停旧实例）
        self._last_restart: Dict[str, float] = {}
        self._last_healthy_since: Dict[str, float] = {}  # 持续健康起始时间
        self._exhausted_since: Dict[str, float] = {}  # 记录重启次数耗尽的时间
        self._notified_exhausted: set = set()  # 已通知过耗尽的 bot_id，防重复推送
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register_restart_func(self, bot_id: str, restart_func: Callable, stop_func: Optional[Callable] = None):
        """注册 bot 重启函数和停止函数"""
        self._restart_funcs[bot_id] = restart_func
        if stop_func:
            self._stop_funcs[bot_id] = stop_func

    async def _check_loop(self):
        """定期检查并自动恢复"""
        while self._running:
            try:
                statuses = self.health.check_all()
                now = time.time()
                for bot_id, healthy in statuses.items():
                    if healthy:
                        # 记录持续健康起始时间
                        if bot_id not in self._last_healthy_since:
                            self._last_healthy_since[bot_id] = now
                        # 持续健康超过 reset_window，重置重启计数
                        elif now - self._last_healthy_since[bot_id] > self.reset_window:
                            status = self.health._bot_status.get(bot_id, {})
                            if status.get("restart_count", 0) > 0:
                                logger.info(f"[{bot_id}] 持续健康 {self.reset_window:.0f}s，重置重启计数")
                                status["restart_count"] = 0
                                self._last_healthy_since[bot_id] = now
                    else:
                        # 不健康时清除健康计时
                        self._last_healthy_since.pop(bot_id, None)
                        await self._try_restart(bot_id)
            except Exception as e:
                logger.error(f"健康检查循环错误: {e}")

            await asyncio.sleep(30)  # 每30秒检查一次

    async def _try_restart(self, bot_id: str):
        """尝试重启 bot（先停旧实例，等待后再启新实例）"""
        status = self.health._bot_status.get(bot_id, {})
        restart_count = status.get("restart_count", 0)

        if restart_count >= self.max_restarts:
            now = time.time()
            exhausted_at = self._exhausted_since.get(bot_id)
            if exhausted_at is None:
                # 首次达到上限，记录时间并通知用户
                self._exhausted_since[bot_id] = now
                cooldown_min = self.exhausted_cooldown / 60
                logger.error(
                    f"[{bot_id}] 已达最大重启次数 ({self.max_restarts})，"
                    f"进入 {self.exhausted_cooldown:.0f}s 冷却期后再试"
                )
                # 主动推送 Telegram 通知 — 让用户知道 Bot 暂时不可用
                if self._notify_func and bot_id not in self._notified_exhausted:
                    self._notified_exhausted.add(bot_id)
                    try:
                        await self._notify_func(
                            f"⚠️ [{bot_id}] 连续崩溃 {self.max_restarts} 次，"
                            f"已暂停恢复 {cooldown_min:.0f} 分钟。\n"
                            f"通常是网络波动导致，冷却后系统会自动重试。"
                        )
                    except Exception:
                        pass
                return
            elif now - exhausted_at < self.exhausted_cooldown:
                # 仍在冷却期内，静默跳过（每5分钟打一条日志提醒）
                elapsed = now - exhausted_at
                remaining = self.exhausted_cooldown - elapsed
                if int(elapsed) % 300 < 30:  # 大约每5分钟打一次
                    logger.info(
                        f"[{bot_id}] 冷却中，还剩 {remaining:.0f}s 后重置重启计数"
                    )
                return
            else:
                # 冷却期结束，重置重启计数，再给一轮机会
                logger.warning(
                    f"[{bot_id}] 冷却期结束，重置重启计数，重新尝试恢复"
                )
                status["restart_count"] = 0
                restart_count = 0
                self._exhausted_since.pop(bot_id, None)
                self._notified_exhausted.discard(bot_id)
                # 通知用户系统正在重新尝试恢复
                if self._notify_func:
                    try:
                        await self._notify_func(f"🔄 [{bot_id}] 冷却结束，正在自动重连...")
                    except Exception:
                        pass

        last = self._last_restart.get(bot_id, 0)
        if time.time() - last < self.restart_cooldown:
            return

        restart_func = self._restart_funcs.get(bot_id)
        if not restart_func:
            logger.warning(f"[{bot_id}] 未注册重启函数")
            return

        logger.warning(f"[{bot_id}] 尝试自动恢复 (第 {restart_count + 1} 次)")
        self._last_restart[bot_id] = time.time()

        try:
            # 先停止旧的 polling 实例，防止 409 Conflict
            stop_func = self._stop_funcs.get(bot_id)
            if stop_func:
                logger.info(f"[{bot_id}] 停止旧实例...")
                try:
                    await stop_func()
                except Exception as e:
                    logger.debug(f"[{bot_id}] 停止旧实例时出错(可忽略): {e}")

            # 等待 Telegram 释放 polling 会话
            await asyncio.sleep(5)

            await restart_func()
            status["restart_count"] = restart_count + 1
            status["healthy"] = True
            status["consecutive_errors"] = 0
            status["last_heartbeat"] = time.time()
            # 恢复成功，清除耗尽状态
            self._exhausted_since.pop(bot_id, None)
            logger.info(f"[{bot_id}] 自动恢复成功")
        except Exception as e:
            status["restart_count"] = restart_count + 1
            logger.error(f"[{bot_id}] 自动恢复失败: {e}")

    def start(self):
        """启动自动恢复"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        def _recovery_done(t):
            if not t.cancelled() and t.exception():
                logger.warning("[AutoRecovery] 自动恢复循环崩溃: %s", t.exception())
        self._task.add_done_callback(_recovery_done)
        logger.info("自动恢复管理器已启动")

    def stop(self):
        """停止"""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("自动恢复管理器已停止")
