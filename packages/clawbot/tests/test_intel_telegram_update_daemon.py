from __future__ import annotations

import json

from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE


def test_daemon_gate_requires_token_ack_network_and_send_flag(tmp_path):
    from scripts.intel_telegram_update_daemon import build_daemon_gate

    gate = build_daemon_gate(env={}, allow_real_network=False, allow_send_message=False)

    assert gate["ready"] is False
    assert gate["missing_gates"] == [
        "telegram_bot_token_missing",
        "telegram_runtime_ack_missing",
        "real_network_not_allowed",
        "send_message_not_allowed",
    ]


def test_daemon_once_processes_start_and_writes_heartbeat_without_leaking_secret(tmp_path):
    from scripts.intel_telegram_update_daemon import run_daemon_once
    from src.intel.telegram_update_processor import set_telegram_offset

    db_path = tmp_path / "intel.db"
    heartbeat = tmp_path / "heartbeat.json"
    evidence_dir = tmp_path / "evidence"
    token = "fake-daemon-token-secret"
    chat_id = "daemon-chat-secret"
    set_telegram_offset(db_path, 100)

    calls: list[dict[str, object]] = []

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        if url.endswith("/getUpdates"):
            assert payload["offset"] == 101
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 101,
                        "message": {
                            "message_id": 201,
                            "text": "/start",
                            "from": {"id": "daemon-user", "username": "daemon"},
                            "chat": {"id": chat_id, "type": "private"},
                        },
                    }
                ],
            }
        if url.endswith("/sendMessage"):
            assert payload["chat_id"] == chat_id
            return {"ok": True, "result": {"message_id": 9001, "chat": {"id": chat_id}}}
        raise AssertionError(url)

    result = run_daemon_once(
        db_path=db_path,
        env={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": token,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
            "INTEL_BRIEF_TELEGRAM_LISTENER_ACK": "I_UNDERSTAND_REAL_TELEGRAM_LISTENER",
        },
        allow_real_network=True,
        allow_send_message=True,
        now="2026-07-08T16:30:00+00:00",
        evidence_dir=evidence_dir,
        heartbeat_path=heartbeat,
        transport=transport,
        limit=20,
        timeout_seconds=0,
    )

    assert result["status"] == "success"
    assert result["send_message_attempted"] is True
    assert result["processor"]["runtime"]["handled_count"] == 1
    assert heartbeat.exists()
    saved = heartbeat.read_text(encoding="utf-8")
    assert token not in saved
    assert chat_id not in saved
    payload = json.loads(saved)
    assert payload["last_status"] == "success"
    assert payload["last_handled_count"] == 1
    assert payload["last_start_menu_success_at"] == result["timestamp"]
    assert payload["last_start_menu_inline_keyboard_sent"] is True
    assert payload["last_start_menu_persistent_keyboard_sent"] is True
    assert payload["last_start_menu_raw_content_persisted"] is False
    assert (evidence_dir / "latest-real-update-daemon.json").exists()
    assert len(calls) == 3


def test_daemon_heartbeat_keeps_last_start_menu_success_after_empty_poll(tmp_path):
    from scripts.intel_telegram_update_daemon import run_daemon_once
    from src.intel.telegram_update_processor import set_telegram_offset

    db_path = tmp_path / "intel.db"
    heartbeat = tmp_path / "heartbeat.json"
    evidence_dir = tmp_path / "evidence"
    token = "fake-daemon-token-secret"
    chat_id = "daemon-chat-secret"
    set_telegram_offset(db_path, 200)

    updates_by_call: list[list[dict[str, object]]] = [
        [
            {
                "update_id": 201,
                "message": {
                    "message_id": 301,
                    "text": "/start",
                    "from": {"id": "daemon-user", "username": "daemon"},
                    "chat": {"id": chat_id, "type": "private"},
                },
            }
        ],
        [],
    ]

    def transport(url: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        if url.endswith("/getUpdates"):
            return {"ok": True, "result": updates_by_call.pop(0)}
        if url.endswith("/sendMessage"):
            return {"ok": True, "result": {"message_id": 9001, "chat": {"id": chat_id}}}
        raise AssertionError(url)

    env = {
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": token,
        "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": TELEGRAM_SANDBOX_ACK_VALUE,
        "INTEL_BRIEF_TELEGRAM_LISTENER_ACK": "I_UNDERSTAND_REAL_TELEGRAM_LISTENER",
    }
    first = run_daemon_once(
        db_path=db_path,
        env=env,
        allow_real_network=True,
        allow_send_message=True,
        now="2026-07-08T16:30:00+00:00",
        evidence_dir=evidence_dir,
        heartbeat_path=heartbeat,
        transport=transport,
        limit=20,
        timeout_seconds=0,
    )
    second = run_daemon_once(
        db_path=db_path,
        env=env,
        allow_real_network=True,
        allow_send_message=True,
        now="2026-07-08T16:30:05+00:00",
        evidence_dir=evidence_dir,
        heartbeat_path=heartbeat,
        transport=transport,
        limit=20,
        timeout_seconds=0,
    )

    payload = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert first["status"] == "success"
    assert second["status"] == "no_new_updates"
    assert payload["last_status"] == "no_new_updates"
    assert payload["last_start_menu_success_at"] == first["timestamp"]
    assert payload["last_start_menu_inline_keyboard_sent"] is True
    assert payload["last_start_menu_update_id_present"] is True
    saved = heartbeat.read_text(encoding="utf-8")
    assert token not in saved
    assert chat_id not in saved


def test_daemon_launchagent_plist_uses_safe_paths(tmp_path):
    from scripts.intel_telegram_update_daemon import build_launchagent_plist

    plist = build_launchagent_plist(
        project_root=tmp_path,
        label="ai.openclaw.intel-brief.telegram-listener",
        interval_seconds=5,
        timeout_seconds=3,
    )

    assert "intel_telegram_update_daemon.py" in plist
    assert "ai.openclaw.intel-brief.telegram-listener" in plist
    assert "INTEL_BRIEF_TELEGRAM_LISTENER_ACK" in plist
    assert "KeepAlive" in plist
    assert str(tmp_path / "packages" / "clawbot" / ".venv312" / "bin" / "python") in plist
    assert str(tmp_path / ".openclaw" / "intel-brief.production.env") in plist
