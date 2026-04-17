"""
综合周报 — 每周日推送的 7 天数据汇总

聚合投资+社媒+闲鱼+成本的周度表现。
由 scheduler 每周日 20:30 自动触发，也可通过 /weekly 手动触发。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from src.notify_style import format_digest, kv, bullet
from src.execution.daily_brief_data import _section, _get_timestamp_tag

logger = logging.getLogger(__name__)


async def weekly_report() -> str:
    """生成综合周报 — 聚合 7 天数据

    内容架构:
      1. 📱 社媒周报 (发文绩效 + 自动驾驶 + 粉丝增长)
      2. 🐟 闲鱼周报 (营收/利润/成交/咨询/转化)
      3. 💰 成本周报 (API 日均/周均/月预估)
      4. 🎯 目标进度 (交易目标达成情况)

    所有数据源独立 try/except，一个失败不影响其他。
    """
    sections: List[Tuple[str, List[str]]] = []

    # 计算本周起止日期
    now = datetime.now(timezone.utc)
    week_end = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    # ── 1. 📱 社媒周报 ──────────────────────────────────────
    try:
        items = []
        # 发文绩效报告
        try:
            # 修复: content_pipeline 实际位于 src/execution/social/ 目录下
            from src.execution.social.content_pipeline import content_pipeline

            if content_pipeline and hasattr(content_pipeline, "get_post_performance_report"):
                post_report = content_pipeline.get_post_performance_report(days=7)
                if post_report:
                    if post_report.get("best_post"):
                        bp = post_report["best_post"]
                        items.append(
                            bullet(
                                f"最佳帖子: {bp.get('title', '无标题')[:30]} ({bp.get('engagement', 0)} 互动)",
                                icon="⭐",
                            )
                        )
                    if post_report.get("follower_change") is not None:
                        fc = post_report["follower_change"]
                        fc_emoji = "📈" if fc >= 0 else "📉"
                        items.append(kv("粉丝变化", f"{fc_emoji} {fc:+d}"))
        except Exception as e:
            logger.debug("静默异常: %s", e)

        # 社交自动驾驶状态
        try:
            from src.social_scheduler import social_autopilot

            if social_autopilot and hasattr(social_autopilot, "status"):
                s = social_autopilot.status()
                if s and s.get("posts_today", 0) > 0:
                    items.append(kv("自动驾驶", "运行中" if s.get("running") else "已停止"))
        except Exception as e:
            logger.debug("静默异常: %s", e)

        # 粉丝增长趋势 (7天)
        try:
            from src.execution.life_automation import get_follower_growth

            growth = get_follower_growth(days=7)
            if growth:
                _plat_names = {"x": "X", "xhs": "小红书"}
                for plat, data in growth.items():
                    name = _plat_names.get(plat, plat)
                    change = data.get("change", 0)
                    pct = data.get("change_pct", 0)
                    fc_emoji = "📈" if change >= 0 else "📉"
                    items.append(kv(f"{name} 粉丝", f"{fc_emoji} {data.get('end', 0):,} ({change:+d}, {pct:+.1f}%)"))
        except Exception as e:
            logger.debug("静默异常: %s", e)

        if items:
            sections.append(_section("📱 社媒周报", items))
    except Exception as e:
        logger.debug("[WeeklyReport] 社媒: %s", e)

    # ── 2. 🐟 闲鱼周报 ──────────────────────────────────────
    try:
        xctx = None
        try:
            from src.xianyu.xianyu_context import XianyuContextManager

            xctx = XianyuContextManager()
        except ImportError:
            pass

        if xctx:
            items = []
            # 尝试获取利润汇总（7天）
            profit = {}
            if hasattr(xctx, "get_profit_summary"):
                try:
                    profit = xctx.get_profit_summary(days=7) or {}
                except Exception as e:
                    logger.debug("静默异常: %s", e)
            # 尝试获取日统计（聚合7天）
            xstats = {}
            if hasattr(xctx, "daily_stats"):
                try:
                    xstats = xctx.daily_stats() or {}
                except Exception as e:
                    logger.debug("静默异常: %s", e)
            if profit.get("revenue", 0) > 0:
                items.append(kv("营收", f"¥{profit['revenue']:,.0f}"))
                items.append(kv("利润", f"¥{profit.get('profit', 0):,.0f}"))
                if profit.get("orders", 0) > 0:
                    avg = profit["revenue"] / profit["orders"]
                    items.append(kv("成交", f"{profit['orders']} 单 | 客单价 ¥{avg:.0f}"))
            if xstats.get("messages", 0) > 0:
                items.append(kv("咨询", f"{xstats['messages']} 条"))
            if xstats.get("conversion_rate"):
                items.append(kv("转化率", f"{xstats['conversion_rate']}"))
            if items:
                sections.append(_section("🐟 闲鱼周报", items))
    except Exception as e:
        logger.debug("[WeeklyReport] 闲鱼: %s", e)

    # ── 3. 💰 成本周报 ──────────────────────────────────────
    try:
        ca = None
        try:
            from src.monitoring import cost_analyzer

            ca = cost_analyzer
        except ImportError:
            pass

        if ca:
            items = []
            # 使用 predict_monthly_cost 获取日均成本
            prediction = ca.predict_monthly_cost() if hasattr(ca, "predict_monthly_cost") else {}
            if prediction:
                daily_avg = prediction.get("daily_average", 0)
                monthly = prediction.get("monthly_prediction", 0)
                if daily_avg > 0:
                    weekly_est = daily_avg * 7
                    items.append(kv("本周估算", f"${weekly_est:.2f}"))
                    items.append(kv("日均成本", f"${daily_avg:.2f}"))
                    items.append(kv("月度预估", f"${monthly:.2f}"))
            # 如果有专门的周报方法则优先使用
            if hasattr(ca, "get_weekly_report"):
                try:
                    wr = ca.get_weekly_report()
                    if wr:
                        if wr.get("this_week") is not None:
                            items = [kv("本周成本", f"${wr['this_week']:.2f}")]
                        if wr.get("last_week") is not None:
                            change = wr["this_week"] - wr["last_week"]
                            ch_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                            items.append(kv("环比变化", f"{ch_emoji} ${change:+,.2f}"))
                        if wr.get("daily_average") is not None:
                            items.append(kv("日均", f"${wr['daily_average']:.2f}"))
                except Exception as e:
                    logger.debug("静默异常: %s", e)
            if items:
                sections.append(_section("💰 成本周报", items))
    except Exception as e:
        logger.debug("[WeeklyReport] 成本: %s", e)

    # ── 4. 🎯 目标进度 ──────────────────────────────────────
    try:
        tj = None
        try:
            from src.trading_journal import journal

            tj = journal
        except ImportError:
            pass

        if tj and hasattr(tj, "format_target_progress"):
            progress_text = tj.format_target_progress()
            if progress_text and len(progress_text.strip()) > 5:
                # 将文本拆成行作为 items
                items = [line.strip() for line in progress_text.strip().split("\n") if line.strip()]
                if items:
                    sections.append(_section("🎯 目标进度", items))
        elif tj and hasattr(tj, "get_active_targets"):
            targets = tj.get_active_targets()
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
        logger.debug("[WeeklyReport] 目标进度: %s", e)

    # ── 组装最终周报 ─────────────────────────────────────────
    if not sections:
        sections.append(_section("📋 本周概况", ["暂无数据，所有数据源均不可用"]))

    return format_digest(
        title="📋 综合周报",
        intro=f"📅 {week_start} — {week_end}",
        sections=sections,
        footer=f"💡 说「周报」随时查看 | ⏱ {_get_timestamp_tag()}",
    )
