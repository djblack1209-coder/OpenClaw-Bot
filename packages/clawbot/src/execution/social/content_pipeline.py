"""
Social — 内容管道引擎 (从 execution_hub.py 迁移)

包含:
- 热门内容自动发布 (autopost_hot_content / autopost_topic_content)
- 社交计划构建 (build_social_plan / build_social_repost_bundle)
- 话题研究 (research_social_topic)
- 内容创意生成 (generate_content_ideas / generate_content_calendar)
- 内容包创建 (create_topic_social_package / create_hot_social_package)
- 人设内容组合 (compose_human_x_post / compose_human_xhs_article)
- 首发草稿套件 (create_social_launch_drafts)
- 发布效果报告 (get_post_performance_report)

迁移自: execution_hub.py (反编译巨石) → HI-006/HI-008
"""
import logging
import re
from datetime import datetime, timedelta

from src.execution._ai import ai_pool
from src.execution._utils import extract_json_object
from src.utils import scrub_secrets

logger = logging.getLogger(__name__)


# ── 辅助: 标签/趋势/评分 ────────────────────────────────────

def social_topic_tags(topic: str = "") -> list[str]:
    """从话题推导标签"""
    topic = topic or ""
    tags: list[str] = []
    if "AI" in topic or "ai" in topic:
        tags.extend(["AI", "效率"])
    if "OpenClaw" in topic:
        tags.extend(["OpenClaw", "自动化"])
    if "出海" in topic:
        tags.extend(["出海", "独立开发"])
    return tags or ["AI", "工具"]


def creator_trend_label(topic: str = "", strategy: dict | None = None) -> str:
    """获取趋势标签"""
    strategy = strategy or {}
    trend_label = strategy.get("trend_label", "")
    return trend_label or "今日热点"


def source_title_lines(sources: list | None = None, limit: int = 1, max_len: int = 18) -> list[str]:
    """格式化来源标题"""
    sources = sources or []
    rows: list[str] = []
    for item in sources[:max(1, int(limit))]:
        title = item.get("title", "")
        source = item.get("source", "")
        if not title:
            continue
        if source:
            rows.append(f"{title}（{source}）")
        else:
            rows.append(title)
    return rows


def utility_profile(topic: str = "") -> dict:
    """话题实用性评分"""
    topic = topic or ""
    score = 50
    if "OpenClaw" in topic:
        score += 30
    if "AI" in topic or "Coding" in topic:
        score += 20
    return {
        "utility_score": min(100, score),
        "positioning": f"OpenClaw 实战视角解读 {topic}",
        "audience": "独立开发者和AI工具爱好者",
        "cta": "评论区告诉我你最想了解什么",
        "measurement_window": "48h",
        "validation_metrics": ["收藏率", "评论数", "转发数"],
    }


def score_practical_value(topic: str = "", insights=None, sources=None) -> int:
    """评估内容实用价值分数"""
    score = 30
    topic_str = str(topic or "").lower()
    keywords_high = ["openclaw", "ai coding", "agent", "copilot", "gpt", "llm", "prompt"]
    keywords_mid = ["开发", "编程", "自动化", "api", "workflow", "工具"]
    for kw in keywords_high:
        if kw in topic_str:
            score += 15
    for kw in keywords_mid:
        if kw in topic_str:
            score += 8
    if insights:
        insight_text = str(insights).lower()
        if "实战" in insight_text or "tutorial" in insight_text:
            score += 10
        if "趋势" in insight_text or "trend" in insight_text:
            score += 5
    if sources:
        score += min(20, len(sources) * 4)
    return min(100, max(0, score))


# ── 策略推导 ────────────────────────────────────────────────

