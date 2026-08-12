#!/usr/bin/env bash
set -Eeuo pipefail

# Sub2API 在 Oracle ARM 上的安装、升级、切换和回滚唯一入口。

readonly DEFAULT_VERSION="v0.1.172"
readonly GITHUB_REPOSITORY="Wei-Shaw/sub2api"
readonly GITHUB_API_URL="https://api.github.com/repos/${GITHUB_REPOSITORY}/releases/latest"
readonly GITHUB_RELEASE_URL="https://github.com/${GITHUB_REPOSITORY}/releases/download"
readonly INSTALL_DIR="/opt/sub2api"
readonly CONFIG_DIR="/etc/sub2api"
readonly ENV_FILE="${CONFIG_DIR}/sub2api.env"
readonly REDIS_CONFIG="${CONFIG_DIR}/redis.conf"
readonly BACKUP_ROOT="/var/backups/sub2api"
readonly STATE_DIR="/var/lib/sub2api-ops"
readonly MANAGER_PATH="/usr/local/sbin/openclaw-sub2api-manager"
readonly SUB2API_SERVICE="sub2api.service"
readonly REDIS_SERVICE="sub2api-redis.service"
readonly UPDATE_SERVICE="sub2api-update.service"
readonly UPDATE_TIMER="sub2api-update.timer"
readonly BACKUP_SERVICE="sub2api-backup.service"
readonly BACKUP_TIMER="sub2api-backup.timer"
readonly APACHE_SITE="${SUB2API_APACHE_SITE:-/etc/apache2/sites-available/frist-api.conf}"
readonly APACHE_ROLLBACK_FILE="${STATE_DIR}/apache-before-sub2api.conf"
readonly UPDATE_STATE_FILE="${STATE_DIR}/upstream-release.json"
readonly NEWAPI_SERVICE="openclaw-newapi.service"
readonly DOMAIN="${SUB2API_PUBLIC_DOMAIN:-jiyu.245334.xyz}"
readonly HEALTH_URL="http://127.0.0.1:18080/health"
readonly LOCK_FILE="/run/lock/sub2api-update.lock"
readonly JIYU_UPDATE_BROKER_PATH="/usr/local/sbin/sub2api-jiyu-update-broker"
readonly JIYU_UPDATE_CONFIG="${CONFIG_DIR}/jiyu-update.conf"
readonly JIYU_UPDATE_SUDOERS="/etc/sudoers.d/sub2api-jiyu-update"
readonly JIYU_UPDATE_DROPIN="/etc/systemd/system/${SUB2API_SERVICE}.d/jiyu-update.conf"
readonly JIYU_UPDATE_SOCKET_UNIT="/etc/systemd/system/sub2api-jiyu-update.socket"
readonly JIYU_UPDATE_SERVICE_UNIT="/etc/systemd/system/sub2api-jiyu-update@.service"
readonly JIYU_STAGE_STATE_FILE="${STATE_DIR}/jiyu-stage-pending"
readonly JIYU_STAGE_RESULT_FILE="${STATE_DIR}/jiyu-stage-last-result.json"
readonly CLOUDFLARE_ORIGIN_NFT="${CONFIG_DIR}/jiyu-cloudflare-origin.nft"
readonly CLOUDFLARE_ORIGIN_SERVICE="jiyu-cloudflare-origin.service"
readonly CLOUDFLARE_ORIGIN_UNIT="/etc/systemd/system/${CLOUDFLARE_ORIGIN_SERVICE}"
readonly CLOUDFLARE_ROLLBACK_UNIT="jiyu-cloudflare-origin-rollback"
readonly SITE_BRAND_NAME="${SUB2API_SITE_NAME:-JIYU AI}"
readonly SITE_BRAND_SUBTITLE="${SUB2API_SITE_SUBTITLE:-Unified AI API Gateway}"
readonly RECHARGE_PAGE_SLUG="recharge-center"
readonly CHAIN_STORE_ORIGIN="https://pay.ldxp.cn"
readonly CHAIN_STORE_URL="${CHAIN_STORE_ORIGIN}/shop/ZCUGEDMV"
readonly DOCS_PAGE_SLUG="docs"
readonly BRAND_LOGO_SOURCE="${SUB2API_BRAND_LOGO_SOURCE:-/usr/local/share/jiyu-ai/jiyu-ai-logo.png}"
readonly BRAND_LOGO_PUBLIC_PATH="/api/v1/pages/${DOCS_PAGE_SLUG}/images/jiyu-ai-logo.png"
readonly UPSTREAM_ALLOWLIST_HOSTS="api.openai.com,api.anthropic.com,api.deepseek.com,api.kimi.com,api.moonshot.ai,api.moonshot.cn,api.siliconflow.cn,open.bigmodel.cn,api.minimaxi.com,generativelanguage.googleapis.com,cloudcode-pa.googleapis.com,*.openai.azure.com,api.aigo0.com,www.huyunapi.com"
readonly PRICING_FALLBACK_URL="https://raw.githubusercontent.com/Wei-Shaw/model-price-repo/main/model_prices_and_context_window.json"
readonly PRICING_FALLBACK_HASH_URL="https://raw.githubusercontent.com/Wei-Shaw/model-price-repo/main/model_prices_and_context_window.sha256"
readonly PRICING_FALLBACK_DIR="${INSTALL_DIR}/resources/model-pricing"
readonly PRICING_FALLBACK_FILE="${PRICING_FALLBACK_DIR}/model_prices_and_context_window.json"
readonly PRICING_FALLBACK_HASH_FILE="${PRICING_FALLBACK_DIR}/model_prices_and_context_window.sha256"

log() {
  printf '[Sub2API] %s\n' "$*"
}

fail() {
  printf '[Sub2API] 错误: %s\n' "$*" >&2
  exit 1
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || fail "此操作必须使用 root 执行。"
}

require_linux() {
  [[ "$(uname -s)" == "Linux" ]] || fail "此脚本只允许在 Linux 服务器执行。"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令: $1"
}

prepare_config_directory() {
  install -d -m 0750 -o root -g root "$CONFIG_DIR"
  # 配置文件各自保持最小所有权；运行用户只获得父目录穿越权限，不能列目录。
  setfacl -m u:sub2api:--x,u:sub2api-redis:--x,m::r-x "$CONFIG_DIR"
  runuser -u sub2api -- test -x "$CONFIG_DIR" || fail "sub2api 无法穿越配置目录。"
  runuser -u sub2api-redis -- test -x "$CONFIG_DIR" || fail "Redis 无法穿越配置目录。"
  if [[ -f "$REDIS_CONFIG" ]]; then
    runuser -u sub2api-redis -- test -r "$REDIS_CONFIG" || fail "Redis 无法读取专用配置。"
  fi
}

random_hex() {
  openssl rand -hex "$1"
}

release_arch() {
  case "$(uname -m)" in
    aarch64 | arm64)
      printf 'arm64\n'
      ;;
    x86_64 | amd64)
      printf 'amd64\n'
      ;;
    *)
      fail "Sub2API 官方二进制暂不支持当前架构: $(uname -m)"
      ;;
  esac
}

