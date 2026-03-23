"""
Execution Hub — 生活自动化 v2.0
场景8: 提醒、Webhook、HomeKit 等生活自动化

v2.0 变更 (2026-03-23):
  - 搬运 dateparser (2.5k⭐) — 自然语言时间解析
  - 用户可以说 "明天下午三点提醒我开会" 而不是指定分钟数
  - 支持中英文: "10分钟后" / "下周一" / "in 2 hours" / "next Friday 3pm"
  - dateparser 不可用时降级到 delay_minutes 模式
"""
import logging
from datetime import datetime, timedelta

from src.execution._db import get_conn
from src.execution._utils import safe_int, run_osascript
from src.utils import now_et

logger = logging.getLogger(__name__)

# ── dateparser (2.5k⭐) — 自然语言时间解析 ──────────────────
_HAS_DATEPARSER = False
try:
    import dateparser as _dp
    _HAS_DATEPARSER = True
    logger.debug("[life_automation] dateparser 已加载")
except ImportError:
    _dp = None  # type: ignore[assignment]
    logger.info("[life_automation] dateparser 未安装，提醒仅支持分钟延迟 (pip install dateparser)")


def _parse_remind_time(time_text: str = None, delay_minutes: int = None) -> tuple:
    """解析提醒时间 — 搬运 dateparser 自然语言解析模式。

    支持:
      - "10分钟后" / "半小时后" / "明天下午三点"
      - "in 2 hours" / "next Monday 9am" / "tomorrow 15:00"
      - delay_minutes=30 (传统模式)

    Returns:
        (remind_at_iso, display_text)
    """
    now = now_et()

    # 路径1: dateparser 自然语言解析
    if time_text and _HAS_DATEPARSER:
        try:
            parsed = _dp.parse(
                time_text,
                settings={
                    "PREFER_DATES_FROM": "future",
                    "RETURN_AS_TIMEZONE_AWARE": False,
                },
            )
            if parsed and parsed > now:
                delta = parsed - now
                mins = int(delta.total_seconds() / 60)
                return parsed.isoformat(), f"{mins}分钟后 ({parsed.strftime('%m-%d %H:%M')})"
        except Exception as e:
            logger.debug(f"[life_automation] dateparser 解析失败: {e}")

    # 路径2: delay_minutes 降级
    delay = max(1, safe_int(delay_minutes, 5))
    remind_at = now + timedelta(minutes=delay)
    return remind_at.isoformat(), f"{delay}分钟后"


async def create_reminder(
    message=None,
    delay_minutes=None,
    time_text: str = None,
    db_path=None,
) -> dict:
    """创建定时提醒。

    v2.0: 支持自然语言时间 (time_text) 或传统分钟延迟 (delay_minutes)。
    """
    msg = str(message or "").strip()
    if not msg:
        return {"success": False, "error": "提醒内容不能为空"}

    remind_at, display = _parse_remind_time(time_text, delay_minutes)

    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO reminders (message, remind_at, status, created_at) "
                "VALUES (?, ?, 'pending', ?)",
                (msg, remind_at, now_et().isoformat()),
            )
            return {
                "success": True,
                "reminder_id": cursor.lastrowid,
                "message": msg,
                "remind_at": remind_at,
                "display": display,
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
