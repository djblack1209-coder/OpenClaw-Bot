"""异步工具函数 — 统一的任务创建与监控

提供 create_monitored_task() 替代裸 asyncio.create_task()，
确保所有异步任务的异常都会被记录，不会静默丢失。
"""

import asyncio
import logging
from collections.abc import Coroutine

logger = logging.getLogger(__name__)


def create_monitored_task(
    coro: Coroutine,
    *,
    name: str | None = None,
    task_logger: logging.Logger | None = None,
) -> asyncio.Task:
    """创建带异常监控的异步任务

    替代 asyncio.create_task()，自动添加 done_callback，
    任务异常时记录错误日志，避免"幽灵任务"静默崩溃。

    Args:
        coro: 要执行的协程
        name: 任务名称，用于日志识别（可选）
        task_logger: 自定义 logger，默认使用本模块 logger

    Returns:
        asyncio.Task: 带监控回调的任务对象

    用法:
        # 替代: asyncio.create_task(some_coro())
        task = create_monitored_task(some_coro(), name="heartbeat")
    """
    task = asyncio.create_task(coro, name=name)
    _log = task_logger or logger

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            _log.debug("任务 %s 已取消", t.get_name())
            return
        exc = t.exception()
        if exc:
            _log.error(
                "异步任务 '%s' 执行失败: %s",
                t.get_name(),
                exc,
                exc_info=exc,
            )

    task.add_done_callback(_on_done)
    return task