validate_version() {
  [[ "$1" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "非法 Sub2API 版本号: $1"
}

validate_jiyu_version() {
  [[ "$1" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-jiyu\.[0-9]+$ ]] || fail "非法 JIYU 构建版本号: $1"
}

curl_release() {
  local url="$1"
  local output="$2"
  local curl_args=(
    -fsSL
    --retry 3
    --retry-delay 2
    --retry-all-errors
    -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28"
    -H "User-Agent: OpenClaw-Sub2API-Updater"
    -o "$output"
  )
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    curl_args+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
  fi
  curl "${curl_args[@]}" "$url"
}

latest_version() {
  local release_json
  release_json="$(mktemp)"
  curl_release "$GITHUB_API_URL" "$release_json"
  local version
  version="$(jq -r '.tag_name // empty' "$release_json")"
  rm -f "$release_json"
  validate_version "$version"
  printf '%s\n' "$version"
}

download_release() {
  local version="$1"
  local destination="$2"
  validate_version "$version"
  local arch version_without_prefix archive expected_checksum actual_checksum
  arch="$(release_arch)"
  version_without_prefix="${version#v}"
  archive="sub2api_${version_without_prefix}_linux_${arch}.tar.gz"

  mkdir -p "$destination"
  curl_release "${GITHUB_RELEASE_URL}/${version}/${archive}" "${destination}/${archive}"
  curl_release "${GITHUB_RELEASE_URL}/${version}/checksums.txt" "${destination}/checksums.txt"

  expected_checksum="$(awk -v archive="$archive" '$2 == archive {print $1}' "${destination}/checksums.txt")"
  [[ "$expected_checksum" =~ ^[0-9a-f]{64}$ ]] || fail "官方 checksums.txt 中找不到 ${archive}。"
  actual_checksum="$(sha256sum "${destination}/${archive}" | awk '{print $1}')"
  [[ "$actual_checksum" == "$expected_checksum" ]] || fail "${archive} SHA-256 校验失败。"

  tar -xzf "${destination}/${archive}" -C "$destination" sub2api
  [[ -s "${destination}/sub2api" ]] || fail "官方压缩包中缺少 sub2api 二进制。"
  chmod 0755 "${destination}/sub2api"
  log "已校验官方 ${version} ${arch} 发布包。"
}

wait_for_health() {
  local attempts="${1:-60}"
  local index
  for ((index = 1; index <= attempts; index += 1)); do
    if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

write_systemd_units() {
  local postgresql_unit
  postgresql_unit="$(postgresql_cluster_unit)"
  cat >"/etc/systemd/system/${REDIS_SERVICE}" <<'UNIT'
[Unit]
Description=Sub2API dedicated Redis
After=network.target

[Service]
Type=notify
User=sub2api-redis
Group=sub2api-redis
ExecStart=/usr/bin/redis-server /etc/sub2api/redis.conf --supervised systemd
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/sub2api-redis
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT

  cat >"/etc/systemd/system/${SUB2API_SERVICE}" <<UNIT
[Unit]
Description=Sub2API API gateway
After=network-online.target ${postgresql_unit} sub2api-redis.service
Wants=network-online.target
Requires=${postgresql_unit} sub2api-redis.service

[Service]
Type=simple
User=sub2api
Group=sub2api
WorkingDirectory=/opt/sub2api
EnvironmentFile=/etc/sub2api/sub2api.env
ExecStart=/opt/sub2api/sub2api
# WebUI 的"重启服务"接口会让进程正常退出；必须让 systemd 在正常退出后也拉起新构建，
# 否则 JIYU 暂存验证任务会在新进程出现前超时并触发不必要的自动回滚。
Restart=always
RestartSec=5
TimeoutStartSec=180
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/opt/sub2api
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT

  cat >"/etc/systemd/system/${UPDATE_SERVICE}" <<'UNIT'
[Unit]
Description=Check the pinned Sub2API build against the official GitHub release
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/openclaw-sub2api-manager check-upstream
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
UNIT

  cat >"/etc/systemd/system/${UPDATE_TIMER}" <<'UNIT'
[Unit]
Description=Daily Sub2API update check

[Timer]
OnCalendar=*-*-* 04:20:00 Asia/Singapore
RandomizedDelaySec=20m
Persistent=true
Unit=sub2api-update.service

[Install]
WantedBy=timers.target
UNIT

  cat >"/etc/systemd/system/${BACKUP_SERVICE}" <<'UNIT'
[Unit]
Description=Create a consistent local Sub2API backup
After=postgresql.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/openclaw-sub2api-manager backup
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
UNIT

  cat >"/etc/systemd/system/${BACKUP_TIMER}" <<'UNIT'
[Unit]
Description=Daily Sub2API PostgreSQL backup

[Timer]
OnCalendar=*-*-* 03:40:00 Asia/Singapore
RandomizedDelaySec=15m
Persistent=true
Unit=sub2api-backup.service

[Install]
WantedBy=timers.target
UNIT

  systemctl daemon-reload
}

postgresql_cluster_unit() {
  local version cluster port
  while read -r version cluster port _; do
    if [[ "$port" == "5432" ]]; then
      printf 'postgresql@%s-%s.service\n' "$version" "$cluster"
      return 0
    fi
  done < <(pg_lsclusters --no-header)
  fail "找不到监听 5432 的 PostgreSQL 实例。"
}

prepare_postgresql_runtime() {
  local pg_ctl
  pg_ctl="$(pg_config --bindir)/pg_ctl"
  [[ -x "$pg_ctl" ]] || fail "PostgreSQL pg_ctl 不可执行: ${pg_ctl}"

  # PostgreSQL 只获得 /var/log 的穿越权限，不能读取其他日志目录内容。
  chmod 1777 /dev/shm
  setfacl -m u:postgres:--x,m::--x /var/log
  runuser -u postgres -- test -x /var/log || fail "postgres 无法穿越 /var/log。"
  runuser -u postgres -- test -w /var/log/postgresql || fail "postgres 无法写入日志目录。"
  runuser -u postgres -- test -w /var/log/postgresql/postgresql-16-main.log || \
    fail "postgres 无法写入当前集群日志。"
}

postgresql_preflight() {
  local postgresql_unit pg_ctl
  postgresql_unit="$(postgresql_cluster_unit)"
  pg_ctl="$(pg_config --bindir)/pg_ctl"
  [[ -x "$pg_ctl" ]] || fail "PostgreSQL pg_ctl 不可执行: ${pg_ctl}"
  [[ "$(stat -c '%a' /dev/shm)" == "1777" ]] || fail "/dev/shm 权限不是 1777。"
  runuser -u postgres -- test -x /var/log || fail "postgres 无法穿越 /var/log。"
  runuser -u postgres -- test -w /var/log/postgresql || fail "postgres 无法写入日志目录。"
  runuser -u postgres -- test -w /var/log/postgresql/postgresql-16-main.log || \
    fail "postgres 无法写入当前集群日志。"
  systemctl is-active --quiet "$postgresql_unit" || fail "PostgreSQL 服务未运行。"
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d sub2api -Atc 'SELECT 1' | grep -qx '1' || \
    fail "PostgreSQL sub2api 数据库连通性检查失败。"
}

harden_postgresql_runtime() {
  require_root
  require_linux
  prepare_postgresql_runtime
  systemctl start "$(postgresql_cluster_unit)"
  postgresql_preflight
  log "PostgreSQL 运行权限和数据库连通性检查通过。"
}

configure_postgresql() {
  local database_password="$1"
  local postgresql_unit
  postgresql_unit="$(postgresql_cluster_unit)"
  prepare_postgresql_runtime
  systemctl enable --now "$postgresql_unit"

  if runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='sub2api'" | grep -qx '1'; then
    fail "PostgreSQL 已存在 sub2api 角色，拒绝覆盖非全新数据库。"
  fi
  if runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='sub2api'" | grep -qx '1'; then
    fail "PostgreSQL 已存在 sub2api 数据库，拒绝覆盖非全新数据库。"
  fi

  runuser -u postgres -- psql -v ON_ERROR_STOP=1 \
    -c "CREATE ROLE sub2api LOGIN PASSWORD '${database_password}'"
  runuser -u postgres -- createdb --owner=sub2api sub2api
}

write_runtime_config() {
  local database_password="$1"
  local redis_password="$2"
  local admin_password="$3"
  local jwt_secret="$4"
  local totp_key="$5"
  local admin_email="${SUB2API_ADMIN_EMAIL:-djblack1209@gmail.com}"

  cat >"$REDIS_CONFIG" <<EOF
bind 127.0.0.1
protected-mode yes
port 16379
supervised systemd
dir /var/lib/sub2api-redis
dbfilename dump.rdb
appendonly yes
appendfsync everysec
requirepass ${redis_password}
EOF
  chown root:sub2api-redis "$REDIS_CONFIG"
  chmod 0640 "$REDIS_CONFIG"

  cat >"$ENV_FILE" <<EOF
DATA_DIR=${INSTALL_DIR}/data
AUTO_SETUP=true
SERVER_HOST=127.0.0.1
SERVER_PORT=18080
SERVER_MODE=release
RUN_MODE=standard
DATABASE_HOST=127.0.0.1
DATABASE_PORT=5432
DATABASE_USER=sub2api
DATABASE_PASSWORD=${database_password}
DATABASE_DBNAME=sub2api
DATABASE_SSLMODE=disable
DATABASE_MAX_OPEN_CONNS=50
DATABASE_MAX_IDLE_CONNS=10
DATABASE_CONN_MAX_LIFETIME_MINUTES=30
DATABASE_CONN_MAX_IDLE_TIME_MINUTES=5
REDIS_HOST=127.0.0.1
REDIS_PORT=16379
REDIS_USERNAME=
REDIS_PASSWORD=${redis_password}
REDIS_DB=0
REDIS_POOL_SIZE=100
REDIS_MIN_IDLE_CONNS=10
REDIS_ENABLE_TLS=false
ADMIN_EMAIL=${admin_email}
ADMIN_PASSWORD=${admin_password}
JWT_SECRET=${jwt_secret}
JWT_EXPIRE_HOUR=24
TOTP_ENCRYPTION_KEY=${totp_key}
TZ=Asia/Singapore
SETUP_MIGRATION_TIMEOUT_SECONDS=180
SECURITY_URL_ALLOWLIST_ENABLED=true
SECURITY_URL_ALLOWLIST_ALLOW_INSECURE_HTTP=false
SECURITY_URL_ALLOWLIST_ALLOW_PRIVATE_HOSTS=false
SECURITY_URL_ALLOWLIST_UPSTREAM_HOSTS=${UPSTREAM_ALLOWLIST_HOSTS}
GATEWAY_OPENAI_WS_MODE_ROUTER_V2_ENABLED=true
EOF
  chown root:root "$ENV_FILE"
  chmod 0600 "$ENV_FILE"
}

apply_upstream_allowlist() {
  require_root
  require_linux
  [[ -f "$ENV_FILE" ]] || fail "找不到 Sub2API 环境配置: ${ENV_FILE}"

  local temporary_file env_backup
  temporary_file="$(mktemp)"
  env_backup="$(mktemp "${STATE_DIR}/upstream-allowlist-env.XXXXXXXX")"
  cp -a "$ENV_FILE" "$env_backup"
  awk -v hosts="$UPSTREAM_ALLOWLIST_HOSTS" '
    BEGIN { replaced = 0 }
    /^SECURITY_URL_ALLOWLIST_UPSTREAM_HOSTS=/ {
      print "SECURITY_URL_ALLOWLIST_UPSTREAM_HOSTS=" hosts
      replaced = 1
      next
    }
    { print }
    END {
      if (!replaced) print "SECURITY_URL_ALLOWLIST_UPSTREAM_HOSTS=" hosts
    }
  ' "$ENV_FILE" >"$temporary_file"
  chown root:root "$temporary_file"
  chmod 0600 "$temporary_file"
  mv -f "$temporary_file" "$ENV_FILE"
  if ! systemctl restart "$SUB2API_SERVICE" || ! wait_for_health 90; then
    cp -a "$env_backup" "$ENV_FILE"
    systemctl restart "$SUB2API_SERVICE" || true
    if ! wait_for_health 90; then
      fail "上游域名白名单应用失败，且回滚后健康检查仍未恢复；恢复副本保留在受限状态目录。"
    fi
    rm -f "$env_backup"
    fail "上游域名白名单应用失败，已恢复原配置。"
  fi
  rm -f "$env_backup"
  log "上游域名白名单已更新为当前生产账号使用的受信官方域名。"
}

set_jiyu_region_enforcement() {
  require_root
  require_linux
  [[ -f "$ENV_FILE" ]] || fail "找不到 Sub2API 环境配置: ${ENV_FILE}"

  local mode="$1" enabled temporary_file env_backup
  case "$mode" in
    enable) enabled=1 ;;
    disable) enabled=0 ;;
    *) fail "地域强制模式只能是 enable 或 disable。" ;;
  esac

  temporary_file="$(mktemp)"
  env_backup="$(mktemp "${STATE_DIR}/region-enforcement-env.XXXXXXXX")"
  cp -a "$ENV_FILE" "$env_backup"
  awk -v enabled="$enabled" '
    BEGIN { replaced = 0 }
    /^SUB2API_JIYU_REGION_ENFORCEMENT=/ {
      print "SUB2API_JIYU_REGION_ENFORCEMENT=" enabled
      replaced = 1
      next
    }
    { print }
    END {
      if (!replaced) print "SUB2API_JIYU_REGION_ENFORCEMENT=" enabled
    }
  ' "$ENV_FILE" >"$temporary_file"
  chown root:root "$temporary_file"
  chmod 0600 "$temporary_file"
  mv -f "$temporary_file" "$ENV_FILE"

  if ! systemctl restart "$SUB2API_SERVICE" || ! wait_for_health 90; then
    cp -a "$env_backup" "$ENV_FILE"
    systemctl restart "$SUB2API_SERVICE" || true
    if ! wait_for_health 90; then
      fail "地域强制配置应用失败，且回滚后健康检查仍未恢复；恢复副本保留在受限状态目录。"
    fi
    rm -f "$env_backup"
    fail "地域强制配置应用失败，已恢复原配置。"
  fi
  rm -f "$env_backup"
  if [[ "$enabled" == "1" ]]; then
    log "JIYU 地域强制已启用。"
  else
    log "JIYU 地域强制已关闭。"
  fi
}

set_openai_ws_mode_router() {
  require_root
  require_linux
  [[ -f "$ENV_FILE" ]] || fail "找不到 Sub2API 环境配置: ${ENV_FILE}"

  local enabled="$1"
  [[ "$enabled" == "true" || "$enabled" == "false" ]] || fail "WS 模式路由开关只能是 true 或 false。"

  local temporary_file
  temporary_file="$(mktemp)"
  awk -v enabled="$enabled" '
    BEGIN { replaced = 0 }
    /^GATEWAY_OPENAI_WS_MODE_ROUTER_V2_ENABLED=/ {
      print "GATEWAY_OPENAI_WS_MODE_ROUTER_V2_ENABLED=" enabled
      replaced = 1
      next
    }
    { print }
    END {
      if (!replaced) print "GATEWAY_OPENAI_WS_MODE_ROUTER_V2_ENABLED=" enabled
    }
  ' "$ENV_FILE" >"$temporary_file"
  chown root:root "$temporary_file"
  chmod 0600 "$temporary_file"
  mv -f "$temporary_file" "$ENV_FILE"

  systemctl restart "$SUB2API_SERVICE"
  wait_for_health 90 || fail "应用 OpenAI WS 模式路由配置后健康检查失败。"
  if [[ "$enabled" == "true" ]]; then
    log "OpenAI WS 模式路由已启用；API Key 账号需在 WebUI 中选择 HTTP 桥接。"
  else
    log "OpenAI WS 模式路由已关闭，已恢复旧版账号传输判定。"
  fi
}

install_clean() {
  require_root
  require_linux
  [[ -f /etc/os-release ]] || fail "无法识别 Linux 发行版。"
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID:-}" == "ubuntu" || "${ID:-}" == "debian" ]] || fail "当前只支持 Ubuntu/Debian。"
  [[ ! -e "$ENV_FILE" && ! -e "/etc/systemd/system/${SUB2API_SERVICE}" ]] || \
    fail "检测到 Sub2API 安装痕迹；全新安装不会覆盖现有实例。"

  local redis_was_installed=0
  if command -v redis-server >/dev/null 2>&1; then
    redis_was_installed=1
  fi

  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends \
    acl ca-certificates curl jq openssl postgresql postgresql-client redis-server tar

  for command_name in curl jq openssl pg_lsclusters psql redis-server setfacl sha256sum tar; do
    require_command "$command_name"
  done

  if [[ "$redis_was_installed" -eq 0 ]]; then
    systemctl disable --now redis-server.service >/dev/null 2>&1 || true
  fi

  getent passwd sub2api >/dev/null 2>&1 || \
    useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin sub2api
  getent passwd sub2api-redis >/dev/null 2>&1 || \
    useradd --system --home-dir /var/lib/sub2api-redis --shell /usr/sbin/nologin sub2api-redis

  install -d -m 0750 -o sub2api -g sub2api "$INSTALL_DIR" "${INSTALL_DIR}/data"
  prepare_config_directory
  install -d -m 0700 -o root -g root "$BACKUP_ROOT" "$STATE_DIR"
  install -d -m 0750 -o sub2api-redis -g sub2api-redis /var/lib/sub2api-redis

  local database_password redis_password admin_password jwt_secret totp_key release_dir
  database_password="$(random_hex 24)"
  redis_password="$(random_hex 24)"
  admin_password="$(random_hex 18)"
  jwt_secret="$(random_hex 32)"
  totp_key="$(random_hex 32)"
  release_dir="$(mktemp -d)"

  configure_postgresql "$database_password"
  write_runtime_config "$database_password" "$redis_password" "$admin_password" "$jwt_secret" "$totp_key"
  download_release "${SUB2API_INSTALL_VERSION:-$DEFAULT_VERSION}" "$release_dir"
  install -m 0755 -o sub2api -g sub2api "${release_dir}/sub2api" "${INSTALL_DIR}/sub2api"
  printf '%s\n' "${SUB2API_INSTALL_VERSION:-$DEFAULT_VERSION}" >"${INSTALL_DIR}/VERSION"
  chown sub2api:sub2api "${INSTALL_DIR}/VERSION"

  finish_install
  log "全新 Sub2API 已安装，未导入任何 New-API 用户、Key 或渠道。"
  log "管理账号保存在 ${ENV_FILE}，文件权限为 root-only。"
  show_status
}

