#!/usr/bin/env bash
# ============================================================
# 统一夜间审计通知服务
# 功能：扫描所有项目的审计结果 → Qwen AI 生成日报 → Telegram 推送
# 与各项目审计系统完全解耦，只读取审计产出物
# ============================================================
set -euo pipefail

# === 脚本所在目录 ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# === 加载配置 ===
CONFIG_FILE="${SCRIPT_DIR}/config.env"
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "[FATAL] 配置文件不存在: ${CONFIG_FILE}" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$CONFIG_FILE"

# === 常量 ===
# 参数解析：支持 --dry-run 和指定日期，顺序不限
DRY_RUN="false"
CUSTOM_DATE=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN="true" ;;
        *) CUSTOM_DATE="$arg" ;;
    esac
done
DATE="${CUSTOM_DATE:-$(date +%Y-%m-%d)}"
DATE8="$(echo "$DATE" | tr -d '-')"
PROJECTS_CONF="${SCRIPT_DIR}/projects.conf"
PROMPT_FILE="${SCRIPT_DIR}/unified-prompt.md"
LOG_DIR="${SCRIPT_DIR}/logs"
NOTIFY_LOG="${LOG_DIR}/${DATE}.unified-notify.log"

# === Qwen API 配置（从 config.env 读取）===
QWEN_API_URL="${QWEN_API_URL:-https://api.siliconflow.cn/v1/chat/completions}"
QWEN_API_KEY="${QWEN_API_KEY:-}"
QWEN_MODEL="${QWEN_MODEL:-Qwen/Qwen3-235B-A22B-Instruct-2507}"

# === Telegram 配置（复用审计系统的配置）===
TG_BOT_TOKEN="${NOTIFY_TG_BOT_TOKEN:-}"
TG_CHAT_ID="${NOTIFY_TG_CHAT_ID:-}"

# === 日志函数 ===
log() {
    local level="$1"; shift
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[${ts}] [${level}] $*" | tee -a "$NOTIFY_LOG"
}

