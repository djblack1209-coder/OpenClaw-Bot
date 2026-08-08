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
readonly APACHE_SITE="/etc/apache2/sites-available/frist-api.conf"
readonly APACHE_ROLLBACK_FILE="${STATE_DIR}/apache-before-sub2api.conf"
readonly UPDATE_STATE_FILE="${STATE_DIR}/upstream-release.json"
readonly NEWAPI_SERVICE="openclaw-newapi.service"
readonly DOMAIN="${SUB2API_PUBLIC_DOMAIN:-jiyu.245334.xyz}"
readonly HEALTH_URL="http://127.0.0.1:18080/health"
readonly LOCK_FILE="/run/lock/sub2api-update.lock"
readonly SITE_BRAND_NAME="${SUB2API_SITE_NAME:-JIYU AI}"
readonly SITE_BRAND_SUBTITLE="${SUB2API_SITE_SUBTITLE:-Unified AI API Gateway}"
readonly RECHARGE_PAGE_SLUG="recharge-center"
readonly DOCS_PAGE_SLUG="docs"
readonly BRAND_LOGO_SOURCE="${SUB2API_BRAND_LOGO_SOURCE:-/usr/local/share/jiyu-ai/jiyu-ai-logo.png}"
readonly BRAND_LOGO_PUBLIC_PATH="/api/v1/pages/${DOCS_PAGE_SLUG}/images/jiyu-ai-logo.png"
readonly UPSTREAM_ALLOWLIST_HOSTS="api.openai.com,api.anthropic.com,api.kimi.com,api.moonshot.ai,api.moonshot.cn,open.bigmodel.cn,api.minimaxi.com,generativelanguage.googleapis.com,cloudcode-pa.googleapis.com,*.openai.azure.com,api.aigo0.com,www.huyunapi.com"

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
Restart=on-failure
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

configure_postgresql() {
  local database_password="$1"
  local postgresql_unit
  postgresql_unit="$(postgresql_cluster_unit)"
  # 服务器收紧了 /var/log 权限，只给 postgres 增加穿越权限，不开放目录列表。
  if ! runuser -u postgres -- test -x /var/log; then
    setfacl -m u:postgres:--x /var/log
  fi
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
EOF
  chown root:root "$ENV_FILE"
  chmod 0600 "$ENV_FILE"
}

