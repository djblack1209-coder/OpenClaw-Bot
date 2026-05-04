"""
New-API 管理代理端点 — 通过 FastAPI 转发 new-api 管理接口请求。

提供状态检查、通道管理、令牌管理等功能的代理转发，
让 Tauri 桌面端通过统一的 ClawBot API 访问 new-api 后台。
"""

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel

from src.http_client import ResilientHTTPClient

from ..error_utils import safe_error as _safe_error

logger = logging.getLogger(__name__)
router = APIRouter()

# New-API 服务地址和管理员令牌（从环境变量读取）
_NEWAPI_BASE: str = os.getenv("NEWAPI_BASE_URL", "http://localhost:3000")
_NEWAPI_TOKEN: str = os.getenv("NEWAPI_ADMIN_TOKEN", "")
_NEWAPI_USER_ID: str = os.getenv("NEWAPI_ADMIN_USER_ID", os.getenv("NEWAPI_USER_ID", ""))

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


class TokenCreate(BaseModel):
    """创建或更新 New-API 用户令牌的请求体"""

    name: str
    remain_quota: int = 0
    expired_time: int = -1
    unlimited_quota: bool = True
    model_limits_enabled: bool = False
    model_limits: str = ""
    allow_ips: str = ""
    group: str = ""
    cross_group_retry: bool = False


def _headers() -> dict[str, str]:
    """构建请求头 — 携带管理员令牌"""
    if not _NEWAPI_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="NEWAPI_ADMIN_TOKEN 未配置，无法访问 New-API 管理接口",
        )
    headers = {
        "Authorization": f"Bearer {_NEWAPI_TOKEN}",
        "Content-Type": "application/json",
    }
    if _NEWAPI_USER_ID:
        headers["New-Api-User"] = _NEWAPI_USER_ID
    return headers


def _extract_data(body: Any) -> Any:
    """解包 New-API 的标准响应体"""
    return body.get("data", body) if isinstance(body, dict) else body


