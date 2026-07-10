"""Official AI model update sources for Intel Brief."""

from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from src.intel.runtime_policy import resolve_runtime_policy
from src.intel.sources.base import IntelSourceResult

OPENAI_NEWS_RSS_URL = "https://openai.com/news/rss.xml"
ANTHROPIC_NEWS_URL = "https://www.anthropic.com/news"
DEEPSEEK_NEWS_URL = "https://www.deepseek.com/"


@dataclass(frozen=True)
class FeedSpec:
    """One official AI update endpoint."""

    provider: str
    kind: str
    url: str


DEFAULT_AI_MODEL_UPDATE_FEEDS = (
    FeedSpec(provider="openai", kind="rss", url=OPENAI_NEWS_RSS_URL),
    FeedSpec(provider="anthropic", kind="anthropic_html", url=ANTHROPIC_NEWS_URL),
    FeedSpec(provider="deepseek", kind="deepseek_html", url=DEEPSEEK_NEWS_URL),
)


def _space(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def _local_name(tag: str) -> str:
    return str(tag or "").rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(node):
        if _local_name(child.tag) in wanted:
            return _space("".join(child.itertext()))
    return ""


def _atom_link(node: ET.Element) -> str:
    for child in list(node):
        if _local_name(child.tag) == "link":
            href = _space(child.attrib.get("href"))
            if href:
                return href
            text = _space("".join(child.itertext()))
            if text:
                return text
    return ""


def parse_rss_xml(payload: bytes | str, *, provider: str, limit: int = 20) -> list[dict[str, str]]:
    """Parse RSS or Atom XML into normalized AI update rows."""
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
    root = ET.fromstring(text)
    rows: list[dict[str, str]] = []
    for node in root.iter():
        name = _local_name(node.tag)
        if name not in {"item", "entry"}:
            continue
        title = _child_text(node, "title")
        url = _child_text(node, "link") if name == "item" else _atom_link(node)
        published = _child_text(node, "pubDate", "published", "updated", "date")
        summary = _child_text(node, "description", "summary", "content")
        if not title or not url:
            continue
        rows.append(
            {
                "source": "official_rss",
                "provider": _space(provider).lower(),
                "title": title,
                "url": url,
                "published_at": published,
                "summary": summary,
            }
        )
        if len(rows) >= max(0, int(limit)):
            break
    return rows


class _OfficialNewsLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._tag_stack: list[str] = []
        self._capture_tag = ""
        self._capture_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "a":
            self._current = {"href": attr.get("href", ""), "text_parts": [], "headings": [], "paragraphs": [], "time": ""}
            self._tag_stack = ["a"]
        elif self._current is not None:
            self._tag_stack.append(tag)

        if self._current is None:
            return
        if tag in {"h1", "h2", "h3", "h4", "p", "time"}:
            self._capture_tag = tag
            self._capture_buffer = []
            if tag == "time" and attr.get("datetime"):
                self._current["time"] = attr["datetime"]

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        self._current["text_parts"].append(data)
        if self._capture_tag:
            self._capture_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if self._capture_tag == tag:
            text = _space(" ".join(self._capture_buffer))
            if text:
                if tag.startswith("h"):
                    self._current["headings"].append(text)
                elif tag == "p":
                    self._current["paragraphs"].append(text)
                elif tag == "time" and not self._current.get("time"):
                    self._current["time"] = text
            self._capture_tag = ""
            self._capture_buffer = []

        if self._tag_stack:
            self._tag_stack.pop()
        if tag == "a" or not self._tag_stack:
            self._current["text"] = _space(" ".join(self._current.get("text_parts", [])))
            self.links.append(self._current)
            self._current = None
            self._tag_stack = []
            self._capture_tag = ""
            self._capture_buffer = []


def _absolute_url(base: str, href: str) -> str:
    href = _space(href)
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return base.rstrip("/") + href
    return href


def parse_anthropic_news_html(payload: bytes | str, *, limit: int = 20) -> list[dict[str, str]]:
    """Parse Anthropic's official news page."""
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
    parser = _OfficialNewsLinkParser()
    parser.feed(text)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in parser.links:
        href = _space(link.get("href"))
        if not href.startswith("/news/"):
            continue
        url = _absolute_url("https://www.anthropic.com", href)
        if url in seen:
            continue
        title = _space((link.get("headings") or [""])[0]) or _space(link.get("text"))
        summary = _space((link.get("paragraphs") or [""])[0])
        if not title:
            continue
        seen.add(url)
        rows.append(
            {
                "source": "official_html",
                "provider": "anthropic",
                "title": title,
                "url": url,
                "published_at": _space(link.get("time")),
                "summary": summary,
            }
        )
        if len(rows) >= max(0, int(limit)):
            break
    return rows


def _deepseek_title_and_summary(text: str) -> tuple[str, str]:
    cleaned = _space(re.sub(r"^[🎉\\s]+", "", text))
    parts = re.split(r"[，,。]", cleaned, maxsplit=1)
    title = _space(parts[0])
    summary = _space(parts[1]) if len(parts) > 1 else ""
    return title, summary


def parse_deepseek_news_html(payload: bytes | str, *, limit: int = 20) -> list[dict[str, str]]:
    """Parse DeepSeek's official news page."""
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
    parser = _OfficialNewsLinkParser()
    parser.feed(text)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in parser.links:
        link_text = _space(link.get("text"))
        href = _space(link.get("href"))
        if not any(marker in href for marker in ("mp.weixin.qq.com", "/news/")):
            continue
        if "deepseek" not in link_text.lower() or not any(token in link_text for token in ("发布", "上线", "模型")):
            continue
        title, summary = _deepseek_title_and_summary(link_text)
        url = _absolute_url("https://www.deepseek.com", href)
        key = f"{title}|{url}"
        if not title or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source": "official_html",
                "provider": "deepseek",
                "title": title,
                "url": url,
                "published_at": _space(link.get("time")),
                "summary": summary,
            }
        )
        if len(rows) >= max(0, int(limit)):
            break
    return rows


