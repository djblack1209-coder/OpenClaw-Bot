from __future__ import annotations

from src.intel.sources.ai_model_updates import (
    AIModelUpdatesAdapter,
    FeedSpec,
    parse_anthropic_news_html,
    parse_deepseek_news_html,
    parse_rss_xml,
)

OPENAI_RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Introducing GPT-5.2</title>
      <link>https://openai.com/news/gpt-5-2</link>
      <pubDate>Tue, 07 Jul 2026 12:00:00 GMT</pubDate>
      <description>Latest frontier model update.</description>
    </item>
    <item>
      <title>OpenAI platform release notes</title>
      <link>https://openai.com/news/platform-release-notes</link>
      <pubDate>Mon, 06 Jul 2026 12:00:00 GMT</pubDate>
      <description>API and platform update.</description>
    </item>
  </channel>
</rss>
"""


ANTHROPIC_HTML_SAMPLE = """
<html><body>
  <a href="/news/claude-sonnet-5">
    <div><time datetime="2026-07-07">Jul 7, 2026</time></div>
    <h3>Introducing Claude Sonnet 5</h3>
    <p>Our latest model for coding and agents.</p>
  </a>
</body></html>
"""


DEEPSEEK_HTML_SAMPLE = """
<html><body>
  <a target="_blank" href="https://mp.weixin.qq.com/s/example">
    🎉 DeepSeek-V4 预览版本发布，具备世界顶级推理性能，Agent 能力大幅提高，已在网页端、APP 和 API 上线，点击查看详情。
  </a>
</body></html>
"""


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_parse_openai_rss_items_to_ai_update_rows():
    rows = parse_rss_xml(OPENAI_RSS_SAMPLE, provider="openai", limit=1)

    assert rows == [
        {
            "source": "official_rss",
            "provider": "openai",
            "title": "Introducing GPT-5.2",
            "url": "https://openai.com/news/gpt-5-2",
            "published_at": "Tue, 07 Jul 2026 12:00:00 GMT",
            "summary": "Latest frontier model update.",
        }
    ]


def test_parse_anthropic_news_html_extracts_official_news_links():
    rows = parse_anthropic_news_html(ANTHROPIC_HTML_SAMPLE, limit=1)

    assert rows == [
        {
            "source": "official_html",
            "provider": "anthropic",
            "title": "Introducing Claude Sonnet 5",
            "url": "https://www.anthropic.com/news/claude-sonnet-5",
            "published_at": "2026-07-07",
            "summary": "Our latest model for coding and agents.",
        }
    ]


def test_parse_deepseek_news_html_extracts_official_announcement_link():
    rows = parse_deepseek_news_html(
        DEEPSEEK_HTML_SAMPLE
        + """
        <a href="https://chat.deepseek.com">开始对话 与 DeepSeek 免费对话 体验全新旗舰模型</a>
        <a href="https://platform.deepseek.com">API 开放平台 调用 DeepSeek 最新模型</a>
        """,
        limit=3,
    )

    assert rows == [
        {
            "source": "official_html",
            "provider": "deepseek",
            "title": "DeepSeek-V4 预览版本发布",
            "url": "https://mp.weixin.qq.com/s/example",
            "published_at": "",
            "summary": "具备世界顶级推理性能，Agent 能力大幅提高，已在网页端、APP 和 API 上线，点击查看详情。",
        }
    ]


def test_ai_model_updates_adapter_combines_official_feeds_without_credentials():
    bodies = {
        "https://openai.com/news/rss.xml": OPENAI_RSS_SAMPLE,
        "https://www.anthropic.com/news": ANTHROPIC_HTML_SAMPLE,
        "https://www.deepseek.com/": DEEPSEEK_HTML_SAMPLE,
    }
    calls: list[str] = []

    def opener(request, timeout: int):
        calls.append(request.full_url)
        return _FakeResponse(bodies[request.full_url])

    adapter = AIModelUpdatesAdapter(
        opener=opener,
        timeout=6,
        evidence_path="evidence/ai-model-updates.json",
        feeds=(
            FeedSpec(provider="openai", kind="rss", url="https://openai.com/news/rss.xml"),
            FeedSpec(provider="anthropic", kind="anthropic_html", url="https://www.anthropic.com/news"),
            FeedSpec(provider="deepseek", kind="deepseek_html", url="https://www.deepseek.com/"),
        ),
    )

    result = adapter.fetch(limit=3)

    assert result.source == "ai_model_updates"
    assert result.worker == "overseas"
    assert result.health_status == "success"
    assert result.raw_count == 3
    assert [item["provider"] for item in result.items] == ["openai", "anthropic", "deepseek"]
    assert calls == [
        "https://openai.com/news/rss.xml",
        "https://www.anthropic.com/news",
        "https://www.deepseek.com/",
    ]
    assert result.evidence_path.endswith("ai-model-updates.json")


def test_ai_model_updates_adapter_samples_each_provider_before_truncating():
    bodies = {
        "https://openai.com/news/rss.xml": OPENAI_RSS_SAMPLE,
        "https://www.anthropic.com/news": ANTHROPIC_HTML_SAMPLE,
        "https://www.deepseek.com/": DEEPSEEK_HTML_SAMPLE,
    }

    def opener(request, timeout: int):
        return _FakeResponse(bodies[request.full_url])

    adapter = AIModelUpdatesAdapter(opener=opener)

    result = adapter.fetch(limit=3)

    assert [item["provider"] for item in result.items] == ["openai", "anthropic", "deepseek"]
