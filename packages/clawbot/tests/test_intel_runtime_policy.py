from datetime import UTC, datetime

import pytest

from src.intel.runtime_policy import (
    DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE,
    evaluate_intel_brief_delivery_window,
    get_social_auth_strategy,
    resolve_runtime_policy,
    should_use_domestic_worker,
)


def test_domestic_sources_prefer_domestic_worker():
    policy = resolve_runtime_policy("weibo")

    assert policy.preferred_worker == "domestic"
    assert policy.region_hint == "cn"
    assert policy.requires_overseas_egress is False
    assert should_use_domestic_worker("akshare") is True


def test_overseas_sources_prefer_overseas_worker():
    policy = resolve_runtime_policy("sec_edgar")

    assert policy.preferred_worker == "overseas"
    assert policy.region_hint == "global"
    assert policy.requires_overseas_egress is True
    assert should_use_domestic_worker("github_trending") is False
    assert should_use_domestic_worker("ai_model_updates") is False


def test_social_auth_strategy_prefers_unattended_modes_before_qrcode():
    xhs = get_social_auth_strategy("xiaohongshu")
    weibo = get_social_auth_strategy("weibo")

    assert xhs.unattended_first is True
    assert weibo.unattended_first is True
    assert xhs.preferred_login_modes[:3] == ["cdp_cookie", "cookie", "phone"]
    assert weibo.preferred_login_modes[:3] == ["cdp_cookie", "cookie", "public_web"]
    assert xhs.qrcode_mode == "fallback_only"
    assert weibo.qrcode_mode == "fallback_only"


def test_runtime_policy_preserves_unknown_sources_on_controller():
    policy = resolve_runtime_policy("unknown_source")

    assert policy.preferred_worker == "controller"
    assert policy.region_hint == "auto"
    assert policy.reason == "unknown_source"


@pytest.mark.parametrize(
    ("now", "expected_reason", "expected_should_run"),
    [
        (datetime(2026, 8, 4, 0, 29, tzinfo=UTC), "skipped_before_window", False),
        (datetime(2026, 8, 4, 0, 30, tzinfo=UTC), "inside_delivery_window", True),
        (datetime(2026, 8, 4, 2, 0, tzinfo=UTC), "inside_delivery_window", True),
        (datetime(2026, 8, 4, 2, 1, tzinfo=UTC), "skipped_late_trigger", False),
    ],
)
def test_intel_brief_delivery_window_uses_singapore_wall_clock(
    now: datetime,
    expected_reason: str,
    expected_should_run: bool,
):
    decision = evaluate_intel_brief_delivery_window(now=now)

    assert decision.scheduler_timezone == DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE
    assert decision.local_now.utcoffset().total_seconds() == 8 * 60 * 60
    assert decision.reason == expected_reason
    assert decision.should_run is expected_should_run


def test_intel_brief_delivery_window_converts_aware_datetime_to_configured_zone():
    decision = evaluate_intel_brief_delivery_window(
        now=datetime(2026, 8, 4, 8, 45, tzinfo=UTC),
        scheduler_timezone="America/Denver",
        window_start=(2, 30),
        window_end=(3, 0),
    )

    assert decision.local_now.strftime("%Y-%m-%d %H:%M") == "2026-08-04 02:45"
    assert decision.reason == "inside_delivery_window"
    assert decision.should_run is True


@pytest.mark.parametrize(
    ("timezone_name", "window_start", "window_end"),
    [
        ("Mars/Olympus", (8, 30), (10, 0)),
        ("Asia/Singapore", (24, 0), (10, 0)),
        ("Asia/Singapore", (10, 0), (8, 30)),
    ],
)
def test_intel_brief_delivery_window_rejects_invalid_configuration(
    timezone_name: str,
    window_start: tuple[int, int],
    window_end: tuple[int, int],
):
    with pytest.raises(ValueError):
        evaluate_intel_brief_delivery_window(
            now=datetime(2026, 8, 4, 0, 30, tzinfo=UTC),
            scheduler_timezone=timezone_name,
            window_start=window_start,
            window_end=window_end,
        )
