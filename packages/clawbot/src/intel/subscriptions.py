"""Commercial MVP subscription and Telegram menu helpers for Intel Brief.

The functions in this module are deliberately small and SQLite-only.  They
prepare the paid-subscription layer without touching payment providers,
Telegram Bot API, schedulers, or remote workers.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.intel.channel_menu import (
    INTEL_INLINE_MENU_BUTTONS,
    build_intel_menu_text,
    intel_inline_menu_buttons,
    intel_numbered_commands,
)
from src.intel.db.store import initialize_intel_db
from src.intel.localization import DEFAULT_CONTENT_LANGUAGE, normalize_content_language, parse_content_language
from src.intel.runtime_policy import DEFAULT_INTEL_BRIEF_DELIVERY_TIME, DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE

DEFAULT_MVP_CATEGORIES = [
    "senate_trading",
    "akshare",
    "github_trending",
    "ai_model_updates",
    "institutional_13f",
    "weather",
    "air_quality",
    "rainfall",
    "temperature",
    "humidity",
    "disaster_alerts",
]

TELEGRAM_COMMANDS_ZH = [
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

TELEGRAM_COMMANDS_EN = [
    {"command": "start", "description": "Open menu"},
    {"command": "today", "description": "Today's brief"},
    {"command": "status", "description": "My subscription"},
    {"command": "market", "description": "Markets"},
    {"command": "ai", "description": "AI and tech"},
    {"command": "weather", "description": "Weather alerts"},
    {"command": "schedule", "description": "Delivery time"},
    {"command": "track", "description": "Track a topic"},
    {"command": "pause", "description": "Pause brief"},
    {"command": "language", "description": "Brief language"},
    {"command": "help", "description": "Help"},
]

TELEGRAM_COMMANDS = TELEGRAM_COMMANDS_ZH

TELEGRAM_INLINE_MENU_BUTTONS = INTEL_INLINE_MENU_BUTTONS

TELEGRAM_INLINE_MENU_KEYBOARD = [[button["text"] for button in row] for row in TELEGRAM_INLINE_MENU_BUTTONS]

TELEGRAM_PERSISTENT_MENU_BUTTONS = [
    [
        {"text": "🧭 今日简报"},
        {"text": "📌 我的订阅"},
    ],
]

TELEGRAM_PERSISTENT_MENU_BUTTONS_EN = [
    [
        {"text": "🧭 Today's Brief"},
        {"text": "📌 Subscription"},
    ],
]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _categories(values: list[str] | tuple[str, ...] | None) -> list[str]:
    cleaned = sorted({_clean(value) for value in (values or []) if _clean(value)})
    return cleaned


def telegram_commands_for_language(content_language: str = DEFAULT_CONTENT_LANGUAGE) -> list[dict[str, str]]:
    """返回指定语言的 Telegram 原生命令定义副本。"""
    commands = TELEGRAM_COMMANDS_EN if normalize_content_language(content_language) == "en" else TELEGRAM_COMMANDS_ZH
    return [dict(item) for item in commands]


def _has_delivery_language_column(conn: sqlite3.Connection) -> bool:
    """兼容探测新旧数据库是否已具备语言偏好列。"""
    columns = conn.execute("PRAGMA table_info(delivery_preferences)").fetchall()
    return any(str(row[1]) == "content_language" for row in columns)


def _subscriber_id(conn: sqlite3.Connection, user_id: str) -> int:
    row = conn.execute("SELECT id FROM subscribers WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        raise ValueError(f"subscriber_not_found: {user_id}")
    return int(row[0])


def upsert_subscription_plan(
    db_path: str | Path,
    *,
    plan_name: str,
    categories: list[str] | None = None,
    price_cents: int = 0,
    duration_type: str = "manual",
) -> dict[str, Any]:
    """Create or update a plan and return a redaction-safe plan record."""
    initialize_intel_db(db_path)
    plan = _clean(plan_name)
    if not plan:
        raise ValueError("plan_name is required")
    category_list = _categories(categories or DEFAULT_MVP_CATEGORIES)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO subscription_plans (plan_name, categories, price_cents, duration_type)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(plan_name) DO UPDATE SET
                categories=excluded.categories,
                price_cents=excluded.price_cents,
                duration_type=excluded.duration_type
            """,
            (plan, json.dumps(category_list, ensure_ascii=False), int(price_cents), _clean(duration_type) or "manual"),
        )
        row = conn.execute(
            "SELECT id, plan_name, categories, price_cents, duration_type FROM subscription_plans WHERE plan_name=?",
            (plan,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise RuntimeError("subscription_plan_write_failed")
    return {
        "plan_id": int(row[0]),
        "plan_name": str(row[1]),
        "categories": json.loads(str(row[2] or "[]")),
        "price_cents": int(row[3] or 0),
        "duration_type": str(row[4] or ""),
    }


def upsert_telegram_subscriber(
    db_path: str | Path,
    *,
    telegram_user_id: str,
    chat_id: str,
    reactivate: bool = True,
) -> dict[str, Any]:
    """Create/update a Telegram subscriber using a stable internal user id."""
    initialize_intel_db(db_path)
    tg_user = _clean(telegram_user_id)
    chat = _clean(chat_id)
    if not tg_user:
        raise ValueError("telegram_user_id is required")
    if not chat:
        raise ValueError("chat_id is required")
    user_id = f"tg:{tg_user}"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO subscribers (user_id, channel_type, channel_user_id, status, updated_at)
            VALUES (?, 'telegram', ?, 'active', CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                channel_type='telegram',
                channel_user_id=excluded.channel_user_id,
                status=CASE WHEN ? THEN 'active' ELSE subscribers.status END,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, chat, 1 if reactivate else 0),
        )
        subscriber_id = _subscriber_id(conn, user_id)
        conn.commit()
    return {
        "subscriber_id": subscriber_id,
        "user_id": user_id,
        "channel_type": "telegram",
        "channel_user_id": chat,
    }


def grant_subscription(
    db_path: str | Path,
    *,
    user_id: str,
    plan_name: str,
    starts_at: str = "CURRENT_TIMESTAMP",
    expires_at: str | None = None,
    status: str = "active",
    source: str = "manual",
) -> dict[str, Any]:
    """Grant a subscription to an existing subscriber.

    Previous active rows for the same subscriber/plan are marked superseded so
    the latest grant is the source of truth for MVP entitlement.
    """
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        subscriber_id = _subscriber_id(conn, user_id)
        plan_row = conn.execute(
            "SELECT id, plan_name FROM subscription_plans WHERE plan_name=?", (plan_name,)
        ).fetchone()
        if plan_row is None:
            raise ValueError(f"plan_not_found: {plan_name}")
        plan_id = int(plan_row[0])
        conn.execute(
            """
            UPDATE user_subscriptions
            SET status='superseded'
            WHERE subscriber_id=? AND plan_id=? AND status='active'
            """,
            (subscriber_id, plan_id),
        )
        if starts_at == "CURRENT_TIMESTAMP":
            conn.execute(
                """
                INSERT INTO user_subscriptions (subscriber_id, plan_id, starts_at, expires_at, status)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
                """,
                (subscriber_id, plan_id, expires_at, _clean(status) or "active"),
            )
        else:
            conn.execute(
                """
                INSERT INTO user_subscriptions (subscriber_id, plan_id, starts_at, expires_at, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (subscriber_id, plan_id, starts_at, expires_at, _clean(status) or "active"),
            )
        subscription_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            """
            INSERT INTO subscription_audit_log (subscriber_id, plan_name, event_type, source)
            VALUES (?, ?, 'grant', ?)
            """,
            (subscriber_id, plan_name, _clean(source) or "manual"),
        )
        conn.commit()
    return {
        "subscription_id": subscription_id,
        "subscriber_id": subscriber_id,
        "plan_name": plan_name,
        "starts_at": starts_at,
        "expires_at": expires_at or "",
        "status": _clean(status) or "active",
        "source": _clean(source) or "manual",
    }


def set_source_preferences(
    db_path: str | Path,
    *,
    user_id: str,
    enabled_categories: list[str],
) -> dict[str, Any]:
    """Replace enabled source preferences for a subscriber."""
    initialize_intel_db(db_path)
    enabled = _categories(enabled_categories)
    with sqlite3.connect(db_path) as conn:
        subscriber_id = _subscriber_id(conn, user_id)
        conn.execute(
            "UPDATE source_preferences SET enabled=0, updated_at=CURRENT_TIMESTAMP WHERE subscriber_id=?",
            (subscriber_id,),
        )
        for category in enabled:
            conn.execute(
                """
                INSERT INTO source_preferences (subscriber_id, category, enabled, updated_at)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(subscriber_id, category) DO UPDATE SET enabled=1, updated_at=CURRENT_TIMESTAMP
                """,
                (subscriber_id, category),
            )
        conn.commit()
    return {"subscriber_id": subscriber_id, "enabled_categories": enabled}


def set_delivery_preferences(
    db_path: str | Path,
    *,
    user_id: str,
    frequency: str = "daily",
    delivery_time: str = "08:30",
    timezone: str = "Asia/Singapore",
    content_language: str | None = None,
) -> dict[str, Any]:
    """Set MVP delivery cadence for a subscriber."""
    normalized_frequency = _clean(frequency) or "daily"
    normalized_time = _clean(delivery_time) or DEFAULT_INTEL_BRIEF_DELIVERY_TIME
    normalized_timezone = _clean(timezone) or DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE
    if normalized_frequency not in {"daily", "weekly"}:
        raise ValueError("frequency must be daily or weekly")
    if (
        normalized_time != DEFAULT_INTEL_BRIEF_DELIVERY_TIME
        or normalized_timezone != DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE
    ):
        raise ValueError("unsupported_delivery_schedule")
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        subscriber_id = _subscriber_id(conn, user_id)
        has_language = _has_delivery_language_column(conn)
        requested_language = parse_content_language(content_language) if content_language is not None else None
        if content_language is not None and requested_language is None:
            raise ValueError("content_language must be zh or en")
        if has_language and requested_language is not None:
            conn.execute(
                """
                INSERT INTO delivery_preferences (
                    subscriber_id, frequency, delivery_time, timezone, content_language, updated_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(subscriber_id) DO UPDATE SET
                    frequency=excluded.frequency,
                    delivery_time=excluded.delivery_time,
                    timezone=excluded.timezone,
                    content_language=excluded.content_language,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    subscriber_id,
                    normalized_frequency,
                    normalized_time,
                    normalized_timezone,
                    requested_language,
                ),
            )
        elif has_language:
            conn.execute(
                """
                INSERT INTO delivery_preferences (
                    subscriber_id, frequency, delivery_time, timezone, content_language, updated_at
                )
                VALUES (?, ?, ?, ?, 'zh', CURRENT_TIMESTAMP)
                ON CONFLICT(subscriber_id) DO UPDATE SET
                    frequency=excluded.frequency,
                    delivery_time=excluded.delivery_time,
                    timezone=excluded.timezone,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    subscriber_id,
                    normalized_frequency,
                    normalized_time,
                    normalized_timezone,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO delivery_preferences (subscriber_id, frequency, delivery_time, timezone, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(subscriber_id) DO UPDATE SET
                    frequency=excluded.frequency,
                    delivery_time=excluded.delivery_time,
                    timezone=excluded.timezone,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    subscriber_id,
                    normalized_frequency,
                    normalized_time,
                    normalized_timezone,
                ),
            )
        row = conn.execute(
            (
                "SELECT frequency, delivery_time, timezone, content_language "
                "FROM delivery_preferences WHERE subscriber_id=?"
                if has_language
                else "SELECT frequency, delivery_time, timezone FROM delivery_preferences WHERE subscriber_id=?"
            ),
            (subscriber_id,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise RuntimeError("delivery_preferences_write_failed")
    result: dict[str, Any] = {
        "frequency": str(row[0] or "daily"),
        "delivery_time": str(row[1] or "08:30"),
        "timezone": str(row[2] or "Asia/Singapore"),
    }
    if content_language is not None:
        result["content_language"] = normalize_content_language(
            row[3] if has_language and len(row) > 3 else DEFAULT_CONTENT_LANGUAGE
        )
        result["language_persisted"] = has_language
    return result


def set_content_language(
    db_path: str | Path,
    *,
    user_id: str,
    content_language: str,
) -> dict[str, Any]:
    """只更新资讯语言，不改变频率、时间、时区或订阅启停状态。"""
    requested = parse_content_language(content_language)
    if requested is None:
        raise ValueError("content_language must be zh or en")
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        subscriber_id = _subscriber_id(conn, user_id)
        has_language = _has_delivery_language_column(conn)
        if has_language:
            conn.execute(
                """
                INSERT INTO delivery_preferences (
                    subscriber_id, frequency, delivery_time, timezone, content_language, updated_at
                )
                VALUES (?, 'daily', '08:30', 'Asia/Singapore', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(subscriber_id) DO UPDATE SET
                    content_language=excluded.content_language,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (subscriber_id, requested),
            )
        conn.commit()
    profile = get_subscription_profile(db_path, user_id=user_id)
    preferences = dict(profile.get("delivery_preferences") or {})
    return {
        **preferences,
        "content_language": requested if has_language else DEFAULT_CONTENT_LANGUAGE,
        "language_persisted": has_language,
    }


def _active_subscription_row(
    conn: sqlite3.Connection, subscriber_id: int, now: str
) -> sqlite3.Row | tuple[Any, ...] | None:
    return conn.execute(
        """
        SELECT us.id, sp.plan_name, us.starts_at, us.expires_at, us.status
        FROM user_subscriptions us
        JOIN subscription_plans sp ON sp.id=us.plan_id
        WHERE us.subscriber_id=?
          AND us.status='active'
          AND (us.expires_at IS NULL OR us.expires_at > ?)
        ORDER BY us.id DESC
        LIMIT 1
        """,
        (subscriber_id, now),
    ).fetchone()


def get_subscription_profile(
    db_path: str | Path,
    *,
    user_id: str,
    now: str = "9999-12-31T00:00:00+00:00",
) -> dict[str, Any]:
    """Return a redaction-safe profile for menu rendering and entitlement checks."""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        subscriber_row = conn.execute(
            "SELECT id, user_id, channel_type, channel_user_id, status FROM subscribers WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if subscriber_row is None:
            return {"eligible": False, "status": "not_found", "user_id": user_id}
        subscriber_id = int(subscriber_row[0])
        subscription = _active_subscription_row(conn, subscriber_id, now)
        prefs = [
            str(row[0])
            for row in conn.execute(
                "SELECT category FROM source_preferences WHERE subscriber_id=? AND enabled=1 ORDER BY category",
                (subscriber_id,),
            ).fetchall()
        ]
        has_language = _has_delivery_language_column(conn)
        delivery = conn.execute(
            (
                "SELECT frequency, delivery_time, timezone, content_language "
                "FROM delivery_preferences WHERE subscriber_id=?"
                if has_language
                else "SELECT frequency, delivery_time, timezone FROM delivery_preferences WHERE subscriber_id=?"
            ),
            (subscriber_id,),
        ).fetchone()
    delivery_preferences = {
        "frequency": str(delivery[0]) if delivery else "daily",
        "delivery_time": str(delivery[1]) if delivery else "08:30",
        "timezone": str(delivery[2]) if delivery else "Asia/Singapore",
        "content_language": normalize_content_language(
            delivery[3] if delivery and has_language and len(delivery) > 3 else DEFAULT_CONTENT_LANGUAGE
        ),
    }
    subscriber_status = str(subscriber_row[4])
    status = "active" if subscription is not None and subscriber_status == "active" else "inactive_or_expired"
    if subscriber_status == "paused":
        status = "paused"
    return {
        "eligible": subscription is not None and str(subscriber_row[4]) == "active",
        "status": status,
        "subscriber_id": subscriber_id,
        "user_id": str(subscriber_row[1]),
        "channel_type": str(subscriber_row[2]),
        "channel_user_id": str(subscriber_row[3]),
        "plan_name": str(subscription[1]) if subscription else "",
        "starts_at": str(subscription[2]) if subscription else "",
        "expires_at": str(subscription[3] or "") if subscription else "",
        "enabled_categories": prefs,
        "delivery_preferences": delivery_preferences,
    }


def eligible_subscribers_for_categories(
    db_path: str | Path,
    *,
    categories: list[str],
    now: str,
) -> list[dict[str, Any]]:
    """Return active Telegram subscribers with at least one enabled category."""
    initialize_intel_db(db_path)
    requested = set(_categories(categories))
    if not requested:
        return []
    recipients: list[dict[str, Any]] = []
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT s.user_id
            FROM subscribers s
            JOIN user_subscriptions us ON us.subscriber_id=s.id
            WHERE s.status='active'
              AND s.channel_type='telegram'
              AND us.status='active'
              AND (us.expires_at IS NULL OR us.expires_at > ?)
            ORDER BY s.id
            """,
            (now,),
        ).fetchall()
    for row in rows:
        profile = get_subscription_profile(db_path, user_id=str(row[0]), now=now)
        matched = sorted(requested.intersection(profile.get("enabled_categories", [])))
        if matched:
            recipients.append({**profile, "matched_categories": matched})
    return recipients


def build_telegram_menu_contract(profile: dict[str, Any]) -> dict[str, Any]:
    """Build the Telegram MVP menu contract without sending it."""
    enabled = list(profile.get("enabled_categories") or [])
    status = str(profile.get("status") or "inactive_or_expired")
    delivery_preferences = dict(profile.get("delivery_preferences") or {})
    content_language = normalize_content_language(delivery_preferences.get("content_language"))
    commands = telegram_commands_for_language(content_language)
    inline_buttons = intel_inline_menu_buttons(content_language)
    numbered_commands = intel_numbered_commands(content_language)
    persistent_buttons = (
        TELEGRAM_PERSISTENT_MENU_BUTTONS_EN if content_language == "en" else TELEGRAM_PERSISTENT_MENU_BUTTONS
    )
    text = build_intel_menu_text(
        channel="telegram",
        subscription_status=status,
        content_language=content_language,
    )
    persistent_reply_markup = {
        "keyboard": [[dict(button) for button in row] for row in persistent_buttons],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "is_persistent": True,
        "input_field_placeholder": "Search intelligence..." if content_language == "en" else "输入关键词搜索...",
    }
    reply_markup = {
        "inline_keyboard": [[dict(button) for button in row] for row in inline_buttons],
    }
    return {
        "bot_profile": "intel_brief_bot",
        "commands": commands,
        "inline_buttons": inline_buttons,
        "inline_keyboard": [[button["text"] for button in row] for row in inline_buttons],
        "numbered_commands": numbered_commands,
        "persistent_keyboard": [[button["text"] for button in row] for row in persistent_buttons],
        "persistent_reply_markup": persistent_reply_markup,
        "prelude_replies": [
            {
                "text": (
                    "Quick actions are ready. Tap a button or reply with a number, for example 706 NVIDIA."
                    if content_language == "en"
                    else "菜单快捷入口已打开：可点按钮，也可直接回复数字，例如 706 英伟达。"
                ),
                "reply_markup": persistent_reply_markup,
            }
        ],
        "menu_style": "product_numbered_inline_card_with_persistent_shortcuts",
        "reply_markup": reply_markup,
        "text": text,
        "subscription_status": status,
        "enabled_categories": enabled,
        "delivery_preferences": delivery_preferences,
        "content_language": content_language,
    }
