"""
ClawBot - Telegram AI 助手 (v5.0 Mixin 架构版)
"""

import os

# ClawBot 会创建会话、订单、记忆和证据文件；默认只允许当前系统用户访问。
os.umask(0o077)

from .context_manager import ContextManager  # noqa: E402
from .history_store import HistoryStore  # noqa: E402
from .http_client import ResilientHTTPClient  # noqa: E402
from .monitoring import AutoRecovery, HealthChecker, StructuredLogger  # noqa: E402
from .routing import ChatRouter  # noqa: E402

__all__ = [
    "AutoRecovery",
    "ChatRouter",
    "ContextManager",
    "HealthChecker",
    "HistoryStore",
    "ResilientHTTPClient",
    "StructuredLogger",
]
__version__ = "5.0.0"