finish_install() {
  require_root
  require_linux
  [[ -x "${INSTALL_DIR}/sub2api" && -f "$ENV_FILE" && -f "$REDIS_CONFIG" ]] || \
    fail "缺少 Sub2API 二进制或配置，无法收口安装。"

  chown root:sub2api-redis "$REDIS_CONFIG"
  chmod 0640 "$REDIS_CONFIG"
  chmod 0600 "$ENV_FILE"
  prepare_config_directory
  if [[ "$(readlink -f "${BASH_SOURCE[0]}")" != "$(readlink -f "$MANAGER_PATH")" ]]; then
    install -m 0755 -o root -g root "${BASH_SOURCE[0]}" "$MANAGER_PATH"
  fi
  write_systemd_units

  local postgresql_unit
  postgresql_unit="$(postgresql_cluster_unit)"
  systemctl enable "$postgresql_unit" "$REDIS_SERVICE" "$SUB2API_SERVICE" \
    "$BACKUP_TIMER" "$UPDATE_TIMER"
  systemctl start "$postgresql_unit"
  systemctl restart "$REDIS_SERVICE"
  systemctl restart "$SUB2API_SERVICE"

  if ! wait_for_health 90; then
    journalctl -u "$SUB2API_SERVICE" -n 80 --no-pager >&2
    fail "Sub2API 首次启动未通过健康检查。"
  fi

  apply_branding
  apply_recharge_placeholder
  apply_brand_asset
  apply_docs_page
  apply_upstream_allowlist
  harden_apache_admin_updates
  sed -i 's/^AUTO_SETUP=true$/AUTO_SETUP=false/' "$ENV_FILE"
  systemctl start "$BACKUP_TIMER" "$UPDATE_TIMER"
}

site_logo_data_uri() {
  printf 'data:image/svg+xml;base64,'
  base64 <<'SVG' | tr -d '\n'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2048 2048"><rect x="128" y="128" width="1792" height="1792" rx="256" fill="#F8FAFC" stroke="#111827" stroke-width="64"/><path d="M448 480H992V1180C992 1460 820 1620 520 1620H368V1320H512C622 1320 672 1260 672 1150V780H448V480Z" fill="#111827"/><path d="M848 480H1168L1344 800L1520 480H1840L1504 1052V1620H1184V1052L848 480Z" fill="#0F766E"/><circle cx="1344" cy="800" r="88" fill="#F97316"/></svg>
SVG
}

apply_branding() {
  require_root
  require_linux
  require_command psql

  local site_logo
  site_logo="$(site_logo_data_uri)"
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d sub2api \
    -v site_name="$SITE_BRAND_NAME" -v site_subtitle="$SITE_BRAND_SUBTITLE" \
    -v site_logo="$site_logo" <<'SQL'
INSERT INTO settings (key, value, updated_at)
VALUES
  ('site_name', :'site_name', NOW()),
  ('site_subtitle', :'site_subtitle', NOW()),
  ('site_logo', :'site_logo', NOW())
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value, updated_at = NOW();
SQL

  systemctl restart "$SUB2API_SERVICE"
  wait_for_health 90 || fail "应用 JIYU AI 品牌后健康检查失败。"
  log "站点品牌和 JY Logo 已设置为 ${SITE_BRAND_NAME}。"
}

apply_brand_asset() {
  require_root
  require_linux
  [[ -f "$BRAND_LOGO_SOURCE" ]] || fail "找不到 JIYU AI 图形 Logo: ${BRAND_LOGO_SOURCE}"

  local page_assets_dir
  # Sub2API 将 /pages/<slug>/images/* 映射到 data/pages/<slug>/*。
  page_assets_dir="${INSTALL_DIR}/data/pages/${DOCS_PAGE_SLUG}"
  install -d -m 0750 -o sub2api -g sub2api "$page_assets_dir"
  install -m 0644 -o sub2api -g sub2api \
    "$BRAND_LOGO_SOURCE" "${page_assets_dir}/jiyu-ai-logo.png"

  systemctl restart "$SUB2API_SERVICE"
  wait_for_health 90 || fail "发布 JIYU AI 图形 Logo 后健康检查失败。"
  curl -fsS --retry 10 --retry-delay 1 --retry-all-errors --max-time 15 \
    "https://${DOMAIN}${BRAND_LOGO_PUBLIC_PATH}" >/dev/null || \
    fail "JIYU AI 图形 Logo 公网地址不可用。"
  log "JIYU AI 图形 Logo 已发布到 ${BRAND_LOGO_PUBLIC_PATH}。"
}

apply_recharge_csp_policy() {
  local config_file="${INSTALL_DIR}/data/config.yaml"
  local current_policy
  local config_temp

  require_command curl
  require_command python3
  [[ -f "$config_file" ]] || fail "找不到 Sub2API 配置文件: ${config_file}"

  current_policy="$(
    curl -fsS -D - -o /dev/null --max-time 15 "$HEALTH_URL" |
      awk 'BEGIN { IGNORECASE=1 } /^Content-Security-Policy:/ {
        sub(/^[^:]+:[[:space:]]*/, ""); sub(/\r$/, ""); print; exit
      }'
  )"
  [[ -n "$current_policy" ]] || fail "无法读取 Sub2API 当前有效 CSP。"

  config_temp="$(mktemp "${config_file}.csp.XXXXXX")"
  if ! CSP_ORIGIN="$CHAIN_STORE_ORIGIN" EFFECTIVE_CSP="$current_policy" \
    python3 - "$config_file" "$config_temp" <<'PY'
import os
import re
import sys

import yaml

source_path, target_path = sys.argv[1:]
origin = os.environ["CSP_ORIGIN"]
effective_policy = os.environ["EFFECTIVE_CSP"]

with open(source_path, "r", encoding="utf-8") as source:
    config = yaml.safe_load(source) or {}

if not isinstance(config, dict):
    raise SystemExit("Sub2API 配置根节点不是对象")

security = config.setdefault("security", {})
if not isinstance(security, dict):
    raise SystemExit("Sub2API security 配置不是对象")
csp = security.setdefault("csp", {})
if not isinstance(csp, dict):
    raise SystemExit("Sub2API security.csp 配置不是对象")

policy = csp.get("policy")
if not isinstance(policy, str) or not policy.strip():
    policy = effective_policy
policy = re.sub(r"'nonce-[^']+'", "__CSP_NONCE__", policy)

directives = [item.strip() for item in policy.split(";") if item.strip()]
result = []
frame_sources = []
frame_index = None
for directive in directives:
    tokens = directive.split()
    if not tokens:
        continue
    name = tokens[0].lower()
    sources = [token for token in tokens[1:] if token != origin]
    if name == "frame-src":
        if frame_index is None:
            frame_index = len(result)
        for source in sources:
            if source not in frame_sources:
                frame_sources.append(source)
        continue
    result.append(" ".join([tokens[0], *sources]))

frame_sources.append(origin)
frame_directive = " ".join(["frame-src", *frame_sources])
if frame_index is None:
    result.append(frame_directive)
else:
    result.insert(frame_index, frame_directive)

origin_directives = [item for item in result if origin in item.split()[1:]]
if origin_directives != [frame_directive] or frame_directive.split().count(origin) != 1:
    raise SystemExit("链动小铺来源必须且只能出现一次于 frame-src")

csp["enabled"] = True
csp["policy"] = "; ".join(result) + ";"

with open(target_path, "w", encoding="utf-8") as target:
    yaml.safe_dump(config, target, allow_unicode=True, sort_keys=False)
PY
  then
    rm -f "$config_temp"
    fail "无法写入 Sub2API CSP 配置。"
  fi

  chown --reference="$config_file" "$config_temp"
  chmod --reference="$config_file" "$config_temp"
  mv -f "$config_temp" "$config_file"
}

apply_recharge_center() {
  require_root
  require_linux
  require_command psql

  local pages_dir
  local effective_csp
  pages_dir="${INSTALL_DIR}/data/pages"
  install -d -m 0750 -o sub2api -g sub2api "$pages_dir"

  cat >"${pages_dir}/${RECHARGE_PAGE_SLUG}.md" <<MARKDOWN
[打开 JIYU AI 链动小铺](${CHAIN_STORE_URL})
MARKDOWN

  chown sub2api:sub2api "${pages_dir}/${RECHARGE_PAGE_SLUG}.md"
  chmod 0640 "${pages_dir}/${RECHARGE_PAGE_SLUG}.md"

  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d sub2api <<'SQL'
WITH current_items AS (
  SELECT COALESCE(
    (SELECT value::jsonb FROM settings WHERE key = 'custom_menu_items'),
    '[]'::jsonb
  ) AS items
), filtered_items AS (
  SELECT COALESCE(
    jsonb_agg(item) FILTER (WHERE item->>'id' <> 'recharge-center'),
    '[]'::jsonb
  ) AS items
  FROM current_items, LATERAL jsonb_array_elements(items) AS item
)
INSERT INTO settings (key, value, updated_at)
SELECT 'custom_menu_items', (
  items || jsonb_build_array(jsonb_build_object(
    'id', 'recharge-center',
    'label', '充值中心',
    'icon_svg', '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="14" x="2" y="5" rx="2"/><path d="M16 13h.01M2 10h20"/></svg>',
    'url', 'md:recharge-center',
    'page_slug', 'recharge-center',
    'visibility', 'user',
    'sort_order', 80
  ))
)::text, NOW()
FROM filtered_items
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value, updated_at = NOW();
SQL

  apply_recharge_csp_policy
  systemctl restart "$SUB2API_SERVICE"
  wait_for_health 90 || fail "应用充值中心页面后健康检查失败。"
  effective_csp="$(
    curl -fsS -D - -o /dev/null --max-time 15 "https://${DOMAIN}/health" |
      awk 'BEGIN { IGNORECASE=1 } /^Content-Security-Policy:/ {
        sub(/^[^:]+:[[:space:]]*/, ""); sub(/\r$/, ""); print; exit
      }'
  )"
  CSP_ORIGIN="$CHAIN_STORE_ORIGIN" CSP_POLICY="$effective_csp" python3 <<'PY'
import os

origin = os.environ["CSP_ORIGIN"]
directives = [item.strip().split() for item in os.environ["CSP_POLICY"].split(";") if item.strip()]
matches = [(tokens[0].lower(), tokens[1:].count(origin)) for tokens in directives if origin in tokens[1:]]
if matches != [("frame-src", 1)]:
    raise SystemExit("生产 CSP 未把链动小铺来源精确限制到 frame-src")
PY
  curl -fsS --max-time 20 "https://${DOMAIN}/custom/${RECHARGE_PAGE_SLUG}" >/dev/null || \
    fail "充值中心公网页面不可用。"
  log "充值中心已启用专用公开整店嵌入；固定地址不携带站内用户参数。"
}

