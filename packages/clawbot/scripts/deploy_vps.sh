#!/bin/bash
# ClawBot VPS 部署脚本
# 用法: ./deploy_vps.sh [VPS_HOST] [SSH_PORT]

VPS_HOST="${DEPLOY_VPS_HOST:?请设置 DEPLOY_VPS_HOST 环境变量}"
SSH_PORT="${DEPLOY_VPS_PORT:-29222}"
VPS_USER="${DEPLOY_VPS_USER:-clawbot}"
# NOTE: clawbot 用户必须预先创建: useradd -m -s /bin/bash clawbot
REMOTE_DIR="/home/clawbot/clawbot"

echo "=== ClawBot VPS 部署 ==="
echo "目标: ${VPS_USER}@${VPS_HOST}:${SSH_PORT}"
echo ""

# 本地目录
LOCAL_DIR="$(dirname "$0")/.."

# 创建远程目录
echo "1. 创建远程目录..."
ssh -p "$SSH_PORT" "${VPS_USER}@${VPS_HOST}" "mkdir -p ${REMOTE_DIR}/{src/tools,config,logs,scripts,data}"

# 同步文件
echo "2. 同步文件..."
# NOTE: .env 中含 API Keys，不应通过 rsync 传输，应在 VPS 上手动管理
# NOTE: data/*.db 是运行时数据库，不应被本地开发环境覆盖
rsync -avz -e "ssh -p ${SSH_PORT}" \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'logs/*' \
    --exclude '.DS_Store' \
    --exclude 'config/.env' \
    --exclude 'data/*.db' \
    --exclude 'data/*.db-wal' \
    --exclude 'data/*.db-shm' \
    --exclude 'data/backups/' \
    --exclude 'data/qdrant_data/' \
    --exclude 'data/llm_cache/' \
    --exclude 'data/api_keys.json' \
    --exclude '.venv*' \
    --exclude '.git' \
    --exclude 'kiro-gateway/' \
    --exclude 'browser-agent/' \
    --exclude 'dist/' \
    --exclude 'deploy_bundle_final/' \
    --exclude 'deploy_resources/' \
    --exclude 'openclaw_deploy_final/' \
    "${LOCAL_DIR}/" "${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/"

# 安装依赖
echo "3. 安装依赖..."
ssh -p "$SSH_PORT" "${VPS_USER}@${VPS_HOST}" << 'REMOTECMD'
cd /home/clawbot/clawbot

# 检查 Python
if ! command -v python3 &> /dev/null; then
    apt update && apt install -y python3 python3-pip python3-venv
fi

# 创建虚拟环境（幂等）
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# 在虚拟环境中安装依赖
.venv/bin/pip install -r requirements.txt

# 创建 clawbot 用户（幂等）
# NOTE: 必须确保 clawbot 用户已存在，否则 systemd 服务无法启动
id -u clawbot &>/dev/null || useradd -m -s /bin/bash clawbot
chown -R clawbot:clawbot /home/clawbot/clawbot

# 安装 systemd 单元文件（从独立文件复制，不再内联）
cp ${REMOTE_DIR}/scripts/systemd/clawbot.service /etc/systemd/system/
cp ${REMOTE_DIR}/scripts/systemd/clawbot-failover.service /etc/systemd/system/
cp ${REMOTE_DIR}/scripts/systemd/clawbot-failover.timer /etc/systemd/system/

# 安装 failover 检查脚本到 /opt/openclaw/scripts/
mkdir -p /opt/openclaw/{scripts,data}
cp ${REMOTE_DIR}/scripts/vps_failover_check.sh /opt/openclaw/scripts/
chmod +x /opt/openclaw/scripts/vps_failover_check.sh
chown -R openclaw:openclaw /opt/openclaw 2>/dev/null || true

# 重载并启动服务
systemctl daemon-reload
systemctl enable clawbot
systemctl restart clawbot

# 启用 failover 定时器（VPS 备节点自动接管）
systemctl enable --now clawbot-failover.timer

echo ""
echo "服务状态:"
systemctl status clawbot --no-pager
echo ""
echo "Failover 定时器状态:"
systemctl status clawbot-failover.timer --no-pager 2>/dev/null || echo "(failover timer 未运行)"
REMOTECMD

echo ""
echo "=== 部署完成 ==="
echo "查看日志: ssh -p ${SSH_PORT} ${VPS_USER}@${VPS_HOST} 'journalctl -u clawbot -f'"
