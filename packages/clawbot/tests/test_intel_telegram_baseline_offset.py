from __future__ import annotations

import json

from src.intel.telegram_update_processor import get_telegram_offset, set_telegram_offset

CHAT_ID = "baseline-chat-should-not-leak"


class FakeBaselineClient:
    def __init__(self, updates: list[dict[str, object]], *, success: bool = True) -> None:
        self.updates = updates
        self.success = success
        self.calls: list[dict[str, object]] = []

    def get_updates(self, *, limit: int = 20, offset: int | None = None, timeout_seconds: int = 0) -> dict[str, object]:
        self.calls.append({"limit": limit, "offset": offset, "timeout_seconds": timeout_seconds})
        selected = [item for item in self.updates if offset is None or int(item.get("update_id", 0)) >= offset][:limit]
        return {
            "success": self.success,
            "method": "getUpdates",
            "network": "fake_client",
            "network_calls": 0,
            "update_count": len(selected),
            "command_update_count": len(selected),
            "max_update_id_present": bool(selected),
            "redacted": {"update_count": len(selected), "chat_id_values_persisted": False},
            "updates": selected,
            "error_code": "",
            "error": "" if self.success else "boom",
        }


def _update(update_id: int, text: str = "/start") -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "text": text,
            "chat": {"id": CHAT_ID, "type": "private"},
            "from": {"id": "baseline-user"},
        },
    }


def test_seed_baseline_offset_advances_to_latest_update_without_replying(tmp_path):
    from src.intel.telegram_baseline_offset import seed_telegram_baseline_offset

    db_path = tmp_path / "baseline.db"
    client = FakeBaselineClient([_update(41), _update(43), _update(42)])

    result = seed_telegram_baseline_offset(db_path, client=client, limit=20)

    assert result["status"] == "success"
    assert result["previous_offset"] == 0
    assert result["baseline_update_id"] == 43
    assert result["new_offset"] == 43
    assert result["reply_sent"] is False
    assert result["raw_updates_persisted"] is False
    assert result["network_calls"] == 0
    assert client.calls == [{"limit": 20, "offset": None, "timeout_seconds": 0}]
    assert get_telegram_offset(db_path) == 43
    assert CHAT_ID not in json.dumps(result, ensure_ascii=False)


def test_seed_baseline_offset_never_decreases_existing_offset(tmp_path):
    from src.intel.telegram_baseline_offset import seed_telegram_baseline_offset

    db_path = tmp_path / "baseline.db"
    set_telegram_offset(db_path, 100)
    client = FakeBaselineClient([_update(90), _update(99)])

    result = seed_telegram_baseline_offset(db_path, client=client)

    assert result["status"] == "success"
    assert result["previous_offset"] == 100
    assert result["baseline_update_id"] == 100
    assert result["new_offset"] == 100
    assert client.calls == [{"limit": 100, "offset": 101, "timeout_seconds": 0}]
    assert get_telegram_offset(db_path) == 100


def test_seed_baseline_offset_drains_more_than_one_hundred_updates(tmp_path):
    from src.intel.telegram_baseline_offset import seed_telegram_baseline_offset

    db_path = tmp_path / "baseline.db"
    client = FakeBaselineClient([_update(update_id) for update_id in range(1, 251)])

    result = seed_telegram_baseline_offset(db_path, client=client, limit=100)

    assert result["status"] == "success"
    assert result["batch_count"] == 3
    assert result["drained_update_count"] == 250
    assert result["drain_complete"] is True
    assert result["baseline_update_id"] == 250
    assert result["new_offset"] == 250
    assert result["reply_sent"] is False
    assert [call["offset"] for call in client.calls] == [None, 101, 201]
    assert get_telegram_offset(db_path) == 250


def test_baseline_evidence_builder_writes_redacted_json(tmp_path):
    from src.intel.telegram_baseline_offset import build_telegram_baseline_offset_evidence

    db_path = tmp_path / "baseline.db"
    output = tmp_path / "baseline-evidence.json"
    client = FakeBaselineClient([_update(200), _update(201, "/sources akshare")])

    evidence = build_telegram_baseline_offset_evidence(
        db_path=db_path,
        evidence_path=output,
        client=client,
        source="sandbox_contract",
    )

    saved = output.read_text(encoding="utf-8")
    assert evidence["status"] == "success"
    assert evidence["phase"] == "AD-telegram-baseline-offset"
    assert evidence["new_offset"] == 201
    assert evidence["reply_sent"] is False
    assert evidence["raw_updates_persisted"] is False
    assert evidence["source"] == "sandbox_contract"
    assert CHAT_ID not in saved
    assert get_telegram_offset(db_path) == 201


def test_baseline_cli_blocks_without_real_network_ack(tmp_path):
    from scripts.intel_telegram_baseline_offset import main

    output = tmp_path / "blocked.json"
    db_path = tmp_path / "baseline.db"
    missing_env = tmp_path / "missing.env"

    exit_code = main(["--db", str(db_path), "--env-path", str(missing_env), "--output", str(output)])

    assert exit_code == 2
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "blocked"
    assert saved["network_calls"] == 0
    assert saved["reply_sent"] is False
    assert get_telegram_offset(db_path) == 0
