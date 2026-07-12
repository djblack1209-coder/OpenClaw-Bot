#!/usr/bin/env python3
"""闲鱼 Cookie 人工登录助手 — Playwright 可见浏览器 + 登录态提取

流程：
1. 打开可见浏览器访问闲鱼登录页
2. 用户本人扫码并手动完成平台验证码
3. 检测到登录成功后自动提取所有 Cookie
4. 写入 config/.env 文件
5. 通知 xianyu_main 进程热更新（SIGUSR1）

使用方式：
  python3 scripts/xianyu_login.py              # 有界面模式（扫码）
  python3 scripts/xianyu_login.py --headless    # 安全拒绝：登录必须有界面并由用户操作
  python3 scripts/xianyu_login.py --quiet       # 静默模式（被其他脚本调用时）
"""

import os
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Cookie 必须包含的关键字段
REQUIRED_COOKIE_KEYS = {"_m_h5_tk", "_m_h5_tk_enc", "unb", "cna"}

# 登录超时（秒）
LOGIN_TIMEOUT = 600  # 10 分钟

# 闲鱼登录页（redirect 到闲鱼消息页，确保触发完整 session 初始化）
LOGIN_URL = "https://login.taobao.com/member/login.jhtml?redirectURL=https%3A%2F%2Fwww.goofish.com%2Fim"
# 登录成功后应该跳转到的域名
SUCCESS_DOMAIN = "goofish.com"


def _log(msg: str, quiet: bool = False):
    """输出日志（静默模式下只写文件不打印）"""
    if not quiet:
        print(f"[闲鱼登录] {msg}")


