"""
风控 Validator 链式架构单元测试

覆盖范围:
- ValidatorChain: 注册、排序、执行、移除、空链、异常容错
- 各内置 Validator: 通过/拒绝/边界条件
- ValidatorContext: 中间结果传递（adjusted_quantity, warnings）
- build_default_chain: 默认链完整性
"""

import pytest
from dataclasses import field
from unittest.mock import MagicMock, patch

from src.risk_config import RiskConfig, RiskCheckResult
from src.risk_validators import (
    ValidatorContext,
    ValidatorChain,
    RiskValidator,
    ParameterValidator,
    BlacklistValidator,
    CooldownValidator,
    DailyLossValidator,
    TradingHoursValidator,
    StopLossValidator,
    RiskRewardValidator,
    PositionSizeValidator,
    ExposureValidator,
    DrawdownValidator,
    FrequencyValidator,
    build_default_chain,
)


# ── 测试用辅助工具 ──────────────────────────────────────


def _make_config(**overrides) -> RiskConfig:
    """创建测试用 RiskConfig，可覆盖任意字段"""
    defaults = dict(
        total_capital=10000.0,
        max_risk_per_trade_pct=0.02,
        daily_loss_limit=200.0,
        max_position_pct=0.30,
        max_total_exposure_pct=0.80,
        max_open_positions=5,
        min_risk_reward_ratio=2.0,
        min_signal_score=20,
        max_consecutive_losses=3,
        cooldown_minutes=30,
        trading_hours_enabled=False,
        blacklist=["SCAM", "JUNK"],
        drawdown_window_days=7,
        drawdown_warn_pct=0.05,
        drawdown_halt_pct=0.08,
        rolling_loss_max_pct=0.08,
        extreme_market_cooldown_minutes=60,
    )
    defaults.update(overrides)
    return RiskConfig(**defaults)


def _make_ctx(**overrides) -> ValidatorContext:
    """创建测试用 ValidatorContext，默认是一笔合法的 BUY 交易"""
    defaults = dict(
        symbol="AAPL",
        side="BUY",
        quantity=5.0,
        entry_price=150.0,
        stop_loss=145.0,
        take_profit=162.0,
        signal_score=60,
        current_positions=[],
        config=_make_config(),
        today_pnl=0.0,
        consecutive_losses=0,
        position_scale=1.0,
        current_tier=0,
        rolling_pnl=[],
        trade_history=[],
        peak_capital=10000.0,
    )
    defaults.update(overrides)
    return ValidatorContext(**defaults)


class _AlwaysPassValidator(RiskValidator):
    """测试用：永远通过的 Validator"""

    name = "总是通过"
    order = 50

    def validate(self, ctx):
        return None


class _AlwaysRejectValidator(RiskValidator):
    """测试用：永远拒绝的 Validator"""

    name = "总是拒绝"
    order = 50

    def validate(self, ctx):
        return (False, "测试拒绝")


class _ExplodingValidator(RiskValidator):
    """测试用：抛出异常的 Validator"""

    name = "会爆炸"
    order = 50

    def validate(self, ctx):
        raise RuntimeError("模拟内部错误")


class _OrderedValidator(RiskValidator):
    """测试用：可指定 order 的 Validator，执行时记录调用顺序"""

    def __init__(self, name_str: str, order_val: int, call_log: list):
        self._name = name_str
        self._order = order_val
        self._call_log = call_log

    @property
    def name(self):
        return self._name

    @property
    def order(self):
        return self._order

    def validate(self, ctx):
        self._call_log.append(self._name)
        return None


# ── ValidatorChain 测试 ──────────────────────────────────


