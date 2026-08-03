from __future__ import annotations

import json
from datetime import UTC, datetime


def test_runtime_health_reports_source_coverage_and_listener_limits(tmp_path):
    from src.intel.db.store import record_source_attempt
    from src.intel.runtime_health import EXPECTED_SOURCES, build_intel_runtime_health

    db_path = tmp_path / "intel.db"
    evidence_dir = tmp_path / "listener"
    evidence_dir.mkdir()
    now = datetime(2026, 8, 4, 1, 0, tzinfo=UTC)
    (evidence_dir / "heartbeat.json").write_text(json.dumps({"timestamp": now.isoformat()}), encoding="utf-8")
    for source in EXPECTED_SOURCES:
        record_source_attempt(
            db_path,
            run_key="run-1",
            source_name=source,
            attempted_at=now.isoformat(),
            status="success",
            item_count=1,
        )
    record_source_attempt(
        db_path,
        run_key="retired-run",
        source_name="retired_source",
        attempted_at="2020-01-01T00:00:00+00:00",
        status="failed",
    )

    result = build_intel_runtime_health(
        db_path=db_path,
        listener_evidence_dir=evidence_dir,
        now=now,
    )

    assert result["status"] == "ok"
    assert result["source_health"]["coverage"] == 6
    assert result["listener"]["event_file_count"] == 1
    assert result["checks"]["listener_heartbeat_recent"] is True
    assert result["source_health"]["stale_sources"] == []


def test_runtime_health_marks_evidence_explosion_as_bad(tmp_path):
    from src.intel.db.store import initialize_intel_db
    from src.intel.runtime_health import build_intel_runtime_health

    db_path = tmp_path / "intel.db"
    initialize_intel_db(db_path)
    evidence_dir = tmp_path / "listener"
    evidence_dir.mkdir()
    for index in range(2001):
        (evidence_dir / f"event-{index}.json").touch()

    result = build_intel_runtime_health(
        db_path=db_path,
        listener_evidence_dir=evidence_dir,
        now=datetime(2026, 8, 4, 1, 0, tzinfo=UTC),
    )

    assert result["status"] == "bad"
    assert "listener_file_limit" in result["hard_failures"]


def test_runtime_health_does_not_create_missing_database(tmp_path):
    from src.intel.runtime_health import build_intel_runtime_health

    db_path = tmp_path / "missing.db"

    result = build_intel_runtime_health(
        db_path=db_path,
        listener_evidence_dir=tmp_path / "listener",
        now=datetime(2026, 8, 4, 1, 0, tzinfo=UTC),
    )

    assert result["status"] == "bad"
    assert result["database"]["error"] == "database_missing"
    assert not db_path.exists()
