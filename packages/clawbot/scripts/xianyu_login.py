#!/usr/bin/env python3
"""闲鱼 Cookie 自动登录工具 — Playwright 浏览器登录 + Stealth 反检测 + 滑块自动处理

流程：
1. 打开浏览器（注入 stealth 反检测脚本）访问闲鱼登录页
2. 用户用手机扫码登录（或自动处理滑块验证码）
3. 检测到登录成功后自动提取所有 Cookie
4. 写入 config/.env 文件
5. 通知 xianyu_main 进程热更新（SIGUSR1）

使用方式：
  python3 scripts/xianyu_login.py              # 有界面模式（扫码）
  python3 scripts/xianyu_login.py --headless    # 无界面模式（后台静默）
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

    集成 stealth 反检测 + 滑块自动处理。
    headless=True 时完全后台运行，不弹出任何窗口。

    返回 Cookie 字符串，失败返回空字符串。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _log("Playwright 未安装，请执行: pip install playwright && playwright install chromium", quiet)
        return ""

    # 加载滑块求解器
    try:
        from src.xianyu.slider_solver import SliderSolverSync, STEALTH_JS

        slider_solver = SliderSolverSync()
        has_slider_solver = True
        _log("滑块求解器已加载", quiet)
    except ImportError:
        has_slider_solver = False
        STEALTH_JS = ""
        _log("滑块求解器不可用，跳过自动处理", quiet)

    mode_str = "headless 静默" if headless else "有界面"
    _log(f"正在以 {mode_str} 模式打开浏览器...", quiet)

    cookie_str = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        page = context.new_page()

        # 注入 stealth 反检测脚本（在任何页面加载前生效）
        if STEALTH_JS:
            try:
                context.add_init_script(STEALTH_JS)
                _log("Stealth 反检测脚本已注入", quiet)
            except Exception as e:
                _log(f"Stealth 脚本注入失败（非致命）: {e}", quiet)

        # 访问登录页
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        _log("浏览器已打开登录页面，请用手机扫码登录", quiet)

        # 等待登录成功
        start = time.time()
        logged_in = False
        slider_checked = False

        while time.time() - start < LOGIN_TIMEOUT:
            try:
                current_url = page.url

                # 每 5 秒检查一次是否出现滑块（登录过程中可能弹出）
                if has_slider_solver and not slider_checked:
                    if slider_solver.detect_slider(page):
                        _log("检测到滑块验证码，正在自动处理...", quiet)
                        solved = slider_solver.solve(page, max_retries=5)
                        if solved:
                            _log("滑块验证码已自动通过!", quiet)
                        else:
                            _log("滑块自动处理失败，可能需要手动处理", quiet)
                        slider_checked = True
                        # 处理完滑块后重置计时器，给用户更多时间扫码
                        start = time.time()

                # 登录成功判定
                if SUCCESS_DOMAIN in current_url and "login.taobao.com" not in current_url:
                    _log("检测到登录成功，等待 Cookie 同步...", quiet)
                    time.sleep(5)

                    # 登录后也可能出现滑块验证（风控二次验证）
                    if has_slider_solver and slider_solver.detect_slider(page):
                        _log("登录后检测到二次滑块验证，正在处理...", quiet)
                        slider_solver.solve(page, max_retries=5)
                        time.sleep(2)

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
            # 每 10 秒重新检查滑块（可能动态加载）
            if int(time.time() - start) % 10 == 0:
                slider_checked = False

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
                        _log(f"从 hasLogin API 获取到用户 ID: {user_id}", quiet)
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
                        _log(f"从页面获取到用户 ID: {user_id}", quiet)
                except Exception:
                    pass

            # 方法3: 再次获取所有 Cookie（hasLogin 可能触发了新的 Set-Cookie）
            if "unb" not in cookie_dict:
                all_cookies = context.cookies()
                for c in all_cookies:
                    if c["name"] == "unb":
                        cookie_dict["unb"] = c["value"]
                        _log(f"从 Cookie 获取到用户 ID: {c['value']}", quiet)
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
                            _log(f"从本地数据库获取到卖家 ID: {row[0]}", quiet)
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
    _log("=== 闲鱼 Cookie 自动登录工具 ===", quiet)

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

    _log("=== 登录完成，闲鱼客服即将恢复 ===", quiet)
    return True


if __name__ == "__main__":
    quiet = "--quiet" in sys.argv
    headless = "--headless" in sys.argv
    success = run_login(quiet=quiet, headless=headless)
    sys.exit(0 if success else 1)
