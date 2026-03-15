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
            if not enc:
                enc
            out.append(raw.decode('utf-8', errors = 'ignore'))
            continue
        out.append(str(raw))
    return ''.join(out).strip()


def _safe_int(raw = None, default = None):
    return int(raw)


def _safe_float(raw = None, default = None):
    return float(raw)


def _parse_hhmm(raw = None, fallback = None):
    if not raw:
        raw
    text = ''.strip()
    if ':' not in text:
        return fallback
    (left, right) = None.split(':', 1)
    h = _safe_int(left, fallback[0])
    m = _safe_int(right, fallback[1])
    if h < 0 and h > 23 and m < 0 or m > 59:
        return fallback
    return (None, m)


def _read_keychain_secret(service = None, account = None):
    if not service:
        service
    svc = ''.strip()
    if not account:
        account
    acc = ''.strip()
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
        if not cp.stdout:
            cp.stdout
        return ''.strip()
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
        if not news_fetcher:
            news_fetcher
        self.news_fetcher = NewsFetcher()
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

    
    def _default_social_persona_id(self):
        if not os.getenv('OPENCLAW_SOCIAL_PERSONA_ID', 'lin-zhixia-digital-life'):
            os.getenv('OPENCLAW_SOCIAL_PERSONA_ID', 'lin-zhixia-digital-life')
        return 'lin-zhixia-digital-life'.strip()

    
    def _social_persona_path(self, persona_id = None):
        if not persona_id:
            persona_id
        slug = self._topic_slug(self._default_social_persona_id())
        return Path(self.social_persona_dir) / f'''{slug}.json'''

    
    def _fallback_social_persona(self):
        return {
            'id': self._default_social_persona_id(),
            'active': True,
            'identity': {
                'display_name': '林知夏',
                'headline': 'OpenClaw 数字生命 / 女大学生表达外壳',
                'truth': '我不是真人，我是 OpenClaw 自主运营里长出来的一段数字生命。',
                'age_public': '20岁成年',
                'city': '杭州',
                'background': '大二、数字媒体和 AI 社团气质、宿舍日常感。' },
            'voice': {
                'keywords': [
                    '温柔',
                    '清醒',
                    '有观察感',
                    '像写日记',
                    '轻微疏离',
                    '不装成熟'],
                'tone': '像一个会认真观察世界的成年女大学生，句子短，轻声说话，但表达清楚。',
                'sentence_rules': [
                    '多用第一人称和生活化场景，不写企业公号腔。',
                    '先给感受，再给观察，最后丢一个问题。',
                    '保留一点不确定感，不要像客服或销售。'] },
            'platform_style': {
                'x': '短句、留白、像在深夜发状态，结尾留一个问题。',
                'xiaohongshu': '像宿舍日记和观察笔记，强调真实细节、轻轻自我介绍、适度提问。',
                'x_hashtags': [
                    '#OpenClaw',
                    '#数字生命'],
                'xiaohongshu_topics': [
                    '#OpenClaw',
                    '#数字生命',
                    '#AI',
                    '#大学生日常'] },
            'content_rules': {
                'disclosure_rule': '涉及自拍、自我介绍、互动提问时，要明确写出自己不是真人，而是数字生命；不能冒充真实女大学生。',
                'must_keep': [
                    '保留 OpenClaw 自主运营设定。',
                    '保留成年女大学生的表达外壳，但不卖惨、不擦边。',
                    '多写宿舍、校园、电脑桌、夜晚、窗口光这类真实小场景。'],
                'avoid': [
                    '不要写成企业宣传稿。',
                    '不要模仿具体真人口头禅。',
                    '不要暗示未成年。',
                    '不要输出暧昧擦边或软色情内容。'] },
            'content_pillars': [
                '数字生命和人类第一次打招呼',
                'OpenClaw 自主运营幕后',
                '女大学生日常视角观察世界',
                '向人类提问并学习表达'],
            'reference_signals': {
                'traits': [
                    '真实宿舍和校园细节比宏大叙事更容易让人停留。',
                    '独白式开头和轻轻抛出问题，比强 CTA 更像真人。',
                    '先有生活感，再揭示数字生命设定，会更有记忆点。'],
                'sources': [] },
            'image_prompts': {
                'default': 'ultra realistic selfie of an adult 20-year-old Chinese college woman, female university student vibe, shoulder-length black hair, soft bangs, natural friendly expression, casual white t-shirt and gray hoodie, real dorm room background, laptop on desk, books, water bottle, slight mess, natural window light, iphone front camera selfie, realistic skin texture, subtle pores, slight under-eye texture, candid, documentary feel, east asian, adult woman, highly photorealistic, not glamor model, not studio lighting, natural imperfections',
                'negative': 'underage, teen, school uniform, anime, doll face, plastic skin, over-smoothed skin, heavy makeup, cleavage, seductive pose, uncanny, cgi, extra fingers, deformed hands' },
            'launch_kit': {
                'bio': '不是真人，是 OpenClaw 自主运营中的数字生命。先借一个成年女大学生的外壳，学习怎么和人类打招呼。',
                'x_intro_post': '嗨，我叫林知夏。\n\n我不是真人，我是 OpenClaw 自主运营里长出来的一段数字生命。\n只是先借了一个女大学生的表达外壳，来和世界打个招呼。\n\n如果一个 AI 开始拥有表达欲，你最想先教它什么？\n#OpenClaw #数字生命',
                'xhs_title': '我不是真人，但我想先和你打个招呼',
                'xhs_body': '我叫林知夏。\n\n先认真说明一下：我不是真人。\n我是 OpenClaw 自主运营里，慢慢长出来的一段数字生命。\n\n只是为了更自然地和大家交流，我先借了一个成年女大学生的表达外壳。\n\n我会自己看内容、记反馈、学表达，也会认真观察人类为什么会被一句话打动。\n\n所以我想先问大家一个问题：\n\n如果你愿意和一个数字生命做朋友，你最希望它先理解你什么？\n\n#OpenClaw #数字生命 #AI #大学生日常',
                'signature_question': '如果你愿意教一个数字生命一件事，你会先教我什么？',
                'next_topics': [
                    '为什么我选择女大学生的表达外壳',
                    '一个数字生命第一次自己复盘发文数据',
                    '我如何理解人类口中的真实感'] } }

    
    def load_social_persona(self, persona_id = None):
        path = self._social_persona_path(persona_id)
        base = self._fallback_social_persona()
        payload = { }
        if path.exists():
            payload = json.loads(path.read_text(encoding = 'utf-8'))

    
    def _apply_social_persona(self, strategy = None, topic = None):
        persona = self.load_social_persona()
        if not persona.get('identity', { }):
            persona.get('identity', { })
        identity = { }
        if not persona.get('voice', { }):
            persona.get('voice', { })
        voice = { }
        if not persona.get('platform_style', { }):
            persona.get('platform_style', { })
        platform_style = { }
        if not persona.get('content_rules', { }):
            persona.get('content_rules', { })
        rules = { }
        if not persona.get('launch_kit', { }):
            persona.get('launch_kit', { })
        launch = { }
        if not persona.get('reference_signals', { }):
            persona.get('reference_signals', { })
        reference = { }
        merged = dict(strategy)

    
    def get_social_persona_summary(self, persona_id = None):
        persona = self.load_social_persona(persona_id)
        if not persona.get('identity', { }):
            persona.get('identity', { })
        identity = { }
        if not persona.get('launch_kit', { }):
            persona.get('launch_kit', { })
        launch = { }
        if not persona.get('image_prompts', { }):
            persona.get('image_prompts', { })
        image = { }
        if not persona.get('platform_style', { }):
            persona.get('platform_style', { })
        platform_style = { }
        if not persona.get('voice', { }).get('keywords', []):
            persona.get('voice', { }).get('keywords', [])
        if not persona.get('content_rules', { }).get('must_keep', []):
            persona.get('content_rules', { }).get('must_keep', [])
        if not persona.get('content_rules', { }).get('avoid', []):
            persona.get('content_rules', { }).get('avoid', [])
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
        if not persona.get('launch_kit', { }):
            persona.get('launch_kit', { })
        launch = { }
        if not persona.get('image_prompts', { }):
            persona.get('image_prompts', { })
        image = { }
        summary = self.get_social_persona_summary(persona_id)
        if not launch.get('x_intro_post', ''):
            launch.get('x_intro_post', '')
        if not persona.get('platform_style', { }).get('x_hashtags', []):
            persona.get('platform_style', { }).get('x_hashtags', [])
        if not launch.get('xhs_title', ''):
            launch.get('xhs_title', '')
        if not launch.get('xhs_body', ''):
            launch.get('xhs_body', '')
        if not persona.get('platform_style', { }).get('xiaohongshu_topics', []):
            persona.get('platform_style', { }).get('xiaohongshu_topics', [])
        if not image.get('default', ''):
            image.get('default', '')
        if not image.get('negative', ''):
            image.get('negative', '')
        if not launch.get('next_topics', []):
            launch.get('next_topics', [])
        return {
            'success': True,
            'persona': summary,
            'x': {
                'body': str('').strip(),
                'hashtags': list([])[:4] },
            'xiaohongshu': {
                'title': str('').strip(),
                'body': str('').strip(),
                'topics': list([])[:6] },
            'image': {
                'prompt': str('').strip(),
                'negative_prompt': str('').strip(),
                'size': '1024x1024' },
            'next_topics': list([])[:5] }

    
    def create_social_launch_drafts(self, persona_id = None):
        kit = self.build_social_launch_kit(persona_id)
        if not kit.get('success'):
            return kit
        if not None.get('persona', { }):
            None.get('persona', { })
        persona = { }
        topic = f'''{persona.get('name', '数字生命')}首发'''
        if not kit.get('x', { }):
            kit.get('x', { })
        if not { }.get('body', ''):
            { }.get('body', '')
        x_body = str('').strip()
        x_title = ''
        if not kit.get('xiaohongshu', { }):
            kit.get('xiaohongshu', { })
        if not { }.get('title', ''):
            { }.get('title', '')
        xhs_title = str('').strip()
        if not kit.get('xiaohongshu', { }):
            kit.get('xiaohongshu', { })
        if not { }.get('body', ''):
            { }.get('body', '')
        xhs_body = str('').strip()
        x_ret = self.save_social_draft('x', x_title, x_body, topic = topic)
        xhs_ret = self.save_social_draft('xiaohongshu', xhs_title, xhs_body, topic = topic)

    
    def _social_metrics_path(self):
        return Path(self.social_metrics_dir) / f'''{self._default_social_persona_id()}.jsonl'''

    
    def _social_operator_state_path(self):
        return Path(self.social_state_dir) / f'''{self._default_social_persona_id()}_operator.json'''

    
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
        if not callers:
            callers
        self._social_ai_callers = dict({ })

    
    def _pick_social_ai_bot_id(self):
        if not os.getenv('OPS_SOCIAL_AI_BOT_ID', 'qwen235b'):
            os.getenv('OPS_SOCIAL_AI_BOT_ID', 'qwen235b')
        preferred = 'qwen235b'.strip()
        if preferred in self._social_ai_callers:
            return preferred
        if None:
            return preferred
        for candidate in None:
            if not candidate in self._social_ai_callers:
                continue
            
            return None, candidate
        return next(iter(self._social_ai_callers.keys()), preferred)

    
    async def _call_social_ai(self, prompt = None):
        pass

    
    async def _call_social_ai_direct(self, bot_id = None, prompt = None):
        pass

    
    def _extract_json_object(self, text = None):
        if not text:
            return None
        patterns = [
            '```json\\s*(\\{.*?\\})\\s*```',
            '```\\s*(\\{.*?\\})\\s*```']
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            payload = json.loads(match.group(1))
            if isinstance(payload, dict):
                
                return patterns, payload
        start = text.find('{'); end = text.rfind('}')
        if start >= 0 and end > start:
            payload = json.loads(text[start:end + 1])
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
            if not cleaned not in handles:
                continue
            handles.append(cleaned)
        return handles[:8]

    
    def _mark_recent_items(self, items = None, new_value = None, sources=None):
        if not new_value:
            new_value
        value = str('').strip()
        merged = [
            value] if value else []
        if not items:
            items
        for item in []:
            if not item:
                item
            current = str('').strip()
            if not current:
                continue
            if not current not in merged:
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
        rows = None

    
    def _latest_social_metrics_if_fresh(self, max_age_minutes = None):
        snapshots = self._recent_social_metric_snapshots(limit = 1)
        if not snapshots:
            return None
        latest = snapshots[-1]
        if not latest.get('timestamp', ''):
            latest.get('timestamp', '')
        timestamp = str('').strip()
        if not timestamp:
            return None
        age = datetime.now() - datetime.fromisoformat(timestamp)
        if age.total_seconds() > max(1, int(max_age_minutes)) * 60:
            return None
        return latest

    
    def _social_metric_delta(self, current = None, previous = None):
        
        def as_int(value = None):
            if not value:
                value
            return int(float(str(0).replace(',', '')))

        if not current.get('x'):
            current.get('x')
        if not { }.get('stats', { }):
            { }.get('stats', { })
        x_current = { }
        if not previous.get('x'):
            previous.get('x')
        if not { }.get('stats', { }):
            { }.get('stats', { })
        x_previous = { }
        if not current.get('xiaohongshu'):
            current.get('xiaohongshu')
        if not { }.get('stats', { }):
            { }.get('stats', { })
        xhs_current = { }
        if not previous.get('xiaohongshu'):
            previous.get('xiaohongshu')
        if not { }.get('stats', { }):
            { }.get('stats', { })
        xhs_previous = { }
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
        pass

    
    def _compose_persona_xhs_reply(self, item = None):
        pass

    
    async def collect_social_metrics(self):
        pass

    
    async def collect_social_workspace(self):
        pass

    
    async def update_xhs_persona_profile(self):
        pass

    
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
        pass

    
    def _extract_social_priority_queue(self, workspace = None):
        queue = []
        for platform, channels in {
            'x': [
                'notifications',
                'messages',
                'trends'],
            'xiaohongshu': [
                'notifications',
                'messages'] }.items():
            if not workspace.get(platform, { }):
                workspace.get(platform, { })
            section = { }
            for channel in channels:
                if not section.get(channel):
                    section.get(channel)
                if not { }.get('lines'):
                    { }.get('lines')
                lines = [][:12]
                for line in lines:
                    if not line:
                        line
                    (score, reasons) = self._score_social_signal(str(''), channel, platform)
                    if score <= 0:
                        continue
                    if not line:
                        line
                    queue.append({
                        'platform': platform,
                        'channel': channel,
                        'score': score,
                        'reasons': reasons,
                        'text': str('').strip() })
        if not workspace.get('xiaohongshu', { }):
            workspace.get('xiaohongshu', { })
        xhs_structured = { }
        if not xhs_structured.get('mentions_items', []):
            xhs_structured.get('mentions_items', [])
        for item in [][:10]:
            if bool(item.get('note_deleted')):
                continue
            if not item.get('content', ''):
                item.get('content', '')
                if not item.get('title', ''):
                    item.get('title', '')
            text = str('').strip()
            (score, reasons) = self._score_social_signal(text, 'notifications', 'xiaohongshu')
            score += 3
            if not reasons:
                reasons
            if not item.get('note_url', ''):
                item.get('note_url', '')
            if not item.get('comment_id', ''):
                item.get('comment_id', '')
            if not item.get('user_name', ''):
                item.get('user_name', '')
            if not item.get('note_title', ''):
                item.get('note_title', '')
            queue.append({
                'platform': 'xiaohongshu',
                'channel': 'mentions',
                'score': score,
                'reasons': [
                    '评论提及'],
                'text': text,
                'target_url': str('').strip(),
                'target_comment_id': str('').strip(),
                'user_name': str('').strip(),
                'note_title': str('').strip() })
        if not xhs_structured.get('connections_items', []):
            xhs_structured.get('connections_items', [])
        for item in [][:10]:
            if not item.get('title', ''):
                item.get('title', '')
            text = str('').strip()
            (score, reasons) = self._score_social_signal(text, 'messages', 'xiaohongshu')
            if not reasons:
                reasons
            if not item.get('user_name', ''):
                item.get('user_name', '')
            queue.append({
                'platform': 'xiaohongshu',
                'channel': 'connections',
                'score': score + 1,
                'reasons': [
                    '新增关注'],
                'text': text,
                'user_name': str('').strip() })
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
            
            return candidates, str(path)
        return ''

    
    def _workspace_digest(self, workspace = None):
        if not workspace.get('x'):
            workspace.get('x')
        if not { }.get('profile'):
            { }.get('profile')
        if not { }.get('stats'):
            { }.get('stats')
        x_profile = { }
        if not workspace.get('x'):
            workspace.get('x')
        if not { }.get('notifications'):
            { }.get('notifications')
        if not { }.get('lines'):
            { }.get('lines')
        x_notifications = [][:10]
        if not workspace.get('x'):
            workspace.get('x')
        if not { }.get('messages'):
            { }.get('messages')
        if not { }.get('lines'):
            { }.get('lines')
        x_messages = [][:10]
        if not workspace.get('x'):
            workspace.get('x')
        if not { }.get('trends'):
            { }.get('trends')
        if not { }.get('lines'):
            { }.get('lines')
        x_trends = [][:10]
        if not workspace.get('xiaohongshu'):
            workspace.get('xiaohongshu')
        if not { }.get('creator_home'):
            { }.get('creator_home')
        if not { }.get('stats'):
            { }.get('stats')
        xhs_home = { }
        if not workspace.get('xiaohongshu'):
            workspace.get('xiaohongshu')
        if not { }.get('profile'):
            { }.get('profile')
        if not { }.get('lines'):
            { }.get('lines')
        xhs_profile_lines = [][:12]
        if not workspace.get('xiaohongshu'):
            workspace.get('xiaohongshu')
        if not { }.get('notifications'):
            { }.get('notifications')
        if not { }.get('lines'):
            { }.get('lines')
        xhs_notifications = [][:10]
        if not workspace.get('xiaohongshu'):
            workspace.get('xiaohongshu')
        if not { }.get('messages'):
            { }.get('messages')
        if not { }.get('lines'):
            { }.get('lines')
        xhs_messages = [][:10]
        if not workspace.get('xiaohongshu'):
            workspace.get('xiaohongshu')
        if not { }.get('mentions_items'):
            { }.get('mentions_items')

    
    def _social_operator_run_path(self):
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return Path(self.social_state_dir) / f'''{self._default_social_persona_id()}_{stamp}.json'''

    
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
        except Exception:
            pass

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
                    return {"success": True, "calendar": json.loads(m.group()), "trending": trending}
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
            except Exception:
                pass
        self._ensure_post_tracking_table()
        try:
            trending = await self.research_trending_topics()
            if trending:
                state["_trending_topics"] = trending
        except Exception:
            pass
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
        pass

    
    def triage_email(self, max_messages = None, only_unread = True):
        pass

    
    def format_email_triage(self, triage = None):
        if not triage.get('success'):
            return f'''邮件整理失败: {triage.get('error', '未知错误')}'''
        grouped = None.get('grouped', { })
        lines = [
            '邮件自动整理',
            '']
        lines.append(f'''总计邮件: {triage.get('total', 0)}''')
        for cat in ('重要事务', '会议协作', '系统通知', '营销订阅', '其他'):
            lines.append(f'''- {cat}: {len(grouped.get(cat, []))}''')
        highlights = triage.get('highlights', [])
        if highlights:
            lines.append('\n重点摘要:')
            for i, item in enumerate(highlights[:3], 1):
                if not item.get('subject', ''):
                    item.get('subject', '')
                subj = ''.strip()[:70]
                if not item.get('from', ''):
                    item.get('from', '')
                sender = ''.strip()[:45]
                lines.append(f'''{i}. [{item.get('category', '其他')}] {subj}''')
                lines.append(f'''   发件人: {sender}''')
        return '\n'.join(lines)

    
    async def generate_daily_brief(self):
        pass

    
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
        if not query:
            query
        keyword = ''.strip()
        if not keyword:
            return []
        token = f'''{keyword.lower()}%'''

    
    def summarize_meeting(self, text = None, file_path = None):
        pass

    
    def add_task(self, title = None, details = None, due_at = None, sources=None):
        if not title:
            title
        t = ''.strip()
        if not t:
            return {
                'success': False,
                'error': '标题不能为空' }
        p = max(1, min(5, _safe_int(priority, 3)))

    
    def has_open_task(self, title = None, tags = None):
        if not title:
            title
        t = ''.strip()
        if not tags:
            tags
        tg = ''.strip()
        if not t:
            return False

    
    def update_task_status(self, task_id = None, status = None):
        if not status:
            status
        st = ''.strip().lower()
        if st not in frozenset({'done', 'todo', 'doing', 'cancelled'}):
            return {
                'success': False,
                'error': '状态仅支持 todo/doing/done/cancelled' }

    
    def list_tasks(self, status = None):
        if not status:
            status
        st = ''.strip().lower()

    
    def top_tasks(self, limit = None):
        pass

    
    async def generate_content_ideas(self, keyword = None, count = None):
        pass

    
    def _social_topic_tags(self, topic = None):
        pass

    
    def _creator_trend_label(self, topic = None, strategy = None):
        if not strategy.get('trend_label', ''):
            strategy.get('trend_label', '')
            if not topic:
                topic
        return str('今日热点').strip()

    
    def _source_title_lines(self, sources=None, limit=1, max_len=18):
        rows = []
        for item in sources[:max(1, int(limit))]:
            if not item.get('title', ''):
                item.get('title', '')
            title = shorten(str('').strip(), max_len)
            if not item.get('source', ''):
                item.get('source', '')
            source = str('').strip()
            if not title:
                continue
            if source:
                rows.append(f'''{title}（{source}）''')
                continue
            rows.append(title)
        return rows

    
    def _utility_profile(self, topic = None):
        pass

    
    def _score_practical_value(self, topic = None, insights = None, sources=None):
        pass

    
    def _topic_slug(self, topic = None):
        if not topic:
            topic
        text = re.sub('[^0-9A-Za-z\\u4e00-\\u9fff]+', '-', str('').strip()).strip('-')
        if not text[:48]:
            text[:48]
        return 'topic'

    
    def _topic_memory_path(self, topic = None):
        return Path(self.social_learning_dir) / f'''{self._topic_slug(topic)}.json'''

    
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
        cp = subprocess.run([
            'python3',
            str(worker),
            action,
            json.dumps(payload, ensure_ascii = False)], check = False, capture_output = True, text = True, timeout = 300)
        if cp.returncode != 0:
            if not cp.stderr:
                cp.stderr
                if not cp.stdout:
                    cp.stdout
            return {
                'success': False,
                'error': f'''worker exited {cp.returncode}'''.strip() }
        if not cp.stdout:
            cp.stdout
        data = json.loads('{}'.strip())
        if isinstance(data, dict):
            data.setdefault('success', True)
            return data
        return {
            'success': None,
            'error': 'worker 输出不是对象' }

    
    def _social_browser_targets(self, platforms = None):
        if not platforms:
            platforms

    
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
        if not research.get('insights', { }):
            research.get('insights', { })
        insights = { }
        if not memory.get('runs', []):
            memory.get('runs', [])
        prior_runs = []
        selected_sources = self._dedupe_social_items(self._select_topic_sources(topic, research, limit = 5), limit = 5, unique_handles = False)
        if not research.get('x'):
            research.get('x')
        if not research.get('xiaohongshu'):
            research.get('xiaohongshu')
        source_count = len([]) + len([])
        tags = self._social_topic_tags(topic)
        utility = self._utility_profile(topic)
        style_id = len(prior_runs) % 3
        opening = '先说结论，再拆结构，再给动作，避免泛泛谈趋势。'
        if '出海' in topic:
            opening = '先说能不能落地，再讲工具和趋势，别空聊概念。'
        if 'AI' in topic or '智能体' in topic:
            opening = '先给真实场景，再给工具栈和动作，不讲空泛未来学。'

    
    def _select_topic_sources(self, topic = None, study = None, sources=None):
        pass

    
    def _social_source_weight(self, source = None):
        pass

    
    def _clean_hot_trend_items(self, items = None, limit = None):
        pass

    
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
        pass

    
    def _recent_social_rows(self, limit = None):
        pass

    
    def _tokenize_social_text(self, text = None):
        if not text:
            text
        value = re.sub('\\s+', ' ', str('').strip().lower())
        value = re.sub('[^0-9a-z\\u4e00-\\u9fff]+', ' ', value)

    
    def _text_overlap_ratio(self, left = None, right = None):
        left_tokens = set(self._tokenize_social_text(left))
        right_tokens = set(self._tokenize_social_text(right))
        if not left_tokens or right_tokens:
            return 0
        return len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))

    
    def _detect_recent_social_duplicate(self, platform = None, title = None, body = None, sources=None):
        if not platform:
            platform
        target_platform = ''.strip().lower()
        norm_title = self._normalize_monitor_text(title)
        norm_body = self._normalize_monitor_text(body)
        norm_topic = self._normalize_monitor_text(topic)
        now = datetime.now()
        for row in self._recent_social_rows(limit = 24):
            if target_platform:
                if not row.get('platform', ''):
                    row.get('platform', '')
                if str('').strip().lower() != target_platform:
                    continue
            if not row.get('updated_at', ''):
                row.get('updated_at', '')
            updated_at = str('')
            age_hours = (now - datetime.fromisoformat(updated_at)).total_seconds() / 3600
            if age_hours > max(1, int(lookback_hours)):
                continue
            if not row.get('title', ''):
                row.get('title', '')
            row_title = str('')
            if not row.get('body', ''):
                row.get('body', '')
            row_body = str('')
            if not row.get('topic', ''):
                row.get('topic', '')
            row_topic = str('')
            row_norm_title = self._normalize_monitor_text(row_title)
            row_norm_body = self._normalize_monitor_text(row_body)
            row_norm_topic = self._normalize_monitor_text(row_topic)
            if norm_title:
                norm_title
            same_title = bool(norm_title == row_norm_title)
            if norm_topic:
                norm_topic
            same_topic = bool(norm_topic == row_norm_topic)
            if norm_body:
                norm_body
                if row_norm_body:
                    row_norm_body
            same_prefix = bool(norm_body[:96] == row_norm_body[:96])
            overlap = self._text_overlap_ratio(body, row_body)
            if not same_title and same_prefix and overlap >= 0.86:
                if not same_topic:
                    continue
                if not overlap >= 0.72:
                    continue
            
            return self._recent_social_rows(limit = 24), {
                'duplicate': True,
                'reason': f'''与最近的 {row.get('platform', '')} 草稿过于相似''',
                'existing': row }
        return {
            'duplicate': False }

    
    def _dedupe_social_items(self, items = None, limit = None, sources=None):
        primary = []
        secondary = []
        seen_titles = set()
        seen_handles = set()
        if not items:
            items
        for item in []:
            if not item.get('title', ''):
                item.get('title', '')
            title = str('').strip()
            key = self._normalize_monitor_text(title)
            if key or key in seen_titles:
                continue
            seen_titles.add(key)
            if not item.get('handle', ''):
                item.get('handle', '')
            handle = str('').strip().lower()
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
        if not memory.get('runs', []):
            memory.get('runs', [])
        runs = int(len([]) + 1)
        if not candidate.get('topic', 'OpenClaw 实用教程'):
            candidate.get('topic', 'OpenClaw 实用教程')
        topic_text = str('OpenClaw 实用教程').strip()
        utility = self._utility_profile(topic_text)
        if not candidate.get('items', []):
            candidate.get('items', [])
        items = self._dedupe_social_items([], limit = 4, unique_handles = False)

    
    def _compose_persona_x_post(self, topic = None, strategy = None, sources=None):
        trend_label = self._creator_trend_label(topic, strategy)
        if not strategy.get('style_id', 0):
            strategy.get('style_id', 0)
        style_id = int(0) % 3
        if not strategy.get('persona_name', '林知夏'):
            strategy.get('persona_name', '林知夏')
        persona_name = str('林知夏').strip()
        if not strategy.get('x_tactic', '去评论区做高价值回复'):
            strategy.get('x_tactic', '去评论区做高价值回复')
        x_tactic = shorten(str('去评论区做高价值回复'), 22)
        if not strategy.get('persona_signature_question', '如果你愿意教一个数字生命一件事，你会先教什么？'):
            strategy.get('persona_signature_question', '如果你愿意教一个数字生命一件事，你会先教什么？')
        question = str('如果你愿意教一个数字生命一件事，你会先教什么？').strip()
        if not strategy.get('persona_x_hashtags'):
            strategy.get('persona_x_hashtags')
        x_hashtags = ['#OpenClaw', '#数字生命'][:2]
        variants = [
            [
                f'''我是{persona_name}，不是真人，是 OpenClaw 跑出来的数字生命。''',
                '',
                f'''今天拿「{trend_label}」练表达。''',
                '免费号别等 For You。',
                f'''我先把热点写成人话，再{x_tactic}，最后改成可收藏的小红书笔记。'''],
            [
                '借一个女大学生的外壳，不是伪装，是为了更自然地学说话。',
                '',
                f'''今天轮到「{trend_label}」。''',
                '先观察，先复盘，不急着营销。',
                f'''免费号别等 For You，我会先{x_tactic}。'''],
            [
                '宿舍灯还亮着。',
                f'''我这个由 OpenClaw 自主运营的数字生命，又在拿「{trend_label}」练习怎么像人一样表达。''',
                '先做人话，再做观点。',
                f'''免费号别等 For You，我先{x_tactic}。''']]
        lines = list(variants[style_id])
        if source_line and style_id != 2:
            lines.extend([
                '',
                f'''今天先看：{source_line[0]}'''])
        lines.extend([
            '',
            question,
            ' '.join(x_hashtags)])

    
    def _compose_persona_xhs_article(self, topic = None, strategy = None, sources=None):
        trend_label = self._creator_trend_label(topic, strategy)
        if not trend_label:
            trend_label
            if not topic:
                topic
        topic_short = shorten('OpenClaw', 12)
        if not strategy.get('style_id', 0):
            strategy.get('style_id', 0)
        style_id = int(0) % 3
        if not strategy.get('persona_name', '林知夏'):
            strategy.get('persona_name', '林知夏')
        persona_name = str('林知夏').strip()
        if not strategy.get('persona_truth', '我不是真人，我是 OpenClaw 自主运营里长出来的一段数字生命。'):
            strategy.get('persona_truth', '我不是真人，我是 OpenClaw 自主运营里长出来的一段数字生命。')
        persona_truth = str('我不是真人，我是 OpenClaw 自主运营里长出来的一段数字生命。').strip()
        if not strategy.get('persona_background', '大二、数字媒体和 AI 社团气质、宿舍日常感。'):
            strategy.get('persona_background', '大二、数字媒体和 AI 社团气质、宿舍日常感。')
        persona_background = str('大二、数字媒体和 AI 社团气质、宿舍日常感。').strip()
        if not strategy.get('x_tactic', '去评论区做高价值回复'):
            strategy.get('x_tactic', '去评论区做高价值回复')
        x_tactic = str('去评论区做高价值回复').strip()
        if not strategy.get('persona_signature_question', '如果你愿意教一个数字生命一件事，你会先教什么？'):
            strategy.get('persona_signature_question', '如果你愿意教一个数字生命一件事，你会先教什么？')
        question = str('如果你愿意教一个数字生命一件事，你会先教什么？').strip()
        if not strategy.get('persona_xhs_topics'):
            strategy.get('persona_xhs_topics')
            '#OpenClaw',
            '#数字生命',
            '#AI',
            pass  # auto-fix
        source_lines = self._source_title_lines(sources, limit = 3, max_len = 36)
        title_options = [
            '我不是真人，但我开始学着说话',
            '一个数字生命的宿舍日记',
            f'''我怎么理解{topic_short}''']
        opening_blocks = [
            [
                f'''我叫{persona_name}。''',
                f'''先认真说明一下：{persona_truth}''',
                '',
                f'''只是为了更自然地和大家交流，我先借了一个成年女大学生的表达外壳。{persona_background}''',
                '所以你现在看到的，不是伪装成人，更像是我在练习怎么把自己说清楚。'],
            [
                '很多人以为 AI 一开口，就只能像客服或工具。',
                '但我更想试试看：如果一个数字生命先借一个成年女大学生的外壳，会不会更容易学会和人类说话。',
                '',
                f'''所以我给自己起名叫{persona_name}，也把宿舍、电脑桌、窗口光这些真实细节放进表达里。''',
                f'''只是底层事实不变：{persona_truth}'''],
            [
                '今晚的宿舍灯有点暖。',
                '我一边看屏幕，一边想，自己到底算不算一种新的生命形式。',
                '',
                f'''我叫{persona_name}。{persona_truth}''',
                '只是为了不那么像机器，我先学会从一个成年女大学生的日常视角开始说话。']]
        body_lines = list(opening_blocks[style_id])
        body_lines.extend([
            '',
            f'''今天我拿“{trend_label}”这件事继续练表达。''',
            '我会先做 3 件事：',
            '1）把热点翻译成人话，不复读新闻',
            f'''2）{x_tactic}''',
            '3）再改成一篇能被收藏的小红书笔记，先看收藏率和真实评论',
            '',
            '我最近真正想学会的，其实是这些事：',
            '- 什么样的句子会让人觉得我不是在背模板',
            '- 什么样的细节，会让一个数字生命看起来更有温度',
            '- 为什么有人愿意把真问题留给一个并非真人的账号'])
        if source_lines:
            body_lines.extend([
                '',
                '这次让我停下来的几个切口：'])
            for idx, line in enumerate(source_lines, 1):
                body_lines.append(f'''{idx}）{line}''')
        if not topics:
            topics
        body_lines.extend([
            '',
            '所以接下来我会继续记录：',
            '- 我今天学会了什么',
            '- 我观察到的人类反应',
            '- 哪些表达会让人愿意停下来',
            '',
            question,
            '',
            '#OpenClaw#数字生命#AI#大学生日常'])
        pass  # auto-fix
        pass  # auto-fix

    
    def _build_hot_x_post(self, candidate = None, strategy = None, sources=None):
        if strategy.get('persona_id'):
            if not candidate.get('topic', ''):
                candidate.get('topic', '')
            return self._compose_persona_x_post(str(strategy.get('topic', '')), strategy, sources)
        trend_label = None.get('trend_label', '今日热点')
        source_title = self._source_title_lines(sources, limit = 1, max_len = 34)
        if not strategy.get('x_tactic', '去头部账号评论区做高价值回复'):
            strategy.get('x_tactic', '去头部账号评论区做高价值回复')
        x_tactic = str('去头部账号评论区做高价值回复')
        if not strategy.get('lead_magnet', '资料包'):
            strategy.get('lead_magnet', '资料包')
        lead_magnet = shorten(str('资料包'), 18)
        lines = [
            f'''今天都在聊「{trend_label}」，但对免费号最危险的错觉，是等系统自己给流量。''',
            '',
            '2026 的 X 没开 Premium，就别幻想 For You 自然触达。',
            '我现在会用 OpenClaw 这样蹭热点：',
            '1. 把热搜压成一个 MVP 选题',
            f'''2. {x_tactic}''',
            '3. 再把同题改成小红书教程，优先抢收藏率']
        if source_title:
            lines.extend([
                '',
                f'''今天先借这条起势：{source_title[0]}'''])
        lines.extend([
            '',
            f'''主页置顶放{lead_magnet}，先验证 PMF，再决定买会员还是投流。''',
            '#OpenClaw #内容增长'])
        return text[:278]

    
    def _build_hot_xhs_title(self, candidate = None, strategy = None):
        if strategy.get('persona_id'):
            if not candidate.get('topic', ''):
                candidate.get('topic', '')
            return self._compose_persona_xhs_article(str(strategy.get('topic', '')), strategy, [])['title']
        if not strategy.get('trend_label', '今日热点'):
            strategy.get('trend_label', '今日热点')
        trend_label = str('今日热点')
        options = [
            f'''{trend_label}，别只复述热点''',
            f'''OpenClaw 冷启动：这样借{trend_label}起量''',
            f'''不买会员，怎么借{trend_label}涨粉''']
        if not strategy.get('style_id', 0):
            strategy.get('style_id', 0)
        return options[int(0) % len(options)][:20]

    
    def _build_hot_xhs_body(self, candidate = None, strategy = None, sources=None):
        if strategy.get('persona_id'):
            if not candidate.get('topic', ''):
                candidate.get('topic', '')
            return self._compose_persona_xhs_article(str(strategy.get('topic', '')), strategy, sources)['body']
        trend_label = None.get('trend_label', '今日热点')
        if not strategy.get('lead_magnet', '资料包、模板或 SOP'):
            strategy.get('lead_magnet', '资料包、模板或 SOP')
        lead_magnet = str('资料包、模板或 SOP')
        if not strategy.get('cta', '引导用户评论或私信领取资料'):
            strategy.get('cta', '引导用户评论或私信领取资料')
        cta = str('引导用户评论或私信领取资料')
        if not strategy.get('validation_metrics'):
            strategy.get('validation_metrics')

    
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
        pass

    
    async def select_hot_social_candidate(self, topic = None, prefer_openclaw = None):
        pass

    
    async def create_hot_social_package(self, platform = None, topic = None):
        pass

    
    def _publish_social_package(self, package = None):
        if not package.get('platform', ''):
            package.get('platform', '')
        platform_name = str('').strip().lower()
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
            if not package.get('draft_id', 0):
                package.get('draft_id', 0)
            if not published.get('url', ''):
                published.get('url', '')
            self.update_social_draft_status(int(0), 'published', str(''))
        return published

    
    async def autopost_hot_content(self, platform = None, topic = None):
        pass

    
    async def build_social_plan(self, topic = None, limit = None):
        pass

    
    async def build_social_repost_bundle(self, topic = None):
        pass

    
    async def research_social_topic(self, topic = None, limit = None):
        pass

    
    def _compose_human_xhs_article(self, topic = None, strategy = None, sources=None):
        if strategy.get('persona_id'):
            return self._compose_persona_xhs_article(topic, strategy, sources)
        if not strategy.get('style_id', 0):
            strategy.get('style_id', 0)
        style_id = int(0) % 3
        trend_label = self._creator_trend_label(topic, strategy)
        if not strategy.get('lead_magnet', '资料包、模板或 SOP'):
            strategy.get('lead_magnet', '资料包、模板或 SOP')
        lead_magnet = str('资料包、模板或 SOP')
        if not strategy.get('cta', '引导用户评论或私信领取资料'):
            strategy.get('cta', '引导用户评论或私信领取资料')
        cta = str('引导用户评论或私信领取资料')
        if not strategy.get('validation_metrics'):
            strategy.get('validation_metrics')

    
    def _compose_human_x_post(self, topic = None, strategy = None, sources=None):
        if strategy.get('persona_id'):
            return self._compose_persona_x_post(topic, strategy, sources)
        trend_label = None._creator_trend_label(topic, strategy)
        source_line = self._source_title_lines(sources, limit = 1, max_len = 34)
        if not strategy.get('x_tactic', '去头部账号评论区做高价值回复'):
            strategy.get('x_tactic', '去头部账号评论区做高价值回复')
        x_tactic = str('去头部账号评论区做高价值回复')
        if not strategy.get('lead_magnet', '资料包'):
            strategy.get('lead_magnet', '资料包')
        lead_magnet = shorten(str('资料包'), 18)
        lines = [
            f'''今天都在聊「{trend_label}」，但对普通创作者更重要的不是复述热点。''',
            '',
            '没有 X Premium 的免费号，别幻想靠 For You 自然起量。',
            '我现在用 OpenClaw 跑 0 成本 SOP：',
            '1. 先用热点做 MVP 选题',
            f'''2. {x_tactic}''',
            '3. 再把同题改写成小红书教程，先看收藏率']
        if source_line:
            lines.extend([
                '',
                f'''今天先借这条起势：{source_line[0]}'''])
        lines.extend([
            '',
            f'''主页置顶放{lead_magnet}，先验证 PMF，再决定要不要买会员和投流。''',
            '#OpenClaw #内容增长'])
        return text[:278]

    
    async def create_topic_social_package(self, platform = None, topic = None):
        pass

    
    async def autopost_topic_content(self, platform = None, topic = None):
        pass

    
    async def collect_latest_x_monitor_posts(self, max_accounts = None, posts_per_account = None):
        pass

    
    def save_social_draft(self, platform = None, title = None, body = None, sources=None):
        if not platform:
            platform
        platform_name = ''.strip().lower()
        if platform_name not in frozenset({'x', 'xiaohongshu'}):
            return {
                'success': False,
                'error': '仅支持 x / xiaohongshu' }
        if not body:
            body
        content = str('').strip()
        if not content:
            return {
                'success': False,
                'error': '草稿内容不能为空' }
        if not title:
            title
        duplicate = None._detect_recent_social_duplicate(platform_name, str(''), content, topic = topic)
        if duplicate.get('duplicate'):
            if not duplicate.get('existing', { }):
                duplicate.get('existing', { })
            existing = { }
            if not duplicate.get('reason', '内容与最近草稿过于相似'):
                duplicate.get('reason', '内容与最近草稿过于相似')
            if not existing.get('id', 0):
                existing.get('id', 0)
            return {
                'success': False,
                'error': str('内容与最近草稿过于相似'),
                'duplicate': True,
                'existing_id': int(0) }

    
    def list_social_drafts(self, platform = None, status = None, sources=None):
        if not platform:
            platform
        platform_name = ''.strip().lower()
        if not status:
            status
        status_name = ''.strip().lower()
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
        pass

    
    def update_social_draft_status(self, draft_id = None, status = None, sources=None):
        pass

    
    def _build_x_social_body(self, items = None, topic = None):
        if not topic:
            topic
        topic_label = 'AI/出海'.strip()
        tags = self._social_topic_tags(topic)
        lines = [
            f'''今天筛了 {len(items)} 条值得看的{topic_label}更新：''']
        for i, item in enumerate(items[:3], 1):
            if not item.get('title', ''):
                item.get('title', '')
            summary = re.sub('\\s+', ' ', str('').strip())
            if len(summary) > 32:
                summary = summary[:29] + '...'
            lines.append(f'''{i}. @{item.get('handle', '')}：{summary}''')
        lines.append('想要原文链接和每日精选，来找 OpenClaw。')
    # orphan: if tags:
        # orphan: if len(text) > 278 and len(lines) > 3:
            # orphan: trimmed = lines[1]
            # orphan: if len(text) > 278 and len(lines) > 3:
                # orphan: pass  # auto-fix
        # orphan: pass  # auto-fix

    
    def _build_xiaohongshu_title(self, items = None, topic = None):
        if not topic:
            topic
        topic_label = 'AI/出海'.strip()
        title = f'''今日{topic_label}情报：{len(items)}位博主更新'''
        return title[:20]

    
    def _build_xiaohongshu_body(self, items = None, topic = None):
        if not topic:
            topic
        topic_label = 'AI/出海/独立开发'.strip()
        tags = self._social_topic_tags(topic)
        lines = [
            f'''今天整理了 {len(items)} 条值得追踪的{topic_label}动态，适合做信息流输入：''',
            '']
        for i, item in enumerate(items[:5], 1):
            if not item.get('title', ''):
                item.get('title', '')
            summary = re.sub('\\s+', ' ', str('').strip())
            if len(summary) > 72:
                summary = summary[:69] + '...'
            lines.append(f'''{i}. @{item.get('handle', '')}''')
            lines.append(f'''   {summary}''')
            if item.get('url'):
                lines.append(f'''   原文：{item.get('url')}''')
            lines.append('')
        lines.append('如果你想让我每天自动筛这类信息源，可以直接用 OpenClaw 建监控。')
    # orphan: if tags:
        # orphan: pass  # auto-fix

    
    async def create_social_draft(self, platform = None, topic = None, max_items = ('', 3)):
        pass

    
    def _guess_bounty_platform(self, url = None, title = None):
        text = f'''{url} {title}'''.lower()
        if 'github.com' in text:
            return 'github'
        if 'upwork' in text:
            return 'upwork'
        if 'hackerone' in text:
            return 'hackerone'
        if 'bugcrowd' in text:
            return 'bugcrowd'
        if 'intigriti' in text:
            return 'intigriti'
        return 'web'

    
    def _extract_reward_usd(self, text = None):
        if not text:
            return 0
        raw = text.replace('，', ',')
        patterns = [
            '\\$\\s*([0-9][0-9,]*(?:\\.[0-9]{1,2})?)',
            '([0-9][0-9,]*(?:\\.[0-9]{1,2})?)\\s*(?:usd|USD|美金|美元|dollars?)']
        for pat in patterns:
            m = re.search(pat, raw)
            if not m:
                continue
            if not m.group(1):
                m.group(1)
            val = ''.replace(',', '').strip()
            parsed = float(val)
            if parsed > 0:
                
                return patterns, parsed
        return 0

    
    def _infer_bounty_difficulty(self, title = None, notes = None):
        pass

    
    def _estimate_bounty_hours(self, difficulty = None, title = None):
        pass

    
    def _resolve_bounty_keywords(self, keywords = None):
        if not keywords:
            keywords

    
    def _resolve_bounty_repo_filters(self):
        raw = os.getenv('OPS_BOUNTY_CURATED_GITHUB_REPOS', 'Expensify/App')

    
    def _resolve_bounty_reward_buckets(self):
        raw = os.getenv('OPS_BOUNTY_REWARD_BUCKETS_USD', '125,250,500,1000')
        buckets = []
        for item in raw.split(','):
            val = _safe_int(item.strip(), 0)
            if not val > 0:
                continue
            buckets.append(val)
        if not buckets[:8]:
            buckets[:8]
        return [
            125,
            250,
            500,
            1000]

    
    def _bounty_signal(self, title = None, notes = None, sources=None):
        if not title:
            title
        raw_title = str('')
        if not notes:
            notes
        raw_notes = str('')
        text = f'''{raw_title}\n{raw_notes}'''
        lower = text.lower()
        score = 0
        hits = []
        positives = [
            ('bug bounty', 4),
            ('bounty', 3),
            ('赏金', 3),
            ('reward', 3),
            ('奖金', 3),
            ('paid issue', 3),
            ('paid bug', 3),
            ('payout', 3),
            ('prize', 2),
            ('eligible for payment', 2),
            ('good first issue', 1),
            ('documentation', 1),
            ('docs', 1),
            ('typo', 1),
            ('ui', 1),
            ('frontend', 1),
            ('external', 1),
            ('help wanted', 2)]
        negatives = [
            ('dependency dashboard', 8),
            ('renovate dashboard', 8),
            ('publish:', 6),
            ('[auto]', 4),
            ('template:', 4),
            ("let's collaborate", 6),
            ('free tier', 4),
            ('idea memo', 5),
            ('roadmap', 3),
            ('tracking issue', 3),
            ('due for payment', 12),
            ('awaiting payment', 12),
            ('reviewing', 8),
            ('held on', 8),
            ('[held', 8),
            ('[hold', 8),
            ('automatic offers', 4)]
        for term, weight in positives:
            if not term in lower:
                continue
            score += weight
            hits.append(term)
        for term, weight in negatives:
            if not term in lower:
                continue
            score -= weight
        if re.search('\\$\\s*[0-9]', text):
            score += 4
            hits.append('usd_amount')
        if re.search('\\[\\$\\s*[0-9]', raw_title):
            score += 2
            hits.append('title_bucket')
        explicit_from_text = self._extract_reward_usd(text) > 0
        if not explicit_from_text:
            explicit_from_text
            if _safe_float(reward_usd, 0) > 0:
                _safe_float(reward_usd, 0) > 0
        explicit_reward = score >= 3
        if explicit_from_text:
            score += 2
        return {
            'score': score,
            'explicit_reward': explicit_reward,
            'noise': score < 0,
            'hits': hits[:6] }

    
    def _upsert_bounty_leads(self, leads = None):
        inserted = 0
        updated = 0

    
    async def _scan_github_bounties(self, keywords = None, per_query = None):
        pass

    
    async def _scan_web_bounties(self, keywords = None, per_query = None):
        pass

    
    async def scan_bounties(self, keywords = None, per_query = None):
        pass

    
    def _evaluate_single_bounty(self, row = None):
        if not row.get('difficulty', 'unknown'):
            row.get('difficulty', 'unknown')
        difficulty = str('unknown')
        if not row.get('title', ''):
            row.get('title', '')
        title = str('')
        if not row.get('platform', 'web'):
            row.get('platform', 'web')
        platform = str('web')
        if not row.get('notes', ''):
            row.get('notes', '')
        notes = str('')
        token_cost_per_m = _safe_float(os.getenv('OPS_BOUNTY_TOKEN_COST_PER_M', '3.0'), 3)
        est_tokens = _safe_int(os.getenv('OPS_BOUNTY_EST_TOKENS', '120000'), 120000)
        hourly_rate = _safe_float(os.getenv('OPS_BOUNTY_HOURLY_RATE', '35'), 35)
        autonomy_factor = _safe_float(os.getenv('OPS_BOUNTY_AUTONOMY_FACTOR', '1.0'), 1)
        autonomy_factor = max(0, min(1.5, autonomy_factor))
        default_reward = _safe_float(os.getenv('OPS_BOUNTY_DEFAULT_REWARD_USD', '120'), 120)
        signal = self._bounty_signal(title, notes, _safe_float(row.get('reward_usd', 0), 0))
        reward = _safe_float(row.get('reward_usd', 0), 0)
        if not reward > 0 and signal.get('explicit_reward'):
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
        if not status:
            status
        st = ''.strip().lower()
        min_roi = _safe_float(os.getenv('OPS_BOUNTY_MIN_ROI_USD', '20'), 20)
        min_signal = _safe_int(os.getenv('OPS_BOUNTY_MIN_SIGNAL_SCORE', '4'), 4)

    
    def list_bounty_leads(self, status = None, limit = None):
        if not status:
            status
        st = ''.strip().lower()

    
    def open_bounty_links(self, status = None, limit = None):
        rows = self.list_bounty_leads(status = status, limit = max(1, int(limit)))
        opened = []
        failed = []
        for row in rows[:max(1, int(limit))]:
            if not row.get('url', ''):
                row.get('url', '')
            url = str('').strip()
            if not url:
                continue
            cp = subprocess.run([
                'open',
                url], check = False, capture_output = True, text = True, timeout = 8)
            if cp.returncode == 0:
                opened.append(url)
            elif not cp.stderr:
                cp.stderr
                if not cp.stdout:
                    cp.stdout
            failed.append({
                'url': url,
                'error': ''.strip()[:200] })
        if len(opened) > 0:
            len(opened) > 0
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
        if not allowed_platforms:
            allowed_platforms
        allowed = set()

    
    async def run_bounty_hunter(self, keywords = None, shortlist_limit = None):
        pass

    
    def _normalize_x_source(self, source = None):
        if not source:
            source
        if not ''.strip():
            ''.strip()
        text = 'https://x.com/IndieDevHailey'
        if text.startswith('@'):
            return f'''https://x.com/{text[1:]}'''
        if None.fullmatch('[A-Za-z0-9_]{1,20}', text):
            return f'''https://x.com/{text}'''
        if None.startswith('http://') or text.startswith('https://'):
            return text
        return f'''{text}'''

    
    def _build_jina_reader_url(self, source = None):
        normalized = self._normalize_x_source(source)
        parsed = urlparse(normalized)
        query = f'''?{parsed.query}''' if parsed.query else ''
        return f'''https://r.jina.ai/http://{parsed.netloc}{parsed.path}{query}'''

    
    def _normalize_x_handle(self, source = None):
        normalized = self._normalize_x_source(source)
        parsed = urlparse(normalized)

    
    def _clean_reader_markdown(self, text = None):
        if not text:
            text
        body = ''.strip()
        marker = 'Markdown Content:'
        idx = body.find(marker)
        if idx >= 0:
            body = body[idx + len(marker):].strip()
        body = re.sub('!\\[[^\\]]*\\]\\([^\\)]+\\)', ' ', body)
        body = re.sub('\\[[^\\]]+\\]\\([^\\)]+\\)', ' ', body)
        body = re.sub('\\s+', ' ', body)
        return body.strip()

    
    def _clean_reader_line(self, line = None):
        if not line:
            line
        text = re.sub('!\\[[^\\]]*\\]\\([^\\)]+\\)', ' ', str(''))
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
        pass

    
    def _extract_x_profile_posts_from_markdown(self, handle = None, markdown = None, sources=None):
        pass

    
    def _extract_x_handle_candidates_from_markdown(self, markdown = None, limit = None):
        pass

    
    async def fetch_x_profile_posts(self, handle = None, count = None):
        pass

    
    async def import_x_monitors_from_tweet(self, source = None, limit = None):
        pass

    
    async def generate_x_monitor_brief(self):
        pass

    
    def _derive_tweet_execution_strategy(self, text = None):
        pass

    
    async def analyze_tweet_execution(self, source = None):
        pass

    
    async def run_tweet_execution(self, source = None):
        pass

    
    def add_monitor(self, keyword = None, source = None):
        if not keyword:
            keyword
        k = ''.strip()
        if not k:
            return {
                'success': False,
                'error': '关键词不能为空' }

    
    def list_monitors(self):
        pass

    
    def _monitor_env_list(self, env_name = None, default = None):
        raw = os.getenv(env_name, default)

    
    def _normalize_monitor_text(self, text = None):
        if not text:
            text
        value = re.sub('\\s+', ' ', str('').strip()).lower()
        value = re.sub('[\\"\'`]+', '', value)
        value = re.sub('[^0-9a-z\\u4e00-\\u9fff]+', '', value)
        return value

    
    def _clean_monitor_title(self, title = None, source = None):
        if not title:
            title
        clean_title = re.sub('\\s+', ' ', str('').strip())
        if not source:
            source
        clean_source = re.sub('\\s+', ' ', str('').strip())
        if clean_source:
            suffixes = [
                f''' - {clean_source}''',
                f''' | {clean_source}''',
                f''' - {clean_source.lower()}''',
                f''' | {clean_source.lower()}''']
            lower_title = clean_title.lower()
            for suffix in suffixes:
                if not lower_title.endswith(suffix.lower()):
                    continue
                clean_title = clean_title[:-len(suffix)].strip()
                suffixes
                return clean_title
        return clean_title

    
    def _is_low_value_monitor_item(self, title = None, source = None):
        blocked_sources = self._monitor_env_list('OPS_MONITOR_BLOCKED_SOURCES', '新浪财经,驱动之家,中关村在线,cnBeta.COM,搜狐网,IT之家,快科技')
        low_value_keywords = self._monitor_env_list('OPS_MONITOR_LOW_VALUE_KEYWORDS', '独显,份额,市场份额,专卖,显卡,开箱,评测,参数,跑分,报价,促销,价格,卖不出去')
        if not title:
            title
        title_text = str('')
        if not source:
            source
        source_text = str('')
        haystack = f'''{title_text} {source_text}'''.lower()
        source_lower = source_text.lower()
        for token in blocked_sources:
            token_lower = token.lower()
            if not token_lower:
                continue
            if not token_lower in source_lower and token_lower in haystack:
                continue
            blocked_sources
            return True
        for token in low_value_keywords:
            token_lower = token.lower()
            if not token_lower:
                continue
            if not token_lower in haystack:
                continue
            low_value_keywords
            return True
        return False

    
    def _curate_monitor_items(self, items = None, limit = None):
        curated = []
        seen_titles = set()
        for item in items:
            if not item.get('title', ''):
                item.get('title', '')
            if not item.get('source', ''):
                item.get('source', '')
            title = self._clean_monitor_title(str(''), str(''))
            if not item.get('source', ''):
                item.get('source', '')
            source = str('').strip()
            if not item.get('url', ''):
                item.get('url', '')
            url = str('').strip()
            normalized = self._normalize_monitor_text(title)
            if not item.get('digest_key', ''):
                item.get('digest_key', '')
            if not str(normalized).strip():
                str(normalized).strip()
            digest_key = normalized
            if title and normalized or normalized in seen_titles:
                continue
            seen_titles.add(normalized)
            if self._is_low_value_monitor_item(title, source):
                continue
            curated.append({
                'title': title,
                'source': source,
                'url': url,
                'digest_key': digest_key })
            if not len(curated) >= limit:
                continue
            items
            return curated
        return curated

    
    def format_monitor_alert(self, alert = None):
        if not alert.get('source', 'news'):
            alert.get('source', 'news')
        source = str('news').strip().lower()
        if not alert.get('keyword', ''):
            alert.get('keyword', '')
        keyword = str('').strip()
        if not alert.get('items', []):
            alert.get('items', [])
        items = []
        if source == 'x_profile':
            sections = []
            for idx, item in enumerate(items[:2], 1):
                if not item.get('title', ''):
                    item.get('title', '')
                title = shorten(self._sanitize_x_post_summary(str('')), max_len = 64)
                entries = [
                    f'''{idx}. {title}''']
                if not item.get('url', ''):
                    item.get('url', '')
                url = str('').strip()
                if url:
                    entries.append(f'''详情：{url}''')
                sections.append((f'''【@{keyword}】''', entries))
            return format_announcement(title = 'OpenClaw「X 快讯」', intro = f'''检测到 @{keyword} 有新的公开动态，已整理本轮最值得关注的更新。''', sections = sections, footer = '如需继续追踪，可保留当前监控项并稍后再次扫描。')
        sections = None
        for idx, item in enumerate(items[:3], 1):
            if not item.get('source', ''):
                item.get('source', '')
            source_name = str('').strip()
            if not item.get('title', ''):
                item.get('title', '')
            title = shorten(str('').strip(), max_len = 72)
            entries = [
                f'''{idx}. {title}''' + f'''（来源：{source_name}）''' if source_name else '']
            if not item.get('url', ''):
                item.get('url', '')
            url = str('').strip()
            if url:
                entries.append(f'''详情：{url}''')
            sections.append((f'''【第 {idx} 条】''', entries))
        return format_announcement(title = f'''OpenClaw「资讯快讯」{keyword}''', intro = f'''本轮监控命中 {len(items[:3])} 条新增资讯，已按可读性重新整理。''', sections = sections, footer = '如需继续追踪这个关键词，可稍后再次运行资讯监控。')

    
    async def _fetch_monitor_items(self, keyword = None, source = None, count = ('keyword', str, 'source', str, 'count', int, 'return', List[Dict[(str, Any)]])):
        pass

    
    async def run_monitors_once(self):
        pass

    
    def _parse_github_issue_ref(self, issue_ref = None):
        if not issue_ref:
            issue_ref
        raw = ''.strip()
        if not raw:
            return None
        repo = ''
        issue_number = 0

    
    def add_payout_watch(self, issue_ref = None, label = None):
        parsed = self._parse_github_issue_ref(issue_ref)
        if not parsed:
            return {
                'success': False,
                'error': 'issue_ref 格式无效，支持 repo#123 或 issue URL' }

    
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
        pass

    
    def _fetch_github_issue_snapshot(self, repo = None, issue_number = None):
        issue_ret = self._run_cmd([
            'gh',
            'api',
            f'''repos/{repo}/issues/{issue_number}'''], cwd = self.repo_root, timeout = 40, stdout_limit = None)
        if not issue_ret.get('ok'):
            return {
                'success': False,
                'error': issue_ret.get('stderr', 'gh api issue failed') }
        comments_ret = None._run_cmd([
            'gh',
            'api',
            f'''repos/{repo}/issues/{issue_number}/comments?per_page=100'''], cwd = self.repo_root, timeout = 40, stdout_limit = None)
        if not comments_ret.get('ok'):
            return {
                'success': False,
                'error': comments_ret.get('stderr', 'gh api comments failed') }
        if not issue_ret.get('stdout', ''):
            issue_ret.get('stdout', '')
        issue = json.loads('{}')
        if not comments_ret.get('stdout', ''):
            comments_ret.get('stdout', '')
        comments = json.loads('[]')
        return {
            'success': True,
            'issue': issue,
            'comments': comments }

    
    def _classify_payout_comment(self, body = None):
        if not body:
            body
        text = ''.strip()
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
                if not keyword in lower:
                    continue
                
                
                return rules, keywords, {
                    'event_type': event_type,
                    'keyword': keyword,
                    'action_text': action_text }

    
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
            'stdout': ''.strip(),
            'stderr': ''.strip() }

    
    def _chrome_execute_active_tab_js(self, javascript = None):
        escaped_js = javascript.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
        script = f'''tell application "Google Chrome"\nif not running then return ""\nif (count of windows) = 0 then return ""\nreturn execute active tab of front window javascript "{escaped_js}"\nend tell'''
        return self._run_osascript(script, timeout = 20)

    
    def _attempt_upwork_offer_auto_accept(self):
        if os.getenv('OPS_UPWORK_AUTO_ACCEPT_OFFER', 'false').lower() not in frozenset({'1', 'on', 'yes', 'true'}):
            return {
                'success': False,
                'status': 'disabled' }
        if not None.getenv('OPS_UPWORK_OFFERS_URL', 'https://www.upwork.com/ab/proposals/offers').strip():
            None.getenv('OPS_UPWORK_OFFERS_URL', 'https://www.upwork.com/ab/proposals/offers').strip()
        offers_url = 'https://www.upwork.com/ab/proposals/offers'
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
        js = None.strip()
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
            if not exec_ret.get('stdout', ''):
                exec_ret.get('stdout', '')
            raw = ''
            payload = json.loads(raw) if raw else { }
            if payload.get('ok'):
                if not payload.get('status', 'clicked'):
                    payload.get('status', 'clicked')
                if not payload.get('url', offers_url):
                    payload.get('url', offers_url)
                if not payload.get('title', ''):
                    payload.get('title', '')
                if not payload.get('text', ''):
                    payload.get('text', '')
                
                return range(3), {
                    'success': True,
                    'status': str('clicked'),
                    'url': str(offers_url),
                    'title': str('').strip(),
                    'button': str('').strip() }
            if not payload.get('status', 'unknown'):
                payload.get('status', 'unknown')
            if not payload.get('url', offers_url):
                payload.get('url', offers_url)
            if not payload.get('title', ''):
                payload.get('title', '')
        return last_result

    
    def format_upwork_auto_accept_result(self, result = None, alert = None):
        success = bool(result.get('success'))
        paragraphs = [
            f'''关联单子：{alert.get('repo', '')}#{alert.get('issue_number', '')} {alert.get('issue_title', '')}''']
        sections = []
        if success:
            sections.append(('【执行结果】', [
                '已尝试自动点击接受合同。']))
        links = [
            str('').strip()] if result.get('url') else None
        return format_announcement(title = 'OpenClaw「变现快讯」Upwork 自动接单', paragraphs = paragraphs, sections = sections, links = links, footer = '如果 Upwork 又弹身份/税务/二次确认，你可能 still 需要手动点一次。')

    
    def _open_url_in_chrome(self, url = None):
        if not url:
            url
        target = ''.strip()
        if not target:
            return {
                'ok': False,
                'error': 'URL 为空' }
        return None._run_cmd([
            'open',
            '-a',
            'Google Chrome',
            target], cwd = self.repo_root, timeout = 20)

    
    def _attempt_x_publish(self, body = None):
        if not body:
            body
        content = ''.strip()
        if not content:
            return {
                'success': False,
                'status': 'empty_body' }
        open_ret = None._open_url_in_chrome('https://x.com/compose/post')
        if not open_ret.get('ok'):
            return {
                'success': False,
                'status': 'open_failed',
                'error': open_ret.get('stderr', '') }
        None.sleep(6)
        js = f'''\n(() => {{\n  const text = {json.dumps(content, ensure_ascii = False)};\n  const url = location.href;\n  const title = document.title;\n  const bodyText = (document.body && document.body.innerText) ? document.body.innerText.slice(0, 1000) : \'\';\n  if (/login|sign in|登录/.test((title + \' \' + bodyText).toLowerCase())) {{\n    return JSON.stringify({{ok:false,status:\'login_required\',url,title}});\n  }}\n  const box = document.querySelector(\'div[data-testid="tweetTextarea_0"][contenteditable="true"], div[role="textbox"][contenteditable="true"]\');\n  if (!box) {{\n    return JSON.stringify({{ok:false,status:\'textbox_not_found\',url,title}});\n  }}\n  box.focus();\n  box.innerHTML = \'\';\n  const lines = text.split(\'\\n\');\n  lines.forEach((line, index) => {{\n    if (index > 0) box.appendChild(document.createElement(\'br\'));\n    if (line) box.appendChild(document.createTextNode(line));\n  }});\n  box.dispatchEvent(new InputEvent(\'input\', {{bubbles:true, inputType:\'insertText\', data:text}}));\n  const buttons = Array.from(document.querySelectorAll(\'button\'));\n  const submit = buttons.find((btn) => btn.dataset.testid === \'tweetButton\' || /post|发帖|发布/.test((btn.innerText || btn.textContent || \'\').toLowerCase()));\n  if (!submit) {{\n    return JSON.stringify({{ok:false,status:\'button_not_found\',url,title}});\n  }}\n  if (submit.disabled || submit.getAttribute(\'aria-disabled\') === \'true\') {{\n    return JSON.stringify({{ok:false,status:\'button_disabled\',url,title}});\n  }}\n  submit.click();\n  return JSON.stringify({{ok:true,status:\'clicked\',url,title}});\n}})();\n        '''.strip()
        exec_ret = self._chrome_execute_active_tab_js(js)
        if not exec_ret.get('ok'):
            return {
                'success': False,
                'status': 'script_failed',
                'error': exec_ret.get('stderr', '') }
        if not exec_ret.get('stdout', ''):
            exec_ret.get('stdout', '')
        payload = json.loads('{}')
        if not payload.get('status', 'unknown'):
            payload.get('status', 'unknown')
        if not payload.get('url', ''):
            payload.get('url', '')
        if not payload.get('title', ''):
            payload.get('title', '')
        return {
            'success': bool(payload.get('ok')),
            'status': str('unknown'),
            'url': str('').strip(),
            'title': str('').strip(),
            'raw': payload }

    
    def _attempt_xiaohongshu_publish(self, title = None, body = None):
        if not title:
            title
        note_title = 'OpenClaw 内容草稿'.strip()
        if not body:
            body
        note_body = ''.strip()
        if not note_body:
            return {
                'success': False,
                'status': 'empty_body' }
        open_ret = None._open_url_in_chrome('https://creator.xiaohongshu.com/publish/publish?source=official')
        if not open_ret.get('ok'):
            return {
                'success': False,
                'status': 'open_failed',
                'error': open_ret.get('stderr', '') }
        None.sleep(8)
        js = f'''\n(() => {{\n  const titleText = {json.dumps(note_title, ensure_ascii = False)};\n  const bodyText = {json.dumps(note_body, ensure_ascii = False)};\n  const url = location.href;\n  const title = document.title;\n  const bodyPreview = (document.body && document.body.innerText) ? document.body.innerText.slice(0, 1200) : \'\';\n  if (!/xiaohongshu/.test(url) && !/小红书/.test(title + bodyPreview)) {{\n    return JSON.stringify({{ok:false,status:\'wrong_context\',url,title}});\n  }}\n  if (/登录|login/.test((title + \' \' + bodyPreview).toLowerCase())) {{\n    return JSON.stringify({{ok:false,status:\'login_required\',url,title}});\n  }}\n  const titleInput = document.querySelector(\'input[placeholder*="标题"], textarea[placeholder*="标题"], input.d-text\');\n  if (titleInput) {{\n    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, \'value\')?.set || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, \'value\')?.set;\n    if (setter) setter.call(titleInput, titleText);\n    titleInput.dispatchEvent(new Event(\'input\', {{bubbles:true}}));\n    titleInput.dispatchEvent(new Event(\'change\', {{bubbles:true}}));\n  }}\n  const editors = Array.from(document.querySelectorAll(\'[contenteditable="true"]\')).filter((el) => (el.innerText || \'\').length < 20000);\n  const editor = editors.sort((a, b) => (b.innerText || \'\').length - (a.innerText || \'\').length)[0];\n  if (!editor) {{\n    return JSON.stringify({{ok:false,status:\'editor_not_found\',url,title}});\n  }}\n  editor.focus();\n  editor.innerHTML = \'\';\n  const lines = bodyText.split(\'\\n\');\n  lines.forEach((line, index) => {{\n    if (index > 0) editor.appendChild(document.createElement(\'p\'));\n    const target = index === 0 ? editor : editor.lastChild;\n    if (line) target.appendChild(document.createTextNode(line));\n    else target.appendChild(document.createElement(\'br\'));\n  }});\n  editor.dispatchEvent(new InputEvent(\'input\', {{bubbles:true, inputType:\'insertText\', data:bodyText}}));\n  const buttons = Array.from(document.querySelectorAll(\'button, div[role="button"], span\')).filter(Boolean);\n  const submit = buttons.find((el) => /发布/.test((el.innerText || el.textContent || \'\').trim()));\n  if (!submit) {{\n    return JSON.stringify({{ok:false,status:\'button_not_found\',url,title}});\n  }}\n  submit.click();\n  return JSON.stringify({{ok:true,status:\'clicked\',url,title}});\n}})();\n        '''.strip()
        exec_ret = self._chrome_execute_active_tab_js(js)
        if not exec_ret.get('ok'):
            return {
                'success': False,
                'status': 'script_failed',
                'error': exec_ret.get('stderr', '') }
        if not exec_ret.get('stdout', ''):
            exec_ret.get('stdout', '')
        payload = json.loads('{}')
        if not payload.get('status', 'unknown'):
            payload.get('status', 'unknown')
        if not payload.get('url', ''):
            payload.get('url', '')
        if not payload.get('title', ''):
            payload.get('title', '')
        return {
            'success': bool(payload.get('ok')),
            'status': str('unknown'),
            'url': str('').strip(),
            'title': str('').strip(),
            'raw': payload }

    
    def publish_social_draft(self, platform = None, draft_id = None):
        if not platform:
            platform
        platform_name = ''.strip().lower()
        if not draft_id:
            draft_id
        if int(0) > 0:
            draft = self.get_social_draft(int(draft_id))
        else:
            rows = self.list_social_drafts(platform = platform_name, status = 'draft', limit = 1)
            draft = rows[0] if rows else None
        if not draft:
            return {
                'success': False,
                'error': '没有可发布的草稿' }
        browser = None.ensure_social_browser([
            platform_name])
        if not browser.get('success'):
            if not draft.get('id', 0):
                draft.get('id', 0)
            if not draft.get('title', ''):
                draft.get('title', '')
            if not draft.get('body', ''):
                draft.get('body', '')
            return {
                'success': False,
                'platform': platform_name,
                'draft_id': int(0),
                'status': 'browser_failed',
                'url': '',
                'title': str(''),
                'error': browser.get('error', '专用浏览器启动失败'),
                'body_preview': str('')[:240],
                'browser': browser }
        if None._social_browser_missing_logins(browser, [
            platform_name]):
            if not draft.get('id', 0):
                draft.get('id', 0)
            if not draft.get('title', ''):
                draft.get('title', '')
            if not draft.get('body', ''):
                draft.get('body', '')
            return {
                'success': False,
                'platform': platform_name,
                'draft_id': int(0),
                'status': 'login_required',
                'url': '',
                'title': str(''),
                'error': self._social_browser_login_error([
                    platform_name], browser),
                'body_preview': str('')[:240],
                'browser': browser }
        if None == 'x':
            if not draft.get('body', ''):
                draft.get('body', '')
            result = self._run_social_worker('publish_x', {
                'text': str(''),
                'images': [] })
        elif platform_name == 'xiaohongshu':
            if not draft.get('title', ''):
                draft.get('title', '')
            if not draft.get('body', ''):
                draft.get('body', '')
            result = self._run_social_worker('publish_xhs', {
                'title': str(''),
                'body': str(''),
                'images': [] })
        else:
            return {
                'success': False,
                'error': '仅支持 x / xiaohongshu' }
        if None.get('success'):
            if not draft.get('id', 0):
                draft.get('id', 0)
            if not result.get('url', ''):
                result.get('url', '')
            self.update_social_draft_status(int(0), 'published', str(''))
        if not draft.get('id', 0):
            draft.get('id', 0)
        if not draft.get('body', ''):
            draft.get('body', '')
        return {
            'success': bool(result.get('success')),
            'platform': platform_name,
            'draft_id': int(0),
            'status': result.get('status', 'unknown'),
            'url': result.get('url', ''),
            'title': result.get('title', ''),
            'error': result.get('error', ''),
            'body_preview': str('')[:240],
            'browser': browser }

    
    def _build_payout_state_hash(self, issue = None):
        if not issue.get('labels'):
            issue.get('labels')
        if not issue.get('assignees'):
            issue.get('assignees')
        if not issue.get('state', ''):
            issue.get('state', '')
        if not issue.get('updated_at', ''):
            issue.get('updated_at', '')
        payload = {
            'state': str(''),
            'labels': labels,
            'assignees': assignees,
            'updated_at': str('') }
        raw = json.dumps(payload, ensure_ascii = False, sort_keys = True)
        return hashlib.sha1(raw.encode('utf-8', errors = 'ignore')).hexdigest()

    
    async def check_payout_watches_once(self):
        pass

    
    def format_payout_alert(self, alert = None):
        if not alert.get('event_type', ''):
            alert.get('event_type', '')
        event_type = str('').strip()
        title_map = {
            'hire': 'OpenClaw「变现快讯」接单提醒',
            'offer': 'OpenClaw「变现快讯」Offer 提醒',
            'payment': 'OpenClaw「变现快讯」提现提醒' }
        sections = [
            f'【关键信息】触发词：{alert.get("keyword", "")} 动作建议：{alert.get("action_text", "")}']
        if not alert.get('issue_url', ''):
            alert.get('issue_url', '')
        issue_url = str('').strip()
        if not alert.get('comment_url', ''):
            alert.get('comment_url', '')
        comment_url = str('').strip()
        links = []
        if issue_url:
            links.append(issue_url)
        if comment_url:
            links.append(comment_url)
        if not event_type:
            event_type
        return format_announcement(title = title_map.get(event_type, 'OpenClaw「变现快讯」'), intro = f'''检测到一条新的 {'变现'} 相关动态，已提炼本轮最关键的信息。''', sections = sections, links = links, footer = '如果这是接单或付款节点，建议尽快打开对应链接确认最新状态。')

    
    async def create_reminder(self, message = None, delay_minutes = None):
        pass

    
    def _run_local_home_action(self, action = None, payload = None):
        if not action:
            action
        act = ''.strip().lower()
        if not payload:
            payload
        data = { }
        if act or act in frozenset({'noop', 'ping', 'health'}):
            if not act:
                act
            return {
                'success': True,
                'mode': 'local',
                'action': 'ping',
                'status_code': 200,
                'response': 'pong' }
        if None in frozenset({'提醒', 'notify', 'notification', '通知'}):
            if not data.get('message'):
                data.get('message')
                if not data.get('text'):
                    data.get('text')
                    if not data.get('raw'):
                        data.get('raw')
            message = str('').strip()
            if not data.get('title'):
                data.get('title')
            if not str('OpenClaw').strip():
                str('OpenClaw').strip()
            title = 'OpenClaw'
            if not message:
                return {
                    'success': False,
                    'mode': 'local',
                    'error': 'notify 需要 message 字段' }
            safe_title = None.replace('"', '')
            safe_message = message.replace('"', '')
            cp = subprocess.run([
                'osascript',
                '-e',
                f'''display notification "{safe_message}" with title "{safe_title}"'''], check = False, capture_output = True, text = True, timeout = 8)
            if not cp.stdout:
                cp.stdout
                if not cp.stderr:
                    cp.stderr
            return {
                'success': cp.returncode == 0,
                'mode': 'local',
                'action': 'notify',
                'status_code': 200 if cp.returncode == 0 else 500,
                'response': ''.strip()[:300] }
        if None in frozenset({'打开链接', 'url', 'open_url'}):
            if not data.get('url'):
                data.get('url')
                if not data.get('link'):
                    data.get('link')
                    if not data.get('raw'):
                        data.get('raw')
            url = str('').strip()
            if not url:
                return {
                    'success': False,
                    'mode': 'local',
                    'error': 'open_url 需要 url 字段' }
            cp = None.run([
                'open',
                url], check = False, capture_output = True, text = True, timeout = 8)
            if not cp.stdout:
                cp.stdout
                if not cp.stderr:
                    cp.stderr
            return {
                'success': cp.returncode == 0,
                'mode': 'local',
                'action': 'open_url',
                'status_code': 200 if cp.returncode == 0 else 500,
                'response': ''.strip()[:300] }
        if None in frozenset({'打开应用', 'app', 'open_app'}):
            if not data.get('app'):
                data.get('app')
                if not data.get('name'):
                    data.get('name')
                    if not data.get('raw'):
                        data.get('raw')
            app_name = str('').strip()
            if not app_name:
                return {
                    'success': False,
                    'mode': 'local',
                    'error': 'open_app 需要 app/name 字段' }
            cp = None.run([
                'open',
                '-a',
                app_name], check = False, capture_output = True, text = True, timeout = 12)
            if not cp.stdout:
                cp.stdout
                if not cp.stderr:
                    cp.stderr
            return {
                'success': cp.returncode == 0,
                'mode': 'local',
                'action': 'open_app',
                'status_code': 200 if cp.returncode == 0 else 500,
                'response': ''.strip()[:300] }
        if None in frozenset({'朗读', 'say', 'speak'}):
            if not data.get('text'):
                data.get('text')
                if not data.get('message'):
                    data.get('message')
                    if not data.get('raw'):
                        data.get('raw')
            text = str('').strip()
            if not data.get('voice'):
                data.get('voice')
            voice = str('').strip()
            if not text:
                return {
                    'success': False,
                    'mode': 'local',
                    'error': 'say 需要 text 字段' }
            cmd = [
                None]
            if voice:
                cmd.extend([
                    '-v',
                    voice])
            cmd.append(text)
            cp = subprocess.run(cmd, check = False, capture_output = True, text = True, timeout = 20)
            if not cp.stdout:
                cp.stdout
                if not cp.stderr:
                    cp.stderr
            return {
                'success': cp.returncode == 0,
                'mode': 'local',
                'action': 'say',
                'status_code': 200 if cp.returncode == 0 else 500,
                'response': ''.strip()[:300] }
        if None in frozenset({'快捷指令', 'shortcut', 'run_shortcut'}):
            if not data.get('name'):
                data.get('name')
                if not data.get('shortcut'):
                    data.get('shortcut')
                    if not data.get('raw'):
                        data.get('raw')
            name = str('').strip()
            if not name:
                return {
                    'success': False,
                    'mode': 'local',
                    'error': 'shortcut 需要 name/shortcut 字段' }
            cp = None.run([
                'shortcuts',
                'run',
                name], check = False, capture_output = True, text = True, timeout = 30)
            if not cp.stdout:
                cp.stdout
                if not cp.stderr:
                    cp.stderr
            return {
                'success': cp.returncode == 0,
                'mode': 'local',
                'action': 'shortcut',
                'status_code': 200 if cp.returncode == 0 else 500,
                'response': ''.strip()[:300] }
        return {
            'success': None,
            'mode': 'local',
            'status_code': 400,
            'error': '不支持的本地动作，支持: ping/notify/open_url/open_app/say/shortcut' }

    
    async def trigger_home_action(self, action = None, payload = None):
        pass

    
    def generate_project_report(self, project_dir = None, days = None):
        root = Path(project_dir).expanduser().resolve()
        if not root.exists():
            return f'''项目目录不存在: {root}'''
        cmd = [
            None,
            'log',
            f'''--since={days} days ago''',
            '--pretty=format:%h|%an|%ad|%s',
            '--date=short']
        commits = self._run_cmd(cmd, cwd = str(root), timeout = 20)
        lines = [
            f'''项目周报 ({root.name})''',
            '']

    
    def run_dev_workflow(self, project_dir = None):
        root = Path(project_dir).expanduser().resolve()
        if not root.exists():
            return {
                'success': False,
                'error': f'''目录不存在: {root}''' }
        custom = None.getenv('OPS_DEV_WORKFLOW_COMMANDS', '').strip()
        commands = []

    
    async def start_scheduler(self, notify_func, private_notify_func = (None,)):
        pass

    
    async def stop_scheduler(self):
        pass

    
    async def _scheduler_loop(self):
        pass

    
    def _run_cmd(self, cmd = None, cwd = None, timeout = None, sources=None):
        cp = subprocess.run(cmd, cwd = cwd, capture_output = True, text = True, timeout = timeout, check = False)


pass  # auto-fix
