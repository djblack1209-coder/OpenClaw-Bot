"""WebSocket endpoint for real-time event streaming
搬运自 freqtrade/rpc/api_server/api_ws.py 的 pub/sub 模式
"""
import asyncio
import json
import logging
from collections import deque
from datetime import datetime
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..schemas import WSMessageType
from src.utils import now_et

logger = logging.getLogger(__name__)
router = APIRouter()

# Connected clients
_clients: Set[WebSocket] = set()

# Thread-safe event buffer for non-async callers (sync code can push events here)
_event_buffer: deque = deque(maxlen=1000)


def push_event(event_type: WSMessageType, data: dict = None):
    """Push an event from any context (sync or async). Thread-safe.

    Events are buffered in a deque and drained by connected WebSocket clients
    during their keepalive loop. This avoids the need for callers to be in an
    async context or to hold a reference to the event loop.
    """
    _event_buffer.append({
        "type": event_type.value,
        "data": data or {},
        "timestamp": now_et().isoformat(),
    })


async def broadcast_event(event_type: WSMessageType, data: dict = None):
    """Broadcast an event to all connected WebSocket clients.
    Called by other modules when significant events happen.
    """
    if not _clients:
        return

    message = json.dumps({
        "type": event_type.value,
        "data": data or {},
        "timestamp": now_et().isoformat(),
    })

    disconnected = set()
    for client in _clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.add(client)

    _clients.difference_update(disconnected)


@router.websocket("/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint for real-time event streaming.
    Clients connect and receive all events (trade signals, alerts, etc.)
    """
    await websocket.accept()
    _clients.add(websocket)
    logger.info("WebSocket client connected (total: %d)", len(_clients))

    try:
        # Send initial status on connect
        from ..rpc import ClawBotRPC
        status = ClawBotRPC._rpc_system_status()
        await websocket.send_json({
            "type": WSMessageType.STATUS.value,
            "data": status,
            "timestamp": now_et().isoformat(),
        })

        # Keep alive — wait for disconnect, drain buffered events
        while True:
            try:
                # Drain any buffered events from sync callers
                while _event_buffer:
                    event = _event_buffer.popleft()
                    await websocket.send_json(event)

                # Wait for client messages (ping/pong or subscription changes)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=5)
                # Echo ping
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Drain buffered events on timeout too
                while _event_buffer:
                    event = _event_buffer.popleft()
                    await websocket.send_json(event)
                # Send heartbeat
                try:
                    await websocket.send_json({"type": "heartbeat", "timestamp": now_et().isoformat()})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WebSocket error: %s", e)
    finally:
        _clients.discard(websocket)
        logger.info("WebSocket client disconnected (total: %d)", len(_clients))
