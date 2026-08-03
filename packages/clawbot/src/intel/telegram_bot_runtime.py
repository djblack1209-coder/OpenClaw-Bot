"""Telegram Bot API runtime probe for Intel Brief.

This module covers low-risk Bot API runtime operations required before wiring a
real bot loop: command registration and update retrieval.  Raw updates are kept
in memory for callers but never persisted by the probe evidence.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.subscriptions import telegram_commands_for_language
from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE, TelegramTransport

TELEGRAM_API_ENDPOINT_TEMPLATE = "https://api.telegram.org/bot{token}/{method}"


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


def intel_brief_bot_commands(language_code: str = "") -> list[dict[str, str]]:
    """Return Telegram Bot API command definitions for Intel Brief."""
    language = "en" if _clean(language_code).lower().startswith("en") else "zh"
    return telegram_commands_for_language(language)


def build_bot_runtime_gate(
    env: dict[str, str] | None = None,
    *,
    allow_real_network: bool = False,
) -> dict[str, Any]:
    """Build a redacted gate for Bot API runtime probes."""
    env_map = dict(os.environ if env is None else env)
    token_present = bool(_clean(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN")))
    ack_ok = _clean(env_map.get("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK")) == TELEGRAM_SANDBOX_ACK_VALUE
    missing = []
    if not token_present:
        missing.append("telegram_bot_token_missing")
    if not ack_ok:
        missing.append("telegram_runtime_ack_missing")
    if not allow_real_network:
        missing.append("real_network_not_allowed")
    ready = not missing
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "missing_gates": missing,
        "redacted_env": {
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": token_present,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": ack_ok,
            "allow_real_network": bool(allow_real_network),
        },
    }


class TelegramBotApiRuntimeClient:
    """Small Bot API client for command registration and update retrieval."""

    def __init__(self, *, token: str, transport: TelegramTransport | None = None, timeout: int = 15) -> None:
        self.token = _clean(token)
        self.transport = transport or _default_transport
        self.network_label = "injected_transport" if transport is not None else "real_http"
        self.timeout = int(timeout)
        self.network_calls = 0

    def _method(self, method: str, payload: dict[str, object]) -> dict[str, Any]:
        url = TELEGRAM_API_ENDPOINT_TEMPLATE.format(token=self.token, method=method)
        self.network_calls += 1
        try:
            response = self.transport(url, payload, self.timeout)
        except Exception as exc:
            return {"ok": False, "description": str(exc)[:300]}
        return response if isinstance(response, dict) else {"ok": False, "description": "non_json_response"}

    def set_my_commands(
        self,
        commands: list[dict[str, str]] | None = None,
        *,
        language_code: str = "",
    ) -> dict[str, Any]:
        command_list = commands or intel_brief_bot_commands(language_code)
        payload: dict[str, object] = {"commands": command_list}
        normalized_language = _clean(language_code).lower()
        if normalized_language:
            payload["language_code"] = normalized_language
        response = self._method("setMyCommands", payload)
        return {
            "success": bool(response.get("ok")),
            "method": "setMyCommands",
            "network": self.network_label,
            "network_calls": self.network_calls,
            "command_count": len(command_list),
            "language_code": normalized_language or "default",
            "error_code": _clean(response.get("error_code")),
            "error": _clean(response.get("description"))[:300],
        }

    def set_localized_commands(self) -> dict[str, Any]:
        """注册 default、zh、en 三套原生命令菜单。"""
        results = [
            self.set_my_commands(intel_brief_bot_commands("zh")),
            self.set_my_commands(intel_brief_bot_commands("zh"), language_code="zh"),
            self.set_my_commands(intel_brief_bot_commands("en"), language_code="en"),
        ]
        return {
            "success": all(bool(item.get("success")) for item in results),
            "method": "setMyCommands",
            "network": self.network_label,
            "network_calls": self.network_calls,
            "command_count": len(intel_brief_bot_commands()),
            "language_scope_count": len(results),
            "languages": [str(item.get("language_code")) for item in results],
            "results": results,
            "error_code": next((_clean(item.get("error_code")) for item in results if item.get("error_code")), ""),
            "error": next((_clean(item.get("error")) for item in results if item.get("error")), ""),
        }

    def get_updates(
        self,
        *,
        limit: int = 20,
        offset: int | None = None,
        timeout_seconds: int = 0,
    ) -> dict[str, Any]:
        payload: dict[str, object] = {
            "limit": int(limit),
            "timeout": int(timeout_seconds),
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = int(offset)
        response = self._method("getUpdates", payload)
        updates_raw = response.get("result", []) if isinstance(response, dict) else []
        updates = updates_raw if isinstance(updates_raw, list) else []
        redacted = _redact_updates(updates)
        return {
            "success": bool(response.get("ok")) if isinstance(response, dict) else False,
            "method": "getUpdates",
            "network": self.network_label,
            "network_calls": self.network_calls,
            "update_count": len(updates),
            "command_update_count": redacted["command_update_count"],
            "max_update_id_present": redacted["max_update_id_present"],
            "redacted": redacted,
            "updates": updates,
            "error_code": _clean(response.get("error_code")) if isinstance(response, dict) else "",
            "error": _clean(response.get("description"))[:300] if isinstance(response, dict) else "",
        }


def _message_from_update(update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message")
    return message if isinstance(message, dict) else {}


def _callback_from_update(update: dict[str, Any]) -> dict[str, Any]:
    callback = update.get("callback_query")
    return callback if isinstance(callback, dict) else {}


def _redact_updates(updates: list[dict[str, Any]]) -> dict[str, Any]:
    command_count = 0
    callback_count = 0
    private_count = 0
    latest_update_id_present = False
    for update in updates:
        if not isinstance(update, dict):
            continue
        latest_update_id_present = latest_update_id_present or update.get("update_id") not in (None, "")
        callback = _callback_from_update(update)
        if callback:
            callback_count += 1
            message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
            chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        else:
            message = _message_from_update(update)
            text = _clean(message.get("text"))
            if text.startswith("/"):
                command_count += 1
            chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        if isinstance(chat, dict) and _clean(chat.get("type")) == "private":
            private_count += 1
    return {
        "update_count": len(updates),
        "command_update_count": command_count,
        "callback_query_update_count": callback_count,
        "private_chat_update_count": private_count,
        "max_update_id_present": latest_update_id_present,
        "chat_id_values_persisted": False,
        "message_text_values_persisted": False,
    }


def _public_get_updates_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": bool(result.get("success")),
        "method": "getUpdates",
        "network": _clean(result.get("network")),
        "network_calls": int(result.get("network_calls", 0) or 0),
        "update_count": int(result.get("update_count", 0) or 0),
        "command_update_count": int(result.get("command_update_count", 0) or 0),
        "max_update_id_present": bool(result.get("max_update_id_present")),
        "redacted": result.get("redacted", {}),
        "error_code": _clean(result.get("error_code")),
        "error": _clean(result.get("error")),
    }


def build_telegram_bot_runtime_probe(
    *,
    evidence_path: str | Path,
    env: dict[str, str] | None = None,
    allow_real_network: bool = False,
    transport: TelegramTransport | None = None,
    limit: int = 20,
    timeout_seconds: int = 0,
    set_commands: bool = True,
) -> dict[str, Any]:
    """Write redacted evidence for setMyCommands + getUpdates Bot API readiness."""
    env_map = dict(os.environ if env is None else env)
    gate = build_bot_runtime_gate(env_map, allow_real_network=allow_real_network)
    status = "blocked"
    set_result: dict[str, Any] | None = None
    updates_result: dict[str, Any] | None = None
    network_calls = 0

    if gate["ready"]:
        client = TelegramBotApiRuntimeClient(
            token=_clean(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN")),
            transport=transport,
        )
        if set_commands:
            set_result = client.set_localized_commands()
        updates_internal = client.get_updates(limit=limit, timeout_seconds=timeout_seconds)
        updates_result = _public_get_updates_result(updates_internal)
        network_calls = int(client.network_calls)
        status = (
            "success" if (not set_result or set_result.get("success")) and updates_result.get("success") else "failed"
        )

    payload = {
        "timestamp": _now_iso(),
        "phase": "AB-telegram-bot-api-runtime-probe",
        "scope": "telegram_set_my_commands_and_get_updates_runtime_readiness",
        "status": status,
        "gate": gate,
        "commands": {
            "bot_profile": "intel_brief_bot",
            "command_count": len(intel_brief_bot_commands()),
            "commands": intel_brief_bot_commands(),
        },
        "set_my_commands": set_result,
        "get_updates": updates_result,
        "raw_updates_persisted": False,
        "network_calls": network_calls,
        "limits": [
            "Token is never written to evidence; only boolean presence is recorded.",
            "Raw updates, chat ids, user ids, and message text are not persisted in evidence.",
            "No sendMessage call is made by this probe.",
            "No scheduler/cron/systemd registration, production DB write, payment/Xianyu call, scraper call, or worker mutation.",
        ],
    }
    path = Path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
