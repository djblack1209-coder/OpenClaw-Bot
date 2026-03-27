"""
OpenClaw 日志系统 — 搬运 loguru (23.7k⭐)
拦截 stdlib logging → 路由到 loguru, 零改动现有代码。

特性:
  - 彩色控制台输出 (自动检测 TTY)
  - 结构化 JSON 文件日志 (方便 Phoenix/Langfuse 关联)
  - 自动日志轮转 (10MB/文件, 保留 7 天)
  - 变量全追踪的异常堆栈
  - 模块级过滤 (httpx/litellm 降为 WARNING)

Usage:
    # 在 multi_main.py 顶部调用一次:
    from src.log_config import setup_logging
    setup_logging()
    # 之后所有 logging.getLogger() 自动走 loguru
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# ── Graceful degradation: 没装 loguru 时回退到 stdlib ──────────
try:
    from loguru import logger as _loguru_logger
    _HAS_LOGURU = True
except ImportError:
    _HAS_LOGURU = False
    _loguru_logger = None  # type: ignore[assignment]

__all__ = ["setup_logging", "get_logger"]

# 幂等标记 — 防止多次调用重复安装 handler
_SETUP_DONE = False

# 需要降噪的第三方库 → 最低日志等级
_NOISY_LIBS: dict[str, str] = {
    "httpx": "WARNING",
    "litellm": "WARNING",
    "apscheduler": "WARNING",
    "urllib3": "WARNING",
    "yfinance": "WARNING",
    "ib_insync.wrapper": "WARNING",
    "ib_insync.client": "WARNING",
    "hpack": "WARNING",
    "httpcore": "WARNING",
    "openai": "WARNING",
    "watchfiles": "WARNING",
}

# ── stdlib logging → loguru 桥接 ──────────────────────────────

class InterceptHandler(logging.Handler):
    """
    拦截所有 stdlib logging 调用, 转发到 loguru。

    搬运自 loguru 官方文档推荐模式:
    https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
    """

    def emit(self, record: logging.LogRecord) -> None:
        # 获取对应的 loguru level
        try:
            level = _loguru_logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)

        # 找到实际调用者的栈帧 (跳过 logging 内部帧)
        frame, depth = logging.currentframe(), 0
        while frame is not None:
            filename = frame.f_code.co_filename
            if filename == logging.__file__:
                frame = frame.f_back
                depth += 1
            else:
                break

        _loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _make_module_filter(min_levels: dict[str, str]):
    """创建模块级过滤函数 — 按模块名设置最低日志等级。"""
    # 预计算数值映射
    level_map: dict[str, int] = {}
    for mod, lvl_name in min_levels.items():
        level_map[mod] = logging.getLevelName(lvl_name)

    def _filter(record) -> bool:
        name: str = record.get("name", "")
        for mod, min_no in level_map.items():
            if name == mod or name.startswith(mod + "."):
                # loguru record["level"].no 是 loguru 的等级数值
                return record["level"].no >= min_no
        return True

    return _filter


# ── Public API ────────────────────────────────────────────────

def setup_logging(
    level: str = "INFO",
    json_log_dir: str = "logs/",
    console: bool = True,
) -> None:
    """
    一次性配置全局日志: loguru sinks + stdlib 拦截。

    幂等: 多次调用安全, 不会重复安装 handler。

    Args:
        level: 全局最低日志等级 (DEBUG/INFO/WARNING/ERROR)
        json_log_dir: 日志文件输出目录 (相对于 cwd 或绝对路径)
        console: 是否启用控制台输出
    """
    global _SETUP_DONE
    if _SETUP_DONE:
        return

    if not _HAS_LOGURU:
        # 回退: 用 stdlib 最小化配置, 确保项目仍能运行
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()],
        )
        logging.getLogger(__name__).warning(
            "loguru 未安装, 回退到 stdlib logging。"
            "运行 `pip install loguru>=0.7.0` 启用增强日志。"
        )
        _SETUP_DONE = True
        return

    # ── 1. 清理 loguru 默认 sink (stderr) ──────────────────────
    _loguru_logger.remove()

    # ── 2. 构建模块过滤器 ──────────────────────────────────────
    module_filter = _make_module_filter(_NOISY_LIBS)

    # ── 3. Console sink: 彩色, 人类可读 ────────────────────────
    if console:
        _loguru_logger.add(
            sys.stderr,
            level=level.upper(),
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level:<7}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            filter=module_filter,
            colorize=None,  # 自动检测 TTY
            backtrace=True,
            diagnose=False,
        )

    # ── 4. File sinks ──────────────────────────────────────────
    log_dir = Path(json_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # 4a. JSON 结构化日志 — 方便 Phoenix/Langfuse 关联分析
    _loguru_logger.add(
        str(log_dir / "openclaw_{time}.log"),
        level=level.upper(),
        format="{message}",
        serialize=True,  # JSON 格式
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        filter=module_filter,
        backtrace=True,
        diagnose=False,  # 安全: 防止变量值泄露到日志文件
        encoding="utf-8",
    )

    # 4b. 纯文本错误日志 — 快速 grep 排障
    _loguru_logger.add(
        str(log_dir / "errors_{time}.log"),
        level="ERROR",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | "
            "{name}:{function}:{line} | {message}"
        ),
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        backtrace=True,
        diagnose=False,  # 安全: 防止变量值泄露到日志文件
        encoding="utf-8",
    )

    # ── 5. 拦截 stdlib logging → loguru ────────────────────────
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # 为所有已注册的 logger 也挂上 InterceptHandler
    for name in list(logging.root.manager.loggerDict):
        lib_logger = logging.getLogger(name)
        lib_logger.handlers = [InterceptHandler()]
        lib_logger.propagate = False

    # 对噪声库在 stdlib 层面也设置过滤 (双保险)
    for lib_name, lib_level in _NOISY_LIBS.items():
        logging.getLogger(lib_name).setLevel(
            getattr(logging, lib_level, logging.WARNING)
        )

    _SETUP_DONE = True
    _loguru_logger.info("loguru 日志系统已初始化 (level={}, dir={})", level, log_dir)


def get_logger(name: str):
    """
    获取带 module 绑定的 loguru logger。

    用法:
        from src.log_config import get_logger
        logger = get_logger(__name__)
        logger.info("hello")  # 日志自带 module=xxx 上下文

    Args:
        name: 模块名, 通常传 __name__

    Returns:
        loguru logger (bind(module=name)), 或 stdlib logger 作为回退
    """
    if _HAS_LOGURU and _loguru_logger is not None:
        return _loguru_logger.bind(module=name)
    # 回退
    return logging.getLogger(name)
