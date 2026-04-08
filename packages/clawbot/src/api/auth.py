"""
FastAPI API 认证中间件 — 共享密钥 Token 验证。

使用方式:
  1. 在 config/.env 中设置 OPENCLAW_API_TOKEN=<random-secret>
  2. 客户端请求时带 Header: X-API-Token: <secret>
  3. 未配置 Token 时自动降级为无认证 (开发模式)

设计原则:
  - 不阻塞开发: 未设 OPENCLAW_API_TOKEN 时所有请求通过 (附 warning 日志)
  - 轻量: 纯 Header 验证, 无 JWT/数据库
  - WebSocket 兼容: WS 连接通过 query param ?token= 验证
"""
import hmac
import os
import logging
from typing import Optional

from fastapi import HTTPException, Depends, WebSocket
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

# 从环境变量读取 (python-dotenv 在 multi_main.py 启动时已加载)
_API_TOKEN: str = os.getenv("OPENCLAW_API_TOKEN", "")

# 首次警告标志
_warned_no_token: bool = False

_header_scheme = APIKeyHeader(name="X-API-Token", auto_error=False)


def log_token_status() -> None:
    """启动时记录 Token 配置状态 — 应在 app 启动后调用一次。"""
    if not _API_TOKEN:
        # 检查是否绑定到非 localhost (可能是生产环境)
        # 注意: 0.0.0.0 绑定全部网络接口，应视为外网暴露 (HI-387)
        bind_host = os.getenv("API_HOST", "127.0.0.1")
        env_mode = os.getenv("ENV", "development").lower()
        if env_mode == "production":
            logger.critical(
                "[API Auth] ⚠️ 生产环境未配置 OPENCLAW_API_TOKEN! "
                "所有 API 请求将被拒绝。请设置 OPENCLAW_API_TOKEN 环境变量。"
            )
        elif bind_host not in ("127.0.0.1", "localhost"):
            logger.critical(
                "[API Auth] ⚠️ 危险: API 绑定到外网地址 %s 但未配置认证 Token! "
                "设置 OPENCLAW_API_TOKEN 环境变量或改为绑定 127.0.0.1", bind_host
            )
        else:
            logger.warning(
                "[API Auth] OPENCLAW_API_TOKEN 未配置 — API 运行在无认证模式 (仅限开发环境!)"
            )
    else:
        logger.info("[API Auth] API Token 认证已启用")


async def verify_api_token(
    api_key: Optional[str] = Depends(_header_scheme),
) -> None:
    """FastAPI dependency: 验证 X-API-Token header。

    - Token 未配置: 所有请求放行 (开发模式), 首次打印 warning
    - Token 已配置但请求缺失/不匹配: 返回 401
    """
    global _warned_no_token

    # 未配置 Token 时：仅允许 localhost 请求通过（开发模式安全降级）
    if not _API_TOKEN:
        env_mode = os.getenv("ENV", "development").lower()
        bind_host = os.getenv("API_HOST", "127.0.0.1")
        # 生产环境无 Token → 强制拒绝所有请求
        if env_mode == "production":
            raise HTTPException(
                status_code=503,
                detail="生产环境未配置 OPENCLAW_API_TOKEN，拒绝所有请求。"
            )
        if bind_host not in ("127.0.0.1", "localhost"):
            # 绑定到非 localhost 地址但未配置 Token → 强制拒绝所有请求
            raise HTTPException(
                status_code=503,
                detail="API 认证未配置且绑定到外网地址，拒绝所有请求。请设置 OPENCLAW_API_TOKEN 环境变量。"
            )
        if not _warned_no_token:
            logger.warning(
                "[API Auth] 请求未验证 — 设置 OPENCLAW_API_TOKEN 环境变量以启用认证"
            )
            _warned_no_token = True
        return

    # Token 已配置但请求未携带
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")

    # 使用 hmac.compare_digest 防止时序攻击（逐字符比较时间相同）
    if not hmac.compare_digest(api_key, _API_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


def verify_ws_token(websocket: WebSocket) -> bool:
    """验证 WebSocket 连接的 token (通过 query param ?token=xxx)。

    Returns:
        True 如果验证通过或 Token 未配置 (开发模式)
        False 如果验证失败
    """
    if not _API_TOKEN:
        return True

    token = websocket.query_params.get("token", "")
    # 使用 hmac.compare_digest 防止时序攻击（与 HTTP 认证保持一致）
    return hmac.compare_digest(token, _API_TOKEN)
