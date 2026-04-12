#!/usr/bin/env bash
# ============================================================
# OpenClaw Bot 夜间自动审计系统 — 主执行脚本
# 在中国时间 00:00-08:00 自动调度 Claude Code 进行全面审计
#
# 用法:
#   ./run-audit.sh              # 运行全部阶段
#   ./run-audit.sh 3            # 从第3阶段开始
#   ./run-audit.sh 2 4          # 只运行第2到第4阶段
#   ./run-audit.sh --dry-run    # 试运行（不实际执行 Claude）
# ============================================================

set -euo pipefail

# === 定位脚本目录 ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.env"

# === 加载配置 ===
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "❌ 找不到配置文件: $CONFIG_FILE"
    echo "   请先复制模板并填入配置:"
    echo "   cp ${SCRIPT_DIR}/config.env.example ${CONFIG_FILE}"
    exit 1
fi
# shellcheck source=config.env.example
source "$CONFIG_FILE"

# === 常量 ===
PHASES_DIR="${SCRIPT_DIR}/phases"
LOG_DIR="${SCRIPT_DIR}/logs"
DATE=$(date +%Y-%m-%d)
PROGRESS_FILE="${LOG_DIR}/${DATE}.progress"
SUMMARY_FILE="${LOG_DIR}/${DATE}.summary"
TOTAL_SPENT=0
LOCK_DIR="/tmp/openclaw-nightly-audit.lock"

# === 进程锁（防止多实例同时运行）===
acquire_lock() {
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        local existing_pid
        existing_pid=$(cat "${LOCK_DIR}/pid" 2>/dev/null || echo "未知")
        echo "❌ 另一个审计实例正在运行 (PID: ${existing_pid})"
        echo "   如果确认没有其他实例，请手动删除锁: rm -rf ${LOCK_DIR}"
        exit 1
    fi
    echo $$ > "${LOCK_DIR}/pid"
}

