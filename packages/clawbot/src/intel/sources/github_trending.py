"""GitHub Trending source adapter for Intel Brief."""

from __future__ import annotations

import html
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

from src.intel.runtime_policy import resolve_runtime_policy
from src.intel.sources.base import IntelSourceResult

GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"


class _TrendingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self._in_article = False
        self._article_depth = 0
        self._current: dict[str, str] = {}
        self._capture = ""
        self._buffer: list[str] = []
        self._in_repo_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        class_text = attr.get("class", "")
        if tag == "article" and "Box-row" in class_text:
            self._in_article = True
            self._article_depth = 1
            self._current = {}
            self._capture = ""
            self._buffer = []
            self._in_repo_heading = False
            return
        if not self._in_article:
            return
        self._article_depth += 1
        if tag == "h2":
            self._in_repo_heading = True
        if tag == "a" and self._in_repo_heading and not self._current.get("repo") and attr.get("href", "").count("/") >= 2:
            href = attr.get("href", "")
            parts = [part for part in href.strip("/").split("/") if part]
            if len(parts) == 2:
                repo = "/".join(parts)
                self._current["repo"] = repo
                self._current["url"] = "https://github.com/" + repo
                self._capture = "repo"
                self._buffer = []
        elif tag == "p" and "col-9" in class_text:
            self._capture = "description"
            self._buffer = []
        elif tag == "span" and attr.get("itemprop") == "programmingLanguage":
            self._capture = "language"
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if not self._in_article:
            return
        if self._capture:
            self._buffer.append(data)
        # The "stars today" text is outside a stable semantic tag, so collect
        # all article text as a fallback for trend count extraction.
        self._current["_article_text"] = (self._current.get("_article_text", "") + " " + data).strip()

    def handle_endtag(self, tag: str) -> None:
        if not self._in_article:
            return
        if self._capture and ((self._capture == "repo" and tag == "a") or (self._capture == "description" and tag == "p") or (self._capture == "language" and tag == "span")):
            text = _space(" ".join(self._buffer))
            if self._capture == "description":
                self._current["description"] = text
            elif self._capture == "language":
                self._current["language"] = text
            self._capture = ""
            self._buffer = []
        if tag == "h2":
            self._in_repo_heading = False
        self._article_depth -= 1
        if tag == "article" or self._article_depth <= 0:
            item = _finalize_item(self._current)
            if item:
                self.items.append(item)
            self._in_article = False
            self._article_depth = 0
            self._current = {}
            self._capture = ""
            self._buffer = []
            self._in_repo_heading = False


def _space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def _finalize_item(raw: dict[str, str]) -> dict[str, str]:
    repo = _space(raw.get("repo", ""))
    if not repo or "/" not in repo:
        return {}
    article_text = _space(raw.get("_article_text", ""))
    stars_today = ""
    match = re.search(r"([0-9][0-9,]*)\s+stars?\s+today", article_text, flags=re.IGNORECASE)
    if match:
        stars_today = match.group(1).replace(",", "")
    return {
        "source": "github_trending_daily",
        "repo": repo,
        "url": raw.get("url", "https://github.com/" + repo),
        "description": _space(raw.get("description", "")),
        "language": _space(raw.get("language", "")),
        "stars_today": stars_today,
    }


def parse_github_trending_html(payload: bytes | str, *, limit: int = 20) -> list[dict[str, str]]:
    """Parse GitHub Trending HTML into normalized repository rows."""
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
    parser = _TrendingParser()
    parser.feed(text)
    return parser.items[: max(0, int(limit))]


def fetch_github_trending(
    *,
    url: str = GITHUB_TRENDING_URL,
    limit: int = 20,
    timeout: int = 20,
    opener=None,
) -> list[dict[str, str]]:
    """Fetch daily GitHub Trending without API credentials."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "OpenClaw-IntelBrief/0.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    open_fn = opener or urllib.request.urlopen
    with open_fn(request, timeout=timeout) as response:
        payload = response.read()
    return parse_github_trending_html(payload, limit=limit)


class GitHubTrendingAdapter:
    """GitHub daily trending repository adapter."""

    source_name = "github_trending"

    def __init__(
        self,
        *,
        url: str = GITHUB_TRENDING_URL,
        timeout: int = 20,
        opener=None,
        evidence_path: str = "",
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.opener = opener
        self.evidence_path = evidence_path

    def fetch(self, *, limit: int = 20) -> IntelSourceResult:
        items = fetch_github_trending(url=self.url, limit=limit, timeout=self.timeout, opener=self.opener)
        policy = resolve_runtime_policy(self.source_name)
        return IntelSourceResult(
            source=self.source_name,
            worker=policy.preferred_worker,
            fetched_at=datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Python 3.10 worker compatibility
            items=items,
            raw_count=len(items),
            health_status="success",
            evidence_path=self.evidence_path,
        )
