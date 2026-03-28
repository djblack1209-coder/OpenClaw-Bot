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
import importlib.util
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.event_bus import EventType, get_event_bus
from src.core.intent_parser import IntentParser, ParsedIntent, TaskType
from src.core.task_graph import (
    TaskGraph, TaskGraphExecutor,
    TaskNode, NodeStatus,
)
from config.prompts import (
    CHAT_FALLBACK_PROMPT,
)
from src.core.response_synthesizer import (
    get_response_synthesizer,
    get_context_collector,
)
# 速率限制 — resilience 模块始终可导入，内部已做优雅降级
from src.resilience import api_limiter

from src.core.brain_graph_builders import BrainGraphBuilderMixin
from src.core.brain_executors import BrainExecutorMixin

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

class OpenClawBrain(BrainGraphBuilderMixin, BrainExecutorMixin):
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
            except Exception as e:
                pass
                logger.debug("静默异常: %s", e)

            if not intent.is_actionable:
                # ── 模糊输入智能引导 — 无法识别明确意图时提供快捷操作建议 ──
                # 搬运灵感: ChatGPT suggested prompts / Google Gemini 推荐操作
                # 这些建议会被 message_mixin 渲染成 InlineKeyboard 按钮
                _suggestions = [
                    ("📊 看持仓", "cmd:portfolio"),
                    ("📋 今日简报", "cmd:brief"),
                    ("📱 账单状态", "cmd:bill"),
                ]
                # 检查闲鱼模块是否可用
                if importlib.util.find_spec("src.xianyu.xianyu_context"):
                    _suggestions.append(("🐟 闲鱼状态", "cmd:xianyu"))
                result.extra_data["quick_suggestions"] = _suggestions

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
                except Exception as e:
                    pass
                    logger.debug("静默异常: %s", e)

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
            except RuntimeError as e:  # noqa: F841
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


    # ── _build_*_graph 方法已拆分至 brain_graph_builders.py ──
    # ── _exec_* 方法已拆分至 brain_executors.py ──


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
