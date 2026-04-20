"""
Social — X (Twitter) 集成层 v3.0

v3.0 变更 (2026-04-20):
  - 新增 twikit (Cookie 持久化登录) — 无需 API Key，用用户名密码登录
  - Cookie 自动保存到 ~/.openclaw/x_cookies.json，下次启动免登录
  - 四级降级: twikit Cookie → tweepy API → Jina Reader → browser worker
  - 新增 twikit_login / twikit_is_authenticated / twikit_post_tweet 函数

v2.0 变更 (2026-03-23):
  - 搬运 tweepy (10.6k⭐, MIT) — X/Twitter 官方 Python SDK
  - 新增 API 直连路径: Bearer Token → tweepy.Client
  - 三级降级: tweepy API → Jina Reader → browser worker

支持:
- 发布推文 (twikit Cookie / tweepy API / browser worker)
- 获取用户动态 (twikit / tweepy API / Jina reader)
- Cookie 持久化登录（首次登录后免密码）
- 监控 X 动态
- 推文分析和转发策略
"""
import asyncio
import logging
import os
import hashlib
from pathlib import Path
from typing import Dict, List, Optional

from src.http_client import ResilientHTTPClient

logger = logging.getLogger(__name__)

# 模块级别 HTTP 客户端（自动重试 + 熔断）
_http = ResilientHTTPClient(timeout=20.0, name="x_platform")

# ── Cookie 存储路径 ──────────────────────────────────────────
_OPENCLAW_DIR = Path.home() / ".openclaw"
X_COOKIES_PATH = _OPENCLAW_DIR / "x_cookies.json"


# ── twikit — Cookie 持久化登录（无需 API Key）────────────────
_HAS_TWIKIT = False
_twikit_client = None

def _init_twikit() -> bool:
    """初始化 twikit 客户端，优先从本地 Cookie 文件加载"""
    global _HAS_TWIKIT, _twikit_client
    if _twikit_client is not None:
        return _HAS_TWIKIT
    try:
        from twikit import Client as TwikitClient
        _twikit_client = TwikitClient("zh-CN")
        if X_COOKIES_PATH.exists():
            try:
                _twikit_client.load_cookies(str(X_COOKIES_PATH))
                _HAS_TWIKIT = True
                logger.info("[X] twikit 已加载 (Cookie 持久化: %s)", X_COOKIES_PATH)
            except Exception as e:
                logger.warning("[X] twikit Cookie 加载失败，需要重新登录: %s", e)
                _HAS_TWIKIT = False
        else:
            logger.info("[X] twikit 已就绪，但无 Cookie 文件 — 需要调用 twikit_login() 登录")
            _HAS_TWIKIT = False
        return _HAS_TWIKIT
    except ImportError:
        logger.info("[X] twikit 未安装 (pip install twikit)")
        _twikit_client = None
        return False

# 模块加载时尝试初始化 twikit
_init_twikit()


async def twikit_login(
    username: str,
    email: str,
    password: str,
    totp_secret: Optional[str] = None,
) -> Dict:
    """使用用户名/邮箱/密码登录 X，Cookie 自动保存到本地文件

    首次登录后，后续启动会自动加载 Cookie，无需再次输入密码。
    """
    global _HAS_TWIKIT, _twikit_client
    try:
        from twikit import Client as TwikitClient
    except ImportError:
        return {"success": False, "error": "twikit 未安装 (pip install twikit)"}

    if _twikit_client is None:
        _twikit_client = TwikitClient("zh-CN")

    try:
        # 确保存储目录存在
        _OPENCLAW_DIR.mkdir(parents=True, exist_ok=True)

        # 构建登录参数
        login_kwargs = {
            "auth_info_1": username,
            "auth_info_2": email,
            "password": password,
        }
        if totp_secret:
            login_kwargs["totp_secret"] = totp_secret

        await _twikit_client.login(**login_kwargs)

        # 登录成功 — 保存 Cookie 到本地
        _twikit_client.save_cookies(str(X_COOKIES_PATH))
        _HAS_TWIKIT = True
        logger.info("[X] twikit 登录成功，Cookie 已保存到 %s", X_COOKIES_PATH)

        return {
            "success": True,
            "message": f"X 登录成功，Cookie 已保存到 {X_COOKIES_PATH}",
            "cookies_path": str(X_COOKIES_PATH),
        }
    except Exception as e:
        logger.error("[X] twikit 登录失败: %s", e)
        return {"success": False, "error": f"X 登录失败: {e}"}


def twikit_is_authenticated() -> bool:
    """检查 twikit 是否已认证（Cookie 文件存在且可加载）"""
    if _HAS_TWIKIT:
        return True
    # 尝试重新初始化（可能 Cookie 文件刚创建）
    return _init_twikit()


