"""微信 iLink 桥接的失效提示回归测试。"""

import json
import logging
from unittest.mock import AsyncMock

import pytest

from src import wechat_bridge


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class _FakeHttp:
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = list(responses)
        self.calls = 0

    async def post(self, *_args, **_kwargs):
        self.calls += 1
        return self.responses.pop(0)


class _RecordingFakeHttp(_FakeHttp):
    def __init__(self, responses: list[_FakeResponse]):
        super().__init__(responses)
        self.request_bodies: list[bytes] = []

    async def post(self, *_args, **kwargs):
        self.request_bodies.append(kwargs.get("content", b""))
        return await super().post(*_args, **kwargs)


@pytest.mark.asyncio
async def test_ilink_expired_bot_token_logs_clear_rescan_instruction_once(monkeypatch, caplog):
    """iLink errcode=-14 时明确提示重新扫码，且同一轮只告警一次。"""
    monkeypatch.setattr(wechat_bridge, "_WECHAT_ENABLED", True)
    monkeypatch.setattr(
        wechat_bridge,
        "_http",
        _FakeHttp(
            [
                _FakeResponse(200, {"errcode": -14, "errmsg": "token expired"}),
                _FakeResponse(200, {"errcode": -14, "errmsg": "token expired"}),
                _FakeResponse(200, {"errcode": -14, "errmsg": "token expired"}),
                _FakeResponse(200, {"errcode": -14, "errmsg": "token expired"}),
            ]
        ),
    )
    wechat_bridge._creds._token = "unit-test-token"
    wechat_bridge._creds._user_id = "unit-test-user"
    wechat_bridge._creds._warned = False
    wechat_bridge._creds._token_expired_warned = False
    wechat_bridge._creds.clear_context()

    with caplog.at_level(logging.WARNING, logger="src.wechat_bridge"):
        first = await wechat_bridge.send_to_wechat("测试消息")
        second = await wechat_bridge.send_to_wechat("测试消息")

    assert first is False
    assert second is False
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "iLink bot token 已失效" in messages
    assert "openclaw channels login --channel openclaw-weixin" in messages
    assert messages.count("iLink bot token 已失效") == 1


@pytest.mark.asyncio
async def test_success_log_does_not_expose_wechat_user_id(monkeypatch, caplog):
    """发送成功日志只能记录脱敏标识，不能输出微信用户 ID。"""
    sensitive_user_id = "wx-sensitive-user-id-123456789"
    monkeypatch.setattr(wechat_bridge, "_WECHAT_ENABLED", True)
    monkeypatch.setattr(
        wechat_bridge,
        "_http",
        _FakeHttp([_FakeResponse(200, {"errcode": 0})]),
    )
    monkeypatch.setattr(
        wechat_bridge,
        "_get_context_token",
        AsyncMock(return_value="unit-test-context"),
    )
    wechat_bridge._creds._token = "unit-test-token"
    wechat_bridge._creds._user_id = sensitive_user_id
    wechat_bridge._creds._warned = False
    wechat_bridge._creds._token_expired_warned = False
    wechat_bridge._creds.clear_context()

    with caplog.at_level(logging.DEBUG, logger="src.wechat_bridge"):
        sent = await wechat_bridge.send_to_wechat("测试消息")

    assert sent is True
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert sensitive_user_id not in messages
    assert "target_hash=" in messages


@pytest.mark.asyncio
async def test_send_retry_rebuilds_body_with_refreshed_context_token(monkeypatch):
    """401/403 刷新 contextToken 后，第二次请求必须使用新请求体。"""
    fake_http = _RecordingFakeHttp(
        [
            _FakeResponse(401, {"errcode": 401}),
            _FakeResponse(200, {"errcode": 0}),
        ]
    )
    context_tokens = AsyncMock(side_effect=["context-old", "context-new"])
    monkeypatch.setattr(wechat_bridge, "_WECHAT_ENABLED", True)
    monkeypatch.setattr(wechat_bridge, "_http", fake_http)
    monkeypatch.setattr(wechat_bridge, "_get_context_token", context_tokens)
    wechat_bridge._creds._token = "unit-test-token"
    wechat_bridge._creds._user_id = "unit-test-user"
    wechat_bridge._creds._warned = False
    wechat_bridge._creds._token_expired_warned = False
    wechat_bridge._creds.clear_context()

    sent = await wechat_bridge.send_to_wechat("测试消息")

    assert sent is True
    assert context_tokens.await_count == 2
    first = json.loads(fake_http.request_bodies[0])
    second = json.loads(fake_http.request_bodies[1])
    assert first["msg"]["context_token"] == "context-old"
    assert second["msg"]["context_token"] == "context-new"
