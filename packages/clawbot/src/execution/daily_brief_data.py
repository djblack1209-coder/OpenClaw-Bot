"""
每日日报 — 数据采集模块

提供昨日对比、delta 计算、日程构建、趋势项目获取、天气、汇率等数据采集功能。
每个数据源独立 try/except，一个失败不影响其他。
"""

import logging
import os
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
        "telegram bot",
        "social media",
        "auto upload",
        "xianyu",
        "闲鱼",
        "llm",
        "ai agent",
        "tts",
        "edge-tts",
        "novel writing",
        "trading bot",
        "web scraping",
        "automation",
        "小红书",
        "douyin",
        "bilibili",
        "wechat",
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
                        items.append(f"⭐{stars} {name}: {repo.description[:80] if repo.description else ''}")
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


# ═══════════════════════════════════════════════════════════════
# 日报 Section 子函数 — 每个函数负责采集一个 section 并 append 到 sections
# 命名统一: _brief_xxx(sections, **kwargs) -> None
# 异常策略: 每个函数内部 try/except，一个 section 失败不影响其他
# ═══════════════════════════════════════════════════════════════


async def _brief_agenda(sections: list, *, db_path=None) -> None:
    """section 0: 今日日程 — 所有源按紧急度排序"""
    try:
        agenda_items = await _build_today_agenda(db_path=db_path)
        if agenda_items:
            sections.append(_section("📋 今日日程", agenda_items))
    except Exception as e:
        logger.debug("[DailyBrief] agenda: %s", e)


async def _brief_quick_ref(sections: list) -> None:
    """section 0.5: 天气+汇率快速参考"""
    try:
        import asyncio as _asyncio

        # 并行获取天气和汇率，互不阻塞
        weather_result, forex_result = await _asyncio.gather(
            _fetch_weather(),
            _fetch_forex(),
            return_exceptions=True,
        )
        # 处理异常返回值
        weather_text = weather_result if isinstance(weather_result, str) else ""
        forex_text = forex_result if isinstance(forex_result, str) else ""

        quick_ref_items = []
        if weather_text:
            quick_ref_items.append(f"🌤 天气: {weather_text}")
        if forex_text:
            quick_ref_items.append(f"💱 汇率: {forex_text}")
        if quick_ref_items:
            sections.append(_section("🌍 快速参考", quick_ref_items))
    except Exception as e:
        logger.debug("[DailyBrief] 天气/汇率: %s", e)


async def _brief_positions(sections: list) -> None:
    """section 1: 持仓概览"""
    try:
        from src.position_monitor import position_monitor

        if position_monitor and position_monitor.positions:
            status = position_monitor.get_status()
            items = []
            total_pnl = status.get("total_unrealized_pnl", 0)
            pnl_emoji = "📈" if total_pnl >= 0 else "📉"
            items.append(f"{pnl_emoji} 总浮盈亏: ${total_pnl:+,.2f}")
            items.append(f"监控持仓: {status.get('monitored_count', 0)} 个")
            for p in status.get("positions", [])[:5]:
                sym = p["symbol"]
                pnl_pct = p.get("unrealized_pnl_pct", 0)
                cur = p.get("current_price", 0)
                sl = p.get("stop_loss", 0)
                emoji = "🟢" if pnl_pct >= 0 else "🔴"
                line = f"{emoji} {sym} ${cur:.2f} ({pnl_pct:+.1f}%)"
                if sl > 0:
                    distance = ((cur - sl) / cur * 100) if cur > 0 else 0
                    line += f" | SL ${sl:.2f} ({distance:.0f}%)"
                items.append(line)
            if status.get("recent_exits", 0) > 0:
                items.append(f"最近自动平仓: {status['recent_exits']} 笔")
            sections.append(_section("💼 持仓概览", items))
        else:
            # 持仓数据为空，显示引导占位
            sections.append(_section("💼 持仓概览", ["暂无持仓数据", "💡 说「帮我投资 AAPL」开始你的第一笔交易"]))
    except Exception as e:
        logger.debug("[DailyBrief] positions: %s", e)
        # 获取持仓数据异常，显示引导占位
        sections.append(_section("💼 持仓概览", ["暂无持仓数据", "💡 说「帮我投资 AAPL」开始你的第一笔交易"]))


