#!/bin/bash
# OpenClaw 一键停止脚本 - 停止所有服务

cd "$(dirname "$0")/.."

echo "🛑 停止所有 OpenClaw 服务..."

# 停止 ClawBot (6个Telegram Bot)
if [ -f /tmp/clawbot.pid ]; then
    PID=$(cat /tmp/clawbot.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID && echo "  ✅ ClawBot 已停止 (PID: $PID)"
        rm /tmp/clawbot.pid
    fi
fi

# 停止闲鱼客服
if [ -f /tmp/xianyu.pid ]; then
    PID=$(cat /tmp/xianyu.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID && echo "  ✅ 闲鱼客服已停止 (PID: $PID)"
        rm /tmp/xianyu.pid
    fi
fi

# 停止部署服务
if [ -f /tmp/deploy_server.pid ]; then
    PID=$(cat /tmp/deploy_server.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID && echo "  ✅ 部署服务已停止 (PID: $PID)"
        rm /tmp/deploy_server.pid
    fi
fi

# 停止 g4f
if [ -f /tmp/g4f.pid ]; then
    PID=$(cat /tmp/g4f.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID && echo "  ✅ g4f 已停止 (PID: $PID)"
        rm /tmp/g4f.pid
    fi
fi

echo "✅ 所有服务已停止"
