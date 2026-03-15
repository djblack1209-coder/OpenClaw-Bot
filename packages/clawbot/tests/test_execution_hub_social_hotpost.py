import pytest
from typing import cast

import src.execution_hub as execution_hub_module
from src.execution_hub import ExecutionHub
from src.news_fetcher import NewsFetcher


class StubFetcher:
    async def fetch_from_google_news_rss(self, query, count=5):
        if query == "GitHub Copilot GPT-5.4":
            return [
                {
                    "title": "GitHub Copilot仅用数小时完成接入OpenAI最新旗舰模型GPT‑5.4 - cnBeta.COM",
                    "source": "cnBeta.COM",
                    "url": "https://example.com/copilot-gpt54",
                },
                {
                    "title": "GitHub Copilot SDK 使开发人员可以将 Copilot CLI 的引擎集成到应用中 - InfoQ 官网",
                    "source": "InfoQ 官网",
                    "url": "https://example.com/copilot-sdk",
                },
            ]
        if query == "AI Agent workflow":
            return [
                {
                    "title": "一切皆可Agent Skills，无处不在的AI Agent会替代业务流程吗？ - 51CTO",
                    "source": "51CTO",
                    "url": "https://example.com/agent-workflow",
                }
            ]
        if query == "OpenClaw":
            return [
                {
                    "title": "OpenClaw 100个实战案例全公开（最全实操手册） - 51CTO",
                    "source": "51CTO",
                    "url": "https://example.com/openclaw-guide",
                }
            ]
        return []

    async def fetch_from_bing(self, query, count=5):
        return []


