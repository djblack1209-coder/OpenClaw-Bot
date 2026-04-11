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

from src.http_client import ResilientHTTPClient
from ..error_utils import safe_error as _safe_error

logger = logging.getLogger(__name__)
router = APIRouter()

# New-API 服务地址和管理员令牌（从环境变量读取）
_NEWAPI_BASE: str = os.getenv("NEWAPI_BASE_URL", "http://localhost:3000")
_NEWAPI_TOKEN: str = os.getenv("NEWAPI_ADMIN_TOKEN", "")

# 模块级别 HTTP 客户端（自动重试 + 熔断）
_http = ResilientHTTPClient(timeout=10.0, name="newapi_proxy")


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
        resp = await _http.get(f"{_NEWAPI_BASE}/api/status")
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
        resp = await _http.get(
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
        resp = await _http.get(
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
        resp = await _http.post(
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


@router.put("/newapi/channels/{channel_id}")
async def update_channel(channel_id: int, payload: ChannelCreate) -> dict[str, Any]:
    """更新通道 — 代理转发 PUT /api/channel/ 接口"""
    try:
        data = payload.model_dump()
        data["id"] = channel_id
        resp = await _http.request(
            "PUT",
            f"{_NEWAPI_BASE}/api/channel/",
            headers=_headers(),
            json=data,
        )
        resp.raise_for_status()
        body = resp.json()
        inner_data = body.get("data", body) if isinstance(body, dict) else body
        return {"success": True, "data": inner_data}
    except httpx.ConnectError:
        return {"success": False, "error": "无法连接到 New-API 服务"}
    except Exception as e:
        logger.exception("更新 New-API 通道失败")
        return {"success": False, "error": _safe_error(e)}


@router.delete("/newapi/channels/{channel_id}")
async def delete_channel(channel_id: int) -> dict[str, Any]:
    """删除通道 — 代理转发 DELETE /api/channel/{id} 接口"""
    try:
        resp = await _http.request(
            "DELETE",
            f"{_NEWAPI_BASE}/api/channel/{channel_id}",
            headers=_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        return {"success": body.get("success", True)}
    except httpx.ConnectError:
        return {"success": False, "error": "无法连接到 New-API 服务"}
    except Exception as e:
        logger.exception("删除 New-API 通道失败")
        return {"success": False, "error": _safe_error(e)}


@router.post("/newapi/channels/{channel_id}/status")
async def toggle_channel_status(channel_id: int) -> dict[str, Any]:
    """切换通道启用/禁用状态 — 先获取当前状态再反转"""
    try:
        # 获取通道详情
        resp = await _http.get(
            f"{_NEWAPI_BASE}/api/channel/{channel_id}",
            headers=_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        channel_data = body.get("data", body)
        current_status = channel_data.get("status", 1)
        # 切换状态: 1(启用) ↔ 2(禁用)
        new_status = 2 if current_status == 1 else 1
        channel_data["status"] = new_status
        # 更新
        resp2 = await _http.request(
            "PUT",
            f"{_NEWAPI_BASE}/api/channel/",
            headers=_headers(),
            json=channel_data,
        )
        resp2.raise_for_status()
        return {"success": True, "status": new_status}
    except httpx.ConnectError:
        return {"success": False, "error": "无法连接到 New-API 服务"}
    except Exception as e:
        logger.exception("切换 New-API 通道状态失败")
        return {"success": False, "error": _safe_error(e)}


@router.delete("/newapi/tokens/{token_id}")
async def delete_token(token_id: int) -> dict[str, Any]:
    """删除令牌 — 代理转发 DELETE /api/token/{id} 接口"""
    try:
        resp = await _http.request(
            "DELETE",
            f"{_NEWAPI_BASE}/api/token/{token_id}",
            headers=_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        return {"success": body.get("success", True)}
    except httpx.ConnectError:
        return {"success": False, "error": "无法连接到 New-API 服务"}
    except Exception as e:
        logger.exception("删除 New-API 令牌失败")
        return {"success": False, "error": _safe_error(e)}