apply_docs_page() {
  require_root
  require_linux
  require_command psql

  local pages_dir
  pages_dir="${INSTALL_DIR}/data/pages"
  install -d -m 0750 -o sub2api -g sub2api "$pages_dir"

  cat >"${pages_dir}/${DOCS_PAGE_SLUG}.md" <<'MARKDOWN'
# JIYU AI 使用文档

> 当前为邀请内测。目标地区规则：中国大陆 IP 只显示国内模型，境外 IP 显示全部模型；账户、余额、订单、API 密钥和模型请求仍以海外主系统为唯一事实源。技术分流尚未完成真实生产回读前，请以线上实际目录和 API 返回为准。对于仍受制裁、出口管制或相关服务限制的地区，服务仍不开放。

## 下载 CC Switch

官方版本：**v3.19.2**（2026-08-06 发布）

<div class="cc-switch-download-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:16px 0 24px">
  <a class="cc-switch-download-link cc-switch-download-link--mac" href="https://github.com/farion1231/cc-switch/releases/download/v3.19.2/CC-Switch-v3.19.2-macOS.dmg" target="_blank" rel="noopener noreferrer" style="display:flex;align-items:center;justify-content:center;box-sizing:border-box;width:100%;min-width:0;min-height:52px;padding:10px 8px;border:1px solid transparent;border-radius:6px;background:#0f766e;color:#fff;text-align:center;line-height:1.35;overflow-wrap:anywhere;text-decoration:none;font-weight:650">下载 macOS</a>
  <a class="cc-switch-download-link cc-switch-download-link--windows" href="https://github.com/farion1231/cc-switch/releases/download/v3.19.2/CC-Switch-v3.19.2-Windows.msi" target="_blank" rel="noopener noreferrer" style="display:flex;align-items:center;justify-content:center;box-sizing:border-box;width:100%;min-width:0;min-height:52px;padding:10px 8px;border:1px solid transparent;border-radius:6px;background:#111827;color:#fff;text-align:center;line-height:1.35;overflow-wrap:anywhere;text-decoration:none;font-weight:650">下载 Windows</a>
  <a class="cc-switch-download-link cc-switch-download-link--linux" href="https://github.com/farion1231/cc-switch/releases/download/v3.19.2/CC-Switch-v3.19.2-Linux-x86_64.AppImage" target="_blank" rel="noopener noreferrer" style="display:flex;align-items:center;justify-content:center;box-sizing:border-box;width:100%;min-width:0;min-height:52px;padding:10px 8px;border:1px solid transparent;border-radius:6px;background:#c2410c;color:#fff;text-align:center;line-height:1.35;overflow-wrap:anywhere;text-decoration:none;font-weight:650">下载 Linux</a>
  <a class="cc-switch-download-link cc-switch-download-link--all" href="https://github.com/farion1231/cc-switch/releases/latest" target="_blank" rel="noopener noreferrer" style="display:flex;align-items:center;justify-content:center;box-sizing:border-box;width:100%;min-width:0;min-height:52px;padding:10px 8px;border:1px solid #64748b;border-radius:6px;background:transparent;color:inherit;text-align:center;line-height:1.35;overflow-wrap:anywhere;text-decoration:none;font-weight:650">全部官方版本</a>
</div>

## 一键导入

1. 打开 [API 密钥](/keys)，创建一个仅供自己使用的 Key。
2. 在该 Key 右侧点击 **导入到 CCS**，浏览器询问时允许打开 CC Switch。
3. 在 CC Switch 中选择 Claude、Codex、OpenCode、Gemini 或其他目标客户端，确认后完成导入。

<a href="/keys" style="display:inline-flex;align-items:center;padding:9px 14px;border-radius:6px;background:#0f766e;color:#fff;text-decoration:none;font-weight:650">打开 API 密钥页</a>

导入链接只把当前站点地址和你选择的 Key 交给本机 CC Switch。请勿把导入链接、Key 或配置截图发送给他人。

## 手动配置

- OpenAI 兼容地址：`https://jiyu.245334.xyz/v1`
- Claude 兼容地址：`https://jiyu.245334.xyz`
- 鉴权：使用 API 密钥页创建的 Key

连接失败时，先确认 Key 已启用、余额充足，并在 [渠道状态](/monitor) 查看当前可用渠道。
MARKDOWN

  chown sub2api:sub2api "${pages_dir}/${DOCS_PAGE_SLUG}.md"
  chmod 0640 "${pages_dir}/${DOCS_PAGE_SLUG}.md"

  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d sub2api <<'SQL'
WITH current_items AS (
  SELECT COALESCE(
    (SELECT value::jsonb FROM settings WHERE key = 'custom_menu_items'),
    '[]'::jsonb
  ) AS items
), filtered_items AS (
  SELECT COALESCE(
    jsonb_agg(item) FILTER (WHERE item->>'id' <> 'docs'),
    '[]'::jsonb
  ) AS items
  FROM current_items, LATERAL jsonb_array_elements(items) AS item
)
INSERT INTO settings (key, value, updated_at)
SELECT 'custom_menu_items', (
  items || jsonb_build_array(jsonb_build_object(
    'id', 'docs',
    'label', '文档',
    'icon_svg', '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/></svg>',
    'url', 'md:docs',
    'page_slug', 'docs',
    'visibility', 'user',
    'sort_order', 70
  ))
)::text, NOW()
FROM filtered_items
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value, updated_at = NOW();
SQL

  systemctl restart "$SUB2API_SERVICE"
  wait_for_health 90 || fail "应用 JIYU AI 文档页后健康检查失败。"
  log "左侧文档入口和 CC Switch 下载、导入说明已应用。"
}

apply_terms_page() {
  require_root
  require_linux
  require_command psql

  # 只替换过时的地区总禁用句，保留其余法律文本和文档顺序。
  local replacement terms_revision agreement_state
  replacement='**地区展示与服务范围：** 中国大陆 IP 只显示并可使用国内模型；境外 IP 显示全部模型。账户、余额、订单、API 密钥和模型请求继续由海外主系统统一处理，地区展示不创建第二套账户、余额或账本。大陆/境外技术分流尚未完成真实生产回读前，请以线上实际目录和 API 返回为准。对于仍受联合国、新加坡、美国、欧盟或相关服务提供方制裁、出口管制或服务限制的国家和地区，服务仍不开放。不得使用代理、虚假身份或其他方式规避适用限制。'
  terms_revision="$(printf '%s' "$replacement" | sha256sum | awk '{print $1}')"

  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d sub2api \
    -v replacement="$replacement" -v revision="$terms_revision" <<'SQL'
WITH current AS (
  SELECT value::jsonb AS documents
  FROM settings
  WHERE key = 'login_agreement_documents'
), updated AS (
  SELECT jsonb_agg(
    CASE
      WHEN item->>'id' = 'terms' THEN jsonb_set(
        item,
        '{content_md}',
        to_jsonb(replace(
          item->>'content_md',
          $$**JIYU AI 不向中国大陆以及受联合国、新加坡、美国、欧盟或相关服务提供方制裁、出口管制或服务限制的国家和地区开放。**不得使用代理、虚假身份或其他方式规避地区限制。$$,
          :'replacement'
        ))
      )
      ELSE item
    END
    ORDER BY ordinal
  )::text AS documents
  FROM current, jsonb_array_elements(current.documents) WITH ORDINALITY AS expanded(item, ordinal)
)
UPDATE settings
SET value = updated.documents, updated_at = NOW()
FROM updated
WHERE settings.key = 'login_agreement_documents';

INSERT INTO settings (key, value, updated_at)
VALUES ('login_agreement_revision', :'revision', NOW())
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value, updated_at = NOW();
SQL

  agreement_state="$(runuser -u postgres -- psql -d sub2api -Atc "SELECT CASE WHEN value ILIKE '%地区展示与服务范围%' AND value NOT ILIKE '%不向中国大陆以及%' THEN 'ok' ELSE 'invalid' END FROM settings WHERE key='login_agreement_documents'")"
  [[ "$agreement_state" == "ok" ]] || fail "登录条款地区文案回读失败。"
  systemctl restart "$SUB2API_SERVICE"
  wait_for_health 90 || fail "应用登录条款后健康检查失败。"
  log "登录条款已移除中国大陆总禁用表述，并明确地区展示目标及真实回读前置条件。"
}

backup_database() {
  local destination="$1"
  postgresql_preflight
  install -d -m 0700 -o root -g root "$destination"
  runuser -u postgres -- pg_dump --format=custom sub2api >"${destination}/sub2api.dump"
  local required_file
  for required_file in \
    "${INSTALL_DIR}/sub2api" "${INSTALL_DIR}/VERSION" "$ENV_FILE" \
    "$REDIS_CONFIG" "$APACHE_SITE"; do
    if [[ -e "$required_file" ]]; then
      cp -a "$required_file" "${destination}/"
    fi
  done
  if [[ -f "${INSTALL_DIR}/data/config.yaml" ]]; then
    cp -a "${INSTALL_DIR}/data/config.yaml" "${destination}/"
  fi
  if [[ -d "${INSTALL_DIR}/data/pages" ]]; then
    cp -a "${INSTALL_DIR}/data/pages" "${destination}/pages"
  fi
  if [[ -d "$PRICING_FALLBACK_DIR" ]]; then
    cp -a "$PRICING_FALLBACK_DIR" "${destination}/model-pricing"
  fi
  if [[ -d /usr/local/share/jiyu-ai ]]; then
    cp -a /usr/local/share/jiyu-ai "${destination}/brand-assets"
  fi
  for required_file in \
    "/etc/systemd/system/${SUB2API_SERVICE}" \
    "/etc/systemd/system/${REDIS_SERVICE}" \
    "/etc/systemd/system/${UPDATE_SERVICE}" \
    "/etc/systemd/system/${UPDATE_TIMER}" \
    "/etc/systemd/system/${BACKUP_SERVICE}" \
    "/etc/systemd/system/${BACKUP_TIMER}"; do
    if [[ -e "$required_file" ]]; then
      cp -a "$required_file" "${destination}/"
    fi
  done
  find "$destination" -maxdepth 2 -type f ! -name SHA256SUMS -print0 | sort -z | \
    xargs -0 sha256sum >"${destination}/SHA256SUMS"
  chmod -R go-rwx "$destination"
}

daily_backup() {
  require_root
  require_linux
  local timestamp backup_dir
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="${BACKUP_ROOT}/daily-${timestamp}"
  backup_database "$backup_dir"
  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'daily-*' -mtime +30 -exec rm -rf -- {} +
  log "Sub2API 一致性备份已保存到 ${backup_dir}。"
}

install_pricing_fallback() {
  require_root
  require_linux
  require_command curl
  require_command jq
  require_command sha256sum

  local timestamp backup_dir temporary_json temporary_hash expected_hash actual_hash staged_json staged_hash
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="${BACKUP_ROOT}/pricing-fallback-${timestamp}"
  backup_database "$backup_dir"

  temporary_json="$(mktemp)"
  temporary_hash="$(mktemp)"
  trap 'rm -f "${temporary_json:-}" "${temporary_hash:-}" "${staged_json:-}" "${staged_hash:-}"' RETURN
  curl -fsSL --retry 3 --retry-all-errors --max-time 60 "$PRICING_FALLBACK_URL" -o "$temporary_json"
  curl -fsSL --retry 3 --retry-all-errors --max-time 30 "$PRICING_FALLBACK_HASH_URL" -o "$temporary_hash"
  expected_hash="$(awk 'NR == 1 { print $1 }' "$temporary_hash")"
  [[ "$expected_hash" =~ ^[0-9a-fA-F]{64}$ ]] || fail "官方价格回退校验文件格式无效。"
  actual_hash="$(sha256sum "$temporary_json" | awk '{print $1}')"
  [[ "${actual_hash,,}" == "${expected_hash,,}" ]] || fail "官方价格回退文件 SHA-256 校验失败。"
  jq -e 'type == "object" and length > 0' "$temporary_json" >/dev/null || fail "官方价格回退文件不是非空 JSON 对象。"

  install -d -m 0755 -o sub2api -g sub2api "$PRICING_FALLBACK_DIR"
  staged_json="${PRICING_FALLBACK_FILE}.new"
  staged_hash="${PRICING_FALLBACK_HASH_FILE}.new"
  install -m 0644 -o sub2api -g sub2api "$temporary_json" "$staged_json"
  printf '%s  %s\n' "$actual_hash" "model_prices_and_context_window.json" | install -m 0644 -o sub2api -g sub2api /dev/stdin "$staged_hash"
  mv -f "$staged_json" "$PRICING_FALLBACK_FILE"
  mv -f "$staged_hash" "$PRICING_FALLBACK_HASH_FILE"
  systemctl restart "$SUB2API_SERVICE"
  if ! wait_for_health 90; then
    [[ -f "${backup_dir}/model-pricing/model_prices_and_context_window.json" ]] || fail "价格回退资源上线失败且备份中没有旧资源，拒绝继续。"
    cp -a "${backup_dir}/model-pricing/." "$PRICING_FALLBACK_DIR/"
    systemctl restart "$SUB2API_SERVICE"
    wait_for_health 90 || fail "价格回退资源回滚后服务健康检查仍失败。"
    fail "价格回退资源上线失败，已恢复备份。"
  fi
  log "官方价格回退资源已校验、原子安装并由服务加载；备份位于 ${backup_dir}。"
}

