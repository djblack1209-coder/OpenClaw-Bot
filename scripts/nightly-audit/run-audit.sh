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
# === 补跑模式标记（审计被系统延迟触发时自动启用）===
FORCE_RUN=false
# 补跑模式最大允许运行时长（分钟）
FORCE_RUN_MAX_MINUTES=120
# 补跑模式开始时间戳（用于计算已用时间）
FORCE_RUN_START_TS=""
# === 多项目隔离: 用项目目录的哈希值区分不同项目的锁 ===
PROJECT_HASH=$(echo "${PROJECT_DIR:-$(pwd)}" | md5sum 2>/dev/null | cut -c1-8 || echo "${PROJECT_DIR:-$(pwd)}" | md5 -q 2>/dev/null | cut -c1-8 || echo "default")
LOCK_DIR="/tmp/openclaw-nightly-audit-${PROJECT_HASH}.lock"

# === 进程锁（防止同一项目多实例运行，不同项目互不干扰）===
acquire_lock() {
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        local existing_pid
        existing_pid=$(cat "${LOCK_DIR}/pid" 2>/dev/null || echo "未知")
        # 检查旧进程是否还活着，如果已经死了则清理旧锁
        if [[ "$existing_pid" != "未知" ]] && ! kill -0 "$existing_pid" 2>/dev/null; then
            log WARN "旧审计进程 (PID: ${existing_pid}) 已不存在，清理残留锁..."
            rm -rf "$LOCK_DIR"
            mkdir "$LOCK_DIR" 2>/dev/null || { echo "❌ 无法创建锁"; exit 1; }
        else
            echo "❌ 另一个审计实例正在运行 (PID: ${existing_pid})"
            echo "   如果确认没有其他实例，请手动删除锁: rm -rf ${LOCK_DIR}"
            exit 1
        fi
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

# === 健康预检（正式审计前确认环境可用）===
preflight_check() {
    local ok=true

    # 检查 Claude Code 可用
    if ! command -v "${CLAUDE_BIN:-claude}" &>/dev/null; then
        log ERROR "Claude Code 不可用: ${CLAUDE_BIN:-claude}"
        ok=false
    fi

    # 检查 API Key 不为空
    if [[ -z "${ANTHROPIC_API_KEY:-}" || "${ANTHROPIC_API_KEY}" == "sk-your-api-key-here" ]]; then
        log ERROR "ANTHROPIC_API_KEY 未配置或仍为模板值"
        ok=false
    fi

    # 检查项目目录存在
    if [[ ! -d "${PROJECT_DIR}" ]]; then
        log ERROR "项目目录不存在: ${PROJECT_DIR}"
        ok=false
    fi

    # 检查磁盘空间（至少 500MB）
    local free_mb
    if [[ "$(uname)" == "Darwin" ]]; then
        free_mb=$(df -m "${PROJECT_DIR}" | tail -1 | awk '{print $4}')
    else
        free_mb=$(df -m "${PROJECT_DIR}" | tail -1 | awk '{print $4}')
    fi
    if [[ -n "$free_mb" ]] && [[ "$free_mb" -lt 500 ]]; then
        log ERROR "磁盘空间不足: 仅剩 ${free_mb}MB（需要至少 500MB）"
        ok=false
    fi

    # 检查 git 仓库状态
    if [[ ! -d "${PROJECT_DIR}/.git" ]]; then
        log ERROR "项目目录不是 git 仓库: ${PROJECT_DIR}"
        ok=false
    fi

    if [[ "$ok" == "false" ]]; then
        log ERROR "健康预检失败，终止审计"
        send_notification "🚨 *夜间审计预检失败*\n\n环境有问题，审计无法启动。请检查日志: ${LOG_DIR}/${DATE}.log"
        return 1
    fi

    log INFO "✅ 健康预检通过"
    return 0
}

# === 日志自动清理（保留最近 N 天）===
cleanup_old_logs() {
    local keep_days="${LOG_RETENTION_DAYS:-30}"
    local count=0
    if [[ -d "$LOG_DIR" ]]; then
        while IFS= read -r old_file; do
            rm -f "$old_file"
            count=$((count + 1))
        done < <(find "$LOG_DIR" -name "*.log" -mtime "+${keep_days}" -type f 2>/dev/null)
        while IFS= read -r old_file; do
            rm -f "$old_file"
            count=$((count + 1))
        done < <(find "$LOG_DIR" -name "*.progress" -mtime "+${keep_days}" -type f 2>/dev/null)
        while IFS= read -r old_file; do
            rm -f "$old_file"
            count=$((count + 1))
        done < <(find "$LOG_DIR" -name "*.summary" -mtime "+${keep_days}" -type f 2>/dev/null)
        while IFS= read -r old_file; do
            rm -f "$old_file"
            count=$((count + 1))
        done < <(find "$LOG_DIR" -name "*.scorecard" -mtime "+${keep_days}" -type f 2>/dev/null)
        if [[ $count -gt 0 ]]; then
            log INFO "已清理 ${count} 个超过 ${keep_days} 天的旧日志文件"
        fi
    fi
}

# === 断点续跑: 检测上次未完成的审计 ===
detect_resume_point() {
    # 如果用户手动指定了阶段范围，优先用用户的
    if [[ "${USER_SPECIFIED_RANGE:-false}" == "true" ]]; then
        return
    fi

    # 查找最近 3 天内未完成的 progress 文件
    local recent_progress=""
    for days_ago in 0 1 2; do
        local check_date
        if [[ "$(uname)" == "Darwin" ]]; then
            check_date=$(date -v-${days_ago}d +%Y-%m-%d)
        else
            check_date=$(date -d "${days_ago} days ago" +%Y-%m-%d)
        fi
        local check_file="${LOG_DIR}/${check_date}.progress"
        if [[ -f "$check_file" ]]; then
            recent_progress="$check_file"
            break
        fi
    done

    if [[ -z "$recent_progress" ]]; then
        return
    fi

    # 找到最后完成的阶段
    local last_done=0
    local total_phases="${TOTAL_PHASES:-8}"
    for p in $(seq 1 "$total_phases"); do
        if grep -q "phase${p}_done=" "$recent_progress" 2>/dev/null; then
            last_done=$p
        fi
    done

    # 如果有阶段完成了但没全部完成，从下一个阶段继续
    if [[ $last_done -gt 0 && $last_done -lt $total_phases ]]; then
        local resume_from=$((last_done + 1))
        # 检查是否是今天的文件（避免从好几天前的进度续跑）
        local progress_date
        progress_date=$(basename "$recent_progress" .progress)
        if [[ "$progress_date" == "$DATE" ]]; then
            log INFO "检测到今天的审计在阶段 ${last_done} 后中断，从阶段 ${resume_from} 续跑"
            START_PHASE=$resume_from
        else
            log INFO "检测到 ${progress_date} 的审计在阶段 ${last_done} 后中断"
            log INFO "时间超过今天，执行完整审计（如需续跑请手动: ./run-audit.sh ${resume_from}）"
        fi
    fi
}

# === 参数解析 ===
DRY_RUN=false
START_PHASE=1
END_PHASE=${TOTAL_PHASES:-8}
USER_SPECIFIED_RANGE=false

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
    USER_SPECIFIED_RANGE=true
elif [[ ${#POSITIONAL_ARGS[@]} -eq 2 ]]; then
    START_PHASE="${POSITIONAL_ARGS[0]}"
    END_PHASE="${POSITIONAL_ARGS[1]}"
    USER_SPECIFIED_RANGE=true
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
# 补跑模式下：返回补跑剩余时间（最多 FORCE_RUN_MAX_MINUTES 分钟）
get_remaining_minutes() {
    # 补跑模式：按启动时间计算剩余时长，不看时钟
    if [[ "$FORCE_RUN" == "true" && -n "$FORCE_RUN_START_TS" ]]; then
        local now_ts
        now_ts=$(date +%s)
        local elapsed_minutes=$(( (now_ts - FORCE_RUN_START_TS) / 60 ))
        local remaining=$(( FORCE_RUN_MAX_MINUTES - elapsed_minutes ))
        if [[ $remaining -lt 0 ]]; then
            remaining=0
        fi
        echo "$remaining"
        return
    fi

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
# 补跑模式下：只要补跑时间没用完就放行
check_time_ok() {
    local remaining
    remaining=$(get_remaining_minutes)

    # 补跑模式下，剩余时间由补跑计时器决定
    if [[ "$FORCE_RUN" == "true" ]]; then
        if [[ $remaining -le 0 ]]; then
            log WARN "补跑模式：${FORCE_RUN_MAX_MINUTES} 分钟补跑时间已用完，停止调度"
            return 1
        fi
        log INFO "补跑模式：剩余补跑时间 ${remaining} 分钟"
        return 0
    fi

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

# 严重问题实时告警（审计过程中发现严重问题立即通知）
send_urgent_alert() {
    local phase_num="$1"
    local phase_name="$2"
    local alert_msg="$3"
    send_notification "🚨 *夜间审计严重告警*

⚠️ 阶段 ${phase_num} (${phase_name})
${alert_msg}

请尽快查看日志: ${LOG_DIR}/${DATE}.log"
}

# 生成增量审计补丁提示词（只审计最近变更的文件）
build_incremental_prompt() {
    local phase_prompt="$1"
    local changed_files=""

    # 获取自上次审计以来变更的文件列表
    local last_audit_tag=""
    last_audit_tag=$(git tag -l "nightly-audit-*" --sort=-version:refname 2>/dev/null | head -1)

    if [[ -n "$last_audit_tag" ]]; then
        changed_files=$(git diff --name-only "$last_audit_tag"..HEAD 2>/dev/null | head -100)
    fi

    if [[ -z "$changed_files" ]]; then
        # 没有上次标记或没有变更，回退到最近 3 天的变更
        changed_files=$(git diff --name-only HEAD~50..HEAD 2>/dev/null | head -100 || echo "")
    fi

    if [[ -n "$changed_files" && "${INCREMENTAL_AUDIT:-false}" == "true" ]]; then
        echo "${phase_prompt}

【增量审计模式】
以下是自上次审计以来变更的文件，请优先审计这些文件：
${changed_files}

注意：增量审计仍需检查变更文件对其他模块的影响，但不需要全量扫描所有文件。"
    else
        echo "$phase_prompt"
    fi
}

# 检查阶段运行后的变更量（防止 AI 一次改太多文件）
check_change_volume() {
    local phase_num="$1"
    local phase_name="$2"
    local max_files="${MAX_CHANGED_FILES_PER_PHASE:-30}"

    local changed_count
    changed_count=$(git diff --name-only HEAD~1..HEAD 2>/dev/null | wc -l | tr -d ' ')

    if [[ -n "$changed_count" && "$changed_count" -gt "$max_files" ]]; then
        log WARN "阶段 ${phase_num} (${phase_name}) 修改了 ${changed_count} 个文件，超过上限 ${max_files}"
        send_urgent_alert "$phase_num" "$phase_name" "单阶段修改了 ${changed_count} 个文件（上限 ${max_files}），建议人工审查"
    fi
}

# 生成单阶段评分卡（分析阶段输出日志评估质量）
generate_phase_scorecard() {
    local phase_num="$1"
    local phase_name="$2"
    local run_log="$3"

    if [[ ! -f "$run_log" ]]; then return; fi

    local fixes=0 issues_found=0 tests_ok=0

    # 统计修复次数（通过 git commit 消息计数）
    fixes=$(git log --oneline --since="1 hour ago" --grep="\\[" 2>/dev/null | wc -l | tr -d ' ')

    # 统计发现问题数（在日志中搜索关键词）
    issues_found=$(grep -ciE '(发现|问题|bug|漏洞|缺失|错误|风险)' "$run_log" 2>/dev/null || echo "0")

    # 统计测试结果
    if grep -q "passed" "$run_log" 2>/dev/null; then
        tests_ok=1
    fi

    echo "phase${phase_num}: name=${phase_name} fixes=${fixes} issues=${issues_found} tests_ok=${tests_ok}" >> "${LOG_DIR}/${DATE}.scorecard"
}

# 生成最终审计评分报告
generate_final_scorecard() {
    local scorecard_file="${LOG_DIR}/${DATE}.scorecard"
    if [[ ! -f "$scorecard_file" ]]; then return; fi

    local total_fixes=0 total_issues=0 phases_tested=0
    while IFS= read -r line; do
        local f i t
        f=$(echo "$line" | grep -oP 'fixes=\K[0-9]+' 2>/dev/null || echo "0")
        i=$(echo "$line" | grep -oP 'issues=\K[0-9]+' 2>/dev/null || echo "0")
        t=$(echo "$line" | grep -oP 'tests_ok=\K[0-9]+' 2>/dev/null || echo "0")
        total_fixes=$((total_fixes + f))
        total_issues=$((total_issues + i))
        phases_tested=$((phases_tested + t))
    done < "$scorecard_file"

    {
        echo ""
        echo "## 审计评分"
        echo "- 总修复数: ${total_fixes}"
        echo "- 发现问题数: ${total_issues}"
        echo "- 测试通过阶段: ${phases_tested}"
    } >> "${SUMMARY_FILE}"

    log INFO "审计评分: 修复 ${total_fixes} 项, 发现 ${total_issues} 项问题"
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
# 审计报告生成（兼容 AI Bridge 格式）
# ============================================================

# 生成 health-score.json（机器可读的健康评分）
generate_health_score() {
    local phases_completed="$1"
    local phases_total="$2"
    local total_commits="$3"

    local score=100
    local deductions=""

    # 扣分项1: 未完成的阶段（每个 -5 分）
    local incomplete=$((phases_total - phases_completed))
    if [[ $incomplete -gt 0 ]]; then
        local deduct=$((incomplete * 5))
        score=$((score - deduct))
        deductions="${deductions}\n    {\"reason\": \"${incomplete} 个审计阶段未完成\", \"points\": -${deduct}},"
    fi

    # 扣分项2: 测试结果（检查最近的测试输出）
    local test_failures=0
    local latest_phase_log=""
    for p in $(seq 1 "$phases_total"); do
        local plog="${LOG_DIR}/${DATE}_phase${p}_run1.log"
        if [[ -f "$plog" ]]; then
            latest_phase_log="$plog"
            local fails
            fails=$(grep -oP '\d+(?= failed)' "$plog" 2>/dev/null | tail -1 || echo "0")
            if [[ -n "$fails" && "$fails" -gt 0 ]]; then
                test_failures=$((test_failures + fails))
            fi
        fi
    done
    if [[ $test_failures -gt 0 ]]; then
        score=$((score - 30))
        deductions="${deductions}\n    {\"reason\": \"测试有 ${test_failures} 个失败\", \"points\": -30},"
    fi

    # 扣分项3: 未提交的改动
    local uncommitted=0
    uncommitted=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$uncommitted" -gt 0 ]]; then
        score=$((score - 10))
        deductions="${deductions}\n    {\"reason\": \"有 ${uncommitted} 个未提交的改动\", \"points\": -10},"
    fi

    # 确保分数不低于 0
    if [[ $score -lt 0 ]]; then score=0; fi

    # 评级
    local grade="需要关注"
    if [[ $score -ge 90 ]]; then grade="优秀"
    elif [[ $score -ge 75 ]]; then grade="良好"
    elif [[ $score -ge 60 ]]; then grade="及格"
    fi

    # 去掉最后一个逗号
    deductions=$(echo -e "$deductions" | sed '$ s/,$//')

    # 写入 JSON
    local score_file="${LOG_DIR}/${DATE}.health-score.json"
    cat > "$score_file" << SCORE_JSON
{
    "date": "${DATE}",
    "score": ${score},
    "grade": "${grade}",
    "max_score": 100,
    "project": "OpenClaw Bot",
    "phases_completed": ${phases_completed},
    "phases_total": ${phases_total},
    "commits": ${total_commits},
    "deductions": [${deductions}
    ]
}
SCORE_JSON

    log INFO "健康评分: ${score}/100 (${grade})" >&2

    # 返回评分供后续使用（通过 stdout）
    echo "${score}|${grade}"
}

# 生成回归对比报告（与上次审计对比）
generate_regression_report() {
    local current_score="$1"
    local current_grade="$2"
    local regression_file="${LOG_DIR}/${DATE}.regression.md"

    # 查找上次的评分
    local last_score_file="${LOG_DIR}/last-health-score.json"
    local last_score=""
    local last_grade=""
    local last_date=""

    if [[ -f "$last_score_file" ]]; then
        last_score=$(grep -oP '"score":\s*\K[0-9]+' "$last_score_file" 2>/dev/null || echo "")
        last_grade=$(grep -oP '"grade":\s*"\K[^"]+' "$last_score_file" 2>/dev/null || echo "")
        last_date=$(grep -oP '"date":\s*"\K[^"]+' "$last_score_file" 2>/dev/null || echo "")
    fi

    {
        echo "# 与上次审计对比"
        echo ""
        if [[ -n "$last_score" ]]; then
            local diff=$((current_score - last_score))
            local trend=""
            if [[ $diff -gt 0 ]]; then
                trend="项目在变好 (+${diff}分)"
            elif [[ $diff -lt 0 ]]; then
                trend="项目出现退步，请关注 (${diff}分)"
            else
                trend="保持稳定"
            fi
            echo "- 上次评分（${last_date}）：${last_score} 分（${last_grade}）"
            echo "- 本次评分：${current_score} 分（${current_grade}）"
            echo "- 变化：$(if [[ $diff -ge 0 ]]; then echo "+${diff}"; else echo "${diff}"; fi) 分"
            echo "- 趋势：${trend}"
        else
            echo "- 本次评分：${current_score} 分（${current_grade}）"
            echo "- 趋势：首次审计，无历史数据对比"
        fi
    } > "$regression_file"

    # 保存本次评分供下次对比
    cp "${LOG_DIR}/${DATE}.health-score.json" "$last_score_file" 2>/dev/null || true

    log INFO "回归对比报告已生成: ${regression_file}"
}

# 生成富格式审计摘要（AI Bridge 风格）
generate_rich_summary() {
    local phases_completed="$1"
    local phases_total="$2"
    local total_commits="$3"
    local score="$4"
    local grade="$5"
    local git_hash="$6"
    local git_hash_end="$7"

    local rich_summary="${LOG_DIR}/${DATE}.summary.md"

    {
        echo "# OpenClaw Bot 夜间审计报告"
        echo ""
        echo "> 这是 AI 工程师昨晚值班的工作汇报，打开即可了解项目状态。"
        echo ""
        echo "- **日期**: ${DATE}"
        echo "- **结束时间**: $(TZ=Asia/Shanghai date '+%H:%M:%S')"
        echo "- **预估花费**: \$${TOTAL_SPENT}（上限 \$${MAX_TOTAL_BUDGET:-35}）"
        echo "- **项目健康评分**: ${score}/100（${grade}）"
        echo ""

        # 各阶段完成情况
        echo "## 昨晚干了什么"
        for phase_num in $(seq "$START_PHASE" "$END_PHASE"); do
            local p_name
            p_name=$(get_phase_name "$phase_num")
            if grep -q "phase${phase_num}_done=" "$PROGRESS_FILE" 2>/dev/null; then
                local done_time
                done_time=$(grep "phase${phase_num}_done=" "$PROGRESS_FILE" | cut -d= -f2)
                echo "- [x] **${p_name}** — 搞定了（${done_time}）"
            elif grep -q "phase${phase_num}_start=" "$PROGRESS_FILE" 2>/dev/null; then
                echo "- [ ] **${p_name}** — 做了一半没做完"
            else
                echo "- [ ] **${p_name}** — 没来得及做"
            fi
        done
        echo ""

        # 回归对比
        local regression_file="${LOG_DIR}/${DATE}.regression.md"
        if [[ -f "$regression_file" ]]; then
            cat "$regression_file"
            echo ""
        fi

        # Git 改动
        echo "## 改了哪些东西"
        echo ""
        echo "> 下面是昨晚每次修改的一句话摘要（最新的在最上面）："
        echo ""
        if [[ "$total_commits" -gt 0 ]]; then
            git log --oneline "${git_hash}..${git_hash_end}" 2>/dev/null | head -20 || echo "（无法获取 git log）"
        else
            echo "（没有代码变更）"
        fi
        echo ""

        # 需要老板看的
        echo "## 需要你看一眼的事"
        echo ""
        echo "> 以下是 AI 搞不定、需要你（老板）拍板的事："
        echo ""
        echo "- 界面好不好看 → 只有你能判断"
        echo "- 其他技术问题 → AI 已经全部处理了"
        echo ""
        echo "---"
        echo "*本报告由 OpenClaw Bot 夜间审计系统 v2.0 自动生成*"
    } > "$rich_summary"

    log INFO "富格式摘要已生成: ${rich_summary}"
}

# 读取单个兄弟项目的审计评分
# 参数: 项目名称 日志目录
# 支持两种评分文件格式:
#   - health-score.json (AI Bridge 格式)
#   - YYYY-MM-DD.health-score.json (OpenClaw 格式)
read_project_score() {
    local project_name="$1"
    local audit_dir="$2"

    # 尝试多种评分文件路径
    local score_file=""
    local candidates=(
        "${audit_dir}/${DATE}/health-score.json"
        "${audit_dir}/${DATE}.health-score.json"
        "${audit_dir}/health-score.json"
    )
    for f in "${candidates[@]}"; do
        if [[ -f "$f" ]]; then
            score_file="$f"
            break
        fi
    done

    if [[ -z "$score_file" ]]; then
        # 没有评分 JSON，尝试从 summary.md 推断完成状态
        local summary_candidates=(
            "${audit_dir}/${DATE}/summary.md"
            "${audit_dir}/${DATE}.summary"
            "${audit_dir}/${DATE}.summary.md"
        )
        for s in "${summary_candidates[@]}"; do
            if [[ -f "$s" ]]; then
                echo "${project_name}|有报告|--"
                return 0
            fi
        done
        return 1
    fi

    # macOS grep 不支持 -P, 用 sed 替代
    local b_score b_grade
    b_score=$(sed -n 's/.*"score"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$score_file" 2>/dev/null | head -1)
    b_grade=$(sed -n 's/.*"grade"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$score_file" 2>/dev/null | head -1)

    if [[ -n "$b_score" ]]; then
        echo "${project_name}|${b_score}|${b_grade}"
        return 0
    fi
    return 1
}

# 收集所有兄弟项目的审计结果
# 返回格式: 每行一个 "项目名|分数|评级"
collect_all_project_scores() {
    local results=""

    # 从配置的项目列表中读取
    # SIBLING_PROJECTS 格式: "项目名:日志目录;项目名:日志目录;..."
    local projects="${SIBLING_PROJECTS:-}"

    # 兼容旧配置: 如果只配了 AI_BRIDGE_AUDIT_DIR，自动加入
    if [[ -z "$projects" && -n "${AI_BRIDGE_AUDIT_DIR:-}" ]]; then
        projects="AI Bridge:${AI_BRIDGE_AUDIT_DIR}"
    fi

    if [[ -z "$projects" ]]; then
        return
    fi

    # 解析项目列表（分号分隔）
    local IFS_BAK="$IFS"
    IFS=";"
    for entry in $projects; do
        IFS="$IFS_BAK"
        local name dir
        name=$(echo "$entry" | cut -d':' -f1 | xargs)
        dir=$(echo "$entry" | cut -d':' -f2- | xargs)

        if [[ -z "$name" || -z "$dir" ]]; then continue; fi
        if [[ ! -d "$dir" ]]; then continue; fi

        local result
        result=$(read_project_score "$name" "$dir" 2>/dev/null || echo "")
        if [[ -n "$result" ]]; then
            results="${results}${result}\n"
        fi
    done
    IFS="$IFS_BAK"

    echo -e "$results"
}

# ============================================================
# 阶段执行引擎
# ============================================================

run_phase() {
    local phase_num="$1"
    local phase_file="$2"
    local phase_name="$3"

    log PHASE "========== 阶段 ${phase_num}/${TOTAL_PHASES:-8}: ${phase_name} =========="

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

    # 增量审计模式: 注入变更文件列表
    prompt=$(build_incremental_prompt "$prompt")

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

        # 执行 Claude Code（--bare 加速启动 + 注入自主决策指令和项目规范）
        local session_id
        session_id=$(uuidgen 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())")
        local directive_file="${SCRIPT_DIR}/autonomous-directive.txt"
        local agents_file="${PROJECT_DIR}/AGENTS.md"

        "${CLAUDE_BIN:-claude}" \
            -p "$prompt" \
            --bare \
            --dangerously-skip-permissions \
            --append-system-prompt-file "$directive_file" \
            --append-system-prompt-file "$agents_file" \
            --max-budget-usd "${BUDGET_PER_PHASE:-5}" \
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
                --append-system-prompt-file "$directive_file" \
                --append-system-prompt-file "$agents_file" \
                --max-budget-usd "${BUDGET_PER_PHASE:-5}" \
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

    # 评分卡: 记录本阶段的修复/问题/测试状态
    generate_phase_scorecard "$phase_num" "$phase_name" "$run_log"

    # 变更量检查: 单阶段改太多文件则告警
    check_change_volume "$phase_num" "$phase_name"

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
    log INFO "进程锁已获取 (项目标识: ${PROJECT_HASH})"

    # 健康预检（确认环境可用后再继续）
    if ! preflight_check; then
        exit 1
    fi

    # 清理旧日志
    cleanup_old_logs

    # 断点续跑检测（如果上次审计中断，自动从断点继续）
    detect_resume_point

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

    # === 补跑模式检测 ===
    # 如果当前时间已超过 END_HOUR_CST（正常审计窗口已过），
    # 但今天还没有完成任何审计阶段，说明审计被系统延迟了（如 macOS provenance 拦截）
    # 此时启用补跑模式，允许最多运行 FORCE_RUN_MAX_MINUTES 分钟
    local normal_remaining
    normal_remaining=$(get_remaining_minutes)
    if [[ $normal_remaining -eq 0 ]]; then
        # 检查今天是否已经有完成的阶段
        local has_completed_phase=false
        if [[ -f "$PROGRESS_FILE" ]]; then
            for _p in $(seq 1 "${TOTAL_PHASES:-8}"); do
                if grep -q "phase${_p}_done=" "$PROGRESS_FILE" 2>/dev/null; then
                    has_completed_phase=true
                    break
                fi
            done
        fi

        if [[ "$has_completed_phase" == "false" ]]; then
            FORCE_RUN=true
            FORCE_RUN_START_TS=$(date +%s)
            echo "force_run=true" >> "$PROGRESS_FILE"
            echo "force_run_reason=审计被延迟触发，当前已超过正常窗口(CST ${END_HOUR_CST}:00)" >> "$PROGRESS_FILE"
            log WARN "========================================="
            log WARN " ⚠️ 补跑模式启用"
            log WARN " 原因: 审计被延迟触发，当前中国时间已超过 ${END_HOUR_CST}:00"
            log WARN " 今日尚无任何审计阶段完成，自动进入补跑模式"
            log WARN " 补跑时间上限: ${FORCE_RUN_MAX_MINUTES} 分钟"
            log WARN "========================================="
        fi
    fi

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
    # 索引 0 占位，1-8 对应阶段编号
    local phase_names_list="_ 安全审计 后端稳定性 API与集成 前端与UI 架构与运维 文件治理与文档 数据库与交易 端到端与可观测"
    local phase_files_list="_ 01-security.txt 02-backend.txt 03-api-integration.txt 04-frontend-ui.txt 05-architecture-ops.txt 06-governance-docs.txt 07-data-trading.txt 08-e2e-observability.txt"

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
        # 打审计完成标记（用于增量审计的基准点）
        git tag "nightly-audit-${DATE}" 2>/dev/null || true

        log INFO "推送代码到远程仓库..."
        git push "${GIT_REMOTE:-origin}" "${GIT_BRANCH:-main}" 2>&1 | while read -r line; do
            log INFO "  git: $line"
        done || {
            log WARN "git push 失败，可能需要手动推送"
        }
        # 推送标签
        git push "${GIT_REMOTE:-origin}" "nightly-audit-${DATE}" 2>/dev/null || true
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

    # 追加审计评分到摘要
    generate_final_scorecard

    # === 生成健康评分 JSON ===
    local score_result
    score_result=$(generate_health_score "$phases_completed" "$END_PHASE" "$total_commits")
    local health_score health_grade
    health_score=$(echo "$score_result" | cut -d'|' -f1)
    health_grade=$(echo "$score_result" | cut -d'|' -f2)

    # === 生成回归对比报告 ===
    generate_regression_report "$health_score" "$health_grade"

    # === 生成富格式摘要 ===
    generate_rich_summary "$phases_completed" "$END_PHASE" "$total_commits" "$health_score" "$health_grade" "$git_hash" "$git_hash_end"

    cat "$SUMMARY_FILE"

    log INFO "========================================="
    log INFO " 夜间审计结束"
    log INFO " 完成: ${phases_completed}  跳过: ${phases_skipped}  失败: ${phases_failed}"
    log INFO " 产生 ${total_commits} 个 commit"
    log INFO " 健康评分: ${health_score}/100 (${health_grade})"
    log INFO " 日志目录: ${LOG_DIR}/"
    log INFO "========================================="

    # === 构建通知内容 ===
    local notify_body="🤖 *OpenClaw Bot 夜间审计完成*

📅 日期: ${DATE}
🏥 健康评分: ${health_score}/100（${health_grade}）"

    # 附加回归趋势
    local last_score_file="${LOG_DIR}/last-health-score.json"
    # 注意: last-health-score.json 此时已被覆盖为本次分数
    # 从 regression.md 中提取趋势
    local regression_file="${LOG_DIR}/${DATE}.regression.md"
    if [[ -f "$regression_file" ]]; then
        local trend_line
        trend_line=$(grep "趋势：" "$regression_file" 2>/dev/null | head -1 | sed 's/.*趋势：//' || echo "")
        if [[ -n "$trend_line" ]]; then
            notify_body="${notify_body}
📈 趋势: ${trend_line}"
        fi
    fi

    notify_body="${notify_body}
✅ 完成: ${phases_completed}/${TOTAL_PHASES:-8} 阶段
📝 产生: ${total_commits} 个 commit
💰 预估花费: \$${TOTAL_SPENT}"

    # 附加所有兄弟项目的审计结果
    local sibling_scores
    sibling_scores=$(collect_all_project_scores 2>/dev/null || echo "")
    if [[ -n "$sibling_scores" ]]; then
        notify_body="${notify_body}

📊 *其他项目体检结果:*"
        while IFS= read -r line; do
            if [[ -z "$line" ]]; then continue; fi
            local p_name p_score p_grade
            p_name=$(echo "$line" | cut -d'|' -f1)
            p_score=$(echo "$line" | cut -d'|' -f2)
            p_grade=$(echo "$line" | cut -d'|' -f3)
            if [[ "$p_score" == "有报告" ]]; then
                notify_body="${notify_body}
  ${p_name}: 有审计报告（无评分）"
            elif [[ -n "$p_score" && "$p_score" != "--" ]]; then
                notify_body="${notify_body}
  ${p_name}: ${p_score}/100（${p_grade}）"
            fi
        done <<< "$sibling_scores"
    fi

    notify_body="${notify_body}

详情: ${LOG_DIR}/${DATE}.summary.md"

    # === 发送通知（旧版单项目通知，保留兼容）===
    send_notification "$notify_body"

    # === 触发统一通知服务（Qwen AI 全项目日报）===
    local unified_script="${SCRIPT_DIR}/unified-notifier.sh"
    if [[ -f "$unified_script" && -n "${QWEN_API_KEY:-}" ]]; then
        log INFO "触发统一通知服务..."
        bash "$unified_script" "$DATE" &>/dev/null &
        log INFO "统一通知服务已在后台启动"
    fi

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
