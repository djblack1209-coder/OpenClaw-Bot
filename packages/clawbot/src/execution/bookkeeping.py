"""
Execution — 记账与账单管理
包含个人收支记录、预算管理、账单跟踪等功能。
从 life_automation.py 拆分以改善可维护性。

> 最后更新: 2026-03-28
"""
import logging
from datetime import datetime

from src.execution._db import get_conn
from src.utils import now_et

logger = logging.getLogger(__name__)

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
        # 发射预算超支事件到 EventBus — 触发主动通知引擎
        try:
            import asyncio
            from src.core.event_bus import get_event_bus, EventType
            bus = get_event_bus()
            _event_data = {
                "category": "总支出",
                "amount": spent,
                "budget": budget,
            }
            try:
                loop = asyncio.get_running_loop()
                # 有事件循环时创建异步任务
                loop.create_task(bus.publish(
                    EventType.BUDGET_EXCEEDED, _event_data, source="life_automation",
                ))
            except RuntimeError:
                # 无事件循环（同步调用场景），跳过事件发射
                pass
        except Exception as e:
            logger.debug(f"[预算] 发射超支事件失败: {e}")

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
        logger.debug("静默异常: %s", e)
    return None
