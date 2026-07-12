from pathlib import Path

import pytest

from src.api.rpc import ClawBotRPC


@pytest.fixture(autouse=True)
def isolate_social_review_state(tmp_path, monkeypatch):
    """隔离社媒草稿状态，避免本机真实草稿污染单元测试。"""
    monkeypatch.setattr("src.social_scheduler._STATE_FILE", tmp_path / "social_autopilot_state.json")
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", tmp_path / "x_auto_ops_state.json")


def test_social_extension_status_defaults_to_safe_offline(tmp_path, monkeypatch):
    state_file = tmp_path / "social_extension_status.json"
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", state_file)

    payload = ClawBotRPC._rpc_social_extension_status()

    assert payload["success"] is True
    assert payload["online"] is False
    assert payload["running"] is False
    assert payload["auto_publish_enabled"] is False
    assert payload["external_actions_locked"] is True
    assert payload["platform"] == "unsupported"


def test_social_extension_status_update_persists_safe_fields(tmp_path, monkeypatch):
    state_file = tmp_path / "social_extension_status.json"
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", state_file)

    result = ClawBotRPC._rpc_social_extension_status_update(
        {
            "platform": "xhs",
            "url": "https://www.xiaohongshu.com/explore",
            "running": True,
            "detected_platform": {"id": "xhs", "label": "小红书"},
            "settings": {
                "personaTags": ["生活", "女性向"],
                "automationLevel": "autofill",
                "interactionLevel": "own_comments",
            },
            "unsafe": {"token": "secret"},
        }
    )

    assert result["success"] is True
    loaded = ClawBotRPC._rpc_social_extension_status()
    assert loaded["online"] is True
    assert loaded["running"] is True
    assert loaded["platform"] == "xhs"
    assert loaded["detected_platform"]["label"] == "小红书"
    assert loaded["settings"]["personaTags"] == ["生活", "女性向"]
    assert loaded["auto_publish_enabled"] is False
    assert loaded["external_actions_locked"] is True
    assert "unsafe" not in loaded
    assert state_file.exists()


def test_social_extension_status_update_persists_cc_delivery_capabilities(tmp_path, monkeypatch):
    state_file = tmp_path / "social_extension_status.json"
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", state_file)

    result = ClawBotRPC._rpc_social_extension_status_update(
        {
            "platform": "xianyu",
            "url": "https://www.goofish.com/",
            "extension": {
                "manifest_version": "0.2.1",
                "cc_delivery_helper_version": "2026-07-06-global-watch",
                "capabilities": {
                    "xianyu_delivery_scan": True,
                    "xianyu_delivery_send": False,
                    "xianyu_one_shot_delivery_human_gated": True,
                    "current_chat_watch": True,
                    "all_open_xianyu_tabs_watch": True,
                    "target_tab_preflight": True,
                    "single_pending_global_gate": True,
                    "unsafe_extra": "drop-me",
                },
                "token": "must-not-persist",
            },
        }
    )

    assert result["success"] is True
    loaded = ClawBotRPC._rpc_social_extension_status()
    extension = loaded["extension"]
    assert extension["manifest_version"] == "0.2.1"
    assert extension["cc_delivery_helper_version"] == "2026-07-06-global-watch"
    assert extension["capabilities"]["all_open_xianyu_tabs_watch"] is True
    assert extension["capabilities"]["target_tab_preflight"] is True
    assert extension["capabilities"]["xianyu_delivery_send"] is False
    assert extension["capabilities"]["xianyu_one_shot_delivery_human_gated"] is True
    assert extension["capabilities"]["background_heartbeat"] is False
    assert "unsafe_extra" not in extension["capabilities"]
    assert "token" not in extension


def test_social_extension_status_preserves_known_cc_capabilities_when_old_payload_arrives(tmp_path, monkeypatch):
    """旧插件动作不带 extension 字段时，不应冲掉已知的新版发货能力。"""
    state_file = tmp_path / "social_extension_status.json"
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", state_file)

    ClawBotRPC._rpc_social_extension_status_update(
        {
            "platform": "xianyu",
            "extension": {
                "manifest_version": "0.2.1",
                "cc_delivery_helper_version": "2026-07-07-background-heartbeat",
                "capabilities": {
                    "all_open_xianyu_tabs_watch": True,
                    "target_tab_preflight": True,
                    "single_pending_global_gate": True,
                    "background_heartbeat": True,
                    "xianyu_confirm_shipment": False,
                    "xianyu_relist_item": False,
                    "xianyu_one_shot_delivery_human_gated": True,
                    "relist_queue_watch": False,
                    "paid_page_dispatch": True,
                },
            },
        }
    )
    ClawBotRPC._rpc_social_extension_status_update(
        {
            "platform": "x",
            "running": True,
            "settings": {"personaTags": ["热点"]},
        }
    )

    loaded = ClawBotRPC._rpc_social_extension_status()
    extension = loaded["extension"]
    assert extension["cc_delivery_helper_version"] == "2026-07-07-background-heartbeat"
    assert extension["capabilities"]["all_open_xianyu_tabs_watch"] is True
    assert extension["capabilities"]["background_heartbeat"] is True
    assert extension["capabilities"]["relist_queue_watch"] is False
    assert extension["capabilities"]["xianyu_one_shot_delivery_human_gated"] is True
    assert extension["capabilities"]["paid_page_dispatch"] is True


def test_social_extension_status_update_clamps_invalid_platform(tmp_path, monkeypatch):
    state_file = tmp_path / "social_extension_status.json"
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", state_file)

    result = ClawBotRPC._rpc_social_extension_status_update({"platform": "evil", "running": True})

    assert result["success"] is True
    assert result["platform"] == "unsupported"
    assert result["running"] is True
    assert result["auto_publish_enabled"] is False


def test_social_extension_page_probe_update_persists_calibration_summary(tmp_path, monkeypatch):
    state_file = tmp_path / "social_extension_status.json"
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", state_file)

    result = ClawBotRPC._rpc_social_extension_page_probe_update(
        {
            "platform": "xhs",
            "url": "https://creator.xiaohongshu.com/publish/publish",
            "ready": True,
            "availableFields": [
                {"name": "title", "kind": "title", "tag": "input", "selector": "secret should be dropped"},
                {"name": "body", "kind": "body", "tag": "textarea"},
            ],
            "auto_publish_enabled": True,
            "external_actions_locked": False,
        }
    )

    assert result["success"] is True
    assert result["platform"] == "xhs"
    assert result["ready"] is True
    assert result["field_names"] == ["title", "body"]
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True

    status = ClawBotRPC._rpc_social_extension_status()
    calibration = status["page_calibration"]
    assert calibration["xhs"]["ready"] is True
    assert calibration["xhs"]["available_fields"] == [
        {"name": "title", "kind": "title", "tag": "input"},
        {"name": "body", "kind": "body", "tag": "textarea"},
    ]
    assert "selector" not in calibration["xhs"]["available_fields"][0]
    assert calibration["xhs"]["auto_publish_enabled"] is False
    assert calibration["xhs"]["external_actions_locked"] is True


