"""闲鱼 API endpoints — QR 扫码登录 + CookieCloud 自动同步 + 对话查询"""

import base64
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..auth import verify_api_token
from ..error_utils import safe_error as _safe_error

logger = logging.getLogger(__name__)
# 安全加固(HI-582): 路由级别也挂载 Token 认证，防止被单独挂载时缺少全局认证保护
router = APIRouter(dependencies=[Depends(verify_api_token)])

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

            # Login confirmed — extract cookies and save server-side
            manager.cookies.update({k: v for k, v in resp.cookies.items()})
            cookies_str = "; ".join(f"{k}={v}" for k, v in manager.cookies.items())

            # 安全加固(HI-583): cookies 仅在服务端保存，不返回给前端
            # 防止 cookies 通过 API 响应泄露到客户端日志或前端存储
            try:
                import dotenv
                env_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "..", "..", "config", ".env",
                )
                env_path = os.path.normpath(env_path)
                dotenv.set_key(env_path, "XIANYU_COOKIES", cookies_str)
                logger.info("闲鱼 cookies 已保存到 .env 文件")
            except Exception:
                logger.exception("保存闲鱼 cookies 到 .env 失败，尝试写入环境变量")
                os.environ["XIANYU_COOKIES"] = cookies_str

            return {
                "status": "confirmed",
                "success": True,
                # cookies 不返回给前端，已在服务端安全存储
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
    # 安全修复: 限制 limit 参数范围，防止大值 DoS
    limit = min(max(1, limit), 100)
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


# ---------------------------------------------------------------------------
# CookieCloud 集成 API — Cookie 自动同步管理
# ---------------------------------------------------------------------------


@router.get("/xianyu/cookiecloud/status")
async def cookiecloud_status():
    """获取 CookieCloud 同步状态

    返回当前配置、同步状态、最近同步记录等信息。
    GUI 面板用此接口展示 Cookie 管理面板。
    """
    try:
        from src.xianyu.cookie_cloud import get_cookie_cloud_manager
        manager = get_cookie_cloud_manager()
        return {"success": True, **manager.status}
    except Exception as e:
        logger.exception("获取 CookieCloud 状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/xianyu/cookiecloud/sync")
async def cookiecloud_sync_now():
    """立即执行一次 CookieCloud Cookie 同步

    手动触发同步，不等待定时任务。
    """
    try:
        from src.xianyu.cookie_cloud import get_cookie_cloud_manager
        manager = get_cookie_cloud_manager()

        if not manager.enabled:
            return {
                "success": False,
                "message": "CookieCloud 未配置，请先设置 COOKIECLOUD_HOST/UUID/PASSWORD",
            }

        success = await manager.sync_once()
        return {
            "success": success,
            "message": "Cookie 同步成功" if success else "Cookie 同步失败（浏览器可能离线）",
            **manager.status,
        }
    except Exception as e:
        logger.exception("CookieCloud 手动同步失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/xianyu/cookiecloud/configure")
async def cookiecloud_configure(
    host: str = "",
    uuid: str = "",
    password: str = "",
    interval: int = 300,
):
    """配置 CookieCloud 服务端连接信息

    配置成功后会立即执行一次同步测试。
    参数通过 JSON body 或 form-data 传递。
    """
    try:
        from src.xianyu.cookie_cloud import get_cookie_cloud_manager
        manager = get_cookie_cloud_manager()

        if not host or not uuid or not password:
            return {
                "success": False,
                "message": "缺少必填参数: host, uuid, password",
            }

        success = await manager.configure(host, uuid, password, interval)
        return {
            "success": success,
            "message": "CookieCloud 配置成功并已完成首次同步" if success else "配置已保存但首次同步失败（请检查参数）",
            **manager.status,
        }
    except Exception as e:
        logger.exception("CookieCloud 配置失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))
