"""
Execution Hub — 向后兼容门面 (Facade)

将原 3789 行的 execution_hub.py 拆分为模块化包后，
通过此文件提供 100% 向后兼容的 ExecutionHub 类。

原有代码中 `from src.execution_hub import ExecutionHub` 继续工作。
新代码应直接导入子模块: `from src.execution.task_mgmt import add_task`
"""
import asyncio
import logging
from pathlib import Path

from src.execution._db import DB_PATH, ensure_db_dir, init_db, get_conn
from src.execution._ai import ai_pool
from src.execution._utils import (
    extract_json_object, topic_slug, normalize_monitor_text,
    safe_int, safe_float, parse_hhmm,
)
from src.execution.monitoring import MonitorManager
from src.execution.scheduler import ExecutionScheduler

logger = logging.getLogger(__name__)


class ExecutionHub:
    """
    向后兼容的 ExecutionHub 门面类。
    将方法调用委托给拆分后的子模块。

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
        self._draft_store = []
        self._max_drafts = 500

    # ── AI Caller 注入 ──────────────────────────────────────

    def set_social_ai_callers(self, callers=None):
        self._social_ai_callers = dict(callers or {})
        ai_pool.set_callers(self._social_ai_callers)

    # ── 场景1: 邮件 ─────────────────────────────────────────

    def triage_email(self, max_messages=20, only_unread=True):
        from src.execution.email_triage import triage_email
        return asyncio.get_event_loop().run_until_complete(
            triage_email(max_messages, only_unread)
        )

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

    def summarize_meeting(self, text=None, file_path=None):
        from src.execution.meeting_notes import summarize_meeting
        return asyncio.get_event_loop().run_until_complete(
            summarize_meeting(text, file_path)
        )

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

    # ── 场景9: 项目周报 ─────────────────────────────────────

    def generate_project_report(self, project_dir=None, days=7):
        from src.execution.project_report import generate_project_report
        return generate_project_report(project_dir, days)

    # ── 场景10: 开发流程 ────────────────────────────────────

    def run_dev_workflow(self, project_dir=None):
        from src.execution.dev_workflow import run_dev_workflow
        return run_dev_workflow(project_dir)

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

    # ── 场景6: 社交媒体 ─────────────────────────────────────

    def load_social_persona(self, persona_id=None):
        from src.execution.social.content_strategy import load_persona
        return load_persona(persona_id, persona_dir=self.social_persona_dir)

    def get_social_persona_summary(self):
        persona = self.load_social_persona()
        return {
            "name": persona.get("name", "未配置"),
            "voice": persona.get("voice", ""),
            "platforms": persona.get("platforms", []),
        }

    async def discover_hot_social_topics(self, count=5):
        from src.execution.social.content_strategy import discover_hot_topics
        return await discover_hot_topics(count)

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

    async def research_social_topic(self, topic=None, platform="both"):
        from src.execution.social.content_strategy import derive_content_strategy
        persona = self.load_social_persona()
        return await derive_content_strategy(topic, platform, persona)

    async def build_social_plan(self, days=7):
        from src.execution.social.content_strategy import compose_post
        persona = self.load_social_persona()
        topics = await self.discover_hot_social_topics(count=days)
        plans = []
        for t in topics:
            plan = await compose_post(
                topic=t.get("title", ""),
                platform="both",
                persona=persona,
            )
            plans.append(plan)
        return plans

    def get_social_browser_status(self):
        """社交浏览器状态 — 向后兼容"""
        return {
            "browser_running": False,
            "x_ready": None,
            "xiaohongshu_ready": None,
        }

    # ── 场景11: 赏金猎人 ────────────────────────────────────

    async def scan_bounties(self, keywords=None):
        from src.execution.bounty import scan_bounties
        return await scan_bounties(keywords, db_path=self.db_path)

    def list_bounty_leads(self, status=None, limit=20):
        from src.execution.bounty import list_bounty_leads
        return list_bounty_leads(status, limit, db_path=self.db_path)

    async def run_bounty_hunter(self):
        from src.execution.bounty import run_bounty_hunter
        return await run_bounty_hunter(db_path=self.db_path)
