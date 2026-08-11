"""
Cookie 同步中心 API — 一键同步 + 全平台状态查询
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cookies")


@router.get("/status")
async def cookie_status() -> dict[str, Any]:
    """查询所有平台 Cookie 状态"""
    platforms = {}

    # X/Twitter
    x_path = Path.home() / ".openclaw" / "x_cookies.json"
    platforms["x"] = {
        "name": "X (Twitter)",
        "has_cookie": x_path.exists() and x_path.stat().st_size > 10,
        "source": "OpenClaw profile / twikit",
        "last_modified": datetime.fromtimestamp(x_path.stat().st_mtime).isoformat() if x_path.exists() else None,
    }

    # 小红书
    xhs_path = Path.home() / ".openclaw" / "xhs_cookies.json"
    platforms["xhs"] = {
        "name": "小红书",
        "has_cookie": xhs_path.exists() and xhs_path.stat().st_size > 10,
        "source": "OpenClaw profile",
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
