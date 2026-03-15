#!/bin/bash
# ClawBot 启动脚本
# 用法: ./scripts/start.sh

cd "$(dirname "$0")/.."

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3"
    exit 1
fi

# 检查依赖
if ! python3 -c "import telegram" 2>/dev/null; then
    echo "安装依赖..."
    pip3 install -r requirements.txt
fi

# 启动
echo "启动 ClawBot 多机器人系统..."
python3 multi_main.py
