"""
Execution Hub — 每日简报 v2.0
场景2: 汇总待办、社媒、监控、新闻、行情信息生成每日简报

v2.0 变更 (2026-03-23):
  - 接入 news_fetcher RSS 源 — AI/科技/金融新闻自动聚合
  - 接入 invest_tools 行情摘要 — S&P 500 / 纳指 / BTC 快照
  - 简报内容从 3 段扩展到 6 段
"""
import logging
from src.execution._db import get_conn
from src.notify_style import format_announcement

logger = logging.getLogger(__name__)


async def generate_daily_brief(monitors=None, db_path=None) -> str:
    """生成每日简报，汇总待办、社媒、监控、新闻、行情"""
    paragraphs = []

    # 1. 待办事项
    try:
        from src.execution.task_mgmt import top_tasks
        tasks = top_tasks(limit=5, db_path=db_path)
        if tasks:
            task_lines = [
                f"- [{t.get('status','pending')}] {t.get('title','')}"
                for t in tasks
            ]
            paragraphs.append("📋 待办事项:\n" + "\n".join(task_lines))
    except Exception as e:
        logger.debug(f"[DailyBrief] tasks error: {e}")

    # 2. 社媒草稿
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM social_drafts WHERE status='draft'"
            )
            count = cursor.fetchone()[0]
            if count:
                paragraphs.append(f"📱 待发布社媒草稿: {count} 条")
    except Exception as e:
        logger.debug(f"[DailyBrief] social drafts error: {e}")

    # 3. 活跃监控
    try:
        if monitors:
            paragraphs.append(f"👁 活跃监控: {len(monitors)} 个")
    except Exception as e:
        logger.debug(f"[DailyBrief] monitors error: {e}")

    # 4. [NEW] 科技/AI 新闻 (RSS)
    try:
        from src.news_fetcher import NewsFetcher
        nf = NewsFetcher()
        ai_news = await nf.fetch_by_category("ai", count=3)
        tech_news = await nf.fetch_by_category("tech_cn", count=3)
        news_items = ai_news + tech_news
        if news_items:
            lines = [f"• {item['title']}" for item in news_items[:5]]
            paragraphs.append("📰 科技快讯:\n" + "\n".join(lines))
    except Exception as e:
        logger.debug(f"[DailyBrief] news error: {e}")

    # 5. [NEW] 主要指数行情
    try:
        from src.invest_tools import get_quick_quotes
        quotes = await get_quick_quotes(["^GSPC", "^IXIC", "BTC-USD"])
        if quotes:
            lines = []
            for sym, data in quotes.items():
                name = {"^GSPC": "S&P 500", "^IXIC": "纳斯达克", "BTC-USD": "BTC"}.get(sym, sym)
                price = data.get("price", 0)
                change = data.get("change_pct", 0)
                emoji = "📈" if change >= 0 else "📉"
                lines.append(f"{emoji} {name}: ${price:,.2f} ({change:+.2f}%)")
            paragraphs.append("💹 主要指数:\n" + "\n".join(lines))
    except Exception as e:
        logger.debug(f"[DailyBrief] quotes error: {e}")

    # 6. [NEW] 恐惧贪婪指数
    try:
        from src.invest_tools import get_fear_greed_index
        fng = await get_fear_greed_index()
        if fng and fng.get("source") != "fallback":
            paragraphs.append(fng["telegram_text"])
    except Exception as e:
        logger.debug(f"[DailyBrief] fng error: {e}")

    if not paragraphs:
        paragraphs.append("今日暂无待处理事项")
    return format_announcement(title="每日简报", paragraphs=paragraphs)
