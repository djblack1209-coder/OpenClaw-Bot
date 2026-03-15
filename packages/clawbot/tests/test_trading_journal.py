"""
trading_journal 单元测试 — 覆盖交易生命周期、绩效计算、边界条件
"""
import os
import tempfile
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta

from src.trading_journal import TradingJournal


@pytest.fixture
def journal(tmp_path):
    """使用临时文件创建 TradingJournal 实例"""
    db_path = str(tmp_path / "test_trading.db")
    return TradingJournal(db_path=db_path)


@pytest.fixture
def mock_now_et():
    """Mock now_et 返回固定时间"""
    fixed_time = datetime(2025, 2, 24, 10, 30, 0)
    with patch("src.trading_journal.now_et", return_value=fixed_time) as mock:
        yield mock, fixed_time


# ============ 配置 ============

class TestConfig:
    def test_default_config(self, journal):
        assert journal.get_config("initial_capital") == "2000"
        assert journal.get_config("daily_loss_limit") == "100"

    def test_set_and_get_config(self, journal):
        journal.set_config("test_key", "test_value")
        assert journal.get_config("test_key") == "test_value"

    def test_get_missing_config_returns_default(self, journal):
        assert journal.get_config("nonexistent", "fallback") == "fallback"

    def test_overwrite_config(self, journal):
        journal.set_config("initial_capital", "50000")
        assert journal.get_config("initial_capital") == "50000"


# ============ 开仓 ============

class TestOpenTrade:
    def test_basic_open(self, journal):
        trade_id = journal.open_trade(
            symbol="AAPL", side="BUY", quantity=10,
            entry_price=150.0, entry_reason="RSI超卖",
        )
        assert trade_id > 0

        trade = journal.get_trade(trade_id)
        assert trade["symbol"] == "AAPL"
        assert trade["side"] == "BUY"
        assert trade["quantity"] == 10
        assert trade["entry_price"] == 150.0
        assert trade["status"] == "open"

    def test_symbol_uppercased(self, journal):
        trade_id = journal.open_trade("aapl", "buy", 5, 150.0)
        trade = journal.get_trade(trade_id)
        assert trade["symbol"] == "AAPL"
        assert trade["side"] == "BUY"

    def test_open_multiple_trades(self, journal):
        id1 = journal.open_trade("AAPL", "BUY", 10, 150.0)
        id2 = journal.open_trade("MSFT", "BUY", 5, 400.0)
        assert id1 != id2

        open_trades = journal.get_open_trades()
        assert len(open_trades) == 2

    def test_open_with_all_fields(self, journal):
        trade_id = journal.open_trade(
            symbol="NVDA", side="BUY", quantity=20,
            entry_price=800.0, entry_order_id="ORD-123",
            stop_loss=780.0, take_profit=850.0,
            signal_score=65, ai_analysis="强势突破",
            entry_reason="放量突破阻力位", decided_by="Qwen",
        )
        trade = journal.get_trade(trade_id)
        assert trade["stop_loss"] == 780.0
        assert trade["take_profit"] == 850.0
        assert trade["signal_score"] == 65
        assert trade["decided_by"] == "Qwen"


# ============ 平仓 ============

class TestCloseTrade:
    def test_close_winning_buy(self, journal):
        trade_id = journal.open_trade("AAPL", "BUY", 10, 150.0)
        result = journal.close_trade(trade_id, exit_price=160.0, fees=5.0)

        assert result["pnl"] == 95.0  # (160-150)*10 - 5
        assert result["pnl_pct"] == pytest.approx(6.33, abs=0.1)
        assert result["trade_id"] == trade_id

        trade = journal.get_trade(trade_id)
        assert trade["status"] == "closed"

    def test_close_losing_buy(self, journal):
        trade_id = journal.open_trade("AAPL", "BUY", 10, 150.0)
        result = journal.close_trade(trade_id, exit_price=140.0)

        assert result["pnl"] == -100.0  # (140-150)*10

    def test_close_winning_sell(self, journal):
        trade_id = journal.open_trade("TSLA", "SELL", 5, 200.0)
        result = journal.close_trade(trade_id, exit_price=180.0)

        assert result["pnl"] == 100.0  # (200-180)*5

    def test_close_nonexistent_trade(self, journal):
        result = journal.close_trade(9999, exit_price=100.0)
        assert "error" in result

    def test_close_already_closed_trade(self, journal):
        trade_id = journal.open_trade("AAPL", "BUY", 10, 150.0)
        journal.close_trade(trade_id, exit_price=160.0)
        result = journal.close_trade(trade_id, exit_price=170.0)
        assert "error" in result

    def test_close_removes_from_open(self, journal):
        trade_id = journal.open_trade("AAPL", "BUY", 10, 150.0)
        assert len(journal.get_open_trades()) == 1
        journal.close_trade(trade_id, exit_price=160.0)
        assert len(journal.get_open_trades()) == 0


