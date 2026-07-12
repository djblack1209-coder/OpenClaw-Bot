#!/usr/bin/env bash
# ClawBot Agent 启动入口；供 Tauri 的受控 fallback 使用，也可在终端前台运行。
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/.venv312/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  printf '错误：项目 Python 环境不存在：%s\n' "$PYTHON" >&2
  exit 1
fi
mkdir -p "$ROOT_DIR/logs"
chmod 700 "$ROOT_DIR/logs" 2>/dev/null || true

# 只检查端口，不杀任何未知进程。服务已存在或端口被占用时安全停止。
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:18790 -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "ClawBot Agent 未启动：127.0.0.1:18790 已被占用。"
  exit 1
fi

cd "$ROOT_DIR"
exec "$PYTHON" "$ROOT_DIR/multi_main.py"
