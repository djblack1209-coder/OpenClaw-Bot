#!/usr/bin/env bash
# OpenEverything 自动健康检查：只读巡检，不重启、不写生产数据。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JSON_MODE=0
[[ "${1:-}" == "--json" ]] && JSON_MODE=1

load_env() {
  local env_file="$ROOT_DIR/packages/clawbot/config/.env"
  [[ -f "$env_file" ]] || return 0
  local line key value
  while IFS= read -r line; do
    line="${line#export }"
    key="${line%%=*}"
    value="${line#*=}"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%'}"
    value="${value#'}"
    case "$key" in
      OPENCLAW_API_TOKEN|G4F_ENABLED|KIRO_GATEWAY_ENABLED|OLLAMA_ENABLED|IBKR_ENABLED|IBKR_PORT|HEARTBEAT_SENDER_ENABLED)
        export "$key=$value"
        ;;
    esac
  done < <(grep -E '^(export[[:space:]]+)?(OPENCLAW_API_TOKEN|G4F_ENABLED|KIRO_GATEWAY_ENABLED|OLLAMA_ENABLED|IBKR_ENABLED|IBKR_PORT|HEARTBEAT_SENDER_ENABLED)=' "$env_file" || true)
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip(), ensure_ascii=False))'
}

CHECKS=()
add_check() {
  local name="$1" status="$2" detail="$3" fix="$4"
  CHECKS+=("$name|$status|$detail|$fix")
}

http_code() {
  local url="$1"
  curl -L -sS -o /dev/null -w '%{http_code}' --max-time 8 "$url" 2>/dev/null || echo "000"
}

feature_enabled() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

launchagent_report() {
  launchctl print "gui/$UID/$1" 2>/dev/null
}

check_required_launchagent() {
  local label="$1" report state pid last_exit
  if ! report="$(launchagent_report "$label")"; then
    add_check "launchagent:$label" "bad" "$label 未加载" "重新部署并启动该必需服务"
    return
  fi
  state="$(printf '%s\n' "$report" | sed -n 's/^[[:space:]]*state = //p' | head -1)"
  pid="$(printf '%s\n' "$report" | sed -n 's/^[[:space:]]*pid = //p' | head -1)"
  last_exit="$(printf '%s\n' "$report" | sed -n 's/^[[:space:]]*last exit code = //p' | head -1)"
  if [[ "$state" == "running" && "$pid" =~ ^[0-9]+$ ]]; then
    add_check "launchagent:$label" "ok" "$label 正在运行 (PID $pid)" "无需处理"
  else
    add_check "launchagent:$label" "bad" "$label 未运行 (state=${state:-unknown}, exit=${last_exit:-unknown})" "检查对应 stderr 日志并重新启动"
  fi
}

check_scheduled_launchagent() {
  local label="$1" report state last_exit
  if ! report="$(launchagent_report "$label")"; then
    add_check "launchagent:$label" "bad" "$label 未加载" "重新部署该定时任务"
    return
  fi
  state="$(printf '%s\n' "$report" | sed -n 's/^[[:space:]]*state = //p' | head -1)"
  last_exit="$(printf '%s\n' "$report" | sed -n 's/^[[:space:]]*last exit code = //p' | head -1)"
  if [[ "$state" == "running" || "$last_exit" == "0" ]]; then
    add_check "launchagent:$label" "ok" "$label 已加载且最近退出正常" "无需处理"
  else
    add_check "launchagent:$label" "bad" "$label 最近执行异常 (state=${state:-unknown}, exit=${last_exit:-unknown})" "检查定时任务日志和最近触发时间"
  fi
}

check_optional_tcp_service() {
  local name="$1" enabled_value="$2" label="$3" port="$4"
  if ! feature_enabled "$enabled_value"; then
    add_check "optional:$name" "disabled" "$name 未启用" "需要该能力时先配置依赖和 ENABLED 开关"
    return
  fi
  check_required_launchagent "$label"
  if /usr/bin/nc -z -w 2 127.0.0.1 "$port" >/dev/null 2>&1; then
    add_check "endpoint:$name" "ok" "$name 监听 127.0.0.1:$port" "无需处理"
  else
    add_check "endpoint:$name" "bad" "$name 未监听 127.0.0.1:$port" "检查依赖、凭据和服务日志"
  fi
}

load_env

# 核心守护进程必须同时满足 launchd 正在运行和真实端点可用。
check_required_launchagent "ai.openclaw.clawbot-agent"
check_required_launchagent "ai.openclaw.gateway"
check_required_launchagent "ai.openclaw.xianyu"
check_required_launchagent "ai.openclaw.intel-brief.telegram-listener"
check_required_launchagent "ai.openclaw.cc-seller-bridge"
check_scheduled_launchagent "ai.openclaw.intel-brief.scheduler"

