"""
ClawBot 共享工具函数
避免跨模块重复的样板代码
"""
import logging
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
