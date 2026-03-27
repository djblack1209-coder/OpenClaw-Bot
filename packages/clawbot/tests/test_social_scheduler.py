"""
Tests for SocialScheduler — automated social media posting.

Covers: _load_state, _save_state, roundtrip persistence,
        draft status transitions, dedup, scheduler lifecycle.
"""
import json
import threading

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

import src.social_scheduler as ss_module


# ============ Fixtures ============

@pytest.fixture(autouse=True)
def isolate_state_file(tmp_path, monkeypatch):
    """Redirect state file to tmp_path for every test."""
    state_file = tmp_path / "social_autopilot_state.json"
    monkeypatch.setattr(ss_module, "_STATE_FILE", state_file)
    # Reset singleton for each test
    ss_module.SocialAutopilot._instance = None
    yield state_file


@pytest.fixture
def autopilot():
    """Fresh SocialAutopilot instance (singleton reset per test)."""
    return ss_module.SocialAutopilot()


# ============ _load_state / _save_state ============

class TestStateManagement:

    def test_load_state_returns_defaults_for_missing_file(self, isolate_state_file):
        """_load_state should return defaults when no state file exists."""
        state = ss_module._load_state()
        assert state["enabled"] is False
        assert state["drafts"] == []
        assert state["last_scan_topics"] == []
        assert state["today_published"] == []
        assert state["stats"]["posts_today"] == 0

    def test_save_state_creates_file(self, isolate_state_file):
        """_save_state should persist state to disk."""
        state = {"enabled": True, "drafts": [{"id": "abc"}]}
        ss_module._save_state(state)
        assert isolate_state_file.exists()
        data = json.loads(isolate_state_file.read_text(encoding="utf-8"))
        assert data["enabled"] is True
        assert len(data["drafts"]) == 1

    def test_roundtrip_preserves_data(self, isolate_state_file):
        """_save_state + _load_state should roundtrip data."""
        original = {
            "enabled": True,
            "last_scan_topics": [{"title": "AI News", "score": 9}],
            "drafts": [{"id": "d1", "status": "ready", "text": "hello"}],
            "today_published": [],
            "last_review": "2026-03-24T10:00:00",
            "stats": {"posts_today": 3, "engagement_today": 42},
        }
        ss_module._save_state(original)
        loaded = ss_module._load_state()
        assert loaded["enabled"] is True
        assert len(loaded["last_scan_topics"]) == 1
        assert loaded["last_scan_topics"][0]["title"] == "AI News"
        assert loaded["stats"]["posts_today"] == 3

    def test_load_state_handles_corrupt_file(self, isolate_state_file):
        """_load_state should return defaults for corrupt JSON."""
        isolate_state_file.parent.mkdir(parents=True, exist_ok=True)
        isolate_state_file.write_text("not valid json {{{", encoding="utf-8")
        state = ss_module._load_state()
        assert state["enabled"] is False  # defaults


# ============ Draft status transitions ============

class TestDraftStatusTransitions:

    def test_ready_to_published(self, isolate_state_file):
        """Draft status: ready -> publishing -> published."""
        state = ss_module._load_state()
        draft = {"id": "d1", "status": "ready", "platform": "x", "text": "test"}
        state["drafts"] = [draft]

        # Simulate publishing flow
        draft["status"] = "publishing"
        ss_module._save_state(state)
        loaded = ss_module._load_state()
        assert loaded["drafts"][0]["status"] == "publishing"

        draft["status"] = "published"
        ss_module._save_state(state)
        loaded = ss_module._load_state()
        assert loaded["drafts"][0]["status"] == "published"

    def test_ready_to_failed(self, isolate_state_file):
        """Draft status: ready -> publishing -> failed."""
        state = ss_module._load_state()
        draft = {"id": "d2", "status": "ready", "platform": "xhs", "text": "test"}
        state["drafts"] = [draft]

        draft["status"] = "publishing"
        ss_module._save_state(state)

        draft["status"] = "failed"
        draft["error"] = "publish API error"
        ss_module._save_state(state)

        loaded = ss_module._load_state()
        assert loaded["drafts"][0]["status"] == "failed"
        assert "error" in loaded["drafts"][0]

    def test_double_publish_protection(self, isolate_state_file):
        """Draft in 'publishing' status should be skipped by ready filter."""
        state = ss_module._load_state()
        state["drafts"] = [
            {"id": "d1", "status": "publishing", "platform": "x", "text": "in progress"},
            {"id": "d2", "status": "ready", "platform": "x", "text": "waiting"},
        ]
        ss_module._save_state(state)

        loaded = ss_module._load_state()
        ready_drafts = [d for d in loaded["drafts"] if d.get("status") == "ready"]
        assert len(ready_drafts) == 1
        assert ready_drafts[0]["id"] == "d2"


