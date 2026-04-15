"""
Tests for LiteLLM Router — ALL LLM calls flow through this module.

Covers: FreeAPISource, _scrub_secrets, get_model_score, LiteLLMPool core methods.
"""
import asyncio
import time

import pytest
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

from src.litellm_router import (
    FreeAPISource,
    LiteLLMPool,
    _scrub_secrets,
    get_model_score,
    MODEL_RANKING,
    TIER_S,
    TIER_A,
    TIER_B,
    TIER_C,
)


# ============ Fixtures ============

@pytest.fixture
def pool():
    """LiteLLMPool with no env keys — empty sources, no real Router."""
    with patch.dict("os.environ", {}, clear=True):
        p = LiteLLMPool()
    return p


@pytest.fixture
def pool_with_sources(pool):
    """Pool pre-loaded with a few fake sources for testing."""
    pool._reg("qwen", FreeAPISource(
        provider="test_qwen", base_url="http://fake", api_key="sk-fake",
        model="Qwen/Qwen3-235B-A22B", tier=TIER_S,
    ))
    pool._reg("deepseek", FreeAPISource(
        provider="test_ds", base_url="http://fake", api_key="sk-fake",
        model="deepseek-v3", tier=TIER_A,
    ))
    pool._reg("llama", FreeAPISource(
        provider="test_llama", base_url="http://fake", api_key="sk-fake",
        model="llama-3.3-70b-versatile", tier=TIER_B,
    ))
    pool._reg("g4f", FreeAPISource(
        provider="g4f", base_url="http://127.0.0.1:18891/v1", api_key="dummy",
        model="auto", tier=TIER_A,
    ))
    return pool


# ============ FreeAPISource.can_accept_request ============

class TestCanAcceptRequest:
    """Tests for FreeAPISource.can_accept_request()."""

    def test_enabled_source_accepts(self):
        src = FreeAPISource(provider="test", base_url="", api_key="k",
                            model="m", disabled=False, consecutive_errors=0)
        assert src.can_accept_request() is True

    def test_disabled_source_rejects(self):
        src = FreeAPISource(provider="test", base_url="", api_key="k",
                            model="m", disabled=True)
        assert src.can_accept_request() is False

    def test_too_many_errors_rejects(self):
        src = FreeAPISource(provider="test", base_url="", api_key="k",
                            model="m", consecutive_errors=5)
        assert src.can_accept_request() is False

    def test_daily_limit_exhausted_rejects(self):
        src = FreeAPISource(provider="test", base_url="", api_key="k",
                            model="m", daily_limit=10, used_today=10)
        assert src.can_accept_request() is False

    def test_daily_limit_not_reached_accepts(self):
        src = FreeAPISource(provider="test", base_url="", api_key="k",
                            model="m", daily_limit=10, used_today=5)
        assert src.can_accept_request() is True


# ============ get_model_score ============

class TestGetModelScore:

    def test_known_model_returns_correct_score(self):
        assert get_model_score("gemini-2.5-pro") == 98

    def test_another_known_model(self):
        assert get_model_score("deepseek-r1") == 93

    def test_unknown_model_returns_default_50(self):
        assert get_model_score("totally-unknown-model-xyz") == 50.0


# ============ _scrub_secrets ============