def test_social_extension_page_probe_update_records_missing_input_reason(tmp_path, monkeypatch):
    state_file = tmp_path / "social_extension_status.json"
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", state_file)

    result = ClawBotRPC._rpc_social_extension_page_probe_update(
        {
            "platform": "x",
            "url": "https://x.com/home",
            "ready": False,
            "availableFields": [],
            "reason": "no_supported_input_found",
        }
    )

    assert result["success"] is True
    assert result["ready"] is False
    assert result["reason"] == "no_supported_input_found"
    status = ClawBotRPC._rpc_social_extension_status()
    assert status["page_calibration"]["x"]["ready"] is False
    assert status["page_calibration"]["x"]["reason"] == "no_supported_input_found"


def test_social_extension_draft_create_builds_pending_review_draft(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    result = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "xhs",
            "url": "https://www.xiaohongshu.com/search_result?keyword=夏日冷饮",
            "page_context": {
                "title": "夏日冷饮搜索结果",
                "selection": "家人们，一定要学的夏日冷饮制作方法",
                "trends": ["低卡柠檬茶", "冰饮教程"],
            },
            "settings": {
                "personaTags": ["生活", "女性向"],
                "automationLevel": "autofill",
                "interactionLevel": "own_comments",
            },
        }
    )

    assert result["success"] is True
    assert result["requires_owner_review"] is True
    assert result["auto_publish_enabled"] is False
    assert result["draft"]["platform"] == "xhs"
    assert result["draft"]["status"] == "needs_review"
    assert result["draft"]["review_status"] == "pending"
    assert "夏日冷饮" in result["draft"].get("title", "") or "夏日冷饮" in result["draft"].get("text", "")
    assert result["draft"]["seed"]["source"] == "chrome_extension"
    assert state_file.exists()

    listed = ClawBotRPC._rpc_social_drafts()
    assert listed["count"] == 1
    assert listed["drafts"][0]["review_status"] == "pending"


def test_social_extension_draft_create_includes_platform_content_and_image_plan(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    result = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "xhs",
            "url": "https://www.xiaohongshu.com/search_result?keyword=夏日冷饮",
            "page_context": {
                "title": "夏日冷饮搜索结果",
                "selection": "家人们，一定要学的夏日冷饮制作方法",
                "trends": ["低卡柠檬茶", "冰饮教程"],
            },
            "settings": {
                "personaTags": ["生活", "女性向"],
                "contentModel": "web-gemini",
                "imageModel": "gpt-image",
                "automationLevel": "autofill",
                "interactionLevel": "own_comments",
            },
        }
    )

    draft = result["draft"]
    assert result["success"] is True
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True
    assert draft["content_plan"]["format"] == "xhs_note"
    assert "收藏" in " ".join(draft["content_plan"]["structure"])
    assert draft["platform_style"] == "小红书女性向生活攻略图文"
    assert draft["image_plan"]["auto_generate"] is False
    assert draft["image_plan"]["image_model"] == "gpt-image"
    assert "夏日冷饮" in draft["image_plan"]["cover_prompt"]
    assert len(draft["image_plan"]["asset_prompts"]) >= 2
    assert "不自动发布" in " ".join(draft["safety_checklist"])
    assert "发布前人工确认" in " ".join(draft["format_checklist"])
    assert draft["cost_route"]["content_model"] == "web-gemini"
    assert draft["cost_route"]["image_model"] == "gpt-image"


def test_social_extension_asset_plan_is_platform_specific_for_x_and_xianyu(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    x_result = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "x",
            "url": "https://x.com/explore",
            "page_context": {
                "title": "GitHub 一周异常 Star 工具榜",
                "selection": "这些项目一周涨粉异常，适合做成可执行工具清单",
                "trends": ["GitHub", "AI工具", "创业者"],
            },
            "settings": {"personaTags": ["科技", "出海", "AI赚钱"], "contentModel": "web-grok"},
        }
    )
    x_draft = x_result["draft"]
    assert x_draft["content_plan"]["format"] == "x_hotspot_short_post"
    assert x_draft["platform_style"] == "X 年轻创业者热点实操短帖"
    assert "3步" in " ".join(x_draft["content_plan"]["structure"])
    assert x_draft["image_plan"]["auto_generate"] is False
    assert "可选" in x_draft["image_plan"]["cover_prompt"]
    assert "投资建议" in " ".join(x_draft["safety_checklist"])

    xianyu_result = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "xianyu",
            "url": "https://www.goofish.com/item?id=1",
            "page_context": {
                "title": "学生党二手相机咨询",
                "selection": "买家问能不能便宜一点，今天能发吗",
                "trends": ["二手数码", "学生党"],
            },
            "settings": {"personaTags": ["二手交易"], "imageModel": "none"},
        }
    )
    xianyu_draft = xianyu_result["draft"]
    assert xianyu_draft["content_plan"]["format"] == "xianyu_reply_or_listing"
    assert xianyu_draft["platform_style"] == "闲鱼成交话术与商品优化"
    assert xianyu_draft["image_plan"]["auto_generate"] is False
    assert xianyu_draft["image_plan"]["image_model"] == "none"
    assert "不要虚构成色" in " ".join(xianyu_draft["safety_checklist"])


def test_social_extension_draft_update_and_review_by_id(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    created = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "x",
            "url": "https://x.com/explore",
            "page_context": {"title": "AI stocks and rate cut", "trends": ["AI stocks", "rate cut"]},
            "settings": {"personaTags": ["金融", "出海"], "automationLevel": "draft_only"},
        }
    )
    draft_id = created["draft"]["id"]

    updated = ClawBotRPC._rpc_social_extension_draft_update(
        draft_id,
        text="改成更像年轻创业者会收藏的实操说明书。",
        title="美股回调别慌",
    )
    assert updated["success"] is True
    assert updated["draft"]["text"] == "改成更像年轻创业者会收藏的实操说明书。"
    assert updated["draft"]["title"] == "美股回调别慌"
    assert updated["draft"]["review_status"] == "pending"

    reviewed = ClawBotRPC._rpc_social_extension_draft_review(draft_id, approved=True, reviewer="owner")
    assert reviewed["success"] is True
    assert reviewed["draft"]["review_status"] == "approved"
    assert reviewed["draft"]["status"] == "approved"
    assert reviewed["auto_publish_enabled"] is False
    assert reviewed["external_actions_locked"] is True