class TestValidatorChain:
    """ValidatorChain 核心功能测试"""

    def test_空链返回通过(self):
        """空链应该直接返回 approved=True"""
        chain = ValidatorChain()
        ctx = _make_ctx()
        result = chain.run(ctx)
        assert result.approved is True
        assert result.reason == ""

    def test_空链长度为零(self):
        """空链 len() 应该返回 0"""
        chain = ValidatorChain()
        assert len(chain) == 0

    def test_注册单个_validator(self):
        """注册一个 Validator 后链长度为 1"""
        chain = ValidatorChain()
        chain.add_validator(_AlwaysPassValidator())
        assert len(chain) == 1
        assert "总是通过" in chain.validator_names

    def test_注册多个_validator_按_order_排序(self):
        """多个 Validator 应按 order 从小到大排序"""
        chain = ValidatorChain()
        call_log = []
        chain.add_validator(_OrderedValidator("C", 300, call_log))
        chain.add_validator(_OrderedValidator("A", 100, call_log))
        chain.add_validator(_OrderedValidator("B", 200, call_log))
        assert chain.validator_names == ["A", "B", "C"]

    def test_执行顺序按_order(self):
        """run() 时应按 order 顺序调用 Validator"""
        chain = ValidatorChain()
        call_log = []
        chain.add_validator(_OrderedValidator("第三", 30, call_log))
        chain.add_validator(_OrderedValidator("第一", 10, call_log))
        chain.add_validator(_OrderedValidator("第二", 20, call_log))
        chain.run(_make_ctx())
        assert call_log == ["第一", "第二", "第三"]

    def test_全部通过返回_approved(self):
        """所有 Validator 都通过时，结果应为 approved"""
        chain = ValidatorChain()
        chain.add_validator(_AlwaysPassValidator())
        chain.add_validator(_AlwaysPassValidator())
        result = chain.run(_make_ctx())
        assert result.approved is True

    def test_任一拒绝即终止(self):
        """链中有一个 reject，后续 Validator 不再执行"""
        chain = ValidatorChain()
        call_log = []
        chain.add_validator(_OrderedValidator("先执行", 10, call_log))
        reject = _AlwaysRejectValidator()
        reject.order = 20  # 不能直接设置 property，用子类方式
        # 直接用一个中间 order 的 reject
        chain.add_validator(reject)
        chain.add_validator(_OrderedValidator("不该执行", 30, call_log))
        result = chain.run(_make_ctx())
        assert result.approved is False
        assert "测试拒绝" in result.reason
        # "不该执行" 不应出现在调用日志中
        assert "不该执行" not in call_log

    def test_异常不阻塞链(self):
        """Validator 抛异常时，链应继续执行（fail-open）"""
        chain = ValidatorChain()
        chain.add_validator(_ExplodingValidator())
        chain.add_validator(_AlwaysPassValidator())
        ctx = _make_ctx()
        result = chain.run(ctx)
        # 链应该继续执行并最终通过
        assert result.approved is True
        # 异常应记录到 warnings
        assert any("会爆炸" in w for w in ctx.warnings)

    def test_异常后的_reject_仍然生效(self):
        """异常 Validator 之后的 reject 仍然应该生效"""
        chain = ValidatorChain()
        exploder = _ExplodingValidator()
        exploder.__class__.order = 10  # 先执行
        chain.add_validator(exploder)
        rejecter = _AlwaysRejectValidator()
        chain.add_validator(rejecter)
        result = chain.run(_make_ctx())
        assert result.approved is False

    def test_remove_validator_按名称移除(self):
        """remove_validator 应按名称移除指定 Validator"""
        chain = ValidatorChain()
        chain.add_validator(_AlwaysPassValidator())
        chain.add_validator(_AlwaysRejectValidator())
        assert len(chain) == 2
        chain.remove_validator("总是拒绝")
        assert len(chain) == 1
        assert "总是拒绝" not in chain.validator_names
        # 移除 reject 后应该通过
        result = chain.run(_make_ctx())
        assert result.approved is True

    def test_remove_不存在的名称无副作用(self):
        """移除不存在的 Validator 不应报错"""
        chain = ValidatorChain()
        chain.add_validator(_AlwaysPassValidator())
        chain.remove_validator("不存在的名字")
        assert len(chain) == 1

    def test_warnings_和_adjusted_quantity_传递到结果(self):
        """ctx 中的 warnings 和 adjusted_quantity 应传递到 RiskCheckResult"""
        chain = ValidatorChain()
        chain.add_validator(_AlwaysPassValidator())
        ctx = _make_ctx()
        ctx.warnings.append("测试警告")
        ctx.adjusted_quantity = 3.0
        result = chain.run(ctx)
        assert result.approved is True
        assert "测试警告" in result.warnings
        assert result.adjusted_quantity == 3.0


