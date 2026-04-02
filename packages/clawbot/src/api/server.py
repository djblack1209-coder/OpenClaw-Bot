"""
ClawBot Internal API Server
搬运自 freqtrade/rpc/api_server/webserver.py + Open WebUI main.py 模式

启动方式: 在 multi_main.py 中调用 start_api_server(port=18790)
"""
import logging
import os
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import verify_api_token, log_token_status
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

        # 安全加固: 生产环境关闭 API 文档页面
        _is_production = os.environ.get("ENV", "").lower() in ("prod", "production")
        self.app = FastAPI(
            title="ClawBot Internal API",
            description="Internal control API for ClawBot — consumed by the Tauri Manager app",
            version="1.0.0",
            docs_url=None if _is_production else "/api/docs",
            redoc_url=None,
            dependencies=[Depends(verify_api_token)],
        )

        self._configure_app()
        self._register_exception_handlers()

    def _register_exception_handlers(self):
        """注册全局异常处理器 — 防止 Pydantic 模型信息泄露和未处理异常暴露堆栈"""

        @self.app.exception_handler(RequestValidationError)
        async def validation_handler(request, exc):
            # 只返回通用错误消息，不泄露内部模型字段名
            logger.debug("请求参数验证失败: %s", exc.errors())
            return JSONResponse(
                status_code=422,
                content={"detail": "请求参数验证失败，请检查参数格式"},
            )

        @self.app.exception_handler(Exception)
        async def catch_all_handler(request, exc):
            # 兜底异常处理器，防止未捕获异常返回含堆栈的默认 500
            logger.error("未处理的 API 异常: %s", exc, exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"detail": "内部服务错误"},
            )

    def _configure_app(self):
        """Mount routers and middleware — pattern from freqtrade webserver.py"""
        # CORS — only localhost (Tauri Manager)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:1420",     # Tauri dev
                f"http://localhost:{os.environ.get('GATEWAY_PORT', '18789')}",    # OpenClaw gateway
                "tauri://localhost",         # Tauri production
                "https://tauri.localhost",   # Tauri production (Windows)
            ],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["X-API-Token", "Content-Type", "Authorization"],
        )

        # Routers — protected by global verify_api_token dependency
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
        log_token_status()

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
