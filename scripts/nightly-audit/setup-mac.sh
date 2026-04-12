#!/usr/bin/env bash
# ============================================================
# OpenClaw Bot 夜间审计 — macOS 定时任务配置
# 使用 launchd 在每天中国时间 00:00 自动启动审计
#
# 用法: ./setup-mac.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.openclaw.nightly-audit"
PLIST_FILE="${HOME}/Library/LaunchAgents/${PLIST_NAME}.plist"
CONFIG_FILE="${SCRIPT_DIR}/config.env"
RUN_SCRIPT="${SCRIPT_DIR}/run-audit.sh"
LOG_DIR="${SCRIPT_DIR}/logs"

echo "============================================"
echo " OpenClaw Bot 夜间审计 — macOS 定时配置"
echo "============================================"
echo ""

# === 检查前置条件 ===
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "❌ 配置文件不存在: ${CONFIG_FILE}"
    echo "   请先创建配置:"
    echo "   cp ${SCRIPT_DIR}/config.env.example ${CONFIG_FILE}"
    exit 1
fi

if ! command -v claude &> /dev/null; then
    echo "❌ Claude Code 未安装"
    echo "   安装: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# === 确保脚本有执行权限 ===
chmod +x "$RUN_SCRIPT"

# === 创建日志目录 ===
mkdir -p "$LOG_DIR"

