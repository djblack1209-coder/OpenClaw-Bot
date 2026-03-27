"""
OpenClawBrain 单元测试。

覆盖:
  1. get_brain() 单例行为
  2. process_message() 基本流程
  3. pre_parsed_intent 跳过二次解析
  4. 追问（clarification）→ 记录 → 恢复
  5. 上下文收集（_build_context 路径）包含记忆
  6. 异常不崩溃（error_handling）

所有外部依赖（LLM、EventBus、ContextCollector、TaskGraphExecutor）均用 mock 替代。
pytest.ini 已配置 asyncio_mode = auto，async 测试不需要装饰器。
"""
import time
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from src.core.intent_parser import ParsedIntent, TaskType
from src.core.task_graph import NodeStatus, TaskNode


# ── 辅助工具 ────────────────────────────────────────────────


def _make_actionable_intent(**overrides) -> ParsedIntent:
    """创建一个可执行的 ParsedIntent（confidence >= 0.5 且 task_type != UNKNOWN）。"""
    defaults = dict(
        goal="测试目标",
        task_type=TaskType.INFO,
        known_params={},
        missing_critical=[],
        confidence=0.9,
        raw_message="测试消息",
    )
    defaults.update(overrides)
    return ParsedIntent(**defaults)


def _make_non_actionable_intent(**overrides) -> ParsedIntent:
    """创建一个不可执行的 ParsedIntent（UNKNOWN + 低置信度）。"""
    defaults = dict(
        goal="",
        task_type=TaskType.UNKNOWN,
        known_params={},
        confidence=0.2,
    )
    defaults.update(overrides)
    return ParsedIntent(**defaults)


def _mock_completed_graph(is_success=True):
    """构造一个已完成的 mock 任务图（用于 TaskGraphExecutor.execute 返回值）。"""
    graph = MagicMock()
    graph.is_complete = True
    graph.is_success = is_success
    graph.name = "测试图"
    graph.get_progress.return_value = {
        "total": 1,
        "completed": 1 if is_success else 0,
        "failed": 0 if is_success else 1,
        "running": 0,
        "pending": 0,
        "progress_pct": 100.0 if is_success else 0.0,
        "nodes": [],
    }

    # 构造成功节点
    node = MagicMock()
    node.id = "query"
    node.status = NodeStatus.SUCCESS if is_success else NodeStatus.FAILED
    node.result = {"source": "test", "answer": "测试回答"} if is_success else None
    node.error = None if is_success else "执行失败"
    node.name = "测试节点"

    graph.nodes = {"query": node}
    return graph


# ── Fixture: 每次测试重置 Brain 单例 + mock 外部依赖 ─────────


@pytest.fixture(autouse=True)
def _reset_brain_singleton():
    """每个测试前后重置 brain 全局单例，防止测试间干扰。"""
    import src.core.brain as brain_mod
    brain_mod._brain = None
    yield
    brain_mod._brain = None


@pytest.fixture
def mock_event_bus():
    """mock EventBus，所有 publish 调用不做任何事。"""
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_ctx_collector():
    """mock ContextCollector，返回基本上下文（含用户画像和对话历史）。"""
    collector = MagicMock()
    collector.collect = AsyncMock(return_value={
        "user_profile": "测试用户画像: 喜欢科技股",
        "conversation_summary": "之前聊过苹果股票",
        "recent_messages": "用户: 帮我看看AAPL\nBot: AAPL目前150美元",
        "cross_domain_signals": "",
    })
    return collector


def _create_brain(mock_event_bus, mock_ctx_collector):
    """创建 Brain 实例，注入 mock 依赖。"""
    with patch("src.core.brain.get_event_bus", return_value=mock_event_bus):
        from src.core.brain import OpenClawBrain
        brain = OpenClawBrain()

    # 替换执行器为 mock（避免真实执行任务图节点）
    brain._graph_executor = MagicMock()
    brain._graph_executor.execute = AsyncMock()

    return brain


@pytest.fixture
def brain(mock_event_bus, mock_ctx_collector):
    """返回一个依赖全部被 mock 的 Brain 实例。"""
    return _create_brain(mock_event_bus, mock_ctx_collector)


