"""Manual order-to-entitlement helpers for Intel Brief.

This is the safe operator bridge before payment automation exists.  It
turns a verified external order into a subscription grant, with dry-run by
default and redacted evidence.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.intel.db.store import initialize_intel_db
from src.intel.subscriptions import (
    DEFAULT_MVP_CATEGORIES,
    get_subscription_profile,
    grant_subscription,
    set_delivery_preferences,
    set_source_preferences,
    upsert_subscription_plan,
    upsert_telegram_subscriber,
)

DEFAULT_MANUAL_PLAN = "intel_mvp_manual_monthly"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _source_with_order_fingerprint(source: str, order_ref: str) -> str:
    source_label = _clean(source) or "manual_order"
    fingerprint = hashlib.sha256(_clean(order_ref).encode("utf-8")).hexdigest()[:12]
    return f"{source_label}:order_ref_sha256:{fingerprint}"


def _parse_dt(value: str | datetime | None, *, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif _clean(value):
        parsed = datetime.fromisoformat(_clean(value).replace("Z", "+00:00"))
    elif fallback is not None:
        parsed = fallback
    else:
        parsed = datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    return parsed.astimezone(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility


def _active_expiry(conn: sqlite3.Connection, *, subscriber_id: int, now: datetime) -> str:
    row = conn.execute(
        """
        SELECT expires_at
        FROM user_subscriptions
        WHERE subscriber_id=?
          AND status='active'
          AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (subscriber_id, now.isoformat()),
    ).fetchone()
    return str(row[0] or "") if row else ""


def _safe_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "eligible": bool(profile.get("eligible")),
        "status": _clean(profile.get("status")),
        "subscriber_id": int(profile.get("subscriber_id", 0) or 0),
        "user_id_present": bool(_clean(profile.get("user_id"))),
        "channel_type": _clean(profile.get("channel_type")),
        "channel_user_id_present": bool(_clean(profile.get("channel_user_id"))),
        "plan_name": _clean(profile.get("plan_name")),
        "starts_at": _clean(profile.get("starts_at")),
        "expires_at": _clean(profile.get("expires_at")),
        "enabled_categories": list(profile.get("enabled_categories") or []),
        "delivery_preferences": profile.get("delivery_preferences") or {},
    }


