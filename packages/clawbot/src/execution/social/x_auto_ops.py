"""
X 自动运营闭环。

目标：把“中文/英文热点 → 可吐槽选题 → X 风格抽象短推 → 全天自动发布”做成可验证链路。
实现原则：优先使用公开热榜/RSS/页面字幕，不依赖额外 API Key；外部抓取失败时自动降级到本地素材，保证定时任务不中断。
"""

from __future__ import annotations

import hashlib
import html
import http.client
import json
import re
import threading
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.utils import now_et

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_STATE_FILE = _PACKAGE_ROOT / "data" / "x_auto_ops_state.json"
_DEFAULT_TZ = "America/Denver"


@dataclass(frozen=True)
class ContentSeed:
    """保存一个可改写成 X 内容的通用素材。"""

    title: str
    channel: str
    url: str
    published: str = ""
    source: str = "youtube_rss"
    summary: str = ""
    transcript: str = ""
    tags: list[str] = field(default_factory=list)
    language: str = ""
    raw_score: int = 0
    raw_rank: int = 0
    heat_reason: str = ""


ContentSeed.__name__ = "VideoSeed"
VideoSeed = ContentSeed


@dataclass(frozen=True)
class TrendSeed(ContentSeed):
    """保存中文/英文热榜素材，优先用于追热点内容。"""

    source: str = "trend"


DEFAULT_CHANNELS: list[dict[str, str]] = [
    {"name": "Fireship", "channel_id": "UCsBjURrPoezykLs9EqgamOA"},
    {"name": "ThePrimeagen", "channel_id": "UC8ENHE5xdFSwx71u3fDH5Xw"},
    {"name": "Two Minute Papers", "channel_id": "UCbfYPyITQ-7l4upoX8nvctg"},
    {"name": "AI Explained", "channel_id": "UCNJ1Ymd5yFuUPtn21xtRbbw"},
    {"name": "Theo - t3.gg", "channel_id": "UCbRP3c757lWg9M-U7TyEkXA"},
    {"name": "Y Combinator", "channel_id": "UCcefcZRL2oaA_uBNeo5UOWg"},
]

DEFAULT_DAILY_TIMES: list[tuple[int, int]] = [
    (8, 30),
    (10, 30),
    (12, 30),
    (15, 0),
    (17, 30),
    (20, 30),
]

POST_ANGLES: list[str] = [
    "internet_mood",
    "abstract_roast",
    "contrast_meme",
    "three_line_take",
    "cn_en_mirror",
    "reply_bait",
]

_FALLBACK_SEEDS = [
    TrendSeed(
        title="大家开始用一句话形容自己的精神状态",
        channel="本地兜底热点",
        url="https://x.com/BonoDJblack",
        source="fallback_trend",
        summary="互联网每天都在把复杂人生压缩成一句离谱但准确的话。",
        tags=["热点", "互联网精神状态"],
        language="zh",
        raw_score=600,
        raw_rank=8,
        heat_reason="低风险、易共鸣、适合做抽象吐槽",
    ),
    TrendSeed(
        title="Everyone is posting like the timeline is a group therapy session",
        channel="local fallback trend",
        url="https://x.com/BonoDJblack",
        source="fallback_trend",
        summary="英文信息流也在从新闻现场变成大型互助吐槽会。",
        tags=["Trending", "Internet"],
        language="en",
        raw_score=560,
        raw_rank=9,
        heat_reason="轻松、可互动、适合中英互译梗",
    ),
    TrendSeed(
        title="网友把周一早会称为灵魂出厂设置",
        channel="本地兜底热点",
        url="https://x.com/BonoDJblack",
        source="fallback_trend",
        summary="职场共鸣强，适合做轻吐槽和评论接龙。",
        tags=["热点", "抽象", "打工人"],
        language="zh",
        raw_score=540,
        raw_rank=10,
        heat_reason="打工人共鸣、低风险、评论区容易接梗",
    ),
    TrendSeed(
        title="Someone turned ad fatigue into a tiny logic puzzle side quest",
        channel="local fallback trend",
        url="https://x.com/BonoDJblack",
        source="fallback_trend",
        summary="广告疲劳和自制小游戏有反差，适合英文短推。",
        tags=["Internet", "meme"],
        language="en",
        raw_score=520,
        raw_rank=11,
        heat_reason="轻技术、轻娱乐、可吐槽广告体验",
    ),
    TrendSeed(
        title="UP主把导航广告逼成了互联网公敌",
        channel="本地兜底热点",
        url="https://x.com/BonoDJblack",
        source="fallback_trend",
        summary="普通用户对广告的共同情绪强，适合轻松吐槽。",
        tags=["Bilibili", "网友"],
        language="zh",
        raw_score=510,
        raw_rank=12,
        heat_reason="用户共鸣强、无严肃风险、容易引发评论",
    ),
    TrendSeed(
        title="The timeline discovered another harmless object to overthink",
        channel="local fallback trend",
        url="https://x.com/BonoDJblack",
        source="fallback_trend",
        summary="英文区常见轻梗，可承接各种小众趋势。",
        tags=["Internet", "weird"],
        language="en",
        raw_score=500,
        raw_rank=13,
        heat_reason="抽象但低风险，适合保持账号日更",
    ),
]

_KEYWORDS = [
    "ai",
    "agent",
    "agents",
    "claude",
    "openai",
    "gpt",
    "llm",
    "automation",
    "automate",
    "code",
    "coding",
    "developer",
    "rust",
    "python",
    "javascript",
    "startup",
    "workflow",
    "tool",
    "model",
    "deepseek",
    "content",
    "robot",
    "browser",
    "prompt",
    "cursor",
    "vercel",
]

_NEGATIVE_KEYWORDS = [
    "football",
    "soccer",
    "movie trailer",
    "makeup",
    "nba",
    "game highlights",
    "vs",
    "战胜",
    "世界杯",
    "姆巴佩",
    "破门",
    "进球",
    "球员",
]

_ALWAYS_SKIP_KEYWORDS = [
    "高考",
    "查分",
    "分数线",
    "本科",
    "罕见病",
    "涉毒",
    "禁毒",
    "网警",
    "谣言",
    "死缓",
    "判死",
    "辞职",
    "首相",
    "总理",
    "乌克兰",
    "军事合作",
    "资产全线下跌",
    "全球资产",
    "雨水",
    "高温",
    "核电",
    "巡逻执法",
    "枪手",
    "abduction",
    "ransom note",
    "citizenship",
    "federal database",
    "voters",
    "ufc show",
    "sanctions",
    "oil sanctions",
    "housing bill",
]

_LIGHT_ENTERTAINMENT_KEYWORDS = [
    "微信",
    "艺人",
    "艺名",
    "热播",
    "剧",
    "电影",
    "综艺",
    "挑战",
    "卧鱼",
    "瑞克摇",
    "rickroll",
    "up主",
    "广告",
    "摸头",
    "游戏",
    "玩家",
    "steam",
    "puzzle",
    "logic puzzle",
    "show hn",
    "mythos",
]

_TREND_SOURCE_WEIGHTS = {
    "weibo": 70,
    "baidu": 64,
    "zhihu": 58,
    "toutiao": 58,
    "bilibili_trending": 56,
    "bilibili": 56,
    "google_news_cn": 46,
    "google_news_us": 38,
    "hacker_news": 48,
    "fallback_trend": 32,
}

_PLAYFUL_KEYWORDS = [
    "抽象",
    "离谱",
    "整活",
    "挑战",
    "精神状态",
    "年轻人",
    "网友",
    "打工人",
    "玄学",
    "反转",
    "meme",
    "memes",
    "weird",
    "funny",
    "viral",
    "internet",
    "trend",
    "challenge",
]

_RISK_KEYWORDS = [
    "killed",
    "murder",
    "shooting",
    "death",
    "dead",
    "war",
    "terror",
    "suicide",
    "rape",
    "遇难",
    "死亡",
    "枪击",
    "自杀",
    "战争",
    "恐袭",
    "性侵",
    "坠楼",
    "重伤",
]

_OFFICIAL_POLITICS_KEYWORDS = [
    "总书记",
    "习近平",
    "治国",
    "强国",
    "初心使命",
    "复兴征程",
    "中国网新闻中心",
    "牢记初心",
    "信仰强基",
    "理论固本",
    "思想铸魂",
    "新华社",
    "人民日报",
    "央视网",
    "中央",
    "外交部",
    "国防部",
    "国务院",
    "人大",
    "政协",
    "党",
    "president",
    "election",
    "government",
]