# ============================================================
# 收集单个项目的审计数据
# 参数: 项目名  日志目录  评分文件模式  摘要文件模式
# 输出: 结构化文本块
# ============================================================
collect_project_data() {
    local name="$1"
    local log_dir="$2"
    local score_pattern="$3"
    local summary_pattern="$4"

    # 替换日期变量
    local score_path summary_path
    score_path="$(echo "$score_pattern" | sed "s|{DATE}|${DATE}|g; s|{DATE8}|${DATE8}|g")"
    summary_path="$(echo "$summary_pattern" | sed "s|{DATE}|${DATE}|g; s|{DATE8}|${DATE8}|g")"

    local result=""
    result+="### ${name}\n"

    # 读取评分
    if [[ "$score_pattern" != "none" ]]; then
        local full_score_path="${log_dir}/${score_path}"
        if [[ -f "$full_score_path" ]]; then
            local score grade phases_done phases_total commits deductions
            score=$(sed -n 's/.*"score"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$full_score_path" 2>/dev/null | head -1)
            grade=$(sed -n 's/.*"grade"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$full_score_path" 2>/dev/null | head -1)
            phases_done=$(sed -n 's/.*"phases_completed"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$full_score_path" 2>/dev/null | head -1)
            phases_total=$(sed -n 's/.*"phases_total"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$full_score_path" 2>/dev/null | head -1)
            commits=$(sed -n 's/.*"commits"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$full_score_path" 2>/dev/null | head -1)
            # 提取扣分原因列表
            deductions=$(sed -n 's/.*"reason"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/  - \1/p' "$full_score_path" 2>/dev/null || echo "")

            result+="评分: ${score:-?}/100（${grade:-未知}）\n"
            result+="完成阶段: ${phases_done:-?}/${phases_total:-?}\n"
            result+="代码提交: ${commits:-0} 个\n"
            if [[ -n "$deductions" ]]; then
                result+="扣分项:\n${deductions}\n"
            fi
        else
            result+="评分: 无评分文件（${full_score_path} 不存在）\n"
        fi
    else
        result+="评分: 该项目暂无自动评分机制\n"
    fi

    # 读取摘要（取前 40 行，避免过长）
    local full_summary_path="${log_dir}/${summary_path}"
    if [[ -f "$full_summary_path" ]]; then
        local summary_content
        summary_content=$(head -40 "$full_summary_path" 2>/dev/null || echo "（读取失败）")
        result+="摘要内容:\n${summary_content}\n"
    else
        result+="摘要: 无摘要文件（${full_summary_path} 不存在）\n"
    fi

    # 检查回归报告（如果有的话）
    local regression_candidates=(
        "${log_dir}/${DATE}/regression.md"
        "${log_dir}/${DATE}.regression.md"
    )
    for rf in "${regression_candidates[@]}"; do
        if [[ -f "$rf" ]]; then
            local regression_content
            regression_content=$(head -20 "$rf" 2>/dev/null || echo "")
            if [[ -n "$regression_content" ]]; then
                result+="回归对比:\n${regression_content}\n"
            fi
            break
        fi
    done

    result+="\n---\n"
    echo -e "$result"
}

# ============================================================
# 收集所有项目数据
# ============================================================
collect_all_data() {
    local all_data=""

    if [[ ! -f "$PROJECTS_CONF" ]]; then
        log "ERROR" "项目配置文件不存在: ${PROJECTS_CONF}"
        return 1
    fi

    while IFS= read -r line; do
        # 跳过注释和空行
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$(echo "$line" | tr -d '[:space:]')" ]] && continue

        local name log_dir score_pattern summary_pattern
        name="$(echo "$line" | cut -d'|' -f1)"
        log_dir="$(echo "$line" | cut -d'|' -f2)"
        score_pattern="$(echo "$line" | cut -d'|' -f3)"
        summary_pattern="$(echo "$line" | cut -d'|' -f4)"

        if [[ -z "$name" ]]; then continue; fi

        log "INFO" "收集项目数据: ${name}"

        if [[ ! -d "$log_dir" ]]; then
            all_data+="### ${name}\n状态: ⚠️ 日志目录不存在（${log_dir}）\n\n---\n\n"
            log "WARN" "  日志目录不存在: ${log_dir}"
            continue
        fi

        local project_data
        project_data=$(collect_project_data "$name" "$log_dir" "$score_pattern" "$summary_pattern")
        all_data+="${project_data}\n"
        log "INFO" "  数据收集完成"
    done < "$PROJECTS_CONF"

    echo -e "$all_data"
}

# ============================================================
# 调用 Qwen AI 生成通知
# 参数: 审计数据文本
# 输出: AI 生成的通知正文
# ============================================================
call_qwen_ai() {
    local audit_data="$1"

    if [[ -z "$QWEN_API_KEY" ]]; then
        log "ERROR" "QWEN_API_KEY 未配置"
        return 1
    fi

    # 读取提示词模板
    if [[ ! -f "$PROMPT_FILE" ]]; then
        log "ERROR" "提示词文件不存在: ${PROMPT_FILE}"
        return 1
    fi

    local prompt_template
    prompt_template=$(cat "$PROMPT_FILE")

    # 将 {{AUDIT_DATA}} 替换为实际数据, {{DATE}} 替换为日期
    local full_prompt
    full_prompt=$(echo "$prompt_template" | sed "s|{{DATE}}|${DATE}|g")

    # 构建 JSON 请求体（用 python 来安全处理特殊字符）
    local request_body
    request_body=$(python3 -c "
import json, sys

prompt = sys.stdin.read()
audit_data = '''${audit_data}'''

# 将审计数据插入提示词
full_prompt = prompt.replace('{{AUDIT_DATA}}', audit_data)

body = {
    'model': '${QWEN_MODEL}',
    'messages': [
        {'role': 'system', 'content': '你是一个专业的项目审计通知生成器。只输出通知正文，不要输出任何其他内容。'},
        {'role': 'user', 'content': full_prompt}
    ],
    'max_tokens': 3000,
    'temperature': 0.3,
    'extra_body': {'enable_thinking': False}
}
print(json.dumps(body, ensure_ascii=False))
" <<< "$full_prompt" 2>/dev/null)

    if [[ -z "$request_body" ]]; then
        log "ERROR" "构建请求体失败"
        return 1
    fi

    log "INFO" "调用 Qwen AI 生成通知..."

    local response
    response=$(curl -s --max-time 60 -X POST "$QWEN_API_URL" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${QWEN_API_KEY}" \
        -d "$request_body" 2>/dev/null)

    if [[ -z "$response" ]]; then
        log "ERROR" "Qwen API 无响应"
        return 1
    fi

    # 提取生成的文本
    local ai_text
    ai_text=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    content = data['choices'][0]['message']['content']
    # 去掉思考过程（如果有 <think> 标签）
    import re
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    # 去掉 markdown 代码块标记（AI 有时会包裹在 \`\`\` 里）
    content = re.sub(r'^\`\`\`[a-z]*\n?', '', content)
    content = re.sub(r'\n?\`\`\`\s*$', '', content)
    content = content.strip()
    print(content)
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" <<< "$response" 2>/dev/null)

    if [[ -z "$ai_text" ]]; then
        log "ERROR" "Qwen AI 返回内容为空"
        log "ERROR" "原始响应: $(echo "$response" | head -5)"
        return 1
    fi

    echo "$ai_text"
}

# ============================================================
# 生成降级通知（Qwen 不可用时的纯模板方案）
# 参数: 审计数据文本
# ============================================================
generate_fallback_notification() {
    local audit_data="$1"

    local notify_body="📋 全项目夜间审计日报
📅 ${DATE}

━━━━━━━━━━━━━━━━━━"

    # 逐项目解析评分
    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$(echo "$line" | tr -d '[:space:]')" ]] && continue

        local name log_dir score_pattern
        name="$(echo "$line" | cut -d'|' -f1)"
        log_dir="$(echo "$line" | cut -d'|' -f2)"
        score_pattern="$(echo "$line" | cut -d'|' -f3)"

        if [[ -z "$name" ]]; then continue; fi

        notify_body+="

🏷 ${name}"

        if [[ "$score_pattern" == "none" ]]; then
            # 无评分的项目
            local summary_pattern
            summary_pattern="$(echo "$line" | cut -d'|' -f4)"
            local sp
            sp="$(echo "$summary_pattern" | sed "s|{DATE}|${DATE}|g; s|{DATE8}|${DATE8}|g")"
            if [[ -f "${log_dir}/${sp}" ]]; then
                notify_body+="
📊 状态：有审计报告（暂无评分）"
            else
                notify_body+="
⚠️ 状态：今晚未运行"
            fi
        else
            # 有评分的项目
            local sp
            sp="$(echo "$score_pattern" | sed "s|{DATE}|${DATE}|g; s|{DATE8}|${DATE8}|g")"
            local full_path="${log_dir}/${sp}"
            if [[ -f "$full_path" ]]; then
                local score grade
                score=$(sed -n 's/.*"score"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' "$full_path" 2>/dev/null | head -1)
                grade=$(sed -n 's/.*"grade"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$full_path" 2>/dev/null | head -1)
                notify_body+="
📊 健康评分：${score:-?}/100（${grade:-未知}）"
            else
                notify_body+="
⚠️ 状态：今晚未运行"
            fi
        fi

        notify_body+="
━━━━━━━━━━━━━━━━━━"
    done < "$PROJECTS_CONF"

    notify_body+="

（注：AI 通知服务暂时不可用，本条为简化模板）"

    echo "$notify_body"
}

# ============================================================
# 发送 Telegram 消息
# 参数: 消息文本
# ============================================================
send_telegram() {
    local message="$1"

    if [[ -z "$TG_BOT_TOKEN" || -z "$TG_CHAT_ID" ]]; then
        log "WARN" "Telegram 未配置，跳过发送"
        echo "$message"
        return 0
    fi

    # Telegram 单条消息上限 4096 字符，超长则截断
    if [[ ${#message} -gt 4000 ]]; then
        log "WARN" "消息超长(${#message}字符)，截断至 4000"
        message="${message:0:3990}

...（消息过长已截断）"
    fi

    local response
    response=$(curl -s --max-time 15 -X POST \
        "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TG_CHAT_ID}" \
        --data-urlencode "text=${message}" \
        2>/dev/null)

    local ok
    ok=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print('true' if data.get('ok') else 'false')
except:
    print('false')
" <<< "$response" 2>/dev/null)

    if [[ "$ok" == "true" ]]; then
        log "INFO" "Telegram 通知发送成功"
    else
        log "ERROR" "Telegram 发送失败: $(echo "$response" | head -3)"
        return 1
    fi
}

# ============================================================
# 主流程
# ============================================================
main() {
    mkdir -p "$LOG_DIR"

    log "INFO" "========================================"
    log "INFO" " 统一夜间审计通知服务"
    log "INFO" " 日期: ${DATE}"
    log "INFO" "========================================"

    # --- 检查模式 ---
    if [[ "$DRY_RUN" == "true" ]]; then
        log "INFO" "⚡ 试运行模式 — 不会实际发送 Telegram"
    fi

    # --- 收集所有项目数据 ---
    log "INFO" "开始收集各项目审计数据..."
    local audit_data
    audit_data=$(collect_all_data)

    if [[ -z "$audit_data" ]]; then
        log "WARN" "所有项目均无审计数据，跳过通知"
        return 0
    fi

    # 保存收集到的原始数据
    echo -e "$audit_data" > "${LOG_DIR}/${DATE}.unified-raw.md"
    log "INFO" "原始数据已保存: ${LOG_DIR}/${DATE}.unified-raw.md"

    # --- 生成通知 ---
    local notification=""

    if [[ -n "$QWEN_API_KEY" ]]; then
        # 优先用 Qwen AI 生成
        notification=$(call_qwen_ai "$audit_data" 2>/dev/null || echo "")
    fi

    if [[ -z "$notification" ]]; then
        # Qwen 不可用时降级到模板
        log "WARN" "Qwen AI 不可用，使用降级模板"
        notification=$(generate_fallback_notification "$audit_data")
    fi

    # 保存生成的通知内容
    echo "$notification" > "${LOG_DIR}/${DATE}.unified-notify.md"
    log "INFO" "通知内容已保存: ${LOG_DIR}/${DATE}.unified-notify.md"

    # --- 发送 ---
    if [[ "$DRY_RUN" == "true" ]]; then
        log "INFO" "=== 预览通知内容 ==="
        echo ""
        echo "$notification"
        echo ""
        log "INFO" "=== 预览结束 ==="
    else
        send_telegram "$notification"
    fi

    log "INFO" "统一通知服务完成"
}

main "$@"
