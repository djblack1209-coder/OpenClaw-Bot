"""
每日智能日报 v4.0 — 编排器 (HI-358 拆分后)

子模块: daily_brief_llm / daily_brief_data / weekly_report
每个 section 独立获取，一个失败不影响其他。
"""

import logging
from datetime import datetime, timezone
from typing import List, Tuple

from src.execution._db import get_conn
from src.notify_style import format_digest

# ── 从子模块导入 ──────────────────────────────────────────────
from src.execution.daily_brief_data import (  # noqa: F401
    _section,
    _get_timestamp_tag,
    _get_yesterday_comparison,
    _calc_deltas,
    _format_delta,
    _build_today_agenda,
    _fetch_trending_projects,
    _fetch_weather,
    _fetch_forex,
)
from src.execution.daily_brief_llm import (  # noqa: F401
    _analyze_news_with_llm,
    _generate_executive_summary,
    _generate_daily_recommendations,
)

# 向后兼容: scheduler.py / cmd_analysis_mixin.py 从本模块导入 weekly_report
from src.execution.weekly_report import weekly_report  # noqa: F401

logger = logging.getLogger(__name__)


async def generate_daily_brief(monitors=None, db_path=None) -> str:
    """生成智能每日日报 — 13+ 数据源自动聚合 + LLM 执行摘要 + 智能建议 + 昨日对比"""
    sections: List[Tuple[str, List[str]]] = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # ── 0. 今日日程 (所有源按紧急度排序，日报最前面) ──────────
    try:
        agenda_items = await _build_today_agenda(db_path=db_path)
        if agenda_items:
            sections.append(_section("📋 今日日程", agenda_items))
    except Exception as e:
        logger.debug(f"[DailyBrief] agenda: {e}")
    # ── 0.5 天气 + 汇率（快速参考信息，放在日报前部）──────────
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
        logger.debug(f"[DailyBrief] 天气/汇率: {e}")
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
        else:
            # 持仓数据为空，显示引导占位
            sections.append(_section("💼 持仓概览", ["暂无持仓数据", "💡 说「帮我投资 AAPL」开始你的第一笔交易"]))
    except Exception as e:
        logger.debug(f"[DailyBrief] positions: {e}")
        # 获取持仓数据异常，显示引导占位
        sections.append(_section("💼 持仓概览", ["暂无持仓数据", "💡 说「帮我投资 AAPL」开始你的第一笔交易"]))
    # ── 2. 交易绩效 ──────────────────────────────────────────
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
        else:
            # journal 模块未初始化，显示引导占位
            sections.append(_section("📊 交易绩效", ["暂无交易记录", "💡 说「自动交易」让AI帮你寻找机会"]))
    except Exception as e:
        logger.debug(f"[DailyBrief] journal: {e}")
        # 获取交易数据异常，显示引导占位
        sections.append(_section("📊 交易绩效", ["暂无交易记录", "💡 说「自动交易」让AI帮你寻找机会"]))
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
                status_icon = {"done": "✅", "in_progress": "🔄"}.get(t.get("status", ""), "⬜")
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
                    for pos in positions or []:
                        sym = pos.get("symbol", "")
                        if sym:
                            watchlist_symbols.append(sym)
        except Exception as e:
            logger.debug("静默异常: %s", e)

        # 补充 watchlist 中的股票
        try:
            from src.watchlist import get_watchlist_symbols

            wl = get_watchlist_symbols()
            for sym in wl or []:
                if sym not in watchlist_symbols:
                    watchlist_symbols.append(sym)
        except Exception as e:
            logger.debug("静默异常: %s", e)

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
        logger.debug(f"[DailyBrief] watchlist: {e}")
        # 获取关注股票数据异常，显示引导占位
        sections.append(_section("👀 关注股票", ["暂无自选股", "💡 说「关注 TSLA」添加你感兴趣的股票"]))
    # ── 5. 市场行情 (9 大指数) ────────────────────────────────
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
        logger.debug(f"[DailyBrief] quotes: {e}")
    # ── 6. 恐惧贪婪指数 ──────────────────────────────────────
    try:
        from src.invest_tools import get_fear_greed_index

        fng = await get_fear_greed_index()
        if fng and fng.get("source") != "fallback":
            value = fng.get("value", 0)
            label = fng.get("label", "")
            gauge = "🟢" if value > 60 else "🟡" if value > 40 else "🔴"
            sections.append(_section("🧭 市场情绪", [f"{gauge} 恐惧贪婪指数: {value} ({label})"]))
    except Exception as e:
        logger.debug(f"[DailyBrief] fng: {e}")
    # ── 7. 科技/AI 新闻 (LLM 深度分析 + 持仓关联) ──────────
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
                logger.debug("静默异常: %s", e)
            # 尝试用 LLM 生成深度分析
            analyzed = await _analyze_news_with_llm(headlines, holdings)
            if analyzed:
                sections.append(_section("📰 科技快讯 (AI解读)", analyzed))
            else:
                # 降级: LLM 失败则回退到纯标题列表
                items = [f"• {t}" for t in headlines]
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
            else:
                # status 为空，显示引导占位
                sections.append(_section("📱 社媒运营", ["自动驾驶未启动", "💡 说「社媒计划」开始自动发文"]))
        else:
            # social_autopilot 未初始化，显示引导占位
            sections.append(_section("📱 社媒运营", ["自动驾驶未启动", "💡 说「社媒计划」开始自动发文"]))
    except Exception as e:
        logger.debug(f"[DailyBrief] social: {e}")
        # 获取社媒数据异常，显示引导占位
        sections.append(_section("📱 社媒运营", ["自动驾驶未启动", "💡 说「社媒计划」开始自动发文"]))
    # ── 9. 监控 + 草稿 ──────────────────────────────────────
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
    # ── 10. API 成本 ─────────────────────────────────────────
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
        logger.debug(f"[DailyBrief] cost: {e}")
    # ── 11. 闲鱼运营 ─────────────────────────────────────────
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
            # 营收+利润数据（搬运 Shopify Analytics 的日报模式）
            try:
                profit = xctx.get_profit_summary(days=1) if hasattr(xctx, "get_profit_summary") else {}
                if profit and profit.get("revenue", 0) > 0:
                    xlines.append(f"💵 营收 ¥{profit['revenue']:.0f} | 利润 ¥{profit['profit']:.0f}")
                    if profit.get("orders", 0) > 0:
                        avg = profit["revenue"] / profit["orders"]
                        xlines.append(f"📊 客单价 ¥{avg:.0f}")
            except Exception as e:
                logger.debug("静默异常: %s", e)
            if xlines:
                sections.append(_section("🐟 闲鱼运营", xlines))
            else:
                # xstats 存在但所有指标都为0，显示引导占位
                sections.append(_section("🐟 闲鱼运营", ["暂无闲鱼数据", "💡 说「闲鱼」查看闲鱼客服状态"]))
            # 今日热销 Top3 — 调用 BI 商品排行接口
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
                logger.debug("静默异常: %s", e)
        else:
            # 无闲鱼数据，显示引导占位
            sections.append(_section("🐟 闲鱼运营", ["暂无闲鱼数据", "💡 说「闲鱼」查看闲鱼客服状态"]))
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)
        # 获取闲鱼数据异常，显示引导占位
        sections.append(_section("🐟 闲鱼运营", ["暂无闲鱼数据", "💡 说「闲鱼」查看闲鱼客服状态"]))
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
    # ── 12.5 粉丝增长 ─────────────────────────────────────────
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
    # ── 13. 项目发现 (GitHub Trending) ─────────────────────────
    try:
        trending_items = await _fetch_trending_projects()
        if trending_items:
            sections.append(_section("🔭 项目发现", trending_items))
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)
    # ── 收集各模块关键指标，用于执行摘要 + 智能建议 ──────────
    sections_data = {}
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
            logger.debug("静默异常: %s", e)
    except Exception as e:
        logger.debug("[DailyBrief] 指标收集总异常: %s", e)
    # ── 获取昨日对比数据 + 计算 delta ────────────────────────
    try:
        yesterday_data = await _get_yesterday_comparison(db_path=db_path)
        deltas = _calc_deltas(sections_data, yesterday_data)
        sections_data["deltas"] = deltas
    except Exception as e:
        logger.debug(f"[DailyBrief] 昨日对比: {e}")
        sections_data["deltas"] = {}
    # ── 生成执行摘要 (LLM / 模板降级) ────────────────────────
    try:
        summary_text = await _generate_executive_summary(sections_data)
        if summary_text:
            # 插入到最前面，让用户一眼看到全局态势
            sections.insert(0, _section("📊 今日概况", [summary_text]))
    except Exception as e:
        logger.debug(f"[DailyBrief] 执行摘要: {e}")
    # ── 生成智能建议 (LLM) ───────────────────────────────────
    try:
        recommendations = await _generate_daily_recommendations(sections_data)
        if recommendations:
            rec_items = [f"💡 {r}" for r in recommendations]
            sections.append(_section("💡 今日建议", rec_items))
    except Exception as e:
        logger.debug(f"[DailyBrief] 建议: {e}")
    # ── 组装最终日报 ─────────────────────────────────────────
    if not sections:
        sections.append(_section("📋 今日概况", ["暂无数据，所有数据源均不可用"]))

    return format_digest(
        title="📊 每日智能日报",
        intro=f"📅 {today}",
        sections=sections,
        footer=f"💡 说「日报」随时查看 | ⏱ {_get_timestamp_tag()}",
    )
