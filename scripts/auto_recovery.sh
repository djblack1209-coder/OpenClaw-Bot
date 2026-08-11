#!/usr/bin/env bash
# OpenEverything 自动恢复：默认只展示动作，必须显式确认后才会修改本机状态。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=1
CONFIRMED=0
SCOPE="services"

usage() {
  cat <<'USAGE'
用法：scripts/auto_recovery.sh [--dry-run] [--confirm] [--scope services|maintenance]

默认只预览服务恢复动作，不会修改系统。真正执行必须带 --confirm：
  --scope services      只恢复本机服务（默认）
  --scope maintenance   只清理旧日志和测试缓存
USAGE
}

while (( $# > 0 )); do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      CONFIRMED=0
      ;;
    --confirm)
      DRY_RUN=0
      CONFIRMED=1
      ;;
    --scope)
      shift
      [[ $# -gt 0 ]] || { echo "❌ --scope 缺少取值" >&2; usage >&2; exit 64; }
      SCOPE="$1"
      ;;
    --scope=*)
      SCOPE="${1#*=}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "❌ 不认识的参数：$1" >&2
      usage >&2
      exit 64
      ;;
  esac
  shift
done

case "$SCOPE" in
  services|maintenance) ;;
  *)
    echo "❌ --scope 只能是 services 或 maintenance" >&2
    exit 64
    ;;
esac

run_action() {
  local label="$1"; shift
  echo "▶ $label: $*"
  if (( DRY_RUN == 0 )); then
    "$@"
  fi
}

notify_mac() {
  local title="$1" body="$2"
  if [[ "${OPENCLAW_NOTIFICATIONS_ENABLED:-1}" == "1" ]] && command -v osascript >/dev/null 2>&1; then
    run_action "macOS 通知" osascript -e "display notification \"$body\" with title \"$title\""
  fi
}

cd "$ROOT_DIR"
if (( DRY_RUN == 1 )); then
  echo "OpenEverything 自动恢复（dry-run，范围：${SCOPE}）"
  echo "ℹ️ 本次不会修改系统；确认动作后请增加 --confirm。"
else
  (( CONFIRMED == 1 )) || { echo "❌ 执行模式必须显式提供 --confirm" >&2; exit 64; }
  echo "OpenEverything 自动恢复（执行模式，范围：${SCOPE}）"
fi

if [[ "$SCOPE" == "services" ]]; then
  echo "ℹ️ 服务恢复由各 LaunchAgent 原生 KeepAlive 策略负责；此入口仅执行恢复后的统一健康检查。"
fi

if [[ "$SCOPE" == "maintenance" ]]; then
  # 维护范围只处理可再生成的历史文件。
  run_action "清理 30 天前日志" find "$ROOT_DIR" -path '*/logs/*' -type f -mtime +30 -delete
  run_action "清理 pytest 缓存" find "$ROOT_DIR" -type d -name '.pytest_cache' -prune -exec rm -rf {} +
fi

if (( DRY_RUN == 1 )); then
  echo "▶ 重新健康检查: bash $ROOT_DIR/scripts/auto_health_check.sh --json --strict"
  exit 0
fi

health_status=0
if health_output="$(bash "$ROOT_DIR/scripts/auto_health_check.sh" --json --strict)"; then
  printf '%s\n' "$health_output"
  notify_mac "OpenEverything 恢复完成" "健康检查已通过。"
else
  health_status=$?
  printf '%s\n' "$health_output"
  echo "❌ 恢复动作已执行，但严格健康检查仍未通过（退出码 $health_status）。" >&2
  notify_mac "OpenEverything 恢复未通过" "仍有红灯或黄灯，请查看健康报告。" || true
  exit "$health_status"
fi
