#!/usr/bin/env bash
# OpenEverything 自动恢复：默认按 dry-run 展示动作，去掉 --dry-run 才真正执行。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

run_action() {
  local label="$1"; shift
  echo "▶ $label: $*"
  if (( DRY_RUN == 0 )); then
    "$@"
  fi
}

notify_mac() {
  local title="$1" body="$2"
  if command -v osascript >/dev/null 2>&1; then
    run_action "macOS 通知" osascript -e "display notification \"$body\" with title \"$title\""
  fi
}

cd "$ROOT_DIR"
echo "OpenEverything 自动恢复 $( ((DRY_RUN==1)) && echo '(dry-run)' || echo '(执行模式)' )"

# 1. 本机控制台不通时，优先 kickstart LaunchAgent；没有安装则提示老板打开卖家桥接。
dashboard_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:18800/dashboard 2>/dev/null || echo 000)
root_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:18800/ 2>/dev/null || echo 000)
api_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:18800/api/status 2>/dev/null || echo 000)
api_alive=0
case "$api_code" in
  200|401) api_alive=1 ;;
esac
if [[ "${dashboard_code}" != "200" && "${root_code}" != "200" && "${api_alive}" != "1" ]]; then
  if launchctl print "gui/$UID/ai.openclaw.xianyu" >/dev/null 2>&1; then
    run_action "重启闲鱼本机服务" launchctl kickstart -k "gui/$UID/ai.openclaw.xianyu"
  else
    echo "⚠️ 未找到 ai.openclaw.xianyu LaunchAgent；请先按运维文档安装。"
  fi
else
  echo "✅ 本机控制台可访问（dashboard=${dashboard_code} / root=${root_code} / api=${api_code}）"
fi

# 2. 卖家 Chrome/桥接器一键兜底；dry-run 下只展示命令。
run_action "检查卖家 Chrome 与桥接器" make cc-seller-auto

# 3. 清理旧日志，避免磁盘被历史日志撑满。
run_action "清理 30 天前日志" find "$ROOT_DIR" -path '*/logs/*' -type f -mtime +30 -delete
run_action "清理 pytest 缓存" find "$ROOT_DIR" -type d -name '.pytest_cache' -prune -exec rm -rf {} +

# 4. 重新跑健康检查，给老板一个结果。
run_action "重新健康检查" bash "$ROOT_DIR/scripts/auto_health_check.sh" --json
notify_mac "OpenEverything 恢复完成" "如果仍是红灯，请导出状态报告给技术支持。"
