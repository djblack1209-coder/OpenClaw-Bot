"""测试 LiteLLM 路由池"""
import pytest
from src.litellm_router import (
    LiteLLMPool, FreeAPISource,
    TIER_S, TIER_A, TIER_B, TIER_C,
    get_model_score,
)


def _make_pool():
    """创建测试用池（不初始化 LiteLLM Router，仅测试兼容接口）"""
    pool = LiteLLMPool()
    pool.add_source("qwen", FreeAPISource(
        provider="groq", base_url="http://test", api_key="k",
        model="Qwen/Qwen3-235B-A22B", tier=TIER_S, daily_limit=100,
    ))
    pool.add_source("deepseek", FreeAPISource(
        provider="sambanova", base_url="http://test", api_key="k",
        model="deepseek-ai/DeepSeek-V3-0324", tier=TIER_S, daily_limit=50,
    ))
    pool.add_source("gemini", FreeAPISource(
        provider="google", base_url="http://test", api_key="k",
        model="gemini-2.5-flash", tier=TIER_S, daily_limit=200,
    ))
    pool.add_source("llama", FreeAPISource(
        provider="groq", base_url="http://test", api_key="k",
        model="llama-3.3-70b-versatile", tier=TIER_A, daily_limit=100,
    ))
    return pool


def test_get_best_source():
    pool = _make_pool()
    src = pool.get_best_source("qwen")
    assert src is not None
    assert src.provider == "groq"
    assert src.model == "Qwen/Qwen3-235B-A22B"


def test_get_any_source():
    pool = _make_pool()
    result = pool.get_any_source()
    assert result is not None
    family, src = result
    assert src is not None
    # 应该选最强的模型
    assert get_model_score(src.model) >= 83


def test_get_best_source_with_tier_filter():
    pool = _make_pool()
    # 只要 S 级
    src = pool.get_best_source("llama", min_tier=TIER_S)
    assert src is None  # llama 只有 A 级
    # A 级可以
    src = pool.get_best_source("llama", min_tier=TIER_A)
    assert src is not None


def test_record_success_and_error():
    """测试 FreeAPISource 的计数逻辑（原 pool.record_success/error 已清理，直接操作属性）"""
    pool = _make_pool()
    src = pool.get_best_source("qwen")
    assert src.consecutive_errors == 0
    assert src.used_today == 0

    # 模拟成功
    src.used_today += 1
    src.consecutive_errors = 0
    assert src.used_today == 1
    assert src.consecutive_errors == 0

    # 模拟失败
    src.consecutive_errors += 1
    assert src.consecutive_errors == 1

    # 成功后重置
    src.consecutive_errors = 0
    assert src.consecutive_errors == 0


def test_disabled_source_not_available():
    pool = _make_pool()
    src = pool.get_best_source("qwen")
    src.disabled = True
    src2 = pool.get_best_source("qwen")
    assert src2 is None  # 只有一个 qwen 源，禁用后无可用


def test_exhausted_source_not_available():
    pool = _make_pool()
    src = pool.get_best_source("deepseek")
    src.used_today = 50  # 达到 daily_limit
    src2 = pool.get_best_source("deepseek")
    assert src2 is None


def test_consecutive_errors_disable():
    """测试连续错误后 source 不可用"""
    pool = _make_pool()
    src = pool.get_best_source("qwen")
    src.consecutive_errors = 5
    assert src.consecutive_errors == 5
    assert not src.can_accept_request()
    src2 = pool.get_best_source("qwen")
    assert src2 is None


def test_reset_daily_counters():
    pool = _make_pool()
    src = pool.get_best_source("qwen")
    src.used_today = 100
    src.consecutive_errors = 5
    src.disabled = True
    pool.reset_daily_counters()
    assert src.used_today == 0
    assert src.consecutive_errors == 0
    assert not src.disabled


def test_get_stats():
    pool = _make_pool()
    stats = pool.get_stats()
    assert stats["total_sources"] == 4
    assert stats["active_sources"] == 4
    assert stats["engine"] == "litellm"
    assert "qwen" in stats["families"]
    assert "groq" in stats["by_provider"]


def test_model_score():
    assert get_model_score("gemini-2.5-flash") == 97
    assert get_model_score("unknown-model") == 50.0
    assert get_model_score("auto") == 65
