"""
Tests for ChatRouter — ALL messages route through this module.

Covers: intent classification, should_respond routing, lane overrides,
discuss mode, service workflow auto-start.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.routing import (
    ChatRouter,
    BotCapability,
    Intent,
    INTENT_KEYWORDS,
    INTENT_BOT_MAP,
    CHAIN_DISCUSS_TRIGGERS,
    CollabOrchestrator,
    CollabPhase,
)


# ============ Fixtures ============

@pytest.fixture
def router():
    """ChatRouter with 3 bots registered."""
    r = ChatRouter()
    r.register_bot(BotCapability(
        bot_id="qwen235b", name="Qwen", username="qwen_bot",
        keywords=["代码", "编程"], domains=["coding", "math"],
        priority=3,
    ))
    r.register_bot(BotCapability(
        bot_id="deepseek_v3", name="DeepSeek", username="deepseek_bot",
        keywords=["debug", "调试"], domains=["coding", "analysis"],
        priority=2,
    ))
    r.register_bot(BotCapability(
        bot_id="claude_sonnet", name="Claude", username="claude_bot",
        keywords=["creative", "创意", "文案"], domains=["creative", "analysis"],
        priority=1,
    ))
    r.register_bot(BotCapability(
        bot_id="gptoss", name="GPT-OSS", username="gptoss_bot",
        keywords=[], domains=["general"],
        priority=0,
    ))
    r.register_bot(BotCapability(
        bot_id="claude_haiku", name="Haiku", username="haiku_bot",
        keywords=["故事", "小说"], domains=["creative"],
        priority=0,
    ))
    return r


# ============ classify_intent ============

class TestClassifyIntent:

    def test_code_keywords_detected(self, router):
        """Code-related keywords should classify as Intent.CODE."""
        intents = router.classify_intent("帮我看看这个python代码有bug")
        top_intent = intents[0][0]
        assert top_intent == Intent.CODE

    def test_creative_keywords_detected(self, router):
        """Creative keywords should classify as Intent.CREATIVE."""
        intents = router.classify_intent("帮我写一个广告文案关于创意设计")
        top_intent = intents[0][0]
        assert top_intent == Intent.CREATIVE

    def test_no_keyword_defaults_to_general(self, router):
        """Messages with no matching keywords default to GENERAL."""
        intents = router.classify_intent("你好")
        top_intent = intents[0][0]
        assert top_intent == Intent.GENERAL

    def test_math_keywords_detected(self, router):
        """Math keywords should classify as Intent.MATH."""
        intents = router.classify_intent("请帮我求解这个方程的概率")
        top_intent = intents[0][0]
        assert top_intent == Intent.MATH


# ============ should_respond ============

class TestShouldRespond:

    def test_private_chat_always_responds(self, router):
        """Any bot should respond in private chat."""
        should, reason = router.should_respond(
            "qwen235b", "hello", "private",
        )
        assert should is True
        assert "私聊" in reason

    def test_at_mention_triggers_response(self, router):
        """Bot should respond when @mentioned."""
        should, reason = router.should_respond(
            "qwen235b", "hey @qwen_bot help me", "supergroup", message_id=1,
        )
        assert should is True
        assert "@" in reason or "提及" in reason

    def test_at_mention_other_bot_no_response(self, router):
        """Bot should NOT respond when another bot is @mentioned."""
        should, reason = router.should_respond(
            "qwen235b", "hey @deepseek_bot help me", "supergroup", message_id=2,
        )
        assert should is False

    def test_keyword_trigger(self, router):
        """Bot with matching keyword should respond."""
        should, reason = router.should_respond(
            "qwen235b", "我的代码有问题", "supergroup", message_id=3,
        )
        assert should is True
        assert "关键词" in reason

    def test_bot_message_ignored(self, router):
        """Messages from other bots should be ignored."""
        router.register_bot_user_id(12345)
        should, reason = router.should_respond(
            "qwen235b", "some text", "supergroup",
            message_id=4, from_user_id=12345,
        )
        assert should is False
        assert "Bot" in reason

    def test_chain_discuss_trigger_detected(self, router):
        """Chain discuss triggers should return False with special reason."""
        should, reason = router.should_respond(
            "qwen235b", "所有人来讨论一下这个问题", "supergroup", message_id=5,
        )
        assert should is False
        assert reason.startswith("chain_discuss:")


# ============ Lane routing ============

class TestLaneRouting:

    def test_lane_marker_routes_to_correct_bot(self, router):
        """#风控 should route to claude_sonnet."""
        should, reason = router.should_respond(
            "claude_sonnet", "这个项目的#风控怎么做", "supergroup", message_id=10,
        )
        assert should is True
        assert "lane" in reason

    def test_lane_marker_excludes_other_bots(self, router):
        """#风控 should NOT let qwen respond."""
        should, reason = router.should_respond(
            "qwen235b", "这个项目的#风控怎么做", "supergroup", message_id=10,
        )
        assert should is False
        assert "lane" in reason


