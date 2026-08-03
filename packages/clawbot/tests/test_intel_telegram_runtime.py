from __future__ import annotations

import json

from src.intel.subscriptions import get_subscription_profile, grant_subscription, upsert_subscription_plan

NOW = "2026-07-07T16:30:00+00:00"
FAKE_CHAT_ID = "runtime-chat-should-not-leak"


class FakeReplySender:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.network_calls = 0

    def send(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.sent.append({"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "reply_markup": reply_markup})
        return {
            "success": True,
            "network": "fake_sender",
            "network_calls": 0,
            "chat_id_present": bool(chat_id),
            "message_id": f"fake-{len(self.sent)}",
            "endpoint": "fake://telegram/sendMessage",
            "reply_markup_present": bool(reply_markup),
        }


def _update(update_id: int, text: str, *, user_id: str = "runtime-user") -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id + 100,
            "text": text,
            "from": {"id": user_id, "username": "runtime_tester"},
            "chat": {"id": FAKE_CHAT_ID, "type": "private"},
        },
    }


def test_runtime_processes_telegram_update_with_injected_sender_and_redacted_evidence(tmp_path):
    from src.intel.telegram_runtime import process_intel_telegram_updates

    db_path = tmp_path / "runtime.db"
    sender = FakeReplySender()

    result = process_intel_telegram_updates(
        db_path,
        updates=[_update(1, "/start")],
        sender=sender,
        now=NOW,
    )

    assert result["status"] == "success"
    assert result["updates_seen"] == 1
    assert result["handled_count"] == 1
    assert result["send_success_count"] == 1
    assert result["network_calls"] == 0
    assert len(sender.sent) == 2
    assert sender.sent[0]["chat_id"] == FAKE_CHAT_ID
    assert "快捷入口" in str(sender.sent[0]["text"])
    assert sender.sent[0]["reply_markup"]["keyboard"] == [[{"text": "🧭 今日简报"}, {"text": "📌 我的订阅"}]]
    assert "700 今日简报" in str(sender.sent[1]["text"])
    assert sender.sent[1]["reply_markup"]["inline_keyboard"][0][0]["text"] == "🧭 今日简报"
    assert result["handled_updates"][0]["reply_message_count"] == 2
    assert result["handled_updates"][0]["persistent_keyboard_sent"] is True
    assert result["handled_updates"][0]["inline_keyboard_sent"] is True
    assert result["replies"][0]["chat_id_present"] is True
    assert FAKE_CHAT_ID not in json.dumps(result, ensure_ascii=False)

    profile = get_subscription_profile(db_path, user_id="tg:runtime-user", now=NOW)
    assert profile["status"] == "inactive_or_expired"
    assert profile["channel_type"] == "telegram"


def test_runtime_escapes_tracking_name_before_html_reply(tmp_path):
    from src.intel.telegram_runtime import process_intel_telegram_updates

    sender = FakeReplySender()
    result = process_intel_telegram_updates(
        tmp_path / "runtime.db",
        updates=[_update(1, "/custom <b&signal")],
        sender=sender,
        now=NOW,
    )

    assert result["status"] == "success"
    assert len(sender.sent) == 1
    assert "&lt;b&amp;signal" in str(sender.sent[0]["text"])
    assert "<b&signal" not in str(sender.sent[0]["text"])


def test_runtime_handles_active_user_configuration_commands(tmp_path):
    from src.intel.telegram_runtime import process_intel_telegram_updates

    db_path = tmp_path / "runtime.db"
    sender = FakeReplySender()
    start = process_intel_telegram_updates(db_path, updates=[_update(1, "/start")], sender=sender, now=NOW)
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare", "senate_trading"])
    grant_subscription(
        db_path,
        user_id=start["handled_updates"][0]["subscriber_user_id"],
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at="2026-08-07T00:00:00+00:00",
        source="runtime_contract_test",
    )

    result = process_intel_telegram_updates(
        db_path,
        updates=[
            _update(2, "/sources akshare senate_trading"),
            _update(3, "/schedule daily 08:30 Asia/Singapore"),
            _update(4, "/custom 周杰伦"),
            _update(5, "/status"),
        ],
        sender=sender,
        now=NOW,
    )

    assert result["status"] == "success"
    assert result["handled_count"] == 4
    assert [item["command"] for item in result["handled_updates"]] == ["sources", "schedule", "custom", "status"]
    assert result["send_success_count"] == 4
    assert result["tracking_targets"] == [{"name": "周杰伦", "active_subscription_count": 1}]
    assert FAKE_CHAT_ID not in json.dumps(result, ensure_ascii=False)

    profile = get_subscription_profile(db_path, user_id="tg:runtime-user", now=NOW)
    assert profile["eligible"] is True
    assert profile["enabled_categories"] == ["akshare", "senate_trading"]
    assert profile["delivery_preferences"] == {
        "frequency": "daily",
        "delivery_time": "08:30",
        "timezone": "Asia/Singapore",
        "content_language": "zh",
    }


def test_runtime_sandbox_evidence_builder_replays_full_user_flow_without_network(tmp_path):
    from scripts.intel_telegram_runtime_sandbox import build_intel_telegram_runtime_sandbox_evidence

    evidence_dir = tmp_path / "runtime-evidence"
    evidence = build_intel_telegram_runtime_sandbox_evidence(evidence_dir, now=NOW)

    assert evidence["status"] == "success"
    assert evidence["phase"] == "AA-telegram-runtime-adapter-sandbox"
    assert evidence["network_calls"] == 0
    assert evidence["runtime"]["handled_count"] == 5
    assert evidence["runtime"]["send_success_count"] == 5
    assert evidence["runtime"]["handled_updates"][0]["reply_message_count"] == 2
    assert evidence["final_profile"]["status"] == "active"
    assert evidence["final_profile"]["enabled_categories"] == ["akshare", "senate_trading"]
    assert evidence["tracking_targets"] == [{"name": "周杰伦", "active_subscription_count": 1}]
    assert evidence["redaction"]["chat_id_present_only"] is True
    saved = (evidence_dir / "evidence.json").read_text(encoding="utf-8")
    assert FAKE_CHAT_ID not in saved
    assert (evidence_dir / "intel_telegram_runtime_sandbox.db").exists()
