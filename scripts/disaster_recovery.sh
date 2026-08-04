#!/usr/bin/env bash
# OpenEverything 灾备恢复：先验双层 checksum 与归档路径，默认只预览。
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_BACKUP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/openclaw/backups"
BACKUP_DIR="${OPENCLAW_BACKUP_DIR:-$DEFAULT_BACKUP_DIR}"
OFFSITE_DIR="${OPENCLAW_BACKUP_OFFSITE_DIR:-}"
RESTORE_ROOT="${OPENCLAW_RESTORE_ROOT:-$ROOT_DIR}"
RESTORE_HOME="${OPENCLAW_RESTORE_HOME:-$HOME}"
FROM_OFFSITE=0
MODE="dry-run"
MODE_SELECTED=0
ARCHIVE=""

usage() {
  cat <<'EOF'
用法: scripts/disaster_recovery.sh [--archive FILE] [--dry-run|--drill|--confirm] [--from-r2]

  默认模式为 --dry-run；只有 --confirm 会写入项目目录和 ~/.openclaw。
  --drill 会完整解包、校验 manifest 和 SQLite，但不会写入恢复目标。
  --from-r2 是兼容名称，从 OPENCLAW_BACKUP_OFFSITE_DIR 选择最近的就绪备份。
EOF
}

fail() {
  printf '%s\n' "$1" >&2
  exit "${2:-1}"
}

