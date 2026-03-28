"""
Trading — 美股市场日历
包含美国市场假日计算，用于自动交易系统判断开盘日。
从 auto_trader.py 拆分以改善可维护性。

> 最后更新: 2026-03-28
"""
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# ── exchange-calendars (4.1k⭐) — 替代手写休市日计算 ──────────
# 支持全球 50+ 交易所: NYSE/NASDAQ/SSE/HKEX/LSE/TSX...
# 不可用时降级到原有手写逻辑（零破坏性）
_HAS_XCAL = False
_xcal_nyse = None
try:
    import exchange_calendars as xcals
    _xcal_nyse = xcals.get_calendar("XNYS")  # NYSE
    _HAS_XCAL = True
    logger.debug("[AutoTrader] exchange-calendars 已加载 (XNYS/NYSE)")
except Exception as e:
    logger.info("[AutoTrader] exchange-calendars 未安装，使用内置休市日计算 (pip install exchange-calendars)")


def _env_bool(key: str, default: bool) -> bool:
    from src.utils import env_bool
    return env_bool(key, default)


def _env_int(key: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError) as e:  # noqa: F841
        return default


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm for Easter Sunday."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observe(d: date) -> date:
    """如果假日落在周末，返回观察日（周六→周五，周日→周一）"""
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """第 n 个星期几（weekday: 0=Mon）"""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """某月最后一个星期几"""
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _us_market_holidays(year: int) -> set:
    """动态计算 NYSE 休市日（P1#22: 替代硬编码列表，永不过期）"""
    holidays = set()
    # 元旦
    holidays.add(_observe(date(year, 1, 1)))
    # 马丁·路德·金纪念日 — 1月第3个周一
    holidays.add(_nth_weekday(year, 1, 0, 3))
    # 总统日 — 2月第3个周一
    holidays.add(_nth_weekday(year, 2, 0, 3))
    # 耶稣受难日 — 复活节前的周五
    holidays.add(_easter(year) - timedelta(days=2))
    # 阵亡将士纪念日 — 5月最后一个周一
    holidays.add(_last_weekday(year, 5, 0))
    # 六月节 — 6月19日
    holidays.add(_observe(date(year, 6, 19)))
    # 独立日 — 7月4日
    holidays.add(_observe(date(year, 7, 4)))
    # 劳动节 — 9月第1个周一
    holidays.add(_nth_weekday(year, 9, 0, 1))
    # 感恩节 — 11月第4个周四
    holidays.add(_nth_weekday(year, 11, 3, 4))
    # 圣诞节 — 12月25日
    holidays.add(_observe(date(year, 12, 25)))
    return {d.strftime("%Y-%m-%d") for d in holidays}


def is_market_holiday(date_str: str) -> bool:
    """检查给定日期是否为美股休市日。

    v1.1: 优先用 exchange-calendars (4.1k⭐) — 支持全球50+交易所，
    数据由交易所官方维护，永不遗漏特殊休市日（如飓风/国葬临时休市）。
    不可用时降级到手写计算。
    """
    try:
        import pandas as pd
        ts = pd.Timestamp(date_str)
    except Exception as e:  # noqa: F841
        return False

    # ── 路径1: exchange-calendars（精准，含特殊休市日）──
    if _HAS_XCAL and _xcal_nyse is not None:
        try:
            return not _xcal_nyse.is_session(ts)
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)

    # ── 路径2: 手写计算（降级，不含特殊休市日）──
    try:
        year = int(date_str[:4])
        return date_str in _us_market_holidays(year)
    except (ValueError, IndexError) as e:  # noqa: F841
        return False
