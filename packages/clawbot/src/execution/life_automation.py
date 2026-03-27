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
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

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


def trigger_home_action_script(action_script: str) -> str:
    """通过 AppleScript 触发 HomeKit/系统操作 (简单版)"""
    if not action_script:
        return "操作脚本不能为空"
    return run_osascript(action_script) or "操作已执行"


# ── 智能家居动作路由 (从 execution_hub.py 迁移) ─────────────

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
        cmd = ["say"]
        if voice:
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
        return _run_local_home_action(action, payload)
    except Exception as e:
        logger.error(f"[TriggerHome] failed: {e}")
        return {"success": False, "error": str(e)}


# ─────────── 简易记账 v2 (收入 + 支出 + 预算 + 月度汇总) ───────────

# 分类自动推断 — 根据备注关键词自动匹配分类
_CATEGORY_KEYWORDS = {
    "餐饮": ["午饭", "晚饭", "早饭", "外卖", "点餐", "奶茶", "咖啡", "火锅",
             "烧烤", "饭", "吃", "餐", "食", "零食", "水果", "菜", "肉",
             "面包", "蛋糕", "饮料", "甜品", "汉堡", "披萨", "寿司"],
    "交通": ["打车", "滴滴", "出租", "地铁", "公交", "加油", "停车",
             "高铁", "火车", "机票", "飞机", "车费", "油费", "过路费",
             "骑行", "共享单车"],
    "居住": ["房租", "水电", "物业", "维修", "家具", "装修", "搬家"],
    "购物": ["淘宝", "京东", "拼多多", "购物", "衣服", "鞋", "包",
             "化妆品", "护肤", "日用品", "超市"],
    "通信": ["话费", "流量", "宽带", "网费", "手机", "充值"],
    "娱乐": ["电影", "游戏", "KTV", "唱歌", "旅游", "门票", "演出",
             "健身", "运动", "会员", "订阅", "视频"],
    "医疗": ["看病", "药", "医院", "体检", "挂号", "牙", "配镜"],
    "教育": ["学费", "培训", "课程", "书", "教材", "考试", "网课"],
    "工资": ["工资", "薪资", "薪水", "月薪", "底薪", "基本工资"],
    "兼职": ["兼职", "外快", "副业", "零工", "打工"],
    "理财": ["利息", "分红", "投资收益", "股息", "基金收益", "理财收益",
             "回报", "返利"],
    "转账": ["转账", "红包", "收款", "借款", "还款"],
}

# 分类 → emoji 映射
_CATEGORY_EMOJI = {
    "餐饮": "🍜", "交通": "🚗", "居住": "🏠", "购物": "🛒",
    "通信": "📱", "娱乐": "🎮", "医疗": "🏥", "教育": "📚",
    "工资": "💼", "兼职": "💪", "理财": "📈", "转账": "💸",
    "其他": "📦",
}


def _auto_categorize(note: str, default: str = "其他") -> str:
    """根据备注关键词自动推断分类 — 命中第一个匹配的分类"""
    if not note:
        return default
    note_lower = note.lower()
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in note_lower:
                return cat
    return default


def add_expense(user_id: int, amount: float, note: str = "", category: str = "其他",
                chat_id: int = 0, db_path=None) -> dict:
    """记录一笔开支"""
    # 金额验证
    if amount <= 0 or amount > 1_000_000:
        return {"success": False, "error": "金额无效，请输入 0.01 ~ 1,000,000 之间的数字"}
    # 字段长度限制
    if note:
        note = note[:500]
    # 智能分类: 如果用户没指定分类，根据备注自动推断
    if category == "其他":
        category = _auto_categorize(note)
    if category:
        category = category[:50]
    try:
        with get_conn(db_path) as conn:
            conn.execute(
                "INSERT INTO expenses (user_id, chat_id, category, amount, note, type) "
                "VALUES (?,?,?,?,?,'expense')",
                (user_id, chat_id, category, amount, note),
            )
        return {"success": True, "amount": amount, "category": category, "note": note}
    except Exception as e:
        logger.error(f"[Expense] 记账失败: {e}")
        return {"success": False, "error": str(e)}


def add_income(user_id: int, amount: float, note: str = "", category: str = "其他",
               chat_id: int = 0, db_path=None) -> dict:
    """记录一笔收入"""
    # 金额验证
    if amount <= 0 or amount > 1_000_000:
        return {"success": False, "error": "金额无效，请输入 0.01 ~ 1,000,000 之间的数字"}
    if note:
        note = note[:500]
    # 智能分类: 根据备注推断收入分类
    if category == "其他":
        category = _auto_categorize(note)
    if category:
        category = category[:50]
    try:
        with get_conn(db_path) as conn:
            conn.execute(
                "INSERT INTO expenses (user_id, chat_id, category, amount, note, type) "
                "VALUES (?,?,?,?,?,'income')",
                (user_id, chat_id, category, amount, note),
            )
        return {"success": True, "amount": amount, "category": category, "note": note}
    except Exception as e:
        logger.error(f"[Income] 收入记录失败: {e}")
        return {"success": False, "error": str(e)}


