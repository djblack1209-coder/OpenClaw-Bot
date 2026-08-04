"""闲鱼实时服务跨线程事件循环边界测试。"""

import asyncio
import contextlib
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor
from types import MappingProxyType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from scripts.xianyu_main import _run_live
from src.core.loop_owner import AsyncLoopOwner
from src.xianyu import xianyu_admin
from src.xianyu.xianyu_context import XianyuContextManager
from src.xianyu.xianyu_live import XianyuLive


def _start_live_owner(live: XianyuLive):
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    async def bind() -> None:
        live._loop_owner.bind_current()

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bind())
        ready.set()
        loop.run_forever()
        loop.close()

    thread = threading.Thread(target=run, name="xianyu-live-owner-test", daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    return loop, thread


def test_admin_operation_executes_once_on_live_owner_loop():
    live = object.__new__(XianyuLive)
    live._loop_owner = AsyncLoopOwner("xianyu-live")
    calls: list[tuple[int, int]] = []

    async def resend_cc_shipment(shipment_id: int) -> dict:
        calls.append((shipment_id, threading.get_ident()))
        return {"ok": True, "id": shipment_id}

    live.resend_cc_shipment = resend_cc_shipment
    loop, thread = _start_live_owner(live)
    try:
        result = asyncio.run(
            live.call_on_owner(
                "resend_cc_shipment",
                shipment_id=17,
                timeout=1,
            )
        )
        assert result == {"ok": True, "id": 17}
        assert calls == [(17, thread.ident)]
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_runtime_snapshot_is_immutable_and_captured_on_live_owner_loop():
    live = object.__new__(XianyuLive)
    live._loop_owner = AsyncLoopOwner("xianyu-live")
    live._state_lock = asyncio.Lock()
    accessed_threads: list[int] = []

    class OwnerThreadWebSocket:
        @property
        def open(self) -> bool:
            accessed_threads.append(threading.get_ident())
            return True

    live.ws = OwnerThreadWebSocket()
    live._cookie_ok = True
    live.last_hb_resp = 123.5
    live.token_ts = 120.0
    live.manual_chats = {"chat-1": 100.0, "chat-2": 110.0}
    loop, thread = _start_live_owner(live)
    try:
        snapshot = asyncio.run(
            live.call_on_owner(
                "runtime_snapshot",
                timeout=1,
            )
        )

        assert dict(snapshot) == {
            "ws_connected": True,
            "cookie_ok": True,
            "last_heartbeat": 123.5,
            "token_ts": 120.0,
            "manual_chats": 2,
        }
        assert accessed_threads == [thread.ident]
        with pytest.raises(TypeError):
            snapshot["cookie_ok"] = False
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_concurrent_runtime_snapshots_never_mix_owner_states():
    live = object.__new__(XianyuLive)
    live._loop_owner = AsyncLoopOwner("xianyu-live")
    live._state_lock = asyncio.Lock()
    live.ws = SimpleNamespace(open=True)
    live._cookie_ok = True
    live.last_hb_resp = 10.0
    live.token_ts = 5.0
    live.manual_chats = {"chat-a": 1.0}
    loop, thread = _start_live_owner(live)

    async def alternate_states() -> None:
        for index in range(100):
            async with live._state_lock:
                if index % 2 == 0:
                    live.ws = SimpleNamespace(open=True)
                    live._cookie_ok = True
                    live.last_hb_resp = 10.0
                    live.token_ts = 5.0
                    live.manual_chats = {"chat-a": 1.0}
                else:
                    live.ws = SimpleNamespace(open=False)
                    live._cookie_ok = False
                    live.last_hb_resp = 20.0
                    live.token_ts = 15.0
                    live.manual_chats = {"chat-b": 2.0, "chat-c": 3.0}
            await asyncio.sleep(0)

    expected_states = {
        (True, True, 10.0, 5.0, 1),
        (False, False, 20.0, 15.0, 2),
    }
    mutation = asyncio.run_coroutine_threadsafe(alternate_states(), loop)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            snapshots = list(pool.map(lambda _: live.runtime_snapshot_sync(timeout=1), range(80)))
        mutation.result(timeout=2)

        observed_states = {
            (
                snapshot["ws_connected"],
                snapshot["cookie_ok"],
                snapshot["last_heartbeat"],
                snapshot["token_ts"],
                snapshot["manual_chats"],
            )
            for snapshot in snapshots
        }
        assert observed_states
        assert observed_states <= expected_states
    finally:
        if not mutation.done():
            mutation.cancel()
        with contextlib.suppress(CancelledError):
            mutation.result(timeout=2)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_admin_status_readiness_and_sale_lock_only_use_runtime_snapshot(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("CC_OPERATOR_STATE_FILE", str(tmp_path / "cc-operator-state.json"))
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_PAUSED", "0")
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_ENABLED", "1")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_URL", "https://example.test/xianyu")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_TOKEN", "unit-token")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "")
    monkeypatch.setattr(xianyu_admin.app.state, "bind_host", "127.0.0.1")
    monkeypatch.setattr(
        xianyu_admin,
        "_ctx",
        XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db")),
    )
    monkeypatch.setattr(xianyu_admin, "_last_cc_readiness_audit", {})
    monkeypatch.setattr(xianyu_admin, "_last_cc_strict_audit", {})

    class SnapshotOnlyLive:
        forbidden = {"ws", "_cookie_ok", "manual_chats", "last_hb_resp", "token_ts"}

        def __init__(self) -> None:
            self.snapshot_calls = 0

        def __getattribute__(self, name: str):
            if name in object.__getattribute__(self, "forbidden"):
                raise AssertionError(f"管理线程禁止直接读取 {name}")
            return object.__getattribute__(self, name)

        def runtime_snapshot_sync(self, timeout: float = 5.0):
            assert timeout == 5.0
            self.snapshot_calls += 1
            return MappingProxyType(
                {
                    "ws_connected": True,
                    "cookie_ok": True,
                    "last_heartbeat": 123.5,
                    "token_ts": 0.0,
                    "manual_chats": 2,
                }
            )

    live = SnapshotOnlyLive()
    monkeypatch.setattr(xianyu_admin, "_live", live)
    client = TestClient(xianyu_admin.app)

    status = client.get("/api/status")
    readiness = client.get("/api/cc-sale-readiness")
    sale_lock = client.get("/api/cc-public-sale-lock")

    assert status.status_code == 200
    assert status.json()["ws_connected"] is True
    assert status.json()["cookie_ok"] is True
    assert status.json()["manual_chats"] == 2
    assert status.json()["last_heartbeat"] == 123.5
    assert status.json()["token_age_s"] == -1
    assert readiness.status_code == 200
    assert readiness.json()["checks"]["ws_connected"] is True
    assert readiness.json()["checks"]["cookie_ok"] is True
    assert readiness.json()["manual_chats"] == 2
    assert sale_lock.status_code == 200
    assert sale_lock.json()["gates"]["ws_connected"] is True
    assert sale_lock.json()["gates"]["cookie_ok"] is True
    assert live.snapshot_calls == 3


def test_entrypoint_runs_and_closes_live_on_same_loop():
    loop_ids: list[int] = []

    class FakeLive:
        async def run(self) -> None:
            loop_ids.append(id(asyncio.get_running_loop()))

        async def close(self) -> None:
            loop_ids.append(id(asyncio.get_running_loop()))

    asyncio.run(_run_live(FakeLive()))

    assert len(loop_ids) == 2
    assert loop_ids[0] == loop_ids[1]


def test_concurrent_admin_resend_executes_external_send_once(tmp_path):
    live = object.__new__(XianyuLive)
    live._loop_owner = AsyncLoopOwner("xianyu-live")
    live.ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    live.ctx.record_cc_shipment(
        order_id="xy_oid_owner_once",
        buyer_id="buyer-owner",
        item_id="item-owner",
        chat_id="chat-owner",
        status="message_send_failed",
        delivery_message="兑换码：CC-OWNER-ONCE",
    )
    shipment_id = live.ctx.list_cc_shipments(include_message=True)[0]["id"]
    live.ws = SimpleNamespace(open=True)
    live.notifier = SimpleNamespace(notify_order=lambda payload: None)
    sends: list[int] = []

    async def send_msg(ws, chat_id: str, buyer_id: str, message: str) -> None:
        sends.append(threading.get_ident())
        await asyncio.sleep(0.02)

    async def skip_confirm(order_id: str, item_id: str, buyer_id: str) -> dict:
        return {"ok": False, "skipped": True}

    live.send_msg = send_msg
    live._maybe_confirm_xianyu_order_shipped = skip_confirm
    loop, thread = _start_live_owner(live)
    try:

        async def submit_twice():
            return await asyncio.gather(
                live.call_on_owner("resend_cc_shipment", shipment_id=shipment_id, timeout=1),
                live.call_on_owner("resend_cc_shipment", shipment_id=shipment_id, timeout=1),
                return_exceptions=True,
            )

        results = asyncio.run(submit_twice())

        assert sum(isinstance(result, dict) and result.get("ok") for result in results) == 1
        assert sum(isinstance(result, RuntimeError) for result in results) == 1
        assert sends == [thread.ident]
        assert live.ctx.get_cc_shipment(shipment_id)["status"] == "message_sent"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_uncertain_send_is_not_automatically_retried(tmp_path):
    live = object.__new__(XianyuLive)
    live.ctx = XianyuContextManager(db_path=str(tmp_path / "xianyu-chat.db"))
    live.ctx.record_cc_shipment(
        order_id="xy_oid_uncertain_send",
        buyer_id="buyer-uncertain",
        item_id="item-uncertain",
        chat_id="chat-uncertain",
        status="message_send_failed",
        delivery_message="兑换码：CC-UNCERTAIN",
    )
    shipment_id = live.ctx.list_cc_shipments(include_message=True)[0]["id"]
    live.ws = SimpleNamespace(open=True)
    live.notifier = SimpleNamespace(notify_order=lambda payload: None)
    send_count = 0

    async def uncertain_send(ws, chat_id: str, buyer_id: str, message: str) -> None:
        nonlocal send_count
        send_count += 1
        raise ConnectionError("连接在确认帧前断开")

    live.send_msg = uncertain_send

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="结果不确定"):
            await live.resend_cc_shipment(shipment_id)
        with pytest.raises(RuntimeError, match="禁止直接重试"):
            await live.resend_cc_shipment(shipment_id)

    asyncio.run(scenario())

    assert send_count == 1
    assert live.ctx.get_cc_shipment(shipment_id)["status"] == "message_send_uncertain"
