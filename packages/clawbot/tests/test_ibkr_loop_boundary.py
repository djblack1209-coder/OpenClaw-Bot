"""IBKR 单例跨线程事件循环边界测试。"""

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.broker_bridge import IBKRBridge
from src.broker_scanner import BrokerScannerMixin
from src.core.loop_owner import AsyncLoopOwner, OwnerLoopNotReady

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _start_bridge_owner(bridge: IBKRBridge):
    """在独立线程启动 IBKR 所有者循环。"""
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    async def bind() -> None:
        bridge._loop_owner.bind_current()

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bind())
        ready.set()
        loop.run_forever()
        loop.close()

    thread = threading.Thread(target=run, name="ibkr-owner-test", daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    return loop, thread


def _stop_bridge_owner(
    loop: asyncio.AbstractEventLoop,
    thread: threading.Thread,
) -> None:
    """停止测试所有者循环。"""
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)
    assert not thread.is_alive()


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("ensure_connected", ()),
        ("get_account_summary", ()),
        ("get_account_value", ()),
        ("get_positions", ()),
        ("get_positions_text", ()),
        ("get_market_scanner_symbols", ()),
        ("search_matching_contracts", ("AAPL",)),
        ("get_realtime_snapshot", ("AAPL",)),
        ("buy", ("AAPL", 1)),
        ("sell", ("AAPL", 1)),
        ("get_open_orders", ()),
        ("get_trade_snapshots", ()),
        ("get_recent_fills", ()),
        ("get_orders_text", ()),
        ("cancel_order", (88,)),
        ("cancel_all_orders", ()),
        ("sync_capital", ()),
        ("close", ()),
    ],
)
async def test_stateful_operations_fail_closed_before_owner_is_bound(
    method_name: str,
    args: tuple,
):
    bridge = IBKRBridge()
    bridge._loop_owner = AsyncLoopOwner("ibkr")

    with pytest.raises(OwnerLoopNotReady):
        await getattr(bridge, method_name)(*args)


async def test_connect_claims_current_loop_and_close_releases_it():
    bridge = IBKRBridge()

    with patch("src.broker_bridge.HAS_IB", False):
        assert await bridge.connect() is False
    assert bridge._loop_owner.is_current() is True

    await bridge.close()

    assert bridge._loop_owner.is_bound is False


def test_cross_loop_account_query_runs_on_owner_thread_once():
    bridge = IBKRBridge()
    bridge._loop_owner = AsyncLoopOwner("ibkr")
    calls: list[int] = []

    class FakeIB:
        @staticmethod
        def isConnected() -> bool:
            return True

        @staticmethod
        def accountSummary(**_kwargs):
            calls.append(threading.get_ident())
            return []

    bridge.ib = FakeIB()
    loop, thread = _start_bridge_owner(bridge)
    try:
        result = asyncio.run(bridge.get_account_summary())

        assert result == {}
        assert calls == [thread.ident]
    finally:
        _stop_bridge_owner(loop, thread)


def test_cross_loop_connect_runs_on_existing_owner_thread():
    bridge = IBKRBridge()
    bridge._loop_owner = AsyncLoopOwner("ibkr")
    calls: list[int] = []
    loop, thread = _start_bridge_owner(bridge)
    try:
        with (
            patch("src.broker_bridge.HAS_IB", False),
            patch(
                "src.broker_bridge.logger.error",
                side_effect=lambda *_args, **_kwargs: calls.append(threading.get_ident()),
            ),
        ):
            assert asyncio.run(bridge.connect()) is False

        assert calls == [thread.ident]
    finally:
        _stop_bridge_owner(loop, thread)


def test_cross_loop_order_submission_runs_once_on_owner_thread():
    bridge = IBKRBridge()
    bridge._loop_owner = AsyncLoopOwner("ibkr")
    calls: list[tuple[str, str, int]] = []

    async def place_order(side: str, symbol: str, *_args, **_kwargs) -> dict:
        calls.append((side, symbol, threading.get_ident()))
        return {
            "status": "Submitted",
            "order_id": 77,
            "broker_result_ambiguous": True,
        }

    bridge._place_order = place_order
    loop, thread = _start_bridge_owner(bridge)
    try:
        result = asyncio.run(bridge.buy("AAPL", 1))

        assert result["broker_result_ambiguous"] is True
        assert calls == [("BUY", "AAPL", thread.ident)]
    finally:
        _stop_bridge_owner(loop, thread)


