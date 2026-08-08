#!/usr/bin/env bash
# OpenEverything 一致性备份：私有 staging、SQLite 快照、双层 SHA-256 与原子就绪标记。
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_BACKUP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/openclaw/backups"
BACKUP_DIR="${OPENCLAW_BACKUP_DIR:-$DEFAULT_BACKUP_DIR}"
OPENCLAW_HOME_DIR="${OPENCLAW_HOME_DIR:-$HOME/.openclaw}"
OFFSITE_DIR="${OPENCLAW_BACKUP_OFFSITE_DIR:-}"
OFFSITE_GPG_RECIPIENT="${OPENCLAW_BACKUP_GPG_RECIPIENT:-}"
RETENTION_DAYS="${OPENCLAW_BACKUP_RETENTION_DAYS:-30}"
RETENTION_COUNT="${OPENCLAW_BACKUP_RETENTION_COUNT:-14}"
STAMP="${OPENCLAW_BACKUP_STAMP:-$(date +%Y%m%d-%H%M%S)}"
STRICT_INVENTORY="${OPENCLAW_BACKUP_STRICT_INVENTORY:-0}"
REQUIRE_OFFSITE=0

usage() {
  cat <<'EOF'
用法: scripts/local_backup.sh [--require-offsite] [--strict-inventory]

环境变量:
  OPENCLAW_BACKUP_DIR              本地备份目录
  OPENCLAW_BACKUP_OFFSITE_DIR      可选离机/同步盘目录；只发布 GPG 加密包
  OPENCLAW_BACKUP_GPG_RECIPIENT    离机加密公钥指纹或收件人
  OPENCLAW_BACKUP_RETENTION_DAYS   按天保留，默认 30
  OPENCLAW_BACKUP_RETENTION_COUNT  最多保留份数，默认 14
  OPENCLAW_HOME_DIR                OpenClaw 用户数据目录，默认 ~/.openclaw
EOF
}

fail() {
  printf '%s\n' "$1" >&2
  exit "${2:-1}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-offsite) REQUIRE_OFFSITE=1 ;;
    --strict-inventory) STRICT_INVENTORY=1 ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown_argument: $1" 2 ;;
  esac
  shift
done