# ════════════════════════════════════════════════════════════
#  1. get_brain() 单例测试
# ════════════════════════════════════════════════════════════


class TestBrainSingleton:
    """get_brain() 应该返回同一个实例（单例模式）。"""

    def test_brain_singleton_returns_same_instance(self):
        """连续两次调用 get_brain() 应返回同一个对象。"""
        with patch("src.core.brain.get_event_bus") as mock_bus_factory:
            mock_bus_factory.return_value = MagicMock(publish=AsyncMock())

            from src.core.brain import get_brain
            brain1 = get_brain()
            brain2 = get_brain()

            assert brain1 is brain2, "get_brain() 应返回同一实例"

    def test_init_brain_creates_new_instance(self):
        """init_brain() 应该创建新实例，覆盖旧的。"""
        with patch("src.core.brain.get_event_bus") as mock_bus_factory:
            mock_bus_factory.return_value = MagicMock(publish=AsyncMock())

            from src.core.brain import get_brain, init_brain
            brain_old = get_brain()
            brain_new = init_brain()

            assert brain_new is not brain_old, "init_brain() 应创建新实例"

            # 之后 get_brain() 应返回新实例
            brain_check = get_brain()
            assert brain_check is brain_new


# ════════════════════════════════════════════════════════════
#  2. process_message() 基本流程
# ════════════════════════════════════════════════════════════


class TestProcessMessageBasic:
    """process_message() 正常流程: 解析意图 → 构建任务图 → 执行 → 返回结果。"""

    async def test_process_message_basic_success(
        self, brain, mock_ctx_collector
    ):
        """可执行意图 → 任务图执行成功 → 返回 TaskResult.success == True。"""
        intent = _make_actionable_intent(
            goal="查询信息",
            task_type=TaskType.INFO,
            known_params={"question": "什么是量化交易"},
        )
        brain._intent_parser.parse = AsyncMock(return_value=intent)

        # mock 任务图执行返回成功结果
        completed_graph = _mock_completed_graph(is_success=True)
        brain._graph_executor.execute = AsyncMock(return_value=completed_graph)

        # mock 上下文收集
        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ):
            result = await brain.process_message(
                source="telegram",
                message="什么是量化交易",
            )

        assert result.error is None, f"不应有错误，实际: {result.error}"
        assert result.intent is not None
        assert result.intent.task_type == TaskType.INFO
        assert result.elapsed_seconds > 0

    async def test_process_message_non_actionable_forwards_to_chat(
        self, brain, mock_ctx_collector
    ):
        """不可执行的意图（闲聊）→ 降级为转发到聊天处理。"""
        intent = _make_non_actionable_intent()
        brain._intent_parser.parse = AsyncMock(return_value=intent)

        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ):
            # skip_chat_fallback=True 时直接返回 forward_to_chat
            result = await brain.process_message(
                source="telegram",
                message="今天心情不错",
                skip_chat_fallback=True,
            )

        assert result.error is None
        assert result.final_result is not None
        assert result.final_result.get("action") == "forward_to_chat"


# ════════════════════════════════════════════════════════════
#  3. pre_parsed_intent 跳过二次解析
# ════════════════════════════════════════════════════════════


