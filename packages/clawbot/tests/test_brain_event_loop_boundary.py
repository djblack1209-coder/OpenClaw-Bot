"""Brain、EventBus 与 API 的跨线程事件循环边界测试。"""

import asyncio
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import src.core.brain as brain_module
from src.api.routers import conversation, omega
from src.core.brain import OpenClawBrain
from src.core.event_bus import EventBus
from src.core.loop_owner import AsyncLoopOwner, OwnerLoopNotReady

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _start_owner_loop(bind) -> tuple[asyncio.AbstractEventLoop, threading.Thread]:
    """在真实独立线程启动并绑定一个所有者事件循环。"""
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    async def setup() -> None:
        await bind()
        ready.set()

    def run() -> None:
        asyncio.set_event_loop(loop)
        setup_task = loop.create_task(setup())
        loop.run_forever()
        assert setup_task.done()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

    thread = threading.Thread(target=run, name="brain-event-owner-test", daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    return loop, thread


def _stop_owner_loop(loop: asyncio.AbstractEventLoop, thread: threading.Thread) -> None:
    """停止测试所有者循环。"""
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)
    assert not thread.is_alive()


@pytest.fixture(autouse=True)
def _reset_brain_singleton():
    """隔离 Brain 单例，避免边界测试污染其他用例。"""
    previous = brain_module._brain
    brain_module._brain = None
    yield
    brain_module._brain = previous


def test_event_bus_cross_loop_handler_runs_once_on_owner_thread():
    bus = EventBus(audit_enabled=False)
    calls: list[int] = []

    async def bind() -> None:
        bus.bind_current_loop()

        async def telegram_handler(_event) -> None:
            calls.append(threading.get_ident())

        bus.subscribe("brain.progress", telegram_handler, "telegram")

    loop, thread = _start_owner_loop(bind)
    try:
        count = asyncio.run(bus.publish("brain.progress", {"step": 1}))

        assert count == 1
        assert calls == [thread.ident]
    finally:
        _stop_owner_loop(loop, thread)


def test_cancelled_event_publisher_does_not_truncate_notification_handler():
    bus = EventBus(audit_enabled=False)
    started = threading.Event()
    completed = threading.Event()

    async def bind() -> None:
        bus.bind_current_loop()

        async def telegram_handler(_event) -> None:
            started.set()
            await asyncio.sleep(0.05)
            completed.set()

        bus.subscribe("system.task_completed", telegram_handler, "telegram")

    loop, thread = _start_owner_loop(bind)
    try:

        async def cancel_publisher() -> None:
            task = asyncio.create_task(bus.publish("system.task_completed", {"task_id": "one"}))
            assert await asyncio.to_thread(started.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(cancel_publisher())

        assert completed.wait(timeout=1)
    finally:
        _stop_owner_loop(loop, thread)


def test_brain_cross_loop_process_runs_once_on_owner_thread():
    brain = object.__new__(OpenClawBrain)
    brain._loop_owner = AsyncLoopOwner("brain")
    calls: list[int] = []

    async def process_on_owner(**_kwargs):
        calls.append(threading.get_ident())
        return "owner-result"

    brain._process_message_on_owner = process_on_owner

    async def bind() -> None:
        brain.bind_current_loop()

    loop, thread = _start_owner_loop(bind)
    try:
        result = asyncio.run(brain.process_message(source="api", message="hello"))

        assert result == "owner-result"
        assert calls == [thread.ident]
    finally:
        _stop_owner_loop(loop, thread)


def test_cancelled_brain_waiter_does_not_cancel_owner_side_effect():
    brain = object.__new__(OpenClawBrain)
    brain._loop_owner = AsyncLoopOwner("brain")
    started = threading.Event()
    completed = threading.Event()

    async def process_on_owner(**_kwargs):
        started.set()
        await asyncio.sleep(0.05)
        completed.set()
        return "owner-result"

    brain._process_message_on_owner = process_on_owner

    async def bind() -> None:
        brain.bind_current_loop()

    loop, thread = _start_owner_loop(bind)
    try:

        async def cancel_waiter() -> None:
            task = asyncio.create_task(brain.process_message(source="api", message="notify"))
            assert await asyncio.to_thread(started.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(cancel_waiter())

        assert completed.wait(timeout=1)
    finally:
        _stop_owner_loop(loop, thread)


async def test_brain_singleton_is_not_lazy_and_init_is_idempotent():
    with pytest.raises(OwnerLoopNotReady):
        brain_module.get_brain()

    event_bus = MagicMock(publish=AsyncMock())
    with patch("src.core.brain.get_event_bus", return_value=event_bus):
        first = brain_module.init_brain()
        second = brain_module.init_brain()

    assert first is second
    assert brain_module.get_brain() is first
    assert first._loop_owner.is_current() is True


async def test_omega_process_fails_closed_when_brain_is_not_ready():
    with pytest.raises(HTTPException) as exc_info:
        await omega.omega_process(message="hello", source="api")

    assert exc_info.value.status_code == 503


async def test_conversation_send_fails_before_recording_when_brain_is_not_ready():
    session = conversation._store.create_session("owner-boundary")

    with pytest.raises(HTTPException) as exc_info:
        await conversation.send_message(session["id"], message="hello")

    assert exc_info.value.status_code == 503
    assert conversation._store.get_session(session["id"])["messages"] == []


def test_main_initializes_stateful_services_before_api_start():
    source = (PROJECT_ROOT / "multi_main.py").read_text(encoding="utf-8")

    event_bus_init = source.index("init_event_bus()")
    brain_init = source.index("init_brain()")
    ptb_start = source.index("start_results = await asyncio.gather(")
    trading_init = source.index("init_trading_system(")
    scheduler_start = source.index("await execution_hub.start_scheduler(")
    api_start = source.index("start_api_server(port=api_port)")

    assert event_bus_init < brain_init < ptb_start < trading_init < scheduler_start < api_start
