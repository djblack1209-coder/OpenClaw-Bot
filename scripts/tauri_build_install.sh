#!/usr/bin/env bash
# OpenClaw 桌面端事务式构建安装：候选包验证后才交换旧副本，失败时恢复上一个可用版本。
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/apps/openclaw-manager-src"
BUNDLE_DIR="$FRONTEND_DIR/src-tauri/target/release/bundle/macos"
BUNDLE_APP="$BUNDLE_DIR/OpenClaw.app"
INSTALL_DIR="${OPENCLAW_INSTALL_DIR:-/Applications}"
INSTALL_APP="$INSTALL_DIR/OpenClaw.app"
INSTALL_TMP="$INSTALL_DIR/.OpenClaw.app.install-$$"
INSTALL_PREVIOUS="$INSTALL_DIR/.OpenClaw.app.previous-$$"
BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/openclaw-app-backup.XXXXXX")"
PERSISTENT_ROLLBACK_DIR="${OPENCLAW_ROLLBACK_DIR:-$HOME/Library/Application Support/OpenClaw/release-backups}"
PERSISTENT_ROLLBACK_APP="$PERSISTENT_ROLLBACK_DIR/OpenClaw.app"
PERSISTENT_ROLLBACK_TMP="$PERSISTENT_ROLLBACK_DIR/.OpenClaw.previous-$$"
PERSISTENT_ROLLBACK_OLD="$PERSISTENT_ROLLBACK_DIR/.OpenClaw.rollback-old-$$"
ROLLBACK_MANIFEST="$PERSISTENT_ROLLBACK_DIR/manifest.plist"
ROLLBACK_MANIFEST_TMP="$PERSISTENT_ROLLBACK_DIR/.manifest-$$.plist"
PERSISTENT_SWAP_STARTED=0
BACKUP_READY=0
INSTALL_SWAP_STARTED=0
LEGACY_CLEANUP_STARTED=0
OLD_APP_NAMES=("OpenEverything.app" "OpenClaw.app" "OpenClaw-Gateway.app")

cdhash_for() {
  codesign -dvvv "$1" 2>&1 | awk -F= '/^CDHash=/{print $2; exit}'
}

source_patch_sha256() {
  {
    git -C "$ROOT_DIR" diff --binary HEAD --
    git -C "$ROOT_DIR" ls-files --others --exclude-standard | LC_ALL=C sort | while IFS= read -r path; do
      [[ -f "$ROOT_DIR/$path" ]] || continue
      printf 'untracked:%s\n' "$path"
      printf 'sha256:%s\n' "$(shasum -a 256 "$ROOT_DIR/$path" | awk '{print $1}')"
    done
  } | shasum -a 256 | awk '{print $1}'
}

write_rollback_manifest() {
  local previous_cdhash="$1"
  local installed_cdhash="$2"
  local dmg_sha256="$3"
  local source_dirty="false"
  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
    source_dirty="true"
  fi
  plutil -create xml1 "$ROLLBACK_MANIFEST_TMP"
  plutil -insert createdAt -string "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ROLLBACK_MANIFEST_TMP"
  plutil -insert previousCDHash -string "$previous_cdhash" "$ROLLBACK_MANIFEST_TMP"
  plutil -insert installedCDHash -string "$installed_cdhash" "$ROLLBACK_MANIFEST_TMP"
  plutil -insert sourceCommit -string "$(git -C "$ROOT_DIR" rev-parse HEAD)" "$ROLLBACK_MANIFEST_TMP"
  plutil -insert sourceDirty -bool "$source_dirty" "$ROLLBACK_MANIFEST_TMP"
  plutil -insert sourcePatchSHA256 -string "$(source_patch_sha256)" "$ROLLBACK_MANIFEST_TMP"
  plutil -insert dmgSHA256 -string "$dmg_sha256" "$ROLLBACK_MANIFEST_TMP"
  plutil -insert lastOperation -string "build-install" "$ROLLBACK_MANIFEST_TMP"
}

