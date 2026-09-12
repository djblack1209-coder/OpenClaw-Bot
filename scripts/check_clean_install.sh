#!/usr/bin/env bash
# 安装到临时目录；构建和测试禁止访问真实用户文件及外网。
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$ROOT_DIR/scripts/check_clean_install.py" "$@"
