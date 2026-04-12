#!/bin/bash
# VPS Failover 检查脚本
# 部署方式: 在 VPS 上用 systemd timer 每 30 秒执行一次
# 检查 /opt/openclaw/data/primary_heartbeat 文件的修改时间和内容
# 连续 3 次失败 (90秒无心跳) → 自动切换为主节点
#
# 心跳文件格式: "bot_alive|<unix_timestamp>"
#   - "bot_alive" 标识 Mac 端 Bot 进程确实在运行
#   - 仅当内容包含 "bot_alive" 且文件未超时时才视为有效心跳
#
# 安装步骤:
#   1. 复制到 VPS: scp vps_failover_check.sh openclaw@VPS:/opt/openclaw/scripts/
#   2. 复制 systemd 单元文件到 /etc/systemd/system/
#   3. sudo systemctl daemon-reload
#   4. sudo systemctl enable --now clawbot-failover.timer

set -euo pipefail

# ── 配置 ──
HEARTBEAT_FILE="/opt/openclaw/data/primary_heartbeat"
SHUTDOWN_FILE="/opt/openclaw/data/primary_shutdown"
FAIL_COUNT_FILE="/opt/openclaw/data/failover_fail_count"
MAX_HEARTBEAT_AGE=120  # 心跳文件最大年龄(秒)，超过视为丢失
MAX_FAIL_COUNT=3       # 连续失败次数达到后触发切换
CLAWBOT_SERVICE="clawbot"
LOG_TAG="clawbot-failover"

log() { logger -t "$LOG_TAG" "$1"; }

# ── 检查主动关机标记 ──
if [ -f "$SHUTDOWN_FILE" ]; then
    log "检测到主节点主动关机标记，立即切换"
    rm -f "$SHUTDOWN_FILE"
    rm -f "$FAIL_COUNT_FILE"
    sudo systemctl start "$CLAWBOT_SERVICE" 2>/dev/null && log "已启动 $CLAWBOT_SERVICE" || log "启动失败"
    exit 0
fi

# ── 检查心跳文件 ──
FAIL=0
if [ ! -f "$HEARTBEAT_FILE" ]; then
    log "心跳文件不存在: $HEARTBEAT_FILE"
    FAIL=1
else
    LAST_MOD=$(stat -c %Y "$HEARTBEAT_FILE" 2>/dev/null || stat -f %m "$HEARTBEAT_FILE" 2>/dev/null)
    NOW=$(date +%s)
    AGE=$((NOW - LAST_MOD))

    if [ "$AGE" -gt "$MAX_HEARTBEAT_AGE" ]; then
        log "心跳超时: ${AGE}秒 > ${MAX_HEARTBEAT_AGE}秒"
        FAIL=1
    else
        # 验证心跳文件内容: 必须包含 "bot_alive" 标记
        HEARTBEAT_CONTENT=$(cat "$HEARTBEAT_FILE" 2>/dev/null || echo "")
        if echo "$HEARTBEAT_CONTENT" | grep -q "bot_alive"; then
            # 心跳有效 — Bot 确实在运行，重置计数器
            rm -f "$FAIL_COUNT_FILE"

            # 退让机制: Mac Bot 确认存活后，VPS 应让位
            if sudo systemctl is-active --quiet "$CLAWBOT_SERVICE" 2>/dev/null; then
                log "主节点 Bot 确认存活 (心跳内容: $HEARTBEAT_CONTENT)，VPS 退让: 停止 $CLAWBOT_SERVICE"
                sudo systemctl stop "$CLAWBOT_SERVICE" 2>/dev/null
            fi
            exit 0
        else
            # 心跳文件存在但不含 bot_alive — Mac 开机但 Bot 未运行
            log "心跳文件存在但 Bot 未运行 (内容: $HEARTBEAT_CONTENT)，视为失败"
            FAIL=1
        fi
    fi
fi

# ── 累加失败计数 ──
if [ "$FAIL" -eq 1 ]; then
    CURRENT_COUNT=0
    [ -f "$FAIL_COUNT_FILE" ] && CURRENT_COUNT=$(cat "$FAIL_COUNT_FILE")
    CURRENT_COUNT=$((CURRENT_COUNT + 1))
    echo "$CURRENT_COUNT" > "$FAIL_COUNT_FILE"

    if [ "$CURRENT_COUNT" -ge "$MAX_FAIL_COUNT" ]; then
        log "连续 $CURRENT_COUNT 次心跳失败，触发 failover 切换"
        rm -f "$FAIL_COUNT_FILE"
        systemctl start "$CLAWBOT_SERVICE" 2>/dev/null && log "已启动 $CLAWBOT_SERVICE" || log "启动失败"
    else
        log "心跳失败 $CURRENT_COUNT/$MAX_FAIL_COUNT"
    fi
fi
