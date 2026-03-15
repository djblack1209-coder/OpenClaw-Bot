#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
  printf '[IBKR-START] %s\n' "$*"
}

is_true() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

detect_app_path() {
  if [[ -n "${IBKR_APP_PATH:-}" && -d "${IBKR_APP_PATH}" ]]; then
    printf '%s\n' "${IBKR_APP_PATH}"
    return 0
  fi

  local candidates=(
    "$HOME/Applications/IB Gateway 10.37/IB Gateway 10.37.app"
    "$HOME/Applications/IB Gateway/IB Gateway.app"
    "/Applications/IB Gateway.app"
    "/Applications/Trader Workstation.app"
  )

  local app
  for app in "${candidates[@]}"; do
    if [[ -d "$app" ]]; then
      printf '%s\n' "$app"
      return 0
    fi
  done

  local discovered
  discovered="$(mdfind 'kMDItemContentType == "com.apple.application-bundle" && kMDItemFSName == "*IB Gateway*.app"' | head -n 1)"
  if [[ -n "$discovered" && -d "$discovered" ]]; then
    printf '%s\n' "$discovered"
    return 0
  fi

  return 1
}

is_port_ready() {
  python3 - <<'PY'
import socket

s = socket.socket()
s.settimeout(1)
try:
    s.connect(("127.0.0.1", 4002))
    print("1")
except Exception:
    print("0")
finally:
    s.close()
PY
}

if [[ "$(is_port_ready)" == "1" ]]; then
  log "API 端口 4002 已就绪，跳过启动"
  exit 0
fi

APP_PATH="$(detect_app_path || true)"
if [[ -z "$APP_PATH" ]]; then
  log "未找到 IB Gateway/TWS 应用，请设置 IBKR_APP_PATH"
  exit 1
fi

log "启动应用: $APP_PATH"
open "$APP_PATH"

if is_true "${IBKR_AUTOLOGIN_ENABLED:-true}"; then
  log "尝试执行自动登录脚本"
  osascript "$SCRIPT_DIR/ibkr_autologin.applescript" > /tmp/clawbot-ibkr-autologin.log 2>&1 || true
fi

TIMEOUT="${IBKR_START_TIMEOUT_SECONDS:-120}"
for ((i=0; i< TIMEOUT; i++)); do
  if [[ "$(is_port_ready)" == "1" ]]; then
    log "API 端口 4002 已就绪"
    exit 0
  fi

  if is_true "${IBKR_AUTOLOGIN_ENABLED:-true}"; then
    if (( i > 0 && i % 15 == 0 )); then
      log "端口未就绪，重试自动登录"
      osascript "$SCRIPT_DIR/ibkr_autologin.applescript" >> /tmp/clawbot-ibkr-autologin.log 2>&1 || true
    fi
  fi

  sleep 1
done

log "启动超时: ${TIMEOUT}s 内端口 4002 未就绪"
exit 1