def set_monthly_budget(user_id, budget: float, db_path=None) -> dict:
    """设定月预算 — 存到 budgets 表"""
    if budget <= 0 or budget > 1_000_000:
        return {"success": False, "error": "预算金额无效，请输入 0.01 ~ 1,000,000"}
    try:
        import time as _time
        with get_conn(db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO budgets (user_id, monthly_budget, updated_at) "
                "VALUES (?, ?, ?)",
                (str(user_id), round(budget, 2), _time.time()),
            )
        return {"success": True, "budget": round(budget, 2)}
    except Exception as e:
        logger.error(f"[Budget] 设定预算失败: {e}")
        return {"success": False, "error": str(e)}


def get_monthly_summary(user_id: int, year_month: str = None, db_path=None) -> dict:
    """月度财务汇总 — 收入/支出/结余/预算使用率/分类明细

    Args:
        user_id: 用户 ID
        year_month: 格式 "YYYY-MM"，默认当月

    Returns:
        包含月度财务全景的字典
    """
    from datetime import datetime as _dt

    # 解析月份
    if year_month:
        try:
            parts = year_month.split("-")
            year, month = int(parts[0]), int(parts[1])
        except (ValueError, IndexError) as e:  # noqa: F841
            return {"success": False, "error": "月份格式无效，请用 YYYY-MM 格式"}
    else:
        now = _dt.now()
        year, month = now.year, now.month
        year_month = now.strftime("%Y-%m")

    # 计算月份的时间戳范围
    import calendar
    first_day = _dt(year, month, 1)
    last_day_num = calendar.monthrange(year, month)[1]
    last_day = _dt(year, month, last_day_num, 23, 59, 59)
    ts_start = first_day.timestamp()
    ts_end = last_day.timestamp()

    try:
        with get_conn(db_path) as conn:
            # 总支出
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM expenses "
                "WHERE user_id=? AND ts>=? AND ts<=? AND "
                "(type IS NULL OR type='expense')",
                (user_id, ts_start, ts_end),
            ).fetchone()
            total_expense = round(row[0], 2)

            # 总收入
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM expenses "
                "WHERE user_id=? AND ts>=? AND ts<=? AND type='income'",
                (user_id, ts_start, ts_end),
            ).fetchone()
            total_income = round(row[0], 2)

            # 支出分类明细
            cats = conn.execute(
                "SELECT category, SUM(amount), COUNT(*) FROM expenses "
                "WHERE user_id=? AND ts>=? AND ts<=? AND "
                "(type IS NULL OR type='expense') "
                "GROUP BY category ORDER BY SUM(amount) DESC",
                (user_id, ts_start, ts_end),
            ).fetchall()
            by_category = []
            for c in cats:
                pct = round(c[1] / max(total_expense, 0.01) * 100, 1)
                by_category.append({
                    "category": c[0], "amount": round(c[1], 2),
                    "count": c[2], "pct": pct,
                })

            # 最大 3 笔支出
            top3 = conn.execute(
                "SELECT amount, note, category, ts FROM expenses "
                "WHERE user_id=? AND ts>=? AND ts<=? AND "
                "(type IS NULL OR type='expense') "
                "ORDER BY amount DESC LIMIT 3",
                (user_id, ts_start, ts_end),
            ).fetchall()
            top_expenses = []
            for r in top3:
                dt_str = _dt.fromtimestamp(r[3]).strftime("%m-%d") if r[3] else ""
                top_expenses.append({
                    "amount": r[0], "note": r[1],
                    "category": r[2], "date": dt_str,
                })

            # 预算查询
            budget_row = conn.execute(
                "SELECT monthly_budget FROM budgets WHERE user_id=?",
                (str(user_id),),
            ).fetchone()
            budget = round(budget_row[0], 2) if budget_row else 0

        # 计算衍生指标
        net = round(total_income - total_expense, 2)
        budget_remaining = round(budget - total_expense, 2) if budget > 0 else 0
        budget_pct = round(total_expense / max(budget, 0.01) * 100, 1) if budget > 0 else 0

        return {
            "success": True,
            "month": year_month,
            "total_expense": total_expense,
            "total_income": total_income,
            "net": net,
            "budget": budget,
            "budget_remaining": budget_remaining,
            "budget_pct": budget_pct,
            "by_category": by_category,
            "top_expenses": top_expenses,
        }
    except Exception as e:
        logger.error(f"[MonthlySummary] 月度汇总失败: {e}")
        return {"success": False, "error": str(e)}


