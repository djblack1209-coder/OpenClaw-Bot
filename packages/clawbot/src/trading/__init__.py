"""
Trading — 向后兼容门面

Phase 1 拆分:
- trading/env_helpers.py         — 环境变量工具
- trading/market_hours.py        — 市场时间判断
- trading/reentry_queue.py       — 重入队列管理
- trading/position_sync.py       — 仓位同步
- trading/ai_team_integration.py — AI 团队投票集成

Phase 3 新增 (AI 团队量化交易护城河):
- trading/protections.py         — 保护系统 (止损守卫/回撤/冷却/低收益锁定)
- trading/weight_optimizer.py    — Optuna 投票权重优化
- trading/strategy_pipeline.py   — 策略管道连接器 (串联所有组件)

新代码应直接导入子模块:
  from src.trading.strategy_pipeline import StrategyPipeline
  from src.trading.protections import create_default_protections
  from src.trading.weight_optimizer import optimize_weights
"""

from src.trading.env_helpers import env_bool, env_int, env_float
from src.trading.market_hours import is_us_market_open_now, parse_datetime
from src.trading.reentry_queue import (
    load_pending_reentry_queue,
    save_pending_reentry_queue,
    queue_reentry_from_trade,
)
from src.trading.position_sync import (
    estimate_open_positions_exposure,
    ensure_monitor_position_from_trade,
)
from src.trading.ai_team_integration import (
    set_ai_team_callers,
    get_ai_team_callers,
    ai_team_wrapper,
)
from src.trading.protections import (
    ProtectionManager,
    StoplossGuard,
    MaxDrawdownGuard,
    CooldownGuard,
    LowProfitGuard,
    create_default_protections,
)
from src.trading.strategy_pipeline import StrategyPipeline, PipelineCandidate

__all__ = [
    # Phase 1
    "env_bool", "env_int", "env_float",
    "is_us_market_open_now", "parse_datetime",
    "load_pending_reentry_queue", "save_pending_reentry_queue", "queue_reentry_from_trade",
    "estimate_open_positions_exposure", "ensure_monitor_position_from_trade",
    "set_ai_team_callers", "get_ai_team_callers", "ai_team_wrapper",
    # Phase 3
    "ProtectionManager", "StoplossGuard", "MaxDrawdownGuard",
    "CooldownGuard", "LowProfitGuard", "create_default_protections",
    "StrategyPipeline", "PipelineCandidate",
]
