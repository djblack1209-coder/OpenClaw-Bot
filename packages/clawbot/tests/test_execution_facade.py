"""
Tests for ExecutionHub Facade — unified execution interface.

Covers: method delegation, __getattr__ fallback,
        private attribute blocking, monitor helpers.

v3.0: _get_legacy removed — all methods delegate to modular submodules.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from src.execution import ExecutionHub


# ============ Fixtures ============

@pytest.fixture
def hub(tmp_path):
    """ExecutionHub with mocked DB paths."""
    with patch("src.execution._db.DB_PATH", tmp_path / "test.db"), \
         patch("src.execution._db.ensure_db_dir"), \
         patch("src.execution._db.init_db"), \
         patch("src.execution.MonitorManager"), \
         patch("src.execution.ExecutionScheduler"):
        h = ExecutionHub(news_fetcher=MagicMock())
    return h


# ============ Explicit method delegation ============

class TestExplicitDelegation:

    def test_add_monitor_delegates_to_monitor_mgr(self, hub):
        """add_monitor should delegate to _monitor_mgr."""
        hub._monitor_mgr.add_monitor = MagicMock(return_value={"ok": True})
        result = hub.add_monitor("AI", "news")
        hub._monitor_mgr.add_monitor.assert_called_once_with("AI", "news")
        assert result == {"ok": True}

    def test_list_monitors_delegates(self, hub):
        """list_monitors should delegate to _monitor_mgr."""
        hub._monitor_mgr.list_monitors = MagicMock(return_value=[])
        result = hub.list_monitors()
        assert result == []

    async def test_run_monitors_once_delegates(self, hub):
        """run_monitors_once should delegate to _monitor_mgr."""
        hub._monitor_mgr.run_monitors_once = AsyncMock(return_value={"alerts": []})
        result = await hub.run_monitors_once()
        hub._monitor_mgr.run_monitors_once.assert_awaited_once()
        assert result == {"alerts": []}

    async def test_start_scheduler_delegates(self, hub):
        """start_scheduler should delegate to _scheduler."""
        hub._scheduler.start = AsyncMock()
        notify = AsyncMock()
        await hub.start_scheduler(notify)
        hub._scheduler.start.assert_awaited_once_with(notify, None)

    async def test_stop_scheduler_delegates(self, hub):
        """stop_scheduler should delegate to _scheduler."""
        hub._scheduler.stop = AsyncMock()
        await hub.stop_scheduler()
        hub._scheduler.stop.assert_awaited_once()


# ============ Legacy delegation (v3.0: now direct module delegation) ============

class TestLegacyDelegation:

    def test_legacy_get_legacy_removed(self, hub):
        """_get_legacy has been removed in v3.0 — no legacy fallback."""
        assert not hasattr(ExecutionHub, '_get_legacy')

    async def test_scan_bounties_delegates_to_module(self, hub):
        """scan_bounties should delegate to bounty module."""
        with patch("src.execution.bounty.scan_bounties", new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = {"found": 5}
            result = await hub.scan_bounties(keywords=["python"])
            mock_scan.assert_awaited_once()
            assert result == {"found": 5}

    def test_get_post_performance_report_delegates(self, hub):
        """get_post_performance_report should delegate to content_pipeline."""
        with patch("src.execution.social.content_pipeline.get_post_performance_report") as mock_report:
            mock_report.return_value = {"posts": 10}
            result = hub.get_post_performance_report(days=14)
            assert result == {"posts": 10}


# ============ __getattr__ fallback (v3.0: now raises AttributeError) ============

class TestGetattr:

    def test_private_attribute_raises(self, hub):
        """__getattr__ should raise AttributeError for private attrs."""
        with pytest.raises(AttributeError, match="has no attribute"):
            _ = hub._some_nonexistent_private_method

    def test_unknown_method_raises_error(self, hub):
        """__getattr__ for unknown method should raise AttributeError in v3.0."""
        with pytest.raises(AttributeError, match="has no attribute"):
            _ = hub.totally_nonexistent_method_xyz

    def test_unknown_method_no_fallback(self, hub):
        """v3.0: No legacy fallback — unknown methods always raise."""
        with pytest.raises(AttributeError):
            _ = hub.some_unknown_method


# ============ Helper methods ============

class TestHelperMethods:

    def test_clean_monitor_title_removes_source_suffix(self, hub):
        """_clean_monitor_title should remove source suffix from title."""
        result = hub._clean_monitor_title(
            "AI Breakthrough - TechCrunch", "TechCrunch"
        )
        assert result == "AI Breakthrough"

    def test_clean_monitor_title_preserves_clean(self, hub):
        """_clean_monitor_title should preserve titles without suffix."""
        result = hub._clean_monitor_title("Clean Title", "OtherSource")
        assert result == "Clean Title"

    def test_is_low_value_detects_blocked_source(self, hub):
        """_is_low_value_monitor_item should detect blocked sources."""
        result = hub._is_low_value_monitor_item("Some Title", "新浪财经")
        assert result is True

    def test_is_low_value_passes_good_content(self, hub):
        """_is_low_value_monitor_item should pass quality content."""
        result = hub._is_low_value_monitor_item("OpenAI releases GPT-5", "Reuters")
        assert result is False

    def test_monitor_env_list_parses_csv(self, hub):
        """_monitor_env_list should parse comma-separated env values."""
        with patch.dict("os.environ", {"TEST_LIST": "a, b, c"}):
            result = hub._monitor_env_list("TEST_LIST")
        assert result == ["a", "b", "c"]

    def test_monitor_env_list_returns_default(self, hub):
        """_monitor_env_list should return default when env not set."""
        with patch.dict("os.environ", {}, clear=True):
            result = hub._monitor_env_list("NONEXISTENT_VAR", "x,y")
        assert result == ["x", "y"]

    def test_curate_monitor_items_deduplicates(self, hub):
        """_curate_monitor_items should deduplicate by normalized title."""
        items = [
            {"title": "AI News Today", "source": "Reuters", "url": "http://a"},
            {"title": "AI News Today", "source": "AP", "url": "http://b"},
            {"title": "Different Story", "source": "Reuters", "url": "http://c"},
        ]
        result = hub._curate_monitor_items(items, limit=10)
        # Should deduplicate the two "AI News Today" entries
        titles = [r["title"] for r in result]
        assert titles.count("AI News Today") <= 1

    def test_curate_monitor_items_respects_limit(self, hub):
        """_curate_monitor_items should respect the limit parameter."""
        items = [
            {"title": f"Story {i}", "source": "Reuters", "url": f"http://{i}"}
            for i in range(20)
        ]
        result = hub._curate_monitor_items(items, limit=5)
        assert len(result) <= 5


# ============ Social browser status ============

class TestSocialBrowserStatus:

    def test_returns_correct_structure(self, hub):
        """get_social_browser_status should return expected keys."""
        status = hub.get_social_browser_status()
        assert "browser_running" in status
        assert status["browser_running"] is False
        assert "x_ready" in status
        assert "xiaohongshu_ready" in status
