#!/bin/bash
# OpenClaw 一键启动脚本 - 启动所有服务
# 包括: 6个Telegram Bot + 闲鱼AI客服 + g4f API + 部署授权服务

set -e
cd "$(dirname "$0")/.."

echo "🚀 OpenClaw 全系统启动中..."

# 1. 启动 g4f API (端口 18891)
echo "[1/4] 启动 g4f API..."
if lsof -ti:18891 > /dev/null 2>&1; then
    echo "  ✅ g4f 已在运行 (端口 18891)"
else
    nohup python3 -m g4f.api --port 18891 > logs/g4f.log 2>&1 &
    echo $! > /tmp/g4f.pid
    sleep 2
    echo "  ✅ g4f 已启动 (PID: $(cat /tmp/g4f.pid))"
fi

# 2. 启动部署授权服务 (端口 18800)
echo "[2/4] 启动部署授权服务..."
if lsof -ti:18800 > /dev/null 2>&1; then
    echo "  ✅ 部署服务已在运行 (端口 18800)"
else
    nohup .venv312/bin/python3 -c "from src.deployer.deploy_server import run_server; run_server()" > logs/deploy_server.log 2>&1 &
    echo $! > /tmp/deploy_server.pid
    sleep 1
    echo "  ✅ 部署服务已启动 (PID: $(cat /tmp/deploy_server.pid))"
fi

# 3. 启动闲鱼AI客服
echo "[3/4] 启动闲鱼AI客服..."
if [ -f /tmp/xianyu.pid ] && kill -0 $(cat /tmp/xianyu.pid) 2>/dev/null; then
    echo "  ✅ 闲鱼客服已在运行 (PID: $(cat /tmp/xianyu.pid))"
else
    bash scripts/start_xianyu.sh
fi

# 4. 启动 6 个 Telegram Bot
echo "[4/4] 启动 6 个 Telegram Bot..."
if [ -f /tmp/clawbot.pid ] && kill -0 $(cat /tmp/clawbot.pid) 2>/dev/null; then
    echo "  ✅ ClawBot 已在运行 (PID: $(cat /tmp/clawbot.pid))"
else
    nohup .venv312/bin/python3 multi_main.py > logs/multi_bot.log 2>&1 &
    echo $! > /tmp/clawbot.pid
    sleep 3
    echo "  ✅ ClawBot 已启动 (PID: $(cat /tmp/clawbot.pid))"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 所有服务已启动"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 服务状态:"
echo "  - g4f API:        http://127.0.0.1:18891"
echo "  - 部署授权服务:   http://127.0.0.1:18800"
echo "  - 闲鱼AI客服:     运行中"
echo "  - 6个Telegram Bot: 运行中"
echo ""
echo "📝 日志位置:"
echo "  - g4f:           logs/g4f.log"
echo "  - 部署服务:       logs/deploy_server.log"
echo "  - 闲鱼客服:       logs/xianyu.log"
echo "  - Telegram Bot:  logs/multi_bot.log"
echo ""
echo "🛑 停止所有服务: bash scripts/stop_all.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
