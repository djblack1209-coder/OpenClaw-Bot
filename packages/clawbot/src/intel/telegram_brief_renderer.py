"""把结构化 Intel Brief 渲染为 Telegram Top 3 富媒体信封。"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from src.constants import TG_SAFE_LENGTH

DEFAULT_COVER_PATH = Path(__file__).resolve().parents[2] / "assets" / "intel" / "openclaw-intel-brief-dark.jpg"
_LANGUAGES = {"zh", "en"}


@dataclass(frozen=True)
class DeliveryEnvelope:
    """与 Telegram 传输实现解耦的完整投递契约。"""

    brief_ref: str
    language: str
    cover_path: str
    caption_html: str
    full_text_html: str
    reply_markup: dict[str, Any]
    item_event_keys: list[str] = field(default_factory=list)
    category_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回可持久化 JSON 字典。"""
        return asdict(self)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _escape(value: Any) -> str:
    return html.escape(_clean(value), quote=True)


def _clip_sentence(value: Any, limit: int) -> str:
    """优先在句号或空格处收束，避免把英文单词截成两半。"""
    text = _clean(value)
    if len(text) <= limit:
        return text
    window = text[: max(1, limit - 1)]
    boundaries = [window.rfind(mark) for mark in ("。", "！", "？", ". ", "; ", "；", " ")]
    boundary = max(boundaries)
    if boundary >= int(limit * 0.58):
        window = window[: boundary + (1 if window[boundary : boundary + 1] in "。！？；" else 0)]
    return window.rstrip(" ,，;；:.。") + "…"


def _language_copy(language: str) -> dict[str, str]:
    if language == "en":
        return {
            "title": "Daily Intelligence Brief",
            "signals": "SIGNALS",
            "sources": "SOURCES CHECKED",
            "top": "TOP 3",
            "all": "View all",
            "market": "Markets",
            "ai": "AI",
            "language": "中文",
            "source": "Source",
            "empty": "No fresh, verifiable signals matched your subscriptions today.",
            "disclaimer": "Public-source aggregation; not investment advice.",
            "fresh": "Freshness and duplicate checks passed",
        }
    return {
        "title": "今日情报简报",
        "signals": "条信号",
        "sources": "个来源已核验",
        "top": "今日 Top 3",
        "all": "查看全部",
        "market": "市场",
        "ai": "AI",
        "language": "English",
        "source": "来源",
        "empty": "今天没有匹配订阅且通过时效核验的新情报。",
        "disclaimer": "内容来自公开来源自动汇总，不构成投资建议。",
        "fresh": "时效与跨日去重已核验",
    }


def _event_key(item: dict[str, Any], index: int) -> str:
    explicit = _clean(item.get("event_key") or item.get("stable_key") or item.get("source_item_id"))
    if explicit:
        return explicit
    identity = "\0".join(
        _clean(item.get(key)) for key in ("source", "source_name", "source_url", "url", "title", "published_at")
    )
    if identity.strip("\0"):
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"item-{index}"


def event_key_for_item(item: dict[str, Any], index: int = 0) -> str:
    """公开稳定事件键算法，供渲染与跨日投递去重共同使用。"""
    return _event_key(item, index)


def _category(item: dict[str, Any]) -> str:
    return _clean(item.get("category") or item.get("source_label") or item.get("source")) or "其他"


def _source_link(item: dict[str, Any], copy: dict[str, str]) -> str:
    url = _clean(item.get("source_url") or item.get("url"))
    source = _escape(item.get("provider") or item.get("source_label") or item.get("source") or copy["source"])
    if not url.startswith(("https://", "http://")):
        return source
    return f'<a href="{html.escape(url, quote=True)}">{source}</a>'


def _published_label(item: dict[str, Any]) -> str:
    value = _clean(item.get("published_at") or item.get("event_at") or item.get("observed_at"))
    if not value:
        return ""
    return value[:16].replace("T", " ")


def _render_top_item(item: dict[str, Any], index: int, copy: dict[str, str]) -> str:
    category = _escape(_category(item))
    title = _escape(item.get("title") or "Untitled signal")
    summary = _escape(_clip_sentence(item.get("summary") or item.get("description"), 240))
    metadata = " · ".join(value for value in (_published_label(item), _source_link(item, copy)) if value)
    lines = [f"<b>{index:02d}  {category}</b>", f"<b>{title}</b>"]
    if summary:
        lines.append(summary)
    if metadata:
        lines.append(f"<i>{metadata}</i>")
    return "\n".join(lines)


def _render_full_item(item: dict[str, Any], index: int, copy: dict[str, str]) -> str:
    category = _escape(_category(item))
    title = _escape(item.get("title") or "Untitled signal")
    summary = _escape(_clip_sentence(item.get("summary") or item.get("description"), 360))
    metadata = " · ".join(value for value in (_published_label(item), _source_link(item, copy)) if value)
    body = f"<b>{index}. [{category}] {title}</b>"
    if summary:
        body += f"\n{summary}"
    if metadata:
        body += f"\n<i>{metadata}</i>"
    return body