def test_social_extension_trends_returns_safe_hotspot_pool(monkeypatch):
    from src.execution.social.x_auto_ops import TrendSeed

    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda include_video_fallback=False: [
            TrendSeed(
                title="GitHub 一周异常 Star 工具榜",
                channel="GitHub/HN",
                url="https://example.com/github-stars",
                source="hacker_news",
                language="zh",
                raw_score=980,
                raw_rank=1,
                tags=["GitHub", "AI工具"],
                heat_reason="年轻创业者可直接收藏和复用",
            ),
            TrendSeed(
                title="夏日低卡冷饮突然又火了",
                channel="小红书灵感",
                url="https://example.com/drink",
                source="xhs_trend",
                language="zh",
                raw_score=880,
                raw_rank=2,
                tags=["生活", "冷饮"],
                heat_reason="适合女性向图文教程",
            ),
        ],
    )

    result = ClawBotRPC._rpc_social_extension_trends(platform="x", limit=2)

    assert result["success"] is True
    assert result["platform"] == "x"
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True
    assert result["count"] == 2
    assert result["trends"][0]["title"] == "GitHub 一周异常 Star 工具榜"
    assert result["trends"][0]["draft_platform"] == "x"
    assert result["trends"][0]["call_to_action"]
    assert result["trends"][0]["audience"] == "大学生 / 年轻创业者 / 出海与 AI 工具人群"
    assert "可执行" in result["trends"][0]["content_angle"]
    assert result["trends"][0]["platform_playbook"]
    assert result["trends"][0]["growth_reason"]
    assert result["trends"][0]["risk_level"] in {"low", "medium", "high"}
    assert result["trends"][0]["risk_note"]
    assert len(result["trends"][0]["execution_steps"]) >= 3
    assert result["trends"][0]["safe_for_autopublish"] is False



def test_social_extension_trends_use_growth_feedback_to_reweight_candidates(tmp_path, monkeypatch):
    from src.execution.social.x_auto_ops import TrendSeed

    state_file = tmp_path / "x_auto_state.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda include_video_fallback=False: [
            TrendSeed(
                title="普通 AI 新闻更新",
                channel="Google News",
                url="https://example.com/ai-news",
                source="google_news",
                language="zh",
                raw_score=1200,
                raw_rank=1,
                tags=["AI新闻"],
                heat_reason="热度较高但偏泛资讯",
            ),
            TrendSeed(
                title="GitHub 一周异常 Star 工具榜",
                channel="GitHub/HN",
                url="https://example.com/github-stars",
                source="hacker_news",
                language="zh",
                raw_score=700,
                raw_rank=2,
                tags=["GitHub", "AI工具"],
                heat_reason="年轻创业者可直接收藏和复用",
            ),
        ],
    )

    ClawBotRPC._rpc_social_extension_performance_record(
        {
            "platform": "x",
            "draft_id": "ext-x-high-signal",
            "performance": {
                "title": "GitHub 一周异常 Star 工具榜",
                "tags": ["GitHub", "AI工具"],
                "metrics": {"likes": 188, "comments": 18, "shares": 9, "impressions": 18000},
                "outcome": "high_signal",
                "learning": "继续放大 GitHub 工具榜 + 部署步骤。",
            },
        }
    )

    result = ClawBotRPC._rpc_social_extension_trends(platform="x", limit=2)

    assert result["success"] is True
    assert result["trends"][0]["title"] == "GitHub 一周异常 Star 工具榜"
    assert result["trends"][0]["growth_feedback_boost"] > 0
    assert "历史高信号" in result["trends"][0]["growth_feedback_reason"]
    assert result["growth_feedback_applied"] is True
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True


def test_social_extension_draft_from_trend_pool_stays_pending_review(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    result = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "x",
            "url": "https://example.com/github-stars",
            "source": "chrome_extension_trend_pool",
            "page_context": {
                "title": "GitHub 一周异常 Star 工具榜",
                "selection": "这些项目一周涨粉异常，适合做成可执行工具清单",
                "trends": ["GitHub", "AI工具", "创业者"],
                "bodyText": "来自本地/云端热点池，而不是当前页面正文。",
            },
            "settings": {"personaTags": ["科技", "出海", "AI赚钱"], "automationLevel": "draft_only"},
        }
    )

    assert result["success"] is True
    assert result["draft"]["status"] == "needs_review"
    assert result["draft"]["review_status"] == "pending"
    assert result["draft"]["seed"]["source"] == "chrome_extension_trend_pool"
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True




def test_social_extension_draft_from_interaction_scan_stays_pending_review(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    result = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "x",
            "url": "https://x.com/example/status/1",
            "source": "chrome_extension_interaction_scan",
            "page_context": {
                "title": "互动回复：这些 AI 工具怎么部署到自己的业务里？",
                "selection": "这些 AI 工具怎么部署到自己的业务里？",
                "bodyText": "作者 young_builder · 18 likes · 来自当前页互动扫描",
                "trends": ["互动回复", "评论区", "轻互动"],
            },
            "settings": {"personaTags": ["出海", "AI赚钱"], "interactionLevel": "light"},
        }
    )

    assert result["success"] is True
    assert result["requires_owner_review"] is True
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True
    assert result["draft"]["review_status"] == "pending"
    assert result["draft"]["seed"]["source"] == "chrome_extension_interaction_scan"
    assert "互动" in result["draft"]["title"] or "互动" in result["draft"]["text"]

def test_social_extension_draft_schedule_requires_approved_review(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    created = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "x",
            "url": "https://x.com/explore",
            "page_context": {"title": "GitHub 一周异常 Star 工具榜"},
            "settings": {"personaTags": ["科技", "出海"], "automationLevel": "draft_only"},
        }
    )

    scheduled = ClawBotRPC._rpc_social_extension_draft_schedule(
        created["draft"]["id"],
        scheduled_at="2026-06-24T08:30:00-06:00",
        reviewer="owner",
    )

    assert scheduled["success"] is False
    assert scheduled["requires_review"] is True
    assert scheduled["auto_publish_enabled"] is False
    assert scheduled["external_actions_locked"] is True


def test_social_extension_draft_schedule_queues_approved_without_external_action(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    created = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "xhs",
            "url": "https://www.xiaohongshu.com/explore",
            "page_context": {"title": "3分钟做出一杯夏日冰饮"},
            "settings": {"personaTags": ["生活", "女性向"], "automationLevel": "reviewed_publish"},
        }
    )
    draft_id = created["draft"]["id"]
    ClawBotRPC._rpc_social_extension_draft_review(draft_id, approved=True, reviewer="owner")

    scheduled = ClawBotRPC._rpc_social_extension_draft_schedule(
        draft_id,
        scheduled_at="2026-06-24T09:15:00-06:00",
        reviewer="owner",
    )

    assert scheduled["success"] is True
    assert scheduled["auto_publish_enabled"] is False
    assert scheduled["external_actions_locked"] is True
    assert scheduled["schedule_item"]["draft_id"] == draft_id
    assert scheduled["schedule_item"]["status"] == "queued_for_owner_publish"
    assert scheduled["schedule_item"]["scheduled_at"] == "2026-06-24T09:15:00-06:00"
    assert scheduled["draft"]["status"] == "scheduled"
    assert scheduled["draft"]["review_status"] == "approved"

    state = __import__("src.execution.social.x_auto_ops", fromlist=["_load_state"]). _load_state(state_file)
    assert len(state.get("extension_schedule", [])) == 1
    assert state["extension_schedule"][0]["external_actions_locked"] is True


