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


def main():
    _load_env()

    cookies = os.getenv("XIANYU_COOKIES", "")
    if not cookies:
        logger.error("请设置 XIANYU_COOKIES 环境变量（闲鱼网页端 Cookie）")
        sys.exit(1)

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
        logger.info("收到 SIGUSR1，重新加载 Cookie...")
        _load_env()
        new_cookies = os.getenv("XIANYU_COOKIES", "")
        if new_cookies and new_cookies != live.cookies_str:
            live.cookies_str = new_cookies
            live.cookies = __import__("src.xianyu.utils", fromlist=["trans_cookies"]).trans_cookies(new_cookies)
            live.api.session.cookies.update(live.cookies)
            live.myid = live.cookies.get("unb", "")
            live.restart_flag = True
            if live.ws:
                asyncio.get_event_loop().call_soon_threadsafe(live.ws.close)
            logger.info("Cookie 已热更新，正在重连...")
        else:
            logger.info("Cookie 未变化，跳过")

    signal.signal(signal.SIGUSR1, _reload_cookies)

    logger.info("闲鱼 AI 客服启动中... (发送 SIGUSR1 可热更新 Cookie)")
    asyncio.run(live.run())


if __name__ == "__main__":
    main()