# 每日资讯不能只看 launchd 退出码，还要检查中央来源、offset 证据和磁盘增长。
intel_python="$ROOT_DIR/packages/clawbot/.venv312/bin/python"
intel_health_script="$ROOT_DIR/packages/clawbot/scripts/intel_runtime_health.py"
if [[ -x "$intel_python" && -f "$intel_health_script" ]]; then
  intel_health_output="$($intel_python "$intel_health_script" 2>/dev/null || true)"
  intel_health_status="$(printf '%s' "$intel_health_output" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", "bad"))' 2>/dev/null || echo bad)"
  intel_health_detail="$(printf '%s' "$intel_health_output" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d.get("source_health",{}); l=d.get("listener",{}); print(f"来源 {s.get('"'"'coverage'"'"',0)}/{s.get('"'"'expected'"'"',6)}，listener {l.get('"'"'event_file_count'"'"',0)} 文件/{round(l.get('"'"'event_bytes'"'"',0)/1048576,1)}MB")' 2>/dev/null || echo "运行健康 JSON 无法解析")"
  case "$intel_health_status" in
    ok) add_check "intel_runtime" "ok" "$intel_health_detail" "无需处理" ;;
    warn) add_check "intel_runtime" "warn" "$intel_health_detail" "等待自然周期补齐来源与投递 SLI" ;;
    *) add_check "intel_runtime" "bad" "$intel_health_detail" "检查每日资讯中央库、listener heartbeat 和证据保留策略" ;;
  esac
else
  add_check "intel_runtime" "bad" "每日资讯运行健康脚本不可用" "恢复 .venv312 和 intel_runtime_health.py"
fi

# 本机操作台：有 Token 时检查受保护接口，否则只检查页面是否打开。
if [[ -n "${OPENCLAW_API_TOKEN:-}" ]]; then
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 -H "X-API-Token: ${OPENCLAW_API_TOKEN}" "http://127.0.0.1:18800/api/status" 2>/dev/null || echo "000")
else
  code=$(http_code "http://127.0.0.1:18800/dashboard")
fi
if [[ "$code" == "200" ]]; then
  add_check "local_console" "ok" "本机控制台 HTTP $code" "无需处理"
else
  add_check "local_console" "bad" "本机控制台不可用 HTTP $code" "运行 scripts/auto_recovery.sh --dry-run，确认后再去掉 --dry-run"
fi

if [[ -n "${OPENCLAW_API_TOKEN:-}" ]]; then
  bot_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 -H "X-API-Token: ${OPENCLAW_API_TOKEN}" "http://127.0.0.1:18790/api/v1/status" 2>/dev/null || echo "000")
else
  bot_code="000"
fi
if [[ "$bot_code" == "200" ]]; then
  add_check "clawbot_api" "ok" "ClawBot API HTTP 200" "无需处理"
else
  add_check "clawbot_api" "bad" "ClawBot API 鉴权健康检查失败 HTTP $bot_code" "检查 18790、OPENCLAW_API_TOKEN 和 Bot 日志"
fi

gateway_code=$(http_code "http://127.0.0.1:18789/health")
if [[ "$gateway_code" == "200" ]]; then
  add_check "gateway_api" "ok" "OpenClaw Gateway HTTP 200" "无需处理"
else
  add_check "gateway_api" "bad" "OpenClaw Gateway 健康检查失败 HTTP $gateway_code" "检查 18789 和 Gateway 日志"
fi