restore_database() {
  local dump_file="$1"
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='sub2api' AND pid <> pg_backend_pid()"
  runuser -u postgres -- dropdb --if-exists sub2api
  runuser -u postgres -- createdb --owner=sub2api sub2api
  runuser -u postgres -- pg_restore --exit-on-error --clean --if-exists \
    --no-owner --role=sub2api --dbname=sub2api <"$dump_file"
}

update_sub2api() {
  require_root
  require_linux
  require_command flock
  [[ "${SUB2API_ALLOW_UPSTREAM_BINARY_UPDATE:-0}" == "1" ]] || \
    fail "当前运行 JIYU 品牌构建；官方二进制只能先进入构建和验收流程，不能直接覆盖生产。"
  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "已有 Sub2API 升级任务正在运行。"
  postgresql_preflight

  [[ -x "${INSTALL_DIR}/sub2api" && -f "${INSTALL_DIR}/VERSION" ]] || \
    fail "未检测到可升级的 Sub2API。"
  local current latest release_dir timestamp backup_dir
  current="$(tr -d '[:space:]' <"${INSTALL_DIR}/VERSION")"
  latest="$(latest_version)"
  validate_version "$current"
  if [[ "$current" == "$latest" ]]; then
    log "当前 ${current} 已是 GitHub 最新稳定版。"
    return 0
  fi

  release_dir="$(mktemp -d)"
  download_release "$latest" "$release_dir"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="${BACKUP_ROOT}/update-${current}-to-${latest}-${timestamp}"
  backup_database "$backup_dir"

  systemctl stop "$SUB2API_SERVICE"
  install -m 0755 -o sub2api -g sub2api "${release_dir}/sub2api" "${INSTALL_DIR}/sub2api"
  printf '%s\n' "$latest" >"${INSTALL_DIR}/VERSION"
  chown sub2api:sub2api "${INSTALL_DIR}/VERSION"
  systemctl start "$SUB2API_SERVICE"

  if ! wait_for_health 90; then
    log "新版本健康检查失败，正在恢复旧二进制和数据库。"
    systemctl stop "$SUB2API_SERVICE" || true
    install -m 0755 -o sub2api -g sub2api "${backup_dir}/sub2api" "${INSTALL_DIR}/sub2api"
    install -m 0644 -o sub2api -g sub2api "${backup_dir}/VERSION" "${INSTALL_DIR}/VERSION"
    restore_database "${backup_dir}/sub2api.dump"
    systemctl start "$SUB2API_SERVICE"
    wait_for_health 90 || fail "自动回滚后健康检查仍失败，需要人工查看 journalctl。"
    fail "升级到 ${latest} 失败，已自动恢复 ${current}。"
  fi

  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'update-*' -mtime +30 -exec rm -rf -- {} +
  log "Sub2API 已从 ${current} 安全升级到 ${latest}。"
}

install_jiyu_build() {
  require_root
  require_linux
  require_command flock
  local candidate="${2:-}"
  local version="${SUB2API_JIYU_VERSION:-v0.1.172-jiyu.1}"
  [[ -n "$candidate" && -f "$candidate" && -x "$candidate" ]] || \
    fail "请提供已验证的 JIYU Linux 二进制路径。"
  validate_jiyu_version "$version"
  file "$candidate" | grep -Eq 'ELF 64-bit.*(ARM aarch64|x86-64)' || \
    fail "JIYU 二进制不是受支持的 Linux ELF。"

  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "已有 Sub2API 发布任务正在运行。"
  postgresql_preflight

  local timestamp backup_dir
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="${BACKUP_ROOT}/jiyu-${version}-${timestamp}"
  backup_database "$backup_dir"

  systemctl stop "$SUB2API_SERVICE"
  install -m 0755 -o sub2api -g sub2api "$candidate" "${INSTALL_DIR}/sub2api"
  printf '%s\n' "$version" >"${INSTALL_DIR}/VERSION"
  chown sub2api:sub2api "${INSTALL_DIR}/VERSION"
  systemctl start "$SUB2API_SERVICE"

  if ! wait_for_health 90; then
    log "JIYU 构建健康检查失败，正在恢复发布前版本和数据库。"
    systemctl stop "$SUB2API_SERVICE" || true
    install -m 0755 -o sub2api -g sub2api "${backup_dir}/sub2api" "${INSTALL_DIR}/sub2api"
    install -m 0644 -o sub2api -g sub2api "${backup_dir}/VERSION" "${INSTALL_DIR}/VERSION"
    restore_database "${backup_dir}/sub2api.dump"
    systemctl start "$SUB2API_SERVICE"
    wait_for_health 90 || fail "自动回滚后健康检查仍失败，需要人工查看 journalctl。"
    fail "JIYU 构建发布失败，已恢复发布前版本。"
  fi

  log "JIYU 构建 ${version} 已发布；发布前备份位于 ${backup_dir}。"
  show_status
}

stage_jiyu_build() {
  require_root
  require_linux
  require_command flock
  require_command systemd-run
  local candidate="${2:-}"
  local version="${SUB2API_JIYU_VERSION:-}"
  [[ -n "$candidate" && -f "$candidate" && -x "$candidate" ]] || \
    fail "请提供已验证且可执行的 JIYU Linux 二进制路径。"
  validate_jiyu_version "$version"
  file "$candidate" | grep -Eq 'ELF 64-bit.*(ARM aarch64|x86-64)' || \
    fail "JIYU 二进制不是受支持的 Linux ELF。"

  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "已有 Sub2API 发布任务正在运行。"
  postgresql_preflight

  local timestamp backup_dir staged_binary staged_version expected_sha old_pid state_file
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="${BACKUP_ROOT}/jiyu-stage-${version}-${timestamp}"
  backup_database "$backup_dir"
  staged_binary="${INSTALL_DIR}/.sub2api-jiyu-stage"
  staged_version="${INSTALL_DIR}/.VERSION-jiyu-stage"

  install -m 0755 -o sub2api -g sub2api "$candidate" "$staged_binary"
  printf '%s\n' "$version" >"$staged_version"
  chown sub2api:sub2api "$staged_version"
  expected_sha="$(sha256sum "$staged_binary" | awk '{print $1}')"
  old_pid="$(systemctl show --property MainPID --value "$SUB2API_SERVICE")"
  [[ "$old_pid" =~ ^[0-9]+$ ]] || old_pid=0
  install -d -m 0700 -o root -g root "$STATE_DIR"
  state_file="$(mktemp)"
  printf 'VERSION=%s\nBACKUP_DIR=%s\nEXPECTED_SHA=%s\nOLD_PID=%s\n' \
    "$version" "$backup_dir" "$expected_sha" "$old_pid" >"$state_file"
  install -m 0600 -o root -g root "$state_file" "$JIYU_STAGE_STATE_FILE"
  rm -f "$state_file"
  mv -f "$staged_binary" "${INSTALL_DIR}/sub2api"
  mv -f "$staged_version" "${INSTALL_DIR}/VERSION"
  if ! systemd-run \
    --unit="sub2api-jiyu-stage-verify-${timestamp,,}" \
    --on-active=5s \
    --property=Type=oneshot \
    --collect \
    "$MANAGER_PATH" verify-jiyu-stage >/dev/null; then
    install -m 0755 -o sub2api -g sub2api "${backup_dir}/sub2api" "${INSTALL_DIR}/sub2api"
    install -m 0644 -o sub2api -g sub2api "${backup_dir}/VERSION" "${INSTALL_DIR}/VERSION"
    rm -f "$JIYU_STAGE_STATE_FILE"
    fail "无法启动独立验证任务，已撤销暂存。"
  fi
  log "JIYU 构建 ${version} 已原子暂存；WebUI 重启后将独立核对运行哈希和健康状态，失败自动回滚。"
}

write_jiyu_stage_result() {
  local status="$1"
  local version="$2"
  local message="$3"
  local temporary_file
  temporary_file="$(mktemp)"
  jq -n \
    --arg status "$status" \
    --arg version "$version" \
    --arg message "$message" \
    --arg checked_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{status:$status,version:$version,message:$message,checked_at:$checked_at}' \
    >"$temporary_file"
  install -m 0600 -o root -g root "$temporary_file" "$JIYU_STAGE_RESULT_FILE"
  rm -f "$temporary_file"
}

verify_staged_jiyu_build() {
  require_root
  require_linux
  require_command jq
  require_command sha256sum
  [[ -f "$JIYU_STAGE_STATE_FILE" ]] || fail "没有等待验证的 JIYU 暂存构建。"

  local version backup_dir expected_sha old_pid
  version="$(sed -n 's/^VERSION=//p' "$JIYU_STAGE_STATE_FILE" | tail -n 1)"
  backup_dir="$(sed -n 's/^BACKUP_DIR=//p' "$JIYU_STAGE_STATE_FILE" | tail -n 1)"
  expected_sha="$(sed -n 's/^EXPECTED_SHA=//p' "$JIYU_STAGE_STATE_FILE" | tail -n 1)"
  old_pid="$(sed -n 's/^OLD_PID=//p' "$JIYU_STAGE_STATE_FILE" | tail -n 1)"
  validate_jiyu_version "$version"
  [[ "$backup_dir" =~ ^${BACKUP_ROOT}/jiyu-stage-v[0-9]+\.[0-9]+\.[0-9]+-jiyu\.[0-9]+-[0-9]{8}T[0-9]{6}Z$ ]] || \
    fail "暂存备份目录非法。"
  [[ "$expected_sha" =~ ^[a-f0-9]{64}$ ]] || fail "暂存二进制哈希非法。"
  [[ "$old_pid" =~ ^[0-9]+$ ]] || fail "暂存进程编号非法。"
  [[ -x "${backup_dir}/sub2api" && -f "${backup_dir}/VERSION" && -f "${backup_dir}/sub2api.dump" ]] || \
    fail "暂存回滚材料不完整。"

  local attempt current_pid live_sha restart_seen=false post_restart_attempts=0
  for ((attempt = 1; attempt <= 120; attempt += 1)); do
    current_pid="$(systemctl show --property MainPID --value "$SUB2API_SERVICE" 2>/dev/null || printf '0')"
    [[ "$current_pid" =~ ^[0-9]+$ ]] || current_pid=0
    if [[ "$current_pid" != "$old_pid" ]]; then
      restart_seen=true
    fi
    if [[ "$current_pid" -gt 0 && -r "/proc/${current_pid}/exe" ]]; then
      live_sha="$(sha256sum "/proc/${current_pid}/exe" 2>/dev/null | awk '{print $1}' || true)"
      if [[ "$live_sha" == "$expected_sha" ]] && postgresql_preflight && wait_for_health 45; then
        rm -f "$JIYU_STAGE_STATE_FILE"
        write_jiyu_stage_result applied "$version" "运行哈希与健康检查通过"
        log "JIYU 构建 ${version} 已由独立验证任务确认生效。"
        return 0
      fi
    fi
    if [[ "$restart_seen" == true ]]; then
      post_restart_attempts=$((post_restart_attempts + 1))
      [[ "$post_restart_attempts" -lt 18 ]] || break
    fi
    sleep 5
  done

  log "JIYU 构建 ${version} 未在时限内通过运行验证，正在自动回滚。"
  systemctl stop "$SUB2API_SERVICE" || true
  install -m 0755 -o sub2api -g sub2api "${backup_dir}/sub2api" "${INSTALL_DIR}/sub2api"
  install -m 0644 -o sub2api -g sub2api "${backup_dir}/VERSION" "${INSTALL_DIR}/VERSION"
  restore_database "${backup_dir}/sub2api.dump"
  systemctl start "$SUB2API_SERVICE"
  wait_for_health 90 || fail "暂存构建自动回滚后健康检查仍失败，需要人工查看 journalctl。"
  rm -f "$JIYU_STAGE_STATE_FILE"
  write_jiyu_stage_result rolled_back "$version" "新构建未通过运行哈希或健康检查，已恢复发布前版本和数据库"
  log "JIYU 构建 ${version} 已自动回滚，生产服务恢复健康。"
}

check_update() {
  require_linux
  [[ -f "${INSTALL_DIR}/VERSION" ]] || fail "未检测到 Sub2API VERSION 文件。"
  local current current_base latest
  current="$(tr -d '[:space:]' <"${INSTALL_DIR}/VERSION")"
  current_base="${current%%-jiyu.*}"
  latest="$(latest_version)"
  log "已安装版本: ${current}"
  log "GitHub 最新版: ${latest}"
  if [[ "$current" == "$latest" ]]; then
    log "状态: 已是最新版。"
  elif [[ "$current_base" == "$latest" ]]; then
    log "状态: 当前 JIYU 构建已基于最新版。"
  else
    log "状态: 发现新版本，等待 JIYU 构建、测试和人工发布。"
  fi
}

