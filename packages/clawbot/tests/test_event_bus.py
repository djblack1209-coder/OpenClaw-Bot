"""
Tests for src/core/event_bus.py — EventBus.

Covers:
  - subscribe() + publish() — subscriber receives event
  - Multiple subscribers receive same event
  - unsubscribe() — no longer receives events
  - Priority ordering of handlers
  - Exception in callback doesn't affect other subscribers
  - Audit log writing verification
  - Wildcard subscriptions
  - Event filtering
"""
import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from src.core.event_bus import EventBus, Event, EventType


# ── Fixtures ────────────────────────────────────────────


@pytest.fixture
def bus(tmp_path, monkeypatch):
    """EventBus with audit writing to tmp_path."""
    monkeypatch.setattr("src.core.event_bus.AUDIT_DIR", tmp_path)
    return EventBus(audit_enabled=True)


@pytest.fixture
def bus_no_audit(tmp_path, monkeypatch):
    """EventBus with audit disabled."""
    monkeypatch.setattr("src.core.event_bus.AUDIT_DIR", tmp_path)
    return EventBus(audit_enabled=False)


# ── subscribe + publish ─────────────────────────────────


class TestSubscribePublish:
    """Basic subscribe and publish flow."""

    async def test_subscriber_receives_event(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.TRADE_EXECUTED, handler, "test_sub")
        count = await bus.publish(EventType.TRADE_EXECUTED, {"symbol": "AAPL"})
        assert count == 1
        assert len(received) == 1
        assert received[0].event_type == EventType.TRADE_EXECUTED
        assert received[0].data["symbol"] == "AAPL"

    async def test_no_subscriber_returns_zero(self, bus):
        count = await bus.publish(EventType.TRADE_EXECUTED, {"symbol": "AAPL"})
        assert count == 0

    async def test_event_id_auto_generated(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.TRADE_SIGNAL, handler, "test")
        await bus.publish(EventType.TRADE_SIGNAL, {})
        assert received[0].event_id.startswith("trade.signal_")


# ── Multiple subscribers ────────────────────────────────


class TestMultipleSubscribers:
    """Multiple subscribers receive the same event."""

    async def test_two_subscribers_both_receive(self, bus):
        results_a = []
        results_b = []

        async def handler_a(event: Event):
            results_a.append(event.data)

        async def handler_b(event: Event):
            results_b.append(event.data)

        bus.subscribe(EventType.TRADE_EXECUTED, handler_a, "sub_a")
        bus.subscribe(EventType.TRADE_EXECUTED, handler_b, "sub_b")
        count = await bus.publish(EventType.TRADE_EXECUTED, {"price": 150.0})
        assert count == 2
        assert len(results_a) == 1
        assert len(results_b) == 1
        assert results_a[0]["price"] == 150.0
        assert results_b[0]["price"] == 150.0

    async def test_three_subscribers_all_receive(self, bus):
        call_count = {"n": 0}

        async def handler(event: Event):
            call_count["n"] += 1

        for i in range(3):
            bus.subscribe(EventType.COST_WARNING, handler, f"sub_{i}")

        count = await bus.publish(EventType.COST_WARNING, {"spend": 45.0})
        assert count == 3
        assert call_count["n"] == 3


# ── unsubscribe ─────────────────────────────────────────


class TestUnsubscribe:
    """Unsubscribed handlers no longer receive events."""

    async def test_unsubscribe_stops_delivery(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.TRADE_EXECUTED, handler, "test")
        result = bus.unsubscribe(EventType.TRADE_EXECUTED, handler)
        assert result is True

        await bus.publish(EventType.TRADE_EXECUTED, {"symbol": "AAPL"})
        assert len(received) == 0

    async def test_unsubscribe_nonexistent_returns_false(self, bus):
        async def handler(event: Event):
            pass

        result = bus.unsubscribe(EventType.TRADE_EXECUTED, handler)
        assert result is False

    async def test_unsubscribe_one_keeps_others(self, bus):
        received_a = []
        received_b = []

        async def handler_a(event: Event):
            received_a.append(1)

        async def handler_b(event: Event):
            received_b.append(1)

        bus.subscribe(EventType.TRADE_EXECUTED, handler_a, "a")
        bus.subscribe(EventType.TRADE_EXECUTED, handler_b, "b")
        bus.unsubscribe(EventType.TRADE_EXECUTED, handler_a)

        await bus.publish(EventType.TRADE_EXECUTED, {})
        assert len(received_a) == 0
        assert len(received_b) == 1

    async def test_unsubscribe_wildcard(self, bus):
        received = []

        async def handler(event: Event):
            received.append(1)

        bus.subscribe("trade.*", handler, "wildcard_test")
        result = bus.unsubscribe("trade.*", handler)
        assert result is True

        await bus.publish(EventType.TRADE_EXECUTED, {})
        assert len(received) == 0


