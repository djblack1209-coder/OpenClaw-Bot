#!/usr/bin/env bash
# OpenEverything 自动健康检查：只读巡检，不重启、不写生产数据。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JSON_MODE=0
STRICT_MODE=0

while (( $# > 0 )); do
  case "$1" in
    --json) JSON_MODE=1 ;;
    --strict) STRICT_MODE=1 ;;
    -h|--help)
      echo "用法：scripts/auto_health_check.sh [--json] [--strict]"
      exit 0
      ;;
    *)
      echo "❌ 不认识的参数：$1" >&2
      exit 64
      ;;
  esac
  shift
done

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
    value="${value%\'}"
    value="${value#\'}"
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

intel_scheduler_artifact_status() {
  local report="$1" run_evidence stdout_log stderr_log audit_file audit_status
  run_evidence="$(printf '%s\n' "$report" | awk '/^[[:space:]]*--evidence$/{getline; gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0); print; exit}')"
  stdout_log="$(printf '%s\n' "$report" | sed -n 's/^[[:space:]]*stdout path = //p' | head -1)"
  stderr_log="$(printf '%s\n' "$report" | sed -n 's/^[[:space:]]*stderr path = //p' | head -1)"
  if [[ -z "$run_evidence" || -z "$stdout_log" || -z "$stderr_log" ]]; then
    printf 'not_verified|Intel 调度产物路径不可读取\n'
    return
  fi

  local intel_python="$ROOT_DIR/packages/clawbot/.venv312/bin/python"
  local audit_script="$ROOT_DIR/packages/clawbot/scripts/intel_launchagent_audit.py"
  if [[ ! -x "$intel_python" || ! -f "$audit_script" ]]; then
    printf 'not_verified|Intel 调度审计运行时不可用\n'
    return
  fi

  if ! audit_file="$(mktemp "${TMPDIR:-/tmp}/openclaw-intel-audit.XXXXXX")"; then
    printf 'not_verified|Intel 调度审计临时文件不可创建\n'
    return
  fi
  "$intel_python" "$audit_script" \
    --run-evidence "$run_evidence" \
    --stdout-log "$stdout_log" \
    --stderr-log "$stderr_log" \
    --output "$audit_file" >/dev/null 2>&1 || true
  audit_status="$(python3 - "$audit_file" <<'PY' 2>/dev/null || true
import json
import sys
from pathlib import Path

try:
    print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get("status", "not_verified"))
except (OSError, json.JSONDecodeError, IndexError):
    print("not_verified")
PY
)"
  rm -f "$audit_file"
  if [[ "$audit_status" == "verified_success" ]]; then
    printf 'ok|Intel 调度产物、标准输出和投递结果已验证（LaunchAgent 计数器未更新）\n'
  else
    printf '%s|Intel 调度产物尚未通过只读审计\n' "${audit_status:-not_verified}"
  fi
}

