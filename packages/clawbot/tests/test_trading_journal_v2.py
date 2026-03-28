"""
TradingJournal v2 测试 — 生命周期完整路径 + 财务计算 + 预测系统。
覆盖 R16 审计中发现的 25 个未测试方法中的关键路径。

> 最后更新: 2026-03-28
"""
import pytest
from src.trading_journal import TradingJournal


@pytest.fixture
def journal(tmp_path):
    """每个测试用例独立的临时数据库"""
    return TradingJournal(db_path=str(tmp_path / "test_v2.db"))


# ══════════════════════════════════════════════════════════════
# Group 1: 交易生命周期 — pending → open → closed / cancelled
# ══════════════════════════════════════════════════════════════

class TestMarkTradeEntryFilled:
    """mark_trade_entry_filled — pending 订单成交回写"""

    def test_fill_pending_trade(self, journal):
        """pending 订单成交后状态变为 open，数量和价格正确回写"""
        tid = journal.open_trade("AAPL", "BUY", 0, 0, status="pending")
        result = journal.mark_trade_entry_filled(tid, filled_qty=100, fill_price=150.0)
        assert "error" not in result
        assert result["status"] == "open"
        assert result["quantity"] == 100.0
        assert result["entry_price"] == 150.0
        # 从数据库再验证一遍
        trade = journal.get_trade(tid)
        assert trade["status"] == "open"
        assert trade["quantity"] == 100.0

    def test_fill_zero_quantity_rejected(self, journal):
        """filled_qty=0 → 拒绝"""
        tid = journal.open_trade("AAPL", "BUY", 0, 0, status="pending")
        result = journal.mark_trade_entry_filled(tid, filled_qty=0, fill_price=150.0)
        assert "error" in result

    def test_fill_negative_price_rejected(self, journal):
        """fill_price < 0 → 拒绝"""
        tid = journal.open_trade("AAPL", "BUY", 0, 0, status="pending")
        result = journal.mark_trade_entry_filled(tid, filled_qty=10, fill_price=-5.0)
        assert "error" in result

    def test_fill_nonexistent_trade(self, journal):
        """trade_id 不存在 → 错误"""
        result = journal.mark_trade_entry_filled(9999, filled_qty=100, fill_price=150.0)
        assert "error" in result

    def test_fill_preserves_existing_order_id(self, journal):
        """不传 entry_order_id 时保留原有 order_id"""
        tid = journal.open_trade("AAPL", "BUY", 0, 0, status="pending",
                                  entry_order_id="ORD-001")
        result = journal.mark_trade_entry_filled(tid, filled_qty=50, fill_price=155.0)
        assert result["entry_order_id"] == "ORD-001"


class TestCancelTrade:
    """cancel_trade — 取消交易"""

    def test_cancel_open_trade(self, journal):
        """取消一个 open 状态的交易"""
        tid = journal.open_trade("AAPL", "BUY", 100, 150.0)
        result = journal.cancel_trade(tid, reason="测试取消")
        assert "error" not in result
        assert result["status"] == "cancelled"
        trade = journal.get_trade(tid)
        assert trade["status"] == "cancelled"
        assert trade["exit_time"] is not None

    def test_cancel_pending_trade(self, journal):
        """取消一个 pending 状态的交易"""
        tid = journal.open_trade("MSFT", "BUY", 0, 0, status="pending")
        result = journal.cancel_trade(tid, reason="限价单撤单")
        assert result["status"] == "cancelled"

    def test_cancel_nonexistent(self, journal):
        """trade_id 不存在"""
        result = journal.cancel_trade(9999)
        assert "error" in result

    def test_cancel_already_closed(self, journal):
        """已关闭的交易不能再取消"""
        tid = journal.open_trade("AAPL", "BUY", 100, 150.0)
        journal.close_trade(tid, exit_price=160.0)
        result = journal.cancel_trade(tid)
        assert "error" in result

    def test_cancel_already_cancelled(self, journal):
        """已取消的交易不能再次取消"""
        tid = journal.open_trade("AAPL", "BUY", 100, 150.0)
        journal.cancel_trade(tid)
        result = journal.cancel_trade(tid)
        assert "error" in result


