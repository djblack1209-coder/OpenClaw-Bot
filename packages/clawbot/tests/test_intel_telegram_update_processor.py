from __future__ import annotations

import json

from src.intel.db.store import initialize_intel_db
from src.intel.subscriptions import get_subscription_profile, grant_subscription, upsert_subscription_plan

NOW = "2026-07-07T17:00:00+00:00"
CHAT_ID = "processor-chat-should-not-leak"


class FakeBotClient:
    def __init__(self, updates: list[dict[str, object]]) -> None:
        self.updates = updates
        self.calls: list[dict[str, object]] = []
        self.network_calls = 0

    def get_updates(self, *, limit: int = 20, offset: int | None = None, timeout_seconds: int = 0) -> dict[str, object]:
        self.calls.append({"limit": limit, "offset": offset, "timeout_seconds": timeout_seconds})
        self.network_calls += 1
        selected = [u for u in self.updates if offset is None or int(u.get("update_id", 0)) >= offset]
        return {
            "success": True,
            "method": "getUpdates",
            "network": "fake_client",
            "network_calls": self.network_calls,
            "update_count": len(selected),
            "command_update_count": len(selected),
            "max_update_id_present": bool(selected),
            "redacted": {"update_count": len(selected), "chat_id_values_persisted": False},
            "updates": selected,
            "error_code": "",
            "error": "",
        }


class FakeReplySender:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.network_calls = 0

    def send(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.sent.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
        return {
            "success": True,
            "network": "fake_sender",
            "network_calls": 0,
            "chat_id_present": bool(chat_id),
            "message_id": f"fake-{len(self.sent)}",
            "endpoint": "fake://telegram/sendMessage",
            "reply_markup_present": bool(reply_markup),
        }


def _update(update_id: int, text: str, *, user_id: str = "processor-user") -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id + 100,
            "text": text,
            "from": {"id": user_id, "username": "processor_tester"},
            "chat": {"id": CHAT_ID, "type": "private"},
        },
    }


def test_schema_contains_telegram_runtime_state(tmp_path):
    db_path = tmp_path / "processor.db"

    initialize_intel_db(db_path)

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "telegram_runtime_state" in tables
    assert "telegram_pending_actions" in tables


def test_update_processor_persists_offset_and_skips_duplicate_updates(tmp_path):
    from src.intel.telegram_update_processor import get_telegram_offset, process_telegram_updates_once

    db_path = tmp_path / "processor.db"
    sender = FakeReplySender()
    first_client = FakeBotClient([_update(10, "/start")])

    first = process_telegram_updates_once(db_path, client=first_client, sender=sender, now=NOW)

    assert first["status"] == "success"
    assert first["previous_offset"] == 0
    assert first["request_offset"] is None
    assert first["new_offset"] == 10
    assert first["runtime"]["handled_count"] == 1
    assert first["runtime"]["handled_updates"][0]["reply_message_count"] == 2
    assert sender.sent[0]["chat_id"] == CHAT_ID
    assert get_telegram_offset(db_path) == 10
    assert CHAT_ID not in json.dumps(first, ensure_ascii=False)

    duplicate_client = FakeBotClient([_update(10, "/start"), _update(11, "/status")])
    second = process_telegram_updates_once(db_path, client=duplicate_client, sender=sender, now=NOW)

    assert duplicate_client.calls[0]["offset"] == 11
    assert second["previous_offset"] == 10
    assert second["new_offset"] == 11
    assert second["fetched_update_count"] == 1
    assert second["skipped_duplicate_count"] == 0
    assert second["runtime"]["handled_count"] == 1
    assert len(sender.sent) == 3
    assert get_telegram_offset(db_path) == 11


def test_update_processor_handles_active_user_configuration_after_manual_grant(tmp_path):
    from src.intel.telegram_update_processor import process_telegram_updates_once

    db_path = tmp_path / "processor.db"
    sender = FakeReplySender()
    first = process_telegram_updates_once(db_path, client=FakeBotClient([_update(20, "/start")]), sender=sender, now=NOW)
    user_id = first["runtime"]["handled_updates"][0]["subscriber_user_id"]
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare", "senate_trading"])
    grant_subscription(
        db_path,
        user_id=user_id,
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at="2026-08-07T00:00:00+00:00",
        source="processor_contract_test",
    )

    second = process_telegram_updates_once(
        db_path,
        client=FakeBotClient(
            [
                _update(20, "/start"),
                _update(21, "/sources akshare senate_trading"),
                _update(22, "/schedule daily 08:30 America/Denver"),
                _update(23, "/custom 周杰伦"),
            ]
        ),
        sender=sender,
        now=NOW,
    )

    assert second["previous_offset"] == 20
    assert second["request_offset"] == 21
    assert second["new_offset"] == 23
    assert second["runtime"]["handled_count"] == 3
    assert second["tracking_targets"] == [{"name": "周杰伦", "active_subscription_count": 1}]
    profile = get_subscription_profile(db_path, user_id=user_id, now=NOW)
    assert profile["eligible"] is True
    assert profile["enabled_categories"] == ["akshare", "senate_trading"]
    assert profile["delivery_preferences"]["delivery_time"] == "08:30"


def test_update_processor_sandbox_evidence_replays_offset_safe_flow(tmp_path):
    from scripts.intel_telegram_update_processor_sandbox import build_intel_telegram_update_processor_sandbox_evidence

    evidence_dir = tmp_path / "processor-evidence"
    evidence = build_intel_telegram_update_processor_sandbox_evidence(evidence_dir, now=NOW)

    assert evidence["status"] == "success"
    assert evidence["phase"] == "AC-telegram-update-processor-offset-sandbox"
    assert evidence["network_calls"] == 0
    assert evidence["runs"][0]["new_offset"] == 100
    assert evidence["runs"][1]["new_offset"] == 103
    assert evidence["duplicate_replay"]["runtime"]["handled_count"] == 0
    assert evidence["final_offset"] == 103
    assert evidence["final_profile"]["status"] == "active"
    assert evidence["final_profile"]["enabled_categories"] == ["akshare", "senate_trading"]
    saved = (evidence_dir / "evidence.json").read_text(encoding="utf-8")
    assert CHAT_ID not in saved
    assert (evidence_dir / "intel_telegram_update_processor_sandbox.db").exists()
