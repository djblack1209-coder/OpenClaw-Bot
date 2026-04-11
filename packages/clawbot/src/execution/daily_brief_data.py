"""
每日日报 — 数据采集模块

提供昨日对比、delta 计算、日程构建、趋势项目获取等数据采集功能。
每个数据源独立 try/except，一个失败不影响其他。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from src.execution._db import get_conn

logger = logging.getLogger(__name__)


def _section(title: str, items: List[str]) -> Tuple[str, List[str]]:
    """构建一个 section tuple (title, items) for format_digest"""
    return (title, items)


def _get_timestamp_tag() -> str:
    """获取时间戳标签，优先使用 notify_style 的统一格式"""
    try:
        from src.notify_style import timestamp_tag
        return timestamp_tag()
    except Exception:
        return datetime.now(timezone.utc).strftime("%H:%M UTC")


async def _get_yesterday_comparison(db_path=None) -> dict:
    """获取昨日关键指标，用于与今日数据对比计算 delta。

    只对比 3-4 个核心指标（持仓盈亏/闲鱼咨询/闲鱼下单/社媒发帖），
    每个数据源独立 try/except，任一失败不影响其他。

    Args:
        db_path: 可选的数据库路径
    Returns:
        昨日指标字典，如 {"portfolio_pnl": 100.5, "xianyu_consultations": 12, ...}
    """
    from src.utils import now_et
    yesterday_str = (now_et() - timedelta(days=1)).strftime("%Y-%m-%d")
    result = {}

    # 1. 昨日持仓盈亏 — 从交易日志获取
    try:
        from src.trading_journal import journal
        if journal and hasattr(journal, "get_today_pnl"):
            # get_today_pnl 返回今日的，我们需要用 get_performance(days=1) 近似
            perf = journal.get_performance(days=1)
            if perf:
                result["portfolio_pnl"] = perf.get("total_pnl", 0)
    except Exception as e:
        logger.debug(f"[DailyBrief] 昨日持仓对比失败: {e}")

    # 2. 昨日闲鱼数据 — daily_stats 支持传入日期
    try:
        from src.xianyu.xianyu_context import XianyuContextManager
        xctx = XianyuContextManager()
        if hasattr(xctx, "daily_stats"):
            ystats = xctx.daily_stats(date=yesterday_str)
            if ystats:
                result["xianyu_consultations"] = ystats.get("consultations", 0)
                result["xianyu_orders"] = ystats.get("orders", 0)
    except Exception as e:
        logger.debug(f"[DailyBrief] 昨日闲鱼对比失败: {e}")

    # 3. 昨日社媒发帖 — 通过 engagement_summary(days=1) 近似
    try:
        from src.execution.life_automation import get_engagement_summary
        eng = get_engagement_summary(days=1, db_path=db_path)
        if eng.get("success"):
            result["social_posts"] = eng.get("total_posts", 0)
    except Exception as e:
        logger.debug(f"[DailyBrief] 昨日社媒对比失败: {e}")

    return result


def _calc_deltas(today_data: dict, yesterday_data: dict) -> dict:
    """计算今日 vs 昨日的差值。

    Args:
        today_data: 今日指标字典
        yesterday_data: 昨日指标字典（来自 _get_yesterday_comparison）
    Returns:
        中文标签到 delta 值的映射，如 {"持仓盈亏": +50.0, "闲鱼咨询": -3}
    """
    # 定义要对比的指标: (内部 key, 中文标签)
    comparisons = [
        ("portfolio_pnl", "持仓盈亏"),
        ("xianyu_consultations", "闲鱼咨询"),
        ("xianyu_orders", "闲鱼下单"),
        ("social_posts", "社媒发帖"),
    ]
    deltas = {}
    for key, label in comparisons:
        today_val = today_data.get(key, 0)
        yesterday_val = yesterday_data.get(key, 0)
        # 只有两边都有数据时才计算 delta
        if today_val != 0 or yesterday_val != 0:
            deltas[label] = today_val - yesterday_val
    return deltas


def _format_delta(value, unit: str = "") -> str:
    """格式化 delta 值为带箭头的可读文本。

    Args:
        value: 差值（正数=增长，负数=下降）
        unit: 单位后缀，如 "条"、"笔"、""
    Returns:
        格式化文本如 "↑3条" 或 "↓$50.00"
    """
    if value == 0:
        return ""
    arrow = "↑" if value > 0 else "↓"
    abs_val = abs(value)
    if isinstance(value, float) and unit == "$":
        return f" ({arrow}${abs_val:,.2f})"
    return f" ({arrow}{abs_val:.0f}{unit})"


async def _build_today_agenda(db_path=None) -> List[str]:
    """今日日程 — 合并所有数据源按紧急度排序

    数据源:
      1. 持仓风险项 — position_monitor 距止损 <3%
      2. 今日提醒 — reminders 今天到期
      3. 账单到期 — bill_accounts remind_day == 今天
      4. 今日待办 — top_tasks
      5. 降价监控到期 — price_watches last_checked 超过1天

    返回排序后的日程文本列表，空列表表示无日程。
    """
    # (优先级, 文本) — 数字越小越紧急
    agenda: List[Tuple[int, str]] = []

    # ── 1. 持仓风险项 — 接近止损的持仓 ──
    try:
        from src.position_monitor import position_monitor
        if position_monitor and position_monitor.positions:
            status = position_monitor.get_status()
            for p in status.get("positions", []):
                cur = p.get("current_price", 0)
                sl = p.get("stop_loss", 0)
                sym = p.get("symbol", "?")
                if sl > 0 and cur > 0:
                    distance = (cur - sl) / cur * 100
                    if 0 < distance < 3:
                        agenda.append((0, f"⚡ {sym} 距止损仅 {distance:.1f}%，注意！"))
    except Exception as e:
        logger.debug(f"[TodayAgenda] 持仓风险: {e}")

    # ── 2. 今日提醒 ──
    try:
        from src.execution.life_automation import list_reminders
        from src.utils import now_et
        pending = list_reminders(status="pending", db_path=db_path)
        if pending:
            now = now_et()
            today_end = now.replace(hour=23, minute=59, second=59)
            for r in pending:
                try:
                    remind_time = datetime.fromisoformat(r["remind_at"])
                    if remind_time <= today_end:
                        time_str = remind_time.strftime("%H:%M")
                        agenda.append((1, f"⏰ {time_str} {r['message']}"))
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        logger.debug(f"[TodayAgenda] 提醒: {e}")

    # ── 3. 账单到期 ──
    try:
        from src.execution.life_automation import get_bill_reminders_due
        bills = get_bill_reminders_due(db_path=db_path)
        for b in bills:
            name = b.get("account_name", b.get("account_type", "账单"))
            balance = b.get("balance", 0)
            threshold = b.get("low_threshold", 0)
            alert = " ‼️ 低于阈值" if threshold and balance < threshold else ""
            agenda.append((1, f"📱 {name} 余额 ¥{balance:.0f}{alert}"))
    except Exception as e:
        logger.debug(f"[TodayAgenda] 账单: {e}")

    # ── 4. 今日待办 ──
    try:
        from src.execution.task_mgmt import top_tasks
        tasks = top_tasks(limit=3, db_path=db_path)
        for t in tasks:
            agenda.append((2, f"📝 {t.get('title', '未命名任务')} (待办)"))
    except Exception as e:
        logger.debug(f"[TodayAgenda] 待办: {e}")

    # ── 5. 降价监控到期 — 超过1天未检查的活跃监控 ──
    try:
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT keyword, last_checked FROM price_watches "
                "WHERE status='active' AND last_checked IS NOT NULL "
                "AND (julianday('now') - julianday(last_checked)) > 1.0 "
                "LIMIT 5"
            ).fetchall()
            for r in rows:
                agenda.append((3, f"🛒 {r[0]} 监控已超1天未检查"))
    except Exception as e:
        logger.debug(f"[TodayAgenda] 降价监控: {e}")

    if not agenda:
        return []

    # 按紧急度排序，同级保持插入顺序
    agenda.sort(key=lambda x: x[0])
    return [text for _, text in agenda]


async def _fetch_trending_projects() -> List[str]:
    """从 GitHub Trending 获取与 OpenClaw 相关的有价值项目"""

    # 关注的关键领域
    INTEREST_KEYWORDS = [
        "telegram bot", "social media", "auto upload", "xianyu", "闲鱼",
        "llm", "ai agent", "tts", "edge-tts", "novel writing",
        "trading bot", "web scraping", "automation",
        "小红书", "douyin", "bilibili", "wechat",
    ]

    items: List[str] = []
    try:
        # 使用现有的 github_trending 模块
        try:
            from src.evolution.github_trending import fetch_trending
            repos = await fetch_trending(language="python", since="daily")
            if repos:
                for repo in repos[:10]:
                    name = repo.name or ""
                    desc = (repo.description or "").lower()
                    stars = repo.stars or 0
                    # 筛选与 OpenClaw 领域相关的
                    relevant = any(kw in desc or kw in name.lower() for kw in INTEREST_KEYWORDS)
                    if relevant and stars > 50:
                        items.append(
                            f"⭐{stars} {name}: {repo.description[:80] if repo.description else ''}"
                        )
        except ImportError:
            pass

        if not items:
            items.append("暂无与 OpenClaw 相关的热门项目")
        else:
            items.insert(0, "今日与 OpenClaw 相关的 GitHub 热门项目:")
    except Exception as e:
        logger.debug("[DailyBrief] Trending 获取失败: %s", e)
        items.append("GitHub Trending 获取失败")

    return items
