"""
ClawBot 共享工具函数
避免跨模块重复的样板代码
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")
    except ImportError:
        _ET = None
        logger.warning("[utils] zoneinfo 不可用，将使用 UTC-5 降级")

# 固定 UTC-5 偏移，作为 ZoneInfo 不可用时的降级方案
_UTC_MINUS_5 = timezone(timedelta(hours=-5))


def now_et() -> datetime:
    """获取美东时间 now()，ZoneInfo 不可用时降级为 UTC-5"""
    if _ET is not None:
        try:
            return datetime.now(_ET)
        except Exception as e:
            logger.error("[utils] ZoneInfo 失败，降级 UTC-5: %s", e)
    return datetime.now(_UTC_MINUS_5)


def today_et_str(fmt: str = "%Y-%m-%d") -> str:
    """获取美东时间今日日期字符串"""
    return now_et().strftime(fmt)


# ============ 环境变量工具 ============


def env_bool(key: str, default: bool) -> bool:
    """从环境变量读取布尔值，支持 1/true/yes/on"""
    raw = os.getenv(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def env_int(key: str, default: int, minimum: int | None = None) -> int:
    """从环境变量读取整数，支持可选最小值限制"""
    raw = os.getenv(key)
    if raw is None:
        val = default
    else:
        try:
            val = int(raw)
        except (TypeError, ValueError):
            val = default
    if minimum is not None:
        val = max(minimum, val)
    return val


def env_float(key: str, default: float) -> float:
    """从环境变量读取浮点数"""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError) as e:  # noqa: F841
        return default


def emit_flow_event(source: str, target: str, status: str, msg: str, data: dict | None = None):
    """
    通过日志流向 Tauri 前端广播执行图状态
    格式规范必须严格遵守前缀 __CLAW_FLOW_EVENT__

    参数:
      source: 起始节点 ID (例如 "hub")
      target: 目标节点 ID (例如 "llm")
      status: 状态 ("pending" | "running" | "success" | "failed")
      msg: 简短的描述信息
      data: 附加的调试或上下文数据字典
    """
    from src.observability_policy import ObservabilityPolicy, redact_text, safe_label

    event = {
        "source": safe_label(source),
        "target": safe_label(target),
        "status": safe_label(status),
        "msg": redact_text(msg),
        "data": ObservabilityPolicy.from_environment().metadata(data or {})
    }
    # 强制绕过普通日志格式化，直接打入日志管道供前端正则解析
    formatted_event = f"__CLAW_FLOW_EVENT__:{json.dumps(event)}"
    logger.debug(formatted_event)
    # 也打入标准日志系统供后台归档
    logging.getLogger("clawbot.flow").info(formatted_event)


# ── 日志脱敏工具 ──────────────────────────────────────

def scrub_secrets(msg: str) -> str:
    """Use the shared bounded telemetry policy; never stringify unknown objects."""
    from src.observability_policy import redact_text

    return redact_text(msg)
