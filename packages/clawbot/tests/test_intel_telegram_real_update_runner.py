from __future__ import annotations

import json

from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE
from src.intel.telegram_update_processor import get_telegram_offset, set_telegram_offset

FAKE_TOKEN = "fake-real-runner-token"
CHAT_ID = "real-runner-chat-should-not-leak"
NOW = "2026-07-07T17:30:00+00:00"


def _update(update_id: int, text: str = "/start") -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id + 100,
            "text": text,
            "from": {"id": "real-runner-user", "username": "runner_tester"},
            "chat": {"id": CHAT_ID, "type": "private"},
        },
    }


def test_real_update_runner_gate_requires_token_ack_network_and_send_flag():
    from src.intel.telegram_real_update_runner import build_real_update_runner_gate

    gate = build_real_update_runner_gate(env={}, allow_real_network=False, allow_send_message=False)

    assert gate["status"] == "blocked"
    assert gate["ready"] is False
    assert gate["missing_gates"] == [
        "telegram_bot_token_missing",
        "telegram_runtime_ack_missing",
        "real_network_not_allowed",
        "send_message_not_allowed",
    ]
    assert gate["redacted_env"] == {
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": False,
        "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": False,
        "allow_real_network": False,
        "allow_send_message": False,
    }


def test_real_update_runner_processes_new_update_with_injected_transport(tmp_path):
    from src.intel.telegram_real_update_runner import run_real_update_processor_once

    db_path = tmp_path / "real-runner.db"
    set_telegram_offset(db_path, 500)
    calls: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        if url.endswith("/getUpdates"):
            assert payload["offset"] == 501
            return {"ok": True, "result": [_update(501, "/start")]}
        if url.endswith("/sendMessage"):
            assert payload["chat_id"] == CHAT_ID
            text = str(payload["text"])
            assert "菜单快捷入口" in text or "700 今日简报" in text
            return {"ok": True, "result": {"message_id": 9001, "chat": {"id": CHAT_ID}}}
        raise AssertionError(url)

    result = run_real_update_processor_once(
        db_path=db_path,
        env={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        },
        allow_real_network=True,
        allow_send_message=True,
        transport=transport,
        now=NOW,
    )

    assert result["status"] == "success"
    assert result["gate"]["ready"] is True
    assert result["processor"]["previous_offset"] == 500
    assert result["processor"]["request_offset"] == 501
    assert result["processor"]["new_offset"] == 501
    assert result["processor"]["runtime"]["handled_count"] == 1
    assert result["processor"]["runtime"]["send_success_count"] == 1
    assert result["network_calls"] == 3
    assert result["send_message_attempted"] is True
    assert get_telegram_offset(db_path) == 501
    public_text = json.dumps(result, ensure_ascii=False)
    assert FAKE_TOKEN not in public_text
    assert CHAT_ID not in public_text
    assert len(calls) == 3
    assert "菜单快捷入口" in str(calls[1]["payload"]["text"])
    assert "700 今日简报" in str(calls[2]["payload"]["text"])


def test_real_update_runner_no_new_updates_does_not_send_or_advance(tmp_path):
    from src.intel.telegram_real_update_runner import run_real_update_processor_once

    db_path = tmp_path / "real-runner.db"
    set_telegram_offset(db_path, 700)
    calls: list[str] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append(url)
        if url.endswith("/getUpdates"):
            return {"ok": True, "result": []}
        if url.endswith("/sendMessage"):
            raise AssertionError("sendMessage must not be called when there are no new updates")
        raise AssertionError(url)

    result = run_real_update_processor_once(
        db_path=db_path,
        env={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        },
        allow_real_network=True,
        allow_send_message=True,
        transport=transport,
        now=NOW,
    )

    assert result["status"] == "no_new_updates"
    assert result["network_calls"] == 1
    assert result["send_message_attempted"] is False
    assert result["processor"]["new_offset"] == 700
    assert get_telegram_offset(db_path) == 700
    assert len(calls) == 1


def test_real_update_runner_evidence_builder_blocks_without_send_flag(tmp_path):
    from src.intel.telegram_real_update_runner import build_real_update_runner_evidence

    output = tmp_path / "blocked.json"
    db_path = tmp_path / "real-runner.db"

    result = build_real_update_runner_evidence(
        db_path=db_path,
        evidence_path=output,
        env={"INTEL_BRIEF_TELEGRAM_BOT_TOKEN": FAKE_TOKEN, "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE},
        allow_real_network=True,
        allow_send_message=False,
        now=NOW,
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "blocked"
    assert saved["gate"]["missing_gates"] == ["send_message_not_allowed"]
    assert saved["network_calls"] == 0
    assert saved["send_message_attempted"] is False


def test_real_update_runner_cli_blocks_without_explicit_send_flag(tmp_path):
    from scripts.intel_telegram_real_update_runner import main

    output = tmp_path / "blocked-cli.json"
    db_path = tmp_path / "real-runner.db"
    env_path = tmp_path / "env"
    env_path.write_text(
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN=fake\n"
        f"INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK={TELEGRAM_SANDBOX_ACK_VALUE}\n",
        encoding="utf-8",
    )

    exit_code = main(["--db", str(db_path), "--env-path", str(env_path), "--output", str(output), "--allow-real-network"])

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["send_message_attempted"] is False
    assert saved["gate"]["missing_gates"] == ["send_message_not_allowed"]


def test_real_update_runner_evidence_redacts_subscriber_user_id(tmp_path):
    from src.intel.telegram_real_update_runner import run_real_update_processor_once

    db_path = tmp_path / "real-runner-redaction.db"
    set_telegram_offset(db_path, 800)

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        if url.endswith("/getUpdates"):
            return {"ok": True, "result": [_update(801, "/start")]}
        if url.endswith("/sendMessage"):
            return {"ok": True, "result": {"message_id": 9002, "chat": {"id": CHAT_ID}}}
        raise AssertionError(url)

    result = run_real_update_processor_once(
        db_path=db_path,
        env={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        },
        allow_real_network=True,
        allow_send_message=True,
        transport=transport,
        now=NOW,
    )

    public_text = json.dumps(result, ensure_ascii=False)
    assert "tg:real-runner-user" not in public_text
    handled = result["processor"]["runtime"]["handled_updates"][0]
    assert "subscriber_user_id" not in handled
    assert handled["subscriber_user_id_present"] is True