def grant_manual_entitlement(
    *,
    db_path: str | Path,
    telegram_user_id: str,
    chat_id: str,
    order_ref: str,
    duration_days: int = 30,
    plan_name: str = DEFAULT_MANUAL_PLAN,
    categories: list[str] | None = None,
    starts_at: str | datetime | None = None,
    source: str = "manual_order",
    apply: bool = False,
    delivery_time: str = "08:30",
    timezone_name: str = "Asia/Singapore",
) -> dict[str, Any]:
    """Grant or preview a manual subscription entitlement.

    ``apply=False`` performs no DB mutation beyond schema initialization.  It
    returns the planned starts/expires timestamps and redacted target presence.
    """
    initialize_intel_db(db_path)
    if not _clean(telegram_user_id):
        raise ValueError("telegram_user_id is required")
    if not _clean(chat_id):
        raise ValueError("chat_id is required")
    if not _clean(order_ref):
        raise ValueError("order_ref is required")
    if int(duration_days) <= 0:
        raise ValueError("duration_days must be positive")

    now_value = _parse_dt(starts_at)
    category_list = sorted({_clean(item) for item in (categories or DEFAULT_MVP_CATEGORIES) if _clean(item)})
    user_id = f"tg:{_clean(telegram_user_id)}"
    active_expires_at = ""
    subscriber_id = 0
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT id FROM subscribers WHERE user_id=?", (user_id,)).fetchone()
        if row:
            subscriber_id = int(row[0])
            active_expires_at = _active_expiry(conn, subscriber_id=subscriber_id, now=now_value)
    base_start = _parse_dt(active_expires_at, fallback=now_value) if active_expires_at else now_value
    if base_start < now_value:
        base_start = now_value
    expires_at = base_start + timedelta(days=int(duration_days))
    planned = {
        "user_id_present": bool(user_id),
        "chat_id_present": bool(_clean(chat_id)),
        "existing_subscriber": bool(subscriber_id),
        "existing_active_expires_at": active_expires_at,
        "starts_at": base_start.isoformat(),
        "expires_at": expires_at.isoformat(),
        "duration_days": int(duration_days),
        "plan_name": _clean(plan_name) or DEFAULT_MANUAL_PLAN,
        "categories": category_list,
        "order_ref_present": True,
        "source": _clean(source) or "manual_order",
    }
    if not apply:
        return {
            "timestamp": _now_iso(),
            "status": "dry_run",
            "applied": False,
            "planned": planned,
            "profile_after": None,
            "network_calls": 0,
            "limits": [
                "Dry-run only; no subscriber, subscription, preference, or audit row is written.",
                "Telegram user/chat ids and order reference are represented only by presence flags.",
            ],
        }

    plan = upsert_subscription_plan(
        db_path,
        plan_name=planned["plan_name"],
        categories=category_list,
        price_cents=0,
        duration_type=f"manual_{int(duration_days)}d",
    )
    subscriber = upsert_telegram_subscriber(db_path, telegram_user_id=_clean(telegram_user_id), chat_id=_clean(chat_id))
    subscription = grant_subscription(
        db_path,
        user_id=subscriber["user_id"],
        plan_name=plan["plan_name"],
        starts_at=planned["starts_at"],
        expires_at=planned["expires_at"],
        source=_source_with_order_fingerprint(source, order_ref),
    )
    preferences = set_source_preferences(db_path, user_id=subscriber["user_id"], enabled_categories=category_list)
    delivery = set_delivery_preferences(
        db_path,
        user_id=subscriber["user_id"],
        frequency="daily",
        delivery_time=delivery_time,
        timezone=timezone_name,
    )
    profile = get_subscription_profile(db_path, user_id=subscriber["user_id"], now=now_value.isoformat())
    return {
        "timestamp": _now_iso(),
        "status": "success",
        "applied": True,
        "planned": planned,
        "plan": {
            "plan_id": plan["plan_id"],
            "plan_name": plan["plan_name"],
            "categories": plan["categories"],
            "duration_type": plan["duration_type"],
        },
        "subscriber": {
            "subscriber_id": subscriber["subscriber_id"],
            "user_id_present": bool(_clean(subscriber.get("user_id"))),
            "channel_type": subscriber["channel_type"],
            "channel_user_id_present": bool(_clean(subscriber.get("channel_user_id"))),
        },
        "subscription": {
            "subscription_id": subscription["subscription_id"],
            "subscriber_id": subscription["subscriber_id"],
            "plan_name": subscription["plan_name"],
            "starts_at": subscription["starts_at"],
            "expires_at": subscription["expires_at"],
            "status": subscription["status"],
            "source_present": bool(_clean(subscription.get("source"))),
        },
        "preferences": preferences,
        "delivery_preferences": delivery,
        "profile_after": _safe_profile(profile),
        "network_calls": 0,
        "limits": [
            "Manual entitlement writes local SQLite only; no payment provider, marketplace, Telegram, or remote worker is called.",
            "Telegram user/chat ids and order reference are represented only by presence flags in evidence.",
        ],
    }


def build_manual_entitlement_sandbox(output_dir: str | Path) -> dict[str, Any]:
    """Write sandbox evidence for manual order dry-run and apply."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "intel_manual_entitlement_sandbox.db"
    evidence_path = out_dir / "evidence.json"
    dry_run = grant_manual_entitlement(
        db_path=db_path,
        telegram_user_id="manual-user",
        chat_id="manual-chat",
        order_ref="marketplace-order-001",
        duration_days=30,
        categories=["akshare", "senate_trading"],
        starts_at="2026-07-07T00:00:00+00:00",
        apply=False,
    )
    applied = grant_manual_entitlement(
        db_path=db_path,
        telegram_user_id="manual-user",
        chat_id="manual-chat",
        order_ref="marketplace-order-001",
        duration_days=30,
        categories=["akshare", "senate_trading"],
        starts_at="2026-07-07T00:00:00+00:00",
        apply=True,
    )
    renewed = grant_manual_entitlement(
        db_path=db_path,
        telegram_user_id="manual-user",
        chat_id="manual-chat",
        order_ref="marketplace-order-002-renewal",
        duration_days=30,
        categories=["akshare", "senate_trading"],
        starts_at="2026-07-08T00:00:00+00:00",
        apply=True,
    )
    evidence = {
        "timestamp": _now_iso(),
        "phase": "AP-manual-entitlement-sandbox",
        "scope": "manual_order_to_subscription_entitlement_contract",
        "status": "success" if applied["status"] == "success" and renewed["status"] == "success" else "failed",
        "sandbox_db": str(db_path),
        "dry_run": dry_run,
        "applied": applied,
        "renewed": renewed,
        "network_calls": 0,
        "redaction": {
            "raw_telegram_user_id_written": False,
            "raw_chat_id_written": False,
            "raw_order_ref_written": False,
            "telegram_token_written": False,
        },
        "rollback": [str(db_path), str(evidence_path)],
        "limits": [
            "Sandbox SQLite only; production intel_brief.db was not touched.",
            "No payment provider, marketplace, Telegram Bot API, scheduler, or remote worker call.",
        ],
    }
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence
