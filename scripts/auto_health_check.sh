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
  add_check "local_console" "bad" "本机控制台不可用 HTTP $code" "先运行 scripts/auto_recovery.sh --dry-run 查看计划；确认无误后显式运行 scripts/auto_recovery.sh --confirm"
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
  add_check "disk" "bad" "剩余 ${available_gb}GB" "先运行 scripts/auto_recovery.sh --dry-run 查看清理范围；确认无误后显式运行 scripts/auto_recovery.sh --confirm"
fi

# 本机 SQLite 备份状态：只读取脱敏状态文件，不打开数据库内容。
backup_status_file="$ROOT_DIR/packages/clawbot/data/backups/latest-status.json"
if [[ -f "$backup_status_file" ]]; then
  backup_probe=$(python3 - "$backup_status_file" <<'PY_BACKUP' 2>/dev/null || true
import json
import sys
from datetime import datetime, timezone

try:
    payload = json.load(open(sys.argv[1], encoding="utf-8"))
    status = str(payload.get("status") or "unknown")
    stamp = str(payload.get("last_success_at") or payload.get("last_attempt_at") or "")
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_hours = max(0, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() // 3600))
    print(f"{status}|{age_hours}")
except Exception:
    print("invalid|9999")
PY_BACKUP
)
  IFS='|' read -r backup_status backup_age_hours <<<"$backup_probe"
  if [[ "$backup_status" == "ok" && "$backup_age_hours" -le 30 ]]; then
    add_check "local_db_backup" "ok" "最近成功备份距今 ${backup_age_hours} 小时" "无需处理"
  elif [[ "$backup_status" == "failed" || "$backup_status" == "invalid" ]]; then
    add_check "local_db_backup" "bad" "最近备份失败或状态损坏" "运行 make backup-databases；通过后运行 make backup-restore-drill"
  else
    add_check "local_db_backup" "warn" "最近成功备份已超过 30 小时" "运行 make backup-databases；通过后运行 make backup-restore-drill"
  fi
else
  add_check "local_db_backup" "warn" "尚无本机数据库备份状态" "运行 make backup-databases；通过后运行 make backup-restore-drill"
fi

# 资源续费：只读取无凭据台账并计算日期，不登录供应商、不付款。
renewal_script="$ROOT_DIR/scripts/check_renewals.py"
renewal_file="${OPENCLAW_RENEWALS_FILE:-$ROOT_DIR/packages/clawbot/config/renewals.json}"
if [[ ! -x "$renewal_script" ]]; then
  add_check "renewals" "warn" "续费提醒脚本不存在" "确认 scripts/check_renewals.py 已安装"
elif [[ ! -f "$renewal_file" ]]; then
  add_check "renewals" "warn" "尚未建立本机续费台账，所有到期日都按 unknown 处理" "复制 packages/clawbot/config/renewals.example.json 为 renewals.json，只填写日期、费用和供应商，不要写任何凭据"
else
  renewal_output=$(python3 "$renewal_script" --config "$renewal_file" --json 2>/dev/null || true)
  renewal_probe=$(printf '%s' "$renewal_output" | python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
    summary = payload.get("summary") or {}
    print("|".join(str(value) for value in (
        payload.get("status", "invalid"),
        summary.get("total", 0),
        summary.get("expired", 0),
        summary.get("expires_today", 0),
        summary.get("due_soon", 0),
        summary.get("unknown", 0),
    )))
except Exception:
    print("invalid|0|0|0|0|0")
' 2>/dev/null || echo 'invalid|0|0|0|0|0')
  IFS='|' read -r renewal_status renewal_total renewal_expired renewal_today renewal_due renewal_unknown <<<"$renewal_probe"
  case "$renewal_status" in
    ok)
      add_check "renewals" "ok" "${renewal_total} 项资源均在 30 天安全窗外" "无需处理"
      ;;
    action_required)
      if (( renewal_expired > 0 || renewal_today > 0 )); then
        add_check "renewals" "bad" "${renewal_expired} 项已过期，${renewal_today} 项今日到期，${renewal_due} 项进入 30/14/7/3/1 天提醒窗" "打开 docs/081-owner-ops-handbook.md 的续费清单；由本人决定续费或停用，系统不会代付"
      else
        add_check "renewals" "warn" "${renewal_due} 项进入 30/14/7/3/1 天提醒窗" "打开 docs/081-owner-ops-handbook.md 的续费清单；由本人决定续费或停用，系统不会代付"
      fi
      ;;
    warning)
      add_check "renewals" "warn" "${renewal_unknown} / ${renewal_total} 项到期日仍是 unknown" "补齐 renewals.json 的供应商和到期日；不要写密码、Token、Cookie 或恢复码"
      ;;
    *)
      add_check "renewals" "bad" "续费台账格式无效，提醒可能失效" "运行 make renewals-check 校验模板，再按模板修复本机 renewals.json"
      ;;
  esac
fi

# 敏感运行文件权限：只读取元数据，不读取 Cookie、会话、数据库或状态内容。
permission_script="$ROOT_DIR/scripts/harden_runtime_permissions.py"
if [[ -x "$permission_script" ]]; then
  permission_probe=$(OPENCLAW_PROJECT_ROOT="$ROOT_DIR" python3 "$permission_script" --check 2>/dev/null || true)
  permission_count=$(printf '%s' "$permission_probe" | python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("violations", -1)))' 2>/dev/null || echo -1)
  if [[ "$permission_count" == "0" ]]; then
    add_check "runtime_permissions" "ok" "敏感运行文件仅当前用户可访问" "无需处理"
  elif [[ "$permission_count" =~ ^[1-9][0-9]*$ ]]; then
    add_check "runtime_permissions" "bad" "发现 ${permission_count} 个权限过宽的敏感运行文件或目录" "运行 make runtime-permissions-fix；该命令只改权限，不读取内容"
  else
    add_check "runtime_permissions" "warn" "敏感运行文件权限状态无法读取" "运行 make runtime-permissions-check 查看脱敏计数"
  fi
else
  add_check "runtime_permissions" "warn" "权限检查脚本不存在" "确认 scripts/harden_runtime_permissions.py 已安装"
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
