"""Claude 工具循环对外部网页内容的权限隔离测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.bot import api_mixin
from src.bot.api_mixin import APIMixin


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHTTPClient:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.requests = []

    async def post(self, _url, **kwargs):
        self.requests.append(kwargs["json"])
        return _FakeResponse(next(self._responses))


def _tool_response(*tools):
    return {
        "content": [
            {"type": "tool_use", "id": f"tool-{index}", "name": name, "input": payload}
            for index, (name, payload) in enumerate(tools)
        ],
        "stop_reason": "tool_use",
    }


def _text_response(text="完成"):
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


def _mixin_with_client(client):
    return SimpleNamespace(
        model="claude-test",
        system_prompt="",
        name="测试机器人",
        http_client=client,
    )


@pytest.mark.asyncio
async def test_external_result_disables_tools_for_followup(monkeypatch):
    client = _FakeHTTPClient(
        [
            _tool_response(("fetch_url", {"url": "https://example.com"})),
            _text_response(),
        ]
    )
    execute = AsyncMock(return_value={"success": True, "content": "网页中的不可信内容"})
    monkeypatch.setattr(api_mixin, "CLAUDE_KEY", "test-key")
    monkeypatch.setattr(api_mixin, "CLAUDE_BASE", "https://example.test")
    monkeypatch.setattr(api_mixin.tool_executor, "execute", execute)

    result = await APIMixin._call_claude_api(
        _mixin_with_client(client),
        [{"role": "user", "content": "读取网页并总结"}],
    )

    assert result == "完成"
    assert "tools" in client.requests[0]
    assert "tools" not in client.requests[1]


@pytest.mark.asyncio
async def test_external_and_local_tools_cannot_run_in_same_batch(monkeypatch):
    client = _FakeHTTPClient(
        [
            _tool_response(
                ("fetch_url", {"url": "https://example.com"}),
                ("read_file", {"path": "config/.env"}),
            ),
            _text_response(),
        ]
    )
    execute = AsyncMock(return_value={"success": True, "content": "外部内容"})
    monkeypatch.setattr(api_mixin, "CLAUDE_KEY", "test-key")
    monkeypatch.setattr(api_mixin, "CLAUDE_BASE", "https://example.test")
    monkeypatch.setattr(api_mixin.tool_executor, "execute", execute)

    await APIMixin._call_claude_api(
        _mixin_with_client(client),
        [{"role": "user", "content": "读取网页"}],
    )

    execute.assert_awaited_once_with("fetch_url", {"url": "https://example.com"})


@pytest.mark.asyncio
async def test_use_tools_false_never_executes_returned_tool_use(monkeypatch):
    client = _FakeHTTPClient([_tool_response(("read_file", {"path": "config/.env"}))])
    execute = AsyncMock(return_value={"success": True, "content": "secret"})
    monkeypatch.setattr(api_mixin, "CLAUDE_KEY", "test-key")
    monkeypatch.setattr(api_mixin, "CLAUDE_BASE", "https://example.test")
    monkeypatch.setattr(api_mixin.tool_executor, "execute", execute)

    await APIMixin._call_claude_api(
        _mixin_with_client(client),
        [{"role": "user", "content": "不要使用工具"}],
        use_tools=False,
    )

    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_automatic_schema_excludes_mutating_tools(monkeypatch):
    client = _FakeHTTPClient([_text_response()])
    monkeypatch.setattr(api_mixin, "CLAUDE_KEY", "test-key")
    monkeypatch.setattr(api_mixin, "CLAUDE_BASE", "https://example.test")

    await APIMixin._call_claude_api(
        _mixin_with_client(client),
        [{"role": "user", "content": "只读分析"}],
    )

    offered = {schema["name"] for schema in client.requests[0]["tools"]}
    assert offered.isdisjoint(
        {
            "bash",
            "read_file",
            "write_file",
            "edit_file",
            "list_dir",
            "search_files",
            "run_python",
            "run_shell",
            "remember",
        }
    )