# ============ 绩效统计 ============

class TestGetPerformance:
    def test_empty_trades(self, journal):
        perf = journal.get_performance()
        assert perf["total_trades"] == 0
        assert perf["win_rate"] == 0
        assert perf["sharpe"] == 0

    def test_single_winning_trade(self, journal):
        tid = journal.open_trade("AAPL", "BUY", 10, 150.0)
        journal.close_trade(tid, exit_price=160.0)

        perf = journal.get_performance()
        assert perf["total_trades"] == 1
        assert perf["win_rate"] == 100.0
        assert perf["total_pnl"] == 100.0
        assert perf["wins"] == 1
        assert perf["losses"] == 0
        assert perf["sharpe"] == 0  # stdev=0 with single trade

    def test_mixed_wins_and_losses(self, journal):
        # 3 wins, 2 losses
        for price_out in [160, 155, 165]:  # wins
            tid = journal.open_trade("AAPL", "BUY", 10, 150.0)
            journal.close_trade(tid, exit_price=float(price_out))
        for price_out in [140, 135]:  # losses
            tid = journal.open_trade("AAPL", "BUY", 10, 150.0)
            journal.close_trade(tid, exit_price=float(price_out))

        perf = journal.get_performance()
        assert perf["total_trades"] == 5
        assert perf["wins"] == 3
        assert perf["losses"] == 2
        assert perf["win_rate"] == 60.0
        assert perf["total_pnl"] == pytest.approx(100 + 50 + 150 - 100 - 150, abs=0.1)
        assert perf["max_win"] > 0
        assert perf["max_loss"] < 0
        assert perf["profit_factor"] > 0

    def test_all_losses(self, journal):
        for _ in range(3):
            tid = journal.open_trade("AAPL", "BUY", 10, 150.0)
            journal.close_trade(tid, exit_price=140.0)

        perf = journal.get_performance()
        assert perf["win_rate"] == 0
        assert perf["total_pnl"] < 0
        # profit_factor with no wins: sum(wins)=0, so 0/sum(losses)=0
        assert perf["profit_factor"] == 0

    def test_consecutive_wins_tracking(self, journal):
        # W W W L W
        exits = [160, 155, 165, 140, 155]
        for ep in exits:
            tid = journal.open_trade("AAPL", "BUY", 10, 150.0)
            journal.close_trade(tid, exit_price=float(ep))

        perf = journal.get_performance()
        assert perf["consecutive_wins"] == 3
        assert perf["consecutive_losses"] == 1

    def test_max_drawdown(self, journal):
        # +100, +50, -200, +30 → peak=150, trough=-20, dd=170
        exits = [160, 155, 130, 153]
        for ep in exits:
            tid = journal.open_trade("AAPL", "BUY", 10, 150.0)
            journal.close_trade(tid, exit_price=float(ep))

        perf = journal.get_performance()
        assert perf["max_drawdown"] > 0


# ============ 复盘 ============

class TestReview:
    def test_add_review(self, journal):
        tid = journal.open_trade("AAPL", "BUY", 10, 150.0)
        journal.add_review(tid, "好的入场时机", review_score=4, lessons="耐心等待信号")

        trade = journal.get_trade(tid)
        assert trade["review_notes"] == "好的入场时机"
        assert trade["review_score"] == 4

    def test_save_and_get_review_session(self, journal):
        session_id = journal.save_review_session(
            date="2025-02-24",
            trades_reviewed=5,
            total_pnl=250.0,
            win_rate=60.0,
            market_summary="市场震荡上行",
        )
        assert session_id > 0

        latest = journal.get_latest_review()
        assert latest["date"] == "2025-02-24"
        assert latest["total_pnl"] == 250.0

    def test_no_review_returns_none(self, journal):
        assert journal.get_latest_review() is None


# ============ 格式化 ============

class TestFormatPerformance:
    def test_empty_format(self, journal):
        text = journal.format_performance()
        assert "暂无交易记录" in text

    def test_with_trades_format(self, journal):
        tid = journal.open_trade("AAPL", "BUY", 10, 150.0)
        journal.close_trade(tid, exit_price=160.0)

        text = journal.format_performance()
        assert "绩效仪表盘" in text
        assert "胜率" in text
        assert "总盈亏" in text
