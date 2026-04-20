#!/usr/bin/env python3
"""
iFlow API Key 自动续期脚本

流程:
  1. Playwright 打开 iFlow 登录页
  2. 输入手机号 → 通过阿里云滑动验证 → 发送短信
  3. 从 macOS Messages 数据库自动读取验证码
  4. 登录 → 导航到 API Key 页面 → 重新生成 Key
  5. 更新 .env 文件 + 重置过期计时器

用法:
  python scripts/iflow_key_renew.py              # 全自动模式
  python scripts/iflow_key_renew.py --manual-code # 手动输入验证码模式

定时触发: 由 ExecutionScheduler 在 key 使用第 6 天自动调用
"""

import argparse
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 反检测：playwright_stealth（可选）
try:
    from playwright_stealth import stealth_sync
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

# 滑块验证码识别：ddddocr（可选）
try:
    import ddddocr
    HAS_DDDDOCR = True
except ImportError:
    HAS_DDDDOCR = False


# ============================================================
# 配置
# ============================================================

PHONE_NUMBER = "18291555529"
IFLOW_LOGIN_URL = "https://platform.iflow.cn/login"
IFLOW_APIKEY_URL = "https://platform.iflow.cn/docs/api-key-management"
ENV_FILE = Path(__file__).parent.parent / "config" / ".env"
TIMESTAMP_FILE = Path.home() / ".openclaw" / "iflow_key_timestamp.json"
MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"


# ============================================================
# macOS 短信读取
# ============================================================

def read_latest_sms_code(phone: str = PHONE_NUMBER, max_age_seconds: int = 300) -> str | None:
    """从 macOS Messages 数据库读取最近的短信验证码

    Args:
        phone: 发送验证码的手机号（用于过滤）
        max_age_seconds: 最多读取多少秒前的短信

    Returns:
        提取到的验证码字符串，或 None
    """
    if not MESSAGES_DB.exists():
        print("[iflow] ⚠️ macOS 短信数据库不存在")
        return None

    try:
        # macOS Messages 的时间基准是 2001-01-01 00:00:00 UTC
        # 需要转换为 Core Data 时间戳（纳秒）
        epoch_offset = 978307200  # 2001-01-01 的 Unix 时间戳
        min_time = (time.time() - max_age_seconds - epoch_offset) * 1_000_000_000

        conn = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
        cursor = conn.cursor()

        # 查询最近的短信，按时间倒序
        cursor.execute("""
            SELECT m.text, m.date
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.date > ?
              AND m.is_from_me = 0
              AND m.text IS NOT NULL
            ORDER BY m.date DESC
            LIMIT 10
        """, (int(min_time),))

        for text, _ in cursor.fetchall():
            if not text:
                continue
            # 提取 4-8 位数字验证码
            match = re.search(r'(?:验证码|code)[：:\s]*(\d{4,8})', text, re.IGNORECASE)
            if match:
                code = match.group(1)
                print(f"[iflow] ✅ 从短信中提取到验证码: {code}")
                conn.close()
                return code
            # 备选：纯数字匹配（短信只包含一个 4-6 位数字）
            match = re.search(r'\b(\d{4,6})\b', text)
            if match and ('iflow' in text.lower() or '硅基' in text or '验证' in text):
                code = match.group(1)
                print(f"[iflow] ✅ 从短信中提取到验证码: {code}")
                conn.close()
                return code

        conn.close()
    except Exception as e:
        print(f"[iflow] ⚠️ 读取短信失败: {e}")

    return None


def wait_for_sms_code(timeout: int = 60, poll_interval: int = 3) -> str | None:
    """轮询等待短信验证码到达

    Args:
        timeout: 最大等待时间（秒）
        poll_interval: 轮询间隔（秒）

    Returns:
        验证码字符串，或 None（超时）
    """
    print(f"[iflow] 等待短信验证码（最多 {timeout} 秒）...")
    start = time.time()
    while time.time() - start < timeout:
        code = read_latest_sms_code(max_age_seconds=timeout)
        if code:
            return code
        time.sleep(poll_interval)

    print("[iflow] ⚠️ 等待短信超时")
    return None


