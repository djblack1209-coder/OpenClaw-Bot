#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_DIR="$ROOT_DIR/packages/new-api-upstream"
PATCH_FILE="$ROOT_DIR/scripts/patches/new-api-cc-brand.patch"

if [[ ! -d "$UPSTREAM_DIR" ]]; then
  echo "缺少 New-API submodule：$UPSTREAM_DIR" >&2
  exit 1
fi

if [[ ! -s "$PATCH_FILE" ]]; then
  echo "缺少 CC中转品牌补丁：$PATCH_FILE" >&2
  exit 1
fi

if git -C "$UPSTREAM_DIR" apply --reverse --check "$PATCH_FILE" >/dev/null 2>&1; then
  echo "CC中转品牌补丁已经应用，无需重复处理。"
  exit 0
fi

if ! git -C "$UPSTREAM_DIR" apply --check "$PATCH_FILE"; then
  echo "CC中转品牌补丁与当前 New-API 版本不兼容，请先人工复核上游改动。" >&2
  exit 1
fi

git -C "$UPSTREAM_DIR" apply "$PATCH_FILE"
echo "已应用 CC中转品牌补丁。提交基线时只提交补丁文件，不提交 submodule 脏工作区。"
