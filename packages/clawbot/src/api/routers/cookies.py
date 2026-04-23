"""
Cookie 同步中心 API — 一键同步 + 全平台状态查询
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cookies")


@router.get("/status")
async def cookie_status() -> Dict[str, Any]:
    """查询所有平台 Cookie 状态"""
    platforms = {}

    # 闲鱼
    xy_cookie = os.getenv("XIANYU_COOKIES", "")
    platforms["xianyu"] = {
        "name": "闲鱼",
        "has_cookie": bool(xy_cookie),
        "source": "CookieCloud",
    }

    # X/Twitter
    x_path = Path.home() / ".openclaw" / "x_cookies.json"
    platforms["x"] = {
        "name": "X (Twitter)",
        "has_cookie": x_path.exists() and x_path.stat().st_size > 10,
        "source": "CookieCloud / twikit",
        "last_modified": datetime.fromtimestamp(x_path.stat().st_mtime).isoformat() if x_path.exists() else None,
    }

    # 小红书
    xhs_path = Path.home() / ".openclaw" / "xhs_cookies.json"
    platforms["xhs"] = {
        "name": "小红书",
        "has_cookie": xhs_path.exists() and xhs_path.stat().st_size > 10,
        "source": "CookieCloud",
        "last_modified": datetime.fromtimestamp(xhs_path.stat().st_mtime).isoformat() if xhs_path.exists() else None,
    }

    # 微信
    wechat_path = Path.home() / ".openclaw" / "openclaw-weixin" / "accounts"
    has_wechat = wechat_path.exists() and any(wechat_path.glob("*.json"))
    platforms["wechat"] = {
        "name": "微信",
        "has_cookie": has_wechat,
        "source": "OpenClaw CLI 扫码",
    }

    total = len(platforms)
    active = sum(1 for p in platforms.values() if p["has_cookie"])

    return {
        "platforms": platforms,
        "summary": {"total": total, "active": active, "inactive": total - active},
    }


@router.post("/sync-all")
async def sync_all_cookies() -> Dict[str, Any]:
    """一键同步所有平台 Cookie（通过 CookieCloud）"""
    results = {}

    # 触发 CookieCloud 同步（会自动提取闲鱼+X+XHS）
    try:
        from src.xianyu.cookie_cloud import CookieCloudManager
        manager = CookieCloudManager.get_instance()
        if manager:
            sync_result = await manager.sync_once()
            results["cookiecloud"] = {
                "success": sync_result is not None,
                "message": "CookieCloud 同步完成" if sync_result else "CookieCloud 同步失败或未配置",
            }
        else:
            results["cookiecloud"] = {"success": False, "message": "CookieCloud 未配置"}
    except Exception as e:
        results["cookiecloud"] = {"success": False, "message": str(e)[:100]}

    # 返回同步后的状态
    status = await cookie_status()
    return {"sync_results": results, "status": status}
