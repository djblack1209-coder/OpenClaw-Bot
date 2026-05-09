#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_DIR="$ROOT_DIR/packages/new-api-upstream"
COMPOSE_FILE="$ROOT_DIR/docker-compose.newapi.yml"
REMOTE_URL="https://github.com/QuantumNous/new-api.git"
API_URL="https://api.github.com/repos/QuantumNous/new-api/releases?per_page=20"
MODE="${1:-check}"

if [[ "$MODE" != "check" && "$MODE" != "update" ]]; then
  echo "用法: $0 [check|update]" >&2
  exit 2
fi

if ! command -v git >/dev/null 2>&1; then
  echo "缺少 git，无法同步 New-API 上游。" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "缺少 curl，无法检查 GitHub 最新版本。" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "缺少 python3，无法解析 GitHub Release 响应。" >&2
  exit 1
fi

latest_json="$(curl -fsSL "$API_URL")"
latest_info="$(printf '%s' "$latest_json" | python3 -c '
import json
import sys

releases = json.load(sys.stdin)
for release in releases:
    if release.get("draft"):
        continue
    print("\t".join([
        release.get("tag_name", ""),
        release.get("published_at", ""),
        str(release.get("prerelease", False)).lower(),
    ]))
    break
')"
latest_tag="$(printf '%s' "$latest_info" | awk -F '\t' '{print $1}')"
published_at="$(printf '%s' "$latest_info" | awk -F '\t' '{print $2}')"
prerelease="$(printf '%s' "$latest_info" | awk -F '\t' '{print $3}')"

if [[ -z "$latest_tag" ]]; then
  echo "无法从 GitHub Release 响应解析 New-API 最新版本。" >&2
  exit 1
fi

if [[ ! -d "$UPSTREAM_DIR/.git" && ! -f "$UPSTREAM_DIR/.git" ]]; then
  echo "New-API submodule 不存在，请先执行: git submodule update --init packages/new-api-upstream" >&2
  exit 1
fi

git -C "$UPSTREAM_DIR" fetch --tags origin >/dev/null
current_ref="$(git -C "$UPSTREAM_DIR" describe --tags --exact-match 2>/dev/null || git -C "$UPSTREAM_DIR" rev-parse --short=12 HEAD)"
latest_sha="$(git -C "$UPSTREAM_DIR" rev-list -n 1 "$latest_tag")"
current_sha="$(git -C "$UPSTREAM_DIR" rev-parse HEAD)"
compose_tag="$(sed -n 's/^[[:space:]]*image:[[:space:]]*calciumion\/new-api:\([^[:space:]]*\).*/\1/p' "$COMPOSE_FILE" | head -1)"

echo "New-API 上游: $REMOTE_URL"
echo "GitHub 最新: $latest_tag ($latest_sha, $published_at, prerelease=$prerelease)"
echo "本地源码: $current_ref ($current_sha)"
echo "Compose 镜像: calciumion/new-api:${compose_tag:-未找到}"

if [[ "$MODE" == "check" ]]; then
  if [[ "$current_sha" == "$latest_sha" && "$compose_tag" == "$latest_tag" ]]; then
    echo "状态: 已同步到最新 release。"
    exit 0
  else
    echo "状态: 需要同步。执行 make new-api-sync 更新源码指针和镜像 tag。"
    exit 2
  fi
fi

git -C "$UPSTREAM_DIR" checkout "$latest_tag" >/dev/null

tmp_file="$(mktemp)"
sed "s#image:[[:space:]]*calciumion/new-api:[^[:space:]]*#image: calciumion/new-api:$latest_tag#" "$COMPOSE_FILE" >"$tmp_file"
mv "$tmp_file" "$COMPOSE_FILE"

echo "已更新 New-API 到 $latest_tag。"
echo "后续请运行: docker compose -f docker-compose.newapi.yml config"
echo "升级运行服务前请先备份 data/newapi。"