def _trim_html_message(value: str, max_chars: int) -> str:
    """在 Telegram 安全长度内按条目边界收束正文。"""
    if len(value) <= max_chars:
        return value
    blocks = value.split("\n\n")
    kept: list[str] = []
    for block in blocks:
        candidate = "\n\n".join([*kept, block])
        if len(candidate) > max_chars - 40:
            break
        kept.append(block)
    return "\n\n".join(kept) + "\n\n<i>内容较长，请按分类查看其余条目。</i>"


def build_brief_envelope(
    payload: dict[str, Any],
    *,
    brief_ref: str,
    language: str = "zh",
    cover_path: str | Path | None = None,
    max_chars: int = TG_SAFE_LENGTH,
) -> DeliveryEnvelope:
    """构建深色视觉封面、Top 3 首屏和可展开按钮。"""
    normalized_language = language if language in _LANGUAGES else "zh"
    copy = _language_copy(normalized_language)
    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []
    items = [item for item in raw_items if isinstance(item, dict)]
    has_pipeline_rank = any(int(item.get("rank_position") or 0) > 0 for item in items)
    if has_pipeline_rank:
        items.sort(
            key=lambda item: (
                int(item.get("rank_position") or 1_000_000),
                -float(item.get("rank_score", item.get("score", 0)) or 0),
                _event_key(item, 0),
            )
        )
    else:
        items.sort(key=lambda item: (-float(item.get("rank_score", item.get("score", 0)) or 0), _event_key(item, 0)))
    source_count = len(
        {
            _clean(item.get("source") or item.get("source_name") or item.get("provider"))
            for item in items
            if _clean(item.get("source") or item.get("source_name") or item.get("provider"))
        }
    )
    category_counts: dict[str, int] = {}
    for item in items:
        label = _category(item)
        category_counts[label] = category_counts.get(label, 0) + 1

    brief_date = _clean(payload.get("brief_date") or payload.get("date") or date.today().isoformat())
    if normalized_language == "en":
        status_line = f"{source_count} {copy['sources']} · {len(items)} {copy['signals']}"
    else:
        status_line = f"{source_count} {copy['sources']} · {len(items)} {copy['signals']}"
    header = (
        f"<b>{copy['title']}</b>\n<code>{_escape(brief_date)} · {_escape(status_line)}</code>\n<i>{copy['fresh']}</i>"
    )
    llm_payload = payload.get("llm") if isinstance(payload.get("llm"), dict) else {}
    overview = _escape(_clip_sentence(llm_payload.get("summary_text"), 280))
    localization = payload.get("localization") if isinstance(payload.get("localization"), dict) else {}
    fallback_notice = ""
    if localization.get("source_fallback"):
        fallback_notice = (
            "Some content remains in its source language." if normalized_language == "en" else "部分内容保留来源语言。"
        )
    top_blocks = [_render_top_item(item, index, copy) for index, item in enumerate(items[:3], 1)]
    lead_blocks = [header, overview] if overview else [header]
    caption_blocks = [*lead_blocks, *top_blocks]
    if fallback_notice:
        caption_blocks.append(f"<i>{fallback_notice}</i>")
    caption = "\n\n".join(caption_blocks) if top_blocks else f"{header}\n\n{copy['empty']}"
    caption = _trim_html_message(caption, 980)

    full_blocks = [_render_full_item(item, index, copy) for index, item in enumerate(items, 1)]
    footer_blocks = [f"<i>{copy['disclaimer']}</i>"]
    if fallback_notice:
        footer_blocks.insert(0, f"<i>{fallback_notice}</i>")
    full_text = "\n\n".join([*lead_blocks, *full_blocks, *footer_blocks])
    full_text = _trim_html_message(full_text, max_chars)
    ref = re.sub(r"[^a-zA-Z0-9_-]", "", brief_ref)[:20]
    keyboard = {
        "inline_keyboard": [
            [
                {"text": copy["market"], "callback_data": f"ib1:v:market:{ref}"},
                {"text": copy["ai"], "callback_data": f"ib1:v:ai:{ref}"},
            ],
            [
                {"text": copy["all"], "callback_data": f"ib1:v:all:{ref}"},
                {
                    "text": copy["language"],
                    "callback_data": f"ib1:l:{'en' if normalized_language == 'zh' else 'zh'}:{ref}",
                },
            ],
        ]
    }
    chosen_cover = Path(cover_path) if cover_path is not None else DEFAULT_COVER_PATH
    return DeliveryEnvelope(
        brief_ref=ref,
        language=normalized_language,
        cover_path=str(chosen_cover) if chosen_cover.is_file() else "",
        caption_html=caption,
        full_text_html=full_text,
        reply_markup=keyboard,
        item_event_keys=[_event_key(item, index) for index, item in enumerate(items, 1)],
        category_counts=category_counts,
    )