def check_budget_alert(user_id, db_path=None) -> tuple:
    """检查是否超预算 — 返回 (is_over, msg)

    逻辑:
    - 无预算 → (False, "未设置预算")
    - 已花费 < 80% → (False, 正常消息)
    - 已花费 80%~100% → (True, 预警消息)
    - 已花费 > 100% → (True, 超支消息)
    """
    summary = get_monthly_summary(user_id, db_path=db_path)
    if not summary.get("success"):
        return (False, "查询失败")

    budget = summary.get("budget", 0)
    if budget <= 0:
        return (False, "未设置月预算，说「月预算5000」即可设定")

    spent = summary.get("total_expense", 0)
    pct = summary.get("budget_pct", 0)
    remaining = summary.get("budget_remaining", 0)
    month = summary.get("month", "")

    if pct > 100:
        msg = (
            f"🔴 {month} 已超预算!\n"
            f"预算: ¥{budget:,.0f} | 已花: ¥{spent:,.0f} ({pct:.1f}%)\n"
            f"超出: ¥{abs(remaining):,.0f}\n"
            f"💡 建议控制非必要支出"
        )
        return (True, msg)
    elif pct >= 80:
        msg = (
            f"🟡 {month} 预算即将用完!\n"
            f"预算: ¥{budget:,.0f} | 已花: ¥{spent:,.0f} ({pct:.1f}%)\n"
            f"剩余: ¥{remaining:,.0f}\n"
            f"💡 还有 ¥{remaining:,.0f} 可用，注意控制"
        )
        return (True, msg)
    else:
        msg = (
            f"✅ {month} 预算健康\n"
            f"预算: ¥{budget:,.0f} | 已花: ¥{spent:,.0f} ({pct:.1f}%)\n"
            f"剩余: ¥{remaining:,.0f}"
        )
        return (False, msg)


def get_expense_summary(user_id: int, days: int = 30, db_path=None) -> dict:
    """获取近N天开支汇总"""
    import time
    cutoff = time.time() - days * 86400
    try:
        with get_conn(db_path) as conn:
            # 总额 (仅支出)
            row = conn.execute(
                "SELECT COUNT(*), SUM(amount) FROM expenses "
                "WHERE user_id=? AND ts>? AND (type IS NULL OR type='expense')",
                (user_id, cutoff),
            ).fetchone()
            total_count = row[0] or 0
            total_amount = round(row[1] or 0, 2)
            # 分类汇总
            cats = conn.execute(
                "SELECT category, SUM(amount), COUNT(*) FROM expenses "
                "WHERE user_id=? AND ts>? AND (type IS NULL OR type='expense') "
                "GROUP BY category ORDER BY SUM(amount) DESC",
                (user_id, cutoff),
            ).fetchall()
            categories = [{"name": c[0], "amount": round(c[1], 2), "count": c[2]} for c in cats]
            # 最近5笔
            recent = conn.execute(
                "SELECT amount, note, category, ts FROM expenses "
                "WHERE user_id=? AND ts>? AND (type IS NULL OR type='expense') "
                "ORDER BY ts DESC LIMIT 5",
                (user_id, cutoff),
            ).fetchall()
            recent_list = []
            for r in recent:
                from datetime import datetime
                dt = datetime.fromtimestamp(r[3]).strftime("%m-%d %H:%M") if r[3] else ""
                recent_list.append({"amount": r[0], "note": r[1], "category": r[2], "time": dt})
        return {
            "success": True, "days": days,
            "total_count": total_count, "total_amount": total_amount,
            "categories": categories, "recent": recent_list,
        }
    except Exception as e:
        logger.error(f"[Expense] 汇总失败: {e}")
        return {"success": False, "error": str(e)}


def get_all_expenses(user_id: int, days: int = 30, db_path=None) -> list:
    """获取记账明细（含收入和支出）— 用于 Excel 导出

    Returns:
        list[dict]: 每条记录包含 date, type, category, amount, note
    """
    import time as _time
    cutoff = _time.time() - days * 86400
    try:
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT amount, note, category, ts, "
                "COALESCE(type, 'expense') as type "
                "FROM expenses WHERE user_id=? AND ts>? "
                "ORDER BY ts DESC",
                (user_id, cutoff),
            ).fetchall()
        result = []
        for r in rows:
            dt_str = datetime.fromtimestamp(r[3]).strftime("%Y-%m-%d %H:%M") if r[3] else ""
            result.append({
                "date": dt_str,
                "type": r[4],
                "category": r[2] or "其他",
                "amount": r[0],
                "note": r[1] or "",
            })
        return result
    except Exception as e:
        logger.error("[Expense] 获取全部记录失败: %s", e)
        return []


def delete_last_expense(user_id: int, chat_id: int = 0, db_path=None) -> bool:
    """删除最近一笔开支（撤销）。chat_id > 0 时仅删除该对话的最近一笔。"""
    try:
        with get_conn(db_path) as conn:
            if chat_id > 0:
                conn.execute(
                    "DELETE FROM expenses WHERE id = ("
                    "SELECT MAX(id) FROM expenses WHERE user_id=? AND chat_id=?)",
                    (user_id, chat_id),
                )
            else:
                conn.execute(
                    "DELETE FROM expenses WHERE id = ("
                    "SELECT MAX(id) FROM expenses WHERE user_id=?)",
                    (user_id,),
                )
        return True
    except Exception as e:  # noqa: F841
        return False


