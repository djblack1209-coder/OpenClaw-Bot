"""System status endpoints — ping, version, full status, daily-brief, notifications, services"""

import asyncio
import logging
import os
import subprocess
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC
from ..schemas import Ping, SystemStatus

logger = logging.getLogger(__name__)
router = APIRouter()


# ============ 原有端点 ============


@router.get("/ping", response_model=Ping)
def ping():
    """系统存活检测"""
    try:
        return ClawBotRPC._rpc_ping()
    except Exception as e:
        logger.exception("Ping 失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/status", response_model=SystemStatus)
def system_status():
    """获取完整系统状态"""
    try:
        return ClawBotRPC._rpc_system_status()
    except Exception as e:
        logger.exception("获取系统状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


# ============ 今日简报 ============


@router.get("/system/daily-brief")
async def daily_brief():
    """获取首页今日简报数据 — 聚合各模块关键指标

    返回:
    - date: 日期字符串
    - system_status: 系统整体状态 (healthy/degraded/error)
    - metrics: {portfolio_pnl, positions_count, xianyu_consultations, xianyu_orders, social_posts, api_daily_cost, market_sentiment}
    - modules: [{name, status, summary}] 各模块快速状态
    """
    try:
        now = datetime.now()
        result: Dict[str, Any] = {
            "date": now.strftime("%Y年%m月%d日"),
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
            "system_status": "healthy",
            "metrics": {},
            "modules": [],
        }

        # 收集各模块指标（复用 daily_brief_data 的收集逻辑）
        try:
            from src.execution.daily_brief_data import _collect_brief_metrics

            metrics = await _collect_brief_metrics()
            result["metrics"] = {
                "portfolio_pnl": metrics.get("portfolio_pnl", 0),
                "positions_count": metrics.get("positions_count", 0),
                "xianyu_consultations": metrics.get("xianyu_consultations", 0),
                "xianyu_orders": metrics.get("xianyu_orders", 0),
                "social_posts": metrics.get("social_posts", 0),
                "api_daily_cost": metrics.get("api_daily_cost", 0),
                "market_sentiment": metrics.get("market_sentiment", ""),
                "deltas": metrics.get("deltas", {}),
            }
        except Exception as e:
            logger.warning("简报指标收集失败: %s", e)

        # 各模块状态
        try:
            status_data = ClawBotRPC._rpc_system_status()

            # Bot 状态汇总
            bots = status_data.get("bots", [])
            alive_count = sum(1 for b in bots if b.get("alive"))
            total_count = len(bots)
            bot_status = (
                "online"
                if alive_count == total_count and total_count > 0
                else ("degraded" if alive_count > 0 else "offline")
            )

            result["modules"] = [
                {
                    "name": "投资组合",
                    "status": "online" if result["metrics"].get("positions_count", 0) > 0 else "idle",
                    "summary": f"{result['metrics'].get('positions_count', 0)} 个持仓",
                },
                {
                    "name": "闲鱼客服",
                    "status": "online" if status_data.get("xianyu", {}).get("running") else "offline",
                    "summary": f"今日 {result['metrics'].get('xianyu_consultations', 0)} 咨询",
                },
                {
                    "name": "社媒运营",
                    "status": "online" if status_data.get("social", {}).get("scheduler_running") else "idle",
                    "summary": f"今日 {result['metrics'].get('social_posts', 0)} 帖",
                },
                {
                    "name": "AI 机器人",
                    "status": bot_status,
                    "summary": f"{alive_count}/{total_count} 在线",
                },
            ]

            # 整体状态判定
            offline_count = sum(1 for m in result["modules"] if m["status"] == "offline")
            if offline_count >= 2:
                result["system_status"] = "error"
            elif offline_count >= 1:
                result["system_status"] = "degraded"
        except Exception as e:
            logger.warning("简报模块状态收集失败: %s", e)

        return result
    except Exception as e:
        logger.exception("获取今日简报失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


# ============ 通知中心 ============

# 内存通知存储（轻量实现 — 可以接收 EventBus 推送的事件）
_notifications: deque = deque(maxlen=200)
_notification_counter: int = 0


def push_notification(
    title: str,
    body: str,
    category: str = "system",
    level: str = "info",
    action_url: str = "",
) -> Dict[str, Any]:
    """推送一条通知（供其他模块调用）

    category: system / trading / xianyu / social / security / ai
    level: info / warning / error / success
    """
    global _notification_counter
    _notification_counter += 1
    notif = {
        "id": f"n-{uuid.uuid4().hex[:8]}",
        "seq": _notification_counter,
        "title": title,
        "body": body,
        "category": category,
        "level": level,
        "action_url": action_url,
        "read": False,
        "created_at": datetime.now().isoformat(),
    }
    _notifications.appendleft(notif)
    return notif


@router.get("/system/notifications")
def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    category: Optional[str] = Query(default=None, description="按类别过滤: system/trading/xianyu/social/security/ai"),
    unread_only: bool = Query(default=False, description="只返回未读通知"),
):
    """获取通知列表"""
    try:
        items = list(_notifications)

        # 过滤
        if category:
            items = [n for n in items if n["category"] == category]
        if unread_only:
            items = [n for n in items if not n["read"]]

        items = items[:limit]
        unread_count = sum(1 for n in _notifications if not n["read"])

        return {
            "notifications": items,
            "total": len(_notifications),
            "unread_count": unread_count,
        }
    except Exception as e:
        logger.exception("获取通知列表失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/system/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str = Path(...)):
    """标记通知为已读"""
    for notif in _notifications:
        if notif["id"] == notification_id:
            notif["read"] = True
            return {"ok": True}
    raise HTTPException(status_code=404, detail="通知不存在")


@router.post("/system/notifications/read-all")
def mark_all_notifications_read():
    """标记所有通知为已读"""
    count = 0
    for notif in _notifications:
        if not notif["read"]:
            notif["read"] = True
            count += 1
    return {"ok": True, "marked_count": count}


# ============ 服务管理 ============

# 服务定义表（与前端 Bots 页面的自动化脚本卡片对应）
_SERVICE_REGISTRY: List[Dict[str, Any]] = [
    {
        "id": "clawbot-agent",
        "name": "AI 助手后端",
        "description": "核心 AI 引擎 + Telegram Bot + FastAPI",
        "process_keyword": "multi_main",
        "port": 18790,
    },
    {
        "id": "xianyu",
        "name": "闲鱼 AI 客服",
        "description": "闲鱼平台自动回复 + 智能议价",
        "process_keyword": "xianyu_main",
        "port": None,
    },
    {
        "id": "gateway",
        "name": "API 网关",
        "description": "Kiro 反向代理网关",
        "process_keyword": "kiro",
        "port": 18789,
    },
    {
        "id": "g4f",
        "name": "G4F 免费模型",
        "description": "g4f-api 免费 LLM 提供者",
        "process_keyword": "g4f",
        "port": 18891,
    },
    {
        "id": "newapi",
        "name": "New-API 网关",
        "description": "LLM API 统一管理网关",
        "process_keyword": "new-api",
        "port": 3000,
    },
]


def _check_process_alive(keyword: str) -> bool:
    """通过 pgrep 检测进程是否存活"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", keyword],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


@router.get("/system/services")
def list_services():
    """获取所有服务的运行状态"""
    try:
        services = []
        for svc in _SERVICE_REGISTRY:
            alive = _check_process_alive(svc["process_keyword"])
            services.append(
                {
                    "id": svc["id"],
                    "name": svc["name"],
                    "description": svc["description"],
                    "status": "running" if alive else "stopped",
                    "port": svc["port"],
                }
            )
        return {"services": services}
    except Exception as e:
        logger.exception("获取服务列表失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/system/services/{service_id}")
def get_service_status(service_id: str = Path(...)):
    """获取单个服务的详细状态"""
    svc = next((s for s in _SERVICE_REGISTRY if s["id"] == service_id), None)
    if not svc:
        raise HTTPException(status_code=404, detail="服务不存在")

    alive = _check_process_alive(svc["process_keyword"])
    return {
        "id": svc["id"],
        "name": svc["name"],
        "description": svc["description"],
        "status": "running" if alive else "stopped",
        "port": svc["port"],
    }
