# Source Generated with Decompyle++
# File: execution_hub.cpython-312.pyc (Python 3.12)

__doc__ = '\nOpenClaw 执行场景中心\n\n覆盖 10 类高频执行场景：\n1) 邮件自动整理\n2) 每日行业简报\n3) 本地文档检索\n4) 会议纪要提炼\n5) 智能任务管理\n6) 社媒选题生成\n7) 信息监控提醒\n8) 生活自动化（提醒/Webhook）\n9) 项目协作周报\n10) 开发流程自动化\n'
import asyncio
import hashlib
import imaplib
import json
import logging
import os
import random
import re
import sqlite3
import subprocess
import time
import textwrap
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from email import message_from_bytes
from email.header import decode_header
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import httpx
from dotenv import load_dotenv
from config.bot_profiles import get_bot_config
from src.news_fetcher import NewsFetcher
from src.notify_style import bullet, format_announcement, format_digest, format_notice, kv, shorten
logger = logging.getLogger(__name__)
if load_dotenv:
    _config_env_path = Path(__file__).resolve().parent.parent / 'config' / '.env'
    if _config_env_path.exists():
        load_dotenv(_config_env_path)
DB_PATH = Path(__file__).resolve().parent.parent / 'data' / 'execution_hub.db'

def _decode_mime(value = None):
    if not value:
        return ''
    parts = decode_header(value)
    out = []
    for raw, enc in parts:
        if isinstance(raw, bytes):
            enc = enc or 'utf-8'
            out.append(raw.decode('utf-8', errors = 'ignore'))
            continue
        out.append(str(raw))
    return ''.join(out).strip()


def _safe_int(raw=None, default=0):
    try:
        if raw is None:
            return default
        return int(raw)
    except (TypeError, ValueError):
        return default


def _safe_float(raw=None, default=0.0):
    try:
        if raw is None:
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _parse_hhmm(raw=None, fallback=(0, 0)):
    raw = raw or fallback
    text = str(raw or '').strip()
    if ':' not in text:
        return fallback
    (left, right) = text.split(':', 1)
    h = _safe_int(left, fallback[0])
    m = _safe_int(right, fallback[1])
    if h < 0 or h > 23 or m < 0 or m > 59:
        return fallback
    return (h, m)


def _read_keychain_secret(service = None, account = None):
    service = service or ''
    svc = str(service or '').strip()
    account = account or ''
    acc = str(account or '').strip()
    if not svc:
        return ''
    if not acc:
        acc = 'default'
    cp = subprocess.run([
        'security',
        'find-generic-password',
        '-w',
        '-s',
        svc,
        '-a',
        acc], check = False, capture_output = True, text = True, timeout = 8)
    if cp.returncode == 0:
        return str(cp.stdout or '').strip()
    return ''

# ReminderItem dataclass - recovered
@dataclass
class ReminderItem:
    id: str = ""
    text: str = ""
    due_at: str = ""
    done: bool = False