# CC中转生产内测巡检：复用现有只读审计脚本。
if command -v node >/dev/null 2>&1 && [[ -f "$ROOT_DIR/scripts/cc_zhongzhuan_readiness_audit.mjs" ]]; then
  audit_output=$(cd "$ROOT_DIR" && python3 - <<'PY_AUDIT' 2>/dev/null || true
import subprocess
try:
    result = subprocess.run(
        ["node", "scripts/cc_zhongzhuan_readiness_audit.mjs", "--json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    print(result.stdout)
except subprocess.TimeoutExpired:
    print('{"ok":false,"error":"readiness_audit_timeout_20s"}')
PY_AUDIT
)
  if printf '%s' "$audit_output" | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("ok") else 1)' >/dev/null 2>&1; then
    add_check "cc_readiness" "ok" "生产内测只读巡检 ok=true" "无需处理"
  elif printf '%s' "$audit_output" | grep -q 'readiness_audit_timeout_20s'; then
    add_check "cc_readiness" "warn" "生产内测巡检超过 20 秒，已自动跳过" "打开 http://127.0.0.1:18800/dashboard 查看缓存状态"
  else
    add_check "cc_readiness" "warn" "生产内测巡检未通过或无法解析" "打开 http://127.0.0.1:18800/dashboard 查看红色提示"
  fi
else
  add_check "cc_readiness" "warn" "node 或 cc_zhongzhuan_readiness_audit.mjs 不存在" "确认 Node.js 已安装"
fi

# 公网主站和渠道状态页：只看是否能打开，不输出任何密钥。
main_code=$(http_code "https://jiyu.245334.xyz/")
if [[ "$main_code" == "200" ]]; then
  add_check "public_site" "ok" "公网主站 HTTP 200" "无需处理"
else
  add_check "public_site" "bad" "公网主站 HTTP $main_code" "检查 Oracle 服务和域名 HTTPS"
fi
monitor_code=$(http_code "https://api.86gamestore.com/monitor")
if [[ "$monitor_code" =~ ^(200|401|403)$ ]]; then
  add_check "upstream_monitor" "ok" "86Game 渠道状态页可达 HTTP $monitor_code" "同步状态到看板"
else
  add_check "upstream_monitor" "warn" "86Game 渠道状态页不可达 HTTP $monitor_code" "上游可能异常；看板应显示黄色/红色"
fi

# 可选能力必须显式启用；关闭状态不算故障，启用后则必须真实可用。
check_optional_tcp_service "g4f" "${G4F_ENABLED:-false}" "ai.openclaw.g4f" "18891"
check_optional_tcp_service "kiro_gateway" "${KIRO_GATEWAY_ENABLED:-false}" "ai.openclaw.kiro-gateway" "18793"

if feature_enabled "${OLLAMA_ENABLED:-false}"; then
  if /usr/bin/nc -z -w 2 127.0.0.1 "11434" >/dev/null 2>&1; then
    add_check "optional:ollama" "ok" "Ollama 已启用且端口可达" "无需处理"
  else
    add_check "optional:ollama" "bad" "Ollama 已启用但 11434 不可达" "启动 Ollama 或关闭 OLLAMA_ENABLED"
  fi
else
  add_check "optional:ollama" "disabled" "Ollama 未启用" "确认模型库存后再显式配置"
fi

if feature_enabled "${IBKR_ENABLED:-false}"; then
  if /usr/bin/nc -z -w 2 127.0.0.1 "${IBKR_PORT:-4002}" >/dev/null 2>&1; then
    add_check "optional:ibkr" "ok" "IBKR 已启用且端口可达" "无需处理"
  else
    add_check "optional:ibkr" "bad" "IBKR 已启用但端口不可达" "启动 IB Gateway/TWS 或关闭 IBKR_ENABLED"
  fi
else
  add_check "optional:ibkr" "disabled" "IBKR 未启用" "需要实盘时再显式配置"
fi

if feature_enabled "${HEARTBEAT_SENDER_ENABLED:-false}"; then
  check_scheduled_launchagent "ai.openclaw.heartbeat-sender"
else
  add_check "optional:heartbeat_sender" "disabled" "VPS 心跳未启用" "启用主备容灾前先配置目标并做实机验收"
fi

# 磁盘空间：低于 10GB 红灯。
available_kb=$(df -k "$ROOT_DIR" | awk 'NR==2{print $4+0}')
available_gb=$((available_kb / 1024 / 1024))
if (( available_gb >= 10 )); then
  add_check "disk" "ok" "剩余 ${available_gb}GB" "无需处理"
else
  add_check "disk" "bad" "剩余 ${available_gb}GB" "运行 scripts/auto_recovery.sh 清理旧日志"
fi

if (( JSON_MODE == 1 )); then
  printf '{"ok":'
  if printf '%s\n' "${CHECKS[@]}" | grep -q '|bad|'; then printf 'false'; else printf 'true'; fi
  printf ',"release_ready":'
  if printf '%s\n' "${CHECKS[@]}" | grep -Eq '\|(bad|warn)\|'; then printf 'false'; else printf 'true'; fi
  printf ',"generated_at":'; date -u +%Y-%m-%dT%H:%M:%SZ | json_escape
  printf ',"checks":['
  first=1
  for item in "${CHECKS[@]}"; do
    IFS='|' read -r name status detail fix <<<"$item"
    (( first == 0 )) && printf ','
    first=0
    printf '{"name":%s,"status":%s,"detail":%s,"recommended_fix":%s}' \
      "$(printf '%s' "$name" | json_escape)" \
      "$(printf '%s' "$status" | json_escape)" \
      "$(printf '%s' "$detail" | json_escape)" \
      "$(printf '%s' "$fix" | json_escape)"
  done
  printf ']}'
  printf '\n'
else
  echo "OpenEverything 健康检查"
  for item in "${CHECKS[@]}"; do
    IFS='|' read -r name status detail fix <<<"$item"
    icon="🟢"; [[ "$status" == "warn" ]] && icon="🟡"; [[ "$status" == "bad" ]] && icon="🔴"
    printf '%s %s — %s\n   怎么办：%s\n' "$icon" "$name" "$detail" "$fix"
  done
fi
