"""
ClawBot Internal API Server
搬运自 freqtrade/rpc/api_server/webserver.py + Open WebUI main.py 模式

启动方式: 在 multi_main.py 中调用 start_api_server(port=18790)
"""
import asyncio
import logging
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import router_system, router_trading, router_social, router_memory, router_pool, router_ws, router_evolution, router_shopping, router_omega

logger = logging.getLogger(__name__)

# Singleton
_api_server: Optional["APIServer"] = None


class APIServer:
    """
    Threaded FastAPI server — runs alongside the Telegram bots.
    Pattern: freqtrade's UvicornServer running in a daemon thread.
    """

    def __init__(self, port: int = 18790, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self._thread: Optional[threading.Thread] = None
        self._server: Optional[uvicorn.Server] = None

        self.app = FastAPI(
            title="ClawBot Internal API",
            description="Internal control API for ClawBot — consumed by the Tauri Manager app",
            version="1.0.0",
            docs_url="/api/docs",
            redoc_url=None,
        )

        self._configure_app()

    def _configure_app(self):
        """Mount routers and middleware — pattern from freqtrade webserver.py"""
        # CORS — only localhost (Tauri Manager)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:1420",     # Tauri dev
                "http://localhost:18789",    # OpenClaw gateway
                "tauri://localhost",         # Tauri production
                "https://tauri.localhost",   # Tauri production (Windows)
            ],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Public — no auth (localhost only, so OK)
        self.app.include_router(router_system, prefix="/api/v1", tags=["System"])
        self.app.include_router(router_trading, prefix="/api/v1", tags=["Trading"])
        self.app.include_router(router_social, prefix="/api/v1", tags=["Social"])
        self.app.include_router(router_memory, prefix="/api/v1", tags=["Memory"])
        self.app.include_router(router_pool, prefix="/api/v1", tags=["API Pool"])
        self.app.include_router(router_ws, prefix="/api/v1", tags=["WebSocket"])
        self.app.include_router(router_evolution, prefix="/api/v1", tags=["Evolution"])
        self.app.include_router(router_shopping, prefix="/api/v1", tags=["Shopping"])
        self.app.include_router(router_omega, prefix="/api/v1", tags=["OMEGA"])

    def start(self):
        """Start uvicorn in a daemon thread"""
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        self._thread = threading.Thread(
            target=self._server.run,
            name="clawbot-api-server",
            daemon=True,
        )
        self._thread.start()
        logger.info("ClawBot Internal API: http://%s:%d/api/docs", self.host, self.port)

    def stop(self):
        """Graceful shutdown"""
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("ClawBot Internal API stopped")


def start_api_server(port: int = 18790, host: str = "127.0.0.1") -> APIServer:
    """Start the internal API server — called from multi_main.py"""
    global _api_server
    if _api_server is not None:
        logger.warning("API server already running")
        return _api_server
    
    _api_server = APIServer(port=port, host=host)
    _api_server.start()
    return _api_server


def stop_api_server():
    """Stop the internal API server"""
    global _api_server
    if _api_server:
        _api_server.stop()
        _api_server = None
