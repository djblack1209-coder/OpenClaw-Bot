from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.core.cost_control import CostController


@pytest.fixture
def controller(tmp_path, monkeypatch):
    moment = datetime(2026, 9, 10, 16, tzinfo=UTC)
    cc = CostController(2, ledger_path=tmp_path / "cost.sqlite3", clock=lambda: moment)
    monkeypatch.setattr("src.core.cost_control.get_cost_controller", lambda: cc)
    return cc


def test_rpc_pool_costs_come_from_ledger_and_unknown_is_nullable(controller, monkeypatch):
    from src.api.rpc import ClawBotRPC
    from src.litellm_router import free_pool

    monkeypatch.setattr(free_pool, "get_stats", lambda: {})
    unknown = ClawBotRPC._rpc_pool_stats()
    assert unknown["today_cost"] is unknown["week_cost"] is unknown["month_cost"] is None
    controller.ledger.activate(opening_spend_usd=0.50)
    controller.record_cost("fixture", 0.01)
    known = ClawBotRPC._rpc_pool_stats()
    assert known["today_cost"] == pytest.approx(0.51)
    assert known["week_cost"] is known["month_cost"] is None
    assert known["known_week_cost"] == known["known_month_cost"] == known["today_cost"]


def test_system_status_preserves_daily_cost_separately_from_total(controller, monkeypatch):
    from src.api.rpc import ClawBotRPC
    from src.litellm_router import free_pool

    monkeypatch.setattr(
        free_pool,
        "get_stats",
        lambda: {
            "total_sources": 0,
            "active_sources": 0,
            "total_cost_usd": 900,
            "cost_today_usd": 0.25,
            "cost_accounting": {"accounting_complete": False},
        },
    )
    status = ClawBotRPC._rpc_system_status()
    assert status["cost_today_usd"] == 0.25
    assert status["total_cost_usd"] == 900
    assert status["cost_accounting"]["accounting_complete"] is False


@pytest.mark.parametrize("mode", ["inactive", "imported", "active", "pending"])
def test_cost_api_distinguishes_coverage_and_known_subtotals(controller, monkeypatch, tmp_path, mode):
    from src.api.rpc import ClawBotRPC
    from src.litellm_router import free_pool

    monkeypatch.setattr(free_pool, "get_stats", lambda: {})
    if mode == "imported":
        source = tmp_path / "legacy.jsonl"
        source.write_text('{"date":"2026-09-10","cost_usd":0.2}\n')
        controller.ledger.import_legacy(source, dry_run=False)
    elif mode in {"active", "pending"}:
        controller.ledger.activate(opening_spend_usd=0)
        if mode == "pending":
            controller.ledger.reserve(
                attempt_id="pending",
                request_id="request",
                provider="fixture",
                deployment_id="fixture",
                model="fixture",
                price_snapshot="fixture",
                budget_usd=2,
                max_cost_usd=0.1,
            )
    data = ClawBotRPC._rpc_pool_stats()
    accounting = data["cost_accounting"]
    assert accounting["accounting_complete"] is (mode == "active")
    assert accounting["total_cost_usd"] == (0 if mode == "active" else None)
    assert data["week_cost"] is data["month_cost"] is None
    if mode == "imported":
        assert data["known_week_cost"] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_zero_budget_telegram_still_shows_cost_message(controller):
    from unittest.mock import AsyncMock

    from src.gateway.telegram_gateway import OpenClawGateway

    controller.ledger.activate(opening_spend_usd=0)
    controller._daily_budget = 0
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=SimpleNamespace(reply_text=AsyncMock()))
    gateway = SimpleNamespace(_check_authorized=lambda user: True)
    await OpenClawGateway._cmd_cost(gateway, update, None)
    text = update.message.reply_text.await_args.args[0]
    assert "日预算: $0.00" in text
    assert "已知花费: $0.0000" in text