def test_cancelled_api_waiter_does_not_cancel_submitted_owner_operation():
    bridge = IBKRBridge()
    bridge._loop_owner = AsyncLoopOwner("ibkr")
    started = threading.Event()
    completed = threading.Event()

    async def place_order(*_args, **_kwargs) -> dict:
        started.set()
        await asyncio.sleep(0.05)
        completed.set()
        return {"status": "Submitted", "order_id": 79}

    bridge._place_order = place_order
    loop, thread = _start_bridge_owner(bridge)
    try:

        async def cancel_waiter() -> None:
            task = asyncio.create_task(bridge.buy("AAPL", 1))
            assert await asyncio.to_thread(started.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(cancel_waiter())

        assert completed.wait(timeout=1)
    finally:
        _stop_bridge_owner(loop, thread)


def test_post_submit_failure_stays_ambiguous_and_never_resubmits(tmp_path):
    bridge = IBKRBridge(budget=100.0)
    bridge._loop_owner = AsyncLoopOwner("ibkr")
    contract = SimpleNamespace(symbol="AAPL")
    calls: list[int] = []

    class BrokenOrderStatus:
        @property
        def status(self) -> str:
            raise RuntimeError("订单状态读取失败")

    trade = SimpleNamespace(
        order=SimpleNamespace(orderId=501),
        orderStatus=BrokenOrderStatus(),
    )

    class FakeIB:
        @staticmethod
        def isConnected() -> bool:
            return True

        @staticmethod
        async def qualifyContractsAsync(_contract):
            return [contract]

        @staticmethod
        def placeOrder(_contract, _order):
            calls.append(threading.get_ident())
            return trade

    bridge.ib = FakeIB()
    bridge._make_contract = lambda _symbol: contract
    loop, thread = _start_bridge_owner(bridge)
    try:
        with (
            patch("src.broker_bridge.BUDGET_STATE_FILE", tmp_path / "budget.json"),
            patch(
                "src.broker_bridge.LimitOrder",
                side_effect=lambda *_args: SimpleNamespace(account=""),
            ),
        ):
            result = asyncio.run(
                bridge.buy(
                    "AAPL",
                    1,
                    order_type="LMT",
                    limit_price=10.0,
                )
            )

        assert result["broker_result_ambiguous"] is True
        assert result["status"] == "Submitted"
        assert "error" not in result
        assert calls == [thread.ident]
    finally:
        _stop_bridge_owner(loop, thread)


def test_cross_loop_cancel_runs_once_on_owner_thread(monkeypatch):
    bridge = IBKRBridge()
    bridge._loop_owner = AsyncLoopOwner("ibkr")
    calls: list[int] = []
    order = SimpleNamespace(orderId=88)
    trade = SimpleNamespace(order=order)

    class FakeIB:
        @staticmethod
        def isConnected() -> bool:
            return True

        @staticmethod
        def openTrades():
            return [trade]

        @staticmethod
        def cancelOrder(_order) -> None:
            calls.append(threading.get_ident())

    bridge.ib = FakeIB()
    monkeypatch.setattr("src.broker_bridge.IBKR_CANCEL_CONFIRM_WAIT", 0)
    loop, thread = _start_bridge_owner(bridge)
    try:
        result = asyncio.run(bridge.cancel_order(88))

        assert result == {"order_id": 88, "status": "cancelled"}
        assert calls == [thread.ident]
    finally:
        _stop_bridge_owner(loop, thread)


def test_inherited_market_query_runs_on_owner_thread():
    bridge = IBKRBridge()
    bridge._loop_owner = AsyncLoopOwner("ibkr")
    calls: list[tuple[str, int]] = []

    async def snapshot(_self, *, symbol: str, **_kwargs) -> dict:
        calls.append((symbol, threading.get_ident()))
        return {"symbol": symbol, "price": 123.0}

    loop, thread = _start_bridge_owner(bridge)
    try:
        with patch.object(BrokerScannerMixin, "get_realtime_snapshot", snapshot):
            result = asyncio.run(bridge.get_realtime_snapshot("AAPL"))

        assert result == {"symbol": "AAPL", "price": 123.0}
        assert calls == [("AAPL", thread.ident)]
    finally:
        _stop_bridge_owner(loop, thread)


def test_foreign_thread_connection_check_does_not_touch_ib_client():
    bridge = IBKRBridge()
    bridge._loop_owner = AsyncLoopOwner("ibkr")
    bridge._connected = True

    class FakeIB:
        @staticmethod
        def isConnected() -> bool:
            raise AssertionError("禁止从非所有者线程读取 IB client")

    bridge.ib = FakeIB()
    loop, thread = _start_bridge_owner(bridge)
    try:
        assert bridge.is_connected() is True
    finally:
        _stop_bridge_owner(loop, thread)


def test_main_binds_owner_before_api_start_and_closes_after_api_stop():
    source = (PROJECT_ROOT / "multi_main.py").read_text(encoding="utf-8")

    assert source.index("ibkr.bind_current_loop()") < source.index("start_api_server(port=api_port)")
    assert source.index("stop_api_server()") < source.index("await ibkr.close()")
