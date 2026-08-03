"""Tests for src/broker_bridge.py — pure logic & mock-based (no real IBKR connection)."""

import asyncio
import json
import multiprocessing
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.broker_bridge as broker_bridge_module
from src.broker_bridge import IBKRBridge, SlippageEstimate


@pytest.fixture(autouse=True)
def isolate_budget_state(tmp_path, monkeypatch):
    """隔离预算账本，避免测试读写本机运行状态。"""
    monkeypatch.setattr(
        broker_bridge_module,
        "BUDGET_STATE_FILE",
        tmp_path / "broker-budget.json",
    )


def _reserve_budget_in_process(state_file, barrier, result_queue) -> None:
    """让独立 OS 进程同时争抢同一账户的预算额度。"""
    broker_bridge_module.BUDGET_STATE_FILE = Path(state_file)
    bridge = IBKRBridge(account="DU-SHARED", budget=100.0)
    barrier.wait(timeout=10)
    try:
        accepted, remaining = bridge._reserve_buy_budget(60.0)
        result_queue.put({"accepted": accepted, "remaining": remaining})
    except Exception as exc:
        result_queue.put({"error": str(exc)})

# ============ IBKRBridge.__init__ ============


def test_init_default_attributes():
    bridge = IBKRBridge()
    assert bridge.host == "127.0.0.1"
    assert bridge.port == 4002
    assert bridge.client_id == 0
    assert bridge.account == ""
    assert bridge.budget == 2000.0
    assert bridge.total_spent == 0.0
    assert bridge.ib is None
    assert bridge._connected is False
    assert bridge._notify_func is None


def test_init_custom_attributes():
    bridge = IBKRBridge(host="10.0.0.1", port=7497, client_id=5, account="TEST123", budget=5000.0)
    assert bridge.host == "10.0.0.1"
    assert bridge.port == 7497
    assert bridge.client_id == 5
    assert bridge.account == "TEST123"
    assert bridge.budget == 5000.0


# ============ set_notify ============


def test_set_notify():
    bridge = IBKRBridge()
    cb = MagicMock()
    bridge.set_notify(cb)
    assert bridge._notify_func is cb


# ============ is_connected ============


def test_is_connected_ib_none():
    bridge = IBKRBridge()
    assert bridge.is_connected() is False


def test_is_connd_true():
    bridge = IBKRBridge()
    bridge.ib = MagicMock()
    bridge.ib.isConnected.return_value = True
    assert bridge.is_connected() is True


def test_is_connected_false():
    bridge = IBKRBridge()
    bridge.ib = MagicMock()
    bridge.ib.isConnected.return_value = False
    assert bridge.is_connected() is False


# ============ get_budget_status ============


def test_budget_status_fresh():
    bridge = IBKRBridge(budget=2000.0)
    status = bridge.get_budget_status()
    assert "$2000.00" in status
    assert "0.0%" in status


def test_budget_status_partial_spend():
    bridge = IBKRBridge(budget=1000.0)
    bridge.total_spent = 250.0
    status = bridge.get_budget_status()
    assert "$250.00" in status
    assert "25.0%" in status
    assert "$750.00" in status


# ============ reset_budget ============


def test_reset_budget_default():
    bridge = IBKRBridge(budget=5000.0)
    bridge.total_spent = 3000.0
    bridge.reset_budget()
    assert bridge.budget == 2000.0
    assert bridge.total_spent == 0.0


def test_reset_budget_custom():
    bridge = IBKRBridge()
    bridge.total_spent = 999.0
    bridge.reset_budget(new_budget=10000.0)
    assert bridge.budget == 10000.0
    assert bridge.total_spent == 0.0


# ============ get_connection_status ============


def test_connection_status_no_ib_installed():
    bridge = IBKRBridge()
    with patch("src.broker_bridge.HAS_IB", False):
        status = bridge.get_connection_status()
    assert "ib_async 未安装" in status


def test_connection_status_connected():
    bridge = IBKRBridge()
    bridge.ib = MagicMock()
    bridge.ib.isConnected.return_value = True
    bridge._connected_since = time.time() - 600
    bridge._consecutive_pings = 20
    bridge._last_ping_latency_ms = 5.0
    bridge._disconnect_count = 1
    bridge._total_reconnects = 1
    with patch("src.broker_bridge.HAS_IB", True):
        status = bridge.get_connection_status()
    assert "已连接" in status
    assert "心跳" in status


