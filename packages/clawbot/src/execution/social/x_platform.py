"""
Social — X (Twitter) 集成层 v2.0

v2.0 变更 (2026-03-23):
  - 搬运 tweepy (10.6k⭐, MIT) — X/Twitter 官方 Python SDK
  - 新增 API 直连路径: Bearer Token → tweepy.Client
  - 发推文 / 获取动态 不再依赖 browser worker
  - 三级降级: tweepy API → Jina Reader → browser worker

支持:
- 发布推文 (API 或 browser worker)
- 获取用户动态 (API 或 Jina reader)
- 监控 X 动态
- 推文分析和转发策略
"""
import logging
import os
import hashlib
from typing import Dict, List

logger = logging.getLogger(__name__)

# ── tweepy (10.6k⭐) — X/Twitter 官方 SDK ──────────────────
_HAS_TWEEPY = False
_tweepy_client = None
try:
    import tweepy
    _bearer = os.getenv("X_BEARER_TOKEN", "").strip()
    if _bearer:
        _tweepy_client = tweepy.Client(bearer_token=_bearer)
        _HAS_TWEEPY = True
        logger.info("[X] tweepy 已加载 (Bearer Token)")
    else:
        # OAuth 1.0a (完全写权限)
        _ck = os.getenv("X_CONSUMER_KEY", "").strip()
        _cs = os.getenv("X_CONSUMER_SECRET", "").strip()
        _at = os.getenv("X_ACCESS_TOKEN", "").strip()
        _ats = os.getenv("X_ACCESS_TOKEN_SECRET", "").strip()
        if all([_ck, _cs, _at, _ats]):
            _tweepy_client = tweepy.Client(
                consumer_key=_ck, consumer_secret=_cs,
                access_token=_at, access_token_secret=_ats,
            )
            _HAS_TWEEPY = True
            logger.info("[X] tweepy 已加载 (OAuth 1.0a)")
        else:
            logger.info("[X] X API 凭证未设置，降级到 Jina/browser")
except ImportError:
    logger.info("[X] tweepy 未安装 (pip install tweepy)")

try:
    from src.utils import emit_flow_event as _emit_flow
except Exception:
    def _emit_flow(src, tgt, status, msg, data=None):  # type: ignore[misc]
        pass


async def fetch_x_profile_posts(
    handle: str,
    count: int = 8,
    worker_fn=None,
) -> List[Dict]:
    """获取 X 用户最近的公开动态

    v2.0 三级降级:
      1. tweepy API (Bearer Token, 最快最可靠)
      2. Jina reader (免费, 无需登录)
      3. browser worker (需要登录态)
    """
    handle = str(handle or "").strip().lstrip("@")
    if not handle:
        return []

    # 方式0: tweepy API (v2.0 新增)
    if _HAS_TWEEPY and _tweepy_client:
        items = await _fetch_via_tweepy(handle, count)
        if items:
            return items

    # 方式1: Jina reader (免费)
    items = await _fetch_via_jina(handle, count)
    if items:
        return items

    # 方式2: browser worker
    if worker_fn:
        try:
            result = worker_fn("research", {
                "query": f"from:@{handle}",
                "platform": "x",
                "count": count,
            })
            return result.get("items", []) if isinstance(result, dict) else []
        except Exception as e:
            logger.debug(f"[X.fetch] worker fallback failed: {e}")

    return []


async def _fetch_via_jina(handle: str, count: int) -> List[Dict]:
    """通过 Jina reader 抓取 X 动态"""
    import httpx
    url = f"https://r.jina.ai/https://x.com/{handle}"
    headers = {"Accept": "text/plain"}
    jina_key = os.getenv("JINA_API_KEY", "")
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return []
            text = resp.text
            return _parse_jina_x_output(text, handle, count)
    except Exception as e:
        logger.debug(f"[X.jina] {handle} failed: {e}")
        return []


