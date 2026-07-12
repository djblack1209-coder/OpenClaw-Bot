#!/usr/bin/env python3
"""OpenClaw SQLite 备份与可丢弃恢复演练。

默认由 ExecutionScheduler 每日 04:00 ET 调用。实现只使用 Python 标准库：
- 非阻塞文件锁，避免并发重复备份；
- 备份前空间预检；
- SQLite 在线备份、完整性检查、SHA-256 和原子替换；
- 每日/每周保留策略；
- 机器可读 manifest 和 latest-status；
- 只恢复到可丢弃目录的演练入口，不覆盖生产数据库。
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PACKAGE_ROOT / "data"
BACKUP_DIR = DATA_DIR / "backups"
STATUS_FILE_NAME = "latest-status.json"
LOCK_FILE_NAME = ".backup.lock"
MANIFEST_VERSION = 1
MIN_FREE_SPACE_BYTES = 16 * 1024 * 1024

# 保留兼容名单，同时通过目录发现自动纳入未来新增数据库。
DATABASES = [
    "trading.db",
    "portfolio.db",
    "history.db",
    "shared_memory.db",
    "execution_hub.db",
    "xianyu_chat.db",
    "feedback.db",
    "cost_analytics.db",
    "deploy_licenses.db",
    "novels.db",
    "auto_shipper.db",
    "intel_brief.db",
    "blackfriday_seen.db",
]

_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})(?:\.[^.]+)$")


@dataclass(frozen=True)
class DatabaseSource:
    """一个需要保护的 SQLite 数据源；logical_name 不包含真实绝对路径。"""

    logical_name: str
    path: Path
    scope: str


def _utc_now(now: datetime | None = None) -> datetime:
    """把调用方时间统一为 UTC，便于命名和证据比较。"""
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _available_bytes(path: Path) -> int:
    """返回目标文件系统可用字节，独立函数便于确定性测试。"""
    return int(shutil.disk_usage(path).free)


def _sha256(path: Path) -> str:
    """流式计算文件摘要，不把数据库内容读入日志。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quote_identifier(value: str) -> str:
    """安全引用 SQLite 标识符，仅用于 manifest 行数核验。"""
    return '"' + str(value).replace('"', '""') + '"'


def _sqlite_metadata(path: Path) -> dict[str, Any]:
    """验证 SQLite 可读性并返回不含业务内容的结构摘要。"""
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30) as connection:
        connection.execute("PRAGMA query_only = ON")
        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        if not integrity_rows or any(str(row[0]).lower() != "ok" for row in integrity_rows):
            detail = "; ".join(str(row[0]) for row in integrity_rows[:3]) or "no result"
            raise sqlite3.DatabaseError(f"integrity_check failed: {detail}")
        quick_rows = connection.execute("PRAGMA quick_check").fetchall()
        if not quick_rows or any(str(row[0]).lower() != "ok" for row in quick_rows):
            detail = "; ".join(str(row[0]) for row in quick_rows[:3]) or "no result"
            raise sqlite3.DatabaseError(f"quick_check failed: {detail}")
        table_rows = connection.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND COALESCE(sql, '') NOT LIKE 'CREATE VIRTUAL TABLE%' "
            "ORDER BY name"
        ).fetchall()
        table_counts: dict[str, int] = {}
        for (table_name,) in table_rows:
            row = connection.execute(
                f"SELECT COUNT(*) FROM {_quote_identifier(str(table_name))}"
            ).fetchone()
            table_counts[str(table_name)] = int(row[0] if row else 0)
        schema_objects = int(
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_schema "
                "WHERE type IN ('table','index','trigger','view')"
            ).fetchone()[0]
        )
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    return {
        "integrity_check": "ok",
        "quick_check": "ok",
        "schema_objects": schema_objects,
        "page_count": page_count,
        "user_version": user_version,
        "table_counts": table_counts,
    }


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """以 0600 原子写入 JSON，防止中断后留下半份绿色状态。"""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        logger.debug("无法调整备份目录权限: %s", path.parent.name)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.chmod(0o600)
    with temp_path.open("rb") as handle:
        os.fsync(handle.fileno())
    temp_path.replace(path)


