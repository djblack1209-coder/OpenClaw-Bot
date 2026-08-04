"""WebSocket endpoint for real-time event streaming
搬运自 freqtrade/rpc/api_server/api_ws.py 的 pub/sub 模式

v2 修复:
  - HI-NEW-02: 共享 deque + popleft 导致多客户端丢消息 → 每客户端独立 asyncio.Queue
  - HI-NEW-03: 初始状态获取无异常保护 → 加 try/except 降级发送空状态
"""

import asyncio
import contextlib
import logging
import threading
from dataclasses import dataclass

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.utils import now_et

from ..auth import verify_ws_token
from ..schemas import WSMessageType

logger = logging.getLogger(__name__)
router = APIRouter()

# 每个客户端拥有独立的事件队列，避免 popleft 互抢。
# asyncio.Queue 只能在创建它的事件循环操作，因此同时记录所属循环。


@dataclass(frozen=True)
class _ClientQueue:
    """WebSocket 客户端的队列及其唯一归属事件循环。"""

    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, object]]


_client_queues: dict[WebSocket, _ClientQueue] = {}
_lock = threading.Lock()


def _register_client(websocket: WebSocket, client: _ClientQueue) -> None:
    """登记已接受连接的队列；调用方必须位于该客户端的 API 事件循环。"""
    with _lock:
        _client_queues[websocket] = client


def _unregister_client(websocket: WebSocket, client: _ClientQueue | None = None) -> None:
    """移除连接；仅移除同一代客户端，防止旧回调删掉重连后的队列。"""
    with _lock:
        current = _client_queues.get(websocket)
        if client is None or current is client:
            _client_queues.pop(websocket, None)


def _enqueue_event(websocket: WebSocket, client: _ClientQueue, event: dict[str, object]) -> None:
    """仅由客户端所属事件循环执行的入队回调。"""
    if asyncio.get_running_loop() is not client.loop:
        logger.error("[WS] 拒绝在非归属事件循环操作客户端队列")
        return

    with _lock:
        if _client_queues.get(websocket) is not client:
            return

    try:
        client.queue.put_nowait(event)
    except asyncio.QueueFull:
        # 慢客户端保留最新状态：先淘汰最旧事件，再写入当前事件。
        with contextlib.suppress(asyncio.QueueEmpty):
            client.queue.get_nowait()
        try:
            client.queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("[WS] 客户端事件队列持续满载，放弃最新事件")


def push_event(event_type: WSMessageType, data: dict | None = None):
    """从任意上下文（同步/异步）推送事件到所有已连接客户端。线程安全。

    每个客户端有独立队列，不会因一个客户端消费而导致其他客户端丢失事件。
    队列满时（maxsize=1000）丢弃最旧事件，防止慢客户端导致内存增长。
    """
    event = {
        "type": event_type.value,
        "data": data or {},
        "timestamp": now_et().isoformat(),
    }
    with _lock:
        clients = list(_client_queues.items())

    for websocket, client in clients:
        try:
            # 即便调用者恰好位于 API 线程，也统一通过线程安全投递路径，
            # 这样队列操作始终由其唯一归属循环串行执行。
            client.loop.call_soon_threadsafe(_enqueue_event, websocket, client, event)
        except RuntimeError:
            # 事件循环已关闭，连接不再可用；移除过期登记，后续事件不重试。
            _unregister_client(websocket, client)


async def broadcast_event(event_type: WSMessageType, data: dict | None = None):
    """异步广播事件到所有已连接客户端。
    由其他模块在发生重要事件时调用。
    """
    # 复用 push_event，避免异步调用者跨 WebSocket 所属事件循环直接 send_text。
    push_event(event_type, data)


@router.websocket("/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket 实时事件流端点。
    客户端连接后接收所有事件（交易信号、告警等）

    认证: 查询参数 ?token=<OPENCLAW_API_TOKEN>
    如果 OPENCLAW_API_TOKEN 未配置，则接受所有连接。
    """
    # 验证 token
    if not verify_ws_token(websocket):
        await websocket.close(code=1008, reason="Invalid or missing API token")
        logger.warning("WebSocket connection rejected: invalid token")
        return

    await websocket.accept()

    # 为此客户端创建独立队列
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1000)
    client = _ClientQueue(loop=asyncio.get_running_loop(), queue=queue)
    _register_client(websocket, client)
    logger.info("WebSocket client connected (total: %d)", len(_client_queues))

    try:
        # 发送初始系统状态（HI-NEW-03 修复：加异常保护）
        try:
            from ..rpc import ClawBotRPC

            status = ClawBotRPC._rpc_system_status()
        except Exception as e:
            logger.warning("获取初始系统状态失败，降级发送空状态: %s", e)
            status = {"error": "系统状态暂不可用"}

        await websocket.send_json(
            {
                "type": WSMessageType.STATUS.value,
                "data": status,
                "timestamp": now_et().isoformat(),
            }
        )

        # 保活循环 — 从独立队列 drain 事件 + 处理客户端消息
        while True:
            try:
                # 同时等待：客户端消息 或 队列事件
                # 用 asyncio.wait 实现非阻塞双监听
                recv_task = asyncio.ensure_future(websocket.receive_text())
                queue_task = asyncio.ensure_future(queue.get())

                done, pending = await asyncio.wait(
                    {recv_task, queue_task},
                    timeout=15,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # 取消未完成的任务
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task

                if not done:
                    # 超时 — 发送心跳
                    try:
                        await websocket.send_json(
                            {
                                "type": "heartbeat",
                                "timestamp": now_et().isoformat(),
                            }
                        )
                    except Exception:
                        break
                    continue

                for task in done:
                    if task is recv_task:
                        # 客户端发来消息
                        data = task.result()
                        if data == "ping":
                            await websocket.send_text("pong")
                    elif task is queue_task:
                        # 队列有新事件
                        event = task.result()
                        await websocket.send_json(event)

                # drain 队列中剩余事件（批量发送）
                while not queue.empty():
                    try:
                        event = queue.get_nowait()
                        await websocket.send_json(event)
                    except asyncio.QueueEmpty:
                        break

            except TimeoutError:
                # 发送心跳
                try:
                    await websocket.send_json(
                        {
                            "type": "heartbeat",
                            "timestamp": now_et().isoformat(),
                        }
                    )
                except Exception:
                    break
    except WebSocketDisconnect:
        pass  # 合理保留：客户端主动断开属于正常流程
    except Exception as e:
        logger.debug("WebSocket error: %s", e)
    finally:
        _unregister_client(websocket, client)
        logger.info("WebSocket client disconnected (total: %d)", len(_client_queues))