def derive_topic_strategy(topic: str, research: dict, memory: dict) -> dict:
    """为话题推导完整的内容策略"""
    insights = research.get("insights", {})
    patterns = insights.get("patterns", [])
    hooks = insights.get("hooks", [])
    opportunity = insights.get("opportunity", "")

    runs = memory.get("runs", [])
    x_tactic = "去头部账号评论区做高价值回复"
    xhs_tactic = "搜索热搜关键词 → 教程/SOP 型文章"
    lead_magnet = "资料包、模板或 SOP"
    cta = "引导用户评论或私信领取资料"

    if runs:
        last_run = runs[-1] if runs else {}
        if last_run.get("x_tactic"):
            x_tactic = last_run["x_tactic"]
        if last_run.get("xhs_tactic"):
            xhs_tactic = last_run["xhs_tactic"]

    return {
        "topic": topic,
        "x_tactic": x_tactic,
        "xhs_tactic": xhs_tactic,
        "lead_magnet": lead_magnet,
        "cta": cta,
        "trend_label": hooks[0] if hooks and hooks[0] else creator_trend_label(topic, {}),
        "utility_score": score_practical_value(topic, insights, research.get("x", [])),
        "patterns": patterns,
        "hooks": hooks,
        "opportunity": opportunity,
    }


# ── 内容组合 (X / 小红书) ───────────────────────────────────

def compose_human_x_post(topic: str = "", strategy: dict | None = None, sources: list | None = None) -> str:
    """组合人类风格的 X 推文"""
    strategy = strategy or {}
    sources = sources or []
    trend_label = creator_trend_label(topic, strategy)
    src_lines = source_title_lines(sources, limit=1, max_len=34)
    x_tactic = strategy.get("x_tactic", "去头部账号评论区做高价值回复")
    lead_magnet = strategy.get("lead_magnet", "资料包")

    lines = [
        f"今天都在聊「{trend_label}」，但对普通创作者更重要的不是复述热点。",
        "",
        "没有 X Premium 的免费号，别幻想靠 For You 自然起量。",
        "我现在用 OpenClaw 跑 0 成本 AI SOP：",
        "1. 先用热点做 MVP 选题",
        f"2. {x_tactic}",
        "3. 再把同题改写成小红书教程，先看收藏率",
    ]
    if src_lines:
        lines.extend(["", f"今天先借这条起势：{src_lines[0]}"])
    lines.extend([
        "",
        f"主页置顶放{lead_magnet}，先验证 PMF，再决定要不要买会员和投流。",
        "#OpenClaw #内容增长",
    ])
    return "\n".join(lines)[:278]


def compose_human_xhs_article(topic: str = "", strategy: dict | None = None, sources: list | None = None) -> dict:
    """组合人类风格的小红书文章"""
    strategy = strategy or {}
    sources = sources or []
    trend_label = creator_trend_label(topic, strategy)
    cta = strategy.get("cta", "引导用户评论或私信领取资料")
    return {
        "title": f"{trend_label}实用教程",
        "body": f"关于{trend_label}的实用分享\n\n{cta}",
    }


# ── 话题研究 ────────────────────────────────────────────────

async def research_social_topic(
    topic: str = "AI 工具",
    limit: int = 5,
    news_fetcher=None,
    curate_fn=None,
) -> dict:
    """研究社媒话题 — 从新闻源收集素材并分类

    Args:
        topic: 研究话题
        limit: 每个来源的条目上限
        news_fetcher: NewsFetcher 实例
        curate_fn: 策划过滤函数 (items, limit) -> list
    """
    google_items: list = []
    bing_items: list = []
    if news_fetcher:
        try:
            google_items = await news_fetcher.fetch_from_google_news_rss(topic, count=limit)
            bing_items = await news_fetcher.fetch_from_bing(topic, count=limit)
        except Exception as e:
            logger.error(f"[ResearchTopic] fetch failed: {scrub_secrets(str(e))}")

    all_items_raw = (google_items or []) + (bing_items or [])
    if curate_fn:
        all_items = curate_fn(all_items_raw, limit=limit * 2)
    else:
        all_items = all_items_raw[:limit * 2]

    x_items = [
        item for item in all_items
        if any(k in item.get("title", "").lower() for k in ["x", "twitter", "thread"])
    ]
    xhs_items = [
        item for item in all_items
        if any(k in item.get("title", "").lower() for k in ["小红书", "教程", "分享"])
    ]
    if not x_items:
        x_items = all_items[:limit]
    if not xhs_items:
        xhs_items = all_items[:limit]

    insights = {
        "patterns": ["教程", "SOP", "实操"],
        "hooks": [topic],
        "opportunity": f"围绕「{topic}」产出实用内容",
    }
    return {"success": True, "x": x_items, "xiaohongshu": xhs_items, "insights": insights}


