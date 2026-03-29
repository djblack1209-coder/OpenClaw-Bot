#!/bin/bash
# 闲鱼 AI 客服启动脚本
cd "$(dirname "$0")/.."

# 自动检测 Python 解释器
if [ -x ".venv312/bin/python3" ]; then
    PY=".venv312/bin/python3"
elif command -v python3 &>/dev/null; then
    PY="python3"
else
    echo "错误: 未找到 python3"
    exit 1
fi

"$PY" scripts/xianyu_main.py >> logs/xianyu.log 2>&1 &
echo $! > /tmp/xianyu.pid
echo "闲鱼 AI 客服已启动 (PID: $(cat /tmp/xianyu.pid))"
