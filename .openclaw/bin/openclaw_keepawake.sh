#!/bin/bash
set -euo pipefail

PATTERN='openclaw-manager|openclaw-gateway|multi_main.py'

while true; do
  PID="$(pgrep -f "$PATTERN" | head -n 1 || true)"
  if [[ -n "$PID" ]]; then
    /usr/bin/caffeinate -dimsu -w "$PID"
  else
    sleep 10
  fi
done
