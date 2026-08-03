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
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.delivery import build_delivery_message
from src.intel.telegram_brief_renderer import DeliveryEnvelope

TELEGRAM_SANDBOX_ACK_VALUE = "I_UNDERSTAND_TELEGRAM_SANDBOX_SEND"
TELEGRAM_SEND_ENDPOINT_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_SEND_PHOTO_ENDPOINT_TEMPLATE = "https://api.telegram.org/bot{token}/sendPhoto"
TELEGRAM_ANSWER_CALLBACK_ENDPOINT_TEMPLATE = "https://api.telegram.org/bot{token}/answerCallbackQuery"

TelegramTransport = Callable[[str, dict[str, object], int], dict[str, Any]]
TelegramMultipartTransport = Callable[[str, dict[str, object], Path, int], dict[str, Any]]


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


def _default_multipart_transport(
    url: str,
    payload: dict[str, object],
    photo_path: Path,
    timeout: int,
) -> dict[str, Any]:
    """用标准库构建 Telegram sendPhoto multipart 请求。"""
    boundary = f"----OpenClawIntel{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in payload.items():
        serialized = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                serialized.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (f'Content-Disposition: form-data; name="photo"; filename="{photo_path.name}"\r\n').encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            photo_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        url,
        data=b"".join(chunks),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
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

    def __init__(
        self,
        *,
        token: str,
        transport: TelegramTransport | None = None,
        multipart_transport: TelegramMultipartTransport | None = None,
        timeout: int = 15,
    ) -> None:
        self.token = _clean(token)
        self.network_label = "injected_transport" if transport is not None else "real_http"
        self.transport = transport or _default_transport
        self.multipart_transport = multipart_transport or _default_multipart_transport
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
                "ambiguous_delivery": True,
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
            "ambiguous_delivery": bool(isinstance(response, dict) and int(response.get("error_code") or 0) >= 500),
        }

    def send_photo(
        self,
        chat_id: str,
        photo: str,
        *,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """发送或上传封面，并暴露同一 Bot 可复用的最大尺寸 file_id。"""
        endpoint = TELEGRAM_SEND_PHOTO_ENDPOINT_TEMPLATE.format(token=self.token)
        payload: dict[str, object] = {
            "chat_id": _clean(chat_id),
            "caption": str(caption or ""),
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        photo_path = Path(str(photo or ""))
        self.network_calls += 1
        try:
            if photo_path.is_file():
                response = self.multipart_transport(endpoint, payload, photo_path, self.timeout)
            else:
                response = self.transport(endpoint, {**payload, "photo": str(photo or "")}, self.timeout)
        except Exception as exc:
            return {
                "timestamp": _now_iso(),
                "provider": self.provider,
                "success": False,
                "network": self.network_label,
                "network_calls": self.network_calls,
                "endpoint": "https://api.telegram.org/bot***/sendPhoto",
                "chat_id_present": bool(_clean(chat_id)),
                "caption_chars": len(str(caption or "")),
                "reply_markup_present": bool(reply_markup),
                "message_id": "",
                "photo_file_id": "",
                "photo_file_unique_id": "",
                "ambiguous_delivery": True,
                "error": str(exc)[:300],
            }
        result = response.get("result", {}) if isinstance(response, dict) else {}
        photos = result.get("photo", []) if isinstance(result, dict) else []
        photo_sizes = [item for item in photos if isinstance(item, dict)] if isinstance(photos, list) else []
        largest = max(
            photo_sizes,
            key=lambda item: (
                int(item.get("file_size") or 0),
                int(item.get("width") or 0) * int(item.get("height") or 0),
            ),
            default={},
        )
        error_code = int(response.get("error_code") or 0) if isinstance(response, dict) else 0
        return {
            "timestamp": _now_iso(),
            "provider": self.provider,
            "success": bool(response.get("ok")) if isinstance(response, dict) else False,
            "network": self.network_label,
            "network_calls": self.network_calls,
            "endpoint": "https://api.telegram.org/bot***/sendPhoto",
            "chat_id_present": bool(_clean(chat_id)),
            "caption_chars": len(str(caption or "")),
            "reply_markup_present": bool(reply_markup),
            "message_id": str(result.get("message_id") or "") if isinstance(result, dict) else "",
            "photo_file_id": str(largest.get("file_id") or ""),
            "photo_file_unique_id": str(largest.get("file_unique_id") or ""),
            "error_code": error_code or "",
            "error": _clean(response.get("description") if isinstance(response, dict) else "")[:300],
            "ambiguous_delivery": error_code >= 500,
        }

    def send_rich_message(
        self,
        chat_id: str,
        envelope: DeliveryEnvelope,
        *,
        photo: str = "",
    ) -> dict[str, Any]:
        """官方 Bot API 无此方法，本地拒绝后交给 sendPhoto 降级。"""
        return {
            "success": False,
            "endpoint": "unsupported://telegram/sendRichMessage",
            "network": self.network_label,
            "network_calls": self.network_calls,
            "chat_id_present": bool(_clean(chat_id)),
            "photo_present": bool(_clean(photo)),
            "message_id": "",
            "error_code": 404,
            "error": "telegram_send_rich_message_unsupported",
            "ambiguous_delivery": False,
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


def _attempt_view(method: str, result: dict[str, Any]) -> dict[str, Any]:
    """保留投递诊断字段，同时去掉 chat_id 与媒体 file_id。"""
    return {
        "method": method,
        "success": bool(result.get("success")),
        "endpoint": _clean(result.get("endpoint")),
        "message_id": _clean(result.get("message_id")),
        "error_code": result.get("error_code", ""),
        "error": _clean(result.get("error"))[:300],
        "ambiguous_delivery": bool(result.get("ambiguous_delivery")),
    }


def _invalid_cached_photo_reference(result: dict[str, Any]) -> bool:
    """识别 Telegram 对过期或跨 Bot file_id 的明确拒绝。"""
    if int(result.get("error_code") or 0) != 400:
        return False
    error = _clean(result.get("error")).casefold()
    return any(marker in error for marker in ("file_id", "file identifier", "wrong file", "invalid file"))


def send_delivery_envelope(
    sender: Any,
    *,
    chat_id: str,
    envelope: DeliveryEnvelope,
    photo: str = "",
    prefer_rich: bool = False,
) -> dict[str, Any]:
    """按 Rich→Photo→Text 投递，并在结果不确定时停止防重复。"""
    before = int(getattr(sender, "network_calls", 0) or 0)
    attempts: list[dict[str, Any]] = []
    message_ids: list[str] = []

    if prefer_rich and hasattr(sender, "send_rich_message"):
        rich = sender.send_rich_message(chat_id, envelope, photo=photo)
        attempts.append(_attempt_view("sendRichMessage", rich))
        if rich.get("success"):
            if _clean(rich.get("message_id")):
                message_ids.append(_clean(rich.get("message_id")))
            return {
                "success": True,
                "delivery_state": "sent",
                "render_mode": "rich_message",
                "attempts": attempts,
                "message_ids": message_ids,
                "network_calls": int(getattr(sender, "network_calls", before) or before) - before,
                "error": "",
            }
        if rich.get("ambiguous_delivery"):
            return {
                "success": False,
                "delivery_state": "unknown",
                "render_mode": "rich_message",
                "attempts": attempts,
                "message_ids": [],
                "network_calls": int(getattr(sender, "network_calls", before) or before) - before,
                "error": _clean(rich.get("error")),
            }

    chosen_photo = photo or envelope.cover_path
    photo_reference_invalid = False
    if chosen_photo and hasattr(sender, "send_photo"):
        photo_result = sender.send_photo(
            chat_id,
            chosen_photo,
            caption=envelope.caption_html,
            parse_mode="HTML",
            reply_markup=envelope.reply_markup,
        )
        attempts.append(_attempt_view("sendPhoto", photo_result))
        if photo_result.get("success"):
            if _clean(photo_result.get("message_id")):
                message_ids.append(_clean(photo_result.get("message_id")))
            return {
                "success": True,
                "delivery_state": "sent",
                "render_mode": "photo",
                "attempts": attempts,
                "message_ids": message_ids,
                "network_calls": int(getattr(sender, "network_calls", before) or before) - before,
                "photo_file_id": _clean(photo_result.get("photo_file_id")),
                "photo_file_unique_id": _clean(photo_result.get("photo_file_unique_id")),
                "error": "",
            }
        if photo_result.get("ambiguous_delivery"):
            return {
                "success": False,
                "delivery_state": "unknown",
                "render_mode": "photo",
                "attempts": attempts,
                "message_ids": [],
                "network_calls": int(getattr(sender, "network_calls", before) or before) - before,
                "error": _clean(photo_result.get("error")),
            }
        if (
            photo
            and chosen_photo == photo
            and envelope.cover_path
            and envelope.cover_path != chosen_photo
            and _invalid_cached_photo_reference(photo_result)
        ):
            photo_reference_invalid = True
            upload_result = sender.send_photo(
                chat_id,
                envelope.cover_path,
                caption=envelope.caption_html,
                parse_mode="HTML",
                reply_markup=envelope.reply_markup,
            )
            attempts.append(_attempt_view("sendPhotoUpload", upload_result))
            if upload_result.get("success"):
                if _clean(upload_result.get("message_id")):
                    message_ids.append(_clean(upload_result.get("message_id")))
                return {
                    "success": True,
                    "delivery_state": "sent",
                    "render_mode": "photo",
                    "attempts": attempts,
                    "message_ids": message_ids,
                    "network_calls": int(getattr(sender, "network_calls", before) or before) - before,
                    "photo_file_id": _clean(upload_result.get("photo_file_id")),
                    "photo_file_unique_id": _clean(upload_result.get("photo_file_unique_id")),
                    "photo_reference_invalid": True,
                    "error": "",
                }
            if upload_result.get("ambiguous_delivery"):
                return {
                    "success": False,
                    "delivery_state": "unknown",
                    "render_mode": "photo",
                    "attempts": attempts,
                    "message_ids": [],
                    "network_calls": int(getattr(sender, "network_calls", before) or before) - before,
                    "photo_reference_invalid": True,
                    "error": _clean(upload_result.get("error")),
                }

    try:
        text_result = sender.send(
            chat_id,
            envelope.full_text_html,
            parse_mode="HTML",
            reply_markup=envelope.reply_markup,
        )
    except TypeError as exc:
        if "reply_markup" not in str(exc):
            raise
        text_result = sender.send(chat_id, envelope.full_text_html, parse_mode="HTML")
    attempts.append(_attempt_view("sendMessage", text_result))
    if _clean(text_result.get("message_id")):
        message_ids.append(_clean(text_result.get("message_id")))
    state = "sent" if text_result.get("success") else ("unknown" if text_result.get("ambiguous_delivery") else "failed")
    return {
        "success": bool(text_result.get("success")),
        "delivery_state": state,
        "render_mode": "text",
        "attempts": attempts,
        "message_ids": message_ids,
        "network_calls": int(getattr(sender, "network_calls", before) or before) - before,
        "photo_reference_invalid": photo_reference_invalid,
        "error": _clean(text_result.get("error")),
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
