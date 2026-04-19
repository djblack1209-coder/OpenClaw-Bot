"""
e2e 测试：投资分析路径

覆盖两条链路：
  1. 用户中文输入 → NLP 匹配 → signal/ta 命令 → 返回分析结果
  2. 用户中文输入 → Brain 意图解析 → 任务图执行 → 返回分析结果

测试不发起任何真实 API 请求，全部使用 mock。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot.chinese_nlp_mixin import _match_chinese_command
from src.core.intent_parser import ParsedIntent, TaskType
from src.core.brain import OpenClawBrain, TaskResult


# ============================================================================
# 测试组 1：中文 NLP 匹配 → signal/ta 路由
# ============================================================================


class TestInvestAnalysisNLPMatch:
    """验证中文自然语言输入能正确匹配到投资分析命令。"""

    def test_aapl_can_buy(self):
        """「AAPL能买吗」应匹配为 signal 命令，参数包含 AAPL

        注意: 「AAPL今天能买吗」因为"今天"夹在中间，regex 不匹配，
        这是已知行为——NLP 只做简洁格式匹配，复杂句式走 Brain 路径。
        """
        result = _match_chinese_command("AAPL能买吗")
        assert result is not None, "应该匹配到命令，但返回了 None"
        action, arg = result
        assert action == "signal", f"期望 action='signal'，实际 '{action}'"
        assert "AAPL" in arg.upper(), f"参数中应包含 AAPL，实际 '{arg}'"

    def test_aapl_how_about(self):
        """「AAPL怎么样」也应匹配为 signal 命令"""
        result = _match_chinese_command("AAPL怎么样")
        assert result is not None, "应该匹配到命令，但返回了 None"
        action, arg = result
        assert action == "signal", f"期望 action='signal'，实际 '{action}'"
        assert "AAPL" in arg.upper(), f"参数中应包含 AAPL，实际 '{arg}'"

    def test_tesla_analysis(self):
        """「分析特斯拉」应匹配为 ta 命令（技术分析），参数包含 TSLA"""
        result = _match_chinese_command("分析特斯拉")
        assert result is not None, "应该匹配到命令，但返回了 None"
        action, arg = result
        # 「分析 + 中文公司名」走 ta（技术分析）路径
        assert action == "ta", f"期望 action='ta'，实际 '{action}'"
        assert "TSLA" in arg.upper(), f"参数中应包含 TSLA，实际 '{arg}'"

    def test_chinese_ticker_mapping(self):
        """「苹果能买吗」应将中文公司名映射为 AAPL"""
        result = _match_chinese_command("苹果能买吗")
        assert result is not None, "应该匹配到命令，但返回了 None"
        action, arg = result
        assert action == "signal", f"期望 action='signal'，实际 '{action}'"
        assert "AAPL" in arg.upper(), f"苹果应映射为 AAPL，实际 '{arg}'"

    def test_ambiguous_input_no_crash(self):
        """「今天天气怎么样」不应匹配为投资命令，也不应崩溃"""
        result = _match_chinese_command("今天天气怎么样")
        # 可能返回 None（无匹配）或者匹配到其他非投资类命令
        # 关键验证：不崩溃，且不会误匹配为 signal/ta/buy/sell
        if result is not None:
            action, _ = result
            assert action not in (
                "signal", "ta", "buy", "sell", "chart", "quote",
            ), f"天气查询被误匹配为投资命令 '{action}'"


# ============================================================================
# 测试组 2：Brain 处理投资意图
# ============================================================================


class TestInvestAnalysisBrainPath:
    """验证 Brain 收到投资意图后能正确编排并返回 TaskResult。"""

    @pytest.mark.asyncio
    async def test_brain_processes_investment_intent(self):
        """构造一个预解析的投资意图，喂给 Brain，验证返回 TaskResult"""

        # 构造预解析的投资意图（跳过 LLM 解析）
        intent = ParsedIntent(
            goal="分析 AAPL 是否值得买入",
            task_type=TaskType.INVESTMENT,
            known_params={"ticker": "AAPL", "action": "analyze"},
            confidence=0.95,
            raw_message="AAPL今天能买吗",
        )

        # 构造一个假的任务图执行结果
        fake_graph = MagicMock()
        fake_graph.name = "investment_analysis"
        fake_graph.nodes = {}
        fake_graph.is_success = True
        fake_graph.get_progress.return_value = {"completed": 1, "total": 1}

        # 构造假的上下文收集器
        fake_ctx_collector = MagicMock()
        fake_ctx_collector.collect = AsyncMock(return_value={
            "user_profile": "测试用户",
            "conversation_summary": "",
        })

        # 构造假的响应合成器
        fake_synthesizer = MagicMock()
        fake_synthesizer.synthesize = AsyncMock(
            return_value="AAPL 当前技术面偏强，建议关注 180 支撑位。"
        )
        fake_synthesizer.generate_suggestions = AsyncMock(return_value=[])
        fake_synthesizer.generate_tldr = AsyncMock(return_value="AAPL 短期看涨")

        with (
            # mock 配置文件加载（防止读取真实 omega.yaml）
            patch.object(OpenClawBrain, "_load_config", return_value={
                "cost": {"daily_budget_usd": 50.0},
                "security": {"require_pin_for_trades": True},
                "investment": {"team_enabled": True, "auto_trade": False, "risk_rules": {}},
                "executor": {"fallback_chain": ["api"]},
            }),
            # mock 事件总线
            patch("src.core.brain.get_event_bus") as mock_event_bus,
            # mock 任务图执行器
            patch("src.core.brain.TaskGraphExecutor") as mock_executor_cls,
            # mock 上下文收集
            patch("src.core.brain.get_context_collector", return_value=fake_ctx_collector),
            # mock 响应合成
            patch("src.core.brain.get_response_synthesizer", return_value=fake_synthesizer),
            # mock api_limiter（防止真实限流）
            patch("src.core.brain.api_limiter"),
        ):
            # 配置事件总线 mock
            bus_instance = MagicMock()
            bus_instance.publish = AsyncMock()
            mock_event_bus.return_value = bus_instance

            # 配置执行器 mock — 返回成功的任务图
            executor_instance = MagicMock()
            executor_instance.execute = AsyncMock(return_value=fake_graph)
            mock_executor_cls.return_value = executor_instance

            # 实例化 Brain 并喂入预解析意图
            brain = OpenClawBrain()

            # mock _build_task_graph（避免走真实的图构建逻辑）
            brain._build_task_graph = AsyncMock(return_value=fake_graph)

            result = await brain.process_message(
                source="telegram",
                message="AAPL今天能买吗",
                context={"user_id": "67890", "chat_id": "12345"},
                pre_parsed_intent=intent,
            )

            # 验证返回了有效的 TaskResult
            assert isinstance(result, TaskResult), "应返回 TaskResult 实例"
            assert result.error is None, f"不应有错误，实际: {result.error}"
            assert result.intent is not None, "应包含解析后的意图"
            assert result.intent.task_type == TaskType.INVESTMENT, "意图类型应为投资"
