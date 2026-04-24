"""Router package — each file handles one API domain"""

from .cli import router as router_cli
from .controls import router as router_controls
from .conversation import router as router_conversation
from .cookies import router as router_cookies
from .evolution import router as router_evolution
from .memory import router as router_memory
from .monitor import router as router_monitor
from .newapi import router as router_newapi
from .omega import router as router_omega
from .pool import router as router_pool
from .shopping import router as router_shopping
from .social import router as router_social
from .store import router as router_store
from .system import router as router_system
from .trading import router as router_trading
from .wechat import router as router_wechat
from .ws import router as router_ws
from .xianyu import router as router_xianyu

__all__ = [
    "router_cli",
    "router_controls",
    "router_conversation",
    "router_cookies",
    "router_evolution",
    "router_memory",
    "router_monitor",
    "router_newapi",
    "router_omega",
    "router_pool",
    "router_shopping",
    "router_social",
    "router_store",
    "router_system",
    "router_trading",
    "router_wechat",
    "router_ws",
    "router_xianyu",
]
