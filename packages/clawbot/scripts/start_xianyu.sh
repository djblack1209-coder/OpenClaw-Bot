#!/bin/bash
# 闲鱼 AI 客服后台启动脚本 (供 Tauri APP Fallback 使用)

DIR="/Users/blackdj/Desktop/OpenEverything/packages/clawbot"
cd "$DIR" || exit 1

pkill -f "xianyu_main" 2>/dev/null

nohup .venv312/bin/python -m src.xianyu.xianyu_live >> logs/com-clawbot-xianyu.stderr.log 2>&1 &
echo "闲鱼 AI 客服已启动，PID: $!"
