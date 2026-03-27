"""
PositionMonitor v2 高优先级测试 — 涉及真金白银的退出条件

覆盖场景：
  - 分批止盈 (PARTIAL_TAKE_PROFIT) 触发/跳过逻辑
  - 日亏损限额熔断 (DAILY_LIMIT)
  - SELL 方向持仓的止损/止盈处理（当前代码仅覆盖 BUY 方向）
"""
import pytest
from unittest.mock import MagicMock
from datetime import timedelta

from src.position_monitor import (
    PositionMonitor, MonitoredPosition, ExitReason, ExitSignal,
)
from src.risk_manager import RiskManager, RiskConfig
from src.utils import now_et


# ============ 辅助工厂方法 ============

def _make_monitor(**kwargs) -> PositionMonitor:
    """创建最小化的 PositionMonitor"""
    return PositionMonitor(check_interval=30, **kwargs)


def _make_pos(**kwargs) -> MonitoredPosition:
    """创建 MonitoredPosition，提供合理默认值"""
    defaults = dict(
        trade_id=1,
        symbol="AAPL",
        side="BUY",
        quantity=10,
        entry_price=100.0,
        entry_time=now_et(),
    )
    defaults.update(kwargs)
    return MonitoredPosition(**defaults)


# ============ 分批止盈 (Partial Take Profit) ============

class TestPartialTakeProfit:
    """分批止盈在 1.5R 处触发，平掉 50% 仓位"""

    def test_partial_take_profit_at_1_5R(self):
        """BUY 持仓，止损 $95，risk=$5/股。
        价格达到 entry + 1.5*risk = 100 + 7.5 = $107.5 → 触发 PARTIAL_TAKE_PROFIT。

        注意: 必须先设 breakeven_triggered=True，否则 update_price() 在 1R 处
        触发保本止损，将 stop_loss 从 $95 上移到 ~$100.20，导致
        risk_per_share = entry - new_stop = 100 - 100.20 < 0，分批止盈条件不满足。
        """
        mon = _make_monitor()
        pos = _make_pos(
            entry_price=100.0,
            stop_loss=95.0,
            quantity=10,  # >= 2，满足数量条件
            breakeven_triggered=True,  # 防止 update_price 修改 stop_loss
        )
        pos.highest_price = 100.0
        # 价格涨到 1.5R 位置: 100 + (100-95)*1.5 = 107.5
        pos.update_price(107.5)

        signal = mon._check_exit_conditions(pos)

        assert signal is not None, "1.5R 价位应触发分批止盈"
        assert signal.reason == ExitReason.PARTIAL_TAKE_PROFIT
        assert signal.trigger_price == 107.5

    def test_partial_take_profit_skipped_if_already_done(self):
        """partial_exit_done=True 时不再触发分批止盈"""
        mon = _make_monitor()
        pos = _make_pos(
            entry_price=100.0,
            stop_loss=95.0,
            quantity=10,
            partial_exit_done=True,  # 已执行过分批止盈
        )
        pos.highest_price = 100.0
        pos.update_price(110.0)  # 远超 1.5R

        signal = mon._check_exit_conditions(pos)

        # 不应触发分批止盈（已做过），也不应触发其他退出
        assert signal is None or signal.reason != ExitReason.PARTIAL_TAKE_PROFIT

    def test_partial_take_profit_skipped_if_quantity_too_small(self):
        """持仓数量 < 2 时跳过分批止盈（无法拆分）"""
        mon = _make_monitor()
        pos = _make_pos(
            entry_price=100.0,
            stop_loss=95.0,
            quantity=1,  # 只有 1 股，不够拆
        )
        pos.highest_price = 100.0
        pos.update_price(110.0)  # 远超 1.5R

        signal = mon._check_exit_conditions(pos)

        # 不应触发分批止盈
        assert signal is None or signal.reason != ExitReason.PARTIAL_TAKE_PROFIT


# ============ 日亏损限额熔断 (Daily Limit Circuit Breaker) ============