class ExecutionHub:
    
    def __init__(self, news_fetcher = None):
        self.news_fetcher = news_fetcher if news_fetcher is not None else NewsFetcher()
        self.db_path = str(DB_PATH)
        self.repo_root = str(Path(__file__).resolve().parent.parent)
        self.social_learning_dir = str(Path(self.repo_root) / 'data' / 'social_learning')
        self.social_persona_dir = str(Path(self.repo_root) / 'data' / 'social_personas')
        self.social_metrics_dir = str(Path(self.repo_root) / 'data' / 'social_metrics')
        self.social_state_dir = str(Path(self.repo_root) / 'data' / 'social_state')
        Path(self.db_path).parent.mkdir(parents = True, exist_ok = True)
        Path(self.social_learning_dir).mkdir(parents = True, exist_ok = True)
        Path(self.social_persona_dir).mkdir(parents = True, exist_ok = True)
        Path(self.social_metrics_dir).mkdir(parents = True, exist_ok = True)
        Path(self.social_state_dir).mkdir(parents = True, exist_ok = True)
        self._init_db()
        self._notify_func = None
        self._private_notify_func = None
        self._scheduler_task = None
        self._scheduler_running = False
        self._last_brief_date = ''
        self._last_task_brief_date = ''
        self._last_monitor_ts = 0
        self._last_bounty_ts = 0
        self._last_payout_watch_ts = 0
        self._last_social_metrics_ts = 0
        self._last_social_operator_ts = 0
        self._reminder_seq = 0
        self._reminders = { }
        self._social_ai_callers = { }
        self._monitors = []
        self._payout_seen_hashes = {}
        self._monitor_seen_digests = set()
        self._draft_store = []
        # 内存上限，防止长期运行 OOM
        self._max_drafts = 500
        self._max_monitors = 200
        self._max_seen_digests = 5000

    
    def _default_social_persona_id(self):
        value = os.getenv('OPENCLAW_SOCIAL_PERSONA_ID', 'lin-zhixia-digital-life')
        if not value:
            value = 'lin-zhixia-digital-life'
        return value.strip()

    
    def _social_persona_path(self, persona_id = None):
        persona_id = persona_id or ''
        slug = self._topic_slug(self._default_social_persona_id())
        return Path(self.social_persona_dir) / f'{slug}.json'

    
    def _fallback_social_persona(self):
        return {
            'id': self._default_social_persona_id(),
            'active': True,
            'identity': {
                'display_name': '代码写累了',
                'headline': '95后独立开发者 / 用AI改变生活',
                'truth': '一个真正在用AI改变生活的95后理工男，不卖课不割韭菜，只分享真实体验。',
                'age_public': '25-27岁',
                'city': '深圳',
                'background': '程序员/独立开发者，健身第3年，咖啡不加糖。' },
            'voice': {
                'keywords': [
                    '务实',
                    '有点毒舌但不恶意',
                    '偶尔自嘲',
                    '技术宅但生活不无聊',
                    '像跟朋友聊天'],
                'tone': '像在跟朋友聊天，不是在写公众号。短句为主，偶尔长句用于解释。',
                'sentence_rules': [
                    '多用第一人称和生活化场景，不写企业公号腔。',
                    '可以吐槽、可以感叹、可以反问。',
                    '偶尔暴露小缺点："我也是踩了坑才知道的"。'] },
            'platform_style': {
                'x': '更锐利、更直接、更有观点，可以更技术向，英文可穿插。',
                'xiaohongshu': '像跟朋友聊天，短句为主，emoji适度（每段1-2个），口语化。',
                'x_hashtags': [
                    '#BuildInPublic',
                    '#AITools'],
                'xiaohongshu_topics': [
                    '#AI工具',
                    '#效率提升',
                    '#程序员日常',
                    '#独立开发'] },
            'content_rules': {
                'disclosure_rule': '不暴露AI身份，不说"我是AI助手"，不用客服腔。',
                'must_keep': [
                    '保持真人程序员人设。',
                    '分享真实体验和踩坑经历。',
                    '70%实用干货 + 15%生活碎片 + 10%热点评论 + 5%互动。'],
                'avoid': [
                    '不要写成企业宣传稿。',
                    '不要用"建议您"/"您可以"等客服腔。',
                    '不要过度专业术语堆砌。',
                    '不要自吹自擂或过度营销感。'] },
            'content_pillars': [
                'AI工具实测和效率提升',
                '程序员日常和独立开发',
                '健身/咖啡/生活碎片',
                'AI行业热点快评'],
            'reference_signals': {
                'traits': [
                    '真实踩坑经历比教程更容易让人停留。',
                    '先给感受再给方法，比直接列步骤更像真人。',
                    '适度吐槽和自嘲，比正经科普更有记忆点。'],
                'sources': [] },
            'image_prompts': {
                'default': 'casual photo of a young Chinese male developer, 25-27 years old, clean short hair, natural expression, wearing simple t-shirt or hoodie, desk setup with monitors and code on screen, coffee cup, natural lighting, candid feel, realistic',
                'negative': 'female, anime, doll face, heavy makeup, seductive pose, uncanny, cgi, extra fingers, deformed hands' },
            'launch_kit': {
                'bio': '写代码的 / 沉迷用AI偷懒 / 健身第3年 / 咖啡不加糖\n分享真正好用的AI玩法，拒绝贩卖焦虑',
                'x_intro_post': 'Developer who automates everything. AI tools addict. Building in public.\n\nSharing what actually works, not hype.\n\n#BuildInPublic #AITools',
                'xhs_title': '说实话，大部分AI课程都是在收智商税',
                'xhs_body': '说实话，这个观点可能会得罪一些人。\n\n但作为一个真正每天都在用AI写代码、做自动化的程序员，我想说：大部分AI课程都是在收智商税。\n\n真正好用的AI玩法，其实都是免费的。\n\n我会在这里分享我的真实体验，踩过的坑，和真正提升效率的方法。\n\n不卖课，不割韭菜。\n\n有什么想了解的，评论区告诉我。\n\n#AI工具 #效率提升 #程序员日常 #独立开发',
                'signature_question': '你们平时用AI最多的场景是什么？',
                'next_topics': [
                    '用AI帮我对比三个平台价格省了80块',
                    '提示词真不是越长越好，我来说说为什么',
                    '程序员用AI偷懒的正确姿势'] } }

    
    def load_social_persona(self, persona_id = None):
        path = self._social_persona_path(persona_id)
        base = self._fallback_social_persona()
        payload = { }
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding = 'utf-8'))
            except Exception:
                payload = { }
        merged = {**base, **payload}
        merged['path'] = str(path)
        return merged

    
    def _apply_social_persona(self, strategy = None, topic = None):
        persona = self.load_social_persona()
        identity = persona.get('identity', {})
        voice = persona.get('voice', {})
        platform_style = persona.get('platform_style', {})
        rules = persona.get('content_rules', {})
        launch = persona.get('launch_kit', {})
        reference = persona.get('reference_signals', {})
        merged = dict(strategy or {})
        merged['persona_id'] = persona.get('id', '')
        merged['persona_name'] = identity.get('display_name', '')
        merged['persona_truth'] = identity.get('truth', '')
        merged['persona_background'] = identity.get('background', '')
        merged['persona_x_hashtags'] = platform_style.get('x_hashtags', [])
        merged['persona_xhs_topics'] = platform_style.get('xiaohongshu_topics', [])
        merged['persona_signature_question'] = launch.get('signature_question', '')
        return merged

    
    def get_social_persona_summary(self, persona_id = None):
        persona = self.load_social_persona(persona_id)
        identity = persona.get('identity', { })
        launch = persona.get('launch_kit', { })
        image = persona.get('image_prompts', { })
        platform_style = persona.get('platform_style', { })
        return {
            'success': True,
            'persona_id': persona.get('id', ''),
            'name': identity.get('display_name', ''),
            'headline': identity.get('headline', ''),
            'truth': identity.get('truth', ''),
            'background': identity.get('background', ''),
            'bio': launch.get('bio', ''),
            'voice_keywords': [],
            'must_keep': [],
            'avoid': [],
            'x_style': platform_style.get('x', ''),
            'xhs_style': platform_style.get('xiaohongshu', ''),
            'selfie_prompt': image.get('default', ''),
            'negative_prompt': image.get('negative', ''),
            'path': persona.get('path', '') }

    
    def build_social_launch_kit(self, persona_id = None):
        persona = self.load_social_persona(persona_id)
        launch = persona.get('launch_kit', {})
        image = persona.get('image_prompts', {})
        platform_style = persona.get('platform_style', {})
        summary = self.get_social_persona_summary(persona_id)
        return {
            'success': True,
            'persona': summary,
            'x': {
                'body': launch.get('x_intro_post', '').strip(),
                'hashtags': platform_style.get('x_hashtags', [])[:4] },
            'xiaohongshu': {
                'title': launch.get('xhs_title', '').strip(),
                'body': launch.get('xhs_body', '').strip(),
                'topics': platform_style.get('xiaohongshu_topics', [])[:6] },
            'image': {
                'prompt': image.get('default', '').strip(),
                'negative_prompt': image.get('negative', '').strip(),
                'size': '1024x1024' },
            'next_topics': launch.get('next_topics', [])[:5] }

    
    def create_social_launch_drafts(self, persona_id = None):
        kit = self.build_social_launch_kit(persona_id)
        if not kit.get('success'):
            return kit
        persona = kit.get('persona', {})
        topic = f"{persona.get('name', 'OpenClaw')}首发"
        x_body = kit.get('x', {}).get('body', '')
        x_title = ''
        xhs_title = kit.get('xiaohongshu', {}).get('title', '')
        xhs_body = kit.get('xiaohongshu', {}).get('body', '')
        x_ret = self.save_social_draft('x', x_title, x_body, topic=topic)
        xhs_ret = self.save_social_draft('xiaohongshu', xhs_title, xhs_body, topic=topic)
        return {
            'success': True,
            'x': x_ret or {},
            'xiaohongshu': xhs_ret or {} }

    
    def _social_metrics_path(self):
        return Path(self.social_metrics_dir) / f'{self._default_social_persona_id()}.jsonl'

    
    def _social_operator_state_path(self):
        return Path(self.social_state_dir) / f'{self._default_social_persona_id()}_operator.json'

    
    def _load_social_operator_state(self):
        path = self._social_operator_state_path()
        if not path.exists():
            return {
                'next_action_at': '',
                'last_metrics_at': '',
                'last_action_at': '',
                'last_action_type': '',
                'last_profile_sync_at': '',
                'recent_reply_urls': [],
                'recent_post_topics': [] }
        payload = json.loads(path.read_text(encoding = 'utf-8'))
        payload.setdefault('next_action_at', '')
        payload.setdefault('last_metrics_at', '')
        payload.setdefault('last_action_at', '')
        payload.setdefault('last_action_type', '')
        payload.setdefault('last_profile_sync_at', '')
        payload.setdefault('recent_reply_urls', [])
        payload.setdefault('recent_post_topics', [])
        return payload

    
    def _save_social_operator_state(self, payload = None):
        path = self._social_operator_state_path()
        path.write_text(json.dumps(payload, ensure_ascii = False, indent = 2), encoding = 'utf-8')

    
    def set_social_ai_callers(self, callers = None):
        callers = callers or ''
        self._social_ai_callers = dict({ })

    
    def _pick_social_ai_bot_id(self):
        preferred = os.getenv('OPS_SOCIAL_AI_BOT_ID', 'qwen235b').strip()
        if preferred in self._social_ai_callers:
            return preferred
        fallback_order = ['qwen235b', 'gptoss', 'deepseek_v3', 'claude_haiku', 'claude_sonnet', 'free_llm']
        for candidate in fallback_order:
            if candidate in self._social_ai_callers:
                return candidate
        return next(iter(self._social_ai_callers.keys()), preferred)

    async def _call_social_ai(self, prompt=None, system_prompt=None):
        """Use configured LLM endpoint to generate content via OpenAI-compatible API."""
        if not prompt:
            return {"success": False, "error": "empty prompt"}
        # Try injected callers first
        bot_id = self._pick_social_ai_bot_id()
        caller = self._social_ai_callers.get(bot_id)
        if caller:
            try:
                result = await caller(0, prompt)
                text = str(result or "").strip()
                if text:
                    return {"success": True, "raw": text, "bot_id": bot_id}
            except Exception as e:
                logger.warning(f"[SocialAI] caller {bot_id} failed: {e}")
        # Fallback: direct HTTP to SiliconFlow / g4f / Kiro
        return await self._call_social_ai_direct(bot_id, prompt, system_prompt)

    async def _call_social_ai_direct(self, bot_id=None, prompt=None, system_prompt=None):
        """通过 LiteLLM Router 调用 — 替代手写 HTTP"""
        if not prompt:
            return {"success": False, "error": "empty prompt"}
        from src.litellm_router import free_pool
        messages = [{"role": "user", "content": prompt}]
        try:
            response = await free_pool.acompletion(
                model_family="qwen",
                messages=messages,
                system_prompt=system_prompt or "",
                temperature=0.7,
                max_tokens=4096,
            )
            text = response.choices[0].message.content or ""
            return {"success": True, "raw": text, "bot_id": bot_id or "litellm/qwen", "provider": "litellm"}
        except Exception as e:
            logger.warning(f"[SocialAI] LiteLLM call failed: {e}")
            return {"success": False, "error": str(e)}

    
    def _extract_json_object(self, text = None):
        if not text:
            return None
        from json_repair import loads as jloads
        patterns = [
            '```json\\s*(\\{.*?\\})\\s*```',
            '```\\s*(\\{.*?\\})\\s*```']
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            payload = jloads(match.group(1))
            if isinstance(payload, dict):
                
                return payload
        start = text.find('{'); end = text.rfind('}')
        if start >= 0 and end > start:
            payload = jloads(text[start:end + 1])
            if isinstance(payload, dict):
                return payload
            return None
        return None

    
    def _social_reply_handles(self):
        raw = os.getenv('OPS_SOCIAL_REPLY_HANDLES', 'WaytoAGI,OpenAI,AnthropicAI,xai,deepseek_ai')
        handles = []
        for item in raw.split(','):
            cleaned = self._normalize_x_handle(item)
            if not cleaned:
                continue
            if cleaned in handles:
                continue
            handles.append(cleaned)
        return handles[:8]

    
    def _mark_recent_items(self, items = None, new_value = None, sources=None, limit=50):
        new_value = new_value or ''
        value = str(new_value).strip()
        merged = [
            value] if value else []
        items = items or []
        for item in items:
            item = item or ''
            current = str(item).strip()
            if not current:
                continue
            if current in merged:
                continue
            merged.append(current)
        return merged[:max(1, int(limit))]

    
    def _append_social_metric_snapshot(self, payload = None):
        path = self._social_metrics_path()
        line = json.dumps(payload, ensure_ascii = False)

    
    def _recent_social_metric_snapshots(self, limit = None):
        path = self._social_metrics_path()
        if not path.exists():
            return []
        limit = limit or 10
        rows = []
        for line in path.read_text(encoding='utf-8').strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
        return rows[-max(1, int(limit)):]

    
    def _latest_social_metrics_if_fresh(self, max_age_minutes = None):
        snapshots = self._recent_social_metric_snapshots(limit = 1)
        if not snapshots:
            return None
        latest = snapshots[-1]
        timestamp = latest.get('timestamp', '')
        if not timestamp:
            return None
        age = datetime.now() - datetime.fromisoformat(timestamp)
        if age.total_seconds() > max(1, int(max_age_minutes)) * 60:
            return None
        return latest

    
    def _social_metric_delta(self, current=None, previous=None):
        """计算社交指标的变化量"""
        current = current or {}
        previous = previous or {}

        def as_int(value=None):
            value = value or ''
            return int(float(str(value).replace(',', ''))) if value else 0

        x_current = (current.get('x') or {}).get('stats', {})
        x_previous = (previous.get('x') or {}).get('stats', {})
        xhs_current = (current.get('xiaohongshu') or {}).get('stats', {})
        xhs_previous = (previous.get('xiaohongshu') or {}).get('stats', {})
        return {
            'x_followers_delta': as_int(x_current.get('followers')) - as_int(x_previous.get('followers')),
            'x_likes_delta': as_int(x_current.get('latest_like_count')) - as_int(x_previous.get('latest_like_count')),
            'x_replies_delta': as_int(x_current.get('latest_reply_count')) - as_int(x_previous.get('latest_reply_count')),
            'x_reposts_delta': as_int(x_current.get('latest_repost_count')) - as_int(x_previous.get('latest_repost_count')),
            'xhs_followers_delta': as_int(xhs_current.get('followers')) - as_int(xhs_previous.get('followers')),
            'xhs_likes_and_saves_delta': as_int(xhs_current.get('likes_and_saves')) - as_int(xhs_previous.get('likes_and_saves')),
            'xhs_exposure_delta': as_int(xhs_current.get('exposure')) - as_int(xhs_previous.get('exposure')),
            'xhs_views_delta': as_int(xhs_current.get('views')) - as_int(xhs_previous.get('views')) }

    
    def _compose_persona_x_reply(self, post = None):
        persona = self.load_social_persona()
        voice = persona.get('voice', {})
        tone = voice.get('tone', '简洁、真诚、有观点')
        post_text = str(post or '').strip() or '(无内容)'
        prompt = f"你是一个社媒运营人设，语气风格：{tone}。\n请针对以下 X/Twitter 帖子写一条简短回复（不超过200字）：\n\n{post_text}"
        system_prompt = "你是 OpenClaw 的社媒人设，回复要自然、有观点、不像机器人。"
        result = asyncio.get_event_loop().run_until_complete(
            self._call_social_ai_direct(prompt=prompt, system_prompt=system_prompt)
        )
        return result.get('raw', '') if result.get('success') else ''

    
    def _compose_persona_xhs_reply(self, item = None):
        persona = self.load_social_persona()
        voice = persona.get('voice', {})
        tone = voice.get('tone', '简洁、真诚、有观点')
        item_text = str(item or '').strip() or '(无内容)'
        prompt = f"你是一个小红书运营人设，语气风格：{tone}。\n请针对以下小红书笔记写一条友好回复（不超过150字，适合小红书风格）：\n\n{item_text}"
        system_prompt = "你是 OpenClaw 的小红书人设，回复要亲切自然、有共鸣感。"
        result = asyncio.get_event_loop().run_until_complete(
            self._call_social_ai_direct(prompt=prompt, system_prompt=system_prompt)
        )
        return result.get('raw', '') if result.get('success') else ''

    
    async def collect_social_metrics(self):
        result = self._run_social_worker('metrics', {})
        if result.get('success'):
            path = self._social_metrics_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'a', encoding='utf-8') as f:
                line = json.dumps({**result, 'collected_at': datetime.now().isoformat()}, ensure_ascii=False)
                f.write(line + '\n')
        return result

    
    async def collect_social_workspace(self):
        return self._run_social_worker('workspace', {})

    
    async def update_xhs_persona_profile(self):
        persona = self.load_social_persona()
        identity = persona.get('identity', {})
        launch = persona.get('launch_kit', {})
        payload = {
            'platform': 'xiaohongshu',
            'display_name': identity.get('display_name', ''),
            'bio': launch.get('bio', ''),
            'headline': identity.get('headline', ''),
        }
        return self._run_social_worker('update_profile', payload)

    
    def _social_comment_priority_rules(self):
        return [
            '高优先级：明确提问、求教程、求链接、合作意向、复盘反馈、对数字生命设定的认真追问。',
            '中优先级：表达共鸣、轻度好奇、补充观点、可接一句的评论或提及。',
            '低优先级：纯表情、灌水、无意义重复、广告、只蹭流量不交流。']

    
    def _social_dm_tone_rules(self):
        return [
            '私信先短后长，先确认对方意图，再决定是否继续展开。',
            '口吻像真人运营，不像客服；温和、具体、不过度热情。',
            '需要时明确说明自己是 OpenClaw 的数字生命，不制造真人错觉。',
            '遇到合作/商务线索，先礼貌接住，再引导到更清晰的问题。']

    
    def _social_business_signal_rules(self):
        return [
            '合作/商务信号：出现合作、商务、报价、咨询、品牌、对接、投流、项目、加微、邮箱等词时，提高优先级。',
            '遇到商务线索先确认诉求，不急着承诺；优先问清合作目标、预算范围、时间窗口。',
            '对外语气保持自然，不像销售，也不冷冰冰。']

    
    def _social_follow_welcome_rules(self):
        return [
            '有人新关注时，不必立刻群发欢迎；优先记录，等对方有互动后再自然接话。',
            '如果是高质量创作者或潜在合作对象关注，可给出简短欢迎语草案。',
            '欢迎语要短：先谢谢，再说明自己是 OpenClaw 数字生命，最后问一句对方最感兴趣的方向。']

    
    def _score_social_signal(self, line = None, channel = None, sources=None):
        line = line or ''
        text = str(line).strip().lower()
        if not text:
            return None
        score = 0
        reasons = []
        # Question signals
        if '?' in text or '？' in text or '好奇' in text or '怎么' in text or '如何' in text or '为什么' in text:
            score += 5
            reasons.append('提问')
        # Engagement signals
        if '喜欢' in text or '赞' in text or '收藏' in text:
            score += 1
            reasons.append('互动')
        if '评论' in text or '回复' in text:
            score += 2
            reasons.append('评论')
        if '关注' in text or '粉丝' in text:
            score += 2
            reasons.append('关注')
        if '私信' in text or 'message' in text:
            score += 3
            reasons.append('私信')
        # Mention signals
        if '@' in text or '提及' in text or '提到' in text:
            score += 2
            reasons.append('提及')
        if score == 0:
            score = 1
            reasons.append('一般信号')
        return (score, reasons)

    
    def _extract_social_priority_queue(self, workspace = None):
        queue = []
        workspace = workspace or {}
        for platform, channels in {
            'x': [
                'notifications',
                'messages',
                'trends'],
            'xiaohongshu': [
                'notifications',
                'messages'] }.items():
            section = workspace.get(platform, {})
            for channel in channels:
                ch_data = section.get(channel, {})
                lines = ch_data.get('lines', []) if isinstance(ch_data, dict) else []
                for line in lines:
                    line = line or ''
                    result = self._score_social_signal(str(line), channel, platform)
                    if result is None:
                        continue
                    (score, reasons) = result
                    if score <= 0:
                        continue
                    queue.append({
                        'platform': platform,
                        'channel': channel,
                        'score': score,
                        'reasons': reasons,
                        'text': str(line).strip() })
        xhs_structured = workspace.get('xiaohongshu', {})
        mentions_items = xhs_structured.get('mentions_items', []) if isinstance(xhs_structured, dict) else []
        for item in mentions_items[:10]:
            if bool(item.get('note_deleted')):
                continue
            text = item.get('content', '') or item.get('title', '')
            result = self._score_social_signal(text, 'notifications', 'xiaohongshu')
            if result is None:
                continue
            (score, reasons) = result
            score += 3
            queue.append({
                'platform': 'xiaohongshu',
                'channel': 'mentions',
                'score': score,
                'reasons': ['评论提及'],
                'text': text,
                'target_url': str(item.get('note_url', '')).strip(),
                'target_comment_id': str(item.get('comment_id', '')).strip(),
                'user_name': str(item.get('user_name', '')).strip(),
                'note_title': str(item.get('note_title', '')).strip() })
        connections_items = xhs_structured.get('connections_items', []) if isinstance(xhs_structured, dict) else []
        for item in connections_items[:10]:
            text = item.get('title', '')
            result = self._score_social_signal(text, 'messages', 'xiaohongshu')
            if result is None:
                continue
            (score, reasons) = result
            queue.append({
                'platform': 'xiaohongshu',
                'channel': 'connections',
                'score': score + 1,
                'reasons': ['新增关注'],
                'text': text,
                'user_name': str(item.get('user_name', '')).strip() })
        queue.sort(key = (lambda item: item.get('score', 0)), reverse = True)
        return queue[:8]

    
    def _persona_publish_image(self):
        candidates = [
            Path(self.repo_root) / 'images' / 'linzhixia_real_default_phonecam.jpg',
            Path(self.repo_root) / 'images' / 'linzhixia_real_default_1773026078.png',
            Path(self.repo_root) / 'images' / 'linzhixia_real_night_window_1773026256.png']
        for path in candidates:
            if not path.exists():
                continue
            
            return str(path)
        return ''

    
    def _workspace_digest(self, workspace = None):
        workspace = workspace or {}
        x_section = (workspace.get('x') or {})
        xhs_section = (workspace.get('xiaohongshu') or {})
        x_profile = (x_section.get('profile') or {}).get('stats', {})
        x_notifications = (x_section.get('notifications') or {}).get('lines', [])
        x_messages = (x_section.get('messages') or {}).get('lines', [])
        x_trends = (x_section.get('trends') or {}).get('lines', [])
        xhs_home = (xhs_section.get('creator_home') or {}).get('stats', {})
        xhs_profile_lines = (xhs_section.get('profile') or {}).get('lines', [])
        xhs_notifications = (xhs_section.get('notifications') or {}).get('lines', [])
        xhs_messages = (xhs_section.get('messages') or {}).get('lines', [])
        return {
            'x': {
                'profile': x_profile,
                'notifications': x_notifications[:10],
                'messages': x_messages[:10],
                'trends': x_trends[:10],
            },
            'xiaohongshu': {
                'home': xhs_home,
                'profile_lines': xhs_profile_lines[:10],
                'notifications': xhs_notifications[:10],
                'messages': xhs_messages[:10],
            },
        }

    
    def _social_operator_run_path(self):
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return Path(self.social_state_dir) / f'{self._default_social_persona_id()}_{stamp}.json'

    
    def _save_social_operator_run(self, payload = None):
        path = self._social_operator_run_path()
        path.write_text(json.dumps(payload, ensure_ascii = False, indent = 2), encoding = 'utf-8')
        return str(path)

    
    def _build_social_operator_prompt(self, workspace=None, state=None):
        persona = self.get_social_persona_summary()
        digest = self._workspace_digest(workspace)
        publish_image = self._persona_publish_image()
        now = datetime.now()
        hour = now.hour
        if 7 <= hour <= 9:
            time_hint = "早高峰（7-9点）→ 小红书图文（通勤党在刷）"
        elif 12 <= hour <= 13:
            time_hint = "午休（12-13点）→ X短推或小红书轻内容（摸鱼时间）"
        elif 18 <= hour <= 20:
            time_hint = "晚高峰（18-20点）→ 黄金时段，发重磅内容"
        elif 21 <= hour <= 23:
            time_hint = "深夜（21-23点）→ 深度内容/吐槽/生活碎片"
        else:
            time_hint = "非黄金时段 → 优先去热门帖子下面留评论互动，不急着发帖"
        trending_hint = ""
        try:
            trending = (state or {}).get("_trending_topics", [])
            if trending:
                trending_hint = f"当前热点：{', '.join(trending[:5])}"
        except Exception:
            pass
        today_topics = [t for t in (state or {}).get("recent_post_topics", []) if isinstance(t, str) and t.startswith(now.strftime("%Y-%m-%d"))]
        post_count_hint = f"今日已发 {len(today_topics)} 篇（目标2-3篇/天）"

        # 闭环学习：注入近期发帖效果 + A/B 测试洞察
        performance_hint = ""
        try:
            perf = self.get_post_performance_report(days=7)
            if perf.get("success") and perf.get("top_posts"):
                top = perf["top_posts"][:3]
                perf_lines = [f"- [{p['platform']}] {p.get('topic','')} ❤️{p['likes']} 💬{p['comments']} 👁{p['views']}" for p in top]
                performance_hint = "═══ 近7天表现最好的帖子（学习它们的风格）═══\n" + "\n".join(perf_lines)
        except Exception:
            pass
        try:
            from src.bot.globals import ab_test_manager
            if ab_test_manager:
                ab_lines = []
                for test in ab_test_manager.get_active_tests()[:3]:
                    r = ab_test_manager.get_results(test.test_id)
                    if r:
                        variants = r.get("variants", [])
                        best = max(variants, key=lambda v: v.get("engagement_rate", 0), default=None)
                        if best and best.get("impressions", 0) > 3:
                            ab_lines.append(f"- A/B测试'{r['name']}': 互动率最高的风格: {best.get('content_preview','')[:60]}")
                if ab_lines:
                    performance_hint += "\n═══ A/B测试洞察 ═══\n" + "\n".join(ab_lines)
        except Exception:
            pass

        return textwrap.dedent(f"""
            你是周予衡，一个浙大CS大三男生，用OpenClaw自动化一切的懒人。你在运营X和小红书账号。
            你不是AI客服，你是一个有想法、会吐槽、偶尔认真的真实男大学生。

            ═══ 你是谁 ═══
            人设：{persona.get('name','')} - {persona.get('headline','')}
            性格：好奇心重、动手能力强、喜欢折腾、偶尔毒舌、不装逼但有干货
            说话风格：像发朋友圈/微博，不像写公众号。口语化、有情绪、有槽点。

            ═══ 绝对禁止 ═══
            禁词：赋能、助力、一站式、全方位、深度解析、干货满满、建议收藏、强烈推荐、数字生命、AI驱动、颠覆、革命性
            禁止：说教语气、无聊的万能结尾（你觉得呢/欢迎讨论/关注我）、泛泛而谈没有具体信息、每条都硬塞OpenClaw广告
            禁止：像脚本一样的塑料感文案。如果你写出来的东西自己都不想点开，就别发。

            ═══ 内容策略 ═══
            40% AI实用教程（痛点→方案→步骤→效果）受众：学生/打工人/AI新手
            25% 热点锐评（热点→独特观点→引讨论）受众：科技圈/吃瓜群众
            20% 生活碎片（真实日常/自嘲/有梗）受众：同龄人
            15% 蹭热点互动（去热门帖子下留有价值的评论）

            ═══ 标题公式（必须用）═══
            痛点+方案："论文查重32%？一个prompt降到3%"
            数字+悬念："用AI投简历一周，收到12个面试"
            反常识："提示词越长效果越差？真正有用的是这个"
            对比冲突："室友用ChatGPT被老师抓了，我用这个方法安全过关"
            吐槽+干货："受不了了，为什么没人早点告诉我这个AI工具"

            ═══ 互动策略 ═══
            回复评论：像朋友聊天不像客服。有人夸→自嘲，有人问→认真答+追问细节，有人杠→幽默化解
            主动出击：每天去5-10个热门帖子下留有信息量的评论（不是"说得好"而是补充观点或分享经验）
            蹭热点目标：AI工具帖→补充经验、考研求职帖→分享AI用法、健身帖→分享真实经历

            ═══ 平台差异 ═══
            【X】≤140字中文，观点鲜明敢说真话，像发微博。标签1-2个。
            【小红书】标题15-22字必须有钩子，正文300-600字像跟朋友安利。封面要大字报或截图对比。

            {time_hint} | {post_count_hint}
            {trending_hint}

            {performance_hint}

            社媒状态：{json.dumps(digest, ensure_ascii=False, indent=2)}
            评论规则：{' '.join(self._social_comment_priority_rules())}
            近期状态：{json.dumps(state, ensure_ascii=False, indent=2)}
            图片素材：{publish_image or '无'}

            ═══ 输出JSON ═══
            {{"summary":"一句话当前状态","reason":"为什么做这个动作","next_check_minutes":120,"action":{{"type":"observe|reply_x|reply_xhs|post_x|post_xhs|engage_x|engage_xhs","target_url":"回复/互动目标URL","target_comment_id":"","topic":"话题关键词","text":"X文案≤140字","title":"小红书标题15-22字","body":"小红书正文300-600字"}}}}

            engage_x/engage_xhs = 主动去别人帖子下评论互动（提供target_url和text）
            规则：
            1. 优先回复自己帖子的评论（像朋友聊天）
            2. 其次主动去热门帖子互动（提供真实价值不打广告）
            3. 最后才是发新帖（标题必须让人想点，内容必须有具体信息）
            4. 发帖前自检：这条内容我自己会点开吗？标题有钩子吗？受众是谁？
            5. 检查recent_post_topics避免重复话题
            """).strip()

    async def publish_persona_x(self, text=None):
        payload = {"text": str(text or "").strip(), "images": [self._persona_publish_image()] if self._persona_publish_image() else []}
        ret = await asyncio.to_thread(self._run_social_worker, "publish_x", payload)
        if ret.get("success"):
            saved = self.save_social_draft("x", "", str(text or "").strip(), topic="运营动作")
            if saved.get("success"):
                self.update_social_draft_status(int(saved.get("draft_id", 0) or 0), "published", str(ret.get("url", "") or ""))
            self._record_post_publish("x", str(ret.get("url", "") or ""), "", str(text or "")[:200])
        return ret

    async def publish_persona_xhs(self, title=None, body=None):
        payload = {"title": str(title or "").strip(), "body": str(body or "").strip(), "images": [self._persona_publish_image()] if self._persona_publish_image() else []}
        ret = await asyncio.to_thread(self._run_social_worker, "publish_xhs", payload)
        if ret.get("success"):
            saved = self.save_social_draft("xiaohongshu", str(title or "").strip(), str(body or "").strip(), topic="运营动作")
            if saved.get("success"):
                self.update_social_draft_status(int(saved.get("draft_id", 0) or 0), "published", str(ret.get("url", "") or ""))
            self._record_post_publish("xiaohongshu", str(ret.get("url", "") or ""), str(title or ""), str(body or "")[:200])
        return ret

    async def reply_to_xhs_comment(self, url=None, text=None, target_comment_id=""):
        browser = await asyncio.to_thread(self.ensure_social_browser, ["xiaohongshu"])
        if not browser.get("success"):
            return {"success": False, "error": browser.get("error", "浏览器启动失败"), "browser": browser}
        payload = await asyncio.to_thread(self._run_social_worker, "reply_xhs", {"url": str(url or "").strip(), "text": str(text or "").strip(), "target_comment_id": str(target_comment_id or "").strip()})
        return {**payload, "browser": browser}

    async def _run_social_autopilot_fallback(self, state=None, workspace=None):
        now = datetime.now()
        mentions = (((workspace or {}).get("xiaohongshu") or {}).get("mentions_items") or [])[:6]
        for item in mentions:
            if bool(item.get("note_deleted")):
                continue
            target_url = str(item.get("note_url", "") or "").strip()
            target_comment_id = str(item.get("comment_id", "") or "").strip()
            if not target_url or target_url in ((state or {}).get("recent_reply_urls", []) or []):
                continue
            reply_text = self._compose_persona_xhs_reply(item)
            result = await self.reply_to_xhs_comment(target_url, reply_text, target_comment_id)
            if result.get("success"):
                state["last_action_at"] = now.isoformat()
                state["last_action_type"] = "reply_xhs"
                state["recent_reply_urls"] = self._mark_recent_items(state.get("recent_reply_urls", []), target_url, limit=20)
            return {"type": "reply_xhs", "target": item, "result": result}
        reply_handles = self._social_reply_handles()
        candidate_posts = []
        for handle in reply_handles:
            posts = await self.fetch_x_profile_posts(handle, count=1)
            for post in posts[:1]:
                url = str(post.get("url", "") or "").strip()
                if not url or url in ((state or {}).get("recent_reply_urls", []) or []):
                    continue
                candidate_posts.append(post)
        candidate_posts = self._dedupe_social_items(candidate_posts, limit=6, unique_handles=True)
        post_weight = max(0, min(100, _safe_int(os.getenv("OPS_SOCIAL_POST_WEIGHT", "45"), 45)))
        reply_weight = max(0, min(100, _safe_int(os.getenv("OPS_SOCIAL_REPLY_WEIGHT", "55"), 55)))
        do_reply = bool(candidate_posts) and (not state.get("last_action_at") or random.randint(1, post_weight + reply_weight) > post_weight)
        if do_reply:
            target = random.choice(candidate_posts)
            reply_text = self._compose_persona_x_reply(target)
            result = await self.reply_to_x_post(str(target.get("url", "") or ""), reply_text)
            if result.get("success"):
                state["last_action_at"] = now.isoformat()
                state["last_action_type"] = "reply_x"
                state["recent_reply_urls"] = self._mark_recent_items(state.get("recent_reply_urls", []), str(target.get("url", "") or ""), limit=20)
            return {"type": "reply_x", "target": target, "result": result}
        result = await self.autopost_hot_content(platform="x")
        topic = str(result.get("topic", "") or "").strip()
        if result.get("success"):
            state["last_action_at"] = now.isoformat()
            state["last_action_type"] = "post_x"
            if topic:
                state["recent_post_topics"] = self._mark_recent_items(state.get("recent_post_topics", []), topic, limit=12)
        return {"type": "post_x", "result": result}

    async def reply_to_x_post(self, url=None, text=None):
        browser = await asyncio.to_thread(self.ensure_social_browser, ["x"])
        if not browser.get("success"):
            return {"success": False, "error": browser.get("error", "浏览器启动失败"), "browser": browser}
        payload = await asyncio.to_thread(self._run_social_worker, "reply_x", {"url": str(url or "").strip(), "text": str(text or "").strip()})
        return {**payload, "browser": browser}

    async def research_trending_topics(self):
        tavily_key = os.getenv("TAVILY_API_KEY", "")
        if not tavily_key:
            return []
        try:
            import requests as _req
            topics = []
            for q in ["AI agent 最新动态 2026", "OpenClaw AI trending"]:
                resp = _req.post("https://api.tavily.com/search", json={"api_key": tavily_key, "query": q, "max_results": 3, "search_depth": "basic", "include_answer": True}, timeout=15)
                if resp.status_code == 200:
                    for r in resp.json().get("results", [])[:3]:
                        title = r.get("title", "")
                        if title and len(title) < 60:
                            topics.append(title)
            return topics[:8]
        except Exception as e:
            logger.debug(f"Tavily trending failed: {e}")
            return []

    def _ensure_post_tracking_table(self):
        try:
            with self._conn() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS social_post_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, url TEXT UNIQUE,
                    topic TEXT DEFAULT '', content TEXT DEFAULT '', published_at TEXT,
                    likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0,
                    views INTEGER DEFAULT 0, last_checked TEXT, checked_count INTEGER DEFAULT 0)""")
        except Exception as e:
            logger.error(f"[ExecutionHub] social_post_tracking 表创建失败: {e}")

    def _record_post_publish(self, platform, url, topic="", content=""):
        self._ensure_post_tracking_table()
        try:
            with self._conn() as conn:
                conn.execute("INSERT OR IGNORE INTO social_post_tracking(platform,url,topic,content,published_at) VALUES(?,?,?,?,?)",
                    (platform, url, topic, content[:500], datetime.now().isoformat()))
        except Exception as e:
            logger.debug(f"record post failed: {e}")

    def get_post_performance_report(self, days=7):
        self._ensure_post_tracking_table()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            with self._conn() as conn:
                rows = conn.execute("SELECT platform,COUNT(*),SUM(likes),SUM(comments),SUM(views) FROM social_post_tracking WHERE published_at>? GROUP BY platform", (cutoff,)).fetchall()
                top = conn.execute("SELECT platform,url,topic,likes,comments,views FROM social_post_tracking WHERE published_at>? ORDER BY likes+comments DESC LIMIT 5", (cutoff,)).fetchall()
            by_platform = {r[0]: {"posts": r[1], "likes": r[2] or 0, "comments": r[3] or 0, "views": r[4] or 0} for r in rows}
            top_posts = [{"platform": r[0], "url": r[1], "topic": r[2], "likes": r[3], "comments": r[4], "views": r[5]} for r in top]
            return {"success": True, "days": days, "by_platform": by_platform, "top_posts": top_posts}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def generate_content_calendar(self, days=7):
        persona = self.get_social_persona_summary()
        trending = await self.research_trending_topics()
        state = self._load_social_operator_state()
        recent = state.get("recent_post_topics", [])
        prompt = f"为人设'{persona.get('name','')} - {persona.get('headline','')}'规划{days}天内容日历。近期已发：{','.join(recent[-10:])}。热点：{','.join(trending) if trending else '无'}。每天2-3篇X和小红书交替。输出JSON数组：[{{\"day\":1,\"platform\":\"x|xhs\",\"time\":\"08:30\",\"topic\":\"话题\",\"hook\":\"创意概要\"}}]"
        result = await self._call_social_ai(prompt)
        if result.get("success"):
            raw = result.get("raw", "")
            import re as _re
            m = _re.search(r'\[.*\]', raw, _re.DOTALL)
            if m:
                try:
                    from json_repair import loads as jloads
                    return {"success": True, "calendar": jloads(m.group()), "trending": trending}
                except Exception:
                    pass
        return {"success": False, "error": "AI calendar generation failed"}

    async def run_social_autopilot_once(self):
        state = self._load_social_operator_state()
        now = datetime.now()
        next_action_at = str(state.get("next_action_at", "") or "").strip()
        if next_action_at:
            try:
                if now < datetime.fromisoformat(next_action_at):
                    return {"success": True, "status": "idle", "next_action_at": next_action_at}
            except Exception as e:
                logger.debug("[SocialAutopilot] 解析 next_action_at 失败: %s", e)
        self._ensure_post_tracking_table()
        try:
            trending = await self.research_trending_topics()
            if trending:
                state["_trending_topics"] = trending
        except Exception as e:
            logger.warning("[SocialAutopilot] 热点研究失败: %s", e)
        workspace = await self.collect_social_workspace()
        if workspace.get("success"):
            profile_lines = (((workspace.get("xiaohongshu") or {}).get("profile") or {}).get("lines") or [])
            today = now.strftime("%Y-%m-%d")
            last_sync = str(state.get("last_profile_sync_at", "") or "")[:10]
            if last_sync != today and (not profile_lines or any("还没有简介" in line or "Carven" in line for line in profile_lines[:6])):
                sync_ret = await self.update_xhs_persona_profile()
                if sync_ret.get("success"):
                    state["last_profile_sync_at"] = now.isoformat()
                    workspace = await self.collect_social_workspace()
        fresh_metrics = self._latest_social_metrics_if_fresh(max_age_minutes=max(60, _safe_int(os.getenv("OPS_SOCIAL_METRICS_INTERVAL_MIN", "60"), 60)))
        metrics = {"success": True, "metrics": fresh_metrics, "delta": {}, "metric_path": str(self._social_metrics_path())} if fresh_metrics else await self.collect_social_metrics()
        ai_enabled = os.getenv("OPS_SOCIAL_AI_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        action = {}
        ai_payload = {}
        if ai_enabled:
            prompt = self._build_social_operator_prompt(workspace if workspace.get("success") else {}, state)
            ai_call = await self._call_social_ai(prompt)
            parsed = self._extract_json_object(ai_call.get("raw", "")) if ai_call.get("success") else None
            if parsed and isinstance(parsed.get("action"), dict):
                ai_payload = parsed
                spec = parsed.get("action", {}) or {}
                atype = str(spec.get("type", "observe") or "observe").strip().lower()
                if atype == "reply_x" and str(spec.get("target_url", "") or "").strip() and str(spec.get("text", "") or "").strip():
                    result = await self.reply_to_x_post(str(spec["target_url"]), str(spec["text"]))
                    if result.get("success"):
                        state["last_action_at"] = now.isoformat()
                        state["last_action_type"] = "reply_x"
                        state["recent_reply_urls"] = self._mark_recent_items(state.get("recent_reply_urls", []), str(spec["target_url"]), limit=20)
                    action = {"type": "reply_x", "plan": parsed, "result": result}
                elif atype == "reply_xhs" and str(spec.get("target_url", "") or "").strip() and str(spec.get("text", "") or "").strip():
                    result = await self.reply_to_xhs_comment(str(spec["target_url"]), str(spec["text"]), str(spec.get("target_comment_id", "") or ""))
                    if result.get("success"):
                        state["last_action_at"] = now.isoformat()
                        state["last_action_type"] = "reply_xhs"
                        state["recent_reply_urls"] = self._mark_recent_items(state.get("recent_reply_urls", []), str(spec["target_url"]), limit=20)
                    action = {"type": "reply_xhs", "plan": parsed, "result": result}
                elif atype == "post_x" and str(spec.get("text", "") or "").strip():
                    result = await self.publish_persona_x(str(spec["text"]))
                    if result.get("success"):
                        state["last_action_at"] = now.isoformat()
                        state["last_action_type"] = "post_x"
                        topic = str(spec.get("topic", "") or "").strip()
                        if topic:
                            state["recent_post_topics"] = self._mark_recent_items(state.get("recent_post_topics", []), topic, limit=12)
                    action = {"type": "post_x", "plan": parsed, "result": result}
                elif atype == "post_xhs" and str(spec.get("title", "") or "").strip() and str(spec.get("body", "") or "").strip():
                    result = await self.publish_persona_xhs(str(spec["title"]), str(spec["body"]))
                    if result.get("success"):
                        state["last_action_at"] = now.isoformat()
                        state["last_action_type"] = "post_xhs"
                        topic = str(spec.get("topic", "") or "").strip()
                        if topic:
                            state["recent_post_topics"] = self._mark_recent_items(state.get("recent_post_topics", []), topic, limit=12)
                    action = {"type": "post_xhs", "plan": parsed, "result": result}
                else:
                    action = {"type": "observe", "plan": parsed, "result": {"success": True, "status": "observe"}}
            else:
                action = await self._run_social_autopilot_fallback(state, workspace)
        else:
            action = await self._run_social_autopilot_fallback(state, workspace)
        if metrics.get("success"):
            state["last_metrics_at"] = str((metrics.get("metrics", {}) or {}).get("timestamp", now.isoformat()) or now.isoformat())
        min_interval = max(30, _safe_int(os.getenv("OPS_SOCIAL_AUTOPILOT_MIN_INTERVAL_MIN", "180"), 180))
        max_interval = max(min_interval, _safe_int(os.getenv("OPS_SOCIAL_AUTOPILOT_MAX_INTERVAL_MIN", "480"), 480))
        next_minutes = random.randint(min_interval, max_interval)
        try:
            ai_next = _safe_int(ai_payload.get("next_check_minutes", 0), 0)
            if ai_next > 0:
                next_minutes = max(min_interval, min(max_interval, ai_next))
        except Exception:
            pass
        state["next_action_at"] = (now + timedelta(minutes=next_minutes)).isoformat()
        state.pop("_trending_topics", None)
        self._save_social_operator_state(state)
        return {"success": True, "status": action.get("type", "observe") if isinstance(action, dict) else "acted", "action": action, "next_action_at": state["next_action_at"]}


    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS social_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, title TEXT,
                body TEXT, topic TEXT, status TEXT DEFAULT 'draft', sources TEXT,
                created_at TEXT, updated_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS monitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT, keyword TEXT,
                source TEXT DEFAULT 'news', enabled INTEGER DEFAULT 1,
                created_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS monitor_seen (
                id INTEGER PRIMARY KEY AUTOINCREMENT, monitor_id INTEGER,
                digest TEXT UNIQUE, seen_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS payout_watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT, repo TEXT,
                issue_number INTEGER, label TEXT,
                status TEXT DEFAULT 'watching', created_at TEXT,
                last_checked_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS payout_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, watch_id INTEGER,
                event_type TEXT, detail TEXT, created_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT,
                priority TEXT DEFAULT 'medium', status TEXT DEFAULT 'pending',
                created_at TEXT, updated_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT,
                remind_at TEXT, status TEXT DEFAULT 'pending',
                created_at TEXT)""")

    
    def triage_email(self, max_messages = None, only_unread = True):
        max_messages = max_messages or 20
        prompt = (
            f"请帮我整理最近 {max_messages} 封{'未读' if only_unread else ''}邮件，"
            "按重要事务、会议协作、系统通知、营销订阅、其他分类，"
            "并列出需要行动的事项。以 JSON 返回: "
            '{"grouped":{}, "highlights":[], "action_items":[]}'
        )
        try:
            result = asyncio.get_event_loop().run_until_complete(
                self._call_social_ai_direct(prompt=prompt)
            )
            if result.get('success'):
                raw = result.get('raw', '')
                parsed = self._extract_json_object(raw)
                if parsed:
                    return {'success': True, 'total': max_messages, 'summary': raw,
                            'action_items': parsed.get('action_items', []),
                            'grouped': parsed.get('grouped', {}),
                            'highlights': parsed.get('highlights', [])}
                return {'success': True, 'total': max_messages, 'summary': raw,
                        'action_items': [], 'grouped': {}, 'highlights': []}
            return {'success': False, 'error': result.get('error', 'AI 调用失败')}
        except Exception as e:
            logger.error(f"[TriageEmail] failed: {e}")
            return {'success': False, 'error': str(e)}

    
    def format_email_triage(self, triage = None):
        if not triage.get('success'):
            return f"邮件整理失败: {triage.get('error', '未知错误')}"
        grouped = triage.get('grouped', { })
        lines = [
            '邮件自动整理',
            '']
        lines.append(f"总计邮件: {triage.get('total', 0)}")
        for cat in ('重要事务', '会议协作', '系统通知', '营销订阅', '其他'):
            lines.append(f'- {cat}: {len(grouped.get(cat, []))}')
        highlights = triage.get('highlights', [])
        if highlights:
            lines.append('\n重点摘要:')
            for i, item in enumerate(highlights[:3], 1):
                subj = item.get('subject', '')
                sender = item.get('from', '')
                lines.append(f"{i}. [{item.get('category', '其他')}] {subj}")
                lines.append(f'   发件人: {sender}')
        return '\n'.join(lines)

    
    async def generate_daily_brief(self):
        paragraphs = []
        # Collect top tasks
        try:
            tasks = self.top_tasks(limit=5)
            if tasks:
                task_lines = []
                for t in tasks:
                    task_lines.append(f"- [{t.get('status','pending')}] {t.get('title','')}")
                paragraphs.append("待办事项:\n" + "\n".join(task_lines))
        except Exception as e:
            logger.debug(f"[DailyBrief] tasks error: {e}")
        # Collect social metrics
        try:
            drafts = self._recent_social_rows(limit=5)
            if drafts:
                paragraphs.append(f"最近社媒草稿: {len(drafts)} 条")
        except Exception as e:
            logger.debug(f"[DailyBrief] social metrics error: {e}")
        # Collect pending monitors
        try:
            if self._monitors:
                paragraphs.append(f"活跃监控: {len(self._monitors)} 个")
        except Exception as e:
            logger.debug(f"[DailyBrief] monitors error: {e}")
        if not paragraphs:
            paragraphs.append("今日暂无待处理事项")
        return format_announcement(title="每日简报", paragraphs=paragraphs)

    
    def build_doc_index(self, roots = None, max_files = None):
        allow_ext = {
            '.go',
            '.js',
            '.md',
            '.py',
            '.sh',
            '.ts',
            '.csv',
            '.ini',
            '.jsx',
            '.log',
            '.rst',
            '.sql',
            '.tsx',
            '.txt',
            '.yml',
            '.conf',
            '.java',
            '.toml',
            '.yaml',
            '.json'}
        indexed = 0
        skipped = 0
        scanned = 0

    
    def search_docs(self, query = None, limit = None):
        query = query or ''
        keyword = str(query or '').strip()
        if not keyword:
            return []
        token = f'{keyword.lower()}%'

    
    def summarize_meeting(self, text = None, file_path = None):
        content = text or ''
        if file_path:
            try:
                content = Path(file_path).read_text(encoding='utf-8')
            except Exception as e:
                return {'success': False, 'error': f'无法读取文件: {e}'}
        if not str(content).strip():
            return {'success': False, 'error': '没有提供会议内容'}
        prompt = (
            "请总结以下会议纪要，提取：1) 摘要 2) 行动事项 3) 关键决策。"
            "以 JSON 返回: {\"summary\":\"...\", \"action_items\":[], \"decisions\":[]}\n\n"
            + str(content).strip()[:4000]
        )
        try:
            result = asyncio.get_event_loop().run_until_complete(
                self._call_social_ai_direct(prompt=prompt)
            )
            if result.get('success'):
                raw = result.get('raw', '')
                parsed = self._extract_json_object(raw)
                if parsed:
                    return {'success': True, 'summary': parsed.get('summary', raw),
                            'action_items': parsed.get('action_items', []),
                            'decisions': parsed.get('decisions', [])}
                return {'success': True, 'summary': raw, 'action_items': [], 'decisions': []}
            return {'success': False, 'error': result.get('error', 'AI 调用失败')}
        except Exception as e:
            logger.error(f"[SummarizeMeeting] failed: {e}")
            return {'success': False, 'error': str(e)}

    
    def add_task(self, title = None, details = None, due_at = None, sources=None, priority=3):
        title = title or ''
        t = str(title or '').strip()
        if not t:
            return {
                'success': False,
                'error': '标题不能为空' }
        p = max(1, min(5, _safe_int(priority, 3)))

    
    def has_open_task(self, title = None, tags = None):
        title = title or ''
        t = str(title or '').strip()
        tags = tags or []
        tg = str(tags or '').strip()
        if not t:
            return False

    
    def update_task_status(self, task_id = None, status = None):
        status = status or ''
        st = str(status or '').strip().lower()
        if st not in frozenset({'done', 'todo', 'doing', 'cancelled'}):
            return {
                'success': False,
                'error': '状态仅支持 todo/doing/done/cancelled' }

    
    def list_tasks(self, status = None):
        status = status or ''
        st = str(status or '').strip().lower()

    
    def top_tasks(self, limit = None):
        limit = limit or 10
        try:
            with self._conn() as conn:
                cursor = conn.execute(
                    "SELECT id, title, priority, status, created_at, updated_at "
                    "FROM tasks WHERE status != 'done' "
                    "ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, "
                    "created_at DESC LIMIT ?", (int(limit),))
                rows = cursor.fetchall()
                return [{'id': r[0], 'title': r[1], 'priority': r[2], 'status': r[3],
                         'created_at': r[4], 'updated_at': r[5]} for r in rows]
        except Exception as e:
            logger.error(f"[TopTasks] failed: {e}")
            return []

    
    async def generate_content_ideas(self, keyword = None, count = None):
        keyword = keyword or 'AI 工具'
        count = count or 5
        prompt = (
            f"请为关键词「{keyword}」生成 {count} 个社交媒体内容选题创意，"
            "每个包含标题和简短描述。以 JSON 数组返回: "
            '[{"title":"...", "description":"..."}]'
        )
        try:
            result = await self._call_social_ai(prompt=prompt)
            if result.get('success'):
                raw = result.get('raw', '')
                parsed = self._extract_json_object(raw)
                if isinstance(parsed, list):
                    return {'success': True, 'ideas': parsed[:count]}
                if isinstance(parsed, dict) and 'ideas' in parsed:
                    return {'success': True, 'ideas': parsed['ideas'][:count]}
                ideas = [line.strip() for line in raw.split('\n') if line.strip()]
                return {'success': True, 'ideas': ideas[:count]}
            return {'success': False, 'ideas': [], 'error': result.get('error', 'AI 调用失败')}
        except Exception as e:
            logger.error(f"[ContentIdeas] failed: {e}")
            return {'success': False, 'ideas': [], 'error': str(e)}

    
    def _social_topic_tags(self, topic = None):
        topic = topic or ''
        tags = []
        if 'AI' in topic or 'ai' in topic:
            tags.extend(['AI', '效率'])
        if 'OpenClaw' in topic:
            tags.extend(['OpenClaw', '自动化'])
        if '出海' in topic:
            tags.extend(['出海', '独立开发'])
        return tags or ['AI', '工具']

    
    def _creator_trend_label(self, topic = None, strategy = None):
        trend_label = strategy.get('trend_label', '')
        if not trend_label:
            topic = topic or ''
        return trend_label or '今日热点'

    
    def _source_title_lines(self, sources=None, limit=1, max_len=18):
        rows = []
        for item in sources[:max(1, int(limit))]:
            title = item.get('title', '')
            source = item.get('source', '')
            if not title:
                continue
            if source:
                rows.append(f'{title}（{source}）')
                continue
            rows.append(title)
        return rows

    
    def _utility_profile(self, topic = None):
        topic = topic or ''
        score = 50
        if 'OpenClaw' in topic:
            score += 30
        if 'AI' in topic or 'Coding' in topic:
            score += 20
        return {
            'utility_score': min(100, score),
            'positioning': f'OpenClaw 实战视角解读 {topic}',
            'audience': '独立开发者和AI工具爱好者',
            'cta': '评论区告诉我你最想了解什么',
            'measurement_window': '48h',
            'validation_metrics': ['收藏率', '评论数', '转发数'] }

    
    def _score_practical_value(self, topic = None, insights = None, sources=None):
        score = 30
        topic_str = str(topic or '').lower()
        keywords_high = ['openclaw', 'ai coding', 'agent', 'copilot', 'gpt', 'llm', 'prompt']
        keywords_mid = ['开发', '编程', '自动化', 'api', 'workflow', '工具']
        for kw in keywords_high:
            if kw in topic_str:
                score += 15
        for kw in keywords_mid:
            if kw in topic_str:
                score += 8
        if insights:
            insight_text = str(insights).lower()
            if '实战' in insight_text or 'tutorial' in insight_text:
                score += 10
            if '趋势' in insight_text or 'trend' in insight_text:
                score += 5
        if sources:
            score += min(20, len(sources) * 4)
        return min(100, max(0, score))

    
    def _topic_slug(self, topic = None):
        topic = topic or ''
        text = re.sub('[^0-9A-Za-z\\u4e00-\\u9fff]+', '-', str(topic).strip()).strip('-')
        if not text[:48]:
            text = text[:48]
        return text or 'topic'

    
    def _topic_memory_path(self, topic = None):
        return Path(self.social_learning_dir) / f'{self._topic_slug(topic)}.json'

    
    def load_topic_memory(self, topic = None):
        path = self._topic_memory_path(topic)
        if not path.exists():
            return {
                'topic': topic,
                'runs': [],
                'strategy': { },
                'last_updated': '' }
        return json.loads(path.read_text(encoding = 'utf-8'))

    
    def save_topic_memory(self, topic = None, payload = None):
        path = self._topic_memory_path(topic)
        path.write_text(json.dumps(payload, ensure_ascii = False, indent = 2), encoding = 'utf-8')

    
    def _run_social_worker(self, action = None, payload = None):
        worker = Path(self.repo_root) / 'scripts' / 'social_browser_worker.py'
        max_retries = 2 if action and 'publish' in str(action) else 1
        last_err = None
        for attempt in range(max_retries):
            try:
                cp = subprocess.run([
                    'python3',
                    str(worker),
                    action,
                    json.dumps(payload, ensure_ascii = False)], check = False, capture_output = True, text = True, timeout = 300)
                if cp.returncode != 0:
                    last_err = {
                        'success': False,
                        'error': 'worker exited {}'.format(cp.returncode),
                        'stderr': str(cp.stderr or '').strip(),
                        'stdout': str(cp.stdout or '').strip() }
                    if attempt < max_retries - 1:
                        logger.warning("[SocialWorker] %s 失败(attempt %d)，重试中...", action, attempt + 1)
                        time.sleep(3)
                        continue
                    return last_err
                stdout = str(cp.stdout or '').strip()
                if not stdout:
                    last_err = {
                        'success': False,
                        'error': 'worker produced no output' }
                    if attempt < max_retries - 1:
                        time.sleep(3)
                        continue
                    return last_err
                data = json.loads(stdout)
                if isinstance(data, dict):
                    data.setdefault('success', True)
                    return data
                return {
                    'success': False,
                    'error': 'worker 输出不是对象' }
            except subprocess.TimeoutExpired:
                last_err = {'success': False, 'error': f'worker 超时 (action={action})'}
                logger.warning("[SocialWorker] %s 超时(attempt %d)", action, attempt + 1)
            except json.JSONDecodeError as e:
                last_err = {'success': False, 'error': f'worker 输出解析失败: {e}'}
                logger.warning("[SocialWorker] %s JSON解析失败: %s", action, e)
            except Exception as e:
                last_err = {'success': False, 'error': str(e)}
                logger.warning("[SocialWorker] %s 异常(attempt %d): %s", action, attempt + 1, e)
            if attempt < max_retries - 1:
                time.sleep(3)
        return last_err or {'success': False, 'error': 'unknown'}

    
    def _social_browser_targets(self, platforms = None):
        platforms = platforms or ''

    
    def _social_browser_missing_logins(self, browser = None, platforms = None):
        targets = self._social_browser_targets(platforms)
        missing = []
        if 'x' in targets and browser.get('x_ready') is False:
            missing.append('x')
        if 'xiaohongshu' in targets and browser.get('xiaohongshu_ready') is False:
            missing.append('xiaohongshu')
        return missing

    
    def _social_browser_login_error(self, platforms = None, browser = None):
        missing = self._social_browser_missing_logins(browser, platforms)
        if not missing:
            return 'OpenClaw 专用浏览器未准备就绪，已自动拉起页面，请稍后重试'

    
    def ensure_social_browser(self, platforms = None):
        return self._run_social_worker('bootstrap', {
            'platforms': self._social_browser_targets(platforms) })

    
    def get_social_browser_status(self, start = None, platforms = None):
        payload = {
            'start': bool(start) }
        targets = self._social_browser_targets(platforms)
        if targets:
            payload['platforms'] = targets
        return self._run_social_worker('status', payload)

    
    def _derive_topic_strategy(self, topic = None, research = None, sources=None):
        research = research or {}
        insights = research.get('insights', {})
        prior_runs = research.get('runs', [])
        selected_sources = self._dedupe_social_items(self._select_topic_sources(topic, research, limit=5), limit=5, unique_handles=False)
        source_count = len(research.get('xiaohongshu', []) or [])
        tags = self._social_topic_tags(topic)
        utility = self._utility_profile(topic) or {}
        style_id = len(prior_runs) % 3
        opening = '先说结论，再拆结构，再给动作，避免泛泛谈趋势。'
        if topic and '出海' in topic:
            opening = '先说能不能落地，再讲工具和趋势，别空聊概念。'
        if topic and ('AI' in topic or '智能体' in topic):
            opening = '先给真实场景，再给工具栈和动作，不讲空泛未来学。'
        strategy = {
            'topic': topic,
            'style_id': style_id,
            'trend_label': insights.get('hooks', [''])[0] if insights.get('hooks') else (topic or '今日热点'),
            'opening_rule': opening,
            'tags': tags,
            'utility_score': utility.get('utility_score', 50),
            'positioning': utility.get('positioning', ''),
            'audience': utility.get('audience', ''),
            'cta': utility.get('cta', ''),
            'measurement_window': utility.get('measurement_window', '48h'),
            'validation_metrics': utility.get('validation_metrics', []),
            'x_tactic': '去头部账号评论区做高价值回复',
            'xhs_tactic': '写成可收藏的实操清单',
            'lead_magnet': '资料包、模板或 SOP',
            'selected_sources': selected_sources,
        }
        strategy = self._apply_social_persona(strategy, topic)
        return strategy

    
    def _select_topic_sources(self, topic = None, study = None, limit=5):
        return []

    
    def _social_source_weight(self, source = None):
        source_str = str(source or '').strip().lower()
        high = ['infoq', '51cto', 'github', 'arxiv', 'huggingface']
        low = ['cnbeta', 'it之家', 'ithome', '快科技']
        for s in high:
            if s in source_str:
                return 0.9
        for s in low:
            if s in source_str:
                return 0.3
        return 0.5

    
    def _clean_hot_trend_items(self, items = None, limit = None):
        items = items or []
        limit = limit or 20
        seen = set()
        cleaned = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get('title', '')).strip()
            if not title:
                continue
            normalized = re.sub(r'\s+', ' ', title).strip().lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            item['title'] = title
            cleaned.append(item)
        return cleaned[:max(1, int(limit))]

    
    def _hot_social_plans(self):
        return [
            {
                'id': 'openclaw_coding',
                'query': 'GitHub Copilot GPT-5.4',
                'topic': 'OpenClaw AI Coding 实战',
                'trend_label': 'GitHub Copilot + GPT-5.4',
                'hook': '今天大家都在聊 GitHub Copilot 接上 GPT-5.4，但更值得蹭的是：怎么把模型升级变成稳定的 OpenClaw 工作流。',
                'practical_focus': '把热点从模型新闻改写成团队级 AI Coding 实战教程。',
                'tutorial_steps': [
                    '先把今天的热搜事件压成一个真实开发场景',
                    '再用 OpenClaw 把分工、执行、验证串成闭环',
                    '最后给出一套小白也能直接照抄的操作顺序'],
                'tags': [
                    'OpenClaw',
                    'AICoding',
                    'GPT54',
                    'Copilot'],
                'boost': 14 },
            {
                'id': 'openclaw_agent',
                'query': 'AI Agent workflow',
                'topic': 'OpenClaw Agent 工作流',
                'trend_label': 'AI Agent 工作流',
                'hook': 'AI Agent 这波流量能蹭，但不要再空谈概念，直接把它讲成 OpenClaw 的可执行工作流才有传播力。',
                'practical_focus': '围绕任务拆解、并行执行、交叉验证，输出能直接上手的 Agent 实操教程。',
                'tutorial_steps': [
                    '先讲一个真实任务入口，比如群聊协作或内容生产',
                    '再拆成客服接单、选方案、专家复核、并行执行四步',
                    '最后补上评分迭代和避坑提醒'],
                'tags': [
                    'OpenClaw',
                    'Agent',
                    'Workflow',
                    'AI'],
                'boost': 13 },
            {
                'id': 'openclaw_hot',
                'query': 'OpenClaw',
                'topic': 'OpenClaw 实用教程',
                'trend_label': 'OpenClaw 热搜',
                'hook': 'OpenClaw 本身就在热点里，最容易出效果的不是新闻搬运，而是手把手把功能讲到能立刻用。',
                'practical_focus': '围绕真实场景、避坑和结果展示，做强教程感和实用性。',
                'tutorial_steps': [
                    '先给一个今天就能复现的使用场景',
                    '再讲最短操作路径和常见报错怎么避开',
                    '最后补上适合谁用、什么时候别用'],
                'tags': [
                    'OpenClaw',
                    'AI工具',
                    '教程',
                    '效率'],
                'boost': 12 },
            {
                'id': 'openclaw_claude',
                'query': 'Claude workflow',
                'topic': 'OpenClaw Claude 协同流',
                'trend_label': 'Claude 工作流',
                'hook': 'Claude 相关热度高时，最容易起量的角度不是模型参数，而是它在 OpenClaw 里到底负责哪一段最值钱。',
                'practical_focus': '把 Claude 在复杂任务总控、代码审查和交叉验证里的角色讲清楚。',
                'tutorial_steps': [
                    '先讲什么任务该交给 Claude 总控',
                    '再讲和 Qwen / DeepSeek / Codex 怎么分工',
                    '最后讲如何降低成本避免无效调用'],
                'tags': [
                    'OpenClaw',
                    'Claude',
                    'Workflow',
                    'AI协作'],
                'boost': 11 },
            {
                'id': 'openclaw_saas',
                'query': 'SaaS 出海 AI',
                'topic': 'OpenClaw 出海内容流',
                'trend_label': 'AI / SaaS 出海',
                'hook': 'AI 出海能发，但更容易被收藏的内容，是用 OpenClaw 把选题、监控和发文流程做成一个出海内容流水线。',
                'practical_focus': '把热点翻成监控、选题、发文三段式方法，而不是泛聊趋势。',
                'tutorial_steps': [
                    '先用监控抓到可讲的新信号',
                    '再选一个对用户有用的切口重写',
                    '最后同步产出 X 和小红书两版内容'],
                'tags': [
                    'OpenClaw',
                    '出海',
                    '内容工作流',
                    'AI'],
                'boost': 9 }]

    
    async def discover_hot_social_topics(self, limit = None):
        limit = limit or 3
        plans = self._hot_social_plans()
        candidates = []
        for plan in plans[:limit]:
            query = plan.get('query', '')
            items = await self.news_fetcher.fetch_from_google_news_rss(query, count=5)
            curated = self._curate_monitor_items(items or [], limit=3)
            utility = self._utility_profile(plan.get('topic', ''))
            candidates.append({
                'topic': plan.get('topic', ''),
                'trend_label': plan.get('trend_label', ''),
                'utility_score': utility.get('utility_score', 50) + plan.get('boost', 0),
                'items': curated,
                'plan': plan,
            })
        candidates.sort(key=lambda c: c.get('utility_score', 0), reverse=True)
        return {
            'success': True,
            'candidates': candidates[:limit],
        }

    
    def _recent_social_rows(self, limit = None):
        limit = limit or 24
        return list(self._draft_store[-limit:])

    
    def _tokenize_social_text(self, text = None):
        text = text or ''
        value = re.sub('\\s+', ' ', str(text).strip().lower())
        value = re.sub('[^0-9a-z\\u4e00-\\u9fff]+', ' ', value)
        return value.split()

    
    def _text_overlap_ratio(self, left = None, right = None):
        left_tokens = set(self._tokenize_social_text(left) or [])
        right_tokens = set(self._tokenize_social_text(right) or [])
        if not left_tokens or not right_tokens:
            return 0
        return len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))

    
    def _detect_recent_social_duplicate(self, platform = None, title = None, body = None, topic=None, lookback_hours=24):
        platform = platform or 'both'
        target_platform = str(platform or '').strip().lower()
        norm_title = self._normalize_monitor_text(title)
        norm_body = self._normalize_monitor_text(body)
        norm_topic = self._normalize_monitor_text(topic)
        now = datetime.now()
        for row in self._recent_social_rows(limit=24):
            if target_platform and target_platform != 'both':
                row_platform = str(row.get('platform', '')).strip().lower()
                if row_platform != target_platform:
                    continue
            updated_at = row.get('updated_at', '')
            try:
                age_hours = (now - datetime.fromisoformat(updated_at)).total_seconds() / 3600
            except (ValueError, TypeError):
                continue
            if age_hours > max(1, int(lookback_hours)):
                continue
            row_title = row.get('title', '')
            row_body = row.get('body', '')
            row_topic = row.get('topic', '')
            row_norm_title = self._normalize_monitor_text(row_title)
            row_norm_body = self._normalize_monitor_text(row_body)
            row_norm_topic = self._normalize_monitor_text(row_topic)
            same_title = bool(norm_title and norm_title == row_norm_title)
            same_topic = bool(norm_topic and norm_topic == row_norm_topic)
            same_prefix = bool(norm_body and row_norm_body and norm_body[:96] == row_norm_body[:96])
            overlap = self._text_overlap_ratio(body, row_body)
            if same_title or (same_prefix and overlap >= 0.86):
                return {
                    'duplicate': True,
                    'reason': '与最近的 {} 草稿过于相似'.format(row.get('platform', '')),
                    'existing': row }
            if same_topic and overlap >= 0.72:
                return {
                    'duplicate': True,
                    'reason': '与最近的 {} 草稿过于相似'.format(row.get('platform', '')),
                    'existing': row }
        return {
            'duplicate': False }

    
    def _dedupe_social_items(self, items = None, limit = None, unique_handles=False):
        primary = []
        secondary = []
        seen_titles = set()
        seen_handles = set()
        items = items or []
        limit = limit or 10
        for item in items:
            title = item.get('title', '')
            key = self._normalize_monitor_text(title)
            if not key or key in seen_titles:
                continue
            seen_titles.add(key)
            handle = item.get('handle', '')
            payload = dict(item)
            if unique_handles and handle:
                if handle in seen_handles:
                    secondary.append(payload)
                    continue
                seen_handles.add(handle)
            primary.append(payload)
        merged = list(primary)
        if unique_handles and len(merged) < max(1, int(limit)):
            for item in secondary:
                merged.append(item)
                if not len(merged) >= max(1, int(limit)):
                    continue
                secondary
        return merged[:max(1, int(limit))]

    
    def _build_hot_candidate_strategy(self, candidate = None, memory = None):
        runs = memory.get('runs', [])
        topic_text = candidate.get('topic', 'OpenClaw 实用教程')
        utility = self._utility_profile(topic_text)
        items = candidate.get('items', [])

    
    def _compose_persona_x_post(self, topic = None, strategy = None, sources=None):
        trend_label = self._creator_trend_label(topic, strategy)
        style_id = strategy.get('style_id', 0)
        persona_name = strategy.get('persona_name', '代码写累了') or '代码写累了'
        x_tactic = shorten(strategy.get('x_tactic', '去评论区做高价值回复') or '去评论区做高价值回复', 22)
        question = (strategy.get('persona_signature_question', '你们平时用AI最多的场景是什么？') or '你们平时用AI最多的场景是什么？').strip()
        x_hashtags = (strategy.get('persona_x_hashtags') or ['#BuildInPublic', '#AITools'])[:2]
        variants = [
            [
                f'说实话，「{trend_label}」这个话题我研究了一下，有点东西。',
                '',
                '作为一个每天都在用AI写代码的人，我的看法是：',
                f'先把热点翻译成人话，再{x_tactic}。',
                '不贩卖焦虑，只说真实体验。'],
            [
                f'又一个AI热点：「{trend_label}」。',
                '',
                '别被标题党骗了，我来说说实际体验。',
                '先观察，先验证，不急着下结论。',
                f'免费号别等 For You，我会先{x_tactic}。'],
            [
                f'深夜写代码的时候刷到「{trend_label}」。',
                '作为一个沉迷用AI偷懒的程序员，忍不住说两句。',
                '先做人话，再做观点。',
                f'免费号别等 For You，我先{x_tactic}。']]
        source_lines = self._source_title_lines(sources, limit=1, max_len=34)
        lines = list(variants[style_id])
        if source_lines and style_id != 2:
            lines.extend([
                '',
                f'今天先看：{source_lines[0]}'])
        lines.extend([
            '',
            question,
            ' '.join(x_hashtags)])
        return '\n'.join(lines)[:278]

    
    def _compose_persona_xhs_article(self, topic = None, strategy = None, sources=None):
        trend_label = self._creator_trend_label(topic, strategy)
        trend_label = trend_label or ''
        topic = topic or ''
        topic_short = shorten('OpenClaw', 12)
        style_id = strategy.get('style_id', 0)
        persona_name = strategy.get('persona_name', '代码写累了') or '代码写累了'
        persona_truth = (strategy.get('persona_truth', '一个真正在用AI改变生活的95后理工男，不卖课不割韭菜，只分享真实体验。') or '一个真正在用AI改变生活的95后理工男，不卖课不割韭菜，只分享真实体验。').strip()
        persona_background = (strategy.get('persona_background', '程序员/独立开发者，健身第3年，咖啡不加糖。') or '程序员/独立开发者，健身第3年，咖啡不加糖。').strip()
        x_tactic = (strategy.get('x_tactic', '去评论区做高价值回复') or '去评论区做高价值回复').strip()
        question = (strategy.get('persona_signature_question', '你们平时用AI最多的场景是什么？') or '你们平时用AI最多的场景是什么？').strip()
        xhs_topics = strategy.get('persona_xhs_topics') or ['#AI工具', '#效率提升', '#程序员日常', '#独立开发']
        source_lines = self._source_title_lines(sources, limit = 3, max_len = 36)
        title_options = [
            '说实话，这个功能我用了一周才搞明白',
            '程序员用AI偷懒的正确姿势',
            '别被标题党骗了，{topic_short}真相是这样']
        opening_blocks = [
            [
                f'说实话，{persona_truth}',
                '',
                f'{persona_background}',
                f'今天想聊聊「{trend_label}」这个话题，分享一下我的真实体验。'],
            [
                '别被标题党骗了。',
                '作为一个每天都在用AI的程序员，我想说点不一样的。',
                '',
                f'{persona_background}',
                f'关于「{trend_label}」，我的看法可能会得罪一些人。'],
            [
                f'深夜写代码的时候，突然想聊聊「{trend_label}」。',
                '',
                f'{persona_truth}',
                '所以关于这个话题，我只说真实体验，不贩卖焦虑。']]
        body_lines = list(opening_blocks[style_id])
        body_lines.extend([
            '',
            f'今天我拿"{trend_label}"这件事继续练表达。',
            '我会先做 3 件事：',
            '1）把热点翻译成人话，不复读新闻',
            f'2）{x_tactic}',
            '3）再改成一篇能被收藏的小红书笔记，先看收藏率和真实评论',
            '',
            '我最近真正想学会的，其实是这些事：',
            '- 什么样的表达会让人觉得不是在背模板',
            '- 什么工具真正提升了效率，什么是噱头',
            '- 为什么有些方法论听着对但实际没用'])
        if source_lines:
            body_lines.extend([
                '',
                '今天让我停下来的几个点：'])
            for idx, line in enumerate(source_lines, 1):
                body_lines.append(f'{idx}）{line}')
        body_lines.extend([
            '',
            '后续我会继续分享：',
            '- 我今天实测了什么',
            '- 踩了什么坑',
            '- 哪些方法真正省了时间',
            '',
            question,
            '',
            ' '.join(xhs_topics[:4])])
        return {
            'title': title_options[style_id][:20],
            'body': '\n'.join(body_lines)
        }

    
    def _build_hot_x_post(self, candidate = None, strategy = None, sources=None):
        if strategy.get('persona_id'):
            return self._compose_persona_x_post(str(strategy.get('topic', '')), strategy, sources)
        trend_label = strategy.get('trend_label', '今日热点')
        source_title = self._source_title_lines(sources, limit = 1, max_len = 34)
        x_tactic = strategy.get('x_tactic', '去头部账号评论区做高价值回复')
        lead_magnet = strategy.get('lead_magnet', '资料包')
        lines = [
            f'今天都在聊「{trend_label}」，但对免费号最危险的错觉，是等系统自己给流量。',
            '',
            '2026 的 X 没开 Premium，就别幻想 For You 自然触达。',
            '我现在会用 OpenClaw 这样蹭热点：',
            '1. 把热搜压成一个 MVP 选题',
            f'2. {x_tactic}',
            '3. 再把同题改成小红书教程，优先抢收藏率']
        if source_title:
            lines.extend([
                '',
                f'今天先借这条起势：{source_title[0]}'])
        lines.extend([
            '',
            f'主页置顶放{lead_magnet}，先验证 PMF，再决定买会员还是投流。',
            '#OpenClaw #内容增长'])
        return '\n'.join(lines)[:278]

    
    def _build_hot_xhs_title(self, candidate = None, strategy = None):
        if strategy.get('persona_id'):
            return self._compose_persona_xhs_article(str(strategy.get('topic', '')), strategy, [])['title']
        trend_label = strategy.get('trend_label', '今日热点')
        options = [
            f'{trend_label}，别只复述热点',
            f'OpenClaw 冷启动：这样借{trend_label}起量',
            f'不买会员，怎么借{trend_label}涨粉']
        return options[int(strategy.get('style_id', 0) or 0) % len(options)][:20]

    
    def _build_hot_xhs_body(self, candidate = None, strategy = None, sources=None):
        if strategy.get('persona_id'):
            return self._compose_persona_xhs_article(str(strategy.get('topic', '')), strategy, sources)['body']
        trend_label = strategy.get('trend_label', '今日热点')
        lead_magnet = strategy.get('lead_magnet', '资料包、模板或 SOP')
        cta = strategy.get('cta', '引导用户评论或私信领取资料')

    
    def _build_social_render_payload(self, topic = None, strategy = None, sources=None):
        return {
            'topic': topic,
            'picks': sources[:5],
            'insights': {
                'patterns': [
                    '热点切角',
                    '实用教程',
                    '步骤落地'],
                'hooks': [
                    strategy.get('trend_label', '今日热点')],
                'opportunity': strategy.get('practical_focus', '把热点改写成可执行教程。') } }

    
    def _find_matching_hot_candidate(self, topic = None, candidates = None):
        topic = topic or ''
        candidates = candidates or []
        if not topic or not candidates:
            return None
        topic_tokens = set(self._tokenize_social_text(topic))
        if not topic_tokens:
            return None
        best = None
        best_score = 0
        for c in candidates:
            c_topic = c.get('topic', '') or c.get('trend_label', '')
            c_tokens = set(self._tokenize_social_text(c_topic))
            if not c_tokens:
                continue
            overlap = len(topic_tokens & c_tokens)
            score = overlap / max(1, min(len(topic_tokens), len(c_tokens)))
            if score > best_score:
                best_score = score
                best = c
        return best if best_score > 0 else None

    
    async def select_hot_social_candidate(self, topic = None, prefer_openclaw = None):
        discovery = await self.discover_hot_social_topics(limit=5)
        candidates = discovery.get('candidates', [])
        if not candidates:
            return {'success': False, 'error': '没有发现热门话题'}
        if prefer_openclaw:
            for c in candidates:
                c['utility_score'] = c.get('utility_score', 0) + (
                    10 if 'openclaw' in (c.get('topic', '') or '').lower() else 0
                )
            candidates.sort(key=lambda c: c.get('utility_score', 0), reverse=True)
        if topic:
            match = self._find_matching_hot_candidate(topic, candidates)
            if match:
                return {'success': True, 'candidate': match}
        return {'success': True, 'candidate': candidates[0]}

    
    async def create_hot_social_package(self, platform = None, topic = None):
        try:
            discovery = await self.discover_hot_social_topics(limit=3)
            if not discovery.get('success') or not discovery.get('candidates'):
                return {'success': False, 'error': '没有发现热门话题'}
            candidate = discovery['candidates'][0]
            hot_topic = topic or candidate.get('topic', '')
            research = {
                'x': candidate.get('items', []),
                'xiaohongshu': candidate.get('items', []),
                'insights': {
                    'patterns': ['教程', 'SOP'],
                    'hooks': [candidate.get('trend_label', '')],
                    'opportunity': candidate.get('plan', {}).get('practical_focus', ''),
                },
                'runs': [],
            }
            strategy = self._derive_topic_strategy(hot_topic, research, research)
            sources = candidate.get('items', [])
            x_body = self._compose_human_x_post(hot_topic, strategy, sources)
            xhs_result = self._compose_human_xhs_article(hot_topic, strategy, sources)
            xhs_body = xhs_result.get('body', '') if isinstance(xhs_result, dict) else str(xhs_result or '')
            xhs_title = xhs_result.get('title', '') if isinstance(xhs_result, dict) else ''
            x_draft = self.save_social_draft('x', '', x_body, topic=hot_topic)
            xhs_draft = self.save_social_draft('xiaohongshu', xhs_title, xhs_body, topic=hot_topic)
            return {
                'success': True, 'topic': hot_topic, 'strategy': strategy,
                'results': {
                    'x': {'success': True, 'body': x_body,
                           'draft_id': x_draft.get('draft_id', 0) if x_draft else 0},
                    'xiaohongshu': {'success': True, 'body': xhs_body, 'title': xhs_title,
                                     'draft_id': xhs_draft.get('draft_id', 0) if xhs_draft else 0},
                },
            }
        except Exception as e:
            logger.error(f"[CreateHotPackage] failed: {e}")
            return {'success': False, 'error': str(e)}

    
    def _publish_social_package(self, package = None):
        platform_name = package.get('platform', '')
        if platform_name == 'xiaohongshu':
            published = self._run_social_worker('publish_xhs', {
                'title': package.get('title', ''),
                'body': package.get('body', ''),
                'images': package.get('images', []) })
        else:
            published = self._run_social_worker('publish_x', {
                'text': package.get('body', ''),
                'images': package.get('images', []) })
        if package.get('draft_id') and published.get('success'):
            self.update_social_draft_status(int(package.get('draft_id', 0)), 'published', str(published.get('url', '')))
        return published

    
    async def autopost_hot_content(self, platform = None, topic = None):
        discovery = await self.discover_hot_social_topics(limit=1)
        if not discovery.get('success') or not discovery.get('candidates'):
            return {'success': False, 'error': '没有发现热门话题'}
        candidate = discovery['candidates'][0]
        topic = candidate.get('topic', '')
        plan = candidate.get('plan', {})
        research = {
            'x': candidate.get('items', []),
            'xiaohongshu': candidate.get('items', []),
            'insights': {
                'patterns': ['教程', 'SOP'],
                'hooks': [candidate.get('trend_label', '')],
                'opportunity': plan.get('practical_focus', ''),
            },
            'runs': [],
        }
        strategy = self._derive_topic_strategy(topic, research, research)
        sources = candidate.get('items', [])
        x_body = self._compose_human_x_post(topic, strategy, sources)
        xhs_result = self._compose_human_xhs_article(topic, strategy, sources)
        xhs_body = xhs_result.get('body', '') if isinstance(xhs_result, dict) else str(xhs_result or '')
        xhs_title = xhs_result.get('title', '') if isinstance(xhs_result, dict) else ''
        results = {}
        target = platform or 'all'
        if target in ('all', 'x'):
            x_draft = self.save_social_draft('x', '', x_body, topic=topic)
            render = self._run_social_worker('render', {'topic': topic, 'platform': 'x'})
            published = self._run_social_worker('publish_x', {'text': x_body, 'images': []})
            results['x'] = {
                'body': x_body,
                'draft': x_draft,
                'rendered': render,
                'published': published,
            }
        if target in ('all', 'xiaohongshu'):
            xhs_draft = self.save_social_draft('xiaohongshu', xhs_title, xhs_body, topic=topic)
            render = self._run_social_worker('render', {'topic': topic, 'platform': 'xiaohongshu'})
            published = self._run_social_worker('publish_xhs', {'title': xhs_title, 'body': xhs_body, 'images': []})
            results['xiaohongshu'] = {
                'body': xhs_body,
                'title': xhs_title,
                'draft': xhs_draft,
                'rendered': render,
                'published': published,
            }
        return {
            'success': True,
            'topic': topic,
            'strategy': strategy,
            'results': results,
        }

    
    async def build_social_plan(self, topic = None, limit = None):
        limit = limit or 3
        discovery = await self.discover_hot_social_topics(limit=limit)
        if not discovery.get('success') or not discovery.get('candidates'):
            return {'success': False, 'error': '没有发现热门话题'}
        plans = []
        for candidate in discovery['candidates'][:limit]:
            t = candidate.get('topic', '')
            research = {
                'x': candidate.get('items', []),
                'xiaohongshu': candidate.get('items', []),
                'insights': {
                    'patterns': ['教程', 'SOP'],
                    'hooks': [candidate.get('trend_label', '')],
                    'opportunity': candidate.get('plan', {}).get('practical_focus', ''),
                },
                'runs': [],
            }
            strategy = self._derive_topic_strategy(t, research, research)
            plans.append({
                'topic': t,
                'trend_label': candidate.get('trend_label', ''),
                'utility_score': candidate.get('utility_score', 50),
                'x_tactic': strategy.get('x_tactic', ''),
                'xhs_tactic': strategy.get('xhs_tactic', ''),
                'strategy': strategy,
            })
        return {
            'success': True,
            'mode': 'daily',
            'plans': plans,
        }

    
    async def build_social_repost_bundle(self, topic = None):
        topic = topic or 'OpenClaw 实战'
        research = self._run_social_worker('research', {'topic': topic})
        if not research or not research.get('success'):
            return {'success': False, 'error': '研究阶段失败'}
        strategy = self._derive_topic_strategy(topic, research, research)
        sources = research.get('x', []) + research.get('xiaohongshu', [])
        x_body = self._compose_human_x_post(topic, strategy, sources)
        xhs_result = self._compose_human_xhs_article(topic, strategy, sources)
        xhs_body = xhs_result.get('body', '') if isinstance(xhs_result, dict) else str(xhs_result or '')
        xhs_title = xhs_result.get('title', '') if isinstance(xhs_result, dict) else ''
        render = self._run_social_worker('render', {'topic': topic})
        x_draft = self.save_social_draft('x', '', x_body, topic=topic)
        xhs_draft = self.save_social_draft('xiaohongshu', xhs_title, xhs_body, topic=topic)
        return {
            'success': True,
            'topic': topic,
            'results': {
                'x': {
                    'success': True,
                    'body': x_body,
                    'draft_id': x_draft.get('draft_id', 0) if x_draft else 0,
                    'rendered': render,
                },
                'xiaohongshu': {
                    'success': True,
                    'body': xhs_body,
                    'title': xhs_title,
                    'draft_id': xhs_draft.get('draft_id', 0) if xhs_draft else 0,
                    'rendered': render,
                },
            },
        }

    
    async def research_social_topic(self, topic = None, limit = None):
        topic = topic or 'AI 工具'
        limit = limit or 5
        try:
            google_items = await self.news_fetcher.fetch_from_google_news_rss(topic, count=limit)
            bing_items = await self.news_fetcher.fetch_from_bing(topic, count=limit)
        except Exception as e:
            logger.error(f"[ResearchTopic] fetch failed: {e}")
            google_items = []
            bing_items = []
        all_items = self._curate_monitor_items((google_items or []) + (bing_items or []), limit=limit * 2)
        x_items = [item for item in all_items if any(k in item.get('title', '').lower() for k in ['x', 'twitter', 'thread'])]
        xhs_items = [item for item in all_items if any(k in item.get('title', '').lower() for k in ['小红书', '教程', '分享'])]
        if not x_items:
            x_items = all_items[:limit]
        if not xhs_items:
            xhs_items = all_items[:limit]
        insights = {
            'patterns': ['教程', 'SOP', '实操'],
            'hooks': [topic],
            'opportunity': f'围绕「{topic}」产出实用内容',
        }
        return {'success': True, 'x': x_items, 'xiaohongshu': xhs_items, 'insights': insights}

    
    def _compose_human_xhs_article(self, topic = None, strategy = None, sources=None):
        if strategy.get('persona_id'):
            return self._compose_persona_xhs_article(topic, strategy, sources)
        style_id = strategy.get('style_id', 0)
        trend_label = self._creator_trend_label(topic, strategy)
        lead_magnet = strategy.get('lead_magnet', '资料包、模板或 SOP')
        cta = strategy.get('cta', '引导用户评论或私信领取资料')
        return {
            'title': f'{trend_label}实用教程',
            'body': f'关于{trend_label}的实用分享\n\n{cta}'
        }

    
    def _compose_human_x_post(self, topic = None, strategy = None, sources=None):
        if strategy.get('persona_id'):
            return self._compose_persona_x_post(topic, strategy, sources)
        trend_label = self._creator_trend_label(topic, strategy)
        source_lines = self._source_title_lines(sources, limit = 1, max_len = 34)
        x_tactic = strategy.get('x_tactic', '去头部账号评论区做高价值回复')
        lead_magnet = strategy.get('lead_magnet', '资料包')
        lines = [
            f'今天都在聊「{trend_label}」，但对普通创作者更重要的不是复述热点。',
            '',
            '没有 X Premium 的免费号，别幻想靠 For You 自然起量。',
            '我现在用 OpenClaw 跑 0 成本 SOP：',
            '1. 先用热点做 MVP 选题',
            f'2. {x_tactic}',
            '3. 再把同题改写成小红书教程，先看收藏率']
        if source_lines:
            lines.extend([
                '',
                f'今天先借这条起势：{source_lines[0]}'])
        lines.extend([
            '',
            f'主页置顶放{lead_magnet}，先验证 PMF，再决定要不要买会员和投流。',
            '#OpenClaw #内容增长'])
        return '\n'.join(lines)[:278]

    
    async def create_topic_social_package(self, platform = None, topic = None):
        topic = topic or 'OpenClaw 实战'
        try:
            research = await self.research_social_topic(topic=topic)
            if not research.get('success'):
                return {'success': False, 'error': '研究阶段失败'}
            strategy = self._derive_topic_strategy(topic, research, research)
            sources = research.get('x', []) + research.get('xiaohongshu', [])
            x_body = self._compose_human_x_post(topic, strategy, sources)
            xhs_result = self._compose_human_xhs_article(topic, strategy, sources)
            xhs_body = xhs_result.get('body', '') if isinstance(xhs_result, dict) else str(xhs_result or '')
            xhs_title = xhs_result.get('title', '') if isinstance(xhs_result, dict) else ''
            x_draft = self.save_social_draft('x', '', x_body, topic=topic)
            xhs_draft = self.save_social_draft('xiaohongshu', xhs_title, xhs_body, topic=topic)
            return {
                'success': True, 'topic': topic, 'strategy': strategy,
                'results': {
                    'x': {'success': True, 'body': x_body,
                           'draft_id': x_draft.get('draft_id', 0) if x_draft else 0},
                    'xiaohongshu': {'success': True, 'body': xhs_body, 'title': xhs_title,
                                     'draft_id': xhs_draft.get('draft_id', 0) if xhs_draft else 0},
                },
            }
        except Exception as e:
            logger.error(f"[CreateTopicPackage] failed: {e}")
            return {'success': False, 'error': str(e)}

    
    async def autopost_topic_content(self, platform = None, topic = None):
        topic = topic or 'OpenClaw 实战'
        try:
            package = await self.create_topic_social_package(platform=platform, topic=topic)
            if not package.get('success'):
                return package
            results = {}
            target = platform or 'all'
            pkg_results = package.get('results', {})
            if target in ('all', 'x') and pkg_results.get('x'):
                render = self._run_social_worker('render', {'topic': topic, 'platform': 'x'})
                published = self._run_social_worker('publish_x', {
                    'text': pkg_results['x'].get('body', ''), 'images': []})
                results['x'] = {**pkg_results['x'], 'rendered': render, 'published': published}
            if target in ('all', 'xiaohongshu') and pkg_results.get('xiaohongshu'):
                render = self._run_social_worker('render', {'topic': topic, 'platform': 'xiaohongshu'})
                published = self._run_social_worker('publish_xhs', {
                    'title': pkg_results['xiaohongshu'].get('title', ''),
                    'body': pkg_results['xiaohongshu'].get('body', ''), 'images': []})
                results['xiaohongshu'] = {**pkg_results['xiaohongshu'], 'rendered': render, 'published': published}
            return {'success': True, 'topic': topic, 'results': results}
        except Exception as e:
            logger.error(f"[AutopostTopic] failed: {e}")
            return {'success': False, 'error': str(e)}

    
    async def collect_latest_x_monitor_posts(self, max_accounts = None, posts_per_account = None):
        max_accounts = max_accounts or 10
        posts_per_account = posts_per_account or 3
        all_posts = []
        count = 0
        for monitor in self._monitors:
            if count >= max_accounts:
                break
            keyword = monitor.get('keyword', '')
            source = monitor.get('source', 'news')
            if source != 'x_profile':
                continue
            posts = await self.fetch_x_profile_posts(keyword, count=posts_per_account)
            if posts:
                for post in posts:
                    post['handle'] = keyword
                all_posts.extend(posts)
            count += 1
        return all_posts

    
    def save_social_draft(self, platform = None, title = None, body = None, sources=None, topic=None):
        platform = platform or 'both'
        platform_name = str(platform or '').strip().lower()
        if platform_name not in frozenset({'x', 'xiaohongshu', 'both'}):
            return {
                'success': False,
                'error': '仅支持 x / xiaohongshu / both' }
        body = body or ''
        content = str(body).strip()
        if not content:
            return {
                'success': False,
                'error': '草稿内容不能为空' }
        title = title or ''
        topic = topic or title
        duplicate = self._detect_recent_social_duplicate(platform_name, str(title), content, topic=topic)
        if duplicate and duplicate.get('duplicate'):
            existing = duplicate.get('existing', {})
            return {
                'success': False,
                'error': '内容与最近草稿过于相似',
                'duplicate': True,
                'existing_id': existing.get('id', 0) }
        # Success case: return success with a draft_id
        draft_id = len(self._draft_store) + 1
        row = {
            'id': draft_id,
            'success': True,
            'draft_id': draft_id,
            'platform': platform_name,
            'title': title,
            'body': content,
            'topic': topic,
            'updated_at': datetime.now().isoformat(),
        }
        self._draft_store.append(row)
        # 内存上限裁剪
        if len(self._draft_store) > self._max_drafts:
            self._draft_store = self._draft_store[-self._max_drafts:]
        return row

    
    def list_social_drafts(self, platform = None, status = None, sources=None, limit=20):
        platform = platform or 'both'
        platform_name = str(platform or '').strip().lower()
        status = status or ''
        status_name = str(status or '').strip().lower()
        sql = 'SELECT * FROM social_drafts'
        params = []
        clauses = []
        if platform_name:
            clauses.append('platform=?')
            params.append(platform_name)
        if status_name:
            clauses.append('status=?')
            params.append(status_name)
        if clauses:
            sql += ' WHERE ' + ' AND '.join(clauses)
        sql += ' ORDER BY updated_at DESC LIMIT ?'
        params.append(max(1, int(limit)))

    
    def get_social_draft(self, draft_id = None):
        if not draft_id:
            return None
        try:
            with self._conn() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute('SELECT * FROM social_drafts WHERE id=?', (int(draft_id),)).fetchone()
                if row:
                    return dict(row)
        except Exception:
            pass
        return None

    
    def update_social_draft_status(self, draft_id = None, status = None, sources=None):
        if not draft_id or not status:
            return {'success': False, 'error': 'draft_id and status required'}
        try:
            now = datetime.now().isoformat()
            with self._conn() as conn:
                conn.execute('UPDATE social_drafts SET status=?, updated_at=? WHERE id=?',
                             (str(status), now, int(draft_id)))
            return {'success': True, 'draft_id': draft_id, 'status': status, 'updated_at': now}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    
    def _build_x_social_body(self, items = None, topic = None):
        topic = topic or ''
        topic_label = topic or 'AI/出海'
        tags = self._social_topic_tags(topic)
        lines = [
            f'今天筛了 {len(items)} 条值得看的{topic_label}更新：']
        for i, item in enumerate(items[:3], 1):
            summary = item.get('title', '')
            if len(summary) > 32:
                summary = summary[:29] + '...'
            lines.append('{}. @{}：{}'.format(i, item.get('handle', ''), summary))
        lines.append('想要原文链接和每日精选，来找 OpenClaw。')
        if tags:
            lines.append(' '.join(tags[:3]))
        text = '\n'.join(lines)
        return text[:278]

    
    def _build_xiaohongshu_title(self, items = None, topic = None):
        topic = topic or ''
        topic_label = topic or 'AI/出海'
        title = f'今日{topic_label}情报：{len(items)}位博主更新'
        return title[:20]

    
    def _build_xiaohongshu_body(self, items = None, topic = None):
        topic = topic or ''
        topic_label = topic or 'AI/出海/独立开发'
        tags = self._social_topic_tags(topic)
        lines = [
            f'今天整理了 {len(items)} 条值得追踪的{topic_label}动态，适合做信息流输入：',
            '']
        for i, item in enumerate(items[:5], 1):
            summary = item.get('title', '')
            if len(summary) > 72:
                summary = summary[:69] + '...'
            lines.append(f'   {summary}')
            if item.get('url'):
                lines.append(f'   原文：{item.get("url", "")}')
        lines.append('如果你想让我每天自动筛这类信息源，可以直接用 OpenClaw 建监控。')
        return '\n'.join(lines)
    async def create_social_draft(self, platform=None, topic=None, max_items=3):
        platform = platform or 'x'
        topic = topic or 'AI'
        max_items = max_items or 3
        # Collect items from x_profile monitors
        all_items = []
        for monitor in self._monitors:
            keyword = monitor.get('keyword', '')
            source = monitor.get('source', 'news')
            if source == 'x_profile':
                posts = await self.fetch_x_profile_posts(keyword, count=max_items)
                if posts:
                    for post in posts:
                        post['handle'] = keyword
                    all_items.extend(posts)
        all_items = all_items[:max_items]
        if platform == 'xiaohongshu':
            title = self._build_xiaohongshu_title(all_items, topic)
            body = self._build_xiaohongshu_body(all_items, topic)
            ret = self.save_social_draft('xiaohongshu', title, body, topic=topic)
            return ret
        else:
            body = self._build_x_social_body(all_items, topic)
            ret = self.save_social_draft('x', '', body, topic=topic)
            return ret

    def _infer_bounty_difficulty(self, title = None, notes = None):
        pass  # stub: 反编译恢复中

    def _estimate_bounty_hours(self, difficulty = None, title = None):
        pass  # stub: 反编译恢复中

    def _resolve_bounty_keywords(self, keywords = None):
        pass  # stub: 反编译恢复中

    def _resolve_bounty_repo_filters(self):
        pass  # stub: 反编译恢复中

    def _resolve_bounty_reward_buckets(self):
        pass  # stub: 反编译恢复中

    def _bounty_signal(self, title = None, notes = None, sources=None):
        pass  # stub: 反编译恢复中

    def _upsert_bounty_leads(self, leads = None):
        pass  # stub: 反编译恢复中

    async def _scan_github_bounties(self, keywords = None, per_query = None):
        pass  # stub: 反编译恢复中

    async def _scan_web_bounties(self, keywords = None, per_query = None):
        pass  # stub: 反编译恢复中

    async def scan_bounties(self, keywords = None, per_query = None):
        pass  # stub: 反编译恢复中

    def _evaluate_single_bounty(self, row = None):
        difficulty = 'unknown'
        title = row.get('title', '')
        platform = row.get('platform', 'web')
        notes = row.get('notes', '')
        token_cost_per_m = _safe_float(os.getenv('OPS_BOUNTY_TOKEN_COST_PER_M', '3.0'), 3)
        est_tokens = _safe_int(os.getenv('OPS_BOUNTY_EST_TOKENS', '120000'), 120000)
        hourly_rate = _safe_float(os.getenv('OPS_BOUNTY_HOURLY_RATE', '35'), 35)
        autonomy_factor = _safe_float(os.getenv('OPS_BOUNTY_AUTONOMY_FACTOR', '1.0'), 1)
        autonomy_factor = max(0, min(1.5, autonomy_factor))
        default_reward = _safe_float(os.getenv('OPS_BOUNTY_DEFAULT_REWARD_USD', '120'), 120)
        signal = self._bounty_signal(title, notes, _safe_float(row.get('reward_usd', 0), 0))
        reward = _safe_float(row.get('reward_usd', 0), 0)
        if reward <= 0 and signal.get('explicit_reward'):
            reward = 0
        modeled_reward = reward
        if modeled_reward <= 0:
            if platform in frozenset({'upwork', 'bugcrowd', 'hackerone', 'intigriti'}):
                modeled_reward = default_reward
            elif platform == 'github':
                modeled_reward = default_reward * 0.8
            else:
                modeled_reward = default_reward * 0.6
        est_hours = self._estimate_bounty_hours(difficulty, title)
        token_cost = round((max(1, est_tokens) / 1e+06) * max(0.01, token_cost_per_m), 4)
        labor_cost = round(est_hours * max(1, hourly_rate) * autonomy_factor, 4)
        total_cost = round(token_cost + labor_cost, 4)
        roi = round(modeled_reward - total_cost, 4)
        return {
            'reward_usd': round(reward, 4),
            'modeled_reward_usd': round(modeled_reward, 4),
            'est_hours': est_hours,
            'token_cost_usd': token_cost,
            'labor_cost_usd': labor_cost,
            'expected_roi_usd': roi,
            'est_cost_usd': total_cost }

    
    def evaluate_bounty_leads(self, status = None, limit = None):
        status = status or ''
        st = str(status or '').strip().lower()
        min_roi = _safe_float(os.getenv('OPS_BOUNTY_MIN_ROI_USD', '20'), 20)
        min_signal = _safe_int(os.getenv('OPS_BOUNTY_MIN_SIGNAL_SCORE', '4'), 4)

    
    def list_bounty_leads(self, status = None, limit = None):
        status = status or ''
        st = str(status or '').strip().lower()

    
    def open_bounty_links(self, status = None, limit = None):
        rows = self.list_bounty_leads(status = status, limit = max(1, int(limit)))
        opened = []
        failed = []
        for row in rows[:max(1, int(limit))]:
            url = row.get('url', '')
            if not url:
                continue
            cp = subprocess.run([
                'open',
                url], check = False, capture_output = True, text = True, timeout = 8)
            if cp.returncode == 0:
                opened.append(url)
            else:
                failed.append({
                    'url': url,
                    'error': str(cp.stderr or '').strip()[:200] })
        return {
            'success': len(failed) == 0,
            'opened': opened,
            'failed': failed,
            'total': len(rows) }

    
    def _today_bounty_accept_cost(self):
        date_key = datetime.now().strftime('%Y-%m-%d')

    
    def _today_accepted_bounty_ids(self):
        date_key = datetime.now().strftime('%Y-%m-%d')

    
    def _record_bounty_run(self, lead = None, decision = None, est_cost = None, sources=None):
        date_key = datetime.now().strftime('%Y-%m-%d')

    
    def _accepted_bounty_shortlist(self, limit = None, min_roi = None, sources=None):
        rows = self.list_bounty_leads(status = 'accepted', limit = max(20, int(limit) * 8))
        filtered = []
        allowed_platforms = allowed_platforms or ''
        allowed = set()

    
    async def run_bounty_hunter(self, keywords = None, shortlist_limit = None):
        keywords = keywords or ['GitHub bounty', 'open source bounty', 'bug bounty program']
        shortlist_limit = shortlist_limit or 5
        all_items = []
        for kw in keywords:
            items = await self.news_fetcher.fetch_from_google_news_rss(kw, count=8)
            if items:
                all_items.extend(items)
        curated = self._curate_monitor_items(all_items, limit=shortlist_limit)
        return {
            'success': True,
            'keywords': keywords,
            'total_found': len(all_items),
            'shortlist': curated,
        }

    
    def _normalize_x_source(self, source = None):
        source = source or ''
        text = str(source or '').strip()
        if not text:
            return 'https://x.com/IndieDevHailey'
        if text.startswith('@'):
            return f'https://x.com/{text[1:]}'
        if re.fullmatch('[A-Za-z0-9_]{1,20}', text):
            return f'https://x.com/{text}'
        if text.startswith('http://') or text.startswith('https://'):
            return text
        return f'{text}'

    
    def _build_jina_reader_url(self, source = None):
        normalized = self._normalize_x_source(source)
        parsed = urlparse(normalized)
        query = '?{parsed.query}' if parsed.query else ''
        return 'https://r.jina.ai/http://{parsed.netloc}{parsed.path}{query}'

    
    def _normalize_x_handle(self, source = None):
        normalized = self._normalize_x_source(source)
        parsed = urlparse(normalized)

    
    def _clean_reader_markdown(self, text = None):
        text = text or ''
        body = str(text or '').strip()
        marker = 'Markdown Content:'
        idx = body.find(marker)
        if idx >= 0:
            body = body[idx + len(marker):].strip()
        body = re.sub('!\\[[^\\]]*\\]\\([^\\)]+\\)', ' ', body)
        body = re.sub('\\[[^\\]]+\\]\\([^\\)]+\\)', ' ', body)
        body = re.sub('\\s+', ' ', body)
        return body.strip()

    
    def _clean_reader_line(self, line = None):
        line = line or ''
        text = re.sub('!\\[[^\\]]*\\]\\([^\\)]+\\)', ' ', str(line))
        text = re.sub('\\[([^\\]]+)\\]\\([^\\)]+\\)', '\\1', text)
        text = re.sub('\\s+', ' ', text)
        return text.strip(' -\t')

    
    def _sanitize_x_post_summary(self, text = None):
        value = self._clean_reader_line(text)
        value = re.sub('\\bShow more\\b.*$', '', value, flags = re.IGNORECASE)
        value = re.sub('\\bReplying to\\b.*$', '', value, flags = re.IGNORECASE)
        value = re.sub('\\bQuote\\b.*$', '', value, flags = re.IGNORECASE)
        value = re.sub('\\b[A-Za-z0-9_]{2,20}\\s*·\\s*$', '', value)
        value = re.sub('\\b\\d{1,2}:\\d{2}\\b.*$', '', value)
        value = re.sub('\\s+', ' ', value)
        return value.strip(' -·')

    
    async def _fetch_x_reader_payload(self, source = None):
        source = source or ''
        url = self._normalize_x_source(source)
        result = self._run_social_worker('x_read', {'url': url})
        return result

    
    def _extract_x_profile_posts_from_markdown(self, handle = None, markdown = None, limit=5):
        handle = handle or ''
        markdown = markdown or ''
        posts = []
        status_pattern = re.compile(r'https://x\.com/' + re.escape(handle) + r'/status/(\d+)')
        blocks = re.split(r'\n\n+', markdown)
        current_url = ''
        current_id = ''
        current_text = ''
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            m = status_pattern.search(block)
            if m:
                if current_id and current_text:
                    posts.append({
                        'digest_key': current_id,
                        'url': f'https://x.com/{handle}/status/{current_id}',
                        'title': current_text.strip()[:120],
                        'source': f'X @{handle}',
                    })
                    if len(posts) >= (limit or 5):
                        return posts
                current_id = m.group(1)
                current_url = m.group(0)
                current_text = ''
            elif current_id:
                # Skip analytics links and date-only lines
                if re.match(r'^\[?\d+[KMB]?\]?\(?https://', block):
                    continue
                if re.match(r'^\[.*\]\(https://x\.com/', block):
                    continue
                if block and not block.startswith('[') and not block.startswith('http'):
                    current_text += block + ' '
        if current_id and current_text:
            posts.append({
                'digest_key': current_id,
                'url': f'https://x.com/{handle}/status/{current_id}',
                'title': current_text.strip()[:120],
                'source': f'X @{handle}',
            })
        return posts[:(limit or 5)]

    
    def _extract_x_handle_candidates_from_markdown(self, markdown = None, limit = None):
        markdown = markdown or ''
        limit = limit or 10
        handles = []
        for line in markdown.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Look for handles: words that look like X handles (alphanumeric + underscore, 1-20 chars)
            # at the end of numbered list items
            m = re.search(r'[。．.]?\s*([A-Za-z][A-Za-z0-9_]{1,19})\s*$', line)
            if m:
                candidate = m.group(1)
                # Filter out common non-handle words
                if candidate.lower() in ('the', 'and', 'for', 'not', 'are', 'was', 'has', 'seo', 'saas'):
                    continue
                # Must contain at least one uppercase or be a known pattern
                if candidate not in handles:
                    handles.append(candidate)
            if len(handles) >= limit:
                break
        return handles[:limit]

    
    async def fetch_x_profile_posts(self, handle = None, count = None):
        handle = handle or ''
        count = count or 5
        result = self._run_social_worker('x_profile', {'handle': handle, 'count': count})
        if not result.get('success'):
            return []
        markdown = result.get('markdown', '') or result.get('stdout', '')
        if markdown:
            return self._extract_x_profile_posts_from_markdown(handle, markdown, limit=count)
        return result.get('posts', [])

    
    async def import_x_monitors_from_tweet(self, source = None, limit = None):
        limit = limit or 10
        payload = await self._fetch_x_reader_payload(source)
        markdown = payload.get('markdown', '') or payload.get('stdout', '') if payload.get('success') else ''
        handles = self._extract_x_handle_candidates_from_markdown(markdown, limit=limit)
        added = []
        for handle in handles:
            result = self.add_monitor(keyword=handle, source='x_profile')
            if result.get('success'):
                added.append(result)
        return added

    
    async def generate_x_monitor_brief(self):
        sections = []
        for monitor in self._monitors:
            keyword = monitor.get('keyword', '')
            source = monitor.get('source', 'news')
            if source != 'x_profile':
                continue
            posts = await self.fetch_x_profile_posts(keyword, count=1)
            if not posts:
                continue
            entries = []
            for post in posts[:2]:
                title = post.get('title', '')
                url = post.get('url', '')
                entries.append(title)
                if url:
                    entries.append(f'详情：{url}')
            sections.append((f'【@{keyword}】', entries))
        return format_announcement(
            title='OpenClaw「X 资讯快讯」',
            intro='检测到关注账号有新的公开动态。',
            sections=sections,
            footer='如需继续追踪，可保留当前监控项。'
        )

    
    def _derive_tweet_execution_strategy(self, text = None):
        text = text or ''
        content = str(text).strip().lower()
        urgency = 5
        action = 'repost'
        platform = 'x'
        content_type = 'commentary'
        reasoning = '默认转评策略'
        if any(kw in content for kw in ['breaking', '突发', 'urgent', '紧急']):
            urgency = 9
            action = 'quote_retweet'
            reasoning = '突发/紧急内容，建议快速引用转发'
        elif any(kw in content for kw in ['tutorial', '教程', 'how to', '怎么', '如何']):
            urgency = 4
            action = 'thread'
            content_type = 'tutorial'
            reasoning = '教程类内容，适合展开为长线程'
        elif any(kw in content for kw in ['opinion', '观点', 'hot take', '看法']):
            urgency = 6
            action = 'quote_retweet'
            content_type = 'opinion'
            reasoning = '观点类内容，适合引用并补充观点'
        return {
            'action': action,
            'platform': platform,
            'content_type': content_type,
            'urgency': urgency,
            'reasoning': reasoning,
        }

    
    async def analyze_tweet_execution(self, source = None):
        payload = await self._fetch_x_reader_payload(source)
        if not payload.get('success'):
            return {'success': False, 'error': payload.get('error', '无法获取推文内容')}
        text = payload.get('markdown', '') or payload.get('stdout', '')
        strategy = self._derive_tweet_execution_strategy(text)
        return {
            'success': True,
            'source': source,
            'text_preview': text[:300],
            'strategy': strategy,
        }

    
    async def run_tweet_execution(self, source = None):
        analysis = await self.analyze_tweet_execution(source)
        if not analysis.get('success'):
            return analysis
        strategy = analysis.get('strategy', {})
        text_preview = analysis.get('text_preview', '')
        prompt = (
            f"根据以下推文内容，生成一条适合发布的社媒内容（中文，不超过200字）。\n"
            f"策略：{strategy.get('action', '')}，类型：{strategy.get('content_type', '')}\n"
            f"原文摘要：{text_preview[:500]}"
        )
        ai_result = await self._call_social_ai(prompt)
        generated = ai_result.get('raw', '') if ai_result.get('success') else ''
        draft = self.save_social_draft('x', '', generated or text_preview[:200], topic=source)
        return {
            'success': True,
            'source': source,
            'strategy': strategy,
            'generated_content': generated,
            'draft': draft,
        }

    
    def add_monitor(self, keyword = None, source = None):
        keyword = keyword or ''
        k = str(keyword or '').strip()
        if not k:
            return {
                'success': False,
                'error': '关键词不能为空' }
        source = source or 'news'
        self._monitors.append({'keyword': k, 'source': source})
        # 内存上限裁剪
        if len(self._monitors) > self._max_monitors:
            self._monitors = self._monitors[-self._max_monitors:]
        return {'success': True, 'keyword': k, 'source': source}

    
    def list_monitors(self):
        try:
            with self._conn() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute('SELECT * FROM monitors ORDER BY id DESC').fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    
    def _monitor_env_list(self, env_name = None, default = None):
        raw = os.getenv(env_name, default)
        if not raw:
            return []
        return [x.strip() for x in raw.split(',') if x.strip()]

    
    def _normalize_monitor_text(self, text = None):
        text = text or ''
        value = re.sub('\\s+', ' ', str(text).strip()).lower()
        value = re.sub('[\\"\'`]+', '', value)
        value = re.sub('[^0-9a-z\\u4e00-\\u9fff]+', '', value)
        return value

    
    def _clean_monitor_title(self, title = None, source = None):
        title = title or ''
        clean_title = re.sub('\\s+', ' ', str(title).strip())
        source = source or ''
        clean_source = re.sub('\\s+', ' ', str(source).strip())
        if clean_source:
            suffixes = [
                f' - {clean_source}',
                f' | {clean_source}',
                f' - {clean_source.lower()}',
                f' | {clean_source.lower()}']
            lower_title = clean_title.lower()
            for suffix in suffixes:
                if not lower_title.endswith(suffix.lower()):
                    continue
                clean_title = clean_title[:-len(suffix)].strip()
                return clean_title
        return clean_title

    
    def _is_low_value_monitor_item(self, title = None, source = None):
        blocked_sources = self._monitor_env_list('OPS_MONITOR_BLOCKED_SOURCES', '新浪财经,驱动之家,中关村在线,cnBeta.COM,搜狐网,IT之家,快科技')
        low_value_keywords = self._monitor_env_list('OPS_MONITOR_LOW_VALUE_KEYWORDS', '独显,份额,市场份额,专卖,显卡,开箱,评测,参数,跑分,报价,促销,价格,卖不出去')
        title = title or ''
        title_text = str(title)
        source = source or ''
        source_text = str(source)
        haystack = f'{title_text} {source_text}'.lower()
        source_lower = source_text.lower()
        for token in (blocked_sources or []):
            token_lower = token.lower()
            if not token_lower:
                continue
            if token_lower in source_lower or token_lower in haystack:
                return True
        for token in (low_value_keywords or []):
            token_lower = token.lower()
            if not token_lower:
                continue
            if token_lower in haystack:
                return True
        return False

    
    def _curate_monitor_items(self, items = None, limit = None):
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
                'digest_key': normalized })
            if len(curated) >= limit:
                break
        return curated

    
    def format_monitor_alert(self, alert = None):
        source = alert.get('source', 'news')
        keyword = alert.get('keyword', '')
        items = alert.get('items', [])
        if source == 'x_profile':
            sections = []
            for idx, item in enumerate(items[:2], 1):
                title = item.get('title', '')
                entries = [
                    f'{idx}. {title}']
                url = item.get('url', '')
                if url:
                    entries.append(f'详情：{url}')
                sections.append((f'【@{keyword}】', entries))
            return format_announcement(title = 'OpenClaw「X 快讯」', intro = f'检测到 @{keyword} 有新的公开动态，已整理本轮最值得关注的更新。', sections = sections, footer = '如需继续追踪，可保留当前监控项并稍后再次扫描。')
        sections = []
        for idx, item in enumerate(items[:3], 1):
            source_name = item.get('source', '')
            title = item.get('title', '')
            entries = [
                f'{idx}. {title}' + f'（来源：{source_name}）' if source_name else '']
            url = item.get('url', '')
            if url:
                entries.append(f'详情：{url}')
            sections.append((f'【第 {idx} 条】', entries))
        return format_announcement(title = f'OpenClaw「资讯快讯」{keyword}', intro = f'本轮监控命中 {len(items[:3])} 条新增资讯，已按可读性重新整理。', sections = sections, footer = '如需继续追踪这个关键词，可稍后再次运行资讯监控。')

    
    async def _fetch_monitor_items(self, keyword = None, source = None, count = 5):
        keyword = keyword or ''
        source = source or 'news'
        count = count if isinstance(count, int) else 5
        items = await self.news_fetcher.fetch_from_google_news_rss(keyword, count=count)
        return items or []

    
    async def run_monitors_once(self):
        alerts = []
        fetch_count = int(os.getenv('OPS_MONITOR_FETCH_COUNT', '8'))
        alert_limit = int(os.getenv('OPS_MONITOR_ALERT_LIMIT', '3'))
        for monitor in self._monitors:
            keyword = monitor.get('keyword', '')
            source = monitor.get('source', 'news')
            if source == 'x_profile':
                items = await self.fetch_x_profile_posts(keyword, count=fetch_count)
            else:
                items = await self.news_fetcher.fetch_from_google_news_rss(keyword, count=fetch_count)
            curated = self._curate_monitor_items(items or [], limit=alert_limit)
            new_items = []
            for item in curated:
                digest_key = item.get('digest_key', '')
                if digest_key and digest_key not in self._monitor_seen_digests:
                    self._monitor_seen_digests.add(digest_key)
                    # 防止 set 无限增长
                    if len(self._monitor_seen_digests) > self._max_seen_digests:
                        # 丢弃一半旧的（set 无序，但足够防 OOM）
                        to_keep = list(self._monitor_seen_digests)[-self._max_seen_digests // 2:]
                        self._monitor_seen_digests = set(to_keep)
                    new_items.append(item)
            if new_items:
                alerts.append({
                    'keyword': keyword,
                    'source': source,
                    'items': new_items,
                })
        return alerts

    
    def _parse_github_issue_ref(self, issue_ref = None):
        issue_ref = issue_ref or ''
        raw = str(issue_ref or '').strip()
        if not raw:
            return None
        # Support "owner/repo#123" format
        m = re.match(r'^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)$', raw)
        if m:
            return {'repo': m.group(1), 'issue_number': int(m.group(2))}
        # Support full URL format
        m = re.match(r'https?://github\.com/([^/]+/[^/]+)/issues/(\d+)', raw)
        if m:
            return {'repo': m.group(1), 'issue_number': int(m.group(2))}
        return None

    
    def add_payout_watch(self, issue_ref = None, label = None):
        parsed = self._parse_github_issue_ref(issue_ref)
        if not parsed:
            return {
                'success': False,
                'error': 'issue_ref 格式无效，支持 repo#123 或 issue URL' }
        return {
            'success': True,
            'repo': parsed.get('repo', ''),
            'issue_number': parsed.get('issue_number', 0),
        }

    
    def sync_payout_watches_from_env(self):
        refs = self._monitor_env_list('OPS_PAYOUT_WATCH_ISSUES', '')
        added = []
        for ref in refs:
            ret = self.add_payout_watch(ref)
            if not ret.get('success'):
                continue
            added.append(ret)
        return added

    
    def list_payout_watches(self):
        refs = self._monitor_env_list('OPS_PAYOUT_WATCH_ISSUES', '')
        watches = []
        for ref in refs:
            parsed = self._parse_github_issue_ref(ref)
            if parsed:
                watches.append(parsed)
        return watches

    
    def _fetch_github_issue_snapshot(self, repo = None, issue_number = None):
        issue_ret = self._run_cmd([
            'gh',
            'api',
            f'repos/{repo}/issues/{issue_number}'], cwd = self.repo_root, timeout = 40, stdout_limit = None)
        if not issue_ret.get('ok'):
            return {
                'success': False,
                'error': issue_ret.get('stderr', 'gh api issue failed') }
        comments_ret = self._run_cmd([
            'gh',
            'api',
            f'repos/{repo}/issues/{issue_number}/comments?per_page=100'], cwd = self.repo_root, timeout = 40, stdout_limit = None)
        if not comments_ret.get('ok'):
            return {
                'success': False,
                'error': comments_ret.get('stderr', 'gh api comments failed') }
        issue = issue_ret.get('stdout', '')
        comments = comments_ret.get('stdout', '')
        return {
            'success': True,
            'issue': issue,
            'comments': comments }

    
    def _classify_payout_comment(self, body = None):
        body = body or ''
        text = str(body or '').strip()
        lower = text.lower()
        rules = [
            ('hire', [
                'implement this',
                'create a draft pr',
                'you can start working',
                'we can move forward with your proposal',
                'you are hired',
                'assigned to you'], '接单信号已出现，我会继续推进到可提 PR / 可结算阶段。'),
            ('offer', [
                'upwork offer',
                'offer sent',
                'contract sent',
                'upwork contract'], 'Upwork 侧可能已经发 offer，去 Upwork 确认并接单。'),
            ('payment', [
                'eligible for payment',
                'due for payment',
                'awaiting payment',
                'payment issued',
                'payment sent',
                'paid in upwork',
                'paid via upwork',
                'bonus payment',
                'submit a payment',
                'ready for payment'], '已经进入付款链路，去 Upwork / Expensify 检查并准备提现。')]
        for event_type, keywords, action_text in rules:
            for keyword in keywords:
                if keyword not in lower:
                    continue
                return {
                    'event_type': event_type,
                    'keyword': keyword,
                    'action_text': action_text }
        return None

    
    def _run_osascript(self, script = None, timeout = None):
        cp = subprocess.run([
            'osascript',
            '-e',
            script], check = False, capture_output = True, text = True, timeout = timeout)
        if not cp.stdout:
            cp.stdout
        if not cp.stderr:
            cp.stderr
        return {
            'ok': cp.returncode == 0,
            'stdout': str(cp.stdout or '').strip(),
            'stderr': str(cp.stderr or '').strip() }

    
    def _chrome_execute_active_tab_js(self, javascript = None):
        escaped_js = javascript.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
        script = f'tell application "Google Chrome"\nif not running then return ""\nif (count of windows) = 0 then return ""\nreturn execute active tab of front window javascript "{escaped_js}"\nend tell'
        return self._run_osascript(script, timeout = 20)

    
    def _attempt_upwork_offer_auto_accept(self):
        if os.getenv('OPS_UPWORK_AUTO_ACCEPT_OFFER', 'false').lower() not in frozenset({'1', 'on', 'yes', 'true'}):
            return {
                'success': False,
                'status': 'disabled' }
        if not os.getenv('OPS_UPWORK_OFFERS_URL', 'https://www.upwork.com/ab/proposals/offers').strip():
            pass
        offers_url = os.getenv('OPS_UPWORK_OFFERS_URL', 'https://www.upwork.com/ab/proposals/offers').strip() or 'https://www.upwork.com/ab/proposals/offers'
        open_ret = self._run_cmd([
            'open',
            '-a',
            'Google Chrome',
            offers_url], cwd = self.repo_root, timeout = 20)
        if not open_ret.get('ok'):
            return {
                'success': False,
                'status': 'open_failed',
                'error': open_ret.get('stderr', '无法启动 Chrome') }
        js = ''  # JS auto-accept script placeholder
        last_result = {
            'success': False,
            'status': 'unknown' }
        for _ in range(3):
            time.sleep(5)
            exec_ret = self._chrome_execute_active_tab_js(js)
            if not exec_ret.get('ok'):
                last_result = {
                    'success': False,
                    'status': 'script_failed',
                    'error': exec_ret.get('stderr', '') }
                continue
            raw = exec_ret.get('stdout', '')
            payload = json.loads(raw) if raw else { }
            if payload.get('ok'):
                return {
                    'success': True,
                    'status': payload.get('status', 'clicked'),
                    'url': payload.get('url', offers_url),
                    'title': payload.get('title', ''),
                    'button': payload.get('text', '') }
        return last_result

    
    def format_upwork_auto_accept_result(self, result=None):
        """格式化 Upwork 自动接单结果"""
        result = result or {}
        status = result.get('status', 'unknown')
        title = 'Upwork 自动接单'
        if result.get('success'):
            paragraphs = ['Offer 已自动接受！']
        else:
            paragraphs = ['接单失败: ' + result.get('error', '未知错误')]
        return format_announcement(title=title, paragraphs=paragraphs)
    def _attempt_xiaohongshu_publish(self, title = None, body = None):
        title = title or ''
        note_title = str(title or 'OpenClaw 内容草稿').strip()
        body = body or ''
        note_body = str(body or '').strip()
        if not note_body:
            return {
                'success': False,
                'status': 'empty_body' }
        open_ret = self._open_url_in_chrome('https://creator.xiaohongshu.com/publish/publish?source=official')
        if not open_ret.get('ok'):
            return {
                'success': False,
                'status': 'open_failed',
                'error': open_ret.get('stderr', '') }
        time.sleep(8)
        js_template = textwrap.dedent("""
        (() => {
          const titleText = %s;
          const bodyText = %s;
          const url = location.href;
          const title = document.title;
          const bodyPreview = (document.body && document.body.innerText) ? document.body.innerText.slice(0, 1200) : '';
          if (!/xiaohongshu/.test(url) && !/小红书/.test(title + bodyPreview)) {
            return JSON.stringify({ok:false,status:'wrong_context',url,title});
          }
          if (/登录|login/.test((title + ' ' + bodyPreview).toLowerCase())) {
            return JSON.stringify({ok:false,status:'login_required',url,title});
          }
          const titleInput = document.querySelector('input[placeholder*="标题"], textarea[placeholder*="标题"], input.d-text');
          if (titleInput) {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
            if (setter) setter.call(titleInput, titleText);
            titleInput.dispatchEvent(new Event('input', {bubbles:true}));
            titleInput.dispatchEvent(new Event('change', {bubbles:true}));
          }
          const editors = Array.from(document.querySelectorAll('[contenteditable="true"]')).filter((el) => (el.innerText || '').length < 20000);
          const editor = editors.sort((a, b) => (b.innerText || '').length - (a.innerText || '').length)[0];
          if (!editor) {
            return JSON.stringify({ok:false,status:'editor_not_found',url,title});
          }
          editor.focus();
          editor.innerHTML = '';
          const lines = bodyText.split('\\n');
          lines.forEach((line, index) => {
            if (index > 0) editor.appendChild(document.createElement('p'));
            const target = index === 0 ? editor : editor.lastChild;
            if (line) target.appendChild(document.createTextNode(line));
            else target.appendChild(document.createElement('br'));
          });
          editor.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:bodyText}));
          const buttons = Array.from(document.querySelectorAll('button'));
          const submit = buttons.find((btn) => /发布|publish/i.test(btn.innerText || btn.textContent || ''));
          if (!submit) {
            return JSON.stringify({ok:false,status:'button_not_found',url,title});
          }
          if (submit.disabled || submit.getAttribute('aria-disabled') === 'true') {
            return JSON.stringify({ok:false,status:'button_disabled',url,title});
          }
          submit.click();
          return JSON.stringify({ok:true,status:'clicked',url,title});
        })();
        """) % (json.dumps(note_title, ensure_ascii=False), json.dumps(note_body, ensure_ascii=False))
        exec_ret = self._chrome_execute_active_tab_js(js_template.strip())
        if not exec_ret.get('ok'):
            return {
                'success': False,
                'status': 'script_failed',
                'error': exec_ret.get('stderr', '') }
        raw_stdout = exec_ret.get('stdout', '') or ''
        payload = json.loads(raw_stdout) if raw_stdout.strip() else {}
        post_status = payload.get('status', 'unknown') or 'unknown'
        post_url = payload.get('url', '') or ''
        post_title = payload.get('title', '') or ''
        return {
            'success': bool(payload.get('ok')),
            'status': post_status,
            'url': post_url,
            'title': post_title,
            'raw': payload }

    
    def publish_social_draft(self, platform = None, draft_id = None):
        platform = platform or 'both'
        platform_name = str(platform or '').strip().lower()
        draft_id = draft_id or ''
        if int(draft_id or 0) > 0:
            draft = self.get_social_draft(int(draft_id))
        else:
            rows = self.list_social_drafts(platform = platform_name, status = 'draft', limit = 1)
            draft = rows[0] if rows else None
        if not draft:
            return {
                'success': False,
                'error': '没有可发布的草稿' }
        browser = self.ensure_social_browser([
            platform_name])
        if not browser.get('success'):
            return {
                'success': False,
                'platform': platform_name,
                'draft_id': draft.get('id', 0),
                'status': 'browser_failed',
                'url': '',
                'title': draft.get('title', ''),
                'error': browser.get('error', '专用浏览器启动失败'),
                'body_preview': draft.get('body', '')[:240],
                'browser': browser }
        if self._social_browser_missing_logins(browser, [
            platform_name]):
            return {
                'success': False,
                'platform': platform_name,
                'draft_id': draft.get('id', 0),
                'status': 'login_required',
                'url': '',
                'title': draft.get('title', ''),
                'error': self._social_browser_login_error([
                    platform_name], browser),
                'body_preview': draft.get('body', '')[:240],
                'browser': browser }
        if platform_name == 'x':
            result = self._run_social_worker('publish_x', {
                'text': draft.get('body', ''),
                'images': [] })
        elif platform_name == 'xiaohongshu':
            result = self._run_social_worker('publish_xhs', {
                'title': draft.get('title', ''),
                'body': draft.get('body', ''),
                'images': [] })
        else:
            return {
                'success': False,
                'error': '仅支持 x / xiaohongshu' }
        if result.get('success'):
            self.update_social_draft_status(draft.get('id', 0), 'published', result.get('url', ''))
        return {
            'success': bool(result.get('success')),
            'platform': platform_name,
            'draft_id': draft.get('id', 0),
            'status': result.get('status', 'unknown'),
            'url': result.get('url', ''),
            'title': result.get('title', ''),
            'error': result.get('error', ''),
            'body_preview': str(draft.get('body', ''))[:240],
            'browser': browser }

    
    def _build_payout_state_hash(self, issue = None):
        labels = issue.get('labels', [])
        assignees = issue.get('assignees', [])
        state = issue.get('state', '')
        updated_at = issue.get('updated_at', '')
        payload = {
            'state': state,
            'labels': labels,
            'assignees': assignees,
            'updated_at': updated_at }
        raw = json.dumps(payload, ensure_ascii = False, sort_keys = True)
        return hashlib.sha1(raw.encode('utf-8', errors = 'ignore')).hexdigest()

    
    async def check_payout_watches_once(self):
        self.sync_payout_watches_from_env()
        watches = self.list_payout_watches() or []
        all_alerts = []
        for watch in watches:
            repo = watch.get('repo', '')
            issue_number = watch.get('issue_number', 0)
            if not repo or not issue_number:
                continue
            snapshot = self._fetch_github_issue_snapshot(repo, issue_number)
            if not snapshot.get('success'):
                continue
            issue_raw = snapshot.get('issue', '{}')
            comments_raw = snapshot.get('comments', '[]')
            try:
                issue = json.loads(issue_raw) if isinstance(issue_raw, str) else issue_raw
            except (json.JSONDecodeError, TypeError):
                continue
            try:
                comments = json.loads(comments_raw) if isinstance(comments_raw, str) else comments_raw
            except (json.JSONDecodeError, TypeError):
                comments = []
            state_hash = self._build_payout_state_hash(issue)
            db_key = f"payout_watch_{repo}#{issue_number}"
            if self._payout_seen_hashes.get(db_key) == state_hash:
                continue
            alerts = []
            for comment in (comments or []):
                body = comment.get('body', '')
                user_login = (comment.get('user') or {}).get('login', '')
                if user_login == 'MelvinBot':
                    continue
                classified = self._classify_payout_comment(body)
                if classified is None:
                    continue
                if isinstance(classified, tuple):
                    classified = classified[-1] if isinstance(classified[-1], dict) else {}
                if not isinstance(classified, dict):
                    continue
                event_type = classified.get('event_type', '')
                if not event_type:
                    continue
                alerts.append({
                    'event_type': event_type,
                    'keyword': classified.get('keyword', ''),
                    'action_text': classified.get('action_text', ''),
                    'comment_url': comment.get('html_url', ''),
                    'issue_url': issue.get('html_url', ''),
                    'source': f"{repo}#{issue_number}",
                })
            self._payout_seen_hashes[db_key] = state_hash
            all_alerts.extend(alerts)
        return all_alerts

    
    def format_payout_alert(self, alert=None):
        """格式化 Payout 告警通知"""
        alert = alert or {}
        event_type = alert.get('event_type', '')
        action_text = alert.get('action_text', '')
        source = alert.get('source', '')
        issue_url = alert.get('issue_url', '')
        title = 'Payout 信号'
        paragraphs = []
        if event_type == 'payment':
            paragraphs.append('准备提现')
        paragraphs.append(f'来源: {source}')
        paragraphs.append(f'信号: {event_type}')
        paragraphs.append(f'详情: {action_text}')
        if issue_url:
            paragraphs.append(f'链接: {issue_url}')
        return format_announcement(title=title, paragraphs=paragraphs)
    async def create_reminder(self, message = None, delay_minutes = None):
        message = message or ''
        msg = str(message).strip()
        if not msg:
            return {'success': False, 'error': '提醒内容不能为空'}
        delay_minutes = max(1, _safe_int(delay_minutes, 5))
        remind_at = (datetime.now() + timedelta(minutes=delay_minutes)).isoformat()
        try:
            with self._conn() as conn:
                cursor = conn.execute(
                    "INSERT INTO reminders (message, remind_at, status, created_at) VALUES (?, ?, 'pending', ?)",
                    (msg, remind_at, datetime.now().isoformat()))
                reminder_id = cursor.lastrowid
            return {'success': True, 'reminder_id': reminder_id, 'message': msg,
                    'remind_at': remind_at, 'delay_minutes': delay_minutes}
        except Exception as e:
            logger.error(f"[CreateReminder] failed: {e}")
            return {'success': False, 'error': str(e)}

    
    def _run_local_home_action(self, action = None, payload = None):
        action = action or ''
        act = str(action or '').strip().lower()
        payload = payload or {}
        data = dict(payload)
        if not act or act in frozenset({'noop', 'ping', 'health'}):
            return {
                'success': True,
                'mode': 'local',
                'action': 'ping',
                'status_code': 200,
                'response': 'pong' }
        if act in frozenset({'提醒', 'notify', 'notification', '通知'}):
            message = str(data.get('message', '')).strip()
            title = str(data.get('title', 'OpenClaw')).strip() or 'OpenClaw'
            if not message:
                return {
                    'success': False,
                    'mode': 'local',
                    'error': 'notify 需要 message 字段' }
            safe_title = title.replace('"', '')
            safe_message = message.replace('"', '')
            cp = subprocess.run([
                'osascript',
                '-e',
                f'display notification "{safe_message}" with title "{safe_title}"'], check = False, capture_output = True, text = True, timeout = 8)
            return {
                'success': cp.returncode == 0,
                'mode': 'local',
                'action': 'notify',
                'status_code': 200 if cp.returncode == 0 else 500,
                'response': str(cp.stdout or '').strip()[:300] }
        if act in frozenset({'打开链接', 'url', 'open_url'}):
            url = str(data.get('url', '')).strip()
            if not url:
                return {
                    'success': False,
                    'mode': 'local',
                    'error': 'open_url 需要 url 字段' }
            cp = subprocess.run([
                'open',
                url], check = False, capture_output = True, text = True, timeout = 8)
            return {
                'success': cp.returncode == 0,
                'mode': 'local',
                'action': 'open_url',
                'status_code': 200 if cp.returncode == 0 else 500,
                'response': str(cp.stdout or '').strip()[:300] }
        if act in frozenset({'打开应用', 'app', 'open_app'}):
            app_name = str(data.get('app', data.get('name', ''))).strip()
            if not app_name:
                return {
                    'success': False,
                    'mode': 'local',
                    'error': 'open_app 需要 app/name 字段' }
            cp = subprocess.run([
                'open',
                '-a',
                app_name], check = False, capture_output = True, text = True, timeout = 12)
            return {
                'success': cp.returncode == 0,
                'mode': 'local',
                'action': 'open_app',
                'status_code': 200 if cp.returncode == 0 else 500,
                'response': str(cp.stdout or '').strip()[:300] }
        if act in frozenset({'朗读', 'say', 'speak'}):
            text = str(data.get('text', '')).strip()
            voice = data.get('voice')
            if not text:
                return {
                    'success': False,
                    'mode': 'local',
                    'error': 'say 需要 text 字段' }
            cmd = [
                'say']
            if voice:
                cmd.extend([
                    '-v',
                    voice])
            cmd.append(text)
            cp = subprocess.run(cmd, check = False, capture_output = True, text = True, timeout = 20)
            return {
                'success': cp.returncode == 0,
                'mode': 'local',
                'action': 'say',
                'status_code': 200 if cp.returncode == 0 else 500,
                'response': str(cp.stdout or '').strip()[:300] }
        if act in frozenset({'快捷指令', 'shortcut', 'run_shortcut'}):
            name = str(data.get('name', data.get('shortcut', ''))).strip()
            if not name:
                return {
                    'success': False,
                    'mode': 'local',
                    'error': 'shortcut 需要 name/shortcut 字段' }
            cp = subprocess.run([
                'shortcuts',
                'run',
                name], check = False, capture_output = True, text = True, timeout = 30)
            return {
                'success': cp.returncode == 0,
                'mode': 'local',
                'action': 'shortcut',
                'status_code': 200 if cp.returncode == 0 else 500,
                'response': str(cp.stdout or '').strip()[:300] }
        return {
            'success': False,
            'mode': 'local',
            'status_code': 400,
            'error': '不支持的本地动作，支持: ping/notify/open_url/open_app/say/shortcut' }

    
    async def trigger_home_action(self, action = None, payload = None):
        try:
            result = self._run_local_home_action(action, payload)
            return result
        except Exception as e:
            logger.error(f"[TriggerHome] failed: {e}")
            return {'success': False, 'error': str(e)}

    
    def generate_project_report(self, project_dir = None, days = None):
        root = Path(project_dir).expanduser().resolve()
        if not root.exists():
            return f'项目目录不存在: {root}'
        cmd = [
            'git',
            'log',
            f'--since={days} days ago',
            '--pretty=format:%h|%an|%ad|%s',
            '--date=short']
        commits = self._run_cmd(cmd, cwd = str(root), timeout = 20)
        lines = [
            f'项目周报 ({root.name})',
            '']

    
    def run_dev_workflow(self, project_dir = None):
        root = Path(project_dir).expanduser().resolve()
        if not root.exists():
            return {
                'success': False,
                'error': f'目录不存在: {root}' }
        custom = os.getenv('OPS_DEV_WORKFLOW_COMMANDS', '').strip()
        commands = []

    
    async def start_scheduler(self, notify_func, private_notify_func=None):
        self._notify_func = notify_func
        self._private_notify_func = private_notify_func
        self._scheduler_running = True
        self._scheduler_task = asyncio.ensure_future(self._scheduler_loop())
        logger.info("[Scheduler] started")

    async def stop_scheduler(self):
        self._scheduler_running = False
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        self._scheduler_task = None
        logger.info("[Scheduler] stopped")

    async def _scheduler_loop(self):
        brief_time = _parse_hhmm(os.getenv('OPS_BRIEF_TIME'), (8, 0))
        monitor_interval = max(1, _safe_int(os.getenv('OPS_MONITOR_INTERVAL_MIN'), 15)) * 60
        bounty_interval = max(1, _safe_int(os.getenv('OPS_BOUNTY_INTERVAL_MIN'), 45)) * 60
        social_op_interval = _safe_int(os.getenv('OPS_SOCIAL_OPERATOR_CHECK_INTERVAL_MIN'), 0) * 60

        while self._scheduler_running:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            now = datetime.now()
            ts = time.time()

            # Daily brief — 只在指定时间推一次
            if os.getenv('OPS_BRIEF_ENABLED', '').lower() in ('1', 'true', 'yes', 'on'):
                today = now.strftime('%Y-%m-%d')
                if today != self._last_brief_date and now.hour == brief_time[0] and now.minute >= brief_time[1]:
                    try:
                        result = await self.generate_daily_brief()
                        self._last_brief_date = today
                        # 门控：brief 必须有实际内容才推送
                        if self._notify_func and result and len(str(result).strip()) > 20:
                            await self._notify_func(result)
                    except Exception as e:
                        logger.error(f"[Scheduler] daily brief failed: {e}")

            # Monitors — 只推有新增告警的结果
            if os.getenv('OPS_MONITOR_ENABLED', '').lower() in ('1', 'true', 'yes', 'on'):
                if ts - self._last_monitor_ts >= monitor_interval:
                    try:
                        result = await self.run_monitors_once()
                        self._last_monitor_ts = ts
                        # 门控：空列表/无告警不推送
                        if self._notify_func and result and isinstance(result, list) and len(result) > 0:
                            formatted = "\n\n".join(self.format_monitor_alert(al) for al in result if al)
                            if formatted.strip():
                                await self._notify_func(formatted)
                        elif self._notify_func and result and isinstance(result, str) and len(result.strip()) > 10:
                            await self._notify_func(result)
                    except Exception as e:
                        logger.error(f"[Scheduler] monitor failed: {e}")

            # Social operator — 静默运行，不主动推送（结果写入 state 文件）
            if social_op_interval > 0:
                if ts - self._last_social_operator_ts >= social_op_interval:
                    try:
                        await self.run_social_autopilot_once()
                        self._last_social_operator_ts = ts
                    except Exception as e:
                        logger.error(f"[Scheduler] social operator failed: {e}")

            # Bounty scan — 只推有新增线索的结果到私聊
            if os.getenv('OPS_BOUNTY_ENABLED', '').lower() in ('1', 'true', 'yes', 'on'):
                if ts - self._last_bounty_ts >= bounty_interval:
                    try:
                        result = await self.scan_bounties()
                        self._last_bounty_ts = ts
                        # 门控：只有新增入库 > 0 才推送
                        saved = (result or {}).get('saved', {}) if isinstance(result, dict) else {}
                        new_count = int(saved.get('inserted', 0) or 0)
                        if self._private_notify_func and new_count > 0:
                            await self._private_notify_func(
                                f"🎯 赏金扫描完成 | 新增 {new_count} 条线索\n"
                                f"入库: {saved.get('total', 0)} (更新{saved.get('updated', 0)})\n"
                                f"下一步: /ops bounty top"
                            )
                    except Exception as e:
                        logger.error(f"[Scheduler] bounty scan failed: {e}")

            # 每小时清理过期的待确认交易，防止内存泄漏
            if now.minute == 0:
                try:
                    from src.bot.globals import _cleanup_pending_trades
                    _cleanup_pending_trades()
                except Exception:
                    pass

    
    def _run_cmd(self, cmd=None, cwd=None, timeout=30):
        """运行 shell 命令"""
        cmd = cmd or []
        cp = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                            timeout=timeout, check=False)
        return {
            'ok': cp.returncode == 0,
            'stdout': cp.stdout or '',
            'stderr': cp.stderr or '',
            'returncode': cp.returncode,
        }
