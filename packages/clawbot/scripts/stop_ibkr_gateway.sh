#!/bin/bash
set -euo pipefail

log() {
  printf '[IBKR-STOP] %s\n' "$*"
}

osascript <<'APPLESCRIPT' >/dev/null 2>&1 || true
tell application "System Events"
  if exists process "JavaApplicationStub" then
    try
      tell process "JavaApplicationStub"
        set frontmost to true
        keystroke "q" using {command down}
      end tell
    end try
  end if
end tell
APPLESCRIPT

pkill -f "IB Gateway" >/dev/null 2>&1 || true
pkill -f "ibgateway" >/dev/null 2>&1 || true
pkill -f "Trader Workstation" >/dev/null 2>&1 || true

sleep 2

PORT_READY="$(python3 - <<'PY'
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
)"

if [[ "$PORT_READY" == "1" ]]; then
  log "端口 4002 仍可访问，可能还有其他客户端占用"
  exit 1
fi

log "IBKR 相关进程已停止"
