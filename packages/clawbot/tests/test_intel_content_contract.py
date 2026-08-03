from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.intel.content_contract import (
    ContentItem,
    canonicalize_url,
    normalize_source_batch,
    normalize_source_item,
    normalize_source_items,
    normalize_source_result,
    parse_content_datetime,
)
from src.intel.sources.base import IntelSourceResult

NOW = datetime(2026, 8, 4, 1, 0, tzinfo=timezone.utc)  # noqa: UP017


def test_canonicalize_url_removes_fragment_tracking_and_sorts_query():
    url = canonicalize_url("HTTPS://OpenAI.com/news/model/?utm_source=tg&b=2&a=1&fbclid=secret#section")

    assert url == "https://openai.com/news/model?a=1&b=2"
    assert canonicalize_url("javascript:alert(1)") == ""
    assert canonicalize_url("https://example.com:bad/path") == ""


def test_parse_content_datetime_supports_rfc822_and_source_dates():
    assert parse_content_datetime("Tue, 04 Aug 2026 01:00:00 GMT") == NOW
    assert parse_content_datetime("08/04/2026") == datetime(2026, 8, 4, tzinfo=timezone.utc)  # noqa: UP017


def test_normalize_senate_uses_disclosure_date_and_stable_audit_fields():
    item = normalize_source_item(
        "senate_trading",
        {
            "source": "senate-stock-watcher-data",
            "transaction_date": "11/10/2020",
            "disclosure_date": "11/16/2020",
            "person": "Ron L Wyden",
            "ticker": "BYND",
            "transaction_type": "Sale (Full)",
            "amount": "$50,001 - $100,000",
            "ptr_link": "https://example.com/ptr/1?utm_source=test",
        },
        fetched_at=NOW,
        evidence_path="evidence/senate.json",
    )

    assert item.source_name == "senate_trading"
    assert item.event_at == datetime(2020, 11, 16, tzinfo=timezone.utc)  # noqa: UP017
    assert item.date_confidence == "date_only"
    assert item.source_url == "https://example.com/ptr/1"
    assert item.payload["amount_upper_bound"] == 100000
    assert item.evidence_path == "evidence/senate.json"


def test_normalize_ai_without_publication_date_keeps_missing_confidence():
    item = normalize_source_item(
        "ai_model_updates",
        {
            "provider": "anthropic",
            "title": "Introducing Claude Opus 5",
            "url": "https://anthropic.com/news/opus-5?utm_medium=tg",
            "summary": "Model update.",
            "published_at": "",
        },
        fetched_at=NOW,
    )

    assert item.event_at is None
    assert item.date_confidence == "missing"
    assert item.source_url == "https://anthropic.com/news/opus-5"


def test_normalize_github_preserves_real_repository_and_url():
    item = normalize_source_item(
        "github_trending",
        {
            "repo": "openai/codex",
            "url": "https://github.com/openai/codex",
            "description": "Coding agent.",
            "stars_today": "1234",
        },
        fetched_at=NOW,
    )

    assert item.title == "openai/codex"
    assert item.source_url == "https://github.com/openai/codex"
    assert item.date_confidence == "observed"
    assert item.payload["repo"] == "openai/codex"


def test_normalize_13f_groups_holdings_by_accession():
    rows = normalize_source_items(
        "institutional_13f",
        [
            {
                "provider": "sec_edgar",
                "fund_name": "BERKSHIRE HATHAWAY INC",
                "cik": "0001067983",
                "accession_number": "0001193125-26-226661",
                "filing_date": "2026-05-15",
                "issuer": "APPLE INC",
            },
            {
                "provider": "sec_edgar",
                "fund_name": "BERKSHIRE HATHAWAY INC",
                "cik": "0001067983",
                "accession_number": "0001193125-26-226661",
                "filing_date": "2026-05-15",
                "issuer": "ALLY FINL INC",
            },
        ],
        fetched_at=NOW,
    )

    assert len(rows) == 1
    assert rows[0].source_item_id == "0001193125-26-226661"
    assert rows[0].title.endswith("（2 项持仓）")
    assert len(rows[0].payload["holdings"]) == 2
    assert rows[0].source_url.endswith("/1067983/000119312526226661")


def test_normalize_astock_requires_real_trade_date_instead_of_fetch_time():
    missing = normalize_source_item(
        "akshare",
        {"code": "000021", "name": "深科技", "reason": "机构买入"},
        fetched_at=NOW,
    )
    dated = normalize_source_item(
        "akshare",
        {"trade_date": "2026-08-04", "code": "000021", "name": "深科技", "reason": "机构买入"},
        fetched_at=NOW,
    )

    assert missing.event_at is None
    assert missing.date_confidence == "missing"
    assert dated.event_at == datetime(2026, 8, 4, tzinfo=timezone.utc)  # noqa: UP017


def test_payload_is_json_safe_and_bad_rows_are_isolated():
    result = normalize_source_batch(
        "github_trending",
        [
            {"repo": "", "url": "https://github.com/"},
            {
                "repo": "openai/codex",
                "url": "https://github.com/openai/codex",
                "observed_marker": NOW,
                "invalid_number": float("nan"),
            },
        ],
        fetched_at=NOW,
    )

    assert len(result.items) == 1
    assert len(result.rejected) == 1
    assert result.rejected[0].index == 0
    assert result.items[0].payload["observed_marker"] == NOW.isoformat()
    assert result.items[0].payload["invalid_number"] is None
    json.dumps(result.items[0].to_dict(), allow_nan=False)


def test_normalize_source_result_accepts_existing_adapter_contract():
    source_result = IntelSourceResult(
        source="github_trending",
        worker="overseas",
        fetched_at=NOW.isoformat(),
        items=[{"repo": "openai/codex", "url": "https://github.com/openai/codex"}],
        raw_count=1,
        health_status="success",
        evidence_path="evidence/github.json",
    )

    result = normalize_source_result(source_result)

    assert len(result.items) == 1
    assert result.items[0].title == "openai/codex"
    assert result.items[0].evidence_path == "evidence/github.json"


def test_non_mapping_rows_are_rejected_with_original_index():
    result = normalize_source_batch(
        "github_trending",
        [None, {"repo": "openai/codex", "url": "https://github.com/openai/codex"}],
        fetched_at=NOW,
    )

    assert len(result.items) == 1
    assert result.rejected[0].index == 0
    assert result.rejected[0].reason == "TypeError:source_row_must_be_mapping"


def test_content_item_rejects_naive_dates_and_missing_required_taxonomy():
    common = {
        "source_name": "ai_model_updates",
        "content_kind": "model_update",
        "source_item_id": "item-1",
        "event_key": "event-1",
        "entity_key": "entity-1",
        "category": "ai",
        "provider": "openai",
        "title": "Model update",
        "summary": "Summary",
        "source_url": "https://openai.com/news/model",
        "published_at": None,
        "observed_at": NOW,
        "date_confidence": "exact",
    }

    with pytest.raises(ValueError, match="event_at_must_be_timezone_aware"):
        ContentItem(event_at=datetime(2026, 8, 4), **common)

    with pytest.raises(ValueError, match="missing_required_field"):
        ContentItem(event_at=NOW, **{**common, "category": ""})