# ── Priority ordering ──────────────────────────────────


class TestPriorityOrdering:
    """Handlers execute in priority order (lower number = higher priority)."""

    async def test_high_priority_runs_first(self, bus):
        order = []

        async def high_priority(event: Event):
            order.append("high")

        async def low_priority(event: Event):
            order.append("low")

        async def medium_priority(event: Event):
            order.append("medium")

        # Subscribe in reverse order to verify sorting
        bus.subscribe(EventType.TRADE_SIGNAL, low_priority, "low", priority=10)
        bus.subscribe(EventType.TRADE_SIGNAL, high_priority, "high", priority=1)
        bus.subscribe(EventType.TRADE_SIGNAL, medium_priority, "med", priority=5)

        await bus.publish(EventType.TRADE_SIGNAL, {})

        assert order == ["high", "medium", "low"]


# ── Exception isolation ─────────────────────────────────


class TestExceptionIsolation:
    """Exception in one callback doesn't affect others."""

    async def test_error_handler_doesnt_break_others(self, bus):
        results = []

        async def good_handler(event: Event):
            results.append("ok")

        async def bad_handler(event: Event):
            raise ValueError("Intentional error")

        bus.subscribe(EventType.TRADE_EXECUTED, good_handler, "good", priority=1)
        bus.subscribe(EventType.TRADE_EXECUTED, bad_handler, "bad", priority=5)

        count = await bus.publish(EventType.TRADE_EXECUTED, {"symbol": "AAPL"})
        # good_handler succeeded, bad_handler failed
        assert count == 1
        assert len(results) == 1
        assert results[0] == "ok"

    async def test_error_counted_in_stats(self, bus):
        async def bad_handler(event: Event):
            raise RuntimeError("boom")

        bus.subscribe(EventType.COST_WARNING, bad_handler, "crasher")
        await bus.publish(EventType.COST_WARNING, {})

        stats = bus.get_stats()
        assert stats["error_counts"]["crasher:system.cost_warning"] == 1

    async def test_multiple_errors_all_counted(self, bus):
        async def bad_handler(event: Event):
            raise RuntimeError("boom")

        bus.subscribe(EventType.COST_WARNING, bad_handler, "crasher")
        await bus.publish(EventType.COST_WARNING, {})
        await bus.publish(EventType.COST_WARNING, {})

        stats = bus.get_stats()
        assert stats["error_counts"]["crasher:system.cost_warning"] == 2


# ── Audit log writing ──────────────────────────────────


class TestAuditLog:
    """Audit log file writing verification."""

    async def test_publish_writes_audit(self, bus, tmp_path):
        async def handler(event: Event):
            pass

        bus.subscribe(EventType.TRADE_EXECUTED, handler, "test")
        await bus.publish(
            EventType.TRADE_EXECUTED,
            {"symbol": "AAPL", "price": 150.0},
            source="test_source",
        )

        audit_file = tmp_path / "events.jsonl"
        assert audit_file.exists()
        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["type"] == EventType.TRADE_EXECUTED
        assert record["source"] == "test_source"
        assert "symbol" in record["data_keys"]
        assert "price" in record["data_keys"]

    async def test_audit_disabled_no_file(self, bus_no_audit, tmp_path):
        async def handler(event: Event):
            pass

        bus_no_audit.subscribe(EventType.TRADE_EXECUTED, handler, "test")
        await bus_no_audit.publish(EventType.TRADE_EXECUTED, {"symbol": "AAPL"})

        audit_file = tmp_path / "events.jsonl"
        assert not audit_file.exists()

    async def test_multiple_publishes_append(self, bus, tmp_path):
        await bus.publish(EventType.TRADE_SIGNAL, {"a": 1})
        await bus.publish(EventType.TRADE_EXECUTED, {"b": 2})
        await bus.publish(EventType.COST_WARNING, {"c": 3})

        audit_file = tmp_path / "events.jsonl"
        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) == 3