apply_upstream_allowlist() {
  require_root
  require_linux
  [[ -f "$ENV_FILE" ]] || fail "找不到 Sub2API 环境配置: ${ENV_FILE}"

  local temporary_file
  temporary_file="$(mktemp)"
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
  systemctl restart "$SUB2API_SERVICE"
  wait_for_health 90 || fail "应用上游域名白名单后健康检查失败。"
  log "上游域名白名单已收紧为官方默认域名及 api.aigo0.com、www.huyunapi.com。"
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
  install -d -m 0750 -o root -g sub2api-redis "$CONFIG_DIR"
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

  chown root:sub2api-redis "$CONFIG_DIR" "$REDIS_CONFIG"
  chmod 0750 "$CONFIG_DIR"
  chmod 0640 "$REDIS_CONFIG"
  chmod 0600 "$ENV_FILE"
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

apply_recharge_placeholder() {
  require_root
  require_linux
  require_command psql

  local pages_dir
  pages_dir="${INSTALL_DIR}/data/pages"
  install -d -m 0750 -o sub2api -g sub2api "$pages_dir"

  cat >"${pages_dir}/${RECHARGE_PAGE_SLUG}.md" <<'MARKDOWN'
# JIYU AI 充值中心

当前充值通道正在完成商品与自动发货验收。验收完成前不会展示无法付款的假入口。

充值后的标准流程：注册或登录 → 兑换余额 → 创建 API 密钥 → 导入 CC Switch → 开始使用。

如已持有兑换码，请直接前往 [兑换中心](/redeem)。
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

  systemctl restart "$SUB2API_SERVICE"
  wait_for_health 90 || fail "应用充值中心预留页后健康检查失败。"
  log "充值中心已使用同源 Markdown 模式预留，未向外部网站传递用户令牌。"
}

apply_docs_page() {
  require_root
  require_linux
  require_command psql

  local pages_dir
  pages_dir="${INSTALL_DIR}/data/pages"
  install -d -m 0750 -o sub2api -g sub2api "$pages_dir"

  cat >"${pages_dir}/${DOCS_PAGE_SLUG}.md" <<'MARKDOWN'
<style>
@media (max-width: 640px) {
  .custom-page-layout .toc-sidebar { display: none !important; }
}
</style>

# JIYU AI 使用文档

> 当前为邀请内测。JIYU AI 不向中国大陆及其他受限制、制裁或上游禁止服务的地区开放。

## 下载 CC Switch

官方版本：**v3.19.2**（2026-08-06 发布）

<div style="display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 24px">
  <a href="https://github.com/farion1231/cc-switch/releases/download/v3.19.2/CC-Switch-v3.19.2-macOS.dmg" target="_blank" rel="noopener noreferrer" style="display:inline-flex;align-items:center;padding:9px 14px;border-radius:6px;background:#0f766e;color:#fff;text-decoration:none;font-weight:650">下载 macOS</a>
  <a href="https://github.com/farion1231/cc-switch/releases/download/v3.19.2/CC-Switch-v3.19.2-Windows.msi" target="_blank" rel="noopener noreferrer" style="display:inline-flex;align-items:center;padding:9px 14px;border-radius:6px;background:#111827;color:#fff;text-decoration:none;font-weight:650">下载 Windows</a>
  <a href="https://github.com/farion1231/cc-switch/releases/download/v3.19.2/CC-Switch-v3.19.2-Linux-x86_64.AppImage" target="_blank" rel="noopener noreferrer" style="display:inline-flex;align-items:center;padding:9px 14px;border-radius:6px;background:#f97316;color:#fff;text-decoration:none;font-weight:650">下载 Linux</a>
  <a href="https://github.com/farion1231/cc-switch/releases/latest" target="_blank" rel="noopener noreferrer" style="display:inline-flex;align-items:center;padding:9px 14px;border:1px solid #94a3b8;border-radius:6px;color:inherit;text-decoration:none;font-weight:650">全部官方版本</a>
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

backup_database() {
  local destination="$1"
  install -d -m 0700 -o root -g root "$destination"
  runuser -u postgres -- pg_dump --format=custom sub2api >"${destination}/sub2api.dump"
  cp -a "${INSTALL_DIR}/sub2api" "${INSTALL_DIR}/VERSION" "$ENV_FILE" \
    "$REDIS_CONFIG" "$APACHE_SITE" "${destination}/"
  if [[ -f "${INSTALL_DIR}/data/config.yaml" ]]; then
    cp -a "${INSTALL_DIR}/data/config.yaml" "${destination}/"
  fi
  if [[ -d "${INSTALL_DIR}/data/pages" ]]; then
    cp -a "${INSTALL_DIR}/data/pages" "${destination}/pages"
  fi
  if [[ -d /usr/local/share/jiyu-ai ]]; then
    cp -a /usr/local/share/jiyu-ai "${destination}/brand-assets"
  fi
  cp -a "/etc/systemd/system/${SUB2API_SERVICE}" \
    "/etc/systemd/system/${REDIS_SERVICE}" \
    "/etc/systemd/system/${UPDATE_SERVICE}" \
    "/etc/systemd/system/${UPDATE_TIMER}" \
    "/etc/systemd/system/${BACKUP_SERVICE}" \
    "/etc/systemd/system/${BACKUP_TIMER}" \
    "${destination}/"
  find "$destination" -maxdepth 2 -type f -print0 | sort -z | \
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
  systemctl reload apache2.service
  log "已禁止浏览器直接更新或回滚生产二进制。"
}

backup_legacy_newapi() {
  local timestamp archive
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  archive="${BACKUP_ROOT}/legacy-newapi-before-cutover-${timestamp}.tar.gz"
  local candidates=(
    opt/frist-api/data/newapi
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

verify_public_health() {
  curl -fsS --max-time 15 "https://${DOMAIN}/health" >/dev/null
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

  if ! apache2ctl configtest; then
    cp -a "$APACHE_ROLLBACK_FILE" "$APACHE_SITE"
    fail "Apache 配置校验失败，已恢复原配置。"
  fi
  systemctl reload apache2.service

  if ! verify_public_health; then
    cp -a "$APACHE_ROLLBACK_FILE" "$APACHE_SITE"
    apache2ctl configtest
    systemctl reload apache2.service
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
  if ! apache2ctl configtest; then
    cp -a "$temporary_backup" "$APACHE_SITE"
    fail "清理旧品牌注入后 Apache 校验失败，已恢复。"
  fi
  systemctl reload apache2.service
  if ! verify_public_health; then
    cp -a "$temporary_backup" "$APACHE_SITE"
    apache2ctl configtest
    systemctl reload apache2.service
    fail "清理旧品牌注入后公网健康失败，已恢复。"
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
  apache2ctl configtest
  systemctl reload apache2.service
  curl -fsS --max-time 15 "https://${DOMAIN}/api/status" >/dev/null || \
    fail "Apache 已恢复，但旧 New-API 公网状态检查失败。"
  log "域名已回滚到旧 New-API。Sub2API 服务保持运行，便于排障。"
}

scrub_newapi_env_file() {
  local env_path="$1"
  [[ -f "$env_path" ]] || return 0
  local cleaned_env
  cleaned_env="$(mktemp)"
  awk '!/^FRIST_API_NEWAPI_/ && !/^FRIST_API_REQUIRE_NEWAPI_DATABASE=/' \
    "$env_path" >"$cleaned_env"
  cat >>"$cleaned_env" <<'EOF'
FRIST_API_NEWAPI_ENABLED=0
FRIST_API_NEWAPI_GATEWAY_ENABLED=0
FRIST_API_REQUIRE_NEWAPI_DATABASE=0
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
  if [[ -f /etc/frist-api/newapi.env ]]; then
    shred -u -- /etc/frist-api/newapi.env
  fi
  if [[ -d /opt/frist-api/data/newapi ]]; then
    find /opt/frist-api/data/newapi -xdev -type f -exec shred -u -- {} +
    find /opt/frist-api/data/newapi -xdev -depth -mindepth 1 -delete
    rmdir /opt/frist-api/data/newapi
  fi
  if [[ -f /usr/local/bin/openclaw-newapi ]]; then
    unlink /usr/local/bin/openclaw-newapi
  fi

  rm -f "/etc/systemd/system/${NEWAPI_SERVICE}"
  find /etc/systemd/system -maxdepth 3 -type l -name "$NEWAPI_SERVICE" -delete
  if [[ -d /opt/frist-api/backups ]]; then
    local legacy_path
    local legacy_paths=()
    while IFS= read -r -d '' legacy_path; do
      legacy_paths+=("$legacy_path")
    done < <(
      find /opt/frist-api/backups -depth \
        \( -iname '*newapi*' -o -iname '*new-api*' \) -print0
    )
    for legacy_path in "${legacy_paths[@]}"; do
      [[ "$legacy_path" == /opt/frist-api/backups/* ]] || fail "拒绝删除备份根目录外的路径。"
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

  scrub_newapi_env_file /etc/frist-api/frist-api.env
  scrub_newapi_env_file /opt/frist-api/.env

  systemctl daemon-reload
  [[ ! -e /opt/frist-api/data/newapi ]] || fail "旧 New-API 数据目录仍存在。"
  [[ ! -e /usr/local/bin/openclaw-newapi ]] || fail "旧 New-API 二进制仍存在。"
  [[ ! -e "/etc/systemd/system/${NEWAPI_SERVICE}" ]] || fail "旧 New-API 服务定义仍存在。"
  verify_public_health || fail "清理后 Sub2API 公网健康检查失败。"
  log "Oracle 上的旧 New-API 数据、密钥、二进制、服务定义和同名本地备份已清理。"
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
  if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
    log "内网健康检查: 通过"
  else
    log "内网健康检查: 失败"
    return 1
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
  backup             立即生成数据库、页面、品牌、配置和二进制一致性备份
  brand              重新应用 JIYU AI 网站名称、副标题和 JY Logo
  brand-asset        重新发布邮件和文档使用的 JIYU AI 图形 Logo
  recharge-placeholder  重新应用充值中心外部窗口预留页
  docs-page           重新应用文档入口和 CC Switch 下载、导入说明
  upstream-allowlist    重新应用两个指定上游的安全域名白名单
  harden-apache      禁止浏览器直接更新或回滚生产二进制
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
    backup)
      daily_backup
      ;;
    brand)
      apply_branding
      ;;
    brand-asset)
      apply_brand_asset
      ;;
    recharge-placeholder)
      apply_recharge_placeholder
      ;;
    docs-page)
      apply_docs_page
      ;;
    upstream-allowlist)
      apply_upstream_allowlist
      ;;
    harden-apache)
      harden_apache_admin_updates
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