# ── 内容包创建 ──────────────────────────────────────────────

async def create_topic_social_package(
    platform: str = None,
    topic: str = "OpenClaw 实战",
    news_fetcher=None,
    curate_fn=None,
    save_draft_fn=None,
) -> dict:
    """创建话题内容包 — 研究 → 策略 → 双平台内容 → 草稿"""
    try:
        research = await research_social_topic(
            topic=topic, news_fetcher=news_fetcher, curate_fn=curate_fn
        )
        if not research.get("success"):
            return {"success": False, "error": "研究阶段失败"}

        strategy = derive_topic_strategy(topic, research, research)
        sources = research.get("x", []) + research.get("xiaohongshu", [])

        x_body = compose_human_x_post(topic, strategy, sources)
        xhs_result = compose_human_xhs_article(topic, strategy, sources)
        xhs_body = xhs_result.get("body", "") if isinstance(xhs_result, dict) else str(xhs_result or "")
        xhs_title = xhs_result.get("title", "") if isinstance(xhs_result, dict) else ""

        x_draft = save_draft_fn("x", "", x_body, topic=topic) if save_draft_fn else {}
        xhs_draft = save_draft_fn("xiaohongshu", xhs_title, xhs_body, topic=topic) if save_draft_fn else {}

        return {
            "success": True,
            "topic": topic,
            "strategy": strategy,
            "results": {
                "x": {
                    "success": True,
                    "body": x_body,
                    "draft_id": x_draft.get("draft_id", 0) if x_draft else 0,
                },
                "xiaohongshu": {
                    "success": True,
                    "body": xhs_body,
                    "title": xhs_title,
                    "draft_id": xhs_draft.get("draft_id", 0) if xhs_draft else 0,
                },
            },
        }
    except Exception as e:
        logger.error(f"[CreateTopicPackage] failed: {scrub_secrets(str(e))}")
        return {"success": False, "error": str(e)}


# ── 自动发布 ────────────────────────────────────────────────

async def autopost_topic_content(
    platform: str = None,
    topic: str = "OpenClaw 实战",
    news_fetcher=None,
    curate_fn=None,
    save_draft_fn=None,
    worker_fn=None,
) -> dict:
    """按话题自动发布社媒内容 — 通过适配器统一分发"""
    try:
        package = await create_topic_social_package(
            platform=platform, topic=topic,
            news_fetcher=news_fetcher, curate_fn=curate_fn,
            save_draft_fn=save_draft_fn,
        )
        if not package.get("success"):
            return package

        from src.execution.social.platform_adapter import get_adapter, get_all_adapters

        results = {}
        target = platform or "all"
        pkg_results = package.get("results", {})

        # 确定要发布到哪些平台
        target_adapters = {}
        if target == "all":
            target_adapters = get_all_adapters()
        else:
            adapter = get_adapter(target)
            if adapter:
                target_adapters = {adapter.platform_id: adapter}

        for pid, adapter in target_adapters.items():
            pkg_data = pkg_results.get(pid)
            if not pkg_data:
                continue
            if worker_fn:
                render = worker_fn("render", {"topic": topic, "platform": pid})
                body = pkg_data.get("body", "")
                title = pkg_data.get("title", "")
                payload = adapter.build_worker_payload(body, title)
                published = worker_fn(adapter.worker_action, payload)
                results[pid] = {**pkg_data, "rendered": render, "published": published}
            else:
                results[pid] = pkg_data

        return {"success": True, "topic": topic, "results": results}
    except Exception as e:
        logger.error(f"[AutopostTopic] failed: {scrub_secrets(str(e))}")
        return {"success": False, "error": str(e)}


