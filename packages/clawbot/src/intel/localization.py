"""每日资讯本地化纯逻辑。

本模块不读取密钥、不调用具体模型，也不写数据库。调用方注入翻译提供器和缓存后，
即可获得带实体保护、缓存键和可审计降级状态的翻译结果。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

DEFAULT_CONTENT_LANGUAGE = "zh"
SUPPORTED_CONTENT_LANGUAGES = frozenset({"zh", "en"})
TRANSLATION_PROMPT_VERSION = "intel-brief-translation-v1"
ENTITY_MASK_VERSION = "intel-brief-entity-mask-v1"

_LANGUAGE_ALIASES = {
    "zh": "zh",
    "zh-cn": "zh",
    "cn": "zh",
    "chinese": "zh",
    "中文": "zh",
    "简体中文": "zh",
    "en": "en",
    "en-us": "en",
    "english": "en",
    "英文": "en",
    "英语": "en",
}

_PROTECTED_PATTERNS = (
    re.compile(r"https?://[^\s<>()\[\]{}]+", re.IGNORECASE),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<!\w)[$€£¥￥]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|万|亿))?", re.IGNORECASE),
    re.compile(r"(?<!\w)\d+(?:\.\d+)?%(?!\w)"),
    re.compile(r"(?<!\w)\$[A-Z][A-Z0-9.-]{0,11}(?!\w)"),
    re.compile(r"(?<!\d)(?:\d{6}|\d{3,5}\.(?:HK|SS|SZ))(?!\w)", re.IGNORECASE),
    re.compile(r"(?<!\d)\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?(?!\d)"),
    re.compile(
        r"\b(?:GPT|Claude|Gemini|Qwen|DeepSeek|Llama|Fable|Opus|Sonnet|Haiku)"
        r"(?:[-\s][A-Za-z0-9][A-Za-z0-9.+-]*){0,2}\b",
        re.IGNORECASE,
    ),
)
_PLACEHOLDER_PATTERN = re.compile(r"\[\[OC_ENTITY_(\d{4})\]\]")


@runtime_checkable
class TranslationProvider(Protocol):
    """调用方注入的翻译提供器最小接口。"""

    provider_name: str
    provider_version: str

    def translate(self, text: str, *, source_language: str, target_language: str) -> str:
        """翻译文本并原样保留实体占位符。"""


@dataclass(frozen=True)
class MaskedTranslationText:
    """被实体占位符保护的文本。"""

    text: str
    entities: tuple[str, ...]


@dataclass(frozen=True)
class TranslationResult:
    """可直接写入审计或缓存的翻译结果。"""

    text: str
    status: str
    source_language: str
    target_language: str
    cache_key: str
    provider_name: str
    provider_version: str
    protected_entity_count: int
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化且不包含密钥的结果。"""
        return {
            "text": self.text,
            "status": self.status,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "cache_key": self.cache_key,
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "protected_entity_count": self.protected_entity_count,
            "error": self.error,
        }


def normalize_content_language(value: Any, *, default: str = DEFAULT_CONTENT_LANGUAGE) -> str:
    """把用户输入统一为 zh/en，不支持的值回落到指定默认语言。"""
    cleaned = str(value or "").strip().lower().replace("_", "-")
    fallback = _LANGUAGE_ALIASES.get(str(default or "").strip().lower(), DEFAULT_CONTENT_LANGUAGE)
    return _LANGUAGE_ALIASES.get(cleaned, fallback)


def parse_content_language(value: Any) -> str | None:
    """严格解析用户语言选择，不支持的值返回 None。"""
    cleaned = str(value or "").strip().lower().replace("_", "-")
    return _LANGUAGE_ALIASES.get(cleaned)


def _provider_identity(provider: TranslationProvider | None) -> tuple[str, str]:
    if provider is None:
        return "none", "none"
    name = str(getattr(provider, "provider_name", "") or provider.__class__.__name__).strip()
    version = str(getattr(provider, "provider_version", "") or "1").strip()
    return name or "injected", version or "1"