# ============================================================
# .env 文件更新
# ============================================================

def update_env_key(new_key: str) -> bool:
    """更新 .env 文件中的 SILICONFLOW_UNLIMITED_KEY"""
    if not ENV_FILE.exists():
        print(f"[iflow] ❌ .env 文件不存在: {ENV_FILE}")
        return False

    content = ENV_FILE.read_text()
    pattern = r'SILICONFLOW_UNLIMITED_KEY=.*'
    if not re.search(pattern, content):
        print("[iflow] ❌ .env 中未找到 SILICONFLOW_UNLIMITED_KEY")
        return False

    new_content = re.sub(pattern, f'SILICONFLOW_UNLIMITED_KEY={new_key}', content)
    ENV_FILE.write_text(new_content)
    print(f"[iflow] ✅ .env 已更新为新 Key: {new_key[:10]}...{new_key[-6:]}")
    return True


def reset_timestamp():
    """重置 iFlow key 时间戳（标记为刚刚续期）"""
    TIMESTAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "key_first_used": datetime.now().isoformat(),
        "renewed_at": datetime.now().isoformat(),
    }
    TIMESTAMP_FILE.write_text(json.dumps(data, indent=2))
    print(f"[iflow] ✅ 时间戳已重置: {TIMESTAMP_FILE}")


# ============================================================
# 滑块拖动辅助函数
# ============================================================

def human_like_drag(page, slider_box, distance):
    """模拟人类拖动轨迹：加速→匀速→减速+微抖动"""
    start_x = slider_box["x"] + slider_box["width"] / 2
    start_y = slider_box["y"] + slider_box["height"] / 2

    page.mouse.move(start_x, start_y)
    page.mouse.down()

    # 生成轨迹点
    steps = random.randint(15, 25)
    for i in range(steps):
        progress = (i + 1) / steps
        # 缓入缓出 easing
        eased = progress * progress * (3 - 2 * progress)
        x = start_x + distance * eased + random.uniform(-2, 2)
        y = start_y + random.uniform(-3, 3)
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.01, 0.04))

    # 最后微调到精确位置
    page.mouse.move(start_x + distance, start_y)
    time.sleep(random.uniform(0.1, 0.3))
    page.mouse.up()


# ============================================================
# Playwright 自动化
# ============================================================

