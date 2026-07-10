"""Real Telegram update runner for Intel Brief.

This module wires the offset-safe update processor to real Bot API client and
sender.  It is intentionally gated: sendMessage requires explicit command-line
permission in addition to token and runtime ack.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.telegram_bot_runtime import TelegramBotApiRuntimeClient
from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE, TelegramBotApiSender, TelegramTransport
from src.intel.telegram_update_processor import DEFAULT_BOT_PROFILE, process_telegram_updates_once


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def build_real_update_runner_gate(
    env: dict[str, str] | None = None,
    *,
    allow_real_network: bool = False,
    allow_send_message: bool = False,
) -> dict[str, Any]:
    """Return redacted readiness decision for real update processing."""
    env_map = dict(env or {})
    token_present = bool(_clean(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN")))
    ack_ok = _clean(env_map.get("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK")) == TELEGRAM_SANDBOX_ACK_VALUE
    missing = []
    if not token_present:
        missing.append("telegram_bot_token_missing")
    if not ack_ok:
        missing.append("telegram_runtime_ack_missing")
    if not allow_real_network:
        missing.append("real_network_not_allowed")
    if not allow_send_message:
        missing.append("send_message_not_allowed")
    ready = not missing
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "missing_gates": missing,
        "redacted_env": {
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": token_present,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": ack_ok,
            "allow_real_network": bool(allow_real_network),
            "allow_send_message": bool(allow_send_message),
        },
    }


def _redact_processor_for_evidence(processor: dict[str, Any]) -> dict[str, Any]:
    """Remove internal Telegram user identifiers before returning real-run evidence."""
    redacted = json.loads(json.dumps(processor, ensure_ascii=False))
    runtime = redacted.get("runtime") if isinstance(redacted.get("runtime"), dict) else {}
    handled = runtime.get("handled_updates") if isinstance(runtime.get("handled_updates"), list) else []
    for item in handled:
        if not isinstance(item, dict):
            continue
        value = item.pop("subscriber_user_id", "")
        item["subscriber_user_id_present"] = bool(_clean(value) or item.get("subscriber_user_id_present"))
    return redacted


def _blocked_result(*, db_path: str | Path, gate: dict[str, Any], bot_profile: str) -> dict[str, Any]:
    return {
        "timestamp": _now_iso(),
        "phase": "AE-telegram-real-update-runner",
        "scope": "real_telegram_updates_to_intel_handler_and_sendmessage",
        "status": "blocked",
        "db_path": str(db_path),
        "bot_profile": _clean(bot_profile) or DEFAULT_BOT_PROFILE,
        "gate": gate,
        "processor": None,
        "network_calls": 0,
        "send_message_attempted": False,
        "raw_updates_persisted": False,
        "limits": [
            "No Telegram Bot API call unless token, ack, real network, and sendMessage gates are all present.",
            "Raw updates/chat ids/user ids/message text are not written to evidence.",
        ],
    }


def run_real_update_processor_once(
    *,
    db_path: str | Path,
    env: dict[str, str],
    allow_real_network: bool,
    allow_send_message: bool,
    now: str,
    transport: TelegramTransport | None = None,
    bot_profile: str = DEFAULT_BOT_PROFILE,
    limit: int = 20,
    timeout_seconds: int = 0,
) -> dict[str, Any]:
    """Run one gated real-update processing cycle and return redacted evidence."""
    gate = build_real_update_runner_gate(env, allow_real_network=allow_real_network, allow_send_message=allow_send_message)
    if not gate["ready"]:
        return _blocked_result(db_path=db_path, gate=gate, bot_profile=bot_profile)

    token = _clean(env.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN"))
    client = TelegramBotApiRuntimeClient(token=token, transport=transport)
    sender = TelegramBotApiSender(token=token, transport=transport)
    processor = process_telegram_updates_once(
        db_path,
        client=client,
        sender=sender,
        now=now,
        bot_profile=bot_profile,
        limit=limit,
        timeout_seconds=timeout_seconds,
    )
    public_processor = _redact_processor_for_evidence(processor)
    handled_count = int((public_processor.get("runtime") or {}).get("handled_count", 0) or 0)
    send_success_count = int((public_processor.get("runtime") or {}).get("send_success_count", 0) or 0)
    status = str(public_processor.get("status") or "failed")
    if status == "success" and handled_count == 0:
        status = "no_new_updates"
    return {
        "timestamp": _now_iso(),
        "phase": "AE-telegram-real-update-runner",
        "scope": "real_telegram_updates_to_intel_handler_and_sendmessage",
        "status": status,
        "db_path": str(db_path),
        "bot_profile": _clean(bot_profile) or DEFAULT_BOT_PROFILE,
        "gate": gate,
        "processor": public_processor,
        "network_calls": int(public_processor.get("network_calls", 0) or 0),
        "send_message_attempted": handled_count > 0,
        "send_success_count": send_success_count,
        "raw_updates_persisted": False,
        "limits": [
            "Processes only updates above the persisted Telegram offset.",
            "Raw updates/chat ids/user ids/message text are not written to evidence.",
            "sendMessage is allowed only by explicit runtime gate and results are redacted.",
        ],
    }


def build_real_update_runner_evidence(
    *,
    db_path: str | Path,
    evidence_path: str | Path,
    env: dict[str, str],
    allow_real_network: bool,
    allow_send_message: bool,
    now: str,
    transport: TelegramTransport | None = None,
    bot_profile: str = DEFAULT_BOT_PROFILE,
    limit: int = 20,
    timeout_seconds: int = 0,
) -> dict[str, Any]:
    """Run one cycle and write redacted evidence JSON."""
    result = run_real_update_processor_once(
        db_path=db_path,
        env=env,
        allow_real_network=allow_real_network,
        allow_send_message=allow_send_message,
        now=now,
        transport=transport,
        bot_profile=bot_profile,
        limit=limit,
        timeout_seconds=timeout_seconds,
    )
    path = Path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
