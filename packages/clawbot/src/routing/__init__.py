"""
Routing — 向后兼容门面

原 chat_router.py (1411行) 拆分为:
- routing/models.py      — 常量、枚举、数据类
- routing/streaming.py   — 流式传输
- routing/priority_queue.py — 优先级队列

ChatRouter 和 CollabOrchestrator 仍在原 chat_router.py 中
（它们与太多内部状态耦合，渐进式迁移更安全）。

新代码应直接导入子模块:
  from src.routing.models import BotCapability, Intent
  from src.routing.streaming import StreamingResponse, stream_llm_to_telegram
  from src.routing.priority_queue import PriorityMessageQueue
"""

# Re-export 新模块的公共 API
from src.routing.models import (
    Intent,
    INTENT_KEYWORDS,
    INTENT_BOT_MAP,
    LANE_ROUTE_RULES,
    CHAIN_DISCUSS_TRIGGERS,
    SERVICE_WORKFLOW_ACTION_HINTS,
    SERVICE_WORKFLOW_NOUN_HINTS,
    SERVICE_WORKFLOW_SKIP_HINTS,
    BotCapability,
    ServiceWorkflowSession,
    CollabPhase,
    CollabTask,
    MessagePriority,
    PrioritizedMessage,
)
from src.routing.streaming import StreamingResponse, stream_llm_to_telegram
from src.routing.priority_queue import PriorityMessageQueue

__all__ = [
    "Intent",
    "INTENT_KEYWORDS",
    "INTENT_BOT_MAP",
    "LANE_ROUTE_RULES",
    "CHAIN_DISCUSS_TRIGGERS",
    "BotCapability",
    "ServiceWorkflowSession",
    "CollabPhase",
    "CollabTask",
    "MessagePriority",
    "PrioritizedMessage",
    "StreamingResponse",
    "stream_llm_to_telegram",
    "PriorityMessageQueue",
]