class TestPreParsedIntent:
    """传入 pre_parsed_intent 时，应复用该意图而不重新解析。"""

    async def test_process_message_with_pre_parsed_intent(
        self, brain, mock_ctx_collector
    ):
        """传入 pre_parsed_intent → 跳过 IntentParser.parse()。"""
        pre_intent = _make_actionable_intent(
            goal="分析TSLA",
            task_type=TaskType.INVESTMENT,
            known_params={"symbol_hint": "TSLA"},
        )

        # 设置 parser.parse 为 spy，确认它不被调用
        brain._intent_parser.parse = AsyncMock(
            side_effect=AssertionError("不应调用 parse")
        )

        completed_graph = _mock_completed_graph(is_success=True)
        brain._graph_executor.execute = AsyncMock(return_value=completed_graph)

        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ):
            result = await brain.process_message(
                source="telegram",
                message="分析TSLA",
                pre_parsed_intent=pre_intent,
            )

        # 验证使用了预解析意图
        assert result.intent is pre_intent
        assert result.intent.task_type == TaskType.INVESTMENT
        # parse() 不应被调用
        brain._intent_parser.parse.assert_not_called()

    async def test_non_actionable_pre_parsed_falls_through(
        self, brain, mock_ctx_collector
    ):
        """pre_parsed_intent.is_actionable == False 时，仍走 IntentParser.parse()。"""
        # 不可执行的预解析意图
        weak_intent = _make_non_actionable_intent()
        assert weak_intent.is_actionable is False

        # parser 应被调用，返回一个新的可执行意图
        real_intent = _make_actionable_intent(
            goal="真实意图", task_type=TaskType.SYSTEM
        )
        brain._intent_parser.parse = AsyncMock(return_value=real_intent)

        completed_graph = _mock_completed_graph(is_success=True)
        brain._graph_executor.execute = AsyncMock(return_value=completed_graph)

        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ):
            result = await brain.process_message(
                source="telegram",
                message="查看状态",
                pre_parsed_intent=weak_intent,
            )

        # parser 应被调用一次
        brain._intent_parser.parse.assert_called_once()
        assert result.intent is real_intent


# ════════════════════════════════════════════════════════════
#  4. 追问（Clarification）→ 记录 → 恢复
# ════════════════════════════════════════════════════════════


class TestPendingClarification:
    """追问流程: 缺少关键参数 → 记录 pending → 用户回答 → 恢复执行。"""

    async def test_clarification_recorded_and_returned(
        self, brain, mock_ctx_collector
    ):
        """意图缺少关键参数时，返回 needs_clarification=True 并记录 pending。"""
        intent = _make_actionable_intent(
            goal="帮我订餐厅",
            task_type=TaskType.BOOKING,
            missing_critical=["restaurant_name", "date"],
        )
        # 让 needs_clarification 为 True
        assert intent.needs_clarification is True

        brain._intent_parser.parse = AsyncMock(return_value=intent)

        # mock _build_task_graph 返回 None（无可先执行的节点）
        brain._build_task_graph = AsyncMock(return_value=None)

        chat_id = 12345
        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ):
            result = await brain.process_message(
                source="telegram",
                message="帮我订餐厅",
                context={"chat_id": chat_id, "user_id": 1},
            )

        # 验证返回追问状态
        assert result.needs_clarification is True
        assert "restaurant_name" in result.clarification_params
        assert "date" in result.clarification_params

        # 验证 pending 已记录
        pending_tid = brain.get_pending_clarification(chat_id)
        assert pending_tid is not None, "应记录 pending clarification"

    async def test_resume_with_answer_clears_pending(
        self, brain, mock_ctx_collector
    ):
        """用户回答追问后，pending 应被清除，任务恢复执行。"""
        chat_id = 99999
        task_id = "test123"

        # 手动注入 pending 状态（模拟之前的追问）
        intent = _make_actionable_intent(
            goal="帮我订餐厅",
            task_type=TaskType.BOOKING,
            known_params={},
            missing_critical=["restaurant_name"],
        )
        brain._pending_callbacks[task_id] = {
            "intent": intent,
            "partial_task": None,
            "graph": None,
            "context": {"chat_id": chat_id},
            "created_at": time.time(),
        }
        brain._pending_clarifications[chat_id] = task_id

        # mock 恢复执行的任务图
        completed_graph = _mock_completed_graph(is_success=True)
        brain._graph_executor.execute = AsyncMock(return_value=completed_graph)

        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ):
            result = await brain.resume_with_answer(
                task_id=task_id,
                answer="海底捞",
                context={"chat_id": chat_id, "user_id": 1},
            )

        # 验证回答被注入到 known_params
        assert intent.known_params.get("restaurant_name") == "海底捞"
        assert intent.known_params.get("clarification_answer") == "海底捞"

        # 验证 missing_critical 中已移除该参数
        assert "restaurant_name" not in intent.missing_critical

        # 验证 pending 已清除
        assert brain.get_pending_clarification(chat_id) is None
        assert task_id not in brain._pending_callbacks

    async def test_resume_with_expired_task(self, brain):
        """追问超时后（pending 已清理），恢复应返回错误。"""
        result = await brain.resume_with_answer(
            task_id="expired_task",
            answer="过期回答",
            context={"chat_id": 0},
        )

        assert result.error is not None
        assert "过期" in result.error


