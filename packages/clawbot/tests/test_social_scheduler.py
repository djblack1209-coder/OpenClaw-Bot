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
    from src.execution.social import x_auto_ops

    x_state_file = tmp_path / "x_auto_ops_state.json"
    monkeypatch.setattr(x_auto_ops, "_STATE_FILE", x_state_file)
    x_auto_ops._save_state(
        {
            "seen": [],
            "drafts": [],
            "scheduled": [],
            "published": [],
            "daily_times": ["08:30"],
            "last_run": "",
        },
        x_state_file,
    )
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

        def fake_run_async(coro):
            """模拟 _run_async：执行状态重置逻辑"""
            coro.close()
            st = ss_module._load_state()
            st["last_scan_topics"] = [{"title": "Test Topic", "score": 8}]
            st["drafts"] = []
            st["today_published"] = []
            st["stats"] = {"posts_today": 0, "engagement_today": 0}
            ss_module._save_state(st)

        with patch("src.social_scheduler._run_async", side_effect=fake_run_async):
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
        assert status["review_mode"] is True
        assert status["external_actions_locked"] is True

# ============ Draft review gate ============

from unittest.mock import patch

from src.api.rpc import ClawBotRPC
import src.social_scheduler as ss_module


def test_social_draft_publish_requires_review_approval(isolate_state_file):
    state = ss_module._load_state()
    state["drafts"] = [
        {
            "id": "draft-review-1",
            "status": "ready",
            "platform": "x",
            "text": "未确认的人设内容不能直接发布",
        }
    ]
    ss_module._save_state(state)

    result = __import__("asyncio").run(ClawBotRPC._rpc_social_draft_publish(0))

    assert result["success"] is False
    assert result["requires_review"] is True
    assert "先确认" in result["error"]


def test_social_draft_approve_then_publish(isolate_state_file):
    state = ss_module._load_state()
    state["drafts"] = [
        {
            "id": "draft-review-2",
            "status": "ready",
            "platform": "x",
            "text": "这条已经确认，可以发布",
        }
    ]
    ss_module._save_state(state)

    approval = ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")

    assert approval["success"] is True
    approved_state = ss_module._load_state()
    assert approved_state["drafts"][0]["review_status"] == "approved"
    assert approved_state["drafts"][0]["approved_by"] == "owner"

    with patch("src.execution.social.worker_bridge.run_social_worker", return_value={"success": True, "url": "https://x.com/demo/status/1"}) as worker:
        blocked = __import__("asyncio").run(ClawBotRPC._rpc_social_draft_publish(0))
        result = __import__("asyncio").run(
            ClawBotRPC._rpc_social_draft_publish(0, final_confirmed=True)
        )

    assert blocked["success"] is False
    assert blocked["requires_human_confirmation"] is True
    assert result["success"] is True
    worker.assert_called_once()
    final_state = ss_module._load_state()
    assert final_state["drafts"][0]["status"] == "published"





def test_job_evening_produce_marks_drafts_as_needs_review(isolate_state_file, monkeypatch):
    """旧 autopilot 生产的 X/小红书草稿应直接进入待确认队列。"""
    state = ss_module._load_state()
    state["last_scan_topics"] = [{"title": "网友把周一早会称为灵魂出厂设置", "score": 9}]
    ss_module._save_state(state)

    async def fake_strategy(**kwargs):
        return {"success": True, "strategy": {"angle": "abstract_roast"}}

    async def fake_compose(**kwargs):
        return {"success": True, "text": f"待确认内容：{kwargs['platform']}"}

    monkeypatch.setattr("src.execution.social.content_strategy.load_persona", lambda name="default": {"name": "demo"})
    monkeypatch.setattr("src.execution.social.content_strategy.derive_content_strategy", fake_strategy)
    monkeypatch.setattr("src.execution.social.content_strategy.compose_post", fake_compose)
    monkeypatch.setattr(ss_module, "_notify", lambda *args, **kwargs: None)

    ss_module.job_evening_produce()

    loaded = ss_module._load_state()
    assert len(loaded["drafts"]) == 2
    assert {draft["platform"] for draft in loaded["drafts"]} == {"x", "xhs"}
    assert all(draft["status"] == "needs_review" for draft in loaded["drafts"])
    assert all(draft["review_status"] == "pending" for draft in loaded["drafts"])
    assert all(draft["review_required_reason"] == "发布前请先确认人设和内容" for draft in loaded["drafts"])