check_upstream_release() {
  require_root
  require_linux
  install -d -m 0700 -o root -g root "$STATE_DIR"
  local current current_base latest checked_at update_available temporary_file
  current="$(tr -d '[:space:]' <"${INSTALL_DIR}/VERSION")"
  current_base="${current%%-jiyu.*}"
  latest="$(latest_version)"
  checked_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  update_available=false
  [[ "$current" == "$latest" || "$current_base" == "$latest" ]] || update_available=true
  temporary_file="$(mktemp)"
  jq -n \
    --arg current "$current" \
    --arg latest "$latest" \
    --arg checked_at "$checked_at" \
    --argjson update_available "$update_available" \
    '{current:$current,latest:$latest,checked_at:$checked_at,update_available:$update_available}' \
    >"$temporary_file"
  install -m 0600 -o root -g root "$temporary_file" "$UPDATE_STATE_FILE"
  rm -f "$temporary_file"
  check_update
}

harden_apache_admin_updates() {
  require_root
  require_linux
  [[ -f "$APACHE_SITE" ]] || fail "找不到 Apache 站点配置: ${APACHE_SITE}"
  if ! grep -q 'JIYU-BLOCK-UPSTREAM-SELF-UPDATE' "$APACHE_SITE"; then
    cat >>"$APACHE_SITE" <<'APACHE'

# JIYU-BLOCK-UPSTREAM-SELF-UPDATE: 品牌构建只能通过受控发布流程升级。
<LocationMatch "^/api/v1/admin/system/(update|rollback)$">
    Require all denied
</LocationMatch>
APACHE
  fi
  apache2ctl configtest
  reload_apache_with_recovery || fail "Apache 重载和自动重启后公网健康检查仍失败。"
  log "已禁止浏览器直接更新或回滚生产二进制。"
}

rewrite_jiyu_region_headers() {
  local source_file="$1"
  local destination_file="$2"
  local canonical_host="$3"

  awk -v domain="$canonical_host" '
    function emit_region_block() {
      print "    # JIYU-REGION-TRUST-BOUNDARY-BEGIN: 只信任 Cloudflare 注入的两位国家码。"
      print "    SetEnvIf CF-IPCountry \"^([A-Z]{2})$\" JIYU_CF_COUNTRY=$1"
      print "    RequestHeader unset X-JIYU-Country"
      print "    RequestHeader set X-JIYU-Country \"%{JIYU_CF_COUNTRY}e\" env=JIYU_CF_COUNTRY"
      print "    RequestHeader unset CF-IPCountry"
      print "    # JIYU-REGION-TRUST-BOUNDARY-END"
      print ""
    }

    /# JIYU-REGION-TRUST-BOUNDARY-BEGIN:/ { skipping_managed = 1; next }
    skipping_managed {
      if (/# JIYU-REGION-TRUST-BOUNDARY-END/) {
        skipping_managed = 0
        skip_managed_blank = 1
      }
      next
    }
    skip_managed_blank && /^[[:space:]]*$/ { skip_managed_blank = 0; next }
    skip_managed_blank { skip_managed_blank = 0 }
    /# JIYU-REGION-TRUST-BOUNDARY:/ { legacy_lines = 4; next }
    legacy_lines > 0 {
      legacy_lines--
      if (legacy_lines == 0) skip_legacy_blank = 1
      next
    }
    skip_legacy_blank && /^[[:space:]]*$/ { skip_legacy_blank = 0; next }
    skip_legacy_blank { skip_legacy_blank = 0 }

    /^[[:space:]]*<VirtualHost[[:space:]]+[^>]*\*:443[^>]*>/ {
      in_https_vhost = 1
      server_name = ""
    }
    in_https_vhost && /^[[:space:]]*ServerName[[:space:]]+/ {
      server_name = $2
    }
    in_https_vhost && /^[[:space:]]*<\/VirtualHost>/ {
      if (server_name == domain) {
        emit_region_block()
        inserted++
      }
      in_https_vhost = 0
      server_name = ""
    }
    { print }
    END { if (inserted != 1) exit 42 }
  ' "$source_file" >"$destination_file"
}

ensure_jiyu_region_headers() {
  require_root
  require_linux
  require_command apache2ctl
  [[ -f "$APACHE_SITE" ]] || fail "找不到 Apache 站点配置: ${APACHE_SITE}"

  local temporary_file temporary_backup timestamp backup_dir
  temporary_file="$(mktemp)"
  if ! rewrite_jiyu_region_headers "$APACHE_SITE" "$temporary_file" "$DOMAIN"; then
    rm -f "$temporary_file"
    fail "无法唯一定位 ${DOMAIN} 的 HTTPS VirtualHost，拒绝写入地域头规则。"
  fi
  if cmp -s "$APACHE_SITE" "$temporary_file"; then
    rm -f "$temporary_file"
    log "Apache 地域可信头边界已位于目标 HTTPS VirtualHost。"
    return 0
  fi

  temporary_backup="${STATE_DIR}/apache-before-region-headers.conf"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="${BACKUP_ROOT}/region-headers-${timestamp}"
  backup_database "$backup_dir"
  install -d -m 0700 -o root -g root "$STATE_DIR"
  cp -a "$APACHE_SITE" "$temporary_backup"
  cat "$temporary_file" >"$APACHE_SITE"
  rm -f "$temporary_file"
  if ! apache2ctl configtest || ! reload_apache_with_recovery; then
    cp -a "$temporary_backup" "$APACHE_SITE"
    reload_apache_with_recovery || true
    fail "Apache 地域头规则校验或重载失败，已恢复原配置。"
  fi
  log "Apache 已在目标 HTTPS VirtualHost 剥离客户端伪造地域头，并仅转发可信 CF-IPCountry。"
}

rewrite_jiyu_cn_production_gate() {
  local source_file="$1"
  local destination_file="$2"
  local canonical_host="$3"
  local action="$4"

  awk -v domain="$canonical_host" -v action="$action" '
    function emit_gate() {
      if (action == "pause") {
        print "    # JIYU-CN-PRODUCTION-GATE-BEGIN: 临时暂停中国大陆生产面，资产保留。"
        print "    SetEnvIf CF-IPCountry \"^CN$\" JIYU_CN_PRODUCTION_PAUSED=1"
        print "    <Location />"
        print "        <RequireAll>"
        print "            Require all granted"
        print "            Require not env JIYU_CN_PRODUCTION_PAUSED"
        print "        </RequireAll>"
        print "    </Location>"
        print "    # JIYU-CN-PRODUCTION-GATE-END"
      }
    }

    /# JIYU-CN-PRODUCTION-GATE-BEGIN:/ { skipping = 1; next }
    skipping {
      if (/# JIYU-CN-PRODUCTION-GATE-END/) { skipping = 0 }
      next
    }
    /^[[:space:]]*<VirtualHost[[:space:]]+[^>]*\*:443[^>]*>/ {
      in_https_vhost = 1
      server_name = ""
    }
    in_https_vhost && /^[[:space:]]*ServerName[[:space:]]+/ { server_name = $2 }
    in_https_vhost && /^[[:space:]]*<\/VirtualHost>/ {
      if (server_name == domain) {
        emit_gate()
        found++
      }
      in_https_vhost = 0
      server_name = ""
    }
    { print }
    END { if (found != 1) exit 42 }
  ' "$source_file" >"$destination_file"
}

set_jiyu_cn_production() {
  require_root
  require_linux
  require_command apache2ctl
  [[ -f "$APACHE_SITE" ]] || fail "找不到 Apache 站点配置: ${APACHE_SITE}"

  local action="$1" temporary_file temporary_backup timestamp backup_dir
  case "$action" in
    pause|resume) ;;
    *) fail "中国生产面只能是 pause 或 resume。" ;;
  esac

  temporary_file="$(mktemp)"
  if ! rewrite_jiyu_cn_production_gate "$APACHE_SITE" "$temporary_file" "$DOMAIN" "$action"; then
    rm -f "$temporary_file"
    fail "无法唯一定位 ${DOMAIN} 的 HTTPS VirtualHost，拒绝修改中国生产面。"
  fi
  if cmp -s "$APACHE_SITE" "$temporary_file"; then
    rm -f "$temporary_file"
    log "中国生产面已经处于 ${action} 状态。"
    return 0
  fi

  temporary_backup="${STATE_DIR}/apache-before-cn-production-${action}.conf"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_dir="${BACKUP_ROOT}/cn-production-${action}-${timestamp}"
  backup_database "$backup_dir"
  install -d -m 0700 -o root -g root "$STATE_DIR"
  cp -a "$APACHE_SITE" "$temporary_backup"
  cat "$temporary_file" >"$APACHE_SITE"
  rm -f "$temporary_file"
  if ! apache2ctl configtest || ! reload_apache_with_recovery; then
    cp -a "$temporary_backup" "$APACHE_SITE"
    reload_apache_with_recovery || true
    fail "中国生产面 ${action} 校验或重载失败，已恢复原配置。"
  fi
  if [[ "$action" == "pause" ]]; then
    log "中国大陆生产面已暂停；国内资产、账号、分组和渠道均保留。"
  else
    log "中国大陆生产面已恢复；仍受现有地域模型策略约束。"
  fi
}

enable_managed_web_updates() {
  require_root
  require_linux
  local broker_source="${2:-}"
  local manifest_url="${3:-}"
  [[ -f "$broker_source" ]] || fail "请提供更新代理脚本路径。"
  [[ "$manifest_url" =~ ^https:// ]] || fail "兼容包清单必须使用 HTTPS。"
  postgresql_preflight

  install -m 0755 -o root -g root "$broker_source" "$JIYU_UPDATE_BROKER_PATH"
  prepare_config_directory
  printf 'MANIFEST_URL=%s\n' "$manifest_url" >"$JIYU_UPDATE_CONFIG"
  chown root:root "$JIYU_UPDATE_CONFIG"
  chmod 0600 "$JIYU_UPDATE_CONFIG"
  rm -f "$JIYU_UPDATE_SUDOERS"

  cat >"$JIYU_UPDATE_SOCKET_UNIT" <<'SYSTEMD_SOCKET'
[Unit]
Description=JIYU managed update activation socket

[Socket]
ListenStream=/run/sub2api-jiyu-update.sock
SocketUser=root
SocketGroup=sub2api
SocketMode=0660
DirectoryMode=0755
Accept=yes
MaxConnections=1
RemoveOnStop=yes

[Install]
WantedBy=sockets.target
SYSTEMD_SOCKET

  cat >"$JIYU_UPDATE_SERVICE_UNIT" <<'SYSTEMD_SERVICE'
[Unit]
Description=JIYU managed update request
After=network-online.target

[Service]
Type=exec
User=root
Group=root
ExecStart=/usr/local/sbin/sub2api-jiyu-update-broker
StandardInput=socket
StandardOutput=socket
StandardError=socket
TimeoutStartSec=20min
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=full
ReadWritePaths=/opt/sub2api /var/backups/sub2api /var/lib/sub2api-ops /run/lock
SYSTEMD_SERVICE

  chmod 0644 "$JIYU_UPDATE_SOCKET_UNIT" "$JIYU_UPDATE_SERVICE_UNIT"

  install -d -m 0755 "$(dirname "$JIYU_UPDATE_DROPIN")"
  cat >"$JIYU_UPDATE_DROPIN" <<'SYSTEMD'
[Service]
Environment=SUB2API_JIYU_MANAGED_UPDATE=1
SYSTEMD

  if [[ -f "$APACHE_SITE" ]]; then
    sed -i '/# JIYU-BLOCK-UPSTREAM-SELF-UPDATE:/,/^<\/LocationMatch>$/d' "$APACHE_SITE"
    apache2ctl configtest
    reload_apache_with_recovery || fail "启用 WebUI 更新时 Apache 未能恢复公网服务。"
  fi
  systemctl daemon-reload
  systemctl enable sub2api-jiyu-update.socket >/dev/null
  systemctl restart sub2api-jiyu-update.socket
  systemctl is-active --quiet sub2api-jiyu-update.socket || fail "JIYU 更新套接字未能启动。"
  systemctl restart "$SUB2API_SERVICE"
  wait_for_health 90 || fail "启用 WebUI 更新后服务健康检查失败。"
  log "WebUI 已启用受限 JIYU 兼容包更新；浏览器不能向 root 代理传入命令或下载地址。"
}

backup_legacy_newapi() {
  local timestamp archive
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  archive="${BACKUP_ROOT}/legacy-newapi-before-cutover-${timestamp}.tar.gz"
  local candidates=(
    opt/sub2api/data/newapi
    etc/systemd/system/openclaw-newapi.service
    usr/local/bin/openclaw-newapi
  )
  local existing=()
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -e "/${candidate}" ]]; then
      existing+=("$candidate")
    fi
  done
  if [[ "${#existing[@]}" -gt 0 ]]; then
    tar -C / -czf "$archive" "${existing[@]}"
    chmod 0600 "$archive"
    log "旧 New-API 冷回滚包已保存到 ${archive}。"
  fi
}

