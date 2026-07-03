"""微信 iLink 桥接的失效提示回归测试。"""

import logging

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
