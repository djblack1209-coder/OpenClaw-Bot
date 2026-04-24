"""
ClawBot 自动交易系统集成层 v1.0 — 重导出 shim

本文件保留所有全局状态变量，实现代码已拆分到 src/trading/ 子模块：
  - src/trading/_helpers.py          — 工具函数（环境变量、日期解析等）
  - src/trading/_init_system.py      — init_trading_system + set_ai_team_callers
  - src/trading/_scheduler_tasks.py  — 重型定时任务（成交回写、撤单、重挂等）
  - src/trading/_scheduler_daily.py  — 每日定时任务 + Scheduler 配置
  - src/trading/_lifecycle.py        — 启停、状态恢复、访问器

所有 `from src.trading_system import X` 仍然正常工作。
"""
from collections import OrderedDict

# ============ 全局状态（单一真相源，子模块通过延迟导入访问） ============

_risk_manager = None
_position_monitor = None
_trading_pipeline = None
_auto_trader = None
_scheduler = None
_quote_cache = None
_rebalancer = None
_weekly_guard_last_week_key = ""
_weekly_kill_switch_triggered = False
_pending_reentry_queue: list[dict] = []
_processed_fill_exec_ids = OrderedDict()  # 保持插入顺序，截断时保留最近的
_initialized = False
_ai_team_api_callers: dict = {}  # {bot_id: async callable} — 由 multi_main.py 注入

_PENDING_REENTRY_CONFIG_KEY = "pending_reentry_queue_json"

# ============ 从子模块重导出所有公开 API ============

# 工具函数
from src.trading._helpers import (  # noqa: E402, F401
    _ensure_monitor_position_from_trade,
    _estimate_open_positions_exposure,
    _is_us_market_open_now,
    _load_pending_reentry_queue,
    _parse_datetime,
    _queue_reentry_from_trade,
    _save_pending_reentry_queue,
)

# 初始化
from src.trading._init_system import (  # noqa: E402, F401
    init_trading_system,
    set_ai_team_callers,
)

# 生命周期与访问器
from src.trading._lifecycle import (  # noqa: E402, F401
    get_auto_trader,
    get_position_monitor,
    get_quote_cache,
    get_rebalancer,
    get_risk_manager,
    get_system_status,
    get_trading_pipeline,
    start_trading_system,
    stop_trading_system,
)

# 环境变量工具已统一到 src.utils (消除重复包装函数)
from src.utils import env_bool, env_float, env_int  # noqa: E402, F401