remove_newapi_apache_branding() {
  sed -i \
    -e '/^[[:space:]]*RequestHeader unset Accept-Encoding[[:space:]]*$/d' \
    -e '/^[[:space:]]*AddOutputFilterByType SUBSTITUTE text\/html[[:space:]]*$/d' \
    -e '/^[[:space:]]*Substitute "s|New API|CC中转|ni"[[:space:]]*$/d' \
    -e '/^[[:space:]]*Substitute "s|New-API|CC中转|ni"[[:space:]]*$/d' \
    -e '/^[[:space:]]*Substitute "s|<\/head>|<script>.*CC中转.*<\/script><\/head>|ni"[[:space:]]*$/d' \
    -e 's/cc-newapi-error\.log/cc-sub2api-error.log/g' \
    -e 's/cc-newapi-access\.log/cc-sub2api-access.log/g' \
    "$APACHE_SITE"
}

ensure_apache_responses_websocket_proxy() {
  local proxy_count temporary_file
  proxy_count="$(grep -Ec '^[[:space:]]*ProxyPass(Reverse)? /v1/responses http://127\.0\.0\.1:18080/v1/responses' "$APACHE_SITE" || true)"
  if [[ "$proxy_count" -eq 2 ]]; then
    return 0
  fi
  [[ "$proxy_count" -eq 0 ]] || fail "Apache Responses WebSocket 代理配置不完整，拒绝自动覆盖。"

  temporary_file="$(mktemp)"
  if ! awk '
    !inserted && /^[[:space:]]*ProxyPass \/ http:\/\/127\.0\.0\.1:18080\// {
      print "    # JIYU-RESPONSES-WEBSOCKET: Codex 新版默认使用 Responses WebSocket。"
      print "    ProxyPass /v1/responses http://127.0.0.1:18080/v1/responses upgrade=websocket retry=0 timeout=120"
      print "    ProxyPassReverse /v1/responses http://127.0.0.1:18080/v1/responses"
      print ""
      inserted = 1
    }
    { print }
    END { if (!inserted) exit 42 }
  ' "$APACHE_SITE" >"$temporary_file"; then
    rm -f "$temporary_file"
    fail "找不到 Sub2API 根代理，无法安全插入 Responses WebSocket 规则。"
  fi
  cat "$temporary_file" >"$APACHE_SITE"
  rm -f "$temporary_file"
}

repair_apache_responses_websocket_proxy() {
  require_root
  require_linux
  [[ -f "$APACHE_SITE" ]] || fail "找不到 Apache 站点配置: ${APACHE_SITE}"
  local temporary_backup
  temporary_backup="$(mktemp)"
  cp -a "$APACHE_SITE" "$temporary_backup"
  ensure_apache_responses_websocket_proxy
  if ! apache2ctl configtest; then
    cp -a "$temporary_backup" "$APACHE_SITE"
    fail "Responses WebSocket 代理校验失败，已恢复原配置。"
  fi
  if ! reload_apache_with_recovery; then
    cp -a "$temporary_backup" "$APACHE_SITE"
    reload_apache_with_recovery || fail "Responses WebSocket 代理回滚后公网健康仍失败。"
    fail "Responses WebSocket 代理上线后公网健康失败，已恢复原配置。"
  fi
  rm -f "$temporary_backup"
  log "Responses WebSocket 代理已位于根代理之前，Codex 升级请求不会再被普通 HTTP 代理截断。"
}

