from __future__ import annotations

import sqlite3

from src.intel.db.store import (
    record_delivery_artifact,
    save_intel_brief,
    save_intel_brief_localization,
)
from src.intel.subscriptions import (
    get_subscription_profile,
    grant_subscription,
    set_source_preferences,
    upsert_subscription_plan,
    upsert_telegram_subscriber,
)


class ReplaySender:
    def __init__(self):
        self.network_calls = 0
        self.messages = []
        self.callback_answers = 0

    def send(self, chat_id, text, *, parse_mode="HTML", reply_markup=None):
        self.network_calls += 1
        self.messages.append({"text": text, "reply_markup": reply_markup})
        return {
            "success": True,
            "message_id": str(self.network_calls),
            "network_calls": self.network_calls,
            "reply_markup_present": bool(reply_markup),
        }

    def answer_callback_query(self, callback_query_id, *, text=""):
        self.network_calls += 1
        self.callback_answers += 1
        return {"success": True, "network_calls": self.network_calls}


def _seed_brief(db_path):
    subscriber = upsert_telegram_subscriber(
        db_path,
        telegram_user_id="100",
        chat_id="200",
    )
    upsert_subscription_plan(db_path, plan_name="intel", categories=["ai_model_updates"])
    grant_subscription(
        db_path,
        user_id=subscriber["user_id"],
        plan_name="intel",
        starts_at="2026-08-01T00:00:00+00:00",
        expires_at="2026-09-01T00:00:00+00:00",
        source="test",
    )
    set_source_preferences(db_path, user_id=subscriber["user_id"], enabled_categories=["ai_model_updates"])
    zh = {
        "brief_date": "2026-08-04",
        "content_language": "zh",
        "items": [
            {
                "event_key": f"evt-{index}",
                "source": "ai_model_updates",
                "category": "ai",
                "title": f"中文条目 {index}",
                "summary": "完整摘要",
                "rank_score": 100 - index,
            }
            for index in range(1, 5)
        ],
    }
    en = {
        **zh,
        "content_language": "en",
        "items": [{**item, "title": f"English item {index}"} for index, item in enumerate(zh["items"], 1)],
    }
    brief = save_intel_brief(db_path, brief_date="2026-08-04", payload=zh)
    for language, payload in (("zh", zh), ("en", en)):
        save_intel_brief_localization(
            db_path,
            brief_id=brief["id"],
            language=language,
            translator_version="test-v1",
            status="translated",
            payload=payload,
        )
    return subscriber, brief, zh


def _callback(data):
    return {
        "update_id": 10,
        "callback_query": {
            "id": "callback-1",
            "data": data,
            "from": {"id": 100, "username": "reader"},
            "message": {"chat": {"id": 200}},
        },
    }


def test_view_all_callback_replays_same_full_brief(tmp_path):
    from src.intel.telegram_runtime import process_intel_telegram_updates

    db_path = tmp_path / "intel.db"
    _, brief, _ = _seed_brief(db_path)
    sender = ReplaySender()

    result = process_intel_telegram_updates(
        db_path,
        updates=[_callback(f"ib1:v:all:{brief['public_ref']}")],
        sender=sender,
        now="2026-08-04T01:00:00+00:00",
    )

    assert result["status"] == "success"
    assert "中文条目 4" in sender.messages[0]["text"]
    assert sender.callback_answers == 1


def test_language_callback_updates_preference_and_replays_same_brief(tmp_path):
    from src.intel.telegram_runtime import process_intel_telegram_updates

    db_path = tmp_path / "intel.db"
    subscriber, brief, _ = _seed_brief(db_path)
    sender = ReplaySender()

    process_intel_telegram_updates(
        db_path,
        updates=[_callback(f"ib1:l:en:{brief['public_ref']}")],
        sender=sender,
        now="2026-08-04T01:00:00+00:00",
    )

    profile = get_subscription_profile(db_path, user_id=subscriber["user_id"], now="2026-08-04T01:00:00+00:00")
    assert profile["delivery_preferences"]["content_language"] == "en"
    assert "English item 4" in sender.messages[0]["text"]


def test_language_callback_retries_partial_translation_after_provider_recovers(tmp_path, monkeypatch):
    from src.intel.db.store import get_intel_brief
    from src.intel.telegram_runtime import process_intel_telegram_updates

    class RecoveredProvider:
        provider_name = "recovered-provider"
        provider_version = "v2"
        ready = True

        def translate(self, text, *, source_language, target_language):
            import json

            payload = json.loads(text)
            return json.dumps({"texts": [f"EN: {value}" for value in payload["texts"]]}, ensure_ascii=False)

    db_path = tmp_path / "intel.db"
    _, brief, zh = _seed_brief(db_path)
    partial = {
        **zh,
        "content_language": "en",
        "localization": {
            "status": "partial_source_fallback",
            "target_language": "en",
            "source_fallback": True,
        },
    }
    save_intel_brief_localization(
        db_path,
        brief_id=brief["id"],
        language="en",
        translator_version="failed-v1",
        status="partial_source_fallback",
        payload=partial,
    )
    monkeypatch.setattr("src.intel.telegram_runtime.CCSwitchTranslationProvider", RecoveredProvider)
    sender = ReplaySender()

    process_intel_telegram_updates(
        db_path,
        updates=[_callback(f"ib1:l:en:{brief['public_ref']}")],
        sender=sender,
        now="2026-08-04T01:00:00+00:00",
    )

    recovered = get_intel_brief(db_path, public_ref=brief["public_ref"], language="en")
    assert recovered["localization_status"] == "translated"
    assert recovered["payload"]["items"][0]["title"].startswith("EN: ")
    assert "EN:" in sender.messages[0]["text"]


def test_brief_callbacks_do_not_reactivate_paused_subscriber(tmp_path):
    from src.intel.telegram_runtime import process_intel_telegram_updates

    db_path = tmp_path / "intel.db"
    subscriber, brief, _ = _seed_brief(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE subscribers SET status='paused' WHERE id=?", (subscriber["subscriber_id"],))
        conn.commit()

    sender = ReplaySender()
    for callback_data in (
        f"ib1:l:en:{brief['public_ref']}",
        f"ib1:v:all:{brief['public_ref']}",
    ):
        result = process_intel_telegram_updates(
            db_path,
            updates=[_callback(callback_data)],
            sender=sender,
            now="2026-08-04T01:00:00+00:00",
        )
        assert result["status"] == "success"
        profile = get_subscription_profile(
            db_path,
            user_id=subscriber["user_id"],
            now="2026-08-04T01:00:00+00:00",
        )
        assert profile["status"] == "paused"


def test_today_prefers_structured_artifact_over_truncated_delivery_log(tmp_path):
    from src.intel.channel_menu import handle_numbered_intel_command
    from src.intel.telegram_brief_renderer import build_brief_envelope

    db_path = tmp_path / "intel.db"
    subscriber, brief, zh = _seed_brief(db_path)
    envelope = build_brief_envelope(zh, brief_ref=brief["public_ref"], language="zh", cover_path="")
    record_delivery_artifact(
        db_path,
        delivery_log_id=None,
        subscriber_id=subscriber["subscriber_id"],
        brief_id=brief["id"],
        language="zh",
        render_mode="photo",
        message_ids=["55"],
        envelope=envelope.to_dict(),
    )

    result = handle_numbered_intel_command(
        db_path,
        channel="telegram",
        external_user_id="100",
        channel_user_id="200",
        number=700,
        now="2026-08-04T01:00:00+00:00",
    )

    assert "中文条目 4" in result["reply_text"]
    assert result["reply_markup"] == envelope.reply_markup
