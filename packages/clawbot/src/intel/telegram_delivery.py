"""Intel Brief Telegram Bot API contract layer.

This module prepares the real Telegram delivery path without requiring a real
token during development.  It is intentionally evidence-first: gates are
redacted, transports are injectable, and default probes do not call the network.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.delivery import build_delivery_message

TELEGRAM_SANDBOX_ACK_VALUE = "I_UNDERSTAND_TELEGRAM_SANDBOX_SEND"
TELEGRAM_SEND_ENDPOINT_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_ANSWER_CALLBACK_ENDPOINT_TEMPLATE = "https://api.telegram.org/bot{token}/answerCallbackQuery"

TelegramTransport = Callable[[str, dict[str, object], int], dict[str, Any]]


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


def build_telegram_sandbox_gate(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return a redacted readiness decision for one real Telegram sandbox send."""
    env_map = dict(os.environ if env is None else env)
    token_present = bool(_clean(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN")))
    chat_present = bool(_clean(env_map.get("INTEL_BRIEF_TELEGRAM_CHAT_ID")))
    ack_ok = _clean(env_map.get("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK")) == TELEGRAM_SANDBOX_ACK_VALUE
    missing = []
    if not token_present:
        missing.append("telegram_bot_token_missing")
    if not chat_present:
        missing.append("telegram_chat_id_missing")
    if not ack_ok:
        missing.append("sandbox_send_ack_missing")
    ready = not missing
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "missing_gates": missing,
        "redacted_env": {
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": token_present,
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": chat_present,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": ack_ok,
        },
    }


class TelegramBotApiSender:
    """Small Telegram Bot API sender with injectable transport for tests/evidence."""

    provider = "telegram_bot_api"

    def __init__(self, *, token: str, transport: TelegramTransport | None = None, timeout: int = 15) -> None:
        self.token = _clean(token)
        self.network_label = "injected_transport" if transport is not None else "real_http"
        self.transport = transport or _default_transport
        self.timeout = int(timeout)
        self.network_calls = 0

    def send(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        endpoint = TELEGRAM_SEND_ENDPOINT_TEMPLATE.format(token=self.token)
        payload: dict[str, object] = {
            "chat_id": _clean(chat_id),
            "text": str(text or ""),
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        self.network_calls += 1
        try:
            response = self.transport(endpoint, payload, self.timeout)
        except Exception as exc:
            return {
                "timestamp": _now_iso(),
                "provider": self.provider,
                "success": False,
                "network": self.network_label,
                "network_calls": self.network_calls,
                "endpoint": "https://api.telegram.org/bot***/sendMessage",
                "chat_id_present": bool(_clean(chat_id)),
                "parse_mode": parse_mode,
                "text_chars": len(str(text or "")),
                "reply_markup_present": bool(reply_markup),
                "message_id": "",
                "error": str(exc)[:300],
            }
        result = response.get("result", {}) if isinstance(response, dict) else {}
        message_id = result.get("message_id") if isinstance(result, dict) else ""
        return {
            "timestamp": _now_iso(),
            "provider": self.provider,
            "success": bool(response.get("ok")) if isinstance(response, dict) else False,
            "network": self.network_label,
            "network_calls": self.network_calls,
            "endpoint": "https://api.telegram.org/bot***/sendMessage",
            "chat_id_present": bool(_clean(chat_id)),
            "parse_mode": parse_mode,
            "text_chars": len(str(text or "")),
            "reply_markup_present": bool(reply_markup),
            "message_id": str(message_id or ""),
            "error_code": response.get("error_code", "") if isinstance(response, dict) else "",
            "error": _clean(response.get("description") if isinstance(response, dict) else "")[:300],
        }

    def answer_callback_query(self, callback_query_id: str, *, text: str = "") -> dict[str, Any]:
        endpoint = TELEGRAM_ANSWER_CALLBACK_ENDPOINT_TEMPLATE.format(token=self.token)
        payload: dict[str, object] = {"callback_query_id": _clean(callback_query_id)}
        if _clean(text):
            payload["text"] = _clean(text)
        self.network_calls += 1
        try:
            response = self.transport(endpoint, payload, self.timeout)
        except Exception as exc:
            return {
                "timestamp": _now_iso(),
                "provider": self.provider,
                "method": "answerCallbackQuery",
                "success": False,
                "network": self.network_label,
                "network_calls": self.network_calls,
                "endpoint": "https://api.telegram.org/bot***/answerCallbackQuery",
                "callback_query_id_present": bool(_clean(callback_query_id)),
                "text_present": bool(_clean(text)),
                "error": str(exc)[:300],
            }
        return {
            "timestamp": _now_iso(),
            "provider": self.provider,
            "method": "answerCallbackQuery",
            "success": bool(response.get("ok")) if isinstance(response, dict) else False,
            "network": self.network_label,
            "network_calls": self.network_calls,
            "endpoint": "https://api.telegram.org/bot***/answerCallbackQuery",
            "callback_query_id_present": bool(_clean(callback_query_id)),
            "text_present": bool(_clean(text)),
            "error_code": response.get("error_code", "") if isinstance(response, dict) else "",
            "error": _clean(response.get("description") if isinstance(response, dict) else "")[:300],
        }


def build_telegram_sandbox_probe(
    *,
    evidence_path: str | Path,
    env: dict[str, str] | None = None,
    message: str = "Intel Brief Telegram sandbox probe",
    transport: TelegramTransport | None = None,
    allow_real_network: bool = False,
) -> dict[str, Any]:
    """Write evidence for the Telegram sandbox send gate/contract."""
    env_map = dict(os.environ if env is None else env)
    gate = build_telegram_sandbox_gate(env_map)
    send_result: dict[str, Any] | None = None
    status = "blocked"
    network_calls = 0

    if gate["ready"]:
        if transport is None and not allow_real_network:
            gate = {
                **gate,
                "status": "blocked",
                "ready": False,
                "missing_gates": [*gate["missing_gates"], "real_network_not_allowed"],
            }
        else:
            sender = TelegramBotApiSender(
                token=_clean(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN")),
                transport=transport,
            )
            send_result = sender.send(
                _clean(env_map.get("INTEL_BRIEF_TELEGRAM_CHAT_ID")),
                message,
            )
            network_calls = sender.network_calls
            status = "success" if send_result.get("success") else "failed"

    payload = {
        "timestamp": _now_iso(),
        "phase": "K-telegram-sandbox-contract",
        "scope": "telegram_bot_api_gate_and_sender_contract",
        "status": status,
        "gate": gate,
        "send_result": send_result,
        "network_calls": network_calls,
        "limits": [
            "No Telegram Bot API call unless gate is ready and network is explicitly allowed.",
            "Token and chat id are never written to evidence; only boolean presence is recorded.",
            "Injected transports may be used for contract verification without real network.",
            "No scheduler/cron/systemd registration or production DB write.",
        ],
    }
    path = Path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def build_telegram_summary_delivery_probe(
    *,
    summary_evidence_path: str | Path,
    evidence_path: str | Path,
    env: dict[str, str] | None = None,
    transport: TelegramTransport | None = None,
    allow_real_network: bool = False,
) -> dict[str, Any]:
    """Render a real Intel Brief summary evidence and probe Telegram delivery."""
    summary_path = Path(summary_evidence_path)
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    message = build_delivery_message(summary_payload)
    env_map = dict(os.environ if env is None else env)
    gate = build_telegram_sandbox_gate(env_map)
    send_result: dict[str, Any] | None = None
    status = "blocked"
    network_calls = 0

    if gate["ready"]:
        if transport is None and not allow_real_network:
            gate = {
                **gate,
                "status": "blocked",
                "ready": False,
                "missing_gates": [*gate["missing_gates"], "real_network_not_allowed"],
            }
        else:
            sender = TelegramBotApiSender(
                token=_clean(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN")),
                transport=transport,
            )
            send_result = sender.send(
                _clean(env_map.get("INTEL_BRIEF_TELEGRAM_CHAT_ID")),
                message,
            )
            network_calls = sender.network_calls
            status = "success" if send_result.get("success") else "failed"

    payload = {
        "timestamp": _now_iso(),
        "phase": "L-pre-telegram-summary-delivery",
        "scope": "intel_summary_evidence_to_telegram_sandbox_delivery",
        "status": status,
        "summary_evidence": str(summary_path),
        "gate": gate,
        "message_preview": {
            "text_chars": len(message),
            "text_head": message[:240],
        },
        "send_result": send_result,
        "network_calls": network_calls,
        "limits": [
            "Uses real Intel Brief summary evidence to render the Telegram message.",
            "No Telegram Bot API call unless gate is ready and network is explicitly allowed.",
            "Token and chat id are never written to evidence; only boolean presence is recorded.",
            "Injected transports may be used for contract verification without real network.",
            "No scheduler/cron/systemd registration or production DB write.",
        ],
    }
    path = Path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
