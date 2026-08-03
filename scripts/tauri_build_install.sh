#!/usr/bin/env bash
# OpenClaw 桌面端事务式构建安装：先清理旧副本，失败时恢复上一个可用版本。
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/apps/openclaw-manager-src"
BUNDLE_DIR="$FRONTEND_DIR/src-tauri/target/release/bundle/macos"
BUNDLE_APP="$BUNDLE_DIR/OpenClaw.app"
INSTALL_DIR="/Applications"
INSTALL_APP="$INSTALL_DIR/OpenClaw.app"
INSTALL_TMP="$INSTALL_DIR/.OpenClaw.app.install-$$"
BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/openclaw-app-backup.XXXXXX")"
OLD_APP_NAMES=("OpenEverything.app" "OpenClaw.app" "OpenClaw-Gateway.app")

restore_previous_apps() {
  local status=$?
  trap - EXIT INT TERM
  rm -rf "$INSTALL_TMP"
  if (( status != 0 )); then
    for app_name in "${OLD_APP_NAMES[@]}"; do
      if [[ -d "$BACKUP_DIR/$app_name" && ! -e "$INSTALL_DIR/$app_name" ]]; then
        ditto "$BACKUP_DIR/$app_name" "$INSTALL_DIR/$app_name"
      fi
    done
    echo "构建或安装失败，已恢复上一个桌面版本" >&2
  fi
  rm -rf "$BACKUP_DIR"
  exit "$status"
}
trap restore_previous_apps EXIT INT TERM

echo "══════ 备份并清理历史桌面版本 ══════"
for app_name in "${OLD_APP_NAMES[@]}"; do
  if [[ -d "$INSTALL_DIR/$app_name" ]]; then
    ditto "$INSTALL_DIR/$app_name" "$BACKUP_DIR/$app_name"
  fi
  rm -rf "$INSTALL_DIR/$app_name"
done
rm -rf \
  "$BUNDLE_DIR/OpenEverything.app" \
  "$BUNDLE_DIR/OpenClaw.app"
if [[ -d "$ROOT_DIR/.worktrees" ]]; then
  find "$ROOT_DIR/.worktrees" -path "*/bundle/macos/*.app" -type d -exec rm -rf {} +
fi

echo "══════ 构建 Tauri 桌面端 ══════"
(cd "$FRONTEND_DIR" && npm run tauri:build)
[[ -d "$BUNDLE_APP" ]] || {
  echo "构建未生成 OpenClaw.app" >&2
  exit 1
}
codesign --verify --deep --strict --verbose=2 "$BUNDLE_APP"

echo "══════ 原子安装到 /Applications ══════"
rm -rf "$INSTALL_TMP"
ditto "$BUNDLE_APP" "$INSTALL_TMP"
codesign --verify --deep --strict --verbose=2 "$INSTALL_TMP"
mv "$INSTALL_TMP" "$INSTALL_APP"
rm -rf "$BUNDLE_APP"

defaults write com.apple.dock ResetLaunchPad -bool true
killall Dock 2>/dev/null || true

trap - EXIT INT TERM
rm -rf "$BACKUP_DIR"
echo "OpenClaw.app 已安装；历史副本已清理"
