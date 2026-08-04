"""
OMEGA 核心流水线端到端集成测试。

覆盖:
  A. IntentParser 单元测试 (5) — 快速模式匹配 + LLM 降级
  B. TaskGraph 单元测试 (5)   — DAG 创建/依赖/并行/失败传播/进度
  C. MultiPathExecutor 单元测试 (3) — API 路径/降级/熔断
  D. 流水线集成测试 (2)       — Brain 完整流程 + 错误自愈

pytest.ini 已配置 asyncio_mode = auto，async 测试不需要装饰器。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.executor import MultiPathExecutor
from src.core.intent_parser import IntentParser, ParsedIntent, TaskType
from src.core.task_graph import (
    ExecutorType,
    NodeStatus,
    TaskGraphBuilder,
    TaskGraphExecutor,
)

# ════════════════════════════════════════════════════════════
#  A. IntentParser 单元测试
# ════════════════════════════════════════════════════════════


class TestIntentParser:
    """IntentParser._try_fast_parse 走正则，不调 LLM。"""

    @pytest.fixture(autouse=True)
    def _parser(self):
        self.parser = IntentParser()

    # ── A1. 投资意图 ─────────────────────────────────────

    async def test_investment_intent(self):
        """'帮我分析AAPL' → TaskType.INVESTMENT，fast parse 命中。"""
        intent = await self.parser.parse("帮我分析AAPL")

        assert intent.task_type == TaskType.INVESTMENT
        assert intent.confidence >= 0.8
        assert intent.is_actionable is True
        assert "AAPL" in intent.known_params.get("symbol_hint", "")

    # ── A2. 购物意图 ─────────────────────────────────────

    async def test_shopping_intent(self):
        """'帮我比价AirPods' → TaskType.SHOPPING。"""
        intent = await self.parser.parse("帮我比价AirPods")

        assert intent.task_type == TaskType.SHOPPING
        assert intent.confidence >= 0.8
        assert "airpods" in intent.known_params.get("product_hint", "").lower()

    # ── A3. 系统意图 ─────────────────────────────────────

    async def test_system_intent(self):
        """'查看状态' → TaskType.SYSTEM。"""
        intent = await self.parser.parse("查看状态")

        assert intent.task_type == TaskType.SYSTEM
        assert intent.confidence >= 0.8
        assert intent.is_actionable is True

    # ── A4. 模糊/空输入 → UNKNOWN ─────────────────────────

    async def test_empty_input_fallback(self):
        """空字符串: fast parse 不命中，LLM 也不可用 → UNKNOWN。"""
        # mock 掉 _llm_parse 使其抛异常，模拟 LLM 不可用
        self.parser._llm_parse = AsyncMock(
            side_effect=RuntimeError("LLM router 未初始化")
        )

        intent = await self.parser.parse("")

        assert intent.task_type == TaskType.UNKNOWN
        assert intent.confidence < 0.5
        assert intent.is_actionable is False

    # ── A5. 多意图（第一个匹配优先）─────────────────────

    async def test_multi_intent_first_match(self):
        """'查AAPL行情然后发到推特' — fast parse 匹配到投资（第一个模式优先）。"""
        intent = await self.parser.parse("查AAPL行情然后发到推特")

        # fast parse 按顺序匹配，投资类模式 r"(.+)的?行情" 先命中
        assert intent.task_type == TaskType.INVESTMENT
        assert intent.confidence >= 0.8


# ════════════════════════════════════════════════════════════
#  B. TaskGraph 单元测试
# ════════════════════════════════════════════════════════════


class TestTaskGraph:
    """DAG 结构创建、依赖、并行、失败传播、进度统计。"""

    # ── B1. 单节点图 ─────────────────────────────────────

    async def test_single_node_graph(self):
        """单节点: 创建 → 执行 → 完成。"""
        result_data = {"answer": "hello"}

        async def _fn(params):
            return result_data

        b = TaskGraphBuilder("单节点测试")
        b.add("only", "唯一节点", ExecutorType.LOCAL, _fn, params={}, timeout=5)
        graph = b.build()

        assert len(graph.nodes) == 1
        assert graph.nodes["only"].status == NodeStatus.PENDING

        executor = TaskGraphExecutor()
        completed = await executor.execute(graph)

        assert completed.is_complete is True
        assert completed.is_success is True
        assert completed.nodes["only"].status == NodeStatus.SUCCESS
        assert completed.nodes["only"].result == result_data

    # ── B2. 并行图 — 两个独立节点同时就绪 ──────────────

    async def test_parallel_nodes(self):
        """两个无依赖节点应该同时就绪。"""
        execution_order = []

        async def _fn_a(params):
            execution_order.append("a")
            return {"node": "a"}

        async def _fn_b(params):
            execution_order.append("b")
            return {"node": "b"}

        b = TaskGraphBuilder("并行测试")
        b.add("a", "节点A", ExecutorType.LOCAL, _fn_a, timeout=5)
        b.add("b", "节点B", ExecutorType.LOCAL, _fn_b, timeout=5)
        graph = b.build()

        # 构建后两个节点都是 PENDING 且无依赖 → 都应就绪
        ready = graph.get_ready_nodes()
        assert len(ready) == 2

        executor = TaskGraphExecutor()
        completed = await executor.execute(graph)

        assert completed.is_success is True
        assert set(execution_order) == {"a", "b"}

    # ── B3. 依赖图 — A → B ─────────────────────────────

    async def test_dependency_chain(self):
        """A → B: B 等 A 完成后才执行，且能拿到正确结果。"""
        call_log = []

        async def _fn_a(params):
            call_log.append("a")
            return {"from_a": True}

        async def _fn_b(params):
            call_log.append("b")
            return {"from_b": True}

        b = TaskGraphBuilder("依赖链测试")
        b.add("a", "节点A", ExecutorType.LOCAL, _fn_a, timeout=5)
        b.add("b", "节点B", ExecutorType.LOCAL, _fn_b, after=["a"], timeout=5)
        graph = b.build()

        # 初始只有 A 就绪
        ready = graph.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "a"

        executor = TaskGraphExecutor()
        completed = await executor.execute(graph)

        assert completed.is_success is True
        # A 一定在 B 之前执行
        assert call_log == ["a", "b"]

    async def test_dependency_results_are_passed_without_mutating_declared_params(self):
        """下游节点应收到依赖结果，同时保留构建时声明的参数。"""
        received = {}

        async def _fn_a(params):
            return {"strategy": {"angle": "practical"}, "source": "a"}

        async def _fn_b(params):
            received.update(params)
            return {"success": True}

        builder = TaskGraphBuilder("结果传递")
        builder.add("a", "节点A", ExecutorType.LOCAL, _fn_a, params={"seed": 1})
        builder.add("b", "节点B", ExecutorType.LOCAL, _fn_b, params={"platform": "x"}, after=["a"])
        graph = builder.build()

        await TaskGraphExecutor().execute(graph)

        assert received["strategy"] == {"angle": "practical"}
        assert received["_upstream_results"]["a"]["source"] == "a"
        assert graph.nodes["b"].params == {"platform": "x"}

    async def test_dependency_result_snapshot_cannot_mutate_upstream_result(self):
        """下游修改嵌套参数时，不得污染上游节点保存的原始结果。"""

        async def _fn_a(params):
            return {"items": [{"symbol": "AAPL"}]}

        async def _fn_b(params):
            params["items"][0]["symbol"] = "MUTATED"
            params["_upstream_results"]["a"]["items"].append({"symbol": "TSLA"})
            return {"success": True}

        builder = TaskGraphBuilder("深拷贝结果")
        builder.add("a", "节点A", ExecutorType.LOCAL, _fn_a)
        builder.add("b", "节点B", ExecutorType.LOCAL, _fn_b, after=["a"])
        graph = await TaskGraphExecutor().execute(builder.build())

        assert graph.nodes["a"].result == {"items": [{"symbol": "AAPL"}]}

    @pytest.mark.parametrize(
        "result",
        [
            {"success": False},
            {"ok": False},
            {"error": "明确失败"},
            {"approved": False},
            {"confirmed": False},
            {"status": "pending"},
            {"status": "pending_confirmation"},
            {"status": "queued"},
            {"status": "submitted"},
            {"status": "cancelled"},
            {"source": "wrapper", "data": {"success": False, "error": "嵌套业务失败"}},
        ],
    )
    async def test_business_failure_blocks_dependents(self, result):
        """协程正常返回但业务拒绝时，也必须阻止依赖节点。"""
        dependent = AsyncMock(return_value={"success": True})

        async def _business_failure(params):
            return result

        builder = TaskGraphBuilder("业务失败")
        builder.add("gate", "业务闸口", ExecutorType.LOCAL, _business_failure, retry=1)
        builder.add("dependent", "依赖节点", ExecutorType.LOCAL, dependent, after=["gate"])

        graph = await TaskGraphExecutor().execute(builder.build())

        assert graph.nodes["gate"].status == NodeStatus.FAILED
        assert graph.nodes["dependent"].status == NodeStatus.SKIPPED
        dependent.assert_not_called()

    async def test_life_reminder_failure_is_promoted_to_top_level(self):
        """提醒落库失败不能被包装成 OMEGA 节点成功。"""
        from src.core.brain_exec_life import LifeExecutorMixin

        reminder_result = {"success": False, "error": "数据库只读"}
        with patch(
            "src.execution.life_automation.create_reminder",
            new=AsyncMock(return_value=reminder_result),
        ):
            result = await LifeExecutorMixin()._exec_life_service({"goal": "提醒我明天交报告"})

        assert result["success"] is False
        assert result["error"] == "数据库只读"
        assert TaskGraphExecutor._business_failure_reason(result) == "数据库只读"

    def test_builder_rejects_missing_dependency_and_fallback(self):
        """依赖或备选 ID 拼错时必须在执行前报错。"""
        missing_dependency = TaskGraphBuilder("缺失依赖")
        missing_dependency.add(
            "dangerous",
            "危险下游",
            ExecutorType.LOCAL,
            AsyncMock(return_value={"success": True}),
            after=["missing-risk-gate"],
        )
        with pytest.raises(ValueError, match="依赖不存在"):
            missing_dependency.build()

        missing_fallback = TaskGraphBuilder("缺失备选")
        missing_fallback.add(
            "primary",
            "主路径",
            ExecutorType.LOCAL,
            AsyncMock(return_value={"success": False}),
            fallback="missing-fallback",
        )
        with pytest.raises(ValueError, match="备选节点不存在"):
            missing_fallback.build()

    async def test_fallback_starts_only_after_primary_failure(self):
        """备选节点不能与主节点并发，成功后应恢复主依赖链。"""
        call_order = []

        async def _primary(params):
            call_order.append("primary")
            return {"success": False, "error": "主路径失败"}

        async def _fallback(params):
            call_order.append("fallback")
            return {"success": True, "channel": "phone"}

        async def _confirm(params):
            call_order.append("confirm")
            return {"success": True, "received": params["_upstream_results"]["primary"]}

        builder = TaskGraphBuilder("备选时序")
        builder.add("primary", "主路径", ExecutorType.API, _primary, retry=1, fallback="fallback")
        builder.add("fallback", "备选路径", ExecutorType.VOICE_CALL, _fallback, retry=1)
        builder.add("confirm", "确认", ExecutorType.LOCAL, _confirm, after=["primary"])

        graph = await TaskGraphExecutor().execute(builder.build())

        assert call_order == ["primary", "fallback", "confirm"]
        assert graph.is_success is True
        assert graph.nodes["primary"].result["fallback_node_id"] == "fallback"
        assert graph.nodes["primary"].result["success"] is True

    # ── B4. 失败传播 — A 失败 → B 被 SKIPPED ──────────

    async def test_failure_propagation(self):
        """A 失败后，依赖 A 的 B 应被标记为 SKIPPED。"""

        async def _fn_fail(params):
            raise RuntimeError("节点 A 爆炸了")

        async def _fn_b(params):
            return {"never": "reached"}

        b = TaskGraphBuilder("失败传播测试")
        b.add("a", "会失败的节点", ExecutorType.LOCAL, _fn_fail,
              timeout=5, retry=1)  # retry=1 避免重试拖慢测试
        b.add("b", "依赖A的节点", ExecutorType.LOCAL, _fn_b,
              after=["a"], timeout=5)
        graph = b.build()

        executor = TaskGraphExecutor()
        completed = await executor.execute(graph)

        assert completed.is_complete is True
        assert completed.is_success is False
        assert completed.nodes["a"].status == NodeStatus.FAILED
        assert completed.nodes["b"].status == NodeStatus.SKIPPED
        assert "依赖节点失败" in (completed.nodes["b"].error or "")

    # ── B5. get_progress() 统计 ──────────────────────────

    async def test_get_progress(self):
        """get_progress() 返回正确的统计数据。"""

        async def _ok(params):
            return "ok"

        async def _fail(params):
            raise ValueError("boom")

        b = TaskGraphBuilder("进度测试")
        b.add("s1", "成功1", ExecutorType.LOCAL, _ok, timeout=5)
        b.add("s2", "成功2", ExecutorType.LOCAL, _ok, timeout=5)
        b.add("f1", "失败1", ExecutorType.LOCAL, _fail, timeout=5, retry=1)
        b.add("dep", "被跳过", ExecutorType.LOCAL, _ok, after=["f1"], timeout=5)
        graph = b.build()

        executor = TaskGraphExecutor()
        completed = await executor.execute(graph)
        progress = completed.get_progress()

        assert progress["total"] == 4
        # s1 + s2 成功, dep 被跳过 → completed = 3
        assert progress["completed"] == 3
        assert progress["failed"] == 1
        assert progress["running"] == 0
        assert progress["pending"] == 0
        assert 0 <= progress["progress_pct"] <= 100
        assert isinstance(progress["nodes"], list)
        assert len(progress["nodes"]) == 4


class TestToolsExecutor:
    """OMEGA 工具节点必须传播沙箱的真实执行状态。"""

    async def test_code_task_propagates_sandbox_failure_without_awaiting_sync_method(self):
        from src.core.brain_exec_tools import ToolsExecutorMixin

        executor = ToolsExecutorMixin()
        sandbox_result = {"success": False, "error": "代码安全检查未通过"}
        with patch(
            "src.tools.code_tool.CodeTool.execute_python",
            return_value=sandbox_result,
        ) as execute_python:
            result = await executor._exec_code_task({"task": "print(1)"})

        assert result["success"] is False
        assert result["output"] == sandbox_result
        execute_python.assert_called_once_with("print(1)")


# ════════════════════════════════════════════════════════════
#  C. MultiPathExecutor 单元测试
# ════════════════════════════════════════════════════════════


class TestMultiPathExecutor:
    """MultiPathExecutor — API 降级、熔断。"""

    @pytest.fixture(autouse=True)
    async def _executor(self):
        self.executor = MultiPathExecutor()
        # 预先创建 httpx 客户端，以便测试中可以直接 mock _http_client 属性
        self.executor._get_http_client()
        yield
        await self.executor.close()

    # ── C1. API 路径执行成功 ──────────────────────────────

    async def test_api_success(self):
        """API 路径正常返回 JSON。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"price": 150.0}

        self.executor._http_client.request = AsyncMock(return_value=mock_resp)

        # 测试环境跳过 SSRF 检查（api.example.com 无法通过真实 DNS 解析）
        with patch("src.core.security.check_ssrf", return_value=True):
            result = await self.executor.execute_with_fallback(
                [{"type": "api", "endpoint": "https://api.example.com/quote",
                  "method": "GET", "params": {"symbol": "AAPL"}}],
                platform="test",
            )

        assert result.success is True
        assert result.execution_path == "api"
        assert result.data == {"price": 150.0}

    async def test_api_redirect_to_private_address_fails_before_second_request(self):
        """API 公网入口重定向到本机时必须失败关闭。"""
        first_response = MagicMock()
        first_response.status_code = 302
        first_response.next_request = httpx.Request("GET", "http://127.0.0.1/admin")
        first_response.aclose = AsyncMock()
        first_response.headers = {"content-type": "text/plain"}
        first_response.raise_for_status = MagicMock()
        self.executor._http_client.get = AsyncMock(return_value=first_response)
        self.executor._http_client.request = AsyncMock(return_value=first_response)
        self.executor._http_client.send = AsyncMock()

        with patch(
            "src.core.security.check_ssrf",
            side_effect=lambda value: "127.0.0.1" not in str(value),
        ):
            result = await self.executor.execute_with_fallback(
                [{"type": "api", "endpoint": "https://public.example/redirect"}],
                platform="test",
            )

        assert result.success is False
        self.executor._http_client.send.assert_not_awaited()

    def test_browser_targets_are_limited_to_registered_platform_hosts(self):
        """浏览器路径不得接受攻击者控制的任意公网域名。"""
        from src.core.executor import is_allowed_browser_target

        assert is_allowed_browser_target("https://www.dianping.com/shop/1") is True
        assert is_allowed_browser_target("https://attacker.example/redirect") is False
        assert is_allowed_browser_target("http://127.0.0.1:18790/api/v1/status") is False

    # ── C2. API 失败 → 降级到下一路径 ────────────────────

    async def test_api_failure_fallback(self):
        """API 抛异常 → 尝试下一条 human 策略。"""
        self.executor._http_client.request = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        # 第二条策略是 human，直接通知
        with patch.object(
            self.executor, "fallback_to_human", new_callable=AsyncMock
        ):
            result = await self.executor.execute_with_fallback(
                [
                    {"type": "api", "endpoint": "https://broken.example.com"},
                    {"type": "human", "description": "需要人工帮忙"},
                ],
                platform="test",
            )

        assert result.success is True
        assert result.execution_path == "human"
        assert len(result.attempts) == 2
        assert result.attempts[0]["success"] is False
        assert result.attempts[1]["success"] is True

    # ── C3. 熔断器触发后跳过 ─────────────────────────────

    async def test_circuit_breaker_skip(self):
        """熔断器触发后，对应路径被跳过。"""
        breaker = self.executor._circuit_breaker

        # 手动触发熔断 (threshold=3)
        for _ in range(3):
            breaker.record_failure("test_plat:api")

        assert breaker.is_available("test_plat:api") is False

        result = await self.executor.execute_with_fallback(
            [{"type": "api", "endpoint": "https://will.be.skipped.com"}],
            platform="test_plat",
        )

        assert result.success is False
        assert len(result.attempts) == 1
        assert result.attempts[0]["skipped"] is True
        assert "熔断器" in result.attempts[0]["reason"]


