"""
ClawBot - 结构化日志 + 健康检查 + 自动恢复
"""
import time
import json
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ============ 结构化日志 ============

class StructuredLogger:
    """结构化日志记录器，追踪请求级别指标"""

    def __init__(self, name: str, log_dir: Optional[str] = None):
        self.name = name
        self._stats: Dict[str, Any] = {
            "start_time": time.time(),
            "total_messages": 0,
            "total_api_calls": 0,
            "total_errors": 0,
            "model_usage": {},       # model -> count
            "daily_messages": {},    # date -> count
            "api_latencies": [],     # 最近100次延迟
        }
        self._max_latencies = 100

        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = Path(__file__).parent.parent / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._metrics_path = self.log_dir / "metrics.json"
        self._load_metrics()

    def _load_metrics(self):
        """加载持久化的指标"""
        if self._metrics_path.exists():
            try:
                with open(self._metrics_path, 'r') as f:
                    saved = json.load(f)
                self._stats["total_messages"] = saved.get("total_messages", 0)
                self._stats["total_api_calls"] = saved.get("total_api_calls", 0)
                self._stats["total_errors"] = saved.get("total_errors", 0)
                self._stats["model_usage"] = saved.get("model_usage", {})
                self._stats["daily_messages"] = saved.get("daily_messages", {})
            except Exception as e:
                logger.warning("[Metrics] 加载指标文件失败: %s", e)

    def _save_metrics(self):
        """持久化指标"""
        try:
            data = {
                "total_messages": self._stats["total_messages"],
                "total_api_calls": self._stats["total_api_calls"],
                "total_errors": self._stats["total_errors"],
                "model_usage": self._stats["model_usage"],
                "daily_messages": self._stats["daily_messages"],
                "last_saved": datetime.now().isoformat(),
            }
            with open(self._metrics_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"保存指标失败: {e}")

    def log_message(self, bot_id: str, chat_id: int, user_id: int, text_length: int):
        """记录收到的消息"""
        self._stats["total_messages"] += 1
        today = datetime.now().strftime("%Y-%m-%d")
        self._stats["daily_messages"][today] = self._stats["daily_messages"].get(today, 0) + 1

        logger.info(
            f"[MSG] bot={bot_id} chat={chat_id} user={user_id} len={text_length}"
        )

        # 每50条消息持久化一次
        if self._stats["total_messages"] % 50 == 0:
            self._save_metrics()

    def log_api_call(
        self,
        bot_id: str,
        model: str,
        latency_ms: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error: Optional[str] = None,
    ):
        """记录 API 调用"""
        self._stats["total_api_calls"] += 1
        self._stats["model_usage"][model] = self._stats["model_usage"].get(model, 0) + 1

        latencies = self._stats["api_latencies"]
        latencies.append(latency_ms)
        if len(latencies) > self._max_latencies:
            self._stats["api_latencies"] = latencies[-self._max_latencies:]

        if not success:
            self._stats["total_errors"] += 1

        level = logging.INFO if success else logging.WARNING
        logger.log(
            level,
            f"[API] bot={bot_id} model={model} "
            f"latency={latency_ms:.0f}ms tokens={input_tokens}+{output_tokens} "
            f"{'OK' if success else f'FAIL: {error}'}"
        )

    def log_error(self, bot_id: str, error_type: str, error_msg: str):
        """记录错误"""
        self._stats["total_errors"] += 1
        logger.error(f"[ERR] bot={bot_id} type={error_type} msg={error_msg}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = time.time() - self._stats["start_time"]
        latencies = self._stats["api_latencies"]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        today = datetime.now().strftime("%Y-%m-%d")
        today_messages = self._stats["daily_messages"].get(today, 0)

        return {
            "uptime_hours": round(uptime / 3600, 1),
            "total_messages": self._stats["total_messages"],
            "today_messages": today_messages,
            "total_api_calls": self._stats["total_api_calls"],
            "total_errors": self._stats["total_errors"],
            "error_rate": round(
                self._stats["total_errors"] / max(self._stats["total_api_calls"], 1) * 100, 1
            ),
            "avg_latency_ms": round(avg_latency, 0),
            "model_usage": self._stats["model_usage"],
        }

    def shutdown(self):
        """关闭时保存"""
        self._save_metrics()


# ============ 健康检查 ============

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


# ============ 自动恢复 ============

class AutoRecovery:
    """Bot 自动恢复管理器"""

    def __init__(
        self,
        health_checker: HealthChecker,
        max_restarts: int = 3,
        restart_cooldown: float = 60.0,
        reset_window: float = 600.0,  # 持续健康10分钟后重置重启计数
    ):
        self.health = health_checker
        self.max_restarts = max_restarts
        self.restart_cooldown = restart_cooldown
        self.reset_window = reset_window
        self._restart_funcs: Dict[str, Callable] = {}
        self._stop_funcs: Dict[str, Callable] = {}  # 停止函数（重启前先停旧实例）
        self._last_restart: Dict[str, float] = {}
        self._last_healthy_since: Dict[str, float] = {}  # 持续健康起始时间
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
            logger.error(
                f"[{bot_id}] 已达最大重启次数 ({self.max_restarts})，放弃恢复"
            )
            return

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
        logger.info("自动恢复管理器已启动")

    def stop(self):
        """停止"""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("自动恢复管理器已停止")
