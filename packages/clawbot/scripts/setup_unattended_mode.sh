#!/bin/bash
set -euo pipefail

ROOT="/Users/blackdj/Desktop/OpenClaw Bot"
LOG_DIR="$ROOT/clawbot/logs"
LAUNCH_DIR="$ROOT/launchagents"
USER_LAUNCH_DIR="$HOME/Library/LaunchAgents"
RUNTIME_BIN_DIR="$HOME/.openclaw/bin"
RUNTIME_LOG_DIR="$HOME/.openclaw/logs"

mkdir -p "$LOG_DIR" "$USER_LAUNCH_DIR" "$RUNTIME_BIN_DIR" "$RUNTIME_LOG_DIR"
chmod +x "$ROOT/clawbot/scripts/openclaw_keepawake.sh"
chmod +x "$ROOT/clawbot/scripts/bootstrap_browser_session.py"
cp "$ROOT/clawbot/scripts/openclaw_keepawake.sh" "$RUNTIME_BIN_DIR/openclaw_keepawake.sh"
cp "$ROOT/clawbot/scripts/bootstrap_browser_session.py" "$RUNTIME_BIN_DIR/bootstrap_browser_session.py"
chmod +x "$RUNTIME_BIN_DIR/openclaw_keepawake.sh" "$RUNTIME_BIN_DIR/bootstrap_browser_session.py"

for label in com.openclaw.keepawake com.openclaw.browser.bootstrap; do
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
done

ln -sf "$LAUNCH_DIR/com.openclaw.keepawake.plist" "$USER_LAUNCH_DIR/com.openclaw.keepawake.plist"
ln -sf "$LAUNCH_DIR/com.openclaw.browser.bootstrap.plist" "$USER_LAUNCH_DIR/com.openclaw.browser.bootstrap.plist"

launchctl bootstrap "gui/$(id -u)" "$LAUNCH_DIR/com.openclaw.keepawake.plist"
launchctl bootstrap "gui/$(id -u)" "$LAUNCH_DIR/com.openclaw.browser.bootstrap.plist"
launchctl kickstart -k "gui/$(id -u)/com.openclaw.keepawake"
launchctl kickstart -k "gui/$(id -u)/com.openclaw.browser.bootstrap"

python3 "$ROOT/clawbot/scripts/bootstrap_browser_session.py"

echo "OpenClaw 无人值守模式已启用"
echo "- 防睡眠: com.openclaw.keepawake"
echo "- 专用浏览器预热: com.openclaw.browser.bootstrap"
