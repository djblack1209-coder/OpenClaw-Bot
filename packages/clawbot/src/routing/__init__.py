"""
routing 包 — 群聊智能路由 + 协作编排
从 chat_router.py 拆分而来，按职责分为多个子模块。
"""

# 常量
from src.routing.constants import (
    CHAIN_DISCUSS_TRIGGERS,
    SERVICE_WORKFLOW_ACTION_HINTS,
    SERVICE_WORKFLOW_NOUN_HINTS,
    SERVICE_WORKFLOW_SKIP_HINTS,
    Intent,
    INTENT_BOT_MAP,
    INTENT_KEYWORDS,
    LANE_ROUTE_RULES,
    FALLBACK_ROTATION,
)

# 数据模型
from src.routing.models import (
    BotCapability,
    ServiceWorkflowSession,
    CollabPhase,
    CollabTask,
    MessagePriority,
    PrioritizedMessage,
)

# 核心路由器
from src.routing.router import ChatRouter

# 协作编排器
from src.routing.orchestrator import CollabOrchestrator

# 流式传输
from src.routing.streaming import StreamingResponse, stream_llm_to_telegram

# 优先级队列
from src.routing.priority_queue import PriorityMessageQueue

# 向后兼容：原 chat_router.py 中的私有变量名
_FALLBACK_ROTATION = FALLBACK_ROTATION

__all__ = [
    # 常量
    "CHAIN_DISCUSS_TRIGGERS",
    "SERVICE_WORKFLOW_ACTION_HINTS",
    "SERVICE_WORKFLOW_NOUN_HINTS",
    "SERVICE_WORKFLOW_SKIP_HINTS",
    "Intent",
    "INTENT_BOT_MAP",
    "INTENT_KEYWORDS",
    "LANE_ROUTE_RULES",
    "FALLBACK_ROTATION",
    "_FALLBACK_ROTATION",
    # 模型
    "BotCapability",
    "ServiceWorkflowSession",
    "CollabPhase",
    "CollabTask",
    "MessagePriority",
    "PrioritizedMessage",
    # 路由器
    "ChatRouter",
    # 编排器
    "CollabOrchestrator",
    # 流式传输
    "StreamingResponse",
    "stream_llm_to_telegram",
    # 优先级队列
    "PriorityMessageQueue",
]
