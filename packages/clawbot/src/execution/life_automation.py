"""
Execution Hub — 生活自动化 v2.0
场景8: 提醒、Webhook、HomeKit 等生活自动化

v2.0 变更 (2026-03-23):
  - 搬运 dateparser (2.5k⭐) — 自然语言时间解析
  - 用户可以说 "明天下午三点提醒我开会" 而不是指定分钟数
  - 支持中英文: "10分钟后" / "下周一" / "in 2 hours" / "next Friday 3pm"
  - dateparser 不可用时降级到 delay_minutes 模式
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from src.execution._db import get_conn
from src.execution._utils import safe_int
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
                    "RETURN_AS_TIMEZONE_AWARE": True,
                    "TIMEZONE": "America/New_York",
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
    recurrence_rule: str = "",
    user_chat_id: int = 0,
    db_path=None,
) -> dict:
    """创建定时提醒。

    v2.0: 支持自然语言时间 (time_text) 或传统分钟延迟 (delay_minutes)。
    """
    msg = str(message or "").strip()
    if not msg:
        return {"success": False, "error": "提醒内容不能为空"}

    remind_at, display = _parse_remind_time(time_text, delay_minutes)

    # 周期性提醒但无指定首次时间 → 用周期规则计算首次触发（而非降级到5分钟后）
    if not time_text and delay_minutes is None and recurrence_rule:
        next_dt = _calc_next_occurrence(recurrence_rule, now_et())
        if next_dt:
            remind_at = next_dt.isoformat()
            display = f"首次: {next_dt.strftime('%m-%d %H:%M')}"

    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO reminders (message, remind_at, status, created_at, recurrence_rule, user_chat_id) "
                "VALUES (?, ?, 'pending', ?, ?, ?)",
                (msg, remind_at, now_et().isoformat(), recurrence_rule, user_chat_id),
            )
            return {
                "success": True,
                "reminder_id": cursor.lastrowid,
                "message": msg,
                "remind_at": remind_at,
                "display": display,
                "recurrence_rule": recurrence_rule,
            }
    except Exception as e:
        logger.error(f"[CreateReminder] failed: {e}")
        return {"success": False, "error": str(e)}


def list_reminders(status="pending", db_path=None) -> list:
    """列出提醒"""
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "SELECT id, message, remind_at, status, created_at, "
                "COALESCE(recurrence_rule, '') as recurrence_rule, "
                "COALESCE(user_chat_id, 0) as user_chat_id "
                "FROM reminders WHERE status=? ORDER BY remind_at ASC",
                (status,),
            )
            return [
                {"id": r[0], "message": r[1], "remind_at": r[2],
                 "status": r[3], "created_at": r[4],
                 "recurrence_rule": r[5], "user_chat_id": r[6]}
                for r in cursor.fetchall()
            ]
    except Exception as e:  # noqa: F841
        return []


def cancel_reminder(reminder_id: int, db_path=None) -> bool:
    """取消(删除)指定ID的提醒。成功返回 True，失败返回 False。"""
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "UPDATE reminders SET status='cancelled' WHERE id=? AND status='pending'",
                (reminder_id,),
            )
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"[CancelReminder] failed for id={reminder_id}: {e}")
        return False


def fire_due_reminders(db_path=None) -> list:
    """查找并触发所有到期的提醒。

    Returns:
        List of dicts: [{"id": 1, "message": "吃药", "user_chat_id": 123, "recurrence_rule": "daily"}]
    """
    now = now_et()
    now_str = now.isoformat()
    fired = []
    try:
        with get_conn(db_path) as conn:
            # 原子性操作: 先标记非重复提醒为 fired，防止并发重复触发
            conn.execute(
                "UPDATE reminders SET status='fired' "
                "WHERE status='pending' AND remind_at <= ? AND "
                "(recurrence_rule IS NULL OR recurrence_rule = '')",
                (now_str,),
            )

            # 查询所有到期的提醒（刚标记为 fired 的单次 + 仍 pending 的重复提醒）
            cursor = conn.execute(
                "SELECT id, message, remind_at, recurrence_rule, user_chat_id "
                "FROM reminders WHERE remind_at <= ? AND ("
                "  (status='fired' AND (recurrence_rule IS NULL OR recurrence_rule = '')) OR "
                "  (status='pending' AND recurrence_rule IS NOT NULL AND recurrence_rule != '')"
                ")",
                (now_str,),
            )
            rows = cursor.fetchall()
            for row in rows:
                rid, msg, remind_at, recurrence, chat_id = row
                fired.append({
                    "id": rid,
                    "message": msg,
                    "remind_at": remind_at,
                    "recurrence_rule": recurrence or "",
                    "user_chat_id": chat_id or 0,
                })
                if recurrence:
                    # 重复提醒: 计算下一次触发时间并更新
                    next_time = _calc_next_occurrence(recurrence, now)
                    if next_time:
                        conn.execute(
                            "UPDATE reminders SET remind_at=? WHERE id=?",
                            (next_time.isoformat(), rid),
                        )
                    else:
                        # 无法计算下次时间,标记完成
                        conn.execute(
                            "UPDATE reminders SET status='fired' WHERE id=?",
                            (rid,),
                        )
    except Exception as e:
        logger.error(f"[Reminders] fire_due_reminders 失败: {e}")
    return fired


def _calc_next_occurrence(recurrence_rule: str, from_time: datetime) -> datetime:
    """根据重复规则计算下一次触发时间。

    支持的规则:
    - "daily" 或 "每天" → 明天同一时间
    - "hourly" 或 "每小时" → 1小时后
    - "weekly:1" 或 "每周一" → 下周同一天
    - "monthly:15" 或 "每月15号" → 下月同一天
    - "weekdays" 或 "工作日" → 下一个工作日
    - "30min" 或 "每30分钟" → 30分钟后
    """
    rule = recurrence_rule.strip().lower()

    if rule in ("daily", "每天"):
        return from_time + timedelta(days=1)

    if rule in ("hourly", "每小时"):
        return from_time + timedelta(hours=1)

    if rule.startswith("weekly:") or rule.startswith("每周"):
        # weekly:1 = Monday (0=Mon, 6=Sun)
        try:
            if rule.startswith("weekly:"):
                target_day = int(rule.split(":")[1])
            else:
                # 每周一=0, 每周二=1, ..., 每周日=6
                weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
                day_char = rule.replace("每周", "")
                target_day = weekday_map.get(day_char, 0)
            days_ahead = target_day - from_time.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return from_time + timedelta(days=days_ahead)
        except (ValueError, IndexError) as e:  # noqa: F841
            return from_time + timedelta(weeks=1)

    if rule.startswith("monthly:") or rule.startswith("每月"):
        try:
            if rule.startswith("monthly:"):
                target_day = int(rule.split(":")[1])
            else:
                import re
                m = re.search(r"(\d+)", rule)
                target_day = int(m.group(1)) if m else 1
            # 下个月的 target_day 号
            year, month = from_time.year, from_time.month
            if from_time.day >= target_day:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            target_day = min(target_day, max_day)
            return from_time.replace(year=year, month=month, day=target_day)
        except (ValueError, IndexError) as e:  # noqa: F841
            return from_time + timedelta(days=30)

    if rule in ("weekdays", "工作日"):
        next_time = from_time + timedelta(days=1)
        while next_time.weekday() >= 5:  # 5=Sat, 6=Sun
            next_time += timedelta(days=1)
        return next_time

    # "30min" / "每30分钟" / "每N分钟" — 最小间隔保护: N<5 强制设为 5 分钟
    m = re.search(r"(\d+)\s*min", rule)
    if m:
        minutes = max(5, int(m.group(1)))
        if minutes != int(m.group(1)):
            logger.warning("[提醒] 间隔过短 (%s min)，强制调整为 5 分钟", m.group(1))
        return from_time + timedelta(minutes=minutes)
    m = re.search(r"每(\d+)分钟", rule)
    if m:
        minutes = max(5, int(m.group(1)))
        if minutes != int(m.group(1)):
            logger.warning("[提醒] 间隔过短 (%s 分钟)，强制调整为 5 分钟", m.group(1))
        return from_time + timedelta(minutes=minutes)

    # 无法解析,默认1天
    logger.warning(f"[Reminders] 无法解析重复规则: {recurrence_rule}, 默认1天")
    return from_time + timedelta(days=1)


# cancel_reminder 已在上方行 126 定义（安全版: 仅取消 status='pending' 的提醒）


# ── 智能家居动作路由 (从 execution_hub.py 迁移) ─────────────
# 注意: trigger_home_action_script() 和 run_osascript() 已于 2026-03-30 移除
# 原因: 接受任意 AppleScript 字符串执行是严重的命令注入风险 (P0 安全审计)
# 如需 HomeKit 控制，请使用下方 _run_local_home_action() 的白名单路由

def _run_local_home_action(action: str = "", payload: dict = None) -> dict:
    """执行本地 macOS 智能家居动作

    支持: ping / notify / open_url / open_app / say / shortcut
    """
    import subprocess

    act = str(action or "").strip().lower()
    data = dict(payload or {})

    if not act or act in frozenset({"noop", "ping", "health"}):
        return {
            "success": True, "mode": "local", "action": "ping",
            "status_code": 200, "response": "pong",
        }

    if act in frozenset({"提醒", "notify", "notification", "通知"}):
        message = str(data.get("message", "")).strip()
        title = str(data.get("title", "OpenClaw")).strip() or "OpenClaw"
        if not message:
            return {"success": False, "mode": "local", "error": "notify 需要 message 字段"}
        # 只保留中英文字符、数字、基本标点，去除所有可能的注入字符
        safe_title = re.sub(r'[^\w\s\u4e00-\u9fff.,!?;:，。！？；：\-]', '', title)[:100]
        safe_message = re.sub(r'[^\w\s\u4e00-\u9fff.,!?;:，。！？；：\-]', '', message)[:500]
        cp = subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe_message}" with title "{safe_title}"'],
            check=False, capture_output=True, text=True, timeout=8,
        )
        return {
            "success": cp.returncode == 0, "mode": "local", "action": "notify",
            "status_code": 200 if cp.returncode == 0 else 500,
            "response": str(cp.stdout or "").strip()[:300],
        }

    if act in frozenset({"打开链接", "url", "open_url"}):
        url = str(data.get("url", "")).strip()
        if not url:
            return {"success": False, "mode": "local", "error": "open_url 需要 url 字段"}
        # URL scheme 白名单校验，防止通过 file:// 等协议执行本地操作
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"success": False, "mode": "local", "error": "仅支持 http/https 链接"}
        cp = subprocess.run(
            ["open", url], check=False, capture_output=True, text=True, timeout=8,
        )
        return {
            "success": cp.returncode == 0, "mode": "local", "action": "open_url",
            "status_code": 200 if cp.returncode == 0 else 500,
            "response": str(cp.stdout or "").strip()[:300],
        }

    if act in frozenset({"打开应用", "app", "open_app"}):
        app_name = str(data.get("app", data.get("name", ""))).strip()
        if not app_name:
            return {"success": False, "mode": "local", "error": "open_app 需要 app/name 字段"}
        # 安全白名单：只允许打开这些应用
        _ALLOWED_APPS = frozenset({
            "safari", "chrome", "firefox", "finder", "terminal",
            "notes", "calendar", "reminders", "messages", "mail",
            "music", "photos", "preview", "textedit", "calculator",
            "system preferences", "system settings", "activity monitor",
        })
        app_lower = app_name.lower().strip()
        if app_lower not in _ALLOWED_APPS:
            return {"success": False, "error": f"应用 '{app_name}' 不在安全白名单中"}
        cp = subprocess.run(
            ["open", "-a", app_name],
            check=False, capture_output=True, text=True, timeout=12,
        )
        return {
            "success": cp.returncode == 0, "mode": "local", "action": "open_app",
            "status_code": 200 if cp.returncode == 0 else 500,
            "response": str(cp.stdout or "").strip()[:300],
        }

    if act in frozenset({"朗读", "say", "speak"}):
        text = str(data.get("text", "")).strip()
        voice = data.get("voice")
        if not text:
            return {"success": False, "mode": "local", "error": "say 需要 text 字段"}
        # 安全限制: 文本长度上限 + 去除前导连字符防止被解释为命令参数
        if len(text) > 2000:
            text = text[:2000]
        text = text.lstrip("-")
        if not text:
            return {"success": False, "mode": "local", "error": "say text 无效(空文本)"}
        cmd = ["say"]
        if voice:
            # 安全限制: voice 必须是合法的名称字符，防止参数注入
            voice = str(voice).strip()
            if not re.match(r'^[A-Za-z\u4e00-\u9fff\s\-]+$', voice) or len(voice) > 50:
                return {"success": False, "mode": "local", "error": "voice 名称包含非法字符"}
            cmd.extend(["-v", voice])
        cmd.append(text)
        cp = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=20)
        return {
            "success": cp.returncode == 0, "mode": "local", "action": "say",
            "status_code": 200 if cp.returncode == 0 else 500,
            "response": str(cp.stdout or "").strip()[:300],
        }

    if act in frozenset({"快捷指令", "shortcut", "run_shortcut"}):
        name = str(data.get("name", data.get("shortcut", ""))).strip()
        if not name:
            return {"success": False, "mode": "local", "error": "shortcut 需要 name/shortcut 字段"}
        # 安全限制：快捷指令名称长度和字符检查
        if len(name) > 100 or not re.match(r'^[\w\s\u4e00-\u9fff\-]+$', name):
            return {"success": False, "error": "快捷指令名称包含非法字符"}
        # 安全限制：白名单校验 — 仅允许预定义的快捷指令名称执行
        _SHORTCUT_WHITELIST = frozenset({
            "开灯", "关灯", "回家模式", "离家模式", "晚安", "早安",
            "睡眠模式", "工作模式", "勿扰模式", "省电模式",
            "Turn On Lights", "Turn Off Lights", "Good Morning", "Good Night",
        })
        if name not in _SHORTCUT_WHITELIST:
            logger.warning("[生活自动化] 快捷指令 '%s' 不在白名单中，已拦截", name)
            return {
                "success": False, "mode": "local",
                "error": f"快捷指令 '{name}' 不在允许列表中，请联系管理员添加",
            }
        cp = subprocess.run(
            ["shortcuts", "run", name],
            check=False, capture_output=True, text=True, timeout=30,
        )
        return {
            "success": cp.returncode == 0, "mode": "local", "action": "shortcut",
            "status_code": 200 if cp.returncode == 0 else 500,
            "response": str(cp.stdout or "").strip()[:300],
        }

    return {
        "success": False, "mode": "local", "status_code": 400,
        "error": "不支持的本地动作，支持: ping/notify/open_url/open_app/say/shortcut",
    }


async def trigger_home_action(action: str = "", payload: dict = None) -> dict:
    """触发智能家居/本地 macOS 动作 (异步入口)"""
    try:
        # 使用 to_thread 避免 subprocess.run 阻塞事件循环
        return await asyncio.to_thread(_run_local_home_action, action, payload)
    except Exception as e:
        logger.error(f"[TriggerHome] failed: {e}")
        return {"success": False, "error": str(e)}


# ─────────── 简易记账 v2 (收入 + 支出 + 预算 + 月度汇总) ───────────

# 分类自动推断 — 根据备注关键词自动匹配分类


# ── 向后兼容导出 (v6.0 拆分, 消费者逐步迁移后移除) ──
from src.execution.bookkeeping import (  # noqa: F401
    _CATEGORY_KEYWORDS, _CATEGORY_EMOJI, _auto_categorize,
    add_expense, add_income, set_monthly_budget, get_monthly_summary,
    check_budget_alert, get_expense_summary, get_all_expenses,
    delete_last_expense, format_monthly_report,
    BILL_TYPE_EMOJI, BILL_TYPE_ALIAS, BILL_TYPE_LABEL, MAX_BILL_ACCOUNTS_PER_USER,
    resolve_bill_type, add_bill_account, update_bill_balance,
    list_bill_accounts, remove_bill_account, check_bill_alerts,
    get_bill_reminders_due, find_bill_by_type,
)
from src.execution.tracking import (  # noqa: F401
    MAX_PRICE_WATCHES_PER_USER,
    record_post_engagement, get_engagement_summary,
    record_follower_snapshot, get_follower_growth,
    evaluate_strategy_performance,
    add_price_watch, list_price_watches, remove_price_watch,
    check_price_watches, cleanup_stale_watches,
)