async def autopost_hot_content(
    platform: str = None,
    topic: str = None,
    discover_fn=None,
    save_draft_fn=None,
    worker_fn=None,
) -> dict:
    """自动发布热门内容"""
    if not discover_fn:
        return {"success": False, "error": "discover_fn not provided"}

    discovery = await discover_fn(count=1)
    if not discovery or not isinstance(discovery, list) or len(discovery) == 0:
        return {"success": False, "error": "没有发现热门话题"}

    # discover_hot_topics 返回 list of dicts
    candidate = discovery[0] if isinstance(discovery, list) else {}
    hot_topic = candidate.get("title", "") or str(topic or "")
    if not hot_topic:
        return {"success": False, "error": "没有可用话题"}

    research = {
        "x": [candidate],
        "xiaohongshu": [candidate],
        "insights": {
            "patterns": ["教程", "SOP"],
            "hooks": [hot_topic],
            "opportunity": candidate.get("summary", ""),
        },
        "runs": [],
    }
    strategy = derive_topic_strategy(hot_topic, research, research)
    sources = [candidate]
    x_body = compose_human_x_post(hot_topic, strategy, sources)
    xhs_result = compose_human_xhs_article(hot_topic, strategy, sources)
    xhs_body = xhs_result.get("body", "") if isinstance(xhs_result, dict) else str(xhs_result or "")
    xhs_title = xhs_result.get("title", "") if isinstance(xhs_result, dict) else ""

    results = {}
    target = platform or "all"

    from src.execution.social.platform_adapter import get_adapter, get_all_adapters

    # 构建各平台的内容映射
    platform_content = {
        "x": {"body": x_body, "title": ""},
        "xiaohongshu": {"body": xhs_body, "title": xhs_title},
    }

    # 确定要发布到哪些平台
    target_adapters = {}
    if target == "all":
        target_adapters = get_all_adapters()
    else:
        adapter = get_adapter(target)
        if adapter:
            target_adapters = {adapter.platform_id: adapter}

    for pid, adapter in target_adapters.items():
        content_data = platform_content.get(pid, {})
        body = content_data.get("body", "")
        title = content_data.get("title", "")
        draft = save_draft_fn(pid, title, body, topic=hot_topic) if save_draft_fn else {}
        rendered = worker_fn("render", {"topic": hot_topic, "platform": pid}) if worker_fn else {}
        payload = adapter.build_worker_payload(body, title)
        published = worker_fn(adapter.worker_action, payload) if worker_fn else {}
        results[pid] = {
            "body": body,
            "title": title,
            "draft": draft,
            "rendered": rendered,
            "published": published,
        }

    return {"success": True, "topic": hot_topic, "strategy": strategy, "results": results}


# ── 社交计划 ────────────────────────────────────────────────

async def build_social_plan(
    topic: str = None,
    limit: int = 3,
    discover_fn=None,
) -> dict:
    """构建每日社媒计划"""
    if not discover_fn:
        return {"success": False, "error": "discover_fn not provided"}

    discovery = await discover_fn(count=limit)
    if not discovery or not isinstance(discovery, list):
        return {"success": False, "error": "没有发现热门话题"}

    plans = []
    for candidate in discovery[:limit]:
        t = candidate.get("title", "") or str(topic or "")
        research = {
            "x": [candidate],
            "xiaohongshu": [candidate],
            "insights": {
                "patterns": ["教程", "SOP"],
                "hooks": [candidate.get("title", "")],
                "opportunity": candidate.get("summary", ""),
            },
            "runs": [],
        }
        strategy = derive_topic_strategy(t, research, research)
        plans.append({
            "topic": t,
            "trend_label": creator_trend_label(t, strategy),
            "utility_score": strategy.get("utility_score", 50),
            "x_tactic": strategy.get("x_tactic", ""),
            "xhs_tactic": strategy.get("xhs_tactic", ""),
            "strategy": strategy,
        })

    return {"success": True, "mode": "daily", "plans": plans}


