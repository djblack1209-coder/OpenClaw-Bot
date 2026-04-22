import pytest

from src.routing import BotCapability, ChatRouter


@pytest.mark.asyncio
async def test_group_router_stays_silent_when_auto_routing_is_disabled(monkeypatch):
    monkeypatch.setenv("CHAT_ROUTER_ENABLE_GROUP_LLM", "false")
    monkeypatch.setenv("CHAT_ROUTER_ENABLE_GROUP_INTENT", "false")
    monkeypatch.setenv("CHAT_ROUTER_ENABLE_GROUP_FALLBACK", "false")

    router = ChatRouter()
    router.register_bot(BotCapability(bot_id="qwen235b", name="Qwen", username="carven_Qwen235B_Bot", keywords=["qwen"], domains=["research"]))

    called = {"count": 0}

    async def fake_llm_router(chat_id: int, prompt: str) -> str:
        called["count"] += 1
        return "general|qwen235b"

    router.register_llm_router(fake_llm_router)

    should, reason = await router.should_respond_async(
        "qwen235b",
        "为什么今天市场这么安静",
        "group",
        message_id=1,
        from_user_id=123,
    )

    assert should is False
    assert called["count"] == 0


@pytest.mark.asyncio
async def test_group_router_auto_starts_service_workflow_for_complex_task(monkeypatch):
    monkeypatch.setenv("CHAT_ROUTER_ENABLE_GROUP_LLM", "false")
    monkeypatch.setenv("CHAT_ROUTER_ENABLE_GROUP_INTENT", "false")
    monkeypatch.setenv("CHAT_ROUTER_ENABLE_GROUP_FALLBACK", "false")

    router = ChatRouter()
    router.register_bot(BotCapability(bot_id="qwen235b", name="Qwen", username="carven_Qwen235B_Bot", keywords=["qwen"], domains=["research"]))
    router.register_bot(BotCapability(bot_id="gptoss", name="GPT-OSS", username="carven_GPTOSS120B_Bot", keywords=["gptoss"], domains=["general"]))

    should_qwen, reason_qwen = await router.should_respond_async(
        "qwen235b",
        "帮我优化一下群聊的公告排版流程",
        "group",
        message_id=2,
        from_user_id=123,
    )
    should_gpt, reason_gpt = await router.should_respond_async(
        "gptoss",
        "帮我优化一下群聊的公告排版流程",
        "group",
        message_id=2,
        from_user_id=123,
    )

    assert should_qwen is True
    assert reason_qwen == "service_workflow:auto -> qwen235b"
    assert should_gpt is False
    assert "其他Bot已回复此消息" in reason_gpt


def test_sync_router_disables_group_fallback_by_default(monkeypatch):
    monkeypatch.setenv("CHAT_ROUTER_ENABLE_GROUP_INTENT", "false")
    monkeypatch.setenv("CHAT_ROUTER_ENABLE_GROUP_FALLBACK", "false")

    router = ChatRouter()
    router.register_bot(BotCapability(bot_id="gptoss", name="GPT-OSS", username="carven_GPTOSS120B_Bot", keywords=["gptoss"], domains=["general"]))

    should, _ = router.should_respond(
        "gptoss",
        "今天天气不错",
        "group",
        message_id=5,
        from_user_id=123,
    )

    assert should is False


def test_service_workflow_auto_detects_complex_group_task_requests():
    router = ChatRouter()

    assert router.should_auto_service_workflow(
        "帮我优化一下群聊的公告排版流程",
        "group",
        route_reason="被@提及",
    ) is True


def test_service_workflow_keeps_simple_group_questions_direct():
    router = ChatRouter()

    assert router.should_auto_service_workflow(
        "为什么今天市场这么安静",
        "group",
        route_reason="意图路由: analysis (最佳匹配)",
    ) is False
    assert router.should_auto_service_workflow(
        "帮我看看 NVDA，但直接回答不要方案",
        "group",
        route_reason="被@提及",
    ) is False
