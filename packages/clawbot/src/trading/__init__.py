"""
Trading — 向后兼容门面

存活子模块:
- trading/reentry_queue.py       — 重入队列管理
- trading/market_calendar.py     — 市场日历
- trading/_helpers.py            — 辅助函数
- trading/_init_system.py        — 系统初始化
- trading/_lifecycle.py          — 生命周期管理
- trading/_scheduler_daily.py    — 每日调度
- trading/_scheduler_tasks.py    — 任务调度
- trading/valuation_models.py    — 4种估值模型 (DCF/持有人收益/EV-EBITDA/残余收入)
- trading/hurst_analysis.py      — Hurst指数 + 统计套利信号
- trading/master_analysts.py     — 5位投资大师人格Agent

新代码应直接导入子模块:
  from src.trading.reentry_queue import load_pending_reentry_queue
  from src.trading.valuation_models import get_valuation_summary
  from src.trading.hurst_analysis import calculate_hurst_exponent
  from src.trading.master_analysts import run_master_panel
"""

from src.trading.reentry_queue import (
    load_pending_reentry_queue,
    queue_reentry_from_trade,
    save_pending_reentry_queue,
)

__all__ = [
    "load_pending_reentry_queue",
    "queue_reentry_from_trade",
    "save_pending_reentry_queue",
]