_HARD_NEWS_KEYWORDS = [
    "外资",
    "投资",
    "企业",
    "达沃斯",
    "论坛",
    "新兴技术",
    "科考",
    "出入境",
    "干扰",
    "经济",
    "贸易",
    "通报",
    "发布会",
    "industry",
    "minister",
    "iranian",
    "iran",
    "talks with us",
    "yahoo finance",
    "oil sales",
    "peace deal",
    "reuters",
    "nuclear",
    "reactor",
    "reactors",
    "built by 2040",
]

_AI_VERTICAL_KEYWORDS = [
    "glm",
    "deepseek",
    "claude",
    "openai",
    "gpt",
    "llm",
    "ai agent",
    "ai agents",
    "run locally",
    "local model",
    "foundation model",
]

_FUN_SIGNAL_KEYWORDS = [
    *_PLAYFUL_KEYWORDS,
    "游戏",
    "电竞",
    "玩家",
    "打工",
    "上班",
    "下班",
    "周一",
    "通勤",
    "评论区",
    "网友",
    "热梗",
    *_LIGHT_ENTERTAINMENT_KEYWORDS,
    "meme",
    "desktop",
    "steam",
    "bug",
]


# ---------------------------------------------------------------------------
# 状态读写
# ---------------------------------------------------------------------------


def _load_state(path: Path = _STATE_FILE) -> dict[str, Any]:
    """读取 X 自动运营状态，文件不存在时返回默认值。"""
    defaults: dict[str, Any] = {
        "seen": [],
        "drafts": [],
        "scheduled": [],
        "daily_times": [f"{h:02d}:{m:02d}" for h, m in DEFAULT_DAILY_TIMES],
        "published": [],
        "last_run": "",
    }
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                defaults.update(data)
    except (OSError, json.JSONDecodeError):
        return defaults
    return defaults


def _save_state(state: dict[str, Any], path: Path = _STATE_FILE) -> None:
    """原子化保存 X 自动运营状态。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def is_draft_approved(draft: dict[str, Any]) -> bool:
    """判断草稿是否已经由用户确认可外发。"""
    return draft.get("review_status") == "approved"


def _is_active_x_draft(draft: dict[str, Any]) -> bool:
    """判断草稿是否仍属于当前可处理队列。"""
    return draft.get("platform") == "x" and draft.get("status") in {
        "ready",
        "needs_review",
        "approved",
        "edited",
        "failed",
        "publishing",
    }


def _review_pending_status(draft: dict[str, Any]) -> str:
    """读取草稿审核状态；历史草稿默认视为待审核。"""
    return str(draft.get("review_status") or "pending")


def _video_digest(seed: ContentSeed) -> str:
    """生成稳定视频去重键，避免同一素材被无限重复使用。"""
    raw = f"{seed.source}|{seed.channel}|{seed.title}|{seed.url}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _draft_digest(seed: ContentSeed, angle: str) -> str:
    """生成稳定草稿去重键，同一视频可按不同角度发多条。"""
    raw = f"{_video_digest(seed)}|{angle}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _topic_key(seed: ContentSeed) -> str:
    """生成跨来源的话题去重键，避免同一热点多角度刷屏。"""
    text = re.sub(r"[\s，,。.!！?？:：；;｜|《》\"'“”‘’\-—_]+", "", str(seed.title or "").lower())
    text = re.sub(r"(?:[-_].*)$", "", text)
    return text[:80]


# ---------------------------------------------------------------------------
# 素材抓取：YouTube RSS / YouTube 字幕 / B站热榜
# ---------------------------------------------------------------------------


def _http_get_text(url: str, timeout: int = 12) -> str:
    """读取公开网页文本，失败交给调用方降级。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 OpenClawBot/1.0",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="ignore")


def _extract_video_id(url: str) -> str:
    """从常见 YouTube 链接提取 video id。"""
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/")[:32]
    query = urllib.parse.parse_qs(parsed.query)
    if query.get("v"):
        return str(query["v"][0])[:32]
    match = re.search(r"/(?:shorts|embed)/([A-Za-z0-9_-]{6,})", parsed.path)
    return match.group(1)[:32] if match else ""


def fetch_youtube_rss_seeds(
    channels: list[dict[str, str]] | None = None,
    per_channel: int = 3,
    timeout: int = 10,
) -> list[ContentSeed]:
    """从 YouTube 公开 RSS 拉取最新视频标题。

    这里不依赖 YouTube API Key，也不下载视频；相当于先拿“可蒸馏素材清单”。
    """
    seeds: list[ContentSeed] = []
    for channel in channels or DEFAULT_CHANNELS:
        name = channel.get("name", "YouTube")
        channel_id = channel.get("channel_id", "")
        if not channel_id:
            continue
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            raw = _http_get_text(url, timeout=timeout).encode("utf-8")
            root = ET.fromstring(raw)
            ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
            feed_title = root.findtext("atom:title", default=name, namespaces=ns)
            for entry in root.findall("atom:entry", ns)[: max(1, per_channel)]:
                title = entry.findtext("atom:title", default="", namespaces=ns).strip()
                video_id = entry.findtext("yt:videoId", default="", namespaces=ns).strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.attrib.get("href", "") if link_el is not None else ""
                published = entry.findtext("atom:published", default="", namespaces=ns).strip()
                if title:
                    seeds.append(
                        ContentSeed(
                            title=title,
                            channel=feed_title or name,
                            url=link or (f"https://www.youtube.com/watch?v={video_id}" if video_id else ""),
                            published=published,
                        )
                    )
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, UnicodeError, http.client.IncompleteRead):
            continue
    return seeds


def _decode_youtube_json(raw: str) -> str:
    """解开 YouTube 页面里转义后的 JSON 片段。"""
    text = raw.replace(r"\/", "/")
    text = text.replace(r"\u0026", "&")
    return html.unescape(text)


def extract_youtube_caption_urls(page_html: str) -> list[str]:
    """从 YouTube watch 页面提取字幕 timedtext URL。

    YouTube 页面结构经常变化，所以这里同时支持 JSON 片段和转义字符串两种形式。
    """
    if not page_html:
        return []
    urls: list[str] = []
    decoded = _decode_youtube_json(page_html)
    for match in re.finditer(r'"baseUrl"\s*:\s*"(https://[^"]+)"', decoded):
        url = _decode_youtube_json(match.group(1))
        if "timedtext" in url and url not in urls:
            urls.append(url)
    for match in re.finditer(r"https://www\.youtube\.com/api/timedtext[^\"'<>\\ ]+", decoded):
        url = _decode_youtube_json(match.group(0))
        if url not in urls:
            urls.append(url)
    return urls


def _parse_transcript_xml(raw_xml: str, limit_chars: int = 5000) -> str:
    """解析 YouTube timedtext XML 字幕。"""
    if not raw_xml.strip():
        return ""
    try:
        root = ET.fromstring(raw_xml.encode("utf-8"))
    except ET.ParseError:
        return ""
    chunks: list[str] = []
    for node in root.iter():
        if node.tag.endswith("text") and node.text:
            piece = html.unescape(re.sub(r"\s+", " ", node.text)).strip()
            if piece:
                chunks.append(piece)
        if sum(len(c) for c in chunks) > limit_chars:
            break
    return " ".join(chunks)[:limit_chars]


def fetch_youtube_transcript(url: str, timeout: int = 12, limit_chars: int = 5000) -> str:
    """无依赖抓取 YouTube 字幕，抓不到时返回空字符串。"""
    video_id = _extract_video_id(url)
    if not video_id:
        return ""
    watch_url = f"https://www.youtube.com/watch?v={video_id}&hl=en"
    try:
        page = _http_get_text(watch_url, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, http.client.IncompleteRead):
        return ""
    for caption_url in extract_youtube_caption_urls(page):
        try:
            xml = _http_get_text(caption_url, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, http.client.IncompleteRead):
            continue
        transcript = _parse_transcript_xml(xml, limit_chars=limit_chars)
        if transcript:
            return transcript
    return ""


