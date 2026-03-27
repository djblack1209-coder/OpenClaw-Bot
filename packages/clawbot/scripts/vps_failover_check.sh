#!/bin/bash
# VPS Failover 检查脚本
# 部署方式: 在 VPS 上用 systemd timer 每 30 秒执行一次
# 检查 /opt/openclaw/data/primary_heartbeat 文件的修改时间
# 连续 3 次失败 (90秒无心跳) → 自动切换为主节点
#
# 安装步骤:
#   1. 复制到 VPS: scp vps_failover_check.sh openclaw@VPS:/opt/openclaw/scripts/
#   2. 创建 systemd timer (见文件末尾注释)
#   3. sudo systemctl enable --now clawbot-failover.timer

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
    systemctl start "$CLAWBOT_SERVICE" 2>/dev/null && log "已启动 $CLAWBOT_SERVICE" || log "启动失败"
    exit 0
fi

# ── 检查心跳文件 ──
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
        # 心跳正常 — 重置计数器
        rm -f "$FAIL_COUNT_FILE"

        # 如果 VPS 上的 clawbot 正在运行（Mac 恢复后的退让机制）
        if systemctl is-active --quiet "$CLAWBOT_SERVICE" 2>/dev/null; then
            log "主节点心跳恢复，VPS 退让: 停止 $CLAWBOT_SERVICE"
            systemctl stop "$CLAWBOT_SERVICE" 2>/dev/null
        fi
        exit 0
    fi
fi

# ── 累加失败计数 ──
if [ "${FAIL:-0}" -eq 1 ]; then
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

# ── systemd 安装说明 ──
# 创建 /etc/systemd/system/clawbot-failover.service:
#   [Unit]
#   Description=ClawBot Failover Check
#   After=network.target
#
#   [Service]
#   Type=oneshot
#   User=openclaw
#   ExecStart=/opt/openclaw/scripts/vps_failover_check.sh
#
# 创建 /etc/systemd/system/clawbot-failover.timer:
#   [Unit]
#   Description=ClawBot Failover Check Timer
#
#   [Timer]
#   OnBootSec=30
#   OnUnitActiveSec=30
#
#   [Install]
#   WantedBy=timers.target
#
# 安装:
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now clawbot-failover.timer
