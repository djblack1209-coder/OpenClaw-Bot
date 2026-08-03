"""每日资讯 V2 的时效、去重、评分与配额管道。"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from src.intel.content_contract import ContentItem, clean_text, parse_content_datetime

DEFAULT_MAX_AGE_DAYS = {
    "senate_trading": 14,
    "akshare": 3,
    "github_trending": 1,
    "ai_model_updates": 7,
    "institutional_13f": 120,
    "weather": 1,
}
DEFAULT_SOURCE_VALUE = {
    "senate_trading": 18,
    "akshare": 17,
    "github_trending": 16,
    "ai_model_updates": 20,
    "institutional_13f": 20,
    "weather": 16,
}
DEFAULT_ENTITY_COOLDOWN_DAYS = {
    "github_trending": 7,
}


@dataclass(frozen=True)
class SelectionPolicy:
    """简报候选筛选与配额配置。"""

    brief_limit: int = 8
    source_limit: int = 2
    category_limit: int = 3
    diverse_top_count: int = 3
    future_tolerance_hours: int = 24
    max_age_days: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_MAX_AGE_DAYS))
    source_value: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_SOURCE_VALUE))
    entity_cooldown_days: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_ENTITY_COOLDOWN_DAYS))

    def __post_init__(self) -> None:
        """拒绝无效配额，防止配置把选择器变成无限或空循环。"""
        for value in (self.brief_limit, self.source_limit, self.category_limit, self.diverse_top_count):
            if int(value) < 0:
                raise ValueError("selection_policy_negative_limit")


@dataclass(frozen=True)
class ScoredContentItem:
    """带可解释分数的一条候选内容。"""

    item: ContentItem
    score: float
    score_breakdown: Mapping[str, float]
    score_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """生成包含审计分解的可持久化结果。"""
        return {
            **self.item.to_dict(),
            "score": self.score,
            "score_breakdown": dict(self.score_breakdown),
            "score_reasons": list(self.score_reasons),
        }


@dataclass(frozen=True)
class RejectedContentItem:
    """记录被过滤内容及机器可读原因。"""

    item: ContentItem
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class PipelineResult:
    """一次确定性管道运行的完整选择证据。"""

    selected: tuple[ScoredContentItem, ...]
    eligible: tuple[ScoredContentItem, ...]
    rejected: tuple[RejectedContentItem, ...]
    excluded: tuple[RejectedContentItem, ...]

    @property
    def counts(self) -> dict[str, int]:
        """汇总各阶段数量，供健康检查与运行证据使用。"""
        return {
            "selected": len(self.selected),
            "eligible": len(self.eligible),
            "rejected": len(self.rejected),
            "excluded": len(self.excluded),
        }


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 兼容
    return value.astimezone(timezone.utc)  # noqa: UP017 - Python 3.10 兼容


def _parse_recent_entities(values: Mapping[str, Any]) -> dict[str, datetime]:
    parsed: dict[str, datetime] = {}
    for entity_key, delivered_at in values.items():
        timestamp = parse_content_datetime(delivered_at)
        if timestamp is not None:
            parsed[clean_text(entity_key)] = timestamp
    return parsed


def _numeric(value: Any) -> int:
    match = re.search(r"\d[\d,]*", clean_text(value))
    if not match:
        return 0
    try:
        return int(match.group(0).replace(",", ""))
    except ValueError:
        return 0


def _strength_score(item: ContentItem) -> float:
    payload = item.payload
    if item.source_name == "github_trending":
        stars = _numeric(payload.get("stars_today"))
        if stars >= 1000:
            return 15.0
        if stars >= 500:
            return 12.0
        if stars >= 100:
            return 9.0
        if stars >= 10:
            return 6.0
        return 3.0
    if item.source_name == "senate_trading":
        amount = int(payload.get("amount_upper_bound") or 0)
        if amount >= 1_000_000:
            return 15.0
        if amount >= 100_000:
            return 12.0
        if amount >= 50_000:
            return 9.0
        return 6.0
    if item.source_name == "akshare":
        reason = clean_text(payload.get("reason"))
        strong_markers = ("机构", "净买入", "涨停", "主力", "buy", "inflow")
        return 12.0 if any(marker.casefold() in reason.casefold() for marker in strong_markers) else 8.0
    if item.source_name == "institutional_13f":
        holding_count = len(payload.get("holdings") or []) if isinstance(payload.get("holdings"), list) else 0
        return min(15.0, 10.0 + math.log2(max(1, holding_count)))
    if item.source_name == "ai_model_updates":
        return 12.0
    if item.source_name == "weather":
        return 10.0
    return 8.0


def _tracking_score(item: ContentItem, tracked_terms: tuple[str, ...]) -> float:
    searchable = " ".join((item.title, item.summary, item.entity_key)).casefold()
    return 15.0 if any(term.casefold() in searchable for term in tracked_terms) else 0.0


def _score_item(
    item: ContentItem,
    *,
    age: timedelta,
    max_age_days: int,
    source_value: int,
    tracked_terms: tuple[str, ...],
    is_novel_entity: bool,
) -> ScoredContentItem:
    age_days = max(0.0, age.total_seconds() / 86400)
    freshness = max(0.0, 40.0 * (1.0 - age_days / max(1, max_age_days)))
    source = max(0.0, min(20.0, float(source_value)))
    strength = max(0.0, min(15.0, _strength_score(item)))
    tracking = _tracking_score(item, tracked_terms)
    novelty = 10.0 if is_novel_entity else 0.0
    breakdown = {
        "freshness": round(freshness, 2),
        "source_value": round(source, 2),
        "signal_strength": round(strength, 2),
        "tracking_match": round(tracking, 2),
        "novelty": round(novelty, 2),
    }
    score = round(sum(breakdown.values()), 2)
    reasons = tuple(f"{name}={value:g}" for name, value in breakdown.items())
    return ScoredContentItem(item=item, score=score, score_breakdown=breakdown, score_reasons=reasons)


def _candidate_sort_key(candidate: ScoredContentItem) -> tuple[Any, ...]:
    event_at = candidate.item.freshness_at or datetime.min.replace(tzinfo=timezone.utc)  # noqa: UP017
    return (
        -candidate.score,
        -_aware_utc(event_at).timestamp(),
        candidate.item.source_name,
        candidate.item.event_key,
    )


class ContentPipeline:
    """执行时效过滤、跨批次去重、确定性评分和来源配额。"""

    def __init__(self, policy: SelectionPolicy | None = None) -> None:
        self.policy = policy or SelectionPolicy()

    def process(
        self,
        items: Iterable[ContentItem],
        *,
        now: datetime | None = None,
        seen_event_keys: Iterable[str] = (),
        recent_entity_observations: Mapping[str, Any] | None = None,
        tracked_terms: Iterable[str] = (),
        baseline_only_sources: Iterable[str] = (),
    ) -> PipelineResult:
        """筛选候选并返回全部入选、拒绝和配额证据。"""
        current_time = _aware_utc(now or datetime.now(timezone.utc))  # noqa: UP017 - Python 3.10 兼容
        seen_events = {clean_text(key) for key in seen_event_keys if clean_text(key)}
        recent_entities = _parse_recent_entities(recent_entity_observations or {})
        normalized_terms = tuple(
            sorted({clean_text(term) for term in tracked_terms if len(clean_text(term)) >= 2}, key=str.casefold)
        )
        baseline_sources = {clean_text(source) for source in baseline_only_sources if clean_text(source)}
        rejected: list[RejectedContentItem] = []
        candidates: list[ScoredContentItem] = []
        current_events: set[str] = set()

        ordered_items = sorted(
            items,
            key=lambda item: (item.event_key, item.source_name, item.source_item_id, item.title.casefold()),
        )
        for item in ordered_items:
            if item.event_key in current_events:
                rejected.append(RejectedContentItem(item=item, reason="duplicate_in_run"))
                continue
            current_events.add(item.event_key)
            if item.event_key in seen_events:
                rejected.append(RejectedContentItem(item=item, reason="already_delivered"))
                continue
            if item.source_name in baseline_sources:
                rejected.append(RejectedContentItem(item=item, reason="baseline_only"))
                continue
            event_at = item.freshness_at
            if event_at is None or item.date_confidence == "missing":
                rejected.append(RejectedContentItem(item=item, reason="missing_event_date"))
                continue
            event_at = _aware_utc(event_at)
            if event_at > current_time + timedelta(hours=self.policy.future_tolerance_hours):
                rejected.append(RejectedContentItem(item=item, reason="future_event_date"))
                continue
            max_age_days = max(1, int(self.policy.max_age_days.get(item.source_name, 7)))
            age = current_time - event_at
            if age > timedelta(days=max_age_days):
                rejected.append(
                    RejectedContentItem(
                        item=item,
                        reason="stale_event",
                        detail=f"age_days={age.total_seconds() / 86400:.2f};max_age_days={max_age_days}",
                    )
                )
                continue
            recent_entity_at = recent_entities.get(item.entity_key)
            cooldown_days = max(0, int(self.policy.entity_cooldown_days.get(item.source_name, 0)))
            if (
                recent_entity_at is not None
                and cooldown_days
                and current_time - recent_entity_at < timedelta(days=cooldown_days)
            ):
                rejected.append(
                    RejectedContentItem(
                        item=item,
                        reason="entity_cooldown",
                        detail=f"cooldown_days={cooldown_days}",
                    )
                )
                continue
            candidates.append(
                _score_item(
                    item,
                    age=age,
                    max_age_days=max_age_days,
                    source_value=int(self.policy.source_value.get(item.source_name, 10)),
                    tracked_terms=normalized_terms,
                    is_novel_entity=recent_entity_at is None,
                )
            )

        eligible = sorted(candidates, key=_candidate_sort_key)
        selected, excluded = self._apply_quotas(eligible)
        return PipelineResult(
            selected=tuple(selected),
            eligible=tuple(eligible),
            rejected=tuple(rejected),
            excluded=tuple(excluded),
        )

    def _apply_quotas(
        self, candidates: list[ScoredContentItem]
    ) -> tuple[list[ScoredContentItem], list[RejectedContentItem]]:
        """优先保证 Top 3 类别多样性，再按总分填充剩余名额。"""
        selected: list[ScoredContentItem] = []
        excluded: list[RejectedContentItem] = []
        selected_keys: set[str] = set()
        source_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        diverse_categories: set[str] = set()

        def can_select(candidate: ScoredContentItem) -> str:
            if len(selected) >= self.policy.brief_limit:
                return "brief_limit"
            source_count = source_counts.get(candidate.item.source_name, 0)
            if source_count >= self.policy.source_limit:
                return "source_quota"
            category_count = category_counts.get(candidate.item.category, 0)
            if category_count >= self.policy.category_limit:
                return "category_quota"
            return ""

        def append_candidate(candidate: ScoredContentItem) -> None:
            selected.append(candidate)
            selected_keys.add(candidate.item.event_key)
            source_counts[candidate.item.source_name] = source_counts.get(candidate.item.source_name, 0) + 1
            category_counts[candidate.item.category] = category_counts.get(candidate.item.category, 0) + 1
            diverse_categories.add(candidate.item.category)

        for candidate in candidates:
            if len(diverse_categories) >= min(self.policy.diverse_top_count, self.policy.brief_limit):
                break
            if candidate.item.category in diverse_categories:
                continue
            if not can_select(candidate):
                append_candidate(candidate)

        for candidate in candidates:
            if candidate.item.event_key in selected_keys:
                continue
            reason = can_select(candidate)
            if reason:
                excluded.append(RejectedContentItem(item=candidate.item, reason=reason))
                continue
            append_candidate(candidate)

        return selected, excluded


def select_brief_items(
    items: Iterable[ContentItem],
    *,
    now: datetime | None = None,
    seen_event_keys: Iterable[str] = (),
    recent_entity_observations: Mapping[str, Any] | None = None,
    tracked_terms: Iterable[str] = (),
    policy: SelectionPolicy | None = None,
) -> PipelineResult:
    """提供无需显式构造管道实例的稳定调用入口。"""
    return ContentPipeline(policy).process(
        items,
        now=now,
        seen_event_keys=seen_event_keys,
        recent_entity_observations=recent_entity_observations,
        tracked_terms=tracked_terms,
    )