def extract_cookies_from_browser(quiet: bool = False, headless: bool = False) -> str:
    """打开浏览器让用户登录闲鱼，登录成功后提取 Cookie。

    只检测验证码，不注入反检测脚本、不自动拖动。
    headless=True 会被安全拒绝，因为账号登录必须由用户本人完成。

    返回 Cookie 字符串，失败返回空字符串。
    """
    if headless:
        _log("headless 模式已禁用：账号登录和验证码必须由用户在可见浏览器中完成", quiet)
        return ""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _log("Playwright 未安装，请执行: pip install playwright && playwright install chromium", quiet)
        return ""

    # 只加载验证码检测器，不执行自动求解。
    try:
        from src.xianyu.slider_solver import SliderSolverSync

        slider_solver = SliderSolverSync()
        has_slider_solver = True
        _log("验证码检测器已加载", quiet)
    except ImportError:
        has_slider_solver = False
        slider_solver = None
        _log("验证码检测器不可用；仍需在浏览器中手动完成平台验证", quiet)

    _log("正在打开可见浏览器...", quiet)

    cookie_str = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = context.new_page()

        # 访问登录页
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        _log("浏览器已打开登录页面，请用手机扫码登录", quiet)

        # 等待登录成功
        start = time.time()
        logged_in = False
        captcha_notified = False

        while time.time() - start < LOGIN_TIMEOUT:
            captcha_visible = False
            try:
                current_url = page.url

                # 检测到验证码后只提醒，不模拟轨迹、不自动拖动。
                captcha_visible = bool(
                    has_slider_solver
                    and slider_solver is not None
                    and slider_solver.detect_slider(page)
                )
                if captcha_visible and not captcha_notified:
                    _log("检测到平台验证码，请在浏览器中手动完成；自动化已暂停", quiet)
                    captcha_notified = True

                # 登录成功判定
                if SUCCESS_DOMAIN in current_url and "login.taobao.com" not in current_url:
                    _log("检测到登录成功，等待 Cookie 同步...", quiet)
                    time.sleep(5)

                    # 登录后仍出现验证码时继续等待人工完成，不能提取半成品登录态。
                    if captcha_visible:
                        time.sleep(1)
                        continue

                    # 访问闲鱼消息页面触发 session 初始化
                    if "/im" not in current_url:
                        page.goto("https://www.goofish.com/im", wait_until="domcontentloaded")
                        time.sleep(5)

                    # 访问淘宝域名获取 unb 等 Cookie
                    page.goto("https://2.taobao.com/", wait_until="domcontentloaded")
                    time.sleep(2)

                    logged_in = True
                    break
            except Exception:
                pass

            time.sleep(1)
            if not captcha_visible:
                captcha_notified = False

        if not logged_in:
            _log("登录超时（10分钟内未完成），请重试", quiet)
            browser.close()
            return ""

        # 提取 Cookie（区分域名，优先使用 goofish 域名的值）
        all_cookies = context.cookies()

        # 按域名分组，goofish 域名优先
        goofish_cookies = {}
        taobao_cookies = {}
        other_cookies = {}
        for c in all_cookies:
            domain = c.get("domain", "")
            if "goofish" in domain:
                goofish_cookies[c["name"]] = c["value"]
            elif "taobao" in domain or "tbcdn" in domain:
                taobao_cookies[c["name"]] = c["value"]
            else:
                other_cookies[c["name"]] = c["value"]

        # 合并：其他 → 淘宝 → 闲鱼（闲鱼优先级最高，覆盖同名的）
        cookie_dict = {}
        cookie_dict.update(other_cookies)
        cookie_dict.update(taobao_cookies)
        cookie_dict.update(goofish_cookies)

        _log(
            f"Cookie 来源: goofish={len(goofish_cookies)}, taobao={len(taobao_cookies)}, other={len(other_cookies)}",
            quiet,
        )

        # 在浏览器中调用一次 Token API，让服务端设置正确的 _m_h5_tk
        try:
            page.goto("https://www.goofish.com/", wait_until="domcontentloaded")
            time.sleep(2)
            # 触发一次 API 调用来获取正确域名的 _m_h5_tk（使用 gaia API 更可靠）
            page.evaluate("""() => {
                const data = JSON.stringify({bizScene: 'home'});
                const t = Date.now();
                const params = new URLSearchParams({
                    jsv: '2.7.2',
                    appKey: '34839810',
                    t: t,
                    sign: 'placeholder',
                    v: '1.0',
                    type: 'originaljson',
                    dataType: 'json',
                    timeout: '20000',
                    api: 'mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get',
                    data: data
                });
                return fetch('https://h5api.m.goofish.com/h5/mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get/1.0/?' + params, {
                    method: 'POST', credentials: 'include',
                }).then(r => r.text()).catch(() => '');
            }""")
            time.sleep(3)
            # 重新获取 Cookie（可能更新了 _m_h5_tk）
            all_cookies = context.cookies()
            for c in all_cookies:
                domain = c.get("domain", "")
                if "goofish" in domain or "taobao" in domain:
                    cookie_dict[c["name"]] = c["value"]
            _log(f"触发 API 后获取到 {len(cookie_dict)} 个 Cookie 字段", quiet)
        except Exception as e:
            _log(f"触发 API 获取 h5_tk 失败（非致命）: {e}", quiet)

        # 验证必须字段
        missing = REQUIRED_COOKIE_KEYS - set(cookie_dict.keys())
        if missing:
            _log(f"登录成功但缺少关键 Cookie 字段: {missing}", quiet)
            # unb 可能在淘宝域名的 Cookie 中，尝试多个域名
            for url in [
                "https://login.taobao.com/member/login_status.do",
                "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/?jsv=2.7.4&appKey=34839810&sign=placeholder&type=originaljson",
            ]:
                try:
                    page.goto(url, wait_until="domcontentloaded")
                    time.sleep(2)
                except Exception:
                    pass
            all_cookies = context.cookies()
            for c in all_cookies:
                cookie_dict[c["name"]] = c["value"]

            # 如果 unb 仍然缺失，尝试从 API 和页面获取用户 ID
            if "unb" not in cookie_dict:
                try:
                    # 方法1: 调用 hasLogin API，从响应中提取 UID
                    page.goto("https://www.goofish.com/", wait_until="domcontentloaded")
                    time.sleep(1)
                    user_id = page.evaluate("""() => {
                        return new Promise((resolve) => {
                            fetch('https://passport.goofish.com/newlogin/hasLogin.do?appName=xianyu&fromSite=77', {
                                method: 'POST',
                                credentials: 'include',
                                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                                body: 'appName=xianyu&appEntrance=web&fromSite=77&defaultView=hasLogin'
                            })
                            .then(r => r.json())
                            .then(data => {
                                const uid = data?.content?.data?.uidStr || data?.content?.data?.uid || '';
                                resolve(String(uid));
                            })
                            .catch(() => resolve(''));
                        });
                    }""")
                    if user_id:
                        cookie_dict["unb"] = user_id
                        _log("已从登录状态补齐用户标识（不显示具体值）", quiet)
                except Exception as e:
                    _log(f"hasLogin API 获取 UID 失败: {e}", quiet)

            # 方法2: 从页面 JS 全局变量获取
            if "unb" not in cookie_dict:
                try:
                    user_id = page.evaluate("""() => {
                        try {
                            // 尝试多个全局变量位置
                            return window.__NEXT_DATA__?.props?.initialState?.userInfo?.userId
                                || window.g_config?.userId
                                || window._global?.userId
                                || document.cookie.match(/unb=(\\d+)/)?.[1]
                                || '';
                        } catch(e) { return ''; }
                    }""")
                    if user_id:
                        cookie_dict["unb"] = str(user_id)
                        _log("已从页面补齐用户标识（不显示具体值）", quiet)
                except Exception:
                    pass

            # 方法3: 再次获取所有 Cookie（hasLogin 可能触发了新的 Set-Cookie）
            if "unb" not in cookie_dict:
                all_cookies = context.cookies()
                for c in all_cookies:
                    if c["name"] == "unb":
                        cookie_dict["unb"] = c["value"]
                        _log("已从 Cookie 补齐用户标识（不显示具体值）", quiet)
                        break

            # 方法4: 从闲鱼本地数据库获取历史卖家 ID
            if "unb" not in cookie_dict:
                try:
                    import sqlite3

                    db_path = os.path.join(ROOT, "data", "xianyu_chat.db")
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        row = conn.execute("SELECT DISTINCT user_id FROM consultations LIMIT 1").fetchone()
                        if row and row[0]:
                            cookie_dict["unb"] = str(row[0])
                            _log("已从本地状态补齐卖家标识（不显示具体值）", quiet)
                        conn.close()
                except Exception as e:
                    _log(f"从数据库获取卖家 ID 失败: {e}", quiet)

            missing = REQUIRED_COOKIE_KEYS - set(cookie_dict.keys())
            if missing:
                _log(f"仍缺少: {missing}，Cookie 可能不完整，继续尝试使用", quiet)

        # 构建 Cookie 字符串
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
        _log(f"已提取 {len(cookie_dict)} 个 Cookie 字段", quiet)

        browser.close()

    return cookie_str


