from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from pydantic import BaseModel

import src.litellm_router as litellm_router
import src.structured_llm as structured_llm


class StructuredResult(BaseModel):
    answer: str


async def test_instructor_uses_router_owned_by_current_event_loop(monkeypatch):
    """Instructor 不得绕过 LiteLLMPool 的逐事件循环 Router 边界。"""
    template_router = MagicMock(name="template_router")
    current_router = MagicMock(name="current_router")
    pool = SimpleNamespace(
        _router=template_router,
        router_for_current_loop=MagicMock(return_value=current_router),
    )
    expected = StructuredResult(answer="ok")
    instructor_path = AsyncMock(return_value=expected)
    monkeypatch.setattr(litellm_router, "free_pool", pool)
    monkeypatch.setattr(structured_llm, "HAS_INSTRUCTOR", True)
    monkeypatch.setattr(structured_llm, "_instructor_path", instructor_path)

    result = await structured_llm.structured_completion(
        response_model=StructuredResult,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert result is expected
    pool.router_for_current_loop.assert_called_once_with()
    assert instructor_path.await_args.kwargs["router"] is current_router
