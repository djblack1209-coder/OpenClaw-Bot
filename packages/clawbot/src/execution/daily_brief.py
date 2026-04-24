"""
每日智能日报 v5.0 — 纯编排器 (R5-2 拆分: 542行→~80行)

所有 section 数据采集逻辑已下沉到 daily_brief_data.py 的 _brief_xxx() 子函数。
本模块只负责调用顺序编排 + 最终组装，不包含任何业务逻辑。

子模块: daily_brief_data / daily_brief_llm / weekly_report
"""

import logging
from datetime import UTC, datetime

# ── 从子模块导入 ──────────────────────────────────────────────
from src.execution.daily_brief_data import (  # noqa: F401
    # R5-2: section 子函数
    _brief_agenda,
    _brief_api_cost,
    _brief_engagement,
    _brief_followers,
    _brief_market,
    _brief_news,
    _brief_ops_status,
    _brief_positions,
    _brief_quick_ref,
    _brief_reminders,
    _brief_sentiment,
    _brief_social_ops,
    _brief_targets,
    _brief_todos,
    _brief_trading,
    _brief_trending,
    _brief_watchlist,
    _brief_xianyu,
    _build_today_agenda,
    _calc_deltas,
    _collect_brief_metrics,
    _fetch_forex,
    _fetch_trending_projects,
    _fetch_weather,
    _format_delta,
    _get_timestamp_tag,
    _get_yesterday_comparison,
    _section,
)
from src.execution.daily_brief_llm import (  # noqa: F401
    _analyze_news_with_llm,
    _generate_daily_recommendations,
    _generate_executive_summary,
)

# 向后兼容: scheduler.py / cmd_analysis_mixin.py 从本模块导入 weekly_report
from src.execution.weekly_report import weekly_report  # noqa: F401
from src.notify_style import format_digest

logger = logging.getLogger(__name__)


async def generate_daily_brief(monitors=None, db_path=None) -> str:
    """生成智能每日日报 — 纯编排器，每个 section 委托给 _brief_xxx() 子函数。

    流程: 采集 13+ 数据源 → 收集关键指标 → LLM 执行摘要 → 智能建议 → 组装输出
    """
    sections: list[tuple[str, list[str]]] = []
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # ── 价值位阶排序: 行动建议 > 异常检测 > 资产状况 > 运营数据 > 信息参考 ──

    # 第一层: 快速参考（天气/汇率 — 每天都有用）
    await _brief_quick_ref(sections)

    # 第二层: 资产状况（有数据才显示）
    await _brief_positions(sections)
    await _brief_trading(sections)
    await _brief_watchlist(sections, monitors=monitors)

    # 第三层: 市场（每天有数据）
    await _brief_market(sections)
    await _brief_sentiment(sections)

    # 第四层: 运营数据（社媒+闲鱼合并展示）
    social_sections: list[tuple[str, list[str]]] = []
    await _brief_social_ops(social_sections)
    await _brief_engagement(social_sections, db_path=db_path)
    await _brief_followers(social_sections)
    # 合并社媒数据为一个 section（避免碎片化）
    if social_sections:
        merged_items = []
        for _, items in social_sections:
            merged_items.extend(items)
        sections.append(_section("📱 社媒", merged_items))

    await _brief_xianyu(sections)

    # 第五层: 信息参考
    await _brief_news(sections)
    await _brief_trending(sections)

    # 第六层: 日程/待办/提醒（有才显示）
    await _brief_agenda(sections, db_path=db_path)
    await _brief_targets(sections)
    await _brief_todos(sections, db_path=db_path)
    await _brief_reminders(sections, db_path=db_path)

    # 第七层: 系统运维（运营者关注）
    await _brief_ops_status(sections, monitors=monitors, db_path=db_path)
    await _brief_api_cost(sections)

    # ── 收集关键指标 + 昨日对比（用于执行摘要和智能建议）──
    sections_data = await _collect_brief_metrics(db_path=db_path)

    # ── 生成执行摘要（LLM / 模板降级）──
    try:
        summary_text = await _generate_executive_summary(sections_data)
        if summary_text:
            # 插入到最前面，让用户一眼看到全局态势
            sections.insert(0, _section("📊 今日概况", [summary_text]))
    except Exception as e:
        logger.debug("[DailyBrief] 执行摘要: %s", e)

    # ── 生成智能建议（LLM）──
    try:
        recommendations = await _generate_daily_recommendations(sections_data)
        if recommendations:
            rec_items = [f"💡 {r}" for r in recommendations]
            sections.append(_section("💡 今日建议", rec_items))
    except Exception as e:
        logger.debug("[DailyBrief] 建议: %s", e)

    # ── 组装最终日报 ──
    if not sections:
        sections.append(_section("📋 今日概况", ["暂无数据，所有数据源均不可用"]))

    return format_digest(
        title="📊 每日智能日报",
        intro=f"📅 {today}",
        sections=sections,
        footer=f"💡 说「日报」随时查看 | ⏱ {_get_timestamp_tag()}",
    )
