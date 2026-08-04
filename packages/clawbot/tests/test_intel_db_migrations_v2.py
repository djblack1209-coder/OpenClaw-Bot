from __future__ import annotations

import json
import sqlite3


def _legacy_database(path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL UNIQUE,
                channel_type TEXT NOT NULL,
                channel_user_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE delivery_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL UNIQUE,
                frequency TEXT NOT NULL DEFAULT 'daily',
                delivery_time TEXT NOT NULL DEFAULT '08:30',
                timezone TEXT NOT NULL DEFAULT 'America/Denver',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE delivery_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL,
                delivered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                content_summary TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            );
            INSERT INTO subscribers (user_id, channel_type, channel_user_id)
            VALUES ('tg:legacy', 'telegram', '10001');
            INSERT INTO delivery_preferences (subscriber_id, frequency, delivery_time, timezone)
            VALUES (1, 'daily', '08:30', 'America/Denver');
            INSERT INTO delivery_log (subscriber_id, content_summary, channel_type, success)
            VALUES (1, 'legacy brief', 'telegram', 1);
            """
        )


def test_v0_database_migrates_without_losing_rows(tmp_path):
    from src.intel.db.store import initialize_intel_db

    db_path = tmp_path / "legacy.db"
    _legacy_database(db_path)

    initialize_intel_db(db_path)
    initialize_intel_db(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(delivery_preferences)")}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        language = conn.execute("SELECT content_language FROM delivery_preferences").fetchone()[0]
        timezone_name = conn.execute("SELECT timezone FROM delivery_preferences").fetchone()[0]
        delivery_count = conn.execute("SELECT COUNT(*) FROM delivery_log").fetchone()[0]
        attempt_columns = {
            str(row[1]): row for row in conn.execute("PRAGMA table_info(content_delivery_attempts)")
        }
        versions = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]

    assert "content_language" in columns
    assert language == "zh"
    assert timezone_name == "Asia/Singapore"
    assert delivery_count == 1
    assert {"intel_briefs", "delivery_artifacts", "content_items", "telegram_media_assets", "delivery_claims"} <= tables
    assert "event_key" in attempt_columns
    assert attempt_columns["content_item_id"][3] == 0
    assert versions == [(1,), (2,), (3,), (4,)]
    assert user_version == 4
    assert quick_check == "ok"


def test_v2_database_applies_timezone_claim_and_event_key_migrations(tmp_path):
    from src.intel.db.store import initialize_intel_db

    db_path = tmp_path / "v2.db"
    _legacy_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE delivery_preferences SET frequency='weekly', delivery_time='09:00', timezone='America/Denver'"
        )
        conn.execute("PRAGMA user_version=2")

    initialize_intel_db(db_path)

    with sqlite3.connect(db_path) as conn:
        timezone_name = conn.execute("SELECT timezone FROM delivery_preferences").fetchone()[0]
        frequency, delivery_time = conn.execute("SELECT frequency, delivery_time FROM delivery_preferences").fetchone()
        claim_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='delivery_claims'"
        ).fetchone()
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert timezone_name == "Asia/Singapore"
    assert (frequency, delivery_time) == ("weekly", "08:30")
    assert claim_table == (1,)
    assert user_version == 4


def test_structured_brief_and_delivery_artifact_round_trip(tmp_path):
    from src.intel.db.store import (
        get_intel_brief,
        get_latest_delivery_artifact,
        initialize_intel_db,
        record_delivery_artifact,
        save_intel_brief,
        save_intel_brief_localization,
    )

    db_path = tmp_path / "intel.db"
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO subscribers (user_id, channel_type, channel_user_id) VALUES (?, 'telegram', ?)",
            ("tg:test", "10002"),
        )
        subscriber_id = conn.execute("SELECT id FROM subscribers").fetchone()[0]
        conn.commit()
    payload = {"brief_date": "2026-08-04", "items": [{"event_key": "evt-1", "title": "Signal"}]}
    brief = save_intel_brief(db_path, brief_date="2026-08-04", payload=payload)
    save_intel_brief_localization(
        db_path,
        brief_id=brief["id"],
        language="en",
        translator_version="test-v1",
        status="translated",
        payload={"brief_date": "2026-08-04", "items": [{"event_key": "evt-1", "title": "Signal EN"}]},
    )
    record_delivery_artifact(
        db_path,
        delivery_log_id=None,
        subscriber_id=subscriber_id,
        brief_id=brief["id"],
        language="en",
        render_mode="photo",
        message_ids=["42"],
        envelope={"brief_ref": brief["public_ref"], "caption_html": "Signal EN"},
        media_asset_key="cover:test",
    )

    localized = get_intel_brief(db_path, public_ref=brief["public_ref"], language="en")
    artifact = get_latest_delivery_artifact(db_path, subscriber_id=subscriber_id)

    assert localized["payload"]["items"][0]["title"] == "Signal EN"
    assert localized["localization_status"] == "translated"
    assert artifact["public_ref"] == brief["public_ref"]
    assert artifact["message_ids"] == ["42"]
    assert json.dumps(artifact, ensure_ascii=False).find("10002") == -1


def test_delivery_claim_recovers_stale_lease_and_fences_old_owner(tmp_path):
    from src.intel.db.store import claim_delivery, finalize_delivery_claim, save_intel_brief

    db_path = tmp_path / "intel-claim.db"
    _legacy_database(db_path)
    brief = save_intel_brief(db_path, brief_date="2026-08-04", payload={"items": []})
    first = claim_delivery(
        db_path,
        subscriber_id=1,
        brief_id=brief["id"],
        brief_date="2026-08-04",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE delivery_claims SET lease_expires_at='2000-01-01 00:00:00' WHERE subscriber_id=1")
        conn.commit()

    second = claim_delivery(
        db_path,
        subscriber_id=1,
        brief_id=brief["id"],
        brief_date="2026-08-04",
    )

    assert first["acquired"] is True
    assert second["acquired"] is True
    assert second["reason"] == "stale_lease_recovered"
    assert second["attempt_count"] == 2
    assert (
        finalize_delivery_claim(
            db_path,
            subscriber_id=1,
            brief_date="2026-08-04",
            claim_token=first["claim_token"],
            state="sent",
        )
        is False
    )
    assert (
        finalize_delivery_claim(
            db_path,
            subscriber_id=1,
            brief_date="2026-08-04",
            claim_token=second["claim_token"],
            state="sent",
        )
        is True
    )