# ════════════════════════════════════════════════════════════
#  D. 流水线集成测试
# ════════════════════════════════════════════════════════════


class TestBrainPipeline:
    """
    Brain 集成测试 — 完整流水线 + 错误自愈。

    所有外部依赖（LLM、EventBus、模块 import）均 mock。
    """

    @pytest.fixture(autouse=True)
    def _reset_brain_singleton(self):
        """每个测试重置 brain 全局单例。"""
        import src.core.brain as brain_mod
        brain_mod._brain = None
        yield
        brain_mod._brain = None

    def _make_brain(self):
        """创建 Brain 实例，mock 掉外部依赖。"""
        with patch("src.core.brain.get_event_bus") as mock_bus_factory:
            mock_bus = MagicMock()
            mock_bus.publish = AsyncMock()
            mock_bus_factory.return_value = mock_bus

            from src.core.brain import OpenClawBrain
            brain = OpenClawBrain()

        return brain

    # ── D1. 完整流程: 投资分析 ────────────────────────────

    async def test_investment_full_pipeline(self):
        """
        '帮我分析AAPL' → IntentParser(fast) → TaskGraph(投资分析)
        → TaskGraphExecutor → TaskResult.success
        """
        brain = self._make_brain()

        # mock 掉投资分析节点的执行函数 — 替换为即时返回
        mock_research = AsyncMock(return_value={
            "source": "pydantic_engine",
            "data": {"symbol": "AAPL", "score": 8.5},
        })
        mock_ta = AsyncMock(return_value={
            "source": "ta_engine",
            "data": {"trend": "bullish"},
        })
        mock_quant = AsyncMock(return_value={
            "source": "quant",
            "data": {"momentum": 0.7},
        })
        mock_risk = AsyncMock(return_value={
            "source": "risk_manager", "approved": True,
        })
        mock_decision = AsyncMock(return_value={
            "source": "director_llm",
            "decision": "buy", "confidence": 0.85,
        })

        brain._exec_investment_research = mock_research
        brain._exec_ta_analysis = mock_ta
        brain._exec_quant_analysis = mock_quant
        brain._exec_risk_check = mock_risk
        brain._exec_director_decision = mock_decision

        # mock 掉上下文收集器和响应合成器，隔离 LiteLLM 调用（HI-384 修复）
        mock_ctx = MagicMock()
        mock_ctx.collect = AsyncMock(return_value={
            "user_profile": "", "conversation_summary": "",
            "recent_messages": "", "cross_domain_signals": "",
        })
        mock_synth = MagicMock()
        mock_synth.synthesize = AsyncMock(return_value=None)

        with patch("src.core.brain.get_context_collector", return_value=mock_ctx), \
             patch("src.core.brain.get_response_synthesizer", return_value=mock_synth):
            result = await brain.process_message(
                source="telegram",
                message="帮我分析AAPL",
            )

        # 验证流水线完整走通
        assert result.success is True, f"expected success, got error: {result.error}"
        assert result.intent is not None
        assert result.intent.task_type == TaskType.INVESTMENT
        assert "AAPL" in result.intent.known_params.get("symbol_hint", "")

        # 验证所有节点都被调用
        mock_research.assert_called_once()
        mock_ta.assert_called_once()
        mock_quant.assert_called_once()
        mock_risk.assert_called_once()
        mock_decision.assert_called_once()

        # 验证结果中包含各节点的数据
        assert result.final_result is not None
        assert isinstance(result.final_result, dict)
        # 合成器已 mock 为返回 None，结果应为原始节点数据
        assert "decision" in result.final_result

        # 验证进度
        assert result.graph_progress is not None
        assert result.graph_progress["total"] == 5
        assert result.graph_progress["completed"] == 5

    # ── D2. 错误传播 + 自愈路径 ──────────────────────────

    async def test_error_propagation_with_self_heal(self):
        """
        所有节点执行函数抛异常 → Brain._try_self_heal 被触发。
        自愈成功 → result.success 为 True, final_result 包含 healed 标记。
        """
        brain = self._make_brain()

        # mock IntentParser 使其返回一个可操作的意图
        mock_intent = ParsedIntent(
            goal="投资分析: AAPL",
            task_type=TaskType.INVESTMENT,
            known_params={"symbol_hint": "AAPL"},
            confidence=0.9,
        )
        brain._intent_parser.parse = AsyncMock(return_value=mock_intent)

        # _build_task_graph 抛异常 → 进入 except 分支 → 触发自愈
        brain._build_task_graph = AsyncMock(
            side_effect=RuntimeError("模块加载爆炸")
        )

        # 自愈成功
        with patch(
            "src.core.brain.OpenClawBrain._try_self_heal",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await brain.process_message(
                source="telegram",
                message="帮我分析AAPL",
            )

        # 自愈成功 → error 被清空, final_result 标记 healed
        assert result.success is True
        assert result.final_result == {"healed": True, "note": "已自动修复并重试"}
        assert result.error is None