async def build_social_repost_bundle(
    topic: str = "OpenClaw 实战",
    worker_fn=None,
    save_draft_fn=None,
) -> dict:
    """构建社媒转发包"""
    if not worker_fn:
        return {"success": False, "error": "worker_fn not provided"}

    research = worker_fn("research", {"topic": topic})
    if not research or not research.get("success"):
        return {"success": False, "error": "研究阶段失败"}

    strategy = derive_topic_strategy(topic, research, research)
    sources = research.get("x", []) + research.get("xiaohongshu", [])
    x_body = compose_human_x_post(topic, strategy, sources)
    xhs_result = compose_human_xhs_article(topic, strategy, sources)
    xhs_body = xhs_result.get("body", "") if isinstance(xhs_result, dict) else str(xhs_result or "")
    xhs_title = xhs_result.get("title", "") if isinstance(xhs_result, dict) else ""

    render = worker_fn("render", {"topic": topic})
    x_draft = save_draft_fn("x", "", x_body, topic=topic) if save_draft_fn else {}
    xhs_draft = save_draft_fn("xiaohongshu", xhs_title, xhs_body, topic=topic) if save_draft_fn else {}

    return {
        "success": True,
        "topic": topic,
        "results": {
            "x": {
                "success": True,
                "body": x_body,
                "draft_id": x_draft.get("draft_id", 0) if x_draft else 0,
                "rendered": render,
            },
            "xiaohongshu": {
                "success": True,
                "body": xhs_body,
                "title": xhs_title,
                "draft_id": xhs_draft.get("draft_id", 0) if xhs_draft else 0,
                "rendered": render,
            },
        },
    }


# ── 内容创意 & 日历 ────────────────────────────────────────

async def generate_content_ideas(keyword: str = "AI 工具", count: int = 5) -> dict:
    """AI 生成内容创意选题"""
    prompt = (
        f"请为关键词「{keyword}」生成 {count} 个社交媒体内容选题创意，"
        "每个包含标题和简短描述。以 JSON 数组返回: "
        '[{"title":"...", "description":"..."}]'
    )
    try:
        result = await ai_pool.call(prompt)
        if result.get("success"):
            raw = result.get("raw", "")
            parsed = extract_json_object(raw)
            if isinstance(parsed, list):
                return {"success": True, "ideas": parsed[:count]}
            if isinstance(parsed, dict) and "ideas" in parsed:
                return {"success": True, "ideas": parsed["ideas"][:count]}
            ideas = [line.strip() for line in raw.split("\n") if line.strip()]
            return {"success": True, "ideas": ideas[:count]}
        return {"success": False, "ideas": [], "error": result.get("error", "AI 调用失败")}
    except Exception as e:
        logger.error(f"[ContentIdeas] failed: {scrub_secrets(str(e))}")
        return {"success": False, "ideas": [], "error": str(e)}


# ── 内容日历持久化层 ──────────────────────────────────────

