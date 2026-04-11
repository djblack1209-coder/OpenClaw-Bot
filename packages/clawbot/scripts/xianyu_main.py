#!/usr/bin/env python3
"""闲鱼 AI 客服启动入口 — 含日志轮转 + Cookie 热更新"""
import asyncio
import logging
import logging.handlers
import os
import signal
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.xianyu.xianyu_live import XianyuLive

LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 日志轮转：单文件最大 10MB，保留 3 个备份
handler = logging.handlers.RotatingFileHandler(
    os.path.join(LOG_DIR, "xianyu.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s - %(message)s"))

console = logging.StreamHandler()
console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s - %(message)s"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    handlers=[handler, console],
)
logger = logging.getLogger("xianyu_main")


def _load_env():
    env_path = os.path.join(ROOT, "config", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
    elif os.path.exists(".env"):
        load_dotenv(".env", override=True)


def _try_browser_login() -> str:
    """Cookie 为空时弹出浏览器登录，返回获取到的 Cookie 字符串（失败返回空字符串）"""
    script_path = os.path.join(ROOT, "scripts", "xianyu_login.py")
    if not os.path.exists(script_path):
        logger.error("登录脚本不存在: %s", script_path)
        return ""

    logger.info("Cookie 为空，自动弹出浏览器登录页面...")
    logger.info("请用闲鱼/淘宝 APP 扫码登录")

    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True, timeout=660,
            cwd=ROOT,
        )
        if result.returncode == 0:
            # 登录脚本已写入 .env，重新读取
            _load_env()
            new_cookies = os.getenv("XIANYU_COOKIES", "")
            if new_cookies:
                logger.info("浏览器登录成功，Cookie 已获取")
                return new_cookies
            logger.warning("登录脚本执行成功但 Cookie 未写入 .env")
        else:
            logger.warning("浏览器登录未完成 (退出码: %d)", result.returncode)
            if result.stderr:
                logger.debug("登录脚本 stderr: %s", result.stderr[:500])
    except subprocess.TimeoutExpired:
        logger.warning("浏览器登录超时（11 分钟内未完成扫码）")
    except Exception as e:
        logger.error("启动登录浏览器失败: %s", e)

    return ""


def main():
    _load_env()

    cookies = os.getenv("XIANYU_COOKIES", "")
    if not cookies:
        # 没有 Cookie → 直接弹出浏览器让用户扫码登录
        logger.warning("XIANYU_COOKIES 为空，尝试自动弹出浏览器登录...")
        cookies = _try_browser_login()
        if not cookies:
            # 登录失败也不退出，带空 Cookie 启动（cookie_health_loop 会继续尝试弹出登录）
            logger.warning("首次登录未完成，将在后台继续尝试弹出登录窗口...")
            cookies = "placeholder=1"  # 占位值，让进程启动，cookie_health_loop 会检测并重新弹窗

    api_key = os.getenv("XIANYU_LLM_API_KEY", os.getenv("API_KEY", ""))
    if not api_key:
        logger.error("请设置 XIANYU_LLM_API_KEY 或 API_KEY 环境变量")
        sys.exit(1)

    live = XianyuLive(cookies)

    # 启动 Web 管理面板 (后台线程)
    admin_port = int(os.getenv("XIANYU_ADMIN_PORT", "18800"))
    try:
        from src.xianyu.xianyu_admin import start_admin_server
        start_admin_server(
            ctx_manager=live.ctx,
            reply_bot=live.bot,
            live_instance=live,
            port=admin_port,
        )
        logger.info(f"闲鱼管理面板: http://localhost:{admin_port}")
    except Exception as e:
        logger.warning(f"管理面板启动失败 (非致命): {e}")

    # SIGUSR1 热更新 Cookie：kill -USR1 <pid>
    def _reload_cookies(signum, frame):
        """SIGUSR1 信号处理 — 热更新 Cookie 并触发 WebSocket 重连"""
        logger.info("收到 SIGUSR1，重新加载 Cookie...")
        _load_env()
        new_cookies = os.getenv("XIANYU_COOKIES", "")
        if new_cookies and new_cookies != live.cookies_str:
            from src.xianyu.utils import trans_cookies
            live.cookies_str = new_cookies
            live.cookies = trans_cookies(new_cookies)
            # 同步更新 API 客户端的 Cookie（XianyuApis 使用 self.client，不是 self.session）
            live.api.client.cookies.update(live.cookies)
            live.myid = live.cookies.get("unb", "")
            live.restart_flag = True
            if live.ws:
                try:
                    asyncio.get_event_loop().call_soon_threadsafe(live.ws.close)
                except RuntimeError:
                    # 事件循环不可用时，仅设置 restart_flag 让主循环处理
                    logger.debug("事件循环不可用，依赖 restart_flag 重连")
            logger.info("Cookie 已热更新，正在重连...")
        else:
            logger.info("Cookie 未变化，跳过")

    signal.signal(signal.SIGUSR1, _reload_cookies)

    logger.info("闲鱼 AI 客服启动中... (发送 SIGUSR1 可热更新 Cookie)")
    try:
        asyncio.run(live.run())
    finally:
        # 确保关闭底层 HTTP 连接，防止 TCP 泄漏（HI-410）
        try:
            asyncio.run(live.close())
        except RuntimeError:
            # 事件循环已关闭时忽略
            pass


if __name__ == "__main__":
    main()