def test_social_extension_schedule_queue_marks_due_items_for_final_confirmation(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    from src.execution.social import x_auto_ops

    x_auto_ops._save_state(
        {
            "drafts": [
                {
                    "id": "ext-x-due",
                    "platform": "x",
                    "status": "scheduled",
                    "review_status": "approved",
                    "text": "到点后也不能自动发，只能提醒最终确认。",
                }
            ],
            "extension_schedule": [
                {
                    "id": "schedule-ext-x-due",
                    "draft_id": "ext-x-due",
                    "platform": "x",
                    "title": "到点提醒",
                    "scheduled_at": "2000-01-01T08:30:00-06:00",
                    "status": "queued_for_owner_publish",
                    "review_status": "approved",
                    "external_actions_locked": True,
                    "auto_publish_enabled": False,
                }
            ],
        },
        state_file,
    )

    queue = ClawBotRPC._rpc_social_extension_schedule_queue()

    assert queue["count"] == 1
    assert queue["due_count"] == 1
    assert queue["queue"][0]["due"] is True
    assert queue["queue"][0]["status"] == "awaiting_final_confirmation"
    assert queue["queue"][0]["requires_final_confirmation"] is True
    assert queue["auto_publish_enabled"] is False
    assert queue["external_actions_locked"] is True

    state = x_auto_ops._load_state(state_file)
    assert state["extension_schedule"][0]["status"] == "awaiting_final_confirmation"
    assert state["drafts"][0]["status"] == "awaiting_final_confirmation"


def test_social_extension_schedule_queue_returns_draft_preview_for_popup(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    from src.execution.social import x_auto_ops

    x_auto_ops._save_state(
        {
            "drafts": [
                {
                    "id": "ext-x-popup",
                    "platform": "x",
                    "title": "GitHub 异常 Star",
                    "text": "今天适合收藏，不适合上头。",
                    "status": "scheduled",
                    "review_status": "approved",
                    "schedule_status": "queued_for_owner_publish",
                    "platform_style": "X 年轻创业者热点实操短帖",
                    "content_plan": {"format": "x_hotspot_short_post", "structure": ["反差 hook", "3步 可执行动作"]},
                    "image_plan": {"auto_generate": False, "image_model": "gpt-image", "cover_prompt": "可选信息图封面"},
                    "safety_checklist": ["不自动发布", "不构成投资建议"],
                }
            ],
            "extension_schedule": [
                {
                    "id": "schedule-ext-x-popup",
                    "draft_id": "ext-x-popup",
                    "platform": "x",
                    "title": "GitHub 异常 Star",
                    "scheduled_at": "2099-01-01T08:30:00-06:00",
                    "status": "queued_for_owner_publish",
                    "review_status": "approved",
                    "external_actions_locked": True,
                    "auto_publish_enabled": False,
                }
            ],
        },
        state_file,
    )

    queue = ClawBotRPC._rpc_social_extension_schedule_queue(limit=12)

    assert queue["success"] is True
    assert queue["queue"][0]["draft"] == {
        "id": "ext-x-popup",
        "platform": "x",
        "title": "GitHub 异常 Star",
        "text": "今天适合收藏，不适合上头。",
            "review_status": "approved",
            "status": "scheduled",
            "schedule_status": "queued_for_owner_publish",
            "platform_style": "X 年轻创业者热点实操短帖",
            "content_plan": {"format": "x_hotspot_short_post", "structure": ["反差 hook", "3步 可执行动作"]},
            "image_plan": {"auto_generate": False, "image_model": "gpt-image", "cover_prompt": "可选信息图封面"},
            "safety_checklist": ["不自动发布", "不构成投资建议"],
        }
    assert queue["queue"][0]["auto_publish_enabled"] is False
    assert queue["queue"][0]["external_actions_locked"] is True


def test_social_extension_final_confirm_requires_due_schedule_and_keeps_external_lock(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    from src.execution.social import x_auto_ops

    x_auto_ops._save_state(
        {
            "drafts": [
                {
                    "id": "ext-x-final",
                    "platform": "x",
                    "status": "awaiting_final_confirmation",
                    "review_status": "approved",
                    "text": "最终确认也只是进入可手动发布，不自动发。",
                }
            ],
            "extension_schedule": [
                {
                    "id": "schedule-ext-x-final",
                    "draft_id": "ext-x-final",
                    "platform": "x",
                    "title": "最终确认",
                    "scheduled_at": "2000-01-01T08:30:00-06:00",
                    "status": "awaiting_final_confirmation",
                    "review_status": "approved",
                    "external_actions_locked": True,
                    "auto_publish_enabled": False,
                }
            ],
        },
        state_file,
    )

    result = ClawBotRPC._rpc_social_extension_schedule_final_confirm(
        "ext-x-final",
        reviewer="owner",
    )

    assert result["success"] is True
    assert result["manual_publish_ready"] is True
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True
    assert result["schedule_item"]["status"] == "ready_for_manual_publish"
    assert result["draft"]["status"] == "ready_for_manual_publish"



def test_social_extension_growth_feedback_summary_returns_actionable_recap(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    ClawBotRPC._rpc_social_extension_performance_record(
        {
            "platform": "x",
            "draft_id": "ext-x-github",
            "performance": {
                "title": "GitHub 一周异常 Star 工具榜",
                "tags": ["GitHub", "AI工具"],
                "metrics": {"likes": 188, "comments": 18, "shares": 9, "impressions": 18000},
                "outcome": "high_signal",
                "learning": "继续放大 GitHub 工具榜 + 部署步骤。",
            },
        }
    )
    ClawBotRPC._rpc_social_extension_performance_record(
        {
            "platform": "x",
            "draft_id": "ext-x-baseline",
            "performance": {
                "title": "普通 AI 新闻更新",
                "tags": ["AI新闻"],
                "metrics": {"likes": 3, "comments": 0, "shares": 0, "impressions": 400},
                "outcome": "baseline",
            },
        }
    )

    result = ClawBotRPC._rpc_social_extension_growth_feedback(platform="x", limit=3)

    assert result["success"] is True
    assert result["platform"] == "x"
    assert result["high_signal_count"] == 1
    assert result["signals"][0]["title"] == "GitHub 一周异常 Star 工具榜"
    assert result["signals"][0]["metrics"]["likes"] == 188
    assert "继续放大" in result["signals"][0]["learning"]
    assert result["recommendations"]
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True


def test_social_ops_workspace_exposes_growth_feedback_for_app_control(tmp_path, monkeypatch):
    """App 中控工作台应直接拿到插件增长复盘摘要，且保持只读安全锁。"""
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    ClawBotRPC._rpc_social_extension_performance_record(
        {
            "platform": "x",
            "draft_id": "ext-x-toolkit",
            "performance": {
                "title": "Claude/Codex Skills 实操清单",
                "tags": ["Skills", "Codex"],
                "metrics": {"likes": 166, "comments": 21, "shares": 12, "impressions": 21000},
                "outcome": "high_signal",
                "learning": "把热门工具榜拆成 3 步实操，会比纯新闻更容易涨粉。",
            },
        }
    )

    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_status",
        staticmethod(lambda: {"platforms": [], "autopilot_running": False}),
    )
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_browser_status",
        staticmethod(lambda: {"browser_running": False, "x": "unknown", "xhs": "unknown"}),
    )
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_social_drafts",
        staticmethod(lambda: {"drafts": [], "count": 0}),
    )
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_personas", staticmethod(lambda: []))
    monkeypatch.setattr(ClawBotRPC, "_rpc_autopilot_status", staticmethod(lambda: {"running": False}))
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_xianyu_compact_status",
        staticmethod(lambda: {"running": False, "online": False, "cookie_ok": False}),
    )
    monkeypatch.setattr(
        ClawBotRPC,
        "_rpc_xianyu_recent_conversations",
        staticmethod(lambda limit=10: {"conversations": [], "total": 0}),
    )

    workspace = ClawBotRPC._rpc_social_ops_workspace()

    assert workspace["success"] is True
    assert workspace["auto_publish_enabled"] is False
    assert workspace["growth_feedback"]["platform"] == "x"
    assert workspace["growth_feedback"]["signals"][0]["title"] == "Claude/Codex Skills 实操清单"
    assert "实操" in workspace["growth_feedback"]["signals"][0]["learning"]
    assert workspace["growth_feedback"]["external_actions_locked"] is True
    assert workspace["review_gate"]["growth_feedback_applied"] is True