# === 计算 UTC 时间 ===
# 中国时间 00:00 = UTC 16:00
# launchd 使用系统本地时区，需要根据 Mac 当前时区计算
# 获取 Mac 当前 UTC 偏移（小时）
LOCAL_OFFSET=$(date +%z | sed 's/\([+-]\)\([0-9][0-9]\)\([0-9][0-9]\)/\1\2/')
LOCAL_OFFSET_NUM=$((10#${LOCAL_OFFSET#[+-]}))
if [[ "$LOCAL_OFFSET" == -* ]]; then
    LOCAL_OFFSET_NUM=$((-LOCAL_OFFSET_NUM))
fi

# CST 偏移 = +8
# 本地触发时间 = 0 + (LOCAL_OFFSET - 8) = LOCAL_OFFSET - 8
TRIGGER_HOUR=$(( (24 + LOCAL_OFFSET_NUM - 8) % 24 ))
echo "ℹ️  Mac 时区: $(date +%Z) (UTC${LOCAL_OFFSET})"
echo "ℹ️  中国时间 00:00 = 本地时间 ${TRIGGER_HOUR}:00"
echo ""

# === 卸载旧的 plist（如果存在）===
if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
    echo "ℹ️  卸载旧的定时任务..."
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
fi

# === 生成 launchd plist ===
cat > "$PLIST_FILE" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${RUN_SCRIPT}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$(grep 'PROJECT_DIR=' "$CONFIG_FILE" | cut -d'"' -f2)</string>

    <!-- 每天本地时间 ${TRIGGER_HOUR}:00 触发 = 中国时间 00:00 -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${TRIGGER_HOUR}</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <!-- 环境变量 -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>${HOME}</string>
    </dict>

    <!-- 日志输出 -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchd-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchd-stderr.log</string>

    <!-- 低优先级，不影响日常使用 -->
    <key>LowPriorityIO</key>
    <true/>
    <key>Nice</key>
    <integer>10</integer>
</dict>
</plist>
PLIST

echo "✅ launchd plist 已生成: ${PLIST_FILE}"

# === 加载定时任务 ===
launchctl load "$PLIST_FILE"
echo "✅ 定时任务已加载"

# === 配置 Mac 唤醒（可选）===
echo ""
echo "是否配置 Mac 在中国时间 23:55 自动唤醒？(y/n)"
echo "（需要 sudo 权限，确保 Mac 合盖时也能运行审计）"
read -r CONFIRM
if [[ "$CONFIRM" == "y" || "$CONFIRM" == "Y" ]]; then
    # 计算本地唤醒时间（CST 23:55 转换为本地时间）
    WAKE_HOUR=$(( (24 + LOCAL_OFFSET_NUM - 8 - 1 + 24) % 24 ))  # 提前5分钟
    sudo pmset repeat wakeorpoweron MTWRFSU "${WAKE_HOUR}:55:00"
    echo "✅ 已配置每天 ${WAKE_HOUR}:55 自动唤醒"
else
    echo "ℹ️  跳过。如需手动配置:"
    echo "    sudo pmset repeat wakeorpoweron MTWRFSU ${TRIGGER_HOUR}:55:00"
fi

# === 完成 ===
echo ""
echo "============================================"
echo " ✅ macOS 定时任务配置完成！"
echo "============================================"
echo ""
echo "管理命令:"
echo "  查看状态:  launchctl list | grep openclaw"
echo "  手动触发:  launchctl start ${PLIST_NAME}"
echo "  停止任务:  launchctl unload ${PLIST_FILE}"
echo "  查看日志:  ls ${LOG_DIR}/"
echo "  试运行:    ${RUN_SCRIPT} --dry-run"
echo ""
echo "⚠️  注意事项:"
echo "  - Mac 需要登录状态（不能完全关机）"
echo "  - 合盖休眠时需要配置 pmset 唤醒"
echo "  - 确保 config.env 中的 API 密钥正确"
echo "  - 首次建议先运行 --dry-run 确认配置"

# === 开机补跑机制 ===
echo ""
echo "============================================"
echo " 配置开机补跑检测"
echo "============================================"
echo ""
echo "如果 Mac 在审计时间（CST 00:00-08:00）处于关机状态，"
echo "开机后会自动检测昨晚是否执行过审计，没有则补跑。"
echo ""

CATCHUP_PLIST_NAME="com.openclaw.nightly-audit-catchup"
CATCHUP_PLIST_FILE="${HOME}/Library/LaunchAgents/${CATCHUP_PLIST_NAME}.plist"
CATCHUP_SCRIPT="${SCRIPT_DIR}/catchup-check.sh"

# 生成补跑检测脚本
cat > "$CATCHUP_SCRIPT" << 'CATCHUP'
#!/usr/bin/env bash
# ============================================================
# 开机补跑检测脚本
# Mac 开机/登录时自动运行，检测昨晚审计是否执行
# 如果没有执行，在白天时间窗口外也可以补跑
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.env"
LOG_DIR="${SCRIPT_DIR}/logs"

# 加载配置
if [[ ! -f "$CONFIG_FILE" ]]; then exit 0; fi
source "$CONFIG_FILE"

# 获取昨天的日期
if [[ "$(uname)" == "Darwin" ]]; then
    YESTERDAY=$(date -v-1d +%Y-%m-%d)
else
    YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
fi
TODAY=$(date +%Y-%m-%d)

# 检查昨晚的审计是否执行过
YESTERDAY_PROGRESS="${LOG_DIR}/${YESTERDAY}.progress"
TODAY_PROGRESS="${LOG_DIR}/${TODAY}.progress"

# 如果昨天和今天的审计记录都不存在，说明昨晚审计被跳过了
if [[ ! -f "$YESTERDAY_PROGRESS" && ! -f "$TODAY_PROGRESS" ]]; then
    echo "[$(date)] 检测到昨晚审计未执行（可能Mac关机了），启动补跑..."
    echo "[$(date)] catchup: 昨晚审计未执行，启动补跑" >> "${LOG_DIR}/${TODAY}.log"

    # 等待 60 秒，确保系统完全启动
    sleep 60

    # 执行审计（使用补跑模式，不受时间窗口限制）
    # 通过设置环境变量跳过时间窗口检查
    START_HOUR_CST=0 END_HOUR_CST=23 "${SCRIPT_DIR}/run-audit.sh" &
else
    echo "[$(date)] 昨晚审计已执行，无需补跑"
fi
CATCHUP

chmod +x "$CATCHUP_SCRIPT"

# 卸载旧的补跑 plist
if launchctl list 2>/dev/null | grep -q "$CATCHUP_PLIST_NAME"; then
    launchctl unload "$CATCHUP_PLIST_FILE" 2>/dev/null || true
fi

# 生成补跑检测的 launchd plist（开机/登录时自动运行）
cat > "$CATCHUP_PLIST_FILE" << CATCHUP_PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${CATCHUP_PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${CATCHUP_SCRIPT}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$(grep 'PROJECT_DIR=' "$CONFIG_FILE" | cut -d'"' -f2)</string>

    <!-- 登录时运行一次 -->
    <key>RunAtLoad</key>
    <true/>

    <!-- 环境变量 -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>${HOME}</string>
    </dict>

    <!-- 日志输出 -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/catchup-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/catchup-stderr.log</string>

    <!-- 低优先级 -->
    <key>LowPriorityIO</key>
    <true/>
    <key>Nice</key>
    <integer>15</integer>
</dict>
</plist>
CATCHUP_PLIST

launchctl load "$CATCHUP_PLIST_FILE"
echo "✅ 开机补跑检测已配置"
echo "   Mac 开机/登录时会自动检查昨晚审计是否执行"
echo "   补跑脚本: ${CATCHUP_SCRIPT}"
echo "   plist: ${CATCHUP_PLIST_FILE}"
