"""
OpenClaw OMEGA — 任务DAG引擎 (Task Graph)
将 ParsedIntent 转为有向无环图，支持并行执行和依赖管理。

不依赖 LangGraph（减少依赖），用纯 asyncio 实现 DAG 调度。
如果后续需要更复杂的状态机，可以引入 LangGraph 替换。
"""
import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

from src.utils import emit_flow_event as _emit_flow  # noqa: E402
from src.utils import scrub_secrets  # noqa: E402

# ── 节点状态 ──────────────────────────────────────────

class NodeStatus(StrEnum):
    PENDING = "pending"
    WAITING = "waiting"       # 等待依赖完成
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"       # 依赖失败导致跳过
    CANCELLED = "cancelled"


class ExecutorType(StrEnum):
    """执行器类型"""
    LLM = "llm"               # LLM 推理
    API = "api"               # HTTP API 直连
    BROWSER = "browser"       # 浏览器自动化
    VOICE_CALL = "voice_call" # AI 电话
    LOCAL = "local"           # 本地函数调用
    HUMAN = "human"           # 需要人工介入
    CREW = "crew"             # 项目原生多角色协作（保留兼容值）


# ── 任务节点 ──────────────────────────────────────────

@dataclass
class TaskNode:
    """DAG 中的单个任务节点"""
    id: str                                     # 唯一ID
    name: str                                   # 人类可读名称（中文）
    executor_type: ExecutorType                 # 执行器类型
    execute_fn: Callable | None = None       # 实际执行函数
    params: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # 依赖的节点ID列表
    retry_count: int = 3                        # 最大重试次数
    timeout_seconds: int = 120                  # 超时时间
    fallback_node_id: str | None = None      # 失败时的备选节点
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None                          # 执行结果
    error: str | None = None                 # 错误信息
    started_at: float = 0.0
    finished_at: float = 0.0
    attempt: int = 0                            # 当前重试次数

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        elif self.started_at:
            return time.time() - self.started_at
        return 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "executor_type": self.executor_type.value,
            "status": self.status.value,
            "result_summary": str(self.result)[:200] if self.result else None,
            "error": self.error,
            "elapsed": round(self.elapsed_seconds, 2),
            "attempt": self.attempt,
        }


# ── 任务图 ──────────────────────────────────────────

@dataclass
class TaskGraph:
    """有向无环图，管理一组有依赖关系的任务"""
    graph_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""                              # 任务图名称
    nodes: dict[str, TaskNode] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def add_node(self, node: TaskNode) -> None:
        """添加节点"""
        if node.id in self.nodes:
            raise ValueError(f"节点ID已存在: {node.id}")
        self.nodes[node.id] = node

    def add_dependency(self, node_id: str, depends_on: str) -> None:
        """添加依赖关系"""
        if node_id not in self.nodes:
            raise ValueError(f"节点不存在: {node_id}")
        if depends_on not in self.nodes:
            raise ValueError(f"依赖节点不存在: {depends_on}")
        if depends_on not in self.nodes[node_id].dependencies:
            self.nodes[node_id].dependencies.append(depends_on)

    def get_ready_nodes(self) -> list[TaskNode]:
        """获取所有依赖已满足、可以执行的节点"""
        ready = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            # 检查所有依赖是否完成
            deps_met = all(
                self.nodes[dep_id].status == NodeStatus.SUCCESS
                for dep_id in node.dependencies
                if dep_id in self.nodes
            )
            # 检查是否有依赖失败
            deps_failed = any(
                self.nodes[dep_id].status in (NodeStatus.FAILED, NodeStatus.CANCELLED)
                for dep_id in node.dependencies
                if dep_id in self.nodes
            )
            if deps_failed:
                node.status = NodeStatus.SKIPPED
                node.error = "依赖节点失败，已跳过"
                if node.fallback_node_id:
                    fallback = self.nodes.get(node.fallback_node_id)
                    if fallback is not None and fallback.status == NodeStatus.WAITING:
                        fallback.status = NodeStatus.SKIPPED
                        fallback.error = f"主节点 {node.id} 因依赖失败跳过，未触发备选"
            elif deps_met:
                ready.append(node)
        return ready

    @property
    def is_complete(self) -> bool:
        """所有节点是否都已终止（成功/失败/跳过/取消）"""
        terminal = {NodeStatus.SUCCESS, NodeStatus.FAILED,
                    NodeStatus.SKIPPED, NodeStatus.CANCELLED}
        return all(n.status in terminal for n in self.nodes.values())

    @property
    def is_success(self) -> bool:
        """所有非跳过节点是否都成功"""
        return all(
            n.status in (NodeStatus.SUCCESS, NodeStatus.SKIPPED)
            for n in self.nodes.values()
        )

    def get_progress(self) -> dict:
        """获取执行进度"""
        total = len(self.nodes)
        completed = sum(1 for n in self.nodes.values()
                       if n.status in (NodeStatus.SUCCESS, NodeStatus.SKIPPED))
        failed = sum(1 for n in self.nodes.values()
                    if n.status == NodeStatus.FAILED)
        running = sum(1 for n in self.nodes.values()
                     if n.status == NodeStatus.RUNNING)
        return {
            "graph_id": self.graph_id,
            "name": self.name,
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": total - completed - failed - running,
            "progress_pct": round(completed / total * 100, 1) if total > 0 else 0,
            "nodes": [n.to_dict() for n in self.nodes.values()],
        }

    def to_dict(self) -> dict:
        return self.get_progress()


