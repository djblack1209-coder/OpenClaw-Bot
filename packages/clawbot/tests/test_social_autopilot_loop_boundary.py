"""SocialAutopilot 的主事件循环所有权测试。"""

import asyncio
import threading
from pathlib import Path

import pytest
from fastapi import HTTPException

import src.social_scheduler as scheduler_module
from src.api.routers import social
from src.api.rpc import ClawBotRPC
from src.core.loop_owner import OwnerLoopNotReady
from src.social_scheduler import SocialAutopilot

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _start_owner(autopilot: SocialAutopilot):
    """在真实独立线程启动自动驾驶所有者循环。"""
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    async def setup() -> None:
        autopilot.bind_current_loop()
        ready.set()

    def run() -> None:
        asyncio.set_event_loop(loop)
        setup_task = loop.create_task(setup())
        loop.run_forever()
        assert setup_task.done()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

    thread = threading.Thread(target=run, name="autopilot-owner-test", daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    return loop, thread


def _stop_owner(loop: asyncio.AbstractEventLoop, thread: threading.Thread) -> None:
    """停止测试所有者循环。"""
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)
    assert not thread.is_alive()


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch, tmp_path):
    """隔离单例和持久化状态。"""
    previous_instance = SocialAutopilot._instance
    previous_loop = SocialAutopilot._main_loop
    SocialAutopilot._instance = None
    SocialAutopilot._main_loop = None
    monkeypatch.setattr(scheduler_module, "_STATE_FILE", tmp_path / "autopilot.json")
    yield
    SocialAutopilot._instance = previous_instance
    SocialAutopilot._main_loop = previous_loop


def test_rpc_fails_closed_before_autopilot_owner_is_ready():
    with pytest.raises(OwnerLoopNotReady):
        ClawBotRPC._rpc_autopilot_status()


def test_rpc_status_executes_on_owner_thread_once(monkeypatch):
    autopilot = SocialAutopilot()
    calls: list[int] = []

    def status_on_owner() -> dict:
        calls.append(threading.get_ident())
        return {"running": False, "owner": True}

    monkeypatch.setattr(autopilot, "_status_on_owner", status_on_owner, raising=False)
    loop, thread = _start_owner(autopilot)
    try:
        result = ClawBotRPC._rpc_autopilot_status()

        assert result == {"running": False, "owner": True}
        assert calls == [thread.ident]
        assert SocialAutopilot._main_loop is loop
    finally:
        _stop_owner(loop, thread)


@pytest.mark.parametrize(
    ("rpc_name", "operation", "expected"),
    [
        ("_rpc_autopilot_start", "_start_on_owner", {"status": "started"}),
        ("_rpc_autopilot_stop", "_stop_on_owner", {"status": "stopped"}),
    ],
)
def test_rpc_scheduler_mutation_executes_on_owner_thread_once(
    monkeypatch,
    rpc_name: str,
    operation: str,
    expected: dict,
):
    autopilot = SocialAutopilot()
    calls: list[int] = []

    def mutate_on_owner() -> dict:
        calls.append(threading.get_ident())
        return expected

    monkeypatch.setattr(autopilot, operation, mutate_on_owner)
    loop, thread = _start_owner(autopilot)
    try:
        result = getattr(ClawBotRPC, rpc_name)()

        assert result == expected
        assert calls == [thread.ident]
        assert SocialAutopilot._main_loop is loop
    finally:
        _stop_owner(loop, thread)


def test_cancelled_api_waiter_does_not_cancel_autopilot_side_effect(monkeypatch):
    autopilot = SocialAutopilot()
    started = threading.Event()
    completed = threading.Event()

    async def invoke_on_owner(_operation: str, *_args, **_kwargs):
        started.set()
        await asyncio.sleep(0.05)
        completed.set()
        return {"status": "started"}

    monkeypatch.setattr(autopilot, "_invoke_on_owner", invoke_on_owner, raising=False)
    loop, thread = _start_owner(autopilot)
    try:

        async def cancel_waiter() -> None:
            task = asyncio.create_task(autopilot.call_on_owner("start"))
            assert await asyncio.to_thread(started.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(cancel_waiter())

        assert completed.wait(timeout=1)
    finally:
        _stop_owner(loop, thread)


def test_trigger_job_runs_worker_body_off_owner_loop(monkeypatch):
    autopilot = SocialAutopilot()
    calls: list[tuple[str, int]] = []

    def trigger_on_worker(job_id: str) -> dict:
        calls.append((job_id, threading.get_ident()))
        return {"success": True, "job_id": job_id}

    monkeypatch.setattr(autopilot, "_trigger_job_on_worker", trigger_on_worker, raising=False)
    loop, thread = _start_owner(autopilot)
    try:
        result = ClawBotRPC._rpc_autopilot_trigger("morning_scan")

        assert result == {"success": True, "job_id": "morning_scan"}
        assert calls[0][0] == "morning_scan"
        assert calls[0][1] != thread.ident
    finally:
        _stop_owner(loop, thread)


def test_autopilot_api_fails_closed_when_owner_is_not_ready():
    with pytest.raises(HTTPException) as exc_info:
        social.autopilot_start()

    assert exc_info.value.status_code == 503


def test_scheduler_job_fails_closed_without_owner_loop():
    executed = False

    async def operation() -> None:
        nonlocal executed
        executed = True

    with pytest.raises(OwnerLoopNotReady):
        scheduler_module._run_async(operation())

    assert executed is False


def test_main_binds_autopilot_before_api_start():
    source = (PROJECT_ROOT / "multi_main.py").read_text(encoding="utf-8")

    bind = source.index("_autopilot.bind_current_loop()")
    api_start = source.index("start_api_server(port=api_port)")

    assert bind < api_start

    close = source.index("await _autopilot.close()")
    api_stop = source.index("stop_api_server()")
    assert close < api_stop


def test_autopilot_close_releases_scheduler_without_disabling_persisted_intent(monkeypatch):
    """进程关闭应释放线程调度器与循环引用，但保留用户的 enabled 意图。"""
    autopilot = SocialAutopilot()
    persisted = {"enabled": True}
    monkeypatch.setattr(scheduler_module, "_load_state", lambda: dict(persisted))

    class FakeScheduler:
        running = True

        def __init__(self):
            self.shutdown_calls = 0

        def shutdown(self, wait=False):
            assert wait is False
            self.shutdown_calls += 1
            self.running = False

    scheduler = FakeScheduler()
    autopilot._scheduler = scheduler
    loop, thread = _start_owner(autopilot)
    try:
        result = asyncio.run_coroutine_threadsafe(autopilot.close(), loop).result(timeout=1)
        assert result == {"status": "closed", "was_running": True}
        assert scheduler.shutdown_calls == 1
        assert autopilot._scheduler is None
        assert autopilot._main_loop is None
        assert SocialAutopilot._main_loop is None
        assert persisted["enabled"] is True
        assert autopilot._loop_owner.is_closed is True
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        assert not thread.is_alive()
