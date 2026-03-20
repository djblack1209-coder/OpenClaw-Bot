"""
Execution Hub — 每日简报
场景2: 汇总待办、社媒、监控等信息生成每日简报
"""
import logging
from src.execution._db import get_conn
from src.notify_style import format_announcement

logger = logging.getLogger(__name__)


async def generate_daily_brief(monitors=None, db_path=None) -> str:
    """生成每日简报，汇总待办事项、社媒草稿、活跃监控"""
    paragraphs = []
    # 待办事项
    try:
        from src.execution.task_mgmt import top_tasks
        tasks = top_tasks(limit=5, db_path=db_path)
        if tasks:
            task_lines = [
                f"- [{t.get('status','pending')}] {t.get('title','')}"
                for t in tasks
            ]
            paragraphs.append("待办事项:\n" + "\n".join(task_lines))
    except Exception as e:
        logger.debug(f"[DailyBrief] tasks error: {e}")
    # 社媒草稿
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM social_drafts WHERE status='draft'"
            )
            count = cursor.fetchone()[0]
            if count:
                paragraphs.append(f"待发布社媒草稿: {count} 条")
    except Exception as e:
        logger.debug(f"[DailyBrief] social drafts error: {e}")
    # 活跃监控
    try:
        if monitors:
            paragraphs.append(f"活跃监控: {len(monitors)} 个")
    except Exception as e:
        logger.debug(f"[DailyBrief] monitors error: {e}")

    if not paragraphs:
        paragraphs.append("今日暂无待处理事项")
    return format_announcement(title="每日简报", paragraphs=paragraphs)
