"""
Execution Hub — 智能任务管理
场景5: 任务的增删改查，优先级排序
"""
import logging
import sqlite3
from datetime import datetime

from src.execution._db import get_conn
from src.execution._utils import safe_int
from src.utils import now_et

logger = logging.getLogger(__name__)


def add_task(title=None, priority="medium", db_path=None) -> dict:
    """添加新任务"""
    t = str(title or "").strip()
    if not t:
        return {"success": False, "error": "标题不能为空"}
    p = priority if priority in ("high", "medium", "low") else "medium"
    now = now_et().isoformat()
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO tasks (title, priority, status, created_at, updated_at) "
                "VALUES (?, ?, 'pending', ?, ?)",
                (t, p, now, now),
            )
            return {"success": True, "task_id": cursor.lastrowid, "title": t, "priority": p}
    except Exception as e:
        logger.error(f"[AddTask] failed: {e}")
        return {"success": False, "error": str(e)}


def has_open_task(title=None, db_path=None) -> bool:
    """检查是否存在同名未完成任务"""
    t = str(title or "").strip()
    if not t:
        return False
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE title=? AND status != 'done'", (t,)
            )
            return cursor.fetchone()[0] > 0
    except Exception:
        return False


def update_task_status(task_id=None, status=None, db_path=None) -> dict:
    """更新任务状态"""
    st = str(status or "").strip().lower()
    if st not in ("todo", "doing", "done", "cancelled", "pending"):
        return {"success": False, "error": "状态仅支持 pending/todo/doing/done/cancelled"}
    try:
        with get_conn(db_path) as conn:
            conn.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                (st, now_et().isoformat(), int(task_id)),
            )
            return {"success": True, "task_id": task_id, "status": st}
    except Exception as e:
        logger.error(f"[UpdateTask] failed: {e}")
        return {"success": False, "error": str(e)}


def list_tasks(status=None, db_path=None) -> list:
    """列出任务，可按状态过滤"""
    try:
        with get_conn(db_path) as conn:
            if status:
                cursor = conn.execute(
                    "SELECT id, title, priority, status, created_at, updated_at "
                    "FROM tasks WHERE status=? ORDER BY created_at DESC",
                    (str(status).strip().lower(),),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, title, priority, status, created_at, updated_at "
                    "FROM tasks ORDER BY created_at DESC"
                )
            return [
                {"id": r[0], "title": r[1], "priority": r[2], "status": r[3],
                 "created_at": r[4], "updated_at": r[5]}
                for r in cursor.fetchall()
            ]
    except Exception as e:
        logger.error(f"[ListTasks] failed: {e}")
        return []


def top_tasks(limit=10, db_path=None) -> list:
    """获取优先级最高的未完成任务"""
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "SELECT id, title, priority, status, created_at, updated_at "
                "FROM tasks WHERE status != 'done' "
                "ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 "
                "WHEN 'low' THEN 3 ELSE 4 END, created_at DESC LIMIT ?",
                (int(limit),),
            )
            return [
                {"id": r[0], "title": r[1], "priority": r[2], "status": r[3],
                 "created_at": r[4], "updated_at": r[5]}
                for r in cursor.fetchall()
            ]
    except Exception as e:
        logger.error(f"[TopTasks] failed: {e}")
        return []
