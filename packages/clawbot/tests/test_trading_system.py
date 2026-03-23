"""Tests for src.trading_system module."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import src.trading_system as ts


@pytest.fixture(autouse=True)
def reset_globals():
    ts._initialized = False
    ts._risk_manager = None
    ts._position_monitor = None
    ts._trading_pipeline = None
    ts._auto_trader = None
    ts._scheduler = None
    ts._quote_cache = None
    ts._rebalancer = None
    ts._ai_team_api_callers = {}
    yield
    ts._initialized = False
    ts._risk_manager = None
    ts._position_monitor = None
    ts._trading_pipeline = None
    ts._auto_trader = None
    ts._scheduler = None
    ts._quote_cache = None
    ts._rebalancer = None
    ts._ai_team_api_callers = {}


# ============ _parse_datetime ============

class TestParseDatetime:
    """Tests for _parse_datetime — ensures timezone-aware datetime output."""

    def test_naive_iso_string_gets_et_timezone(self):
        """Naive datetime strings should be tagged with America/New_York."""
        result = ts._parse_datetime("2026-03-23T14:30:00")
        assert result is not None
        assert result.tzinfo is not None
        assert result.year == 2026
        assert result.hour == 14

    def test_aware_iso_string_preserved(self):
        """Already timezone-aware strings should keep their timezone."""
        result = ts._parse_datetime("2026-03-23T14:30:00+00:00")
        assert result is not None
        assert result.tzinfo is not None
        # UTC offset should be preserved
        assert result.utcoffset() == timedelta(0)

    def test_invalid_string_returns_none(self):
        """Invalid datetime strings should return None, not raise."""
        assert ts._parse_datetime("not-a-date") is None
        assert ts._parse_datetime("") is None

    def test_date_only_string(self):
        """Date-only strings (no time) should parse correctly."""
        result = ts._parse_datetime("2026-03-23")
        assert result is not None
        assert result.tzinfo is not None
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 23

    def test_result_can_compare_with_now_et(self):
        """Parsed result should be comparable with now_et() (both aware)."""
        from src.utils import now_et
        result = ts._parse_datetime("2026-03-23T14:30:00")
        assert result is not None
        # Should not raise TypeError (aware vs naive comparison)
        diff = now_et() - result
        assert isinstance(diff, timedelta)


# ============ set_ai_team_callers ============

class TestSetAiTeamCallers:
    def test_sets_global_dict(self):
        callers = {"bot1": AsyncMock(), "bot2": AsyncMock()}
        ts.set_ai_team_callers(callers)
        assert ts._ai_team_api_callers is callers

    def test_overwrites_previous(self):
        ts.set_ai_team_callers({"old": AsyncMock()})
        new = {"new": AsyncMock()}
        ts.set_ai_team_callers(new)
        assert ts._ai_team_api_callers is new


# ============ init_trading_system ============

def _init_patches():
    """Return a dict of patch objects for all lazy imports in init_trading_system."""
    return {
        "RiskManager": patch("src.risk_manager.RiskManager"),
        "RiskConfig": patch("src.risk_manager.RiskConfig"),
        "PositionMonitor": patch("src.position_monitor.PositionMonitor"),
        "TradingPipeline": patch("src.auto_trader.TradingPipeline"),
        "AutoTrader": patch("src.auto_trader.AutoTrader"),
        "DecisionValidator": patch("src.decision_validator.DecisionValidator"),
        "QuoteCache": patch("src.quote_cache.QuoteCache"),
        "CacheConfig": patch("src.quote_cache.CacheConfig"),
        "Rebalancer": patch("src.rebalancer.Rebalancer"),
    }


class TestInitTradingSystem:
    def test_double_init_guard(self):
        """Second call with _initialized=True should be a no-op."""
        ts._initialized = True
        ts.init_trading_system(broker=MagicMock(), portfolio=MagicMock())
        # Nothing created
        assert ts._risk_manager is None

    def test_with_broker_and_portfolio(self):
        patches = _init_patches()
        mocks = {k: p.start() for k, p in patches.items()}
        try:
            broker = MagicMock()
            portfolio = MagicMock()
            ts.init_trading_system(broker=broker, portfolio=portfolio)

            assert ts._initialized is True
            mocks["RiskConfig"].assert_called_once()
            mocks["RiskManager"].assert_called_once()
            mocks["PositionMonitor"].assert_called_once()
            mocks["TradingPipeline"].assert_called_once()
            mocks["AutoTrader"].assert_called_once()
            mocks["QuoteCache"].assert_called_once()
            mocks["Rebalancer"].assert_called_once()
            assert ts._risk_manager is not None
            assert ts._position_monitor is not None
            assert ts._trading_pipeline is not None
            assert ts._auto_trader is not None
            assert ts._quote_cache is not None
            assert ts._rebalancer is not None
        finally:
            for p in patches.values():
                p.stop()

    def test_without_broker_portfolio_only(self):
        patches = _init_patches()
        mocks = {k: p.start() for k, p in patches.items()}
        try:
            portfolio = MagicMock()
            ts.init_trading_system(portfolio=portfolio, get_quote_func=AsyncMock())

            assert ts._initialized is True
            mocks["PositionMonitor"].assert_called_once()
            # sell_func should be the _sim_sell wrapper (not None)
            call_kwargs = mocks["PositionMonitor"].call_args
            assert call_kwargs[1]["execute_sell_func"] is not None
        finally:
            for p in patches.values():
                p.stop()

    def test_without_anything(self):
        patches = _init_patches()
        mocks = {k: p.start() for k, p in patches.items()}
        try:
            ts.init_trading_system()

            assert ts._initialized is True
            call_kwargs = mocks["PositionMonitor"].call_args
            assert call_kwargs[1]["execute_sell_func"] is None
        finally:
            for p in patches.values():
                p.stop()

    def test_custom_capital(self):
        patches = _init_patches()
        mocks = {k: p.start() for k, p in patches.items()}
        try:
            ts.init_trading_system(capital=5000.0)
            mocks["RiskConfig"].assert_called_once_with(total_capital=5000.0)
        finally:
            for p in patches.values():
                p.stop()


# ============ Getter functions ============

class TestGetters:
    def test_get_risk_manager_none(self):
        assert ts.get_risk_manager() is None

    def test_get_risk_manager_set(self):
        sentinel = object()
        ts._risk_manager = sentinel
        assert ts.get_risk_manager() is sentinel

    def test_get_position_monitor(self):
        sentinel = object()
        ts._position_monitor = sentinel
        assert ts.get_position_monitor() is sentinel

    def test_get_trading_pipeline(self):
        sentinel = object()
        ts._trading_pipeline = sentinel
        assert ts.get_trading_pipeline() is sentinel

    def test_get_auto_trader(self):
        sentinel = object()
        ts._auto_trader = sentinel
        assert ts.get_auto_trader() is sentinel

    def test_get_quote_cache(self):
        sentinel = object()
        ts._quote_cache = sentinel
        assert ts.get_quote_cache() is sentinel

    def test_get_rebalancer(self):
        sentinel = object()
        ts._rebalancer = sentinel
        assert ts.get_rebalancer() is sentinel


# ============ get_system_status ============

class TestGetSystemStatus:
    def test_not_initialized(self):
        # Patch broker_bridge so the import inside get_system_status raises
        with patch.dict("sys.modules", {"src.broker_bridge": None}):
            result = ts.get_system_status()
        assert result == "交易系统未初始化"

    @patch("src.trading_system._risk_manager")
    def test_initialized_with_components(self, _mock_rm):
        rm = MagicMock()
        rm.format_status.return_value = "Risk: OK"
        ts._risk_manager = rm

        pm = MagicMock()
        pm.format_status.return_value = "Monitor: 0 positions"
        ts._position_monitor = pm

        at = MagicMock()
        at.format_status.return_value = "AutoTrader: idle"
        ts._auto_trader = at

        with patch("src.broker_bridge.ibkr") as mock_ibkr:
            mock_ibkr.get_connection_status.return_value = "IBKR: connected"
            mock_ibkr.is_connected.return_value = True
            mock_ibkr.budget = 1000.0
            mock_ibkr.total_spent = 200.0

            status = ts.get_system_status()

        assert "Risk: OK" in status
        assert "Monitor: 0 positions" in status
        assert "AutoTrader: idle" in status
        assert "IBKR: connected" in status


# ============ stop_trading_system ============

class TestStopTradingSystem:
    async def test_stop_calls_all_components(self):
        pm = MagicMock()
        pm.stop = AsyncMock()
        ts._position_monitor = pm

        at = MagicMock()
        at.stop = AsyncMock()
        ts._auto_trader = at

        qc = MagicMock()
        qc.stop = AsyncMock()
        ts._quote_cache = qc

        sched = MagicMock()
        ts._scheduler = sched

        await ts.stop_trading_system()

        pm.stop.assert_awaited_once()
        at.stop.assert_awaited_once()
        qc.stop.assert_awaited_once()
        sched.stop.assert_called_once()

    async def test_stop_with_no_components(self):
        # Should not raise
        await ts.stop_trading_system()


# ============ start_trading_system ============

class TestStartTradingSystem:
    async def test_guard_not_initialized(self):
        """Should return early when not initialized."""
        await ts.start_trading_system()
        # No error, nothing happened
        assert ts._scheduler is None

    @patch("src.trading_system._risk_manager")
    async def test_start_runs_components(self, _mock_rm):
        ts._initialized = True

        pm = MagicMock()
        pm.start = AsyncMock()
        pm.positions = {}
        ts._position_monitor = pm

        at = MagicMock()
        at.start = AsyncMock()
        at.auto_mode = False
        at.scan_interval = 30
        ts._auto_trader = at

        rm = MagicMock()
        ts._risk_manager = rm

        mock_scheduler_cls = MagicMock()
        mock_scheduler_inst = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler_inst

        with patch("src.trading_journal.journal") as mock_tj, \
             patch("src.scheduler.Scheduler", mock_scheduler_cls), \
             patch("src.broker_bridge.ibkr") as mock_ibkr:
            mock_tj.get_open_trades.return_value = []
            mock_tj.get_today_pnl.return_value = {"pnl": 0, "trades": 0}
            mock_ibkr.is_connected.return_value = False

            await ts.start_trading_system()

        pm.start.assert_awaited_once()
        at.start.assert_awaited_once()
        mock_scheduler_inst.start.assert_called_once()
