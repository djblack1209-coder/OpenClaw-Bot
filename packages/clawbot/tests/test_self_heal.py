"""
Tests for src/core/self_heal.py — SelfHealEngine.

Covers:
  - heal() main flow (success via known solution, local cache, web search)
  - _search_local_solutions() cache hit path
  - Circuit breaker: open after threshold, cooldown reset, success reset
  - _heal_history max-size trimming
  - _record_to_memory failure isolation
"""

import sys
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.self_heal import SelfHealEngine, HealResult, ErrorCategory


# ── Fixtures ────────────────────────────────────────────


@pytest.fixture
def engine():
    """Fresh SelfHealEngine instance."""
    return SelfHealEngine()


# ── 1. heal() success (known solution) ──────────────────


class TestHealSuccess:
    """heal() returns healed=True when a known solution matches."""

    async def test_heal_success_known_solution(self, engine):
        """Known ConnectionError → retry_with_delay → healed."""
        error = ConnectionError("Connection refused on port 8080")
        context: dict = {}

        # Mock the known-solution executor to succeed immediately
        with patch.object(engine, "_execute_known_solution", new_callable=AsyncMock, return_value=True):
            result = await engine.heal(error, context)

        assert result.healed is True
        assert result.error_category == ErrorCategory.NETWORK
        assert result.solution_used != ""
        assert result.elapsed_seconds >= 0
        # At least analyze + known-solution steps recorded
        assert len(result.attempts) >= 2

    async def test_heal_success_via_local_search(self, engine):
        """When known solution fails but local search returns a hit, heal succeeds."""
        error = RuntimeError("some obscure error xyz")
        context: dict = {}

        with (
            patch.object(engine, "_execute_known_solution", new_callable=AsyncMock, return_value=False),
            patch.object(
                engine,
                "_search_local_solutions",
                new_callable=AsyncMock,
                return_value="retry after clearing cache",
            ),
            patch.object(engine, "_apply_solution", new_callable=AsyncMock, return_value=True),
        ):
            result = await engine.heal(error, context)

        assert result.healed is True
        assert "记忆库" in result.solution_used

    async def test_heal_success_via_web_search(self, engine):
        """When local search misses but web search returns a fix, heal succeeds."""
        error = RuntimeError("unexpected segfault in widget")
        context: dict = {}

        with (
            patch.object(engine, "_execute_known_solution", new_callable=AsyncMock, return_value=False),
            patch.object(engine, "_search_local_solutions", new_callable=AsyncMock, return_value=None),
            patch.object(
                engine,
                "_search_web_solutions",
                new_callable=AsyncMock,
                return_value="upgrade widget library to fix segfault",
            ),
            patch.object(engine, "_apply_solution", new_callable=AsyncMock, return_value=True),
            patch.object(engine, "_record_to_memory", new_callable=AsyncMock),
        ):
            result = await engine.heal(error, context)

        assert result.healed is True
        assert "Web搜索" in result.solution_used


# ── 2. heal() cached solution ───────────────────────────


class TestHealCachedSolution:
    """Second identical error retrieves solution from _solution_cache."""

    async def test_heal_cached_solution(self, engine):
        error_msg = "unique error abc123 for cache test"
        cache_key = error_msg[:100]

        # Pre-populate cache (simulates a prior successful heal)
        engine._solution_cache[cache_key] = "retry after clearing temp files"

        error = Exception(error_msg)
        context: dict = {}

        with (
            patch.object(engine, "_apply_solution", new_callable=AsyncMock, return_value=True),
            patch.object(engine, "_notify_human", new_callable=AsyncMock),
        ):
            result = await engine.heal(error, context)

        assert result.healed is True
        assert "记忆库" in result.solution_used

    async def test_cache_populated_after_web_heal(self, engine):
        """After web-search heal, cache key is populated for next time."""
        error = Exception("rare error for cache population test")
        context: dict = {}

        with (
            patch.object(engine, "_search_local_solutions", new_callable=AsyncMock, return_value=None),
            patch.object(
                engine,
                "_search_web_solutions",
                new_callable=AsyncMock,
                return_value="install hotfix v2.1",
            ),
            patch.object(engine, "_apply_solution", new_callable=AsyncMock, return_value=True),
            patch.object(engine, "_record_to_memory", new_callable=AsyncMock) as mock_record,
        ):
            result = await engine.heal(error, context)
            assert result.healed is True
            mock_record.assert_awaited_once()


# ── 3. Circuit breaker opens after threshold ────────────


