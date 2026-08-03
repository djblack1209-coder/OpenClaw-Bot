from __future__ import annotations

from src.intel.sources.github_trending import (
    GitHubTrendingAdapter,
    parse_github_trending_html,
)

SAMPLE_GITHUB_TRENDING_HTML = """
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/openai/codex">
      openai / codex
    </a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">
    Lightweight coding agent for terminal workflows.
  </p>
  <span itemprop="programmingLanguage">Python</span>
  <span class="d-inline-block float-sm-right">1,234 stars today</span>
</article>
<article class="Box-row">
  <h2><a href="/anthropics/claude-code">anthropics / claude-code</a></h2>
  <p class="col-9 color-fg-muted my-1 pr-4">Agentic coding CLI.</p>
  <span itemprop="programmingLanguage">TypeScript</span>
  <span>98 stars today</span>
</article>
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


def test_parse_github_trending_html_normalizes_daily_rows():
    rows = parse_github_trending_html(SAMPLE_GITHUB_TRENDING_HTML, limit=2)

    assert rows == [
        {
            "source": "github_trending_daily",
            "provider": "github",
            "repo": "openai/codex",
            "title": "openai/codex",
            "url": "https://github.com/openai/codex",
            "description": "Lightweight coding agent for terminal workflows.",
            "summary": "Lightweight coding agent for terminal workflows.",
            "language": "Python",
            "stars_today": "1234",
        },
        {
            "source": "github_trending_daily",
            "provider": "github",
            "repo": "anthropics/claude-code",
            "title": "anthropics/claude-code",
            "url": "https://github.com/anthropics/claude-code",
            "description": "Agentic coding CLI.",
            "summary": "Agentic coding CLI.",
            "language": "TypeScript",
            "stars_today": "98",
        },
    ]


def test_parse_github_trending_html_ignores_sponsor_links_before_repo_anchor():
    html = """
    <article class="Box-row">
      <a href="/sponsors/Zackriya-Solutions">Sponsor</a>
      <h2 class="h3 lh-condensed">
        <a href="/Zackriya-Solutions/meeting-minutes">Zackriya-Solutions / meeting-minutes</a>
      </h2>
      <p class="col-9 color-fg-muted my-1 pr-4">Self-hosted AI meeting notes.</p>
      <span itemprop="programmingLanguage">Rust</span>
      <span>1,781 stars today</span>
    </article>
    """

    rows = parse_github_trending_html(html, limit=1)

    assert rows[0]["repo"] == "Zackriya-Solutions/meeting-minutes"
    assert rows[0]["url"] == "https://github.com/Zackriya-Solutions/meeting-minutes"
    assert rows[0]["stars_today"] == "1781"


def test_github_trending_adapter_uses_injected_opener_without_credentials():
    calls = []

    def opener(request, timeout: int):
        calls.append({"url": request.full_url, "headers": dict(request.header_items()), "timeout": timeout})
        return _FakeResponse(SAMPLE_GITHUB_TRENDING_HTML)

    result = GitHubTrendingAdapter(opener=opener, timeout=7, evidence_path="evidence/github.json").fetch(limit=1)

    assert result.source == "github_trending"
    assert result.health_status == "success"
    assert result.raw_count == 1
    assert result.items[0]["repo"] == "openai/codex"
    assert result.items[0]["title"] == "openai/codex"
    assert result.items[0]["url"] == "https://github.com/openai/codex"
    assert result.items[0]["stars_today"] == "1234"
    assert result.evidence_path == "evidence/github.json"
    assert calls[0]["url"] == "https://github.com/trending?since=daily"
    assert calls[0]["timeout"] == 7
    assert calls[0]["headers"]["User-agent"] == "OpenClaw-IntelBrief/0.1"