backup_natural_run_status() {
  local report="$1" stdout_log backup_dir
  stdout_log="$(printf '%s\n' "$report" | sed -n 's/^[[:space:]]*stdout path = //p' | head -1)"
  backup_dir="${OPENCLAW_BACKUP_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/openclaw/backups}"
  if [[ -z "$stdout_log" ]]; then
    printf 'not_verified|备份自然运行日志路径不可读取\n'
    return
  fi
  python3 - "$stdout_log" "$backup_dir" <<'PY' 2>/dev/null || printf 'not_verified|备份自然运行产物不可读取\n'
import json
import pathlib
import sys
import time

stdout = pathlib.Path(sys.argv[1])
backup_dir = pathlib.Path(sys.argv[2])
if not stdout.is_file() or stdout.is_symlink():
    print("not_verified|备份自然运行日志不存在")
    raise SystemExit
lines = [line for line in stdout.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
if len(lines) < 2 or not lines[-2].startswith("restore drill passed:"):
    print("not_verified|最近备份日志没有恢复演练通过记录")
    raise SystemExit
try:
    payload = json.loads(lines[-1])
except json.JSONDecodeError:
    print("not_verified|最近备份结果不是有效 JSON")
    raise SystemExit
archive_value = payload.get("archive")
if payload.get("ok") is not True or not isinstance(archive_value, str):
    print("not_verified|最近备份结果未标记成功")
    raise SystemExit
archive_path = pathlib.Path(archive_value)
if archive_path.is_symlink():
    print("not_verified|最近备份归档是符号链接")
    raise SystemExit
try:
    archive = archive_path.resolve()
    archive.relative_to(backup_dir.resolve())
except ValueError:
    print("not_verified|最近备份归档不在受管备份目录")
    raise SystemExit
ready = pathlib.Path(f"{archive}.ready")
checksum = pathlib.Path(f"{archive}.sha256")
if (
    not archive.is_file() or archive.is_symlink()
    or not ready.is_file() or ready.is_symlink()
    or not checksum.is_file() or checksum.is_symlink()
):
    print("not_verified|最近备份归档缺少有效就绪标记")
    raise SystemExit
if max(0, int((time.time() - archive.stat().st_mtime) // 3600)) > 36:
    print("not_verified|最近自然备份已超过 36 小时")
    raise SystemExit
if stdout.stat().st_mtime < archive.stat().st_mtime:
    print("not_verified|备份日志早于归档完成时间")
    raise SystemExit
print("ok|备份归档、就绪标记和只读恢复演练已验证（LaunchAgent 计数器未更新）")
PY
}

check_scheduled_launchagent() {
  local label="$1" report state last_exit artifact_status artifact_detail
  if ! report="$(launchagent_report "$label")"; then
    add_check "launchagent:$label" "bad" "$label 未加载" "重新部署该定时任务"
    return
  fi
  state="$(printf '%s\n' "$report" | sed -n 's/^[[:space:]]*state = //p' | head -1)"
  last_exit="$(printf '%s\n' "$report" | sed -n 's/^[[:space:]]*last exit code = //p' | head -1)"
  if [[ "$state" == "running" || "$last_exit" == "0" ]]; then
    add_check "launchagent:$label" "ok" "$label 已加载且最近退出正常" "无需处理"
  elif [[ "$last_exit" == "(never exited)" ]]; then
    if [[ "$label" == "ai.openclaw.intel-brief.scheduler" ]]; then
      IFS='|' read -r artifact_status artifact_detail <<<"$(intel_scheduler_artifact_status "$report")"
      if [[ "$artifact_status" == "ok" ]]; then
        add_check "launchagent:$label" "ok" "$artifact_detail" "无需处理"
      else
        add_check "launchagent:$label" "warn" "$label 已加载，等待自然调度产物验证" "到点后重新运行严格健康检查"
      fi
    elif [[ "$label" == "ai.openclaw.daily-backup" ]]; then
      IFS='|' read -r artifact_status artifact_detail <<<"$(backup_natural_run_status "$report")"
      if [[ "$artifact_status" == "ok" ]]; then
        add_check "launchagent:$label" "ok" "$artifact_detail" "无需处理"
      else
        add_check "launchagent:$label" "warn" "$label 已加载，等待自然调度产物验证" "到点后重新运行严格健康检查"
      fi
    else
      add_check "launchagent:$label" "warn" "$label 已加载，等待首次自然调度验证" "到点后重新运行严格健康检查"
    fi
  else
    add_check "launchagent:$label" "bad" "$label 最近执行异常 (state=${state:-unknown}, exit=${last_exit:-unknown})" "检查定时任务日志和最近触发时间"
  fi
}

check_backup_freshness() {
  local backup_dir="${OPENCLAW_BACKUP_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/openclaw/backups}"
  local report status detail
  report="$(python3 - "$backup_dir" <<'PY' 2>/dev/null || true
import pathlib
import sys
import time

backup_dir = pathlib.Path(sys.argv[1])
archives = sorted(backup_dir.glob("openeverything-*.tgz"), key=lambda path: path.stat().st_mtime, reverse=True)
if not archives:
    print("bad|没有可用的本机备份")
    raise SystemExit
archive = archives[0]
ready = pathlib.Path(f"{archive}.ready")
checksum = pathlib.Path(f"{archive}.sha256")
if not ready.is_file() or not checksum.is_file() or archive.is_symlink() or ready.is_symlink() or checksum.is_symlink():
    print(f"bad|最新备份缺少完整就绪标记: {archive.name}")
    raise SystemExit
age_hours = max(0, int((time.time() - archive.stat().st_mtime) // 3600))
if age_hours > 36:
    print(f"bad|最新备份已过期 {age_hours} 小时: {archive.name}")
else:
    print(f"ok|最新备份 {age_hours} 小时前完成: {archive.name}")
PY
)"
  status="${report%%|*}"
  detail="${report#*|}"
  if [[ "$status" == "ok" ]]; then
    add_check "backup_freshness" "ok" "$detail" "无需处理"
  else
    add_check "backup_freshness" "bad" "${detail:-备份状态无法读取}" "运行 scripts/manage_backup_launchagent.sh run 并检查错误日志"
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
check_required_launchagent "ai.openclaw.intel-brief.telegram-listener"
check_scheduled_launchagent "ai.openclaw.intel-brief.scheduler"
check_scheduled_launchagent "ai.openclaw.daily-backup"
check_backup_freshness

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
  add_check "disk" "bad" "剩余 ${available_gb}GB" "先运行 scripts/auto_recovery.sh --scope maintenance 预览，再增加 --confirm"
fi

has_bad=0
has_warn=0
for item in "${CHECKS[@]}"; do
  IFS='|' read -r _ status _ _ <<<"$item"
  [[ "$status" == "bad" ]] && has_bad=1
  [[ "$status" == "warn" ]] && has_warn=1
done

if (( JSON_MODE == 1 )); then
  printf '{"ok":'
  if (( has_bad == 1 )); then printf 'false'; else printf 'true'; fi
  printf ',"release_ready":'
  if (( has_bad == 1 || has_warn == 1 )); then printf 'false'; else printf 'true'; fi
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

if (( STRICT_MODE == 1 )); then
  (( has_bad == 0 )) || exit 1
  (( has_warn == 0 )) || exit 2
fi