def fetch_bilibili_trending_seeds(timeout: int = 10, limit: int = 8) -> list[ContentSeed]:
    """从 B站公开热榜接口补充中文视频素材种子。"""
    endpoints = [
        "https://app.bilibili.com/x/v2/search/trending/ranking",
        "https://api.bilibili.com/x/web-interface/popular?ps=20&pn=1",
    ]
    seeds: list[ContentSeed] = []
    for endpoint in endpoints:
        try:
            data = json.loads(_http_get_text(endpoint, timeout=timeout))
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError, http.client.IncompleteRead):
            continue
        items = data.get("data", {}).get("list") or data.get("data", {}).get("item") or []
        if isinstance(data.get("data"), dict) and data.get("data", {}).get("trackid") and data.get("data", {}).get("list"):
            items = data["data"]["list"]
        for item in items:
            title = str(item.get("title") or item.get("keyword") or "").strip()
            if not title:
                continue
            url = ""
            if item.get("uri"):
                url = str(item.get("uri"))
            elif item.get("bvid"):
                url = f"https://www.bilibili.com/video/{item.get('bvid')}"
            seeds.append(
                ContentSeed(
                    title=title,
                    channel=str(item.get("owner", {}).get("name") or item.get("name") or "Bilibili"),
                    url=url or "https://www.bilibili.com/",
                    source="bilibili_trending",
                    tags=["Bilibili"],
                )
            )
            if len(seeds) >= limit:
                return seeds
    return seeds


def _detect_language(text: str) -> str:
    """按字符粗略判断素材语言，用于中英热点混排。"""
    value = str(text or "")
    cjk = sum(1 for ch in value if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in value if ("a" <= ch.lower() <= "z"))
    if cjk >= max(2, latin // 3):
        return "zh"
    if latin:
        return "en"
    return ""


def _topic_url(source: str, title: str, raw_url: str = "") -> str:
    """为热点补一个可点击来源，方便发布后用户追上下文。"""
    if raw_url and raw_url.startswith("http"):
        return raw_url
    query = urllib.parse.quote(title)
    if source == "weibo":
        return f"https://s.weibo.com/weibo?q=%23{query}%23"
    if source == "zhihu":
        return f"https://www.zhihu.com/search?type=content&q={query}"
    if source == "bilibili":
        return f"https://search.bilibili.com/all?keyword={query}"
    if source == "hacker_news":
        return "https://news.ycombinator.com/"
    if source.startswith("google_news"):
        return f"https://news.google.com/search?q={query}"
    return f"https://www.baidu.com/s?wd={query}"


def _run_async_blocking(factory) -> Any:
    """在同步脚本中安全执行异步抓取，避免已有事件循环导致 coroutine 泄漏。"""
    try:
        import asyncio

        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    box: dict[str, Any] = {}

    def _target() -> None:
        """在线程中创建独立事件循环执行异步任务。"""
        try:
            import asyncio

            box["value"] = asyncio.run(factory())
        except Exception as exc:
            box["error"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=30)
    if "error" in box:
        raise box["error"]
    return box.get("value", [])


def fetch_real_trending_seeds(timeout: int = 18, limit: int = 30) -> list[ContentSeed]:
    """同步调用既有真实热榜模块，拿微博/百度/知乎等中文热点。"""
    try:
        from src.execution.social.real_trending import fetch_real_trending

        topics = _run_async_blocking(lambda: fetch_real_trending(limit=limit))
    except Exception:
        return []
    seeds: list[ContentSeed] = []
    for idx, item in enumerate(topics[:limit]):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        source = str(item.get("source") or "trend")
        raw_score = int(item.get("raw_score") or item.get("score") or 0)
        seeds.append(
            TrendSeed(
                title=title,
                channel=f"{source}热榜",
                url=_topic_url(source, title, str(item.get("url") or "")),
                source=source,
                summary=str(item.get("summary") or ""),
                language=_detect_language(title),
                raw_score=raw_score,
                raw_rank=idx + 1,
                heat_reason=f"来自 {source}，热度 {raw_score or item.get('score', 0)}",
                tags=["热点", source],
            )
        )
    return seeds


def fetch_google_news_trending_seeds(timeout: int = 10, per_locale: int = 10) -> list[ContentSeed]:
    """用 Google News RSS 补充中文/英文新闻趋势。"""
    feeds = [
        ("google_news_cn", "Google News 中文", "zh-CN", "CN"),
        ("google_news_us", "Google News US", "en-US", "US"),
    ]
    seeds: list[ContentSeed] = []
    for source, channel, hl, gl in feeds:
        url = f"https://news.google.com/rss?hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}"
        try:
            raw = _http_get_text(url, timeout=timeout).encode("utf-8")
            root = ET.fromstring(raw)
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, UnicodeError, http.client.IncompleteRead):
            continue
        for idx, item in enumerate(root.findall(".//item")[:per_locale]):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            published = (item.findtext("pubDate") or "").strip()
            if not title:
                continue
            seeds.append(
                TrendSeed(
                    title=html.unescape(title),
                    channel=channel,
                    url=_topic_url(source, title, link),
                    published=published,
                    source=source,
                    language=_detect_language(title),
                    raw_score=max(1, per_locale - idx) * 100,
                    raw_rank=idx + 1,
                    heat_reason="Google News 头条 RSS",
                    tags=["Trending", "News"],
                )
            )
    return seeds


def fetch_hacker_news_trending_seeds(timeout: int = 10, limit: int = 12) -> list[ContentSeed]:
    """用 HN Algolia API 补充英文科技/互联网社区趋势。"""
    url = f"https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={max(1, limit)}"
    try:
        data = json.loads(_http_get_text(url, timeout=timeout))
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError, http.client.IncompleteRead):
        return []
    seeds: list[ContentSeed] = []
    for idx, item in enumerate(data.get("hits", [])[:limit]):
        title = str(item.get("title") or item.get("story_title") or "").strip()
        if not title:
            continue
        points = int(item.get("points") or 0)
        comments = int(item.get("num_comments") or 0)
        seeds.append(
            TrendSeed(
                title=title,
                channel="Hacker News",
                url=str(item.get("url") or f"https://news.ycombinator.com/item?id={item.get('objectID', '')}"),
                published=str(item.get("created_at") or ""),
                source="hacker_news",
                language="en",
                raw_score=points + comments * 2,
                raw_rank=idx + 1,
                heat_reason=f"HN {points} points / {comments} comments",
                tags=["Internet", "Tech"],
            )
        )
    return seeds


def fetch_free_api_trending_seeds(limit: int = 20) -> list[ContentSeed]:
    """复用 free_apis 多源热榜作为中文热点兜底。"""
    try:
        from src.tools.free_apis import get_multi_trending

        topics = _run_async_blocking(get_multi_trending)
    except Exception:
        return []
    seeds: list[ContentSeed] = []
    for idx, item in enumerate(topics[:limit]):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        source = str(item.get("source") or "free_api")
        hot = int(item.get("hot") or 0)
        seeds.append(
            TrendSeed(
                title=title,
                channel=f"{source}热榜",
                url=_topic_url(source, title),
                source=source,
                language=_detect_language(title) or "zh",
                raw_score=hot,
                raw_rank=idx + 1,
                heat_reason=f"free_apis 中文热榜兜底，热度 {hot}",
                tags=["热点", source],
            )
        )
    return seeds


def _trend_from_bilibili(seed: ContentSeed) -> ContentSeed:
    """把 B站视频热榜素材转成热点素材，便于评分优先级统一。"""
    return TrendSeed(
        title=seed.title,
        channel=seed.channel or "Bilibili",
        url=seed.url,
        published=seed.published,
        source="bilibili_trending",
        summary=seed.summary,
        transcript=seed.transcript,
        tags=seed.tags or ["Bilibili", "热点"],
        language="zh",
        raw_score=seed.raw_score,
        raw_rank=seed.raw_rank,
        heat_reason="B站热榜，适合中文互联网梗和青年话题",
    )


