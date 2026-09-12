"""
综合周报 — 每周日推送的 7 天数据汇总

聚合投资、社媒和成本的周度表现。
由 scheduler 每周日 20:30 自动触发，也可通过 /weekly 手动触发。
"""

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from src.execution.daily_brief_data import _get_timestamp_tag, _report_cost_lines, _report_cost_snapshot, _section
from src.notify_style import bullet, format_digest, kv

logger = logging.getLogger(__name__)


async def weekly_report(*, planned_at=None) -> str:
    """生成综合周报 — 聚合 7 天数据

    内容架构:
      1. 📱 社媒周报 (发文绩效 + 自动驾驶 + 粉丝增长)
      2. 💰 成本周报 (账本已知费用、完整性及覆盖范围)
      3. 🎯 目标进度 (交易目标达成情况)

    所有数据源独立 try/except，一个失败不影响其他。
    """
    sections: list[tuple[str, list[str]]] = []

    # 计算本周起止日期
    now = (planned_at or datetime.now(UTC)).astimezone(ZoneInfo('America/New_York'))
    week_end = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=6)).strftime("%Y-%m-%d")

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

    # ET calendar window ends on the planned report date; values are as of generation.
    cost = _report_cost_snapshot(planned_at=planned_at, days=7)
    sections.append(_section('💰 成本周报', _report_cost_lines(cost)))

    # ── 4. 🎯 目标进度 ──────────────────────────────────────
    try:
        tj = None
        try:
            from src.trading_journal import journal

            tj = journal
        except ImportError:
            pass  # 合理保留：可选依赖缺失时继续走后续降级链

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
