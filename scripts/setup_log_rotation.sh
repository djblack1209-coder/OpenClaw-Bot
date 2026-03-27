#!/bin/bash
set -euo pipefail

# OpenClaw Bot — Install newsyslog log rotation config
# Rotates all LaunchAgent stdout/stderr logs to prevent unbounded growth.
#
# Usage: sudo bash scripts/setup_log_rotation.sh
# Verify: sudo newsyslog -nv

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONF_SRC="$SCRIPT_DIR/tools/newsyslog.d/openclaw.conf"
CONF_DST="/etc/newsyslog.d/openclaw.conf"

if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run with sudo"
    echo "  sudo bash $0"
    exit 1
fi

if [[ ! -f "$CONF_SRC" ]]; then
    echo "Error: Source config not found: $CONF_SRC"
    exit 1
fi

# Ensure target directory exists
mkdir -p /etc/newsyslog.d

# Install config
cp "$CONF_SRC" "$CONF_DST"
chmod 644 "$CONF_DST"

echo "✅ Log rotation config installed: $CONF_DST"
echo ""
echo "Verifying configuration (dry run):"
newsyslog -nv -f "$CONF_DST" 2>&1 | head -30
echo ""
echo "Log rotation will run automatically via macOS newsyslog."
echo "To force immediate rotation: sudo newsyslog -f $CONF_DST"
echo ""

# Show current log sizes for reference
echo "Current LaunchAgent log sizes:"
for f in \
    "$SCRIPT_DIR/packages/clawbot/logs/com-clawbot-agent.stderr.log" \
    "$SCRIPT_DIR/packages/clawbot/logs/com-clawbot-agent.stdout.log" \
    "$SCRIPT_DIR/packages/clawbot/logs/com-clawbot-kiro-gateway.stderr.log" \
    "$SCRIPT_DIR/packages/clawbot/logs/com-clawbot-g4f.stderr.log" \
    "$SCRIPT_DIR/packages/clawbot/logs/com-clawbot-xianyu.stderr.log" \
    "$SCRIPT_DIR/.openclaw/logs/gateway.log" \
    "$SCRIPT_DIR/.openclaw/logs/gateway.err.log"; do
    if [[ -f "$f" ]]; then
        SIZE=$(du -sh "$f" 2>/dev/null | cut -f1)
        echo "  $SIZE  $(basename "$f")"
    fi
done