def distill_seed(seed: ContentSeed, fetch_transcript: bool = True) -> ContentSeed:
    """把素材升级为可发推素材，保留热点元信息。"""
    transcript = seed.transcript
    if fetch_transcript and seed.url and "youtube.com" in seed.url and not transcript:
        transcript = fetch_youtube_transcript(seed.url)
    summary = seed.summary or summarize_transcript(transcript or seed.title)
    tags = seed.tags or infer_tags(f"{seed.title} {summary} {transcript[:500]}")
    cls = TrendSeed if isinstance(seed, TrendSeed) or seed.source in _TREND_SOURCE_WEIGHTS else ContentSeed
    return cls(
        title=seed.title,
        channel=seed.channel,
        url=seed.url,
        published=seed.published,
        source=seed.source,
        summary=summary,
        transcript=transcript,
        tags=tags,
        language=seed.language or _detect_language(f"{seed.title} {summary}"),
        raw_score=seed.raw_score,
        raw_rank=seed.raw_rank,
        heat_reason=seed.heat_reason,
    )


# ---------------------------------------------------------------------------
# 内容筛选与蒸馏
# ---------------------------------------------------------------------------


def infer_tags(text: str) -> list[str]:
    """从文本推断 X 话题标签，默认偏热点而不是 AI 品牌。"""
    lower = text.lower()
    tags: list[str] = []
    mapping = [
        ("热点", ["热点", "热搜", "爆", "全网", "网友", "年轻人", "打工人"]),
        ("抽象", ["抽象", "离谱", "精神状态", "玄学", "整活"]),
        ("Internet", ["internet", "viral", "meme", "memes", "trend"]),
        ("Agent", ["agent", "agents", "browser", "workflow"]),
        ("AI", ["ai", "openai", "claude", "gpt", "llm", "model"]),
        ("Automation", ["automation", "automate", "autonomous"]),
        ("Code", ["code", "coding", "developer", "rust", "python", "javascript"]),
        ("Startup", ["startup", "founder", "y combinator", "yc"]),
    ]
    for tag, words in mapping:
        if any(word in lower for word in words):
            tags.append(tag)
    return tags[:3] or ["热点", "互联网精神状态"]


def summarize_transcript(text: str, max_points: int = 3) -> str:
    """用规则把字幕/标题压缩成要点，保证无 LLM 时也能跑。"""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return "素材强调：把信息流变成可执行的工作流，再用自动化持续验证。"
    sentences = re.split(r"(?<=[。！？.!?])\s+|\n+", cleaned)
    scored: list[tuple[int, int, str]] = []
    for idx, sentence in enumerate(sentences):
        sentence = sentence.strip(" -—:：")
        if len(sentence) < 18:
            continue
        lower = sentence.lower()
        score = sum(2 for key in _KEYWORDS if key in lower)
        score += 1 if any(word in lower for word in ["why", "how", "because", "problem", "solution", "build", "change"]) else 0
        if score > 0:
            scored.append((score, -idx, sentence[:180]))
    if not scored:
        title = cleaned[:180]
        return f"素材核心：{title}。可转化为一个问题：它能不能变成稳定执行的自动化工作流？"
    chosen = [item[2] for item in sorted(scored, reverse=True)[:max_points]]
    return "；".join(chosen)


def _is_relevant_seed(seed: ContentSeed) -> bool:
    """判断素材是否适合追热点账号：有讨论度、低伤害、可玩梗。"""
    text = f"{seed.title} {seed.channel} {seed.summary} {seed.heat_reason}".lower()
    has_fun_signal = any(k.lower() in text for k in _FUN_SIGNAL_KEYWORDS)
    if any(k in text for k in _RISK_KEYWORDS):
        return False
    if any(k.lower() in text for k in _ALWAYS_SKIP_KEYWORDS):
        return False
    if any(k.lower() in text for k in _OFFICIAL_POLITICS_KEYWORDS):
        return False
    if any(k.lower() in text for k in _HARD_NEWS_KEYWORDS) and not has_fun_signal:
        return False
    if _is_trend_seed(seed) and any(k.lower() in text for k in _AI_VERTICAL_KEYWORDS) and not has_fun_signal:
        return False
    if re.search(r"[\w\u4e00-\u9fff]+\s*(?:vs|VS|对阵)\s*[\w\u4e00-\u9fff]+", seed.title):
        return False
    if seed.source in {"baidu", "toutiao", "google_news_cn", "google_news_us"} and not has_fun_signal:
        return False
    if isinstance(seed, TrendSeed) or seed.source in _TREND_SOURCE_WEIGHTS:
        return True
    return not any(k in text for k in _NEGATIVE_KEYWORDS)


def score_content_seed(seed: ContentSeed) -> int:
    """为涨粉向内容打分：热点源、热度、可吐槽性加分，高风险降权。"""
    text = f"{seed.title} {seed.summary} {seed.heat_reason}".lower()
    score = _TREND_SOURCE_WEIGHTS.get(seed.source, 18)
    if seed.raw_rank:
        score += max(0, 32 - seed.raw_rank * 2)
    if seed.raw_score:
        score += min(36, len(str(abs(seed.raw_score))) * 4)
    if seed.language in {"zh", "en"}:
        score += 6
    score += sum(8 for key in _PLAYFUL_KEYWORDS if key.lower() in text)
    score += 10 if len(seed.title) <= 42 else 0
    score -= sum(42 for key in _RISK_KEYWORDS if key.lower() in text)
    score -= sum(45 for key in _OFFICIAL_POLITICS_KEYWORDS if key.lower() in text)
    score -= sum(28 for key in _HARD_NEWS_KEYWORDS if key.lower() in text)
    score -= sum(24 for key in _AI_VERTICAL_KEYWORDS if key.lower() in text)
    score -= sum(16 for key in _NEGATIVE_KEYWORDS if key.lower() in text)
    score -= sum(60 for key in _ALWAYS_SKIP_KEYWORDS if key.lower() in text)
    if any(key.lower() in text for key in _FUN_SIGNAL_KEYWORDS):
        score += 18
    if re.search(r"[\w\u4e00-\u9fff]+\s*(?:vs|VS|对阵)\s*[\w\u4e00-\u9fff]+", seed.title):
        score -= 55
    if seed.source in {"baidu", "toutiao", "google_news_cn", "google_news_us"} and not any(
        key.lower() in text for key in _FUN_SIGNAL_KEYWORDS
    ):
        score -= 40
    if seed.source == "youtube_rss":
        score -= 22
    return score


def choose_seed(seeds: list[ContentSeed], state: dict[str, Any]) -> ContentSeed:
    """选择一条未发过的热点素材，失败时使用内置兜底素材。"""
    seen = set(state.get("seen", []) or [])
    used_video = {str(d).split(":", 1)[0] for d in seen}
    ordered = sorted([seed for seed in seeds if _is_relevant_seed(seed)], key=score_content_seed, reverse=True)
    fallback = sorted([seed for seed in seeds if seed not in ordered], key=score_content_seed, reverse=True)
    for seed in ordered + fallback:
        digest = _video_digest(seed)
        if digest not in seen and digest not in used_video:
            return seed
    for seed in _FALLBACK_SEEDS:
        if _video_digest(seed) not in seen:
            return seed
    return _FALLBACK_SEEDS[0]


def choose_seeds(seeds: list[ContentSeed], state: dict[str, Any], count: int = 6) -> list[ContentSeed]:
    """选择多条素材，用于一天 5-8 篇内容。"""
    seen = set(state.get("seen", []) or [])
    safe_seeds = [seed for seed in seeds if _is_relevant_seed(seed)]
    ordered = sorted(safe_seeds, key=score_content_seed, reverse=True)
    chosen: list[ContentSeed] = []
    chosen_digest: set[str] = set()
    chosen_topics: set[str] = set()

    def add_seed(seed: ContentSeed) -> bool:
        """加入一个未见过且安全的素材。"""
        digest = _video_digest(seed)
        topic_key = _topic_key(seed)
        if digest in seen or digest in chosen_digest or topic_key in chosen_topics or not _is_relevant_seed(seed):
            return False
        chosen.append(seed)
        chosen_digest.add(digest)
        if topic_key:
            chosen_topics.add(topic_key)
        return True

    if count >= 4:
        per_language_floor = min(2, count // 3)
        for language in ("zh", "en"):
            added = 0
            for seed in ordered:
                if (seed.language or _detect_language(seed.title)) != language:
                    continue
                if add_seed(seed):
                    added += 1
                if added >= per_language_floor:
                    break

    for seed in ordered + _FALLBACK_SEEDS:
        add_seed(seed)
        if len(chosen) >= count:
            break
    if len(chosen) >= count:
        return chosen[:count]
    while len(chosen) < count:
        chosen.append(_FALLBACK_SEEDS[len(chosen) % len(_FALLBACK_SEEDS)])
    return chosen


def _clean_title(title: str) -> str:
    """清理视频标题中的夸张符号，保留可读结论。"""
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    text = re.sub(r"[🔥😱🚨]+", "", text).strip()
    return text[:140]


def _format_tags(tags: list[str]) -> str:
    """生成 X 话题标签字符串。"""
    normalized = []
    for tag in tags[:3]:
        clean = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]", "", tag)
        if clean:
            normalized.append(f"#{clean}")
    if not normalized:
        normalized = ["#热点", "#互联网精神状态"]
    return " ".join(normalized[:3])


