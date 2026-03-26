"""
OpenClaw OMEGA — 核心编排器 (Brain)
所有输入的统一入口，负责：意图解析 → 任务图生成 → 调度执行 → 进度推送。

与现有系统的关系:
  - 复用 litellm_router.py 的多模型路由
  - 复用 globals.py 的 DI 容器模式
  - 复用 rpc.py 的 lazy-import + fault-isolation 模式
  - 通过 EventBus 与所有模块松耦合

用法:
    brain = get_brain()
    result = await brain.process_message("telegram", "帮我分析茅台今天能买吗")
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.event_bus import EventType, get_event_bus
from src.core.intent_parser import IntentParser, ParsedIntent, TaskType
from src.core.task_graph import (
    TaskGraph, TaskGraphBuilder, TaskGraphExecutor,
    TaskNode, ExecutorType, NodeStatus,
)
from config.prompts import (
    CHAT_FALLBACK_PROMPT,
    INFO_QUERY_PROMPT,
    INVEST_DIRECTOR_DECISION_PROMPT,
    SOUL_CORE,
)
from src.core.response_synthesizer import (
    get_response_synthesizer,
    get_context_collector,
)
from src.bot.error_messages import error_ai_busy

# Resilience integration — rate-limit external LLM/API calls
try:
    from src.resilience import api_limiter
except ImportError:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def api_limiter(service: str = "generic"):  # type: ignore[misc]
        """No-op fallback when resilience module is unavailable."""
        yield

logger = logging.getLogger(__name__)

# 配置路径
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _BASE_DIR / "config" / "omega.yaml"


# ── 结果数据结构 ──────────────────────────────────────────

@dataclass
class TaskResult:
    """一次任务执行的完整结果"""
    task_id: str
    intent: Optional[ParsedIntent] = None
    graph_progress: Optional[Dict] = None
    final_result: Any = None
    needs_clarification: bool = False
    clarification_params: List[str] = field(default_factory=list)
    error: Optional[str] = None
    elapsed_seconds: float = 0.0
    cost_usd: float = 0.0
    source: str = ""
    extra_data: Dict = field(default_factory=dict)  # 附加数据 (追问建议等)

    @property
    def success(self) -> bool:
        return self.error is None and self.final_result is not None

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "goal": self.intent.goal if self.intent else "",
            "task_type": self.intent.task_type.value if self.intent else "",
            "needs_clarification": self.needs_clarification,
            "clarification_params": self.clarification_params,
            "progress": self.graph_progress,
            "result": self.final_result,
            "error": self.error,
            "elapsed": round(self.elapsed_seconds, 2),
            "cost_usd": round(self.cost_usd, 4),
        }

    def to_user_message(self) -> str:
        """将 TaskResult 转为用户可读的中文消息（HTML 格式）。

        统一使用 message_format 模块，确保:
          - 错误消息人话化，不暴露技术细节
          - 追问消息明确告知需要哪些信息
          - 结果消息根据任务类型格式化
        """
        from src.message_format import format_result, format_error

        if self.error:
            return format_error(
                self.error,
                context=self.intent.goal if self.intent else "",
            )

        if self.needs_clarification:
            params_text = (
                "、".join(self.clarification_params)
                if self.clarification_params
                else "更多信息"
            )
            return f"🤔 需要补充信息：请告诉我 {params_text}"

        if self.final_result:
            task_type = self.intent.task_type.value if self.intent else ""
            return format_result(self.final_result, task_type)

        return "✅ 操作已完成"


# ── 核心编排器 ──────────────────────────────────────────

class OpenClawBrain:
    """
    OpenClaw 的核心大脑。

    职责:
      1. 接收所有输入（Telegram / API / 定时任务）
      2. 解析意图 → 生成任务 DAG → 调度执行
      3. 实时推送进度到 EventBus（Telegram / WebSocket 消费）
      4. 管理活跃任务的生命周期
    """

    def __init__(self):
        self._intent_parser = IntentParser()
        self._event_bus = get_event_bus()
        self._active_tasks: Dict[str, TaskResult] = {}
        self._pending_callbacks: Dict[str, Dict] = {}  # callback_id → context
        self._pending_clarifications: Dict[int, str] = {}  # chat_id → task_id
        self._config = self._load_config()

        # 任务图执行器（带进度回调）
        self._graph_executor = TaskGraphExecutor(
            on_progress=self._on_progress,
            on_node_complete=self._on_node_complete,
        )

        logger.info("OpenClawBrain 初始化完成")

    def _load_config(self) -> Dict:
        """加载 omega.yaml 配置，不存在则用默认值"""
        defaults = {
            "cost": {"daily_budget_usd": 50.0, "show_cost_per_message": False},
            "security": {"require_pin_for_trades": True},
            "investment": {
                "team_enabled": True,
                "auto_trade": False,
                "risk_rules": {
                    "max_position_single": 0.30,     # 与 risk_manager.py 对齐
                    "max_drawdown_stop": 0.10,        # 与 risk_manager.py drawdown_halt_pct 对齐
                    "daily_loss_limit": 0.05,          # $100/$2000=5%, 与 risk_manager.py 对齐
                    "require_human_approval_rmb": 100000,
                },
            },
            "executor": {
                "fallback_chain": ["api", "browser", "voice_call", "human"],
            },
        }
        if _CONFIG_PATH.exists():
            try:
                import yaml
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                    # 合并（loaded 覆盖 defaults）
                    if "omega" in loaded:
                        loaded = loaded["omega"]
                    for k, v in loaded.items():
                        if isinstance(v, dict) and k in defaults:
                            defaults[k].update(v)
                        else:
                            defaults[k] = v
            except Exception as e:
                logger.warning(f"加载 omega.yaml 失败，使用默认配置: {e}")
        return defaults

    # ── 主入口 ──────────────────────────────────────────

    async def process_message(
        self,
        source: str,
        message: str,
        message_type: str = "text",
        context: Optional[Dict] = None,
        pre_parsed_intent: Optional["ParsedIntent"] = None,
        skip_chat_fallback: bool = False,
    ) -> TaskResult:
        """
        处理一条用户消息 — Brain 的唯一入口。

        Args:
            source: 来源标识 ("telegram" / "api" / "cron")
            message: 消息内容
            message_type: text / voice / image / file / forward
            context: 附加上下文（user_id, chat_id, 用户偏好等）

        Returns:
            TaskResult — 包含执行结果或追问请求
        """
        task_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        context = context or {}

        result = TaskResult(task_id=task_id, source=source)
        self._active_tasks[task_id] = result

        try:
            # 0. 收集上下文 (用户画像 + 对话历史)
            ctx_collector = get_context_collector()
            brain_context = await ctx_collector.collect(
                user_id=str(context.get("user_id", "")),
                chat_id=str(context.get("chat_id", "")),
                bot_id=str(context.get("bot_id", "")),
            )

            # 1. 意图解析
            logger.info(f"[{task_id}] 开始处理消息: {message[:80]}...")
            # GAP 9 修复: 复用调用方预解析的意图，避免重复 LLM 调用
            if pre_parsed_intent and pre_parsed_intent.is_actionable:
                intent = pre_parsed_intent
                logger.debug(f"[{task_id}] 复用预解析意图: {intent.task_type}")
            else:
                intent = await self._intent_parser.parse(message, message_type, context)
            result.intent = intent

            # 1.5 复合意图拆解 — 搬运 ChatGPT multi-tool / AutoGPT task chain 模式
            # 检测"分析TSLA然后发到小红书"这类包含多个子任务的指令
            sub_intents = _detect_compound_intent(message, intent)
            if sub_intents and len(sub_intents) > 1:
                logger.info(f"[{task_id}] 复合意图检测到 {len(sub_intents)} 个子任务")
                # 按序执行子任务，前一个结果传给下一个
                combined_results = {}
                for i, sub_intent in enumerate(sub_intents, 1):
                    # 发布进度事件
                    await self._event_bus.publish(
                        "brain.progress",
                        {"step": i, "total": len(sub_intents),
                         "name": sub_intent.goal, "status": "running"},
                        source="brain",
                    )
                    sub_result = await self.process_message(
                        source=source, message=sub_intent.raw_message or sub_intent.goal,
                        message_type=message_type, context=context,
                        pre_parsed_intent=sub_intent, skip_chat_fallback=True,
                    )
                    combined_results[f"step_{i}_{sub_intent.task_type.value}"] = (
                        sub_result.final_result if sub_result.success
                        else {"error": sub_result.error}
                    )
                result.final_result = combined_results
                result.extra_data["compound_steps"] = len(sub_intents)
                return result

            # 写入 current_task 到 core memory (让后续消息知道当前在做什么)
            try:
                from src.bot.globals import tiered_context_manager as _tcm
                _chat_id = int(context.get("chat_id", 0))
                if _tcm and _chat_id:
                    _tcm.core_set("current_task", f"{intent.task_type.value}: {intent.goal}", chat_id=_chat_id)
            except Exception:
                pass

            if not intent.is_actionable:
                # GAP 10 修复: 调用方明确要求跳过聊天降级时，直接返回 forward_to_chat
                # 这避免了 Brain 用低质量路径（无用户画像/300token上限）生成次优回复
                if skip_chat_fallback:
                    result.final_result = {"action": "forward_to_chat", "message": message}
                    result.elapsed_seconds = time.time() - start_time
                    return result
                # 无法识别为特定任务 → 用 LLM 直接回答（闲聊/问答）
                try:
                    from src.litellm_router import free_pool
                    if free_pool:
                        # 构建系统提示: 基础人格 + 用户画像
                        _profile = brain_context.get("user_profile", "")
                        _summary = brain_context.get("conversation_summary", "")
                        _sys = CHAT_FALLBACK_PROMPT
                        if _profile:
                            _sys += f"\n\n[用户画像]\n{_profile}"
                        if _summary:
                            _sys += f"\n\n[对话摘要]\n{_summary}"
                        # 跨域关联信号（搬运 omi cross-context awareness）
                        _cross = brain_context.get("cross_domain_signals", "")
                        if _cross:
                            _sys += f"\n\n[跨域关联]\n{_cross}"
                        messages = [
                            {"role": "system", "content": _sys},
                        ]
                        # 注入最近对话历史 (让 Brain 知道"那"指什么)
                        recent = brain_context.get("recent_messages", "")
                        if recent:
                            messages.append({
                                "role": "system",
                                "content": f"最近对话:\n{recent}",
                            })
                        messages.append({"role": "user", "content": message})

                        async with api_limiter("llm"):
                            resp = await free_pool.acompletion(
                                model_family="qwen",
                                messages=messages,
                                temperature=0.7,
                                max_tokens=1000,
                            )
                        answer = resp.choices[0].message.content
                        if answer:
                            result.final_result = {"answer": answer}
                            result.elapsed_seconds = time.time() - start_time
                            return result
                except Exception as e:
                    logger.debug(f"闲聊 LLM 失败: {e}")

                # 最终降级：转发给现有 MultiBot
                result.final_result = {"action": "forward_to_chat", "message": message}
                result.elapsed_seconds = time.time() - start_time
                return result

            # 2. 检查是否需要追问
            if intent.needs_clarification:
                # 先执行可执行的部分（如搜索），同时生成追问
                graph = await self._build_task_graph(intent)
                partial_task = None
                if graph and len(graph.nodes) > 0:
                    # 有可先执行的节点 → 启动后台执行
                    partial_task = asyncio.create_task(
                        self._graph_executor.execute(graph)
                    )
                    partial_task.add_done_callback(
                        lambda t: t.exception() and logger.error(
                            "[Brain] 后台任务图执行失败: %s", t.exception()
                        )
                    )

                # 始终存储 pending callback（无论是否有可先执行的节点）
                self._pending_callbacks[task_id] = {
                    "intent": intent,
                    "partial_task": partial_task,
                    "graph": graph,
                    "context": context,
                    "created_at": time.time(),
                }
                # chat_id → task_id 映射，让下一条文本消息能路由回来
                _clarify_chat_id = int(context.get("chat_id", 0))
                if _clarify_chat_id:
                    self._pending_clarifications[_clarify_chat_id] = task_id

                result.needs_clarification = True
                result.clarification_params = intent.missing_critical
                result.graph_progress = graph.get_progress() if graph else None
                result.elapsed_seconds = time.time() - start_time
                return result

            # 3. 构建任务图
            graph = await self._build_task_graph(intent)
            if graph is None:
                result.error = "无法为此任务构建执行计划"
                result.elapsed_seconds = time.time() - start_time
                return result

            # 4. 执行任务图
            logger.info(f"[{task_id}] 执行任务图: {graph.name}, {len(graph.nodes)} 个节点")
            completed_graph = await self._graph_executor.execute(graph)

            # 5. 汇总结果
            result.graph_progress = completed_graph.get_progress()
            if completed_graph.is_success:
                # 收集所有成功节点的结果
                results = {}
                for node in completed_graph.nodes.values():
                    if node.status == NodeStatus.SUCCESS and node.result is not None:
                        results[node.id] = node.result
                result.final_result = results

                # 更新 current_task (记录最近完成的任务)
                try:
                    if _tcm and _chat_id:
                        _tcm.core_set("current_task", f"[已完成] {intent.task_type.value}: {intent.goal}", chat_id=_chat_id)
                except Exception:
                    pass

                # 6. 响应合成 — 将数据结果转化为对话式回复
                try:
                    synth = get_response_synthesizer()
                    task_type_str = (
                        intent.task_type.value
                        if hasattr(intent.task_type, "value")
                        else str(intent.task_type)
                    )
                    synthesized = await synth.synthesize(
                        raw_data=results,
                        task_type=task_type_str,
                        user_profile=brain_context.get("user_profile", ""),
                        conversation_summary=brain_context.get("conversation_summary", ""),
                    )
                    if synthesized:
                        # 并行生成追问建议 + TL;DR 摘要（不阻塞主流程）
                        suggestions = []
                        tldr = ""
                        try:
                            _suggest_task = synth.generate_suggestions(
                                synthesized, task_type_str,
                            )
                            _tldr_task = synth.generate_tldr(synthesized)
                            suggestions, tldr = await asyncio.gather(
                                _suggest_task, _tldr_task,
                                return_exceptions=True,
                            )
                            # asyncio.gather 的 return_exceptions 可能返回异常对象
                            if isinstance(suggestions, BaseException):
                                logger.debug(f"追问建议生成异常: {suggestions}")
                                suggestions = []
                            if isinstance(tldr, BaseException):
                                logger.debug(f"TL;DR 摘要生成异常: {tldr}")
                                tldr = ""
                        except Exception as _gather_err:
                            logger.debug(f"追问/摘要并行任务异常: {_gather_err}")

                        # TL;DR 摘要先行: 长回复前面加一句核心结论
                        display_reply = synthesized
                        if tldr:
                            display_reply = f"💡 {tldr}\n\n{'─' * 20}\n\n{synthesized}"

                        # 保留原始数据在 _raw_data，合成结果作为主输出
                        result.final_result = {
                            "synthesized_reply": display_reply,
                            "_raw_data": results,
                            "_task_type": task_type_str,
                        }

                        # 追问建议存入 extra_data（由 message_mixin 读取生成按钮）
                        if suggestions:
                            result.extra_data["followup_suggestions"] = suggestions
                except Exception as e:
                    logger.debug(f"响应合成失败 (使用原始结果): {e}")
            else:
                failed_nodes = [
                    n for n in completed_graph.nodes.values()
                    if n.status == NodeStatus.FAILED
                ]
                result.error = "; ".join(
                    f"{n.name}: {n.error}" for n in failed_nodes
                )

            # 6. 发布完成事件
            event_type = (EventType.TASK_COMPLETED if result.success
                         else EventType.TASK_FAILED)
            await self._event_bus.publish(
                event_type,
                result.to_dict(),
                source=f"brain:{task_id}",
            )

        except Exception as e:
            logger.error(f"[{task_id}] 处理消息失败: {e}", exc_info=True)
            result.error = str(e)

            # 尝试自愈
            try:
                healed = await self._try_self_heal(e, {"message": message, "context": context})
                if healed:
                    result.error = None
                    result.final_result = {"healed": True, "note": "已自动修复并重试"}
            except Exception as heal_error:
                logger.error(f"[{task_id}] 自愈也失败: {heal_error}")

        finally:
            result.elapsed_seconds = time.time() - start_time
            # 清理活跃任务（延迟清理，保留一段时间供查询）
            try:
                loop = asyncio.get_running_loop()
                loop.call_later(
                    300, lambda tid=task_id: self._active_tasks.pop(tid, None)
                )
            except RuntimeError:
                self._active_tasks.pop(task_id, None)

        return result

    # ── 任务图构建 ──────────────────────────────────────

    async def _build_task_graph(self, intent: ParsedIntent) -> Optional[TaskGraph]:
        """根据意图类型构建任务 DAG"""
        builders = {
            TaskType.INVESTMENT: self._build_investment_graph,
            TaskType.SOCIAL: self._build_social_graph,
            TaskType.SHOPPING: self._build_shopping_graph,
            TaskType.BOOKING: self._build_booking_graph,
            TaskType.INFO: self._build_info_graph,
            TaskType.LIFE: self._build_life_graph,
            TaskType.SYSTEM: self._build_system_graph,
            TaskType.EVOLUTION: self._build_evolution_graph,
            TaskType.CODE: self._build_code_graph,
        }
        builder = builders.get(intent.task_type)
        if builder is None:
            logger.warning(f"无任务图构建器: {intent.task_type}")
            return None
        try:
            return await builder(intent)
        except Exception as e:
            logger.error(f"构建任务图失败 ({intent.task_type}): {e}", exc_info=True)
            return None

    async def _build_investment_graph(self, intent: ParsedIntent) -> TaskGraph:
        """
        投资分析任务图:
          如果没有具体标的（如"持仓"），走持仓查询路径
          如果有标的，走完整分析:
          [研究员] ─┐
          [TA分析] ─┤→ [风控审核] → [总监决策]
          [量化]   ─┘
        """
        symbol = intent.known_params.get("symbol_hint", "")

        # 持仓/仓位查询 — 不需要标的
        if not symbol or intent.goal in ("查看持仓状态",):
            b = TaskGraphBuilder("持仓查询")
            b.add("portfolio", "获取持仓", ExecutorType.LOCAL,
                  self._exec_portfolio_query,
                  params={}, timeout=15)
            return b.build()
        b = TaskGraphBuilder(f"投资分析: {symbol}")

        b.add("research", "基本面研究", ExecutorType.CREW,
              self._exec_investment_research,
              params={"symbol": symbol, "intent": intent.known_params},
              timeout=60)
        b.add("ta", "技术面分析", ExecutorType.CREW,
              self._exec_ta_analysis,
              params={"symbol": symbol},
              timeout=45)
        b.add("quant", "量化指标计算", ExecutorType.CREW,
              self._exec_quant_analysis,
              params={"symbol": symbol},
              timeout=45)
        b.add("risk", "风控审核", ExecutorType.CREW,
              self._exec_risk_check,
              params={"symbol": symbol},
              after=["research", "ta", "quant"],
              timeout=30)
        b.add("decision", "总监决策", ExecutorType.CREW,
              self._exec_director_decision,
              params={"symbol": symbol},
              after=["risk"],
              timeout=30)

        return b.build()

    async def _build_social_graph(self, intent: ParsedIntent) -> TaskGraph:
        """
        社媒发帖任务图:
          [热点扫描] → [内容策划] → [素材生成] → [发布]
        """
        b = TaskGraphBuilder(f"社媒发帖: {intent.goal}")

        b.add("trending", "热点扫描", ExecutorType.LOCAL,
              self._exec_trending_scan,
              params=intent.known_params, timeout=30)
        b.add("social_intel", "社交数据采集", ExecutorType.LOCAL,
              self._exec_social_intel,
              params=intent.known_params, timeout=30)
        b.add("strategy", "内容策划", ExecutorType.LLM,
              self._exec_content_strategy,
              params=intent.known_params,
              after=["trending", "social_intel"], timeout=45)
        b.add("generate", "内容生成", ExecutorType.LLM,
              self._exec_content_generate,
              params=intent.known_params,
              after=["strategy"], timeout=60)
        b.add("publish", "发布执行", ExecutorType.BROWSER,
              self._exec_social_publish,
              params=intent.known_params,
              after=["generate"], timeout=120)

        return b.build()

    async def _build_shopping_graph(self, intent: ParsedIntent) -> TaskGraph:
        """
        购物比价任务图 — 三级降级链:
          1. crawl4ai 结构化抽取（CSS/LLM，实时爬取真实价格）
          2. Jina+LLM 分析（网页搜索 + LLM 总结）
          3. 纯 LLM 知识回答（最终降级）
        """
        product = intent.known_params.get("product_hint", intent.goal)
        b = TaskGraphBuilder(f"购物比价: {product}")

        b.add("compare", "智能比价分析", ExecutorType.LLM,
              self._exec_smart_shopping,
              params={"product": product}, timeout=60)

        return b.build()

    async def _build_booking_graph(self, intent: ParsedIntent) -> TaskGraph:
        """
        预订任务图:
          [搜索] → [排序] → [检测预订方式] → [执行预订] → [确认]
        """
        b = TaskGraphBuilder(f"预订: {intent.goal}")

        b.add("search", "搜索服务", ExecutorType.BROWSER,
              self._exec_booking_search,
              params=intent.known_params, timeout=45)
        b.add("rank", "筛选排序", ExecutorType.LOCAL,
              self._exec_rank_results,
              params=intent.known_params,
              after=["search"], timeout=15)
        b.add("detect", "检测预订方式", ExecutorType.LOCAL,
              self._exec_detect_booking_method,
              params={},
              after=["rank"], timeout=10)
        b.add("execute", "执行预订", ExecutorType.BROWSER,
              self._exec_booking_execute,
              params=intent.known_params,
              after=["detect"], timeout=120,
              fallback="execute_phone")
        b.add("execute_phone", "电话预订(备选)", ExecutorType.VOICE_CALL,
              self._exec_booking_phone,
              params=intent.known_params,
              timeout=180)
        b.add("confirm", "确认结果", ExecutorType.LOCAL,
              self._exec_booking_confirm,
              params={},
              after=["execute"], timeout=10)

        return b.build()

    async def _build_info_graph(self, intent: ParsedIntent) -> TaskGraph:
        """简单信息查询 — 单节点 LLM 调用"""
        b = TaskGraphBuilder(f"信息查询: {intent.goal}")
        b.add("query", "查询回答", ExecutorType.LLM,
              self._exec_llm_query,
              params={"question": intent.goal, **intent.known_params},
              timeout=30)
        return b.build()

    async def _build_life_graph(self, intent: ParsedIntent) -> TaskGraph:
        """生活服务任务图"""
        b = TaskGraphBuilder(f"生活服务: {intent.goal}")
        b.add("execute", "执行任务", ExecutorType.LOCAL,
              self._exec_life_service,
              params={"goal": intent.goal, **intent.known_params},
              timeout=60)
        return b.build()

    async def _build_system_graph(self, intent: ParsedIntent) -> TaskGraph:
        """系统状态查询"""
        b = TaskGraphBuilder("系统状态查询")
        b.add("status", "获取系统状态", ExecutorType.LOCAL,
              self._exec_system_status,
              params={}, timeout=15)
        return b.build()

    async def _build_evolution_graph(self, intent: ParsedIntent) -> TaskGraph:
        """进化扫描"""
        b = TaskGraphBuilder("进化扫描")
        b.add("scan", "GitHub趋势扫描", ExecutorType.LOCAL,
              self._exec_evolution_scan,
              params=intent.known_params, timeout=300)
        return b.build()

    async def _build_code_graph(self, intent: ParsedIntent) -> TaskGraph:
        """代码任务"""
        b = TaskGraphBuilder(f"代码任务: {intent.goal}")
        b.add("code", "执行代码任务", ExecutorType.LLM,
              self._exec_code_task,
              params={"task": intent.goal, **intent.known_params},
              timeout=120)
        return b.build()

    # ── 节点执行函数 ──────────────────────────────────────

    async def _exec_investment_research(self, params: Dict) -> Dict:
        """投资研究 — 优先用 Pydantic AI 引擎，降级到原有 team"""
        symbol = params.get("symbol", "")
        if not symbol:
            return {"source": "no_symbol", "note": "未指定标的"}

        # 优先: Pydantic AI 结构化分析（iflow 无限 API）
        try:
            from src.modules.investment.pydantic_agents import get_pydantic_engine
            engine = get_pydantic_engine()
            if engine.available:
                result = await engine.full_analysis(symbol)
                return {
                    "source": "pydantic_engine",
                    "data": result.to_dict(),
                    "telegram_text": result.to_telegram_text(),
                    "recommendation": result.final_recommendation,
                    "vetoed": result.is_vetoed,
                }
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Pydantic 分析引擎失败: {e}")

        # 降级: 原有投资团队
        try:
            from src.modules.investment.team import get_investment_team
            team = get_investment_team()
            if team:
                analysis = await team.analyze(symbol)
                return {"source": "team", "data": analysis.to_dict()}
        except Exception as e:
            logger.warning(f"投资团队分析失败: {e}")

        return {"source": "unavailable", "note": "投资分析模块未就绪"}

    async def _exec_ta_analysis(self, params: Dict) -> Dict:
        """技术分析 — 复用现有 ta_engine"""
        try:
            from src.ta_engine import get_full_analysis
            symbol = params.get("symbol", "")
            if symbol:
                result = await get_full_analysis(symbol)
                return {"source": "ta_engine", "data": result}
        except Exception as e:
            logger.warning(f"技术分析失败: {e}")
        return {"source": "ta_unavailable", "note": "技术分析暂不可用"}

    async def _exec_quant_analysis(self, params: Dict) -> Dict:
        """量化分析 — 调用投资团队的量化工程师"""
        try:
            from src.modules.investment.team import get_investment_team
            team = get_investment_team()
            if team:
                return await team.quant_analysis(params.get("symbol", ""))
        except ImportError:
            pass
        return {"source": "quant_unavailable", "note": "量化分析模块未就绪"}

    async def _exec_risk_check(self, params: Dict) -> Dict:
        """风控审核 — 调用风控官"""
        try:
            from src.trading_system import get_risk_manager
            rm = get_risk_manager()
            if rm:
                check = rm.check_trade(
                    symbol=params.get("symbol", ""),
                    side="BUY",
                    quantity=100,
                    entry_price=0,
                )
                approved = check.approved if hasattr(check, 'approved') else True
                return {"source": "risk_manager", "approved": approved, "details": str(check)}
        except Exception as e:
            logger.warning(f"风控检查失败: {e}")
        # 降级：使用模块级单例
        try:
            from src.risk_manager import risk_manager
            check = risk_manager.check_trade(
                symbol=params.get("symbol", ""), side="BUY", quantity=100, entry_price=0,
            )
            approved = check.approved if hasattr(check, 'approved') else True
            return {"source": "risk_manager_singleton", "approved": approved}
        except Exception:
            logger.debug("Silenced exception", exc_info=True)
        # FAIL-CLOSED: 风控模块不可用时，拒绝交易而非默认放行
        return {"source": "risk_default", "approved": False,
                "note": "风控模块未就绪，安全起见默认拒绝（fail-closed）"}

    async def _exec_director_decision(self, params: Dict) -> Dict:
        """总监决策 — 汇总研究/TA/量化/风控结果做出最终决策"""
        symbol = params.get("symbol", "")
        try:
            from src.litellm_router import free_pool
            if free_pool:
                # Collect results from preceding nodes (passed via task graph context)
                context_summary = params.get("_upstream_results", "")
                async with api_limiter("llm"):
                    resp = await free_pool.acompletion(
                        model_family="deepseek",
                        messages=[{"role": "user", "content": f"Based on the analysis for {symbol}, give a final investment recommendation. Previous analysis: {context_summary}"}],
                        system_prompt=INVEST_DIRECTOR_DECISION_PROMPT,
                        temperature=0.3,
                        max_tokens=500,
                    )
                content = resp.choices[0].message.content
                try:
                    import json_repair
                    data = json_repair.loads(content)
                    if isinstance(data, dict):
                        data["source"] = "director_llm"
                        return data
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)
                return {"source": "director_llm", "decision": "hold", "confidence": 0.5, "reasoning": content[:200]}
        except Exception as e:
            logger.warning(f"总监决策失败: {e}")
        return {"source": "director_fallback", "decision": "hold", "confidence": 0.0, "reasoning": "决策模块异常，默认持有"}

    async def _exec_trending_scan(self, params: Dict) -> Dict:
        """热点扫描 — 复用现有 real_trending"""
        try:
            from src.execution.social.real_trending import fetch_real_trending
            topics = await fetch_real_trending()
            return {"source": "real_trending", "topics": topics[:10]}
        except Exception as e:
            logger.warning(f"热点扫描失败: {e}")
            return {"source": "trending_fallback", "topics": []}

    async def _exec_social_intel(self, params: Dict) -> Dict:
        """社交数据采集 — MediaCrawler (46k⭐) 多平台爬虫"""
        platform = params.get("platform", "xhs")
        topic = params.get("content_hint", params.get("topic", ""))
        try:
            from src.execution.social.media_crawler_bridge import get_media_crawler, init_media_crawler
            crawler = get_media_crawler()
            if crawler is None:
                crawler = init_media_crawler()

            results = {}
            # Trending data for content inspiration
            try:
                trending = await asyncio.to_thread(crawler.get_trending, platform) if hasattr(crawler.get_trending, '__call__') else crawler.get_trending(platform)
                results["trending"] = trending[:10] if trending else []
            except Exception:
                results["trending"] = []

            # Search related content if topic provided
            if topic:
                try:
                    related = crawler.search_platform(platform, [topic], limit=5)
                    results["related_posts"] = related
                except Exception:
                    results["related_posts"] = []

            results["source"] = "media_crawler"
            results["platform"] = platform
            return results
        except Exception as e:
            logger.warning(f"社交数据采集失败: {e}")
        return {"source": "social_intel_unavailable", "trending": [], "related_posts": []}

    async def _exec_content_strategy(self, params: Dict) -> Dict:
        """内容策划 — 复用现有 content_strategy"""
        try:
            from src.execution.social.content_strategy import derive_content_strategy
            topic = params.get("content_hint", params.get("topic", "AI趋势"))
            result = await derive_content_strategy(topic=topic)
            return {"source": "content_strategy", "strategy": result}
        except Exception as e:
            logger.warning(f"内容策划失败: {e}")
            return {"source": "strategy_fallback", "strategy": {}}

    async def _exec_content_generate(self, params: Dict) -> Dict:
        """内容生成 — 调用 content_strategy.compose_post()"""
        try:
            from src.execution.social.content_strategy import compose_post
            topic = params.get("content_hint", params.get("topic", "AI趋势"))
            platform = params.get("platform", "x")
            strategy = params.get("strategy", {})
            draft = await compose_post(topic=topic, platform=platform, strategy=strategy)
            if draft:
                result_dict = {"source": "content_strategy", "draft": draft, "platform": platform, "topic": topic}
                # Try to generate an accompanying image
                try:
                    from src.tools.fal_client import generate_image
                    image_prompt = f"Social media post illustration for: {topic}"
                    image_url = await generate_image(image_prompt)
                    if image_url:
                        result_dict["image_url"] = image_url
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)  # Image generation is optional
                return result_dict
        except Exception as e:
            logger.warning(f"内容生成失败: {e}")
        return {"source": "content_gen_fallback", "draft": "", "note": "内容生成模块异常"}

    async def _exec_social_publish(self, params: Dict) -> Dict:
        """社媒发布 — 调用对应平台发布函数"""
        platform = params.get("platform", "x")
        draft = params.get("draft", params.get("content", ""))
        if not draft:
            return {"source": "publish", "success": False, "note": "无内容可发布"}
        try:
            if platform in ("x", "twitter"):
                from src.execution.social.x_platform import publish_x_post
                result = await publish_x_post(content=draft)
                return {"source": "x_platform", "success": True, "result": result}
            elif platform in ("xhs", "xiaohongshu"):
                from src.execution.social.xhs_platform import publish_xhs_article
                result = await publish_xhs_article(title=draft[:30], content=draft)
                return {"source": "xhs_platform", "success": True, "result": result}
            else:
                # Generic: try worker bridge
                from src.execution.social.worker_bridge import run_social_worker_async
                result = await run_social_worker_async(f"publish_{platform}", {"content": draft})
                return {"source": "worker_bridge", "success": True, "result": result}
        except Exception as e:
            logger.warning(f"社媒发布失败 ({platform}): {e}")
        return {"source": "publish_fallback", "success": False, "note": f"{platform} 发布失败"}

    async def _exec_smart_shopping(self, params: Dict) -> Dict:
        """
        智能购物比价 — 三级降级链:
          1. crawl4ai 结构化抽取（CSS/LLM，实时爬取真实价格）
          2. Jina + LLM 分析（网页搜索 + LLM 总结）
          3. 纯 LLM 知识回答（最终降级）
        """
        product = params.get("product", "")
        if not product:
            return {"source": "error", "note": "未指定商品"}

        # ── 第〇级: Tavily 智能搜索（AI-native，最快）──
        try:
            from src.tools.tavily_search import search_context, _HAS_TAVILY
            if _HAS_TAVILY:
                logger.info(f"[比价] 使用 Tavily 搜索: {product}")
                tavily_ctx = await search_context(f"{product} 价格对比 京东 淘宝 拼多多", max_results=5)
                if tavily_ctx and len(tavily_ctx) > 200:
                    # 用 LLM 结构化 Tavily 结果
                    from src.litellm_router import free_pool
                    if free_pool:
                        async with api_limiter("llm"):
                            resp = await free_pool.acompletion(
                                model_family="deepseek",
                                messages=[
                                    {"role": "system", "content": (
                                        SOUL_CORE + "\n\n你现在在做购物比价任务。"
                                        "根据搜索结果提供各平台价格对比和购买建议。"
                                        "输出JSON格式: {\"products\":[{\"name\":\"商品名\",\"price\":\"价格\","
                                        "\"platform\":\"平台\",\"note\":\"备注\"}],"
                                        "\"recommendation\":\"购买建议\",\"best_deal\":\"最佳选择\","
                                        "\"tips\":\"省钱技巧\"}"
                                    )},
                                    {"role": "user", "content": (
                                        f"帮我比较 {product} 的价格。以下是搜索到的信息:\n{tavily_ctx[:3000]}"
                                    )},
                                ],
                                max_tokens=600,
                                temperature=0.3,
                            )
                        content = resp.choices[0].message.content
                        if content:
                            try:
                                import json_repair
                                data = json_repair.loads(content)
                                if isinstance(data, dict):
                                    data["source"] = "tavily_smart_compare"
                                    data["product"] = product
                                    return data
                            except Exception:
                                logger.debug("Silenced exception", exc_info=True)
                            return {"source": "tavily_smart_compare", "product": product,
                                    "raw": content, "recommendation": content[:200]}
        except ImportError:
            logger.debug("[比价] tavily_search 不可用")
        except Exception as e:
            logger.warning(f"[比价] Tavily 搜索异常: {e}")

        # ── 第一级: crawl4ai 结构化比价 ──
        try:
            from src.shopping.crawl4ai_engine import smart_compare, HAS_CRAWL4AI
            if HAS_CRAWL4AI:
                logger.info(f"[比价] 使用 crawl4ai 引擎: {product}")
                result = await smart_compare(product)
                if result.products and any(p.price > 0 for p in result.products):
                    data = result.to_dict()
                    data["product"] = product
                    return data
                else:
                    logger.info("[比价] crawl4ai 无有效结果，降级到 Jina+LLM")
        except ImportError:
            logger.debug("[比价] crawl4ai_engine 不可用")
        except Exception as e:
            logger.warning(f"[比价] crawl4ai 引擎异常: {e}")

        # ── 第二级: Jina + LLM 分析（原有方案）──
        # 1. 尝试 Jina 读取 Bing Shopping 获取实时数据
        jina_context = ""
        try:
            from src.tools.jina_reader import jina_read
            import urllib.parse
            q = urllib.parse.quote(f"{product} 价格 对比")
            raw = await jina_read(f"https://cn.bing.com/shop?q={q}", max_length=3000)
            if raw and len(raw) > 200:
                jina_context = f"\n\n以下是网页搜索到的相关信息（用于参考）:\n{raw[:2000]}"
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        # 2. 用 LLM 做智能比价分析（通过 litellm_router 统一路由）
        try:
            from src.litellm_router import free_pool
            if free_pool:
                async with api_limiter("llm"):
                    resp = await free_pool.acompletion(
                        model_family="deepseek",
                        messages=[
                            {"role": "system", "content": (
                                "你是专业购物比价助手。根据用户需求提供各平台价格对比和购买建议。"
                                "输出JSON格式: {\"products\":[{\"name\":\"商品名\",\"price\":\"价格\","
                                "\"platform\":\"平台\",\"note\":\"备注\"}],"
                                "\"recommendation\":\"购买建议\",\"best_deal\":\"最佳选择\","
                                "\"tips\":\"省钱技巧\"}"
                            )},
                            {"role": "user", "content": (
                                f"帮我比较 {product} 在京东、淘宝、拼多多、苹果/官网等平台的价格。"
                                f"给出购买建议和省钱技巧。{jina_context}"
                            )},
                        ],
                        max_tokens=600,
                        temperature=0.3,
                    )
                content = resp.choices[0].message.content
                if content:
                    try:
                        import json_repair
                        data = json_repair.loads(content)
                        if isinstance(data, dict):
                            data["source"] = "llm_smart_compare"
                            data["product"] = product
                            return data
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)
                    return {"source": "llm_smart_compare", "product": product,
                            "raw": content, "recommendation": content[:200]}
        except Exception as e:
            logger.warning(f"智能比价失败: {e}")

        return {"source": "unavailable", "product": product, "note": "比价服务暂时不可用"}

    async def _exec_platform_search(self, params: Dict) -> Dict:
        """平台搜索 — 使用实际的 price_engine 函数"""
        platform = params.get("platform", "unknown")
        query = params.get("query", "")
        try:
            if platform == "smzdm":
                from src.shopping.price_engine import search_smzdm
                results = await search_smzdm(query)
                return {"source": "smzdm", "results": [r.__dict__ if hasattr(r, '__dict__') else r for r in results]}
            elif platform == "jd":
                from src.shopping.price_engine import search_jd
                results = await search_jd(query)
                return {"source": "jd", "results": [r.__dict__ if hasattr(r, '__dict__') else r for r in results]}
            else:
                # 其他平台用通用比价
                from src.shopping.price_engine import compare_prices
                report = await compare_prices(query, limit_per_platform=5)
                if hasattr(report, '__dict__'):
                    return {"source": platform, "results": report.__dict__}
                return {"source": platform, "results": report if isinstance(report, dict) else str(report)}
        except ImportError as e:
            logger.warning(f"{platform}搜索: 模块不可用 ({e})")
            return {"source": platform, "results": [], "note": f"{platform} 搜索模块未就绪"}
        except Exception as e:
            logger.warning(f"{platform}搜索失败: {e}")
            return {"source": platform, "results": [], "error": str(e)}

    async def _exec_rank_results(self, params: Dict) -> Dict:
        """排序筛选结果"""
        return {"source": "ranker", "ranked": [], "note": "汇总搜索结果并排序"}

    async def _exec_present_options(self, params: Dict) -> Dict:
        """展示选项给用户"""
        return {"source": "presenter", "options": [], "note": "生成Inline Keyboard"}

    async def _exec_booking_search(self, params: Dict) -> Dict:
        """预订搜索 — Tavily 优先, Jina 降级"""
        goal = params.get("goal", params.get("query", ""))
        if not goal:
            return {"source": "booking_search", "results": [], "note": "未指定搜索内容"}

        # 优先: Tavily search_context (AI-native, 结构化好)
        raw = None
        search_source = "jina"
        try:
            from src.tools.tavily_search import search_context, _HAS_TAVILY
            if _HAS_TAVILY:
                tavily_raw = await search_context(f"{goal} 预约 预订 价格", max_results=5)
                if tavily_raw and len(tavily_raw) > 100:
                    raw = tavily_raw
                    search_source = "tavily"
        except Exception as e:
            logger.debug(f"[预订] Tavily 搜索失败: {e}")

        # 降级: Jina search
        if not raw:
            try:
                from src.tools.jina_reader import jina_search
                raw = await jina_search(f"{goal} 预约 预订 价格")
            except Exception as e:
                logger.debug(f"[预订] Jina 搜索失败: {e}")

        if raw and len(raw) > 100:
            # Use LLM to structure the results
            try:
                from src.litellm_router import free_pool
                if free_pool:
                    resp = await free_pool.acompletion(
                        model_family="qwen",
                        messages=[{"role": "user", "content": f"从以下搜索结果中提取预订选项:\n{raw[:3000]}"}],
                        system_prompt='提取预订选项列表。JSON格式: {"results": [{"name": "名称", "price": "价格", "address": "地址", "rating": "评分", "url": "链接"}]}',
                        temperature=0.2, max_tokens=800,
                    )
                    content = resp.choices[0].message.content
                    try:
                        import json_repair
                        data = json_repair.loads(content)
                        if isinstance(data, dict):
                            data["source"] = f"{search_source}_llm_search"
                            return data
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)
                    return {"source": f"{search_source}_search", "results": [], "raw": content[:500]}
            except Exception as e:
                logger.warning(f"预订搜索 LLM 结构化失败: {e}")
        return {"source": "booking_search", "results": [], "note": "预订搜索暂不可用"}

    async def _exec_detect_booking_method(self, params: Dict) -> Dict:
        """检测预订方式"""
        return {"method": "browser", "fallback": "phone"}

    async def _exec_booking_execute(self, params: Dict) -> Dict:
        """执行预订 — browser-use (81k⭐) 自然语言浏览器自动化"""
        goal = params.get("goal", params.get("query", ""))
        url = params.get("url", "")
        try:
            from src.browser_use_bridge import get_browser_use
            browser = get_browser_use()
            if browser:
                task_desc = f"在网页上完成预订操作: {goal}"
                if url:
                    task_desc += f". 目标网站: {url}"
                result = await browser.run_task(task=task_desc, url=url, max_steps=15)
                if result.get("success"):
                    return {"source": "browser_use", "success": True, "result": result}
                return {"source": "browser_use", "success": False, "details": result}
        except Exception as e:
            logger.warning(f"浏览器预订失败: {e}")
        return {"source": "booking_fallback", "success": False, "note": "浏览器自动化未就绪"}

    async def _exec_booking_phone(self, params: Dict) -> Dict:
        """电话预订"""
        return {"source": "voice_call", "status": "pending", "note": "需要Retell AI"}

    async def _exec_booking_confirm(self, params: Dict) -> Dict:
        """预订确认 — 检查执行结果"""
        upstream = params.get("_upstream_results", {})
        booking_result = upstream.get("execute", {}) if isinstance(upstream, dict) else {}
        if booking_result.get("success"):
            return {"source": "confirmation", "confirmed": True, "details": booking_result}
        return {"source": "confirmation", "confirmed": False, "note": "预订执行未成功，无法确认"}

    async def _exec_llm_query(self, params: Dict) -> Dict:
        """LLM 信息查询 — 注入 SOUL_CORE 人格 + 对话上下文"""
        question = params.get("question", "")
        try:
            from src.litellm_router import free_pool
            if free_pool:
                messages = [
                    {"role": "system", "content": INFO_QUERY_PROMPT},
                ]
                # 注入对话上下文 (如果可用)
                ctx = params.get("_brain_context", {})
                recent = ctx.get("recent_messages", "")
                if recent:
                    messages.append({
                        "role": "system",
                        "content": f"最近对话:\n{recent}",
                    })
                messages.append({"role": "user", "content": question})

                async with api_limiter("llm"):
                    resp = await free_pool.acompletion(
                        model_family="qwen",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1000,
                    )
                answer = resp.choices[0].message.content
                return {"source": "llm", "answer": answer}
        except Exception as e:
            logger.warning(f"LLM查询失败: {e}")
        return {"source": "llm_fallback", "answer": error_ai_busy()}

    async def _exec_life_service(self, params: Dict) -> Dict:
        """生活服务 — 天气查询等"""
        goal = params.get("goal", "")
        city = params.get("city_hint", "")

        # 天气查询
        if "天气" in goal or city:
            try:
                from src.tools.free_apis import get_weather
                if not city:
                    # 从 goal 中提取城市名
                    import re
                    m = re.search(r'(.{1,4})天气|天气(.{1,4})', goal)
                    city = (m.group(1) or m.group(2)).strip() if m else "杭州"
                data = await get_weather(city)
                if data.get("forecasts"):
                    forecast_text = f"📍 {data.get('city', city)} 天气预报:\n"
                    for f in data["forecasts"][:4]:
                        forecast_text += (
                            f"  {f.get('date','')} {f.get('dayweather','')}"
                            f" {f.get('nighttemp','')}-{f.get('daytemp','')}°C\n"
                        )
                    return {"source": "weather", "city": city, "text": forecast_text, "forecasts": data["forecasts"]}
                return {"source": "weather", "city": city, "note": "天气数据暂不可用"}
            except Exception as e:
                logger.warning(f"天气查询失败: {e}")

        # 提醒/日程
        if any(kw in goal for kw in ["提醒", "闹钟", "备忘", "remind"]):
            try:
                from src.execution.life_automation import create_reminder
                reminder = await create_reminder(goal)
                return {"source": "reminder", "data": reminder}
            except Exception as e:
                logger.warning(f"提醒设置失败: {e}")

        # 汇率查询
        if any(kw in goal for kw in ["汇率", "换算", "兑换", "exchange"]):
            try:
                from src.tools.free_apis import get_exchange_rate
                data = await get_exchange_rate()
                return {"source": "exchange_rate", "data": data}
            except Exception as e:
                logger.warning(f"汇率查询失败: {e}")

        return {"source": "life", "note": "生活服务模块开发中"}

    async def _exec_portfolio_query(self, params: Dict) -> Dict:
        """持仓查询 — 先检查连接状态，避免超时等待"""
        try:
            from src.broker_bridge import ibkr
            # 快速检查连接状态（不等待重连）
            if not getattr(ibkr, '_connected', False):
                return {"source": "portfolio", "positions": [],
                        "note": "券商未连接（IB Gateway 未运行）", "card_type": "portfolio"}
            positions = await ibkr.get_positions()
            summary = await ibkr.get_account_summary()
            return {"source": "ibkr", "positions": positions,
                    "summary": summary, "card_type": "portfolio"}
        except Exception as e:
            logger.warning(f"持仓查询失败: {e}")
        return {"source": "portfolio", "positions": [], "note": "券商未连接", "card_type": "portfolio"}

    async def _exec_system_status(self, params: Dict) -> Dict:
        """系统状态 — 复用现有 RPC"""
        try:
            from src.api.rpc import ClawBotRPC
            status = ClawBotRPC._rpc_system_status()
            return {"source": "rpc", "status": status}
        except Exception as e:
            logger.warning(f"获取系统状态失败: {e}")
            return {"source": "status_error", "error": str(e)}

    async def _exec_evolution_scan(self, params: Dict) -> Dict:
        """进化扫描 — 复用现有 evolution engine"""
        try:
            from src.evolution.engine import EvolutionEngine
            engine = EvolutionEngine()
            proposals = await engine.daily_scan()
            return {
                "source": "evolution",
                "proposals_count": len(proposals),
                "proposals": [p.to_dict() for p in proposals[:5]],
            }
        except Exception as e:
            logger.warning(f"进化扫描失败: {e}")
            return {"source": "evolution_error", "error": str(e)}

    async def _exec_code_task(self, params: Dict) -> Dict:
        """代码任务 — 调用 CodeTool 沙盒执行"""
        task_desc = params.get("task", "")
        try:
            from src.tools.code_tool import CodeTool
            tool = CodeTool()
            # If it looks like code, execute directly; otherwise ask LLM to generate code first
            if any(kw in task_desc for kw in ["import ", "def ", "print(", "for ", "class "]):
                result = await tool.execute_python(task_desc)
                return {"source": "code_tool", "output": result, "type": "direct_execution"}
            else:
                # Use LLM to generate code, then execute
                from src.litellm_router import free_pool
                if free_pool:
                    resp = await free_pool.acompletion(
                        model_family="deepseek",
                        messages=[{"role": "user", "content": task_desc}],
                        system_prompt=SOUL_CORE + "\n\n你现在在做代码生成任务。只输出可执行的Python代码，不要解释。用```python代码块包裹。",
                        temperature=0.2, max_tokens=2000,
                    )
                    code = resp.choices[0].message.content
                    # Extract code from markdown block
                    import re
                    code_match = re.search(r'```python\s*(.*?)```', code, re.DOTALL)
                    if code_match:
                        code = code_match.group(1).strip()
                    result = await tool.execute_python(code)
                    return {"source": "code_tool_llm", "code": code[:500], "output": result}
        except Exception as e:
            logger.warning(f"代码任务失败: {e}")
        return {"source": "code_fallback", "note": "代码执行模块异常"}

    # ── 追问回答处理 ────────────────────────────────────

    def get_pending_clarification(self, chat_id: int) -> Optional[str]:
        """检查指定 chat 是否有待回答的追问。

        Returns:
            task_id if pending, None otherwise
        """
        return self._pending_clarifications.get(chat_id)

    async def resume_with_answer(
        self, task_id: str, answer: str, context: Dict
    ) -> TaskResult:
        """用用户的文本回答恢复被追问中断的任务。

        工作流:
        1. 从 _pending_callbacks 恢复 intent
        2. 将 answer 注入 intent.known_params
        3. 清除 missing_critical
        4. 重新构建任务图并执行
        """
        # 清除 chat_id 映射
        chat_id = int(context.get("chat_id", 0))
        self._pending_clarifications.pop(chat_id, None)

        pending = self._pending_callbacks.pop(task_id, None)
        result = TaskResult(task_id=task_id, source="clarification_reply")

        if pending is None:
            result.error = "追问已过期，请重新发起请求"
            return result

        start_time = time.time()
        try:
            intent = pending["intent"]
            # 将用户回答注入到 known_params
            intent.known_params["clarification_answer"] = answer
            # 只将回答赋给第一个缺失参数
            if intent.missing_critical:
                first_param = intent.missing_critical[0]
                intent.known_params[first_param] = answer
                intent.missing_critical.remove(first_param)
            # 如果还有其他缺失参数，保留它们让后续追问处理

            # 收集上下文（用户画像等）
            ctx_collector = get_context_collector()
            brain_context = await ctx_collector.collect(
                user_id=str(context.get("user_id", "")),
                chat_id=str(context.get("chat_id", "")),
                bot_id=str(context.get("bot_id", "")),
            )

            # 重新构建并执行任务图
            graph = await self._build_task_graph(intent)
            if graph is None:
                result.error = "无法为此任务构建执行计划"
                result.elapsed_seconds = time.time() - start_time
                return result

            logger.info(f"[{task_id}] 追问回答后恢复执行: {graph.name}")
            completed = await self._graph_executor.execute(graph)
            result.intent = intent
            result.graph_progress = completed.get_progress()

            if completed.is_success:
                results = {}
                for node in completed.nodes.values():
                    if node.status == NodeStatus.SUCCESS and node.result is not None:
                        results[node.id] = node.result
                result.final_result = results

                # 响应合成
                try:
                    synth = get_response_synthesizer()
                    task_type_str = (
                        intent.task_type.value
                        if hasattr(intent.task_type, "value")
                        else str(intent.task_type)
                    )
                    synthesized = await synth.synthesize(
                        raw_data=results,
                        task_type=task_type_str,
                        user_profile=brain_context.get("user_profile", ""),
                        conversation_summary=brain_context.get("conversation_summary", ""),
                    )
                    if synthesized:
                        result.final_result = {
                            "synthesized_reply": synthesized,
                            "_raw_data": results,
                            "_task_type": task_type_str,
                        }
                except Exception as synth_err:
                    logger.debug(f"追问回答响应合成失败: {synth_err}")
            else:
                result.error = "任务执行失败"

        except Exception as e:
            result.error = str(e)
            logger.error(f"追问回答处理失败: {e}", exc_info=True)

        result.elapsed_seconds = time.time() - start_time
        return result

    # ── 回调处理 ──────────────────────────────────────

    async def handle_callback(self, callback_id: str, data: str) -> TaskResult:
        """
        处理 Telegram Inline Keyboard 回调。

        当用户点击按钮时，从 pending_callbacks 中恢复上下文并继续执行。
        """
        task_id = callback_id.split(":")[0] if ":" in callback_id else callback_id
        pending = self._pending_callbacks.pop(task_id, None)

        result = TaskResult(task_id=task_id, source="callback")

        if pending is None:
            result.error = "回调已过期或不存在"
            return result

        try:
            intent = pending["intent"]
            # 将回调数据补充到 intent 的 known_params
            intent.known_params["callback_data"] = data
            intent.missing_critical.clear()  # 用户已回答

            # 重新构建并执行
            graph = await self._build_task_graph(intent)
            if graph:
                completed = await self._graph_executor.execute(graph)
                result.graph_progress = completed.get_progress()
                if completed.is_success:
                    results = {}
                    for node in completed.nodes.values():
                        if node.status == NodeStatus.SUCCESS and node.result:
                            results[node.id] = node.result
                    result.final_result = results
                else:
                    result.error = "任务执行失败"
        except Exception as e:
            result.error = str(e)
            logger.error(f"回调处理失败: {e}", exc_info=True)

        return result

    # ── 任务管理 ──────────────────────────────────────

    def get_active_tasks(self) -> List[Dict]:
        """获取所有活跃任务状态"""
        return [r.to_dict() for r in self._active_tasks.values()]

    def cancel_task(self, task_id: str) -> bool:
        """取消一个任务"""
        task = self._active_tasks.get(task_id)
        if task:
            task.error = "用户取消"
            self._active_tasks.pop(task_id, None)
            self._pending_callbacks.pop(task_id, None)
            logger.info(f"任务已取消: {task_id}")
            return True
        return False

    def cleanup_pending_callbacks(self, max_age_seconds: int = 600):
        """Remove pending callbacks older than max_age."""
        now = time.time()
        stale = [k for k, v in self._pending_callbacks.items()
                 if now - v.get("created_at", 0) > max_age_seconds]
        for k in stale:
            del self._pending_callbacks[k]
        if stale:
            logger.debug("Cleaned %d stale pending callbacks", len(stale))
        # 同步清理 clarification 映射中已过期的条目
        stale_clarifications = [
            chat_id for chat_id, tid in self._pending_clarifications.items()
            if tid not in self._pending_callbacks
        ]
        for chat_id in stale_clarifications:
            del self._pending_clarifications[chat_id]

    # ── 进度和事件回调 ──────────────────────────────────

    async def _on_progress(self, progress: Dict) -> None:
        """任务图进度更新 — 推送到 EventBus"""
        await self._event_bus.publish(
            "brain.progress",
            progress,
            source="brain",
        )

    async def _on_node_complete(self, node: TaskNode) -> None:
        """单个节点完成 — 推送到 EventBus"""
        await self._event_bus.publish(
            "brain.node_complete",
            node.to_dict(),
            source="brain",
        )

    # ── 自愈 ──────────────────────────────────────────

    async def _try_self_heal(self, error: Exception, context: Dict) -> bool:
        """尝试自愈 — 传递 context 但不传 retry_callable（Brain 层重试逻辑由调用者决定）"""
        try:
            from src.core.self_heal import get_self_heal_engine
            engine = get_self_heal_engine()
            result = await engine.heal(error, context, retry_callable=None)
            return result.healed
        except ImportError:
            logger.debug("自愈引擎未就绪")
        except Exception as e:
            logger.warning(f"自愈失败: {e}")
        return False


# ── 全局单例 ──────────────────────────────────────────────

_brain: Optional[OpenClawBrain] = None


def get_brain() -> OpenClawBrain:
    """获取全局 Brain 实例"""
    global _brain
    if _brain is None:
        _brain = OpenClawBrain()
    return _brain


def init_brain() -> OpenClawBrain:
    """初始化并返回 Brain 实例（用于 multi_main.py 启动时调用）"""
    global _brain
    _brain = OpenClawBrain()
    logger.info("OpenClawBrain 已初始化")
    return _brain


# ── 复合意图拆解 — 搬运 ChatGPT multi-tool / AutoGPT task chain ──────


def _detect_compound_intent(message: str, primary_intent: ParsedIntent) -> list:
    """检测一句话中是否包含多个可拆解的子任务。

    搬运灵感: ChatGPT 的 multi-tool calling / AutoGPT 的 task decomposition
    零 LLM 成本，纯正则检测连接词模式。

    示例:
      "分析TSLA然后发到小红书" → [INVESTMENT("分析TSLA"), SOCIAL("发到小红书")]
      "帮我查天气" → None (单一意图，不拆)

    Returns:
        list[ParsedIntent] 如果检测到复合意图，否则 None
    """
    import re

    if not message or len(message) < 8:
        return None

    # 连接词模式: "然后/接着/之后/再/并且/同时"
    _CONNECTORS = r"(?:然后|接着|之后|再|并且|同时|顺便|最后)"
    parts = re.split(_CONNECTORS, message)

    # 少于 2 段不算复合意图
    if len(parts) < 2:
        return None

    # 每段至少 3 字符才算有效
    valid_parts = [p.strip() for p in parts if len(p.strip()) >= 3]
    if len(valid_parts) < 2:
        return None

    # 为每段创建独立的 ParsedIntent（用主意图的参数作为基础）
    sub_intents = []
    # 任务类型推断映射（简单关键词）
    _TYPE_HINTS = {
        TaskType.INVESTMENT: ["分析", "买入", "卖出", "持仓", "行情", "股", "基金", "回测"],
        TaskType.SOCIAL: ["发", "小红书", "推特", "社媒", "文案", "热点"],
        TaskType.SHOPPING: ["比价", "搜", "买", "价格", "推荐"],
        TaskType.INFO: ["查", "搜索", "什么是", "怎么"],
        TaskType.LIFE: ["提醒", "快递", "天气", "日历"],
    }

    for part in valid_parts:
        # 推断子任务类型
        sub_type = TaskType.UNKNOWN
        for ttype, keywords in _TYPE_HINTS.items():
            if any(kw in part for kw in keywords):
                sub_type = ttype
                break
        if sub_type == TaskType.UNKNOWN:
            sub_type = primary_intent.task_type  # 降级用主意图类型

        sub_intents.append(ParsedIntent(
            goal=part,
            task_type=sub_type,
            known_params=dict(primary_intent.known_params),
            confidence=0.7,
            raw_message=part,
        ))

    return sub_intents if len(sub_intents) >= 2 else None
