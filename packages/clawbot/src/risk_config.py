"""
风控配置与检查结果类型定义

从 risk_manager.py 中提取的数据类，包含：
- RiskConfig: 风控参数配置（单一权威数值来源）
- RiskCheckResult: 风控检查返回结果
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RiskConfig:
    """风控参数配置

    ⚠️ 权威数值来源: 本 dataclass 为运行时真值 (single source of truth)。
    config/omega.yaml investment.risk_rules 必须与此处保持同步。
    bot_profiles.py 风控提示词中的数字也必须匹配。
    修改任一处时，三处都要同步更新。
    """
    # 资金管理
    total_capital: float = 2000.0           # 总资金 (USD) — omega.yaml: total_capital
    max_risk_per_trade_pct: float = 0.02    # 单笔最大风险比例 2% ($40) — omega.yaml: max_risk_per_trade
    daily_loss_limit: float = 100.0         # 日亏损上限 $100 (=5% of $2000) — omega.yaml: daily_loss_limit=0.05

    # 仓位控制
    max_position_pct: float = 0.30          # 单只标的最大仓位 30% — omega.yaml: max_position_single
    max_total_exposure_pct: float = 0.80    # 总敞口上限 80% — omega.yaml: max_total_position
    max_open_positions: int = 5             # 最大同时持仓数

    # 交易质量
    min_risk_reward_ratio: float = 2.0      # 最低风险收益比
    min_signal_score: int = 20              # 最低信号评分（绝对值）

    # 熔断机制
    max_consecutive_losses: int = 3         # 连续亏损熔断阈值
    cooldown_minutes: int = 30              # 熔断冷却时间（分钟）

    # 交易时段（美东时间 9:30-16:00，此处用UTC偏移简化）
    trading_hours_enabled: bool = False     # 是否启用交易时段限制
    trading_start_hour: int = 9             # 开盘小时（本地时间）
    trading_start_minute: int = 30
    trading_end_hour: int = 16
    trading_end_minute: int = 0

    # 标的黑名单
    blacklist: List[str] = field(default_factory=list)

    # 极端行情保护
    volatility_spike_threshold: float = 3.0       # ATR倍数，超过视为波动率飙升
    flash_crash_pct: float = 0.05                 # 单根K线跌幅超过5%视为闪崩
    max_spread_pct: float = 0.02                  # 最大允许买卖价差 (2%)
    circuit_breaker_vix_level: float = 35.0       # VIX超过35暂停新开仓
    extreme_market_cooldown_minutes: int = 60      # 极端事件后冷却时间（分钟）

    # === v2.0 新增：对标 freqtrade ===

    # 动态回撤保护（Drawdown Guard）
    drawdown_window_days: int = 7                 # 滚动窗口天数
    drawdown_warn_pct: float = 0.05              # 回撤5%触发警告（降仓50%）
    drawdown_halt_pct: float = 0.10              # 回撤10%触发停止交易

    # 凯利公式仓位（Kelly Criterion）
    kelly_enabled: bool = True                    # 是否启用凯利公式
    kelly_fraction: float = 0.25                  # 凯利分数（保守系数，0.25=四分之一凯利）
    kelly_min_trades: int = 10                    # 最少交易次数才启用凯利

    # 相关性风险
    max_sector_exposure_pct: float = 0.50         # 同板块最大敞口50%
    correlation_threshold: float = 0.70           # 相关系数>0.7视为高相关

    # 阶梯式熔断（替代一刀切）
    tiered_cooldown_enabled: bool = True          # 启用阶梯式熔断
    tier1_losses: int = 2                         # 连续2笔亏损 -> 仓位减半
    tier2_losses: int = 3                         # 连续3笔亏损 -> 暂停15分钟
    tier3_losses: int = 5                         # 连续5笔亏损 -> 暂停60分钟
    tier1_position_scale: float = 0.5             # 一级降级：仓位缩放到50%
    tier2_cooldown_minutes: int = 15              # 二级降级：冷却15分钟
    tier3_cooldown_minutes: int = 60              # 三级降级：冷却60分钟

    # 滚动窗口风控
    rolling_loss_window_trades: int = 10          # 最近N笔交易的滚动窗口
    rolling_loss_max_pct: float = 0.08            # 滚动窗口最大亏损比例8%

    # 盈利回吐保护（Profit Drawdown Guard）
    profit_drawdown_enabled: bool = True          # 启用盈利回吐保护
    profit_drawdown_pct: float = 0.30             # 浮盈回撤30%触发警告

    # 交易频率限制
    max_trades_per_hour: int = 5                  # 每小时最多交易次数
    max_trades_per_day: int = 20                  # 每日最多交易次数


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    approved: bool                          # 是否通过
    reason: str = ""                        # 拒绝原因
    warnings: List[str] = field(default_factory=list)  # 警告信息
    adjusted_quantity: Optional[float] = None  # 建议调整后的数量
    max_position_value: float = 0           # 允许的最大仓位价值
    max_loss: float = 0                     # 该笔交易最大亏损
    risk_score: int = 0                     # 风险评分 0-100
    market_condition: str = "normal"        # "normal", "elevated", "extreme", "halted"

    def __str__(self) -> str:
        status = "APPROVED" if self.approved else "REJECTED"
        lines = [f"[RiskCheck] {status}"]
        if not self.approved:
            lines.append(f"  Reason: {self.reason}")
        if self.warnings:
            for w in self.warnings:
                lines.append(f"  Warning: {w}")
        if self.adjusted_quantity is not None:
            lines.append(f"  Adjusted qty: {self.adjusted_quantity}")
        lines.append(f"  Max loss: ${self.max_loss:.2f}")
        lines.append(f"  Risk score: {self.risk_score}/100")
        return "\n".join(lines)
