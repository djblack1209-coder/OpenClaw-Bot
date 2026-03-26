"""
Execution Hub — 每日智能日报 v3.0 (Smart Daily Digest)
用户打开 Telegram 就知道一切 — 持仓/交易/市场/社媒/成本 全覆盖

v3.0 变更 (2026-03-24):
  - 从 6 段扩展到 10 段: 新增持仓概览、交易绩效、目标进度、AI 信号准确率
  - 使用 format_digest(sections=...) 替代 paragraphs — 结构化分节
  - 接入 trading_journal / position_monitor / cost_analyzer / social_autopilot
  - 所有数据源独立 try/except + 降级提示 — 不再静默丢失

设计原则:
  - 用户不需要主动查看任何东西 — 早上打开一条消息就够了
  - 每个 section 独立获取，一个失败不影响其他
  - 数据存在才展示，没有假数据填充
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Sequence

from src.execution._db import get_conn
from src.notify_style import format_digest, kv, bullet, divider

logger = logging.getLogger(__name__)


def _section(title: str, items: List[str]) -> Tuple[str, List[str]]:
    """构建一个 section tuple (title, items) for format_digest"""
    return (title, items)


async def generate_daily_brief(monitors=None, db_path=None) -> str:
    """生成智能每日日报 — 10 个数据源自动聚合

    内容架构:
    1. 持仓概览 (position_monitor)
    2. 昨日交易绩效 (trading_journal)
    3. 目标进度 (profit targets)
    4. 待办事项 (task_mgmt)
    5. 市场行情 (invest_tools)
    6. 恐惧贪婪指数 (invest_tools)
    7. 科技/AI 新闻 (news_fetcher RSS)
    8. 社媒运营状态 (social_autopilot)
    9. 活跃监控 + 社媒草稿 (monitors + DB)
    10. API 成本 (cost_analyzer)
    """
    sections: List[Tuple[str, List[str]]] = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    greeting = _get_greeting()

    # ── 1. 持仓概览 ──────────────────────────────────────────
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
    except Exception as e:
        logger.debug(f"[DailyBrief] positions: {e}")

    # ── 2. 交易绩效 ──────────────────────────────────────────
    try:
        from src.trading_journal import journal
        if journal:
            perf = journal.get_performance(days=7)
            if perf and perf.get("total_trades", 0) > 0:
                items = []
                items.append(f"7日战绩: {perf.get('total_trades', 0)} 笔 | "
                             f"胜率 {perf.get('win_rate', 0):.0f}%")
                items.append(f"累计盈亏: ${perf.get('total_pnl', 0):+,.2f}")
                if perf.get("sharpe"):
                    items.append(f"夏普比率: {perf['sharpe']:.2f} | "
                                 f"最大回撤: {perf.get('max_drawdown', 0):.1f}%")
                if perf.get("expectancy"):
                    items.append(f"期望值: ${perf['expectancy']:+.2f}/笔")
                sections.append(_section("📊 7日交易绩效", items))

            # 昨日 P&L
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
    except Exception as e:
        logger.debug(f"[DailyBrief] journal: {e}")

    # ── 3. 目标进度 ──────────────────────────────────────────
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
        logger.debug(f"[DailyBrief] targets: {e}")

    # ── 4. 待办事项 ──────────────────────────────────────────
    try:
        from src.execution.task_mgmt import top_tasks
        tasks = top_tasks(limit=5, db_path=db_path)
        if tasks:
            items = []
            for t in tasks:
                status_icon = {"done": "✅", "in_progress": "🔄"}.get(
                    t.get("status", ""), "⬜"
                )
                items.append(f"{status_icon} {t.get('title', '')}")
            sections.append(_section("📋 待办事项", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] tasks: {e}")

    # ── 4.5 今日提醒 ──────────────────────────────────────────
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
        logger.debug(f"[DailyBrief] reminders: {e}")

    # ── 4.8 关注股票隔夜变动 ──────────────────────────────────
    try:
        from src.invest_tools import get_quick_quotes

        # 从持仓和关注列表获取用户关注的股票
        watchlist_symbols = []
        try:
            if monitors:
                pm = monitors.get("position_monitor")
                if pm:
                    positions = pm.get_positions() if hasattr(pm, "get_positions") else []
                    for pos in (positions or []):
                        sym = pos.get("symbol", "")
                        if sym:
                            watchlist_symbols.append(sym)
        except Exception:
            pass

        # 补充 watchlist 中的股票
        try:
            from src.watchlist import get_watchlist_symbols
            wl = get_watchlist_symbols()
            for sym in (wl or []):
                if sym not in watchlist_symbols:
                    watchlist_symbols.append(sym)
        except Exception:
            pass

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
    except Exception as e:
        logger.debug(f"[DailyBrief] watchlist: {e}")

    # ── 5. 市场行情 (9 大指数) ────────────────────────────────
    try:
        from src.invest_tools import get_quick_quotes
        symbols = ["^GSPC", "^IXIC", "^DJI", "^HSI", "000001.SS", "BTC-USD", "ETH-USD", "GC=F", "CL=F"]
        names = {
            "^GSPC": "S&P 500", "^IXIC": "纳斯达克", "^DJI": "道琼斯",
            "^HSI": "恒生", "000001.SS": "上证",
            "BTC-USD": "BTC", "ETH-USD": "ETH",
            "GC=F": "黄金", "CL=F": "原油",
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
        logger.debug(f"[DailyBrief] quotes: {e}")

    # ── 6. 恐惧贪婪指数 ──────────────────────────────────────
    try:
        from src.invest_tools import get_fear_greed_index
        fng = await get_fear_greed_index()
        if fng and fng.get("source") != "fallback":
            value = fng.get("value", 0)
            label = fng.get("label", "")
            gauge = "🟢" if value > 60 else "🟡" if value > 40 else "🔴"
            sections.append(_section("🧭 市场情绪", [
                f"{gauge} 恐惧贪婪指数: {value} ({label})"
            ]))
    except Exception as e:
        logger.debug(f"[DailyBrief] fng: {e}")

    # ── 7. 科技/AI 新闻 ──────────────────────────────────────
    try:
        from src.news_fetcher import NewsFetcher
        nf = NewsFetcher()
        ai_news = await nf.fetch_by_category("ai", count=3)
        tech_news = await nf.fetch_by_category("tech_cn", count=3)
        news_items = (ai_news or []) + (tech_news or [])
        if news_items:
            items = [f"• {item['title']}" for item in news_items[:5]]
            sections.append(_section("📰 科技快讯", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] news: {e}")

    # ── 8. 社媒运营状态 ──────────────────────────────────────
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
    except Exception as e:
        logger.debug(f"[DailyBrief] social: {e}")

    # ── 9. 监控 + 草稿 ──────────────────────────────────────
    aux_items = []
    try:
        if monitors:
            aux_items.append(f"👁 活跃监控: {len(monitors)} 个")
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM social_drafts WHERE status='draft'"
            )
            count = cursor.fetchone()[0]
            if count:
                aux_items.append(f"✏️ 待发布草稿: {count} 条")
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)
    if aux_items:
        sections.append(_section("🔧 运维状态", aux_items))

    # ── 10. API 成本 ─────────────────────────────────────────
    try:
        from src.monitoring import cost_analyzer
        if cost_analyzer:
            prediction = cost_analyzer.predict_monthly_cost()
            if prediction:
                daily_avg = prediction.get("daily_average", 0)
                monthly = prediction.get("monthly_prediction", 0)
                if daily_avg > 0:
                    sections.append(_section("💰 API 成本", [
                        f"日均: ${daily_avg:.2f} | 月预估: ${monthly:.2f}",
                    ]))
    except Exception as e:
        logger.debug(f"[DailyBrief] cost: {e}")

    # ── 11. 闲鱼运营 ─────────────────────────────────────────
    try:
        from src.xianyu.xianyu_context import XianyuContextManager
        xctx = XianyuContextManager()
        xstats = xctx.daily_stats() if hasattr(xctx, 'daily_stats') else {}
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
            # 营收+利润数据（搬运 Shopify Analytics 的日报模式）
            try:
                profit = xctx.get_profit_summary(days=1) if hasattr(xctx, 'get_profit_summary') else {}
                if profit and profit.get("revenue", 0) > 0:
                    xlines.append(f"💵 营收 ¥{profit['revenue']:.0f} | 利润 ¥{profit['profit']:.0f}")
                    if profit.get("orders", 0) > 0:
                        avg = profit["revenue"] / profit["orders"]
                        xlines.append(f"📊 客单价 ¥{avg:.0f}")
            except Exception:
                pass
            if xlines:
                sections.append(_section("🐟 闲鱼运营", xlines))
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)

    # ── 12. 社媒互动 ─────────────────────────────────────────
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

    # ── 13. 项目发现 (GitHub Trending) ─────────────────────────
    try:
        trending_items = await _fetch_trending_projects()
        if trending_items:
            sections.append(_section("🔭 项目发现", trending_items))
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)

    # ── 组装最终日报 ─────────────────────────────────────────
    if not sections:
        sections.append(_section("📋 今日概况", ["暂无数据，所有数据源均不可用"]))

    return format_digest(
        title=f"{greeting} | 智能日报",
        intro=f"📅 {today}",
        sections=sections,
        footer="💡 说「帮我买100股苹果」直接交易 | 说「帮我找便宜的AirPods」自动比价",
    )


def _get_greeting() -> str:
    """根据时间返回问候语"""
    hour = datetime.now(timezone.utc).hour
    if hour < 6:
        return "🌙 深夜好"
    elif hour < 12:
        return "☀️ 早上好"
    elif hour < 18:
        return "🌤 下午好"
    else:
        return "🌙 晚上好"


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