async def _brief_trading(sections: list) -> None:
    """section 2: 交易绩效 + 今日交易"""
    try:
        from src.trading_journal import journal

        if journal:
            perf = journal.get_performance(days=7)
            if perf and perf.get("total_trades", 0) > 0:
                items = []
                items.append(f"7日战绩: {perf.get('total_trades', 0)} 笔 | 胜率 {perf.get('win_rate', 0):.0f}%")
                items.append(f"累计盈亏: ${perf.get('total_pnl', 0):+,.2f}")
                if perf.get("sharpe"):
                    items.append(f"夏普比率: {perf['sharpe']:.2f} | 最大回撤: {perf.get('max_drawdown', 0):.1f}%")
                if perf.get("expectancy"):
                    items.append(f"期望值: ${perf['expectancy']:+.2f}/笔")
                sections.append(_section("📊 7日交易绩效", items))
            else:
                # 无交易记录，显示引导占位
                sections.append(_section("📊 交易绩效", ["暂无交易记录", "💡 说「自动交易」让AI帮你寻找机会"]))

            # 今日 P&L
            today_pnl = journal.get_today_pnl()
            if today_pnl and today_pnl.get("trades", 0) > 0:
                items = [
                    f"今日: {today_pnl['trades']} 笔 | "
                    f"胜 {today_pnl.get('wins', 0)} 负 {today_pnl.get('losses', 0)} | "
                    f"盈亏 ${today_pnl.get('pnl', 0):+,.2f}"
                ]
                if today_pnl.get("hit_limit"):
                    items.append("⚠️ 已触及日亏损限额")
                sections.append(_section("📅 今日交易", items))
        else:
            # journal 模块未初始化，显示引导占位
            sections.append(_section("📊 交易绩效", ["暂无交易记录", "💡 说「自动交易」让AI帮你寻找机会"]))
    except Exception as e:
        logger.debug("[DailyBrief] journal: %s", e)
        # 获取交易数据异常，显示引导占位
        sections.append(_section("📊 交易绩效", ["暂无交易记录", "💡 说「自动交易」让AI帮你寻找机会"]))


async def _brief_targets(sections: list) -> None:
    """section 3: 目标进度"""
    try:
        from src.trading_journal import journal

        if journal:
            targets = journal.get_active_targets()
            if targets:
                items = []
                for t in targets[:3]:
                    name = t.get("name", "目标")
                    progress = t.get("progress_pct", 0)
                    bar_len = 10
                    filled = int(progress / 100 * bar_len)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    items.append(f"{name}: [{bar}] {progress:.0f}%")
                sections.append(_section("🎯 目标进度", items))
    except Exception as e:
        logger.debug("[DailyBrief] targets: %s", e)


async def _brief_todos(sections: list, *, db_path=None) -> None:
    """section 4: 待办事项"""
    try:
        from src.execution.task_mgmt import top_tasks

        tasks = top_tasks(limit=5, db_path=db_path)
        if tasks:
            items = []
            for t in tasks:
                status_icon = {"done": "✅", "in_progress": "🔄"}.get(t.get("status", ""), "⬜")
                items.append(f"{status_icon} {t.get('title', '')}")
            sections.append(_section("📋 待办事项", items))
    except Exception as e:
        logger.debug("[DailyBrief] tasks: %s", e)


async def _brief_reminders(sections: list, *, db_path=None) -> None:
    """section 4.5: 今日提醒"""
    try:
        from src.execution.life_automation import list_reminders
        from src.utils import now_et

        pending = list_reminders(status="pending", db_path=db_path)
        if pending:
            now = now_et()
            today_end = now.replace(hour=23, minute=59, second=59)
            today_reminders = []
            recurring_reminders = []
            for r in pending:
                try:
                    remind_time = datetime.fromisoformat(r["remind_at"])
                    if remind_time <= today_end:
                        time_str = remind_time.strftime("%H:%M")
                        today_reminders.append(f"⏰ {time_str} — {r['message']}")
                except (ValueError, TypeError):
                    pass
                # 重复提醒也列出（不论时间）
                recurrence = r.get("recurrence_rule", "")
                if recurrence:
                    recurring_reminders.append(f"🔄 {r['message']} ({recurrence})")

            items = []
            if today_reminders:
                items.extend(sorted(today_reminders))
            if recurring_reminders and not today_reminders:
                # 只有重复提醒没有今日一次性提醒时才显示
                items.extend(recurring_reminders[:3])
            if items:
                sections.append(_section("⏰ 今日提醒", items))
    except Exception as e:
        logger.debug("[DailyBrief] reminders: %s", e)