# ── DAG 执行器 ──────────────────────────────────────────

class TaskGraphExecutor:
    """
    DAG 调度执行器。

    执行策略:
      1. 找到所有依赖已满足的节点（就绪节点）
      2. 并行启动所有就绪节点
      3. 等待任一节点完成
      4. 更新状态，重复 1-3
      5. 直到所有节点终止

    进度推送:
      通过 on_progress 回调实时推送到 Telegram / WebSocket。
    """

    def __init__(
        self,
        on_progress: Callable[[dict], Coroutine] | None = None,
        on_node_complete: Callable[[TaskNode], Coroutine] | None = None,
    ):
        self._on_progress = on_progress
        self._on_node_complete = on_node_complete

    async def execute(self, graph: TaskGraph) -> TaskGraph:
        """
        执行整个 DAG。

        Args:
            graph: 任务图

        Returns:
            执行完毕的任务图（包含所有结果）
        """
        logger.info(f"开始执行任务图: {graph.name} ({graph.graph_id}), "
                    f"{len(graph.nodes)} 个节点")
        _emit_flow("hub", "hub", "running", f"任务图开始: {graph.name}",
                   {"graph_id": graph.graph_id, "nodes": len(graph.nodes)})

        while not graph.is_complete:
            ready_nodes = graph.get_ready_nodes()
            if not ready_nodes:
                # 没有就绪节点但未完成 → 可能有循环依赖或死锁
                unfinished = [
                    node
                    for node in graph.nodes.values()
                    if node.status in (NodeStatus.PENDING, NodeStatus.WAITING)
                ]
                if unfinished:
                    logger.error(f"死锁检测: {len(unfinished)} 个节点无法调度")
                    for unfinished_node in unfinished:
                        if unfinished_node.status == NodeStatus.WAITING:
                            unfinished_node.status = NodeStatus.SKIPPED
                            unfinished_node.error = "待命备选未触发，已收口"
                        else:
                            unfinished_node.status = NodeStatus.CANCELLED
                            unfinished_node.error = "死锁: 依赖关系无法满足"
                break

            # 并行执行所有就绪节点
            tasks = [self._execute_node(graph, node) for node in ready_nodes]
            await asyncio.gather(*tasks, return_exceptions=True)

            # 推送进度
            if self._on_progress:
                try:
                    await self._on_progress(graph.get_progress())
                except Exception as e:
                    logger.warning(f"进度推送失败: {scrub_secrets(str(e))}")

        status = "success" if graph.is_success else "error"
        progress = graph.get_progress()
        _emit_flow("hub", "hub", status, f"任务图完毕: {graph.name}",
                   {"graph_id": graph.graph_id, "progress": progress})
        logger.info(f"任务图执行完毕: {graph.graph_id}, "
                    f"成功={graph.is_success}")
        return graph

    async def _execute_node(self, graph: TaskGraph, node: TaskNode) -> None:
        """执行单个节点（带重试）"""
        node.status = NodeStatus.RUNNING
        node.started_at = time.time()
        _emit_flow("hub", node.id, "running", f"开始: {node.name}", {"node": node.id, "name": node.name})

        for attempt in range(1, node.retry_count + 1):
            node.attempt = attempt
            try:
                if node.execute_fn is None:
                    raise ValueError(f"节点 {node.id} 没有执行函数")

                # 每次执行都从已完成依赖收集真实结果，避免下游只看到静态参数。
                execution_params = dict(node.params)
                if node.dependencies:
                    execution_params["_upstream_results"] = {
                        dependency_id: graph.nodes[dependency_id].result
                        for dependency_id in node.dependencies
                        if dependency_id in graph.nodes
                        and graph.nodes[dependency_id].status == NodeStatus.SUCCESS
                    }

                result = await asyncio.wait_for(
                    node.execute_fn(execution_params),
                    timeout=node.timeout_seconds,
                )
                node.result = result
                node.status = NodeStatus.SUCCESS
                node.finished_at = time.time()
                self._complete_fallback_parent(graph, node)
                self._skip_unused_fallback(graph, node)

                logger.info(f"节点完成: {node.name} ({node.elapsed_seconds:.1f}s)")
                _emit_flow(node.id, "hub", "success", f"完成: {node.name}",
                           {"node": node.id, "elapsed": round(node.elapsed_seconds, 2)})

                if self._on_node_complete:
                    try:
                        await self._on_node_complete(node)
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)
                return

            except TimeoutError:
                node.error = f"超时 ({node.timeout_seconds}s)"
                logger.warning(f"节点超时: {node.name} (尝试 {attempt}/{node.retry_count})")
                _emit_flow(node.id, "hub", "error", f"超时: {node.name}",
                           {"node": node.id, "attempt": attempt, "error": node.error})
            except Exception as e:
                node.error = scrub_secrets(str(e))[:500]
                logger.warning(
                    "节点失败: %s (尝试 %s/%s): %s",
                    node.name,
                    attempt,
                    node.retry_count,
                    node.error,
                )
                _emit_flow(node.id, "hub", "error", f"失败: {node.name} - {node.error[:60]}",
                           {"node": node.id, "attempt": attempt, "error": node.error})

            if attempt < node.retry_count:
                await asyncio.sleep(min(attempt * 2, 10))  # 指数退避

        # 所有重试用尽。存在备选时先把主节点置为等待；备选成功后会回填主节点结果。
        node.finished_at = time.time()
        fallback = graph.nodes.get(node.fallback_node_id) if node.fallback_node_id else None
        if fallback is not None and fallback.status == NodeStatus.WAITING:
            node.status = NodeStatus.WAITING
            fallback.status = NodeStatus.PENDING
            logger.info(f"节点 {node.name} 失败，启用备选: {fallback.name}")
            _emit_flow(
                node.id,
                fallback.id,
                "running",
                f"主路径失败，启用备选: {fallback.name}",
                {"node": node.id, "fallback": fallback.id, "error": node.error},
            )
            return

        node.status = NodeStatus.FAILED
        self._fail_fallback_parent(graph, node)
        _emit_flow(node.id, "hub", "error", f"放弃: {node.name} (重试耗尽)",
                   {"node": node.id, "error": node.error})

    @staticmethod
    def _fallback_parents(graph: TaskGraph, fallback_id: str) -> list[TaskNode]:
        return [
            candidate
            for candidate in graph.nodes.values()
            if candidate.fallback_node_id == fallback_id
        ]

    def _complete_fallback_parent(self, graph: TaskGraph, fallback: TaskNode) -> None:
        """备选成功时，把结果回填到等待中的主节点，保持原依赖契约。"""
        for parent in self._fallback_parents(graph, fallback.id):
            if parent.status != NodeStatus.WAITING:
                continue
            parent.result = fallback.result
            parent.status = NodeStatus.SUCCESS
            parent.finished_at = fallback.finished_at
            parent.error = f"主路径失败，已使用备选节点 {fallback.id}"

    def _fail_fallback_parent(self, graph: TaskGraph, fallback: TaskNode) -> None:
        """备选也失败时，终止等待中的主节点，让下游按失败传播。"""
        for parent in self._fallback_parents(graph, fallback.id):
            if parent.status != NodeStatus.WAITING:
                continue
            parent.status = NodeStatus.FAILED
            parent.finished_at = fallback.finished_at
            parent.error = f"主路径与备选节点 {fallback.id} 均失败"

    @staticmethod
    def _skip_unused_fallback(graph: TaskGraph, node: TaskNode) -> None:
        """主路径成功时关闭待命备选，防止外部动作被抢跑。"""
        if not node.fallback_node_id:
            return
        fallback = graph.nodes.get(node.fallback_node_id)
        if fallback is not None and fallback.status == NodeStatus.WAITING:
            fallback.status = NodeStatus.SKIPPED
            fallback.error = f"主节点 {node.id} 已成功，未触发备选"