# ── ParameterValidator 测试 ──────────────────────────────


class TestParameterValidator:
    """参数合法性校验器测试"""

    def test_合法参数通过(self):
        v = ParameterValidator()
        ctx = _make_ctx(entry_price=100.0, quantity=10.0)
        assert v.validate(ctx) is None

    def test_入场价为零被拒绝(self):
        v = ParameterValidator()
        ctx = _make_ctx(entry_price=0.0)
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "入场价" in result[1]

    def test_入场价为负被拒绝(self):
        v = ParameterValidator()
        ctx = _make_ctx(entry_price=-5.0)
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False

    def test_数量为零被拒绝(self):
        v = ParameterValidator()
        ctx = _make_ctx(quantity=0.0)
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "数量" in result[1]

    def test_数量为负被拒绝(self):
        v = ParameterValidator()
        ctx = _make_ctx(quantity=-1.0)
        result = v.validate(ctx)
        assert result[0] is False

    def test_order_为_0(self):
        """ParameterValidator 应该最先执行 (order=0)"""
        v = ParameterValidator()
        assert v.order == 0


# ── BlacklistValidator 测试 ──────────────────────────────


class TestBlacklistValidator:
    """黑名单校验器测试"""

    def test_黑名单标的被拒绝(self):
        v = BlacklistValidator()
        ctx = _make_ctx(symbol="SCAM")
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "黑名单" in result[1]

    def test_正常标的通过(self):
        v = BlacklistValidator()
        ctx = _make_ctx(symbol="AAPL")
        assert v.validate(ctx) is None

    def test_空黑名单全部通过(self):
        v = BlacklistValidator()
        ctx = _make_ctx(symbol="ANYTHING", config=_make_config(blacklist=[]))
        assert v.validate(ctx) is None


# ── DailyLossValidator 测试 ──────────────────────────────


class TestDailyLossValidator:
    """日亏损限额校验器测试"""

    def test_未亏损通过(self):
        v = DailyLossValidator()
        ctx = _make_ctx(today_pnl=0.0)
        assert v.validate(ctx) is None

    def test_盈利通过(self):
        v = DailyLossValidator()
        ctx = _make_ctx(today_pnl=500.0)
        assert v.validate(ctx) is None

    def test_亏损未达限额通过(self):
        v = DailyLossValidator()
        ctx = _make_ctx(today_pnl=-100.0)  # 限额 200
        assert v.validate(ctx) is None

    def test_亏损达到限额被拒绝(self):
        v = DailyLossValidator()
        ctx = _make_ctx(today_pnl=-200.0)  # 刚好等于限额
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "日亏损限额" in result[1]

    def test_亏损超过限额被拒绝(self):
        v = DailyLossValidator()
        ctx = _make_ctx(today_pnl=-300.0)
        result = v.validate(ctx)
        assert result[0] is False

    def test_边界值_刚好未达限额通过(self):
        """today_pnl = -199.99，限额 200，应该通过"""
        v = DailyLossValidator()
        ctx = _make_ctx(today_pnl=-199.99)
        assert v.validate(ctx) is None


# ── StopLossValidator 测试 ──────────────────────────────


