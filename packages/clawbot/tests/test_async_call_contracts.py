"""异步调用契约回归测试。"""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.brain_exec_social import SocialExecutorMixin
from src.core.proactive_engine import GateResult, ProactiveEngine
from src.tool_executor import ToolExecutor


@pytest.mark.asyncio
async def test_proactive_engine_uses_structured_completion_public_contract(monkeypatch):
    captured: dict = {}
    expected = object()

    async def structured_completion(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setitem(
        sys.modules,
        "src.structured_llm",
        SimpleNamespace(structured_completion=structured_completion),
    )

    result = await ProactiveEngine()._llm_structured("需要提醒", GateResult, cheap=True)

    assert result is expected
    assert captured["response_model"] is GateResult
    assert captured["messages"] == [{"role": "user", "content": "需要提醒"}]
    assert "model_class" not in captured
    assert "user_prompt" not in captured


@pytest.mark.asyncio
async def test_social_intel_awaits_media_crawler_methods(monkeypatch):
    from src.execution.social import media_crawler_bridge

    crawler = SimpleNamespace(
        get_trending=AsyncMock(return_value=[{"title": "热点"}]),
        search_platform=AsyncMock(return_value=[{"title": "相关内容"}]),
    )
    monkeypatch.setattr(media_crawler_bridge, "get_media_crawler", lambda: crawler)

    result = await SocialExecutorMixin()._exec_social_intel({"platform": "xhs", "topic": "AI"})

    assert result["trending"] == [{"title": "热点"}]
    assert result["related_posts"] == [{"title": "相关内容"}]
    crawler.get_trending.assert_awaited_once_with("xhs")
    crawler.search_platform.assert_awaited_once_with("xhs", ["AI"], limit=5)


@pytest.mark.asyncio
async def test_tool_positions_awaits_ibkr_query(monkeypatch):
    from src import broker_bridge, invest_tools

    fake_ibkr = SimpleNamespace(
        is_connected=lambda: True,
        get_positions=AsyncMock(
            return_value=[
                {
                    "symbol": "AAPL",
                    "quantity": 2,
                    "avg_cost": 100.0,
                    "market_price": 110.0,
                    "unrealized_pnl": 20.0,
                }
            ]
        ),
        budget=1000.0,
        total_spent=200.0,
    )
    fake_portfolio = SimpleNamespace(get_portfolio_summary=AsyncMock(return_value="模拟组合正常"))
    monkeypatch.setattr(broker_bridge, "ibkr", fake_ibkr)
    monkeypatch.setattr(invest_tools, "portfolio", fake_portfolio)

    result = await object.__new__(ToolExecutor)._tool_get_positions({})

    assert result["success"] is True
    assert "AAPL" in result["content"]
    fake_ibkr.get_positions.assert_awaited_once_with()
