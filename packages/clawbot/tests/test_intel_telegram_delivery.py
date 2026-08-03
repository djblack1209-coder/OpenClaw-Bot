from __future__ import annotations

import json

from src.intel.telegram_delivery import (
    TELEGRAM_SANDBOX_ACK_VALUE,
    TelegramBotApiSender,
    build_telegram_sandbox_gate,
    build_telegram_sandbox_probe,
)

FAKE_TOKEN = "123456:SECRET-DO-NOT-LEAK"
FAKE_CHAT_ID = "987654321"


def test_telegram_sandbox_gate_blocks_missing_credentials_without_leaking_values():
    gate = build_telegram_sandbox_gate(env={})

    assert gate["status"] == "blocked"
    assert gate["ready"] is False
    assert gate["missing_gates"] == [
        "telegram_bot_token_missing",
        "telegram_chat_id_missing",
        "sandbox_send_ack_missing",
    ]
    assert gate["redacted_env"] == {
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": False,
        "INTEL_BRIEF_TELEGRAM_CHAT_ID": False,
        "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": False,
    }


def test_telegram_sandbox_gate_redacts_present_secret_values():
    gate = build_telegram_sandbox_gate(
        env={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": FAKE_CHAT_ID,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        }
    )

    assert gate["status"] == "ready"
    assert gate["ready"] is True
    assert gate["redacted_env"]["INTEL_BRIEF_TELEGRAM_BOT_TOKEN"] is True
    assert gate["redacted_env"]["INTEL_BRIEF_TELEGRAM_CHAT_ID"] is True
    assert "SECRET" not in json.dumps(gate)
    assert FAKE_CHAT_ID not in json.dumps(gate)


def test_telegram_bot_api_sender_uses_injected_transport_and_redacts_result():
    calls: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        return {"ok": True, "result": {"message_id": 42, "chat": {"id": FAKE_CHAT_ID}}}

    sender = TelegramBotApiSender(token=FAKE_TOKEN, transport=transport)
    result = sender.send(FAKE_CHAT_ID, "hello", parse_mode="HTML")

    assert result["success"] is True
    assert result["message_id"] == "42"
    assert result["endpoint"] == "https://api.telegram.org/bot***/sendMessage"
    assert result["chat_id_present"] is True
    assert result["network_calls"] == 1
    assert result["network"] == "injected_transport"
    assert calls[0]["payload"]["text"] == "hello"
    assert FAKE_TOKEN in str(calls[0]["url"])  # transport receives real URL; public result must not
    assert "SECRET" not in json.dumps(result)
    assert FAKE_CHAT_ID not in json.dumps(result)


def test_official_sender_rejects_nonexistent_rich_method_without_network():
    calls = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append((url, payload, timeout))
        raise AssertionError("不存在的 sendRichMessage 不应发起网络请求")

    sender = TelegramBotApiSender(token=FAKE_TOKEN, transport=transport)
    result = sender.send_rich_message(FAKE_CHAT_ID, envelope=object(), photo="file-id")

    assert result["success"] is False
    assert result["error_code"] == 404
    assert result["ambiguous_delivery"] is False
    assert sender.network_calls == 0
    assert calls == []


def test_build_telegram_sandbox_probe_blocks_without_credentials_and_no_network(tmp_path):
    output = tmp_path / "telegram-gate.json"
    result = build_telegram_sandbox_probe(evidence_path=output, env={}, message="probe")

    assert result["status"] == "blocked"
    assert result["network_calls"] == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["limits"][0] == "No Telegram Bot API call unless gate is ready and network is explicitly allowed."


def test_build_telegram_sandbox_probe_contract_transport_success_is_redacted(tmp_path):
    output = tmp_path / "telegram-contract.json"

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        return {"ok": True, "result": {"message_id": 777, "chat": {"id": payload["chat_id"]}}}

    result = build_telegram_sandbox_probe(
        evidence_path=output,
        env={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": FAKE_CHAT_ID,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        },
        message="contract message",
        transport=transport,
    )

    saved_text = output.read_text(encoding="utf-8")
    assert result["status"] == "success"
    assert result["send_result"]["message_id"] == "777"
    assert result["network_calls"] == 1
    assert result["send_result"]["network"] == "injected_transport"
    assert "SECRET" not in saved_text
    assert FAKE_CHAT_ID not in saved_text


def test_intel_telegram_sandbox_probe_cli_writes_blocked_evidence(tmp_path, monkeypatch):
    from scripts.intel_telegram_sandbox_probe import main

    output = tmp_path / "telegram-cli.json"
    monkeypatch.delenv("INTEL_BRIEF_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("INTEL_BRIEF_TELEGRAM_CHAT_ID", raising=False)

    exit_code = main(["--output", str(output), "--message", "hello"])

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["network_calls"] == 0


def _summary_evidence_payload() -> dict[str, object]:
    return {
        "status": "partial_fallback",
        "llm": {
            "summary_text": "本次基于国会持仓和A股龙虎榜生成摘要。",
            "model_family": "qwen",
            "usage": {"total_tokens": 0},
        },
        "items": [
            {"source_label": "国会持仓", "title": "Ron L Wyden Sale BYND"},
            {"source_label": "A股龙虎榜", "title": "深科技（000021）机构买入"},
        ],
    }


def test_build_telegram_summary_delivery_probe_blocks_without_credentials(tmp_path):
    from src.intel.telegram_delivery import build_telegram_summary_delivery_probe

    summary = tmp_path / "summary.json"
    output = tmp_path / "telegram-summary-blocked.json"
    summary.write_text(json.dumps(_summary_evidence_payload(), ensure_ascii=False), encoding="utf-8")

    result = build_telegram_summary_delivery_probe(
        summary_evidence_path=summary,
        evidence_path=output,
        env={},
    )

    assert result["status"] == "blocked"
    assert result["network_calls"] == 0
    assert result["message_preview"]["text_chars"] > 0
    assert "Ron L Wyden" in result["message_preview"]["text_head"]
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["summary_evidence"] == str(summary)
    assert saved["limits"][0] == "Uses real Intel Brief summary evidence to render the Telegram message."


def test_build_telegram_summary_delivery_probe_uses_summary_message_with_injected_transport(tmp_path):
    from src.intel.telegram_delivery import build_telegram_summary_delivery_probe

    summary = tmp_path / "summary.json"
    output = tmp_path / "telegram-summary-contract.json"
    summary.write_text(json.dumps(_summary_evidence_payload(), ensure_ascii=False), encoding="utf-8")
    calls: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        return {"ok": True, "result": {"message_id": 888, "chat": {"id": payload["chat_id"]}}}

    result = build_telegram_summary_delivery_probe(
        summary_evidence_path=summary,
        evidence_path=output,
        env={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": FAKE_CHAT_ID,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        },
        transport=transport,
    )

    saved_text = output.read_text(encoding="utf-8")
    assert result["status"] == "success"
    assert result["send_result"]["message_id"] == "888"
    assert result["send_result"]["network"] == "injected_transport"
    assert "Ron L Wyden" in calls[0]["payload"]["text"]
    assert "深科技" in calls[0]["payload"]["text"]
    assert "SECRET" not in saved_text
    assert FAKE_CHAT_ID not in saved_text


def test_intel_telegram_summary_probe_cli_writes_blocked_evidence(tmp_path, monkeypatch):
    from scripts.intel_telegram_summary_probe import main

    summary = tmp_path / "summary.json"
    output = tmp_path / "telegram-summary-cli.json"
    summary.write_text(json.dumps(_summary_evidence_payload(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.delenv("INTEL_BRIEF_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("INTEL_BRIEF_TELEGRAM_CHAT_ID", raising=False)

    exit_code = main(["--summary-evidence", str(summary), "--output", str(output)])

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["network_calls"] == 0


def test_telegram_sender_can_attach_native_reply_markup_without_leaking_it_to_result():
    calls: list[dict[str, object]] = []
    reply_markup = {"keyboard": [[{"text": "Github"}]], "resize_keyboard": True}

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        return {"ok": True, "result": {"message_id": 43, "chat": {"id": FAKE_CHAT_ID}}}

    sender = TelegramBotApiSender(token=FAKE_TOKEN, transport=transport)
    result = sender.send(FAKE_CHAT_ID, "menu", parse_mode="HTML", reply_markup=reply_markup)

    assert result["success"] is True
    assert calls[0]["payload"]["reply_markup"] == reply_markup
    assert result["reply_markup_present"] is True
    assert "Github" not in json.dumps(result, ensure_ascii=False)
    assert FAKE_CHAT_ID not in json.dumps(result, ensure_ascii=False)


def test_telegram_sender_answers_inline_callback_query_with_redacted_result():
    calls: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        return {"ok": True, "result": True}

    sender = TelegramBotApiSender(token=FAKE_TOKEN, transport=transport)
    result = sender.answer_callback_query("callback-secret-id", text="已收到")

    assert result["success"] is True
    assert result["method"] == "answerCallbackQuery"
    assert result["endpoint"] == "https://api.telegram.org/bot***/answerCallbackQuery"
    assert result["callback_query_id_present"] is True
    assert result["text_present"] is True
    assert result["network_calls"] == 1
    assert calls[0]["url"].endswith("/answerCallbackQuery")
    assert calls[0]["payload"] == {"callback_query_id": "callback-secret-id", "text": "已收到"}
    public_text = json.dumps(result, ensure_ascii=False)
    assert "callback-secret-id" not in public_text
    assert "SECRET" not in public_text