def _is_trend_seed(seed: ContentSeed) -> bool:
    """识别热点素材，和旧视频蒸馏模板分流。"""
    return isinstance(seed, TrendSeed) or seed.source in _TREND_SOURCE_WEIGHTS


def _format_legacy_tags(tags: list[str]) -> str:
    """旧 OpenClaw 实验日志保留品牌标签，避免破坏既有入口。"""
    text = _format_tags(tags)
    return text if "#OpenClaw" in text else f"#OpenClaw {text}".strip()


def x_weighted_length(text: str) -> int:
    """估算 X 推文长度：URL 约 23，CJK 字符按 2 计。"""
    total = 0
    pos = 0
    for match in re.finditer(r"https?://\S+", text or ""):
        total += _weighted_plain_length(text[pos:match.start()])
        total += 23
        pos = match.end()
    total += _weighted_plain_length((text or "")[pos:])
    return total


def _weighted_plain_length(text: str) -> int:
    """估算非 URL 文本在 X 里的权重。"""
    total = 0
    for char in text:
        if char.isspace():
            total += 1
        elif "\u4e00" <= char <= "\u9fff" or "\u3000" <= char <= "\u303f" or "\uff00" <= char <= "\uffef":
            total += 2
        else:
            total += 1
    return total


def _trim_to_weight(text: str, limit: int) -> str:
    """按估算权重截断文本，给 X 普通推文留安全余量。"""
    out: list[str] = []
    total = 0
    for char in text:
        weight = _weighted_plain_length(char)
        if total + weight > limit:
            break
        out.append(char)
        total += weight
    return "".join(out).rstrip(" ，。,.；;：:")


def _compact_x_post(seed: ContentSeed, angle: str, tags: str, url: str, max_weight: int = 250) -> str:
    """生成普通账号也能发布的短推文，保证自动发布不被长度卡住。"""
    title = _clean_title(seed.title)
    channel = _trim_to_weight(seed.channel or "YouTube", 28)
    topic_budget = 64 if url else 86
    title_short = _trim_to_weight(title, topic_budget)
    if _is_trend_seed(seed):
        angle_line = {
            "internet_mood": "大家嘴上说路过，其实都在等评论区发疯。",
            "abstract_roast": "不是新闻离谱，是这个版本的人类太会自我整活。",
            "contrast_meme": "标题负责装正经，评论区负责把大家的精神状态上链接。",
            "three_line_take": "怪。合理。像我今天的待办列表。",
            "cn_en_mirror": "中文区：绷不住了。英文区：we are so cooked.",
            "reply_bait": "所以这算时代进步，还是网友终于不装正常了？",
        }.get(angle, "互联网又给生活加了一个隐藏支线。")
        base_lines = [f"{title_short}", angle_line, tags]
        text = "\n\n".join(base_lines).strip()
        while x_weighted_length(text) > max_weight and title_short:
            title_short = _trim_to_weight(title_short, max(10, x_weighted_length(title_short) - 10))
            base_lines[0] = f"{title_short}"
            text = "\n\n".join(base_lines).strip()
        return text
    angle_line = {
        "operating_loop": "结论：先自动化选题→判断→发布→复盘，而不是只自动化写作。",
        "contrarian": "反常识：账号增长最该自动化的不是文案，而是每天稳定出现。",
        "tool_workflow": "工作流：视频素材→提炼观点→生成推文→定时发布→看反馈。",
        "founder_note": "Founder note：个人社媒会变成一个小型媒体操作系统。",
        "checklist": "我只问 3 件事：新观点是什么？能否变 SOP？明天怎么验证？",
        "longform": "长文先不硬上，先证明自动选题和自动发布每天都能跑。",
    }.get(angle, "结论：把信息流变成可执行工作流，再自动发布复盘。")
    base_lines = [f"OpenClaw 自动蒸馏：{channel}｜{title_short}", angle_line, tags]
    if url:
        base_lines.append(url)
    text = "\n\n".join(base_lines).strip()
    while x_weighted_length(text) > max_weight and title_short:
        title_short = _trim_to_weight(title_short, max(10, x_weighted_length(title_short) - 10))
        base_lines[0] = f"OpenClaw 自动蒸馏：{channel}｜{title_short}"
        text = "\n\n".join(base_lines).strip()
    if x_weighted_length(text) <= max_weight:
        return text
    no_url_lines = base_lines[:-1] if url else base_lines
    return "\n\n".join(no_url_lines).strip()


def _fit_x_post(text: str, seed: ContentSeed, angle: str, tags: str, url: str, max_weight: int = 250) -> str:
    """自动发布默认使用普通推文安全长度，防止 X 按钮 disabled。"""
    if x_weighted_length(text) <= max_weight:
        return text
    return _compact_x_post(seed, angle, tags, url, max_weight=max_weight)


def compose_x_post(seed: ContentSeed, now: datetime | None = None, angle: str = "operating_loop") -> str:
    """把素材改写成 X 风格推文；热点素材默认更像抽象热点号。"""
    now = now or datetime.now(ZoneInfo(_DEFAULT_TZ))
    distilled = distill_seed(seed, fetch_transcript=False)
    title = _clean_title(distilled.title)
    channel = distilled.channel or "YouTube"
    url = distilled.url.strip()
    summary = distilled.summary or summarize_transcript(distilled.transcript or title)
    tags = _format_tags(distilled.tags)
    date_hint = now.strftime("%m/%d")

    if _is_trend_seed(distilled):
        reason = distilled.heat_reason or summary
        topic = _trim_to_weight(title, 72 if distilled.language == "zh" else 120)
        fun_hook = _trim_to_weight(reason, 48 if distilled.language == "zh" else 78)
        templates: dict[str, list[str]] = {
            "internet_mood": [
                f"{topic}",
                "",
                "今天刷到它的感觉：",
                "互联网不是信息流，是一群人轮流提交精神病历。",
                f"梗点：{fun_hook}",
                tags,
            ],
            "abstract_roast": [
                f"{topic}",
                "",
                "第一眼：这啥。",
                "第二眼：好像也合理。",
                "第三眼：完了，我也在这个赛道里。",
                tags,
            ],
            "contrast_meme": [
                f"{topic}",
                "",
                "标题负责装正经。",
                "评论区负责把大家的精神状态开源。",
                tags,
            ],
            "three_line_take": [
                f"{topic}",
                "",
                "很怪。",
                "但又不是不能理解。",
                "像生活突然弹了一个隐藏成就。",
                tags,
            ],
            "cn_en_mirror": [
                f"{topic}",
                "",
                "中文网友：绷不住了。",
                "英文网友：we are so cooked.",
                "结论：大家只是在用梗给现实降噪。",
                tags,
            ],
            "reply_bait": [
                f"{topic}",
                "",
                "我现在只想知道：",
                "这是时代进步，还是网友终于不装正常了？",
                tags,
            ],
        }
        lines = templates.get(angle, templates["internet_mood"])
        text = "\n".join(lines).strip()
        return _fit_x_post(text, distilled, angle, tags, "")

    tags = _format_legacy_tags(distilled.tags)

    templates: dict[str, list[str]] = {
        "operating_loop": [
            f"{date_hint} 的 X 自动运营素材来自 {channel}：{title}",
            "",
            f"我把它压缩成一句话：{summary}",
            "",
            "我的判断：真正值得自动化的不是“看更多视频”，而是固定跑这 3 步：",
            "1. 抓到一个新观点",
            "2. 变成一个可执行工作流",
            "3. 第二天用反馈数据验证",
            "",
            "如果这条能稳定发出来，说明 OpenClaw 的内容运营已经从手工发帖，进入机器值班。",
            tags,
        ],
        "contrarian": [
            f"反常识：做 X 运营，最不该自动化的是“写作”。",
            "",
            f"今天看 {channel} 的素材：{title}",
            f"提炼后我更关心：{summary}",
            "",
            "写作只是最后 10%。前面 90% 是选题、判断、去重、排程、复盘。",
            "所以 OpenClaw 先自动化运营链路，再让模型写字。",
            tags,
        ],
        "tool_workflow": [
            "今天这条不是普通转发，是一次自动运营实验：",
            "",
            f"输入：{channel} 的视频/标题/字幕",
            f"蒸馏：{summary}",
            "输出：一条可讨论、可追踪、可复盘的 X 推文",
            "",
            "下一步要看的不是点赞，而是：哪类素材最容易变成可执行工作流。",
            tags,
        ],
        "founder_note": [
            "Founder note：我越来越觉得，个人社媒会变成一个“小型媒体操作系统”。",
            "",
            f"今天素材：{title}",
            f"来自：{channel}",
            f"蒸馏：{summary}",
            "",
            "人负责定方向，系统负责每天出现。这个差别，会把很多只靠情绪更新的账号拉开。",
            tags,
        ],
        "checklist": [
            f"把 {channel} 的一个视频变成 X 内容，我只问 5 个问题：",
            "",
            f"素材：{title}",
            "1. 它说的新东西是什么？",
            "2. 能不能变成 SOP？",
            "3. 哪一步可以交给 agent？",
            "4. 有没有反常识点？",
            "5. 明天用什么指标复盘？",
            "",
            f"本次提炼：{summary}",
            tags,
        ],
        "longform": [
            "我准备把 X Premium 当成 OpenClaw 的公开实验日志。",
            "",
            f"今天系统抓到的素材是 {channel}：{title}",
            f"字幕/标题蒸馏后的核心是：{summary}",
            "",
            "这件事对我有一个启发：AI 账号不应该只追热点，而应该持续展示一套方法论如何运行。",
            "",
            "我的方法很简单：",
            "- 每天抓取 YouTube/B站/技术社区素材",
            "- 过滤掉泛娱乐和低相关内容",
            "- 用不同角度改写成 5-8 条 X 内容",
            "- 定时发布，再根据反馈调整下一轮选题",
            "",
            "换句话说，账号本身就是一个 agent。人只负责调方向，不再负责每天硬挤灵感。",
            tags,
        ],
    }
    lines = templates.get(angle, templates["operating_loop"])
    if url:
        lines.append(url)
    text = "\n".join(lines).strip()
    return _fit_x_post(text[:3800], distilled, angle, tags, url)


