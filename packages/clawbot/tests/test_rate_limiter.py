"""
Tests for rate_limiter module — RateLimiter, TokenBudget, QualityGate.
"""
import time
import pytest
from unittest.mock import patch

from src.bot.rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    TokenBudget,
    TokenBudgetConfig,
    QualityGate,
)


# ── fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def rate_limiter():
    return RateLimiter(RateLimitConfig(
        max_requests_per_minute=3,
        max_requests_per_hour=10,
        max_requests_per_day=20,
        min_interval_group=5.0,
        min_interval_private=1.0,
    ))


@pytest.fixture
def token_budget():
    return TokenBudget(TokenBudgetConfig(
        daily_token_limit=100_000,
        claude_budget_ratio=0.5,
    ))


@pytest.fixture
def quality_gate():
    return QualityGate(min_response_length=2, max_duplicate_ratio=0.8)


# ── RateLimiter ───────────────────────────────────────────────────────

class TestFirstRequestAllowed:
    """First request for a new bot should always be allowed."""

    def test_first_request_allowed(self, rate_limiter):
        allowed, reason = rate_limiter.check("bot_a", "group")
        assert allowed is True
        assert reason == ""


class TestMinIntervalGroup:
    """Requests within min_interval_group should be blocked."""

    def test_min_interval_group(self, rate_limiter):
        now = time.time()
        rate_limiter._last_response["bot_a"] = now
        allowed, reason = rate_limiter.check("bot_a", "group")
        assert allowed is False
        assert "发言间隔" in reason


class TestMinIntervalPrivate:
    """Private chat has a shorter interval."""

    def test_min_interval_private(self, rate_limiter):
        now = time.time()
        # Set last response 2 seconds ago — exceeds private interval (1s)
        # but within group interval (5s)
        rate_limiter._last_response["bot_a"] = now - 2.0
        allowed_private, _ = rate_limiter.check("bot_a", "private")
        assert allowed_private is True

        # Same gap should be blocked for group
        allowed_group, reason = rate_limiter.check("bot_a", "group")
        assert allowed_group is False
        assert "发言间隔" in reason


class TestPerMinuteLimit:
    """Exceeding max_requests_per_minute blocks the request."""

    def test_per_minute_limit(self, rate_limiter):
        now = time.time()
        # Fill up per-minute quota (3 requests within last 60s)
        rate_limiter._requests["bot_a"] = [now - 30, now - 20, now - 10]
        # Ensure min_interval check passes
        rate_limiter._last_response["bot_a"] = now - 10.0

        allowed, reason = rate_limiter.check("bot_a", "group")
        assert allowed is False
        assert "/min" in reason


class TestPerHourLimit:
    """Exceeding max_requests_per_hour blocks the request."""

    def test_per_hour_limit(self, rate_limiter):
        now = time.time()
        # 10 requests spread across the last hour (but not in last minute)
        rate_limiter._requests["bot_a"] = [now - 600 - i * 60 for i in range(10)]
        rate_limiter._last_response["bot_a"] = now - 10.0

        allowed, reason = rate_limiter.check("bot_a", "group")
        assert allowed is False
        assert "/hr" in reason


class TestPerDayLimit:
    """Exceeding max_requests_per_day blocks the request."""

    def test_per_day_limit(self, rate_limiter):
        now = time.time()
        # 20 requests spread across the last 24h (but not in last hour)
        rate_limiter._requests["bot_a"] = [now - 7200 - i * 100 for i in range(20)]
        rate_limiter._last_response["bot_a"] = now - 10.0

        allowed, reason = rate_limiter.check("bot_a", "group")
        assert allowed is False
        assert "/day" in reason


class TestRecordUpdatesTimestamps:
    """record() updates last_response and adds a timestamp."""

    def test_record_updates_timestamps(self, rate_limiter):
        before = time.time()
        rate_limiter.record("bot_a")
        after = time.time()

        assert len(rate_limiter._requests["bot_a"]) == 1
        assert before <= rate_limiter._requests["bot_a"][0] <= after
        assert before <= rate_limiter._last_response["bot_a"] <= after


class TestGetStatus:
    """get_status returns correct counts."""

    def test_get_status(self, rate_limiter):
        now = time.time()
        rate_limiter._requests["bot_a"] = [
            now - 30,       # within last minute and hour
            now - 120,      # within last hour only
            now - 7200,     # within last day only
        ]
        rate_limiter._throttled_count["bot_a"] = 2

        status = rate_limiter.get_status("bot_a")
        assert status["requests_last_minute"] == 1
        assert status["requests_last_hour"] == 2
        assert status["requests_today"] == 3
        assert status["throttled_count"] == 2
        assert status["limits"]["per_minute"] == 3
        assert status["limits"]["per_hour"] == 10
        assert status["limits"]["per_day"] == 20


class TestGetAllStatus:
    """get_all_status returns all bots."""

    def test_get_all_status(self, rate_limiter):
        rate_limiter.record("bot_a")
        rate_limiter.record("bot_b")
        all_status = rate_limiter.get_all_status()
        assert "bot_a" in all_status
        assert "bot_b" in all_status
        assert len(all_status) == 2


