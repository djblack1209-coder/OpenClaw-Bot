"""P0 交易安全状态机回归测试。"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.broker_bridge import IBKRBridge
from src.models import TradeProposal
from src.position_monitor import ExitReason, ExitSignal, MonitoredPosition, PositionMonitor
from src.trading_pipeline import TradingPipeline
from src.utils import now_et


def _proposal() -> TradeProposal:
    """构造不依赖风控的最小买入提案。"""
    return TradeProposal(
        symbol="AAPL",
        action="BUY",
        quantity=3,
        entry_price=150.0,
        stop_loss=145.0,
        take_profit=160.0,
        signal_score=60,
    )


async def test_sync_capital_never_expands_configured_budget_or_resets_spent(tmp_path):
    bridge = IBKRBridge(budget=2_000.0)
    bridge.bind_current_loop()
    bridge.total_spent = 450.0
    bridge.get_account_summary = AsyncMock(
        return_value={
            "AvailableFunds": {"value": 50_000.0},
            "NetLiquidation": {"value": 75_000.0},
        }
    )

    with patch("src.broker_bridge.BUDGET_STATE_FILE", tmp_path / "budget.json"):
        synced = await bridge.sync_capital()

    assert synced == 2_000.0
    assert bridge.budget == 2_000.0
    assert bridge.total_spent == 450.0


async def test_sync_capital_lowers_budget_to_available_funds_and_preserves_spent(tmp_path):
    bridge = IBKRBridge(budget=2_000.0)
    bridge.bind_current_loop()
    bridge.total_spent = 450.0
    bridge.get_account_summary = AsyncMock(
        return_value={
            "AvailableFunds": {"value": 900.0},
            "NetLiquidation": {"value": 10_000.0},
        }
    )

    with patch("src.broker_bridge.BUDGET_STATE_FILE", tmp_path / "budget.json"):
        synced = await bridge.sync_capital()

    assert synced == 900.0
    assert bridge.total_spent == 450.0


@pytest.mark.parametrize("status", ["Cancelled", "ApiCancelled", "Inactive", "Filled"])
async def test_zero_fill_terminal_order_does_not_create_real_position(status):
    broker = AsyncMock()
    broker.buy.return_value = {
        "status": status,
        "filled_qty": 0,
        "avg_price": 0,
        "order_id": 77,
    }
    journal = MagicMock()
    monitor = MagicMock()
    pipeline = TradingPipeline(broker=broker, journal=journal, monitor=monitor)

    result = await pipeline.execute_proposal(_proposal())

    assert result["status"] == "error"
    assert result["filled_qty"] == 0
    journal.open_trade.assert_not_called()
    monitor.add_position.assert_not_called()


async def test_submitted_zero_fill_is_pending_and_not_a_real_position():
    broker = AsyncMock()
    broker.buy.return_value = {
        "status": "Submitted",
        "filled_qty": 0,
        "avg_price": 0,
        "order_id": 78,
    }
    journal = MagicMock()
    journal.open_trade.return_value = 91
    monitor = MagicMock()
    pipeline = TradingPipeline(broker=broker, journal=journal, monitor=monitor)

    result = await pipeline.execute_proposal(_proposal())

    assert result["status"] == "submitted"
    assert journal.open_trade.call_args.kwargs["status"] == "pending"
    monitor.add_position.assert_not_called()


async def test_cancelled_order_with_confirmed_partial_fill_tracks_real_quantity():
    broker = AsyncMock()
    broker.buy.return_value = {
        "status": "Cancelled",
        "filled_qty": 2,
        "avg_price": 149.0,
        "order_id": 79,
    }
    journal = MagicMock()
    journal.open_trade.return_value = 92
    monitor = MagicMock()
    pipeline = TradingPipeline(broker=broker, journal=journal, monitor=monitor)

    result = await pipeline.execute_proposal(_proposal())

    assert result["status"] == "executed"
    assert result["quantity"] == 2
    assert journal.open_trade.call_args.kwargs["quantity"] == 2
    assert monitor.add_position.call_args.args[0].quantity == 2


def _exit_fixture(sell_result: dict):
    sell = AsyncMock(return_value=sell_result)
    journal = MagicMock()
    risk = MagicMock()
    monitor = PositionMonitor(
        execute_sell_func=sell,
        journal=journal,
        risk_manager=risk,
    )
    position = MonitoredPosition(
        trade_id=12,
        symbol="AAPL",
        side="BUY",
        quantity=10,
        entry_price=150.0,
        entry_time=now_et(),
        stop_loss=145.0,
    )
    position.update_price(140.0)
    monitor.add_position(position)
    signal = ExitSignal(
        position=position,
        reason=ExitReason.STOP_LOSS,
        trigger_price=140.0,
        message="止损",
    )
    return monitor, journal, risk, signal


@pytest.mark.parametrize(
    "sell_result",
    [
        {"error": "连接中断"},
        {"status": "Cancelled", "filled_qty": 0, "order_id": 80},
        {"status": "Inactive", "filled_qty": 0, "order_id": 81},
        {"status": "Submitted", "filled_qty": 0, "order_id": 82},
        {"status": "Filled", "filled_qty": 0, "order_id": 83},
        {"status": "Filled", "filled_qty": 10, "avg_price": 140.0, "simulated": True},
    ],
)
async def test_unconfirmed_or_simulated_exit_keeps_real_position(sell_result):
    monitor, journal, risk, signal = _exit_fixture(sell_result)

    await monitor._execute_exit(signal)

    assert signal.position.trade_id in monitor.positions
    journal.close_trade.assert_not_called()
    risk.record_trade_result.assert_not_called()


async def test_confirmed_partial_exit_reduces_position_without_closing_trade():
    monitor, journal, risk, signal = _exit_fixture(
        {"status": "Submitted", "filled_qty": 4, "avg_price": 140.0, "order_id": 84}
    )

    await monitor._execute_exit(signal)

    assert monitor.positions[12].quantity == 6
    journal.close_trade.assert_not_called()
    risk.record_trade_result.assert_called_once()


async def test_confirmed_full_exit_closes_and_removes_position():
    monitor, journal, risk, signal = _exit_fixture(
        {"status": "Filled", "filled_qty": 10, "avg_price": 140.0, "order_id": 85}
    )

    await monitor._execute_exit(signal)

    assert 12 not in monitor.positions
    journal.close_trade.assert_called_once()
    risk.record_trade_result.assert_called_once()


async def test_pending_exit_can_be_reconciled_to_full_fill():
    monitor, journal, risk, signal = _exit_fixture(
        {"status": "Submitted", "filled_qty": 0, "avg_price": 0, "order_id": 86}
    )
    submitted = await monitor._execute_exit(signal)

    reconciled = await monitor.reconcile_pending_exit(
        12,
        {"status": "Filled", "filled_qty": 10, "avg_price": 139.0, "order_id": 86},
    )

    assert submitted["status"] == "pending_confirmation"
    assert reconciled["success"] is True
    assert 12 not in monitor.positions
    assert 12 not in monitor._pending_exit_orders
    journal.close_trade.assert_called_once()
    risk.record_trade_result.assert_called_once()


async def test_pending_exit_reconciles_only_incremental_partial_fills():
    monitor, journal, risk, signal = _exit_fixture(
        {"status": "Submitted", "filled_qty": 0, "avg_price": 0, "order_id": 87}
    )
    await monitor._execute_exit(signal)

    first = await monitor.reconcile_pending_exit(
        12,
        {"status": "Submitted", "filled_qty": 4, "avg_price": 141.0, "order_id": 87},
    )
    second = await monitor.reconcile_pending_exit(
        12,
        {"status": "Filled", "filled_qty": 10, "avg_price": 140.0, "order_id": 87},
    )

    assert first["status"] == "partially_filled_pending"
    assert first["remaining_qty"] == 6
    assert second["success"] is True
    assert 12 not in monitor.positions
    assert risk.record_trade_result.call_count == 2
    journal.close_trade.assert_called_once()
    assert journal.close_trade.call_args.kwargs["exit_price"] == pytest.approx(140.0)


async def test_cancelled_pending_exit_is_cleared_but_position_remains_monitored():
    monitor, journal, risk, signal = _exit_fixture(
        {"status": "Submitted", "filled_qty": 0, "avg_price": 0, "order_id": 88}
    )
    await monitor._execute_exit(signal)

    result = await monitor.reconcile_pending_exit(
        12,
        {"status": "Cancelled", "filled_qty": 0, "avg_price": 0, "order_id": 88},
    )

    assert result["success"] is False
    assert 12 in monitor.positions
    assert 12 not in monitor._pending_exit_orders
    journal.close_trade.assert_not_called()
    risk.record_trade_result.assert_not_called()


async def test_monitor_loop_reconciles_pending_exit_from_broker_snapshot(tmp_path):
    monitor, journal, risk, signal = _exit_fixture(
        {"status": "Submitted", "filled_qty": 0, "avg_price": 0, "order_id": 89}
    )
    monitor._pending_exit_state_path = tmp_path / "pending-exits.json"
    await monitor._execute_exit(signal)
    monitor.get_order_snapshots = AsyncMock(
        return_value=[
            {
                "order_id": 89,
                "status": "Filled",
                "filled": 10,
                "avg_price": 139.0,
            }
        ]
    )

    await monitor._reconcile_pending_exit_orders()

    assert 12 not in monitor.positions
    assert 12 not in monitor._pending_exit_orders
    journal.close_trade.assert_called_once()
    risk.record_trade_result.assert_called_once()


async def test_restart_restores_partial_exit_and_blocks_duplicate_sell(tmp_path):
    state_path = tmp_path / "pending-exits.json"
    first, _journal, _risk, first_signal = _exit_fixture(
        {"status": "Submitted", "filled_qty": 0, "avg_price": 0, "order_id": 90}
    )
    first._pending_exit_state_path = state_path
    await first._execute_exit(first_signal)
    await first.reconcile_pending_exit(
        12,
        {"status": "Submitted", "filled_qty": 4, "avg_price": 141.0, "order_id": 90},
    )

    duplicate_sell = AsyncMock()
    journal = MagicMock()
    risk = MagicMock()
    restarted = PositionMonitor(
        execute_sell_func=duplicate_sell,
        journal=journal,
        risk_manager=risk,
        get_order_snapshots_func=AsyncMock(
            return_value=[
                {
                    "order_id": 90,
                    "status": "Filled",
                    "filled_qty": 10,
                    "avg_price": 140.0,
                }
            ]
        ),
        pending_exit_state_path=state_path,
    )
    restored_position = MonitoredPosition(
        trade_id=12,
        symbol="AAPL",
        side="BUY",
        quantity=10,
        entry_price=150.0,
        entry_time=now_et(),
        stop_loss=145.0,
    )
    restored_position.update_price(140.0)
    restarted.add_position(restored_position)
    duplicate_signal = ExitSignal(
        position=restored_position,
        reason=ExitReason.STOP_LOSS,
        trigger_price=140.0,
        message="重启后的止损",
    )

    blocked = await restarted._execute_exit(duplicate_signal)
    await restarted._reconcile_pending_exit_orders()

    assert blocked["status"] == "pending_confirmation"
    duplicate_sell.assert_not_called()
    assert restored_position.quantity == 6
    assert 12 not in restarted.positions
    journal.close_trade.assert_called_once()
    assert journal.close_trade.call_args.kwargs["exit_price"] == pytest.approx(140.0)
    persisted = state_path.read_text(encoding="utf-8")
    assert '"pending_exit_orders": {}' in persisted


async def test_two_monitor_instances_share_submission_claim_and_close_tombstone(tmp_path):
    state_path = tmp_path / "pending-exits.json"
    sell_started = asyncio.Event()
    release_sell = asyncio.Event()

    async def blocked_sell(**_kwargs):
        sell_started.set()
        await release_sell.wait()
        return {
            "status": "Filled",
            "filled_qty": 10,
            "avg_price": 140.0,
            "order_id": 901,
        }

    first = PositionMonitor(
        execute_sell_func=blocked_sell,
        pending_exit_state_path=state_path,
    )
    second_sell = AsyncMock(
        return_value={
            "status": "Filled",
            "filled_qty": 10,
            "avg_price": 140.0,
            "order_id": 902,
        }
    )
    second = PositionMonitor(
        execute_sell_func=second_sell,
        pending_exit_state_path=state_path,
    )

    positions = []
    signals = []
    for monitor in (first, second):
        position = MonitoredPosition(
            trade_id=77,
            symbol="AAPL",
            side="BUY",
            quantity=10,
            entry_price=150.0,
            entry_time=now_et(),
            stop_loss=145.0,
        )
        position.update_price(140.0)
        monitor.add_position(position)
        positions.append(position)
        signals.append(
            ExitSignal(
                position=position,
                reason=ExitReason.STOP_LOSS,
                trigger_price=140.0,
                message="双实例止损",
            )
        )

    first_task = asyncio.create_task(first._execute_exit(signals[0]))
    await asyncio.wait_for(sell_started.wait(), timeout=5)
    blocked = await second._execute_exit(signals[1])
    assert blocked["status"] == "pending_confirmation"
    second_sell.assert_not_awaited()

    release_sell.set()
    completed = await asyncio.wait_for(first_task, timeout=5)
    assert completed["success"] is True
    assert 77 in first._completed_exit_trades

    # 第一实例完成后，第二实例仍持有旧内存仓位，也不能再次提交真实卖单。
    already_closed = await second._execute_exit(signals[1])
    assert already_closed["status"] == "already_closed"
    assert 77 not in second.positions
    second_sell.assert_not_awaited()


async def test_two_instances_apply_same_cumulative_exit_fill_only_once(tmp_path):
    state_path = tmp_path / "pending-exits.json"
    seed, _journal, _risk, seed_signal = _exit_fixture(
        {"status": "Submitted", "filled_qty": 0, "avg_price": 0, "order_id": 911}
    )
    seed._pending_exit_state_path = state_path
    await seed._execute_exit(seed_signal)

    notify_started = asyncio.Event()
    release_notify = asyncio.Event()

    async def blocked_notify(_message):
        notify_started.set()
        await release_notify.wait()

    monitors = []
    journals = []
    risks = []
    for _index in range(2):
        journal = MagicMock()
        risk = MagicMock()
        monitor = PositionMonitor(
            journal=journal,
            risk_manager=risk,
            notify_func=blocked_notify,
            pending_exit_state_path=state_path,
        )
        position = MonitoredPosition(
            trade_id=12,
            symbol="AAPL",
            side="BUY",
            quantity=10,
            entry_price=150.0,
            entry_time=now_et(),
            stop_loss=145.0,
        )
        position.update_price(140.0)
        monitor.add_position(position)
        monitors.append(monitor)
        journals.append(journal)
        risks.append(risk)

    cumulative_fill = {
        "status": "Filled",
        "filled_qty": 10,
        "avg_price": 139.0,
        "order_id": 911,
    }
    tasks = [
        asyncio.create_task(monitor.reconcile_pending_exit(12, cumulative_fill))
        for monitor in monitors
    ]
    await asyncio.wait_for(notify_started.wait(), timeout=5)
    await asyncio.sleep(0)
    release_notify.set()
    results = await asyncio.gather(*tasks)

    assert sum(result["success"] for result in results) == 1
    assert {result["status"] for result in results} == {"filled", "reconcile_in_progress"}
    assert sum(journal.close_trade.call_count for journal in journals) == 1
    assert sum(risk.record_trade_result.call_count for risk in risks) == 1
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["pending_exit_orders"] == {}
    assert persisted["completed_exit_trades"] == [12]


async def test_concurrent_reconcile_for_different_trades_preserves_both_claims(tmp_path):
    state_path = tmp_path / "pending-exits.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 2,
                "pending_exit_orders": {
                    "101": {
                        "status": "Submitted",
                        "order_id": 921,
                        "requested_qty": 5,
                        "applied_filled_qty": 0,
                        "applied_order_notional": 0,
                        "remaining_position_qty": 5,
                        "reason": "stop_loss",
                        "trigger_price": 90,
                        "message": "AAPL 止损",
                    },
                    "102": {
                        "status": "Submitted",
                        "order_id": 922,
                        "requested_qty": 7,
                        "applied_filled_qty": 0,
                        "applied_order_notional": 0,
                        "remaining_position_qty": 7,
                        "reason": "stop_loss",
                        "trigger_price": 190,
                        "message": "MSFT 止损",
                    },
                },
                "exit_fill_totals": {},
                "exit_retry_count": {},
                "manual_exit_required": [],
                "completed_exit_trades": [],
            }
        ),
        encoding="utf-8",
    )
    release_notify = asyncio.Event()
    notify_started = [asyncio.Event(), asyncio.Event()]
    monitors = []
    journals = []
    risks = []
    specs = [
        (101, "AAPL", 5, 100.0, 90.0, 921),
        (102, "MSFT", 7, 200.0, 190.0, 922),
    ]

    for index, (trade_id, symbol, quantity, entry_price, exit_price, _order_id) in enumerate(specs):
        async def blocked_notify(_message, event=notify_started[index]):
            event.set()
            await release_notify.wait()

        journal = MagicMock()
        risk = MagicMock()
        monitor = PositionMonitor(
            journal=journal,
            risk_manager=risk,
            notify_func=blocked_notify,
            pending_exit_state_path=state_path,
        )
        position = MonitoredPosition(
            trade_id=trade_id,
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            entry_price=entry_price,
            entry_time=now_et(),
        )
        position.update_price(exit_price)
        monitor.add_position(position)
        monitors.append(monitor)
        journals.append(journal)
        risks.append(risk)

    tasks = [
        asyncio.create_task(
            monitor.reconcile_pending_exit(
                trade_id,
                {
                    "status": "Filled",
                    "filled_qty": quantity,
                    "avg_price": exit_price,
                    "order_id": order_id,
                },
            )
        )
        for monitor, (trade_id, _symbol, quantity, _entry, exit_price, order_id) in zip(
            monitors,
            specs,
            strict=True,
        )
    ]
    await asyncio.wait_for(
        asyncio.gather(*(event.wait() for event in notify_started)),
        timeout=5,
    )
    in_progress = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(in_progress["pending_exit_orders"]) == {"101", "102"}
    assert all(
        "reconcile_claim" in pending
        for pending in in_progress["pending_exit_orders"].values()
    )

    release_notify.set()
    results = await asyncio.gather(*tasks)
    assert all(result["success"] for result in results)
    assert sum(journal.close_trade.call_count for journal in journals) == 2
    assert sum(risk.record_trade_result.call_count for risk in risks) == 2
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["pending_exit_orders"] == {}
    assert persisted["completed_exit_trades"] == [101, 102]