def _save_calendar_to_db(days_list: list[dict]) -> int:
    """将生成的日历条目批量写入 content_calendar 表，返回写入条数"""
    try:
        from src.execution._db import get_conn
        today = datetime.now()
        saved = 0
        with get_conn() as conn:
            for item in days_list:
                # 计算实际日期：Day 1 = 今天, Day 2 = 明天 ...
                day_num = item.get("day", 0)
                if not day_num:
                    # 尝试从 date 字段解析
                    date_str = str(item.get("date", ""))
                    nums = re.findall(r"\d+", date_str)
                    day_num = int(nums[0]) if nums else 1
                plan_date = (today + timedelta(days=max(0, day_num - 1))).strftime("%Y-%m-%d")
                topic = item.get("topic", "")
                if not topic:
                    continue
                content_type = item.get("type", item.get("content_type", ""))
                platform = item.get("platform", "all")
                scheduled_time = item.get("time", item.get("scheduled_time", ""))
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO content_calendar "
                        "(plan_date, topic, content_type, platform, scheduled_time, status) "
                        "VALUES (?, ?, ?, ?, ?, 'planned')",
                        (plan_date, topic, content_type, platform, scheduled_time),
                    )
                    saved += 1
                except Exception as e:
                    logger.debug("[ContentCalendar] 写入单条失败: %s", e)
        return saved
    except Exception as e:
        logger.warning("[ContentCalendar] 批量写入失败: %s", e)
        return 0