def test_job_noon_engage_skips_external_interactions_in_review_mode(monkeypatch):
    """审核模式下不允许旧 autopilot 自动回复/蹭评，避免账号外部互动失控。"""
    calls: list[tuple[str, dict]] = []

    def fake_worker(action, payload):
        calls.append((action, payload))
        return {"success": True}

    monkeypatch.setattr("src.execution.social.worker_bridge.run_social_worker", fake_worker)
    monkeypatch.setattr(ss_module, "_notify", lambda *args, **kwargs: None)

    ss_module.job_noon_engage()

    assert calls == []

def test_job_night_publish_skips_unreviewed_ready_drafts(isolate_state_file, monkeypatch):
    """旧 autopilot 晚间发布任务也不能绕过内容审核闸口。"""
    state = ss_module._load_state()
    state["drafts"] = [
        {
            "id": "unreviewed-ready",
            "status": "ready",
            "platform": "x",
            "review_status": "pending",
            "text": "这条没有人工确认，晚间任务也不能发布",
        }
    ]
    ss_module._save_state(state)
    calls: list[tuple[str, dict]] = []

    async def fake_worker(action, payload):
        calls.append((action, payload))
        return {"success": True, "url": "https://x.com/demo/status/skip"}

    monkeypatch.setattr("src.execution.social.worker_bridge.run_social_worker_async", fake_worker)
    monkeypatch.setattr(ss_module, "_notify", lambda *args, **kwargs: None)

    ss_module.job_night_publish()

    loaded = ss_module._load_state()
    assert calls == []
    assert loaded["drafts"][0]["status"] == "needs_review"
    assert loaded["drafts"][0]["review_status"] == "pending"
    assert loaded["drafts"][0]["review_required_reason"] == "发布前请先确认人设和内容"
    assert loaded["stats"]["posts_today"] == 0


def test_job_night_publish_does_not_auto_publish_approved_drafts_in_review_mode(isolate_state_file, monkeypatch):
    """审核模式下，已确认内容也必须由桌面端最终发布确认触发。"""
    state = ss_module._load_state()
    state["drafts"] = [
        {
            "id": "approved-but-not-final-confirmed",
            "status": "ready",
            "platform": "x",
            "review_status": "approved",
            "text": "这条内容已确认，但还没点最终发布",
        }
    ]
    ss_module._save_state(state)
    calls: list[tuple[str, dict]] = []

    async def fake_worker(action, payload):
        calls.append((action, payload))
        return {"success": True, "url": "https://x.com/demo/status/approved"}

    monkeypatch.setattr("src.execution.social.worker_bridge.run_social_worker_async", fake_worker)
    monkeypatch.setattr(ss_module, "_notify", lambda *args, **kwargs: None)

    ss_module.job_night_publish()

    loaded = ss_module._load_state()
    assert calls == []
    assert loaded["drafts"][0]["status"] == "ready"
    assert loaded["drafts"][0]["review_status"] == "approved"
    assert loaded["stats"]["posts_today"] == 0

def test_social_drafts_merges_x_auto_review_queue(isolate_state_file, tmp_path, monkeypatch):
    """桌面端草稿审核页必须能看到 X 自动运营草稿。"""
    from src.execution.social import x_auto_ops

    x_state_path = tmp_path / "x_auto_ops_state.json"
    monkeypatch.setattr(x_auto_ops, "_STATE_FILE", x_state_path)
    x_auto_ops._save_state(
        {
            "seen": [],
            "drafts": [
                {
                    "id": "xauto-review-visible",
                    "platform": "x",
                    "status": "ready",
                    "review_status": "pending",
                    "text": "这条 X 热点草稿需要在桌面端确认",
                }
            ],
            "scheduled": [],
            "published": [],
            "daily_times": ["08:30"],
            "last_run": "",
        },
        x_state_path,
    )

    result = ClawBotRPC._rpc_social_drafts()

    assert result["count"] == 1
    assert result["drafts"][0]["_state_source"] == "x_auto_ops"
    assert result["drafts"][0]["text"] == "这条 X 热点草稿需要在桌面端确认"


