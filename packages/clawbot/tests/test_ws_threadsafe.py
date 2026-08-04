"""WebSocket 跨线程事件投递边界测试。"""

import asyncio
import threading
from collections.abc import Callable

import pytest

from src.api.routers import ws
from src.api.schemas import WSMessageType


class _LoopThread:
    """为测试提供一个实际运行的 API 事件循环线程。"""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        self.ready.set()
        loop.run_forever()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

    def start(self) -> asyncio.AbstractEventLoop:
        self.thread.start()
        assert self.ready.wait(timeout=2)
        assert self.loop is not None
        return self.loop

    def close(self) -> None:
        assert self.loop is not None
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=2)
        assert not self.thread.is_alive()


@pytest.fixture(autouse=True)
def _clean_clients():
    """隔离模块级连接注册表，避免测试互相影响。"""
    with ws._lock:
        ws._client_queues.clear()
    yield
    with ws._lock:
        ws._client_queues.clear()


def _register_client(loop: asyncio.AbstractEventLoop, maxsize: int = 4):
    """在 WebSocket 所属事件循环中注册一个独立客户端队列。"""
    websocket = object()

    async def register():
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=maxsize)
        client = ws._ClientQueue(loop=loop, queue=queue)
        ws._register_client(websocket, client)
        return client

    client = asyncio.run_coroutine_threadsafe(register(), loop).result(timeout=2)
    return websocket, client


def _on_owner_loop(loop: asyncio.AbstractEventLoop, callback: Callable[[], object]) -> object:
    """在事件循环归属线程读取或修改队列。"""

    async def run():
        return callback()

    return asyncio.run_coroutine_threadsafe(run(), loop).result(timeout=2)


def test_push_event_from_other_thread_uses_api_loop_and_delivers_once(monkeypatch):
    """主线程推送必须由 WebSocket 所属 API 循环执行，且只送达一次。"""
    owner = _LoopThread()
    loop = owner.start()
    websocket, client = _register_client(loop)
    scheduled_callbacks: list[object] = []
    original_call_soon_threadsafe = loop.call_soon_threadsafe

    def record_schedule(callback, *args, context=None):
        if callback is ws._enqueue_event:
            scheduled_callbacks.append(callback)
        return original_call_soon_threadsafe(callback, *args, context=context)

    monkeypatch.setattr(loop, "call_soon_threadsafe", record_schedule)
    try:
        ws.push_event(WSMessageType.NOTIFICATION, {"message": "from-main-thread"})
        event, owner_thread_id = _on_owner_loop(
            loop,
            lambda: (client.queue.get_nowait(), threading.get_ident()),
        )

        assert event["data"] == {"message": "from-main-thread"}
        assert owner_thread_id == owner.thread.ident
        assert len(scheduled_callbacks) == 1
        assert _on_owner_loop(loop, lambda: client.queue.empty()) is True
    finally:
        ws._unregister_client(websocket, client)
        owner.close()


def test_full_client_queue_keeps_latest_event_without_blocking():
    """慢客户端队列已满时丢弃最旧事件，并且推送线程不等待消费者。"""
    owner = _LoopThread()
    loop = owner.start()
    websocket, client = _register_client(loop, maxsize=1)
    try:
        ws.push_event(WSMessageType.NOTIFICATION, {"sequence": 1})
        ws.push_event(WSMessageType.NOTIFICATION, {"sequence": 2})
        queued = _on_owner_loop(loop, lambda: client.queue.get_nowait())

        assert queued["data"] == {"sequence": 2}
        assert _on_owner_loop(loop, lambda: client.queue.empty()) is True
    finally:
        ws._unregister_client(websocket, client)
        owner.close()


def test_disconnected_client_is_not_scheduled_or_enqueued():
    """断开后的客户端既不安排回调，也不会收到后续事件。"""
    owner = _LoopThread()
    loop = owner.start()
    websocket, client = _register_client(loop)
    try:
        ws._unregister_client(websocket, client)
        ws.push_event(WSMessageType.NOTIFICATION, {"message": "ignored"})

        assert _on_owner_loop(loop, lambda: client.queue.empty()) is True
    finally:
        owner.close()
