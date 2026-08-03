"""把 CC Switch 第三方模型池接入每日资讯双语投递。"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import tomllib
import urllib.error
import urllib.request
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.intel.db.store import get_translation_cache, put_translation_cache
from src.intel.localization import (
    TranslationProvider,
    build_translation_cache_key,
    localize_text,
    normalize_content_language,
)

_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
MAX_TRANSLATION_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class _CCSwitchEndpoint:
    """仅驻留内存的 CC Switch 提供器配置。"""

    base_url: str
    api_key: str = field(repr=False)
    model: str
    wire_api: str


def _extract_response_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    output = payload.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
        if chunks:
            return "\n".join(chunks)
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return str(message["content"]).strip()
    return ""


class CCSwitchTranslationProvider:
    """按 CC Switch 当前优先级调用最多三个 OpenAI 兼容第三方端点。"""

    provider_name = "cc-switch-3p-pool"
    provider_version = "responses-translate-v1"

    def __init__(self, *, db_path: str | Path | None = None, timeout: int = 45) -> None:
        configured = os.environ.get("CC_SWITCH_DB_PATH")
        self.db_path = Path(db_path or configured or (Path.home() / ".cc-switch" / "cc-switch.db"))
        self.timeout = max(5, int(timeout))
        self._endpoints = self._load_endpoints()

    @property
    def ready(self) -> bool:
        """至少存在一个 HTTPS 第三方端点时可执行真实翻译。"""
        return bool(self._endpoints)

    def _load_endpoints(self) -> tuple[_CCSwitchEndpoint, ...]:
        if not self.db_path.is_file():
            return ()
        endpoints: list[_CCSwitchEndpoint] = []
        try:
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as conn:
                rows = conn.execute(
                    """
                    SELECT settings_config
                    FROM providers
                    WHERE app_type='codex' AND name='OpenAI'
                    ORDER BY is_current DESC, sort_index ASC
                    """
                ).fetchall()
        except (sqlite3.Error, OSError):
            return ()
        for (raw_settings,) in rows:
            try:
                settings = json.loads(str(raw_settings))
                auth = settings.get("auth") if isinstance(settings.get("auth"), dict) else {}
                api_key = str(auth.get("OPENAI_API_KEY") or "").strip()
                config = tomllib.loads(str(settings.get("config") or ""))
                provider_name = str(config.get("model_provider") or "custom")
                model_providers = config.get("model_providers")
                provider_config = (
                    model_providers.get(provider_name, {})
                    if isinstance(model_providers, dict) and isinstance(model_providers.get(provider_name), dict)
                    else {}
                )
                base_url = str(provider_config.get("base_url") or config.get("base_url") or "").strip().rstrip("/")
                model = str(config.get("model") or "").strip()
                wire_api = str(provider_config.get("wire_api") or "responses").strip().lower()
                parts = urlsplit(base_url)
                if not api_key or not model or parts.scheme != "https" or not parts.hostname:
                    continue
                endpoints.append(
                    _CCSwitchEndpoint(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        wire_api=wire_api,
                    )
                )
            except (json.JSONDecodeError, tomllib.TOMLDecodeError, TypeError, ValueError):
                continue
            if len(endpoints) == 3:
                break
        return tuple(endpoints)

    def _request(
        self,
        endpoint: _CCSwitchEndpoint,
        text: str,
        target_language: str,
        *,
        timeout: float,
    ) -> str:
        target_name = "Simplified Chinese" if target_language == "zh" else "English"
        system = (
            f"Translate the input into {target_name}. Preserve every placeholder like "
            "[[OC_ENTITY_0000]] exactly once. When the input is JSON, preserve its keys, array length "
            "and valid JSON syntax. Return only the translated text or JSON, without Markdown fences."
        )
        if endpoint.wire_api == "responses":
            url = f"{endpoint.base_url}/responses"
            payload = {
                "model": endpoint.model,
                "instructions": system,
                "input": text,
                "temperature": 0.1,
                "max_output_tokens": min(4000, max(512, len(text) * 2)),
            }
        else:
            url = f"{endpoint.base_url}/chat/completions"
            payload = {
                "model": endpoint.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.1,
                "max_tokens": min(4000, max(512, len(text) * 2)),
            }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {endpoint.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=max(1.0, timeout)) as response:
            raw_body = response.read(MAX_TRANSLATION_RESPONSE_BYTES + 1)
        if len(raw_body) > MAX_TRANSLATION_RESPONSE_BYTES:
            raise RuntimeError("translation_response_too_large")
        body = json.loads(raw_body.decode("utf-8", errors="replace"))
        translated = _extract_response_text(body)
        if not translated:
            raise RuntimeError("empty_translation_response")
        return translated

    def translate(self, text: str, *, source_language: str, target_language: str) -> str:
        """依次尝试三个第三方端点，错误只暴露稳定类型。"""
        if not self._endpoints:
            raise RuntimeError("cc_switch_provider_unavailable")
        last_error = "translation_request_failed"
        deadline = time.monotonic() + self.timeout
        for endpoint in self._endpoints:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_error = "translation_request_failed:TimeoutError"
                break
            try:
                return self._request(endpoint, text, target_language, timeout=remaining)
            except (
                OSError,
                TimeoutError,
                urllib.error.URLError,
                urllib.error.HTTPError,
                ValueError,
                RuntimeError,
            ) as exc:
                last_error = f"translation_request_failed:{exc.__class__.__name__}"
        raise RuntimeError(last_error)


def _detect_language(text: str) -> str:
    return "zh" if _CJK_PATTERN.search(str(text or "")) else "en"


def _strip_json_fence(value: str) -> str:
    cleaned = str(value or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _translate_group(
    texts: list[str],
    *,
    source_language: str,
    target_language: str,
    provider: TranslationProvider | None,
    db_path: str | Path,
    protected_entities: tuple[str, ...],
) -> tuple[list[str], str, str]:
    if not texts:
        return [], "source", ""
    source_json = json.dumps({"texts": texts}, ensure_ascii=False, separators=(",", ":"))
    provider_name = str(getattr(provider, "provider_name", "none") if provider else "none")
    provider_version = str(getattr(provider, "provider_version", "none") if provider else "none")
    cache_key = build_translation_cache_key(
        source_json,
        source_language=source_language,
        target_language=target_language,
        provider_name=provider_name,
        provider_version=provider_version,
    )
    cached = get_translation_cache(db_path, cache_key)
    memory_cache = {cache_key: str(cached.get("translated_text"))} if cached else {}
    result = localize_text(
        source_json,
        source_language=source_language,
        target_language=target_language,
        provider=provider,
        cache=memory_cache,
        protected_entities=protected_entities,
    )
    try:
        decoded = json.loads(_strip_json_fence(result.text))
        translated = decoded.get("texts") if isinstance(decoded, dict) else None
        if (
            not isinstance(translated, list)
            or len(translated) != len(texts)
            or not all(isinstance(item, str) for item in translated)
        ):
            raise ValueError("translated_json_shape_mismatch")
    except (json.JSONDecodeError, ValueError, TypeError):
        return texts, "source_fallback", "translation_json_mismatch"
    if result.status in {"translated", "cache_hit"}:
        put_translation_cache(
            db_path,
            cache_key=cache_key,
            source_language=source_language,
            target_language=target_language,
            translator_version=f"{provider_name}:{provider_version}",
            status=result.status,
            source_text=source_json,
            translated_text=result.text,
        )
    return [str(item) for item in translated], result.status, result.error


def localize_brief_payload(
    payload: dict[str, Any],
    *,
    target_language: str,
    db_path: str | Path,
    provider: TranslationProvider | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """按字段语言批量翻译完整简报，每种源语言最多调用一次模型。"""
    target = normalize_content_language(target_language)
    copied = deepcopy(payload)
    fields: list[tuple[dict[str, Any], str, str]] = []
    llm = copied.get("llm") if isinstance(copied.get("llm"), dict) else {}
    if isinstance(llm.get("summary_text"), str) and llm["summary_text"].strip():
        fields.append((llm, "summary_text", llm["summary_text"]))
    items = copied.get("items") if isinstance(copied.get("items"), list) else []
    protected: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("ticker", "code", "repo", "model", "provider"):
            value = item.get(key) or (item.get("payload", {}).get(key) if isinstance(item.get("payload"), dict) else "")
            if isinstance(value, str) and value.strip():
                protected.add(value.strip())
        for key in ("title", "summary", "source_label"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                fields.append((item, key, value))

    statuses: list[str] = []
    errors: list[str] = []
    translated_count = 0
    for source in ("zh", "en"):
        selected = [(container, key, text) for container, key, text in fields if _detect_language(text) == source]
        if source == target or not selected:
            statuses.extend("source" for _ in selected)
            continue
        translated, status, error = _translate_group(
            [text for _, _, text in selected],
            source_language=source,
            target_language=target,
            provider=provider,
            db_path=db_path,
            protected_entities=tuple(sorted(protected)),
        )
        for (container, key, _), value in zip(selected, translated, strict=True):
            container[key] = value
        statuses.append(status)
        if status in {"translated", "cache_hit"}:
            translated_count += len(selected)
        if error:
            errors.append(error)

    fallback = any(status == "source_fallback" for status in statuses)
    copied["content_language"] = target
    copied["localization"] = {
        "status": "partial_source_fallback" if fallback else ("translated" if translated_count else "source"),
        "target_language": target,
        "translated_field_count": translated_count,
        "source_fallback": fallback,
        "provider": str(getattr(provider, "provider_name", "none") if provider else "none"),
    }
    return copied, {
        "status": copied["localization"]["status"],
        "target_language": target,
        "translated_field_count": translated_count,
        "source_fallback": fallback,
        "errors": sorted(set(errors)),
    }