# ---------------------------------------------------------------------------
# 草稿与发布状态
# ---------------------------------------------------------------------------


def fetch_all_video_seeds(include_bilibili: bool = True) -> list[ContentSeed]:
    """聚合 YouTube 与 B站素材种子。"""
    seeds = fetch_youtube_rss_seeds()
    if include_bilibili:
        seeds.extend(fetch_bilibili_trending_seeds())
    return seeds


def fetch_all_content_seeds(include_video_fallback: bool = True) -> list[ContentSeed]:
    """聚合中英文热点源，视频素材只作为低优先级补位。"""
    seeds: list[ContentSeed] = []
    for loader in (
        fetch_real_trending_seeds,
        fetch_free_api_trending_seeds,
        fetch_google_news_trending_seeds,
        fetch_hacker_news_trending_seeds,
    ):
        try:
            seeds.extend(loader())
        except Exception:
            continue
    try:
        seeds.extend(_trend_from_bilibili(seed) for seed in fetch_bilibili_trending_seeds(limit=10))
    except Exception:
        seeds.extend([])
    if include_video_fallback:
        try:
            seeds.extend(fetch_youtube_rss_seeds(per_channel=1))
        except Exception:
            seeds.extend([])
    return seeds


def _is_legacy_ai_draft(draft: dict[str, Any]) -> bool:
    """识别旧 AI 垂直草稿，防止继续被自动发布。"""
    if draft.get("status") != "ready" or draft.get("platform") != "x":
        return False
    text = str(draft.get("text") or "")
    seed = draft.get("seed") if isinstance(draft.get("seed"), dict) else {}
    source = str(seed.get("source") or "")
    return "OpenClaw 自动蒸馏" in text or source in {"youtube_rss", "fallback"}


def _supersede_legacy_ready_drafts(state: dict[str, Any]) -> None:
    """把未发布的旧 AI/视频草稿下线，给热点草稿让路。"""
    for draft in state.get("drafts", []) or []:
        if _is_legacy_ai_draft(draft):
            draft["status"] = "superseded"
            draft["superseded_at"] = now_et().isoformat()
            draft["superseded_reason"] = "用户已将 X 运营方向切换为中英文热点追踪/抽象好玩内容"


def _supersede_ready_drafts_for_rebuild(state: dict[str, Any]) -> None:
    """每日重建草稿时替换旧队列，避免发布过时热点。"""
    for draft in state.get("drafts", []) or []:
        if draft.get("status") == "ready" and draft.get("platform") == "x":
            draft["status"] = "superseded"
            draft["superseded_at"] = now_et().isoformat()
            draft["superseded_reason"] = "已生成更新的热点队列，旧 ready 草稿下线"


def _existing_ready_draft(state: dict[str, Any]) -> dict[str, Any] | None:
    """返回最早的一条已审核待发布草稿。"""
    ready = [
        d
        for d in state.get("drafts", [])
        if d.get("status") in {"ready", "approved"} and d.get("platform") == "x" and is_draft_approved(d)
    ]
    if not ready:
        return None
    return sorted(ready, key=lambda d: str(d.get("created_at", "")))[0]


def mark_draft_review(
    draft_id: str,
    approved: bool,
    reviewer: str = "owner",
    state_path: Path = _STATE_FILE,
) -> dict[str, Any]:
    """审核 X 自动运营草稿：用户确认后才允许定时/手动外发。"""
    state = _load_state(state_path)
    for draft in state.get("drafts", []):
        if draft.get("id") != draft_id:
            continue
        draft["review_status"] = "approved" if approved else "rejected"
        draft["reviewed_at"] = now_et().isoformat()
        draft["approved_by"] = reviewer if approved else ""
        if approved and draft.get("status") in {"ready", "needs_review", "edited", "failed", "rejected"}:
            draft["status"] = "approved"
        elif not approved:
            draft["status"] = "rejected"
        _save_state(state, state_path)
        return {"success": True, "draft": draft}
    return {"success": False, "error": "Invalid draft id"}


def get_next_reviewable_drafts(limit: int = 8, state_path: Path = _STATE_FILE) -> list[dict[str, Any]]:
    """返回需要用户确认的人设/内容草稿。"""
    state = _load_state(state_path)
    drafts = [
        draft
        for draft in state.get("drafts", []) or []
        if _is_active_x_draft(draft) and not is_draft_approved(draft)
    ]
    return sorted(drafts, key=lambda item: str(item.get("created_at", "")))[: max(1, limit)]


def require_draft_review(draft: dict[str, Any], state_path: Path = _STATE_FILE) -> dict[str, Any]:
    """阻止未审核草稿发布，并把状态写回待审核。"""
    state = _load_state(state_path)
    for item in state.get("drafts", []):
        if item.get("id") == draft.get("id"):
            item["status"] = "needs_review"
            item["review_status"] = _review_pending_status(item)
            item["review_required_at"] = now_et().isoformat()
            item["review_required_reason"] = "发布前请先确认人设和内容"
            draft = item
            break
    _save_state(state, state_path)
    return {
        "success": False,
        "requires_review": True,
        "error": "发布前请先确认人设和内容，草稿审核通过后才允许发布",
        "draft": draft,
    }


