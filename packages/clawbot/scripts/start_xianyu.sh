#!/usr/bin/env bash
# 闲鱼客服启动入口；默认安全边界由 xianyu_main.py 和运行时操作员状态共同控制。
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/.venv312/bin/python"
ENTRYPOINT="$ROOT_DIR/scripts/xianyu_main.py"

if [[ ! -x "$PYTHON" ]]; then
  printf '错误：项目 Python 环境不存在：%s\n' "$PYTHON" >&2
  exit 1
fi
if [[ ! -f "$ENTRYPOINT" ]]; then
  printf '错误：闲鱼入口不存在：%s\n' "$ENTRYPOINT" >&2
  exit 1
fi
mkdir -p "$ROOT_DIR/logs"
chmod 700 "$ROOT_DIR/logs" 2>/dev/null || true

# 不发送进程终止信号；发现同一项目入口已运行时直接退出，避免重复连接或误杀其他工作区。
if command -v pgrep >/dev/null 2>&1 && pgrep -f -- "$ENTRYPOINT" >/dev/null 2>&1; then
  echo "闲鱼客服已在运行，本次不重复启动。"
  exit 0
fi

cd "$ROOT_DIR"
exec "$PYTHON" "$ENTRYPOINT"