class TestGetPendingTrades:
    """get_pending_trades — 获取待成交订单"""

    def test_returns_pending_only(self, journal):
        """只返回 pending 状态的交易"""
        journal.open_trade("AAPL", "BUY", 100, 150.0, status="open")
        journal.open_trade("MSFT", "BUY", 50, 300.0, status="pending")
        journal.open_trade("GOOG", "SELL", 20, 170.0, status="open")
        pending = journal.get_pending_trades()
        assert len(pending) == 1
        assert pending[0]["symbol"] == "MSFT"

    def test_empty_when_no_pending(self, journal):
        """没有 pending 交易时返回空列表"""
        journal.open_trade("AAPL", "BUY", 100, 150.0)
        assert journal.get_pending_trades() == []


# ══════════════════════════════════════════════════════════════
# Group 2: 财务计算
# ══════════════════════════════════════════════════════════════

class TestGetTodayPnl:
    """get_today_pnl — 当日盈亏"""

    def test_no_trades_today(self, journal):
        """无交易时 pnl=0"""
        result = journal.get_today_pnl()
        assert result["pnl"] == 0
        assert result["trades"] == 0
        assert result["hit_limit"] is False

    def test_with_winning_trade(self, journal):
        """今天有盈利交易"""
        tid = journal.open_trade("AAPL", "BUY", 10, 100.0)
        journal.close_trade(tid, exit_price=110.0)  # pnl = +100
        result = journal.get_today_pnl()
        assert result["pnl"] == pytest.approx(100.0, abs=0.01)
        assert result["trades"] == 1

    def test_daily_limit_hit(self, journal):
        """当日亏损超过限额 → hit_limit=True"""
        journal.set_config("daily_loss_limit", "50")
        tid = journal.open_trade("AAPL", "BUY", 10, 100.0)
        journal.close_trade(tid, exit_price=94.0)  # pnl = -60 > limit 50
        result = journal.get_today_pnl()
        assert result["hit_limit"] is True


class TestGetEquityCurve:
    """get_equity_curve — 权益曲线"""

    def test_empty_journal(self, journal):
        """无交易返回空列表"""
        values, dates = journal.get_equity_curve()
        assert values == []
        assert dates == []

    def test_with_trades(self, journal):
        """有交易时权益曲线正确累计"""
        journal.set_config("initial_capital", "10000")
        tid = journal.open_trade("AAPL", "BUY", 10, 100.0)
        journal.close_trade(tid, exit_price=110.0)  # pnl = +100
        values, dates = journal.get_equity_curve()
        assert len(dates) >= 1
        # 最终权益 = 初始资本 + 盈亏
        assert values[-1] == pytest.approx(10100.0, abs=1.0)


# ══════════════════════════════════════════════════════════════
# Group 3: 边界情况
# ══════════════════════════════════════════════════════════════

class TestEdgeCases:
    """边界条件测试"""

    def test_zero_profit_counted_as_loss(self, journal):
        """零收益交易（买卖价相同）应计入亏损而非盈利"""
        tid = journal.open_trade("AAPL", "BUY", 10, 100.0)
        journal.close_trade(tid, exit_price=100.0)  # pnl = 0
        perf = journal.get_performance()
        # pnl <= 0 算亏损
        assert perf["wins"] == 0
        assert perf["losses"] == 1

    def test_all_wins_profit_factor(self, journal):
        """全部盈利交易 → profit_factor 为 999 或 inf"""
        tid = journal.open_trade("AAPL", "BUY", 10, 100.0)
        journal.close_trade(tid, exit_price=110.0)
        perf = journal.get_performance()
        assert perf["profit_factor"] >= 999

    def test_get_trade_nonexistent(self, journal):
        """查询不存在的交易返回 None"""
        assert journal.get_trade(9999) is None

    def test_get_closed_trades(self, journal):
        """get_closed_trades 只返回已关闭交易"""
        tid1 = journal.open_trade("AAPL", "BUY", 10, 100.0)
        journal.close_trade(tid1, exit_price=110.0)
        journal.open_trade("MSFT", "BUY", 10, 200.0)  # 保持 open
        closed = journal.get_closed_trades()
        assert len(closed) == 1
        assert closed[0]["symbol"] == "AAPL"