def build_next_draft(state_path: Path = _STATE_FILE, angle: str = "operating_loop", fetch_transcript: bool = True) -> dict[str, Any]:
    """构建下一条 X 自动运营草稿并写入状态。"""
    state = _load_state(state_path)
    _supersede_legacy_ready_drafts(state)
    if angle == "operating_loop":
        angle = "internet_mood"
    seeds = fetch_all_content_seeds()
    if not seeds:
        seeds = fetch_all_video_seeds()
    seed = distill_seed(choose_seed(seeds, state), fetch_transcript=fetch_transcript)
    digest = _draft_digest(seed, angle)
    post = compose_x_post(seed, angle=angle)
    draft = {
        "id": f"xauto-{digest}",
        "platform": "x",
        "status": "ready",
        "review_status": "pending",
        "angle": angle,
        "text": post,
        "seed": seed.__dict__,
        "video_digest": _video_digest(seed),
        "digest": digest,
        "created_at": now_et().isoformat(),
        "review_required_reason": "发布前请先确认热点抽象号人设和内容",
    }
    drafts = [d for d in state.get("drafts", []) if d.get("id") != draft["id"]]
    drafts.append(draft)
    state["drafts"] = drafts[-80:]
    state["last_run"] = now_et().isoformat()
    _save_state(state, state_path)
    return draft


def build_daily_drafts(
    count: int = 6,
    state_path: Path = _STATE_FILE,
    fetch_transcript: bool = True,
) -> list[dict[str, Any]]:
    """一次生成当天 5-8 篇候选草稿。"""
    bounded_count = min(8, max(1, count))
    state = _load_state(state_path)
    _supersede_ready_drafts_for_rebuild(state)
    raw_seeds = fetch_all_content_seeds()
    if not raw_seeds:
        raw_seeds = fetch_all_video_seeds()
    seeds = [distill_seed(seed, fetch_transcript=fetch_transcript) for seed in choose_seeds(raw_seeds, state, bounded_count)]
    existing_ids = {d.get("id") for d in state.get("drafts", [])}
    drafts = list(state.get("drafts", []) or [])
    created: list[dict[str, Any]] = []
    for idx in range(bounded_count):
        seed = seeds[idx % len(seeds)] if seeds else _FALLBACK_SEEDS[idx % len(_FALLBACK_SEEDS)]
        angle = POST_ANGLES[idx % len(POST_ANGLES)]
        digest = _draft_digest(seed, angle)
        draft_id = f"xauto-{digest}"
        draft = {
            "id": draft_id,
            "platform": "x",
            "status": "ready",
            "review_status": "pending",
            "angle": angle,
            "text": compose_x_post(seed, angle=angle),
            "seed": seed.__dict__,
            "video_digest": _video_digest(seed),
            "digest": digest,
            "created_at": now_et().isoformat(),
            "review_required_reason": "发布前请先确认热点抽象号人设和内容",
        }
        if draft_id in existing_ids:
            for pos, existing in enumerate(drafts):
                if existing.get("id") == draft_id and existing.get("status") in {"ready", "failed", "superseded"}:
                    draft["created_at"] = existing.get("created_at") or draft["created_at"]
                    drafts[pos] = draft
                    break
        else:
            drafts.append(draft)
            existing_ids.add(draft_id)
        created.append(draft)
    state["drafts"] = drafts[-80:]
    state["last_run"] = now_et().isoformat()
    _save_state(state, state_path)
    return created


def compose_xhs_note(seed: ContentSeed, angle: str = "internet_mood") -> dict[str, str]:
    """把热点素材改写成小红书图文笔记草稿。"""
    distilled = distill_seed(seed, fetch_transcript=False)
    topic = _trim_to_weight(_clean_title(distilled.title), 56)
    reason = _trim_to_weight(distilled.heat_reason or distilled.summary or "大家都在讨论，适合轻吐槽", 70)
    title_templates = {
        "internet_mood": f"今天的互联网精神状态：{topic}",
        "abstract_roast": f"{topic}，越看越抽象",
        "contrast_meme": f"热搜里最有反差感的一条：{topic}",
        "three_line_take": f"三句话看懂今天这个热梗",
        "cn_en_mirror": f"中英网友对这事的反应太同步了",
        "reply_bait": f"这个热点到底算进化还是整活？",
    }
    title = title_templates.get(angle, f"今天这个热点有点东西：{topic}")[:28]
    body_templates = {
        "internet_mood": [
            f"今天刷到「{topic}」，第一反应不是震惊，是：这届网友真的很会把生活过成弹幕版。",
            f"我觉得好玩的点在这里：{reason}。",
            "适合评论区聊聊：你看到这个热点的第一反应是什么？",
        ],
        "abstract_roast": [
            f"「{topic}」这个话题最抽象的地方是：它看起来很离谱，但又离谱得很符合现实。",
            f"热度原因大概是：{reason}。",
            "有时候互联网不是在解决问题，是在给问题起一个更好笑的名字。",
        ],
        "contrast_meme": [
            f"「{topic}」的反差感很强：标题像正经新闻，评论区像大型精神互助小组。",
            f"为什么能火：{reason}。",
            "我现在越来越觉得，热搜本质上是大家共同写的每日情绪日报。",
        ],
        "three_line_take": [
            f"关于「{topic}」，我的三句话：",
            "1）很怪，但不是不能理解。",
            "2）越看越像生活里的隐藏支线。",
            f"3）它会火，大概率因为：{reason}。",
        ],
        "cn_en_mirror": [
            f"「{topic}」这类热点最妙的是，中英网友反应经常高度一致。",
            "中文区：绷不住了。",
            "英文区：we are so cooked.",
            "本质都是在用梗给现实降噪。",
        ],
        "reply_bait": [
            f"看到「{topic}」我只想问一句：",
            "这是时代进步，还是大家终于不装正常了？",
            f"能上热搜的原因大概是：{reason}。",
            "评论区交给懂的人。",
        ],
    }
    body_lines = body_templates.get(angle, body_templates["internet_mood"])
    tags = " ".join(_format_tags(distilled.tags).split()[:4])
    body = "\n\n".join([*body_lines, tags]).strip()[:900]
    return {"title": title, "body": body, "text": f"{title}\n\n{body}"}


def build_xhs_review_drafts(
    count: int = 2,
    state_path: Path = _STATE_FILE,
    fetch_transcript: bool = False,
) -> list[dict[str, Any]]:
    """生成小红书待审核笔记草稿，和 X 共用热点池但不自动发布。"""
    bounded_count = min(4, max(1, count))
    state = _load_state(state_path)
    raw_seeds = fetch_all_content_seeds()
    seeds = [
        distill_seed(seed, fetch_transcript=fetch_transcript)
        for seed in choose_seeds(raw_seeds, state, bounded_count + 2)
        if (seed.language or _detect_language(seed.title)) == "zh"
    ]
    if not seeds:
        seeds = [
            distill_seed(seed, fetch_transcript=False)
            for seed in choose_seeds(raw_seeds, state, bounded_count + 2)
        ]
    existing_ids = {d.get("id") for d in state.get("drafts", [])}
    drafts = list(state.get("drafts", []) or [])
    created: list[dict[str, Any]] = []
    for idx in range(bounded_count):
        seed = seeds[idx % len(seeds)] if seeds else _FALLBACK_SEEDS[idx % len(_FALLBACK_SEEDS)]
        angle = POST_ANGLES[idx % len(POST_ANGLES)]
        digest = _draft_digest(seed, f"xhs:{angle}")
        note = compose_xhs_note(seed, angle=angle)
        draft_id = f"xhsauto-{digest}"
        draft = {
            "id": draft_id,
            "platform": "xhs",
            "status": "needs_review",
            "review_status": "pending",
            "angle": angle,
            "title": note["title"],
            "body": note["body"],
            "text": note["text"],
            "seed": seed.__dict__,
            "video_digest": _video_digest(seed),
            "digest": digest,
            "created_at": now_et().isoformat(),
            "review_required_reason": "发布前请先确认小红书笔记人设和内容",
        }
        if draft_id in existing_ids:
            for pos, existing in enumerate(drafts):
                if existing.get("id") == draft_id and existing.get("status") in {"ready", "needs_review", "failed", "superseded"}:
                    draft["created_at"] = existing.get("created_at") or draft["created_at"]
                    drafts[pos] = draft
                    break
        else:
            drafts.append(draft)
            existing_ids.add(draft_id)
        created.append(draft)
    state["drafts"] = drafts[-90:]
    state["last_run"] = now_et().isoformat()
    _save_state(state, state_path)
    return created


