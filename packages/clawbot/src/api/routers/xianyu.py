"""闲鱼 API endpoints — CookieCloud 自动同步 + 对话查询"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import verify_api_token
from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC

logger = logging.getLogger(__name__)
# 安全加固(HI-582): 路由级别也挂载 Token 认证，防止被单独挂载时缺少全局认证保护
router = APIRouter(dependencies=[Depends(verify_api_token)])

# ---------------------------------------------------------------------------
# GET /xianyu/status — 闲鱼模块综合状态
# ---------------------------------------------------------------------------


@router.get("/xianyu/status")
async def xianyu_status():
    """获取闲鱼模块综合运行状态。

    聚合进程在线状态、Cookie 健康、今日咨询数等信息，
    供前端一次性获取闲鱼模块全貌。
    """
    try:
        # 从系统状态中提取闲鱼部分
        status_data = ClawBotRPC._rpc_system_status()
        xianyu_detail = status_data.get("xianyu", {})

        result: dict[str, Any] = {
            "running": xianyu_detail.get("online", False),
            "online": xianyu_detail.get("online", False),
            "cookie_ok": xianyu_detail.get("cookie_ok", False),
            "auto_reply_active": xianyu_detail.get("auto_reply_active", False),
            "conversations_today": xianyu_detail.get("conversations_today", 0),
            "unread_chats": xianyu_detail.get("unread_chats", 0),
        }

        # 补充 CookieCloud 同步状态（最佳努力）
        try:
            from src.xianyu.cookie_cloud import get_cookie_cloud_manager
            manager = get_cookie_cloud_manager()
            cc_status = manager.status
            result["cookiecloud_enabled"] = cc_status.get("enabled", False)
            result["cookiecloud_last_sync"] = cc_status.get("last_sync", None)
        except Exception:
            result["cookiecloud_enabled"] = False

        return result
    except Exception as e:
        logger.exception("获取闲鱼状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


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
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


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
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


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
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


class CookieCloudConfigRequest(BaseModel):
    """CookieCloud 配置请求体"""
    host: str = ""
    uuid: str = ""
    password: str = ""
    interval: int = 300


@router.post("/xianyu/cookiecloud/configure")
async def cookiecloud_configure(req: CookieCloudConfigRequest):
    """配置 CookieCloud 服务端连接信息

    配置成功后会立即执行一次同步测试。
    参数通过 JSON body 或 form-data 传递。
    """
    try:
        from src.xianyu.cookie_cloud import get_cookie_cloud_manager
        manager = get_cookie_cloud_manager()

        if not req.host or not req.uuid or not req.password:
            return {
                "success": False,
                "message": "缺少必填参数: host, uuid, password",
            }

        success = await manager.configure(req.host, req.uuid, req.password, req.interval)
        return {
            "success": success,
            "message": "CookieCloud 配置成功并已完成首次同步" if success else "配置已保存但首次同步失败（请检查参数）",
            **manager.status,
        }
    except Exception as e:
        logger.exception("CookieCloud 配置失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


# ---------------------------------------------------------------------------
# 闲鱼收入统计
# ---------------------------------------------------------------------------

@router.get("/xianyu/profit")
async def get_xianyu_profit(days: int = 30):
    """获取闲鱼利润汇总（近 N 天的营收、成本、佣金、净利润）"""
    try:
        from src.xianyu.xianyu_context import XianyuContextManager
        ctx = XianyuContextManager()
        summary = ctx.get_profit_summary(days=days)
        # 补充今日统计
        today_stats = ctx.daily_stats()
        return {
            **summary,
            "today": today_stats,
        }
    except Exception as e:
        logger.exception("获取闲鱼利润失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


# ---------------------------------------------------------------------------
# GET /xianyu/cookie-status
# ---------------------------------------------------------------------------


@router.get("/xianyu/cookie-status")
async def get_cookie_status():
    """获取闲鱼 Cookie 健康状态"""
    from src.xianyu.cookie_refresher import CookieHealthMonitor
    monitor = CookieHealthMonitor()
    try:
        result = await monitor._check_xianyu_cookie()
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("检查闲鱼 Cookie 状态失败: %s", e)
        return {"success": False, "error": str(e)}
