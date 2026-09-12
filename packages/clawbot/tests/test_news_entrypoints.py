"""Legacy news entrypoints must only guide users to Global Intelligence Bot."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routers import wechat
from src.bot.chinese_nlp_mixin import _match_chinese_command
from src.intel.news_entrypoint import global_intelligence_news_guidance, is_legacy_news_command


@pytest.mark.parametrize("username", ["ExampleIntelBot", "@Example_Intel_Bot"])
def test_guidance_links_only_to_configured_bot_username(monkeypatch, username):
    monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_BOT_USERNAME", username)

    reply = global_intelligence_news_guidance()

    assert f"https://t.me/{username.removeprefix('@')}" in reply
    assert "Global Intelligence Bot" in reply
    assert all(command in reply for command in ("/today", "/ai", "/market"))


@pytest.mark.parametrize("username", [
    None, "", "a_bot/evil", "https://t.me/ExampleIntelBot", "a_bot?start=evil",
    "a_bot\nmalicious", "@@ExampleIntelBot", "xbot", "1ExampleBot",
    "a" * 30 + "bot", "ExampleUser", "中文Bot",
])
def test_missing_or_invalid_username_never_invents_or_echoes_a_link(monkeypatch, username):
    if username is None:
        monkeypatch.delenv("INTEL_BRIEF_TELEGRAM_BOT_USERNAME", raising=False)
    else:
        monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_BOT_USERNAME", username)

    reply = global_intelligence_news_guidance()

    assert "当前未配置有效的 Bot 用户名" in reply
    assert "https://" not in reply
    assert "malicious" not in reply
    assert "evil" not in reply


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized", [True, False])
async def test_telegram_news_only_replies_in_current_chat(monkeypatch, authorized):
    from src.bot import globals as bot_globals
    from src.bot.cmd_basic.tools_mixin import _ToolsMixin

    monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_BOT_USERNAME", "ExampleIntelBot")
    fetch = AsyncMock(side_effect=AssertionError("retired report must not run"))
    monkeypatch.setattr(bot_globals.news_fetcher, "generate_morning_report", fetch, raising=False)
    handler = SimpleNamespace(_is_authorized=lambda _user_id: authorized)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        effective_chat=SimpleNamespace(id=42),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace(args=[], bot=AsyncMock())

    await _ToolsMixin.cmd_news(handler, update, context)

    fetch.assert_not_awaited()
    assert context.bot.mock_calls == []
    if authorized:
        update.message.reply_text.assert_awaited_once_with(global_intelligence_news_guidance())
    else:
        update.message.reply_text.assert_not_awaited()


@pytest.mark.parametrize("text", [
    "新闻", "科技早报", "早报", "今日新闻", "最新消息", "今天新闻", "看看科技早报", "/news",
    "帮我看科技早报", "看新闻", "今天的科技早报", "给我看看早报", "请查看科技早报。",
])
def test_historical_telegram_news_triggers_keep_the_redirect(text):
    assert _match_chinese_command(text) == ("news", "")


@pytest.mark.parametrize("text", ["世界新闻", "英伟达新闻", "科技早报标题如何取", "不要看科技早报"])
def test_redirect_does_not_swallow_topic_queries_or_conversation(text):
    assert not is_legacy_news_command(text)


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["104", "科技早报", "早报", "新闻", "/news", "看看今日新闻"])
async def test_wechat_news_is_local_guidance_and_interrupts_pending_actions(monkeypatch, text):
    monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_BOT_USERNAME", "ExampleIntelBot")
    api = AsyncMock(side_effect=AssertionError("news must not call daily-brief API"))
    llm = AsyncMock(side_effect=AssertionError("news must not call LLM"))
    monkeypatch.setattr(wechat, "_self_call_api", api)
    monkeypatch.setattr(wechat, "_generate_wechat_reply", llm)
    monkeypatch.setattr(wechat, "_wechat_pending_actions", {})
    wechat._set_pending_action("news-user", "intel_schedule")

    result = await wechat.wechat_incoming(
        wechat.WeChatIncomingRequest(from_user="news-user", text=text),
    )

    assert result.reply == global_intelligence_news_guidance(channel="wechat")
    assert "700" in result.reply
    assert wechat._get_pending_action("news-user") == ""
    assert "cmd_news" not in wechat._CMD_API_MAP
    api.assert_not_awaited()
    llm.assert_not_awaited()