def _fetch_text(url: str, *, timeout: int, opener=None) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "OpenClaw-IntelBrief/0.1",
            "Accept": "application/rss+xml,application/atom+xml,text/xml,text/html,*/*;q=0.8",
        },
    )
    open_fn = opener or urllib.request.urlopen
    with open_fn(request, timeout=timeout) as response:
        return response.read()


def fetch_ai_model_updates(
    *,
    feeds: tuple[FeedSpec, ...] = DEFAULT_AI_MODEL_UPDATE_FEEDS,
    limit: int = 20,
    timeout: int = 20,
    opener=None,
) -> list[dict[str, str]]:
    """Fetch official OpenAI/Anthropic/DeepSeek update rows."""
    rows_by_feed: list[list[dict[str, str]]] = []
    errors: list[str] = []
    per_feed_limit = max(1, int(limit))
    for feed in feeds:
        try:
            payload = _fetch_text(feed.url, timeout=timeout, opener=opener)
            if feed.kind == "rss":
                parsed = parse_rss_xml(payload, provider=feed.provider, limit=per_feed_limit)
            elif feed.kind == "anthropic_html":
                parsed = parse_anthropic_news_html(payload, limit=per_feed_limit)
            elif feed.kind == "deepseek_html":
                parsed = parse_deepseek_news_html(payload, limit=per_feed_limit)
            else:
                parsed = []
            rows_by_feed.append(parsed)
        except Exception as exc:  # keep other official sources alive
            rows_by_feed.append([])
            errors.append(f"{feed.provider}:{exc}")
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    max_rows = max((len(rows) for rows in rows_by_feed), default=0)
    for index in range(max_rows):
        for rows in rows_by_feed:
            if index >= len(rows):
                continue
            row = rows[index]
            key = f"{row.get('provider')}|{row.get('url')}|{row.get('title')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
            if len(deduped) >= max(0, int(limit)):
                break
        if len(deduped) >= max(0, int(limit)):
            break
    if not deduped and errors:
        raise RuntimeError("; ".join(errors)[:500])
    return deduped


class AIModelUpdatesAdapter:
    """Official OpenAI/Anthropic/DeepSeek update adapter."""

    source_name = "ai_model_updates"

    def __init__(
        self,
        *,
        feeds: tuple[FeedSpec, ...] = DEFAULT_AI_MODEL_UPDATE_FEEDS,
        timeout: int = 20,
        opener=None,
        evidence_path: str = "",
    ) -> None:
        self.feeds = feeds
        self.timeout = timeout
        self.opener = opener
        self.evidence_path = evidence_path

    def fetch(self, *, limit: int = 20) -> IntelSourceResult:
        items = fetch_ai_model_updates(
            feeds=self.feeds,
            limit=limit,
            timeout=self.timeout,
            opener=self.opener,
        )
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