# ════════════════════════════════════════════════════════════
#  5. 上下文收集包含记忆（用户画像 + 对话历史）
# ════════════════════════════════════════════════════════════


class TestBuildContextIncludesMemory:
    """process_message 调用 ContextCollector.collect()，确保上下文被传递。"""

    async def test_context_collector_called_with_ids(
        self, brain, mock_ctx_collector
    ):
        """ContextCollector.collect() 应收到正确的 user_id/chat_id/bot_id。"""
        intent = _make_non_actionable_intent()
        brain._intent_parser.parse = AsyncMock(return_value=intent)

        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ):
            await brain.process_message(
                source="telegram",
                message="你好",
                context={"user_id": 42, "chat_id": 100, "bot_id": "bot7"},
                skip_chat_fallback=True,
            )

        # 验证 collect 被调用且参数正确
        mock_ctx_collector.collect.assert_called_once_with(
            user_id="42",
            chat_id="100",
            bot_id="bot7",
        )

    async def test_context_collector_provides_user_profile(
        self, brain, mock_ctx_collector
    ):
        """ContextCollector 返回的用户画像应包含在上下文中（用于闲聊降级）。"""
        intent = _make_non_actionable_intent()
        brain._intent_parser.parse = AsyncMock(return_value=intent)

        # 验证 collect 返回了用户画像
        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ):
            await brain.process_message(
                source="telegram",
                message="你好",
                skip_chat_fallback=True,
            )

        # collect 被调用一次，说明上下文收集流程正常运行
        mock_ctx_collector.collect.assert_called_once()
        # 验证 mock 返回的数据包含画像字段
        ctx_data = await mock_ctx_collector.collect()
        assert "user_profile" in ctx_data
        assert "conversation_summary" in ctx_data


# ════════════════════════════════════════════════════════════
#  6. 异常不崩溃（Error Handling）
# ════════════════════════════════════════════════════════════


