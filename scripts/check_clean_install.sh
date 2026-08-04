#!/usr/bin/env bash
# 在临时目录验证前端锁文件和当前平台 Python 哈希锁可实际安装。
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/openclaw-clean-install.XXXXXX")"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

install_node_lock() {
  local source_dir="$1"
  local target_dir
  target_dir="$WORK_DIR/$(basename "$source_dir")"
  mkdir -p "$target_dir"
  cp "$source_dir/package.json" "$source_dir/package-lock.json" "$target_dir/"
  npm ci --prefix "$target_dir" --no-audit --no-fund
}

echo "══════ 临时目录 npm 锁安装 ══════"
install_node_lock "$ROOT_DIR/apps/frist-api"
install_node_lock "$ROOT_DIR/apps/openclaw-manager-src"

case "$(uname -s)" in
  Darwin) python_lock="$ROOT_DIR/packages/clawbot/requirements-lock-macos.txt" ;;
  *) python_lock="$ROOT_DIR/packages/clawbot/requirements-lock.txt" ;;
esac

echo "══════ 临时目录 Python 哈希锁安装 ══════"
uv venv "$WORK_DIR/python" --python 3.12 --seed >/dev/null
uv pip install \
  --python "$WORK_DIR/python/bin/python" \
  --require-hashes \
  --no-deps \
  -r "$python_lock"

echo "✅ 干净临时目录安装通过：前端双 npm lock + $(basename "$python_lock")"
