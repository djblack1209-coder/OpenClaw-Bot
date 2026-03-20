"""
Execution Hub — 生活自动化
场景8: 提醒、Webhook、HomeKit 等生活自动化
"""
import logging
from datetime import datetime, timedelta

from src.execution._db import get_conn
from src.execution._utils import safe_int, run_osascript

logger = logging.getLogger(__name__)


async def create_reminder(message=None, delay_minutes=None, db_path=None) -> dict:
    """创建定时提醒"""
    msg = str(message or "").strip()
    if not msg:
        return {"success": False, "error": "提醒内容不能为空"}
    delay = max(1, safe_int(delay_minutes, 5))
    remind_at = (datetime.now() + timedelta(minutes=delay)).isoformat()
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO reminders (message, remind_at, status, created_at) "
                "VALUES (?, ?, 'pending', ?)",
                (msg, remind_at, datetime.now().isoformat()),
            )
            return {
                "success": True,
                "reminder_id": cursor.lastrowid,
                "message": msg,
                "remind_at": remind_at,
                "delay_minutes": delay,
            }
    except Exception as e:
        logger.error(f"[CreateReminder] failed: {e}")
        return {"success": False, "error": str(e)}


def list_reminders(status="pending", db_path=None) -> list:
    """列出提醒"""
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "SELECT id, message, remind_at, status, created_at "
                "FROM reminders WHERE status=? ORDER BY remind_at ASC",
                (status,),
            )
            return [
                {"id": r[0], "message": r[1], "remind_at": r[2],
                 "status": r[3], "created_at": r[4]}
                for r in cursor.fetchall()
            ]
    except Exception:
        return []


def trigger_home_action(action_script: str) -> str:
    """通过 AppleScript 触发 HomeKit/系统操作"""
    if not action_script:
        return "操作脚本不能为空"
    return run_osascript(action_script) or "操作已执行"