async def _proxy_json(
    method: str,
    path: str,
    *,
    auth: bool = True,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一代理 New-API JSON 接口，保持业务逻辑在上游服务内执行。"""
    try:
        resp = await _http.request(
            method,
            f"{_NEWAPI_BASE}{path}",
            headers=_headers() if auth else None,
            params=params,
            json=json,
        )
        resp.raise_for_status()
        body = resp.json()
        return {
            "success": body.get("success", True) if isinstance(body, dict) else True,
            "data": _extract_data(body),
            "message": body.get("message", "") if isinstance(body, dict) else "",
        }
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="无法连接到 New-API 服务")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("代理 New-API 接口失败: %s %s", method, path)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/newapi/status")
async def newapi_status() -> dict[str, Any]:
    """检查 New-API 服务是否可用 — 通过请求 /api/status 端点判断"""
    try:
        resp = await _http.get(f"{_NEWAPI_BASE}/api/status")
        if resp.status_code == 200:
            return {"online": True, "data": resp.json()}
        raise HTTPException(status_code=502, detail=f"HTTP {resp.status_code}")
    except httpx.ConnectError:
        # New-API 服务未启动或无法连接
        raise HTTPException(status_code=503, detail="无法连接到 New-API 服务")
    except HTTPException:
        # 让 FastAPI 原样处理 HTTPException（如 502/503），不要被下面的通用异常吞掉
        raise
    except Exception as e:
        logger.exception("检查 New-API 状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


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
        # New-API v1 返回 {"success":true,"data":{items,total,...}}。
        inner_data = _extract_data(body)
        return {"success": True, "data": inner_data}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="无法连接到 New-API 服务")
    except HTTPException:
        # 让 _headers() 抛出的 503 等 HTTPException 原样透传
        raise
    except Exception as e:
        logger.exception("获取 New-API 通道列表失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


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
        # New-API v1 返回 {"success":true,"data":{items,total,...}}。
        inner_data = _extract_data(body)
        return {"success": True, "data": inner_data}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="无法连接到 New-API 服务")
    except HTTPException:
        # 让 _headers() 抛出的 503 等 HTTPException 原样透传
        raise
    except Exception as e:
        logger.exception("获取 New-API 令牌列表失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


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
        # 解包 New-API 返回的 {"success":true,"data":{...}}
        inner_data = _extract_data(body)
        return {"success": True, "data": inner_data}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="无法连接到 New-API 服务")
    except HTTPException:
        # 让 _headers() 抛出的 503 等 HTTPException 原样透传
        raise
    except Exception as e:
        logger.exception("创建 New-API 通道失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.put("/newapi/channels/{channel_id}")
async def update_channel(payload: ChannelCreate, channel_id: int = Path(ge=1, description="通道ID")) -> dict[str, Any]:
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
        inner_data = _extract_data(body)
        return {"success": True, "data": inner_data}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="无法连接到 New-API 服务")
    except HTTPException:
        # 让 _headers() 抛出的 503 等 HTTPException 原样透传
        raise
    except Exception as e:
        logger.exception("更新 New-API 通道失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.delete("/newapi/channels/{channel_id}")
async def delete_channel(channel_id: int = Path(ge=1, description="通道ID")) -> dict[str, Any]:
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
        raise HTTPException(status_code=503, detail="无法连接到 New-API 服务")
    except HTTPException:
        # 让 _headers() 抛出的 503 等 HTTPException 原样透传
        raise
    except Exception as e:
        logger.exception("删除 New-API 通道失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/newapi/channels/{channel_id}/status")
async def toggle_channel_status(channel_id: int = Path(ge=1, description="通道ID")) -> dict[str, Any]:
    """切换通道启用/禁用状态 — 先获取当前状态再反转"""
    try:
        # 获取通道详情
        resp = await _http.get(
            f"{_NEWAPI_BASE}/api/channel/{channel_id}",
            headers=_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        channel_data = _extract_data(body)
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
        raise HTTPException(status_code=503, detail="无法连接到 New-API 服务")
    except HTTPException:
        # 让 _headers() 抛出的 503 等 HTTPException 原样透传
        raise
    except Exception as e:
        logger.exception("切换 New-API 通道状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.delete("/newapi/tokens/{token_id}")
async def delete_token(token_id: int = Path(ge=1, description="令牌ID")) -> dict[str, Any]:
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
        raise HTTPException(status_code=503, detail="无法连接到 New-API 服务")
    except HTTPException:
        # 让 _headers() 抛出的 503 等 HTTPException 原样透传
        raise
    except Exception as e:
        logger.exception("删除 New-API 令牌失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/newapi/tokens/search")
async def search_tokens(
    keyword: str = "",
    token: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """搜索用户令牌 — 代理 New-API /api/token/search"""
    return await _proxy_json(
        "GET",
        "/api/token/search",
        params={"keyword": keyword, "token": token, "p": page, "size": size},
    )


@router.post("/newapi/tokens")
async def create_token(payload: TokenCreate) -> dict[str, Any]:
    """创建用户令牌 — 代理 New-API /api/token/"""
    return await _proxy_json("POST", "/api/token/", json=payload.model_dump())


@router.put("/newapi/tokens/{token_id}")
async def update_token(payload: TokenCreate, token_id: int = Path(ge=1, description="令牌ID")) -> dict[str, Any]:
    """更新用户令牌 — 代理 New-API PUT /api/token/"""
    data = payload.model_dump()
    data["id"] = token_id
    return await _proxy_json("PUT", "/api/token/", json=data)


@router.post("/newapi/tokens/{token_id}/status")
async def update_token_status(
    token_id: int = Path(ge=1, description="令牌ID"),
    status: int = Body(..., embed=True),
) -> dict[str, Any]:
    """启用或禁用用户令牌 — 代理 New-API status_only 更新"""
    return await _proxy_json(
        "PUT",
        "/api/token/",
        params={"status_only": "true"},
        json={"id": token_id, "status": status},
    )


@router.get("/newapi/logs/self")
async def list_self_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    model_name: str = "",
    token_name: str = "",
    group: str = "",
    start_timestamp: int = 0,
    end_timestamp: int = 0,
) -> dict[str, Any]:
    """获取当前用户使用记录 — 代理 New-API /api/log/self"""
    return await _proxy_json(
        "GET",
        "/api/log/self",
        params={
            "p": page,
            "size": size,
            "model_name": model_name,
            "token_name": token_name,
            "group": group,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
        },
    )


@router.get("/newapi/logs/self/stat")
async def self_log_stat(
    model_name: str = "",
    token_name: str = "",
    group: str = "",
    start_timestamp: int = 0,
    end_timestamp: int = 0,
) -> dict[str, Any]:
    """获取当前用户用量统计 — 代理 New-API /api/log/self/stat"""
    return await _proxy_json(
        "GET",
        "/api/log/self/stat",
        params={
            "model_name": model_name,
            "token_name": token_name,
            "group": group,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
        },
    )


@router.get("/newapi/data/self")
async def self_quota_dates(start_timestamp: int, end_timestamp: int) -> dict[str, Any]:
    """获取当前用户 Token 趋势数据 — 代理 New-API /api/data/self"""
    return await _proxy_json(
        "GET",
        "/api/data/self",
        params={"start_timestamp": start_timestamp, "end_timestamp": end_timestamp},
    )


@router.get("/newapi/subscriptions/plans")
async def list_subscription_plans() -> dict[str, Any]:
    """获取可售订阅套餐 — 代理 New-API /api/subscription/plans"""
    return await _proxy_json("GET", "/api/subscription/plans")


@router.get("/newapi/subscriptions/self")
async def subscription_self() -> dict[str, Any]:
    """获取当前用户订阅状态 — 代理 New-API /api/subscription/self"""
    return await _proxy_json("GET", "/api/subscription/self")


@router.get("/newapi/redemptions")
async def list_redemptions(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """获取兑换码列表 — 代理 New-API 管理端 /api/redemption/"""
    return await _proxy_json("GET", "/api/redemption/", params={"p": page, "size": size})


@router.post("/newapi/redemptions")
async def create_redemption(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """创建兑换码 — 代理 New-API /api/redemption/"""
    return await _proxy_json("POST", "/api/redemption/", json=payload)


@router.get("/newapi/pricing")
async def pricing() -> dict[str, Any]:
    """获取模型价格和可用分组 — 代理 New-API /api/pricing"""
    return await _proxy_json("GET", "/api/pricing", auth=False)


@router.get("/newapi/topup/info")
async def topup_info() -> dict[str, Any]:
    """获取充值配置 — 代理 New-API /api/user/topup/info"""
    return await _proxy_json("GET", "/api/user/topup/info")


@router.get("/newapi/aff")
async def affiliate_code() -> dict[str, Any]:
    """获取邀请返利码 — 代理 New-API /api/user/aff"""
    return await _proxy_json("GET", "/api/user/aff")


@router.post("/newapi/aff/transfer")
async def affiliate_transfer(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """把邀请返利转入余额 — 代理 New-API /api/user/aff_transfer"""
    return await _proxy_json("POST", "/api/user/aff_transfer", json=payload)