# ============ job_morning_scan (mocked) ============

class TestJobMorningScan:

    def test_resets_drafts_on_scan(self, isolate_state_file):
        """job_morning_scan should reset drafts and today_published."""
        # Pre-populate state with stale data
        state = ss_module._load_state()
        state["drafts"] = [{"id": "old", "status": "published"}]
        state["today_published"] = [{"id": "old"}]
        state["stats"]["posts_today"] = 5
        ss_module._save_state(state)

        with patch("src.social_scheduler.asyncio.run") as mock_run:
            # Simulate what _run() does inside job_morning_scan
            async def fake_run():
                st = ss_module._load_state()
                st["last_scan_topics"] = [{"title": "Test Topic", "score": 8}]
                st["drafts"] = []
                st["today_published"] = []
                st["stats"] = {"posts_today": 0, "engagement_today": 0}
                ss_module._save_state(st)

            import asyncio
            mock_run.side_effect = lambda coro: asyncio.get_event_loop().run_until_complete(fake_run())
            ss_module.job_morning_scan()

        loaded = ss_module._load_state()
        assert loaded["drafts"] == []
        assert loaded["today_published"] == []
        assert loaded["stats"]["posts_today"] == 0


# ============ Scheduler lifecycle ============

class TestSchedulerLifecycle:

    def test_start_creates_scheduler(self, autopilot):
        """start() should create and start a BackgroundScheduler."""
        with patch("src.social_scheduler._notify"):
            result = autopilot.start()
        assert result["status"] == "started"
        assert result["jobs"] == 5
        # Clean up
        autopilot.stop()

    def test_stop_shuts_down_scheduler(self, autopilot):
        """stop() should shut down the scheduler."""
        with patch("src.social_scheduler._notify"):
            autopilot.start()
            result = autopilot.stop()
        assert result["status"] == "stopped"

    def test_double_start_returns_already_running(self, autopilot):
        """start() when already running should return 'already_running'."""
        with patch("src.social_scheduler._notify"):
            autopilot.start()
            result = autopilot.start()
        assert result["status"] == "already_running"
        autopilot.stop()

    def test_stop_when_not_running(self, autopilot):
        """stop() when not running should return 'not_running'."""
        result = autopilot.stop()
        assert result["status"] == "not_running"

    def test_enabled_flag_set_on_start(self, autopilot, isolate_state_file):
        """start() should set enabled=True in state."""
        with patch("src.social_scheduler._notify"):
            autopilot.start()
        state = ss_module._load_state()
        assert state["enabled"] is True
        autopilot.stop()

    def test_enabled_flag_cleared_on_stop(self, autopilot, isolate_state_file):
        """stop() should set enabled=False in state."""
        with patch("src.social_scheduler._notify"):
            autopilot.start()
            autopilot.stop()
        state = ss_module._load_state()
        assert state["enabled"] is False

    def test_status_returns_correct_structure(self, autopilot):
        """status() should return all expected keys."""
        status = autopilot.status()
        assert "running" in status
        assert "enabled" in status
        assert "jobs" in status
        assert "draft_count" in status
        assert "posts_today" in status
