"""
New-API 管理代理端点 — 通过 FastAPI 转发 new-api 管理接口请求。

提供状态检查、通道管理、令牌管理等功能的代理转发，
让 Tauri 桌面端通过统一的 ClawBot API 访问 new-api 后台。
"""
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from ..error_utils import safe_error as _safe_error

logger = logging.getLogger(__name__)
router = APIRouter()

# New-API 服务地址和管理员令牌（从环境变量读取）
_NEWAPI_BASE: str = os.getenv("NEWAPI_BASE_URL", "http://localhost:3000")
_NEWAPI_TOKEN: str = os.getenv("NEWAPI_ADMIN_TOKEN", "")

# HTTP 客户端超时（秒）
_TIMEOUT: float = 10.0


class ChannelCreate(BaseModel):
    """创建通道的请求体"""
    name: str
    type: int = 1
    key: str = ""
    base_url: str = ""
    models: str = ""
    group: str = "default"


def _headers() -> dict[str, str]:
    """构建请求头 — 携带管理员令牌"""
    return {
        "Authorization": f"Bearer {_NEWAPI_TOKEN}",
        "Content-Type": "application/json",
    }


@router.get("/newapi/status")
async def newapi_status() -> dict[str, Any]:
    """检查 New-API 服务是否可用 — 通过请求 /api/status 端点判断"""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_NEWAPI_BASE}/api/status")
            if resp.status_code == 200:
                return {"online": True, "data": resp.json()}
            return {"online": False, "error": f"HTTP {resp.status_code}"}
    except httpx.ConnectError:
        # New-API 服务未启动或无法连接
        return {"online": False, "error": "无法连接到 New-API 服务"}
    except Exception as e:
        logger.exception("检查 New-API 状态失败")
        return {"online": False, "error": _safe_error(e)}


@router.get("/newapi/channels")
async def list_channels() -> dict[str, Any]:
    """获取所有通道列表 — 代理转发 /api/channel/ 接口，解包后直接返回数据数组"""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_NEWAPI_BASE}/api/channel/",
                headers=_headers(),
                params={"p": 0},
            )
            resp.raise_for_status()
            body = resp.json()
            # new-api 返回 {"success":true,"data":[...]} — 直接提取内层 data 数组
            inner_data = body.get("data", body) if isinstance(body, dict) else body
            return {"success": True, "data": inner_data}
    except httpx.ConnectError:
        return {"success": False, "error": "无法连接到 New-API 服务"}
    except Exception as e:
        logger.exception("获取 New-API 通道列表失败")
        return {"success": False, "error": _safe_error(e)}


@router.get("/newapi/tokens")
async def list_tokens() -> dict[str, Any]:
    """获取所有令牌列表 — 代理转发 /api/token/ 接口，解包后直接返回数据数组"""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_NEWAPI_BASE}/api/token/",
                headers=_headers(),
                params={"p": 0},
            )
            resp.raise_for_status()
            body = resp.json()
            # new-api 返回 {"success":true,"data":[...]} — 直接提取内层 data 数组
            inner_data = body.get("data", body) if isinstance(body, dict) else body
            return {"success": True, "data": inner_data}
    except httpx.ConnectError:
        return {"success": False, "error": "无法连接到 New-API 服务"}
    except Exception as e:
        logger.exception("获取 New-API 令牌列表失败")
        return {"success": False, "error": _safe_error(e)}


@router.post("/newapi/channels")
async def create_channel(payload: ChannelCreate) -> dict[str, Any]:
    """创建新通道 — 代理转发 /api/channel/ 接口"""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_NEWAPI_BASE}/api/channel/",
                headers=_headers(),
                json=payload.model_dump(),
            )
            resp.raise_for_status()
            body = resp.json()
            # 解包 new-api 返回的 {"success":true,"data":{...}}
            inner_data = body.get("data", body) if isinstance(body, dict) else body
            return {"success": True, "data": inner_data}
    except httpx.ConnectError:
        return {"success": False, "error": "无法连接到 New-API 服务"}
    except Exception as e:
        logger.exception("创建 New-API 通道失败")
        return {"success": False, "error": _safe_error(e)}