[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || fail "invalid_retention_days"
[[ "$RETENTION_COUNT" =~ ^[1-9][0-9]*$ ]] || fail "invalid_retention_count"
[[ "$STAMP" =~ ^[0-9]{8}-[0-9]{6}$ ]] || fail "invalid_backup_stamp"
[[ "$STRICT_INVENTORY" == "0" || "$STRICT_INVENTORY" == "1" ]] || fail "invalid_strict_inventory"
if (( REQUIRE_OFFSITE == 1 )) && [[ -z "$OFFSITE_DIR" ]]; then
  fail "offsite_not_configured: 请设置 OPENCLAW_BACKUP_OFFSITE_DIR" 2
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
if [[ -n "$OFFSITE_DIR" ]]; then
  [[ -n "$OFFSITE_GPG_RECIPIENT" ]] \
    || fail "offsite_encryption_not_configured: 请设置 OPENCLAW_BACKUP_GPG_RECIPIENT" 2
  command -v gpg >/dev/null 2>&1 || fail "gpg_not_installed" 127
  gpg --batch --list-keys "$OFFSITE_GPG_RECIPIENT" >/dev/null 2>&1 \
    || fail "offsite_gpg_recipient_unavailable" 2
  [[ ! -L "$OFFSITE_DIR" ]] || fail "offsite_target_is_symlink"
  mkdir -p "$OFFSITE_DIR"
  chmod 700 "$OFFSITE_DIR"
  [[ "$(cd "$BACKUP_DIR" && pwd -P)" != "$(cd "$OFFSITE_DIR" && pwd -P)" ]] \
    || fail "offsite_target_must_differ_from_local"
else
  printf '%s\n' "warning: offsite_not_configured; 本次仅生成本地备份" >&2
fi

ARCHIVE_NAME="openeverything-$STAMP.tgz"
ARCHIVE="$BACKUP_DIR/$ARCHIVE_NAME"
for candidate in "$ARCHIVE" "$ARCHIVE.sha256" "$ARCHIVE.ready"; do
  [[ ! -e "$candidate" ]] || fail "backup_already_exists: $candidate"
done

WORK_DIR="$(mktemp -d "$BACKUP_DIR/.openeverything-$STAMP.partial.XXXXXX")"
BUNDLE_DIR="$WORK_DIR/bundle"
PAYLOAD_PROJECT="$BUNDLE_DIR/payload/project"
PAYLOAD_HOME="$BUNDLE_DIR/payload/home/.openclaw"
INVENTORY="$BUNDLE_DIR/INVENTORY.tsv"
WARNINGS=0

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

mkdir -p "$PAYLOAD_PROJECT" "$PAYLOAD_HOME"
printf 'scope\tpath\tstatus\ttype\n' > "$INVENTORY"
printf '2\n' > "$BUNDLE_DIR/FORMAT_VERSION"

should_skip() {
  case "$1" in
    .git|.git/*|*/.git/*|node_modules|node_modules/*|*/node_modules/*|.venv*|*/.venv*/*|target|target/*|*/target/*|dist|dist/*|*/dist/*|logs|logs/*|*/logs/*|output|output/*|*/output/*|*/__pycache__/*|*/browser_profiles/*|*/backups/*|*.db-wal|*.db-shm|*.sqlite-wal|*.sqlite-shm|*.sqlite3-wal|*.sqlite3-shm|*.lock|*.pid|*.codex-backup-*)
      return 0
      ;;
  esac
  return 1
}

copy_regular_file() {
  local source="$1"
  local destination="$2"
  local logical_path="$3"
  local escaped_destination
  case "$logical_path" in
    *$'\n'*|*$'\t'*) fail "unsupported_backup_path: $logical_path" ;;
  esac
  mkdir -p "$(dirname "$destination")"
  case "$source" in
    *.db|*.sqlite|*.sqlite3)
      escaped_destination="${destination//\'/\'\'}"
      sqlite3 "$source" ".timeout 5000" ".backup '$escaped_destination'" \
        || fail "sqlite_backup_failed: $logical_path"
      [[ "$(sqlite3 "$destination" 'PRAGMA quick_check;' 2>/dev/null)" == "ok" ]] \
        || fail "sqlite_quick_check_failed: $logical_path"
      ;;
    *)
      cp -p "$source" "$destination"
      ;;
  esac
}

copy_inventory_item() {
  local scope="$1"
  local item="$2"
  local source_root="$3"
  local destination_root="$4"
  local inventory_path="$item"
  local source="$source_root/$item"
  local destination="$destination_root/$item"
  local source_file relative logical_path

  if [[ "$scope" == "home" ]]; then
    inventory_path=".openclaw/$item"
  fi
  if [[ -L "$source" ]]; then
    printf '%s\t%s\tskipped\tsymlink\n' "$scope" "$inventory_path" >> "$INVENTORY"
    WARNINGS=$((WARNINGS + 1))
    return
  fi
  if [[ -f "$source" ]]; then
    printf '%s\t%s\tpresent\tfile\n' "$scope" "$inventory_path" >> "$INVENTORY"
    copy_regular_file "$source" "$destination" "$inventory_path"
    return
  fi
  if [[ -d "$source" ]]; then
    printf '%s\t%s\tpresent\tdirectory\n' "$scope" "$inventory_path" >> "$INVENTORY"
    while IFS= read -r -d '' source_file; do
      relative="${source_file#"$source"/}"
      logical_path="$item/$relative"
      if should_skip "$logical_path"; then
        continue
      fi
      copy_regular_file "$source_file" "$destination/$relative" "$logical_path"
    done < <(
      find "$source" \
        -type d \( -name .git -o -name node_modules -o -name '.venv*' -o -name target \
          -o -name dist -o -name logs -o -name output -o -name __pycache__ \
          -o -name browser_profiles -o -name backups -o -name '.playwright-*' \) -prune \
        -o -type f -print0
    )
    while IFS= read -r -d '' source_file; do
      relative="${source_file#"$source"/}"
      if ! should_skip "$item/$relative"; then
        printf '%s\t%s/%s\tskipped\tsymlink\n' "$scope" "$inventory_path" "$relative" >> "$INVENTORY"
        WARNINGS=$((WARNINGS + 1))
      fi
    done < <(
      find "$source" \
        -type d \( -name .git -o -name node_modules -o -name '.venv*' -o -name target \
          -o -name dist -o -name logs -o -name output -o -name __pycache__ \
          -o -name browser_profiles -o -name backups -o -name '.playwright-*' \) -prune \
        -o -type l -print0
    )
    return
  fi

  printf '%s\t%s\tmissing\tunknown\n' "$scope" "$inventory_path" >> "$INVENTORY"
  WARNINGS=$((WARNINGS + 1))
}

PROJECT_ITEMS=(
  ".env"
  ".openclaw"
  "AGENTS.md"
  "README.md"
  "Makefile"
  "docs"
  "scripts"
  "apps/openclaw"
  "apps/openclaw-manager-src/package.json"
  "apps/openclaw-manager-src/package-lock.json"
  "apps/openclaw-manager-src/.env"
  "apps/openclaw-manager-src/src"
  "apps/openclaw-manager-src/src-tauri"
  "packages/clawbot/multi_main.py"
  "packages/clawbot/pyproject.toml"
  "packages/clawbot/pytest.ini"
  "packages/clawbot/requirements.txt"
  "packages/clawbot/requirements-lock.txt"
  "packages/clawbot/requirements-lock-macos.txt"
  "packages/clawbot/src"
  "packages/clawbot/scripts"
  "packages/clawbot/tests"
  "packages/clawbot/config"
  "packages/clawbot/data"
  "packages/clawbot/kiro-gateway/.env"
  "data/newapi"
)

HOME_ITEMS=(
  "openclaw.json"
  "env"
  "gateway_token"
  "exec-approvals.json"
  "drafts.json"
  "one_time_alerts.json"
  "key_repair_alerts.json"
  "iflow_key_timestamp.json"
  "wechat_coupon_mitm_local_status.json"
  "cc-zhongzhuan-operator-state.json"
  "x_cookies.json"
  "xhs_cookies.json"
  "identity"
  "devices"
  "credentials"
  "agents"
  "plugins"
  "state"
  "memory"
  "cron"
  "tasks"
  "telegram"
  "delivery-queue"
  "openclaw-weixin"
  "workspace"
  "service-env"
)

for item in "${PROJECT_ITEMS[@]}"; do
  copy_inventory_item "project" "$item" "$ROOT_DIR" "$PAYLOAD_PROJECT"
done
for item in "${HOME_ITEMS[@]}"; do
  copy_inventory_item "home" "$item" "$OPENCLAW_HOME_DIR" "$PAYLOAD_HOME"
done

if [[ "$STRICT_INVENTORY" == "1" ]] && (( WARNINGS > 0 )); then
  fail "inventory_incomplete: $WARNINGS 项缺失或被跳过"
fi

python3 - "$BUNDLE_DIR" > "$BUNDLE_DIR/MANIFEST.sha256" <<'PY'
import hashlib
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
for path in sorted((root / "payload").rglob("*")):
    if not path.is_file():
        continue
    relative = path.relative_to(root).as_posix()
    if "\n" in relative or "\t" in relative:
        raise SystemExit(f"unsupported_manifest_path: {relative!r}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    print(f"{digest.hexdigest()}\t{relative}")
PY

COPYFILE_DISABLE=1 COPY_EXTENDED_ATTRIBUTES_DISABLE=1 tar -czf "$WORK_DIR/$ARCHIVE_NAME" -C "$BUNDLE_DIR" \
  FORMAT_VERSION INVENTORY.tsv MANIFEST.sha256 payload
ARCHIVE_DIGEST="$(shasum -a 256 "$WORK_DIR/$ARCHIVE_NAME" | awk '{print $1}')"
printf '%s  %s\n' "$ARCHIVE_DIGEST" "$ARCHIVE_NAME" > "$WORK_DIR/$ARCHIVE_NAME.sha256"
printf '%s\n' "$ARCHIVE_DIGEST" > "$WORK_DIR/$ARCHIVE_NAME.ready"
chmod 600 "$WORK_DIR/$ARCHIVE_NAME" "$WORK_DIR/$ARCHIVE_NAME.sha256" "$WORK_DIR/$ARCHIVE_NAME.ready"

# `.ready` 最后移动；恢复脚本只认三件套齐全的备份。
mv "$WORK_DIR/$ARCHIVE_NAME" "$ARCHIVE"
mv "$WORK_DIR/$ARCHIVE_NAME.sha256" "$ARCHIVE.sha256"
mv "$WORK_DIR/$ARCHIVE_NAME.ready" "$ARCHIVE.ready"

publish_offsite() {
  local target_dir="$1"
  local encrypted_name="$ARCHIVE_NAME.gpg"
  local partial_prefix="$target_dir/.$encrypted_name.partial.$$"
  local encrypted_digest
  for candidate in "$target_dir/$encrypted_name" "$target_dir/$encrypted_name.sha256" "$target_dir/$encrypted_name.ready"; do
    [[ ! -e "$candidate" ]] || fail "offsite_backup_already_exists: $candidate"
  done
  if ! {
    gpg --batch --yes --trust-model always --recipient "$OFFSITE_GPG_RECIPIENT" \
      --output "$partial_prefix" --encrypt "$ARCHIVE" \
      && encrypted_digest="$(shasum -a 256 "$partial_prefix" | awk '{print $1}')" \
      && printf '%s  %s\n' "$encrypted_digest" "$encrypted_name" > "$partial_prefix.sha256" \
      && printf '%s\n' "$encrypted_digest" > "$partial_prefix.ready" \
      && chmod 600 "$partial_prefix" "$partial_prefix.sha256" "$partial_prefix.ready" \
      && mv "$partial_prefix" "$target_dir/$encrypted_name" \
      && mv "$partial_prefix.sha256" "$target_dir/$encrypted_name.sha256" \
      && mv "$partial_prefix.ready" "$target_dir/$encrypted_name.ready"
  }; then
    rm -f \
      "$partial_prefix" "$partial_prefix.sha256" "$partial_prefix.ready" \
      "$target_dir/$encrypted_name" "$target_dir/$encrypted_name.sha256" "$target_dir/$encrypted_name.ready"
    fail "offsite_publish_failed"
  fi
}

apply_retention() {
  local directory="$1"
  local pattern="$2"
  local archive index
  local -a archives=()

  while IFS= read -r archive; do
    rm -f "$archive" "$archive.sha256" "$archive.ready"
  done < <(find "$directory" -maxdepth 1 -type f -name "$pattern" -mtime "+$RETENTION_DAYS" -print)

  while IFS= read -r archive; do
    archives+=("$archive")
  done < <(find "$directory" -maxdepth 1 -type f -name "$pattern" -print | LC_ALL=C sort -r)
  index=0
  for archive in "${archives[@]}"; do
    index=$((index + 1))
    if (( index > RETENTION_COUNT )); then
      rm -f "$archive" "$archive.sha256" "$archive.ready"
    fi
  done
}

OFFSITE_STATUS="not_configured"
if [[ -n "$OFFSITE_DIR" ]]; then
  publish_offsite "$OFFSITE_DIR"
  OFFSITE_STATUS="encrypted"
fi
apply_retention "$BACKUP_DIR" 'openeverything-*.tgz'
if [[ -n "$OFFSITE_DIR" ]]; then
  apply_retention "$OFFSITE_DIR" 'openeverything-*.tgz.gpg'
fi

python3 - "$ARCHIVE" "$RETENTION_DAYS" "$RETENTION_COUNT" "$WARNINGS" "$OFFSITE_STATUS" <<'PY'
import json
import sys

print(json.dumps({
    "ok": True,
    "archive": sys.argv[1],
    "retention_days": int(sys.argv[2]),
    "retention_count": int(sys.argv[3]),
    "inventory_warnings": int(sys.argv[4]),
    "offsite": sys.argv[5],
}, ensure_ascii=False))
PY
