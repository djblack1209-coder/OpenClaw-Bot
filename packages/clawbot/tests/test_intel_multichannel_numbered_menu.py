from __future__ import annotations

import pytest

NOW = "2026-07-08T17:00:00+00:00"


def test_multichannel_menu_has_click_and_number_variants():
    from src.intel.channel_menu import build_intel_channel_menu

    telegram = build_intel_channel_menu(channel="telegram", subscription_status="active")
    wechat = build_intel_channel_menu(channel="wechat", subscription_status="inactive_or_expired")
    feishu = build_intel_channel_menu(channel="feishu", subscription_status="inactive_or_expired")
    dingtalk = build_intel_channel_menu(channel="dingtalk", subscription_status="inactive_or_expired")

    assert telegram["supports_click_menu"] is True
    assert telegram["inline_keyboard"][0][0] == {"text": "🧭 今日简报", "callback_data": "today"}
    assert telegram["numbered_commands"][0]["number"] == 700
    assert "700 今日简报" in telegram["text"]

    for menu in (wechat, feishu, dingtalk):
        assert menu["supports_click_menu"] is False
        assert menu["inline_keyboard"] == []
        assert "回复数字即可操作" in menu["text"]
        assert "700 今日简报" in menu["text"]
        assert "706 添加追踪" in menu["text"]


def test_numbered_intel_command_router_updates_preferences(tmp_path):
    from src.intel.channel_menu import handle_numbered_intel_command

    db_path = tmp_path / "intel-numbered.db"
    start = handle_numbered_intel_command(db_path, channel="wechat", external_user_id="wx-user", number=700, arg="", now=NOW)
    stock = handle_numbered_intel_command(db_path, channel="wechat", external_user_id="wx-user", number=702, arg="", now=NOW)
    tech = handle_numbered_intel_command(db_path, channel="wechat", external_user_id="wx-user", number=703, arg="", now=NOW)
    schedule = handle_numbered_intel_command(db_path, channel="wechat", external_user_id="wx-user", number=705, arg="", now=NOW)
    custom_prompt = handle_numbered_intel_command(db_path, channel="wechat", external_user_id="wx-user", number=706, arg="", now=NOW)
    custom = handle_numbered_intel_command(db_path, channel="wechat", external_user_id="wx-user", number=706, arg="英伟达", now=NOW)
    status = handle_numbered_intel_command(db_path, channel="wechat", external_user_id="wx-user", number=701, arg="", now=NOW)

    assert start["status"] == "success"
    assert "CARVEN 情报简报" in start["reply_text"]
    assert stock["enabled_categories"] == ["akshare", "institutional_13f", "senate_trading"]
    assert tech["enabled_categories"] == ["ai_model_updates", "github_trending"]
    assert "每天 08:30" in schedule["reply_text"]
    assert custom_prompt["status"] == "prompt"
    assert "706 英伟达" in custom_prompt["reply_text"]
    assert custom["status"] == "success"
    assert "英伟达" in custom["reply_text"]
    assert "A股资金流向" in status["reply_text"]
    assert "AI模型动态" in status["reply_text"]


@pytest.mark.asyncio
async def test_wechat_700_series_intel_brief_menu(monkeypatch, tmp_path):
    from src.api.routers import wechat

    monkeypatch.setenv("INTEL_BRIEF_DB_PATH", str(tmp_path / "wechat-intel.db"))
    reply = await wechat._execute_numbered_cmd(700, "", from_user="wx-openid-1")
    stock = await wechat._execute_numbered_cmd(702, "", from_user="wx-openid-1")
    custom_prompt = await wechat._execute_numbered_cmd(706, "", from_user="wx-openid-1")

    assert "CARVEN 情报简报" in reply
    assert "回复数字即可操作" in reply
    assert "700 今日简报" in reply
    assert "A股资金流向" in stock
    assert "706 英伟达" in custom_prompt


@pytest.mark.asyncio
async def test_wechat_incoming_routes_700_series_without_llm(monkeypatch, tmp_path):
    from src.api.routers import wechat

    monkeypatch.setenv("INTEL_BRIEF_DB_PATH", str(tmp_path / "wechat-route-intel.db"))

    menu = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-openid-2", text="700"))
    market = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-openid-2", text="702"))
    custom = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-openid-2", text="706 英伟达"))

    assert "CARVEN 情报简报" in menu.reply
    assert "700 今日简报" in menu.reply
    assert "A股资金流向" in market.reply
    assert "英伟达" in custom.reply


@pytest.mark.asyncio
async def test_wechat_intel_brief_two_step_schedule_and_tracking(monkeypatch, tmp_path):
    from src.api.routers import wechat

    monkeypatch.setenv("INTEL_BRIEF_DB_PATH", str(tmp_path / "wechat-two-step-intel.db"))
    wechat._wechat_pending_actions.clear()

    schedule_prompt = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-openid-3", text="705"))
    schedule_choice = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-openid-3", text="2"))
    track_prompt = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-openid-3", text="706"))
    track_name = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-openid-3", text="英伟达"))

    assert "回复数字即可设置" in schedule_prompt.reply
    assert "每天 09:00" in schedule_choice.reply
    weekly_prompt = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-openid-3", text="705"))
    weekly_choice = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-openid-3", text="每周 09:00"))
    weekly_status = await wechat.wechat_incoming(wechat.WeChatIncomingRequest(from_user="wx-openid-3", text="701"))
    assert "回复数字即可设置" in weekly_prompt.reply
    assert "每周 09:00" in weekly_choice.reply
    assert "推送时间：每周 09:00" in weekly_status.reply
    assert "下一条直接回复名字" in track_prompt.reply
    assert "706 英伟达" in track_prompt.reply
    assert "已添加追踪：英伟达" in track_name.reply


def test_wechat_welcome_exposes_intel_brief_numbers():
    from src.api.routers import wechat

    welcome = wechat._build_welcome_message()
    full = wechat._build_full_help()

    assert "700 每日简报" in welcome
    assert "706 英伟达" in welcome
    assert "🧭 每日简报 (700-708)" in full
    assert "700 — 每日简报菜单" in full
