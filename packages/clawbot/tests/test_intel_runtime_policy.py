from src.intel.runtime_policy import (
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
