"""每日资讯中央运行健康汇总。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_SOURCES = {
    "senate_trading",
    "akshare",
    "github_trending",
    "ai_model_updates",
    "institutional_13f",
    "weather",
}


def _unavailable_database_health(
    *,
    database: Path,
    evidence_dir: Path,
    current: datetime,
    reason: str,
) -> dict[str, Any]:
    """在数据库不可读时返回稳定的故障结构，不修改生产状态。"""
    event_file_count, event_bytes = _evidence_usage(evidence_dir)
    return {
        "status": "bad",
        "ok": False,
        "checks": {
            "database_quick_check": False,
            "source_health_coverage": False,
            "source_attempts_recent": False,
            "listener_file_limit": event_file_count <= 2000,
            "listener_size_limit": event_bytes <= 100 * 1024 * 1024,
            "listener_heartbeat_recent": False,
        },
        "hard_failures": ["database_quick_check"],
        "warmup": [
            "source_health_coverage",
            "source_attempts_recent",
            "listener_heartbeat_recent",
        ],
        "source_health": {
            "coverage": 0,
            "expected": len(EXPECTED_SOURCES),
            "missing_sources": sorted(EXPECTED_SOURCES),
            "stale_sources": [],
        },
        "cycles_7d": {"counts": {}, "availability": None, "target": 0.95},
        "deliveries_7d": {"counts": {}, "success_rate": None, "target": 0.99},
        "listener": {
            "heartbeat_age_seconds": None,
            "event_file_count": event_file_count,
            "event_bytes": event_bytes,
            "file_limit": 2000,
            "byte_limit": 100 * 1024 * 1024,
        },
        "database": {"path": str(database), "error": reason},
        "generated_at": current.isoformat(),
    }


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)  # noqa: UP017
    return parsed.astimezone(timezone.utc)  # noqa: UP017


def _evidence_usage(path: Path) -> tuple[int, int]:
    if not path.is_dir():
        return 0, 0
    count = 0
    total = 0
    for item in path.iterdir():
        if not item.is_file():
            continue
        count += 1
        try:
            total += item.stat().st_size
        except OSError:
            continue
    return count, total


def build_intel_runtime_health(
    *,
    db_path: str | Path,
    listener_evidence_dir: str | Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """汇总数据库、来源、周期、投递与 listener 证据指标。"""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)  # noqa: UP017
    database = Path(db_path)
    evidence_dir = Path(listener_evidence_dir)
    if not database.is_file():
        return _unavailable_database_health(
            database=database,
            evidence_dir=evidence_dir,
            current=current,
            reason="database_missing",
        )
    try:
        database_uri = f"{database.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(database_uri, uri=True) as conn:
            quick_check = str(conn.execute("PRAGMA quick_check").fetchone()[0])
            health_rows = conn.execute(
                """
                SELECT source_name, last_status, last_attempt_at, consecutive_failures
                FROM source_health ORDER BY source_name
                """
            ).fetchall()
            cycle_rows = conn.execute(
                """
                SELECT status, COUNT(*) FROM brief_runs
                WHERE created_at >= datetime('now', '-7 days') GROUP BY status
                """
            ).fetchall()
            delivery_rows = conn.execute(
                """
                SELECT delivery_state, COUNT(*) FROM delivery_artifacts
                WHERE created_at >= datetime('now', '-7 days') GROUP BY delivery_state
                """
            ).fetchall()
    except sqlite3.Error as exc:
        return _unavailable_database_health(
            database=database,
            evidence_dir=evidence_dir,
            current=current,
            reason=f"database_unreadable:{type(exc).__name__}",
        )
    source_names = {str(row[0]) for row in health_rows}
    source_coverage = len(EXPECTED_SOURCES.intersection(source_names))
    missing_sources = sorted(EXPECTED_SOURCES - source_names)
    attempts_stale = []
    for row in health_rows:
        if str(row[0]) not in EXPECTED_SOURCES:
            continue
        attempted = _parse_datetime(row[2])
        if attempted is None or (current - attempted).total_seconds() > 8 * 24 * 3600:
            attempts_stale.append(str(row[0]))

    event_file_count, event_bytes = _evidence_usage(evidence_dir)
    heartbeat_path = evidence_dir / "heartbeat.json"
    heartbeat_age_seconds = None
    if heartbeat_path.is_file():
        try:
            heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            heartbeat_at = _parse_datetime(heartbeat.get("timestamp") or heartbeat.get("updated_at"))
            if heartbeat_at is not None:
                heartbeat_age_seconds = max(0, int((current - heartbeat_at).total_seconds()))
        except (json.JSONDecodeError, OSError):
            heartbeat_age_seconds = None

    cycles = {str(status): int(count) for status, count in cycle_rows}
    cycle_total = sum(cycles.values())
    usable_cycles = cycles.get("success", 0) + cycles.get("partial_success", 0)
    cycle_availability = round(usable_cycles / cycle_total, 4) if cycle_total else None
    deliveries = {str(status): int(count) for status, count in delivery_rows}
    delivery_total = sum(deliveries.values())
    delivery_success_rate = round(deliveries.get("sent", 0) / delivery_total, 4) if delivery_total else None

    checks = {
        "database_quick_check": quick_check == "ok",
        "source_health_coverage": source_coverage == len(EXPECTED_SOURCES),
        "source_attempts_recent": not attempts_stale and source_coverage == len(EXPECTED_SOURCES),
        "listener_file_limit": event_file_count <= 2000,
        "listener_size_limit": event_bytes <= 100 * 1024 * 1024,
        "listener_heartbeat_recent": heartbeat_age_seconds is not None and heartbeat_age_seconds <= 120,
    }
    hard_failures = [
        name for name in ("database_quick_check", "listener_file_limit", "listener_size_limit") if not checks[name]
    ]
    warmup = [name for name, passed in checks.items() if not passed and name not in hard_failures]
    status = "bad" if hard_failures else ("warn" if warmup else "ok")
    return {
        "status": status,
        "ok": status != "bad",
        "checks": checks,
        "hard_failures": hard_failures,
        "warmup": warmup,
        "source_health": {
            "coverage": source_coverage,
            "expected": len(EXPECTED_SOURCES),
            "missing_sources": missing_sources,
            "stale_sources": sorted(attempts_stale),
        },
        "cycles_7d": {
            "counts": cycles,
            "availability": cycle_availability,
            "target": 0.95,
        },
        "deliveries_7d": {
            "counts": deliveries,
            "success_rate": delivery_success_rate,
            "target": 0.99,
        },
        "listener": {
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "event_file_count": event_file_count,
            "event_bytes": event_bytes,
            "file_limit": 2000,
            "byte_limit": 100 * 1024 * 1024,
        },
        "generated_at": current.isoformat(),
    }