def renew_key_playwright(manual_code: bool = False) -> str | None:
    """使用 Playwright 自动化续期 iFlow API Key

    Args:
        manual_code: True 则手动输入验证码，False 则从短信自动读取

    Returns:
        新的 API Key，或 None（失败）
    """
    from playwright.sync_api import sync_playwright

    print("[iflow] 🚀 启动 Playwright 自动续期...")

    with sync_playwright() as p:
        # 启动浏览器（有头模式，方便调试滑动验证）
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = context.new_page()

        # 反指纹检测（如果 playwright_stealth 可用）
        if HAS_STEALTH:
            stealth_sync(page)
            print("[iflow]   已启用 playwright_stealth 反检测")

        try:
            # 步骤 1: 打开登录页
            print("[iflow] 1/6 打开登录页...")
            page.goto(IFLOW_LOGIN_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)

            # 步骤 2: 输入手机号
            print("[iflow] 2/6 输入手机号...")
            phone_input = page.locator('input[placeholder*="手机号"], input[type="tel"], input[name*="phone"]').first
            if phone_input.count() == 0:
                # 备选定位
                phone_input = page.locator('input').first
            phone_input.fill(PHONE_NUMBER)
            time.sleep(1)

            # 步骤 3: 通过阿里云滑动验证（如果有的话）
            print("[iflow] 3/6 处理滑动验证...")
            # 阿里云滑动验证通常在一个 iframe 或特定 div 中
            # 尝试查找并点击触发
            captcha_btn = page.locator('text=点击按住滑块, text=滑动验证, [class*="captcha"], [id*="captcha"]').first
            if captcha_btn.count() > 0:
                captcha_btn.click()
                time.sleep(2)
                # 尝试拖动滑块
                slider = page.locator('[class*="slider"], [class*="btn_slide"]').first
                if slider.count() > 0:
                    box = slider.bounding_box()
                    if box:
                        if HAS_DDDDOCR:
                            # 使用 ddddocr 精确计算滑动距离
                            print("[iflow]   使用 ddddocr 计算滑动距离...")
                            try:
                                # 截取验证码背景图和滑块图
                                bg_el = page.locator('[class*="bg"], [class*="background"], canvas').first
                                target_el = page.locator('[class*="target"], [class*="puzzle"], [class*="slice"]').first
                                bg_bytes = bg_el.screenshot() if bg_el.count() > 0 else page.screenshot()
                                target_bytes = target_el.screenshot() if target_el.count() > 0 else None

                                if target_bytes:
                                    ocr = ddddocr.DdddOcr()
                                    result = ocr.slide_match(target_bytes, bg_bytes)
                                    distance = result.get("target", [0])[0]
                                    print(f"[iflow]   ddddocr 计算滑动距离: {distance}px")
                                    human_like_drag(page, box, distance)
                                else:
                                    # 无法获取滑块截图，使用默认距离 + 人类轨迹
                                    print("[iflow]   未找到滑块元素截图，使用默认距离")
                                    human_like_drag(page, box, 300)
                            except Exception as e:
                                print(f"[iflow]   ddddocr 识别失败: {e}，使用默认距离")
                                human_like_drag(page, box, 300)
                        else:
                            # 无 ddddocr，使用人类轨迹拖动默认距离
                            print("[iflow]   ddddocr 未安装，使用默认距离拖动")
                            human_like_drag(page, box, 300)
                        time.sleep(2)
                        print("[iflow]   滑动验证完成")
            else:
                print("[iflow]   未检测到滑动验证，跳过")

            # 步骤 4: 点击发送验证码
            print("[iflow] 4/6 发送验证码...")
            send_btn = page.locator('text=发送验证码, text=获取验证码, text=发送, button:has-text("验证码")').first
            if send_btn.count() > 0:
                send_btn.click()
                print("[iflow]   验证码已发送")
                time.sleep(3)
            else:
                print("[iflow]   ⚠️ 未找到发送验证码按钮，可能需要先完成滑动验证")
                # 截图保存现场
                page.screenshot(path="/tmp/iflow_renew_debug.png")
                print("[iflow]   截图已保存到 /tmp/iflow_renew_debug.png")

            # 步骤 5: 获取验证码
            if manual_code:
                code = input("[iflow] 请输入收到的验证码: ").strip()
            else:
                code = wait_for_sms_code(timeout=60)

            if not code:
                print("[iflow] ❌ 未获取到验证码，续期失败")
                page.screenshot(path="/tmp/iflow_renew_failed.png")
                browser.close()
                return None

            # 输入验证码
            code_input = page.locator('input[placeholder*="验证码"], input[name*="code"], input[type="number"]').first
            if code_input.count() == 0:
                code_input = page.locator('input').nth(1)
            code_input.fill(code)
            time.sleep(1)

            # 点击登录
            login_btn = page.locator('text=登录, text=Login, button[type="submit"]').first
            if login_btn.count() > 0:
                login_btn.click()
                time.sleep(3)

            # 步骤 6: 导航到 API Key 页面并重新生成
            print("[iflow] 5/6 导航到 API Key 管理...")
            page.goto(IFLOW_APIKEY_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)

            # 查找当前 Key 或重新生成按钮
            regenerate_btn = page.locator(
                'text=重新生成, text=重置, text=生成新Key, text=Regenerate, '
                'button:has-text("生成"), button:has-text("重置")'
            ).first

            if regenerate_btn.count() > 0:
                regenerate_btn.click()
                time.sleep(1)
                # 可能有确认弹窗
                confirm_btn = page.locator('text=确认, text=确定, text=OK').first
                if confirm_btn.count() > 0:
                    confirm_btn.click()
                    time.sleep(2)

            # 读取新 Key
            print("[iflow] 6/6 读取新 API Key...")
            # 尝试从页面元素中提取 sk- 开头的 key
            page_text = page.content()
            key_match = re.search(r'(sk-[a-f0-9]{32,})', page_text)
            if key_match:
                new_key = key_match.group(1)
                print(f"[iflow] ✅ 获取到新 Key: {new_key[:10]}...{new_key[-6:]}")
                browser.close()
                return new_key
            else:
                # 尝试从 input/textarea 中读取
                key_elements = page.locator('input[value*="sk-"], [data-key], code:has-text("sk-")')
                for i in range(key_elements.count()):
                    val = key_elements.nth(i).get_attribute("value") or key_elements.nth(i).text_content()
                    if val and val.startswith("sk-"):
                        print(f"[iflow] ✅ 获取到新 Key: {val[:10]}...{val[-6:]}")
                        browser.close()
                        return val

                print("[iflow] ⚠️ 未能自动提取新 Key，请手动复制")
                page.screenshot(path="/tmp/iflow_renew_key_page.png")
                print("[iflow]   截图已保存到 /tmp/iflow_renew_key_page.png")
                # 等用户手动操作
                new_key_input = input("[iflow] 请手动粘贴新 Key (sk-...): ").strip()
                browser.close()
                return new_key_input if new_key_input.startswith("sk-") else None

        except Exception as e:
            print(f"[iflow] ❌ 自动化执行出错: {e}")
            try:
                page.screenshot(path="/tmp/iflow_renew_error.png")
                print("[iflow]   错误截图已保存到 /tmp/iflow_renew_error.png")
            except:
                pass
            browser.close()
            return None