def get_calendar_from_db(days: int = 7) -> list[dict]:
    """从 content_calendar 表查询未来 N 天的计划"""
    try:
        from src.execution._db import get_conn
        today = datetime.now().strftime("%Y-%m-%d")
        end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, plan_date, topic, content_type, platform, "
                "scheduled_time, status, draft_id "
                "FROM content_calendar "
                "WHERE plan_date >= ? AND plan_date <= ? "
                "ORDER BY plan_date, scheduled_time",
                (today, end),
            ).fetchall()
        return [
            {
                "id": r[0], "plan_date": r[1], "topic": r[2],
                "content_type": r[3], "platform": r[4],
                "scheduled_time": r[5], "status": r[6], "draft_id": r[7],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("[ContentCalendar] 查询失败: %s", e)
        return []


def mark_calendar_done(day_offset: int) -> dict:
    """标记第 N 天的日历条目为已完成"""
    try:
        from src.execution._db import get_conn
        target = (datetime.now() + timedelta(days=max(0, day_offset - 1))).strftime("%Y-%m-%d")
        with get_conn() as conn:
            cur = conn.execute(
                "UPDATE content_calendar SET status = 'published' "
                "WHERE plan_date = ? AND status != 'published'",
                (target,),
            )
        if cur.rowcount > 0:
            return {"success": True, "date": target, "updated": cur.rowcount}
        return {"success": False, "error": f"第 {day_offset} 天（{target}）无可更新条目"}
    except Exception as e:
        logger.warning("[ContentCalendar] 标记完成失败: %s", e)
        return {"success": False, "error": str(e)}


async def generate_content_calendar(days: int = 7) -> dict:
    """AI 生成内容日历 — 注入最佳发布时段 + 结果持久化到 DB"""
    # 注入 PostTimeOptimizer 最佳时段数据
    best_hours_hint = ""
    try:
        from src.social_tools import get_post_time_optimizer
        optimizer = get_post_time_optimizer()
        best = optimizer.best_hours("all")
        if best:
            hours_str = "、".join(f"{h}:00" for h in best[:3])
            best_hours_hint = f"根据历史数据，最佳发布时段: {hours_str}。"
    except Exception as e:
        pass  # 获取失败不阻塞日历生成
        logger.debug("静默异常: %s", e)

    prompt = (
        f"请为接下来 {days} 天生成一份社交媒体内容日历，"
        "包括每天的主题和内容类型。"
        f"{best_hours_hint}"
        "以 JSON 返回: "
        '{"days": [{"date":"Day 1", "topic":"...", "type":"tutorial/opinion/news", "platform":"x/xhs/both"}]}'
    )
    try:
        result = await ai_pool.call(prompt)
        if result.get("success"):
            parsed = extract_json_object(result.get("raw", ""))
            if parsed:
                # 持久化到数据库
                days_list = parsed.get("days", []) if isinstance(parsed, dict) else parsed
                if isinstance(days_list, list):
                    _save_calendar_to_db(days_list)
                return {"success": True, **parsed}
        return {"success": False, "error": "日历生成失败"}
    except Exception as e:
        logger.error(f"[ContentCalendar] failed: {scrub_secrets(str(e))}")
        return {"success": False, "error": str(e)}


# ── 首发套件 ────────────────────────────────────────────────

def create_social_launch_drafts(
    persona: dict | None = None,
    save_draft_fn=None,
) -> dict:
    """创建社媒账号首发草稿套件"""
    persona = persona or {}
    name = persona.get("name", "OpenClaw")
    voice = persona.get("voice", "专业、务实")

    x_intro = (
        f"Hi，我是 {name}。\n"
        f"风格: {voice}\n"
        "关注我，一起探索 AI 工具和效率提升。\n"
        "#OpenClaw #AITools"
    )
    xhs_intro = {
        "title": f"大家好，我是{name}！",
        "body": (
            f"Hi，我是 {name}，一个专注 AI 工具和效率提升的创作者。\n\n"
            f"我的风格: {voice}\n\n"
            "后续会分享实用教程和 SOP，欢迎关注！"
        ),
    }

    results = {}
    if save_draft_fn:
        results["x"] = save_draft_fn("x", "", x_intro, topic="launch")
        results["xhs"] = save_draft_fn(
            "xiaohongshu", xhs_intro["title"], xhs_intro["body"], topic="launch"
        )
    else:
        results["x"] = {"body": x_intro}
        results["xhs"] = xhs_intro

    return {"success": True, "results": results}


# ── 发布效果 ────────────────────────────────────────────────

def get_post_performance_report(
    days: int = 7,
    draft_store: list | None = None,
) -> dict:
    """获取发布效果报告 — 整合草稿状态 + 真实互动数据"""
    drafts = draft_store or []
    total = len(drafts)
    published = sum(1 for d in drafts if d.get("status") == "published")

    # ── 从数据库拉取真实互动数据 ──
    by_platform: dict[str, dict] = {}
    top_posts: list[dict] = []
    try:
        import time

        from src.execution._db import get_conn
        from src.execution.life_automation import get_engagement_summary

        # 按平台聚合的汇总数据
        eng = get_engagement_summary(days=days)
        if eng.get("success"):
            for platform, stats in eng.get("platforms", {}).items():
                by_platform[platform] = {
                    "posts": stats.get("posts", 0),
                    "likes": stats.get("likes", 0),
                    "comments": stats.get("comments", 0),
                    "views": stats.get("views", 0),
                    "shares": stats.get("shares", 0),
                    "engagement_rate": stats.get("engagement_rate", 0),
                }

        # 互动最高的帖子列表 (按 likes+comments+shares 排序)
        cutoff = time.time() - days * 86400
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT draft_id, platform, post_url, likes, comments, shares, views "
                    "FROM post_engagement WHERE checked_at > ? "
                    "ORDER BY (likes + comments + shares) DESC LIMIT 10",
                    (cutoff,),
                ).fetchall()
            for r in rows:
                top_posts.append({
                    "draft_id": r[0],
                    "platform": r[1],
                    "url": r[2] or "",
                    "likes": r[3] or 0,
                    "comments": r[4] or 0,
                    "shares": r[5] or 0,
                    "views": r[6] or 0,
                    "topic": "",  # 草稿关联信息可后续扩展
                })
        except Exception as e:
            logger.warning("[PostPerformance] 查询 top_posts 失败: %s", e)

    except Exception as e:
        logger.warning("[PostPerformance] 获取互动数据失败: %s", e)

    return {
        "success": True,
        "days": days,
        "total_drafts": total,
        "published": published,
        "pending": total - published,
        "by_platform": by_platform,
        "top_posts": top_posts,
    }
