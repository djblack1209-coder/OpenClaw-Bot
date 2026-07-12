#!/usr/bin/env bash
# OpenEverything 自动恢复：默认只展示计划，必须显式 --confirm 才会重启或删除旧文件。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=1
JSON_MODE=0
CONFIRM=0
ACTIONS=0
FAILED_ACTIONS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --confirm) DRY_RUN=0; CONFIRM=1 ;;
    --json) JSON_MODE=1 ;;
    *) printf '未知参数：%s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

log() {
  if (( JSON_MODE == 1 )); then
    printf '%s\n' "$*" >&2
  else
    printf '%s\n' "$*"
  fi
}

run_with_timeout() {
  local timeout_seconds="$1"; shift
  python3 - "$timeout_seconds" "$@" <<'PY'
import subprocess
import sys

timeout = max(1.0, float(sys.argv[1]))
command = sys.argv[2:]
try:
    completed = subprocess.run(command, check=False, timeout=timeout)
except subprocess.TimeoutExpired:
    raise SystemExit(124)
raise SystemExit(completed.returncode)
PY
}

run_action() {
  local label="$1" timeout_seconds="$2"; shift 2
  ACTIONS=$((ACTIONS + 1))
  log "▶ $label: $*"
  if (( DRY_RUN == 1 )); then
    return 0
  fi
  if run_with_timeout "$timeout_seconds" "$@"; then
    log "✅ $label 完成"
    return 0
  fi
  local rc=$?
  FAILED_ACTIONS=$((FAILED_ACTIONS + 1))
  log "⚠️ $label 失败（退出码 $rc），继续执行其他安全恢复项"
  return 0
}

notify_mac() {
  local title="$1" body="$2"
  if command -v osascript >/dev/null 2>&1; then
    run_action "macOS 通知" 15 osascript -e "display notification \"$body\" with title \"$title\""
  fi
}

LOCK_DIR="${TMPDIR:-/tmp}/openclaw-auto-recovery-${UID}.lock"
if (( CONFIRM == 1 )); then
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    if (( JSON_MODE == 1 )); then
      printf '%s\n' '{"ok":false,"error":"auto_recovery_already_running"}'
    else
      log "已有一轮自动恢复正在执行，本次安全退出。"
    fi
    exit 73
  fi
  trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
fi

cd "$ROOT_DIR"
if (( DRY_RUN == 1 )); then
  log "OpenEverything 自动恢复（dry-run，仅展示；真正执行必须加 --confirm）"
else
  log "OpenEverything 自动恢复（已收到 --confirm，执行模式）"
fi

# 1. 本机控制台不通时，优先 kickstart LaunchAgent；没有安装则只提示。
dashboard_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:18800/dashboard 2>/dev/null || echo 000)
root_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:18800/ 2>/dev/null || echo 000)
api_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:18800/api/status 2>/dev/null || echo 000)
api_alive=0
case "$api_code" in
  200|401) api_alive=1 ;;
esac
if [[ "$dashboard_code" != "200" && "$root_code" != "200" && "$api_alive" != "1" ]]; then
  if launchctl print "gui/$UID/ai.openclaw.xianyu" >/dev/null 2>&1; then
    run_action "重启闲鱼本机服务" 30 launchctl kickstart -k "gui/$UID/ai.openclaw.xianyu"
  else
    log "⚠️ 未找到 ai.openclaw.xianyu LaunchAgent；请先按运维文档安装。"
  fi
else
  log "✅ 本机控制台可访问（dashboard=${dashboard_code} / root=${root_code} / api=${api_code}）"
fi

# 2. 卖家 Chrome/桥接器一键兜底；未确认时只展示命令。
run_action "检查卖家 Chrome 与桥接器" 120 make cc-seller-auto

# 3. 清理旧日志和测试缓存；必须收到 --confirm 才删除。
run_action "清理 30 天前日志" 60 find "$ROOT_DIR" -path '*/logs/*' -type f -mtime +30 -delete
run_action "清理 pytest 缓存" 60 find "$ROOT_DIR" -type d -name '.pytest_cache' -prune -exec rm -rf '{}' +

# 4. 重新跑健康检查；失败会进入最终摘要，但不会吞掉其他动作结果。
run_action "重新健康检查" 90 bash "$ROOT_DIR/scripts/auto_health_check.sh" --json
if (( DRY_RUN == 0 )); then
  notify_mac "OpenEverything 恢复完成" "如果仍是红灯，请导出状态报告给技术支持。"
fi

ok=true
(( FAILED_ACTIONS > 0 )) && ok=false
if (( JSON_MODE == 1 )); then
  printf '{"ok":%s,"dry_run":%s,"confirmed":%s,"actions":%d,"failed_actions":%d}\n' \
    "$ok" "$([[ "$DRY_RUN" == "1" ]] && echo true || echo false)" \
    "$([[ "$CONFIRM" == "1" ]] && echo true || echo false)" "$ACTIONS" "$FAILED_ACTIONS"
else
  if (( DRY_RUN == 1 )); then
    log "预演完成：未重启服务、未启动浏览器、未删除文件。真正执行请显式运行 scripts/auto_recovery.sh --confirm"
  elif (( FAILED_ACTIONS == 0 )); then
    log "自动恢复执行完成。"
  else
    log "自动恢复有 ${FAILED_ACTIONS} 项失败，请查看上方动作和老板状态入口。"
  fi
fi

(( FAILED_ACTIONS == 0 ))
