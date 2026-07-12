"""数据库备份必须可并发保护、可校验，并能在可丢弃目录完成恢复演练。"""

from __future__ import annotations

import fcntl
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from scripts import backup_databases
from src.execution import scheduler as scheduler_module


def _create_database(path: Path, rows: tuple[str, ...] = ("alpha", "beta")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany("INSERT INTO records(value) VALUES (?)", ((value,) for value in rows))
        connection.commit()


def test_backup_discovers_new_database_and_writes_verified_manifest(tmp_path):
    data_dir = tmp_path / "data"
    backup_dir = tmp_path / "backups"
    _create_database(data_dir / "trading.db")
    _create_database(data_dir / "future_module.db", ("new",))

    results = backup_databases.backup_all(
        data_dir=data_dir,
        backup_dir=backup_dir,
        now=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )

    assert results["trading.db"].startswith("OK")
    assert results["future_module.db"].startswith("OK")
    manifest_path = backup_dir / "manifest_2026-07-12.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["ok"] is True
    assert {entry["source_name"] for entry in manifest["databases"]} >= {
        "trading.db",
        "future_module.db",
    }
    for entry in manifest["databases"]:
        artifact = backup_dir / entry["artifact"]
        assert artifact.is_file()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == entry["sha256"]
        assert artifact.stat().st_mode & 0o077 == 0
    assert {path.name for path in backup_dir.glob(".*")} <= {".backup.lock"}


def test_backup_refuses_concurrent_run_without_writing_partial_files(tmp_path):
    data_dir = tmp_path / "data"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_database(data_dir / "trading.db")

    lock_path = backup_dir / ".backup.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        results = backup_databases.backup_all(
            data_dir=data_dir,
            backup_dir=backup_dir,
            now=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
        )

    assert results["_lock"].startswith("FAILED")
    assert not list(backup_dir.glob("trading_*.db"))


def test_backup_fails_closed_when_free_space_is_insufficient(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    backup_dir = tmp_path / "backups"
    _create_database(data_dir / "trading.db")
    monkeypatch.setattr(backup_databases, "_available_bytes", lambda _path: 0)

    results = backup_databases.backup_all(
        data_dir=data_dir,
        backup_dir=backup_dir,
        now=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )

    assert results["_preflight"].startswith("FAILED")
    assert not list(backup_dir.glob("trading_*.db"))
    status = json.loads((backup_dir / "latest-status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"


def test_restore_drill_recreates_readable_database_in_disposable_directory(tmp_path):
    data_dir = tmp_path / "data"
    backup_dir = tmp_path / "backups"
    restore_dir = tmp_path / "restored"
    _create_database(data_dir / "execution_hub.db", ("one", "two", "three"))

    backup_databases.backup_all(
        data_dir=data_dir,
        backup_dir=backup_dir,
        now=datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
    )
    result = backup_databases.restore_drill(
        backup_dir=backup_dir,
        restore_dir=restore_dir,
        manifest_path=backup_dir / "manifest_2026-07-12.json",
    )

    assert result["ok"] is True
    assert result["verified_databases"] == 1
    with sqlite3.connect(restore_dir / "execution_hub.db") as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT COUNT(*) FROM records").fetchone() == (3,)


def test_daily_scheduler_returns_failure_summary_and_notifies_once(monkeypatch):
    monkeypatch.setattr(
        backup_databases,
        "backup_all",
        lambda: {"trading.db": "FAILED: disk full", "_cleanup": "Removed 0 old backups"},
    )

    summary = scheduler_module._run_daily_db_backup()

    assert summary == {"ok": 0, "skipped": 0, "failed": 1}


@pytest.mark.asyncio
async def test_scheduler_backup_failure_sends_private_actionable_alert(monkeypatch):
    task_scheduler = scheduler_module.ExecutionScheduler()
    task_scheduler._private_notify_func = AsyncMock()
    monkeypatch.setattr(
        scheduler_module,
        "_run_daily_db_backup",
        lambda: {"ok": 0, "skipped": 0, "failed": 1},
    )
    now = datetime(2026, 7, 12, 4, 0, tzinfo=UTC)

    await task_scheduler._run_cleanup(now)
    await task_scheduler._run_cleanup(now)

    task_scheduler._private_notify_func.assert_awaited_once()
    message = task_scheduler._private_notify_func.await_args.args[0]
    assert "数据库备份失败" in message
    assert "不会自动覆盖生产数据" in message
