#!/bin/bash
# 心跳发送脚本 — Mac 端
# 先检查 Bot 进程是否存活，存活才向 VPS 发送心跳
# 解决原设计缺陷: Mac 开机但 Bot 崩溃时心跳仍然发送，VPS 永远不接管
#
# 心跳文件格式: "bot_alive|<unix_timestamp>"
#   第一个字段标识 Bot 进程确实在运行
#   第二个字段是时间戳，方便 VPS 端检查
#
# 重试机制: 最多尝试 MAX_RETRIES 次，避免单次网络抖动导致 VPS 误判主节点宕机

set -euo pipefail

# ── 配置 ──
VPS_HOST="${DEPLOY_VPS_HOST:?请设置 DEPLOY_VPS_HOST 环境变量}"
VPS_USER="${DEPLOY_VPS_USER:-openclaw}"
VPS_PORT="${DEPLOY_VPS_PORT:-29222}"
VPS_HEARTBEAT_PATH="/opt/openclaw/data/primary_heartbeat"
LOG_TAG="clawbot-heartbeat"
SSH_TIMEOUT=5
MAX_RETRIES=3
BOT_PROCESS_PATTERN="multi_main.py"

log() { logger -t "$LOG_TAG" "$1" 2>/dev/null || echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# ── 检查 Bot 进程是否存活 ──
if ! pgrep -f "$BOT_PROCESS_PATTERN" > /dev/null 2>&1; then
    log "Bot 进程未运行 (未找到 $BOT_PROCESS_PATTERN)，跳过心跳发送"
    exit 0
fi

# ── Bot 存活，发送心跳（带重试） ──
TIMESTAMP=$(date +%s)
HEARTBEAT_CONTENT="bot_alive|${TIMESTAMP}"

SENT=0
for i in $(seq 1 $MAX_RETRIES); do
    if ssh -o "ConnectTimeout=${SSH_TIMEOUT}" \
           -o "StrictHostKeyChecking=accept-new" \
           -o "BatchMode=yes" \
           -p "${VPS_PORT}" \
           "${VPS_USER}@${VPS_HOST}" \
           "echo '${HEARTBEAT_CONTENT}' > ${VPS_HEARTBEAT_PATH}" 2>/dev/null; then
        log "心跳已发送 (Bot PID: $(pgrep -f "$BOT_PROCESS_PATTERN" | head -1), 尝试 $i/$MAX_RETRIES)"
        SENT=1
        break
    fi
    if [ "$i" -lt "$MAX_RETRIES" ]; then
        sleep 2
    fi
done

if [ "$SENT" -eq 0 ]; then
    log "心跳发送失败 ($MAX_RETRIES 次尝试均超时或被拒绝)"
fi
