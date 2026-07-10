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

from src.intel.channel_menu import INTEL_INLINE_MENU_BUTTONS, INTEL_NUMBERED_COMMANDS, build_intel_menu_text
from src.intel.db.store import initialize_intel_db

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

TELEGRAM_COMMANDS = [
    {"command": "start", "description": "打开菜单"},
    {"command": "today", "description": "今日简报"},
    {"command": "status", "description": "我的订阅"},
    {"command": "market", "description": "市场资金"},
    {"command": "ai", "description": "AI科技"},
    {"command": "weather", "description": "天气预警"},
    {"command": "schedule", "description": "推送时间"},
    {"command": "track", "description": "添加追踪"},
    {"command": "pause", "description": "暂停简报"},
    {"command": "help", "description": "帮助"},
]

TELEGRAM_INLINE_MENU_BUTTONS = INTEL_INLINE_MENU_BUTTONS

TELEGRAM_INLINE_MENU_KEYBOARD = [
    [button["text"] for button in row]
    for row in TELEGRAM_INLINE_MENU_BUTTONS
]

TELEGRAM_PERSISTENT_MENU_BUTTONS = [
    [
        {"text": "🧭 今日简报"},
        {"text": "📌 我的订阅"},
    ],
]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _categories(values: list[str] | tuple[str, ...] | None) -> list[str]:
    cleaned = sorted({_clean(value) for value in (values or []) if _clean(value)})
    return cleaned


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
        plan_row = conn.execute("SELECT id, plan_name FROM subscription_plans WHERE plan_name=?", (plan_name,)).fetchone()
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
        conn.execute("UPDATE source_preferences SET enabled=0, updated_at=CURRENT_TIMESTAMP WHERE subscriber_id=?", (subscriber_id,))
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
    timezone: str = "America/Denver",
) -> dict[str, str]:
    """Set MVP delivery cadence for a subscriber."""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        subscriber_id = _subscriber_id(conn, user_id)
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
            (subscriber_id, _clean(frequency) or "daily", _clean(delivery_time) or "08:30", _clean(timezone) or "America/Denver"),
        )
        conn.commit()
    return {
        "frequency": _clean(frequency) or "daily",
        "delivery_time": _clean(delivery_time) or "08:30",
        "timezone": _clean(timezone) or "America/Denver",
    }


def _active_subscription_row(conn: sqlite3.Connection, subscriber_id: int, now: str) -> sqlite3.Row | tuple[Any, ...] | None:
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
        delivery = conn.execute(
            "SELECT frequency, delivery_time, timezone FROM delivery_preferences WHERE subscriber_id=?",
            (subscriber_id,),
        ).fetchone()
    delivery_preferences = {
        "frequency": str(delivery[0]) if delivery else "daily",
        "delivery_time": str(delivery[1]) if delivery else "08:30",
        "timezone": str(delivery[2]) if delivery else "America/Denver",
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
    text = build_intel_menu_text(channel="telegram", subscription_status=status)
    persistent_reply_markup = {
        "keyboard": [
            [dict(button) for button in row]
            for row in TELEGRAM_PERSISTENT_MENU_BUTTONS
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "is_persistent": True,
        "input_field_placeholder": "输入关键词搜索...",
    }
    reply_markup = {
        "inline_keyboard": [
            [dict(button) for button in row]
            for row in TELEGRAM_INLINE_MENU_BUTTONS
        ],
    }
    return {
        "bot_profile": "intel_brief_bot",
        "commands": TELEGRAM_COMMANDS,
        "inline_buttons": TELEGRAM_INLINE_MENU_BUTTONS,
        "inline_keyboard": TELEGRAM_INLINE_MENU_KEYBOARD,
        "numbered_commands": [dict(item) for item in INTEL_NUMBERED_COMMANDS],
        "persistent_keyboard": [[button["text"] for button in row] for row in TELEGRAM_PERSISTENT_MENU_BUTTONS],
        "persistent_reply_markup": persistent_reply_markup,
        "prelude_replies": [
            {
                "text": "菜单快捷入口已打开：可点按钮，也可直接回复数字，例如 706 英伟达。",
                "reply_markup": persistent_reply_markup,
            }
        ],
        "menu_style": "product_numbered_inline_card_with_persistent_shortcuts",
        "reply_markup": reply_markup,
        "text": text,
        "subscription_status": status,
        "enabled_categories": enabled,
        "delivery_preferences": profile.get("delivery_preferences", {}),
    }
