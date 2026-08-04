#!/usr/bin/env bash
# OpenClaw 桌面端上一版本地回滚：默认只检查，实际替换必须显式确认。
set -Eeuo pipefail

MODE="${1:---check}"
INSTALL_DIR="${OPENCLAW_INSTALL_DIR:-/Applications}"
INSTALL_APP="$INSTALL_DIR/OpenClaw.app"
INSTALL_TMP="$INSTALL_DIR/.OpenClaw.app.rollback-$$"
ROLLBACK_DIR="${OPENCLAW_ROLLBACK_DIR:-$HOME/Library/Application Support/OpenClaw/release-backups}"
ROLLBACK_APP="$ROLLBACK_DIR/OpenClaw.app"
ROLLBACK_MANIFEST="$ROLLBACK_DIR/manifest.plist"
CURRENT_TMP="$ROLLBACK_DIR/.OpenClaw.current-$$"
OLD_ROLLBACK_TMP="$ROLLBACK_DIR/.OpenClaw.rollback-old-$$"
MANIFEST_TMP="$ROLLBACK_DIR/.manifest-$$.plist"

cdhash_for() {
  codesign -dvvv "$1" 2>&1 | awk -F= '/^CDHash=/{print $2; exit}'
}

manifest_value() {
  plutil -extract "$1" raw -o - "$ROLLBACK_MANIFEST"
}

check_rollback_ready() {
  [[ "$(uname -s)" == "Darwin" ]] || {
    echo "桌面回滚只支持 macOS" >&2
    return 1
  }
  [[ -d "$INSTALL_APP" ]] || {
    echo "当前 $INSTALL_APP 不存在" >&2
    return 1
  }
  [[ -d "$ROLLBACK_APP" ]] || {
    echo "没有可用的上一版回滚副本，请先成功执行一次 make tauri-build" >&2
    return 1
  }
  [[ -f "$ROLLBACK_MANIFEST" ]] || {
    echo "回滚清单不存在，拒绝使用无法对账的回滚副本" >&2
    return 1
  }
  codesign --verify --deep --strict --verbose=2 "$INSTALL_APP"
  codesign --verify --deep --strict --verbose=2 "$ROLLBACK_APP"
  current_cdhash="$(cdhash_for "$INSTALL_APP")"
  rollback_cdhash="$(cdhash_for "$ROLLBACK_APP")"
  expected_current_cdhash="$(manifest_value installedCDHash)"
  expected_rollback_cdhash="$(manifest_value previousCDHash)"
  source_patch_sha256="$(manifest_value sourcePatchSHA256)"
  dmg_sha256="$(manifest_value dmgSHA256)"
  [[ -n "$current_cdhash" && -n "$rollback_cdhash" && "$current_cdhash" != "$rollback_cdhash" ]] || {
    echo "当前应用与回滚副本指纹相同，不构成有效回滚" >&2
    return 1
  }
  [[ -n "$current_cdhash" && "$current_cdhash" == "$expected_current_cdhash" ]] || {
    echo "当前应用指纹与回滚清单不一致，拒绝回滚" >&2
    return 1
  }
  [[ -n "$rollback_cdhash" && "$rollback_cdhash" == "$expected_rollback_cdhash" ]] || {
    echo "回滚副本指纹与清单不一致，拒绝回滚" >&2
    return 1
  }
  [[ "$source_patch_sha256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "回滚清单缺少可复核的源码补丁 SHA-256" >&2
    return 1
  }
  [[ "$dmg_sha256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "回滚清单缺少可复核的 DMG SHA-256" >&2
    return 1
  }
  for legacy_app in OpenEverything.app OpenClaw-Gateway.app; do
    [[ ! -e "$INSTALL_DIR/$legacy_app" ]] || {
      echo "/Applications 中存在历史应用 $legacy_app，拒绝回滚" >&2
      return 1
    }
  done
  echo "rollback_ready=true"
}

case "$MODE" in
  --check)
    check_rollback_ready
    exit 0
    ;;
  --confirm)
    ;;
  *)
    echo "用法: $0 --check | --confirm" >&2
    exit 2
    ;;
esac

check_rollback_ready
mkdir -p "$ROLLBACK_DIR"
rm -rf "$INSTALL_TMP" "$CURRENT_TMP" "$OLD_ROLLBACK_TMP" "$MANIFEST_TMP"
ditto "$INSTALL_APP" "$CURRENT_TMP"
codesign --verify --deep --strict --verbose=2 "$CURRENT_TMP"
current_cdhash="$(cdhash_for "$CURRENT_TMP")"
rollback_cdhash="$(cdhash_for "$ROLLBACK_APP")"

restore_current_on_failure() {
  local status=$?
  trap - EXIT INT TERM
  rm -rf "$INSTALL_TMP" "$MANIFEST_TMP"
  if (( status != 0 )); then
    if [[ -d "$CURRENT_TMP" ]]; then
      rm -rf "$INSTALL_APP"
      ditto "$CURRENT_TMP" "$INSTALL_APP"
    elif [[ -d "$OLD_ROLLBACK_TMP" && -d "$ROLLBACK_APP" ]]; then
      rm -rf "$INSTALL_APP"
      ditto "$ROLLBACK_APP" "$INSTALL_APP"
    fi
    if [[ -d "$OLD_ROLLBACK_TMP" ]]; then
      rm -rf "$ROLLBACK_APP"
      mv "$OLD_ROLLBACK_TMP" "$ROLLBACK_APP"
    fi
  fi
  rm -rf "$CURRENT_TMP" "$OLD_ROLLBACK_TMP"
  exit "$status"
}
trap restore_current_on_failure EXIT INT TERM

ditto "$ROLLBACK_APP" "$INSTALL_TMP"
codesign --verify --deep --strict --verbose=2 "$INSTALL_TMP"
rm -rf "$INSTALL_APP"
mv "$INSTALL_TMP" "$INSTALL_APP"
codesign --verify --deep --strict --verbose=2 "$INSTALL_APP"

cp "$ROLLBACK_MANIFEST" "$MANIFEST_TMP"
plutil -replace previousCDHash -string "$current_cdhash" "$MANIFEST_TMP"
plutil -replace installedCDHash -string "$rollback_cdhash" "$MANIFEST_TMP"
plutil -replace createdAt -string "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MANIFEST_TMP"
plutil -remove lastOperation "$MANIFEST_TMP" 2>/dev/null || true
plutil -insert lastOperation -string "rollback-swap" "$MANIFEST_TMP"

mv "$ROLLBACK_APP" "$OLD_ROLLBACK_TMP"
mv "$CURRENT_TMP" "$ROLLBACK_APP"
mv "$MANIFEST_TMP" "$ROLLBACK_MANIFEST"

trap - EXIT INT TERM
rm -rf "$OLD_ROLLBACK_TMP"

defaults write com.apple.dock ResetLaunchPad -bool true || true
killall Dock 2>/dev/null || true

echo "OpenClaw.app 已回滚；刚替换的版本保留为下一次反向回滚副本"