class TestStopLossValidator:
    """止损验证器测试"""

    def test_合法止损通过(self):
        v = StopLossValidator()
        ctx = _make_ctx(side="BUY", entry_price=100.0, stop_loss=95.0)
        assert v.validate(ctx) is None

    def test_买入无止损被拒绝(self):
        v = StopLossValidator()
        ctx = _make_ctx(side="BUY", stop_loss=0.0)
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "止损" in result[1]

    def test_止损高于入场价被拒绝(self):
        v = StopLossValidator()
        ctx = _make_ctx(side="BUY", entry_price=100.0, stop_loss=105.0)
        result = v.validate(ctx)
        assert result[0] is False
        assert "止损价" in result[1] and "入场价" in result[1]

    def test_止损等于入场价被拒绝(self):
        v = StopLossValidator()
        ctx = _make_ctx(side="BUY", entry_price=100.0, stop_loss=100.0)
        result = v.validate(ctx)
        assert result[0] is False

    def test_止损幅度过大产生警告(self):
        """止损幅度 > 10% 应产生警告但不拒绝"""
        v = StopLossValidator()
        # 入场 100，止损 85 → 幅度 15%
        ctx = _make_ctx(side="BUY", entry_price=100.0, stop_loss=85.0)
        result = v.validate(ctx)
        assert result is None  # 不拒绝
        assert any("偏大" in w for w in ctx.warnings)

    def test_止损幅度正常无警告(self):
        """止损幅度 <= 10% 不应产生警告"""
        v = StopLossValidator()
        # 入场 100，止损 95 → 幅度 5%
        ctx = _make_ctx(side="BUY", entry_price=100.0, stop_loss=95.0)
        v.validate(ctx)
        assert len(ctx.warnings) == 0

    def test_卖出方向必须设定止损(self):
        """HI-523: SELL 方向也必须设定止损"""
        v = StopLossValidator()
        ctx = _make_ctx(side="SELL", stop_loss=0.0)
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "卖空必须设定止损价" in result[1]


# ── RiskRewardValidator 测试 ──────────────────────────────


class TestRiskRewardValidator:
    """风险收益比校验器测试"""

    def test_合格的风险收益比通过(self):
        """风险收益比 >= 2.0 应通过"""
        v = RiskRewardValidator()
        # 入场 100，止损 95，止盈 112 → 风险 5，收益 12 → 比率 2.4
        ctx = _make_ctx(side="BUY", entry_price=100.0, stop_loss=95.0, take_profit=112.0)
        assert v.validate(ctx) is None

    def test_不合格的风险收益比被拒绝(self):
        """风险收益比 < 2.0 应被拒绝"""
        v = RiskRewardValidator()
        # 入场 100，止损 95，止盈 104 → 风险 5，收益 4 → 比率 0.8
        ctx = _make_ctx(side="BUY", entry_price=100.0, stop_loss=95.0, take_profit=104.0)
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "风险收益比" in result[1]

    def test_刚好等于最低比率通过(self):
        """风险收益比 == 2.0 应通过"""
        v = RiskRewardValidator()
        # 入场 100，止损 95，止盈 110 → 风险 5，收益 10 → 比率 2.0
        ctx = _make_ctx(side="BUY", entry_price=100.0, stop_loss=95.0, take_profit=110.0)
        assert v.validate(ctx) is None

    def test_未设止盈产生警告(self):
        """BUY 且 take_profit <= 0 应产生警告"""
        v = RiskRewardValidator()
        ctx = _make_ctx(side="BUY", stop_loss=95.0, take_profit=0.0)
        result = v.validate(ctx)
        assert result is None  # 不拒绝
        assert any("止盈" in w for w in ctx.warnings)

    def test_卖出方向不检查(self):
        """SELL 方向不检查风险收益比"""
        v = RiskRewardValidator()
        ctx = _make_ctx(side="SELL", stop_loss=0.0, take_profit=0.0)
        assert v.validate(ctx) is None


# ── PositionSizeValidator 测试 ──────────────────────────────