def _remove_sqlite_sidecars(path: Path) -> None:
    """删除备份临时库的 WAL/SHM/journal；绝不用于源数据库。"""
    for suffix in ("-wal", "-shm", "-journal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def _safe_error(error: BaseException, *, roots: Sequence[Path]) -> str:
    """保留错误类型并隐藏本机绝对路径。"""
    text = str(error)
    for root in roots:
        text = text.replace(str(root), f"<{root.name or 'root'}>")
    return f"{type(error).__name__}: {text}"[:300]


def _default_data_dir() -> Path:
    """解析 ClawBot 数据目录；相对路径固定到 packages/clawbot。"""
    configured = str(os.getenv("OPENCLAW_DATA_DIR") or os.getenv("DATA_DIR") or "").strip()
    if not configured:
        return DATA_DIR
    candidate = Path(configured).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (PACKAGE_ROOT / candidate).resolve()


def _discover_sources(data_dir: Path, *, include_runtime_state: bool) -> tuple[list[DatabaseSource], list[str]]:
    """发现已存在数据库，并保留缺失核心库的 skipped 证据。"""
    found: dict[str, DatabaseSource] = {}
    if data_dir.exists():
        for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
            for path in sorted(data_dir.glob(pattern)):
                if path.is_file() and not path.is_symlink():
                    found[path.name] = DatabaseSource(path.name, path, "clawbot_data")

    if include_runtime_state:
        state_root = Path(str(os.getenv("OPENCLAW_STATE_DIR") or Path.home() / ".openclaw")).expanduser()
        runtime_candidates = (
            ("openclaw-state.sqlite", state_root / "state" / "openclaw.sqlite"),
            ("openclaw-memory.sqlite", state_root / "memory" / "main.sqlite"),
        )
        for logical_name, path in runtime_candidates:
            if path.is_file() and not path.is_symlink():
                found[logical_name] = DatabaseSource(logical_name, path, "openclaw_runtime")

        intel_path_text = str(os.getenv("INTEL_BRIEF_DB_PATH") or "").strip()
        if intel_path_text:
            intel_path = Path(intel_path_text).expanduser()
            if not intel_path.is_absolute():
                intel_path = (PACKAGE_ROOT.parent.parent / intel_path).resolve()
            if intel_path.is_file() and not intel_path.is_symlink():
                found.setdefault(
                    "intel-brief-configured.db",
                    DatabaseSource("intel-brief-configured.db", intel_path, "configured_runtime"),
                )

    missing = [name for name in DATABASES if name not in found]
    return sorted(found.values(), key=lambda source: source.logical_name), missing


@contextmanager
def _exclusive_lock(backup_dir: Path) -> Iterator[None]:
    """非阻塞获取备份锁；并发任务必须失败可见，不能重复写归档。"""
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        backup_dir.chmod(0o700)
    except OSError:
        logger.debug("无法调整备份目录权限: %s", backup_dir.name)
    lock_path = backup_dir / LOCK_FILE_NAME
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("backup already running") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _backup_one(source: DatabaseSource, destination: Path) -> dict[str, Any]:
    """在线备份单库到临时文件，验证通过后再原子替换正式归档。"""
    temp_path = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        source_uri = f"file:{source.path.resolve()}?mode=ro"
        with sqlite3.connect(source_uri, uri=True, timeout=30) as source_connection:
            source_connection.execute("PRAGMA busy_timeout = 30000")
            with sqlite3.connect(temp_path, timeout=30) as backup_connection:
                source_connection.backup(backup_connection, sleep=0.05)
                journal_mode = backup_connection.execute("PRAGMA journal_mode=DELETE").fetchone()
                if not journal_mode or str(journal_mode[0]).lower() != "delete":
                    raise sqlite3.DatabaseError("backup journal mode did not switch to DELETE")
                backup_connection.commit()
        metadata = _sqlite_metadata(temp_path)
        temp_path.chmod(0o600)
        with temp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        digest = _sha256(temp_path)
        size_bytes = int(temp_path.stat().st_size)
        temp_path.replace(destination)
        destination.chmod(0o600)
        _remove_sqlite_sidecars(destination)
        return {
            "source_name": source.logical_name,
            "scope": source.scope,
            "artifact": destination.name,
            "size_bytes": size_bytes,
            "sha256": digest,
            **metadata,
        }
    finally:
        _remove_sqlite_sidecars(temp_path)
        temp_path.unlink(missing_ok=True)


def _status_payload(
    *,
    status: str,
    attempted_at: str,
    ok_count: int,
    failed_count: int,
    skipped_count: int,
    manifest_name: str = "",
    error: str = "",
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成健康检查使用的最小状态，不保存数据库内容或绝对路径。"""
    previous = previous or {}
    last_success_at = attempted_at if status == "ok" else str(previous.get("last_success_at") or "")
    return {
        "version": MANIFEST_VERSION,
        "status": status,
        "last_attempt_at": attempted_at,
        "last_success_at": last_success_at,
        "ok_count": int(ok_count),
        "failed_count": int(failed_count),
        "skipped_count": int(skipped_count),
        "manifest": manifest_name,
        "error": error,
    }


def _read_json(path: Path) -> dict[str, Any]:
    """读取可选 JSON；损坏状态不影响新备份落盘。"""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def backup_all(
    *,
    data_dir: Path | str | None = None,
    backup_dir: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, str]:
    """备份全部已发现数据库，并保持旧调度器可消费的字符串结果。"""
    started = time.monotonic()
    resolved_data_dir = Path(data_dir).expanduser().resolve() if data_dir is not None else _default_data_dir()
    resolved_backup_dir = (
        Path(backup_dir).expanduser().resolve()
        if backup_dir is not None
        else (resolved_data_dir / "backups").resolve()
    )
    current = _utc_now(now)
    attempted_at = current.isoformat(timespec="seconds")
    date_stamp = current.strftime("%Y-%m-%d")
    status_path = resolved_backup_dir / STATUS_FILE_NAME
    previous_status = _read_json(status_path)
    results: dict[str, str] = {}

    try:
        with _exclusive_lock(resolved_backup_dir):
            sources, missing = _discover_sources(
                resolved_data_dir,
                include_runtime_state=data_dir is None,
            )
            for name in missing:
                results[name] = "skipped (not found)"

            if not sources:
                results["_preflight"] = "skipped (no databases found)"
                _atomic_json_write(
                    status_path,
                    _status_payload(
                        status="warning",
                        attempted_at=attempted_at,
                        ok_count=0,
                        failed_count=0,
                        skipped_count=len(missing),
                        error="no databases found",
                        previous=previous_status,
                    ),
                )
                return results

            source_bytes = sum(max(0, int(source.path.stat().st_size)) for source in sources)
            required_bytes = max(MIN_FREE_SPACE_BYTES, source_bytes * 2 + 8 * 1024 * 1024)
            free_bytes = _available_bytes(resolved_backup_dir)
            if free_bytes < required_bytes:
                message = f"insufficient disk space (required={required_bytes}, free={free_bytes})"
                results["_preflight"] = f"FAILED: {message}"
                _atomic_json_write(
                    status_path,
                    _status_payload(
                        status="failed",
                        attempted_at=attempted_at,
                        ok_count=0,
                        failed_count=1,
                        skipped_count=len(missing),
                        error=message,
                        previous=previous_status,
                    ),
                )
                return results

            manifest_entries: list[dict[str, Any]] = []
            failures: list[dict[str, str]] = []
            for source in sources:
                suffix = source.path.suffix.lower() if source.path.suffix else ".db"
                stem = Path(source.logical_name).stem
                destination = resolved_backup_dir / f"{stem}_{date_stamp}{suffix}"
                try:
                    entry = _backup_one(source, destination)
                    manifest_entries.append(entry)
                    size_mb = entry["size_bytes"] / (1024 * 1024)
                    results[source.logical_name] = f"OK ({size_mb:.1f} MB, sha256 verified)"
                    logger.info("[Backup] %s → %s (%.1f MB)", source.logical_name, destination.name, size_mb)
                except Exception as error:
                    safe_error = _safe_error(error, roots=(resolved_data_dir, resolved_backup_dir, source.path.parent))
                    results[source.logical_name] = f"FAILED: {safe_error}"
                    failures.append({"source_name": source.logical_name, "error": safe_error})
                    logger.error("[Backup] %s failed: %s", source.logical_name, safe_error)

            manifest_name = f"manifest_{date_stamp}.json"
            manifest_path = resolved_backup_dir / manifest_name
            manifest = {
                "version": MANIFEST_VERSION,
                "created_at": attempted_at,
                "ok": not failures,
                "duration_seconds": round(time.monotonic() - started, 3),
                "databases": manifest_entries,
                "failures": failures,
            }
            _atomic_json_write(manifest_path, manifest)
            results["_manifest"] = f"OK ({manifest_name})" if not failures else f"FAILED: {len(failures)} database(s)"

            cleanup_count = _cleanup_old_backups(
                backup_dir=resolved_backup_dir,
                now=current,
            )
            results["_cleanup"] = f"Removed {cleanup_count} old backups"
            _atomic_json_write(
                status_path,
                _status_payload(
                    status="ok" if not failures else "failed",
                    attempted_at=attempted_at,
                    ok_count=len(manifest_entries),
                    failed_count=len(failures),
                    skipped_count=len(missing),
                    manifest_name=manifest_name,
                    error=(failures[0]["error"] if failures else ""),
                    previous=previous_status,
                ),
            )
            return results
    except RuntimeError as error:
        if "backup already running" in str(error):
            return {"_lock": "FAILED: backup already running"}
        raise


def _cleanup_old_backups(
    daily_keep: int = 7,
    weekly_keep: int = 4,
    *,
    backup_dir: Path | str | None = None,
    now: datetime | None = None,
) -> int:
    """按日期清理归档；周日归档保留更久，状态和锁文件永不删除。"""
    resolved_backup_dir = Path(backup_dir).expanduser().resolve() if backup_dir else BACKUP_DIR
    if not resolved_backup_dir.exists():
        return 0
    current = _utc_now(now)
    cutoff_daily = current - timedelta(days=max(1, int(daily_keep)))
    cutoff_weekly = current - timedelta(weeks=max(1, int(weekly_keep)))
    removed = 0
    for path in sorted(resolved_backup_dir.iterdir()):
        if not path.is_file() or path.name in {STATUS_FILE_NAME, LOCK_FILE_NAME}:
            continue
        match = _DATE_RE.search(path.name)
        if not match:
            continue
        try:
            file_date = datetime.strptime(match.group(1), "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue
        cutoff = cutoff_weekly if file_date.weekday() == 6 else cutoff_daily
        if file_date < cutoff:
            try:
                path.unlink()
                removed += 1
            except OSError as error:
                logger.warning("[Backup] 清理旧归档失败 %s: %s", path.name, error)
    return removed


def _latest_manifest(backup_dir: Path) -> Path | None:
    """返回最新 manifest；不存在时由调用方明确报错。"""
    manifests = sorted(backup_dir.glob("manifest_*.json"), reverse=True)
    return manifests[0] if manifests else None


def restore_drill(
    *,
    backup_dir: Path | str | None = None,
    restore_dir: Path | str,
    manifest_path: Path | str | None = None,
) -> dict[str, Any]:
    """恢复到可丢弃目录并验证摘要、完整性和表行数；永不覆盖源数据库。"""
    started = time.monotonic()
    resolved_backup_dir = Path(backup_dir).expanduser().resolve() if backup_dir else BACKUP_DIR
    resolved_restore_dir = Path(restore_dir).expanduser().resolve()
    selected_manifest = (
        Path(manifest_path).expanduser().resolve()
        if manifest_path is not None
        else _latest_manifest(resolved_backup_dir)
    )
    if selected_manifest is None or not selected_manifest.is_file():
        return {"ok": False, "error": "backup manifest not found", "verified_databases": 0}
    if selected_manifest.parent != resolved_backup_dir:
        return {"ok": False, "error": "manifest must be inside backup directory", "verified_databases": 0}
    if resolved_restore_dir.exists() and any(resolved_restore_dir.iterdir()):
        return {"ok": False, "error": "restore directory must be empty", "verified_databases": 0}
    resolved_restore_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        resolved_restore_dir.chmod(0o700)
    except OSError:
        logger.debug("无法调整恢复演练目录权限: %s", resolved_restore_dir.name)

    manifest = _read_json(selected_manifest)
    entries = manifest.get("databases") if isinstance(manifest.get("databases"), list) else []
    errors: list[dict[str, str]] = []
    verified = 0
    total_bytes = 0
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            errors.append({"source_name": "unknown", "error": "invalid manifest entry"})
            continue
        source_name = str(raw_entry.get("source_name") or "")
        artifact_name = str(raw_entry.get("artifact") or "")
        if not source_name or Path(source_name).name != source_name:
            errors.append({"source_name": "unknown", "error": "invalid restore filename"})
            continue
        if not artifact_name or Path(artifact_name).name != artifact_name:
            errors.append({"source_name": source_name, "error": "invalid artifact path"})
            continue
        artifact = resolved_backup_dir / artifact_name
        destination = resolved_restore_dir / source_name
        temp_destination = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            if not artifact.is_file():
                raise FileNotFoundError("artifact missing")
            if _sha256(artifact) != str(raw_entry.get("sha256") or ""):
                raise ValueError("sha256 mismatch")
            shutil.copy2(artifact, temp_destination)
            temp_destination.chmod(0o600)
            metadata = _sqlite_metadata(temp_destination)
            if metadata["table_counts"] != raw_entry.get("table_counts", {}):
                raise ValueError("table counts mismatch")
            if metadata["schema_objects"] != int(raw_entry.get("schema_objects", -1)):
                raise ValueError("schema object count mismatch")
            if _sha256(temp_destination) != str(raw_entry.get("sha256") or ""):
                raise ValueError("restored sha256 mismatch")
            temp_destination.replace(destination)
            destination.chmod(0o600)
            verified += 1
            total_bytes += int(destination.stat().st_size)
        except Exception as error:
            errors.append(
                {
                    "source_name": source_name or "unknown",
                    "error": _safe_error(error, roots=(resolved_backup_dir, resolved_restore_dir)),
                }
            )
        finally:
            _remove_sqlite_sidecars(temp_destination)
            temp_destination.unlink(missing_ok=True)

    return {
        "ok": bool(entries) and not errors and verified == len(entries),
        "manifest": selected_manifest.name,
        "verified_databases": verified,
        "total_databases": len(entries),
        "total_bytes": total_bytes,
        "duration_seconds": round(time.monotonic() - started, 3),
        "errors": errors,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析手动备份或恢复演练参数。"""
    parser = argparse.ArgumentParser(description="备份 OpenClaw SQLite 数据并做可丢弃恢复演练")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--restore-drill", action="store_true")
    parser.add_argument("--restore-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口；恢复演练默认使用临时目录并在结束后清理。"""
    args = parse_args(argv)
    backup_dir = args.backup_dir or BACKUP_DIR
    if args.restore_drill:
        if args.restore_dir:
            result = restore_drill(
                backup_dir=backup_dir,
                restore_dir=args.restore_dir,
                manifest_path=args.manifest,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="openclaw-restore-drill-") as temp_dir:
                result = restore_drill(
                    backup_dir=backup_dir,
                    restore_dir=Path(temp_dir) / "restored",
                    manifest_path=args.manifest,
                )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        else:
            print(
                "恢复演练: "
                f"{'通过' if result.get('ok') else '失败'} "
                f"({result.get('verified_databases', 0)}/{result.get('total_databases', 0)})"
            )
        return 0 if result.get("ok") else 1

    results = backup_all(data_dir=args.data_dir, backup_dir=args.backup_dir)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, sort_keys=True))
    else:
        print("=== OpenClaw Database Backup ===")
        for database, status in results.items():
            print(f"  {database}: {status}")
    return 1 if any(str(status).startswith("FAILED") for status in results.values()) else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