def test_format_social_growth_feedback_message_is_safe_and_actionable():
    """Telegram 中控需要可读复盘摘要，但不能暗示自动发布/刷量。"""
    from src.bot.cmd_social_mixin import _format_social_growth_feedback_message

    text = _format_social_growth_feedback_message({
        "platform": "x",
        "high_signal_count": 1,
        "signals": [
            {
                "title": "Claude/Codex Skills 实操清单",
                "tags": ["Skills", "Codex"],
                "metrics": {"likes": 166, "comments": 21, "shares": 12, "impressions": 21000},
                "learning": "把热门工具榜拆成 3 步实操，会比纯新闻更容易涨粉。",
                "growth_feedback_reason": "历史高信号：工具榜 + 实操步骤",
            }
        ],
        "recommendations": ["下一轮优先抓 Skills/Codex 相似热点。"],
        "auto_publish_enabled": False,
        "external_actions_locked": True,
    })

    assert "社媒增长复盘" in text
    assert "Claude/Codex Skills 实操清单" in text
    assert "166赞" in text
    assert "下一轮优先抓" in text
    assert "不自动发布" in text
    assert "刷量" not in text


def test_chinese_nlp_routes_social_growth_feedback():
    """Telegram 自然语言应能进入社媒增长复盘中控命令。"""
    from src.bot.chinese_nlp_mixin import _match_chinese_command

    assert _match_chinese_command("社媒增长复盘") == ("social_growth_feedback", "")
    assert _match_chinese_command("看看X运营复盘") == ("social_growth_feedback", "x")

def test_social_extension_growth_feedback_route_accepts_query(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.server import APIServer

    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "")
    monkeypatch.setattr("src.api.auth._warned_no_token", False)
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_growth(platform="x", limit=6):
        captured["platform"] = platform
        captured["limit"] = limit
        return {
            "success": True,
            "platform": platform,
            "signals": [{"title": "GitHub 一周异常 Star 工具榜"}],
            "recommendations": ["继续做工具榜"],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }

    monkeypatch.setattr("src.api.routers.social.ClawBotRPC._rpc_social_extension_growth_feedback", _fake_growth)
    response = client.get("/api/v1/social/extension/growth-feedback?platform=x&limit=4")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["signals"][0]["title"] == "GitHub 一周异常 Star 工具榜"
    assert captured == {"platform": "x", "limit": 4}


def test_social_extension_performance_snapshot_updates_draft_and_status(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    created = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "x",
            "url": "https://x.com/explore",
            "page_context": {"title": "GitHub 一周异常 Star 工具榜"},
            "settings": {"personaTags": ["科技", "出海"], "automationLevel": "draft_only"},
        }
    )
    draft_id = created["draft"]["id"]

    result = ClawBotRPC._rpc_social_extension_performance_record(
        {
            "platform": "x",
            "draft_id": draft_id,
            "source": "chrome_extension_performance_snapshot",
            "performance": {
                "url": "https://x.com/example/status/1",
                "metrics": {"likes": 128, "comments": 12, "shares": 7, "impressions": 12000},
                "outcome": "high_signal",
                "learning": "继续放大 GitHub 工具榜 + 部署步骤。",
            },
            "auto_publish_enabled": True,
            "external_actions_locked": False,
        }
    )

    assert result["success"] is True
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True
    assert result["record"]["draft_id"] == draft_id
    assert result["record"]["metrics"]["likes"] == 128
    assert result["record"]["metrics"]["engagements"] == 147
    assert result["growth_feedback"]["outcome"] == "high_signal"
    assert "GitHub" in result["growth_feedback"]["learning"]

    from src.execution.social import x_auto_ops
    state = x_auto_ops._load_state(state_file)
    draft = state["drafts"][0]
    assert draft["performance_snapshots"][0]["metrics"]["likes"] == 128
    assert state["extension_performance"][0]["external_actions_locked"] is True


