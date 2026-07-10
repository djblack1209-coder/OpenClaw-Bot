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
