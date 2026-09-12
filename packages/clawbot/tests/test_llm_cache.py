"""Cache compatibility must preserve billing-relevant request parameters."""

from unittest.mock import AsyncMock

import pytest

from src.llm_cache import _make_cache_key, cached_completion


@pytest.mark.asyncio
@pytest.mark.parametrize("options", [{"no_cache": True}, {"cache_ttl": 0}, {"stream": True}])
async def test_compatibility_entry_preserves_cache_controls(monkeypatch, options):
    from src.litellm_router import free_pool

    send = AsyncMock(return_value=object())
    monkeypatch.setattr(free_pool, "acompletion", send)
    await cached_completion(model_family="fixture", messages=[], **options)
    assert all(send.call_args.kwargs[key] == value for key, value in options.items())


def test_cache_identity_includes_output_limit_and_tool_call_content():
    base = [{"role": "user", "content": "hello"}]
    short = _make_cache_key(base, "fixture", 0.1, max_tokens=10)
    assert short != _make_cache_key(base, "fixture", 0.1, max_tokens=20)
    assert short != _make_cache_key(base, "fixture", 0.1, max_tokens=10, response_format={"type": "json_object"})
    first = [{"role": "tool", "content": "result", "tool_call_id": "first"}]
    second = [{"role": "tool", "content": "result", "tool_call_id": "second"}]
    assert _make_cache_key(first, "fixture", 0) != _make_cache_key(second, "fixture", 0)