def _parse_jina_x_output(text: str, handle: str, count: int) -> List[Dict]:
    """解析 Jina reader 返回的 X 页面文本"""
    items = []
    lines = text.strip().splitlines()
    current_text = []

    for line in lines:
        line = line.strip()
        if not line:
            if current_text:
                content = " ".join(current_text)
                if len(content) > 20:
                    items.append({
                        "title": content[:200],
                        "source": f"@{handle}",
                        "url": f"https://x.com/{handle}",
                        "digest_key": hashlib.md5(content[:100].encode()).hexdigest(),
                    })
                current_text = []
            continue
        current_text.append(line)

    if current_text:
        content = " ".join(current_text)
        if len(content) > 20:
            items.append({
                "title": content[:200],
                "source": f"@{handle}",
                "url": f"https://x.com/{handle}",
            })

    return items[:count]


async def publish_x_post(
    content: str,
    worker_fn=None,
    image_path: str = None,
) -> Dict:
    """发布推文"""
    if not content:
        return {"success": False, "error": "内容不能为空"}
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置"}
    try:
        payload = {"text": content}
        if image_path:
            payload["image"] = image_path
        _emit_flow("llm", "browser", "running", "启动浏览器发布 X 推文", {"length": len(content)})
        result = worker_fn("publish_x", payload)
        _emit_flow("browser", "social", "success", "X 推文发布完成", {"platform": "x"})
        return {"success": True, "result": result}
    except Exception as e:
        _emit_flow("browser", "social", "error", f"X 发布失败: {e}", {"platform": "x"})
        logger.error(f"[X.publish] failed: {e}")
        return {"success": False, "error": str(e)}


async def reply_to_x_post(
    tweet_url: str,
    reply_text: str,
    worker_fn=None,
) -> Dict:
    """回复推文"""
    if not tweet_url or not reply_text:
        return {"success": False, "error": "URL 和回复内容不能为空"}
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置"}
    try:
        _emit_flow("llm", "browser", "running", "启动浏览器回复 X 推文", {"url": tweet_url[:60]})
        result = worker_fn("reply_x", {
            "url": tweet_url,
            "text": reply_text,
        })
        _emit_flow("browser", "social", "success", "X 回复发布完成", {"platform": "x"})
        return {"success": True, "result": result}
    except Exception as e:
        _emit_flow("browser", "social", "error", f"X 回复失败: {e}", {"platform": "x"})
        logger.error(f"[X.reply] failed: {e}")
        return {"success": False, "error": str(e)}


# ── X 平台工具函数 (从 execution_hub.py 迁移) ───────────────

def normalize_x_source(source: str = "") -> str:
    """标准化 X 来源为完整 URL"""
    import re
    text = str(source or "").strip()
    if not text:
        return "https://x.com/IndieDevHailey"
    if text.startswith("@"):
        return f"https://x.com/{text[1:]}"
    if re.fullmatch(r"[A-Za-z0-9_]{1,20}", text):
        return f"https://x.com/{text}"
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return text


def normalize_x_handle(source: str = "") -> str:
    """标准化 X 用户名 (从 URL 提取 handle)"""
    from urllib.parse import urlparse
    url = normalize_x_source(source)
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    # 取第一段路径作为 handle
    return path.split("/")[0] if path else ""


def extract_x_handle_candidates_from_markdown(
    markdown: str,
    limit: int = 10,
) -> List[str]:
    """从 markdown 文本中提取 X 用户名候选

    支持两种模式:
    1. @handle 或 x.com/handle 格式
    2. 行尾的英文用户名 (如编号列表 "1. 描述。WaytoAGI")
    """
    import re
    handles: List[str] = []
    seen: set = set()
    skip_words = {
        "the", "and", "for", "not", "are", "was", "has",
        "seo", "saas", "i", "x", "twitter", "home", "search", "explore",
    }

    for line in markdown.split("\n"):
        line = line.strip()
        if not line:
            continue

        # 模式1: @handle 或 x.com/handle
        for pattern in [
            re.compile(r"@([A-Za-z0-9_]{1,20})"),
            re.compile(r"x\.com/([A-Za-z0-9_]{1,20})"),
            re.compile(r"twitter\.com/([A-Za-z0-9_]{1,20})"),
        ]:
            for match in pattern.finditer(line):
                candidate = match.group(1)
                if candidate.lower() not in skip_words and candidate.lower() not in seen:
                    seen.add(candidate.lower())
                    handles.append(candidate)
                    if len(handles) >= limit:
                        return handles

        # 模式2: 行尾英文用户名 (编号列表模式)
        m = re.search(r"[。．.]?\s*([A-Za-z][A-Za-z0-9_]{1,19})\s*$", line)
        if m:
            candidate = m.group(1)
            if candidate.lower() not in skip_words and candidate.lower() not in seen:
                seen.add(candidate.lower())
                handles.append(candidate)
                if len(handles) >= limit:
                    return handles

    return handles[:limit]


def extract_x_profile_posts_from_markdown(
    handle: str = "",
    markdown: str = "",
    limit: int = 5,
) -> List[Dict]:
    """从 Jina reader markdown 中提取 X 推文帖子列表"""
    import re
    posts: List[Dict] = []
    status_pattern = re.compile(
        r"https://x\.com/" + re.escape(handle) + r"/status/(\d+)"
    )
    blocks = re.split(r"\n\n+", markdown)
    current_id = ""
    current_text = ""

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m = status_pattern.search(block)
        if m:
            if current_id and current_text:
                posts.append({
                    "digest_key": current_id,
                    "url": f"https://x.com/{handle}/status/{current_id}",
                    "title": current_text.strip()[:120],
                    "source": f"X @{handle}",
                })
                if len(posts) >= limit:
                    return posts
            current_id = m.group(1)
            current_text = ""
        elif current_id:
            # Skip analytics links and date-only lines
            if re.match(r"^\[?\d+[KMB]?\]?\(?https://", block):
                continue
            if re.match(r"^\[.*\]\(https://x\.com/", block):
                continue
            if block and not block.startswith("[") and not block.startswith("http"):
                current_text += block + " "

    if current_id and current_text:
        posts.append({
            "digest_key": current_id,
            "url": f"https://x.com/{handle}/status/{current_id}",
            "title": current_text.strip()[:120],
            "source": f"X @{handle}",
        })
    return posts[:limit]