class TestOldRecordsCleaned:
    """Records older than 24h are cleaned up during check()."""

    def test_old_records_cleaned(self, rate_limiter):
        now = time.time()
        rate_limiter._requests["bot_a"] = [
            now - 90000,  # older than 24h (86400s)
            now - 90001,
            now - 30,     # recent
        ]
        rate_limiter._last_response["bot_a"] = now - 10.0

        rate_limiter.check("bot_a", "group")
        # Only the recent record should survive
        assert len(rate_limiter._requests["bot_a"]) == 1


# ── TokenBudget ───────────────────────────────────────────────────────

class TestTokenFirstCheckAllowed:
    """Fresh bot has full budget."""

    def test_first_check_allowed(self, token_budget):
        allowed, reason = token_budget.check("bot_a")
        assert allowed is True
        assert reason == ""


class TestBudgetExhausted:
    """After recording enough tokens, check returns False."""

    def test_budget_exhausted(self, token_budget):
        token_budget.record("bot_a", 60_000, 40_000)  # total = 100_000
        allowed, reason = token_budget.check("bot_a")
        assert allowed is False
        assert "预算" in reason


class TestClaudeBudgetRatio:
    """Claude bots have reduced budget (0.5x)."""

    def test_claude_budget_ratio(self, token_budget):
        # Effective limit for Claude = 100_000 * 0.5 = 50_000
        token_budget.record("bot_a", 30_000, 20_000)  # total = 50_000
        allowed, reason = token_budget.check("bot_a", is_claude=True)
        assert allowed is False
        assert "预算" in reason

        # Same usage should still be allowed for non-Claude
        allowed_normal, _ = token_budget.check("bot_a", is_claude=False)
        assert allowed_normal is True


class TestDailyReset:
    """Budget resets on a new day."""

    def test_daily_reset(self, token_budget):
        token_budget.record("bot_a", 60_000, 40_000)  # exhaust budget
        allowed, _ = token_budget.check("bot_a")
        assert allowed is False

        # Simulate next day
        with patch.object(token_budget, "_today", return_value="2099-01-01"):
            allowed, reason = token_budget.check("bot_a")
            assert allowed is True
            assert reason == ""


class TestRecordAccumulates:
    """Multiple records accumulate."""

    def test_record_accumulates(self, token_budget):
        token_budget.record("bot_a", 10_000, 5_000)
        token_budget.record("bot_a", 20_000, 3_000)
        usage = token_budget._get_usage("bot_a")
        assert usage["input"] == 30_000
        assert usage["output"] == 8_000


class TestTokenGetStatus:
    """get_status returns correct fields."""

    def test_get_status(self, token_budget):
        token_budget.record("bot_a", 10_000, 5_000)
        status = token_budget.get_status("bot_a")
        assert status["input_tokens"] == 10_000
        assert status["output_tokens"] == 5_000
        assert status["total_tokens"] == 15_000
        assert status["daily_limit"] == 100_000
        assert status["remaining"] == 85_000

        status_claude = token_budget.get_status("bot_a", is_claude=True)
        assert status_claude["daily_limit"] == 50_000
        assert status_claude["remaining"] == 35_000


# ── QualityGate ───────────────────────────────────────────────────────

class TestEmptyResponseRejected:
    """Empty or too-short responses are rejected."""

    def test_empty_response_rejected(self, quality_gate):
        ok, reason = quality_gate.check_response("bot_a", "")
        assert ok is False
        assert "过短" in reason or "为空" in reason

        ok2, reason2 = quality_gate.check_response("bot_a", "x")
        assert ok2 is False


class TestNormalResponsePasses:
    """Normal response passes quality check."""

    def test_normal_response_passes(self, quality_gate):
        ok, reason = quality_gate.check_response("bot_a", "This is a perfectly fine response.")
        assert ok is True
        assert reason == ""


class TestExactDuplicateRejected:
    """Exact duplicate of a recent response is rejected."""

    def test_exact_duplicate_rejected(self, quality_gate):
        msg = "Hello, this is a test response."
        quality_gate.record_response("bot_a", msg)
        ok, reason = quality_gate.check_response("bot_a", msg)
        assert ok is False
        assert "完全重复" in reason


class TestHighSimilarityRejected:
    """Very similar response is rejected (above max_duplicate_ratio)."""

    def test_high_similarity_rejected(self, quality_gate):
        base = "This is a long enough response to trigger similarity detection!!"
        quality_gate.record_response("bot_a", base)
        # Change only a few characters at the end
        similar = base[:-2] + "??"
        ok, reason = quality_gate.check_response("bot_a", similar)
        assert ok is False
        assert "相似" in reason


class TestDifferentResponsePasses:
    """A completely different response passes after recording a previous one."""

    def test_different_response_passes(self, quality_gate):
        quality_gate.record_response("bot_a", "First response about topic A with enough length.")
        ok, reason = quality_gate.check_response(
            "bot_a", "Completely unrelated second response about topic B."
        )
        assert ok is True
        assert reason == ""


class TestHistoryLimited:
    """History is capped at max_history."""

    def test_history_limited(self, quality_gate):
        for i in range(30):
            quality_gate.record_response("bot_a", f"Unique response number {i}")
        assert len(quality_gate._recent_responses["bot_a"]) <= quality_gate._max_history
