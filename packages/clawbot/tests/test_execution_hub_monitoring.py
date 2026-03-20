import pytest
from typing import cast

import src.execution_hub as execution_hub_module
from src.news_fetcher import NewsFetcher
from src.execution_hub import ExecutionHub


class TestExecutionHubMonitoring:
    def test_curate_monitor_items_filters_noise_and_dedupes(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPS_MONITOR_BLOCKED_SOURCES", "新浪财经,驱动之家,中关村在线")
        monkeypatch.setenv("OPS_MONITOR_LOW_VALUE_KEYWORDS", "独显,份额,专卖,显卡")
        monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")

        hub = ExecutionHub()

        items = [
            {
                "title": "NVIDIA- 在中国一颗也卖不出去！NVIDIA无奈停产H200芯片：加速Vera Rubin量产 - 新浪财经",
                "source": "新浪财经",
                "url": "https://example.com/a",
            },
            {
                "title": "独显市场一绿遮天！NVIDIA独吞94%份额、AMD只剩5% - 驱动之家",
                "source": "驱动之家",
                "url": "https://example.com/b",
            },
            {
                "title": "NVIDIA 发布新 AI 平台 - Reuters",
                "source": "Reuters",
                "url": "https://example.com/c",
            },
            {
                "title": "NVIDIA 发布新 AI 平台",
                "source": "Reuters",
                "url": "https://example.com/d",
            },
        ]

        curated = hub._curate_monitor_items(items, limit=3)

        assert curated == [
            {
                "title": "NVIDIA 发布新 AI 平台",
                "source": "Reuters",
                "url": "https://example.com/c",
                "digest_key": "nvidia发布新ai平台",
            }
        ]

    @pytest.mark.asyncio
    async def test_run_monitors_once_uses_stable_digest_for_reordered_items(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPS_MONITOR_BLOCKED_SOURCES", "")
        monkeypatch.setenv("OPS_MONITOR_LOW_VALUE_KEYWORDS", "")
        monkeypatch.setenv("OPS_MONITOR_ALERT_LIMIT", "3")
        monkeypatch.setenv("OPS_MONITOR_FETCH_COUNT", "8")
        monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")

        class StubFetcher:
            def __init__(self):
                self.calls = 0

            async def fetch_from_google_news_rss(self, query, count=5):
                self.calls += 1
                if self.calls == 1:
                    return [
                        {"title": "NVIDIA 发布新 AI 平台 - Reuters", "source": "Reuters", "url": "https://example.com/1"},
                        {"title": "NVIDIA 推出新 SDK - The Verge", "source": "The Verge", "url": "https://example.com/2"},
                    ]
                return [
                    {"title": "NVIDIA 推出新 SDK - The Verge", "source": "The Verge", "url": "https://example.com/2"},
                    {"title": "NVIDIA 发布新 AI 平台 - Reuters", "source": "Reuters", "url": "https://example.com/1"},
                ]

            async def fetch_from_bing(self, query, count=5):
                return []

        hub = ExecutionHub(news_fetcher=cast(NewsFetcher, StubFetcher()))
        hub.add_monitor("NVIDIA")

        first = await hub.run_monitors_once()
        second = await hub.run_monitors_once()

        assert len(first) == 1
        assert second == []

    def test_extract_x_profile_posts_from_markdown(self, monkeypatch, tmp_path):
        monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
        hub = ExecutionHub()

        markdown = """
[WaytoAGI｜通往AGI之路](https://x.com/WaytoAGI)

[@WaytoAGI](https://x.com/WaytoAGI)

[Mar 25, 2024](https://x.com/WaytoAGI/status/1772087763044839450)

《写给不会代码的你：20分钟上手 Python + AI》，作者大聪明，这份简明入门旨在让大家更快掌握 Python 和 AI 的相互调用。

[44K](https://x.com/WaytoAGI/status/1772087763044839450/analytics)

[Dec 10, 2023](https://x.com/WaytoAGI/status/1733793320940552476)

《Claude官方文档提示词工程最佳实践》来自未来力场中英文编译。
        """.strip()

        posts = hub._extract_x_profile_posts_from_markdown("WaytoAGI", markdown, limit=3)

        assert len(posts) == 2
        assert posts[0]["digest_key"] == "1772087763044839450"
        assert posts[0]["url"] == "https://x.com/WaytoAGI/status/1772087763044839450"
        assert "20分钟上手 Python + AI" in posts[0]["title"]

    def test_extract_x_handle_candidates_from_markdown(self, monkeypatch, tmp_path):
        monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
        hub = ExecutionHub()

        markdown = """
1.   中文 AI 圈高频信息源，长期分享 Prompt 工程、AI 实战、前沿工具与模型解读。WaytoAGI
2.   出海 SaaS 和 AI 产品创业者，偏产品开发、增长和 SEO 实战。HongyuanCao
3.   独立开发与出海 SaaS 路线代表账号，分享模板、建站、流量和变现经验。indie_maker_fox
4.   中文互联网知识分享常青树，科技与工具类内容长期稳定高质量。阮一峰
        """.strip()

        handles = hub._extract_x_handle_candidates_from_markdown(markdown, limit=10)

        assert handles == ["WaytoAGI", "HongyuanCao", "indie_maker_fox"]

    @pytest.mark.asyncio
    async def test_create_social_draft_for_x_and_xiaohongshu(self, monkeypatch, tmp_path):
        monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
        hub = ExecutionHub()
        hub.add_monitor("WaytoAGI", "x_profile")
        hub.add_monitor("nextify2024", "x_profile")

        async def fake_fetch_x_profile_posts(handle, count=5):
            return [
                {
                    "title": f"{handle} 最新更新，分享 AI 与出海实战",
                    "url": f"https://x.com/{handle}/status/123",
                    "source": f"X @{handle}",
                    "digest_key": f"{handle}-123",
                    "published": "Mar 7, 2026",
                }
            ]

        monkeypatch.setattr(hub, "fetch_x_profile_posts", fake_fetch_x_profile_posts)

        x_draft = await hub.create_social_draft("x", topic="AI 出海", max_items=2)
        xhs_draft = await hub.create_social_draft("xiaohongshu", topic="AI 出海", max_items=2)

        assert x_draft["success"] is True
        assert x_draft["draft_id"] > 0
        assert "今天筛了 2 条值得看的AI 出海更新" in x_draft["body"]
        assert "AI" in x_draft["body"]

        assert xhs_draft["success"] is True
        assert xhs_draft["draft_id"] > 0
        assert xhs_draft["title"].startswith("今日AI 出海情报")
        assert "原文：https://x.com/WaytoAGI/status/123" in xhs_draft["body"]

    @pytest.mark.asyncio
    async def test_generate_x_monitor_brief_uses_announcement_layout(self, monkeypatch, tmp_path):
        monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
        hub = ExecutionHub()
        hub.add_monitor("WaytoAGI", "x_profile")

        async def fake_fetch_x_profile_posts(handle, count=1):
            return [
                {
                    "title": "WaytoAGI 分享最新 AI 工作流拆解",
                    "url": "https://x.com/WaytoAGI/status/123",
                    "source": "X @WaytoAGI",
                }
            ]

        monkeypatch.setattr(hub, "fetch_x_profile_posts", fake_fetch_x_profile_posts)

        digest = await hub.generate_x_monitor_brief()

        assert digest.startswith("OpenClaw「X 资讯快讯」")
        assert "【@WaytoAGI】" in digest
        assert "详情：https://x.com/WaytoAGI/status/123" in digest

    def test_format_monitor_alert_uses_announcement_layout(self, monkeypatch, tmp_path):
        monkeypatch.setattr(execution_hub_module, "DB_PATH", tmp_path / "execution_hub.db")
        hub = ExecutionHub()

        text = hub.format_monitor_alert(
            {
                "keyword": "NVIDIA",
                "source": "news",
                "items": [
                    {
                        "title": "NVIDIA 发布新 AI 平台",
                        "source": "Reuters",
                        "url": "https://example.com/nvda",
                    }
                ],
            }
        )

        assert text.startswith("OpenClaw「资讯快讯」NVIDIA")
        assert "【第 1 条】" in text
        assert "详情：https://example.com/nvda" in text