# ── 任务图构建器（常用模式）──────────────────────────────

class TaskGraphBuilder:
    """
    便捷的任务图构建器。

    使用方式:
        builder = TaskGraphBuilder("餐厅预订")
        builder.add("search", "搜索餐厅", ExecutorType.API, search_fn, params={...})
        builder.add("rank", "排序筛选", ExecutorType.LOCAL, rank_fn, after=["search"])
        builder.add("present", "展示给用户", ExecutorType.LOCAL, present_fn, after=["rank"])
        graph = builder.build()
    """

    def __init__(self, name: str):
        self._name = name
        self._nodes: list[dict] = []

    def add(
        self,
        node_id: str,
        name: str,
        executor_type: ExecutorType,
        execute_fn: Callable | None = None,
        params: dict | None = None,
        after: list[str] | None = None,
        timeout: int = 120,
        retry: int = 3,
        fallback: str | None = None,
    ) -> "TaskGraphBuilder":
        """添加节点"""
        self._nodes.append({
            "id": node_id,
            "name": name,
            "executor_type": executor_type,
            "execute_fn": execute_fn,
            "params": params or {},
            "dependencies": after or [],
            "timeout_seconds": timeout,
            "retry_count": retry,
            "fallback_node_id": fallback,
        })
        return self

    def build(self) -> TaskGraph:
        """构建任务图"""
        graph = TaskGraph(name=self._name)
        for n in self._nodes:
            node = TaskNode(
                id=n["id"],
                name=n["name"],
                executor_type=n["executor_type"],
                execute_fn=n["execute_fn"],
                params=n["params"],
                dependencies=n["dependencies"],
                timeout_seconds=n["timeout_seconds"],
                retry_count=n["retry_count"],
                fallback_node_id=n.get("fallback_node_id"),
            )
            graph.add_node(node)

        # 备选节点默认待命，不能和主路径一起抢跑。目标缺失或自引用时在构建期直接失败。
        fallback_owners: dict[str, str] = {}
        for node in graph.nodes.values():
            if not node.fallback_node_id:
                continue
            if node.fallback_node_id == node.id:
                raise ValueError(f"节点不能把自己设为备选: {node.id}")
            fallback = graph.nodes.get(node.fallback_node_id)
            if fallback is None:
                raise ValueError(f"备选节点不存在: {node.fallback_node_id}")
            existing_owner = fallback_owners.get(fallback.id)
            if existing_owner:
                raise ValueError(f"备选节点 {fallback.id} 已属于主节点 {existing_owner}")
            fallback_owners[fallback.id] = node.id
            fallback.status = NodeStatus.WAITING
        return graph