def test_connection_status_disconnected():
    bridge = IBKRBridge()
    bridge._disconnect_count = 3
    bridge._total_reconnects = 2
    with patch("src.broker_bridge.HAS_IB", True):
        status = bridge.get_connection_status()
    assert "未连接" in status


# ============ SlippageEstimate dataclass ============


def test_slippage_estimate_defaults():
    est = SlippageEstimate()
    assert est.estimated_slippage_pct == 0.0
    assert est.estimated_fill_price == 0.0
    assert est.liquidity_score == "unknown"
    assert est.avg_volume == 0.0
    assert est.avg_spread_pct == 0.0
    assert est.warnings == []


# ============ format_slippage ============


def test_format_slippage_basic():
    bridge = IBKRBridge()
    est = SlippageEstimate(
        estimated_slippage_pct=0.05,
        estimated_fill_price=150.08,
        liquidity_score="high",
        avg_volume=12_000_000,
    )
    text = bridge.format_slippage(est)
    assert "滑点估算" in text
    assert "高" in text
    assert "12,000,000" in text
    assert "0.05%" in text
    assert "$150.08" in text


def test_format_slippage_with_warnings():
    bridge = IBKRBridge()
    est = SlippageEstimate(warnings=["大单警告: 订单占日均成交量 1.50%"])
    text = bridge.format_slippage(est)
    assert "[!] 大单警告" in text


# ============ connect when HAS_IB=False ============


async def test_connect_returns_false_without_ib():
    bridge = IBKRBridge()
    with patch("src.broker_bridge.HAS_IB", False):
        result = await bridge.connect()
    assert result is False


# ============ buy budget check ============


async def test_buy_rejects_when_budget_exhausted():
    bridge = IBKRBridge(budget=1000.0)
    bridge.total_spent = 1000.0
    bridge.ib = MagicMock()
    bridge.ib.isConnected.return_value = True
    result = await bridge.buy("AAPL", 1)
    assert "error" in result
    assert "预算已用完" in result["error"]


def _configure_filled_buy(bridge: IBKRBridge, price: float = 60.0) -> None:
    """配置一个会立即成交的 IBKR 买入桩。"""
    bridge.ib = MagicMock()
    bridge.ib.isConnected.return_value = True
    contract = MagicMock()
    bridge._make_contract = MagicMock(return_value=contract)
    bridge.ib.qualifyContractsAsync = AsyncMock(return_value=[contract])
    ticker = MagicMock()
    ticker.ask = price
    ticker.last = price
    ticker.close = price
    ticker.marketPrice.return_value = price
    bridge.ib.reqTickers.return_value = [ticker]
    trade = MagicMock()
    trade.orderStatus.status = "Filled"
    trade.orderStatus.filled = 1
    trade.orderStatus.avgFillPrice = price
    trade.order.orderId = 501
    bridge.ib.placeOrder.return_value = trade
    bridge.estimate_slippage = AsyncMock(return_value=SlippageEstimate())


async def test_single_buy_above_remaining_budget_is_rejected_before_order(tmp_path):
    with patch("src.broker_bridge.BUDGET_STATE_FILE", tmp_path / "budget.json"):
        bridge = IBKRBridge(budget=100.0)
        _configure_filled_buy(bridge, price=60.0)
        with patch("src.broker_bridge.LimitOrder", MagicMock()), patch(
            "asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await bridge.buy("AAPL", 2)

    assert "超过剩余预算" in result["error"]
    bridge.ib.placeOrder.assert_not_called()
    assert bridge.total_spent == 0


async def test_concurrent_buys_share_atomic_budget_reservation(tmp_path):
    with patch("src.broker_bridge.BUDGET_STATE_FILE", tmp_path / "budget.json"):
        bridge = IBKRBridge(budget=100.0)
        _configure_filled_buy(bridge, price=60.0)
        market_order = MagicMock()
        limit_order = MagicMock()
        with patch("src.broker_bridge.MarketOrder", market_order), patch(
            "src.broker_bridge.LimitOrder",
            limit_order,
        ), patch(
            "asyncio.sleep",
            new_callable=AsyncMock,
        ):
            first, second = await asyncio.gather(
                bridge.buy("AAPL", 1),
                bridge.buy("AAPL", 1),
            )

    assert sum("error" not in result for result in (first, second)) == 1
    assert bridge.ib.placeOrder.call_count == 1
    market_order.assert_not_called()
    limit_order.assert_called_once()
    assert bridge.total_spent == 60.0
    assert bridge._reserved_buy_notional == 0


def test_two_os_processes_cannot_double_reserve_same_account_budget(tmp_path):
    state_file = tmp_path / "shared-budget.json"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_reserve_budget_in_process,
            args=(str(state_file), barrier, result_queue),
        )
        for _ in range(2)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0

    results = [result_queue.get(timeout=5) for _ in processes]
    assert all("error" not in result for result in results)
    assert sum(result["accepted"] for result in results) == 1
    assert sorted(result["remaining"] for result in results) == [40.0, 100.0]

    with patch("src.broker_bridge.BUDGET_STATE_FILE", state_file):
        restored = IBKRBridge(account="DU-SHARED", budget=100.0)
    assert restored._reserved_buy_notional == 60.0


def test_budget_state_is_bound_to_one_account_scope(tmp_path):
    state_file = tmp_path / "account-budget.json"
    with patch("src.broker_bridge.BUDGET_STATE_FILE", state_file):
        first = IBKRBridge(account="DU-ONE", budget=100.0)
        accepted, _remaining = first._reserve_buy_budget(10.0)
        second = IBKRBridge(account="DU-TWO", budget=100.0)

    assert accepted is True
    assert second._budget_state_valid is False
    assert "另一个 IBKR 账户" in second._budget_state_error


async def test_market_buy_near_budget_is_converted_to_capped_limit_order(tmp_path):
    with patch("src.broker_bridge.BUDGET_STATE_FILE", tmp_path / "budget.json"):
        bridge = IBKRBridge(budget=100.0)
        _configure_filled_buy(bridge, price=98.0)
        market_order = MagicMock()
        limit_order = MagicMock()
        with patch("src.broker_bridge.MarketOrder", market_order), patch(
            "src.broker_bridge.LimitOrder",
            limit_order,
        ), patch(
            "asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await bridge.buy("AAPL", 1)

    assert result["order_type"] == "LMT"
    assert result["limit_price"] <= 100.0
    market_order.assert_not_called()
    limit_order.assert_called_once_with("BUY", 1, result["limit_price"])
    assert bridge.total_spent == 98.0
    assert bridge.total_spent <= bridge.budget


async def test_auto_buy_rounds_limit_up_then_rechecks_actual_notional(tmp_path):
    with patch("src.broker_bridge.BUDGET_STATE_FILE", tmp_path / "budget.json"):
        bridge = IBKRBridge(budget=900.0)
        _configure_filled_buy(bridge, price=0.016)
        market_order = MagicMock()
        limit_order = MagicMock()
        with patch.dict(os.environ, {"IBKR_BUY_RESERVE_BUFFER_PCT": "0"}), patch(
            "src.broker_bridge.MarketOrder",
            market_order,
        ), patch(
            "src.broker_bridge.LimitOrder",
            limit_order,
        ), patch(
            "asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await bridge.buy("CHEAP", 50_000)

    assert "超过剩余预算" in result["error"]
    assert "$1000.00" in result["error"]
    market_order.assert_not_called()
    limit_order.assert_not_called()
    bridge.ib.placeOrder.assert_not_called()


async def test_sub_cent_auto_buy_uses_positive_capped_limit_never_market(tmp_path):
    with patch("src.broker_bridge.BUDGET_STATE_FILE", tmp_path / "budget.json"):
        bridge = IBKRBridge(budget=1.0)
        _configure_filled_buy(bridge, price=0.004)
        market_order = MagicMock()
        limit_order = MagicMock()
        with patch.dict(os.environ, {"IBKR_BUY_RESERVE_BUFFER_PCT": "0"}), patch(
            "src.broker_bridge.MarketOrder",
            market_order,
        ), patch(
            "src.broker_bridge.LimitOrder",
            limit_order,
        ), patch(
            "asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await bridge.buy("CHEAP", 1)

    assert result["order_type"] == "LMT"
    assert result["limit_price"] == 0.01
    market_order.assert_not_called()
    limit_order.assert_called_once_with("BUY", 1, 0.01)


async def test_zero_price_limit_buy_is_rejected_instead_of_falling_back_to_market(tmp_path):
    with patch("src.broker_bridge.BUDGET_STATE_FILE", tmp_path / "budget.json"):
        bridge = IBKRBridge(budget=100.0)
        _configure_filled_buy(bridge, price=10.0)
        market_order = MagicMock()
        with patch("src.broker_bridge.MarketOrder", market_order):
            result = await bridge.buy("AAPL", 1, order_type="LMT", limit_price=0)

    assert "拒绝退化为市价单" in result["error"]
    market_order.assert_not_called()
    bridge.ib.placeOrder.assert_not_called()


async def test_budget_reservation_persistence_failure_blocks_broker_order(tmp_path):
    with patch("src.broker_bridge.BUDGET_STATE_FILE", tmp_path / "budget.json"):
        bridge = IBKRBridge(budget=100.0)
        _configure_filled_buy(bridge, price=40.0)
        bridge._save_budget_state = MagicMock(side_effect=OSError("disk full"))
        limit_order = MagicMock()
        with patch("src.broker_bridge.LimitOrder", limit_order), patch(
            "asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await bridge.buy("AAPL", 1)

    assert "disk full" in result["error"]
    assert bridge._reserved_buy_notional == 0
    assert bridge._budget_state_valid is False
    limit_order.assert_not_called()
    bridge.ib.placeOrder.assert_not_called()

    second = await bridge.buy("AAPL", 1)
    assert "预算状态不可用" in second["error"]
    bridge.ib.placeOrder.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        "{broken-json",
        json.dumps({"date": "2026-08-03", "total_spent": -1}),
        '{"date":"2026-08-03","total_spent":NaN}',
        json.dumps(
            {
                "date": "2026-08-03",
                "total_spent": 0,
                "pending_buy_reservations": {
                    "1": {"requested_qty": 1, "reserved_notional": -10}
                },
            }
        ),
    ],
)
async def test_corrupt_current_budget_state_blocks_all_buys(tmp_path, payload):
    state_file = tmp_path / "budget.json"
    state_file.write_text(payload, encoding="utf-8")
    with patch("src.broker_bridge.BUDGET_STATE_FILE", state_file), patch(
        "src.broker_bridge.now_et"
    ) as clock:
        clock.return_value = datetime(2026, 8, 3)
        bridge = IBKRBridge(budget=100.0)
    bridge.ib = MagicMock()

    result = await bridge.buy("AAPL", 1)

    assert bridge._budget_state_valid is False
    assert "预算状态不可用" in result["error"]
    bridge.ib.placeOrder.assert_not_called()


def test_previous_day_budget_state_resets_normally(tmp_path):
    state_file = tmp_path / "budget.json"
    state_file.write_text(
        json.dumps({"date": "2026-08-02", "total_spent": 99_999}),
        encoding="utf-8",
    )
    with patch("src.broker_bridge.BUDGET_STATE_FILE", state_file), patch(
        "src.broker_bridge.now_et"
    ) as clock:
        clock.return_value = datetime(2026, 8, 3)
        bridge = IBKRBridge(budget=100.0)

    assert bridge._budget_state_valid is True
    assert bridge.total_spent == 0


def test_previous_day_unresolved_buy_reservation_is_preserved_and_blocks_reset(tmp_path):
    state_file = tmp_path / "budget.json"
    state_file.write_text(
        json.dumps(
            {
                "date": "2026-08-02",
                "total_spent": 500,
                "pending_buy_reservations": {
                    "701": {
                        "requested_qty": 2,
                        "estimated_unit_price": 10,
                        "reserved_notional": 10,
                        "applied_filled_qty": 1,
                        "applied_notional": 10,
                    }
                },
                "unbound_buy_reservation": 5,
            }
        ),
        encoding="utf-8",
    )
    with patch("src.broker_bridge.BUDGET_STATE_FILE", state_file), patch(
        "src.broker_bridge.now_et"
    ) as clock:
        clock.return_value = datetime(2026, 8, 3)
        bridge = IBKRBridge(budget=100.0)
        with pytest.raises(RuntimeError, match="未决 BUY"):
            bridge.reset_budget(new_budget=200.0)

    assert bridge.total_spent == 0
    assert bridge._reserved_buy_notional == 15
    assert bridge._pending_buy_reservations["701"]["reserved_notional"] == 10
    assert bridge.budget == 100.0


def test_non_finite_budget_is_rejected_at_initialization():
    with pytest.raises(ValueError, match="有限非负数"):
        IBKRBridge(budget=float("nan"))


async def test_non_finite_buy_quantity_is_rejected_before_connection():
    bridge = IBKRBridge(budget=100.0)
    bridge.ensure_connected = AsyncMock()

    result = await bridge.buy("AAPL", float("nan"))

    assert "数量必须大于零" in result["error"]
    bridge.ensure_connected.assert_not_called()


# ============ sell budget recovery ============


async def test_sell_recovers_budget():
    bridge = IBKRBridge(budget=2000.0)
    bridge.total_spent = 1500.0
    bridge.ib = MagicMock()
    bridge.ib.isConnected.return_value = True

    mock_contract = MagicMock()
    bridge._make_contract = MagicMock(return_value=mock_contract)
    bridge.ib.qualifyContractsAsync = AsyncMock(return_value=[mock_contract])

    mock_trade = MagicMock()
    mock_trade.orderStatus.status = "Filled"
    mock_trade.orderStatus.filled = 10
    mock_trade.orderStatus.avgFillPrice = 150.0
    mock_trade.order.orderId = 42
    bridge.ib.placeOrder.return_value = mock_trade

    with patch("src.broker_bridge.MarketOrder", MagicMock()), patch("asyncio.sleep", new_callable=AsyncMock):
        result = await bridge.sell("AAPL", 10)

    assert result["action"] == "SELL"
    assert result["status"] == "Filled"
    # 1500 - (10 * 150) = 0
    assert bridge.total_spent == 0.0


# ============ get_positions with mock ib ============


async def test_get_positions_returns_formatted():
    bridge = IBKRBridge()
    bridge.ib = MagicMock()
    bridge.ib.isConnected.return_value = True

    mock_pos = MagicMock()
    mock_pos.contract.symbol = "AAPL"
    mock_pos.contract.secType = "STK"
    mock_pos.contract.exchange = "SMART"
    mock_pos.contract.currency = "USD"
    mock_pos.position = 10
    mock_pos.avgCost = 150.0
    bridge.ib.positions.return_value = [mock_pos]

    # qualifyContractsAsync 是异步方法，需要 AsyncMock
    bridge.ib.qualifyContractsAsync = AsyncMock(return_value=[mock_pos.contract])
    # reqTickers 返回带实时价格的 ticker mock
    mock_ticker = MagicMock()
    mock_ticker.contract = mock_pos.contract
    mock_ticker.marketPrice.return_value = 150.0  # 当前价 = 成本价
    bridge.ib.reqTickers.return_value = [mock_ticker]

    positions = await bridge.get_positions()
    assert len(positions) == 1
    p = positions[0]
    assert p["symbol"] == "AAPL"
    assert p["sec_type"] == "STK"
    assert p["quantity"] == 10.0
    assert p["avg_cost"] == 150.0
    assert p["market_value"] == 1500.0


async def test_trade_snapshots_include_cross_session_completed_orders():
    bridge = IBKRBridge()
    bridge.ib = MagicMock()
    bridge.ib.isConnected.return_value = True
    bridge.ib.trades.return_value = []
    completed = MagicMock()
    completed.order.orderId = 991
    completed.order.action = "SELL"
    completed.order.totalQuantity = 10
    completed.contract.symbol = "AAPL"
    completed.orderStatus.status = "Filled"
    completed.orderStatus.filled = 10
    completed.orderStatus.remaining = 0
    completed.orderStatus.avgFillPrice = 139.5
    completed.orderStatus.lastFillPrice = 139.0
    bridge.ib.reqCompletedOrdersAsync = AsyncMock(return_value=[completed])

    snapshots = await bridge.get_trade_snapshots()

    assert snapshots == [
        {
            "order_id": 991,
            "symbol": "AAPL",
            "action": "SELL",
            "quantity": 10.0,
            "status": "Filled",
            "filled": 10.0,
            "filled_qty": 10.0,
            "remaining": 0.0,
            "avg_price": 139.5,
            "last_fill_price": 139.0,
        }
    ]