def test_social_review_can_approve_x_auto_draft(isolate_state_file, tmp_path, monkeypatch):
    """桌面端确认动作必须写回 X 自动运营队列，供定时任务消费。"""
    from src.execution.social import x_auto_ops

    x_state_path = tmp_path / "x_auto_ops_state.json"
    monkeypatch.setattr(x_auto_ops, "_STATE_FILE", x_state_path)
    x_auto_ops._save_state(
        {
            "seen": [],
            "drafts": [
                {
                    "id": "xauto-review-approve",
                    "platform": "x",
                    "status": "needs_review",
                    "review_status": "pending",
                    "text": "确认后才允许发布的 X 草稿",
                }
            ],
            "scheduled": [],
            "published": [],
            "daily_times": ["08:30"],
            "last_run": "",
        },
        x_state_path,
    )

    approval = ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")

    assert approval["success"] is True
    state = x_auto_ops._load_state(x_state_path)
    assert state["drafts"][0]["review_status"] == "approved"
    assert state["drafts"][0]["status"] == "approved"



def test_social_browser_control_allows_safe_workspace_actions(monkeypatch):
    """SaaS 工作台浏览器控制只能执行安全动作，不能绕过审核发帖。"""
    from src.api.rpc import ClawBotRPC

    calls: list[tuple[str, dict]] = []

    def fake_worker(action, payload):
        calls.append((action, payload))
        return {"success": True, "action": action, "payload": payload}

    monkeypatch.setattr("src.execution.social.worker_bridge.run_social_worker", fake_worker)

    result = ClawBotRPC._rpc_social_browser_control("open_x", platform="x")

    assert result["success"] is True
    assert result["action"] == "bootstrap"
    assert result["safe"] is True
    assert calls == [("bootstrap", {"platforms": ["x"]})]


def test_social_browser_control_blocks_publish_like_actions(monkeypatch):
    """浏览器控制入口必须拒绝 publish/reply/delete 等外部变更动作。"""
    from src.api.rpc import ClawBotRPC

    calls: list[tuple[str, dict]] = []

    def fake_worker(action, payload):
        calls.append((action, payload))
        return {"success": True}

    monkeypatch.setattr("src.execution.social.worker_bridge.run_social_worker", fake_worker)

    result = ClawBotRPC._rpc_social_browser_control("publish_x", platform="x")

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["requires_review"] is True
    assert calls == []

def test_social_ops_workspace_aggregates_browser_saas_cards(monkeypatch):
    """统一运营工作台必须聚合 X / 小红书 / 闲鱼，并默认保持审核优先。"""
    monkeypatch.setattr("src.api.rpc._ensure_social_review_drafts", lambda *args, **kwargs: {"success": True})
    monkeypatch.setattr("src.api.rpc._social_review_pack_payload", lambda *args, **kwargs: {"success": True, "samples": []})
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_status",
        staticmethod(lambda: {
            "autopilot_running": False,
            "platforms": [
                {"platform": "x", "connected": True, "posts_today": 1, "total_posts": 8},
                {"platform": "xhs", "connected": False, "posts_today": 0, "total_posts": 2},
            ],
        }),
    )
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_browser_status",
        staticmethod(lambda: {"browser_running": True, "x": "ready", "xhs": "unknown"}),
    )
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_drafts",
        staticmethod(lambda: {
            "drafts": [
                {"id": "x-1", "platform": "x", "status": "ready", "review_status": "pending", "text": "待确认 X"},
                {"id": "x-2", "platform": "x", "status": "approved", "review_status": "approved", "text": "可发布 X"},
                {"id": "xhs-1", "platform": "xhs", "status": "ready", "review_status": "pending", "text": "待确认小红书"},
            ],
            "count": 3,
        }),
    )
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_personas",
        staticmethod(lambda: [{"persona_id": "zhou-yuheng", "display_name": "旧 AI 人设"}]),
    )
    monkeypatch.setattr(ClawBotRPC, "_rpc_autopilot_status", staticmethod(lambda: {"running": False}))
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_xianyu_compact_status",
        staticmethod(lambda: {
            "running": True,
            "online": True,
            "cookie_ok": True,
            "auto_reply_active": True,
            "conversations_today": 4,
            "unread_chats": 1,
        }),
    )
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_xianyu_recent_conversations",
        staticmethod(lambda limit=10: {"conversations": [{"chat_id": "c1"}], "total": 1}),
    )

    workspace = ClawBotRPC._rpc_social_ops_workspace()

    assert workspace["success"] is True
    assert workspace["review_required"] is True
    assert workspace["auto_publish_enabled"] is False
    assert workspace["review_gate"]["needs_review"] == 2
    assert workspace["review_gate"]["ready_to_publish"] == 1
    platforms = {item["id"]: item for item in workspace["platforms"]}
    assert set(platforms) == {"x", "xhs", "xianyu"}
    assert platforms["x"]["ready"] is True
    assert platforms["x"]["needs_review"] == 1
    assert platforms["x"]["ready_to_publish"] == 1
    assert platforms["xhs"]["needs_review"] == 1
    assert platforms["xianyu"]["ready"] is True
    assert platforms["xianyu"]["conversations_today"] == 4
    assert workspace["persona_check"]["needs_confirmation"] is True
    assert len(workspace["persona_check"]["review_samples"]) == 2
    assert workspace["persona_check"]["review_samples"][0]["text"] == "待确认 X"
    assert workspace["persona_check"]["review_samples"][0]["platform"] == "x"
    assert workspace["persona_check"]["sample_count"] == 2
    assert workspace["platforms"][0]["next_step"] == "先确认人设与 1 条内容，再点最终发布"
    assert workspace["platforms"][0]["sample_preview"] == "待确认 X"
    assert workspace["platforms"][2]["next_step"] == "打开闲鱼管理页处理客服会话"
    assert workspace["skill_audit"]["exists"] is True