fail_at_checkpoint() {
  if [[ "${OPENCLAW_TEST_FAIL_AT:-}" == "$1" ]]; then
    echo "测试注入失败点: $1" >&2
    return 97
  fi
}

restore_previous_apps() {
  local status=$?
  trap - EXIT INT TERM
  rm -rf "$INSTALL_TMP"
  if (( status != 0 )); then
    if (( PERSISTENT_SWAP_STARTED == 1 )); then
      if [[ -d "$PERSISTENT_ROLLBACK_OLD" ]]; then
        rm -rf "$PERSISTENT_ROLLBACK_APP"
        mv "$PERSISTENT_ROLLBACK_OLD" "$PERSISTENT_ROLLBACK_APP"
      else
        rm -rf "$PERSISTENT_ROLLBACK_APP"
      fi
    fi
    if (( BACKUP_READY == 1 && (INSTALL_SWAP_STARTED == 1 || LEGACY_CLEANUP_STARTED == 1) )); then
      for app_name in "${OLD_APP_NAMES[@]}"; do
        # 安装目录已有非空默认值，并允许测试注入隔离目录。
        # shellcheck disable=SC2115
        rm -rf "$INSTALL_DIR/$app_name"
      done
      for app_name in "${OLD_APP_NAMES[@]}"; do
        if [[ -d "$BACKUP_DIR/$app_name" ]]; then
          ditto "$BACKUP_DIR/$app_name" "$INSTALL_DIR/$app_name"
        fi
      done
      echo "构建或安装失败，已恢复上一个桌面版本" >&2
    else
      echo "构建已停止且未清理现有桌面版本" >&2
    fi
  fi
  rm -rf "$INSTALL_PREVIOUS" "$PERSISTENT_ROLLBACK_TMP" "$ROLLBACK_MANIFEST_TMP" "$PERSISTENT_ROLLBACK_OLD" "$BACKUP_DIR"
  exit "$status"
}
trap restore_previous_apps EXIT INT TERM

echo "══════ 备份现有桌面版本（构建期间保持原样）══════"
mkdir -p "$PERSISTENT_ROLLBACK_DIR"
rm -rf "$PERSISTENT_ROLLBACK_OLD" "$ROLLBACK_MANIFEST_TMP"
[[ ! -e "$INSTALL_PREVIOUS" ]] || {
  echo "检测到同名安装暂存目录，拒绝覆盖: $INSTALL_PREVIOUS" >&2
  exit 1
}
if [[ -d "$INSTALL_APP" ]]; then
  rm -rf "$PERSISTENT_ROLLBACK_TMP"
  ditto "$INSTALL_APP" "$PERSISTENT_ROLLBACK_TMP"
  codesign --verify --deep --strict --verbose=2 "$PERSISTENT_ROLLBACK_TMP"
fi
for app_name in "${OLD_APP_NAMES[@]}"; do
  if [[ -d "$INSTALL_DIR/$app_name" ]]; then
    ditto "$INSTALL_DIR/$app_name" "$BACKUP_DIR/$app_name"
    fail_at_checkpoint "after-first-local-backup"
  fi
done
BACKUP_READY=1
# 仅删除当前工作区的旧构建产物，防止构建失败时误把旧工件当作新候选包。
rm -rf "$BUNDLE_APP"

echo "══════ 构建 Tauri 桌面端 ══════"
(cd "$FRONTEND_DIR" && npm run tauri:build)
[[ -d "$BUNDLE_APP" ]] || {
  echo "构建未生成 OpenClaw.app" >&2
  exit 1
}
codesign --verify --deep --strict --verbose=2 "$BUNDLE_APP"

