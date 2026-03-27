"""Tests for NotificationManager — multi-channel notification delivery.

Covers: send(), _event_to_level mapping, _format_event_body, get_stats,
        initialization, NotifyLevel ordering.
"""
import asyncio

import pytest
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

from src.notifications import (
    NotificationManager,
    NotifyLevel,
    _EVENT_NOTIFY_MAP,
    APPRISE_AVAILABLE,
)


# ============ Fixtures ============

@pytest.fixture
def nm():
    """Fresh NotificationManager (not initialized)."""
    return NotificationManager()


@pytest.fixture
def nm_no_apprise(nm):
    """NotificationManager initialized with apprise unavailable."""
    with patch("src.notifications.APPRISE_AVAILABLE", False):
        nm.initialize()
    return nm


# ============ send() ============

class TestSend:

    async def test_send_returns_false_when_apprise_not_available(self, nm):
        """send() returns False when Apprise is not installed."""
        with patch("src.notifications.APPRISE_AVAILABLE", False):
            nm._initialized = True
            nm._ap = None
            result = await nm.send("test message")
        assert result is False

    async def test_send_returns_true_on_success(self, nm):
        """send() returns True when Apprise.notify() succeeds."""
        mock_ap = MagicMock()
        mock_ap.notify.return_value = True
        mock_ap.__len__ = lambda self: 1

        nm._ap = mock_ap
        nm._initialized = True

        with patch("src.notifications.APPRISE_AVAILABLE", True):
            result = await nm.send("test body", title="Test")

        assert result is True
        assert nm._send_count >= 1

    async def test_send_handles_exception_gracefully(self, nm):
        """send() catches Apprise exceptions and increments error_count."""
        mock_ap = MagicMock()
        mock_ap.notify.side_effect = RuntimeError("network error")
        mock_ap.__len__ = lambda self: 1

        nm._ap = mock_ap
        nm._initialized = True

        with patch("src.notifications.APPRISE_AVAILABLE", True):
            result = await nm.send("test body")

        assert result is False
        assert nm._error_count >= 1

    async def test_send_increments_error_count_on_failure(self, nm):
        """Error count increases by 1 on each failed send."""
        mock_ap = MagicMock()
        mock_ap.notify.side_effect = Exception("fail")
        mock_ap.__len__ = lambda self: 1

        nm._ap = mock_ap
        nm._initialized = True
        initial_errors = nm._error_count

        with patch("src.notifications.APPRISE_AVAILABLE", True):
            await nm.send("fail msg")

        assert nm._error_count == initial_errors + 1


# ============ _event_to_level mapping ============

class TestEventNotifyMap:

    def test_trade_risk_alert_maps_to_critical(self):
        """trade.risk_alert should map to CRITICAL level."""
        config = _EVENT_NOTIFY_MAP.get("trade.risk_alert")
        assert config is not None
        assert config["level"] == NotifyLevel.CRITICAL

    def test_unknown_event_not_in_map(self):
        """An unknown event type is not present in the mapping."""
        assert "unknown.event.xyz" not in _EVENT_NOTIFY_MAP

    def test_social_published_maps_to_normal(self):
        """social.published should map to NORMAL level."""
        config = _EVENT_NOTIFY_MAP.get("social.published")
        assert config is not None
        assert config["level"] == NotifyLevel.NORMAL


# ============ _format_event_body ============

class TestFormatNotification:

    def test_format_event_body_produces_nonempty_string(self):
        """_format_event_body returns a non-empty string for a typical event."""
        event = MagicMock()
        event.event_type = "trade.executed"
        event.data = {"symbol": "AAPL", "price": 150.0, "message": "Buy executed"}
        event.source = "bot1"

        body = NotificationManager._format_event_body(event)
        assert len(body) > 0
        assert "AAPL" in body

    def test_format_event_body_handles_empty_data(self):
        """_format_event_body works with empty data dict."""
        event = MagicMock()
        event.event_type = "system.test"
        event.data = {}
        event.source = ""

        body = NotificationManager._format_event_body(event)
        assert len(body) > 0  # Should have fallback text


# ============ get_stats ============

class TestGetStats:

    def test_get_stats_returns_correct_structure(self, nm):
        """get_stats returns a dict with all expected keys."""
        stats = nm.get_stats()
        expected_keys = [
            "apprise_available", "initialized", "channel_count",
            "tag_routes", "min_level", "send_count", "error_count",
            "event_subscribed", "mapped_events",
        ]
        for key in expected_keys:
            assert key in stats, f"Missing key: {key}"

    def test_get_stats_zero_counts_initially(self, nm):
        """Counts are zero before any sends."""
        stats = nm.get_stats()
        assert stats["send_count"] == 0
        assert stats["error_count"] == 0
        assert stats["initialized"] is False


# ============ NotifyLevel ============

class TestNotifyLevel:

    def test_priority_ordering(self):
        """Lower numeric value = higher priority."""
        assert NotifyLevel.CRITICAL < NotifyLevel.HIGH
        assert NotifyLevel.HIGH < NotifyLevel.NORMAL
        assert NotifyLevel.NORMAL < NotifyLevel.LOW

    def test_to_apprise_type_returns_string(self):
        """to_apprise_type always returns a string."""
        for level in NotifyLevel:
            result = level.to_apprise_type()
            assert isinstance(result, str)
