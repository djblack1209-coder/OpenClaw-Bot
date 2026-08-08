#!/usr/bin/env bash
set -Eeuo pipefail

# 该脚本只允许由 sudoers 固定命令调用，不接受浏览器传入的参数。

readonly CONFIG_FILE="/etc/sub2api/jiyu-update.conf"
readonly MANAGER_PATH="/usr/local/sbin/openclaw-sub2api-manager"
readonly INSTALL_DIR="/opt/sub2api"
readonly LOCK_FILE="/run/lock/sub2api-jiyu-web-update.lock"
readonly MAX_MANIFEST_BYTES=65536
readonly MAX_ARTIFACT_BYTES=536870912

manifest_file=""
artifact_file=""

cleanup() {
  [[ -z "$manifest_file" ]] || rm -f -- "$manifest_file"
  [[ -z "$artifact_file" ]] || rm -f -- "$artifact_file"
}

fail() {
  printf 'JIYU_UPDATE_STATUS=error\n' >&2
  printf 'JIYU 兼容包更新失败：%s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令 $1"
}

read_config_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$CONFIG_FILE" | tail -n 1
}

validate_https_host() {
  local url="$1"
  local host
  host="$(python3 - "$url" <<'PY'
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
    raise SystemExit(1)
print(parsed.hostname)
PY
)" || fail "下载地址不是合法 HTTPS 地址"
  case "$host" in
    github.com | objects.githubusercontent.com | release-assets.githubusercontent.com)
      ;;
    *)
      fail "下载地址不在允许的发布域名内"
      ;;
  esac
}

main() {
  [[ "$#" -eq 0 ]] || fail "该代理不接受任何命令行参数"
  [[ "${EUID}" -eq 0 ]] || fail "必须由 root 执行"
  [[ "$(uname -s)" == "Linux" ]] || fail "只支持 Linux 服务器"
  [[ -f "$CONFIG_FILE" ]] || fail "缺少 root 管理的更新配置"
  [[ -x "$MANAGER_PATH" ]] || fail "缺少 JIYU 发布管理器"
  require_command curl
  require_command file
  require_command flock
  require_command jq
  require_command python3
  require_command sha256sum

  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "已有更新任务正在执行"

  local manifest_url
  local version upstream_version platform arch artifact_url expected_sha expected_size
  manifest_url="$(read_config_value MANIFEST_URL)"
  [[ -n "$manifest_url" ]] || fail "MANIFEST_URL 尚未配置"
  validate_https_host "$manifest_url"

  manifest_file="$(mktemp)"
  artifact_file="$(mktemp)"
  trap cleanup EXIT
  curl -fsSL --proto '=https' --proto-redir '=https' --max-filesize "$MAX_MANIFEST_BYTES" \
    --connect-timeout 10 --max-time 60 -o "$manifest_file" "$manifest_url"
  [[ "$(wc -c <"$manifest_file" | tr -d ' ')" -le "$MAX_MANIFEST_BYTES" ]] || \
    fail "兼容包清单超过安全上限"
  jq -e '.schema_version == 1' "$manifest_file" >/dev/null || fail "兼容包清单版本不受支持"

  version="$(jq -r '.version // empty' "$manifest_file")"
  upstream_version="$(jq -r '.upstream_version // empty' "$manifest_file")"
  platform="$(jq -r '.platform // empty' "$manifest_file")"
  arch="$(jq -r '.arch // empty' "$manifest_file")"
  artifact_url="$(jq -r '.artifact_url // empty' "$manifest_file")"
  expected_sha="$(jq -r '.sha256 // empty' "$manifest_file")"
  expected_size="$(jq -r '.size // 0' "$manifest_file")"

  [[ "$version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-jiyu\.[0-9]+$ ]] || fail "兼容包版本号非法"
  [[ "$upstream_version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "上游版本号非法"
  [[ "$platform" == "linux" ]] || fail "兼容包平台不匹配"
  case "$(uname -m):$arch" in
    aarch64:arm64 | arm64:arm64 | x86_64:amd64 | amd64:amd64)
      ;;
    *)
      fail "兼容包架构不匹配"
      ;;
  esac
  [[ "$expected_sha" =~ ^[a-f0-9]{64}$ ]] || fail "兼容包 SHA-256 非法"
  [[ "$expected_size" =~ ^[0-9]+$ ]] || fail "兼容包大小非法"
  [[ "$expected_size" -gt 0 && "$expected_size" -le "$MAX_ARTIFACT_BYTES" ]] || \
    fail "兼容包大小超过安全范围"
  validate_https_host "$artifact_url"

  local current
  current="$(tr -d '[:space:]' <"${INSTALL_DIR}/VERSION")"
  if [[ "$current" == "$version" ]]; then
    printf 'JIYU_UPDATE_STATUS=noop\n'
    printf '当前已是 JIYU 兼容包 %s，无需更新。\n' "$version"
    return 0
  fi

  curl -fsSL --proto '=https' --proto-redir '=https' --max-filesize "$MAX_ARTIFACT_BYTES" \
    --connect-timeout 15 --max-time 900 -o "$artifact_file" "$artifact_url"
  [[ "$(wc -c <"$artifact_file" | tr -d ' ')" -le "$MAX_ARTIFACT_BYTES" ]] || \
    fail "兼容包超过下载安全上限"
  [[ "$(sha256sum "$artifact_file" | awk '{print $1}')" == "$expected_sha" ]] || fail "兼容包校验失败"
  [[ "$(wc -c <"$artifact_file" | tr -d ' ')" == "$expected_size" ]] || fail "兼容包大小不一致"
  file "$artifact_file" | grep -Eq 'ELF 64-bit.*(ARM aarch64|x86-64)' || fail "兼容包不是受支持的 Linux ELF"
  chmod 0755 "$artifact_file"

  local stage_output
  if ! stage_output="$(SUB2API_JIYU_VERSION="$version" "$MANAGER_PATH" stage-jiyu-build "$artifact_file" 2>&1)"; then
    fail "$stage_output"
  fi
  printf 'JIYU_UPDATE_STATUS=staged\n'
  printf 'JIYU 兼容包 %s 已校验并暂存，请在 WebUI 点击重启完成更新。\n' "$version"
}

main "$@"