def save_cookies_to_env(cookie_str: str, quiet: bool = False) -> bool:
    """将 Cookie 写入 config/.env 文件"""
    from src.xianyu.cookie_refresher import update_env_file

    try:
        update_env_file(cookie_str)
        _log("Cookie 已写入 config/.env", quiet)
        return True
    except Exception as e:
        _log(f"写入 .env 失败: {e}", quiet)
        return False


def notify_xianyu_process(quiet: bool = False) -> bool:
    """向 xianyu_main 进程发送 SIGUSR1 信号触发 Cookie 热更新"""
    try:
        result = subprocess.run(["pgrep", "-f", "xianyu_main"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                pid = pid.strip()
                if pid:
                    os.kill(int(pid), signal.SIGUSR1)
                    _log(f"已通知闲鱼进程 (PID={pid}) 热更新 Cookie", quiet)
            return True
        else:
            _log("未找到运行中的闲鱼进程，Cookie 将在下次启动时生效", quiet)
            return False
    except Exception as e:
        _log(f"通知闲鱼进程失败: {e}", quiet)
        return False


def run_login(quiet: bool = False, headless: bool = False) -> bool:
    """完整登录流程：浏览器登录 → 提取Cookie → 写入.env → 热更新"""
    _log("=== 闲鱼 Cookie 人工登录助手 ===", quiet)

    # 1. 浏览器登录 + Cookie 提取
    cookie_str = extract_cookies_from_browser(quiet=quiet, headless=headless)
    if not cookie_str:
        _log("Cookie 获取失败", quiet)
        return False

    # 2. 写入 .env
    if not save_cookies_to_env(cookie_str, quiet=quiet):
        return False

    # 3. 验证 Cookie 是否真的有效
    _log("正在验证 Cookie 有效性...", quiet)
    try:
        import httpx as _httpx

        _cookies = {}
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                _cookies[k.strip()] = v.strip()
        with _httpx.Client(timeout=15, follow_redirects=True) as _client:
            _resp = _client.post(
                "https://passport.goofish.com/newlogin/hasLogin.do",
                params={"appName": "xianyu", "fromSite": "77"},
                data={
                    "hid": _cookies.get("unb", ""),
                    "ltl": "true",
                    "appName": "xianyu",
                    "appEntrance": "web",
                    "_csrf_token": _cookies.get("XSRF-TOKEN", ""),
                    "fromSite": "77",
                    "documentReferer": "https://www.goofish.com/",
                    "defaultView": "hasLogin",
                    "deviceId": _cookies.get("cna", ""),
                },
                cookies=_cookies,
            )
            _rj = _resp.json()
            _rc = _rj.get("content", {}).get("data", {}).get("resultCode")
            if _rc == 100:
                _log("⚠️  Cookie 已写入但服务端报告登录态失效(resultCode=100)，可能需要重新扫码", quiet)
            else:
                _log("✅ Cookie 验证通过，登录态有效", quiet)
    except Exception as _e:
        _log(f"验证请求失败（非致命）: {_e}", quiet)

    # 4. 通知闲鱼进程热更新
    notify_xianyu_process(quiet=quiet)

    _log("=== 登录凭据已更新；发货、确认收货等高风险动作仍保持人工闸门 ===", quiet)
    return True


if __name__ == "__main__":
    quiet = "--quiet" in sys.argv
    headless = "--headless" in sys.argv
    success = run_login(quiet=quiet, headless=headless)
    sys.exit(0 if success else 1)
