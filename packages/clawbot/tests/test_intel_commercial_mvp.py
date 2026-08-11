from __future__ import annotations

import sqlite3

from src.intel.db.store import initialize_intel_db
from src.intel.subscriptions import (
    DEFAULT_MVP_CATEGORIES,
    build_telegram_menu_contract,
    eligible_subscribers_for_categories,
    get_subscription_profile,
    grant_subscription,
    set_delivery_preferences,
    set_source_preferences,
    upsert_subscription_plan,
    upsert_telegram_subscriber,
)


def test_schema_contains_commercial_delivery_preferences(tmp_path):
    db_path = tmp_path / "intel_mvp.db"

    initialize_intel_db(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "delivery_preferences" in tables


def test_default_mvp_categories_cover_weather_menu_buttons():
    assert {"weather", "air_quality", "rainfall", "temperature", "humidity", "disaster_alerts"}.issubset(
        set(DEFAULT_MVP_CATEGORIES)
    )


def test_grant_subscription_profile_records_expiry_preferences_and_schedule(tmp_path):
    db_path = tmp_path / "intel_mvp.db"

    plan = upsert_subscription_plan(
        db_path,
        plan_name="intel_mvp_monthly",
        categories=["senate_trading", "akshare", "github_trending"],
        price_cents=9900,
        duration_type="monthly",
    )
    subscriber = upsert_telegram_subscriber(db_path, telegram_user_id="1001", chat_id="2001")
    subscription = grant_subscription(
        db_path,
        user_id=subscriber["user_id"],
        plan_name=plan["plan_name"],
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at="2026-08-07T00:00:00+00:00",
        source="manual_marketplace_sale",
    )
    set_source_preferences(db_path, user_id=subscriber["user_id"], enabled_categories=["senate_trading", "akshare"])
    set_delivery_preferences(
        db_path,
        user_id=subscriber["user_id"],
        frequency="daily",
        delivery_time="08:30",
        timezone="Asia/Singapore",
    )

    profile = get_subscription_profile(db_path, user_id=subscriber["user_id"], now="2026-07-08T00:00:00+00:00")

    assert subscription["status"] == "active"
    assert profile["eligible"] is True
    assert profile["plan_name"] == "intel_mvp_monthly"
    assert profile["expires_at"] == "2026-08-07T00:00:00+00:00"
    assert profile["enabled_categories"] == ["akshare", "senate_trading"]
    assert profile["delivery_preferences"] == {
        "frequency": "daily",
        "delivery_time": "08:30",
        "timezone": "Asia/Singapore",
        "content_language": "zh",
    }


def test_eligible_subscribers_respects_expiry_status_and_enabled_categories(tmp_path):
    db_path = tmp_path / "intel_mvp.db"
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=DEFAULT_MVP_CATEGORIES)

    active = upsert_telegram_subscriber(db_path, telegram_user_id="active", chat_id="chat-active")
    expired = upsert_telegram_subscriber(db_path, telegram_user_id="expired", chat_id="chat-expired")
    disabled_pref = upsert_telegram_subscriber(db_path, telegram_user_id="disabled", chat_id="chat-disabled")
    grant_subscription(
        db_path, user_id=active["user_id"], plan_name="intel_mvp_monthly", expires_at="2026-08-07T00:00:00+00:00"
    )
    grant_subscription(
        db_path, user_id=expired["user_id"], plan_name="intel_mvp_monthly", expires_at="2026-07-01T00:00:00+00:00"
    )
    grant_subscription(
        db_path, user_id=disabled_pref["user_id"], plan_name="intel_mvp_monthly", expires_at="2026-08-07T00:00:00+00:00"
    )
    set_source_preferences(db_path, user_id=active["user_id"], enabled_categories=["akshare"])
    set_source_preferences(db_path, user_id=expired["user_id"], enabled_categories=["akshare"])
    set_source_preferences(db_path, user_id=disabled_pref["user_id"], enabled_categories=["senate_trading"])

    recipients = eligible_subscribers_for_categories(
        db_path,
        categories=["akshare"],
        now="2026-07-08T00:00:00+00:00",
    )

    assert [recipient["user_id"] for recipient in recipients] == ["tg:active"]
    assert recipients[0]["channel_user_id"] == "chat-active"
    assert recipients[0]["matched_categories"] == ["akshare"]


def test_telegram_menu_contract_reflects_subscription_state_and_supported_commands(tmp_path):
    db_path = tmp_path / "intel_mvp.db"
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=DEFAULT_MVP_CATEGORIES)
    subscriber = upsert_telegram_subscriber(db_path, telegram_user_id="1001", chat_id="2001")
    grant_subscription(
        db_path, user_id=subscriber["user_id"], plan_name="intel_mvp_monthly", expires_at="2026-08-07T00:00:00+00:00"
    )
    set_source_preferences(db_path, user_id=subscriber["user_id"], enabled_categories=["senate_trading", "akshare"])
    profile = get_subscription_profile(db_path, user_id=subscriber["user_id"], now="2026-07-08T00:00:00+00:00")

    menu = build_telegram_menu_contract(profile)

    assert menu["bot_profile"] == "intel_brief_bot"
    assert menu["commands"] == [
        {"command": "start", "description": "打开菜单"},
        {"command": "today", "description": "今日简报"},
        {"command": "status", "description": "我的订阅"},
        {"command": "market", "description": "市场资金"},
        {"command": "ai", "description": "AI科技"},
        {"command": "weather", "description": "天气预警"},
        {"command": "schedule", "description": "推送时间"},
        {"command": "track", "description": "添加追踪"},
        {"command": "pause", "description": "暂停简报"},
        {"command": "language", "description": "资讯语言"},
        {"command": "help", "description": "帮助"},
    ]
    assert "700 今日简报" in menu["text"]
    assert "706 添加追踪" in menu["text"]
    assert "709 资讯语言" in menu["text"]
    assert "订阅状态：" not in menu["text"]
    assert "命令：/sources" not in menu["text"]
    labels = [button["text"] for row in menu["reply_markup"]["inline_keyboard"] for button in row]
    assert {"🧭 今日简报", "📌 我的订阅", "📈 市场资金", "🤖 AI科技", "➕ 添加追踪", "❓ 帮助"}.issubset(labels)
    assert menu["subscription_status"] == "active"
    assert menu["enabled_categories"] == ["akshare", "senate_trading"]