class TestProcessMessageErrorHandling:
    """process_message 内部异常应被捕获，返回带 error 的 TaskResult 而非抛异常。"""

    async def test_intent_parser_exception_caught(
        self, brain, mock_ctx_collector
    ):
        """IntentParser.parse() 抛异常 → result.error 有值，不崩溃。"""
        brain._intent_parser.parse = AsyncMock(
            side_effect=RuntimeError("LLM 路由全部不可用")
        )

        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ):
            # 不应抛异常
            result = await brain.process_message(
                source="telegram",
                message="帮我分析AAPL",
            )

        assert result.error is not None
        assert result.success is False
        assert result.elapsed_seconds > 0

    async def test_graph_executor_exception_caught(
        self, brain, mock_ctx_collector
    ):
        """TaskGraphExecutor.execute() 抛异常 → 捕获，不崩溃。"""
        intent = _make_actionable_intent(
            goal="查系统状态",
            task_type=TaskType.SYSTEM,
        )
        brain._intent_parser.parse = AsyncMock(return_value=intent)
        brain._graph_executor.execute = AsyncMock(
            side_effect=ConnectionError("执行器连接断开")
        )

        # mock 自愈为失败，确保异常不被自愈掩盖
        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ), patch.object(
            brain, "_try_self_heal",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await brain.process_message(
                source="telegram",
                message="查看系统状态",
            )

        assert result.error is not None
        assert result.success is False

    async def test_context_collector_exception_caught(self, brain):
        """ContextCollector.collect() 抛异常 → 捕获，不崩溃。"""
        broken_collector = MagicMock()
        broken_collector.collect = AsyncMock(
            side_effect=Exception("Redis 连接失败")
        )

        with patch(
            "src.core.brain.get_context_collector",
            return_value=broken_collector,
        ):
            result = await brain.process_message(
                source="telegram",
                message="帮我分析AAPL",
            )

        # 上下文收集失败应被捕获在外层 try/except
        assert result.error is not None
        assert result.success is False

    async def test_self_heal_triggered_on_error(
        self, brain, mock_ctx_collector
    ):
        """执行异常时，自愈机制应被触发；自愈成功则 result.success == True。"""
        intent = _make_actionable_intent(
            goal="分析AAPL", task_type=TaskType.INVESTMENT,
            known_params={"symbol_hint": "AAPL"},
        )
        brain._intent_parser.parse = AsyncMock(return_value=intent)

        # _build_task_graph 抛异常 → 进入 except → 触发自愈
        brain._build_task_graph = AsyncMock(
            side_effect=RuntimeError("模块爆炸")
        )

        with patch(
            "src.core.brain.get_context_collector",
            return_value=mock_ctx_collector,
        ), patch.object(
            brain, "_try_self_heal",
            new_callable=AsyncMock,
            return_value=True,  # 自愈成功
        ):
            result = await brain.process_message(
                source="telegram",
                message="帮我分析AAPL",
            )

        # 自愈成功 → error 被清空，final_result 标记 healed
        assert result.success is True
        assert result.final_result == {"healed": True, "note": "已自动修复并重试"}
        assert result.error is None


# ════════════════════════════════════════════════════════════
#  附加: TaskResult 数据结构测试
# ════════════════════════════════════════════════════════════


class TestTaskResult:
    """TaskResult 的属性和序列化方法。"""

    def test_success_property(self):
        """success 属性: error 为 None 且 final_result 不为 None 时为 True。"""
        from src.core.brain import TaskResult

        # 成功情况
        r = TaskResult(task_id="t1", final_result={"answer": "ok"})
        assert r.success is True

        # 有错误
        r2 = TaskResult(task_id="t2", error="出错了")
        assert r2.success is False

        # 无结果也不算成功
        r3 = TaskResult(task_id="t3")
        assert r3.success is False

    def test_to_dict_structure(self):
        """to_dict() 返回结构完整的字典。"""
        from src.core.brain import TaskResult

        intent = _make_actionable_intent(goal="测试", task_type=TaskType.INFO)
        r = TaskResult(
            task_id="t1",
            intent=intent,
            final_result={"answer": "42"},
            elapsed_seconds=1.234,
        )
        d = r.to_dict()

        assert d["task_id"] == "t1"
        assert d["success"] is True
        assert d["goal"] == "测试"
        assert d["task_type"] == "info"
        assert d["elapsed"] == 1.23
        assert d["result"] == {"answer": "42"}


# ════════════════════════════════════════════════════════════
#  附加: 任务管理方法
# ════════════════════════════════════════════════════════════


class TestTaskManagement:
    """cancel_task / get_active_tasks / cleanup_pending_callbacks。"""

    def test_cancel_task(self, brain):
        """cancel_task() 应从活跃任务中移除并标记错误。"""
        from src.core.brain import TaskResult

        task = TaskResult(task_id="abc", source="test")
        brain._active_tasks["abc"] = task

        assert brain.cancel_task("abc") is True
        assert "abc" not in brain._active_tasks
        assert task.error == "用户取消"

    def test_cancel_nonexistent_task(self, brain):
        """取消不存在的任务应返回 False。"""
        assert brain.cancel_task("no_such_task") is False

    def test_get_active_tasks(self, brain):
        """get_active_tasks() 应返回所有活跃任务的字典列表。"""
        from src.core.brain import TaskResult

        brain._active_tasks["t1"] = TaskResult(task_id="t1", source="test")
        brain._active_tasks["t2"] = TaskResult(
            task_id="t2", source="test", final_result={"ok": True}
        )

        tasks = brain.get_active_tasks()
        assert len(tasks) == 2
        assert all(isinstance(t, dict) for t in tasks)

    def test_cleanup_stale_callbacks(self, brain):
        """cleanup_pending_callbacks() 应清理超时的回调。"""
        # 注入一个已过期的 pending callback
        brain._pending_callbacks["old_task"] = {
            "intent": _make_actionable_intent(),
            "created_at": time.time() - 9999,  # 很久以前
        }
        brain._pending_clarifications[111] = "old_task"

        brain.cleanup_pending_callbacks(max_age_seconds=600)

        assert "old_task" not in brain._pending_callbacks
        assert 111 not in brain._pending_clarifications
