#!/usr/bin/env bash
# OpenEverything 源码快照：只归档 Git 管理和待纳入的普通文件，不包含密钥或运行数据。
set -euo pipefail

umask 077
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_BACKUP_DIR="$HOME/Desktop/OpenEverything-backups"
ICLOUD_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/OpenEverythingBackups"
if [[ -n "${OPENCLAW_BACKUP_DIR:-}" ]]; then
  BACKUP_DIR="$OPENCLAW_BACKUP_DIR"
elif [[ -d "$ICLOUD_DIR" ]]; then
  BACKUP_DIR="$ICLOUD_DIR"
else
  BACKUP_DIR="$DEFAULT_BACKUP_DIR"
fi
RETENTION_DAYS="${OPENCLAW_BACKUP_RETENTION_DAYS:-30}"
PYTHON_BIN="${OPENCLAW_BACKUP_PYTHON:-$(command -v python3 || true)}"

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  printf '%s\n' '{"ok":false,"error":"python3_not_found"}'
  exit 127
fi

export OPENCLAW_SOURCE_ROOT="$ROOT_DIR"
export OPENCLAW_BACKUP_DIR="$BACKUP_DIR"
export OPENCLAW_BACKUP_RETENTION_DAYS="$RETENTION_DAYS"

"$PYTHON_BIN" - <<'PY'
from __future__ import print_function

import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import time
from pathlib import Path


MIN_FREE_BYTES = 64 * 1024 * 1024
RUNTIME_PARTS = {
    ".git",
    ".playwright-cli",
    ".playwright-mcp",
    ".venv",
    "backups",
    "browser_profiles",
    "dist",
    "logs",
    "node_modules",
    "output",
    "target",
}
SENSITIVE_SUFFIXES = {".db", ".jks", ".key", ".p12", ".pem", ".pfx", ".sqlite", ".sqlite3"}


def emit(payload):
    """输出单行 JSON，便于健康检查和自动任务读取。"""
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def write_atomic(path, content):
    """以 0600 权限原子写入小型状态文件。"""
    temporary = path.with_name(".{}.tmp-{}".format(path.name, os.getpid()))
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(str(temporary), 0o600)
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def is_within(path, parent):
    """判断路径是否位于指定目录内，兼容 Python 3.9。"""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def is_env_file(name):
    """仅允许公开模板 .env.example，其他环境文件一律排除。"""
    if name.endswith(".env.example"):
        return False
    return name == ".env" or name.startswith(".env.") or name.endswith(".env") or ".env." in name


def should_exclude(relative, source, backup_dir):
    """排除依赖、运行产物、凭据、数据库、符号链接和 submodule。"""
    parts = relative.parts
    if relative.is_absolute() or ".." in parts:
        return True
    if source.is_symlink() or not source.exists():
        return True
    mode = source.lstat().st_mode
    if not stat.S_ISREG(mode):
        return True
    if is_within(source.resolve(), backup_dir.resolve()):
        return True
    if any(part in RUNTIME_PARTS or part.startswith(".venv") for part in parts):
        return True
    if ".openclaw" in parts or "data/backups" in relative.as_posix():
        return True
    name = relative.name
    if is_env_file(name):
        return True
    if name in {"credentials.json", "keypool.json"}:
        return True
    if source.suffix.lower() in SENSITIVE_SUFFIXES or name.endswith((".db-wal", ".db-shm")):
        return True
    if name.endswith(".log"):
        return True
    return False


def normalize_tar_info(info):
    """去掉本机用户名等无关元数据，同时保留源码权限和时间。"""
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def collect_files(root, backup_dir):
    """只收集 Git 管理或待纳入且未忽略的普通文件。"""
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    selected = []
    for raw_path in completed.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative = Path(os.fsdecode(raw_path))
        source = root / relative
        if should_exclude(relative, source, backup_dir):
            continue
        selected.append(relative)
    return sorted(set(selected), key=lambda item: item.as_posix())


