#!/bin/bash
# OpenClaw OMEGA v2.0 — 一键启动脚本
# 用法: bash scripts/start_omega.sh

set -e
cd "$(dirname "$0")/.."

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🦞 OpenClaw OMEGA v2.0"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查 Python
PYTHON=""
if [ -f ".venv312/bin/python3" ]; then
    PYTHON=".venv312/bin/python3"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    echo "❌ Python3 未找到"; exit 1
fi
echo "Python: $($PYTHON --version)"

# 检查 .env
if [ ! -f "config/.env" ]; then
    echo "❌ config/.env 未找到"; exit 1
fi

# 加载 .env 中的 key（用于检查）
source config/.env 2>/dev/null || true

# 检查关键配置
echo ""
echo "配置检查:"
[ -n "$SILICONFLOW_UNLIMITED_KEY" ] && echo "  ✅ iflow 无限 API" || echo "  ⚠️  iflow API 未配置"
[ -n "$DEEPGRAM_API_KEY" ] && echo "  ✅ Deepgram STT" || echo "  ⚠️  Deepgram 未配置"
[ -n "$FAL_KEY" ] && echo "  ✅ fal.ai 图像生成" || echo "  ⚠️  fal.ai 未配置"
[ -n "$MEM0_API_KEY" ] && echo "  ✅ mem0 记忆" || echo "  ⚠️  mem0 未配置"
[ -n "$OMEGA_GATEWAY_BOT_TOKEN" ] && echo "  ✅ Gateway Bot" || echo "  ⚠️  Gateway Bot 未配置（可选）"

# 检查 Redis
if command -v redis-cli &>/dev/null && redis-cli ping &>/dev/null 2>&1; then
    echo "  ✅ Redis"
else
    echo "  ⚠️  Redis 未运行（可选，用 brew services start redis）"
fi

echo ""
echo "启动中..."
exec $PYTHON multi_main.py "$@"
