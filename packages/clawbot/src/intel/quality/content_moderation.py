"""Intel Brief 内容合规过滤层。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FILTER_PLACEHOLDER = "该条内容已过滤"

SENSITIVE_KEYWORDS = (
    "政治人物",
    "政治事件",
    "政治敏感",
    "地缘冲突",
    "军事冲突",
    "群体事件",
    "颜色革命",
    "台海",
    "六四",
    "法轮功",
    "习近平",
)

Classifier = Callable[[str, list[str]], bool | str | dict[str, Any]]


@dataclass(frozen=True)
class ModerationResult:
    """单条内容过滤结果。"""

    allowed: bool
    status: str
    output_text: str
    matched_keywords: list[str]
    reason: str
    classifier_label: str | None = None
    confidence: float | None = None


def _matched_keywords(text: str) -> list[str]:
    """返回命中的敏感关键词。"""
    source = str(text or "")
    return [kw for kw in SENSITIVE_KEYWORDS if kw and kw in source]


def _interpret_classifier_result(value: bool | str | dict[str, Any]) -> tuple[bool, str | None, float | None]:
    """把 LLM/规则分类器结果归一化为是否敏感。"""
    if isinstance(value, bool):
        return value, "sensitive" if value else "not_sensitive", None
    if isinstance(value, str):
        lowered = value.strip().lower()
        sensitive = lowered in {"sensitive", "political_sensitive", "yes", "true", "1"}
        return sensitive, value.strip() or None, None
    sensitive = bool(value.get("sensitive", value.get("is_sensitive", False)))
    label = value.get("label") or value.get("category") or ("sensitive" if sensitive else "not_sensitive")
    confidence_raw = value.get("confidence")
    confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else None
    return sensitive, str(label), confidence


def _content_hash(text: str) -> str:
    """生成内容哈希，日志不保存正文。"""
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _write_moderation_log(
    db_path: str | Path,
    source: str,
    content_id: str | None,
    original_text: str,
    result: ModerationResult,
) -> None:
    """写入过滤日志，不保存正文和敏感账号信息。"""
    from src.intel.db.store import initialize_intel_db

    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO content_moderation_log
                (source, content_id, content_hash, status, matched_keywords, classifier_label, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                content_id,
                _content_hash(original_text),
                result.status,
                json.dumps(result.matched_keywords, ensure_ascii=False),
                result.classifier_label,
                result.reason,
            ),
        )
        conn.commit()


def moderate_content(
    text: str,
    source: str,
    classifier: Classifier | None = None,
    db_path: str | Path | None = None,
    content_id: str | None = None,
) -> ModerationResult:
    """过滤单条待推送内容。

    过滤发生在推送前，不阻断抓取；命中关键词且无分类器时默认待复核并替换占位。
    """
    original = str(text or "")
    keywords = _matched_keywords(original)
    if not keywords:
        result = ModerationResult(
            allowed=True,
            status="allowed",
            output_text=original,
            matched_keywords=[],
            reason="no_keyword_hit",
        )
        return result

    if classifier is None:
        result = ModerationResult(
            allowed=False,
            status="needs_review",
            output_text=FILTER_PLACEHOLDER,
            matched_keywords=keywords,
            reason="keyword_prefilter",
        )
    else:
        sensitive, label, confidence = _interpret_classifier_result(classifier(original, keywords))
        if sensitive:
            result = ModerationResult(
                allowed=False,
                status="filtered",
                output_text=FILTER_PLACEHOLDER,
                matched_keywords=keywords,
                reason="classifier_sensitive",
                classifier_label=label,
                confidence=confidence,
            )
        else:
            result = ModerationResult(
                allowed=True,
                status="allowed_after_review",
                output_text=original,
                matched_keywords=keywords,
                reason="classifier_not_sensitive",
                classifier_label=label,
                confidence=confidence,
            )

    if db_path is not None:
        _write_moderation_log(db_path, source, content_id, original, result)
    return result


def moderate_items(
    items: list[dict[str, Any]],
    text_key: str = "title",
    source_key: str = "source",
    classifier: Classifier | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """批量过滤抓取结果，返回不修改原对象的新列表。"""
    moderated: list[dict[str, Any]] = []
    for item in items:
        copied = dict(item)
        text = str(copied.get(text_key, "") or "")
        source = str(copied.get(source_key, "unknown") or "unknown")
        content_id = str(copied.get("id") or copied.get("url") or "") or None
        result = moderate_content(
            text,
            source=source,
            classifier=classifier,
            db_path=db_path,
            content_id=content_id,
        )
        copied[text_key] = result.output_text
        copied["moderation_status"] = result.status
        copied["moderation_reason"] = result.reason
        copied["moderation_matched_keywords"] = result.matched_keywords
        moderated.append(copied)
    return moderated


def build_llm_moderation_prompt(text: str, matched_keywords: list[str]) -> str:
    """生成给现有 LLM 路由使用的二次判断提示词。"""
    keywords = "、".join(matched_keywords)
    return (
        "你是内容合规分类器，只输出 JSON。判断待推送内容是否涉及政治敏感内容。"
        "如果涉及政治人物、政治事件、国家安全、军事冲突或可能引发国内合规风险，"
        "输出 {\"sensitive\": true, \"label\": \"political_sensitive\", \"confidence\": 0.0-1.0}；"
        "否则输出 {\"sensitive\": false, \"label\": \"not_sensitive\", \"confidence\": 0.0-1.0}。"
        f"\n命中关键词：{keywords}\n待判断内容：{text[:1200]}"
    )