class TestScrubSecrets:

    def test_removes_api_key_sk_prefix(self):
        msg = "Error calling sk-abcdef1234567890 at endpoint"
        cleaned = _scrub_secrets(msg)
        assert "abcdef1234567890" not in cleaned
        assert "REDACTED" in cleaned

    def test_removes_bearer_token(self):
        msg = "Auth failed: Bearer eyJhbGciOiJSUzI1Ni"
        cleaned = _scrub_secrets(msg)
        assert "eyJhbGciOiJSUzI1Ni" not in cleaned
        assert "REDACTED" in cleaned

    def test_removes_localhost_urls(self):
        msg = "Connection refused http://localhost:18891/v1/chat/completions"
        cleaned = _scrub_secrets(msg)
        assert "localhost:18891" not in cleaned
        assert "[internal]" in cleaned

    def test_removes_127_urls(self):
        msg = "Timeout http://127.0.0.1:8080/api"
        cleaned = _scrub_secrets(msg)
        assert "127.0.0.1:8080" not in cleaned
        assert "[internal]" in cleaned

    def test_removes_query_param_keys(self):
        msg = "Request to url?api_key=sk12345678abcd&other=1"
        cleaned = _scrub_secrets(msg)
        assert "sk12345678abcd" not in cleaned

    def test_empty_string(self):
        assert _scrub_secrets("") == ""

    def test_no_secrets_unchanged(self):
        msg = "Simple error: model not found"
        assert _scrub_secrets(msg) == msg


# ============ LiteLLMPool.acompletion ============

class TestAcompletion:

    async def test_raises_when_not_initialized(self, pool):
        """acompletion raises RuntimeError when _router is None."""
        with pytest.raises(RuntimeError, match="未初始化"):
            await pool.acompletion("qwen", [{"role": "user", "content": "hi"}])

    async def test_calls_router_with_correct_params(self, pool_with_sources):
        """acompletion delegates to _router.acompletion with right model/messages."""
        mock_router = AsyncMock()
        mock_response = MagicMock()
        mock_response.usage = None
        mock_router.acompletion.return_value = mock_response
        pool_with_sources._router = mock_router

        messages = [{"role": "user", "content": "hello"}]
        result = await pool_with_sources.acompletion(
            "qwen", messages, system_prompt="You are helpful", temperature=0.5
        )

        assert result is mock_response
        call_args = mock_router.acompletion.call_args
        assert call_args.kwargs["model"] == "qwen"
        # system prompt prepended
        sent_msgs = call_args.kwargs["messages"]
        assert sent_msgs[0]["role"] == "system"
        assert sent_msgs[0]["content"] == "You are helpful"

    async def test_handles_timeout_gracefully(self, pool_with_sources):
        """acompletion increments error count on timeout."""
        mock_router = AsyncMock()
        mock_router.acompletion.side_effect = asyncio.TimeoutError()
        pool_with_sources._router = mock_router

        with pytest.raises(asyncio.TimeoutError):
            await pool_with_sources.acompletion("qwen", [{"role": "user", "content": "hi"}])

        assert pool_with_sources._error_count == 1

    async def test_handles_api_error_gracefully(self, pool_with_sources):
        """acompletion increments error count on generic exception."""
        mock_router = AsyncMock()
        mock_router.acompletion.side_effect = Exception("API rate limited")
        pool_with_sources._router = mock_router

        with pytest.raises(Exception, match="API rate limited"):
            await pool_with_sources.acompletion("qwen", [{"role": "user", "content": "hi"}])

        assert pool_with_sources._error_count == 1

    async def test_cost_tracking_increments(self, pool_with_sources):
        """Successful completion increments call count and token stats."""
        mock_router = AsyncMock()
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_router.acompletion.return_value = mock_response
        pool_with_sources._router = mock_router

        with patch("src.litellm_router.litellm") as mock_litellm:
            mock_litellm.completion_cost.return_value = 0.001
            await pool_with_sources.acompletion("qwen", [{"role": "user", "content": "hi"}])

        assert pool_with_sources._call_count == 1
        assert pool_with_sources._total_input_tokens == 100
        assert pool_with_sources._total_output_tokens == 50
        assert pool_with_sources._total_cost == pytest.approx(0.001)


# ============ LiteLLMPool.get_stats ============

class TestGetStats:

    def test_returns_correct_structure(self, pool_with_sources):
        stats = pool_with_sources.get_stats()
        assert "total_sources" in stats
        assert "active_sources" in stats
        assert "model_families" in stats
        assert "engine" in stats
        assert stats["engine"] == "litellm"
        assert stats["total_sources"] == 4  # 4 sources registered
        assert stats["model_families"] == 4  # qwen, deepseek, llama, g4f

    def test_stats_reflect_disabled_sources(self, pool_with_sources):
        # Disable one source
        pool_with_sources._sources["qwen"][0].disabled = True
        stats = pool_with_sources.get_stats()
        assert stats["active_sources"] == 3


