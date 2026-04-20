"""
ClawBot 共享工具函数
避免跨模块重复的样板代码
"""
import json
import logging
import os
from datetime import datetime, timezone, timedelta

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


def env_int(key: str, default: int, minimum: int = None) -> int:
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


def emit_flow_event(source: str, target: str, status: str, msg: str, data: dict = None):
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
    event = {
        "source": source,
        "target": target,
        "status": status,
        "msg": msg,
        "data": data or {}
    }
    # 强制绕过普通日志格式化，直接打入日志管道供前端正则解析
    formatted_event = f"__CLAW_FLOW_EVENT__:{json.dumps(event)}"
    logger.debug(formatted_event)
    # 也打入标准日志系统供后台归档
    logging.getLogger("clawbot.flow").info(formatted_event)


# ── 日志脱敏工具 ──────────────────────────────────────

import re as _re

def scrub_secrets(msg: str) -> str:
    """从错误消息中移除 API Key / Token / 内部URL 等敏感信息（HI-462）

    用于 logger.error/warning 中记录异常消息前的预处理。
    覆盖项目实际使用的所有 key 前缀和敏感模式。
    """
    if not isinstance(msg, str):
        msg = str(msg)
    # 清洗 API keys（覆盖项目当前实际使用的主流前缀）
    msg = _re.sub(
        r'(sk-|key-|Key:|Bearer\s+|gsk_|ghp_|github_pat_|AIza|csk-|nvapi-|hf_|m0-)[a-zA-Z0-9_-]{10,}',
        r'\1***REDACTED***', msg
    )
    # 清洗 Authorization header（Basic + Bearer）
    msg = _re.sub(r'(Authorization:\s*(?:Basic|Bearer)\s+)\S+', r'\1***REDACTED***', msg)
    # 清洗 URL 查询参数中的 key/token
    msg = _re.sub(r'(api_key=|token=|key=|api-key=)[a-zA-Z0-9_-]+', r'\1***REDACTED***', msg)
    # 清洗 x-api-key header 值
    msg = _re.sub(r'(x-api-key:\s*)\S+', r'\1***REDACTED***', msg, flags=_re.IGNORECASE)
    # 清洗内部服务 URL（防止暴露 provider 拓扑）
    msg = _re.sub(r'https?://127\.0\.0\.1:\d+[^\s]*', 'http://[internal]', msg)
    msg = _re.sub(r'https?://localhost:\d+[^\s]*', 'http://[internal]', msg)
    # 清洗 Telegram Bot Token（URL 路径中的 /botXXX:YYY/）
    msg = _re.sub(r'/bot\d+:[A-Za-z0-9_-]+/', '/bot***REDACTED***/', msg)
    # 清洗 Cookie 字符串（_m_h5_tk / unb / XSRF-TOKEN 等）
    msg = _re.sub(r'(_m_h5_tk=|unb=|XSRF-TOKEN=|cookie=)[^\s;]+', r'\1***REDACTED***', msg, flags=_re.IGNORECASE)
    # 清洗 SMTP 密码（常见格式 535 Authentication failed for user@xxx）
    msg = _re.sub(r'(Authentication\s+failed\s+for\s+)\S+', r'\1***REDACTED***', msg, flags=_re.IGNORECASE)
    return msg
