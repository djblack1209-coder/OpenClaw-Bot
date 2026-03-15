#!/usr/bin/env python3
"""部署授权服务启动入口 — gunicorn 生产模式 + 日志轮转"""
import logging
import logging.handlers
import os
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

handler = logging.handlers.RotatingFileHandler(
    os.path.join(LOG_DIR, "deploy_server.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s - %(message)s"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    handlers=[handler, logging.StreamHandler()],
)
logger = logging.getLogger("deploy_server")


def main():
    env_path = os.path.join(ROOT, "config", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)

    host = os.getenv("DEPLOY_HOST", "0.0.0.0")
    port = int(os.getenv("DEPLOY_PORT", "18800"))

    # 优先使用 gunicorn（生产），fallback 到 Flask dev server
    try:
        import gunicorn  # noqa: F401
        bind = f"{host}:{port}"
        logger.info(f"部署授权服务启动 (gunicorn): {bind}")
        os.execvp(
            sys.executable,
            [sys.executable, "-m", "gunicorn",
             "src.deployer.deploy_server:app",
             "--bind", bind,
             "--workers", "2",
             "--timeout", "30",
             "--access-logfile", os.path.join(LOG_DIR, "deploy_access.log"),
             "--error-logfile", os.path.join(LOG_DIR, "deploy_error.log"),
             ],
        )
    except ImportError:
        logger.warning("gunicorn 未安装，使用 Flask dev server（不推荐用于生产）")
        from src.deployer.deploy_server import run_server
        run_server(host, port)


if __name__ == "__main__":
    main()
