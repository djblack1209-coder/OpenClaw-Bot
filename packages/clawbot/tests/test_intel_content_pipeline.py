from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.intel.content_contract import ContentItem, normalize_source_item
from src.intel.content_pipeline import ContentPipeline, SelectionPolicy, select_brief_items

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)  # noqa: UP017


def _item(
    identity: str,
    *,
    source: str,
    category: str,
    age_hours: int,
    score_payload: dict | None = None,
) -> ContentItem:
    event_at = NOW - timedelta(hours=age_hours)
    return ContentItem(
        source_name=source,
        content_kind="test_update",
        source_item_id=identity,
        event_key=f"{source}:{identity}",
        entity_key=f"entity:{identity}",
        category=category,
        provider=source,
        title=f"Signal {identity}",
        summary="Auditable source summary",
        source_url=f"https://example.com/{identity}",
        event_at=event_at,
        published_at=event_at,
        observed_at=NOW,
        date_confidence="exact",
        payload=score_payload or {},
    )


def test_pipeline_rejects_2020_bynd_and_missing_or_old_ai_updates():
    bynd = normalize_source_item(
        "senate_trading",
        {
            "person": "Ron L Wyden",
            "ticker": "BYND",
            "transaction_type": "Sale (Full)",
            "amount": "$50,001 - $100,000",
            "transaction_date": "11/10/2020",
            "disclosure_date": "11/16/2020",
            "ptr_link": "https://example.com/ptr/bynd",
        },
        fetched_at=NOW,
    )
    missing_ai = normalize_source_item(
        "ai_model_updates",
        {"provider": "anthropic", "title": "Introducing Claude Opus 5", "url": "https://example.com/opus-5"},
        fetched_at=NOW,
    )
    old_ai = normalize_source_item(
        "ai_model_updates",
        {
            "provider": "openai",
            "title": "Old model update",
            "url": "https://example.com/old-model",
            "published_at": "2026-07-01",
        },
        fetched_at=NOW,
    )

    result = select_brief_items([bynd, missing_ai, old_ai], now=NOW)

    assert result.selected == ()
    assert {entry.reason for entry in result.rejected} == {"stale_event", "missing_event_date"}
    assert next(entry for entry in result.rejected if entry.item is bynd).reason == "stale_event"


def test_pipeline_deduplicates_current_and_previous_deliveries():
    first = _item("same", source="ai_model_updates", category="ai", age_hours=1)
    duplicate = _item("same", source="ai_model_updates", category="ai", age_hours=1)

    current = select_brief_items([first, duplicate], now=NOW)
    previous = select_brief_items([first], now=NOW, seen_event_keys=[first.event_key])

    assert len(current.selected) == 1
    assert [entry.reason for entry in current.rejected] == ["duplicate_in_run"]
    assert previous.selected == ()
    assert [entry.reason for entry in previous.rejected] == ["already_delivered"]


def test_same_event_is_delivered_at_most_once_across_three_runs():
    item = _item("three-runs", source="ai_model_updates", category="ai", age_hours=1)
    delivered: set[str] = set()
    delivery_count = 0

    for _ in range(3):
        result = select_brief_items([item], now=NOW, seen_event_keys=delivered)
        delivery_count += len(result.selected)
        delivered.update(entry.item.event_key for entry in result.selected)

    assert delivery_count == 1


def test_github_repository_has_seven_day_entity_cooldown():
    github = _item(
        "github-new-day",
        source="github_trending",
        category="technology",
        age_hours=1,
        score_payload={"stars_today": "1500"},
    )
    recent = {github.entity_key: NOW - timedelta(days=2)}

    blocked = select_brief_items([github], now=NOW, recent_entity_observations=recent)
    allowed = select_brief_items(
        [github],
        now=NOW,
        recent_entity_observations={github.entity_key: NOW - timedelta(days=8)},
    )

    assert blocked.selected == ()
    assert blocked.rejected[0].reason == "entity_cooldown"
    assert len(allowed.selected) == 1


def test_top_three_are_category_diverse_and_source_quota_is_enforced():
    items = [
        _item("market-1", source="senate_trading", category="market", age_hours=1),
        _item("market-2", source="senate_trading", category="market", age_hours=2),
        _item("market-3", source="senate_trading", category="market", age_hours=3),
        _item("ai-1", source="ai_model_updates", category="ai", age_hours=5),
        _item(
            "tech-1",
            source="github_trending",
            category="technology",
            age_hours=5,
            score_payload={"stars_today": "1200"},
        ),
    ]
    policy = SelectionPolicy(brief_limit=5, source_limit=2, category_limit=3, diverse_top_count=3)

    result = ContentPipeline(policy).process(items, now=NOW)

    assert {entry.item.category for entry in result.selected[:3]} == {"market", "ai", "technology"}
    assert len({entry.item.category for entry in result.selected[:3]}) == 3
    assert sum(entry.item.source_name == "senate_trading" for entry in result.selected) == 2
    assert any(entry.reason == "source_quota" for entry in result.excluded)


def test_ranking_is_deterministic_and_tracking_match_is_explainable():
    tracked = _item("tracked", source="ai_model_updates", category="ai", age_hours=2)
    plain = _item("plain", source="ai_model_updates", category="ai", age_hours=2)

    first = select_brief_items([plain, tracked], now=NOW, tracked_terms=["tracked"])
    second = select_brief_items([tracked, plain], now=NOW, tracked_terms=["tracked"])

    assert [entry.item.event_key for entry in first.selected] == [entry.item.event_key for entry in second.selected]
    assert first.selected[0].item is tracked
    assert first.selected[0].score_breakdown["tracking_match"] == 15.0
    assert sum(first.selected[0].score_breakdown.values()) == pytest.approx(first.selected[0].score)


def test_baseline_only_source_is_recordable_but_not_selected():
    github = _item("baseline", source="github_trending", category="technology", age_hours=1)

    result = ContentPipeline().process([github], now=NOW, baseline_only_sources=["github_trending"])

    assert result.selected == ()
    assert result.rejected[0].reason == "baseline_only"
