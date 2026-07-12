#!/usr/bin/env bash
# OpenEverything 源码灾备恢复：默认只预演；覆盖真实项目目录必须显式 --confirm。
set -euo pipefail

umask 077
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${OPENCLAW_BACKUP_PYTHON:-$(command -v python3 || true)}"

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  printf '%s\n' '{"ok":false,"error":"python3_not_found"}'
  exit 127
fi

export OPENCLAW_SOURCE_ROOT="$ROOT_DIR"
"$PYTHON_BIN" - "$@" <<'PY'
from __future__ import print_function

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath


MIN_FREE_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_RESTORE_BYTES = 5 * 1024 * 1024 * 1024


def emit(payload):
    """输出单行 JSON，供人工和自动恢复演练共同读取。"""
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def fail(code, error):
    """返回不包含归档内容或本机凭据的安全失败结果。"""
    emit({"ok": False, "error": error})
    return code


def sha256_file(path):
    """流式计算归档校验和，避免一次性把大文件读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def read_expected_digest(checksum_file):
    """只接受标准的 64 位 SHA-256 首字段。"""
    fields = checksum_file.read_text(encoding="utf-8").strip().split()
    if not fields or re.fullmatch(r"[0-9a-fA-F]{64}", fields[0]) is None:
        raise ValueError("invalid_checksum_file")
    return fields[0].lower()


def validate_members(bundle, max_restore_bytes):
    """拒绝绝对路径、父目录跳转、链接、设备文件和解压炸弹。"""
    members = bundle.getmembers()
    seen = set()
    total_bytes = 0
    file_count = 0
    for member in members:
        name = member.name
        if not name or name.startswith("/") or "\\" in name or re.match(r"^[A-Za-z]:", name):
            raise ValueError("unsafe_archive_path")
        raw_parts = name.split("/")
        if any(part in {"", ".", ".."} for part in raw_parts):
            raise ValueError("unsafe_archive_path")
        normalized = PurePosixPath(name)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError("unsafe_archive_path")
        normalized_name = normalized.as_posix()
        if normalized_name in seen:
            raise ValueError("duplicate_archive_path")
        seen.add(normalized_name)
        if member.issym() or member.islnk() or member.isdev() or member.isfifo():
            raise ValueError("unsafe_archive_member_type")
        if not (member.isfile() or member.isdir()):
            raise ValueError("unsupported_archive_member_type")
        if member.isfile():
            total_bytes += member.size
            file_count += 1
            if total_bytes > max_restore_bytes:
                raise ValueError("archive_exceeds_restore_limit")
    if file_count == 0:
        raise ValueError("archive_contains_no_files")
    return members, file_count, total_bytes


def extract_to_staging(bundle, members, staging):
    """只把已经完整验证过的普通文件解压到新建临时目录。"""
    for member in members:
        destination = staging.joinpath(*PurePosixPath(member.name).parts)
        if member.isdir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = bundle.extractfile(member)
        if source is None:
            raise OSError("archive_member_unreadable")
        with source, destination.open("xb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
        os.chmod(str(destination), member.mode & 0o777)


def ensure_no_symlink_parent(target_root, relative):
    """避免目标目录中的既有符号链接把恢复写入项目外部。"""
    current = target_root
    for part in relative.parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise OSError("target_contains_symlink_parent")


def copy_staging(staging, target_root, members):
    """逐文件原子覆盖，不执行 --delete，也不清理目标中的额外数据。"""
    restored = 0
    for member in members:
        relative = Path(*PurePosixPath(member.name).parts)
        source = staging / relative
        destination = target_root / relative
        if member.isdir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        ensure_no_symlink_parent(target_root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(".{}.restore-{}".format(destination.name, os.getpid()))
        try:
            shutil.copy2(str(source), str(temporary), follow_symlinks=False)
            os.replace(str(temporary), str(destination))
        finally:
            if temporary.exists():
                temporary.unlink()
        restored += 1
    return restored


def resolve_latest_archive(backup_dir):
    """按修改时间选择最近一次源码快照。"""
    archives = [item for item in backup_dir.glob("openeverything-*.tgz") if item.is_file()]
    if not archives:
        return None
    return max(archives, key=lambda item: item.stat().st_mtime)


def build_parser():
    """定义显式恢复参数；未确认时一律保持 dry-run。"""
    parser = argparse.ArgumentParser(description="OpenEverything source restore")
    parser.add_argument("--from-r2", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--archive")
    parser.add_argument("--target-dir")
    return parser


def main(argv):
    """先验 checksum 和 tar 安全，再执行可丢弃或人工确认恢复。"""
    started = time.monotonic()
    args = build_parser().parse_args(argv)
    root = Path(os.environ["OPENCLAW_SOURCE_ROOT"]).resolve()
    backup_dir = Path(os.environ.get("OPENCLAW_BACKUP_DIR", "~/Desktop/OpenEverything-backups")).expanduser().resolve()
    if args.from_r2:
        print(
            "R2 restore requested：请先用受信工具把源码快照及同名 .sha256 下载到本机备份目录；本脚本不会读取密钥。",
            file=sys.stderr,
        )

    archive = Path(args.archive).expanduser().resolve() if args.archive else resolve_latest_archive(backup_dir)
    if archive is None or not archive.is_file():
        return fail(1, "backup_archive_not_found")
    checksum_file = Path(str(archive) + ".sha256")
    if not checksum_file.is_file():
        return fail(1, "backup_checksum_not_found")
    try:
        expected_digest = read_expected_digest(checksum_file)
    except (OSError, UnicodeError, ValueError):
        return fail(1, "backup_checksum_invalid")
    if sha256_file(archive) != expected_digest:
        return fail(1, "backup_checksum_mismatch")

    try:
        max_restore_bytes = int(os.environ.get("OPENCLAW_RESTORE_MAX_BYTES", str(DEFAULT_MAX_RESTORE_BYTES)))
    except ValueError:
        return fail(2, "invalid_restore_size_limit")
    if max_restore_bytes < 1:
        return fail(2, "invalid_restore_size_limit")

    try:
        with tarfile.open(str(archive), mode="r:gz") as bundle:
            members, file_count, total_bytes = validate_members(bundle, max_restore_bytes)
    except (OSError, tarfile.TarError):
        return fail(1, "backup_archive_invalid")
    except ValueError as error:
        return fail(1, str(error))

    target_root = Path(args.target_dir).expanduser().resolve() if args.target_dir else root
    target_is_project_root = target_root == root
    dry_run = args.dry_run or not args.confirm
    if dry_run:
        for member in members[:40]:
            print(member.name, file=sys.stderr)
        emit(
            {
                "ok": True,
                "dry_run": True,
                "checksum_verified": True,
                "target_is_project_root": target_is_project_root,
                "file_count": file_count,
                "restore_bytes": total_bytes,
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        )
        return 0

    if target_root == Path(target_root.anchor):
        return fail(2, "unsafe_restore_target")
    if target_root.exists() and target_root.is_symlink():
        return fail(2, "restore_target_is_symlink")
    if not target_is_project_root and target_root.exists() and any(target_root.iterdir()):
        return fail(2, "disposable_restore_target_not_empty")

    required_bytes = max(MIN_FREE_BYTES, total_bytes * 2)
    disk_probe = target_root if target_root.exists() else target_root.parent
    while not disk_probe.exists() and disk_probe != disk_probe.parent:
        disk_probe = disk_probe.parent
    if shutil.disk_usage(str(disk_probe)).free < required_bytes:
        return fail(1, "insufficient_restore_space")

    staging = Path(tempfile.mkdtemp(prefix="openclaw-source-restore-"))
    try:
        with tarfile.open(str(archive), mode="r:gz") as bundle:
            verified_members, _, _ = validate_members(bundle, max_restore_bytes)
            extract_to_staging(bundle, verified_members, staging)
        target_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        restored_files = copy_staging(staging, target_root, verified_members)
    except (OSError, tarfile.TarError):
        return fail(1, "source_restore_failed")
    except ValueError as error:
        return fail(1, str(error))
    finally:
        shutil.rmtree(str(staging), ignore_errors=True)

    emit(
        {
            "ok": True,
            "dry_run": False,
            "checksum_verified": True,
            "target_is_project_root": target_is_project_root,
            "file_count": restored_files,
            "restore_bytes": total_bytes,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    )
    return 0


sys.exit(main(sys.argv[1:]))
PY