# ── Wildcard subscriptions ─────────────────────────────


class TestWildcardSubscription:
    """Wildcard pattern matching (trade.* matches trade.signal, trade.executed)."""

    async def test_wildcard_matches_subtypes(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event.event_type)

        bus.subscribe("trade.*", handler, "trade_monitor")
        await bus.publish(EventType.TRADE_SIGNAL, {"signal": "buy"})
        await bus.publish(EventType.TRADE_EXECUTED, {"executed": True})
        await bus.publish(EventType.COST_WARNING, {"cost": 10})  # Should NOT match

        assert len(received) == 2
        assert EventType.TRADE_SIGNAL in received
        assert EventType.TRADE_EXECUTED in received

    async def test_wildcard_and_exact_both_fire(self, bus):
        wildcard_received = []
        exact_received = []

        async def wildcard_handler(event: Event):
            wildcard_received.append(1)

        async def exact_handler(event: Event):
            exact_received.append(1)

        bus.subscribe("trade.*", wildcard_handler, "wildcard")
        bus.subscribe(EventType.TRADE_EXECUTED, exact_handler, "exact")

        count = await bus.publish(EventType.TRADE_EXECUTED, {})
        assert count == 2
        assert len(wildcard_received) == 1
        assert len(exact_received) == 1


# ── Event filtering ─────────────────────────────────────


class TestEventFiltering:
    """filter_fn skips events that don't match."""

    async def test_filter_fn_skips_non_matching(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event.data)

        def only_aapl(event: Event) -> bool:
            return event.data.get("symbol") == "AAPL"

        bus.subscribe(EventType.TRADE_EXECUTED, handler, "filtered", filter_fn=only_aapl)

        await bus.publish(EventType.TRADE_EXECUTED, {"symbol": "AAPL"})
        await bus.publish(EventType.TRADE_EXECUTED, {"symbol": "MSFT"})

        assert len(received) == 1
        assert received[0]["symbol"] == "AAPL"


# ── Event history and stats ─────────────────────────────


class TestEventStats:
    """get_stats() and get_recent_events()."""

    async def test_stats_count_events(self, bus):
        await bus.publish(EventType.TRADE_SIGNAL, {})
        await bus.publish(EventType.TRADE_SIGNAL, {})
        await bus.publish(EventType.COST_WARNING, {})

        stats = bus.get_stats()
        assert stats["total_events"] == 3
        assert stats["event_counts"][EventType.TRADE_SIGNAL] == 2
        assert stats["event_counts"][EventType.COST_WARNING] == 1

    async def test_recent_events_retrieval(self, bus):
        await bus.publish(EventType.TRADE_SIGNAL, {"n": 1})
        await bus.publish(EventType.TRADE_EXECUTED, {"n": 2})

        recent = bus.get_recent_events(limit=10)
        assert len(recent) == 2
        assert recent[0]["data"]["n"] == 1
        assert recent[1]["data"]["n"] == 2

    async def test_recent_events_filtered_by_type(self, bus):
        await bus.publish(EventType.TRADE_SIGNAL, {"n": 1})
        await bus.publish(EventType.COST_WARNING, {"n": 2})
        await bus.publish(EventType.TRADE_SIGNAL, {"n": 3})

        recent = bus.get_recent_events(event_type=EventType.TRADE_SIGNAL, limit=10)
        assert len(recent) == 2
        assert all(r["type"] == EventType.TRADE_SIGNAL for r in recent)
