"""
路由数据模型 — 所有 dataclass 和 Enum 定义
从 chat_router.py 拆分而来，集中管理路由相关的数据结构。
"""
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.constants import BOT_CLAUDE_SONNET, BOT_QWEN


@dataclass
class BotCapability:
    """Bot 能力描述"""
    bot_id: str
    name: str
    username: str
    keywords: list[str]           # 触发关键词
    domains: list[str]            # 擅长领域
    priority: int = 0             # 优先级（越高越优先）


@dataclass
class ServiceWorkflowSession:
    """服务工作流会话 — 记录链式服务流程的状态"""
    session_id: str
    chat_id: int
    original_text: str
    owner_bot_id: str
    intake_bot_id: str
    expert_bot_id: str
    director_bot_id: str
    stage: str = "awaiting_selection"
    active: bool = True
    options: list[dict[str, Any]] = field(default_factory=list)
    intake_summary: str = ""
    missing_info: list[str] = field(default_factory=list)
    selected_option_id: int = 0
    selection_note: str = ""
    expert_plan: dict[str, Any] = field(default_factory=dict)
    team_plan: dict[str, Any] = field(default_factory=dict)
    execution_results: list[dict[str, Any]] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    final_report: str = ""
    rating_hint: str = ""
    created_at: float = field(default_factory=time.time)


class CollabPhase(Enum):
    """协作阶段"""
    PLANNING = "planning"       # 规划阶段
    EXECUTING = "executing"     # 执行阶段
    REVIEWING = "reviewing"     # 审查阶段
    SUMMARIZING = "summarizing" # 汇总阶段
    DONE = "done"               # 完成


@dataclass
class CollabTask:
    """协作任务 — 记录多 Bot 协作流程的完整状态"""
    task_id: str                    # 唯一任务ID
    chat_id: int                    # Telegram chat ID
    original_text: str              # 用户原始指令
    phase: CollabPhase = CollabPhase.PLANNING
    planner_id: str = ""            # 规划者 bot_id
    executor_id: str = BOT_CLAUDE_SONNET     # 执行者（默认 Claude Sonnet 4.5）
    reviewer_id: str = ""           # 审查者（默认由规划者审查）
    summarizer_id: str = BOT_QWEN  # 汇总者（默认 Qwen 235B）
    plan_result: str = ""           # 规划结果
    exec_result: str = ""           # 执行结果
    review_result: str = ""         # 审查结果
    review_passed: bool = True      # 审查是否通过
    summary_result: str = ""        # 汇总结果
    retry_count: int = 0            # 执行重试次数
    max_retries: int = 1            # 最大重试次数
    created_at: float = 0.0
    error: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()


class MessagePriority(Enum):
    """消息优先级"""
    CRITICAL = 0    # 系统告警、风控通知
    HIGH = 1        # 直接 @bot、私聊
    NORMAL = 2      # 群聊普通消息
    LOW = 3         # 自动化任务、定时消息
    BACKGROUND = 4  # 后台分析、日志


@dataclass(order=True)
class PrioritizedMessage:
    """带优先级的消息"""
    priority: int
    timestamp: float = field(compare=True)
    chat_id: int = field(compare=False)
    user_id: int = field(compare=False)
    text: str = field(compare=False)
    bot_id: str = field(compare=False, default="")
    metadata: dict[str, Any] = field(compare=False, default_factory=dict)
