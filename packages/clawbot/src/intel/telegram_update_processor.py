"""Offset-safe Telegram update processor for Intel Brief.

This module combines the Bot API runtime client shape with the Phase AA runtime
adapter.  It persists Telegram update offsets in SQLite so historical commands
are not replied to repeatedly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Protocol

from src.intel.db.store import initialize_intel_db
from src.intel.telegram_runtime import TelegramReplySender, process_intel_telegram_updates

DEFAULT_BOT_PROFILE = "intel_brief_bot"


class TelegramUpdatesClient(Protocol):
    def get_updates(
        self,
        *,
        limit: int = 20,
        offset: int | None = None,
        timeout_seconds: int = 0,
    ) -> dict[str, Any]:
        """Return Telegram getUpdates-style result with raw updates in memory."""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def get_telegram_offset(db_path: str | Path, *, bot_profile: str = DEFAULT_BOT_PROFILE) -> int:
    """Return the last processed Telegram update id for a bot profile."""
    initialize_intel_db(db_path)
    profile = _clean(bot_profile) or DEFAULT_BOT_PROFILE
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT last_update_id FROM telegram_runtime_state WHERE bot_profile=?",
            (profile,),
        ).fetchone()
    return int(row[0]) if row else 0


def set_telegram_offset(
    db_path: str | Path,
    update_id: int,
    *,
    bot_profile: str = DEFAULT_BOT_PROFILE,
) -> dict[str, Any]:
    """Persist the last processed Telegram update id."""
    initialize_intel_db(db_path)
    profile = _clean(bot_profile) or DEFAULT_BOT_PROFILE
    value = max(0, int(update_id or 0))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO telegram_runtime_state (bot_profile, last_update_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(bot_profile) DO UPDATE SET
                last_update_id=excluded.last_update_id,
                updated_at=CURRENT_TIMESTAMP
            """,
            (profile, value),
        )
        conn.commit()
    return {"bot_profile": profile, "last_update_id": value}


def _update_id(update: dict[str, Any]) -> int:
    try:
        return int(update.get("update_id", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _public_get_updates(get_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": bool(get_result.get("success")),
        "method": _clean(get_result.get("method")) or "getUpdates",
        "network": _clean(get_result.get("network")),
        "network_calls": int(get_result.get("network_calls", 0) or 0),
        "update_count": int(get_result.get("update_count", 0) or 0),
        "command_update_count": int(get_result.get("command_update_count", 0) or 0),
        "max_update_id_present": bool(get_result.get("max_update_id_present")),
        "redacted": get_result.get("redacted", {}),
        "error_code": _clean(get_result.get("error_code")),
        "error_present": bool(_clean(get_result.get("error"))),
    }


def process_telegram_updates_once(
    db_path: str | Path,
    *,
    client: TelegramUpdatesClient,
    sender: TelegramReplySender,
    now: str,
    bot_profile: str = DEFAULT_BOT_PROFILE,
    limit: int = 20,
    timeout_seconds: int = 0,
) -> dict[str, Any]:
    """Fetch, de-duplicate, process, and persist Telegram update offset once."""
    previous_offset = get_telegram_offset(db_path, bot_profile=bot_profile)
    request_offset = previous_offset + 1 if previous_offset > 0 else None
    get_result = client.get_updates(limit=limit, offset=request_offset, timeout_seconds=timeout_seconds)
    raw_updates = get_result.get("updates", []) if isinstance(get_result, dict) else []
    updates = [item for item in raw_updates if isinstance(item, dict)] if isinstance(raw_updates, list) else []
    filtered_updates = [item for item in updates if _update_id(item) > previous_offset]
    skipped_duplicate_count = len(updates) - len(filtered_updates)
    runtime = process_intel_telegram_updates(db_path, updates=filtered_updates, sender=sender, now=now) if filtered_updates else {
        "status": "partial_or_empty",
        "updates_seen": 0,
        "handled_count": 0,
        "skipped_count": 0,
        "send_success_count": 0,
        "handled_updates": [],
        "skipped_updates": [],
        "replies": [],
        "tracking_targets": [],
        "network_calls": 0,
        "limits": ["No new updates above persisted offset."],
    }
    max_seen = max([previous_offset, *[_update_id(item) for item in filtered_updates]])
    all_sends_ok = runtime["handled_count"] == runtime["send_success_count"]
    if bool(get_result.get("success")) and all_sends_ok:
        set_telegram_offset(db_path, max_seen, bot_profile=bot_profile)
        new_offset = max_seen
    else:
        new_offset = previous_offset
    tracking_targets = runtime.get("tracking_targets", []) if isinstance(runtime.get("tracking_targets"), list) else []
    status = "success" if bool(get_result.get("success")) and all_sends_ok else "failed"
    if bool(get_result.get("success")) and not filtered_updates:
        status = "no_new_updates"
    return {
        "status": status,
        "bot_profile": _clean(bot_profile) or DEFAULT_BOT_PROFILE,
        "previous_offset": previous_offset,
        "request_offset": request_offset,
        "new_offset": new_offset,
        "fetched_update_count": len(updates),
        "processable_update_count": len(filtered_updates),
        "skipped_duplicate_count": skipped_duplicate_count,
        "get_updates": _public_get_updates(get_result),
        "runtime": runtime,
        "tracking_targets": tracking_targets,
        "network_calls": int(get_result.get("network_calls", 0) or 0) + int(runtime.get("network_calls", 0) or 0),
        "raw_updates_persisted": False,
        "limits": [
            "Raw updates and chat ids are only used in memory and are not returned by this processor.",
            "Offset advances only when getUpdates succeeds and all processed replies succeed.",
        ],
    }
