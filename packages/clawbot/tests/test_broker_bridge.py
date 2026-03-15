"""Tests for src/broker_bridge.py — pure logic & mock-based (no real IBKR connection)."""
import sys
import os
import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.broker_bridge import IBKRBridge, SlippageEstimate


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
    bridge = IBKRBridge(host="10.0.0.1", port=7497, client_id=5,
                        account="TEST123", budget=5000.0)
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
    assert "ib_insync 未安装" in status


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

    with patch("src.broker_bridge.MarketOrder", MagicMock()), \
         patch("asyncio.sleep", new_callable=AsyncMock):
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

    positions = await bridge.get_positions()
    assert len(positions) == 1
    p = positions[0]
    assert p["symbol"] == "AAPL"
    assert p["sec_type"] == "STK"
    assert p["quantity"] == 10.0
    assert p["avg_cost"] == 150.0
    assert p["market_value"] == 1500.0
