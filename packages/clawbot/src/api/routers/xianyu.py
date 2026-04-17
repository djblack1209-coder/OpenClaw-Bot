"""闲鱼扫码登录 API endpoints — QR code generation + status polling"""

import base64
import logging
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException

from ..error_utils import safe_error as _safe_error

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Module-level session storage
# ---------------------------------------------------------------------------
# Stores the active QR login session so the status endpoint can query it.
# Keyed by creation timestamp; only the latest session is used.
_active_session: Optional[Dict[str, Any]] = None


def _get_session() -> Optional[Dict[str, Any]]:
    """Return the current active QR session, or None."""
    return _active_session


# ---------------------------------------------------------------------------
# POST /xianyu/qr/generate
# ---------------------------------------------------------------------------


@router.post("/xianyu/qr/generate")
async def generate_qr_code():
    """生成闲鱼登录二维码。

    创建 QRLoginManager 实例，生成二维码，
    返回 base64 编码的 PNG 图片和二维码内容。
    """
    global _active_session

    try:
        from src.xianyu.qr_login import QRLoginManager

        manager = QRLoginManager()
        result = await manager.generate_qr_code()

        if not result["success"]:
            return {
                "success": False,
                "message": result.get("message", "二维码生成失败"),
            }

        # Encode QR image as base64
        qr_png: bytes = result["qr_png"]
        qr_b64 = base64.b64encode(qr_png).decode("ascii")

        # Store session for status polling
        _active_session = {
            "manager": manager,
            "created_at": time.time(),
        }

        return {
            "success": True,
            "qr_image": qr_b64,
            "qr_content": result["qr_content"],
        }

    except Exception as e:
        logger.exception("闲鱼 QR 生成失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


# ---------------------------------------------------------------------------
# GET /xianyu/qr/status
# ---------------------------------------------------------------------------

# Reuse the same constants / headers as qr_login.py for the single-check query
_API_QUERY_QR = "https://passport.goofish.com/newlogin/qrcode/query.do"
_QUERY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://passport.goofish.com/",
    "Origin": "https://passport.goofish.com",
}
_QUERY_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)


async def _check_qr_status_once(
    manager: Any,
) -> Dict[str, Any]:
    """Perform a single query against the Goofish passport QR status API.

    This does NOT loop — it fires one request and returns immediately,
    so the frontend can poll every ~2 s without blocking.

    Returns a dict with at least ``{"status": "..."}`` and optionally
    ``{"success": True, "cookies_str": "..."}`` on confirmed login.
    """
    async with httpx.AsyncClient(follow_redirects=True, timeout=_QUERY_TIMEOUT) as client:
        resp = await client.post(
            _API_QUERY_QR,
            data=manager.params,
            cookies=manager.cookies,
            headers=_QUERY_HEADERS,
        )
        data = resp.json()
        qr_status = data.get("content", {}).get("data", {}).get("qrCodeStatus", "")

        if qr_status == "CONFIRMED":
            # Check for risk-control redirect (phone verification)
            if data.get("content", {}).get("data", {}).get("iframeRedirect"):
                return {"status": "scanned"}  # still waiting for user verification

            # Login confirmed — extract cookies
            manager.cookies.update({k: v for k, v in resp.cookies.items()})
            cookies_str = "; ".join(f"{k}={v}" for k, v in manager.cookies.items())
            return {
                "status": "confirmed",
                "success": True,
                "cookies_str": cookies_str,
            }

        elif qr_status == "SCANED":
            return {"status": "scanned"}

        elif qr_status == "EXPIRED":
            return {"status": "expired"}

        elif qr_status == "NEW":
            return {"status": "waiting"}

        else:
            # Unknown / cancelled status
            return {"status": "expired"}


@router.get("/xianyu/qr/status")
async def qr_login_status():
    """查询闲鱼扫码登录状态（单次检查，不阻塞）。

    前端每 2 秒调用一次，此接口立即返回当前状态：
    - waiting:   二维码已生成，等待扫码
    - scanned:   用户已扫码，等待确认
    - confirmed: 登录成功
    - expired:   二维码已过期
    - no_session: 没有活跃的二维码会话
    """
    try:
        session = _get_session()
        if session is None:
            return {"status": "no_session"}

        manager = session["manager"]

        # Check if the QR code has been alive too long (>5 min = 300 s)
        if time.time() - session["created_at"] > 300:
            return {"status": "expired"}

        result = await _check_qr_status_once(manager)
        return result

    except Exception as e:
        logger.exception("闲鱼 QR 状态查询失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


# ---------------------------------------------------------------------------
# GET /xianyu/conversations
# ---------------------------------------------------------------------------


@router.get("/xianyu/conversations")
async def get_xianyu_conversations(limit: int = 20):
    """获取闲鱼最近对话列表"""
    try:
        # 修复: xianyu_bot.py 不存在，改用 XianyuContextManager 查询对话列表
        # XianyuContextManager 通过 SQLite 管理所有闲鱼对话数据
        from src.xianyu.xianyu_context import XianyuContextManager

        ctx = XianyuContextManager()

        # 从 messages 表查询最近的对话（按 chat_id 分组）
        with ctx._conn() as c:
            rows = c.execute(
                """
                SELECT chat_id, MAX(ts) as last_ts, COUNT(*) as msg_count,
                       (SELECT content FROM messages m2
                        WHERE m2.chat_id = m.chat_id
                        ORDER BY id DESC LIMIT 1) as last_msg
                FROM messages m
                GROUP BY chat_id
                ORDER BY last_ts DESC
                LIMIT ?
            """,
                (limit,),
            ).fetchall()

        conversations = [
            {
                "chat_id": r[0],
                "last_ts": r[1],
                "msg_count": r[2],
                "last_msg": r[3][:100] if r[3] else "",
            }
            for r in rows
        ]
        return {"conversations": conversations, "total": len(conversations)}
    except ImportError:
        # XianyuContextManager 模块未安装
        return {"conversations": [], "total": 0}
    except Exception as e:
        logger.exception("获取闲鱼对话失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))
