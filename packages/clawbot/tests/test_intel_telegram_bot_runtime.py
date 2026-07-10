from __future__ import annotations

import json

FAKE_TOKEN = "fake-token-secret"
FAKE_CHAT_ID = "bot-runtime-chat-secret"
ACK = "I_UNDERSTAND_TELEGRAM_SANDBOX_SEND"


def test_bot_runtime_gate_blocks_without_token_ack_or_network():
    from src.intel.telegram_bot_runtime import build_bot_runtime_gate

    gate = build_bot_runtime_gate(env={}, allow_real_network=False)

    assert gate["status"] == "blocked"
    assert gate["ready"] is False
    assert gate["missing_gates"] == [
        "telegram_bot_token_missing",
        "telegram_runtime_ack_missing",
        "real_network_not_allowed",
    ]
    assert gate["redacted_env"] == {
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": False,
        "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": False,
        "allow_real_network": False,
    }


def test_bot_api_client_sets_commands_and_gets_updates_with_redacted_results():
    from src.intel.telegram_bot_runtime import TelegramBotApiRuntimeClient, intel_brief_bot_commands

    calls: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        if url.endswith("/setMyCommands"):
            return {"ok": True, "result": True}
        if url.endswith("/getUpdates"):
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 1001,
                        "message": {
                            "text": "/start",
                            "chat": {"id": FAKE_CHAT_ID, "type": "private"},
                            "from": {"id": "bot-runtime-user", "username": "tester"},
                        },
                    }
                ],
            }
        raise AssertionError(url)

    client = TelegramBotApiRuntimeClient(token=FAKE_TOKEN, transport=transport)
    commands = intel_brief_bot_commands()
    set_result = client.set_my_commands(commands)
    updates_result = client.get_updates(limit=5)

    assert commands[0] == {"command": "start", "description": "打开菜单"}
    assert commands[1:4] == [
        {"command": "today", "description": "今日简报"},
        {"command": "status", "description": "我的订阅"},
        {"command": "market", "description": "市场资金"},
    ]
    assert set_result == {
        "success": True,
        "method": "setMyCommands",
        "network": "injected_transport",
        "network_calls": 1,
        "command_count": len(commands),
        "error_code": "",
        "error": "",
    }
    assert updates_result["success"] is True
    assert updates_result["method"] == "getUpdates"
    assert updates_result["network"] == "injected_transport"
    assert updates_result["network_calls"] == 2
    assert updates_result["update_count"] == 1
    assert updates_result["command_update_count"] == 1
    assert updates_result["max_update_id_present"] is True
    assert updates_result["updates"][0]["message"]["chat"]["id"] == FAKE_CHAT_ID

    public_json = json.dumps({"set": set_result, "updates": updates_result["redacted"]}, ensure_ascii=False)
    assert FAKE_TOKEN not in public_json
    assert FAKE_CHAT_ID not in public_json
    assert FAKE_TOKEN in str(calls[0]["url"])
    assert calls[0]["payload"]["commands"] == commands
    assert calls[1]["payload"]["allowed_updates"] == ["message", "callback_query"]


def test_runtime_probe_contract_sets_commands_gets_updates_and_writes_redacted_evidence(tmp_path):
    from src.intel.telegram_bot_runtime import build_telegram_bot_runtime_probe

    output = tmp_path / "bot-runtime-probe.json"

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        if url.endswith("/setMyCommands"):
            return {"ok": True, "result": True}
        if url.endswith("/getUpdates"):
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 1002,
                        "message": {
                            "text": "/sources akshare",
                            "chat": {"id": FAKE_CHAT_ID, "type": "private"},
                            "from": {"id": "bot-runtime-user"},
                        },
                    }
                ],
            }
        raise AssertionError(url)

    result = build_telegram_bot_runtime_probe(
        evidence_path=output,
        env={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": ACK,
        },
        allow_real_network=True,
        transport=transport,
    )

    saved = output.read_text(encoding="utf-8")
    assert result["status"] == "success"
    assert result["network_calls"] == 2
    assert result["set_my_commands"]["success"] is True
    assert result["get_updates"]["success"] is True
    assert result["get_updates"]["update_count"] == 1
    assert result["get_updates"]["command_update_count"] == 1
    assert result["raw_updates_persisted"] is False
    assert FAKE_TOKEN not in saved
    assert FAKE_CHAT_ID not in saved


def test_bot_runtime_probe_cli_writes_blocked_evidence_without_private_env(tmp_path):
    from scripts.intel_telegram_bot_runtime_probe import main

    output = tmp_path / "blocked.json"
    missing_env = tmp_path / "missing.env"

    exit_code = main(["--env-path", str(missing_env), "--output", str(output)])

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["network_calls"] == 0
    assert saved["gate"]["missing_gates"] == [
        "telegram_bot_token_missing",
        "telegram_runtime_ack_missing",
        "real_network_not_allowed",
    ]


def test_bot_api_get_updates_allows_callback_query_updates():
    from src.intel.telegram_bot_runtime import TelegramBotApiRuntimeClient

    calls: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        return {
            "ok": True,
            "result": [
                {
                    "update_id": 2001,
                    "callback_query": {
                        "id": "cb-1",
                        "data": "Github",
                        "from": {"id": "bot-runtime-user"},
                        "message": {"chat": {"id": FAKE_CHAT_ID, "type": "private"}},
                    },
                }
            ],
        }

    client = TelegramBotApiRuntimeClient(token=FAKE_TOKEN, transport=transport)
    result = client.get_updates(limit=5)

    assert calls[0]["payload"]["allowed_updates"] == ["message", "callback_query"]
    assert result["success"] is True
    assert result["update_count"] == 1
    assert result["redacted"]["callback_query_update_count"] == 1
    public_json = json.dumps(result["redacted"], ensure_ascii=False)
    assert FAKE_CHAT_ID not in public_json
