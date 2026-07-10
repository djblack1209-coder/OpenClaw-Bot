from __future__ import annotations

import json


def test_start_menu_acceptance_waits_when_no_start_success():
    from scripts.intel_telegram_start_menu_acceptance import evaluate_start_menu_acceptance

    result = evaluate_start_menu_acceptance(
        {
            "updated_at": "2026-07-08T17:30:00+00:00",
            "last_status": "no_new_updates",
            "raw_updates_persisted": False,
        },
        since="2026-07-08T17:29:00+00:00",
        now="2026-07-08T17:30:05+00:00",
    )

    assert result["verified"] is False
    assert result["status"] == "waiting_for_start"
    assert "还没看到" in result["blockers"][0]
    assert "/start" in result["next_action"]


def test_start_menu_acceptance_verifies_fresh_redacted_success_after_since():
    from scripts.intel_telegram_start_menu_acceptance import evaluate_start_menu_acceptance

    result = evaluate_start_menu_acceptance(
        {
            "updated_at": "2026-07-08T17:30:10+00:00",
            "last_status": "no_new_updates",
            "last_start_menu_success_at": "2026-07-08T17:30:01+00:00",
            "last_start_menu_reply_message_count": 2,
            "last_start_menu_inline_keyboard_sent": True,
            "last_start_menu_persistent_keyboard_sent": True,
            "last_start_menu_raw_content_persisted": False,
            "raw_updates_persisted": False,
        },
        since="2026-07-08T17:30:00+00:00",
        now="2026-07-08T17:30:15+00:00",
    )

    assert result["verified"] is True
    assert result["status"] == "verified"
    assert result["last_start_menu_reply_message_count"] == 2
    assert result["blockers"] == []
    assert result["redaction"] == {
        "chat_id_persisted": False,
        "telegram_user_id_persisted": False,
        "token_persisted": False,
        "message_text_persisted": False,
    }


def test_start_menu_acceptance_rejects_stale_success_before_since():
    from scripts.intel_telegram_start_menu_acceptance import evaluate_start_menu_acceptance

    result = evaluate_start_menu_acceptance(
        {
            "updated_at": "2026-07-08T17:30:10+00:00",
            "last_start_menu_success_at": "2026-07-08T17:29:59+00:00",
            "last_start_menu_inline_keyboard_sent": True,
            "last_start_menu_persistent_keyboard_sent": True,
            "last_start_menu_raw_content_persisted": False,
            "raw_updates_persisted": False,
        },
        since="2026-07-08T17:30:00+00:00",
        now="2026-07-08T17:30:15+00:00",
    )

    assert result["verified"] is False
    assert result["last_start_menu_success_after_since"] is False


def test_start_menu_acceptance_cli_writes_redacted_evidence(tmp_path):
    from scripts.intel_telegram_start_menu_acceptance import main

    heartbeat = tmp_path / "heartbeat.json"
    output = tmp_path / "acceptance.json"
    heartbeat.write_text(
        json.dumps(
            {
                "updated_at": "2026-07-08T17:30:10+00:00",
                "last_start_menu_success_at": "2026-07-08T17:30:01+00:00",
                "last_start_menu_reply_message_count": 2,
                "last_start_menu_inline_keyboard_sent": True,
                "last_start_menu_persistent_keyboard_sent": True,
                "last_start_menu_raw_content_persisted": False,
                "raw_updates_persisted": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--heartbeat",
            str(heartbeat),
            "--output",
            str(output),
            "--since",
            "2026-07-08T17:30:00+00:00",
            "--max-heartbeat-age-seconds",
            "999999999",
        ]
    )

    assert exit_code == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["verified"] is True
    assert saved["redaction"]["chat_id_persisted"] is False
    assert saved["redaction"]["telegram_user_id_persisted"] is False
    assert saved["redaction"]["token_persisted"] is False
    assert saved["redaction"]["message_text_persisted"] is False
    assert "daemon-chat-secret" not in output.read_text(encoding="utf-8")
