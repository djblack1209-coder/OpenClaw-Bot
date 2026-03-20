"""
Trading — 环境变量工具
从 trading_system.py 提取的环境变量读取工具
"""
import os


def env_bool(key: str, default: bool) -> bool:
    from src.utils import env_bool as _eb
    return _eb(key, default)


def env_int(key: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return default


def env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default
