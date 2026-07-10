from __future__ import annotations

import json

from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE

FAKE_TOKEN = "123456:SECRET-DO-NOT-LEAK"
FAKE_CHAT_ID = "987654321"


def _summary_evidence_payload() -> dict[str, object]:
    return {
        "status": "partial_fallback",
        "llm": {"summary_text": "Intel Brief 沙盒摘要", "usage": {"total_tokens": 0}},
        "items": [
            {"source_label": "国会持仓", "title": "Ron L Wyden Sale BYND"},
            {"source_label": "A股龙虎榜", "title": "深科技（000021）机构买入"},
        ],
    }


def test_find_chat_candidate_prefers_matching_start_payload():
    from src.intel.telegram_bootstrap import find_chat_candidate

    candidate = find_chat_candidate(
        [
            {"update_id": 1, "message": {"text": "hello", "chat": {"id": 111, "type": "private"}}},
            {
                "update_id": 2,
                "message": {
                    "text": "/start intel_brief_sandbox",
                    "chat": {"id": FAKE_CHAT_ID, "type": "private"},
                },
            },
        ],
        start_payload="intel_brief_sandbox",
    )

    assert candidate["chat_id"] == FAKE_CHAT_ID
    assert candidate["matched_start_payload"] is True
    assert candidate["chat_type"] == "private"


def test_telegram_local_bootstrap_blocks_without_ack_and_makes_no_network(tmp_path):
    from src.intel.telegram_bootstrap import build_telegram_local_bootstrap_probe

    summary = tmp_path / "summary.json"
    output = tmp_path / "bootstrap.json"
    summary.write_text(json.dumps(_summary_evidence_payload(), ensure_ascii=False), encoding="utf-8")

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:  # pragma: no cover
        raise AssertionError("transport must not be called when ack is missing")

    result = build_telegram_local_bootstrap_probe(
        token=FAKE_TOKEN,
        bot_username="carven_Jianbao_bot",
        summary_evidence_path=summary,
        evidence_path=output,
        ack="",
        allow_real_network=True,
        open_deep_link=False,
        transport=transport,
    )

    saved_text = output.read_text(encoding="utf-8")
    assert result["status"] == "blocked"
    assert result["network_calls"] == 0
    assert "sandbox_send_ack_missing" in result["missing_gates"]
    assert "SECRET" not in saved_text
    assert FAKE_CHAT_ID not in saved_text


def test_telegram_local_bootstrap_sends_summary_and_redacts_evidence(tmp_path):
    from src.intel.telegram_bootstrap import build_telegram_local_bootstrap_probe

    summary = tmp_path / "summary.json"
    output = tmp_path / "bootstrap-success.json"
    summary.write_text(json.dumps(_summary_evidence_payload(), ensure_ascii=False), encoding="utf-8")
    calls: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        if url.endswith("/getMe"):
            return {"ok": True, "result": {"username": "carven_Jianbao_bot", "id": 4242424242}}
        if url.endswith("/getUpdates"):
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 100,
                        "message": {
                            "text": "/start intel_brief_sandbox",
                            "chat": {"id": FAKE_CHAT_ID, "type": "private"},
                        },
                    }
                ],
            }
        if url.endswith("/sendMessage"):
            assert payload["chat_id"] == FAKE_CHAT_ID
            assert "Ron L Wyden" in str(payload["text"])
            return {"ok": True, "result": {"message_id": 20260707, "chat": {"id": FAKE_CHAT_ID}}}
        raise AssertionError(url)

    result = build_telegram_local_bootstrap_probe(
        token=FAKE_TOKEN,
        bot_username="carven_Jianbao_bot",
        summary_evidence_path=summary,
        evidence_path=output,
        ack=TELEGRAM_SANDBOX_ACK_VALUE,
        allow_real_network=True,
        open_deep_link=False,
        transport=transport,
    )

    saved_text = output.read_text(encoding="utf-8")
    assert result["status"] == "success"
    assert result["chat_candidate"]["present"] is True
    assert result["chat_candidate"]["matched_start_payload"] is True
    assert result["send_result"]["message_id"] == "20260707"
    assert result["network_calls"] == 3
    assert len(calls) == 3
    assert "SECRET" not in saved_text
    assert FAKE_CHAT_ID not in saved_text
    assert "4242424242" not in saved_text


def test_telegram_local_bootstrap_polls_until_start_message_arrives(tmp_path):
    from src.intel.telegram_bootstrap import build_telegram_local_bootstrap_probe

    summary = tmp_path / "summary.json"
    output = tmp_path / "bootstrap-poll.json"
    summary.write_text(json.dumps(_summary_evidence_payload(), ensure_ascii=False), encoding="utf-8")
    get_updates_calls = 0

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        nonlocal get_updates_calls
        if url.endswith("/getMe"):
            return {"ok": True, "result": {"username": "carven_Jianbao_bot", "id": 4242424242}}
        if url.endswith("/getUpdates"):
            get_updates_calls += 1
            if get_updates_calls == 1:
                return {"ok": True, "result": []}
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 101,
                        "message": {
                            "text": "/start intel_brief_sandbox",
                            "chat": {"id": FAKE_CHAT_ID, "type": "private"},
                        },
                    }
                ],
            }
        if url.endswith("/sendMessage"):
            return {"ok": True, "result": {"message_id": 20260708, "chat": {"id": FAKE_CHAT_ID}}}
        raise AssertionError(url)

    result = build_telegram_local_bootstrap_probe(
        token=FAKE_TOKEN,
        bot_username="carven_Jianbao_bot",
        summary_evidence_path=summary,
        evidence_path=output,
        ack=TELEGRAM_SANDBOX_ACK_VALUE,
        allow_real_network=True,
        open_deep_link=False,
        transport=transport,
        wait_seconds=5,
        poll_interval_seconds=0,
    )

    assert result["status"] == "success"
    assert result["get_updates"]["attempts"] == 2
    assert result["network_calls"] == 4
    assert get_updates_calls == 2


def test_intel_telegram_local_bootstrap_cli_writes_blocked_evidence(tmp_path, monkeypatch):
    from scripts.intel_telegram_local_bootstrap import main

    summary = tmp_path / "summary.json"
    output = tmp_path / "bootstrap-cli.json"
    summary.write_text(json.dumps(_summary_evidence_payload(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.delenv("INTEL_BRIEF_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK", raising=False)

    exit_code = main(
        [
            "--summary-evidence",
            str(summary),
            "--output",
            str(output),
            "--bot-username",
            "carven_Jianbao_bot",
        ]
    )

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["network_calls"] == 0
    assert "telegram_bot_token_missing" in saved["missing_gates"]