# ============ should_auto_service_workflow ============

class TestShouldAutoServiceWorkflow:

    def test_action_plus_noun_triggers(self, router):
        """Text with action + noun hints should trigger service workflow."""
        result = router.should_auto_service_workflow(
            "帮我修复这个代码的bug", "supergroup",
        )
        assert result is True

    def test_command_does_not_trigger(self, router):
        """/ commands should not trigger service workflow."""
        result = router.should_auto_service_workflow(
            "/help", "supergroup",
        )
        assert result is False

    def test_private_chat_does_not_trigger(self, router):
        """Private chats should not trigger service workflow."""
        result = router.should_auto_service_workflow(
            "帮我修复这个代码", "private",
        )
        assert result is False

    def test_skip_hint_prevents_trigger(self, router):
        """Skip hints like '直接回答' should prevent workflow."""
        result = router.should_auto_service_workflow(
            "帮我修复这个代码 直接回答", "supergroup",
        )
        assert result is False

    def test_short_text_no_trigger(self, router):
        """Very short text should not trigger."""
        result = router.should_auto_service_workflow(
            "你好", "supergroup",
        )
        assert result is False


# ============ Discuss mode ============

class TestDiscussMode:

    async def test_start_discuss_creates_session(self, router):
        """start_discuss should create an active session."""
        msg = await router.start_discuss(chat_id=100, topic="AI未来", rounds=3)
        assert "讨论模式启动" in msg
        session = router.get_discuss_session(100)
        assert session is not None
        assert session["topic"] == "AI未来"
        assert session["rounds_total"] == 3

    async def test_stop_discuss_clears_session(self, router):
        """stop_discuss should remove the session."""
        await router.start_discuss(chat_id=101, topic="test", rounds=2)
        msg = await router.stop_discuss(101)
        assert "结束" in msg
        assert router.get_discuss_session(101) is None

    async def test_next_discuss_turn_returns_bot_and_prompt(self, router):
        """next_discuss_turn returns (bot_id, prompt) for next speaker."""
        await router.start_discuss(
            chat_id=102, topic="量子计算", rounds=1,
            participants=["qwen235b", "deepseek_v3"],
        )
        result = await router.next_discuss_turn(102)
        assert result is not None
        bot_id, prompt = result
        assert bot_id == "qwen235b"
        assert "量子计算" in prompt


# ============ CollabOrchestrator ============

class TestCollabOrchestrator:

    async def test_start_collab_creates_task(self, router):
        """start_collab should create a CollabTask."""
        orch = CollabOrchestrator(router)
        task = await orch.start_collab(
            chat_id=200, task_text="写一个排序算法",
        )
        assert task.chat_id == 200
        assert task.phase == CollabPhase.PLANNING
        assert task.planner_id in ("deepseek_v3", "qwen235b")

    async def test_select_planner_by_intent(self, router):
        """Code task should select deepseek_v3 as planner."""
        planner = router.select_planner("帮我写一个python函数，调试这个bug")
        assert planner == "deepseek_v3"

    async def test_select_planner_non_code(self, router):
        """Non-code task should select qwen235b as planner."""
        planner = router.select_planner("你好，今天天气怎么样")
        assert planner == "qwen235b"
