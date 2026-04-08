#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Topic research + social publishing worker using a dedicated browser."""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

try:
    import browser_cookie3
except Exception:  # pragma: no cover
    browser_cookie3 = None

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
LEGACY_COOKIE_FILE = Path(
    os.getenv(
        "OPENCLAW_SOCIAL_LEGACY_COOKIE_FILE",
        "/Users/blackdj/Library/Application Support/Google/Chrome/Profile 1/Cookies",
    )
)
SOCIAL_BROWSER_DIR = Path(
    os.getenv(
        "OPENCLAW_SOCIAL_BROWSER_DIR",
        str(ROOT / "clawbot" / "data" / "browser_profiles" / "openclaw_social"),
    )
)
SOCIAL_BROWSER_PORT = int(os.getenv("OPENCLAW_SOCIAL_BROWSER_PORT", "19222"))
SOCIAL_BROWSER_CDP_URL = f"http://127.0.0.1:{SOCIAL_BROWSER_PORT}"
def _detect_font_path() -> str:
    """自动检测系统中可用的中文字体路径（支持 macOS 和 Linux）"""
    import platform
    candidates = []
    if platform.system() == "Darwin":
        candidates = [
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
    else:
        # Linux 常见中文字体路径
        candidates = [
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    # 均未找到时返回空字符串，PIL 会使用默认字体
    return ""

FONT_PATH = os.getenv("OPENCLAW_FONT_PATH", "") or _detect_font_path()
CHROME_CANDIDATES = [
    os.getenv("OPENCLAW_SOCIAL_CHROME_BIN", "").strip(),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
X_HOME_URL = "https://x.com/home"
X_TREND_URL = "https://x.com/explore/tabs/trending"
X_COMPOSE_URL = "https://x.com/compose/post"
X_NOTIFICATIONS_URL = "https://x.com/notifications"
X_MESSAGES_URL = "https://x.com/messages"
X_PROFILE_URL = os.getenv("OPENCLAW_SOCIAL_X_PROFILE_URL", "https://x.com/BonoDJblack")
XHS_HOME_URL = "https://creator.xiaohongshu.com/new/home"
XHS_PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"
XHS_EXPLORE_URL = "https://www.xiaohongshu.com/explore"
XHS_PROFILE_URL = os.getenv("OPENCLAW_SOCIAL_XHS_PROFILE_URL", "https://www.xiaohongshu.com/user/profile/694ec098000000003702a276")
XHS_NOTIFICATIONS_URL = "https://www.xiaohongshu.com/notification"
XHS_IM_URL = "https://www.xiaohongshu.com/im"
DEFAULT_START_URLS = [
    X_HOME_URL,
    X_TREND_URL,
    X_COMPOSE_URL,
    XHS_PUBLISH_URL,
    XHS_HOME_URL,
    "https://www.upwork.com/ab/proposals/offers",
    "https://www.upwork.com/nx/find-work/best-matches",
    "https://www.upwork.com/nx/payments/134843060/disbursement-methods",
]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def short(value: Any, max_len: int = 120) -> str:
    text = clean_text(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def slugify(text: str) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text.strip()).strip("-")
    return text[:48] or "topic"


def topic_match_score(topic: str, text: str) -> int:
    lower = clean_text(text).lower()
    score = 0
    topic_lower = clean_text(topic).lower()
    if topic_lower and topic_lower in lower:
        score += 4
    if "ai" in topic_lower and "ai" in lower:
        score += 2
    chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,}", topic)
    for term in chinese_terms:
        if term in text:
            score += 3
    if chinese_terms and re.search(r"[\u3040-\u30ff]", text):
        score -= 4
    if "出海" in topic and "出海" in text:
        score += 3
    if any(token in text for token in ["跨境", "海外", "global", "saas", "独立开发", "增长", "海外市场", "产品"]):
        score += 1
    if "出海" in topic and not any(token in text for token in ["出海", "跨境", "海外", "global"]):
        score -= 2
    return score


def load_cookies(*domains: str) -> List[Dict[str, Any]]:
    if browser_cookie3 is None or not LEGACY_COOKIE_FILE.exists():
        return []
    cookies: List[Dict[str, Any]] = []
    for domain in domains:
        try:
            jar = browser_cookie3.chrome(cookie_file=str(LEGACY_COOKIE_FILE), domain_name=domain)
        except Exception:
            continue
        for c in jar:
            rest = {k.lower(): v for k, v in c._rest.items()}
            same_site = "Lax"
            raw = str(rest.get("samesite", "")).lower()
            if "strict" in raw:
                same_site = "Strict"
            elif "none" in raw:
                same_site = "None"
            cookies.append(
                {
                    "name": str(c.name),
                    "value": str(c.value),
                    "domain": str(c.domain),
                    "path": str(c.path),
                    "expires": float(c.expires) if c.expires and c.expires > 0 else -1,
                    "httpOnly": bool("httponly" in rest),
                    "secure": bool(c.secure),
                    "sameSite": same_site,
                }
            )
    return cookies


def chrome_bin() -> str:
    for candidate in CHROME_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("Chrome executable not found for OpenClaw social browser")


def cdp_request(path: str, method: str = "GET", timeout: int = 5) -> Any:
    req = urllib.request.Request(f"{SOCIAL_BROWSER_CDP_URL}{path}", method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    if not body:
        return {}
    try:
        return json.loads(body)
    except Exception:
        return body


def browser_running(timeout: int = 2) -> bool:
    try:
        payload = cdp_request("/json/version", timeout=timeout)
        return bool((payload or {}).get("Browser"))
    except Exception:
        return False


def wait_for_browser(timeout: int = 20) -> bool:
    deadline = time.time() + max(1, int(timeout))
    while time.time() < deadline:
        if browser_running(timeout=2):
            return True
        time.sleep(0.4)
    return False


def start_social_browser() -> Dict[str, Any]:
    SOCIAL_BROWSER_DIR.mkdir(parents=True, exist_ok=True)
    if browser_running(timeout=2):
        return {"success": True, "started": False, "browser_running": True}
    subprocess.Popen(
        [
            chrome_bin(),
            f"--user-data-dir={SOCIAL_BROWSER_DIR}",
            f"--remote-debugging-port={SOCIAL_BROWSER_PORT}",
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=DialMediaRouteProvider",
            "--disable-gpu",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not wait_for_browser(timeout=20):
        raise RuntimeError("OpenClaw social browser failed to start")
    return {"success": True, "started": True, "browser_running": True}


def normalized_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return str(url or "").strip()
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


def list_browser_tabs() -> List[Dict[str, str]]:
    try:
        payload = cdp_request("/json/list", timeout=4) or []
    except Exception:
        return []
    tabs: List[Dict[str, str]] = []
    for item in payload:
        if str(item.get("type", "") or "") != "page":
            continue
        url = str(item.get("url", "") or "").strip()
        if not url or url.startswith("devtools://"):
            continue
        tabs.append(
            {
                "id": str(item.get("id", "") or "").strip(),
                "title": str(item.get("title", "") or "").strip(),
                "url": url,
            }
        )
    return tabs


def target_urls_for(platforms: Iterable[str] | None = None) -> List[str]:
    names = {str(item or "").strip().lower() for item in (platforms or []) if str(item or "").strip()}
    if not names:
        return list(DEFAULT_START_URLS)
    urls: List[str] = []
    if "x" in names:
        urls.extend([X_HOME_URL, X_TREND_URL, X_COMPOSE_URL])
    if "xiaohongshu" in names or "xhs" in names:
        urls.extend([XHS_HOME_URL, XHS_PUBLISH_URL, XHS_EXPLORE_URL])
    return urls


def cookie_status(cookies: List[Dict[str, Any]]) -> Tuple[bool, bool]:
    x_ready = any(
        str(cookie.get("name", "")) == "auth_token" and "x.com" in str(cookie.get("domain", ""))
        for cookie in cookies
    )
    xhs_ready = any(
        str(cookie.get("name", "")) in {"a1", "web_session", "webId"}
        and "xiaohongshu" in str(cookie.get("domain", ""))
        for cookie in cookies
    )
    return x_ready, xhs_ready


def dedupe_cookies(cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for cookie in cookies:
        key = (
            str(cookie.get("name", "")),
            str(cookie.get("domain", "")),
            str(cookie.get("path", "/")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cookie)
    return deduped


def current_cookie_snapshot(context) -> List[Dict[str, Any]]:
    return list(context.cookies([X_HOME_URL, XHS_HOME_URL, XHS_PUBLISH_URL]))


def seed_legacy_cookies(context, platforms: Iterable[str]) -> Dict[str, Any]:
    names = {str(item or "").strip().lower() for item in platforms if str(item or "").strip()}
    before = current_cookie_snapshot(context)
    x_ready, xhs_ready = cookie_status(before)
    needed: List[Dict[str, Any]] = []
    if "x" in names and not x_ready:
        needed.extend(load_cookies("x.com"))
    if {"xiaohongshu", "xhs"} & names and not xhs_ready:
        needed.extend(load_cookies("xiaohongshu.com", "creator.xiaohongshu.com"))
    if needed:
        context.add_cookies(dedupe_cookies(needed))
    after = current_cookie_snapshot(context)
    x_ready, xhs_ready = cookie_status(after)
    return {
        "seeded": bool(needed),
        "x_ready": x_ready,
        "xiaohongshu_ready": xhs_ready,
    }


def is_blank_page(page) -> bool:
    return normalized_url(page.url) in {"", "about:blank"}


def get_or_open_page(context, url: str):
    target = normalized_url(url)
    for page in context.pages:
        if normalized_url(page.url) == target:
            return page
    for page in context.pages:
        if is_blank_page(page):
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
            return page
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=120000)
    return page


def ensure_target_tabs(context, urls: Iterable[str]) -> None:
    for url in urls:
        if not str(url or "").strip():
            continue
        page = get_or_open_page(context, str(url))
        page.wait_for_timeout(600)


def inspect_browser_state(context) -> Dict[str, Any]:
    cookies = current_cookie_snapshot(context)
    x_ready, xhs_ready = cookie_status(cookies)
    tabs = list_browser_tabs()
    return {
        "success": True,
        "mode": "dedicated",
        "browser_running": True,
        "profile_dir": str(SOCIAL_BROWSER_DIR),
        "cdp_url": SOCIAL_BROWSER_CDP_URL,
        "tabs": len(tabs),
        "x_ready": x_ready,
        "xiaohongshu_ready": xhs_ready,
        "urls": [item.get("url", "") for item in tabs[:8]],
    }


@contextmanager
def social_browser(urls: Optional[List[str]] = None, seed_platforms: Optional[List[str]] = None) -> Iterator[Tuple[Any, Dict[str, Any]]]:
    start_social_browser()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(SOCIAL_BROWSER_CDP_URL, timeout=120000)
        if not browser.contexts:
            raise RuntimeError("OpenClaw social browser has no usable context")
        context = browser.contexts[0]
        seed = seed_legacy_cookies(context, seed_platforms or [])
        if urls:
            ensure_target_tabs(context, urls)
        yield context, seed


def body_preview(page, limit: int = 1200) -> str:
    try:
        content = page.locator("body").first.inner_text(timeout=3000)
    except Exception:
        return ""
    return clean_text(content)[:limit]


def body_lines(page, limit: int = 20) -> List[str]:
    try:
        content = page.locator("body").first.inner_text(timeout=3000)
    except Exception:
        return []
    lines: List[str] = []
    seen = set()
    skip_exact = {
        "创作中心", "业务合作", "发现", "发布", "我", "首页", "笔记管理", "数据看板", "活动中心", "笔记灵感",
        "创作学院", "创作百科", "收起侧边栏", "查看新帖子", "通知", "全部", "提及", "帖子", "回复", "亮点", "文章", "媒体",
        "喜欢", "当前趋势", "为你推荐", "新闻", "体育", "娱乐", "探索", "全球趋势", "最受欢迎的推文", "更多", "© 2014-2024",
        "行吟信息科技（上海）有限公司", "要查看键盘快捷键，按下问号", "查看键盘快捷键",
    }
    for raw in str(content or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if len(line) > 220:
            line = line[:217] + "..."
        lower = line.lower()
        if line in skip_exact or line.startswith("地址：") or line.startswith("电话：") or re.fullmatch(r"[0-9]+", line):
            continue
        if lower in seen:
            continue
        if any(token in lower for token in ["沪icp", "营业执照", "违法不良信息举报", "服务条款", "隐私政策", "cookie", "更多"]):
            continue
        seen.add(lower)
        lines.append(line)
        if len(lines) >= max(1, int(limit)):
            break
    return lines


def login_page_detected(page) -> bool:
    hay = f"{clean_text(page.title())} {body_preview(page, limit=800)}".lower()
    return any(token in hay for token in ["登录", "login", "sign in", "sign up"]) or "/i/flow/login" in page.url


def _stop_headless_browser() -> None:
    """停止 headless 浏览器进程"""
    try:
        subprocess.run(
            ["pkill", "-f", f"--remote-debugging-port={SOCIAL_BROWSER_PORT}"],
            timeout=5, capture_output=True,
        )
        time.sleep(2)
    except Exception:
        pass


def _start_visible_browser(urls: List[str]) -> subprocess.Popen:
    """启动可见（非 headless）浏览器供用户登录"""
    cmd = [
        chrome_bin(),
        f"--user-data-dir={SOCIAL_BROWSER_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=DialMediaRouteProvider",
    ]
    cmd.extend(urls)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _mac_login_alert(platform_name: str) -> None:
    """登录提醒 — 仅记日志，不弹任何 macOS 原生通知/对话框/声音"""
    # 所有 osascript 通知/弹窗/声音已移除 — 用户明确要求完全静默
    logger.info(f"[登录提醒] {platform_name} 需要登录，请在弹出的浏览器中完成登录")


def interactive_login(platforms: List[str], timeout: int = 300) -> Dict[str, Any]:
    """交互式登录：停止 headless 浏览器 → 弹出可见浏览器 → 用户登录 → 恢复 headless。

    当 X/小红书/Upwork 等平台 Cookie 过期时，自动弹出可见浏览器窗口并通知用户。
    检测到登录完成后自动关闭可见浏览器并恢复 headless 模式。

    Args:
        platforms: 需要登录的平台列表 ["x", "xiaohongshu", "upwork"]
        timeout: 最长等待时间（秒）

    Returns:
        {"success": bool, "platforms_logged_in": list}
    """
    # 准备登录 URL
    login_urls: List[str] = []
    platform_names: List[str] = []
    for p in platforms:
        p_lower = p.strip().lower()
        if p_lower == "x":
            login_urls.append("https://x.com/i/flow/login")
            platform_names.append("X (Twitter)")
        elif p_lower == "xiaohongshu":
            login_urls.append("https://www.xiaohongshu.com/explore")
            platform_names.append("小红书")
        elif p_lower == "upwork":
            login_urls.append("https://www.upwork.com/ab/account-security/login")
            platform_names.append("Upwork")
        else:
            login_urls.append(f"https://{p_lower}.com")
            platform_names.append(p_lower)

    name_str = " + ".join(platform_names)

    # 1. 停止 headless 浏览器（释放 profile 锁）
    _stop_headless_browser()

    # 2. 启动可见浏览器
    proc = _start_visible_browser(login_urls)

    # 3. macOS 桌面弹窗通知
    _mac_login_alert(name_str)
    print(f"[社交登录] 已弹出浏览器，等待 {name_str} 登录 (最多 {timeout}s)...")

    # 4. 等待用户登录完成
    # 通过定期检查浏览器 Cookie 文件的修改时间来检测登录
    cookie_file = SOCIAL_BROWSER_DIR / "Default" / "Cookies"
    initial_mtime = cookie_file.stat().st_mtime if cookie_file.exists() else 0
    logged_in = False
    start_time = time.time()

    while time.time() - start_time < timeout:
        time.sleep(5)
        # 检测 Cookie 文件是否被修改（表明有新的登录状态写入）
        if cookie_file.exists():
            current_mtime = cookie_file.stat().st_mtime
            if current_mtime > initial_mtime + 2:  # 至少变化 2 秒才算有效
                # 等待几秒确保所有 Cookie 写入完成
                time.sleep(5)
                logged_in = True
                break

        # 每 60 秒记录一次日志（不弹通知）
        elapsed = int(time.time() - start_time)
        if elapsed > 0 and elapsed % 60 == 0:
            logger.info(f"[社交登录] 已等待 {elapsed // 60} 分钟，请尽快登录")

    # 5. 关闭可见浏览器
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    # 6. 恢复 headless 浏览器
    time.sleep(2)
    try:
        start_social_browser()
    except Exception as e:
        print(f"[社交登录] 恢复 headless 浏览器失败: {e}")

    if logged_in:
        # 成功 — 仅记日志（不弹 macOS 通知）
        print(f"[社交登录] {name_str} 登录完成，headless 浏览器已恢复")
        return {"success": True, "platforms_logged_in": platform_names}
    else:
        print(f"[社交登录] 登录等待超时 ({timeout}s)")
        return {"success": False, "platforms_logged_in": []}


def search_bing_html(query: str) -> str:
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def extract_xhs_bing_results(topic: str, limit: int = 5) -> List[Dict[str, Any]]:
    html_text = search_bing_html(f"site:xiaohongshu.com {topic}")
    items: List[Dict[str, Any]] = []
    seen = set()
    pattern = re.compile(
        r'<li class="b_algo".*?<h2><a href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a></h2>.*?(?:<p>(?P<snippet>.*?)</p>)?',
        re.S,
    )
    for match in pattern.finditer(html_text):
        url = html.unescape(match.group("url") or "")
        if "xiaohongshu.com" not in url or url in seen:
            continue
        seen.add(url)
        title = clean_text(re.sub(r"<.*?>", " ", html.unescape(match.group("title") or "")))
        snippet = clean_text(re.sub(r"<.*?>", " ", html.unescape(match.group("snippet") or "")))
        score = topic_match_score(topic, f"{title} {snippet}")
        if score <= 0:
            continue
        items.append(
            {
                "platform": "xiaohongshu",
                "title": short(title, 96),
                "summary": short(snippet or title, 180),
                "url": url,
                "score": score,
            }
        )
    items.sort(key=lambda item: item.get("score", 0), reverse=True)
    return items[:limit]


def extract_xhs_site_results(context, topic: str, limit: int = 5) -> List[Dict[str, Any]]:
    page = context.new_page()
    page.goto(XHS_EXPLORE_URL, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(5000)
    page.evaluate(
        """(topic) => {
          const input = document.querySelector('input.search-input');
          if (!input) return false;
          input.focus();
          input.value = topic;
          input.dispatchEvent(new Event('input', {bubbles:true}));
          input.dispatchEvent(new Event('change', {bubbles:true}));
          return true;
        }""",
        topic,
    )
    page.wait_for_timeout(300)
    page.keyboard.press("Enter")
    page.wait_for_timeout(8000)
    payload = page.evaluate(
        """() => ({
          body: document.body.innerText || '',
          links: Array.from(document.querySelectorAll('a[href*="/explore/"]')).map(a => a.href)
        })"""
    )
    page.close()

    body = str(payload.get("body", "") or "")
    links = [str(x) for x in (payload.get("links", []) or []) if "/explore/" in str(x)]
    lines = [clean_text(x) for x in body.splitlines() if clean_text(x)]
    stop = {
        "创作中心", "业务合作", "发现", "发布", "通知", "我", "全部", "图文", "视频", "用户", "筛选", "综合", "相关搜索",
        "深圳", "杭州", "北京", "日本", "新加坡", "个人", "赚钱方法", "俄罗斯", "西语", "活动",
    }
    generic_suffixes = ("赛道", "公司", "营销", "兼职", "渠道", "榜单", "交流", "项目")
    candidates: List[Dict[str, Any]] = []
    seen_titles = set()
    for line in lines:
        if line in stop:
            continue
        if line.endswith("小时前") or line.endswith("天前") or re.fullmatch(r"\d{4}-\d{2}-\d{2}", line):
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if any(token in line for token in ["沪ICP备", "营业执照", "个性化推荐算法", "Carven’s Account"]):
            continue
        if "别再泛泛聊趋势" in line:
            continue
        if clean_text(topic).lower() in line.lower() and len(line) <= 8 and line.endswith(generic_suffixes):
            continue
        score = topic_match_score(topic, line)
        if score <= 0:
            continue
        title = short(line, 96)
        if title in seen_titles:
            continue
        seen_titles.add(title)
        candidates.append({"title": title, "score": score})
    items: List[Dict[str, Any]] = []
    for idx, candidate in enumerate(candidates[: max(limit * 2, 6)]):
        if idx >= len(links):
            break
        items.append(
            {
                "platform": "xiaohongshu",
                "title": candidate["title"],
                "summary": candidate["title"],
                "url": links[idx],
                "score": int(candidate["score"]),
            }
        )
    items.sort(key=lambda item: item.get("score", 0), reverse=True)
    return items[:limit]


def extract_x_items(page, topic: str, limit: int = 5) -> List[Dict[str, Any]]:
    query = topic
    if "AI" in topic or "ai" in topic:
        query = f'"{topic}" OR (AI 出海) OR (出海 AI) OR (AI SaaS 出海)'
    search_url = "https://x.com/search?q=" + urllib.parse.quote(query) + "&src=typed_query&f=live"
    page.goto(search_url, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(8000)
    raw = page.evaluate(
        """() => Array.from(document.querySelectorAll('article')).slice(0, 12).map(a => ({
            text: (a.innerText || '').slice(0, 900),
            links: Array.from(a.querySelectorAll('a[href*="/status/"]')).map(x => x.href)
        }))"""
    )
    items = []
    seen = set()
    for row in raw:
        text = clean_text(row.get("text", ""))
        if not text:
            continue
        link = next((x for x in row.get("links", []) if "/status/" in x), "")
        if not link or link in seen:
            continue
        if "/BonoDJblack/" in link:
            continue
        seen.add(link)
        lines = [clean_text(x) for x in str(row.get("text", "")).splitlines() if clean_text(x)]
        if any(token in text for token in ["广告", "Promoted", "刷单", "灰产", "AI换脸"]):
            continue
        if " 回复 " in f" {text} ":
            continue
        if any(line.startswith("回复") for line in lines[:4]):
            continue
        title = ""
        for line in lines:
            if line.startswith("@") or line.startswith("回复") or line.startswith("引用"):
                continue
            if re.fullmatch(r"[0-9.]+[KMB]?(\s+Views)?", line):
                continue
            if line in {"Carven", "BonoDJblack"}:
                continue
            title = line
            break
        if not title:
            title = text
        score = topic_match_score(topic, text)
        if score <= 0:
            continue
        items.append(
            {
                "platform": "x",
                "title": short(title, 96),
                "summary": short(text, 220),
                "url": link,
                "score": score,
            }
        )
    items.sort(key=lambda item: item.get("score", 0), reverse=True)
    return items[:limit]


def infer_structure(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    text = "\n".join(item.get("summary", "") for item in items)
    patterns = []
    if re.search(r"(?:\d+[.、）)])", text):
        patterns.append("列表/步骤结构")
    if any(token in text for token in ["为什么", "结论", "先说", "核心"]):
        patterns.append("结论先行")
    if any(token in text for token in ["案例", "复盘", "经历", "踩坑"]):
        patterns.append("案例复盘")
    if any(token in text for token in ["模板", "提示词", "流程", "框架"]):
        patterns.append("方法模板")
    if not patterns:
        patterns.append("短结论 + 清单展开")

    stale = []
    for item in items:
        hay = f"{item.get('title', '')} {item.get('summary', '')}"
        if any(token in hay for token in ["2023", "2024", "去年的", "旧版", "旧模型"]):
            stale.append(short(item.get("title", ""), 60))

    hooks = []
    for item in items[:3]:
        title = clean_text(item.get("title", ""))
        if len(title) >= 8:
            hooks.append(title)

    return {
        "patterns": patterns[:3],
        "hooks": hooks[:3],
        "stale_points": stale[:3],
        "opportunity": "用最新工具、真实执行结果、可落地动作替代空泛概念和过时判断。",
    }


def research_topic(topic: str, limit: int = 5) -> Dict[str, Any]:
    with social_browser([X_HOME_URL, XHS_HOME_URL], seed_platforms=["x", "xiaohongshu"]) as (context, _seed):
        page = context.new_page()
        x_items = extract_x_items(page, topic, limit=limit)
        page.close()
        xhs_items = extract_xhs_site_results(context, topic, limit=limit)
    if not xhs_items:
        xhs_items = extract_xhs_bing_results(topic, limit=limit)
    insights = infer_structure(x_items + xhs_items)
    return {
        "topic": topic,
        "x": x_items,
        "xiaohongshu": xhs_items,
        "insights": insights,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def bootstrap_social_browser(payload: Dict[str, Any]) -> Dict[str, Any]:
    platforms = list(payload.get("platforms", []) or [])
    with social_browser(target_urls_for(platforms), seed_platforms=platforms or ["x", "xiaohongshu"]) as (context, seed):
        state = inspect_browser_state(context)
        state["seeded"] = bool(seed.get("seeded"))
        return state


def social_browser_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    start = bool(payload.get("start"))
    platforms = list(payload.get("platforms", []) or [])
    if not browser_running(timeout=2) and not start:
        return {
            "success": True,
            "mode": "dedicated",
            "browser_running": False,
            "profile_dir": str(SOCIAL_BROWSER_DIR),
            "cdp_url": SOCIAL_BROWSER_CDP_URL,
            "tabs": 0,
            "x_ready": None,
            "xiaohongshu_ready": None,
            "urls": [],
        }
    with social_browser(target_urls_for(platforms) if start else [], seed_platforms=platforms if start else []) as (context, seed):
        state = inspect_browser_state(context)
        state["seeded"] = bool(seed.get("seeded"))
        return state


def _parse_count(text: str) -> int:
    value = clean_text(text)
    if not value:
        return 0
    value = value.replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)([万kKmM]?)", value)
    if not match:
        return 0
    number = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "万":
        number *= 10000
    elif suffix == "k":
        number *= 1000
    elif suffix == "m":
        number *= 1000000
    return int(number)


def _x_profile_stats(page) -> Dict[str, Any]:
    body = body_preview(page, limit=2500)
    article = page.locator("article").first

    def action_count(testid: str) -> int:
        locator = article.locator(f'[data-testid="{testid}"]').first
        if locator.count() == 0:
            return 0
        text = clean_text(locator.inner_text(timeout=1000) or "")
        if text:
            return _parse_count(text)
        label = clean_text(locator.get_attribute("aria-label") or "")
        return _parse_count(label)

    following = 0
    followers = 0
    m = re.search(r"([0-9.,万kKmM]+)\s*正在关注", body)
    if m:
        following = _parse_count(m.group(1))
    m = re.search(r"([0-9.,万kKmM]+)\s*关注者", body)
    if m:
        followers = _parse_count(m.group(1))
    latest_text = ""
    try:
        latest_text = clean_text(article.inner_text(timeout=1500))
    except Exception:
        latest_text = ""
    return {
        "followers": followers,
        "following": following,
        "latest_like_count": action_count("like"),
        "latest_reply_count": action_count("reply"),
        "latest_repost_count": action_count("retweet"),
        "latest_bookmark_count": action_count("bookmark"),
        "latest_post_preview": latest_text[:280],
    }


def _xhs_creator_stats(page) -> Dict[str, Any]:
    body = body_preview(page, limit=4000)

    def pick(label: str) -> int:
        m = re.search(rf"{re.escape(label)}\s*\n\s*([0-9.,万kKmM]+)", body)
        return _parse_count(m.group(1)) if m else 0

    latest_note_title = ""
    m = re.search(r"最新笔记\s*\n\s*查看详情\s*\n\s*(.+?)\s*\n", body)
    if m:
        latest_note_title = clean_text(m.group(1))
    return {
        "followers": pick("粉丝数"),
        "likes_and_saves": pick("获赞与收藏"),
        "exposure": pick("曝光数"),
        "views": pick("观看数"),
        "cover_ctr": pick("封面点击率"),
        "likes": pick("点赞数"),
        "comments": pick("评论数"),
        "saves": pick("收藏数"),
        "shares": pick("分享数"),
        "net_followers": pick("净涨粉"),
        "profile_visitors": pick("主页访客"),
        "latest_note_title": latest_note_title,
    }


def _interesting_lines(text: str, limit: int = 18) -> List[str]:
    seen = set()
    out: List[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"\s+", " ", line)
        if len(line) > 160:
            line = line[:157] + "..."
        lower = line.lower()
        if lower in seen:
            continue
        if any(token in lower for token in ["沪icp", "营业执照", "违法不良信息举报", "服务条款", "隐私政策", "cookie", "更多"]):
            continue
        seen.add(lower)
        out.append(line)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _page_snapshot(page, limit: int = 18) -> Dict[str, Any]:
    return {
        "url": page.url,
        "title": clean_text(page.title()),
        "lines": body_lines(page, limit=limit),
    }


def _parse_xhs_notification_payload(payload: Dict[str, Any], category: str) -> List[Dict[str, Any]]:
    rows = (((payload or {}).get("data") or {}).get("message_list") or [])
    items: List[Dict[str, Any]] = []
    for row in rows:
        row = row or {}
        note = (row.get("item_info") or {}) if isinstance(row, dict) else {}
        user = (row.get("user_info") or row.get("user") or {}) if isinstance(row, dict) else {}
        comment = (row.get("comment_info") or {}) if isinstance(row, dict) else {}
        illegal = (note.get("illegal_info") or {}) if isinstance(note, dict) else {}
        note_id = str(note.get("id", "") or "").strip()
        xsec_token = str(note.get("xsec_token", "") or "").strip()
        note_url = ""
        if note_id and xsec_token:
            note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={urllib.parse.quote(xsec_token)}&xsec_source=pc_notice"
        items.append(
            {
                "category": category,
                "title": clean_text(str(row.get("title", "") or "")),
                "type": clean_text(str(row.get("type", "") or "")),
                "time": clean_text(str(row.get("time", "") or "")),
                "user_id": clean_text(str(user.get("userid", user.get("user_id", "")) or "")),
                "user_name": clean_text(str(user.get("nickname", "") or "")),
                "user_profile_url": (
                    f"https://www.xiaohongshu.com/user/profile/{str(user.get('userid', user.get('user_id', '')) or '').strip()}"
                    if str(user.get("userid", user.get("user_id", "")) or "").strip()
                    else ""
                ),
                "content": clean_text(str(comment.get("content", row.get("content", "")) or "")),
                "comment_id": clean_text(str(comment.get("id", "") or "")),
                "note_id": note_id,
                "note_title": clean_text(str(note.get("content", "") or "")),
                "note_url": note_url,
                "xsec_token": xsec_token,
                "note_deleted": str(illegal.get("illegal_status", "") or "").upper() == "DELETE" or int(illegal.get("status", 0) or 0) == 1,
                "raw_link": clean_text(str(note.get("link", "") or "")),
            }
        )
    return items


def capture_xhs_notifications(context) -> Dict[str, Any]:
    page = get_or_open_page(context, XHS_NOTIFICATIONS_URL)
    captured: Dict[str, Any] = {}

    def on_response(resp):
        url = resp.url
        try:
            body = resp.text()
            payload = json.loads(body)
        except Exception:
            return
        if "/api/sns/web/v1/you/mentions" in url:
            captured["mentions"] = payload
        elif "/api/sns/web/v1/you/likes" in url:
            captured["likes"] = payload
        elif "/api/sns/web/v1/you/connections" in url:
            captured["connections"] = payload

    page.on("response", on_response)
    page.goto(XHS_NOTIFICATIONS_URL, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(5000)
    for label in ["赞和收藏", "新增关注", "评论和@"]:
        try:
            page.get_by_text(label, exact=True).click(force=True)
            page.wait_for_timeout(2000)
        except Exception:
            pass
    page.wait_for_timeout(1000)
    return {
        "snapshot": _page_snapshot(page, limit=18),
        "mentions_items": _parse_xhs_notification_payload(captured.get("mentions", {}), "mentions"),
        "likes_items": _parse_xhs_notification_payload(captured.get("likes", {}), "likes"),
        "connections_items": _parse_xhs_notification_payload(captured.get("connections", {}), "connections"),
    }


def ensure_xhs_main_profile_page(context):
    page = get_or_open_page(context, XHS_EXPLORE_URL)
    page.goto(XHS_EXPLORE_URL, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(5000)
    if login_page_detected(page):
        raise RuntimeError("Xiaohongshu login required")
    profile_link = page.locator('a.link-wrapper[href^="/user/profile/"]').first
    if profile_link.count() == 0:
        raise RuntimeError("Xiaohongshu profile link not found")
    profile_link.click()
    page.wait_for_timeout(5000)
    return page


def xhs_note_cover_url(page) -> str:
    try:
        return str(
            page.evaluate(
                """() => {
                  const images = Array.from(document.querySelectorAll('img')).map(img => String(img.src || '').trim());
                  return images.find(src => src.includes('sns-webpic-qc.xhscdn.com')) || '';
                }"""
            )
            or ""
        ).strip()
    except Exception:
        return ""


def xhs_bundle_api(page):
    return page.evaluate_handle(
        """() => {
          let req = null;
          window.webpackChunkxhs_pc_web.push([[Math.random()], {}, function(r){ req = r; }]);
          return req(40122);
        }"""
    )


def xhs_get_selfinfo(page) -> Dict[str, Any]:
    handle = xhs_bundle_api(page)
    try:
        return page.evaluate(
            """async (api) => {
              try {
                const res = await api.gB({ transform: true });
                return { success: true, payload: res };
              } catch (e) {
                return { success: false, error: String(e) };
              }
            }""",
            handle,
        )
    finally:
        handle.dispose()


def xhs_update_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    with social_browser([XHS_EXPLORE_URL], seed_platforms=["xiaohongshu"]) as (context, _seed):
        page = ensure_xhs_main_profile_page(context)
        handle = xhs_bundle_api(page)
        try:
            profile = xhs_get_selfinfo(page)
            current = (((profile.get("payload") or {}).get("basicInfo") or {})) if profile.get("success") else {}
            nickname = str(payload.get("nickname", "") or "").strip()
            desc = str(payload.get("desc", "") or "").strip()
            gender = payload.get("gender")
            image_url = str(payload.get("image_url", "") or "").strip()
            if not image_url and payload.get("use_latest_note_cover", True):
                image_url = xhs_note_cover_url(page)

            operations: List[Dict[str, Any]] = []
            if nickname and nickname != str(current.get("nickname", "") or ""):
                operations.append({"key": "nickname", "value": nickname})
            if desc and desc != str(current.get("desc", "") or ""):
                operations.append({"key": "desc", "value": desc})
            if gender is not None and int(gender) != int(current.get("gender", 0) or 0):
                operations.append({"key": "gender", "value": int(gender)})
            if image_url:
                operations.append({"key": "image", "value": image_url})

            results = []
            for item in operations:
                result = page.evaluate(
                    """async ({ api, payload }) => {
                      try {
                        const res = await api.R6(payload, { transform: true });
                        return { success: true, payload, res };
                      } catch (e) {
                        return { success: false, payload, error: String(e) };
                      }
                    }""",
                    {"api": handle, "payload": item},
                )
                results.append(result)
                page.wait_for_timeout(800)

            refreshed = xhs_get_selfinfo(page)
            current_info = (((refreshed.get("payload") or {}).get("basicInfo") or {})) if refreshed.get("success") else current
            pending_review = any("审核中" in str(item.get("error", "") or "") for item in results)
            success = bool(refreshed.get("success")) and (
                (not nickname or str(current_info.get("nickname", "") or "") == nickname)
                and (not desc or str(current_info.get("desc", "") or "") == desc)
            )
            return {
                "success": success,
                "pending_review": pending_review,
                "results": results,
                "profile": current_info,
                "image_url": image_url,
            }
        finally:
            handle.dispose()


def collect_social_workspace(payload: Dict[str, Any]) -> Dict[str, Any]:
    with social_browser(
        [X_PROFILE_URL, X_NOTIFICATIONS_URL, X_MESSAGES_URL, X_TREND_URL, XHS_HOME_URL, XHS_EXPLORE_URL, XHS_NOTIFICATIONS_URL, XHS_IM_URL],
        seed_platforms=["x", "xiaohongshu"],
    ) as (context, seed):
        x_profile = get_or_open_page(context, X_PROFILE_URL)
        x_profile.goto(X_PROFILE_URL, wait_until="domcontentloaded", timeout=120000)
        x_profile.wait_for_timeout(3000)
        x_notifications = get_or_open_page(context, X_NOTIFICATIONS_URL)
        x_notifications.goto(X_NOTIFICATIONS_URL, wait_until="domcontentloaded", timeout=120000)
        x_notifications.wait_for_timeout(3000)
        x_messages = get_or_open_page(context, X_MESSAGES_URL)
        x_messages.goto(X_MESSAGES_URL, wait_until="domcontentloaded", timeout=120000)
        x_messages.wait_for_timeout(3000)
        x_trends = get_or_open_page(context, X_TREND_URL)
        x_trends.goto(X_TREND_URL, wait_until="domcontentloaded", timeout=120000)
        x_trends.wait_for_timeout(3000)

        xhs_home = get_or_open_page(context, XHS_HOME_URL)
        xhs_home.goto(XHS_HOME_URL, wait_until="domcontentloaded", timeout=120000)
        xhs_home.wait_for_timeout(3000)
        xhs_profile = ensure_xhs_main_profile_page(context)
        xhs_notification_data = capture_xhs_notifications(context)
        xhs_im = get_or_open_page(context, XHS_IM_URL)
        xhs_im.goto(XHS_IM_URL, wait_until="domcontentloaded", timeout=120000)
        xhs_im.wait_for_timeout(3000)

        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seeded": bool(seed.get("seeded")),
            "x": {
                "profile": {"url": x_profile.url, "stats": _x_profile_stats(x_profile), "snapshot": _page_snapshot(x_profile, limit=20)},
                "notifications": _page_snapshot(x_notifications, limit=18),
                "messages": _page_snapshot(x_messages, limit=18),
                "trends": _page_snapshot(x_trends, limit=18),
            },
            "xiaohongshu": {
                "creator_home": {"url": xhs_home.url, "stats": _xhs_creator_stats(xhs_home), "snapshot": _page_snapshot(xhs_home, limit=20)},
                "profile": _page_snapshot(xhs_profile, limit=20),
                "notifications": xhs_notification_data.get("snapshot", {}),
                "mentions_items": xhs_notification_data.get("mentions_items", []),
                "likes_items": xhs_notification_data.get("likes_items", []),
                "connections_items": xhs_notification_data.get("connections_items", []),
                "messages": _page_snapshot(xhs_im, limit=18),
            },
        }


def collect_social_metrics_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    with social_browser([X_HOME_URL, XHS_HOME_URL], seed_platforms=["x", "xiaohongshu"]) as (context, seed):
        x_page = get_or_open_page(context, "https://x.com/BonoDJblack")
        x_page.goto("https://x.com/BonoDJblack", wait_until="domcontentloaded", timeout=120000)
        x_page.wait_for_timeout(5000)
        x_stats = _x_profile_stats(x_page)

        xhs_page = get_or_open_page(context, XHS_HOME_URL)
        xhs_page.goto(XHS_HOME_URL, wait_until="domcontentloaded", timeout=120000)
        xhs_page.wait_for_timeout(5000)
        xhs_stats = _xhs_creator_stats(xhs_page)

        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seeded": bool(seed.get("seeded")),
            "x": {"url": x_page.url, "stats": x_stats},
            "xiaohongshu": {"url": xhs_page.url, "stats": xhs_stats},
        }


def draw_cards(payload: Dict[str, Any]) -> Dict[str, Any]:
    topic = payload.get("topic", "AI出海")
    picks = payload.get("picks", [])[:5]
    insights = payload.get("insights", {})
    out_dir = ROOT / "clawbot" / "images" / "social_posts" / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{slugify(topic)}"
    out_dir.mkdir(parents=True, exist_ok=True)

    title_font = ImageFont.truetype(FONT_PATH, 82)
    sub_font = ImageFont.truetype(FONT_PATH, 38)
    body_font = ImageFont.truetype(FONT_PATH, 34)
    small_font = ImageFont.truetype(FONT_PATH, 28)
    num_font = ImageFont.truetype(FONT_PATH, 52)

    def bg(c1, c2, w=1242, h=1660):
        img = Image.new("RGB", (w, h), c1)
        px = img.load()
        for y in range(h):
            t = y / (h - 1)
            r = int(c1[0] * (1 - t) + c2[0] * t)
            g = int(c1[1] * (1 - t) + c2[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            for x in range(w):
                px[x, y] = (r, g, b)
        d = ImageDraw.Draw(img, "RGBA")
        d.ellipse((900, -100, 1320, 300), fill=(255, 255, 255, 80))
        d.ellipse((-140, 1240, 320, 1720), fill=(255, 255, 255, 70))
        d.rounded_rectangle((62, 62, w - 62, h - 62), radius=42, outline=(255, 255, 255, 120), width=3)
        return img

    # cover
    img = bg((244, 244, 239), (230, 236, 246))
    d = ImageDraw.Draw(img)
    accent = (31, 87, 162)
    d.rounded_rectangle((82, 82, 374, 140), radius=24, fill=accent)
    d.text((108, 96), "OpenClaw 选题生成", font=small_font, fill="white")
    d.text((88, 180), f"{topic} 这类内容", font=title_font, fill=(28, 35, 48))
    d.text((88, 282), "我会这样写成爆文", font=title_font, fill=(28, 35, 48))
    summary = f"先抓热点，再学结构，再用更高密度的信息差重写成自己的文章。"
    for i, line in enumerate(textwrap.wrap(summary, width=22)):
        d.text((92, 406 + i * 46), line, font=sub_font, fill=(76, 86, 102))
    panel_y = 620
    d.rounded_rectangle((92, panel_y, 1150, 1450), radius=36, fill=(255, 255, 255, 212), outline=(255, 255, 255, 245), width=2)
    y = panel_y + 50
    for idx, item in enumerate(picks[:5], 1):
        d.rounded_rectangle((124, y, 210, y + 70), radius=24, fill=accent)
        d.text((150, y + 12), str(idx), font=num_font, fill="white")
        d.text((242, y + 2), short(item.get("title", ""), 18), font=body_font, fill=(31, 45, 58))
        d.text((242, y + 46), short(item.get("summary", ""), 38), font=small_font, fill=(92, 100, 111))
        y += 136
    cover = out_dir / "cover.png"
    img.save(cover)

    # reason card
    img = bg((240, 246, 243), (221, 235, 231))
    d = ImageDraw.Draw(img)
    accent = (24, 110, 90)
    d.rounded_rectangle((82, 82, 334, 140), radius=24, fill=accent)
    d.text((110, 96), "本次学习笔记", font=small_font, fill="white")
    d.text((88, 180), "这类内容的共性", font=title_font, fill=(28, 35, 48))
    y = 420
    blocks = [
        ("常见结构", " / ".join(insights.get("patterns", [])[:3]) or "结论先行 / 列表展开"),
        ("高频钩子", "；".join(insights.get("hooks", [])[:2]) or "先给结果，再讲方法"),
        ("可利用信息差", insights.get("opportunity", "用更新的数据和执行案例替代旧结论")),
    ]
    for idx, (head, text) in enumerate(blocks, 1):
        d.rounded_rectangle((92, y, 1150, y + 240), radius=32, fill=(255, 255, 255, 212), outline=(255, 255, 255, 245), width=2)
        d.rounded_rectangle((124, y + 34, 208, y + 108), radius=22, fill=accent)
        d.text((149, y + 48), str(idx), font=num_font, fill="white")
        d.text((242, y + 28), head, font=body_font, fill=(31, 45, 58))
        for j, line in enumerate(textwrap.wrap(text, width=22)):
            d.text((242, y + 82 + j * 36), line, font=small_font, fill=(92, 100, 111))
        y += 270
    reasons = out_dir / "reasons.png"
    img.save(reasons)

    # x cover
    W, H = 1600, 900
    img = Image.new("RGB", (W, H), (236, 241, 247))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        c1 = (238, 242, 247)
        c2 = (217, 228, 243)
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        for x in range(W):
            px[x, y] = (r, g, b)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((48, 48, W - 48, H - 48), radius=34, outline=(255, 255, 255), width=3)
    d.rounded_rectangle((72, 70, 352, 120), radius=24, fill=(31, 87, 162))
    d.text((96, 84), "OpenClaw 热点学习", font=small_font, fill="white")
    d.text((86, 150), f"{topic} 这个题材", font=ImageFont.truetype(FONT_PATH, 78), fill=(28, 35, 48))
    d.text((86, 246), "我会这样重写", font=ImageFont.truetype(FONT_PATH, 78), fill=(28, 35, 48))
    d.text((92, 366), short(insights.get("opportunity", "用更高密度的信息差重写内容"), 42), font=sub_font, fill=(77, 88, 104))
    x_cover = out_dir / "x-cover.png"
    img.save(x_cover)
    return {"dir": str(out_dir), "x_cover": str(x_cover), "xhs": [str(cover), str(reasons)]}


def publish_x(text: str, images: List[str]) -> Dict[str, Any]:
    def attempt(use_images: bool) -> Dict[str, Any]:
        with social_browser([X_HOME_URL, X_COMPOSE_URL], seed_platforms=["x"]) as (context, _seed):
            page = get_or_open_page(context, X_COMPOSE_URL)
            responses: List[str] = []
            response_payloads: List[str] = []

            def on_response(resp):
                if "CreateTweet" in resp.url:
                    responses.append(resp.url)
                    try:
                        response_payloads.append(resp.text())
                    except Exception:
                        pass

            page.on("response", on_response)
            page.goto(X_COMPOSE_URL, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(5000)
            if login_page_detected(page):
                # 自动弹出可见浏览器供用户登录
                login_result = interactive_login(["x"], timeout=300)
                if login_result.get("success"):
                    # 登录成功，重新尝试
                    return {"success": False, "status": "login_completed_retry", "url": page.url}
                return {"success": False, "status": "login_required", "url": page.url}
            box = page.locator('div[data-testid="tweetTextarea_0"]').first
            if box.count() == 0:
                return {"success": False, "status": "textbox_not_found", "url": page.url}
            box.click()
            page.keyboard.press("Meta+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(text, delay=8)
            if use_images and images:
                file_input = page.locator('input[data-testid="fileInput"]').first
                if file_input.count() == 0:
                    return {"success": False, "status": "file_input_not_found", "url": page.url}
                file_input.set_input_files(images[:1])
                page.wait_for_timeout(9000)
            btn = page.locator('button[data-testid="tweetButton"]').first
            if btn.count() == 0:
                return {"success": False, "status": "button_not_found", "url": page.url}
            if btn.is_disabled():
                return {"success": False, "status": "button_disabled", "url": page.url}
            page.keyboard.press("Meta+Enter")
            page.wait_for_timeout(1500)
            if not responses:
                btn.click(force=True)
            page.wait_for_timeout(12000)
            if not responses:
                return {"success": False, "status": "create_tweet_not_observed", "url": page.url}
            tweet_id = ""
            for raw in response_payloads:
                match = re.search(r'"id_str":"(\d+)"', raw)
                if match:
                    tweet_id = match.group(1)
                    break
                match = re.search(r'"rest_id":"(\d+)"', raw)
                if match:
                    tweet_id = match.group(1)
                    break
            published = bool(tweet_id or responses)
            url = f"https://x.com/BonoDJblack/status/{tweet_id}" if tweet_id else page.url
            return {"success": published, "url": url, "status": "published" if published else "unknown"}

    first = attempt(use_images=bool(images))
    if first.get("success"):
        return first
    return attempt(use_images=False)


def reply_x(url: str, text: str) -> Dict[str, Any]:
    with social_browser([X_HOME_URL, str(url or X_HOME_URL).strip()], seed_platforms=["x"]) as (context, _seed):
        page = context.new_page()
        responses: List[str] = []
        payloads: List[str] = []

        def on_response(resp):
            if "CreateTweet" in resp.url:
                responses.append(resp.url)
                try:
                    payloads.append(resp.text())
                except Exception:
                    pass

        page.on("response", on_response)
        page.goto(str(url or X_HOME_URL).strip(), wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(5000)
        if login_page_detected(page):
            login_result = interactive_login(["x"], timeout=300)
            if login_result.get("success"):
                return {"success": False, "status": "login_completed_retry", "url": page.url}
            return {"success": False, "status": "login_required", "url": page.url}
        reply_btn = page.locator('[data-testid="reply"]').first
        if reply_btn.count() == 0:
            return {"success": False, "status": "reply_button_not_found", "url": page.url}
        reply_btn.click()
        page.wait_for_timeout(1200)
        box = page.locator('div[data-testid="tweetTextarea_0"]').first
        if box.count() == 0:
            return {"success": False, "status": "textbox_not_found", "url": page.url}
        box.click()
        page.keyboard.type(str(text or "").strip(), delay=8)
        send_btn = page.locator('button[data-testid="tweetButton"]').last
        if send_btn.count() == 0 or send_btn.is_disabled():
            return {"success": False, "status": "button_disabled", "url": page.url}
        send_btn.click(force=True)
        page.wait_for_timeout(12000)
        tweet_id = ""
        for raw in payloads:
            match = re.search(r'"id_str":"(\d+)"', raw) or re.search(r'"rest_id":"(\d+)"', raw)
            if match:
                tweet_id = match.group(1)
                break
        return {
            "success": bool(responses),
            "status": "published" if responses else "unknown",
            "url": f"https://x.com/BonoDJblack/status/{tweet_id}" if tweet_id else page.url,
            "reply_to": str(url or "").strip(),
        }


def _xhs_note_id_from_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urllib.parse.urlparse(text)
    path = parsed.path or ""
    match = re.search(r"/explore/([0-9a-z]+)", path, re.I)
    if match:
        return match.group(1)
    match = re.search(r"/item/([0-9a-z]+)", path, re.I)
    if match:
        return match.group(1)
    return ""


def reply_xhs(url: str, text: str, target_comment_id: str = "") -> Dict[str, Any]:
    note_url = str(url or "").strip()
    note_id = _xhs_note_id_from_url(note_url)
    if not note_url or not note_id:
        return {"success": False, "status": "invalid_target", "url": note_url}
    body = str(text or "").strip()
    if not body:
        return {"success": False, "status": "empty_body", "url": note_url}
    with social_browser([note_url], seed_platforms=["xiaohongshu"]) as (context, _seed):
        page = context.new_page()
        page.goto(note_url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(5000)
        if login_page_detected(page):
            login_result = interactive_login(["xiaohongshu"], timeout=300)
            if login_result.get("success"):
                return {"success": False, "status": "login_completed_retry", "url": page.url}
            return {"success": False, "status": "login_required", "url": page.url}
        handle = xhs_bundle_api(page)
        try:
            payload = {"note_id": note_id, "content": body, "at_users": []}
            if str(target_comment_id or "").strip():
                payload["target_comment_id"] = str(target_comment_id).strip()
            result = page.evaluate(
                """async ({ api, payload }) => {
                  try {
                    const res = await api.pe(payload, { transform: true });
                    return { success: true, payload: res };
                  } catch (e) {
                    return { success: false, error: String(e) };
                  }
                }""",
                {"api": handle, "payload": payload},
            )
        finally:
            handle.dispose()
            page.close()
    comment = ((result.get("payload") or {}).get("comment") or {}) if result.get("success") else {}
    return {
        "success": bool(result.get("success")),
        "status": "published" if result.get("success") else "failed",
        "url": note_url,
        "reply_to": note_url,
        "target_comment_id": str(target_comment_id or "").strip(),
        "comment_id": str(comment.get("id", "") or ""),
        "raw": result,
    }


def publish_xhs(title: str, body: str, images: List[str]) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    with social_browser([XHS_HOME_URL, XHS_PUBLISH_URL], seed_platforms=["xiaohongshu"]) as (context, _seed):
        page = get_or_open_page(context, XHS_PUBLISH_URL)

        def on_response(resp):
            if "web_api/sns/v2/note" in resp.url:
                try:
                    records.append(json.loads(resp.text()))
                except Exception:
                    pass

        page.on("response", on_response)
        page.goto(XHS_PUBLISH_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(5000)
        if login_page_detected(page):
            login_result = interactive_login(["xiaohongshu"], timeout=300)
            if login_result.get("success"):
                return {"success": False, "status": "login_completed_retry", "url": page.url}
            return {"success": False, "status": "login_required", "url": page.url}
        page.evaluate(
            """() => {
              const tabs = Array.from(document.querySelectorAll('div')).filter(el => String(el.className||'').includes('creator-tab') && (el.innerText||el.textContent||'').trim() === '上传图文' && !(el.getAttribute('style')||'').includes('left: -9999px'));
              if (tabs.length) tabs[0].click();
            }"""
        )
        page.wait_for_timeout(2500)
        if images:
            file_input = page.locator('input[type=file][accept*="jpg"], input[type=file][accept*="jpeg"], input[type=file][accept*="png"]').first
            if file_input.count() == 0:
                return {"success": False, "status": "file_input_not_found", "url": page.url}
            file_input.set_input_files(images)
            page.wait_for_timeout(12000)
        title_input = page.locator('input[placeholder*="填写标题"], input[placeholder*="标题"]').first
        if title_input.count() == 0:
            return {"success": False, "status": "title_input_not_found", "url": page.url}
        title_input.click()
        title_input.fill(title)
        editor = page.locator('div.tiptap.ProseMirror, div.ProseMirror[contenteditable="true"]').first
        if editor.count() == 0:
            return {"success": False, "status": "editor_not_found", "url": page.url}
        editor.click()
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(body, delay=6)
        page.wait_for_timeout(1200)
        publish_btn = page.locator('button:has-text("发布")').last
        if publish_btn.count() == 0:
            return {"success": False, "status": "button_not_found", "url": page.url}
        publish_btn.click(force=True)
        page.wait_for_timeout(20000)
        # Check if page navigated away from publish (success indicator)
        final_url = page.url
        page_text = body_preview(page, limit=2000)

    payload = records[-1] if records else {}
    share_link = str(payload.get("share_link", "") or "")
    if not share_link:
        share_link = (((payload.get("data") or {}).get("note_info") or {}).get("share_info") or {}).get("share_link", "")
    success = bool(share_link or payload.get("success") is True or payload.get("result") == 0)
    # Fallback: check if page navigated away from publish page (indicates success)
    if not success and final_url and "/publish" not in final_url:
        success = True
    # Fallback: check page text for success indicators
    if not success and page_text:
        if any(kw in page_text for kw in ["发布成功", "已发布", "笔记管理"]):
            success = True
    return {"success": success, "url": share_link or final_url or XHS_PUBLISH_URL, "raw": payload, "status": "published" if success else "unknown", "debug_final_url": final_url, "debug_records_count": len(records), "debug_page_hint": page_text[:200] if page_text else ""}


def delete_x(tweet_url: str) -> Dict[str, Any]:
    """Delete a tweet by navigating to it and clicking the delete option."""
    with social_browser([tweet_url], seed_platforms=["x"]) as (context, _seed):
        page = get_or_open_page(context, tweet_url)
        page.goto(tweet_url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(3000)
        if login_page_detected(page):
            login_result = interactive_login(["x"], timeout=300)
            if login_result.get("success"):
                return {"success": False, "status": "login_completed_retry", "url": page.url}
            return {"success": False, "status": "login_required", "url": page.url}
        # Click the "..." more button on the tweet
        more_btn = page.locator('button[data-testid="caret"]').first
        if more_btn.count() == 0:
            return {"success": False, "status": "more_button_not_found", "url": page.url}
        more_btn.click()
        page.wait_for_timeout(1000)
        # Click "Delete" menu item
        delete_item = page.locator('[data-testid="Dropdown"] [role="menuitem"]:has-text("Delete"), [data-testid="Dropdown"] [role="menuitem"]:has-text("删除")').first
        if delete_item.count() == 0:
            return {"success": False, "status": "delete_option_not_found", "url": page.url}
        delete_item.click()
        page.wait_for_timeout(1000)
        # Confirm delete
        confirm_btn = page.locator('button[data-testid="confirmationSheetConfirm"]').first
        if confirm_btn.count() == 0:
            return {"success": False, "status": "confirm_button_not_found", "url": page.url}
        confirm_btn.click()
        page.wait_for_timeout(3000)
    return {"success": True, "status": "deleted", "url": tweet_url}


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("usage: social_browser_worker.py <bootstrap|status|metrics|workspace|research|render|publish_x|reply_x|reply_xhs|publish_xhs|update_xhs_profile|delete_x> '<json>'")
    action = sys.argv[1]
    payload = json.loads(sys.argv[2])
    if action == "bootstrap":
        result = bootstrap_social_browser(payload)
    elif action == "status":
        result = social_browser_status(payload)
    elif action == "metrics":
        result = collect_social_metrics_snapshot(payload)
    elif action == "workspace":
        result = collect_social_workspace(payload)
    elif action == "research":
        result = research_topic(str(payload.get("topic", "AI出海")), int(payload.get("limit", 5) or 5))
    elif action == "render":
        result = draw_cards(payload)
    elif action == "publish_x":
        result = publish_x(str(payload.get("text", "")), list(payload.get("images", []) or []))
    elif action == "reply_x":
        result = reply_x(str(payload.get("url", "")), str(payload.get("text", "")))
    elif action == "reply_xhs":
        result = reply_xhs(str(payload.get("url", "")), str(payload.get("text", "")), str(payload.get("target_comment_id", "")))
    elif action == "publish_xhs":
        result = publish_xhs(str(payload.get("title", "")), str(payload.get("body", "")), list(payload.get("images", []) or []))
    elif action == "update_xhs_profile":
        result = xhs_update_profile(payload)
    elif action == "delete_x":
        result = delete_x(str(payload.get("url", "")))
    elif action == "login":
        # 交互式登录：弹出可见浏览器供用户登录
        platforms = list(payload.get("platforms", ["x", "xiaohongshu"]))
        timeout = int(payload.get("timeout", 300) or 300)
        result = interactive_login(platforms, timeout=timeout)
    else:
        raise SystemExit(f"unknown action: {action}")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