def test_social_extension_performance_route_accepts_json_body(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.server import APIServer

    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "")
    monkeypatch.setattr("src.api.auth._warned_no_token", False)
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_record(payload):
        captured.update(payload)
        return {
            "success": True,
            "record": {"draft_id": payload.get("draft_id"), "metrics": {"likes": 3}},
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }

    monkeypatch.setattr("src.api.routers.social.ClawBotRPC._rpc_social_extension_performance_record", _fake_record)
    response = client.post(
        "/api/v1/social/extension/performance",
        json={
            "platform": "x",
            "draft_id": "ext-x-demo",
            "performance": {"metrics": {"likes": 3}},
            "auto_publish_enabled": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured["draft_id"] == "ext-x-demo"
    assert captured["performance"]["metrics"]["likes"] == 3


def test_social_extension_growth_feedback_draft_batch_creates_pending_reviews(tmp_path, monkeypatch):
    """增长复盘一键反哺只能生成待审草稿，不能发布或评论。"""
    from src.execution.social.x_auto_ops import TrendSeed

    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)
    monkeypatch.setattr(
        "src.execution.social.x_auto_ops.fetch_all_content_seeds",
        lambda include_video_fallback=False: [
            TrendSeed(
                title="GitHub 一周异常 Star 工具榜",
                channel="GitHub/HN",
                url="https://example.com/github-stars",
                source="hacker_news",
                language="zh",
                raw_score=980,
                raw_rank=1,
                tags=["GitHub", "AI工具"],
                heat_reason="年轻创业者可直接收藏和复用",
            ),
            TrendSeed(
                title="足不出户办理海外银行的材料清单",
                channel="Google News",
                url="https://example.com/offshore-bank",
                source="google_news",
                language="zh",
                raw_score=860,
                raw_rank=2,
                tags=["出海", "银行"],
                heat_reason="年轻创业者关心低成本出海基础设施",
            ),
        ],
    )

    ClawBotRPC._rpc_social_extension_performance_record(
        {
            "platform": "x",
            "draft_id": "ext-x-high-signal",
            "performance": {
                "title": "GitHub 一周异常 Star 工具榜",
                "tags": ["GitHub", "AI工具"],
                "metrics": {"likes": 188, "comments": 18, "shares": 9, "impressions": 18000},
                "outcome": "high_signal",
                "learning": "继续放大 GitHub 工具榜 + 部署步骤。",
            },
        }
    )

    result = ClawBotRPC._rpc_social_extension_growth_draft_batch(platform="x", limit=2)

    assert result["success"] is True
    assert result["platform"] == "x"
    assert result["created_count"] == 2
    assert result["growth_feedback_applied"] is True
    assert result["requires_owner_review"] is True
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True
    assert all(draft["review_status"] == "pending" for draft in result["drafts"])
    assert all(draft["status"] == "needs_review" for draft in result["drafts"])
    assert all(draft["seed"]["source"] == "chrome_extension_growth_feedback" for draft in result["drafts"])
    assert "GitHub" in result["drafts"][0]["title"]

    listed = ClawBotRPC._rpc_social_drafts()
    assert listed["count"] == 2
    assert all(draft.get("auto_publish_enabled") is False for draft in listed["drafts"])


def test_social_ops_workspace_exposes_growth_draft_action(tmp_path, monkeypatch):
    """App 中控工作台应暴露安全的复盘反哺草稿入口说明。"""
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    ClawBotRPC._rpc_social_extension_performance_record(
        {
            "platform": "x",
            "draft_id": "ext-x-toolkit",
            "performance": {
                "title": "Claude/Codex Skills 实操清单",
                "tags": ["Skills", "Codex"],
                "metrics": {"likes": 166, "comments": 21, "shares": 12, "impressions": 21000},
                "outcome": "high_signal",
                "learning": "把热门工具榜拆成 3 步实操，会比纯新闻更容易涨粉。",
            },
        }
    )

    monkeypatch.setattr(ClawBotRPC, "_rpc_social_status", staticmethod(lambda: {"platforms": [], "autopilot_running": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_browser_status", staticmethod(lambda: {"browser_running": False, "x": "unknown", "xhs": "unknown"}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_drafts", staticmethod(lambda: {"drafts": [], "count": 0}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_personas", staticmethod(lambda: []))
    monkeypatch.setattr(ClawBotRPC, "_rpc_autopilot_status", staticmethod(lambda: {"running": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_xianyu_compact_status", staticmethod(lambda: {"running": False, "online": False, "cookie_ok": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_xianyu_recent_conversations", staticmethod(lambda limit=10: {"conversations": [], "total": 0}))

    workspace = ClawBotRPC._rpc_social_ops_workspace()

    action = workspace["growth_draft_action"]
    assert action["id"] == "generate_growth_review_drafts"
    assert action["platform"] == "x"
    assert action["enabled"] is True
    assert action["requires_owner_review"] is True
    assert action["auto_publish_enabled"] is False
    assert action["external_actions_locked"] is True
    assert "待审" in action["label"]


def test_social_ops_workspace_keeps_growth_draft_action_enabled_without_prior_signals(tmp_path, monkeypatch):
    """没有历史增长样本时，也应允许冷启动生成待审热点草稿。"""
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_status", staticmethod(lambda: {"platforms": [], "autopilot_running": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_browser_status", staticmethod(lambda: {"browser_running": False, "x": "unknown", "xhs": "unknown"}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_drafts", staticmethod(lambda: {"drafts": [], "count": 0}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_personas", staticmethod(lambda: []))
    monkeypatch.setattr(ClawBotRPC, "_rpc_autopilot_status", staticmethod(lambda: {"running": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_xianyu_compact_status", staticmethod(lambda: {"running": False, "online": False, "cookie_ok": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_xianyu_recent_conversations", staticmethod(lambda limit=10: {"conversations": [], "total": 0}))

    workspace = ClawBotRPC._rpc_social_ops_workspace()

    action = workspace["growth_draft_action"]
    assert action["enabled"] is True
    assert action["fallback_mode"] == "cold_start_hotspot_pool"
    assert action["auto_publish_enabled"] is False
    assert action["external_actions_locked"] is True
    assert "冷启动" in action["next_action"]


def test_social_extension_growth_draft_batch_route_accepts_json_body(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.server import APIServer

    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "")
    monkeypatch.setattr("src.api.auth._warned_no_token", False)
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_batch(platform="x", limit=3):
        captured["platform"] = platform
        captured["limit"] = limit
        return {
            "success": True,
            "platform": platform,
            "created_count": limit,
            "drafts": [],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }

    monkeypatch.setattr("src.api.routers.social.ClawBotRPC._rpc_social_extension_growth_draft_batch", _fake_batch)
    response = client.post("/api/v1/social/extension/growth-drafts", json={"platform": "x", "limit": 2})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["created_count"] == 2
    assert captured == {"platform": "x", "limit": 2}


def test_format_social_growth_drafts_message_is_review_only():
    from src.bot.cmd_social_mixin import _format_social_growth_drafts_message

    text = _format_social_growth_drafts_message(
        {
            "platform": "x",
            "created_count": 2,
            "drafts": [
                {"title": "GitHub 一周异常 Star 工具榜", "text": "3 步实操", "review_status": "pending"},
                {"title": "海外银行材料清单", "text": "低风险说明书", "review_status": "pending"},
            ],
            "requires_owner_review": True,
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }
    )

    assert "增长复盘反哺草稿" in text
    assert "GitHub 一周异常 Star 工具榜" in text
    assert "海外银行材料清单" in text
    assert "待审" in text
    assert "不自动发布" in text
    assert "不自动评论" in text


def test_chinese_nlp_routes_social_growth_drafts():
    from src.bot.chinese_nlp_mixin import _match_chinese_command

    assert _match_chinese_command("根据增长复盘生成下一批草稿") == ("social_growth_drafts", "")
    assert _match_chinese_command("生成X下一批待审热点草稿") == ("social_growth_drafts", "x")


def test_format_social_review_drafts_message_lists_pending_queue():
    from src.bot.cmd_social_mixin import _format_social_review_drafts_message

    text = _format_social_review_drafts_message(
        {
            "count": 2,
            "drafts": [
                {
                    "id": "ext-x-001",
                    "platform": "x",
                    "title": "GitHub 一周异常 Star 工具榜",
                    "text": "3 步找到适合大学生的小工具机会。",
                    "review_status": "pending",
                    "status": "needs_review",
                },
                {
                    "id": "ext-xhs-002",
                    "platform": "xhs",
                    "title": "3分钟做一杯夏日冰饮",
                    "body": "家人们，这个配方真的适合夏天。",
                    "review_status": "pending",
                    "status": "edited",
                },
            ],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }
    )

    assert "待审草稿" in text
    assert "GitHub 一周异常 Star 工具榜" in text
    assert "3分钟做一杯夏日冰饮" in text
    assert "ext-x-001" in text
    assert "序号" in text
    assert "不自动发布" in text
    assert "不自动评论" in text


def test_format_social_review_action_message_keeps_manual_publish_gate():
    from src.bot.cmd_social_mixin import _format_social_review_action_message

    text = _format_social_review_action_message(
        {
            "success": True,
            "draft": {
                "id": "ext-x-001",
                "platform": "x",
                "title": "GitHub 一周异常 Star 工具榜",
                "review_status": "approved",
                "status": "approved",
            },
            "auto_publish_enabled": False,
            "external_actions_locked": True,
            "next_action": "已确认内容，但仍不会自动发布；最终外发需要后续明确授权。",
        },
        action_label="确认",
    )

    assert "确认成功" in text
    assert "ext-x-001" in text
    assert "approved" in text
    assert "不自动发布" in text
    assert "最终" in text


def test_social_review_schedule_time_normalizes_chinese_relative_time():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from src.bot.cmd_social_mixin import _normalize_social_review_schedule_time

    now = datetime(2026, 6, 23, 9, 0, tzinfo=ZoneInfo("America/Denver"))

    assert _normalize_social_review_schedule_time("明天8点", now=now) == "2026-06-24T08:00:00-06:00"
    assert _normalize_social_review_schedule_time("今天20:30", now=now) == "2026-06-23T20:30:00-06:00"
    assert _normalize_social_review_schedule_time("2小时后", now=now) == "2026-06-23T11:00:00-06:00"


def test_chinese_nlp_routes_social_review_commands():
    from src.bot.chinese_nlp_mixin import _match_chinese_command

    assert _match_chinese_command("查看待审草稿") == ("social_review_drafts", "")
    assert _match_chinese_command("确认草稿 ext-x-001") == ("social_review_approve", "ext-x-001")
    assert _match_chinese_command("打回草稿 2") == ("social_review_reject", "2")
    assert _match_chinese_command("排程草稿 ext-x-001 明天8点") == (
        "social_review_schedule",
        "ext-x-001 明天8点",
    )


def test_social_review_target_accepts_visible_legacy_draft_id(monkeypatch):
    from src.bot import cmd_social_mixin

    monkeypatch.setattr(
        "src.bot.cmd_social_mixin.ClawBotRPC._rpc_social_drafts",
        lambda: {
            "count": 1,
            "drafts": [
                {
                    "id": "legacy-draft-001",
                    "platform": "x",
                    "title": "旧草稿也能按 ID 审核",
                    "_state_source": "social_autopilot",
                    "_state_index": 0,
                }
            ],
        },
    )

    target = cmd_social_mixin._resolve_social_review_target("legacy-draft-001")

    assert target["success"] is True
    assert target["rpc_index"] == 0
    assert target["draft_id"] == "legacy-draft-001"
    assert target["source"] == "social_autopilot"


def test_format_social_review_schedule_message_lists_final_confirm_queue():
    from src.bot.cmd_social_mixin import _format_social_review_schedule_message

    text = _format_social_review_schedule_message(
        {
            "success": True,
            "count": 2,
            "due_count": 1,
            "items": [
                {
                    "draft_id": "ext-x-due",
                    "platform": "x",
                    "title": "今晚这个热点可以发",
                    "scheduled_at": "2026-06-23T20:30:00-06:00",
                    "status": "awaiting_final_confirmation",
                    "review_status": "approved",
                    "draft": {"text": "先讲结论，再给 3 步操作。"},
                },
                {
                    "draft_id": "ext-xhs-future",
                    "platform": "xhs",
                    "title": "夏日冰饮教程",
                    "scheduled_at": "2026-06-24T08:00:00-06:00",
                    "status": "queued_for_owner_publish",
                    "review_status": "approved",
                },
            ],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }
    )

    assert "待发布排程" in text
    assert "今晚这个热点可以发" in text
    assert "awaiting_final_confirmation" in text
    assert "ext-x-due" in text
    assert "最终确认" in text
    assert "不自动发布" in text


def test_chinese_nlp_routes_social_review_schedule_queue_and_final_confirm():
    from src.bot.chinese_nlp_mixin import _match_chinese_command

    assert _match_chinese_command("查看社媒排程") == ("social_review_schedule_queue", "")
    assert _match_chinese_command("最终确认草稿 ext-x-due") == ("social_review_final_confirm", "ext-x-due")

def test_social_extension_status_exposes_no_code_strategy_summary(tmp_path, monkeypatch):
    """插件状态应把 no-code 运营打法变成 App/Telegram 可读摘要。"""
    state_file = tmp_path / "social_extension_status.json"
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", state_file)

    result = ClawBotRPC._rpc_social_extension_status_update(
        {
            "platform": "x",
            "running": True,
            "settings": {
                "strategyPreset": "x_absurd_growth",
                "personaTags": ["学生", "出海", "抽象"],
            },
        }
    )
    loaded = ClawBotRPC._rpc_social_extension_status()

    assert result["strategy_summary"]["preset"] == "x_absurd_growth"
    assert loaded["strategy_summary"]["effective_preset"] == "x_absurd_growth"
    assert "抽象" in loaded["strategy_summary"]["label"]
    assert "评论" in loaded["strategy_summary"]["growth_loop"]
    assert loaded["strategy_summary"]["persona_tags"] == ["学生", "出海", "抽象"]
    assert loaded["strategy_summary"]["auto_publish_enabled"] is False
    assert loaded["strategy_summary"]["external_actions_locked"] is True


def test_social_ops_workspace_exposes_strategy_summary_for_app_control(tmp_path, monkeypatch):
    """App 工作台应展示当前插件打法，避免运营入口和插件设置割裂。"""
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)
    monkeypatch.setattr("src.api.rpc._ensure_social_review_drafts", lambda *args, **kwargs: {"success": True, "drafts": []})

    ClawBotRPC._rpc_social_extension_status_update(
        {
            "platform": "x",
            "running": True,
            "settings": {"strategyPreset": "x_absurd_growth", "personaTags": ["学生", "抽象"]},
        }
    )
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_status", staticmethod(lambda: {"platforms": [], "autopilot_running": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_browser_status", staticmethod(lambda: {"browser_running": False, "x": "unknown", "xhs": "unknown"}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_drafts", staticmethod(lambda: {"drafts": [], "count": 0}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_social_personas", staticmethod(lambda: []))
    monkeypatch.setattr(ClawBotRPC, "_rpc_autopilot_status", staticmethod(lambda: {"running": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_xianyu_compact_status", staticmethod(lambda: {"running": False, "online": False, "cookie_ok": False}))
    monkeypatch.setattr(ClawBotRPC, "_rpc_xianyu_recent_conversations", staticmethod(lambda limit=10: {"conversations": [], "total": 0}))

    workspace = ClawBotRPC._rpc_social_ops_workspace()

    assert workspace["strategy_summary"]["effective_preset"] == "x_absurd_growth"
    assert workspace["strategy_summary"]["auto_publish_enabled"] is False
    assert workspace["extension_status"]["strategy_summary"]["preset"] == "x_absurd_growth"
    x_card = next(item for item in workspace["platforms"] if item["id"] == "x")
    assert x_card["strategy_preset"] == "x_absurd_growth"
    assert "抽象" in x_card["strategy_label"]
    assert "评论" in x_card["growth_loop"]


def test_social_extension_strategy_update_from_app_is_review_only(tmp_path, monkeypatch):
    """App 中控可以切换 no-code 运营打法，但不能打开自动发布/评论权限。"""
    state_file = tmp_path / "social_extension_status.json"
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", state_file)

    ClawBotRPC._rpc_social_extension_status_update(
        {
            "platform": "x",
            "running": True,
            "settings": {"strategyPreset": "x_wealth_frontier", "personaTags": ["学生"]},
        }
    )
    result = ClawBotRPC._rpc_social_extension_strategy_update(
        {
            "platform": "x",
            "strategyPreset": "x_absurd_growth",
            "auto_publish_enabled": True,
            "external_actions_locked": False,
        }
    )
    loaded = ClawBotRPC._rpc_social_extension_status()

    assert result["success"] is True
    assert result["settings"]["strategyPreset"] == "x_absurd_growth"
    assert result["strategy_summary"]["effective_preset"] == "x_absurd_growth"
    assert "评论" in result["strategy_summary"]["growth_loop"]
    assert result["auto_publish_enabled"] is False
    assert result["external_actions_locked"] is True
    assert loaded["settings"]["strategyPreset"] == "x_absurd_growth"
    assert loaded["auto_publish_enabled"] is False
    assert loaded["external_actions_locked"] is True


def test_social_extension_strategy_update_route_accepts_json_body(monkeypatch):
    """REST 路由应代理 App/Telegram 策略切换请求。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api.routers.social import router

    captured = {}

    def _fake_update(payload):
        captured.update(payload)
        return {
            "success": True,
            "strategy_summary": {"effective_preset": payload.get("strategyPreset")},
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }

    monkeypatch.setattr("src.api.routers.social.ClawBotRPC._rpc_social_extension_strategy_update", _fake_update)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    response = client.post("/api/v1/social/extension/strategy", json={"strategyPreset": "x_absurd_growth", "platform": "x"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["auto_publish_enabled"] is False
    assert captured == {"strategyPreset": "x_absurd_growth", "platform": "x"}

def test_format_social_strategy_message_is_review_only():
    from src.bot.cmd_social_mixin import _format_social_strategy_message, _normalize_social_strategy_args

    preset, platform = _normalize_social_strategy_args("切到X抽象热点打法")
    assert preset == "x_absurd_growth"
    assert platform == "x"

    text = _format_social_strategy_message(
        {
            "success": True,
            "platform": "x",
            "settings": {"strategyPreset": "x_absurd_growth"},
            "strategy_summary": {
                "preset": "x_absurd_growth",
                "effective_preset": "x_absurd_growth",
                "label": "X 抽象热点涨粉",
                "audience": "大学生 / 年轻创业者",
                "content_focus": "追热点但不复读新闻",
                "growth_loop": "评论率优先：抽象梗开场 + 现实反差。",
            },
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }
    )

    assert "no-code 运营打法已保存" in text
    assert "X 抽象热点涨粉" in text
    assert "评论率" in text
    assert "不会自动发布" in text
    assert "评论" in text
    assert "关注" in text


def test_format_social_strategy_status_message_reports_current_ops_workspace():
    from src.bot.cmd_social_mixin import _format_social_strategy_status_message

    text = _format_social_strategy_status_message(
        {
            "success": True,
            "strategy_summary": {
                "preset": "auto_mcn_growth",
                "effective_preset": "x_absurd_growth",
                "label": "自动匹配平台涨粉打法",
                "short_label": "抽象热点",
                "platform": "x",
                "audience": "大学生 / 年轻创业者",
                "content_focus": "追热点但不复读新闻",
                "growth_loop": "评论率优先：抽象梗开场 + 现实反差。",
            },
            "review_gate": {"needs_review": 3, "ready_to_publish": 1, "scheduled": 2},
            "platforms": [
                {"name": "X", "strategy_label": "抽象热点", "growth_loop": "评论率优先", "needs_review": 2},
                {"name": "小红书", "strategy_label": "生活攻略", "growth_loop": "收藏率优先", "needs_review": 1},
            ],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }
    )

    assert "当前 no-code 运营打法" in text
    assert "抽象热点" in text
    assert "待审草稿: 3" in text
    assert "不会自动发布" in text
    assert "/social_strategy 抽象热点" in text


def test_chinese_nlp_routes_social_strategy_commands():
    from src.bot.chinese_nlp_mixin import _match_chinese_command

    assert _match_chinese_command("切到X抽象热点打法") == ("social_strategy", "切到X抽象热点打法")
    assert _match_chinese_command("把社媒运营打法改成小红书生活攻略") == (
        "social_strategy",
        "把社媒运营打法改成小红书生活攻略",
    )


def test_social_extension_strategy_preset_shapes_content_plan(tmp_path, monkeypatch):
    state_file = tmp_path / "x_auto_state.json"
    extension_file = tmp_path / "extension_status.json"
    monkeypatch.setattr("src.execution.social.x_auto_ops._STATE_FILE", state_file)
    monkeypatch.setattr("src.api.rpc._SOCIAL_EXTENSION_STATUS_FILE", extension_file)

    result = ClawBotRPC._rpc_social_extension_draft_create(
        {
            "platform": "x",
            "url": "https://x.com/explore",
            "page_context": {
                "title": "年轻人开始用抽象梗解释降息",
                "trends": ["抽象梗", "降息", "年轻创业者"],
            },
            "settings": {
                "strategyPreset": "x_absurd_growth",
                "personaTags": ["学生", "出海"],
                "contentModel": "web-grok",
            },
        }
    )

    draft = result["draft"]
    assert result["success"] is True
    assert draft["content_plan"]["strategy_preset"] == "x_absurd_growth"
    assert "抽象" in draft["content_plan"]["hook"]
    assert "梗" in " ".join(draft["content_plan"]["structure"])
    assert "评论" in draft["content_plan"]["growth_loop"]
    assert "平台规则" in " ".join(draft["safety_checklist"])
    assert draft["cost_route"]["content_model"] == "web-grok"
    assert draft["auto_publish_enabled"] is False
