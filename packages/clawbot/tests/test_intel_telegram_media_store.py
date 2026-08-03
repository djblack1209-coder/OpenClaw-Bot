from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


class FakePhotoSender:
    def __init__(self):
        self.calls = 0

    def send_photo(self, chat_id, photo, **kwargs):
        self.calls += 1
        assert chat_id == "-100-private"
        assert Path(photo).is_file()
        return {
            "success": True,
            "photo_file_id": "telegram-file-id",
            "photo_file_unique_id": "telegram-unique-id",
        }


def test_private_telegram_media_store_uploads_once_then_reuses_file_id(tmp_path):
    from src.intel.telegram_media_store import SqliteTelegramMediaStore

    db_path = tmp_path / "intel.db"
    source = Path(__file__).resolve().parents[1] / "assets" / "intel" / "openclaw-intel-brief-dark.jpg"
    sender = FakePhotoSender()
    media_store = SqliteTelegramMediaStore(
        db_path=db_path,
        sender=sender,
        env={"INTEL_BRIEF_TELEGRAM_MEDIA_CHAT_ID": "-100-private"},
    )

    first = media_store.put_photo("cover:2026-08-04", source)
    second = media_store.put_photo("cover:2026-08-04", source)

    assert sender.calls == 1
    assert first.file_id == second.file_id == "telegram-file-id"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT file_id, file_unique_id, invalidated_at FROM telegram_media_assets").fetchone()
    assert row == ("telegram-file-id", "telegram-unique-id", None)


def test_media_store_rejects_non_image_before_network(tmp_path):
    import pytest

    from src.intel.telegram_media_store import SqliteTelegramMediaStore, TelegramMediaStoreError

    source = tmp_path / "not-image.txt"
    source.write_text("not an image", encoding="utf-8")
    sender = FakePhotoSender()
    media_store = SqliteTelegramMediaStore(
        db_path=tmp_path / "intel.db",
        sender=sender,
        env={"INTEL_BRIEF_TELEGRAM_MEDIA_CHAT_ID": "-100-private"},
    )

    with pytest.raises(TelegramMediaStoreError, match="JPEG"):
        media_store.put_photo("bad", source)
    assert sender.calls == 0


class FakeDeliveryPhotoSender:
    def __init__(self):
        self.network_calls = 0
        self.calls = []

    def send_photo(self, chat_id, photo, **kwargs):
        self.network_calls += 1
        self.calls.append({"chat_id": chat_id, "photo": str(photo), "caption": kwargs.get("caption", "")})
        if chat_id == "-100-private":
            return {
                "success": True,
                "photo_file_id": "telegram-file-id",
                "photo_file_unique_id": "telegram-unique-id",
            }
        return {
            "success": True,
            "message_id": str(self.network_calls),
            "photo_file_id": "telegram-file-id",
            "photo_file_unique_id": "telegram-unique-id",
        }

    def send(self, chat_id, text, **kwargs):
        raise AssertionError("封面发送成功时不应降级为纯文本")


def test_daily_delivery_reuses_same_cover_file_id_across_dates(tmp_path):
    from src.intel.subscription_delivery import deliver_summary_to_eligible_subscribers
    from src.intel.subscriptions import (
        grant_subscription,
        set_source_preferences,
        upsert_subscription_plan,
        upsert_telegram_subscriber,
    )

    db_path = tmp_path / "intel.db"
    upsert_subscription_plan(db_path, plan_name="intel", categories=["ai_model_updates"])
    subscriber = upsert_telegram_subscriber(db_path, telegram_user_id="100", chat_id="200")
    grant_subscription(
        db_path,
        user_id=subscriber["user_id"],
        plan_name="intel",
        starts_at="2026-08-01T00:00:00+00:00",
        expires_at="2026-09-01T00:00:00+00:00",
    )
    set_source_preferences(db_path, user_id=subscriber["user_id"], enabled_categories=["ai_model_updates"])
    sender = FakeDeliveryPhotoSender()

    deliveries = (
        ("2026-08-04", "100:test-token"),
        ("2026-08-05", "100:rotated-token"),
        ("2026-08-06", "200:other-bot-token"),
    )
    for day, bot_token in deliveries:
        summary_path = tmp_path / f"{day}.json"
        summary_path.write_text(
            json.dumps(
                {
                    "brief_date": day,
                    "items": [
                        {
                            "event_key": f"event-{day}",
                            "source": "ai_model_updates",
                            "category": "ai",
                            "title": f"Model update {day}",
                            "published_at": f"{day}T00:00:00+00:00",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        result = deliver_summary_to_eligible_subscribers(
            db_path=db_path,
            summary_evidence_path=summary_path,
            sender=sender,
            now=f"{day}T00:30:00+00:00",
            env={
                "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": bot_token,
            },
        )
        assert result["summary"]["sent"] == 1

    media_uploads = [call for call in sender.calls if call["chat_id"] == "-100-private"]
    subscriber_sends = [call for call in sender.calls if call["chat_id"] == "200"]
    assert len(media_uploads) == 0
    assert len(subscriber_sends) == 3
    assert subscriber_sends[0]["photo"].endswith("openclaw-intel-brief-dark.jpg")
    assert subscriber_sends[1]["photo"] == "telegram-file-id"
    assert subscriber_sends[2]["photo"].endswith("openclaw-intel-brief-dark.jpg")
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT asset_key, file_id FROM telegram_media_assets").fetchall()
    assert len(rows) == 2
    assert all(row[0].startswith("daily-cover:") and ":terminal-v2:" in row[0] for row in rows)
    assert all("2026-08" not in row[0] for row in rows)
    fingerprints = {hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] for value in ("100", "200")}
    assert {row[0].split(":", 2)[1] for row in rows} == fingerprints
    assert {row[1] for row in rows} == {"telegram-file-id"}
