"""通用执行器的外部写操作必须由当前调用显式确认。"""

import ast
import builtins
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.executor import MultiPathExecutor
from src.integrations.composio_bridge import ComposioBridge
from src.integrations.skyvern_bridge import SkyvernBridge


async def test_strategy_cannot_self_report_human_confirmation():
    """模型或策略字典里的确认字段不能替代可信调用方参数。"""
    async with MultiPathExecutor() as executor:
        executor.execute_via_voice_call = AsyncMock(return_value={"status": "initiated"})

        result = await executor.execute_with_fallback(
            [
                {
                    "type": "voice_call",
                    "phone": "+15550000000",
                    "objective": "测试",
                    "human_confirmed": True,
                }
            ]
        )

    assert result.success is False
    assert result.attempts[0]["blocked"] is True
    executor.execute_via_voice_call.assert_not_awaited()


async def test_top_level_confirmation_is_forwarded_to_api_write_path():
    """只有顶层可信参数可以放行单次外部写操作。"""
    async with MultiPathExecutor() as executor:
        executor.execute_via_api = AsyncMock(return_value={"ok": True})

        result = await executor.execute_with_fallback(
            [
                {
                    "type": "api",
                    "endpoint": "https://api.example.test/items",
                    "method": "POST",
                    "params": {"name": "test"},
                }
            ],
            human_confirmed=True,
        )

    assert result.success is True
    executor.execute_via_api.assert_awaited_once_with(
        "https://api.example.test/items",
        "POST",
        {"name": "test"},
        {},
        human_confirmed=True,
    )


async def test_direct_api_write_is_blocked_before_http_client(monkeypatch):
    executor = MultiPathExecutor()
    get_client = MagicMock()
    monkeypatch.setattr(executor, "_get_http_client", get_client)
    monkeypatch.setattr("src.core.security.check_ssrf", lambda _url: True)

    with pytest.raises(PermissionError, match="人工确认"):
        await executor.execute_via_api(
            "https://api.example.test/items",
            "POST",
            {"name": "test"},
        )

    get_client.assert_not_called()
    await executor.close()


async def test_browser_click_is_blocked_before_browser_launch(monkeypatch):
    executor = MultiPathExecutor()
    monkeypatch.setattr("src.core.security.check_ssrf", lambda _url: True)

    with patch(
        "playwright.async_api.async_playwright",
        side_effect=AssertionError("不应打开浏览器"),
    ):
        with pytest.raises(PermissionError, match="人工确认"):
            await executor.execute_via_browser(
                "https://example.test",
                [{"type": "click", "selector": "button"}],
            )

    await executor.close()


async def test_voice_call_is_blocked_before_provider_import(monkeypatch):
    executor = MultiPathExecutor()
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"retell", "twilio.rest"}:
            raise AssertionError("不应加载电话供应商")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(PermissionError, match="人工确认"):
        await executor.execute_via_voice_call("+15550000000", "测试")

    await executor.close()


def test_composio_bridge_blocks_action_before_sdk_availability_check():
    bridge = ComposioBridge(api_key="")

    result = bridge.execute_action("GMAIL_SEND_EMAIL", {"to": "owner@example.test"})

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["requires_human_confirmation"] is True


async def test_skyvern_bridge_blocks_general_task_and_form_by_default():
    bridge = SkyvernBridge(api_key="")

    task_result = await bridge.run_task(
        "https://example.test",
        "点击按钮并提交表单",
    )
    form_result = await bridge.fill_form(
        "https://example.test",
        {"email": "owner@example.test"},
    )

    for result in (task_result, form_result):
        assert result["success"] is False
        assert result["blocked"] is True
        assert result["requires_human_confirmation"] is True


def test_guarded_executor_calls_never_hardcode_confirmation_true():
    """生产代码只能透传可信确认值，不能在内部写死 True。"""
    source_root = Path(__file__).resolve().parents[1] / "src"
    guarded_calls = {
        "execute_with_fallback",
        "execute_via_api",
        "execute_via_browser",
        "execute_via_voice_call",
        "execute_via_composio",
        "execute_via_skyvern",
    }
    violations = []

    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if func_name not in guarded_calls:
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "human_confirmed"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    violations.append(f"{path.relative_to(source_root)}:{node.lineno}")

    assert violations == []


def test_executor_does_not_trust_confirmation_from_strategy_dict():
    path = Path(__file__).resolve().parents[1] / "src" / "core" / "executor.py"
    source = path.read_text(encoding="utf-8")
    assert 'strategy.get("human_confirmed"' not in source
    assert "strategy.get('human_confirmed'" not in source
