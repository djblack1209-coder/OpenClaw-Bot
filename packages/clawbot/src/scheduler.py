"""
ClawBot - 定时任务调度器
支持早报推送、定时提醒等
所有定时任务使用美东时间（America/New_York）
"""
import asyncio
from datetime import datetime, time, timedelta
from typing import Callable, Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _now_et() -> datetime:
    """获取当前美东时间"""
    try:
        return datetime.now(ET)
    except Exception as e:  # noqa: F841
        # Fallback: 返回带 UTC 时区的 datetime，避免 naive vs aware 比较异常
        from datetime import timezone
        return datetime.now(timezone.utc)


class Task:
    """定时任务（美东时间）"""

    def __init__(
        self,
        name: str,
        func: Callable,
        schedule_time: Optional[time] = None,
        interval_minutes: Optional[int] = None,
        enabled: bool = True
    ):
        self.name = name
        self.func = func
        self.schedule_time = schedule_time  # 每天固定时间执行（美东）
        self.interval_minutes = interval_minutes  # 间隔执行
        self.enabled = enabled
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self._calculate_next_run()

    def _calculate_next_run(self):
        """计算下次执行时间（美东时间）"""
        now = _now_et()

        if self.schedule_time:
            # 固定时间任务（美东）
            next_run = datetime.combine(now.date(), self.schedule_time, tzinfo=ET)
            if next_run <= now:
                next_run = datetime.combine(
                    now.date() + timedelta(days=1),
                    self.schedule_time,
                    tzinfo=ET,
                )
            self.next_run = next_run

        elif self.interval_minutes:
            # 间隔任务
            if self.last_run:
                self.next_run = self.last_run + timedelta(minutes=self.interval_minutes)
            else:
                self.next_run = now

    def should_run(self) -> bool:
        """判断是否应该执行"""
        if not self.enabled:
            return False
        if not self.next_run:
            return False
        return _now_et() >= self.next_run

    async def run(self) -> Any:
        """执行任务"""
        try:
            self.last_run = _now_et()
            result = await self.func()
            self._calculate_next_run()
            return result
        except Exception as e:
            logger.error(f"任务 {self.name} 执行失败: {e}")
            self._calculate_next_run()
            raise


class Scheduler:
    """任务调度器"""

    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def add_task(
        self,
        name: str,
        func: Callable,
        schedule_time: Optional[time] = None,
        interval_minutes: Optional[int] = None,
        enabled: bool = True
    ):
        """添加任务"""
        task = Task(
            name=name,
            func=func,
            schedule_time=schedule_time,
            interval_minutes=interval_minutes,
            enabled=enabled
        )
        self.tasks[name] = task
        logger.info(f"添加任务: {name}, 下次执行: {task.next_run}")

    def remove_task(self, name: str):
        """移除任务"""
        if name in self.tasks:
            del self.tasks[name]
            logger.info(f"移除任务: {name}")

    def enable_task(self, name: str):
        """启用任务"""
        if name in self.tasks:
            self.tasks[name].enabled = True

    def disable_task(self, name: str):
        """禁用任务"""
        if name in self.tasks:
            self.tasks[name].enabled = False

    async def _run_loop(self):
        """调度循环"""
        while self._running:
            for task in self.tasks.values():
                if task.should_run():
                    try:
                        logger.info(f"执行任务: {task.name}")
                        # P1#14: 用 create_task 并发执行，避免一个慢任务阻塞其他
                        _t = asyncio.create_task(self._safe_run_task(task))
                        _t.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
                    except Exception as e:
                        logger.error(f"任务调度错误: {e}")

            # 每分钟检查一次
            await asyncio.sleep(60)

    async def _safe_run_task(self, task: Task):
        """安全执行单个任务，异常不影响其他任务"""
        try:
            await task.run()
        except Exception as e:
            logger.error(f"任务执行错误 [{task.name}]: {e}")

    def start(self):
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        self._task.add_done_callback(lambda t: t.exception() and logger.error("调度器主循环崩溃: %s", t.exception()))
        logger.info("调度器已启动")

    def stop(self):
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("调度器已停止")

    def get_status(self) -> List[Dict[str, Any]]:
        """获取所有任务状态"""
        status = []
        for name, task in self.tasks.items():
            status.append({
                "name": name,
                "enabled": task.enabled,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "next_run": task.next_run.isoformat() if task.next_run else None
            })
        return status
