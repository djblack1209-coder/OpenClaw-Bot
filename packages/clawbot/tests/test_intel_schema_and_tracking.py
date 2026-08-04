import sqlite3

from src.intel.db.store import initialize_intel_db, subscribe_tracking_target


def _tables(db_path):
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def test_intel_schema_uses_open_tracking_tables(tmp_path):
    db_path = tmp_path / "intel_brief.db"

    initialize_intel_db(db_path)

    tables = _tables(db_path)
    assert "subscribers" in tables
    assert "subscription_plans" in tables
    assert "user_subscriptions" in tables
    assert "source_preferences" in tables
    assert "tracking_targets" in tables
    assert "tracking_subscriptions" in tables
    assert "tracking_audit_log" in tables
    assert "content_moderation_log" in tables
    assert "delivery_log" in tables
    assert "source_health" in tables
    assert "celebrity_watchlist" not in tables
    assert "celebrity_subscriptions" not in tables


def test_initialize_intel_db_migrates_legacy_delivery_attempt_event_keys(tmp_path):
    db_path = tmp_path / "legacy-intel-brief.db"
    with sqlite3.connect(db_path) as conn:
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
            CREATE TABLE intel_briefs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_ref TEXT NOT NULL UNIQUE,
                brief_date TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                source_payload TEXT NOT NULL,
                item_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (brief_date, content_hash)
            );
            CREATE TABLE content_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                content_kind TEXT NOT NULL,
                source_item_id TEXT NOT NULL,
                event_key TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                category TEXT NOT NULL,
                provider TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                event_at TEXT,
                published_at TEXT,
                observed_at TEXT NOT NULL,
                date_confidence TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                evidence_path TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (source_name, event_key)
            );
            CREATE TABLE content_delivery_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL,
                content_item_id INTEGER NOT NULL,
                brief_id INTEGER,
                state TEXT NOT NULL CHECK (state IN ('pending', 'sent', 'failed', 'unknown')),
                attempt_count INTEGER NOT NULL DEFAULT 1,
                last_error TEXT,
                attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (subscriber_id, content_item_id)
            );
            INSERT INTO subscribers (id, user_id, channel_type, channel_user_id)
            VALUES (1, 'tg:legacy', 'telegram', 'legacy');
            INSERT INTO intel_briefs (id, public_ref, brief_date, content_hash, source_payload)
            VALUES (1, 'legacy-ref', '2026-08-04', 'legacy-hash', '{}');
            INSERT INTO content_items (
                id, source_name, content_kind, source_item_id, event_key, entity_key,
                category, provider, title, observed_at, date_confidence
            ) VALUES (
                1, 'github_trending', 'repository', 'legacy-item', 'github:legacy-item',
                'repo:legacy-item', 'technology', 'github', 'Legacy item',
                '2026-08-04T00:00:00+00:00', 'exact'
            );
            INSERT INTO content_delivery_attempts (
                subscriber_id, content_item_id, brief_id, state, attempt_count
            ) VALUES (1, 1, 1, 'sent', 2);
            PRAGMA user_version=3;
            """
        )

    initialize_intel_db(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {str(row[1]): row for row in conn.execute("PRAGMA table_info(content_delivery_attempts)")}
        attempt = conn.execute(
            """
            SELECT subscriber_id, content_item_id, event_key, brief_id, state, attempt_count
            FROM content_delivery_attempts
            """
        ).fetchone()
        schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])

    assert "event_key" in columns
    assert columns["content_item_id"][3] == 0
    assert attempt == (1, 1, "github:legacy-item", 1, "sent", 2)
    assert schema_version == 4


def test_subscribe_tracking_target_reuses_target_and_writes_audit(tmp_path):
    db_path = tmp_path / "intel_brief.db"
    initialize_intel_db(db_path)

    first = subscribe_tracking_target(
        db_path,
        user_id="tg:1001",
        channel_type="telegram",
        channel_user_id="1001",
        target_name="  Taylor Swift  ",
        source_channel="telegram_menu",
    )
    second = subscribe_tracking_target(
        db_path,
        user_id="tg:1002",
        channel_type="telegram",
        channel_user_id="1002",
        target_name="Taylor Swift",
        source_channel="telegram_menu",
    )

    assert first["target_id"] == second["target_id"]
    assert first["normalized_name"] == "taylor swift"
    assert second["active_subscription_count"] == 2

    with sqlite3.connect(db_path) as conn:
        target_rows = conn.execute("SELECT name, normalized_name, active_subscription_count FROM tracking_targets").fetchall()
        audit_rows = conn.execute(
            "SELECT subscriber_user_id, target_name, source_channel FROM tracking_audit_log ORDER BY id"
        ).fetchall()

    assert target_rows == [("Taylor Swift", "taylor swift", 2)]
    assert audit_rows == [
        ("tg:1001", "Taylor Swift", "telegram_menu"),
        ("tg:1002", "Taylor Swift", "telegram_menu"),
    ]


def test_record_source_health_success_resets_failure_count(tmp_path):
    from src.intel.db.store import get_source_health, record_source_health

    db_path = tmp_path / "intel.db"

    failed = record_source_health(db_path, "senate_trading", "failed", failure_reason="HTTP 403")
    assert failed["source_name"] == "senate_trading"
    assert failed["failure_count"] == 1
    assert failed["last_failure_reason"] == "HTTP 403"

    success = record_source_health(db_path, "senate_trading", "success")
    assert success["failure_count"] == 0
    assert success["last_failure_reason"] == ""
    assert success["last_success_at"]

    persisted = get_source_health(db_path, "senate_trading")
    assert persisted == success


def test_record_source_health_failure_increments_count(tmp_path):
    from src.intel.db.store import get_source_health, record_source_health

    db_path = tmp_path / "intel.db"

    first = record_source_health(db_path, "github_trending", "failed", failure_reason="rate limited")
    second = record_source_health(db_path, "github_trending", "failed", failure_reason="rate limited again")

    assert first["failure_count"] == 1
    assert second["failure_count"] == 2
    assert second["last_failure_reason"] == "rate limited again"
    assert get_source_health(db_path, "github_trending")["failure_count"] == 2
