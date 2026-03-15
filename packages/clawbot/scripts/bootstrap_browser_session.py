#!/usr/bin/env python3
"""Warm the dedicated OpenClaw social browser and open core tabs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHROME_BIN = os.getenv(
    "OPENCLAW_SOCIAL_CHROME_BIN",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
).strip() or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE_DIR = Path(
    os.getenv(
        "OPENCLAW_SOCIAL_BROWSER_DIR",
        str(ROOT / "clawbot" / "data" / "browser_profiles" / "openclaw_social"),
    )
)
CDP_PORT = int(os.getenv("OPENCLAW_SOCIAL_BROWSER_PORT", "19222"))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
TARGET_URLS = [
    "https://x.com/home",
    "https://x.com/explore/tabs/trending",
    "https://x.com/compose/post",
    "https://creator.xiaohongshu.com/publish/publish",
    "https://creator.xiaohongshu.com/new/home",
    "https://www.upwork.com/ab/proposals/offers",
    "https://www.upwork.com/nx/find-work/best-matches",
    "https://www.upwork.com/nx/payments/134843060/disbursement-methods",
]


def cdp_request(path: str, method: str = "GET", timeout: int = 5):
    req = urllib.request.Request(f"{CDP_URL}{path}", method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    if not body:
        return {}
    try:
        return json.loads(body)
    except Exception:
        return body


def browser_ready() -> bool:
    try:
        payload = cdp_request("/json/version", timeout=2)
        return bool((payload or {}).get("Browser"))
    except Exception:
        return False


def wait_for_browser(timeout: int = 20) -> bool:
    deadline = time.time() + max(1, int(timeout))
    while time.time() < deadline:
        if browser_ready():
            return True
        time.sleep(0.4)
    return False


def normalized_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return str(url or "").strip()
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


def launch_chrome() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if browser_ready():
        return
    if not Path(CHROME_BIN).exists():
        raise FileNotFoundError(f"Chrome executable not found: {CHROME_BIN}")
    subprocess.Popen(
        [
            CHROME_BIN,
            f"--user-data-dir={PROFILE_DIR}",
            f"--remote-debugging-port={CDP_PORT}",
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


def list_tab_urls() -> set[str]:
    try:
        payload = cdp_request("/json/list", timeout=4) or []
    except Exception:
        return set()
    urls = set()
    for item in payload:
        if str(item.get("type", "") or "") != "page":
            continue
        url = str(item.get("url", "") or "").strip()
        if url:
            urls.add(normalized_url(url))
    return urls


def open_tab(url: str) -> None:
    encoded = urllib.parse.quote(str(url or ""), safe="")
    last_error = None
    for method in ("PUT", "GET"):
        try:
            cdp_request(f"/json/new?{encoded}", method=method, timeout=8)
            return
        except Exception as exc:  # pragma: no cover
            last_error = exc
    if last_error:
        raise last_error


def open_missing_tabs(urls: list[str]) -> None:
    existing = list_tab_urls()
    for url in urls:
        if normalized_url(url) in existing:
            continue
        open_tab(url)
        time.sleep(0.4)
        existing.add(normalized_url(url))


def main() -> int:
    launch_chrome()
    open_missing_tabs(TARGET_URLS)
    print(f"OpenClaw social browser ready ({PROFILE_DIR})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"bootstrap_browser_session failed: {exc}", file=sys.stderr)
        raise
