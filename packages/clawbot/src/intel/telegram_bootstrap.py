"""Local Telegram sandbox bootstrap for Intel Brief.

This helper closes the gap between "the user has Telegram installed" and "we
have a verified sandbox chat id" without writing token/chat id material to
evidence.  It is intentionally gated: no Bot API network call happens unless a
token is present, an explicit sandbox acknowledgement is present, and the
caller allows real network.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.delivery import build_delivery_message
from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE, TelegramBotApiSender, TelegramTransport

TELEGRAM_API_ENDPOINT_TEMPLATE = "https://api.telegram.org/bot{token}/{method}"
DEFAULT_START_PAYLOAD = "intel_brief_sandbox"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _default_transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {"ok": False, "description": "empty_response"}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"ok": False, "error_code": exc.code, "description": body[:300]}
    except urllib.error.URLError as exc:
        return {"ok": False, "description": str(exc.reason)[:300]}


def _telegram_method(
    *,
    token: str,
    method: str,
    payload: dict[str, object] | None = None,
    transport: TelegramTransport | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    url = TELEGRAM_API_ENDPOINT_TEMPLATE.format(token=token, method=method)
    return (transport or _default_transport)(url, payload or {}, timeout)


def _message_from_update(update: dict[str, Any]) -> tuple[dict[str, Any], str]:
    for key in ("message", "edited_message", "channel_post"):
        message = update.get(key)
        if isinstance(message, dict):
            return message, key
    return {}, ""


def find_chat_candidate(updates: list[dict[str, Any]], *, start_payload: str = DEFAULT_START_PAYLOAD) -> dict[str, Any]:
    """Find the best chat id candidate from Telegram getUpdates payload.

    The returned mapping may contain the raw ``chat_id`` for immediate in-memory
    sending.  Callers must redact it before writing any evidence.
    """
    fallback: dict[str, Any] | None = None
    expected_start = f"/start {start_payload}".strip()
    for update in reversed([item for item in updates if isinstance(item, dict)]):
        message, message_key = _message_from_update(update)
        chat = message.get("chat") if isinstance(message, dict) else {}
        if not isinstance(chat, dict):
            continue
        chat_id = chat.get("id")
        if chat_id in (None, ""):
            continue
        text = _clean(message.get("text"))
        candidate = {
            "chat_id": str(chat_id),
            "chat_type": _clean(chat.get("type")) or "unknown",
            "update_id": update.get("update_id"),
            "message_key": message_key,
            "matched_start_payload": text == expected_start,
            "message_text_kind": "matching_start" if text == expected_start else ("start" if text.startswith("/start") else "other"),
        }
        if candidate["matched_start_payload"]:
            return candidate
        if fallback is None:
            fallback = candidate
    return fallback or {}


def _redact_chat_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(candidate.get("chat_id")),
        "chat_type": _clean(candidate.get("chat_type")),
        "matched_start_payload": bool(candidate.get("matched_start_payload")),
        "message_text_kind": _clean(candidate.get("message_text_kind")),
        "update_id_present": candidate.get("update_id") not in (None, ""),
    }


def _open_telegram_deep_link(bot_username: str, start_payload: str) -> dict[str, Any]:
    username = _clean(bot_username).lstrip("@")
    if not username:
        return {"attempted": False, "success": False, "reason": "bot_username_missing"}
    url = f"tg://resolve?domain={username}&start={start_payload}"
    try:
        completed = subprocess.run(["open", url], check=False, capture_output=True, text=True, timeout=10)
    except Exception as exc:  # pragma: no cover - platform-specific
        return {"attempted": True, "success": False, "reason": str(exc)[:200]}
    return {
        "attempted": True,
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "reason": "" if completed.returncode == 0 else (completed.stderr or completed.stdout)[:200],
    }


def _bootstrap_missing_gates(*, token: str, ack: str, allow_real_network: bool) -> list[str]:
    missing = []
    if not _clean(token):
        missing.append("telegram_bot_token_missing")
    if _clean(ack) != TELEGRAM_SANDBOX_ACK_VALUE:
        missing.append("sandbox_send_ack_missing")
    if not allow_real_network:
        missing.append("real_network_not_allowed")
    return missing


def build_telegram_local_bootstrap_probe(
    *,
    token: str,
    bot_username: str,
    summary_evidence_path: str | Path,
    evidence_path: str | Path,
    ack: str = "",
    allow_real_network: bool = False,
    open_deep_link: bool = True,
    start_payload: str = DEFAULT_START_PAYLOAD,
    transport: TelegramTransport | None = None,
    timeout: int = 15,
    wait_seconds: int = 0,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    """Discover a sandbox Telegram chat and send a real summary message.

    Evidence never includes the token, raw chat id, Bot API URL, or bot numeric
    id.  If the user has not yet sent `/start <payload>` to the bot, the report
    remains blocked with a redacted reason.
    """
    token_clean = _clean(token)
    summary_path = Path(summary_evidence_path)
    message = build_delivery_message(json.loads(summary_path.read_text(encoding="utf-8")))
    missing = _bootstrap_missing_gates(token=token_clean, ack=ack, allow_real_network=allow_real_network)
    status = "blocked" if missing else "failed"
    network_calls = 0
    deep_link = {"attempted": False, "success": False, "reason": "not_requested"}
    get_me: dict[str, Any] | None = None
    updates_result: dict[str, Any] | None = None
    chat_candidate_internal: dict[str, Any] = {}
    send_result: dict[str, Any] | None = None

    if not missing:
        if open_deep_link:
            deep_link = _open_telegram_deep_link(bot_username, start_payload)
        get_me_response = _telegram_method(
            token=token_clean,
            method="getMe",
            transport=transport,
            timeout=timeout,
        )
        network_calls += 1
        get_me_payload = get_me_response.get("result", {}) if isinstance(get_me_response, dict) else {}
        get_me_username = _clean(get_me_payload.get("username") if isinstance(get_me_payload, dict) else "")
        expected_username = _clean(bot_username).lstrip("@")
        get_me = {
            "success": bool(get_me_response.get("ok")) if isinstance(get_me_response, dict) else False,
            "username": get_me_username,
            "username_matches": bool(get_me_username and expected_username and get_me_username.lower() == expected_username.lower()),
            "bot_id_present": bool(get_me_payload.get("id")) if isinstance(get_me_payload, dict) else False,
            "error_code": get_me_response.get("error_code", "") if isinstance(get_me_response, dict) else "",
            "error": _clean(get_me_response.get("description") if isinstance(get_me_response, dict) else "")[:300],
        }
        if not get_me["success"]:
            missing.append("telegram_get_me_failed")
            status = "failed"
        else:
            deadline = time.monotonic() + max(0, int(wait_seconds))
            attempts = 0
            updates: list[dict[str, Any]] = []
            get_updates_response: dict[str, Any] = {}
            while True:
                attempts += 1
                get_updates_response = _telegram_method(
                    token=token_clean,
                    method="getUpdates",
                    payload={"limit": 20, "timeout": 0, "allowed_updates": ["message"]},
                    transport=transport,
                    timeout=timeout,
                )
                network_calls += 1
                updates_raw = get_updates_response.get("result", []) if isinstance(get_updates_response, dict) else []
                updates = updates_raw if isinstance(updates_raw, list) else []
                chat_candidate_internal = find_chat_candidate(updates, start_payload=start_payload)
                if chat_candidate_internal.get("chat_id"):
                    break
                updates_ok = bool(get_updates_response.get("ok")) if isinstance(get_updates_response, dict) else False
                if not updates_ok:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(max(0.0, float(poll_interval_seconds)))
            updates_result = {
                "success": bool(get_updates_response.get("ok")) if isinstance(get_updates_response, dict) else False,
                "update_count": len(updates),
                "attempts": attempts,
                "wait_seconds": max(0, int(wait_seconds)),
                "error_code": get_updates_response.get("error_code", "") if isinstance(get_updates_response, dict) else "",
                "error": _clean(get_updates_response.get("description") if isinstance(get_updates_response, dict) else "")[:300],
            }
            if not updates_result["success"]:
                missing.append("telegram_get_updates_failed")
                status = "failed"
            elif not chat_candidate_internal.get("chat_id"):
                missing.append("telegram_chat_id_not_discovered")
                status = "blocked"
            else:
                sender = TelegramBotApiSender(token=token_clean, transport=transport, timeout=timeout)
                send_result = sender.send(str(chat_candidate_internal["chat_id"]), message)
                network_calls += sender.network_calls
                if send_result.get("success"):
                    status = "success"
                else:
                    status = "failed"
                    missing.append("telegram_send_failed")

    payload = {
        "timestamp": _now_iso(),
        "phase": "L-real-telegram-local-bootstrap",
        "scope": "telegram_local_start_chat_discovery_and_summary_sandbox_send",
        "status": status,
        "bot_username": _clean(bot_username).lstrip("@"),
        "start_payload": start_payload,
        "summary_evidence": str(summary_path),
        "bootstrap_gate": {
            "ready": not _bootstrap_missing_gates(token=token_clean, ack=ack, allow_real_network=allow_real_network),
            "redacted_env": {
                "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": bool(token_clean),
                "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": _clean(ack) == TELEGRAM_SANDBOX_ACK_VALUE,
                "allow_real_network": bool(allow_real_network),
            },
        },
        "missing_gates": sorted(dict.fromkeys(missing)),
        "deep_link": deep_link,
        "get_me": get_me,
        "get_updates": updates_result,
        "chat_candidate": _redact_chat_candidate(chat_candidate_internal),
        "message_preview": {"text_chars": len(message), "text_head": message[:240]},
        "send_result": send_result,
        "network_calls": network_calls,
        "limits": [
            "Token and chat id are never written to evidence; only presence and redacted delivery result are recorded.",
            "No Telegram Bot API call unless token, sandbox ack, and allow_real_network are all present.",
            "The user must send /start with the bootstrap payload before chat discovery can succeed.",
            "No scheduler/cron/systemd registration, production DB write, or persistent worker creation.",
        ],
    }
    path = Path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def token_from_env_or_prompt(env: dict[str, str] | None = None) -> str:
    env_map = dict(os.environ if env is None else env)
    token = _clean(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN"))
    if token:
        return token
    import getpass

    return _clean(getpass.getpass("INTEL_BRIEF_TELEGRAM_BOT_TOKEN (hidden, not saved): "))