# ============ _pick_strongest_family ============

class TestPickStrongestFamily:

    def test_selects_highest_scored_model(self, pool_with_sources):
        """Should pick the family containing the highest-scored available model."""
        best = pool_with_sources._pick_strongest_family()
        # Qwen3-235B-A22B has score 92, deepseek-v3 has 88, llama-3.3-70b has 83
        assert best == "qwen"

    def test_skips_disabled_sources(self, pool_with_sources):
        """If top family is disabled, pick next best."""
        pool_with_sources._sources["qwen"][0].disabled = True
        best = pool_with_sources._pick_strongest_family()
        assert best == "deepseek"

    def test_all_disabled_falls_back_to_g4f(self):
        """If all sources disabled, should return 'g4f' as default."""
        pool = LiteLLMPool()
        pool._reg("qwen", FreeAPISource(
            provider="t", base_url="", api_key="k", model="qwen3",
            disabled=True,
        ))
        best = pool._pick_strongest_family()
        assert best == "g4f"


# ============ health_check ============

class TestHealthCheck:

    async def test_marks_failed_source_as_disabled(self):
        """health_check disables sources whose provider fails the ping."""
        pool = LiteLLMPool()
        pool._reg("test_fam", FreeAPISource(
            provider="failing_prov", base_url="http://fake", api_key="k",
            model="some-model", tier=TIER_B,
        ))
        mock_router = AsyncMock()
        mock_router.acompletion.side_effect = Exception("Connection refused")
        pool._router = mock_router

        result = await pool.health_check(timeout=1.0)

        assert result["checked"] >= 1
        assert len(result["disabled"]) >= 1
        # The source should now be disabled
        assert pool._sources["test_fam"][0].disabled is True


# ============ validate_keys ============

class TestValidateKeys:

    async def test_disables_auth_error_keys(self):
        """validate_keys disables sources that return 401/403 auth errors."""
        pool = LiteLLMPool()
        src = FreeAPISource(
            provider="bad_key_prov", base_url="http://fake", api_key="bad-key",
            model="some-model", tier=TIER_B,
        )
        pool._reg("test_fam", src)

        # Mock _test_single_key to return auth_error
        with patch.object(pool, "_test_single_key", new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {"status": "auth_error", "error": "401 Unauthorized"}
            result = await pool.validate_keys(timeout=1.0)

        assert src.disabled is True
        assert result["unhealthy"] >= 1


# ============ _build_all_deployments ==========

class TestBuildAllDeployments:

    def test_uses_current_gemini_models_and_enables_cerebras(self):
        """Gemini 应切到 2.5 系，Cerebras key 存在时应真正注册 deployment。"""
        with patch.dict("os.environ", {
            "GEMINI_API_KEY": "AIza-test-key",
            "CEREBRAS_API_KEY": "csk-test-key",
        }, clear=True):
            pool = LiteLLMPool()
            deps = pool._build_all_deployments()

        models = [dep["litellm_params"]["model"] for dep in deps]

        assert "gemini/gemini-2.5-flash" in models
        assert "gemini/gemini-2.5-flash-lite" in models
        assert "gemini/gemini-2.0-flash" not in models
        assert any(model.startswith("cerebras/") for model in models)


class TestClaudeDirectApiGuard:

    def test_scrub_secrets_masks_gemini_key_prefix(self):
        """Google AI Studio key 也应被脱敏，避免日志直接打出真实 key。"""
        msg = "Gemini failed with key AIzaSyABCDEFGHIJKLMN1234567890"
        cleaned = _scrub_secrets(msg)
        assert "ABCDEFGHIJKLMN1234567890" not in cleaned
        assert "REDACTED" in cleaned
