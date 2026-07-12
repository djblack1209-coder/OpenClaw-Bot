"""可选 AI 依赖即使未来安装，也不能绕过成本与外部写操作安全边界。"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.browser_use_bridge import BrowserUseBridge
from src.core.brain_exec_life import LifeExecutorMixin


async def test_browser_use_rejects_external_write_intent_before_opening_browser(monkeypatch):
    bridge = BrowserUseBridge(llm=object(), headless=True)
    monkeypatch.setattr("src.browser_use_bridge._browser_use_available", True)
    monkeypatch.setattr(bridge, "_using_browser_use", True)
    browser = MagicMock()
    monkeypatch.setattr("src.browser_use_bridge.Browser", browser)

    result = await bridge.run_task("提交订单并完成付款", url="https://example.test")

    assert result["success"] is False
    assert result["blocked"] is True
    browser.assert_not_called()


async def test_browser_use_read_only_task_excludes_mutating_actions(monkeypatch):
    captured = {}

    class FakeTools:
        def __init__(self, *, exclude_actions):
            captured["exclude_actions"] = set(exclude_actions)

    class FakeBrowser:
        def __init__(self, *args, **kwargs):
            captured["browser_kwargs"] = kwargs

        async def close(self):
            captured["closed"] = True

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["agent_kwargs"] = kwargs
            self.task = kwargs["task"]

        async def run(self, *, max_steps):
            captured["max_steps"] = max_steps
            return "read-only result"

    bridge = BrowserUseBridge(llm=object(), headless=True)
    monkeypatch.setattr("src.browser_use_bridge._browser_use_available", True)
    monkeypatch.setattr("src.browser_use_bridge.BrowserTools", FakeTools)
    monkeypatch.setattr("src.browser_use_bridge.Browser", FakeBrowser)
    monkeypatch.setattr("src.browser_use_bridge.BrowserConfig", None)
    monkeypatch.setattr("src.browser_use_bridge.BrowserAgent", FakeAgent)
    monkeypatch.setattr(bridge, "_using_browser_use", True)

    result = await bridge.run_task("提取页面标题", url="https://example.test")

    assert result["success"] is True
    assert {"click", "input", "upload", "dropdown", "cookies", "write_file", "replace_file"} <= captured[
        "exclude_actions"
    ]
    assert captured["agent_kwargs"]["tools"].__class__ is FakeTools
    assert "只读" in captured["agent_kwargs"]["task"]
    assert captured["closed"] is True


async def test_browser_use_requires_explicit_llm_injection(monkeypatch):
    bridge = BrowserUseBridge(llm=None)
    monkeypatch.setattr("src.browser_use_bridge._browser_use_available", True)
    monkeypatch.setattr(bridge, "_using_browser_use", True)
    assert await bridge._ensure_llm() is None


async def test_fill_form_never_submits():
    bridge = BrowserUseBridge(llm=object())
    result = await bridge.fill_form("https://example.test", {"email": "owner@example.test"})
    assert result["success"] is False
    assert result["blocked"] is True
    assert result["requires_manual_action"] is True


async def test_booking_executor_only_prepares_manual_action():
    executor = LifeExecutorMixin()
    with patch("src.browser_use_bridge.get_browser_use", new_callable=MagicMock) as bridge:
        result = await executor._exec_booking_execute(
            {"goal": "预订酒店", "url": "https://example.test"}
        )
    bridge.assert_not_called()
    assert result["success"] is False
    assert result["requires_manual_confirmation"] is True


def test_crewai_dead_bridge_is_removed_from_active_source_tree():
    source_root = Path(__file__).resolve().parents[1] / "src"
    assert not (source_root / "crewai_bridge.py").exists()
    active_files = [
        source_root / "trading" / "_init_system.py",
        source_root / "modules" / "investment" / "team.py",
        source_root / "observability.py",
    ]
    for path in active_files:
        source = path.read_text(encoding="utf-8")
        assert "from crewai" not in source
        assert "openinference.instrumentation.crewai" not in source


def test_crawl4ai_does_not_use_direct_llm_keys_or_extraction():
    path = Path(__file__).resolve().parents[1] / "src" / "shopping" / "crawl4ai_engine.py"
    source = path.read_text(encoding="utf-8")
    assert "LlmExtractionStrategy" not in source
    assert "DEEPSEEK_API_KEY" not in source
    assert "OPENAI_API_KEY" not in source