select_mode() {
  local requested="$1"
  if (( MODE_SELECTED == 1 )) && [[ "$MODE" != "$requested" ]]; then
    fail "conflicting_restore_modes" 2
  fi
  MODE="$requested"
  MODE_SELECTED=1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-r2|--from-offsite) FROM_OFFSITE=1 ;;
    --dry-run) select_mode "dry-run" ;;
    --drill) select_mode "drill" ;;
    --confirm) select_mode "confirm" ;;
    --archive)
      [[ $# -ge 2 && -n "$2" ]] || fail "missing_archive_argument" 2
      ARCHIVE="$2"
      shift
      ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown_argument: $1" 2 ;;
  esac
  shift
done

SEARCH_DIR="$BACKUP_DIR"
if (( FROM_OFFSITE == 1 )); then
  [[ -n "$OFFSITE_DIR" ]] \
    || fail "offsite_not_configured: 请设置 OPENCLAW_BACKUP_OFFSITE_DIR 或先手工下载备份" 2
  [[ -d "$OFFSITE_DIR" && ! -L "$OFFSITE_DIR" ]] || fail "offsite_target_unavailable"
  SEARCH_DIR="$OFFSITE_DIR"
fi

if [[ -z "$ARCHIVE" ]]; then
  ARCHIVE_PATTERN='openeverything-*.tgz'
  if (( FROM_OFFSITE == 1 )); then
    ARCHIVE_PATTERN='openeverything-*.tgz.gpg'
  fi
  while IFS= read -r candidate; do
    if [[ -f "$candidate.sha256" && -f "$candidate.ready" ]]; then
      ARCHIVE="$candidate"
      break
    fi
  done < <(find "$SEARCH_DIR" -maxdepth 1 -type f -name "$ARCHIVE_PATTERN" -print 2>/dev/null | LC_ALL=C sort -r)
fi

[[ -n "$ARCHIVE" && -f "$ARCHIVE" && ! -L "$ARCHIVE" ]] || fail "backup_archive_not_found"
if (( FROM_OFFSITE == 1 )) && [[ "$ARCHIVE" != *.tgz.gpg ]]; then
  fail "offsite_backup_not_encrypted"
fi
CHECKSUM_FILE="$ARCHIVE.sha256"
READY_FILE="$ARCHIVE.ready"
[[ -f "$CHECKSUM_FILE" && ! -L "$CHECKSUM_FILE" ]] || fail "checksum_manifest_not_found"
[[ -f "$READY_FILE" && ! -L "$READY_FILE" ]] || fail "backup_not_ready"

# 外层 checksum 必须在列出或解包归档前完成，防止损坏包进入后续流程。
read -r EXPECTED_DIGEST RECORDED_NAME EXTRA_FIELDS < "$CHECKSUM_FILE" || fail "checksum_manifest_invalid"
[[ "$EXPECTED_DIGEST" =~ ^[0-9a-fA-F]{64}$ ]] || fail "checksum_manifest_invalid"
[[ -z "${EXTRA_FIELDS:-}" ]] || fail "checksum_manifest_invalid"
[[ "$RECORDED_NAME" == "$(basename "$ARCHIVE")" ]] || fail "checksum_archive_name_mismatch"
ACTUAL_DIGEST="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
EXPECTED_DIGEST="$(printf '%s' "$EXPECTED_DIGEST" | tr '[:upper:]' '[:lower:]')"
[[ "$EXPECTED_DIGEST" == "$ACTUAL_DIGEST" ]] || fail "checksum_mismatch"
read -r READY_DIGEST READY_EXTRA < "$READY_FILE" || fail "ready_marker_invalid"
READY_DIGEST="$(printf '%s' "$READY_DIGEST" | tr '[:upper:]' '[:lower:]')"
[[ -z "${READY_EXTRA:-}" && "$READY_DIGEST" == "$ACTUAL_DIGEST" ]] || fail "ready_marker_invalid"

STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/openclaw-restore.XXXXXX")"
cleanup() {
  rm -rf "$STAGE_DIR"
}
trap cleanup EXIT INT TERM

VERIFIED_ARCHIVE="$ARCHIVE"
if [[ "$ARCHIVE" == *.gpg ]]; then
  command -v gpg >/dev/null 2>&1 || fail "gpg_not_installed" 127
  VERIFIED_ARCHIVE="$STAGE_DIR/verified-archive.tgz"
  gpg --batch --yes --output "$VERIFIED_ARCHIVE" --decrypt "$ARCHIVE" \
    || fail "offsite_decryption_failed"
  chmod 600 "$VERIFIED_ARCHIVE"
fi

python3 - "$VERIFIED_ARCHIVE" "$STAGE_DIR" <<'PY'
import hashlib
import pathlib
import re
import shutil
import sqlite3
import sys
import tarfile


def fail(code: str, detail: str = "") -> None:
    suffix = f": {detail}" if detail else ""
    print(f"{code}{suffix}", file=sys.stderr)
    raise SystemExit(1)


archive_path = pathlib.Path(sys.argv[1])
stage = pathlib.Path(sys.argv[2]).resolve()
allowed_roots = {"FORMAT_VERSION", "INVENTORY.tsv", "MANIFEST.sha256", "payload"}
members_by_path: dict[str, tarfile.TarInfo] = {}

try:
    archive = tarfile.open(archive_path, "r:gz")
except (OSError, tarfile.TarError) as error:
    fail("archive_open_failed", str(error))

with archive:
    for member in archive.getmembers():
        raw_name = member.name.rstrip("/")
        path = pathlib.PurePosixPath(raw_name)
        normalized = path.as_posix()
        if not raw_name or path.is_absolute() or ".." in path.parts or normalized != raw_name:
            fail("unsafe_archive_path", member.name)
        if path.parts[0] not in allowed_roots:
            fail("unexpected_archive_root", member.name)
        if normalized in members_by_path:
            fail("duplicate_archive_path", normalized)
        if not (member.isfile() or member.isdir()):
            fail("unsafe_archive_member_type", member.name)
        members_by_path[normalized] = member

    for required in ("FORMAT_VERSION", "INVENTORY.tsv", "MANIFEST.sha256", "payload"):
        if required not in members_by_path:
            fail("archive_metadata_missing", required)

    for normalized, member in members_by_path.items():
        target = stage.joinpath(*pathlib.PurePosixPath(normalized).parts)
        try:
            target.relative_to(stage)
        except ValueError:
            fail("unsafe_archive_path", member.name)
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        source = archive.extractfile(member)
        if source is None:
            fail("archive_member_unreadable", member.name)
        try:
            with source, target.open("xb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
            target.chmod(member.mode & 0o777)
        except OSError as error:
            fail("archive_extract_failed", f"{member.name}: {error}")

version = (stage / "FORMAT_VERSION").read_text(encoding="utf-8").strip()
if version != "2":
    fail("unsupported_backup_format", version)

manifest_path = stage / "MANIFEST.sha256"
expected_files: dict[str, str] = {}
for line_number, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), 1):
    try:
        digest, relative = line.split("\t", 1)
    except ValueError:
        fail("internal_manifest_invalid", f"line {line_number}")
    path = pathlib.PurePosixPath(relative)
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or path.is_absolute() or ".." in path.parts:
        fail("internal_manifest_invalid", relative)
    if not path.parts or path.parts[0] != "payload" or path.as_posix() != relative:
        fail("internal_manifest_invalid", relative)
    if relative in expected_files:
        fail("internal_manifest_duplicate", relative)
    expected_files[relative] = digest

actual_files = {
    path.relative_to(stage).as_posix()
    for path in (stage / "payload").rglob("*")
    if path.is_file()
}
if actual_files != set(expected_files):
    missing = sorted(set(expected_files) - actual_files)
    extra = sorted(actual_files - set(expected_files))
    fail(
        "internal_manifest_file_set_mismatch",
        f"missing={missing[:3]!r}, extra={extra[:3]!r}",
    )

for relative, expected in expected_files.items():
    digest = hashlib.sha256()
    with (stage / relative).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        fail("internal_checksum_mismatch", relative)

for path in sorted(stage.joinpath("payload").rglob("*")):
    if not path.is_file() or path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        continue
    try:
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
        result = connection.execute("PRAGMA quick_check").fetchone()
        connection.close()
    except sqlite3.Error as error:
        fail("sqlite_quick_check_failed", f"{path.relative_to(stage)}: {error}")
    if result != ("ok",):
        fail("sqlite_quick_check_failed", str(path.relative_to(stage)))
PY

case "$MODE" in
  dry-run)
    printf 'restore dry-run: 已验证 %s，将恢复到 %s 和 %s/.openclaw\n' "$ARCHIVE" "$RESTORE_ROOT" "$RESTORE_HOME"
    sed -n '1,80p' "$STAGE_DIR/INVENTORY.tsv"
    printf "真正恢复请运行：scripts/disaster_recovery.sh --archive '%s' --confirm\n" "$ARCHIVE"
    ;;
  drill)
    printf 'restore drill passed: checksum、路径、manifest 与 SQLite 均有效；未写入恢复目标\n'
    ;;
  confirm)
    [[ ! -L "$RESTORE_ROOT" && ! -L "$RESTORE_HOME" ]] || fail "restore_target_is_symlink"
    # 只检查本次将写入的目标链，避免已有符号链接把文件引到恢复根目录之外。
    python3 - "$STAGE_DIR" "$RESTORE_ROOT" "$RESTORE_HOME" <<'PY'
import pathlib
import sys

stage = pathlib.Path(sys.argv[1])


def check_target_paths(source_root: pathlib.Path, target_root: pathlib.Path) -> None:
    for source in source_root.rglob("*"):
        relative = source.relative_to(source_root)
        current = target_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                print(f"restore_target_symlink: {current}", file=sys.stderr)
                raise SystemExit(1)


check_target_paths(stage / "payload" / "project", pathlib.Path(sys.argv[2]))
check_target_paths(stage / "payload" / "home", pathlib.Path(sys.argv[3]))
PY
    mkdir -p "$RESTORE_ROOT" "$RESTORE_HOME/.openclaw"
    [[ ! -L "$RESTORE_HOME/.openclaw" ]] || fail "restore_target_is_symlink"
    rsync -a "$STAGE_DIR/payload/project/" "$RESTORE_ROOT/"
    rsync -a "$STAGE_DIR/payload/home/.openclaw/" "$RESTORE_HOME/.openclaw/"
    printf 'restore complete: %s\n' "$ARCHIVE"
    ;;
  *) fail "invalid_restore_mode" ;;
esac