# ============================================================
# 后端重启
# ============================================================

def restart_backend():
    """重启 clawbot 后端使新 key 生效"""
    print("[iflow] 🔄 重启后端加载新 Key...")
    try:
        subprocess.run(["launchctl", "stop", "ai.openclaw.clawbot-agent"], check=False)
        time.sleep(3)
        # LaunchAgent 会自动重启
        print("[iflow] ✅ 后端已重启（LaunchAgent 会自动拉起）")
    except Exception as e:
        print(f"[iflow] ⚠️ 重启失败: {e}")


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="iFlow API Key 自动续期")
    parser.add_argument("--manual-code", action="store_true", help="手动输入验证码（不从短信自动读取）")
    parser.add_argument("--check-only", action="store_true", help="仅检查是否需要续期")
    parser.add_argument("--restart", action="store_true", help="续期后自动重启后端")
    args = parser.parse_args()

    print("=" * 50)
    print("  iFlow API Key 自动续期")
    print(f"  手机号: {PHONE_NUMBER}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 检查是否需要续期
    if TIMESTAMP_FILE.exists():
        data = json.loads(TIMESTAMP_FILE.read_text())
        first_used = datetime.fromisoformat(data.get("key_first_used", datetime.now().isoformat()))
        age_days = (datetime.now() - first_used).days
        print(f"[iflow] 当前 Key 已使用 {age_days} 天")

        if age_days < 5:
            print(f"[iflow] Key 还有 {7 - age_days} 天才过期，暂不需要续期")
            if args.check_only:
                return
            else:
                confirm = input("[iflow] 仍要续期吗? (y/N): ").strip().lower()
                if confirm != 'y':
                    return
    else:
        print("[iflow] 未找到时间戳文件，无法判断 Key 年龄")

    if args.check_only:
        print("[iflow] 建议尽快续期")
        return

    # 执行续期
    new_key = renew_key_playwright(manual_code=args.manual_code)

    if new_key:
        # 更新 .env
        if update_env_key(new_key):
            reset_timestamp()
            print("[iflow] 🎉 续期完成！")

            if args.restart:
                restart_backend()
        else:
            print("[iflow] ❌ 更新 .env 失败")
    else:
        print("[iflow] ❌ 续期失败，请手动操作")
        print(f"[iflow] 手动操作地址: {IFLOW_APIKEY_URL}")


if __name__ == "__main__":
    main()
