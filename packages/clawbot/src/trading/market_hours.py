"""
Trading — 市场时间工具
美股交易时段判断、日期解析
"""
from datetime import datetime, time
from typing import Optional


def is_us_market_open_now() -> bool:
    """判断当前是否处于美股常规交易时段（美东 09:30-16:00）"""
    from src.utils import now_et
    from src.auto_trader import is_market_holiday

    now = now_et()
    if now.weekday() >= 5:
        return False
    if is_market_holiday(now.date()):
        return False
    market_open = time(9, 30)
    market_close = time(16, 0)
    return market_open <= now.time() <= market_close


def parse_datetime(value) -> Optional[datetime]:
    """安全解析 ISO 格式日期时间"""
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
