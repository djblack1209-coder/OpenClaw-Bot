#!/bin/bash
# ClawBot macOS 开机自启动卸载脚本
# 用法: ./scripts/uninstall_service.sh

PLIST_NAME="com.clawbot.agent"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "=== 卸载 ClawBot 开机自启动 ==="

# 停止并卸载服务
if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
    echo "停止服务..."
    launchctl bootout "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || true
    echo "服务已停止"
else
    echo "服务未在运行"
fi

# 删除 plist 文件
if [ -f "$PLIST_PATH" ]; then
    rm "$PLIST_PATH"
    echo "已删除: $PLIST_PATH"
else
    echo "plist 文件不存在"
fi

echo ""
echo "ClawBot 开机自启动已卸载"