echo "══════ 原子安装到 $INSTALL_DIR ══════"
[[ ! -e "$INSTALL_TMP" ]] || {
  echo "检测到同名安装临时目录，拒绝覆盖: $INSTALL_TMP" >&2
  exit 1
}
ditto "$BUNDLE_APP" "$INSTALL_TMP"
codesign --verify --deep --strict --verbose=2 "$INSTALL_TMP"
if [[ -d "$INSTALL_APP" ]]; then
  INSTALL_SWAP_STARTED=1
  mv "$INSTALL_APP" "$INSTALL_PREVIOUS"
fi
mv "$INSTALL_TMP" "$INSTALL_APP"
INSTALL_SWAP_STARTED=1
codesign --verify --deep --strict --verbose=2 "$INSTALL_APP"

installed_cdhash="$(cdhash_for "$INSTALL_APP")"
dmg_path="$(find "$FRONTEND_DIR/src-tauri/target/release/bundle/dmg" -maxdepth 1 -type f -name '*.dmg' -print 2>/dev/null | LC_ALL=C sort | tail -n 1)"
dmg_sha256=""
if [[ -n "$dmg_path" && -f "$dmg_path" ]]; then
  dmg_sha256="$(shasum -a 256 "$dmg_path" | awk '{print $1}')"
fi

rollback_candidate=""
previous_cdhash=""
if [[ -d "$PERSISTENT_ROLLBACK_TMP" ]]; then
  previous_cdhash="$(cdhash_for "$PERSISTENT_ROLLBACK_TMP")"
  if [[ -n "$previous_cdhash" && "$previous_cdhash" != "$installed_cdhash" ]]; then
    rollback_candidate="new-previous"
  fi
fi
if [[ -z "$rollback_candidate" && -d "$PERSISTENT_ROLLBACK_APP" ]]; then
  if codesign --verify --deep --strict --verbose=2 "$PERSISTENT_ROLLBACK_APP"; then
    existing_rollback_cdhash="$(cdhash_for "$PERSISTENT_ROLLBACK_APP")"
    if [[ -n "$existing_rollback_cdhash" && "$existing_rollback_cdhash" != "$installed_cdhash" ]]; then
      rollback_candidate="existing-distinct"
      previous_cdhash="$existing_rollback_cdhash"
    fi
  fi
fi

if [[ -n "$rollback_candidate" ]]; then
  write_rollback_manifest "$previous_cdhash" "$installed_cdhash" "$dmg_sha256"
  if [[ "$rollback_candidate" == "new-previous" ]]; then
    PERSISTENT_SWAP_STARTED=1
    if [[ -d "$PERSISTENT_ROLLBACK_APP" ]]; then
      mv "$PERSISTENT_ROLLBACK_APP" "$PERSISTENT_ROLLBACK_OLD"
    fi
    mv "$PERSISTENT_ROLLBACK_TMP" "$PERSISTENT_ROLLBACK_APP"
  else
    rm -rf "$PERSISTENT_ROLLBACK_TMP"
  fi
  mv "$ROLLBACK_MANIFEST_TMP" "$ROLLBACK_MANIFEST"
  echo "rollback_ready=true previous_cdhash=$previous_cdhash installed_cdhash=$installed_cdhash"
else
  rm -rf "$PERSISTENT_ROLLBACK_TMP" "$PERSISTENT_ROLLBACK_APP" "$ROLLBACK_MANIFEST"
  echo "rollback_ready=false reason=no-distinct-previous-version"
fi

echo "══════ 清理历史桌面版本 ══════"
LEGACY_CLEANUP_STARTED=1
for app_name in "OpenEverything.app" "OpenClaw-Gateway.app"; do
  # 安装目录已有非空默认值，并允许测试注入隔离目录。
  # shellcheck disable=SC2115
  rm -rf "$INSTALL_DIR/$app_name"
done
rm -rf "$INSTALL_PREVIOUS"

trap - EXIT INT TERM
rm -rf "$PERSISTENT_ROLLBACK_OLD" "$BACKUP_DIR"
echo "OpenClaw.app 已安装；历史副本已清理，回滚状态以上述 rollback_ready 证据为准"
