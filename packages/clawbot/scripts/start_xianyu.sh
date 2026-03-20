#!/bin/bash
# 闲鱼 AI 客服启动脚本
cd "$(dirname "$0")/.."
.venv312/bin/python3 scripts/xianyu_main.py >> logs/xianyu.log 2>&1 &
echo $! > /tmp/xianyu.pid
echo "闲鱼 AI 客服已启动 (PID: $(cat /tmp/xianyu.pid))"