class TestDailyLimitCircuitBreaker:
    """当日累计亏损 + 浮亏超限时强制平仓"""

    def _make_risk_manager(self, today_pnl: float = 0, daily_limit: float = 100):
        """创建带有指定今日盈亏的 RiskManager"""
        config = RiskConfig(
            total_capital=10000.0,
            daily_loss_limit=daily_limit,
        )
        rm = RiskManager(config=config)
        rm._today_pnl = today_pnl
        rm._last_pnl_update = now_et().strftime('%Y-%m-%d')
        rm._last_refresh_ts = now_et()
        return rm

    def test_daily_limit_circuit_breaker(self):
        """今日已亏 $60 + 浮亏 $50 = 总亏 $110 > 限额 $100 → 触发 DAILY_LIMIT"""
        rm = self._make_risk_manager(today_pnl=-60.0, daily_limit=100.0)
        mon = _make_monitor(risk_manager=rm)

        pos = _make_pos(
            entry_price=100.0,
            quantity=10,
        )
        pos.highest_price = 100.0
        # 价格下跌到 $95，浮亏 = (95-100)*10 = -$50
        pos.update_price(95.0)
        assert pos.unrealized_pnl == -50.0

        signal = mon._check_exit_conditions(pos)

        assert signal is not None, "累计亏损超限应触发 DAILY_LIMIT"
        assert signal.reason == ExitReason.DAILY_LIMIT

    def test_daily_limit_not_triggered_when_positive(self):
        """浮盈为正时，即使今日已亏，也不触发 DAILY_LIMIT"""
        rm = self._make_risk_manager(today_pnl=-80.0, daily_limit=100.0)
        mon = _make_monitor(risk_manager=rm)

        pos = _make_pos(
            entry_price=100.0,
            quantity=10,
        )
        pos.highest_price = 100.0
        # 价格上涨到 $105，浮盈 = (105-100)*10 = $50
        pos.update_price(105.0)
        assert pos.unrealized_pnl == 50.0

        signal = mon._check_exit_conditions(pos)

        # 浮盈为正 → unrealized_pnl > 0 → 日亏损检查分支不进入
        assert signal is None


# ============ SELL 方向持仓退出 ============

class TestSellPositionExitConditions:
    """SELL 方向持仓的止损/止盈检测。

    重要发现: 当前 _check_exit_conditions 中 stop_loss/take_profit/trailing_stop/
    partial_take_profit 全部在 `if pos.side == "BUY":` 分支内，
    SELL 方向仅受 time_stop 和 daily_limit 保护。
    这是一个已知的代码缺口，测试记录当前行为以防回归。
    """

    def test_sell_position_stop_loss_not_handled(self):
        """SELL 持仓价格上涨超过 stop_loss 时，当前代码不会触发止损。

        这是因为 stop_loss 检查在 `if pos.side == "BUY"` 块内。
        测试记录此行为，避免误以为 SELL 止损已覆盖。
        """
        mon = _make_monitor()
        pos = _make_pos(
            side="SELL",
            entry_price=100.0,
            stop_loss=105.0,  # SELL 方向止损应在入场价上方
            quantity=10,
        )
        pos.highest_price = 100.0
        # 价格上涨到 $106，超过止损 $105
        pos.update_price(106.0)

        signal = mon._check_exit_conditions(pos)

        # 当前代码 BUG/缺口: SELL 方向止损未实现
        assert signal is None, (
            "SELL 方向 stop_loss 当前未在 _check_exit_conditions 中实现，"
            "signal 应为 None（记录已知缺口）"
        )

    def test_sell_position_take_profit_not_handled(self):
        """SELL 持仓价格下跌超过 take_profit 时，当前代码不会触发止盈。

        同样因为 take_profit 检查在 `if pos.side == "BUY"` 块内。
        """
        mon = _make_monitor()
        pos = _make_pos(
            side="SELL",
            entry_price=100.0,
            take_profit=90.0,  # SELL 方向止盈应在入场价下方
            quantity=10,
        )
        pos.highest_price = 100.0
        # 价格下跌到 $89，超过止盈 $90
        pos.update_price(89.0)

        signal = mon._check_exit_conditions(pos)

        # 当前代码缺口: SELL 方向 take_profit 未实现
        assert signal is None, (
            "SELL 方向 take_profit 当前未在 _check_exit_conditions 中实现，"
            "signal 应为 None（记录已知缺口）"
        )

    def test_sell_position_pnl_calculation(self):
        """验证 SELL 方向浮盈计算正确: 做空价格下跌应为正收益"""
        pos = _make_pos(
            side="SELL",
            entry_price=100.0,
            quantity=10,
        )
        pos.highest_price = 100.0
        pos.update_price(95.0)

        # SELL: pnl = (entry - current) * qty = (100-95)*10 = 50
        assert pos.unrealized_pnl == 50.0
        assert pos.unrealized_pnl_pct == pytest.approx(5.0, abs=0.1)
