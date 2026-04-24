"""
ClawBot Internal API Server
搬运自 freqtrade/rpc/api_server/webserver.py + Open WebUI main.py 模式

启动方式: 在 multi_main.py 中调用 start_api_server(port=18790)
"""

import logging
import os
import threading
import time
from collections import defaultdict
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse as StarletteJSONResponse

from ..core.user_error import humanize_error
from .auth import log_token_status, verify_api_token
from .routers import (
    router_cli,
    router_controls,
    router_conversation,
    router_cookies,
    router_evolution,
    router_memory,
    router_monitor,
    router_newapi,
    router_omega,
    router_pool,
    router_shopping,
    router_social,
    router_store,
    router_system,
    router_trading,
    router_wechat,
    router_ws,
    router_xianyu,
)

logger = logging.getLogger(__name__)

# Singleton
_api_server: Optional["APIServer"] = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    基于客户端 IP 的滑动窗口速率限制中间件（HI-490）

    实现原理：
    - 为每个 IP 维护一个请求时间戳列表
    - 每次请求时清除窗口外的旧时间戳，再判断窗口内请求数是否超限
    - 使用线程锁保证并发安全（uvicorn 可能多线程）
    - 不依赖任何第三方库，纯标准库实现
    - WebSocket 升级请求直接跳过（BaseHTTPMiddleware 不支持 WS scope）
    """

    # 默认限制：每个 IP 每分钟 300 次请求
    # 较高阈值：此服务仅监听 localhost，供 Tauri 桌面端单用户使用，
    # 前端多个组件并行轮询（5s/10s/15s/30s）轻松超过 60 req/min。
    MAX_REQUESTS: int = 300
    WINDOW_SECONDS: int = 60

    def __init__(self, app, max_requests: int = 300, window_seconds: int = 60):
        super().__init__(app)
        self.MAX_REQUESTS = max_requests
        self.WINDOW_SECONDS = window_seconds
        # 每个 IP 对应一个请求时间戳列表
        self._request_log: dict[str, list[float]] = defaultdict(list)
        # 线程锁，防止并发写入时数据竞争
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        # WebSocket 请求跳过速率限制（BaseHTTPMiddleware 不支持 WS scope，直接 passthrough）
        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)

    def _get_client_ip(self, request) -> str:
        """提取客户端真实 IP，优先取反代转发头"""
        # X-Forwarded-For 可能包含多个 IP，取第一个（最接近客户端的）
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        # X-Real-IP 是 Nginx 常用的单 IP 头
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        # 兜底：直连客户端 IP
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request, call_next):
        client_ip = self._get_client_ip(request)
        now = time.monotonic()

        with self._lock:
            # 取出该 IP 的请求时间戳列表
            timestamps = self._request_log[client_ip]
            # 滑动窗口：只保留窗口内的时间戳
            window_start = now - self.WINDOW_SECONDS
            self._request_log[client_ip] = [ts for ts in timestamps if ts > window_start]
            timestamps = self._request_log[client_ip]

            if len(timestamps) >= self.MAX_REQUESTS:
                # 超限：计算最早时间戳对应的重试时间
                retry_after = int(timestamps[0] - window_start) + 1
                logger.warning(
                    "速率限制触发: IP=%s, 窗口内请求数=%d, 限制=%d",
                    client_ip,
                    len(timestamps),
                    self.MAX_REQUESTS,
                )
                return StarletteJSONResponse(
                    status_code=429,
                    content={
                        "error": "请求过于频繁，请稍后再试",
                        "detail": f"每 {self.WINDOW_SECONDS} 秒最多 {self.MAX_REQUESTS} 次请求",
                        "retry_after_seconds": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            # 未超限：记录本次请求时间戳
            timestamps.append(now)

        # 定期清理不活跃 IP 的记录，防止内存泄漏（每 1000 次请求清理一次）
        self._maybe_cleanup(now)

        return await call_next(request)

    def _maybe_cleanup(self, now: float):
        """清理长时间无请求的 IP 记录，防止字典无限增长"""
        # 简单策略：总 IP 数超过 10000 时清理
        if len(self._request_log) > 10000:
            with self._lock:
                window_start = now - self.WINDOW_SECONDS
                stale_ips = [
                    ip for ip, ts_list in self._request_log.items() if not ts_list or ts_list[-1] <= window_start
                ]
                for ip in stale_ips:
                    del self._request_log[ip]
                if stale_ips:
                    logger.info("速率限制清理: 移除 %d 个不活跃 IP 记录", len(stale_ips))


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    限制请求体大小（默认 10MB），超过直接返回 413

    防护两种场景（HI-491 修复）：
    1. 有 Content-Length 头：直接比较数值，快速拒绝
    2. chunked 传输编码（无 Content-Length）：流式读取时累计字节数，超限立即中断

    WebSocket 升级请求直接跳过（BaseHTTPMiddleware 不支持 WS scope）
    """

    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB

    async def __call__(self, scope, receive, send):
        # WebSocket 请求跳过体积限制（BaseHTTPMiddleware 不支持 WS scope，直接 passthrough）
        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)

    async def dispatch(self, request, call_next):
        content_length = request.headers.get("content-length")
        transfer_encoding = request.headers.get("transfer-encoding", "").lower()

        # 场景 1：有 Content-Length 头，直接判断
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            return StarletteJSONResponse(
                status_code=413,
                content={"error": "请求体过大，最大允许 10MB"},
            )

        # 场景 2：chunked 传输编码（无 Content-Length），需要流式读取并累计字节数
        if "chunked" in transfer_encoding and not content_length:
            # 读取请求体并检查大小
            body = b""
            async for chunk in request.stream():
                body += chunk
                if len(body) > self.MAX_BODY_SIZE:
                    logger.warning(
                        "chunked 请求体超限: 已读取 %d 字节, 限制 %d 字节",
                        len(body),
                        self.MAX_BODY_SIZE,
                    )
                    return StarletteJSONResponse(
                        status_code=413,
                        content={"error": "请求体过大，最大允许 10MB"},
                    )
            # 将已读取的 body 重新注入 request，让后续处理器能正常读取
            # Starlette 的 Request 对象在 stream 被消费后，需要通过 _body 属性恢复
            request._body = body

        return await call_next(request)