# === 全局清理函数 ===
cleanup() {
    # 释放进程锁
    rm -rf "$LOCK_DIR" 2>/dev/null || true
    # 终止防休眠进程
    if [[ -n "${CAFFEINATE_PID:-}" ]]; then
        kill "$CAFFEINATE_PID" 2>/dev/null || true
    fi
    # 如果配置了审计后休眠，让 Mac 进入休眠
    if [[ "$(uname)" == "Darwin" && "${SLEEP_AFTER_AUDIT:-false}" == "true" ]]; then
        pmset sleepnow 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# === 颜色输出 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

# === 参数解析 ===
DRY_RUN=false
START_PHASE=1
END_PHASE=6

for arg in "$@"; do
    if [[ "$arg" == "--dry-run" ]]; then
        DRY_RUN=true
    fi
done

# 非 --dry-run 参数视为阶段范围
POSITIONAL_ARGS=()
for arg in "$@"; do
    if [[ "$arg" != "--dry-run" ]]; then
        POSITIONAL_ARGS+=("$arg")
    fi
done

if [[ ${#POSITIONAL_ARGS[@]} -eq 1 ]]; then
    START_PHASE="${POSITIONAL_ARGS[0]}"
elif [[ ${#POSITIONAL_ARGS[@]} -eq 2 ]]; then
    START_PHASE="${POSITIONAL_ARGS[0]}"
    END_PHASE="${POSITIONAL_ARGS[1]}"
fi

# ============================================================
# 工具函数
# ============================================================

log() {
    local level="$1"
    shift
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local cst_time
    cst_time=$(TZ=Asia/Shanghai date '+%H:%M')

    case "$level" in
        INFO)  echo -e "${GREEN}[${timestamp}] [CST ${cst_time}] [INFO]${NC} $*" ;;
        WARN)  echo -e "${YELLOW}[${timestamp}] [CST ${cst_time}] [WARN]${NC} $*" ;;
        ERROR) echo -e "${RED}[${timestamp}] [CST ${cst_time}] [ERROR]${NC} $*" ;;
        PHASE) echo -e "${BLUE}[${timestamp}] [CST ${cst_time}] [PHASE]${NC} $*" ;;
    esac

    # 同时写入日志文件
    echo "[${timestamp}] [CST ${cst_time}] [${level}] $*" >> "${LOG_DIR}/${DATE}.log"
}

# 获取中国时间当前小时（0-23）
get_cst_hour() {
    TZ=Asia/Shanghai date +%H | sed 's/^0//'
}

# 获取中国时间当前分钟
get_cst_minute() {
    TZ=Asia/Shanghai date +%M | sed 's/^0//'
}

# 计算距离 END_HOUR_CST 还剩多少分钟
get_remaining_minutes() {
    local hour
    hour=$(get_cst_hour)
    local minute
    minute=$(get_cst_minute)

    # 处理跨午夜场景: 如果当前小时 >= 12，说明还没到午夜
    # 如果 < END_HOUR_CST，说明已经过了午夜，在早上时段
    if [[ $hour -ge 12 ]]; then
        # 还没到午夜，剩余 = (24 - hour) * 60 - minute + END_HOUR_CST * 60
        echo $(( (24 - hour) * 60 - minute + END_HOUR_CST * 60 ))
    elif [[ $hour -lt $END_HOUR_CST ]]; then
        # 已过午夜，在 00:00-08:00 窗口内
        echo $(( (END_HOUR_CST - hour) * 60 - minute ))
    else
        # 已过 END_HOUR_CST，时间到了
        echo 0
    fi
}

# 检查是否还有足够时间运行下一个阶段
check_time_ok() {
    local remaining
    remaining=$(get_remaining_minutes)
    if [[ $remaining -lt ${MIN_REMAINING_MINUTES:-30} ]]; then
        log WARN "剩余时间不足 ${MIN_REMAINING_MINUTES:-30} 分钟（剩余 ${remaining} 分钟），停止调度"
        return 1
    fi
    log INFO "剩余时间: ${remaining} 分钟"
    return 0
}

# 检查总预算是否超限
check_budget_ok() {
    # 使用 awk 做浮点比较
    local over
    over=$(awk "BEGIN {print ($TOTAL_SPENT >= ${MAX_TOTAL_BUDGET:-15})}")
    if [[ "$over" == "1" ]]; then
        log WARN "总花费 \$${TOTAL_SPENT} 已达到预算上限 \$${MAX_TOTAL_BUDGET:-15}，停止调度"
        return 1
    fi
    return 0
}

# 发送 Telegram 通知（可选）
send_notification() {
    local message="$1"
    if [[ -n "${NOTIFY_TG_BOT_TOKEN:-}" && -n "${NOTIFY_TG_CHAT_ID:-}" ]]; then
        curl -s -X POST \
            "https://api.telegram.org/bot${NOTIFY_TG_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${NOTIFY_TG_CHAT_ID}" \
            -d "text=${message}" \
            -d "parse_mode=Markdown" \
            > /dev/null 2>&1 || true
        log INFO "Telegram 通知已发送"
    fi
}

# 构建 Claude Code 命令行
build_claude_cmd() {
    local prompt="$1"
    local budget="$2"

    local cmd=("${CLAUDE_BIN:-claude}")
    cmd+=(-p "$prompt")
    cmd+=(--dangerously-skip-permissions)
    cmd+=(--max-budget-usd "$budget")
    cmd+=(--output-format text)

    # 模型配置
    if [[ -n "${MODEL:-}" ]]; then
        cmd+=(--model "$MODEL")
    fi

    echo "${cmd[@]}"
}

# ============================================================
# 阶段执行引擎
# ============================================================

run_phase() {
    local phase_num="$1"
    local phase_file="$2"
    local phase_name="$3"

    log PHASE "========== 阶段 ${phase_num}/6: ${phase_name} =========="

    # 检查提示词文件是否存在
    if [[ ! -f "$phase_file" ]]; then
        log ERROR "提示词文件不存在: $phase_file"
        return 1
    fi

    # 检查时间和预算
    if ! check_time_ok; then return 1; fi
    if ! check_budget_ok; then return 1; fi

    # 读取提示词
    local prompt
    prompt=$(cat "$phase_file")

    # 记录开始时间
    local start_ts
    start_ts=$(date +%s)
    echo "phase${phase_num}_start=$(TZ=Asia/Shanghai date '+%H:%M')" >> "$PROGRESS_FILE"

    # === 首次运行 ===
    local run_log="${LOG_DIR}/${DATE}_phase${phase_num}_run1.log"
    log INFO "首次运行阶段 ${phase_num}..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log INFO "[DRY RUN] 将执行: claude -p '<prompt>' --dangerously-skip-permissions --max-budget-usd ${BUDGET_PER_PHASE}"
        echo "[DRY RUN] 阶段 ${phase_num} 跳过" > "$run_log"
    else
        # 导出 API 配置到环境变量
        export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
        if [[ -n "${ANTHROPIC_BASE_URL:-}" ]]; then
            export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL}"
        fi

        # 执行 Claude Code（使用官方推荐的 --bare 模式加速启动）
        local session_id
        session_id=$(uuidgen 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())")

        "${CLAUDE_BIN:-claude}" \
            -p "$prompt" \
            --bare \
            --dangerously-skip-permissions \
            --max-budget-usd "${BUDGET_PER_PHASE:-3}" \
            --max-turns "${MAX_TURNS_PER_PHASE:-200}" \
            ${MODEL:+--model "$MODEL"} \
            ${FALLBACK_MODEL:+--fallback-model "$FALLBACK_MODEL"} \
            --session-id "$session_id" \
            --output-format text \
            > "$run_log" 2>&1 || {
                log WARN "阶段 ${phase_num} 首次运行异常退出（可能是预算耗尽/上下文已满/达到最大轮次）"
            }

        # 保存 session ID 用于续接
        echo "phase${phase_num}_session=${session_id}" >> "$PROGRESS_FILE"

        # === 续接运行（如果上下文满了或工作未完成）===
        local max_cont="${MAX_CONTINUATIONS:-3}"
        for run_num in $(seq 2 "$max_cont"); do
            # 再次检查时间和预算
            if ! check_time_ok; then break; fi
            if ! check_budget_ok; then break; fi

            # 检查上一轮输出是否暗示工作未完成
            local prev_log="${LOG_DIR}/${DATE}_phase${phase_num}_run$((run_num - 1)).log"
            if [[ -f "$prev_log" ]]; then
                # 如果输出包含"完成"/"all done"等标记，不需要续接
                if grep -qiE '(本阶段.*完成|所有.*审计.*完成|全部.*修复|阶段.*结束)' "$prev_log" 2>/dev/null; then
                    log INFO "阶段 ${phase_num} 已在上一轮完成，跳过续接"
                    break
                fi
            fi

            log INFO "续接运行 ${run_num}/${max_cont}..."
            local cont_log="${LOG_DIR}/${DATE}_phase${phase_num}_run${run_num}.log"

            local cont_prompt="请继续上一轮未完成的审计工作。

【操作步骤】
1. 先读取 docs/status/HANDOFF.md 了解当前进度
2. 回顾上一轮的工作，从停止的地方继续
3. 直接开始执行，不要重复已完成的工作
4. 完成后更新 HANDOFF.md

【重要】不要只做计划或总结，直接动手修复和验证。"

            "${CLAUDE_BIN:-claude}" \
                -p "$cont_prompt" \
                --bare \
                --dangerously-skip-permissions \
                --max-budget-usd "${BUDGET_PER_PHASE:-3}" \
                --max-turns "${MAX_TURNS_PER_PHASE:-200}" \
                ${MODEL:+--model "$MODEL"} \
                ${FALLBACK_MODEL:+--fallback-model "$FALLBACK_MODEL"} \
                --resume "$session_id" \
                --output-format text \
                > "$cont_log" 2>&1 || {
                    log WARN "阶段 ${phase_num} 续接运行 ${run_num} 异常退出"
                }
        done
    fi

    # 记录结束时间和耗时
    local end_ts
    end_ts=$(date +%s)
    local duration=$(( (end_ts - start_ts) / 60 ))
    echo "phase${phase_num}_done=$(TZ=Asia/Shanghai date '+%H:%M') (${duration}分钟)" >> "$PROGRESS_FILE"
    log PHASE "阶段 ${phase_num} 完成，耗时 ${duration} 分钟"

    # 估算花费（粗略，用阶段预算作为上限）
    TOTAL_SPENT=$(awk "BEGIN {print $TOTAL_SPENT + ${BUDGET_PER_PHASE:-3}}")

    return 0
}

# ============================================================
# 主流程
# ============================================================

main() {
    # 创建日志目录
    mkdir -p "$LOG_DIR"

    # 获取进程锁（防止多实例冲突）
    acquire_lock
    log INFO "进程锁已获取"

    # 开始
    log INFO "========================================="
    log INFO " OpenClaw Bot 夜间自动审计"
    log INFO " 日期: ${DATE}"
    log INFO " 本地时间: $(date)"
    log INFO " 中国时间: $(TZ=Asia/Shanghai date)"
    log INFO " 阶段范围: ${START_PHASE} → ${END_PHASE}"
    log INFO " 每阶段预算: \$${BUDGET_PER_PHASE:-3}"
    log INFO " 总预算上限: \$${MAX_TOTAL_BUDGET:-15}"
    if [[ "$DRY_RUN" == "true" ]]; then
        log WARN " ⚡ 试运行模式 — 不会实际执行 Claude"
    fi
    log INFO "========================================="

    # Mac 防休眠
    if [[ "$(uname)" == "Darwin" && "${PREVENT_SLEEP:-true}" == "true" ]]; then
        caffeinate -dims -w $$ &
        CAFFEINATE_PID=$!
        log INFO "Mac 防休眠已启用 (caffeinate PID: ${CAFFEINATE_PID})"
    fi

    # 初始化进度文件
    echo "# 夜间审计进度 — ${DATE}" > "$PROGRESS_FILE"
    echo "start=$(TZ=Asia/Shanghai date '+%H:%M')" >> "$PROGRESS_FILE"
    echo "mode=$(if $DRY_RUN; then echo 'dry-run'; else echo 'live'; fi)" >> "$PROGRESS_FILE"

    # 切换到项目目录
    cd "$PROJECT_DIR"
    log INFO "工作目录: $(pwd)"

    # 拉取最新代码
    if [[ "${AUTO_PUSH:-true}" == "true" ]]; then
        log INFO "拉取最新代码..."
        git pull --rebase origin "${GIT_BRANCH:-main}" 2>&1 | while read -r line; do
            log INFO "  git: $line"
        done || {
            log WARN "git pull 失败，继续使用本地代码"
        }
    fi

    # 记录初始状态
    local git_hash
    git_hash=$(git rev-parse --short HEAD)
    echo "git_start=${git_hash}" >> "$PROGRESS_FILE"
    log INFO "起始 commit: ${git_hash}"

    # === 阶段定义（兼容 bash 3.x / macOS 原生 bash）===
    # 索引 0 占位，1-6 对应阶段编号
    local phase_names_list="_ 安全审计 后端稳定性 API与集成 前端与UI 架构与运维 文件治理与文档"
    local phase_files_list="_ 01-security.txt 02-backend.txt 03-api-integration.txt 04-frontend-ui.txt 05-architecture-ops.txt 06-governance-docs.txt"

    # 按阶段号获取名称的函数
    get_phase_name() { echo "$phase_names_list" | cut -d' ' -f$(($1 + 1)); }
    get_phase_file() { echo "${PHASES_DIR}/$(echo "$phase_files_list" | cut -d' ' -f$(($1 + 1)))"; }

    # === 执行各阶段 ===
    local phases_completed=0
    local phases_skipped=0
    local phases_failed=0

    for phase_num in $(seq "$START_PHASE" "$END_PHASE"); do
        local p_name
        p_name=$(get_phase_name "$phase_num")
        local p_file
        p_file=$(get_phase_file "$phase_num")
        if run_phase "$phase_num" "$p_file" "$p_name"; then
            phases_completed=$((phases_completed + 1))
        else
            # 检查是否是时间/预算不足导致的跳过
            if ! check_time_ok 2>/dev/null || ! check_budget_ok 2>/dev/null; then
                local remaining_phases=$(( END_PHASE - phase_num + 1 ))
                phases_skipped=$((phases_skipped + remaining_phases))
                log WARN "时间或预算不足，跳过剩余 ${remaining_phases} 个阶段"
                break
            fi
            phases_failed=$((phases_failed + 1))
        fi

        # 阶段间休息 10 秒（避免 API 限流）
        if [[ $phase_num -lt $END_PHASE ]]; then
            sleep 10
        fi
    done

    # === 最终 Git 推送 ===
    if [[ "${AUTO_PUSH:-true}" == "true" && "$DRY_RUN" != "true" ]]; then
        log INFO "推送代码到远程仓库..."
        git push "${GIT_REMOTE:-origin}" "${GIT_BRANCH:-main}" 2>&1 | while read -r line; do
            log INFO "  git: $line"
        done || {
            log WARN "git push 失败，可能需要手动推送"
        }
    fi

    # === 记录最终状态 ===
    local git_hash_end
    git_hash_end=$(git rev-parse --short HEAD)
    local total_commits
    total_commits=$(git log --oneline "${git_hash}..${git_hash_end}" 2>/dev/null | wc -l | tr -d ' ')

    echo "" >> "$PROGRESS_FILE"
    echo "git_end=${git_hash_end}" >> "$PROGRESS_FILE"
    echo "total_commits=${total_commits}" >> "$PROGRESS_FILE"
    echo "phases_completed=${phases_completed}" >> "$PROGRESS_FILE"
    echo "phases_skipped=${phases_skipped}" >> "$PROGRESS_FILE"
    echo "phases_failed=${phases_failed}" >> "$PROGRESS_FILE"
    echo "end=$(TZ=Asia/Shanghai date '+%H:%M')" >> "$PROGRESS_FILE"

    # === 生成摘要 ===
    {
        echo "# 夜间审计摘要 — ${DATE}"
        echo ""
        echo "- 开始: $(head -3 "$PROGRESS_FILE" | grep start= | cut -d= -f2) CST"
        echo "- 结束: $(TZ=Asia/Shanghai date '+%H:%M') CST"
        echo "- 阶段完成: ${phases_completed}/${END_PHASE}"
        echo "- 阶段跳过: ${phases_skipped}"
        echo "- 阶段失败: ${phases_failed}"
        echo "- Git commits: ${total_commits} (${git_hash} → ${git_hash_end})"
        echo "- 预估花费: \$${TOTAL_SPENT}"
        echo ""
        echo "## 各阶段状态"
        for phase_num in $(seq "$START_PHASE" "$END_PHASE"); do
            local status="⬜ 未运行"
            if grep -q "phase${phase_num}_done=" "$PROGRESS_FILE" 2>/dev/null; then
                status="✅ 完成"
            elif grep -q "phase${phase_num}_start=" "$PROGRESS_FILE" 2>/dev/null; then
                status="🟡 部分完成"
            fi
            echo "  ${phase_num}. $(get_phase_name "$phase_num"): ${status}"
        done
    } > "$SUMMARY_FILE"

    cat "$SUMMARY_FILE"

    log INFO "========================================="
    log INFO " 夜间审计结束"
    log INFO " 完成: ${phases_completed}  跳过: ${phases_skipped}  失败: ${phases_failed}"
    log INFO " 产生 ${total_commits} 个 commit"
    log INFO " 日志目录: ${LOG_DIR}/"
    log INFO "========================================="

    # === 发送通知 ===
    send_notification "🤖 *OpenClaw Bot 夜间审计完成*

📅 日期: ${DATE}
✅ 完成: ${phases_completed}/6 阶段
📝 产生: ${total_commits} 个 commit
💰 预估花费: \$${TOTAL_SPENT}

详细日志: ${LOG_DIR}/${DATE}.log"

    # === 清理由 trap cleanup EXIT 统一处理 ===

    # === 多轮审计（可选）===
    if [[ "${AUTO_NEXT_ROUND:-false}" == "true" ]]; then
        if check_time_ok 2>/dev/null; then
            log INFO "自动发起下一轮审计..."
            exec "$0" "$@"
        fi
    fi

    return 0
}

# === 入口 ===
main "$@"
