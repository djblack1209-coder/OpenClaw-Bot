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
      OPENCLAW_API_TOKEN) export OPENCLAW_API_TOKEN="$value" ;;
    esac
  done < <(grep -E '^(export[[:space:]]+)?OPENCLAW_API_TOKEN=' "$env_file" || true)
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

load_env

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

# macOS LaunchAgent 状态：没有安装不算故障，只给下一步。
for label in ai.openclaw.xianyu ai.openclaw.intel-brief.scheduler; do
  if launchctl print "gui/$UID/$label" >/dev/null 2>&1; then
    add_check "launchagent:$label" "ok" "$label 已加载" "无需处理"
  else
    add_check "launchagent:$label" "warn" "$label 未加载" "如需自动运行，按 docs/007-operations.md 安装 LaunchAgent"
  fi
done

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
