"""Baseline Telegram update offset before enabling automatic replies.

The baseline step marks historical updates as already seen.  It intentionally
never calls sendMessage and never persists raw updates, chat ids, user ids, or
message text.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.telegram_update_processor import (
    DEFAULT_BOT_PROFILE,
    TelegramUpdatesClient,
    get_telegram_offset,
    set_telegram_offset,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


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


def seed_telegram_baseline_offset(
    db_path: str | Path,
    *,
    client: TelegramUpdatesClient,
    bot_profile: str = DEFAULT_BOT_PROFILE,
    limit: int = 100,
    timeout_seconds: int = 0,
) -> dict[str, Any]:
    """Set offset to the latest currently visible update id without replying."""
    previous_offset = get_telegram_offset(db_path, bot_profile=bot_profile)
    get_result = client.get_updates(limit=limit, offset=None, timeout_seconds=timeout_seconds)
    raw_updates = get_result.get("updates", []) if isinstance(get_result, dict) else []
    updates = [item for item in raw_updates if isinstance(item, dict)] if isinstance(raw_updates, list) else []
    baseline_update_id = max([0, *[_update_id(item) for item in updates]])
    new_offset = max(previous_offset, baseline_update_id)
    status = "success" if bool(get_result.get("success")) else "failed"
    if status == "success":
        set_telegram_offset(db_path, new_offset, bot_profile=bot_profile)
    else:
        new_offset = previous_offset
    return {
        "timestamp": _now_iso(),
        "status": status,
        "bot_profile": _clean(bot_profile) or DEFAULT_BOT_PROFILE,
        "previous_offset": previous_offset,
        "baseline_update_id": baseline_update_id,
        "new_offset": new_offset,
        "get_updates": _public_get_updates(get_result),
        "network_calls": int(get_result.get("network_calls", 0) or 0),
        "reply_sent": False,
        "raw_updates_persisted": False,
        "limits": [
            "Baseline step only reads getUpdates and stores the max update id as offset.",
            "No sendMessage call is made; historical updates are not replied to.",
            "Raw updates, chat ids, user ids, and message text are not returned or persisted.",
        ],
    }


def build_telegram_baseline_offset_evidence(
    *,
    db_path: str | Path,
    evidence_path: str | Path,
    client: TelegramUpdatesClient,
    bot_profile: str = DEFAULT_BOT_PROFILE,
    limit: int = 100,
    timeout_seconds: int = 0,
    source: str = "manual_baseline",
) -> dict[str, Any]:
    """Run baseline offset seed and write redacted evidence."""
    result = seed_telegram_baseline_offset(
        db_path,
        client=client,
        bot_profile=bot_profile,
        limit=limit,
        timeout_seconds=timeout_seconds,
    )
    payload = {
        "timestamp": _now_iso(),
        "phase": "AD-telegram-baseline-offset",
        "scope": "telegram_historical_update_baseline_without_replying",
        "source": _clean(source) or "manual_baseline",
        "db_path": str(db_path),
        **result,
        "rollback": [
            "Reset telegram_runtime_state.last_update_id to the previous_offset recorded in this evidence if baseline was unintended.",
        ],
    }
    path = Path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