async def fetch_x_reader_payload(
    source: str = "",
    worker_fn=None,
) -> Dict:
    """通过 worker 获取 X 内容"""
    url = normalize_x_source(source)
    if not worker_fn:
        return {"success": False, "error": "worker_fn not provided"}
    try:
        result = worker_fn("x_read", {"url": url})
        return result if isinstance(result, dict) else {"success": False, "error": "invalid result"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── X 监控简报 (从 execution_hub.py 迁移) ───────────────────

async def generate_x_monitor_brief(
    monitors: List[Dict] = None,
    fetch_posts_fn=None,
) -> str:
    """生成 X 监控简报"""
    try:
        from src.notify_style import format_announcement
    except ImportError:
        def format_announcement(**kwargs):
            title = kwargs.get("title", "")
            sections = kwargs.get("sections", [])
            lines = [title]
            for section_title, entries in sections:
                lines.append(f"\n{section_title}")
                lines.extend(f"  {e}" for e in entries)
            return "\n".join(lines)

    monitors = monitors or []
    sections = []
    for monitor in monitors:
        keyword = monitor.get("keyword", "")
        source = monitor.get("source", "news")
        if source != "x_profile":
            continue

        posts = []
        if fetch_posts_fn:
            posts = await fetch_posts_fn(keyword, count=1)
        if not posts:
            continue

        entries = []
        for post in posts[:2]:
            title = post.get("title", "")
            url = post.get("url", "")
            entries.append(title)
            if url:
                entries.append(f"详情：{url}")
        sections.append((f"【@{keyword}】", entries))

    return format_announcement(
        title="OpenClaw「X 资讯快讯」",
        intro="检测到关注账号有新的公开动态。",
        sections=sections,
        footer="如需继续追踪，可保留当前监控项。",
    )


# ── 推文执行分析 (从 execution_hub.py 迁移) ──────────────────

def derive_tweet_execution_strategy(text: str = "") -> Dict:
    """根据推文内容推导执行策略"""
    content = str(text or "").strip().lower()
    urgency = 5
    action = "repost"
    platform = "x"
    content_type = "commentary"
    reasoning = "默认转评策略"

    if any(kw in content for kw in ["breaking", "突发", "urgent", "紧急"]):
        urgency = 9
        action = "quote_retweet"
        reasoning = "突发/紧急内容，建议快速引用转发"
    elif any(kw in content for kw in ["tutorial", "教程", "how to", "怎么", "如何"]):
        urgency = 4
        action = "thread"
        content_type = "tutorial"
        reasoning = "教程类内容，适合展开为长线程"
    elif any(kw in content for kw in ["opinion", "观点", "hot take", "看法"]):
        urgency = 6
        action = "quote_retweet"
        content_type = "opinion"
        reasoning = "观点类内容，适合引用并补充观点"

    return {
        "action": action,
        "platform": platform,
        "content_type": content_type,
        "urgency": urgency,
        "reasoning": reasoning,
    }


async def analyze_tweet_execution(
    source: str = "",
    worker_fn=None,
) -> Dict:
    """分析推文并推导执行策略"""
    payload = await fetch_x_reader_payload(source, worker_fn=worker_fn)
    if not payload.get("success"):
        return {"success": False, "error": payload.get("error", "无法获取推文内容")}

    text = payload.get("markdown", "") or payload.get("stdout", "")
    strategy = derive_tweet_execution_strategy(text)
    return {
        "success": True,
        "source": source,
        "text_preview": text[:300],
        "strategy": strategy,
    }


async def run_tweet_execution(
    source: str = "",
    worker_fn=None,
    ai_call_fn=None,
    save_draft_fn=None,
) -> Dict:
    """执行推文发布流程: 分析 → AI 生成 → 保存草稿"""
    analysis = await analyze_tweet_execution(source, worker_fn=worker_fn)
    if not analysis.get("success"):
        return analysis

    strategy = analysis.get("strategy", {})
    text_preview = analysis.get("text_preview", "")

    generated = ""
    if ai_call_fn:
        prompt = (
            f"根据以下推文内容，生成一条适合发布的社媒内容（中文，不超过200字）。\n"
            f"策略：{strategy.get('action', '')}，类型：{strategy.get('content_type', '')}\n"
            f"原文摘要：{text_preview[:500]}"
        )
        ai_result = await ai_call_fn(prompt)
        generated = ai_result.get("raw", "") if ai_result.get("success") else ""

    draft = {}
    if save_draft_fn:
        draft = save_draft_fn("x", "", generated or text_preview[:200], topic=source)

    return {
        "success": True,
        "source": source,
        "strategy": strategy,
        "generated_content": generated,
        "draft": draft,
    }


async def import_x_monitors_from_tweet(
    source: str = "",
    limit: int = 10,
    worker_fn=None,
    add_monitor_fn=None,
) -> List[Dict]:
    """从推文中提取并导入 X 监控账号"""
    payload = await fetch_x_reader_payload(source, worker_fn=worker_fn)
    markdown = ""
    if payload and payload.get("success"):
        markdown = payload.get("markdown", "") or payload.get("stdout", "")

    handles = extract_x_handle_candidates_from_markdown(markdown, limit=limit)
    added = []
    if add_monitor_fn:
        for handle in handles:
            result = add_monitor_fn(keyword=handle, source="x_profile")
            if result and result.get("success"):
                added.append(result)
    return added