def build_translation_cache_key(
    text: str,
    *,
    source_language: str,
    target_language: str,
    provider_name: str,
    provider_version: str,
    prompt_version: str = TRANSLATION_PROMPT_VERSION,
    entity_mask_version: str = ENTITY_MASK_VERSION,
) -> str:
    """生成跨进程稳定、包含翻译规则版本的缓存键。"""
    payload = {
        "entity_mask_version": entity_mask_version,
        "prompt_version": prompt_version,
        "provider_name": str(provider_name or "none"),
        "provider_version": str(provider_version or "none"),
        "source_language": normalize_content_language(source_language),
        "target_language": normalize_content_language(target_language),
        "text": str(text or ""),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"intel-translation:{digest}"


def _protected_spans(text: str, protected_entities: tuple[str, ...]) -> list[tuple[int, int]]:
    candidates: set[tuple[int, int]] = set()
    for pattern in _PROTECTED_PATTERNS:
        for match in pattern.finditer(text):
            end = match.end()
            if pattern is _PROTECTED_PATTERNS[0]:
                while end > match.start() and text[end - 1] in ".,;:!?，。；：！？":
                    end -= 1
            if end > match.start():
                candidates.add((match.start(), end))
    for entity in protected_entities:
        if not entity:
            continue
        start = 0
        while (index := text.find(entity, start)) >= 0:
            candidates.add((index, index + len(entity)))
            start = index + len(entity)

    selected: list[tuple[int, int]] = []
    cursor = 0
    for start, end in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
        if start < cursor:
            continue
        selected.append((start, end))
        cursor = end
    return selected


def mask_translation_entities(text: str, *, protected_entities: tuple[str, ...] = ()) -> MaskedTranslationText:
    """遮罩 URL、代码、金额、日期、模型名及调用方指定实体。"""
    source = str(text or "")
    spans = _protected_spans(source, tuple(str(item) for item in protected_entities if str(item)))
    if not spans:
        return MaskedTranslationText(text=source, entities=())
    chunks: list[str] = []
    entities: list[str] = []
    cursor = 0
    for index, (start, end) in enumerate(spans):
        chunks.append(source[cursor:start])
        chunks.append(f"[[OC_ENTITY_{index:04d}]]")
        entities.append(source[start:end])
        cursor = end
    chunks.append(source[cursor:])
    return MaskedTranslationText(text="".join(chunks), entities=tuple(entities))


def restore_translation_entities(text: str, entities: tuple[str, ...]) -> str | None:
    """校验并恢复占位符；缺失、重复或新增占位符都拒绝采用翻译。"""
    translated = str(text or "")
    expected = [f"[[OC_ENTITY_{index:04d}]]" for index in range(len(entities))]
    actual = [match.group(0) for match in _PLACEHOLDER_PATTERN.finditer(translated)]
    if len(actual) != len(expected) or sorted(actual) != sorted(expected):
        return None
    restored = translated
    for placeholder, entity in zip(expected, entities, strict=True):
        restored = restored.replace(placeholder, entity, 1)
    return restored


def _cache_get(cache: MutableMapping[str, str] | Any | None, key: str) -> str | None:
    if cache is None:
        return None
    try:
        value = cache.get(key)
    except Exception:
        return None
    return value if isinstance(value, str) else None


def _cache_set(cache: MutableMapping[str, str] | Any | None, key: str, value: str) -> None:
    if cache is None:
        return
    try:
        if hasattr(cache, "set"):
            cache.set(key, value)
        else:
            cache[key] = value
    except Exception:
        return


def localize_text(
    text: str,
    *,
    source_language: str,
    target_language: str,
    provider: TranslationProvider | None = None,
    cache: MutableMapping[str, str] | Any | None = None,
    protected_entities: tuple[str, ...] = (),
) -> TranslationResult:
    """翻译一段文本；提供器异常或占位符损坏时原文降级。"""
    source_text = str(text or "")
    source = normalize_content_language(source_language)
    target = normalize_content_language(target_language)
    provider_name, provider_version = _provider_identity(provider)
    cache_key = build_translation_cache_key(
        source_text,
        source_language=source,
        target_language=target,
        provider_name=provider_name,
        provider_version=provider_version,
    )
    masked = mask_translation_entities(source_text, protected_entities=protected_entities)

    if not source_text or source == target:
        return TranslationResult(
            text=source_text,
            status="source",
            source_language=source,
            target_language=target,
            cache_key=cache_key,
            provider_name=provider_name,
            provider_version=provider_version,
            protected_entity_count=len(masked.entities),
        )

    cached = _cache_get(cache, cache_key)
    if cached is not None:
        return TranslationResult(
            text=cached,
            status="cache_hit",
            source_language=source,
            target_language=target,
            cache_key=cache_key,
            provider_name=provider_name,
            provider_version=provider_version,
            protected_entity_count=len(masked.entities),
        )

    if provider is None:
        return TranslationResult(
            text=source_text,
            status="source_fallback",
            source_language=source,
            target_language=target,
            cache_key=cache_key,
            provider_name=provider_name,
            provider_version=provider_version,
            protected_entity_count=len(masked.entities),
            error="translation_provider_unavailable",
        )

    try:
        translated = provider.translate(
            masked.text,
            source_language=source,
            target_language=target,
        )
    except Exception as exc:
        return TranslationResult(
            text=source_text,
            status="source_fallback",
            source_language=source,
            target_language=target,
            cache_key=cache_key,
            provider_name=provider_name,
            provider_version=provider_version,
            protected_entity_count=len(masked.entities),
            error=f"translation_provider_error:{exc.__class__.__name__}",
        )
    if not isinstance(translated, str) or not translated.strip():
        return TranslationResult(
            text=source_text,
            status="source_fallback",
            source_language=source,
            target_language=target,
            cache_key=cache_key,
            provider_name=provider_name,
            provider_version=provider_version,
            protected_entity_count=len(masked.entities),
            error="translation_provider_empty_result",
        )
    restored = restore_translation_entities(translated, masked.entities)
    if restored is None:
        return TranslationResult(
            text=source_text,
            status="source_fallback",
            source_language=source,
            target_language=target,
            cache_key=cache_key,
            provider_name=provider_name,
            provider_version=provider_version,
            protected_entity_count=len(masked.entities),
            error="translation_placeholder_mismatch",
        )
    _cache_set(cache, cache_key, restored)
    return TranslationResult(
        text=restored,
        status="translated",
        source_language=source,
        target_language=target,
        cache_key=cache_key,
        provider_name=provider_name,
        provider_version=provider_version,
        protected_entity_count=len(masked.entities),
    )