def format_monthly_report(summary: dict) -> str:
    """将 get_monthly_summary 的返回值格式化为 Telegram 消息"""
    if not summary.get("success"):
        return "📊 暂无数据"

    month = summary["month"]
    # 把 "2026-03" 转换为 "2026年3月"
    try:
        y, m = month.split("-")
        month_display = f"{y}年{int(m)}月"
    except (ValueError, AttributeError) as e:  # noqa: F841
        month_display = month

    total_expense = summary["total_expense"]
    total_income = summary["total_income"]
    net = summary["net"]
    budget = summary["budget"]
    budget_pct = summary["budget_pct"]
    budget_remaining = summary["budget_remaining"]
    by_category = summary.get("by_category", [])

    lines = [
        f"💰 {month_display}财务报告",
        "━━━━━━━━━━━━━━━",
        f"📤 总支出: ¥{total_expense:,.0f}",
        f"📥 总收入: ¥{total_income:,.0f}",
    ]
    # 结余带正负号
    sign = "+" if net >= 0 else ""
    lines.append(f"📊 结余: {sign}¥{net:,.0f}")

    # 预算信息
    if budget > 0:
        lines.append("")
        lines.append(f"🎯 预算: ¥{budget:,.0f} (已用 {budget_pct:.1f}%)")
        # 进度条: 13格
        filled = min(13, int(budget_pct / 100 * 13))
        bar = "█" * filled + "░" * (13 - filled)
        if budget_remaining >= 0:
            lines.append(f"{bar}  ¥{budget_remaining:,.0f} 剩余")
        else:
            lines.append(f"{bar}  ¥{abs(budget_remaining):,.0f} 超支 ⚠️")

    # 分类明细
    if by_category:
        lines.append("")
        lines.append("📋 支出分类:")
        for cat in by_category[:8]:
            emoji = _CATEGORY_EMOJI.get(cat["category"], "📦")
            lines.append(
                f"  {emoji} {cat['category']}: "
                f"¥{cat['amount']:,.0f} ({cat['pct']:.1f}%)"
            )

    return "\n".join(lines)


# ─────────── 社媒互动数据 ───────────

def record_post_engagement(draft_id: int, platform: str, likes: int = 0,
                           comments: int = 0, shares: int = 0, views: int = 0,
                           post_url: str = "", db_path=None) -> bool:
    """记录帖子的互动数据"""
    # 输入验证
    likes = max(0, int(likes or 0))
    comments = max(0, int(comments or 0))
    shares = max(0, int(shares or 0))
    views = max(0, int(views or 0))
    _valid_platforms = {"x", "xhs", "weibo", "linkedin", "douyin", "bilibili"}
    if platform not in _valid_platforms:
        return {"success": False, "error": f"不支持的平台: {platform}"}
    try:
        with get_conn(db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO post_engagement (draft_id, platform, post_url, likes, comments, shares, views) "
                "VALUES (?,?,?,?,?,?,?)",
                (draft_id, platform, post_url, likes, comments, shares, views),
            )
        return True
    except Exception as e:
        logger.error(f"[Engagement] 记录失败: {e}")
        return False


def get_engagement_summary(days: int = 7, db_path=None) -> dict:
    """获取近N天帖子互动汇总"""
    import time
    cutoff = time.time() - days * 86400
    try:
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT platform, SUM(likes), SUM(comments), SUM(shares), SUM(views), COUNT(*) "
                "FROM post_engagement WHERE checked_at > ? GROUP BY platform",
                (cutoff,),
            ).fetchall()
        platforms = {}
        for r in rows:
            likes = r[1] or 0
            comments = r[2] or 0
            shares = r[3] or 0
            views = r[4] or 0
            posts = r[5] or 0
            engagement_rate = round((likes + comments + shares) / max(views, 1) * 100, 2)
            platforms[r[0]] = {
                "likes": likes, "comments": comments,
                "shares": shares, "views": views, "posts": posts,
                "engagement_rate": engagement_rate,
            }
        total_likes = sum(p["likes"] for p in platforms.values())
        total_posts = sum(p["posts"] for p in platforms.values())
        return {"success": True, "days": days, "platforms": platforms,
                "total_likes": total_likes, "total_posts": total_posts}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────── 粉丝增长时序 ───────────

def record_follower_snapshot(platform: str, followers: int, following: int = 0,
                             total_likes: int = 0, total_views: int = 0,
                             db_path=None) -> bool:
    """记录粉丝数快照 — 每天每平台一条，用 INSERT OR REPLACE 保证唯一性"""
    _valid = {"x", "xhs", "weibo", "linkedin", "douyin", "bilibili"}
    if platform not in _valid:
        logger.warning("[FollowerSnapshot] 不支持的平台: %s", platform)
        return False
    try:
        with get_conn(db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO follower_snapshots "
                "(platform, followers, following, total_likes, total_views, snapshot_at) "
                "VALUES (?, ?, ?, ?, ?, strftime('%s','now'))",
                (platform, max(0, int(followers)), max(0, int(following)),
                 max(0, int(total_likes)), max(0, int(total_views))),
            )
        logger.info("[FollowerSnapshot] %s: followers=%d", platform, followers)
        return True
    except Exception as e:
        logger.error("[FollowerSnapshot] 存储失败: %s", e)
        return False