class APIServer:
    """
    Threaded FastAPI server — runs alongside the Telegram bots.
    Pattern: freqtrade's UvicornServer running in a daemon thread.
    """

    def __init__(self, port: int = 18790, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

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
            # 兜底异常处理器 — 用 humanize_error 将技术异常转为中文人话
            user_msg = humanize_error(exc)
            logger.error(
                "API请求异常 %s %s: %s",
                request.method, request.url.path, exc, exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={"success": False, "detail": user_msg},
            )

    def _configure_app(self):
        """Mount routers and middleware — pattern from freqtrade webserver.py"""
        # 速率限制 — 防止 Token 泄露后被暴力调用（HI-490）
        self.app.add_middleware(RateLimitMiddleware)
        # 请求体大小限制 — 防止超大请求消耗资源（含 chunked 传输防绕过 HI-491）
        self.app.add_middleware(RequestSizeLimitMiddleware)

        # CORS — 允许本地开发和 Tauri 生产环境访问
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:1420",      # Vite dev（localhost）
                "http://127.0.0.1:1420",      # Vite dev（IP 地址，浏览器调试模式）
                f"http://localhost:{os.environ.get('GATEWAY_PORT', '18789')}",  # OpenClaw gateway
                f"http://127.0.0.1:{os.environ.get('GATEWAY_PORT', '18789')}",  # OpenClaw gateway（IP）
                "tauri://localhost",          # Tauri 生产（macOS/Linux）
                "https://tauri.localhost",    # Tauri 生产（Windows）
            ],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
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
        self.app.include_router(router_newapi, prefix="/api/v1", tags=["New-API"])
        self.app.include_router(router_controls, prefix="/api/v1", tags=["Controls"])
        self.app.include_router(router_conversation, prefix="/api/v1", tags=["Conversation"])
        self.app.include_router(router_xianyu, prefix="/api/v1", tags=["Xianyu"])
        self.app.include_router(router_cli, prefix="/api/v1", tags=["CLI"])
        self.app.include_router(router_monitor, prefix="/api/v1", tags=["WorldMonitor"])
        self.app.include_router(router_wechat, prefix="/api/v1", tags=["WeChat"])
        self.app.include_router(router_cookies, prefix="/api/v1", tags=["Cookies"])
        self.app.include_router(router_store, prefix="/api/v1", tags=["Store"])

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
