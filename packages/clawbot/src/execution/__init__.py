"""
Execution Hub — 向后兼容门面 (Facade)

将原 3789 行的 execution_hub.py 拆分为模块化包后，
通过此文件提供 100% 向后兼容的 ExecutionHub 类。

原有代码中 `from src.execution_hub import ExecutionHub` 继续工作。
新代码应直接导入子模块: `from src.execution.task_mgmt import add_task`

v3.0 (2026-03-24): 完成全部 legacy 委托迁移，_get_legacy() 已移除。
  execution_hub.py 不再被运行时加载，仅保留作为反编译参考。
"""
import logging
import os
import re
from pathlib import Path

from src.execution._db import DB_PATH, ensure_db_dir, init_db, get_conn
from src.execution._ai import ai_pool
from src.execution._utils import (
    extract_json_object, topic_slug, normalize_monitor_text,
    safe_int as safe_int, safe_float as safe_float, parse_hhmm as parse_hhmm,
)
from src.execution.monitoring import MonitorManager
from src.execution.scheduler import ExecutionScheduler

logger = logging.getLogger(__name__)


class ExecutionHub:
    """
    向后兼容的 ExecutionHub 门面类。
    将方法调用委托给拆分后的子模块。

    v3.0: 全部方法已迁移，不再依赖 execution_hub.py legacy 文件。
    新功能请直接使用子模块，不要在此类中添加新方法。
    """

    def __init__(self, news_fetcher=None):
        self.news_fetcher = news_fetcher
        self.db_path = str(DB_PATH)
        self.repo_root = str(Path(__file__).resolve().parent.parent.parent)

        # 初始化目录和数据库
        ensure_db_dir()
        init_db(self.db_path)

        # 子系统
        self._monitor_mgr = MonitorManager(
            news_fetcher=news_fetcher, db_path=self.db_path
        )
        self._scheduler = ExecutionScheduler()
        self._scheduler.monitor_manager = self._monitor_mgr

        # 社交相关目录（保持兼容）
        self.social_learning_dir = str(Path(self.repo_root) / "data" / "social_learning")
        self.social_persona_dir = str(Path(self.repo_root) / "data" / "social_personas")
        self.social_metrics_dir = str(Path(self.repo_root) / "data" / "social_metrics")
        self.social_state_dir = str(Path(self.repo_root) / "data" / "social_state")
        for d in (self.social_learning_dir, self.social_persona_dir,
                  self.social_metrics_dir, self.social_state_dir):
            Path(d).mkdir(parents=True, exist_ok=True)

        # 兼容旧属性
        self._social_ai_callers = {}

    # ── AI Caller 注入 ──────────────────────────────────────

    def set_social_ai_callers(self, callers=None):
        self._social_ai_callers = dict(callers or {})
        ai_pool.set_callers(self._social_ai_callers)

    # ── 场景1: 邮件 ─────────────────────────────────────────

    async def triage_email(self, max_messages=20, only_unread=True):
        from src.execution.email_triage import triage_email
        return await triage_email(max_messages, only_unread)

    def format_email_triage(self, triage=None):
        from src.execution.email_triage import format_email_triage
        return format_email_triage(triage)

    # ── 场景2: 每日简报 ─────────────────────────────────────

    async def generate_daily_brief(self):
        from src.execution.daily_brief import generate_daily_brief
        return await generate_daily_brief(
            monitors=self._monitor_mgr._monitors, db_path=self.db_path
        )

    # ── 场景3: 文档检索 ─────────────────────────────────────

    def build_doc_index(self, roots=None, max_files=500):
        from src.execution.doc_search import build_doc_index
        return build_doc_index(roots, max_files)

    def search_docs(self, query=None, limit=10):
        from src.execution.doc_search import search_docs
        return search_docs(query, limit=limit)

    # ── 场景4: 会议纪要 ─────────────────────────────────────

    async def summarize_meeting(self, text=None, file_path=None):
        from src.execution.meeting_notes import summarize_meeting
        return await summarize_meeting(text, file_path)

    # ── 场景5: 任务管理 ─────────────────────────────────────

    def add_task(self, title=None, priority="medium", **kwargs):
        from src.execution.task_mgmt import add_task
        return add_task(title, priority, db_path=self.db_path)

    def has_open_task(self, title=None, **kwargs):
        from src.execution.task_mgmt import has_open_task
        return has_open_task(title, db_path=self.db_path)

    def update_task_status(self, task_id=None, status=None):
        from src.execution.task_mgmt import update_task_status
        return update_task_status(task_id, status, db_path=self.db_path)

    def list_tasks(self, status=None):
        from src.execution.task_mgmt import list_tasks
        return list_tasks(status, db_path=self.db_path)

    def top_tasks(self, limit=10):
        from src.execution.task_mgmt import top_tasks
        return top_tasks(limit, db_path=self.db_path)

    # ── 场景6: 社交媒体 ─────────────────────────────────────

    def load_social_persona(self, persona_id=None):
        from src.execution.social.content_strategy import load_persona
        return load_persona(persona_dir=self.social_persona_dir, name=persona_id or "default")

    def get_social_persona_summary(self):
        persona = self.load_social_persona()
        return {
            "name": persona.get("name", "未配置") if persona else "未配置",
            "voice": persona.get("voice", "") if persona else "",
            "platforms": persona.get("platforms", []) if persona else [],
        }

    async def discover_hot_social_topics(self, count=5, limit=None):
        """发现热门社媒话题 — 使用硬编码计划 + 新闻抓取 + 评分

        保持与原 execution_hub.py 兼容的返回格式:
        {"success": True, "candidates": [{topic, trend_label, utility_score, items, plan}, ...]}
        """
        from src.execution.social.content_pipeline import utility_profile
        effective_limit = limit or count
        plans = self._hot_social_plans()
        candidates = []
        for plan in plans[:effective_limit]:
            query = plan.get("query", "")
            items = []
            if self.news_fetcher:
                try:
                    items = await self.news_fetcher.fetch_from_google_news_rss(query, count=5)
                except Exception as e:
                    logger.debug("静默异常: %s", e)
            curated = self._curate_monitor_items(items or [], limit=3)
            util = utility_profile(plan.get("topic", ""))
            candidates.append({
                "topic": plan.get("topic", ""),
                "trend_label": plan.get("trend_label", ""),
                "utility_score": util.get("utility_score", 50) + plan.get("boost", 0),
                "items": curated,
                "plan": plan,
            })
        candidates.sort(key=lambda c: c.get("utility_score", 0), reverse=True)
        return {"success": True, "candidates": candidates[:effective_limit]}

    @staticmethod
    def _hot_social_plans():
        """硬编码的热门内容计划 (从 execution_hub.py 迁移)"""
        return [
            {
                "id": "openclaw_coding",
                "query": "GitHub Copilot GPT-5.4",
                "topic": "OpenClaw AI Coding 实战",
                "trend_label": "GitHub Copilot + GPT-5.4",
                "hook": "今天大家都在聊 GitHub Copilot 接上 GPT-5.4，但更值得蹭的是：怎么把模型升级变成稳定的 OpenClaw 工作流。",
                "practical_focus": "把热点从模型新闻改写成团队级 AI Coding 实战教程。",
                "boost": 14,
            },
            {
                "id": "openclaw_agent",
                "query": "AI Agent workflow",
                "topic": "OpenClaw Agent 工作流",
                "trend_label": "AI Agent 工作流",
                "hook": "AI Agent 这波流量能蹭，但不要再空谈概念，直接把它讲成 OpenClaw 的可执行工作流才有传播力。",
                "practical_focus": "围绕任务拆解、并行执行、交叉验证，输出能直接上手的 Agent 实操教程。",
                "boost": 13,
            },
            {
                "id": "openclaw_hot",
                "query": "OpenClaw",
                "topic": "OpenClaw 实用教程",
                "trend_label": "OpenClaw 热搜",
                "practical_focus": "围绕真实场景、避坑和结果展示，做强教程感和实用性。",
                "boost": 12,
            },
            {
                "id": "openclaw_claude",
                "query": "Claude workflow",
                "topic": "OpenClaw Claude 协同流",
                "trend_label": "Claude 工作流",
                "practical_focus": "把 Claude 在复杂任务总控、代码审查和交叉验证里的角色讲清楚。",
                "boost": 11,
            },
            {
                "id": "openclaw_saas",
                "query": "SaaS 出海 AI",
                "topic": "OpenClaw 出海内容流",
                "trend_label": "AI / SaaS 出海",
                "practical_focus": "把热点翻成监控、选题、发文三段式方法，而不是泛聊趋势。",
                "boost": 9,
            },
        ]

    async def publish_persona_x(self, topic=None, content=None, **kwargs):
        from src.execution.social.x_platform import publish_x_post
        persona = self.load_social_persona()
        return await publish_x_post(
            topic=topic, content=content, persona=persona, **kwargs
        )

    async def publish_persona_xhs(self, topic=None, content=None, **kwargs):
        from src.execution.social.xhs_platform import publish_xhs_article
        persona = self.load_social_persona()
        return await publish_xhs_article(
            topic=topic, content=content, persona=persona, **kwargs
        )

    async def reply_to_x_post(self, post_url=None, reply_text=None):
        from src.execution.social.x_platform import reply_to_x_post
        return await reply_to_x_post(post_url, reply_text)

    async def reply_to_xhs_comment(self, comment_id=None, reply_text=None):
        from src.execution.social.xhs_platform import reply_to_xhs_comment
        return await reply_to_xhs_comment(comment_id, reply_text)

    async def fetch_x_profile_posts(self, handle=None, count=8):
        from src.execution.social.x_platform import fetch_x_profile_posts
        return await fetch_x_profile_posts(handle, count)

    async def research_social_topic(self, topic=None, limit=None):
        """社媒话题研究"""
        from src.execution.social.content_pipeline import research_social_topic
        return await research_social_topic(
            topic=topic or "AI 工具",
            limit=limit or 5,
            news_fetcher=self.news_fetcher,
            curate_fn=self._curate_monitor_items,
        )

    async def build_social_plan(self, topic=None, limit=None):
        """构建每日社媒计划"""
        from src.execution.social.content_pipeline import derive_topic_strategy
        effective_limit = limit or 3
        discovery = await self.discover_hot_social_topics(limit=effective_limit)
        if not discovery.get("success") or not discovery.get("candidates"):
            return {"success": False, "error": "没有发现热门话题"}
        plans = []
        for candidate in discovery["candidates"][:effective_limit]:
            t = candidate.get("topic", "")
            research = {
                "x": candidate.get("items", []),
                "xiaohongshu": candidate.get("items", []),
                "insights": {
                    "patterns": ["教程", "SOP"],
                    "hooks": [candidate.get("trend_label", "")],
                    "opportunity": candidate.get("plan", {}).get("practical_focus", ""),
                },
                "runs": [],
            }
            strategy = derive_topic_strategy(t, research, research)
            plans.append({
                "topic": t,
                "trend_label": candidate.get("trend_label", ""),
                "utility_score": candidate.get("utility_score", 50),
                "x_tactic": strategy.get("x_tactic", ""),
                "xhs_tactic": strategy.get("xhs_tactic", ""),
                "strategy": strategy,
            })
        return {"success": True, "mode": "daily", "plans": plans}

    def get_social_browser_status(self):
        """社交浏览器状态 — 向后兼容"""
        return {
            "browser_running": False,
            "x_ready": None,
            "xiaohongshu_ready": None,
        }

    def save_social_draft(self, platform=None, title=None, body=None, sources=None, topic=None):
        """保存社媒草稿"""
        from src.execution.social.drafts import save_social_draft
        return save_social_draft(platform, title, body, sources, topic)

    def list_social_drafts(self, platform=None, status=None, limit=20):
        """列出草稿"""
        from src.execution.social.drafts import list_social_drafts
        return list_social_drafts(platform, status, limit)

    def get_social_draft(self, draft_id=None):
        """获取单个草稿"""
        from src.execution.social.drafts import get_social_draft
        return get_social_draft(draft_id)

    def update_social_draft_status(self, draft_id=None, status=None):
        """更新草稿状态"""
        from src.execution.social.drafts import update_social_draft_status
        return update_social_draft_status(draft_id, status)

    async def create_social_draft(self, platform=None, topic=None, max_items=3):
        """创建社媒草稿"""
        from src.execution.social.drafts import create_social_draft
        return await create_social_draft(
            platform=platform, topic=topic, max_items=max_items,
            monitors=self._monitor_mgr._monitors,
            fetch_posts_fn=self.fetch_x_profile_posts,
            news_fetcher=self.news_fetcher,
            curate_fn=self._curate_monitor_items,
        )

    async def autopost_topic_content(self, platform=None, topic=None):
        """按主题自动发布社媒内容"""
        from src.execution.social.content_pipeline import (
            derive_topic_strategy, compose_human_x_post, compose_human_xhs_article,
            research_social_topic,
        )
        topic = topic or "OpenClaw 实战"
        try:
            research = await research_social_topic(
                topic=topic, news_fetcher=self.news_fetcher,
                curate_fn=self._curate_monitor_items,
            )
            if not research.get("success"):
                return {"success": False, "error": "研究阶段失败"}
            strategy = derive_topic_strategy(topic, research, research)
            sources = research.get("x", []) + research.get("xiaohongshu", [])
            x_body = compose_human_x_post(topic, strategy, sources)
            xhs_result = compose_human_xhs_article(topic, strategy, sources)
            xhs_body = xhs_result.get("body", "") if isinstance(xhs_result, dict) else str(xhs_result or "")
            xhs_title = xhs_result.get("title", "") if isinstance(xhs_result, dict) else ""
            x_draft = self.save_social_draft("x", "", x_body, topic=topic)
            xhs_draft = self.save_social_draft("xiaohongshu", xhs_title, xhs_body, topic=topic)
            results = {}
            target = platform or "all"
            if target in ("all", "x"):
                render = self._run_social_worker("render", {"topic": topic, "platform": "x"})
                published = self._run_social_worker("publish_x", {"text": x_body, "images": []})
                results["x"] = {"success": True, "body": x_body,
                                "draft_id": x_draft.get("draft_id", 0) if x_draft else 0,
                                "rendered": render, "published": published}
            if target in ("all", "xiaohongshu"):
                render = self._run_social_worker("render", {"topic": topic, "platform": "xiaohongshu"})
                published = self._run_social_worker("publish_xhs", {"title": xhs_title, "body": xhs_body, "images": []})
                results["xiaohongshu"] = {"success": True, "body": xhs_body, "title": xhs_title,
                                          "draft_id": xhs_draft.get("draft_id", 0) if xhs_draft else 0,
                                          "rendered": render, "published": published}
            return {"success": True, "topic": topic, "results": results}
        except Exception as e:
            logger.error(f"[AutopostTopic] failed: {e}")
            return {"success": False, "error": str(e)}

    def publish_social_draft(self, platform=None, draft_id=None):
        """发布社媒草稿"""
        from src.execution.social.drafts import publish_social_draft
        from src.execution.social.worker_bridge import run_social_worker
        return publish_social_draft(
            platform=platform, draft_id=draft_id,
            worker_fn=run_social_worker,
        )

    async def autopost_hot_content(self, platform=None, topic=None):
        """自动发布热门内容"""
        from src.execution.social.content_pipeline import (
            derive_topic_strategy, compose_human_x_post, compose_human_xhs_article,
        )
        discovery = await self.discover_hot_social_topics(limit=1)
        if not discovery.get("success") or not discovery.get("candidates"):
            return {"success": False, "error": "没有发现热门话题"}
        candidate = discovery["candidates"][0]
        hot_topic = candidate.get("topic", "")
        plan = candidate.get("plan", {})
        research = {
            "x": candidate.get("items", []),
            "xiaohongshu": candidate.get("items", []),
            "insights": {
                "patterns": ["教程", "SOP"],
                "hooks": [candidate.get("trend_label", "")],
                "opportunity": plan.get("practical_focus", ""),
            },
            "runs": [],
        }
        strategy = derive_topic_strategy(hot_topic, research, research)
        sources = candidate.get("items", [])
        x_body = compose_human_x_post(hot_topic, strategy, sources)
        xhs_result = compose_human_xhs_article(hot_topic, strategy, sources)
        xhs_body = xhs_result.get("body", "") if isinstance(xhs_result, dict) else str(xhs_result or "")
        xhs_title = xhs_result.get("title", "") if isinstance(xhs_result, dict) else ""
        results = {}
        target = platform or "all"
        if target in ("all", "x"):
            x_draft = self.save_social_draft("x", "", x_body, topic=hot_topic)
            render = self._run_social_worker("render", {"topic": hot_topic, "platform": "x"})
            published = self._run_social_worker("publish_x", {"text": x_body, "images": []})
            results["x"] = {"body": x_body, "draft": x_draft, "rendered": render, "published": published}
        if target in ("all", "xiaohongshu"):
            xhs_draft = self.save_social_draft("xiaohongshu", xhs_title, xhs_body, topic=hot_topic)
            render = self._run_social_worker("render", {"topic": hot_topic, "platform": "xiaohongshu"})
            published = self._run_social_worker("publish_xhs", {"title": xhs_title, "body": xhs_body, "images": []})
            results["xiaohongshu"] = {"body": xhs_body, "title": xhs_title, "draft": xhs_draft, "rendered": render, "published": published}
        return {"success": True, "topic": hot_topic, "strategy": strategy, "results": results}

    def _run_social_worker(self, action=None, payload=None):
        """运行社交浏览器 worker (可被测试 monkeypatch)"""
        from src.execution.social.worker_bridge import run_social_worker
        return run_social_worker(action, payload)

    async def create_hot_social_package(self, platform=None, topic=None):
        """创建热门社媒内容包"""
        from src.execution.social.content_pipeline import autopost_hot_content
        from src.execution.social.content_strategy import discover_hot_topics
        from src.execution.social.drafts import save_social_draft
        return await autopost_hot_content(
            platform=platform, topic=topic,
            discover_fn=discover_hot_topics,
            save_draft_fn=save_social_draft,
        )

    async def build_social_repost_bundle(self, topic=None):
        """构建社媒转发包"""
        from src.execution.social.content_pipeline import (
            derive_topic_strategy, compose_human_x_post, compose_human_xhs_article,
        )
        topic = topic or "OpenClaw 实战"
        research = self._run_social_worker("research", {"topic": topic})
        if not research or not research.get("success"):
            return {"success": False, "error": "研究阶段失败"}
        strategy = derive_topic_strategy(topic, research, research)
        sources = research.get("x", []) + research.get("xiaohongshu", [])
        x_body = compose_human_x_post(topic, strategy, sources)
        xhs_result = compose_human_xhs_article(topic, strategy, sources)
        xhs_body = xhs_result.get("body", "") if isinstance(xhs_result, dict) else str(xhs_result or "")
        xhs_title = xhs_result.get("title", "") if isinstance(xhs_result, dict) else ""
        render = self._run_social_worker("render", {"topic": topic})
        x_draft = self.save_social_draft("x", "", x_body, topic=topic)
        xhs_draft = self.save_social_draft("xiaohongshu", xhs_title, xhs_body, topic=topic)
        return {
            "success": True, "topic": topic,
            "results": {
                "x": {"success": True, "body": x_body,
                       "draft_id": x_draft.get("draft_id", 0) if x_draft else 0, "rendered": render},
                "xiaohongshu": {"success": True, "body": xhs_body, "title": xhs_title,
                                "draft_id": xhs_draft.get("draft_id", 0) if xhs_draft else 0, "rendered": render},
            },
        }

    async def generate_content_ideas(self, keyword=None, count=None):
        """生成内容创意选题"""
        from src.execution.social.content_pipeline import generate_content_ideas
        return await generate_content_ideas(
            keyword=keyword or "AI 工具", count=count or 5,
        )

    async def generate_content_calendar(self, days=7):
        """生成内容日历 — 优先从DB加载已有计划，无计划时才调AI生成"""
        from src.execution.social.content_pipeline import (
            generate_content_calendar, get_calendar_from_db,
        )
        # 先查表，有已有计划直接返回
        existing = get_calendar_from_db(days=days)
        if existing:
            return {"success": True, "from_db": True, "calendar_items": existing}
        # 无已有计划，AI 生成（内部自动持久化）
        return await generate_content_calendar(days=days)

    def get_calendar_from_db(self, days=7):
        """查询已有内容日历"""
        from src.execution.social.content_pipeline import get_calendar_from_db
        return get_calendar_from_db(days=days)

    def mark_calendar_done(self, day_offset=1):
        """标记某天日历为已完成"""
        from src.execution.social.content_pipeline import mark_calendar_done
        return mark_calendar_done(day_offset=day_offset)

    def create_social_launch_drafts(self, *args, **kwargs):
        """创建社媒发布草稿套件"""
        from src.execution.social.content_pipeline import create_social_launch_drafts
        from src.execution.social.drafts import save_social_draft
        persona = self.load_social_persona()
        return create_social_launch_drafts(
            persona=persona, save_draft_fn=save_social_draft,
        )

    def get_post_performance_report(self, days=7):
        """获取发布效果报告"""
        from src.execution.social.content_pipeline import get_post_performance_report
        from src.execution.social.drafts import _draft_store
        return get_post_performance_report(days=days, draft_store=_draft_store)

    # ── 场景7: 信息监控 ─────────────────────────────────────

    def add_monitor(self, keyword=None, source="news"):
        return self._monitor_mgr.add_monitor(keyword, source)

    def list_monitors(self):
        return self._monitor_mgr.list_monitors()

    async def run_monitors_once(self):
        return await self._monitor_mgr.run_monitors_once()

    def format_monitor_alert(self, alert=None):
        return MonitorManager.format_alert(alert)

    # ── 场景8: 生活自动化 ───────────────────────────────────

    async def create_reminder(self, message=None, delay_minutes=None):
        from src.execution.life_automation import create_reminder
        return await create_reminder(message, delay_minutes, db_path=self.db_path)

    async def trigger_home_action(self, action=None, payload=None):
        """触发智能家居/本地 macOS 动作"""
        from src.execution.life_automation import trigger_home_action
        return await trigger_home_action(action, payload)

    # ── 场景9: 项目周报 ─────────────────────────────────────

    def generate_project_report(self, project_dir=None, days=7):
        from src.execution.project_report import generate_project_report
        return generate_project_report(project_dir, days)

    # ── 场景10: 开发流程 ────────────────────────────────────

    def run_dev_workflow(self, project_dir=None):
        from src.execution.dev_workflow import run_dev_workflow
        return run_dev_workflow(project_dir)

    # ── 场景11: 赏金猎人 ────────────────────────────────────

    async def scan_bounties(self, keywords=None, **kwargs):
        """赏金扫描"""
        from src.execution.bounty import scan_bounties
        return await scan_bounties(keywords=keywords, db_path=self.db_path)

    def list_bounty_leads(self, status=None, limit=20):
        from src.execution.bounty import list_bounty_leads
        return list_bounty_leads(status, limit, db_path=self.db_path)

    async def run_bounty_hunter(self, **kwargs):
        """赏金猎人"""
        from src.execution.bounty import run_bounty_hunter
        return await run_bounty_hunter(db_path=self.db_path)

    def open_bounty_links(self, lead_ids=None, **kwargs):
        """打开赏金链接"""
        import subprocess
        leads = self.list_bounty_leads(limit=50)
        opened = []
        for lead in leads:
            url = lead.get("url", "")
            if url:
                try:
                    subprocess.run(["open", url], check=False, timeout=5)
                    opened.append(url)
                except Exception as e:
                    logger.debug("静默异常: %s", e)
        return {"success": True, "opened": len(opened)}

    # ── 场景12: X 平台高级功能 ──────────────────────────────

    async def generate_x_monitor_brief(self, *args, **kwargs):
        """生成 X 监控简报"""
        from src.execution.social.x_platform import generate_x_monitor_brief
        return await generate_x_monitor_brief(
            monitors=self._monitor_mgr._monitors,
            fetch_posts_fn=self.fetch_x_profile_posts,
        )

    async def analyze_tweet_execution(self, source=None, **kwargs):
        """分析推文执行策略"""
        from src.execution.social.x_platform import analyze_tweet_execution
        from src.execution.social.worker_bridge import run_social_worker
        return await analyze_tweet_execution(
            source=source or "", worker_fn=run_social_worker,
        )

    async def run_tweet_execution(self, source=None, **kwargs):
        """执行推文发布流程"""
        from src.execution.social.x_platform import run_tweet_execution
        from src.execution.social.worker_bridge import run_social_worker
        from src.execution.social.drafts import save_social_draft
        return await run_tweet_execution(
            source=source or "",
            worker_fn=run_social_worker,
            ai_call_fn=ai_pool.call,
            save_draft_fn=save_social_draft,
        )

    async def import_x_monitors_from_tweet(self, source=None, limit=None, **kwargs):
        """从推文导入 X 监控账号"""
        from src.execution.social.x_platform import import_x_monitors_from_tweet
        from src.execution.social.worker_bridge import run_social_worker
        return await import_x_monitors_from_tweet(
            source=source or "", limit=limit or 10,
            worker_fn=run_social_worker,
            add_monitor_fn=self.add_monitor,
        )

    def _normalize_x_handle(self, source=None, **kwargs):
        """标准化 X/Twitter 用户名格式"""
        from src.execution.social.x_platform import normalize_x_handle
        return normalize_x_handle(source or "")

    # ── 调度器 ──────────────────────────────────────────────

    async def start_scheduler(self, notify_func, private_notify_func=None):
        await self._scheduler.start(notify_func, private_notify_func)

    async def stop_scheduler(self):
        await self._scheduler.stop()

    # ── 内部工具（保持兼容） ────────────────────────────────

    def _conn(self):
        return get_conn(self.db_path)

    def _extract_json_object(self, text=None):
        return extract_json_object(text)

    def _topic_slug(self, topic=None):
        return topic_slug(topic)

    def _normalize_monitor_text(self, text=None):
        return normalize_monitor_text(text)

    async def _call_social_ai(self, prompt=None, system_prompt=None):
        return await ai_pool.call(prompt, system_prompt)

    async def _call_social_ai_direct(self, bot_id=None, prompt=None, system_prompt=None):
        return await ai_pool.call_direct(bot_id, prompt, system_prompt)

    # ── 监控辅助 (保持兼容) ──────────────────────────────────

    @staticmethod
    def _monitor_env_list(env_name=None, default=None):
        raw = os.getenv(env_name, default)
        if not raw:
            return []
        return [x.strip() for x in raw.split(',') if x.strip()]

    def _clean_monitor_title(self, title=None, source=None):
        title = title or ''
        clean_title = re.sub(r'\s+', ' ', str(title).strip())
        source = source or ''
        clean_source = re.sub(r'\s+', ' ', str(source).strip())
        if clean_source:
            suffixes = [
                f' - {clean_source}', f' | {clean_source}',
                f' - {clean_source.lower()}', f' | {clean_source.lower()}',
            ]
            lower_title = clean_title.lower()
            for suffix in suffixes:
                if lower_title.endswith(suffix.lower()):
                    clean_title = clean_title[:-len(suffix)].strip()
                    return clean_title
        return clean_title

    def _is_low_value_monitor_item(self, title=None, source=None):
        blocked_sources = self._monitor_env_list(
            'OPS_MONITOR_BLOCKED_SOURCES',
            '新浪财经,驱动之家,中关村在线,cnBeta.COM,搜狐网,IT之家,快科技',
        )
        low_value_keywords = self._monitor_env_list(
            'OPS_MONITOR_LOW_VALUE_KEYWORDS',
            '独显,份额,市场份额,专卖,显卡,开箱,评测,参数,跑分,报价,促销,价格,卖不出去',
        )
        title_text = str(title or '')
        source_text = str(source or '')
        haystack = f'{title_text} {source_text}'.lower()
        source_lower = source_text.lower()
        for token in (blocked_sources or []):
            token_lower = token.lower()
            if token_lower and (token_lower in source_lower or token_lower in haystack):
                return True
        for token in (low_value_keywords or []):
            token_lower = token.lower()
            if token_lower and token_lower in haystack:
                return True
        return False

    def _curate_monitor_items(self, items=None, limit=None):
        curated = []
        seen_titles = set()
        items = items or []
        limit = limit or 10
        for item in items:
            title = item.get('title', '')
            source = item.get('source', '')
            url = item.get('url', '')
            clean_title = self._clean_monitor_title(title, source)
            normalized = self._normalize_monitor_text(clean_title)
            if not normalized or normalized in seen_titles:
                continue
            seen_titles.add(normalized)
            if self._is_low_value_monitor_item(title, source):
                continue
            curated.append({
                'title': clean_title,
                'source': source,
                'url': url,
                'digest_key': normalized,
            })
            if len(curated) >= limit:
                break
        return curated

    # ── 社交内容工具方法 (兼容旧调用) ────────────────────────

    def _derive_topic_strategy(self, topic, research, memory):
        from src.execution.social.content_pipeline import derive_topic_strategy
        return derive_topic_strategy(topic, research, memory)

    def _compose_human_x_post(self, topic=None, strategy=None, sources=None):
        from src.execution.social.content_pipeline import compose_human_x_post
        return compose_human_x_post(topic, strategy, sources)

    def _compose_human_xhs_article(self, topic=None, strategy=None, sources=None):
        from src.execution.social.content_pipeline import compose_human_xhs_article
        return compose_human_xhs_article(topic, strategy, sources)

    def _apply_social_persona(self, strategy=None, topic=None, **kwargs):
        """人设应用 — 兼容方法"""
        persona = self.load_social_persona()
        if persona and strategy:
            strategy["persona_id"] = persona.get("id", "")
            strategy["persona_name"] = persona.get("name", "")
        return strategy

    def build_social_launch_kit(self):
        """社媒首发套件"""
        persona = self.load_social_persona() or {}
        return {
            "success": True,
            "persona": persona,
            "x_intro": f"Hi, I'm {persona.get('name', 'OpenClaw')}. "
                       f"Style: {persona.get('voice', 'professional')}",
            "xhs_intro": f"大家好，我是{persona.get('name', 'OpenClaw')}！",
        }

    # ── Legacy fallback (保留但不应再触发) ────────────────────

    def __getattr__(self, name):
        """Safety net for any remaining unmigrated method access.

        v3.0: All known methods have been migrated.
        If this triggers, it indicates a missed migration — log as ERROR.
        """
        if name.startswith('_'):
            raise AttributeError(f"ExecutionHub has no attribute '{name}'")

        logger.error(
            "UNMIGRATED method accessed: %s — this should not happen in v3.0, "
            "please report this as a bug", name
        )
        raise AttributeError(
            f"ExecutionHub has no attribute '{name}'. "
            f"All methods should be migrated to src/execution/ submodules."
        )