def get_follower_growth(days: int = 7, db_path=None) -> dict:
    """获取粉丝增长数据 — 返回各平台的起止粉丝数和净增长

    返回格式:
        {
            "x":   {"start": 1200, "end": 1350, "change": 150, "change_pct": 12.5},
            "xhs": {"start": 500,  "end": 580,  "change": 80,  "change_pct": 16.0},
        }
    """
    import time
    cutoff = time.time() - days * 86400
    result = {}
    try:
        with get_conn(db_path) as conn:
            # 查找 cutoff 之后每个平台最早和最晚的快照
            rows = conn.execute(
                "SELECT platform, "
                "  MIN(CASE WHEN snapshot_at = earliest THEN followers END) AS start_f, "
                "  MAX(CASE WHEN snapshot_at = latest  THEN followers END) AS end_f "
                "FROM follower_snapshots "
                "INNER JOIN ("
                "  SELECT platform AS p, MIN(snapshot_at) AS earliest, MAX(snapshot_at) AS latest "
                "  FROM follower_snapshots WHERE snapshot_at > ? GROUP BY platform"
                ") sub ON follower_snapshots.platform = sub.p "
                "  AND snapshot_at IN (earliest, latest) "
                "WHERE snapshot_at > ? "
                "GROUP BY platform",
                (cutoff, cutoff),
            ).fetchall()

            for plat, start_f, end_f in rows:
                start_f = start_f or 0
                end_f = end_f or 0
                change = end_f - start_f
                change_pct = round(change / max(start_f, 1) * 100, 1)
                result[plat] = {
                    "start": start_f,
                    "end": end_f,
                    "change": change,
                    "change_pct": change_pct,
                }
    except Exception as e:
        logger.error("[FollowerGrowth] 查询失败: %s", e)
    return result


# ─────────── 策略绩效感知 ───────────

def evaluate_strategy_performance(days: int = 30) -> dict:
    """评估近N天各策略的简易绩效 — 复用 TradingJournal 已有的 get_performance 方法"""
    try:
        from src.trading_journal import journal
        perf = journal.get_performance(days=days)
        total = perf.get("total_trades", 0)
        if total == 0:
            return {"success": False, "reason": "无近期交易数据"}

        win_rate = perf.get("win_rate", 0) or 0
        # 自动检测: >1 说明是百分比格式，需要转换
        if win_rate > 1:
            win_rate = win_rate / 100
        # 此时 win_rate 一定是 0~1 的小数
        total_pnl = perf.get("total_pnl", 0)
        wins = int(total * win_rate)
        losses = total - wins

        # 根据绩效数据给出操作建议
        if win_rate >= 0.6:
            suggestion = "策略表现优秀，维持当前权重"
        elif win_rate >= 0.5:
            suggestion = "策略表现正常，维持当前策略"
        elif win_rate >= 0.4:
            suggestion = "胜率偏低，建议适当降低仓位"
        else:
            suggestion = "胜率过低，建议暂停自动交易并复盘"

        return {
            "success": True,
            "days": days,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 3),
            "total_pnl": round(total_pnl, 2),
            "profit_factor": perf.get("profit_factor", 0),
            "max_drawdown": perf.get("max_drawdown", 0),
            "sharpe": round(perf.get("sharpe", 0), 2),
            "suggestion": suggestion,
        }
    except ImportError:
        return {"success": False, "reason": "trading_journal 模块不可用"}
    except Exception as e:
        return {"success": False, "reason": str(e)}


# ─────────── 账单追踪 (话费/水电费余额检测提醒) ───────────

# 账单类型 → emoji 映射
BILL_TYPE_EMOJI = {
    "phone": "📱", "electricity": "⚡", "water": "💧",
    "gas": "🔥", "internet": "🌐",
}

# 中文别名 → 标准类型映射
BILL_TYPE_ALIAS = {
    "话费": "phone", "手机费": "phone", "手机": "phone", "电话费": "phone",
    "移动": "phone", "联通": "phone", "电信": "phone",
    "电费": "electricity", "电力": "electricity", "电": "electricity",
    "水费": "water", "水": "water", "自来水": "water",
    "燃气费": "gas", "煤气费": "gas", "天然气": "gas", "燃气": "gas", "煤气": "gas",
    "宽带": "internet", "网费": "internet", "光纤": "internet", "wifi": "internet",
    "phone": "phone", "electricity": "electricity", "water": "water",
    "gas": "gas", "internet": "internet",
}

# 中文类型显示名
BILL_TYPE_LABEL = {
    "phone": "话费", "electricity": "电费", "water": "水费",
    "gas": "燃气费", "internet": "宽带",
}

# 每用户账单上限
MAX_BILL_ACCOUNTS_PER_USER = 20


def resolve_bill_type(raw: str) -> str:
    """将中文别名解析为标准 account_type，无法识别返回空字符串"""
    key = (raw or "").strip().lower().replace(" ", "")
    return BILL_TYPE_ALIAS.get(key, "")


def add_bill_account(
    user_id, chat_id, account_type, account_name="", provider="",
    low_threshold=30, remind_day=0, db_path=None,
) -> dict:
    """添加账单追踪 — 返回 account_id"""
    # 类型验证
    if account_type not in BILL_TYPE_EMOJI:
        return {"success": False, "error": f"不支持的账单类型: {account_type}"}
    # 阈值合理性
    low_threshold = max(0, min(float(low_threshold), 100000))
    remind_day = max(0, min(int(remind_day), 31))
    try:
        with get_conn(db_path) as conn:
            # 检查用户账单数量上限
            count = conn.execute(
                "SELECT COUNT(*) FROM bill_accounts WHERE user_id=? AND status='active'",
                (str(user_id),),
            ).fetchone()[0]
            if count >= MAX_BILL_ACCOUNTS_PER_USER:
                return {"success": False, "error": f"最多只能追踪 {MAX_BILL_ACCOUNTS_PER_USER} 个账单"}
            cursor = conn.execute(
                "INSERT INTO bill_accounts "
                "(user_id, chat_id, account_type, account_name, provider, "
                "low_threshold, remind_day) VALUES (?,?,?,?,?,?,?)",
                (str(user_id), str(chat_id), account_type,
                 str(account_name or "")[:100], str(provider or "")[:100],
                 low_threshold, remind_day),
            )
            return {
                "success": True,
                "account_id": cursor.lastrowid,
                "account_type": account_type,
                "account_name": account_name,
            }
    except Exception as e:
        logger.error("[Bill] 添加账单追踪失败: %s", e)
        return {"success": False, "error": str(e)}


