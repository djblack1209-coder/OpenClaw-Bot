"""WebSocket endpoint for real-time event streaming
搬运自 freqtrade/rpc/api_server/api_ws.py 的 pub/sub 模式

v2 修复:
  - HI-NEW-02: 共享 deque + popleft 导致多客户端丢消息 → 每客户端独立 asyncio.Queue
  - HI-NEW-03: 初始状态获取无异常保护 → 加 try/except 降级发送空状态
"""
import asyncio
import json
import logging
import threading
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..schemas import WSMessageType
from ..auth import verify_ws_token
from src.utils import now_et

logger = logging.getLogger(__name__)
router = APIRouter()

# 每个客户端拥有独立的事件队列，避免 popleft 互抢
# key = WebSocket 对象, value = asyncio.Queue
_client_queues: Dict[WebSocket, asyncio.Queue] = {}
_lock = threading.Lock()


def push_event(event_type: WSMessageType, data: dict = None):
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
        for queue in _client_queues.values():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # 慢客户端：丢弃队头最旧事件，腾出空间
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except Exception:
                    pass


async def broadcast_event(event_type: WSMessageType, data: dict = None):
    """异步广播事件到所有已连接客户端。
    由其他模块在发生重要事件时调用。
    """
    if not _client_queues:
        return

    message = json.dumps({
        "type": event_type.value,
        "data": data or {},
        "timestamp": now_et().isoformat(),
    })

    disconnected = []
    with _lock:
        clients = list(_client_queues.keys())

    for client in clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.append(client)

    if disconnected:
        with _lock:
            for client in disconnected:
                _client_queues.pop(client, None)


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
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    with _lock:
        _client_queues[websocket] = queue
    logger.info("WebSocket client connected (total: %d)", len(_client_queues))

    try:
        # 发送初始系统状态（HI-NEW-03 修复：加异常保护）
        try:
            from ..rpc import ClawBotRPC
            status = ClawBotRPC._rpc_system_status()
        except Exception as e:
            logger.warning("获取初始系统状态失败，降级发送空状态: %s", e)
            status = {"error": "系统状态暂不可用"}

        await websocket.send_json({
            "type": WSMessageType.STATUS.value,
            "data": status,
            "timestamp": now_et().isoformat(),
        })

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
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

                if not done:
                    # 超时 — 发送心跳
                    try:
                        await websocket.send_json({
                            "type": "heartbeat",
                            "timestamp": now_et().isoformat(),
                        })
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

            except asyncio.TimeoutError:
                # 发送心跳
                try:
                    await websocket.send_json({
                        "type": "heartbeat",
                        "timestamp": now_et().isoformat(),
                    })
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WebSocket error: %s", e)
    finally:
        with _lock:
            _client_queues.pop(websocket, None)
        logger.info("WebSocket client disconnected (total: %d)", len(_client_queues))