class TestPositionSizeValidator:
    """仓位大小校验器测试"""

    def test_合理仓位通过(self):
        """仓位在限额内应通过"""
        v = PositionSizeValidator()
        # 资金 10000，单笔风险 2% = $200
        # 入场 100，止损 95，数量 5 → 风险 = 5*5 = $25 < $200 ✓
        # 仓位价值 = 5*100 = $500 < 10000*0.3 = $3000 ✓
        ctx = _make_ctx(quantity=5.0, entry_price=100.0, stop_loss=95.0, side="BUY")
        assert v.validate(ctx) is None
        assert ctx.adjusted_quantity is None

    def test_单笔风险超限自动调整数量(self):
        """单笔风险超过限额时，应自动调整数量并产生警告"""
        v = PositionSizeValidator()
        # 资金 10000，单笔风险 2% = $200
        # 入场 100，止损 90，数量 30 → 风险 = 30*10 = $300 > $200
        # 建议数量 = int(200/10) = 20
        ctx = _make_ctx(quantity=30.0, entry_price=100.0, stop_loss=90.0, side="BUY")
        result = v.validate(ctx)
        assert result is None  # 不拒绝，只调整
        assert ctx.adjusted_quantity == 20
        assert ctx.quantity == 20  # 数量已被修改
        assert any("调整" in w for w in ctx.warnings)

    def test_单笔风险超限且无法调整被拒绝(self):
        """风险太大，调整后数量为 0 时应拒绝"""
        v = PositionSizeValidator()
        # 资金 10000，单笔风险 2% = $200
        # 入场 100，止损 1，数量 5 → 风险 = 5*99 = $495
        # 建议数量 = int(200/99) = 2 → 不为 0，不会拒绝
        # 需要更极端的情况：风险/股 > max_risk_amount
        ctx = _make_ctx(
            quantity=5.0,
            entry_price=1000.0,
            stop_loss=1.0,
            side="BUY",
            config=_make_config(total_capital=100.0, max_risk_per_trade_pct=0.01),
        )
        # max_risk = 100 * 0.01 = $1, risk_per_share = 999
        # suggested_qty = int(1/999) = 0 → 拒绝
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "无法调整" in result[1]

    def test_仓位集中度超限产生警告(self):
        """仓位价值超过单只上限时应产生警告"""
        v = PositionSizeValidator()
        # 资金 10000，单只上限 30% = $3000
        # 入场 100，数量 35 → 仓位价值 = $3500 > $3000
        # 但先过单笔风险检查：止损 95，风险 = 35*5 = $175 < $200 ✓
        ctx = _make_ctx(quantity=35.0, entry_price=100.0, stop_loss=95.0, side="BUY")
        result = v.validate(ctx)
        assert result is None  # 不拒绝
        assert any("仓位价值" in w for w in ctx.warnings)

    def test_仓位集中度超限且无法调整被拒绝(self):
        """仓位价值超限且调整后数量为 0 时应拒绝"""
        v = PositionSizeValidator()
        ctx = _make_ctx(
            quantity=5.0,
            entry_price=50000.0,  # 很贵的股票
            stop_loss=49999.0,
            side="BUY",
            config=_make_config(total_capital=1000.0, max_position_pct=0.01),
        )
        # max_position_value = 1000 * 0.01 = $10
        # suggested_qty = int(10/50000) = 0 → 拒绝
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False

    def test_卖出方向跳过单笔风险检查(self):
        """SELL 方向不检查单笔风险金额（只检查仓位集中度）"""
        v = PositionSizeValidator()
        ctx = _make_ctx(quantity=5.0, entry_price=100.0, stop_loss=0.0, side="SELL")
        assert v.validate(ctx) is None


# ── ExposureValidator 测试 ──────────────────────────────