def test_social_persona_review_confirm_updates_workspace(tmp_path, monkeypatch):
    """确认热点抽象号人设后，工作台应显示人设已确认，但不自动发布草稿。"""
    from src.execution.social import persona_review

    monkeypatch.setattr("src.api.rpc._ensure_social_review_drafts", lambda *args, **kwargs: {"success": True})
    monkeypatch.setattr("src.api.rpc._social_review_pack_payload", lambda *args, **kwargs: {"success": True, "samples": []})
    review_state = tmp_path / "persona_review.json"
    monkeypatch.setattr(persona_review, "_STATE_FILE", review_state)
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_status",
        staticmethod(lambda: {"autopilot_running": False, "platforms": []}),
    )
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_browser_status",
        staticmethod(lambda: {"browser_running": False, "x": "unknown", "xhs": "unknown"}),
    )
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_drafts",
        staticmethod(lambda: {
            "drafts": [
                {"id": "x-needs-review", "platform": "x", "status": "ready", "review_status": "pending", "text": "仍需逐条确认"},
            ],
            "count": 1,
        }),
    )
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_personas", staticmethod(lambda: []))
    monkeypatch.setattr(ClawBotRPC, "_rpc_autopilot_status", staticmethod(lambda: {"running": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_xianyu_compact_status", staticmethod(lambda: {"running": False, "online": False, "cookie_ok": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_xianyu_recent_conversations", staticmethod(lambda limit=10: {"conversations": [], "total": 0}))

    before = ClawBotRPC._rpc_social_persona_review()
    assert before["needs_confirmation"] is True

    reviewed = ClawBotRPC._rpc_social_persona_review_update(True, reviewer="owner", notes="方向确认")
    assert reviewed["approved"] is True
    assert reviewed["needs_confirmation"] is False

    workspace = ClawBotRPC._rpc_social_ops_workspace()
    assert workspace["persona_check"]["approved"] is True
    assert workspace["persona_check"]["needs_confirmation"] is False
    assert workspace["review_required"] is True
    assert workspace["auto_publish_enabled"] is False
    assert workspace["review_gate"]["needs_review"] == 1


def test_social_review_pack_generates_review_samples(monkeypatch, tmp_path):
    """待审核运营包应补齐 X 与小红书样稿，但不打开发布能力。"""
    from src.execution.social import x_auto_ops

    state_path = tmp_path / "x_auto_ops_state.json"
    monkeypatch.setattr(x_auto_ops, "_STATE_FILE", state_path)
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda: [
            x_auto_ops.TrendSeed(
                title="多名艺人痛失艺名",
                channel="百度热榜",
                url="https://example.com/stage-name",
                source="baidu",
                language="zh",
                raw_score=900000,
                raw_rank=2,
                tags=["热点"],
            ),
            x_auto_ops.TrendSeed(
                title="Show HN: Got sick of ads, so I made my own logic puzzle site",
                channel="Hacker News",
                url="https://example.com/puzzle",
                source="hacker_news",
                language="en",
                raw_score=500,
                raw_rank=4,
                tags=["Internet"],
            ),
            x_auto_ops.TrendSeed(
                title="UP主一己之力下架导航广告",
                channel="B站热榜",
                url="https://example.com/up",
                source="bilibili_trending",
                language="zh",
                raw_score=100,
                raw_rank=8,
                tags=["Bilibili"],
            ),
        ],
    )

    pack = ClawBotRPC._rpc_social_review_pack(limit=8)

    assert pack["success"] is True
    assert pack["auto_publish_enabled"] is False
    assert pack["requires_owner_confirmation"] is True
    assert pack["sample_count"] >= 2
    platforms = {sample["platform"] for sample in pack["samples"]}
    assert {"x", "xhs"} <= platforms
    assert "确认前不会发布" in pack["content_verdict"]


def test_social_review_pack_hides_unsafe_legacy_samples(monkeypatch):
    """审核包不应展示旧 AI/体育/政治/报错样稿，避免污染用户确认。"""
    monkeypatch.setattr("src.api.rpc._ensure_social_review_drafts", lambda *args, **kwargs: {"success": True})
    monkeypatch.setattr(
        "src.api.rpc._merged_social_draft_refs",
        lambda: [
            {
                "source": "social_autopilot",
                "index": 0,
                "draft": {
                    "id": "bad-politics",
                    "platform": "xhs",
                    "status": "needs_review",
                    "review_status": "pending",
                    "title": "治国之要 首在用人",
                    "text": "❌ 严总，这个请求没处理成功，我再试试。",
                },
            },
            {
                "source": "social_autopilot",
                "index": 1,
                "draft": {
                    "id": "bad-sports",
                    "platform": "x",
                    "status": "ready",
                    "review_status": "pending",
                    "title": "姆巴佩世界波",
                    "text": "姆巴佩世界波太强了",
                },
            },
            {
                "source": "x_auto_ops",
                "index": 2,
                "draft": {
                    "id": "good-abstract",
                    "platform": "x",
                    "status": "ready",
                    "review_status": "pending",
                    "title": "UP主一己之力下架导航广告",
                    "text": "UP主一己之力下架导航广告\n\n第一眼：这啥。\n第二眼：好像也合理。",
                },
            },
        ],
    )

    pack = ClawBotRPC._rpc_social_review_pack(limit=8)
    texts = " ".join(sample["text"] for sample in pack["samples"])

    assert pack["sample_count"] == 1
    assert "UP主" in texts
    assert "严总" not in texts
    assert "姆巴佩" not in texts


def test_social_ops_workspace_exposes_extension_schedule_queue(monkeypatch):
    """统一运营工作台要能看到插件排程队列，但排程仍不能自动发布。"""
    monkeypatch.setattr("src.api.rpc._ensure_social_review_drafts", lambda *args, **kwargs: {"success": True})
    monkeypatch.setattr("src.api.rpc._social_review_pack_payload", lambda *args, **kwargs: {"success": True, "samples": []})
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_status", staticmethod(lambda: {"autopilot_running": False, "platforms": []}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_browser_status", staticmethod(lambda: {"browser_running": False, "x": "unknown", "xhs": "unknown"}))
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_drafts",
        staticmethod(lambda: {
            "drafts": [
                {
                    "id": "ext-x-scheduled",
                    "platform": "x",
                    "status": "scheduled",
                    "review_status": "approved",
                    "text": "已排程但仍需最终确认",
                },
            ],
            "count": 1,
        }),
    )
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_personas", staticmethod(lambda: []))
    monkeypatch.setattr(ClawBotRPC, "_rpc_autopilot_status", staticmethod(lambda: {"running": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_xianyu_compact_status", staticmethod(lambda: {"running": False, "online": False, "cookie_ok": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_xianyu_recent_conversations", staticmethod(lambda limit=10: {"conversations": [], "total": 0}))
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_extension_schedule_queue",
        staticmethod(lambda: {
            "success": True,
            "count": 1,
            "queue": [
                {
                    "draft_id": "ext-x-scheduled",
                    "platform": "x",
                    "scheduled_at": "2026-06-24T08:30:00-06:00",
                    "status": "queued_for_owner_publish",
                    "external_actions_locked": True,
                }
            ],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }),
    )

    workspace = ClawBotRPC._rpc_social_ops_workspace()

    assert workspace["extension_schedule"]["count"] == 1
    assert workspace["extension_schedule"]["auto_publish_enabled"] is False
    assert workspace["extension_schedule"]["external_actions_locked"] is True
    assert workspace["review_gate"]["scheduled"] == 1
    assert workspace["platforms"][0]["scheduled"] == 1
