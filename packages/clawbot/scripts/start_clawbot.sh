#!/bin/bash
# ClawBot Agent 后台启动脚本 (供 Tauri APP Fallback 使用)

DIR="/Users/blackdj/Desktop/OpenClaw Bot/packages/clawbot"
cd "$DIR" || exit 1

# 确保旧进程已被清理 (Tauri 在调用此脚本前会通过端口查杀，但做个双重保险)
pkill -f "multi_main.py" 2>/dev/null

# 后台启动
nohup .venv312/bin/python multi_main.py >> logs/com-clawbot-agent.stderr.log 2>&1 &
echo "ClawBot Agent 已启动，PID: $!"
