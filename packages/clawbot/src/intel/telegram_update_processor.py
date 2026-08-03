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
    """单调保存最后已确认处理的 Telegram update id。"""
    initialize_intel_db(db_path)
    profile = _clean(bot_profile) or DEFAULT_BOT_PROFILE
    value = max(0, int(update_id or 0))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO telegram_runtime_state (bot_profile, last_update_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(bot_profile) DO UPDATE SET
                last_update_id=MAX(telegram_runtime_state.last_update_id, excluded.last_update_id),
                updated_at=CURRENT_TIMESTAMP
            """,
            (profile, value),
        )
        row = conn.execute(
            "SELECT last_update_id FROM telegram_runtime_state WHERE bot_profile=?",
            (profile,),
        ).fetchone()
        conn.commit()
    persisted = int(row[0]) if row else value
    return {"bot_profile": profile, "last_update_id": persisted}


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


def _empty_runtime() -> dict[str, Any]:
    """构造可累加且不包含原始 Telegram 数据的运行结果。"""
    return {
        "status": "partial_or_empty",
        "updates_seen": 0,
        "handled_count": 0,
        "skipped_count": 0,
        "send_success_count": 0,
        "delivery_terminal_count": 0,
        "delivery_unknown_count": 0,
        "callback_answer_failure_count": 0,
        "handled_updates": [],
        "skipped_updates": [],
        "replies": [],
        "tracking_targets": [],
        "network_calls": 0,
        "processing_failures": [],
        "limits": ["No new updates above persisted offset."],
    }


def _merge_runtime(total: dict[str, Any], current: dict[str, Any]) -> None:
    """把单条 update 的脱敏运行结果累加到本轮汇总。"""
    for key in (
        "updates_seen",
        "handled_count",
        "skipped_count",
        "send_success_count",
        "delivery_terminal_count",
        "delivery_unknown_count",
        "callback_answer_failure_count",
        "network_calls",
    ):
        total[key] = int(total.get(key, 0) or 0) + int(current.get(key, 0) or 0)
    for key in ("handled_updates", "skipped_updates", "replies", "tracking_targets"):
        values = current.get(key)
        if isinstance(values, list):
            total[key].extend(values)


def _finalize_runtime_status(runtime: dict[str, Any]) -> None:
    """根据逐条处理结果重算兼容旧调用方的 runtime 状态。"""
    handled_count = int(runtime.get("handled_count", 0) or 0)
    send_success_count = int(runtime.get("send_success_count", 0) or 0)
    delivery_terminal_count = int(runtime.get("delivery_terminal_count", 0) or 0)
    delivery_unknown_count = int(runtime.get("delivery_unknown_count", 0) or 0)
    callback_answer_failure_count = int(runtime.get("callback_answer_failure_count", 0) or 0)
    if (
        handled_count
        and delivery_terminal_count == handled_count
        and (delivery_unknown_count or callback_answer_failure_count)
    ):
        runtime["status"] = "completed_with_warnings"
    elif handled_count and handled_count == send_success_count:
        runtime["status"] = "success"
    elif handled_count:
        runtime["status"] = "partial_failed_send"
    else:
        runtime["status"] = "partial_or_empty"
    runtime["limits"] = [
        "Raw Telegram chat ids are used only in-memory and are not returned in runtime evidence.",
        "Each update is committed independently after a terminal body outcome or explicit skip.",
    ]


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
    """拉取更新并按 update id 逐条处理、确认和推进 offset。"""
    previous_offset = get_telegram_offset(db_path, bot_profile=bot_profile)
    request_offset = previous_offset + 1 if previous_offset > 0 else None
    get_result = client.get_updates(limit=limit, offset=request_offset, timeout_seconds=timeout_seconds)
    raw_updates = get_result.get("updates", []) if isinstance(get_result, dict) else []
    updates = [item for item in raw_updates if isinstance(item, dict)] if isinstance(raw_updates, list) else []
    seen_update_ids: set[int] = set()
    filtered_updates: list[dict[str, Any]] = []
    for item in sorted(updates, key=_update_id):
        item_update_id = _update_id(item)
        if item_update_id <= previous_offset or item_update_id in seen_update_ids:
            continue
        seen_update_ids.add(item_update_id)
        filtered_updates.append(item)
    skipped_duplicate_count = len(updates) - len(filtered_updates)
    runtime = _empty_runtime()
    new_offset = previous_offset
    attempted_update_count = 0
    committed_update_count = 0
    retryable_failure_count = 0

    if bool(get_result.get("success")):
        for item in filtered_updates:
            item_update_id = _update_id(item)
            attempted_update_count += 1
            try:
                current_runtime = process_intel_telegram_updates(
                    db_path,
                    updates=[item],
                    sender=sender,
                    now=now,
                )
            except Exception as exc:
                retryable_failure_count += 1
                runtime["processing_failures"].append(
                    {
                        "update_id_present": item_update_id > 0,
                        "reason": "runtime_exception",
                        "error_type": type(exc).__name__,
                    }
                )
                break
            _merge_runtime(runtime, current_runtime)
            handled_count = int(current_runtime.get("handled_count", 0) or 0)
            skipped_count = int(current_runtime.get("skipped_count", 0) or 0)
            delivery_terminal_count = int(current_runtime.get("delivery_terminal_count", 0) or 0)
            explicitly_skipped = handled_count == 0 and skipped_count == 1
            confirmed_terminal = handled_count == 1 and delivery_terminal_count == 1
            if not (explicitly_skipped or confirmed_terminal):
                retryable_failure_count += 1
                break
            persisted = set_telegram_offset(db_path, item_update_id, bot_profile=bot_profile)
            new_offset = max(new_offset, int(persisted["last_update_id"]))
            committed_update_count += 1

    _finalize_runtime_status(runtime)
    tracking_targets = runtime.get("tracking_targets", []) if isinstance(runtime.get("tracking_targets"), list) else []
    status = "failed" if not bool(get_result.get("success")) or retryable_failure_count else "success"
    if status == "success" and runtime.get("status") == "completed_with_warnings":
        status = "completed_with_warnings"
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
        "attempted_update_count": attempted_update_count,
        "committed_update_count": committed_update_count,
        "retryable_failure_count": retryable_failure_count,
        "skipped_duplicate_count": skipped_duplicate_count,
        "get_updates": _public_get_updates(get_result),
        "runtime": runtime,
        "tracking_targets": tracking_targets,
        "network_calls": int(get_result.get("network_calls", 0) or 0) + int(runtime.get("network_calls", 0) or 0),
        "raw_updates_persisted": False,
        "limits": [
            "Raw updates and chat ids are only used in memory and are not returned by this processor.",
            "Updates are sorted by update id and the offset advances after each terminal body outcome or explicit skip.",
            "Ambiguous or partial body delivery is committed as a warning so already-sent text is never replayed automatically.",
            "Callback-answer failure is auxiliary and never rolls back a terminal body delivery.",
        ],
    }