async def _brief_watchlist(sections: list, *, monitors=None) -> None:
    """section 4.8: 关注股票隔夜变动"""
    try:
        from src.invest_tools import get_quick_quotes

        # 从持仓和关注列表获取用户关注的股票
        watchlist_symbols = []
        try:
            if monitors:
                pm = monitors.get("position_monitor")
                if pm:
                    positions = pm.get_positions() if hasattr(pm, "get_positions") else []
                    for pos in positions or []:
                        sym = pos.get("symbol", "")
                        if sym:
                            watchlist_symbols.append(sym)
        except Exception as e:
            logger.debug("关注股票-持仓获取异常: %s", e)

        # 补充 watchlist 中的股票
        try:
            from src.watchlist import get_watchlist_symbols

            wl = get_watchlist_symbols()
            for sym in wl or []:
                if sym not in watchlist_symbols:
                    watchlist_symbols.append(sym)
        except Exception as e:
            logger.debug("关注股票-自选列表获取异常: %s", e)

        if watchlist_symbols:
            quotes = await get_quick_quotes(watchlist_symbols[:10])  # 最多10只
            if quotes:
                items = []
                for sym in watchlist_symbols[:10]:
                    data = quotes.get(sym)
                    if not data:
                        continue
                    price = data.get("price", 0)
                    change = data.get("change_pct", 0)
                    if abs(change) < 0.5:
                        continue  # 变动<0.5%不显示,减少噪音
                    emoji = "📈" if change >= 0 else "📉"
                    items.append(f"{emoji} {sym}: ${price:,.2f} ({change:+.2f}%)")
                if items:
                    sections.append(_section("👀 关注股票隔夜变动", items))
        else:
            # 无自选股，显示引导占位
            sections.append(_section("👀 关注股票", ["暂无自选股", "💡 说「关注 TSLA」添加你感兴趣的股票"]))
    except Exception as e:
        logger.debug("[DailyBrief] watchlist: %s", e)
        # 获取关注股票数据异常，显示引导占位
        sections.append(_section("👀 关注股票", ["暂无自选股", "💡 说「关注 TSLA」添加你感兴趣的股票"]))


async def _brief_market(sections: list) -> None:
    """section 5: 市场行情 — 9 大指数"""
    try:
        from src.invest_tools import get_quick_quotes

        symbols = ["^GSPC", "^IXIC", "^DJI", "^HSI", "000001.SS", "BTC-USD", "ETH-USD", "GC=F", "CL=F"]
        names = {
            "^GSPC": "S&P 500",
            "^IXIC": "纳斯达克",
            "^DJI": "道琼斯",
            "^HSI": "恒生",
            "000001.SS": "上证",
            "BTC-USD": "BTC",
            "ETH-USD": "ETH",
            "GC=F": "黄金",
            "CL=F": "原油",
        }
        quotes = await get_quick_quotes(symbols)
        if quotes:
            items = []
            for sym in symbols:
                data = quotes.get(sym)
                if not data:
                    continue
                name = names.get(sym, sym)
                price = data.get("price", 0)
                change = data.get("change_pct", 0)
                emoji = "📈" if change >= 0 else "📉"
                if price > 1000:
                    items.append(f"{emoji} {name}: {price:,.0f} ({change:+.2f}%)")
                else:
                    items.append(f"{emoji} {name}: ${price:,.2f} ({change:+.2f}%)")
            if items:
                sections.append(_section("💹 市场行情", items))
    except Exception as e:
        logger.debug("[DailyBrief] quotes: %s", e)


async def _brief_sentiment(sections: list) -> None:
    """section 6: 恐惧贪婪指数"""
    try:
        from src.invest_tools import get_fear_greed_index

        fng = await get_fear_greed_index()
        if fng and fng.get("source") != "fallback":
            value = fng.get("value", 0)
            label = fng.get("label", "")
            gauge = "🟢" if value > 60 else "🟡" if value > 40 else "🔴"
            sections.append(_section("🧭 市场情绪", [f"{gauge} 恐惧贪婪指数: {value} ({label})"]))
    except Exception as e:
        logger.debug("[DailyBrief] fng: %s", e)


async def _brief_news(sections: list) -> None:
    """section 7: 科技/AI 新闻 (LLM 深度分析 + 持仓关联)"""
    try:
        from src.news_fetcher import NewsFetcher

        nf = NewsFetcher()
        ai_news = await nf.fetch_by_category("ai", count=3)
        tech_news = await nf.fetch_by_category("tech_cn", count=3)
        news_items = (ai_news or []) + (tech_news or [])
        if news_items:
            headlines = [item["title"] for item in news_items[:5]]
            # 收集用户持仓 symbols，用于关联分析
            holdings = []
            try:
                from src.position_monitor import position_monitor as _pm

                if _pm and _pm.positions:
                    holdings = list(_pm.positions.keys())
            except Exception as e:
                logger.debug("新闻-持仓关联获取异常: %s", e)

            # 延迟导入 LLM 分析函数
            from src.execution.daily_brief_llm import _analyze_news_with_llm

            # 尝试用 LLM 生成深度分析
            analyzed = await _analyze_news_with_llm(headlines, holdings)
            if analyzed:
                sections.append(_section("📰 科技快讯 (AI解读)", analyzed))
            else:
                # 降级: LLM 失败则回退到纯标题列表
                items = [f"• {t}" for t in headlines]
                sections.append(_section("📰 科技快讯", items))
    except Exception as e:
        logger.debug("[DailyBrief] news: %s", e)


async def _brief_social_ops(sections: list) -> None:
    """section 8: 社媒运营状态"""
    _fallback = _section("📱 社媒运营", ["自动驾驶未启动", "💡 说「社媒计划」开始自动发文"])
    try:
        from src.social_scheduler import social_autopilot

        if social_autopilot:
            status = social_autopilot.status()
            if status:
                items = []
                running = "运行中" if status.get("running") else "已停止"
                items.append(f"自动驾驶: {running}")
                if status.get("posts_today", 0) > 0:
                    items.append(f"今日已发: {status['posts_today']} 篇")
                if status.get("draft_count", 0) > 0:
                    items.append(f"待发草稿: {status['draft_count']} 条")
                next_action = status.get("next_action", "")
                if next_action:
                    next_time = status.get("next_time", "")
                    items.append(f"下一动作: {next_action} ({next_time})")
                sections.append(_section("📱 社媒运营", items))
            else:
                sections.append(_fallback)
        else:
            sections.append(_fallback)
    except Exception as e:
        logger.debug("[DailyBrief] social: %s", e)
        sections.append(_fallback)


async def _brief_ops_status(sections: list, *, monitors=None, db_path=None) -> None:
    """section 9: 监控 + 草稿运维状态"""
    aux_items = []
    try:
        if monitors:
            aux_items.append(f"👁 活跃监控: {len(monitors)} 个")
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM social_drafts WHERE status='draft'")
            count = cursor.fetchone()[0]
            if count:
                aux_items.append(f"✏️ 待发布草稿: {count} 条")
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)
    if aux_items:
        sections.append(_section("🔧 运维状态", aux_items))


async def _brief_api_cost(sections: list) -> None:
    """section 10: API 成本"""
    try:
        from src.monitoring import cost_analyzer

        if cost_analyzer:
            prediction = cost_analyzer.predict_monthly_cost()
            if prediction:
                daily_avg = prediction.get("daily_average", 0)
                monthly = prediction.get("monthly_prediction", 0)
                if daily_avg > 0:
                    sections.append(
                        _section(
                            "💰 API 成本",
                            [
                                f"日均: ${daily_avg:.2f} | 月预估: ${monthly:.2f}",
                            ],
                        )
                    )
    except Exception as e:
        logger.debug("[DailyBrief] cost: %s", e)


async def _brief_xianyu(sections: list) -> None:
    """section 11: 闲鱼运营"""
    _fallback = _section("🐟 闲鱼运营", ["暂无闲鱼数据", "💡 说「闲鱼」查看闲鱼客服状态"])
    try:
        from src.xianyu.xianyu_context import XianyuContextManager

        xctx = XianyuContextManager()
        xstats = xctx.daily_stats() if hasattr(xctx, "daily_stats") else {}
        if xstats:
            xlines = []
            if xstats.get("messages", 0) > 0:
                xlines.append(f"💬 咨询 {xstats.get('messages', 0)} 条")
            if xstats.get("orders", 0) > 0:
                xlines.append(f"📦 下单 {xstats.get('orders', 0)} 笔")
            if xstats.get("payments", 0) > 0:
                xlines.append(f"💰 成交 {xstats.get('payments', 0)} 笔")
            if xstats.get("conversion_rate"):
                xlines.append(f"📈 转化率 {xstats['conversion_rate']}")
            # 营收+利润数据
            try:
                profit = xctx.get_profit_summary(days=1) if hasattr(xctx, "get_profit_summary") else {}
                if profit and profit.get("revenue", 0) > 0:
                    xlines.append(f"💵 营收 ¥{profit['revenue']:.0f} | 利润 ¥{profit['profit']:.0f}")
                    if profit.get("orders", 0) > 0:
                        avg = profit["revenue"] / profit["orders"]
                        xlines.append(f"📊 客单价 ¥{avg:.0f}")
            except Exception as e:
                logger.warning("闲鱼利润数据获取失败: %s", e)
            if xlines:
                sections.append(_section("🐟 闲鱼运营", xlines))
            else:
                sections.append(_fallback)
            # 今日热销 Top3
            try:
                top3 = xctx.get_item_rankings(days=1, limit=3)
                if top3:
                    top_lines = ["🏆 今日热销:"]
                    for i, item in enumerate(top3, 1):
                        title = item.get("title", "未知")[:10]
                        consult = item.get("consultations", 0)
                        convert = item.get("conversions", 0)
                        top_lines.append(f"  {i}. {title} ({consult}咨询/{convert}成交)")
                    sections.append(_section("🏆 闲鱼热销", top_lines))
            except Exception as e:
                logger.debug("闲鱼热销获取异常: %s", e)
        else:
            sections.append(_fallback)
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)
        sections.append(_fallback)


async def _brief_engagement(sections: list, *, db_path=None) -> None:
    """section 12: 社媒互动"""
    try:
        from src.execution.life_automation import get_engagement_summary

        eng = get_engagement_summary(days=7)
        if eng.get("success") and eng.get("total_posts", 0) > 0:
            elines = [f"📊 近7天 {eng['total_posts']} 篇帖子"]
            for plat, data in eng.get("platforms", {}).items():
                elines.append(f"  {plat}: ❤️{data['likes']} 💬{data['comments']} 👀{data['views']}")
            sections.append(_section("📱 社媒互动", elines))
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)


async def _brief_followers(sections: list) -> None:
    """section 12.5: 粉丝增长"""
    try:
        from src.execution.life_automation import get_follower_growth

        growth = get_follower_growth(days=1)
        if growth:
            _plat_names = {"x": "X", "xhs": "小红书"}
            parts = []
            for plat, data in growth.items():
                name = _plat_names.get(plat, plat)
                end = data.get("end", 0)
                change = data.get("change", 0)
                sign = "+" if change >= 0 else ""
                parts.append(f"{name} {end:,}({sign}{change})")
            if parts:
                sections.append(_section("👥 粉丝", [" | ".join(parts)]))
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)


async def _brief_trending(sections: list) -> None:
    """section 13: 项目发现 (GitHub Trending)"""
    try:
        trending_items = await _fetch_trending_projects()
        if trending_items:
            sections.append(_section("🔭 项目发现", trending_items))
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)


async def _collect_brief_metrics(*, db_path=None) -> dict:
    """收集各模块关键指标，用于执行摘要 + 智能建议。

    Returns:
        包含 portfolio_pnl, positions_count, xianyu_*, social_posts,
        api_daily_cost, market_sentiment, deltas 等键的字典
    """
    sections_data: dict = {}
    try:
        # 持仓盈亏
        try:
            from src.position_monitor import position_monitor as _pm_ref

            if _pm_ref and _pm_ref.positions:
                _st = _pm_ref.get_status()
                sections_data["portfolio_pnl"] = _st.get("total_unrealized_pnl", 0)
                sections_data["positions_count"] = _st.get("monitored_count", 0)
        except Exception as e:
            logger.debug("日报指标收集-持仓盈亏异常: %s", e)

        # 闲鱼数据
        try:
            from src.xianyu.xianyu_context import XianyuContextManager

            _xctx = XianyuContextManager()
            _xst = _xctx.daily_stats() if hasattr(_xctx, "daily_stats") else {}
            if _xst:
                sections_data["xianyu_consultations"] = _xst.get("consultations", 0)
                sections_data["xianyu_orders"] = _xst.get("orders", 0)
        except Exception as e:
            logger.debug("日报指标收集-闲鱼数据异常: %s", e)

        # 社媒发帖
        try:
            from src.execution.life_automation import get_engagement_summary

            _eng = get_engagement_summary(days=1, db_path=db_path)
            if _eng.get("success"):
                sections_data["social_posts"] = _eng.get("total_posts", 0)
        except Exception as e:
            logger.debug("日报指标收集-社媒发帖异常: %s", e)

        # API 成本
        try:
            from src.monitoring import cost_analyzer as _ca_ref

            if _ca_ref:
                _pred = _ca_ref.predict_monthly_cost()
                if _pred:
                    sections_data["api_daily_cost"] = _pred.get("daily_average", 0)
        except Exception as e:
            logger.debug("日报指标收集-API成本异常: %s", e)

        # 市场情绪
        try:
            from src.invest_tools import get_fear_greed_index

            _fng = await get_fear_greed_index()
            if _fng and _fng.get("source") != "fallback":
                sections_data["market_sentiment"] = f"{_fng.get('value', 0)} ({_fng.get('label', '')})"
        except Exception as e:
            logger.debug("日报指标收集-市场情绪异常: %s", e)
    except Exception as e:
        logger.debug("[DailyBrief] 指标收集总异常: %s", e)

    # 昨日对比 + delta 计算
    try:
        yesterday_data = await _get_yesterday_comparison(db_path=db_path)
        deltas = _calc_deltas(sections_data, yesterday_data)
        sections_data["deltas"] = deltas
    except Exception as e:
        logger.debug("[DailyBrief] 昨日对比: %s", e)
        sections_data["deltas"] = {}

    return sections_data


