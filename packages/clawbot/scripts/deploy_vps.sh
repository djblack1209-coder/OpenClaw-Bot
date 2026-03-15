#!/bin/bash
# ClawBot VPS 部署脚本
# 用法: ./deploy_vps.sh [VPS_IP] [SSH_PORT]

VPS_IP="${1:-185.186.147.112}"
SSH_PORT="${2:-29222}"
VPS_USER="root"
REMOTE_DIR="/root/clawbot"

echo "=== ClawBot VPS 部署 ==="
echo "目标: ${VPS_USER}@${VPS_IP}:${SSH_PORT}"
echo ""

# 本地目录
LOCAL_DIR="$(dirname "$0")/.."

# 创建远程目录
echo "1. 创建远程目录..."
ssh -p "$SSH_PORT" "${VPS_USER}@${VPS_IP}" "mkdir -p ${REMOTE_DIR}/{src/tools,config,logs,scripts}"

# 同步文件
echo "2. 同步文件..."
rsync -avz -e "ssh -p ${SSH_PORT}" \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'logs/*' \
    --exclude '.DS_Store' \
    "${LOCAL_DIR}/" "${VPS_USER}@${VPS_IP}:${REMOTE_DIR}/"

# 安装依赖
echo "3. 安装依赖..."
ssh -p "$SSH_PORT" "${VPS_USER}@${VPS_IP}" << 'REMOTECMD'
cd /root/clawbot

# 检查 Python
if ! command -v python3 &> /dev/null; then
    apt update && apt install -y python3 python3-pip
fi

# 安装依赖
pip3 install -r requirements.txt

# 创建 systemd 服务
cat > /etc/systemd/system/clawbot.service << 'SERVICEEOF'
[Unit]
Description=ClawBot Telegram AI Assistant
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/clawbot
ExecStart=/usr/bin/python3 /root/clawbot/multi_main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

# 重载并启动服务
systemctl daemon-reload
systemctl enable clawbot
systemctl restart clawbot

echo ""
echo "服务状态:"
systemctl status clawbot --no-pager
REMOTECMD

echo ""
echo "=== 部署完成 ==="
echo "查看日志: ssh -p ${SSH_PORT} ${VPS_USER}@${VPS_IP} 'journalctl -u clawbot -f'"