def update_bill_balance(account_id, balance, user_id=None, db_path=None) -> dict:
    """更新账单余额 — 返回是否触发低余额告警"""
    import time as _time
    balance = round(float(balance), 2)
    if balance < 0 or balance > 1_000_000:
        return {"success": False, "error": "余额无效，请输入 0 ~ 1,000,000"}
    try:
        with get_conn(db_path) as conn:
            # 查询账单信息
            where = "id=? AND status='active'"
            params = [account_id]
            if user_id is not None:
                where += " AND user_id=?"
                params.append(str(user_id))
            row = conn.execute(
                f"SELECT id, account_type, account_name, low_threshold FROM bill_accounts WHERE {where}",
                params,
            ).fetchone()
            if not row:
                return {"success": False, "error": "账单不存在或无权限"}
            _, acct_type, acct_name, threshold = row
            now_ts = _time.time()
            conn.execute(
                "UPDATE bill_accounts SET balance=?, last_updated=? WHERE id=?",
                (balance, now_ts, account_id),
            )
            # 判断是否低于阈值
            is_low = balance <= threshold
            return {
                "success": True,
                "account_id": account_id,
                "account_type": acct_type,
                "account_name": acct_name,
                "balance": balance,
                "threshold": threshold,
                "is_low": is_low,
            }
    except Exception as e:
        logger.error("[Bill] 更新余额失败: %s", e)
        return {"success": False, "error": str(e)}


def list_bill_accounts(user_id, db_path=None) -> list:
    """列出用户的账单追踪列表"""
    try:
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT id, account_type, account_name, provider, balance, "
                "low_threshold, last_updated, remind_day, status "
                "FROM bill_accounts WHERE user_id=? AND status='active' "
                "ORDER BY id ASC",
                (str(user_id),),
            ).fetchall()
            return [
                {
                    "id": r[0], "account_type": r[1], "account_name": r[2],
                    "provider": r[3], "balance": r[4], "low_threshold": r[5],
                    "last_updated": r[6], "remind_day": r[7], "status": r[8],
                }
                for r in rows
            ]
    except Exception as e:  # noqa: F841
        return []


def remove_bill_account(account_id, user_id, db_path=None) -> bool:
    """删除账单追踪（软删除）"""
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "UPDATE bill_accounts SET status='deleted' "
                "WHERE id=? AND user_id=? AND status='active'",
                (account_id, str(user_id)),
            )
            return cursor.rowcount > 0
    except Exception as e:
        logger.error("[Bill] 删除账单失败: %s", e)
        return False


def check_bill_alerts(db_path=None) -> list:
    """检查所有用户的低余额告警 — 返回需要通知的列表

    条件: balance <= low_threshold AND 距上次告警超过24小时
    """
    import time as _time
    cutoff = _time.time() - 86400  # 24小时防重复
    alerts = []
    try:
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT id, user_id, chat_id, account_type, account_name, "
                "balance, low_threshold, last_updated "
                "FROM bill_accounts "
                "WHERE status='active' AND balance <= low_threshold "
                "AND last_updated > 0 AND last_alert_ts < ?",
                (cutoff,),
            ).fetchall()
            now_ts = _time.time()
            for r in rows:
                alerts.append({
                    "account_id": r[0], "user_id": r[1], "chat_id": r[2],
                    "account_type": r[3], "account_name": r[4],
                    "balance": r[5], "low_threshold": r[6],
                    "last_updated": r[7],
                })
                # 标记已告警，防止 24 小时内重复
                conn.execute(
                    "UPDATE bill_accounts SET last_alert_ts=? WHERE id=?",
                    (now_ts, r[0]),
                )
    except Exception as e:
        logger.error("[Bill] 低余额告警检查失败: %s", e)
    return alerts


def get_bill_reminders_due(db_path=None) -> list:
    """获取今天需要发送的账单查询提醒

    条件: remind_day == 今天的日期 AND status='active'
    """
    today_day = now_et().day
    results = []
    try:
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT id, user_id, chat_id, account_type, account_name, "
                "balance, low_threshold, last_updated "
                "FROM bill_accounts "
                "WHERE status='active' AND remind_day=?",
                (today_day,),
            ).fetchall()
            for r in rows:
                results.append({
                    "account_id": r[0], "user_id": r[1], "chat_id": r[2],
                    "account_type": r[3], "account_name": r[4],
                    "balance": r[5], "low_threshold": r[6],
                    "last_updated": r[7],
                })
    except Exception as e:
        logger.error("[Bill] 查询提醒检查失败: %s", e)
    return results