class TestExposureValidator:
    """敞口与持仓数校验器测试"""

    def test_无持仓直接通过(self):
        """没有现有持仓时直接通过"""
        v = ExposureValidator()
        ctx = _make_ctx(current_positions=[])
        assert v.validate(ctx) is None

    def test_总敞口未超限通过(self):
        v = ExposureValidator()
        # 现有持仓: MSFT 10*400 = $4000
        # 新交易: AAPL 5*100 = $500
        # 总敞口 = $4500 < 10000*0.8 = $8000 ✓
        ctx = _make_ctx(
            quantity=5.0,
            entry_price=100.0,
            current_positions=[{"symbol": "MSFT", "quantity": 10, "avg_price": 400.0, "status": "open"}],
        )
        assert v.validate(ctx) is None

    def test_总敞口超限被拒绝(self):
        v = ExposureValidator()
        # 现有持仓: MSFT 20*400 = $8000
        # 新交易: AAPL 5*100 = $500
        # 总敞口 = $8500 > 10000*0.8 = $8000
        ctx = _make_ctx(
            quantity=5.0,
            entry_price=100.0,
            current_positions=[{"symbol": "MSFT", "quantity": 20, "avg_price": 400.0, "status": "open"}],
        )
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "总敞口" in result[1]

    def test_持仓数达上限被拒绝(self):
        """已有 5 个持仓（上限），新开仓应被拒绝"""
        v = ExposureValidator()
        positions = [{"symbol": f"SYM{i}", "quantity": 1, "avg_price": 10.0, "status": "open"} for i in range(5)]
        ctx = _make_ctx(
            side="BUY",
            quantity=1.0,
            entry_price=10.0,
            current_positions=positions,
        )
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "持仓" in result[1]

    def test_已有同标的持仓不算新开仓(self):
        """加仓已有标的不受最大持仓数限制"""
        v = ExposureValidator()
        positions = [{"symbol": f"SYM{i}", "quantity": 1, "avg_price": 10.0, "status": "open"} for i in range(5)]
        # 买入 SYM0（已有持仓），不算新开仓
        ctx = _make_ctx(
            symbol="SYM0",
            side="BUY",
            quantity=1.0,
            entry_price=10.0,
            current_positions=positions,
        )
        # 总敞口 = 5*10 + 1*10 = $60 < $8000 ✓
        result = v.validate(ctx)
        assert result is None

    def test_已关闭持仓不计入(self):
        """status=closed 的持仓不应计入敞口和持仓数"""
        v = ExposureValidator()
        positions = [
            {"symbol": "MSFT", "quantity": 100, "avg_price": 400.0, "status": "closed"},
            {"symbol": "GOOG", "quantity": 1, "avg_price": 10.0, "status": "open"},
        ]
        ctx = _make_ctx(
            quantity=1.0,
            entry_price=10.0,
            current_positions=positions,
        )
        # 只有 GOOG 的 $10 是活跃敞口，新增 $10 → 总 $20 < $8000 ✓
        assert v.validate(ctx) is None

    def test_卖出方向也检查持仓数(self):
        """HI-523: SELL 方向也受最大持仓数限制"""
        v = ExposureValidator()
        positions = [{"symbol": f"SYM{i}", "quantity": 1, "avg_price": 10.0, "status": "open"} for i in range(5)]
        ctx = _make_ctx(
            side="SELL",
            quantity=1.0,
            entry_price=10.0,
            current_positions=positions,
        )
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "达到上限" in result[1]


# ── CooldownValidator 测试 ──────────────────────────────


class TestCooldownValidator:
    """熔断冷却校验器测试"""

    def test_无冷却通过(self):
        rm = MagicMock()
        rm._is_in_cooldown.return_value = False
        rm.is_in_extreme_cooldown.return_value = False
        v = CooldownValidator(rm)
        ctx = _make_ctx()
        assert v.validate(ctx) is None

    def test_熔断冷却中被拒绝(self):
        rm = MagicMock()
        rm._is_in_cooldown.return_value = True
        rm._cooldown_until = MagicMock()
        rm._consecutive_losses = 3
        v = CooldownValidator(rm)
        ctx = _make_ctx()
        with patch("src.risk_validators.now_et") as mock_now:
            from datetime import datetime, timezone

            mock_now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            rm._cooldown_until = datetime(2025, 1, 1, 12, 15, 0, tzinfo=timezone.utc)
            result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "熔断" in result[1]

    def test_极端行情冷却被拒绝(self):
        rm = MagicMock()
        rm._is_in_cooldown.return_value = False
        rm.is_in_extreme_cooldown.return_value = True
        v = CooldownValidator(rm)
        ctx = _make_ctx()
        with patch("src.risk_validators.now_et") as mock_now:
            from datetime import datetime, timedelta, timezone

            now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_now.return_value = now
            rm._last_extreme_time = now - timedelta(minutes=30)
            result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "极端行情" in result[1]


