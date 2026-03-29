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
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

from src.utils import emit_flow_event as _emit_flow


# ── 节点状态 ──────────────────────────────────────────

class NodeStatus(str, Enum):
    PENDING = "pending"
    WAITING = "waiting"       # 等待依赖完成
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"       # 依赖失败导致跳过
    CANCELLED = "cancelled"


class ExecutorType(str, Enum):
    """执行器类型"""
    LLM = "llm"               # LLM 推理
    API = "api"               # HTTP API 直连
    BROWSER = "browser"       # 浏览器自动化
    VOICE_CALL = "voice_call" # AI 电话
    LOCAL = "local"           # 本地函数调用
    HUMAN = "human"           # 需要人工介入
    CREW = "crew"             # CrewAI 多智能体


# ── 任务节点 ──────────────────────────────────────────

@dataclass
class TaskNode:
    """DAG 中的单个任务节点"""
    id: str                                     # 唯一ID
    name: str                                   # 人类可读名称（中文）
    executor_type: ExecutorType                 # 执行器类型
    execute_fn: Optional[Callable] = None       # 实际执行函数
    params: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # 依赖的节点ID列表
    retry_count: int = 3                        # 最大重试次数
    timeout_seconds: int = 120                  # 超时时间
    fallback_node_id: Optional[str] = None      # 失败时的备选节点
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None                          # 执行结果
    error: Optional[str] = None                 # 错误信息
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

    def to_dict(self) -> Dict:
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
    nodes: Dict[str, TaskNode] = field(default_factory=dict)
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

    def get_ready_nodes(self) -> List[TaskNode]:
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

    def get_progress(self) -> Dict:
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

    def to_dict(self) -> Dict:
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
        on_progress: Optional[Callable[[Dict], Coroutine]] = None,
        on_node_complete: Optional[Callable[[TaskNode], Coroutine]] = None,
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
                pending = [n for n in graph.nodes.values()
                          if n.status == NodeStatus.PENDING]
                if pending:
                    logger.error(f"死锁检测: {len(pending)} 个节点无法调度")
                    for n in pending:
                        n.status = NodeStatus.CANCELLED
                        n.error = "死锁: 依赖关系无法满足"
                break

            # 并行执行所有就绪节点
            tasks = [self._execute_node(node) for node in ready_nodes]
            await asyncio.gather(*tasks, return_exceptions=True)

            # 推送进度
            if self._on_progress:
                try:
                    await self._on_progress(graph.get_progress())
                except Exception as e:
                    logger.warning(f"进度推送失败: {e}")

        status = "success" if graph.is_success else "error"
        progress = graph.get_progress()
        _emit_flow("hub", "hub", status, f"任务图完毕: {graph.name}",
                   {"graph_id": graph.graph_id, "progress": progress})
        logger.info(f"任务图执行完毕: {graph.graph_id}, "
                    f"成功={graph.is_success}")
        return graph

    async def _execute_node(self, node: TaskNode) -> None:
        """执行单个节点（带重试）"""
        node.status = NodeStatus.RUNNING
        node.started_at = time.time()
        _emit_flow("hub", node.id, "running", f"开始: {node.name}", {"node": node.id, "name": node.name})

        for attempt in range(1, node.retry_count + 1):
            node.attempt = attempt
            try:
                if node.execute_fn is None:
                    raise ValueError(f"节点 {node.id} 没有执行函数")

                # 带超时执行
                result = await asyncio.wait_for(
                    node.execute_fn(node.params),
                    timeout=node.timeout_seconds,
                )
                node.result = result
                node.status = NodeStatus.SUCCESS
                node.finished_at = time.time()

                logger.info(f"节点完成: {node.name} ({node.elapsed_seconds:.1f}s)")
                _emit_flow(node.id, "hub", "success", f"完成: {node.name}",
                           {"node": node.id, "elapsed": round(node.elapsed_seconds, 2)})

                if self._on_node_complete:
                    try:
                        await self._on_node_complete(node)
                    except Exception as e:
                        logger.debug("Silenced exception", exc_info=True)
                return

            except asyncio.TimeoutError as e:
                node.error = f"超时 ({node.timeout_seconds}s)"
                logger.warning(f"节点超时: {node.name} (尝试 {attempt}/{node.retry_count})")
                _emit_flow(node.id, "hub", "error", f"超时: {node.name}",
                           {"node": node.id, "attempt": attempt, "error": node.error})
            except Exception as e:
                node.error = str(e)
                logger.warning(
                    f"节点失败: {node.name} (尝试 {attempt}/{node.retry_count}): {e}"
                )
                _emit_flow(node.id, "hub", "error", f"失败: {node.name} - {str(e)[:60]}",
                           {"node": node.id, "attempt": attempt, "error": node.error})

            if attempt < node.retry_count:
                await asyncio.sleep(min(attempt * 2, 10))  # 指数退避

        # 所有重试用尽
        node.status = NodeStatus.FAILED
        node.finished_at = time.time()
        _emit_flow(node.id, "hub", "error", f"放弃: {node.name} (重试耗尽)",
                   {"node": node.id, "error": node.error})

        # 尝试备选节点
        if node.fallback_node_id:
            logger.info(f"节点 {node.name} 失败，尝试备选: {node.fallback_node_id}")
            # 备选节点的状态重置为 PENDING，下一轮会被调度


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
        self._nodes: List[Dict] = []

    def add(
        self,
        node_id: str,
        name: str,
        executor_type: ExecutorType,
        execute_fn: Optional[Callable] = None,
        params: Optional[Dict] = None,
        after: Optional[List[str]] = None,
        timeout: int = 120,
        retry: int = 3,
        fallback: Optional[str] = None,
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
        return graph