def find_bill_by_type(user_id, account_type, db_path=None):
    """按类型查找用户的第一个匹配账单 — 用于 NLP 自动更新"""
    try:
        with get_conn(db_path) as conn:
            row = conn.execute(
                "SELECT id, account_type, account_name, balance, low_threshold "
                "FROM bill_accounts WHERE user_id=? AND account_type=? AND status='active' "
                "ORDER BY id ASC LIMIT 1",
                (str(user_id), account_type),
            ).fetchone()
            if row:
                return {
                    "id": row[0], "account_type": row[1],
                    "account_name": row[2], "balance": row[3],
                    "low_threshold": row[4],
                }
    except Exception as e:
        pass
        logger.debug("静默异常: %s", e)
    return None


# ─────────── 降价监控 (购物价格追踪提醒) ───────────

# 每个用户最多 10 个活跃监控
MAX_PRICE_WATCHES_PER_USER = 10


def add_price_watch(user_id, chat_id, keyword, target_price,
                    platform="all", db_path=None) -> dict:
    """添加降价监控 — 返回 watch_id

    用户说 "帮我盯着AirPods，降到800以下告诉我" 就会调用此函数。
    """
    # 参数校验
    keyword = str(keyword or "").strip()
    if not keyword or len(keyword) > 100:
        return {"success": False, "error": "商品关键词不能为空且不超过100字"}
    target_price = float(target_price)
    if target_price <= 0 or target_price > 1_000_000:
        return {"success": False, "error": "目标价格无效，请输入 0.01 ~ 1,000,000"}
    try:
        with get_conn(db_path) as conn:
            # 检查用户活跃监控数量上限
            count = conn.execute(
                "SELECT COUNT(*) FROM price_watches "
                "WHERE user_id=? AND status='active'",
                (str(user_id),),
            ).fetchone()[0]
            if count >= MAX_PRICE_WATCHES_PER_USER:
                return {
                    "success": False,
                    "error": f"最多只能同时监控 {MAX_PRICE_WATCHES_PER_USER} 个商品",
                }
            cursor = conn.execute(
                "INSERT INTO price_watches "
                "(user_id, chat_id, keyword, target_price, platform) "
                "VALUES (?,?,?,?,?)",
                (str(user_id), str(chat_id), keyword,
                 target_price, platform or "all"),
            )
            return {
                "success": True,
                "watch_id": cursor.lastrowid,
                "keyword": keyword,
                "target_price": target_price,
                "platform": platform,
            }
    except Exception as e:
        logger.error("[PriceWatch] 添加监控失败: %s", e)
        return {"success": False, "error": str(e)}


def list_price_watches(user_id, db_path=None) -> list:
    """列出用户的降价监控 — 返回活跃的监控列表"""
    try:
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT id, keyword, target_price, current_price, "
                "lowest_price, platform, status, created_at, last_checked "
                "FROM price_watches "
                "WHERE user_id=? AND status IN ('active', 'paused') "
                "ORDER BY id ASC",
                (str(user_id),),
            ).fetchall()
            return [
                {
                    "id": r[0], "keyword": r[1], "target_price": r[2],
                    "current_price": r[3], "lowest_price": r[4],
                    "platform": r[5], "status": r[6],
                    "created_at": r[7], "last_checked": r[8],
                }
                for r in rows
            ]
    except Exception as e:  # noqa: F841
        return []


def remove_price_watch(watch_id, user_id, db_path=None) -> bool:
    """删除降价监控（软删除: 改状态为 cancelled）"""
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "UPDATE price_watches SET status='cancelled' "
                "WHERE id=? AND user_id=? AND status='active'",
                (watch_id, str(user_id)),
            )
            return cursor.rowcount > 0
    except Exception as e:
        logger.error("[PriceWatch] 删除监控失败: %s", e)
        return False