verify_public_url() {
  local url="$1"
  local attempt
  for ((attempt = 1; attempt <= 5; attempt += 1)); do
    if curl -fsS --max-time 15 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

verify_public_health() {
  verify_public_url "https://${DOMAIN}/health"
}

reload_apache_with_recovery() {
  local public_url="${1:-https://${DOMAIN}/health}"
  apache2ctl configtest || return 1
  if systemctl reload apache2.service && verify_public_url "$public_url"; then
    return 0
  fi
  log "Apache 重载后公网 TLS/健康检查失败，自动执行完整重启。"
  systemctl restart apache2.service || return 1
  verify_public_url "$public_url"
}

cutover_to_sub2api() {
  require_root
  require_linux
  [[ -f "$APACHE_SITE" ]] || fail "找不到 Apache 站点配置: ${APACHE_SITE}"
  wait_for_health 5 || fail "Sub2API 内网健康检查未通过，禁止切换域名。"

  local old_proxy_count
  old_proxy_count="$(grep -Ec 'ProxyPass(Reverse)? / http://127\.0\.0\.1:13000/' "$APACHE_SITE" || true)"
  [[ "$old_proxy_count" -eq 2 ]] || fail "Apache 旧 New-API 代理行不是预期的 2 行，拒绝自动改写。"
  [[ ! -e "$APACHE_ROLLBACK_FILE" ]] || fail "检测到未清理的切换回滚文件，请先确认当前状态。"

  backup_legacy_newapi
  cp -a "$APACHE_SITE" "$APACHE_ROLLBACK_FILE"
  sed -i 's#http://127\.0\.0\.1:13000/#http://127.0.0.1:18080/#g' "$APACHE_SITE"
  remove_newapi_apache_branding
  ensure_apache_responses_websocket_proxy

  if ! apache2ctl configtest; then
    cp -a "$APACHE_ROLLBACK_FILE" "$APACHE_SITE"
    fail "Apache 配置校验失败，已恢复原配置。"
  fi
  if ! reload_apache_with_recovery; then
    cp -a "$APACHE_ROLLBACK_FILE" "$APACHE_SITE"
    apache2ctl configtest
    systemctl restart apache2.service
    fail "公网健康检查失败，已恢复 New-API 域名代理。"
  fi

  systemctl disable --now "$NEWAPI_SERVICE" >/dev/null 2>&1 || true
  verify_public_health || fail "停止 New-API 后公网健康检查失败，请执行 rollback-cutover。"
  log "${DOMAIN} 已切换到全新 Sub2API，旧 New-API 服务已停止但数据和回滚包仍保留。"
  show_status
}

clean_apache_after_cutover() {
  require_root
  require_linux
  local sub2api_proxy_count temporary_backup
  sub2api_proxy_count="$(grep -Ec 'ProxyPass(Reverse)? / http://127\.0\.0\.1:18080/' "$APACHE_SITE" || true)"
  [[ "$sub2api_proxy_count" -eq 2 ]] || fail "Apache 尚未稳定指向 Sub2API。"
  temporary_backup="$(mktemp)"
  cp -a "$APACHE_SITE" "$temporary_backup"
  remove_newapi_apache_branding
  ensure_apache_responses_websocket_proxy
  if ! apache2ctl configtest; then
    cp -a "$temporary_backup" "$APACHE_SITE"
    fail "清理旧品牌注入后 Apache 校验失败，已恢复。"
  fi
  if ! reload_apache_with_recovery; then
    cp -a "$temporary_backup" "$APACHE_SITE"
    reload_apache_with_recovery || fail "恢复旧 Apache 配置后公网健康仍失败。"
    fail "清理旧品牌注入后公网健康失败，已恢复原配置。"
  fi
  rm -f "$temporary_backup"
  log "Apache 旧 New-API HTML 注入已清理。"
}

rollback_cutover() {
  require_root
  require_linux
  [[ -f "$APACHE_ROLLBACK_FILE" ]] || fail "找不到切换前 Apache 配置，无法自动回滚。"
  systemctl enable --now "$NEWAPI_SERVICE"
  cp -a "$APACHE_ROLLBACK_FILE" "$APACHE_SITE"
  reload_apache_with_recovery "https://${DOMAIN}/api/status" || \
    fail "Apache 完整重启后旧 New-API 公网状态检查仍失败。"
  log "域名已回滚到旧 New-API。Sub2API 服务保持运行，便于排障。"
}

scrub_newapi_env_file() {
  local env_path="$1"
  [[ -f "$env_path" ]] || return 0
  local cleaned_env
  cleaned_env="$(mktemp)"
  awk '!/^SUB2API_NEWAPI_/ && !/^SUB2API_REQUIRE_NEWAPI_DATABASE=/' \
    "$env_path" >"$cleaned_env"
  cat >>"$cleaned_env" <<'EOF'
SUB2API_NEWAPI_ENABLED=0
SUB2API_NEWAPI_GATEWAY_ENABLED=0
SUB2API_REQUIRE_NEWAPI_DATABASE=0
EOF
  install -m 0600 -o root -g root "$cleaned_env" "$env_path"
  rm -f "$cleaned_env"
}

purge_newapi() {
  require_root
  require_linux
  wait_for_health 5 || fail "Sub2API 内网健康检查未通过，禁止删除旧 New-API。"
  verify_public_health || fail "Sub2API 公网健康检查未通过，禁止删除旧 New-API。"

  local sub2api_proxy_count
  sub2api_proxy_count="$(grep -Ec 'ProxyPass(Reverse)? / http://127\.0\.0\.1:18080/' "$APACHE_SITE" || true)"
  [[ "$sub2api_proxy_count" -eq 2 ]] || fail "Apache 尚未稳定指向 Sub2API，禁止删除旧 New-API。"

  systemctl disable --now "$NEWAPI_SERVICE" >/dev/null 2>&1 || true
  if ss -ltnH | awk '{print $4}' | grep -q ':13000$'; then
    fail "旧 New-API 端口 13000 仍在监听，拒绝删除运行数据。"
  fi

  # 先移除单独保存的密钥和数据库文件，再删除空目录及普通运行文件。
  if [[ -f /etc/sub2api/newapi.env ]]; then
    shred -u -- /etc/sub2api/newapi.env
  fi
  if [[ -d /opt/sub2api/data/newapi ]]; then
    find /opt/sub2api/data/newapi -xdev -type f -exec shred -u -- {} +
    find /opt/sub2api/data/newapi -xdev -depth -mindepth 1 -delete
    rmdir /opt/sub2api/data/newapi
  fi
  if [[ -f /usr/local/bin/openclaw-newapi ]]; then
    unlink /usr/local/bin/openclaw-newapi
  fi

  rm -f "/etc/systemd/system/${NEWAPI_SERVICE}"
  find /etc/systemd/system -maxdepth 3 -type l -name "$NEWAPI_SERVICE" -delete
  if [[ -d /opt/sub2api/backups ]]; then
    local legacy_path
    local legacy_paths=()
    while IFS= read -r -d '' legacy_path; do
      legacy_paths+=("$legacy_path")
    done < <(
      find /opt/sub2api/backups -depth \
        \( -iname '*newapi*' -o -iname '*new-api*' \) -print0
    )
    for legacy_path in "${legacy_paths[@]}"; do
      [[ "$legacy_path" == /opt/sub2api/backups/* ]] || fail "拒绝删除备份根目录外的路径。"
      if [[ -d "$legacy_path" ]]; then
        find "$legacy_path" -xdev -depth -delete
      elif [[ -f "$legacy_path" ]]; then
        shred -u -- "$legacy_path"
      elif [[ -L "$legacy_path" ]]; then
        unlink "$legacy_path"
      fi
    done
  fi
  find "$BACKUP_ROOT" -maxdepth 1 -type f -name 'legacy-newapi-before-cutover-*.tar.gz' -delete
  rm -f "$APACHE_ROLLBACK_FILE"

  scrub_newapi_env_file /etc/sub2api/sub2api.env
  scrub_newapi_env_file /opt/sub2api/.env

  systemctl daemon-reload
  [[ ! -e /opt/sub2api/data/newapi ]] || fail "旧 New-API 数据目录仍存在。"
  [[ ! -e /usr/local/bin/openclaw-newapi ]] || fail "旧 New-API 二进制仍存在。"
  [[ ! -e "/etc/systemd/system/${NEWAPI_SERVICE}" ]] || fail "旧 New-API 服务定义仍存在。"
  verify_public_health || fail "清理后 Sub2API 公网健康检查失败。"
  log "Oracle 上的旧 New-API 数据、密钥、二进制、服务定义和同名本地备份已清理。"
}

write_cloudflare_origin_policy() {
  local temporary_dir="$1"
  local ipv4_file="${temporary_dir}/ips-v4"
  local ipv6_file="${temporary_dir}/ips-v6"
  curl -fsSL --retry 3 --retry-all-errors https://www.cloudflare.com/ips-v4 -o "$ipv4_file"
  curl -fsSL --retry 3 --retry-all-errors https://www.cloudflare.com/ips-v6 -o "$ipv6_file"

  python3 - "$ipv4_file" "$ipv6_file" <<'PY'
import ipaddress
import pathlib
import sys

for path_value, version, minimum in ((sys.argv[1], 4, 15), (sys.argv[2], 6, 7)):
    path = pathlib.Path(path_value)
    networks = []
    for line in path.read_text(encoding="ascii").splitlines():
        value = line.strip()
        if not value:
            continue
        network = ipaddress.ip_network(value, strict=True)
        if network.version != version:
            raise SystemExit(f"Cloudflare IPv{version} 列表包含错误地址族")
        networks.append(str(network))
    if len(networks) < minimum or len(networks) != len(set(networks)):
        raise SystemExit(f"Cloudflare IPv{version} 列表数量或唯一性异常")
    path.write_text("\n".join(networks) + "\n", encoding="ascii")
PY

  local ipv4_elements ipv6_elements temporary_policy
  ipv4_elements="$(paste -sd, "$ipv4_file")"
  ipv6_elements="$(paste -sd, "$ipv6_file")"
  temporary_policy="${temporary_dir}/jiyu-cloudflare-origin.nft"
  cat >"$temporary_policy" <<NFT
table inet jiyu_cloudflare_origin {
  set cloudflare_v4 {
    type ipv4_addr
    flags interval
    elements = { ${ipv4_elements} }
  }

  set cloudflare_v6 {
    type ipv6_addr
    flags interval
    elements = { ${ipv6_elements} }
  }

  chain input {
    type filter hook input priority -190; policy accept;
    iifname "lo" tcp dport 443 accept
    iifname "tailscale0" tcp dport 443 accept
    ip saddr @cloudflare_v4 tcp dport 443 accept
    ip6 saddr @cloudflare_v6 tcp dport 443 accept
    tcp dport 443 drop
  }
}
NFT
  nft -c -f "$temporary_policy"
  prepare_config_directory
  install -m 0600 -o root -g root "$temporary_policy" "$CLOUDFLARE_ORIGIN_NFT"
}

apply_cloudflare_origin_443() {
  require_root
  require_linux
  require_command curl
  require_command nft
  require_command python3
  require_command systemd-run

  local temporary_dir
  temporary_dir="$(mktemp -d)"
  write_cloudflare_origin_policy "$temporary_dir"
  rm -rf "$temporary_dir"

  cat >"$CLOUDFLARE_ORIGIN_UNIT" <<UNIT
[Unit]
Description=Allow public HTTPS only from Cloudflare for JIYU vhosts
After=network-pre.target
Before=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=-/usr/sbin/nft delete table inet jiyu_cloudflare_origin
ExecStart=/usr/sbin/nft -f ${CLOUDFLARE_ORIGIN_NFT}
ExecStop=-/usr/sbin/nft delete table inet jiyu_cloudflare_origin

[Install]
WantedBy=multi-user.target
UNIT
  chmod 0644 "$CLOUDFLARE_ORIGIN_UNIT"
  systemctl daemon-reload
  systemctl enable "$CLOUDFLARE_ORIGIN_SERVICE" >/dev/null
  systemctl stop "${CLOUDFLARE_ROLLBACK_UNIT}.timer" >/dev/null 2>&1 || true
  systemd-run --unit="$CLOUDFLARE_ROLLBACK_UNIT" --on-active=5m \
    --property=Type=oneshot --collect \
    /usr/bin/systemctl disable --now "$CLOUDFLARE_ORIGIN_SERVICE" >/dev/null
  systemctl restart "$CLOUDFLARE_ORIGIN_SERVICE"
  systemctl is-active --quiet "$CLOUDFLARE_ORIGIN_SERVICE" || \
    fail "Cloudflare 443 源站策略未能启动，自动回滚仍保持生效。"
  verify_public_health || fail "Cloudflare 443 策略应用后公网健康失败，等待自动回滚。"
  log "443 已仅允许 Cloudflare、loopback 和 Tailscale；5 分钟自动回滚已启动，外部验收后必须执行确认命令。"
}

confirm_cloudflare_origin_443() {
  require_root
  require_linux
  systemctl is-active --quiet "$CLOUDFLARE_ORIGIN_SERVICE" || fail "Cloudflare 443 源站策略未运行。"
  nft list table inet jiyu_cloudflare_origin >/dev/null || fail "Cloudflare 443 nftables 表不存在。"
  verify_public_health || fail "公网健康检查失败，拒绝取消自动回滚。"
  systemctl stop "${CLOUDFLARE_ROLLBACK_UNIT}.timer" >/dev/null 2>&1 || true
  systemctl reset-failed "${CLOUDFLARE_ROLLBACK_UNIT}.service" >/dev/null 2>&1 || true
  log "Cloudflare 443 源站策略已确认，自动回滚计时器已取消。"
}

rollback_cloudflare_origin_443() {
  require_root
  require_linux
  systemctl stop "${CLOUDFLARE_ROLLBACK_UNIT}.timer" >/dev/null 2>&1 || true
  systemctl disable --now "$CLOUDFLARE_ORIGIN_SERVICE" >/dev/null 2>&1 || true
  nft delete table inet jiyu_cloudflare_origin >/dev/null 2>&1 || true
  log "Cloudflare 443 源站策略已撤销，443 恢复由原有防火墙规则管理。"
}

show_status() {
  local installed_version="未安装"
  if [[ -f "${INSTALL_DIR}/VERSION" ]]; then
    installed_version="$(tr -d '[:space:]' <"${INSTALL_DIR}/VERSION")"
  fi
  log "版本: ${installed_version}"
  log "Sub2API 服务: $(systemctl is-active "$SUB2API_SERVICE" 2>/dev/null || true)"
  log "专用 Redis: $(systemctl is-active "$REDIS_SERVICE" 2>/dev/null || true)"
  log "自动更新定时器: $(systemctl is-active "$UPDATE_TIMER" 2>/dev/null || true)"
  log "每日备份定时器: $(systemctl is-active "$BACKUP_TIMER" 2>/dev/null || true)"
  log "Cloudflare 443 源站策略: $(systemctl is-active "$CLOUDFLARE_ORIGIN_SERVICE" 2>/dev/null || true)"
  postgresql_preflight
  log "PostgreSQL 预检: 通过"
  if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
    log "内网健康检查: 通过"
  else
    log "内网健康检查: 失败"
    return 1
  fi
  local responses_websocket_proxy_count
  responses_websocket_proxy_count="$(grep -Ec '^[[:space:]]*ProxyPass(Reverse)? /v1/responses http://127\.0\.0\.1:18080/v1/responses' "$APACHE_SITE" 2>/dev/null || true)"
  if [[ "$responses_websocket_proxy_count" -eq 2 ]]; then
    log "Responses WebSocket 代理: 通过"
  else
    log "Responses WebSocket 代理: 缺失或不完整"
  fi
}

usage() {
  cat <<'USAGE'
用法: sub2api_oracle_manage.sh <命令>

命令:
  install            全新安装 Sub2API、PostgreSQL、专用 Redis 和每日版本检查
  finish-install     收口因系统依赖问题中断的安装，不生成或覆盖任何密钥
  check              只读检查当前版本与 GitHub 最新稳定版
  check-upstream     记录官方最新版，只告警不覆盖 JIYU 品牌构建
  update             仅在显式授权环境变量开启后执行官方二进制升级
  install-jiyu-build <path>  备份后发布已验证的 JIYU Linux 二进制，失败自动回滚
  stage-jiyu-build <path>    校验、备份并原子暂存 JIYU 二进制，重启后独立验证并自动回滚
  verify-jiyu-stage          内部入口：核对暂存构建运行哈希与健康状态
  enable-web-update <broker> <manifest-url>  启用 WebUI 受限兼容包更新
  backup             立即生成数据库、页面、品牌、配置和二进制一致性备份
  pricing-fallback   校验并原子安装官方模型价格回退资源，失败自动回滚
  brand              重新应用 JIYU AI 网站名称、副标题和 JY Logo
  brand-asset        重新发布邮件和文档使用的 JIYU AI 图形 Logo
  recharge-center     重新应用充值中心固定公开店铺和精确 CSP
  docs-page           重新应用文档入口和 CC Switch 下载、导入说明
  terms-page          更新登录条款中的地区展示规则（保留其余条款文本）
  region-headers      加固 Cloudflare 地域头的 Apache 信任边界（不启用地域强制）
  region-enforcement <enable|disable>  原子切换 JIYU 地域强制，失败自动回滚
  cn-production <pause|resume>  原子暂停或恢复中国大陆站点生产面，资产不删除
  upstream-allowlist    重新应用当前生产账号的受信官方域名白名单
  harden-apache      禁止浏览器直接更新或回滚生产二进制
  postgres-preflight 修复 PostgreSQL 最小运行权限并验证数据库连通性
  cloudflare-origin-443  仅允许 Cloudflare、loopback、Tailscale 访问 443，并启动 5 分钟回滚
  confirm-cloudflare-origin-443  外部验收后取消 443 自动回滚
  rollback-cloudflare-origin-443  撤销 443 Cloudflare 源站策略
  responses-websocket  修复 Codex Responses WebSocket 的 Apache 代理顺序
  openai-ws-http-bridge  启用 API Key 账号的官方 HTTP 桥接模式路由
  openai-ws-legacy       关闭模式路由，回滚到旧版账号传输判定
  cutover            把 jiyu.245334.xyz 从 New-API 切换到 Sub2API
  clean-apache       清理切换后遗留的 New-API HTML 品牌注入
  rollback-cutover   把域名恢复到旧 New-API
  purge-newapi       切换验收后永久删除 Oracle 上的旧 New-API 数据和服务
  status             查看本机服务和健康状态
USAGE
}

main() {
  case "${1:-}" in
    install)
      install_clean
      ;;
    finish-install)
      finish_install
      show_status
      ;;
    check)
      check_update
      ;;
    check-upstream)
      check_upstream_release
      ;;
    update)
      update_sub2api
      ;;
    install-jiyu-build)
      install_jiyu_build "$@"
      ;;
    stage-jiyu-build)
      stage_jiyu_build "$@"
      ;;
    verify-jiyu-stage)
      verify_staged_jiyu_build "$@"
      ;;
    enable-web-update)
      enable_managed_web_updates "$@"
      ;;
    backup)
      daily_backup
      ;;
    pricing-fallback)
      install_pricing_fallback
      ;;
    brand)
      apply_branding
      ;;
    brand-asset)
      apply_brand_asset
      ;;
    recharge-center|recharge-placeholder)
      apply_recharge_center
      ;;
    docs-page)
      apply_docs_page
      ;;
    terms-page)
      apply_terms_page
      ;;
    region-headers)
      ensure_jiyu_region_headers
      ;;
    region-enforcement)
      set_jiyu_region_enforcement "${2:-}"
      ;;
    cn-production)
      set_jiyu_cn_production "${2:-}"
      ;;
    upstream-allowlist)
      apply_upstream_allowlist
      ;;
    harden-apache)
      harden_apache_admin_updates
      ;;
    postgres-preflight)
      harden_postgresql_runtime
      ;;
    cloudflare-origin-443)
      apply_cloudflare_origin_443
      ;;
    confirm-cloudflare-origin-443)
      confirm_cloudflare_origin_443
      ;;
    rollback-cloudflare-origin-443)
      rollback_cloudflare_origin_443
      ;;
    responses-websocket)
      repair_apache_responses_websocket_proxy
      ;;
    openai-ws-http-bridge)
      set_openai_ws_mode_router true
      ;;
    openai-ws-legacy)
      set_openai_ws_mode_router false
      ;;
    cutover)
      cutover_to_sub2api
      ;;
    clean-apache)
      clean_apache_after_cutover
      ;;
    rollback-cutover)
      rollback_cutover
      ;;
    purge-newapi)
      purge_newapi
      ;;
    status)
      show_status
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
