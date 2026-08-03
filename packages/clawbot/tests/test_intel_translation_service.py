from __future__ import annotations

import json
import sqlite3

import pytest


class JsonTranslationProvider:
    provider_name = "test-json-provider"
    provider_version = "v1"

    def __init__(self):
        self.calls = 0

    def translate(self, text: str, *, source_language: str, target_language: str) -> str:
        self.calls += 1
        payload = json.loads(text)
        prefix = "EN: " if target_language == "en" else "中文："
        return json.dumps({"texts": [prefix + value for value in payload["texts"]]}, ensure_ascii=False)


def test_localize_brief_payload_batches_fields_and_persists_cache(tmp_path):
    from src.intel.translation_service import localize_brief_payload

    db_path = tmp_path / "intel.db"
    provider = JsonTranslationProvider()
    payload = {
        "llm": {"summary_text": "今日重点是深科技（000021）。"},
        "items": [
            {
                "title": "深科技（000021）获机构净买入",
                "summary": "成交占比 46.03%，金额 $50,001。",
                "source_label": "A股龙虎榜",
                "source_url": "https://example.com/item?utm_source=tg",
                "payload": {"code": "000021"},
            }
        ],
    }

    first, evidence = localize_brief_payload(
        payload,
        target_language="en",
        db_path=db_path,
        provider=provider,
    )
    second, second_evidence = localize_brief_payload(
        payload,
        target_language="en",
        db_path=db_path,
        provider=provider,
    )

    assert evidence["status"] == "translated"
    assert second_evidence["status"] == "translated"
    assert provider.calls == 1
    assert first == second
    assert first["items"][0]["title"].startswith("EN: ")
    assert "000021" in first["items"][0]["title"]
    assert "46.03%" in first["items"][0]["summary"]
    assert "$50,001" in first["items"][0]["summary"]
    assert first["items"][0]["source_url"] == payload["items"][0]["source_url"]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM content_translation_cache").fetchone()[0] == 1


def test_cc_switch_provider_loads_three_https_endpoints_without_exposing_keys(tmp_path):
    from src.intel.translation_service import CCSwitchTranslationProvider

    db_path = tmp_path / "cc-switch.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE providers (
                id TEXT, app_type TEXT, name TEXT, settings_config TEXT,
                is_current INTEGER, sort_index INTEGER
            )
            """
        )
        for index in range(4):
            settings = {
                "auth": {"OPENAI_API_KEY": f"test-secret-{index}"},
                "config": (
                    'model_provider = "custom"\nmodel = "gpt-test"\n'
                    '[model_providers.custom]\nbase_url = "https://provider.example/v1"\nwire_api = "responses"\n'
                ),
            }
            conn.execute(
                "INSERT INTO providers VALUES (?, 'codex', 'OpenAI', ?, ?, ?)",
                (str(index), json.dumps(settings), 1 if index == 0 else 0, index),
            )
        conn.commit()

    provider = CCSwitchTranslationProvider(db_path=db_path)

    assert provider.ready is True
    assert len(provider._endpoints) == 3
    assert "test-secret" not in repr(provider)
    assert "test-secret" not in repr(provider._endpoints)


def test_cc_switch_failover_uses_one_total_deadline(monkeypatch):
    from src.intel import translation_service
    from src.intel.translation_service import CCSwitchTranslationProvider

    provider = object.__new__(CCSwitchTranslationProvider)
    provider.timeout = 10
    provider._endpoints = (object(), object(), object())
    monotonic_values = iter((100.0, 100.0, 106.0, 112.0))
    requested_timeouts = []

    def request(endpoint, text, target_language, *, timeout):
        requested_timeouts.append(timeout)
        raise TimeoutError("simulated timeout")

    provider._request = request
    monkeypatch.setattr(translation_service.time, "monotonic", lambda: next(monotonic_values))

    with pytest.raises(RuntimeError, match="translation_request_failed:TimeoutError"):
        provider.translate("hello", source_language="en", target_language="zh")

    assert requested_timeouts == [10.0, 4.0]


def test_cc_switch_rejects_oversized_translation_response(monkeypatch):
    from src.intel.translation_service import (
        MAX_TRANSLATION_RESPONSE_BYTES,
        CCSwitchTranslationProvider,
        _CCSwitchEndpoint,
    )

    class OversizedResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size):
            assert size == MAX_TRANSLATION_RESPONSE_BYTES + 1
            return b"x" * size

    monkeypatch.setattr(
        "src.intel.translation_service.urllib.request.urlopen", lambda request, timeout: OversizedResponse()
    )
    provider = object.__new__(CCSwitchTranslationProvider)
    endpoint = _CCSwitchEndpoint(
        base_url="https://provider.example/v1",
        api_key="test-only-key",
        model="gpt-test",
        wire_api="responses",
    )

    with pytest.raises(RuntimeError, match="translation_response_too_large"):
        provider._request(endpoint, "hello", "zh", timeout=1)