async def check_price_watches(notify_func=None, db_path=None) -> int:
    """定时检查所有活跃监控的价格变化 — 发现降价则通知用户

    逻辑:
    1. 查询所有 status='active' 的监控
    2. 对每个监控，调用 compare_prices(keyword) 获取当前最低价
    3. 更新 current_price 和 lowest_price
    4. 如果 current_price <= target_price:
       - 状态改为 triggered
       - 调用 notify_func 发送降价通知

    返回: 本次触发的降价通知数量
    """
    import asyncio as _asyncio
    import time as _time

    triggered_count = 0
    try:
        # 获取所有活跃监控
        with get_conn(db_path) as conn:
            watches = conn.execute(
                "SELECT id, user_id, chat_id, keyword, target_price, "
                "current_price, lowest_price "
                "FROM price_watches WHERE status='active'"
            ).fetchall()

        if not watches:
            return 0

        logger.info("[PriceWatch] 开始检查 %d 个活跃监控", len(watches))

        # 复用现有比价引擎
        from src.shopping.price_engine import compare_prices

        for watch in watches:
            wid, user_id, chat_id, keyword, target, old_price, lowest = watch
            try:
                # 调用比价引擎获取当前价格
                report = await compare_prices(keyword, use_ai_summary=False,
                                              limit_per_platform=3)
                # 从结果中提取最低价
                best = report.best_deal
                if not best or best.get("price", 0) <= 0:
                    # 没找到有效价格，跳过但更新检查时间
                    with get_conn(db_path) as conn:
                        conn.execute(
                            "UPDATE price_watches SET last_checked=? WHERE id=?",
                            (_time.time(), wid),
                        )
                    await _asyncio.sleep(3)  # 防反爬间隔
                    continue

                new_price = best["price"]
                new_lowest = min(lowest, new_price) if lowest > 0 else new_price
                now_ts = _time.time()

                # 判断是否达到目标价
                if new_price <= target:
                    # 降价触发！
                    with get_conn(db_path) as conn:
                        conn.execute(
                            "UPDATE price_watches SET current_price=?, "
                            "lowest_price=?, last_checked=?, "
                            "status='triggered', triggered_at=? WHERE id=?",
                            (new_price, new_lowest, now_ts, now_ts, wid),
                        )
                    triggered_count += 1

                    # 发送降价通知
                    if notify_func:
                        platform_info = best.get("platform", "")
                        title_info = best.get("title", keyword)[:50]
                        msg = (
                            f"🔔 降价提醒！\n\n"
                            f"📦 {title_info}\n"
                            f"💰 当前价: ¥{new_price}\n"
                            f"🎯 目标价: ¥{target}\n"
                            f"📉 已降到目标价以下！\n"
                        )
                        if platform_info:
                            msg += f"🏪 平台: {platform_info}\n"
                        url = best.get("url", "")
                        if url:
                            msg += f"🔗 链接: {url}\n"
                        msg += "\n💡 此监控已自动停止，如需继续可重新添加"
                        try:
                            await notify_func(msg, chat_id=int(chat_id))
                        except Exception as e:
                            logger.warning("[PriceWatch] 通知发送失败: %s", e)
                else:
                    # 未达目标价，仅更新价格数据
                    with get_conn(db_path) as conn:
                        conn.execute(
                            "UPDATE price_watches SET current_price=?, "
                            "lowest_price=?, last_checked=? WHERE id=?",
                            (new_price, new_lowest, now_ts, wid),
                        )

                # 防反爬: 每次查询间隔 3 秒
                await _asyncio.sleep(3)

            except Exception as e:
                logger.warning("[PriceWatch] 检查 #%d (%s) 失败: %s", wid, keyword, e)
                continue

        logger.info("[PriceWatch] 检查完成, %d 个触发降价通知", triggered_count)

    except Exception as e:
        logger.error("[PriceWatch] 批量检查异常: %s", e)

    return triggered_count


# ─────────── 数据生命周期清理 ───────────

def cleanup_stale_watches(days_triggered=30, days_expired=90, db_path=None):
    """清理过期的降价监控和账单追踪

    三项清理:
    1. 已触发/已取消超过 days_triggered 天的降价监控 → 永久删除
    2. 已删除超过 days_triggered 天的账单追踪 → 永久删除
    3. active 但超过 days_expired 天未检查的降价监控 → 标记为 expired

    Returns:
        dict: 各项清理的行数统计
    """
    import time as _time

    result = {
        "price_watches_purged": 0,
        "price_watches_expired": 0,
        "bill_accounts_purged": 0,
    }
    now_ts = _time.time()

    try:
        with get_conn(db_path) as conn:
            # 1. 清理已触发/已取消超过 N 天的降价监控（硬删除）
            cutoff_triggered = now_ts - days_triggered * 86400
            try:
                cursor = conn.execute(
                    "DELETE FROM price_watches "
                    "WHERE status IN ('triggered', 'cancelled') "
                    "AND COALESCE(triggered_at, created_at) < ?",
                    (cutoff_triggered,),
                )
                result["price_watches_purged"] = cursor.rowcount
            except Exception as e:
                logger.debug("[Cleanup] 清理降价监控失败: %s", e)

            # 2. 清理已删除超过 N 天的账单追踪（硬删除）
            try:
                cursor = conn.execute(
                    "DELETE FROM bill_accounts "
                    "WHERE status = 'deleted' "
                    "AND last_updated < ?",
                    (cutoff_triggered,),
                )
                result["bill_accounts_purged"] = cursor.rowcount
            except Exception as e:
                logger.debug("[Cleanup] 清理账单追踪失败: %s", e)

            # 3. 超过 N 天未更新的 active 降价监控 → 标记为 expired
            cutoff_expired = now_ts - days_expired * 86400
            try:
                cursor = conn.execute(
                    "UPDATE price_watches SET status = 'expired' "
                    "WHERE status = 'active' "
                    "AND last_checked > 0 AND last_checked < ?",
                    (cutoff_expired,),
                )
                result["price_watches_expired"] = cursor.rowcount
            except Exception as e:
                logger.debug("[Cleanup] 标记过期监控失败: %s", e)

    except Exception as e:
        logger.error("[Cleanup] 数据生命周期清理异常: %s", e)

    total = sum(result.values())
    if total > 0:
        logger.info(
            "[Cleanup] 数据清理: 删除监控=%d, 过期监控=%d, 删除账单=%d",
            result["price_watches_purged"],
            result["price_watches_expired"],
            result["bill_accounts_purged"],
        )
    return result
