"""跨线程异步对象的所有者事件循环桥接。"""

import asyncio
import concurrent.futures
import contextlib
import threading
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class OwnerLoopError(RuntimeError):
    """所有者事件循环不可用或执行失败。"""


class OwnerLoopNotReady(OwnerLoopError):
    """有状态异步对象尚未登记所有者事件循环。"""


class OwnerLoopTimeout(OwnerLoopError):
    """提交到所有者事件循环的操作超过等待上限。"""


class AsyncLoopOwner:
    """把有状态异步操作固定提交到首次绑定的事件循环。"""

    def __init__(self, name: str):
        self.name = str(name or "async-resource")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread_id: int | None = None
        self._lock = threading.Lock()
        self._closing = False
        self._closed = False
        self._pending: set[concurrent.futures.Future] = set()
        self._tasks: set[asyncio.Task] = set()
        self._monitor_thread: threading.Thread | None = None

    @property
    def is_bound(self) -> bool:
        with self._lock:
            return bool(
                self._loop
                and not self._closing
                and not self._closed
                and self._loop.is_running()
                and not self._loop.is_closed()
            )

    @property
    def is_closing(self) -> bool:
        """返回所有者循环是否正在关闭。"""
        with self._lock:
            return self._closing

    @property
    def is_closed(self) -> bool:
        """返回所有者是否已经终态关闭。"""
        with self._lock:
            return self._closed

    @staticmethod
    def _fail_future(future: concurrent.futures.Future, message: str) -> None:
        """并发取消可能抢先完成 Future；此时保持原终态即可。"""
        with contextlib.suppress(concurrent.futures.InvalidStateError):
            future.set_exception(OwnerLoopNotReady(message))

    def _watch_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """监视 owner 循环停止，终结排队但永远不会执行的提交。"""
        while True:
            with self._lock:
                if self._loop is not loop or self._closed:
                    return
                if loop.is_running() and not loop.is_closed():
                    should_close = False
                elif not loop.is_closed() and not self._pending:
                    # run_until_complete() 返回后、run_forever() 开始前，循环可能短暂空闲；
                    # 这不是关闭信号，不能让监视线程抢先终结所有者绑定。
                    should_close = False
                else:
                    self._closing = True
                    self._closed = True
                    self._loop = None
                    self._thread_id = None
                    pending = list(self._pending)
                    self._pending.clear()
                    should_close = True
            if should_close:
                for future in pending:
                    if not future.done():
                        self._fail_future(future, f"{self.name} 所有者事件循环已关闭")
                return
            time.sleep(0.01)

    def _track_task(self, task: asyncio.Task) -> asyncio.Task:
        """登记 owner 任务，循环关闭前由 close guard 统一取消并排空。"""
        with self._lock:
            self._tasks.add(task)

        def remove(done: asyncio.Task) -> None:
            with self._lock:
                self._tasks.discard(done)

        task.add_done_callback(remove)
        return task

    def _drain_tasks_before_loop_close(self, loop: asyncio.AbstractEventLoop) -> None:
        """在 owner 线程真正 close 前取消并排空仍在运行的任务。"""
        with self._lock:
            tasks = [
                task
                for task in self._tasks
                if task.get_loop() is loop and not task.done()
            ]
            is_current_owner = self._loop is loop
            if is_current_owner:
                self._closing = True
                self._closed = True
                self._loop = None
                self._thread_id = None
                pending = list(self._pending)
                self._pending.clear()
            else:
                pending = []
        for future in pending:
            if not future.done():
                self._fail_future(future, f"{self.name} 所有者事件循环已关闭")
        for task in tasks:
            task.cancel()
        if not tasks or loop.is_running():
            return

        async def drain() -> None:
            await asyncio.gather(*tasks, return_exceptions=True)

        # close() 通常在 run_forever 返回后由 owner 线程调用，此时可安全跑一轮取消清理。
        with contextlib.suppress(Exception):
            loop.run_until_complete(asyncio.wait_for(drain(), timeout=2.0))
        with self._lock:
            self._tasks.difference_update(tasks)

    def _install_close_guard(self, loop: asyncio.AbstractEventLoop) -> None:
        """把任务排空挂到 loop.close，覆盖外部直接 stop/close 的生命周期路径。"""
        previous_close = loop.close

        def guarded_close() -> None:
            self._drain_tasks_before_loop_close(loop)
            previous_close()

        loop.close = guarded_close  # type: ignore[method-assign]

    def bind_current(self) -> None:
        """将当前运行循环登记为唯一所有者。"""
        loop = asyncio.get_running_loop()
        thread_id = threading.get_ident()
        stale_pending: list[concurrent.futures.Future] = []
        monitor: threading.Thread | None = None
        with self._lock:
            if self._closed:
                raise OwnerLoopError(f"{self.name} 所有者已关闭，不能重新绑定")
            if self._loop is loop:
                self._thread_id = thread_id
                return
            if self._loop and self._loop.is_running() and not self._loop.is_closed():
                raise OwnerLoopError(f"{self.name} 已绑定到另一个运行中的事件循环")
            if self._loop is not None:
                stale_pending = list(self._pending)
                self._pending.clear()
            self._loop = loop
            self._thread_id = thread_id
            self._closing = False
            self._install_close_guard(loop)
            monitor = threading.Thread(
                target=self._watch_loop,
                args=(loop,),
                name=f"{self.name}-loop-watch",
                daemon=True,
            )
            self._monitor_thread = monitor
        for future in stale_pending:
            if not future.done():
                self._fail_future(future, f"{self.name} 原所有者事件循环已关闭")
        if monitor is not None:
            monitor.start()

    def clear_current(self) -> None:
        """仅允许所有者循环在关闭资源后解除绑定。"""
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._loop is not loop:
                raise OwnerLoopError(f"{self.name} 只能由所有者事件循环解除绑定")
            self._loop = None
            self._thread_id = None
            self._closing = True
            self._closed = True
            pending = list(self._pending)
            self._pending.clear()
        for future in pending:
            if not future.done():
                self._fail_future(future, f"{self.name} 所有者事件循环已关闭")

    def is_current(self) -> bool:
        """返回调用方是否正在所有者事件循环中运行。"""
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            return False
        with self._lock:
            return self._loop is current and self._thread_id == threading.get_ident()

    def submit(self, operation: Callable[[], Awaitable[T]]) -> concurrent.futures.Future[T]:
        """从同步线程把异步工厂提交给所有者循环。"""
        with self._lock:
            owner_loop = self._loop
            closing = self._closing or self._closed
        if (
            owner_loop is None
            or closing
            or not owner_loop.is_running()
            or owner_loop.is_closed()
            or getattr(owner_loop, "_stopping", False)
        ):
            raise OwnerLoopNotReady(f"{self.name} 所有者事件循环尚未就绪")

        result: concurrent.futures.Future[T] = concurrent.futures.Future()
        with self._lock:
            self._pending.add(result)

        def start_operation() -> None:
            with self._lock:
                accepted = (
                    self._loop is owner_loop
                    and not self._closing
                    and not self._closed
                    and not owner_loop.is_closed()
                    and not getattr(owner_loop, "_stopping", False)
                )
            if not accepted:
                with self._lock:
                    self._pending.discard(result)
                    if self._loop is owner_loop and getattr(owner_loop, "_stopping", False):
                        self._closing = True
                        self._closed = True
                        self._loop = None
                        self._thread_id = None
                if not result.done():
                    self._fail_future(result, f"{self.name} 所有者事件循环正在关闭")
                return

            async def invoke() -> None:
                try:
                    value = await operation()
                except asyncio.CancelledError:
                    result.cancel()
                except Exception as exc:
                    if not result.done():
                        with contextlib.suppress(concurrent.futures.InvalidStateError):
                            result.set_exception(exc)
                else:
                    if not result.done():
                        with contextlib.suppress(concurrent.futures.InvalidStateError):
                            result.set_result(value)
                finally:
                    with self._lock:
                        self._pending.discard(result)

            try:
                # Python 3.12 的 eager_start 避免 stop 回调与首个 task step 之间留下悬空协程。
                task_holder: list[asyncio.Task | None] = [None]

                def cancel_owner_task(done: concurrent.futures.Future) -> None:
                    if not done.cancelled() or task_holder[0] is None:
                        return
                    with contextlib.suppress(RuntimeError):
                        owner_loop.call_soon_threadsafe(task_holder[0].cancel)

                result.add_done_callback(cancel_owner_task)
                task = self._track_task(asyncio.Task(invoke(), loop=owner_loop, eager_start=True))
                task_holder[0] = task
                if result.cancelled():
                    task.cancel()
            except Exception:
                with self._lock:
                    self._pending.discard(result)
                if not result.done():
                    self._fail_future(result, f"{self.name} 所有者事件循环无法接收任务")

        try:
            owner_loop.call_soon_threadsafe(start_operation)
            return result
        except Exception:
            with self._lock:
                self._pending.discard(result)
            if not result.done():
                self._fail_future(result, f"{self.name} 所有者事件循环无法接收任务")
            raise OwnerLoopNotReady(f"{self.name} 所有者事件循环无法接收任务") from None

    async def run(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        timeout: float | None = 120.0,
        cancel_on_timeout: bool = True,
    ) -> T:
        """在所有者循环执行异步工厂；跨循环调用会线程安全转发。"""
        with self._lock:
            owner_loop = self._loop
            closing = self._closing or self._closed
        if (
            owner_loop is None
            or closing
            or not owner_loop.is_running()
            or owner_loop.is_closed()
            or getattr(owner_loop, "_stopping", False)
        ):
            raise OwnerLoopNotReady(f"{self.name} 所有者事件循环尚未就绪")
        if self.is_current():
            task = self._track_task(asyncio.ensure_future(operation()))
            waiter = task if cancel_on_timeout else asyncio.shield(task)
            try:
                if timeout is None:
                    return await waiter
                return await asyncio.wait_for(waiter, timeout=max(0.001, float(timeout)))
            except TimeoutError as exc:
                if cancel_on_timeout:
                    task.cancel()
                raise OwnerLoopTimeout(f"{self.name} 操作等待超过 {timeout:g} 秒") from exc
            except asyncio.CancelledError:
                if cancel_on_timeout:
                    task.cancel()
                raise

        future = self.submit(operation)
        wrapped = asyncio.wrap_future(future)
        waiter = wrapped if cancel_on_timeout else asyncio.shield(wrapped)
        try:
            if timeout is None:
                return await waiter
            return await asyncio.wait_for(waiter, timeout=max(0.001, float(timeout)))
        except TimeoutError as exc:
            if cancel_on_timeout:
                future.cancel()
            raise OwnerLoopTimeout(f"{self.name} 操作等待超过 {timeout:g} 秒") from exc
        except asyncio.CancelledError:
            if cancel_on_timeout:
                future.cancel()
            raise