# ── TradingHoursValidator 测试 ──────────────────────────────


class TestTradingHoursValidator:
    """交易时段校验器测试"""

    def test_时段检查关闭时通过(self):
        rm = MagicMock()
        v = TradingHoursValidator(rm)
        ctx = _make_ctx(config=_make_config(trading_hours_enabled=False))
        assert v.validate(ctx) is None

    def test_交易时段内通过(self):
        rm = MagicMock()
        rm._is_trading_hours.return_value = True
        v = TradingHoursValidator(rm)
        ctx = _make_ctx(config=_make_config(trading_hours_enabled=True))
        assert v.validate(ctx) is None

    def test_非交易时段被拒绝(self):
        rm = MagicMock()
        rm._is_trading_hours.return_value = False
        v = TradingHoursValidator(rm)
        ctx = _make_ctx(config=_make_config(trading_hours_enabled=True))
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "交易时段" in result[1]


# ── DrawdownValidator 测试 ──────────────────────────────


class TestDrawdownValidator:
    """回撤保护校验器测试"""

    def test_无回撤通过(self):
        rm = MagicMock()
        rm._get_drawdown_level.return_value = "ok"
        v = DrawdownValidator(rm)
        ctx = _make_ctx(rolling_pnl=[])
        assert v.validate(ctx) is None

    def test_回撤达到停止级别被拒绝(self):
        rm = MagicMock()
        rm._get_drawdown_level.return_value = "halt"
        v = DrawdownValidator(rm)
        ctx = _make_ctx()
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "回撤" in result[1]

    def test_回撤达到警告级别仓位减半(self):
        rm = MagicMock()
        rm._get_drawdown_level.return_value = "warn"
        v = DrawdownValidator(rm)
        ctx = _make_ctx(quantity=10.0)
        result = v.validate(ctx)
        assert result is None  # 不拒绝
        assert ctx.quantity == 5  # 减半
        assert ctx.adjusted_quantity == 5
        assert any("回撤保护" in w for w in ctx.warnings)

    def test_回撤警告_数量为_1_不再减少(self):
        """数量为 1 时减半后仍为 1（max(1, ...)）"""
        rm = MagicMock()
        rm._get_drawdown_level.return_value = "warn"
        v = DrawdownValidator(rm)
        ctx = _make_ctx(quantity=1.0)
        v.validate(ctx)
        assert ctx.quantity == 1

    def test_滚动窗口亏损超限被拒绝(self):
        rm = MagicMock()
        rm._get_drawdown_level.return_value = "ok"
        v = DrawdownValidator(rm)
        # 资金 10000，滚动亏损限额 8% = $800
        # 最近 5 笔累计亏损 -$900
        ctx = _make_ctx(rolling_pnl=[-200, -200, -200, -200, -100])
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "滚动窗口" in result[1]

    def test_滚动窗口不足_5_笔不检查(self):
        """不足 5 笔交易时不检查滚动窗口"""
        rm = MagicMock()
        rm._get_drawdown_level.return_value = "ok"
        v = DrawdownValidator(rm)
        ctx = _make_ctx(rolling_pnl=[-500, -500, -500, -500])  # 只有 4 笔
        assert v.validate(ctx) is None

    def test_滚动窗口亏损未超限通过(self):
        rm = MagicMock()
        rm._get_drawdown_level.return_value = "ok"
        v = DrawdownValidator(rm)
        # 累计 -$100 < $800 限额
        ctx = _make_ctx(rolling_pnl=[-20, -20, -20, -20, -20])
        assert v.validate(ctx) is None