def test_save_social_draft_blocks_recent_duplicates(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    first = hub.save_social_draft("x", "OpenClaw 实用教程", "同一条内容", topic="OpenClaw 实用教程")
    second = hub.save_social_draft("x", "OpenClaw 实用教程", "同一条内容", topic="OpenClaw 实用教程")

    assert first["success"] is True
    assert second["success"] is False
    assert second["duplicate"] is True


@pytest.mark.asyncio
async def test_discover_hot_social_topics_prefers_openclaw_practical_candidates(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    ret = await hub.discover_hot_social_topics(limit=3)

    assert ret["success"] is True
    assert ret["candidates"][0]["topic"].startswith("OpenClaw")
    assert ret["candidates"][0]["trend_label"] == "GitHub Copilot + GPT-5.4"
    assert ret["candidates"][0]["utility_score"] >= 60


@pytest.mark.asyncio
async def test_autopost_hot_content_publishes_both_platforms(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    def fake_run_social_worker(action, payload):
        if action == "bootstrap":
            return {"success": True, "browser_running": True, "x_ready": True, "xiaohongshu_ready": True, "tabs": 4}
        if action == "render":
            return {"success": True, "x_cover": "/tmp/x-cover.png", "xhs": ["/tmp/cover.png", "/tmp/reasons.png"]}
        if action == "publish_x":
            return {"success": True, "url": "https://x.com/test/status/1", "status": "published"}
        if action == "publish_xhs":
            return {"success": True, "url": "https://www.xiaohongshu.com/discovery/item/1", "status": "published"}
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr(hub, "_run_social_worker", fake_run_social_worker)

    ret = await hub.autopost_hot_content("all")

    assert ret["success"] is True
    assert ret["topic"].startswith("OpenClaw")
    assert ret["results"]["x"]["published"]["success"] is True
    assert ret["results"]["xiaohongshu"]["published"]["success"] is True
    assert "For You" in ret["results"]["x"]["body"]
    assert "数字生命" in ret["results"]["x"]["body"]
    assert "女大学生" in ret["results"]["x"]["body"]
    assert "收藏率" in ret["results"]["xiaohongshu"]["body"]
    assert "OpenClaw" in ret["results"]["xiaohongshu"]["body"]
    assert "数字生命" in ret["results"]["xiaohongshu"]["body"]


@pytest.mark.asyncio
async def test_build_social_plan_returns_daily_candidates(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    ret = await hub.build_social_plan(limit=2)

    assert ret["success"] is True
    assert ret["mode"] == "daily"
    assert len(ret["plans"]) >= 1
    assert ret["plans"][0]["topic"].startswith("OpenClaw")
    assert ret["plans"][0]["x_tactic"]
    assert ret["plans"][0]["xhs_tactic"]


@pytest.mark.asyncio
async def test_build_social_repost_bundle_creates_two_platform_packages(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    def fake_run_social_worker(action, payload):
        if action == "research":
            return {
                "success": True,
                "topic": payload.get("topic", "OpenClaw 实战"),
                "x": [{"title": "OpenClaw 上线 GPT-5.4 工作流", "source": "InfoQ", "url": "https://example.com/x"}],
                "xiaohongshu": [{"title": "OpenClaw 冷启动教程", "source": "51CTO", "url": "https://example.com/xhs"}],
                "insights": {"patterns": ["教程", "清单"], "hooks": ["GPT-5.4"], "opportunity": "把热点写成可复制 SOP"},
            }
        if action == "render":
            return {"success": True, "x_cover": "/tmp/x-cover.png", "xhs": ["/tmp/cover.png", "/tmp/reasons.png"]}
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr(hub, "_run_social_worker", fake_run_social_worker)

    ret = await hub.build_social_repost_bundle("OpenClaw 实战")

    assert ret["success"] is True
    assert ret["results"]["x"]["success"] is True
    assert ret["results"]["xiaohongshu"]["success"] is True
    assert ret["results"]["x"]["draft_id"]
    assert ret["results"]["xiaohongshu"]["draft_id"]


def test_compose_human_topic_content_uses_zero_cost_validation_language(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    strategy = {
        "style_id": 0,
        "trend_label": "AI 出海",
        "opening_rule": "先做 MVP 再看预算",
    }
    strategy = hub._apply_social_persona(strategy, topic="AI出海")
    sources = [
        {"title": "海外独立开发者靠教程拿到首批用户", "source": "InfoQ 官网", "url": "https://example.com/1"},
        {"title": "小红书资料库打法还在吃收藏红利", "source": "51CTO", "url": "https://example.com/2"},
    ]

    x_text = hub._compose_human_x_post("AI出海", strategy, sources)
    xhs = hub._compose_human_xhs_article("AI出海", strategy, sources)

    assert "数字生命" in x_text
    assert "For You" in x_text
    assert "高价值回复" in x_text
    assert "收藏率" in xhs["body"]
    assert "女大学生" in xhs["body"]
    assert "数字生命" in xhs["body"]
    assert "如果你愿意教一个数字生命一件事" in xhs["body"]


def test_derive_topic_strategy_exposes_utility_playbook(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    strategy = hub._derive_topic_strategy(
        "OpenClaw AI Coding",
        {
            "x": [{"title": "GitHub Copilot 接入 GPT-5.4", "source": "InfoQ 官网", "url": "https://example.com/1"}],
            "xiaohongshu": [{"title": "AI Coding 冷启动教程", "source": "51CTO", "url": "https://example.com/2"}],
            "insights": {
                "patterns": ["教程", "SOP", "清单"],
                "hooks": ["GPT-5.4"],
                "opportunity": "把模型升级讲成团队工作流教程",
            },
        },
        {"runs": []},
    )

    assert strategy["utility_score"] >= 70
    assert "OpenClaw" in strategy["positioning"]
    assert strategy["audience"]
    assert strategy["cta"]
    assert strategy["measurement_window"]
    assert strategy["x_tactic"]
    assert strategy["xhs_tactic"]
    assert strategy["validation_metrics"]
    assert strategy["persona_id"] == "lin-zhixia-digital-life"
    assert "数字生命" in strategy["persona_truth"]


def test_social_launch_kit_exposes_persona_prompt_and_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    ret = hub.build_social_launch_kit()

    assert ret["success"] is True
    assert ret["persona"]["name"] == "林知夏"
    assert "数字生命" in ret["x"]["body"]
    assert "自拍" not in ret["x"]["body"]
    assert "大学女" not in ret["persona"]["selfie_prompt"]
    assert "adult 20-year-old Chinese woman" in ret["image"]["prompt"]
    assert "no beauty filter" in ret["image"]["prompt"]
    assert "underage" in ret["image"]["negative_prompt"]


def test_create_social_launch_drafts_saves_intro_posts(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    ret = hub.create_social_launch_drafts()

    assert ret["success"] is True
    assert ret["x"]["draft_id"]
    assert ret["xiaohongshu"]["draft_id"]
    assert "数字生命" in ret["x"]["body"]
    assert "林知夏" in ret["xiaohongshu"]["body"]


def test_extract_json_object_parses_operator_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    raw = '{"summary":"ok","action":{"type":"observe"},"next_check_minutes":180}'

    payload = hub._extract_json_object(raw)

    assert payload is not None
    assert payload["action"]["type"] == "observe"
    assert payload["next_check_minutes"] == 180


def test_extract_social_priority_queue_prefers_xhs_comment_questions(monkeypatch, tmp_path):
    monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
    hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))

    workspace = {
        "x": {"notifications": {"lines": ["有人喜欢了你的回复"]}, "messages": {"lines": []}, "trends": {"lines": []}},
        "xiaohongshu": {
            "notifications": {"lines": ["评论了你的笔记", "我很好奇，你发这篇帖子的tag是如何选的？"]},
            "messages": {"lines": []},
            "mentions_items": [
                {
                    "content": "我很好奇，你发这篇帖子的tag是如何选的？",
                    "comment_id": "c1",
                    "note_url": "https://www.xiaohongshu.com/explore/1?xsec_token=abc",
                    "user_name": "测试用户",
                    "note_title": "OpenClaw 数字生命打个招呼",
                }
            ],
            "connections_items": [
                {
                    "title": "开始关注你了",
                    "user_name": "新粉丝",
                }
            ],
        },
    }

    queue = hub._extract_social_priority_queue(workspace)

    assert queue
    assert queue[0]["platform"] == "xiaohongshu"
    assert queue[0]["channel"] == "mentions"
    assert queue[0]["target_comment_id"] == "c1"
