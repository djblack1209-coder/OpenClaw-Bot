"""
ClawBot - 群聊智能路由 + 协作编排 (向后兼容入口)

本文件已拆分为 src/routing/ 包下的多个子模块。
此文件仅做 re-export，确保所有 `from src.chat_router import ...` 的代码无需修改。

子模块结构:
  src/routing/constants.py      — 意图/分流/触发词等常量
  src/routing/models.py         — 数据模型 (BotCapability, CollabTask 等)
  src/routing/router.py         — ChatRouter 核心路由器
  src/routing/orchestrator.py   — CollabOrchestrator 协作编排
  src/routing/streaming.py      — StreamingResponse 流式传输
  src/routing/priority_queue.py — PriorityMessageQueue 优先级队列
"""

# 从 routing 包 re-export 全部公开名称
from src.routing import (  # noqa: F401
    # 常量
    CHAIN_DISCUSS_TRIGGERS,
    SERVICE_WORKFLOW_ACTION_HINTS,
    SERVICE_WORKFLOW_NOUN_HINTS,
    SERVICE_WORKFLOW_SKIP_HINTS,
    Intent,
    INTENT_BOT_MAP,
    INTENT_KEYWORDS,
    LANE_ROUTE_RULES,
    FALLBACK_ROTATION,
    # 数据模型
    BotCapability,
    ServiceWorkflowSession,
    CollabPhase,
    CollabTask,
    MessagePriority,
    PrioritizedMessage,
    # 核心组件
    ChatRouter,
    CollabOrchestrator,
    StreamingResponse,
    stream_llm_to_telegram,
    PriorityMessageQueue,
)

# 向后兼容：原文件中的带下划线私有变量
_FALLBACK_ROTATION = FALLBACK_ROTATION
