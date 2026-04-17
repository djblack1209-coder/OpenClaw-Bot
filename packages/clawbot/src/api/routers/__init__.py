"""Router package — each file handles one API domain"""

from .system import router as router_system
from .trading import router as router_trading
from .social import router as router_social
from .memory import router as router_memory
from .pool import router as router_pool
from .ws import router as router_ws
from .evolution import router as router_evolution
from .shopping import router as router_shopping
from .omega import router as router_omega
from .newapi import router as router_newapi
from .controls import router as router_controls
from .conversation import router as router_conversation
from .xianyu import router as router_xianyu

__all__ = [
    "router_system",
    "router_trading",
    "router_social",
    "router_memory",
    "router_pool",
    "router_ws",
    "router_evolution",
    "router_shopping",
    "router_omega",
    "router_newapi",
    "router_controls",
    "router_conversation",
    "router_xianyu",
]
