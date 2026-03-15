#!/usr/bin/env python3
"""Open the core unattended browser tabs in the logged-in Chrome profile."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


CHROME_APP = "/Applications/Google Chrome.app"
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE_DIR = os.getenv("OPENCLAW_BROWSER_PROFILE", "Profile 1")
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


def run_osascript(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"osascript failed: {result.returncode}")
    return (result.stdout or "").strip()


def chrome_running() -> bool:
    result = subprocess.run(["pgrep", "-x", "Google Chrome"], capture_output=True, text=True, check=False)
    return result.returncode == 0


def launch_chrome() -> None:
    if chrome_running():
        return
    if not Path(CHROME_BIN).exists():
        raise FileNotFoundError(f"Chrome executable not found: {CHROME_BIN}")
    subprocess.Popen(
        [CHROME_BIN, f"--profile-directory={PROFILE_DIR}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(4)


def list_tab_urls() -> set[str]:
    try:
        raw = run_osascript(
            'tell application "Google Chrome"\n'
            'if not running then return ""\n'
            'if (count of windows) = 0 then return ""\n'
            'set outText to ""\n'
            'repeat with w in windows\n'
            'repeat with t in tabs of w\n'
            'set outText to outText & (URL of t) & linefeed\n'
            'end repeat\n'
            'end repeat\n'
            'return outText\n'
            'end tell'
        )
    except Exception:
        return set()
    return {line.strip() for line in raw.splitlines() if line.strip()}


def open_missing_tabs(urls: list[str]) -> None:
    existing = list_tab_urls()
    for url in urls:
        if url in existing:
            continue
        run_osascript(
            'tell application "Google Chrome"\n'
            'if not running then activate\n'
            'if (count of windows) = 0 then make new window\n'
            f'make new tab at end of tabs of front window with properties {{URL:"{url}"}}\n'
            'end tell'
        )
        time.sleep(0.6)


def main() -> int:
    launch_chrome()
    open_missing_tabs(TARGET_URLS)
    print(f"Chrome unattended tabs ready ({PROFILE_DIR})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"bootstrap_browser_session failed: {exc}", file=sys.stderr)
        raise
