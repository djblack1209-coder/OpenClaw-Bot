"""
风控 Validator 链式架构

借鉴 rqalpha 的 Validator 链模式:
- 每项风控检查封装为独立的 Validator 类
- Validator 链按顺序执行，任何一个 reject 即终止
- 支持动态注册/移除 Validator（运行时可插拔）
- 对外接口完全不变（check_trade() 签名不变）

优势（对比原来的巨型 if-else 链）:
  1. 新增检查只需新建 Validator 类 + 注册，无需改 check_trade()
  2. 每个 Validator 可独立测试
  3. 可按场景启用/禁用特定检查（如回测模式跳过交易时段检查）
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import timedelta

from src.risk_config import RiskCheckResult
from src.utils import now_et, scrub_secrets

logger = logging.getLogger(__name__)


# ── Validator 基类 ──────────────────────────────────────


@dataclass
class ValidatorContext:
    """传递给每个 Validator 的上下文"""

    symbol: str
    side: str  # BUY / SELL
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    signal_score: int
    current_positions: list[dict]
    # 由 RiskManager 填充的运行时状态
    config: object = None  # RiskConfig
    today_pnl: float = 0.0
    consecutive_losses: int = 0
    position_scale: float = 1.0
    current_tier: int = 0
    rolling_pnl: list = field(default_factory=list)
    trade_history: list = field(default_factory=list)
    peak_capital: float = 0.0
    # 中间结果（Validator 间传递）
    adjusted_quantity: float | None = None
    warnings: list[str] = field(default_factory=list)


class RiskValidator(ABC):
    """风控校验器基类 — 借鉴 rqalpha Frontend Validator 模式"""

    @property
    @abstractmethod
    def name(self) -> str:
        """校验器名称（用于日志和调试）"""
        ...

    @property
    def order(self) -> int:
        """执行顺序（越小越先执行，默认100）"""
        return 100

    @abstractmethod
    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        """
        执行校验

        返回:
            None — 通过（继续下一个 Validator）
            (False, "原因") — 拒绝交易
            不会返回 (True, ...) — 通过就返回 None
        """
        ...


# ── 内置 Validator 实现 ──────────────────────────────


class ParameterValidator(RiskValidator):
    """检查-1: 参数合法性"""

    name = "参数合法性"
    order = 0

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        if ctx.entry_price <= 0:
            return (False, f"入场价必须大于零 (got {ctx.entry_price})")
        if ctx.quantity <= 0:
            return (False, f"交易数量必须大于零 (got {ctx.quantity})")
        return None


class BlacklistValidator(RiskValidator):
    """检查0: 黑名单"""

    name = "黑名单"
    order = 1

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        if ctx.symbol in ctx.config.blacklist:
            return (False, f"{ctx.symbol} 在黑名单中，禁止交易")
        return None


class CooldownValidator(RiskValidator):
    """检查1+1.5: 熔断/极端行情冷却期"""

    name = "熔断冷却"
    order = 2

    def __init__(self, risk_manager):
        self._rm = risk_manager

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        if self._rm._is_in_cooldown():
            remaining = int((self._rm._cooldown_until - now_et()).total_seconds()) // 60
            return (False, f"熔断冷却中，还需等待{remaining}分钟 (连续{self._rm._consecutive_losses}笔亏损触发)")
        if self._rm.is_in_extreme_cooldown():
            remaining = int(
                (
                    self._rm._last_extreme_time
                    + timedelta(minutes=ctx.config.extreme_market_cooldown_minutes)
                    - now_et()
                ).total_seconds()
                // 60
            )
            return (False, f"极端行情冷却期，暂停交易 (剩余{remaining}min)")
        return None


class DailyLossValidator(RiskValidator):
    """检查2: 日亏损限额"""

    name = "日亏损限额"
    order = 3

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        if ctx.today_pnl <= -ctx.config.daily_loss_limit:
            return (
                False,
                f"已触及日亏损限额: 今日PnL=${ctx.today_pnl:.2f}, "
                f"限额=-${ctx.config.daily_loss_limit:.2f}，今日禁止新开仓",
            )
        return None


class TradingHoursValidator(RiskValidator):
    """检查3: 交易时段"""

    name = "交易时段"
    order = 4

    def __init__(self, risk_manager):
        self._rm = risk_manager

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        if ctx.config.trading_hours_enabled and not self._rm._is_trading_hours():
            return (False, "当前非交易时段，禁止下单")
        return None


class StopLossValidator(RiskValidator):
    """检查4+5: 止损必须设定 + 方向合理性"""

    name = "止损验证"
    order = 5

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        if ctx.side == "BUY" and ctx.stop_loss <= 0:
            return (False, "买入必须设定止损价（stop_loss > 0）")
        if ctx.side == "BUY" and ctx.stop_loss > 0:
            if ctx.stop_loss >= ctx.entry_price:
                return (False, f"止损价({ctx.stop_loss})必须低于入场价({ctx.entry_price})")
            sl_pct = (ctx.entry_price - ctx.stop_loss) / ctx.entry_price
            if sl_pct > 0.10:
                ctx.warnings.append(f"止损幅度{sl_pct * 100:.1f}%偏大(>10%)，超短线建议2-5%")
        # HI-523: SELL 方向止损验证 — 做空时止损必须高于入场价
        if ctx.side == "SELL" and ctx.stop_loss <= 0:
            return (False, "卖空必须设定止损价（stop_loss > 0）")
        if ctx.side == "SELL" and ctx.stop_loss > 0:
            if ctx.stop_loss <= ctx.entry_price:
                return (False, f"卖空止损价({ctx.stop_loss})必须高于入场价({ctx.entry_price})")
            sl_pct = (ctx.stop_loss - ctx.entry_price) / ctx.entry_price
            if sl_pct > 0.10:
                ctx.warnings.append(f"卖空止损幅度{sl_pct * 100:.1f}%偏大(>10%)，超短线建议2-5%")
        return None


class RiskRewardValidator(RiskValidator):
    """检查6: 风险收益比"""

    name = "风险收益比"
    order = 6

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        if ctx.side == "BUY" and ctx.stop_loss > 0 and ctx.take_profit > 0:
            risk = ctx.entry_price - ctx.stop_loss
            reward = ctx.take_profit - ctx.entry_price
            if risk > 0:
                rr_ratio = reward / risk
                if rr_ratio < ctx.config.min_risk_reward_ratio:
                    return (
                        False,
                        f"风险收益比{rr_ratio:.2f}:1 低于最低要求"
                        f"{ctx.config.min_risk_reward_ratio}:1 "
                        f"(风险${risk:.2f} vs 收益${reward:.2f})",
                    )
        elif ctx.side == "BUY" and ctx.take_profit <= 0:
            ctx.warnings.append("未设定止盈价，建议设定以锁定利润")
        # HI-523: SELL 方向风险收益比 — 做空时风险=止损-入场，收益=入场-止盈
        if ctx.side == "SELL" and ctx.stop_loss > 0 and ctx.take_profit > 0:
            risk = ctx.stop_loss - ctx.entry_price
            reward = ctx.entry_price - ctx.take_profit
            if risk > 0:
                rr_ratio = reward / risk
                if rr_ratio < ctx.config.min_risk_reward_ratio:
                    return (
                        False,
                        f"卖空风险收益比{rr_ratio:.2f}:1 低于最低要求"
                        f"{ctx.config.min_risk_reward_ratio}:1 "
                        f"(风险${risk:.2f} vs 收益${reward:.2f})",
                    )
        elif ctx.side == "SELL" and ctx.take_profit <= 0:
            ctx.warnings.append("卖空未设定止盈价，建议设定以锁定利润")
        return None


class PositionSizeValidator(RiskValidator):
    """检查7+8: 单笔风险金额 + 仓位集中度"""

    name = "仓位大小"
    order = 7

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        # 单笔风险金额
        max_risk_amount = ctx.config.total_capital * ctx.config.max_risk_per_trade_pct
        if ctx.side == "BUY" and ctx.stop_loss > 0:
            risk_per_share = ctx.entry_price - ctx.stop_loss
            actual_risk = ctx.quantity * risk_per_share
            if actual_risk > max_risk_amount:
                suggested_qty = int(max_risk_amount / risk_per_share)
                if suggested_qty <= 0:
                    return (
                        False,
                        f"单笔风险${actual_risk:.2f}超过上限"
                        f"${max_risk_amount:.2f}(资金的"
                        f"{ctx.config.max_risk_per_trade_pct * 100}%)，"
                        f"且无法调整到合理数量",
                    )
                ctx.adjusted_quantity = suggested_qty
                ctx.warnings.append(
                    f"数量从{ctx.quantity}调整为{suggested_qty}，以控制风险在${max_risk_amount:.2f}以内"
                )
                ctx.quantity = suggested_qty
        # HI-523: SELL 方向单笔风险金额检查 — 做空时风险=止损价-入场价
        if ctx.side == "SELL" and ctx.stop_loss > 0:
            risk_per_share = ctx.stop_loss - ctx.entry_price
            actual_risk = ctx.quantity * risk_per_share
            if actual_risk > max_risk_amount:
                suggested_qty = int(max_risk_amount / risk_per_share)
                if suggested_qty <= 0:
                    return (
                        False,
                        f"卖空单笔风险${actual_risk:.2f}超过上限"
                        f"${max_risk_amount:.2f}(资金的"
                        f"{ctx.config.max_risk_per_trade_pct * 100}%)，"
                        f"且无法调整到合理数量",
                    )
                ctx.adjusted_quantity = suggested_qty
                ctx.warnings.append(
                    f"卖空数量从{ctx.quantity}调整为{suggested_qty}，以控制风险在${max_risk_amount:.2f}以内"
                )
                ctx.quantity = suggested_qty

        # 仓位集中度
        position_value = ctx.quantity * ctx.entry_price
        max_position_value = ctx.config.total_capital * ctx.config.max_position_pct
        if position_value > max_position_value:
            suggested_qty = int(max_position_value / ctx.entry_price)
            if suggested_qty <= 0:
                return (
                    False,
                    f"仓位价值${position_value:.2f}超过单只上限"
                    f"${max_position_value:.2f}(资金的"
                    f"{ctx.config.max_position_pct * 100}%)",
                )
            if ctx.adjusted_quantity is None or suggested_qty < ctx.adjusted_quantity:
                ctx.adjusted_quantity = suggested_qty
            ctx.warnings.append(f"仓位价值${position_value:.2f}超过上限${max_position_value:.2f}，建议减少数量")
        return None


class ExposureValidator(RiskValidator):
    """检查9+10: 总敞口 + 最大持仓数"""

    name = "敞口与持仓数"
    order = 8

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        if not ctx.current_positions:
            return None
        position_value = ctx.quantity * ctx.entry_price
        # 总敞口
        total_exposure = sum(
            p.get("quantity", 0) * (p.get("avg_price", 0) or p.get("avg_cost", 0))
            for p in ctx.current_positions
            if p.get("status", "open") == "open" or "status" not in p
        )
        new_total = total_exposure + position_value
        max_exposure = ctx.config.total_capital * ctx.config.max_total_exposure_pct
        if new_total > max_exposure:
            return (
                False,
                f"总敞口${new_total:.2f}将超过上限"
                f"${max_exposure:.2f}(资金的"
                f"{ctx.config.max_total_exposure_pct * 100}%)",
            )
        # 最大持仓数 — HI-523: 适用于所有方向（BUY 和 SELL 都受持仓数限制）
        open_count = len(
            [p for p in ctx.current_positions if p.get("status", "open") == "open" or "status" not in p]
        )
        has_existing = any(
            p.get("symbol", "").upper() == ctx.symbol
            for p in ctx.current_positions
            if p.get("status", "open") == "open" or "status" not in p
        )
        if not has_existing and open_count >= ctx.config.max_open_positions:
            return (False, f"已有{open_count}个持仓，达到上限{ctx.config.max_open_positions}个，禁止新开仓")
        return None


class DrawdownValidator(RiskValidator):
    """检查14+15: 动态回撤保护 + 滚动窗口亏损"""

    name = "回撤保护"
    order = 10

    def __init__(self, risk_manager):
        self._rm = risk_manager

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        # 动态回撤保护
        drawdown_level = self._rm._get_drawdown_level()
        if drawdown_level == "halt":
            return (
                False,
                f"滚动{ctx.config.drawdown_window_days}天回撤超过{ctx.config.drawdown_halt_pct * 100}%，暂停交易",
            )
        elif drawdown_level == "warn":
            original_qty = ctx.adjusted_quantity or ctx.quantity
            scaled_qty = max(1, int(original_qty * 0.5))
            if scaled_qty < original_qty:
                ctx.adjusted_quantity = scaled_qty
                ctx.warnings.append(
                    f"回撤保护: 近{ctx.config.drawdown_window_days}天回撤超"
                    f"{ctx.config.drawdown_warn_pct * 100}%，仓位减半"
                )
                ctx.quantity = scaled_qty

        # 滚动窗口亏损
        if len(ctx.rolling_pnl) >= 5:
            rolling_total = sum(ctx.rolling_pnl)
            rolling_max_loss = ctx.config.total_capital * ctx.config.rolling_loss_max_pct
            if rolling_total < -rolling_max_loss:
                return (
                    False,
                    f"最近{len(ctx.rolling_pnl)}笔交易累计亏损"
                    f"${abs(rolling_total):.2f}，超过滚动窗口限额"
                    f"${rolling_max_loss:.2f}",
                )
        return None


class FrequencyValidator(RiskValidator):
    """检查16: 交易频率限制"""

    name = "交易频率"
    order = 11

    def __init__(self, risk_manager):
        self._rm = risk_manager

    def validate(self, ctx: ValidatorContext) -> tuple[bool, str] | None:
        freq_check = self._rm._check_trade_frequency()
        if freq_check:
            return (False, freq_check)
        return None


# ── Validator 链管理器 ──────────────────────────────


class ValidatorChain:
    """
    风控 Validator 链管理器

    借鉴 rqalpha 的 add_frontend_validator 机制:
    - 按 order 排序执行
    - 任何一个 reject 即终止（fail-fast）
    - 支持运行时增删 Validator
    """

    def __init__(self):
        self._validators: list[RiskValidator] = []

    def add_validator(self, validator: RiskValidator):
        """注册新的 Validator"""
        self._validators.append(validator)
        self._validators.sort(key=lambda v: v.order)
        logger.debug(f"[ValidatorChain] 注册 Validator: {validator.name} (order={validator.order})")

    def remove_validator(self, name: str):
        """按名称移除 Validator"""
        self._validators = [v for v in self._validators if v.name != name]

    def run(self, ctx: ValidatorContext) -> RiskCheckResult:
        """
        执行 Validator 链

        返回 RiskCheckResult（与 check_trade() 返回格式完全一致）
        """
        result = RiskCheckResult(approved=True)

        for validator in self._validators:
            try:
                check = validator.validate(ctx)
                if check is not None:
                    approved, reason = check
                    if not approved:
                        return RiskCheckResult(approved=False, reason=reason)
            except Exception as e:
                logger.error(f"[ValidatorChain] {validator.name} 异常: {scrub_secrets(str(e))}")
                # Validator 异常不应阻止交易（fail-open for individual validators）
                ctx.warnings.append(f"风控检查 '{validator.name}' 异常: {str(e)[:100]}")

        # 全部通过，汇总结果
        result.adjusted_quantity = ctx.adjusted_quantity
        result.warnings = ctx.warnings
        return result

    @property
    def validator_names(self) -> list[str]:
        """返回当前注册的所有 Validator 名称"""
        return [v.name for v in self._validators]

    def __len__(self):
        return len(self._validators)


def build_default_chain(risk_manager) -> ValidatorChain:
    """
    构建默认的 Validator 链（等效于原 check_trade() 的全部18项检查）

    参数:
        risk_manager: RiskManager 实例（部分 Validator 需要访问其内部状态）
    """
    chain = ValidatorChain()
    # 按检查顺序注册
    chain.add_validator(ParameterValidator())
    chain.add_validator(BlacklistValidator())
    chain.add_validator(CooldownValidator(risk_manager))
    chain.add_validator(DailyLossValidator())
    chain.add_validator(TradingHoursValidator(risk_manager))
    chain.add_validator(StopLossValidator())
    chain.add_validator(RiskRewardValidator())
    chain.add_validator(PositionSizeValidator())
    chain.add_validator(ExposureValidator())
    chain.add_validator(DrawdownValidator(risk_manager))
    chain.add_validator(FrequencyValidator(risk_manager))
    # 检查11(信号强度)、12(日亏损预估)、13(阶梯熔断)、17(板块集中度)、18(VaR)
    # 保留在 check_trade() 中作为 warning-only 检查（不 reject）
    return chain