# ── FrequencyValidator 测试 ──────────────────────────────


class TestFrequencyValidator:
    """交易频率校验器测试"""

    def test_频率正常通过(self):
        rm = MagicMock()
        rm._check_trade_frequency.return_value = None
        v = FrequencyValidator(rm)
        ctx = _make_ctx()
        assert v.validate(ctx) is None

    def test_频率超限被拒绝(self):
        rm = MagicMock()
        rm._check_trade_frequency.return_value = "每小时交易次数已达上限"
        v = FrequencyValidator(rm)
        ctx = _make_ctx()
        result = v.validate(ctx)
        assert result is not None
        assert result[0] is False
        assert "上限" in result[1]


# ── build_default_chain 测试 ──────────────────────────────


class TestBuildDefaultChain:
    """默认链构建测试"""

    def test_默认链包含所有内置_validator(self):
        rm = MagicMock()
        chain = build_default_chain(rm)
        names = chain.validator_names
        # 验证所有内置 Validator 都已注册
        assert "参数合法性" in names
        assert "黑名单" in names
        assert "熔断冷却" in names
        assert "日亏损限额" in names
        assert "交易时段" in names
        assert "止损验证" in names
        assert "风险收益比" in names
        assert "仓位大小" in names
        assert "敞口与持仓数" in names
        assert "回撤保护" in names
        assert "交易频率" in names

    def test_默认链有_11_个_validator(self):
        rm = MagicMock()
        chain = build_default_chain(rm)
        assert len(chain) == 11

    def test_默认链按_order_排序(self):
        """验证默认链的执行顺序正确"""
        rm = MagicMock()
        chain = build_default_chain(rm)
        names = chain.validator_names
        # 参数合法性(0) 应在黑名单(1) 之前
        assert names.index("参数合法性") < names.index("黑名单")
        # 黑名单(1) 应在熔断冷却(2) 之前
        assert names.index("黑名单") < names.index("熔断冷却")
        # 日亏损限额(3) 应在交易时段(4) 之前
        assert names.index("日亏损限额") < names.index("交易时段")


# ── 集成测试：完整链执行 ──────────────────────────────


class TestValidatorChainIntegration:
    """ValidatorChain 集成测试：模拟完整的风控检查流程"""

    def test_合法交易通过完整链(self):
        """一笔完全合法的交易应通过所有检查"""
        rm = MagicMock()
        rm._is_in_cooldown.return_value = False
        rm.is_in_extreme_cooldown.return_value = False
        rm._is_trading_hours.return_value = True
        rm._get_drawdown_level.return_value = "ok"
        rm._check_trade_frequency.return_value = None

        chain = build_default_chain(rm)
        ctx = _make_ctx(
            symbol="AAPL",
            side="BUY",
            quantity=5.0,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=112.0,
            signal_score=60,
            config=_make_config(trading_hours_enabled=True),
        )
        result = chain.run(ctx)
        assert result.approved is True

    def test_参数非法在第一步就被拒绝(self):
        """入场价为 0 应在 ParameterValidator 就被拒绝，不会执行后续检查"""
        rm = MagicMock()
        chain = build_default_chain(rm)
        ctx = _make_ctx(entry_price=0.0)
        result = chain.run(ctx)
        assert result.approved is False
        assert "入场价" in result.reason
        # 后续 Validator 不应被调用（通过 mock 验证）
        rm._is_in_cooldown.assert_not_called()

    def test_黑名单标的在第二步被拒绝(self):
        """黑名单标的应在 BlacklistValidator 被拒绝"""
        rm = MagicMock()
        chain = build_default_chain(rm)
        ctx = _make_ctx(symbol="SCAM")
        result = chain.run(ctx)
        assert result.approved is False
        assert "黑名单" in result.reason