def get_or_build_next_ready_draft(state_path: Path = _STATE_FILE) -> dict[str, Any]:
    """发布入口：只消费已审核草稿；没有则补草稿并等待用户确认。"""
    state = _load_state(state_path)
    draft = _existing_ready_draft(state)
    if draft:
        return draft
    build_daily_drafts(count=6, state_path=state_path)
    state = _load_state(state_path)
    draft = _existing_ready_draft(state)
    if draft:
        return draft
    reviewable = get_next_reviewable_drafts(limit=1, state_path=state_path)
    return reviewable[0] if reviewable else build_next_draft(state_path)


def _published_url(result: dict[str, Any]) -> str:
    """把发布结果标准化为可点击的 X 链接。"""
    url = str(result.get("url") or "").strip()
    if url.startswith("http"):
        return url
    tweet_id = str(result.get("tweet_id") or url or "").strip()
    if tweet_id.isdigit():
        handle = str(result.get("handle") or "BonoDJblack").strip().lstrip("@") or "BonoDJblack"
        return f"https://x.com/{handle}/status/{tweet_id}"
    return url


def mark_published(draft: dict[str, Any], result: dict[str, Any], state_path: Path = _STATE_FILE) -> None:
    """发布成功后记录 URL 和去重键。"""
    state = _load_state(state_path)
    video_digest = draft.get("video_digest", "")
    draft_digest = draft.get("digest", "")
    seen_items = [item for item in [video_digest, f"{video_digest}:{draft.get('angle', '')}", draft_digest] if item]
    if seen_items:
        seen = list(dict.fromkeys(list(state.get("seen", []) or []) + seen_items))
        state["seen"] = seen[-800:]
    event = {
        "id": draft.get("id", ""),
        "platform": "x",
        "url": _published_url(result),
        "method": result.get("method") or result.get("status") or "unknown",
        "published_at": now_et().isoformat(),
        "seed": draft.get("seed", {}),
        "angle": draft.get("angle", ""),
    }
    state.setdefault("published", []).append(event)
    state["published"] = state["published"][-300:]
    for item in state.get("drafts", []):
        if item.get("id") == draft.get("id"):
            item["status"] = "published"
            item["published_at"] = event["published_at"]
            item["url"] = event["url"]
    _save_state(state, state_path)


def mark_failed(draft: dict[str, Any], error: str, state_path: Path = _STATE_FILE) -> None:
    """发布失败时记录原因，但保留草稿等待下一次排程重试。"""
    state = _load_state(state_path)
    failures = state.setdefault("failures", [])
    failures.append({
        "id": draft.get("id", ""),
        "platform": "x",
        "angle": draft.get("angle", ""),
        "error": str(error)[:300],
        "failed_at": now_et().isoformat(),
    })
    state["failures"] = failures[-100:]
    for item in state.get("drafts", []):
        if item.get("id") == draft.get("id"):
            # 不改成 failed，避免临时登录/网络问题导致草稿被跳过。
            item["status"] = "ready"
            item["last_error"] = str(error)[:300]
            item["last_failed_at"] = now_et().isoformat()
    _save_state(state, state_path)


# ---------------------------------------------------------------------------
# launchd 排程
# ---------------------------------------------------------------------------


def parse_daily_times(value: str | list[str] | None = None) -> list[tuple[int, int]]:
    """解析 08:30,10:30 这类每日发布时间。"""
    if value is None:
        return DEFAULT_DAILY_TIMES
    parts = value if isinstance(value, list) else [p.strip() for p in str(value).split(",") if p.strip()]
    times: list[tuple[int, int]] = []
    for part in parts:
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", str(part).strip())
        if not match:
            continue
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            times.append((hour, minute))
    return times or DEFAULT_DAILY_TIMES


def next_morning_at(hour: int = 8, minute: int = 30, tz_name: str = _DEFAULT_TZ) -> datetime:
    """计算下一次指定发布时间。"""
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return target


def next_scheduled_at(times: list[tuple[int, int]] | None = None, tz_name: str = _DEFAULT_TZ) -> datetime:
    """计算多时段排程里的下一次触发时间。"""
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    candidates = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in (times or DEFAULT_DAILY_TIMES)]
    future = [item for item in candidates if item > now]
    return min(future) if future else min(candidates) + timedelta(days=1)


def _calendar_interval_xml(times: list[tuple[int, int]], target: datetime, repeat_daily: bool) -> str:
    """生成 launchd StartCalendarInterval XML。"""
    if not repeat_daily:
        return (
            "<dict>\n"
            f"        <key>Year</key><integer>{target.year}</integer>\n"
            f"        <key>Month</key><integer>{target.month}</integer>\n"
            f"        <key>Day</key><integer>{target.day}</integer>\n"
            f"        <key>Hour</key><integer>{target.hour}</integer>\n"
            f"        <key>Minute</key><integer>{target.minute}</integer>\n"
            "      </dict>"
        )
    if len(times) == 1:
        hour, minute = times[0]
        return (
            "<dict>\n"
            f"        <key>Hour</key><integer>{hour}</integer>\n"
            f"        <key>Minute</key><integer>{minute}</integer>\n"
            "      </dict>"
        )
    blocks = []
    for hour, minute in times:
        blocks.append(
            "      <dict>\n"
            f"        <key>Hour</key><integer>{hour}</integer>\n"
            f"        <key>Minute</key><integer>{minute}</integer>\n"
            "      </dict>"
        )
    return "<array>\n" + "\n".join(blocks) + "\n      </array>"


def write_launchd_plist(
    script_path: Path,
    label: str = "com.openclaw.x-auto-morning-post",
    target_time: datetime | None = None,
    plist_path: Path | None = None,
    repeat_daily: bool = True,
    daily_times: list[tuple[int, int]] | None = None,
) -> Path:
    """写入 macOS launchd 任务配置。

    默认每天 6 个固定时间运行；如果 repeat_daily=False，则写成一次性日期任务。
    """
    times = daily_times or DEFAULT_DAILY_TIMES
    target = target_time or next_scheduled_at(times)
    plist_path = plist_path or (Path.home() / "Library" / "LaunchAgents" / f"{label}.plist")
    stdout = _PACKAGE_ROOT / "logs" / "x_auto_morning_post.out.log"
    stderr = _PACKAGE_ROOT / "logs" / "x_auto_morning_post.err.log"
    stdout.parent.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    python_bin = _PACKAGE_ROOT / ".venv312" / "bin" / "python"
    if not python_bin.exists():
        python_bin = Path("/usr/bin/python3")
    calendar_interval = _calendar_interval_xml(times, target, repeat_daily)
    content = textwrap.dedent(f"""\
    <?xml version=\"1.0\" encoding=\"UTF-8\"?>
    <!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
    <plist version=\"1.0\">
    <dict>
      <key>Label</key><string>{label}</string>
      <key>ProgramArguments</key>
      <array>
        <string>{python_bin}</string>
        <string>{script_path}</string>
        <string>--publish-next</string>
      </array>
      <key>WorkingDirectory</key><string>{_PACKAGE_ROOT}</string>
      <key>StartCalendarInterval</key>
      {calendar_interval}
      <key>StandardOutPath</key><string>{stdout}</string>
      <key>StandardErrorPath</key><string>{stderr}</string>
    </dict>
    </plist>
    """)
    plist_path.write_text(content, encoding="utf-8")
    return plist_path


__all__ = [
    "ContentSeed",
    "VideoSeed",
    "TrendSeed",
    "DEFAULT_CHANNELS",
    "DEFAULT_DAILY_TIMES",
    "POST_ANGLES",
    "extract_youtube_caption_urls",
    "fetch_youtube_transcript",
    "fetch_youtube_rss_seeds",
    "fetch_bilibili_trending_seeds",
    "fetch_real_trending_seeds",
    "fetch_free_api_trending_seeds",
    "fetch_google_news_trending_seeds",
    "fetch_hacker_news_trending_seeds",
    "fetch_all_content_seeds",
    "fetch_all_video_seeds",
    "distill_seed",
    "infer_tags",
    "summarize_transcript",
    "x_weighted_length",
    "score_content_seed",
    "choose_seed",
    "choose_seeds",
    "compose_x_post",
    "compose_xhs_note",
    "build_next_draft",
    "build_daily_drafts",
    "build_xhs_review_drafts",
    "get_or_build_next_ready_draft",
    "mark_published",
    "mark_failed",
    "parse_daily_times",
    "next_morning_at",
    "next_scheduled_at",
    "write_launchd_plist",
]