def remove_expired(backup_dir, retention_days):
    """归档过期时同步删除对应校验和与单次状态文件。"""
    cutoff = time.time() - retention_days * 86400
    removed = 0
    for archive in backup_dir.glob("openeverything-*.tgz"):
        try:
            expired = archive.stat().st_mtime < cutoff
        except FileNotFoundError:
            expired = False
        if not expired:
            continue
        for candidate in (
            archive,
            Path(str(archive) + ".sha256"),
            Path(str(archive) + ".json"),
        ):
            try:
                candidate.unlink()
            except FileNotFoundError:
                continue
        removed += 1
    return removed


def main():
    """创建可校验源码快照并写入脱敏状态。"""
    started = time.monotonic()
    root = Path(os.environ["OPENCLAW_SOURCE_ROOT"]).resolve()
    backup_dir = Path(os.environ["OPENCLAW_BACKUP_DIR"]).expanduser().resolve()
    try:
        retention_days = int(os.environ["OPENCLAW_BACKUP_RETENTION_DAYS"])
    except ValueError:
        emit({"ok": False, "error": "invalid_retention_days"})
        return 2
    if retention_days < 1:
        emit({"ok": False, "error": "invalid_retention_days"})
        return 2
    if not (root / ".git").exists():
        emit({"ok": False, "error": "source_root_is_not_git_worktree"})
        return 2

    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(str(backup_dir), 0o700)
    lock_path = backup_dir / ".source-backup.lock"
    lock_handle = lock_path.open("a+")
    os.chmod(str(lock_path), 0o600)
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        emit({"ok": False, "error": "source_backup_already_running"})
        return 73

    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    archive = backup_dir / "openeverything-{}.tgz".format(stamp)
    checksum_file = Path(str(archive) + ".sha256")
    status_file = Path(str(archive) + ".json")
    latest_status = backup_dir / "latest-source-backup.json"
    temporary_archive = archive.with_name(".{}.tmp-{}".format(archive.name, os.getpid()))

    try:
        selected = collect_files(root, backup_dir)
        if not selected:
            emit({"ok": False, "error": "no_source_files_selected"})
            return 1
        source_bytes = sum((root / relative).stat().st_size for relative in selected)
        required_bytes = max(MIN_FREE_BYTES, source_bytes * 2)
        free_bytes = shutil.disk_usage(str(backup_dir)).free
        if free_bytes < required_bytes:
            emit(
                {
                    "ok": False,
                    "error": "insufficient_backup_space",
                    "required_bytes": required_bytes,
                    "free_bytes": free_bytes,
                }
            )
            return 1

        with tarfile.open(
            str(temporary_archive),
            mode="w:gz",
            format=tarfile.PAX_FORMAT,
            dereference=False,
        ) as bundle:
            for relative in selected:
                bundle.add(
                    str(root / relative),
                    arcname=relative.as_posix(),
                    recursive=False,
                    filter=normalize_tar_info,
                )
        os.chmod(str(temporary_archive), 0o600)
        os.replace(str(temporary_archive), str(archive))

        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        write_atomic(checksum_file, "{}  {}\n".format(digest, archive.name))
        removed_archives = remove_expired(backup_dir, retention_days)
        payload = {
            "ok": True,
            "kind": "source_snapshot",
            "archive": str(archive),
            "checksum_file": str(checksum_file),
            "file_count": len(selected),
            "source_bytes": source_bytes,
            "archive_bytes": archive.stat().st_size,
            "retention_days": retention_days,
            "removed_archives": removed_archives,
            "duration_seconds": round(time.monotonic() - started, 3),
            "contains_runtime_data": False,
        }
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        write_atomic(status_file, serialized)
        write_atomic(latest_status, serialized)
        emit(payload)
        return 0
    except (OSError, subprocess.SubprocessError, tarfile.TarError):
        emit({"ok": False, "error": "source_backup_failed"})
        return 1
    finally:
        if temporary_archive.exists():
            temporary_archive.unlink()
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


sys.exit(main())
PY
