#!/bin/bash
# ClawBot macOS 开机自启动安装脚本
# 用法: ./scripts/install_service.sh

set -e

PLIST_NAME="com.clawbot.agent"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
BOT_DIR="$HOME/Desktop/OpenClaw Bot/clawbot"
PYTHON="/usr/bin/python3"

# 检查项目目录
if [ ! -f "$BOT_DIR/multi_main.py" ]; then
    echo "错误: 未找到 $BOT_DIR/multi_main.py"
    echo "请确认项目路径正确"
    exit 1
fi

# 检查 Python
if [ ! -x "$PYTHON" ]; then
    echo "错误: 未找到 $PYTHON"
    exit 1
fi

# 确保日志目录存在
mkdir -p "$BOT_DIR/logs"

# 确保 LaunchAgents 目录存在
mkdir -p "$HOME/Library/LaunchAgents"

# 如果已有旧服务，先卸载
if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
    echo "检测到旧服务，先卸载..."
    launchctl bootout "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || true
fi

# 创建 LaunchAgent plist
cat > "$PLIST_PATH" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${BOT_DIR}/multi_main.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${BOT_DIR}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>${BOT_DIR}/logs/stdout.log</string>

    <key>StandardErrorPath</key>
    <string>${BOT_DIR}/logs/stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>LANG</key>
        <string>en_US.UTF-8</string>
    </dict>
</dict>
</plist>
PLISTEOF

# 加载服务
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

echo ""
echo "=== ClawBot 开机自启动已安装 ==="
echo ""
echo "  项目路径: $BOT_DIR"
echo "  入口文件: multi_main.py"
echo "  日志文件: $BOT_DIR/logs/stdout.log"
echo "             $BOT_DIR/logs/stderr.log"
echo "             $BOT_DIR/logs/multi_bot.log"
echo ""
echo "常用命令:"
echo "  查看状态:  launchctl print gui/$(id -u)/$PLIST_NAME"
echo "  停止服务:  launchctl bootout gui/$(id -u)/$PLIST_NAME"
echo "  启动服务:  launchctl bootstrap gui/$(id -u) $PLIST_PATH"
echo "  查看日志:  tail -f $BOT_DIR/logs/multi_bot.log"
echo "  卸载服务:  ./scripts/uninstall_service.sh"
echo ""
