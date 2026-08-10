#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly SOURCE_DIR="${SCRIPT_DIR}/jiyu-image-mcp"
readonly INSTALL_DIR="${HOME}/.local/share/jiyu-image-mcp"
readonly CC_SWITCH_DB="${HOME}/.cc-switch/cc-switch.db"
readonly KEYCHAIN_SERVICE="JIYU AI 生图 API Key"
readonly MCP_ID="jiyu-ai-image"

fail() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令：$1"
}

set_keychain_key() {
  [[ "$(uname -s)" == "Darwin" ]] || fail "非 macOS 请使用 JIYU_IMAGE_API_KEY 安全环境变量"
  local api_key
  printf '请输入 JIYU 生图专用 Key（输入不会显示）：' >&2
  IFS= read -r -s api_key
  printf '\n' >&2
  [[ "${#api_key}" -ge 20 ]] || fail "Key 格式无效"
  /usr/bin/security add-generic-password -U -a "${USER}" -s "$KEYCHAIN_SERVICE" -w "$api_key" >/dev/null
  unset api_key
  printf '已写入 macOS 钥匙串服务“%s”。\n' "$KEYCHAIN_SERVICE"
}

backup_legacy_structure() {
  local backup_file="${INSTALL_DIR}/legacy-cc-switch-structure.json"
  local legacy_count
  legacy_count="$(sqlite3 "$CC_SWITCH_DB" \
    "SELECT COUNT(*) FROM mcp_servers WHERE id IN ('86gamestore-image','86gamestore_image');")"
  [[ "$legacy_count" -gt 0 ]] || return 0
  [[ ! -f "$backup_file" ]] || return 0
  sqlite3 -json "$CC_SWITCH_DB" \
    "SELECT id,name,server_config,enabled_claude,enabled_codex,enabled_gemini,enabled_opencode,enabled_hermes,enabled_grokbuild FROM mcp_servers WHERE id IN ('86gamestore-image','86gamestore_image');" | \
    jq 'map(.server_config |= (fromjson | if has("env") then .env = {} else . end))' >"$backup_file"
  chmod 0600 "$backup_file"
}

configure_cc_switch() {
  [[ -f "$CC_SWITCH_DB" ]] || fail "未找到 CC Switch 数据库：$CC_SWITCH_DB"
  require_command sqlite3
  require_command jq
  local node_bin server_config sql_config
  node_bin="$(command -v node)"
  server_config="$(jq -cn --arg command "$node_bin" --arg server "${INSTALL_DIR}/server.mjs" \
    '{type:"stdio",command:$command,args:[$server],startup_timeout_sec:120}')"
  [[ "$server_config" != *"'"* ]] || fail "安装路径包含 CC Switch 无法安全写入的单引号"
  sql_config="$server_config"
  backup_legacy_structure
  sqlite3 "$CC_SWITCH_DB" <<SQL
BEGIN IMMEDIATE;
DELETE FROM mcp_servers WHERE id IN ('86gamestore-image','86gamestore_image');
INSERT INTO mcp_servers (
  id,name,server_config,description,homepage,docs,tags,
  enabled_claude,enabled_codex,enabled_gemini,enabled_opencode,enabled_hermes,enabled_grokbuild
) VALUES (
  '${MCP_ID}','JIYU AI 生图','${sql_config}',
  '固定调用 JIYU AI 原生异步生图端点的中央单图 MCP',
  'https://jiyu.245334.xyz','https://jiyu.245334.xyz/custom/docs','["image","jiyu"]',
  1,1,0,1,0,0
)
ON CONFLICT(id) DO UPDATE SET
  name=excluded.name,server_config=excluded.server_config,description=excluded.description,
  homepage=excluded.homepage,docs=excluded.docs,tags=excluded.tags;
COMMIT;
SQL
}

install_mcp() {
  require_command node
  require_command npm
  install -d -m 0700 "$INSTALL_DIR"
  install -m 0600 "${SOURCE_DIR}/package.json" "${SOURCE_DIR}/package-lock.json" "$INSTALL_DIR/"
  install -m 0700 "${SOURCE_DIR}/server.mjs" "$INSTALL_DIR/server.mjs"
  npm ci --prefix "$INSTALL_DIR" --omit=dev --ignore-scripts --no-audit --no-fund >/dev/null
  configure_cc_switch
  printf 'JIYU AI 生图 MCP 已安装，并已同步到 CC Switch 的 Claude、Codex 和 OpenCode。\n'
}

show_status() {
  local installed=false configured=false keychain=false
  [[ -x "${INSTALL_DIR}/server.mjs" ]] && installed=true
  if [[ -f "$CC_SWITCH_DB" ]] && sqlite3 "$CC_SWITCH_DB" \
    "SELECT 1 FROM mcp_servers WHERE id='${MCP_ID}' LIMIT 1;" | grep -qx 1; then
    configured=true
  fi
  if [[ "$(uname -s)" == "Darwin" ]] && /usr/bin/security find-generic-password \
    -s "$KEYCHAIN_SERVICE" -w >/dev/null 2>&1; then
    keychain=true
  fi
  printf '安装文件：%s\nCC Switch：%s\n钥匙串：%s\n' "$installed" "$configured" "$keychain"
}

uninstall_mcp() {
  if [[ -f "$CC_SWITCH_DB" ]]; then
    sqlite3 "$CC_SWITCH_DB" "DELETE FROM mcp_servers WHERE id='${MCP_ID}';"
  fi
  rm -rf "$INSTALL_DIR"
  printf '已移除 JIYU AI 生图 MCP；钥匙串凭据保持不变。\n'
}

case "${1:-install}" in
  install)
    install_mcp
    ;;
  set-key)
    set_keychain_key
    ;;
  status)
    show_status
    ;;
  uninstall)
    uninstall_mcp
    ;;
  *)
    fail "用法：$0 [install|set-key|status|uninstall]"
    ;;
esac
