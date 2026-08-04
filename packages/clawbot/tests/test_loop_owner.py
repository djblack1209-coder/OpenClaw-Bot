import asyncio
import threading
import time

import pytest

from src.core.loop_owner import AsyncLoopOwner, OwnerLoopNotReady, OwnerLoopTimeout


def _start_owner_loop(owner: AsyncLoopOwner):
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_bind())
        ready.set()
        loop.run_forever()
        loop.close()

    async def _bind() -> None:
        owner.bind_current()

    thread = threading.Thread(target=run, name="owner-loop-test", daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    return loop, thread


def _stop_owner_loop(loop: asyncio.AbstractEventLoop, thread: threading.Thread) -> None:
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_cross_thread_submission_executes_on_bound_owner_loop():
    owner = AsyncLoopOwner("unit")
    loop, thread = _start_owner_loop(owner)
    try:

        async def capture_owner() -> tuple[int, int]:
            return id(asyncio.get_running_loop()), threading.get_ident()

        loop_id, thread_id = asyncio.run(owner.run(capture_owner, timeout=1))

        assert loop_id == id(loop)
        assert thread_id == thread.ident
    finally:
        _stop_owner_loop(loop, thread)


def test_unbound_owner_fails_closed_without_creating_coroutine():
    owner = AsyncLoopOwner("unit")
    created = False

    async def operation() -> None:
        nonlocal created
        created = True

    with pytest.raises(OwnerLoopNotReady):
        asyncio.run(owner.run(operation, timeout=1))
    assert created is False


def test_cross_loop_timeout_cancels_owner_task():
    owner = AsyncLoopOwner("unit")
    loop, thread = _start_owner_loop(owner)
    cancelled = threading.Event()
    try:

        async def wait_forever() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with pytest.raises(OwnerLoopTimeout):
            asyncio.run(owner.run(wait_forever, timeout=0.02))
        assert cancelled.wait(timeout=1)
    finally:
        _stop_owner_loop(loop, thread)


def test_cross_loop_timeout_can_leave_side_effect_operation_running():
    owner = AsyncLoopOwner("unit")
    loop, thread = _start_owner_loop(owner)
    completed = threading.Event()
    try:

        async def finish_later() -> None:
            await asyncio.sleep(0.05)
            completed.set()

        with pytest.raises(OwnerLoopTimeout):
            asyncio.run(owner.run(finish_later, timeout=0.01, cancel_on_timeout=False))
        assert completed.wait(timeout=1)
    finally:
        _stop_owner_loop(loop, thread)


def test_submit_schedules_from_synchronous_caller():
    owner = AsyncLoopOwner("unit")
    loop, thread = _start_owner_loop(owner)
    try:

        async def capture_owner() -> int:
            return threading.get_ident()

        future = owner.submit(capture_owner)

        assert future.result(timeout=1) == thread.ident
    finally:
        _stop_owner_loop(loop, thread)


def test_caller_cancellation_does_not_cancel_side_effect_operation():
    owner = AsyncLoopOwner("unit")
    loop, thread = _start_owner_loop(owner)
    completed = threading.Event()
    try:

        async def finish_later() -> None:
            await asyncio.sleep(0.05)
            completed.set()

        async def cancel_caller() -> None:
            task = asyncio.create_task(owner.run(finish_later, timeout=None, cancel_on_timeout=False))
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(cancel_caller())
        assert completed.wait(timeout=1)
    finally:
        _stop_owner_loop(loop, thread)


def test_same_loop_caller_cancellation_does_not_cancel_side_effect_operation():
    completed = False

    async def scenario() -> None:
        nonlocal completed
        owner = AsyncLoopOwner("unit")
        owner.bind_current()

        async def finish_later() -> None:
            nonlocal completed
            await asyncio.sleep(0.05)
            completed = True

        task = asyncio.create_task(owner.run(finish_later, timeout=None, cancel_on_timeout=False))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.06)

    asyncio.run(scenario())
    assert completed is True