# ── 天气数据采集 ──────────────────────────────────────────

# 天气状况 → emoji 映射
_WEATHER_EMOJI = {
    "晴": "☀️",
    "晴天": "☀️",
    "多云": "⛅",
    "阴天": "☁️",
    "小雨": "🌦",
    "中雨": "🌧",
    "大雨": "🌧",
    "暴雨": "⛈",
    "雷阵雨": "⛈",
    "小雪": "🌨",
    "中雪": "❄️",
    "大雪": "❄️",
    "暴风雪": "❄️",
    "薄雾": "🌫",
    "大雾": "🌫",
    "雨夹雪": "🌨",
}


def _weather_emoji(desc: str) -> str:
    """根据天气描述返回对应 emoji"""
    for keyword, emoji in _WEATHER_EMOJI.items():
        if keyword in desc:
            return emoji
    return "🌤"


async def _fetch_weather(city: str = "") -> str:
    """获取天气数据，格式化为日报单行文本。

    城市优先级: 参数 > 环境变量 WEATHER_CITY > 默认 Shanghai
    失败时返回空字符串（不阻塞日报生成）。

    Returns:
        格式化文本如 "上海 ☀️ 25°C 湿度60% 风速12km/h"，失败返回 ""
    """
    if not city:
        city = os.environ.get("WEATHER_CITY", "Shanghai")
    try:
        from src.tools.free_apis import get_weather

        data = await get_weather(city)
        if data.get("source") == "error":
            return ""

        cur = data.get("current", {})
        temp = cur.get("temp", "")
        weather_desc = cur.get("weather", "")
        humidity = cur.get("humidity", "")
        emoji = _weather_emoji(weather_desc)

        # 组装文本：城市 emoji 温度 天气 湿度
        parts = [f"{city} {emoji} {temp}°C"]
        if weather_desc:
            parts[0] += f" {weather_desc}"
        if humidity:
            parts.append(f"湿度{humidity}%")

        # 追加今日温度范围（如果有预报数据）
        forecasts = data.get("forecasts", [])
        if forecasts:
            today_fc = forecasts[0]
            low = today_fc.get("nighttemp", "")
            high = today_fc.get("daytemp", "")
            if low and high:
                parts.append(f"{low}~{high}°C")

        return " | ".join(parts)
    except Exception as e:
        logger.debug("[DailyBrief] 天气数据获取失败: %s", e)
        return ""


# ── 汇率数据采集 ──────────────────────────────────────────


async def _fetch_forex() -> str:
    """获取 USD/CNY 汇率，格式化为日报单行文本。

    优先使用已有的 free_apis.get_exchange_rate（免费无 key），
    失败时返回空字符串（不阻塞日报生成）。

    Returns:
        格式化文本如 "USD/CNY 7.2345"，失败返回 ""
    """
    try:
        from src.tools.free_apis import get_exchange_rate

        data = await get_exchange_rate("USD", "CNY")
        rate = data.get("rate", 0)
        if not rate or rate == 0:
            return ""

        return f"USD/CNY {rate:.4f}"
    except Exception as e:
        logger.debug("[DailyBrief] 汇率数据获取失败: %s", e)
        return ""