async def twikit_post_tweet(
    text: str,
    media_paths: Optional[List[str]] = None,
) -> Dict:
    """通过 twikit 发布推文（Cookie 认证，无需 API Key）

    如果 Cookie 过期会捕获异常并返回明确错误，不会崩溃。
    """
    global _HAS_TWIKIT
    if not _HAS_TWIKIT or _twikit_client is None:
        return {"success": False, "error": "twikit 未认证，请先调用 twikit_login()"}

    try:
        # 上传媒体（如果有）
        media_ids = []
        if media_paths:
            for path in media_paths:
                if Path(path).exists():
                    try:
                        media_id = await _twikit_client.upload_media(path)
                        media_ids.append(media_id)
                    except Exception as e:
                        logger.warning("[X] twikit 媒体上传失败 (%s): %s", path, e)

        # 发布推文
        tweet = await _twikit_client.create_tweet(
            text=text,
            media_ids=media_ids if media_ids else None,
        )
        logger.info("[X] twikit 发推成功: %s", tweet.id if hasattr(tweet, "id") else "OK")
        return {
            "success": True,
            "tweet_id": str(tweet.id) if hasattr(tweet, "id") else "",
            "method": "twikit",
        }
    except Exception as e:
        error_msg = str(e).lower()
        # 检测常见的 Cookie 过期/认证失败错误
        if any(kw in error_msg for kw in ["unauthorized", "403", "401", "cookie", "login", "auth"]):
            _HAS_TWIKIT = False
            logger.warning("[X] twikit Cookie 可能已过期，需要重新登录: %s", e)
            return {
                "success": False,
                "error": f"X Cookie 已过期，请重新登录: {e}",
                "needs_relogin": True,
            }
        logger.error("[X] twikit 发推失败: %s", e)
        return {"success": False, "error": f"twikit 发推失败: {e}"}


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
            logger.info("[X] X API 凭证未设置，降级到 twikit/Jina/browser")
except ImportError:
    logger.info("[X] tweepy 未安装 (pip install tweepy)")

from src.utils import emit_flow_event as _emit_flow


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

    # 方式0: twikit Cookie (v3.0 新增 — 无需 API Key)
    if _HAS_TWIKIT and _twikit_client:
        items = await _fetch_via_twikit(handle, count)
        if items:
            return items

    # 方式1: tweepy API (v2.0 新增)
    if _HAS_TWEEPY and _tweepy_client:
        items = await _fetch_via_tweepy(handle, count)
        if items:
            return items

    # 方式2: Jina reader (免费)
    items = await _fetch_via_jina(handle, count)
    if items:
        return items

    # 方式3: browser worker
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


async def _fetch_via_twikit(handle: str, count: int) -> List[Dict]:
    """通过 twikit Cookie 获取用户最近推文（无需 API Key）"""
    try:
        user = await _twikit_client.get_user_by_screen_name(handle)
        if not user:
            logger.debug("[X.twikit] 找不到用户 @%s", handle)
            return []

        tweets = await user.get_tweets("Tweets", count=min(count, 20))
        if not tweets:
            return []

        items = []
        for tweet in list(tweets)[:count]:
            items.append({
                "title": str(tweet.text)[:200],
                "source": f"@{handle}",
                "url": f"https://x.com/{handle}/status/{tweet.id}",
                "digest_key": str(tweet.id),
            })
        return items
    except Exception as e:
        logger.debug("[X.twikit] @%s 获取失败: %s", handle, e)
        return []


async def _fetch_via_tweepy(handle: str, count: int) -> List[Dict]:
    """通过 tweepy API v2 获取用户最近推文 (Bearer Token 认证)"""
    try:
        # 先获取用户 ID
        user_resp = _tweepy_client.get_user(username=handle)
        if not user_resp or not user_resp.data:
            logger.debug("[X.tweepy] 找不到用户 @%s", handle)
            return []

        user_id = user_resp.data.id
        # 获取最近推文
        tweets_resp = _tweepy_client.get_users_tweets(
            user_id,
            max_results=min(count, 100),
            tweet_fields=["created_at", "text"],
        )
        if not tweets_resp or not tweets_resp.data:
            return []

        items = []
        for tweet in tweets_resp.data[:count]:
            items.append({
                "title": str(tweet.text)[:200],
                "source": f"@{handle}",
                "url": f"https://x.com/{handle}/status/{tweet.id}",
                "digest_key": str(tweet.id),
            })
        return items
    except Exception as e:
        logger.debug("[X.tweepy] @%s 获取失败: %s", handle, e)
        return []


async def _fetch_via_jina(handle: str, count: int) -> List[Dict]:
    """通过 Jina reader 抓取 X 动态"""
    url = f"https://r.jina.ai/https://x.com/{handle}"
    headers = {"Accept": "text/plain"}
    jina_key = os.getenv("JINA_API_KEY", "")
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"
    try:
        resp = await _http.get(url, headers=headers)
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
    """发布推文

    v3.0 三级降级: twikit Cookie → tweepy API → browser worker
    """
    if not content:
        return {"success": False, "error": "内容不能为空"}

    # 方式0: twikit Cookie 发布（v3.0 新增）
    if _HAS_TWIKIT and _twikit_client:
        media_paths = [image_path] if image_path else None
        result = await twikit_post_tweet(content, media_paths=media_paths)
        if result.get("success"):
            _emit_flow("twikit", "social", "success", "X 推文发布完成 (twikit)", {"platform": "x"})
            return result
        # Cookie 过期则降级到下一种方式
        logger.info("[X] twikit 发布失败，尝试降级: %s", result.get("error"))

    # 方式1: browser worker (现有逻辑)
    if not worker_fn:
        return {"success": False, "error": "browser worker 未配置，且 twikit 未认证"}
    try:
        payload = {"text": content}
        if image_path:
            payload["image"] = image_path
        _emit_flow("llm", "browser", "running", "启动浏览器发布 X 推文", {"length": len(content)})
        # 浏览器自动化是同步阻塞操作（5-30秒），必须丢到线程池避免冻结事件循环
        result = await asyncio.to_thread(worker_fn, "publish_x", payload)
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
        # 浏览器自动化是同步阻塞操作，必须丢到线程池
        reply_payload = {
            "url": tweet_url,
            "text": reply_text,
        }
        result = await asyncio.to_thread(worker_fn, "reply_x", reply_payload)
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
        # 浏览器自动化是同步阻塞操作，必须丢到线程池
        result = await asyncio.to_thread(worker_fn, "x_read", {"url": url})
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