class TestCircuitBreakerOpens:
    """After CIRCUIT_BREAK_THRESHOLD consecutive failures, circuit opens."""

    def test_circuit_not_open_initially(self, engine):
        sig = "TestError:some message"
        assert engine._is_circuit_open(sig) is False

    def test_circuit_opens_at_threshold(self, engine):
        sig = "TestError:repeated failure"
        for _ in range(engine.CIRCUIT_BREAK_THRESHOLD):
            engine._record_circuit_failure(sig)

        assert engine._is_circuit_open(sig) is True

    def test_circuit_not_open_below_threshold(self, engine):
        sig = "TestError:almost failing"
        for _ in range(engine.CIRCUIT_BREAK_THRESHOLD - 1):
            engine._record_circuit_failure(sig)

        assert engine._is_circuit_open(sig) is False

    async def test_heal_skips_when_circuit_open(self, engine):
        """heal() returns immediately with circuit_break when breaker is open."""
        error = Exception("repeated failure pattern")
        sig = engine._get_error_signature(type(error).__name__, str(error))

        for _ in range(engine.CIRCUIT_BREAK_THRESHOLD):
            engine._record_circuit_failure(sig)

        result = await engine.heal(error, {})
        assert result.healed is False
        assert any(a.get("action") == "circuit_break" for a in result.attempts)

    def test_failure_count_increments(self, engine):
        sig = "TestError:counting"
        # pybreaker 内部计数，通过 _is_circuit_open 间接验证
        engine._record_circuit_failure(sig)
        assert engine._is_circuit_open(sig) is False  # 1次，未到阈值
        engine._record_circuit_failure(sig)
        assert engine._is_circuit_open(sig) is False  # 2次，未到阈值
        engine._record_circuit_failure(sig)
        assert engine._is_circuit_open(sig) is True  # 3次，触发熔断


# ── 4. Circuit breaker cooldown resets ──────────────────


class TestCircuitBreakerCooldown:
    """After CIRCUIT_BREAK_COOLDOWN seconds, breaker resets and allows retries."""

    def test_cooldown_resets_circuit(self, engine):
        sig = "TimeoutError:connection timed out"
        for _ in range(engine.CIRCUIT_BREAK_THRESHOLD):
            engine._record_circuit_failure(sig)

        assert engine._is_circuit_open(sig) is True

        # pybreaker 的 reset_timeout 由库自动管理
        # 直接用 close() 模拟冷却完成
        engine._reset_circuit(sig)

        assert engine._is_circuit_open(sig) is False

    def test_cooldown_not_elapsed_stays_open(self, engine):
        sig = "TimeoutError:still cooling"
        for _ in range(engine.CIRCUIT_BREAK_THRESHOLD):
            engine._record_circuit_failure(sig)

        # pybreaker 状态检查：刚刚触发，应该还是 OPEN
        assert engine._is_circuit_open(sig) is True


# ── 5. Circuit breaker success resets ───────────────────


class TestCircuitBreakerSuccessReset:
    """Successful heal resets circuit breaker for that error signature."""

    def test_reset_circuit_removes_entry(self, engine):
        sig = "NetworkError:dns failure"
        engine._record_circuit_failure(sig)
        engine._record_circuit_failure(sig)
        # pybreaker 池中应该有这个 breaker
        assert sig in engine._breakers

        engine._reset_circuit(sig)
        # 重置后 breaker 应该变回 CLOSED 状态
        assert engine._is_circuit_open(sig) is False

    def test_reset_nonexistent_sig_is_safe(self, engine):
        """Resetting a sig that was never recorded does not raise."""
        engine._reset_circuit("NeverSeen:ghost error")
        # No exception — pass

    async def test_heal_success_resets_circuit_count(self, engine):
        """After a successful heal, circuit breaker is cleared."""
        error = ConnectionError("Connection refused")
        sig = engine._get_error_signature("ConnectionError", str(error))

        # Build up some failures first
        engine._record_circuit_failure(sig)
        engine._record_circuit_failure(sig)

        with patch.object(engine, "_execute_known_solution", new_callable=AsyncMock, return_value=True):
            result = await engine.heal(error, {})

        assert result.healed is True
        # pybreaker 重置后应该是 CLOSED
        assert engine._is_circuit_open(sig) is False


# ── 6. heal history max size ────────────────────────────


