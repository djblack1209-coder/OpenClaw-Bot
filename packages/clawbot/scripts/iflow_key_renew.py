#!/usr/bin/env python3
"""iFlow API Key 人工续期助手。

安全边界：
- 不读取 macOS Messages、短信或验证码；
- 不注入反检测脚本，不识别或拖动滑块；
- 不自动点击“重新生成 Key”；
- 只在用户可见浏览器中完成登录、验证码和 Key 轮换后，接收用户手动粘贴的新 Key；
- 仅在用户显式传入 ``--restart`` 时重启本地后端。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

PHONE_NUMBER = os.getenv("IFLOW_PHONE_NUMBER", "").strip()
IFLOW_LOGIN_URL = "https://platform.iflow.cn/login"
IFLOW_APIKEY_URL = "https://platform.iflow.cn/docs/api-key-management"
ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
TIMESTAMP_FILE = Path.home() / ".openclaw" / "iflow_key_timestamp.json"


def _key_age_days() -> int | None:
    """读取不含凭据的本地时间戳，返回 Key 已使用天数。"""
    if not TIMESTAMP_FILE.exists():
        return None
    try:
        data = json.loads(TIMESTAMP_FILE.read_text(encoding="utf-8"))
        if data.get("first_used_ts"):
            return max(0, int((time.time() - float(data["first_used_ts"])) / 86400))
        raw = data.get("key_first_used") or data.get("renewed_at")
        if raw:
            return max(0, (datetime.now() - datetime.fromisoformat(str(raw))).days)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return None


def update_env_key(new_key: str) -> bool:
    """原子更新本地 .env；日志永不显示 Key 或其片段。"""
    if not ENV_FILE.exists():
        print("[iflow] ❌ 本地 .env 不存在")
        return False
    if not new_key.startswith("sk-") or len(new_key) < 20:
        print("[iflow] ❌ 新 Key 格式不正确")
        return False

    content = ENV_FILE.read_text(encoding="utf-8")
    pattern = r"^SILICONFLOW_UNLIMITED_KEY=.*$"
    if not re.search(pattern, content, flags=re.MULTILINE):
        print("[iflow] ❌ .env 中未找到目标变量")
        return False

    new_content = re.sub(
        pattern,
        f"SILICONFLOW_UNLIMITED_KEY={new_key}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    temp_path = ENV_FILE.with_name(f".{ENV_FILE.name}.iflow-renew.tmp")
    try:
        temp_path.write_text(new_content, encoding="utf-8")
        temp_path.chmod(0o600)
        temp_path.replace(ENV_FILE)
        ENV_FILE.chmod(0o600)
    finally:
        temp_path.unlink(missing_ok=True)
    print("[iflow] ✅ 新 Key 已安全写入本地配置（不会显示具体值）")
    return True


def reset_timestamp() -> None:
    """记录续期时间，不保存 Key 明文。"""
    TIMESTAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    data = {
        "first_used_ts": time.time(),
        "key_first_used": now.isoformat(),
        "renewed_at": now.isoformat(),
        "note": "iFlow Key 到期前只提醒人工续期，不自动登录或轮换",
    }
    TIMESTAMP_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    TIMESTAMP_FILE.chmod(0o600)
    print("[iflow] ✅ 已更新时间戳（不含凭据）")


def renew_key_playwright(manual_code: bool = True) -> str | None:
    """打开可见浏览器，等待用户本人完成登录、验证码和 Key 轮换。"""
    del manual_code
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[iflow] ❌ Playwright 未安装，无法打开续期页面")
        return None

    print("[iflow] 正在打开可见浏览器；不会读取短信或自动处理验证码")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(locale="zh-CN")
        page = context.new_page()
        try:
            page.goto(IFLOW_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            if PHONE_NUMBER:
                phone_input = page.locator(
                    'input[placeholder*="手机号"], input[type="tel"], input[name*="phone"]'
                ).first
                if phone_input.count() > 0:
                    phone_input.fill(PHONE_NUMBER)

            print("[iflow] 请在浏览器内手动完成验证码、登录和 Key 轮换")
            input("[iflow] 完成登录后按回车，我将打开 Key 管理页: ")
            page.goto(IFLOW_APIKEY_URL, wait_until="domcontentloaded", timeout=30000)
            print("[iflow] 请在浏览器中手动重新生成并复制新 Key；脚本不会点击确认按钮")
            new_key = input("[iflow] 将新 Key 粘贴到这里（输入不会写入日志）: ").strip()
            if not new_key.startswith("sk-") or len(new_key) < 20:
                print("[iflow] ❌ 未收到有效的新 Key")
                return None
            print("[iflow] 新 Key 已接收（不会显示或写入日志）")
            return new_key
        except Exception as exc:
            print(f"[iflow] ❌ 人工续期助手失败: {type(exc).__name__}")
            return None
        finally:
            browser.close()


def restart_backend() -> None:
    """仅在用户显式请求时重启本地后端。"""
    print("[iflow] 正在按显式参数重启本地后端...")
    result = subprocess.run(
        ["launchctl", "stop", "ai.openclaw.clawbot-agent"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0:
        print("[iflow] ✅ 已请求 LaunchAgent 拉起后端")
    else:
        print("[iflow] ⚠️ 后端重启请求未成功，请从老板手册按步骤检查")


def main() -> int:
    parser = argparse.ArgumentParser(description="iFlow API Key 人工续期助手")
    parser.add_argument("--manual-code", action="store_true", help="兼容旧参数；验证码始终由用户本人处理")
    parser.add_argument("--check-only", action="store_true", help="只检查 Key 使用天数，不打开浏览器")
    parser.add_argument("--restart", action="store_true", help="写入新 Key 后显式重启本地后端")
    args = parser.parse_args()

    age_days = _key_age_days()
    if age_days is None:
        print("[iflow] Key 使用时间未知，需要人工核对到期日")
    else:
        print(f"[iflow] 当前 Key 已使用约 {age_days} 天")
        if age_days < 5:
            print(f"[iflow] 预计仍有约 {max(0, 7 - age_days)} 天；暂不需要续期")
            if args.check_only:
                return 0

    if args.check_only:
        print("[iflow] 请在到期前运行本脚本完成人工续期")
        return 0

    new_key = renew_key_playwright(manual_code=True)
    if not new_key:
        print(f"[iflow] 未完成续期；请手动访问 {IFLOW_APIKEY_URL}")
        return 1
    if not update_env_key(new_key):
        return 1

    reset_timestamp()
    if args.restart:
        restart_backend()
    else:
        print("[iflow] 配置已更新；未重启生产服务。请在合适窗口按老板手册操作")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
