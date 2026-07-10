"""微信编号命令覆盖回归。"""

import json
from datetime import UTC, datetime

import pytest

from src.api.routers import wechat


def test_numbered_commands_do_not_fall_back_to_generic_llm_without_explanation():
    """每个编号命令要么接真实 API/安全本地处理，要么显式说明为什么不能执行。"""
    special = set(wechat._LOCAL_COMMAND_HANDLERS) | set(wechat._EXPLICIT_UNAVAILABLE_COMMANDS)
    uncovered = []
    for number, (_desc, _needs_arg, func_name) in wechat.NUMBERED_COMMANDS.items():
        if func_name not in wechat._CMD_API_MAP and number not in special:
            uncovered.append(number)

    assert uncovered == []


def test_social_publish_numbered_commands_are_review_only_or_blocked():
    """社媒编号命令不能绕过人工审核闸口直接外发。"""
    for number in (301, 302, 303):
        message = wechat._EXPLICIT_UNAVAILABLE_COMMANDS[number]
        assert "不会自动发布" in message
        assert "人工" in message


def test_wechat_incoming_available_on_api_and_legacy_paths(monkeypatch, tmp_path):
    """微信旧转发器和新内控 API 都应该能打到同一个每日简报处理器。"""
    from fastapi.testclient import TestClient

    from src.api import auth
    from src.api.server import APIServer

    monkeypatch.setattr(auth, "_API_TOKEN", "")
    monkeypatch.setattr(auth, "_warned_no_token", False)
    monkeypatch.setenv("INTEL_BRIEF_DB_PATH", str(tmp_path / "intel_brief.db"))

    client = TestClient(APIServer().app)
    for path in ("/api/v1/wechat/incoming", "/wechat/incoming"):
        response = client.post(path, json={"from_user": "wechat-route-test", "text": "700"})
        assert response.status_code == 200
        reply = response.json()["reply"]
        assert "今日简报" in reply
        assert "700 今日简报" in reply
        assert "具体的问题" not in reply


def test_wechat_intel_bridge_status_available_on_api_and_legacy_paths(monkeypatch, tmp_path):
    """微信真实桥接状态接口要给老板看得懂的红黄绿口径。"""
    from fastapi.testclient import TestClient

    from src.api import auth
    from src.api.server import APIServer

    monkeypatch.setattr(auth, "_API_TOKEN", "")
    monkeypatch.setattr(auth, "_warned_no_token", False)
    missing_evidence = tmp_path / "missing-runtime.json"
    monkeypatch.setenv("OPENCLAW_INTEL_BRIEF_WECHAT_EVIDENCE_FILE", str(missing_evidence))

    client = TestClient(APIServer().app)
    for path in ("/api/v1/wechat/intel-brief-bridge-status", "/wechat/intel-brief-bridge-status"):
        response = client.get(path)
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is False
        assert payload["state"] == "waiting_real_wechat_message"
        assert payload["severity"] == "warning"
        assert "今日简报" in payload["next_action"]
        assert payload["privacy"]["stores_raw_wechat_text"] is False


def test_wechat_intel_bridge_status_reports_verified(monkeypatch, tmp_path):
    """有近期真实桥接证据时，状态接口应变绿。"""
    from fastapi.testclient import TestClient

    from src.api import auth
    from src.api.server import APIServer

    evidence = tmp_path / "runtime.json"
    latest = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "source": "openclaw-weixin-intel-brief-bridge",
        "status": "handled",
        "reason": "sent_reply",
        "shortcut_class": "today",
        "sender_hash": "abcdef123456",
        "text_length": 4,
        "bridge_url": "http://127.0.0.1:18790/wechat/incoming",
        "api_token_present": True,
        "http_status": 200,
        "reply_present": True,
        "reply_length": 120,
        "reply_contains_menu": True,
        "reply_contains_status": False,
        "reply_contains_schedule_prompt": False,
        "reply_contains_tracking_prompt": False,
        "reply_fell_to_llm": False,
        "sent_reply_success": True,
    }
    evidence.write_text(json.dumps({"latest": latest, "recent_events": [latest]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_INTEL_BRIEF_WECHAT_EVIDENCE_FILE", str(evidence))
    monkeypatch.setattr(auth, "_API_TOKEN", "")
    monkeypatch.setattr(auth, "_warned_no_token", False)

    response = TestClient(APIServer().app).get("/api/v1/wechat/intel-brief-bridge-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["state"] == "verified"
    assert payload["severity"] == "ok"
    assert payload["latest"]["sender_hash_present"] is True
    assert "sender_hash" not in payload["latest"]


async def _fail_if_llm_called(*_args, **_kwargs):
    """测试保护：这些路径不允许落到普通大模型闲聊。"""
    raise AssertionError("微信每日简报快捷入口不应该调用 LLM")


@pytest.mark.asyncio
async def test_wechat_intel_brief_text_shortcuts_do_not_fall_back_to_llm(monkeypatch, tmp_path):
    """微信用户发中文快捷词时，也要进入每日简报，不要求记数字。"""
    monkeypatch.setenv("INTEL_BRIEF_DB_PATH", str(tmp_path / "wechat-text-shortcuts.db"))
    monkeypatch.setattr(wechat, "_generate_wechat_reply", _fail_if_llm_called)
    wechat._wechat_pending_actions.clear()

    today = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-shortcut-1", text="今日简报"))
    status = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-shortcut-1", text="我的订阅"))

    assert "今日简报" in today.reply
    assert "700 今日简报" in today.reply
    assert "订阅状态" in status.reply
    assert "推送时间" in status.reply


@pytest.mark.asyncio
async def test_wechat_pending_action_does_not_eat_menu_or_shortcuts(monkeypatch, tmp_path):
    """两步式设置过程中，用户回复菜单/今日简报时应跳转，不应被误当作参数。"""
    monkeypatch.setenv("INTEL_BRIEF_DB_PATH", str(tmp_path / "wechat-pending-menu.db"))
    monkeypatch.setattr(wechat, "_generate_wechat_reply", _fail_if_llm_called)
    wechat._wechat_pending_actions.clear()

    schedule_prompt = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-shortcut-2", text="705"))
    menu = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-shortcut-2", text="菜单"))
    custom_prompt = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-shortcut-2", text="706"))
    today = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-shortcut-2", text="今日简报"))

    assert "回复数字即可设置" in schedule_prompt.reply
    assert "发数字编号即可快速操作" in menu.reply
    assert "700 每日简报" in menu.reply
    assert "下一条直接回复名字" in custom_prompt.reply
    assert "今日简报" in today.reply
    assert "700 今日简报" in today.reply
