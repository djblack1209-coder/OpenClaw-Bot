#!/usr/bin/env bash
# ============================================================
# OpenEverything 夜间审计 — Ubuntu 服务器安装脚本
# 在腾讯云 Ubuntu 22.04 服务器上部署自动审计环境
#
# 用法: ssh root@your-server 'bash -s' < install-server.sh
# 或:   scp install-server.sh root@your-server: && ssh root@your-server ./install-server.sh
# ============================================================

set -euo pipefail

echo "============================================"
echo " OpenEverything 夜间审计 — 服务器环境安装"
echo "============================================"

# === 系统依赖 ===
echo "[1/6] 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq \
    git curl wget unzip \
    build-essential \
    software-properties-common \
    > /dev/null 2>&1
echo "  ✅ 系统依赖已安装"

# === Node.js 20 LTS ===
echo "[2/6] 安装 Node.js 20 LTS..."
if ! command -v node &> /dev/null || [[ $(node -v | cut -d. -f1 | tr -d 'v') -lt 20 ]]; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null 2>&1
    apt-get install -y -qq nodejs > /dev/null 2>&1
fi
echo "  ✅ Node.js $(node -v) 已安装"

# === Python 3.12 ===
echo "[3/6] 安装 Python 3.12..."
if ! command -v python3.12 &> /dev/null; then
    add-apt-repository -y ppa:deadsnakes/ppa > /dev/null 2>&1
    apt-get update -qq
    apt-get install -y -qq python3.12 python3.12-venv python3.12-dev > /dev/null 2>&1
fi
echo "  ✅ Python $(python3.12 --version) 已安装"

# === Claude Code ===
echo "[4/6] 安装 Claude Code..."
if ! command -v claude &> /dev/null; then
    # 使用官方推荐的安装方式（npm 方式已废弃）
    curl -fsSL https://claude.ai/install.sh | bash > /dev/null 2>&1 || {
        echo "  ⚠️  官方安装脚本失败，回退到 npm 方式..."
        npm install -g @anthropic-ai/claude-code > /dev/null 2>&1
    }
fi
echo "  ✅ Claude Code $(claude --version 2>/dev/null || echo '已安装') "

# === 项目克隆 ===
echo "[5/6] 克隆项目仓库..."
PROJECT_DIR="/opt/openclaw-bot"
if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "  请输入 GitHub 仓库 URL（如 https://github.com/user/OpenClaw-Bot.git）:"
    read -r REPO_URL
    git clone "$REPO_URL" "$PROJECT_DIR"
    echo "  ✅ 项目已克隆到 ${PROJECT_DIR}"
else
    echo "  ℹ️  项目目录已存在: ${PROJECT_DIR}"
    cd "$PROJECT_DIR" && git pull --rebase || true
fi

# === Python 虚拟环境 ===
echo "[6/6] 配置 Python 虚拟环境..."
VENV_DIR="${PROJECT_DIR}/packages/clawbot/.venv312"
if [[ ! -d "$VENV_DIR" ]]; then
    python3.12 -m venv "$VENV_DIR"
    source "${VENV_DIR}/bin/activate"
    pip install --upgrade pip > /dev/null 2>&1
    if [[ -f "${PROJECT_DIR}/packages/clawbot/requirements.txt" ]]; then
        pip install -r "${PROJECT_DIR}/packages/clawbot/requirements.txt" > /dev/null 2>&1 || {
            echo "  ⚠️  部分依赖安装失败，可能需要手动处理"
        }
    fi
    if [[ -f "${PROJECT_DIR}/packages/clawbot/requirements-dev.txt" ]]; then
        pip install -r "${PROJECT_DIR}/packages/clawbot/requirements-dev.txt" > /dev/null 2>&1 || true
    fi
    deactivate
fi
echo "  ✅ Python venv 已配置"

# === 配置文件 ===
CONFIG_DIR="${PROJECT_DIR}/scripts/nightly-audit"
CONFIG_FILE="${CONFIG_DIR}/config.env"
if [[ ! -f "$CONFIG_FILE" ]]; then
    cp "${CONFIG_DIR}/config.env.example" "$CONFIG_FILE"
    # 更新项目路径为服务器路径
    sed -i "s|PROJECT_DIR=.*|PROJECT_DIR=\"${PROJECT_DIR}\"|" "$CONFIG_FILE"
    sed -i "s|CLAUDE_BIN=.*|CLAUDE_BIN=\"$(which claude)\"|" "$CONFIG_FILE"
    echo ""
    echo "⚠️  请编辑配置文件填入 API 密钥:"
    echo "    vim ${CONFIG_FILE}"
    echo ""
    echo "    必填项:"
    echo "    - ANTHROPIC_API_KEY: 你的 API 密钥"
    echo "    - ANTHROPIC_BASE_URL: 如果使用第三方提供商"
    echo "    - MODEL: 模型名称"
fi

# === Cron 定时任务 ===
echo ""
echo "============================================"
echo " 配置定时任务"
echo "============================================"
echo ""
echo "中国时间 00:00 = UTC 16:00"
echo ""

# 检查是否已有 cron 条目
CRON_CMD="cd ${PROJECT_DIR} && ${CONFIG_DIR}/run-audit.sh >> ${CONFIG_DIR}/logs/cron.log 2>&1"
if crontab -l 2>/dev/null | grep -q "run-audit.sh"; then
    echo "ℹ️  Cron 任务已存在，跳过配置"
else
    echo "是否要添加 cron 定时任务？(y/n)"
    read -r CONFIRM
    if [[ "$CONFIRM" == "y" || "$CONFIRM" == "Y" ]]; then
        # UTC 16:00 = CST 00:00
        (crontab -l 2>/dev/null; echo "0 16 * * * ${CRON_CMD}") | crontab -
        echo "  ✅ Cron 任务已添加: 每天 UTC 16:00 (CST 00:00) 执行"
    else
        echo "  跳过。你可以手动添加:"
        echo "  crontab -e"
        echo "  0 16 * * * ${CRON_CMD}"
    fi
fi

# === 赋予执行权限 ===
chmod +x "${CONFIG_DIR}/run-audit.sh"

# === 完成 ===
echo ""
echo "============================================"
echo " ✅ 安装完成！"
echo "============================================"
echo ""
echo "下一步操作:"
echo "1. 编辑配置: vim ${CONFIG_FILE}"
echo "2. 填入 ANTHROPIC_API_KEY 和其他配置"
echo "3. 试运行:   ${CONFIG_DIR}/run-audit.sh --dry-run"
echo "4. 正式运行: ${CONFIG_DIR}/run-audit.sh"
echo "5. 查看日志: ls ${CONFIG_DIR}/logs/"
echo ""
echo "⚠️  安全提醒:"
echo "- 不要把 config.env 提交到 Git"
echo "- 建议创建专用的非 root 用户运行审计"
echo "- 定期检查日志确认运行正常"