def test_stop_queued_before_cross_loop_submit_fails_closed_without_running_operation():
    """所有者循环已排队停止时，新提交必须失败且不能遗留未 awaited 协程。"""
    owner = AsyncLoopOwner("unit")
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    operation_started = threading.Event()

    async def bind() -> None:
        owner.bind_current()

    def blocker() -> None:
        blocker_started.set()
        release_blocker.wait(timeout=1)

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bind())
        loop.call_soon(blocker)
        ready.set()
        loop.run_forever()
        loop.close()

    thread = threading.Thread(target=run, name="owner-loop-stop-race-test", daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    assert blocker_started.wait(timeout=2)

    async def operation() -> str:
        operation_started.set()
        return "must-not-run"

    loop.call_soon_threadsafe(loop.stop)

    async def submit_after_stop_request() -> None:
        task = asyncio.create_task(owner.run(operation, timeout=None, cancel_on_timeout=False))
        await asyncio.sleep(0)
        release_blocker.set()
        with pytest.raises(OwnerLoopNotReady):
            await task

    try:
        asyncio.run(submit_after_stop_request())
        assert operation_started.is_set() is False
    finally:
        release_blocker.set()
        thread.join(timeout=2)
        assert not thread.is_alive()

    assert owner.is_closed is True
    assert owner.is_bound is False


def test_stop_after_operation_started_drains_owner_task_before_loop_close():
    """停止已启动的 owner 操作时，Task 必须先完成取消清理再关闭循环。"""
    owner = AsyncLoopOwner("unit")
    loop, thread = _start_owner_loop(owner)
    started = threading.Event()
    try:

        async def operation() -> None:
            started.set()
            await asyncio.Event().wait()

        future = owner.submit(operation)
        assert started.wait(timeout=1)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert future.done()
        with pytest.raises(OwnerLoopNotReady):
            future.result()
        assert owner.is_closed is True
        assert owner._tasks == set()
    finally:
        if thread.is_alive():
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=2)


def test_idle_gap_between_bind_and_run_forever_does_not_close_owner():
    """启动流程的正常空档不能被监视线程误判为永久关闭。"""
    owner = AsyncLoopOwner("unit")
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    release = threading.Event()

    async def bind() -> None:
        owner.bind_current()

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bind())
        ready.set()
        release.wait(timeout=2)
        loop.run_forever()
        loop.close()

    thread = threading.Thread(target=run, name="owner-loop-idle-gap-test", daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    try:
        # 留出一个完整的 monitor 轮询周期，验证非 running 但未 closed 的空档可复用。
        time.sleep(0.05)
        assert owner.is_closed is False
    finally:
        loop.call_soon_threadsafe(loop.stop)
        release.set()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_loop_close_drains_already_started_owner_task():
    """循环直接 stop/close 时，已启动的 owner 任务必须收到取消并完成清理。"""
    owner = AsyncLoopOwner("unit")
    loop, thread = _start_owner_loop(owner)
    started = threading.Event()
    cancelled = threading.Event()

    async def wait_forever() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    try:
        future = owner.submit(wait_forever)
        assert started.wait(timeout=1)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert cancelled.is_set() is True
        assert future.done()
    finally:
        if thread.is_alive():
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=2)


def test_closing_stale_loop_does_not_close_rebound_owner():
    """旧循环关闭时不能污染已经重绑到新循环的 owner 状态。"""
    owner = AsyncLoopOwner("unit")
    first_loop = asyncio.new_event_loop()
    second_loop = asyncio.new_event_loop()

    async def bind() -> None:
        owner.bind_current()

    try:
        first_loop.run_until_complete(bind())
        second_loop.run_until_complete(bind())

        first_loop.close()

        assert owner._loop is second_loop
        assert owner.is_closing is False
        assert owner.is_closed is False

        async def verify_rebound_owner() -> str:
            assert owner.is_bound is True

            async def operation() -> str:
                return "second-loop"

            return await owner.run(operation, timeout=1)

        assert second_loop.run_until_complete(verify_rebound_owner()) == "second-loop"
    finally:
        if not first_loop.is_closed():
            first_loop.close()
        if not second_loop.is_closed():
            second_loop.close()
