from __future__ import annotations

from src.intel.localization import (
    build_translation_cache_key,
    localize_text,
    mask_translation_entities,
    normalize_content_language,
    parse_content_language,
)


class _TranslationProvider:
    provider_name = "test-provider"
    provider_version = "2026-08-04"

    def __init__(self, *, break_placeholder: bool = False, fail: bool = False) -> None:
        self.break_placeholder = break_placeholder
        self.fail = fail
        self.calls = 0

    def translate(self, text: str, *, source_language: str, target_language: str) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError("private provider details")
        translated = f"English summary: {text}"
        return translated.replace("[[OC_ENTITY_0000]]", "missing") if self.break_placeholder else translated


def test_language_parser_accepts_user_aliases_and_rejects_unknown_values():
    assert normalize_content_language("中文") == "zh"
    assert normalize_content_language("ENGLISH") == "en"
    assert normalize_content_language("unknown") == "zh"
    assert parse_content_language("简体中文") == "zh"
    assert parse_content_language("英文") == "en"
    assert parse_content_language("fr") is None


def test_localization_masks_and_restores_market_entities_without_changing_them():
    source = (
        "2026-08-04 深科技（000021）上涨 46.03%，Claude Opus 5 关注 $BYND，"
        "金额 $50,001，来源 https://example.com/a?utm=1。"
    )
    masked = mask_translation_entities(source, protected_entities=("深科技",))
    provider = _TranslationProvider()

    result = localize_text(
        source,
        source_language="zh",
        target_language="en",
        provider=provider,
        protected_entities=("深科技",),
    )

    assert masked.entities
    assert result.status == "translated"
    assert result.text.startswith("English summary:")
    for entity in (
        "2026-08-04",
        "深科技",
        "000021",
        "46.03%",
        "Claude Opus 5",
        "$BYND",
        "$50,001",
        "https://example.com/a?utm=1",
    ):
        assert entity in result.text
    assert "[[OC_ENTITY_" not in result.text
    assert provider.calls == 1


def test_localization_cache_key_is_stable_and_skips_duplicate_provider_calls():
    provider = _TranslationProvider()
    cache: dict[str, str] = {}

    first = localize_text("今日重点", source_language="zh", target_language="en", provider=provider, cache=cache)
    second = localize_text("今日重点", source_language="zh", target_language="en", provider=provider, cache=cache)

    assert first.status == "translated"
    assert second.status == "cache_hit"
    assert second.text == first.text
    assert second.cache_key == first.cache_key
    assert provider.calls == 1
    assert first.cache_key in cache


def test_cache_key_changes_when_translation_contract_changes():
    common = {
        "text": "今日重点",
        "source_language": "zh",
        "target_language": "en",
        "provider_name": "provider",
        "provider_version": "1",
    }
    first = build_translation_cache_key(**common)
    second = build_translation_cache_key(**{**common, "provider_version": "2"})
    third = build_translation_cache_key(**{**common, "target_language": "zh"})

    assert first.startswith("intel-translation:")
    assert len({first, second, third}) == 3


def test_placeholder_damage_falls_back_to_source_text():
    source = "Open https://example.com and review $BYND."
    provider = _TranslationProvider(break_placeholder=True)

    result = localize_text(source, source_language="en", target_language="zh", provider=provider)

    assert result.status == "source_fallback"
    assert result.text == source
    assert result.error == "translation_placeholder_mismatch"


def test_provider_failure_uses_source_fallback_without_leaking_error_message():
    source = "Ten advances in mathematics"
    provider = _TranslationProvider(fail=True)

    result = localize_text(source, source_language="en", target_language="zh", provider=provider)

    assert result.status == "source_fallback"
    assert result.text == source
    assert result.error == "translation_provider_error:RuntimeError"
    assert "private provider details" not in str(result.as_dict())


def test_same_language_and_missing_provider_are_explicit_states():
    same = localize_text("今日重点", source_language="zh", target_language="zh")
    unavailable = localize_text("Today", source_language="en", target_language="zh")

    assert same.status == "source"
    assert same.text == "今日重点"
    assert unavailable.status == "source_fallback"
    assert unavailable.error == "translation_provider_unavailable"