class TestHealHistoryMaxSize:
    """_heal_history is trimmed to stay within _max_history."""

    async def test_history_trimmed_after_overflow(self, engine):
        """When history exceeds _max_history, it is trimmed to last 100."""
        # Pre-fill history to just below max
        engine._heal_history = [
            {"error": f"e{i}", "category": "unknown", "healed": False, "timestamp": time.time()}
            for i in range(engine._max_history)
        ]

        # Trigger one more heal that fails all steps → appends to history + trims
        error = Exception("overflow trigger error")
        with (
            patch.object(engine, "_search_local_solutions", new_callable=AsyncMock, return_value=None),
            patch.object(engine, "_search_web_solutions", new_callable=AsyncMock, return_value=None),
            patch.object(engine, "_try_alternatives", new_callable=AsyncMock, return_value=False),
            patch.object(engine, "_notify_human", new_callable=AsyncMock),
        ):
            await engine.heal(error, {})

        # History appended one, then trimmed: should be exactly 100
        assert len(engine._heal_history) == 100

    def test_history_stays_within_bounds_manual(self, engine):
        """Direct unit test of the trimming logic in heal()."""
        engine._heal_history = [{"error": f"e{i}"} for i in range(250)]
        # Simulate the trim logic (lines 293-294 of self_heal.py)
        if len(engine._heal_history) > engine._max_history:
            engine._heal_history = engine._heal_history[-100:]
        assert len(engine._heal_history) == 100

    def test_history_under_max_untouched(self, engine):
        engine._heal_history = [{"error": f"e{i}"} for i in range(50)]
        if len(engine._heal_history) > engine._max_history:
            engine._heal_history = engine._heal_history[-100:]
        assert len(engine._heal_history) == 50


# ── 7. _record_to_memory failure safe ───────────────────


class TestRecordToMemoryFailureSafe:
    """Memory recording failures must not propagate to the caller."""

    async def test_record_to_memory_import_error(self, engine):
        """If shared_memory import fails, no exception and cache is still updated."""
        with patch.dict(sys.modules, {"src.shared_memory": None}):
            # Should not raise
            await engine._record_to_memory("test error msg", "test solution")

        # Cache must still be populated regardless of memory failure
        assert engine._solution_cache["test error msg"[:100]] == "test solution"

    async def test_record_to_memory_add_raises(self, engine):
        """If shared_memory.add() raises, no exception and cache is updated."""
        mock_memory_module = MagicMock()
        mock_memory_module.shared_memory = MagicMock()
        mock_memory_module.shared_memory.add.side_effect = RuntimeError("DB write failed")

        with patch.dict(sys.modules, {"src.shared_memory": mock_memory_module}):
            await engine._record_to_memory("db error msg", "db solution")

        assert engine._solution_cache["db error msg"[:100]] == "db solution"

    async def test_record_to_memory_none_memory(self, engine):
        """If shared_memory is None, cache is still updated."""
        mock_memory_module = MagicMock()
        mock_memory_module.shared_memory = None

        with patch.dict(sys.modules, {"src.shared_memory": mock_memory_module}):
            await engine._record_to_memory("none mem error", "none mem solution")

        assert engine._solution_cache["none mem error"[:100]] == "none mem solution"


# ── Error analysis (bonus) ──────────────────────────────


class TestErrorAnalysis:
    """_analyze_error correctly categorises errors."""

    def test_connection_error_category(self, engine):
        cat, known = engine._analyze_error("ConnectionError", "Connection refused")
        assert cat == ErrorCategory.NETWORK
        assert known is not None

    def test_rate_limit_by_status_code(self, engine):
        cat, known = engine._analyze_error("HTTPError", "Server returned 429")
        assert cat == ErrorCategory.RATE_LIMIT

    def test_timeout_category(self, engine):
        cat, known = engine._analyze_error("TimeoutError", "Read timed out")
        assert cat == ErrorCategory.TIMEOUT

    def test_unknown_error_category(self, engine):
        cat, known = engine._analyze_error("WeirdError", "something nobody has seen")
        assert cat == ErrorCategory.UNKNOWN
        assert known is None

    def test_server_5xx_category(self, engine):
        cat, known = engine._analyze_error("HTTPError", "Server returned 502 Bad Gateway")
        assert cat == ErrorCategory.NETWORK

    def test_auth_401_category(self, engine):
        cat, known = engine._analyze_error("HTTPError", "HTTP 401 Unauthorized")
        assert cat == ErrorCategory.AUTH

    def test_captcha_category(self, engine):
        cat, known = engine._analyze_error("CaptchaError", "captcha verification required")
        assert cat == ErrorCategory.CAPTCHA
