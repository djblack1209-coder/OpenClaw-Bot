#!/usr/bin/env bash
# 管理 macOS 每日备份 LaunchAgent；实际任务始终先备份，再执行只读恢复演练。
set -euo pipefail
umask 077

LABEL="ai.openclaw.daily-backup"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
MANAGER_SCRIPT="$SCRIPT_DIR/manage_backup_launchagent.sh"
BACKUP_SCRIPT="$SCRIPT_DIR/local_backup.sh"
RECOVERY_SCRIPT="$SCRIPT_DIR/disaster_recovery.sh"
LAUNCH_AGENT_DIR="${OPENCLAW_LAUNCH_AGENT_DIR:-$HOME/Library/LaunchAgents}"
PLIST_PATH="$LAUNCH_AGENT_DIR/$LABEL.plist"
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/openclaw"
LOG_DIR="$STATE_ROOT/logs"
STDOUT_LOG="$LOG_DIR/daily-backup.stdout.log"
STDERR_LOG="$LOG_DIR/daily-backup.stderr.log"
BACKUP_HOUR="${OPENCLAW_BACKUP_HOUR:-3}"
BACKUP_MINUTE="${OPENCLAW_BACKUP_MINUTE:-30}"
SAFE_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
DOMAIN="gui/$(id -u)"
SERVICE_TARGET="$DOMAIN/$LABEL"
TEMP_PLIST=""
TEMP_RESULT=""

usage() {
  cat <<'EOF'
用法: scripts/manage_backup_launchagent.sh <install|status|uninstall|run>

  install    原子安装并加载每日备份 LaunchAgent
  status     输出是否已安装、是否已加载及执行时间
  uninstall  幂等卸载并删除 LaunchAgent
  run        执行一次备份；成功后强制运行 disaster_recovery.sh --drill

可选环境变量:
  OPENCLAW_BACKUP_HOUR / OPENCLAW_BACKUP_MINUTE
  OPENCLAW_BACKUP_DIR / OPENCLAW_HOME_DIR
  OPENCLAW_BACKUP_RETENTION_DAYS / OPENCLAW_BACKUP_RETENTION_COUNT
  OPENCLAW_BACKUP_OFFSITE_DIR + OPENCLAW_BACKUP_GPG_RECIPIENT
  GNUPGHOME / XDG_DATA_HOME / XDG_STATE_HOME
EOF
}

fail() {
  printf '%s\n' "$1" >&2
  exit "${2:-1}"
}

cleanup() {
  if [[ -n "$TEMP_PLIST" && -e "$TEMP_PLIST" ]]; then
    rm -f "$TEMP_PLIST"
  fi
  if [[ -n "$TEMP_RESULT" && -e "$TEMP_RESULT" ]]; then
    rm -f "$TEMP_RESULT"
  fi
}
trap cleanup EXIT INT TERM

validate_text() {
  local name="$1"
  local value="$2"
  case "$value" in
    *$'\n'*|*$'\r'*|*$'\t'*) fail "invalid_${name}: control_character" 2 ;;
  esac
}

validate_absolute_path() {
  local name="$1"
  local value="$2"
  [[ -z "$value" ]] && return
  validate_text "$name" "$value"
  [[ "$value" == /* ]] || fail "${name}_must_be_absolute" 2
}

validate_schedule() {
  [[ "$BACKUP_HOUR" =~ ^[0-9]{1,2}$ ]] || fail "invalid_backup_hour" 2
  [[ "$BACKUP_MINUTE" =~ ^[0-9]{1,2}$ ]] || fail "invalid_backup_minute" 2
  BACKUP_HOUR=$((10#$BACKUP_HOUR))
  BACKUP_MINUTE=$((10#$BACKUP_MINUTE))
  (( BACKUP_HOUR >= 0 && BACKUP_HOUR <= 23 )) || fail "invalid_backup_hour" 2
  (( BACKUP_MINUTE >= 0 && BACKUP_MINUTE <= 59 )) || fail "invalid_backup_minute" 2
}

validate_runtime_paths() {
  local path_name
  for path_name in \
    OPENCLAW_BACKUP_DIR \
    OPENCLAW_HOME_DIR \
    OPENCLAW_BACKUP_OFFSITE_DIR \
    GNUPGHOME \
    XDG_DATA_HOME \
    XDG_STATE_HOME; do
    validate_absolute_path "$(printf '%s' "$path_name" | tr '[:upper:]' '[:lower:]')" "${!path_name:-}"
  done
  validate_text "gpg_recipient" "${OPENCLAW_BACKUP_GPG_RECIPIENT:-}"

  if [[ -n "${OPENCLAW_BACKUP_OFFSITE_DIR:-}" || -n "${OPENCLAW_BACKUP_GPG_RECIPIENT:-}" ]]; then
    [[ -n "${OPENCLAW_BACKUP_OFFSITE_DIR:-}" && -n "${OPENCLAW_BACKUP_GPG_RECIPIENT:-}" ]] \
      || fail "offsite_config_incomplete" 2
  fi
}

require_manager_files() {
  local file
  for file in "$MANAGER_SCRIPT" "$BACKUP_SCRIPT" "$RECOVERY_SCRIPT"; do
    [[ -f "$file" && -x "$file" && ! -L "$file" ]] || fail "unsafe_or_missing_script: $file"
  done
}

require_macos() {
  [[ "$(uname -s)" == "Darwin" ]] || fail "macos_required" 2
  command -v launchctl >/dev/null 2>&1 || fail "launchctl_not_found" 127
}

launchctl_command() {
  local executable
  executable="$(command -v launchctl)"
  [[ "$executable" == /* && -x "$executable" ]] || fail "launchctl_not_safe" 127
  "$executable" "$@"
}

print_status() {
  local loaded="$1"
  local installed="$2"
  python3 - "$LABEL" "$PLIST_PATH" "$loaded" "$installed" "$BACKUP_HOUR" "$BACKUP_MINUTE" <<'PY'
import json
import sys

print(json.dumps({
    "label": sys.argv[1],
    "plist": sys.argv[2],
    "loaded": sys.argv[3] == "1",
    "installed": sys.argv[4] == "1",
    "hour": int(sys.argv[5]),
    "minute": int(sys.argv[6]),
}, ensure_ascii=False))
PY
}

create_plist() {
  local destination="$1"
  python3 - \
    "$destination" "$LABEL" "$MANAGER_SCRIPT" "$ROOT_DIR" \
    "$STDOUT_LOG" "$STDERR_LOG" "$BACKUP_HOUR" "$BACKUP_MINUTE" \
    "$HOME" "$SAFE_PATH" \
    "${OPENCLAW_BACKUP_DIR:-}" "${OPENCLAW_HOME_DIR:-}" \
    "${OPENCLAW_BACKUP_RETENTION_DAYS:-}" "${OPENCLAW_BACKUP_RETENTION_COUNT:-}" \
    "${OPENCLAW_BACKUP_OFFSITE_DIR:-}" "${OPENCLAW_BACKUP_GPG_RECIPIENT:-}" \
    "${GNUPGHOME:-}" "${XDG_DATA_HOME:-}" "${XDG_STATE_HOME:-}" <<'PY'
import pathlib
import plistlib
import sys

(
    destination,
    label,
    manager,
    root,
    stdout_log,
    stderr_log,
    hour,
    minute,
    home,
    safe_path,
    backup_dir,
    openclaw_home,
    retention_days,
    retention_count,
    offsite_dir,
    gpg_recipient,
    gnupg_home,
    xdg_data_home,
    xdg_state_home,
) = sys.argv[1:]

environment = {"HOME": home, "PATH": safe_path}
optional = {
    "OPENCLAW_BACKUP_DIR": backup_dir,
    "OPENCLAW_HOME_DIR": openclaw_home,
    "OPENCLAW_BACKUP_RETENTION_DAYS": retention_days,
    "OPENCLAW_BACKUP_RETENTION_COUNT": retention_count,
    "OPENCLAW_BACKUP_OFFSITE_DIR": offsite_dir,
    "OPENCLAW_BACKUP_GPG_RECIPIENT": gpg_recipient,
    "GNUPGHOME": gnupg_home,
    "XDG_DATA_HOME": xdg_data_home,
    "XDG_STATE_HOME": xdg_state_home,
}
environment.update({key: value for key, value in optional.items() if value})

payload = {
    "Label": label,
    "ProgramArguments": ["/bin/bash", manager, "run"],
    "WorkingDirectory": root,
    "StartCalendarInterval": {"Hour": int(hour), "Minute": int(minute)},
    "RunAtLoad": False,
    "KeepAlive": False,
    "ProcessType": "Background",
    "LowPriorityIO": True,
    "ThrottleInterval": 300,
    "Umask": 0o077,
    "StandardOutPath": stdout_log,
    "StandardErrorPath": stderr_log,
    "EnvironmentVariables": environment,
}

path = pathlib.Path(destination)
with path.open("wb") as output:
    plistlib.dump(payload, output, fmt=plistlib.FMT_XML, sort_keys=True)
PY
}

run_backup_and_drill() {
  local result_file archive
  require_manager_files
  validate_runtime_paths

  result_file="$(mktemp "${TMPDIR:-/tmp}/openclaw-daily-backup.XXXXXX")"
  TEMP_RESULT="$result_file"
  if [[ -n "${OPENCLAW_BACKUP_OFFSITE_DIR:-}" ]]; then
    if ! "$BACKUP_SCRIPT" --require-offsite > "$result_file"; then
      fail "daily_backup_failed"
    fi
  elif ! "$BACKUP_SCRIPT" > "$result_file"; then
    fail "daily_backup_failed"
  fi
  archive="$(python3 - "$result_file" <<'PY'
import json
import pathlib
import sys

lines = [line for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line]
if not lines:
    raise SystemExit("backup_result_missing")
payload = json.loads(lines[-1])
archive = payload.get("archive")
if payload.get("ok") is not True or not isinstance(archive, str):
    raise SystemExit("backup_result_invalid")
print(archive)
PY
)" || fail "backup_result_invalid"

  validate_absolute_path "backup_archive" "$archive"
  [[ "$archive" == *.tgz && -f "$archive" && ! -L "$archive" ]] || fail "backup_archive_invalid"
  "$RECOVERY_SCRIPT" --archive "$archive" --drill \
    || fail "daily_backup_drill_failed"
  cat "$result_file"
  rm -f "$result_file"
  TEMP_RESULT=""
}

install_agent() {
  local was_loaded=0
  require_macos
  require_manager_files
  validate_schedule
  validate_runtime_paths
  validate_absolute_path "launch_agent_dir" "$LAUNCH_AGENT_DIR"
  validate_absolute_path "log_dir" "$LOG_DIR"
  [[ ! -L "$LAUNCH_AGENT_DIR" && ! -L "$LOG_DIR" ]] || fail "unsafe_launchagent_path"
  [[ ! -d "$PLIST_PATH" ]] || fail "unsafe_launchagent_path"

  mkdir -p "$LAUNCH_AGENT_DIR" "$LOG_DIR"
  chmod 700 "$LAUNCH_AGENT_DIR" "$LOG_DIR"
  if launchctl_command print "$SERVICE_TARGET" >/dev/null 2>&1; then
    was_loaded=1
    launchctl_command bootout "$SERVICE_TARGET" \
      || fail "launchagent_bootout_failed"
  fi

  TEMP_PLIST="$(mktemp "$LAUNCH_AGENT_DIR/.$LABEL.plist.XXXXXX")"
  create_plist "$TEMP_PLIST"
  chmod 600 "$TEMP_PLIST"
  mv -f "$TEMP_PLIST" "$PLIST_PATH"
  TEMP_PLIST=""

  if ! launchctl_command bootstrap "$DOMAIN" "$PLIST_PATH"; then
    rm -f "$PLIST_PATH"
    fail "launchagent_bootstrap_failed"
  fi
  if ! launchctl_command print "$SERVICE_TARGET" >/dev/null 2>&1; then
    launchctl_command bootout "$SERVICE_TARGET" >/dev/null 2>&1 || true
    rm -f "$PLIST_PATH"
    fail "launchagent_verification_failed"
  fi

  python3 - "$PLIST_PATH" "$was_loaded" <<'PY'
import json
import sys

print(json.dumps({
    "ok": True,
    "action": "install",
    "plist": sys.argv[1],
    "replaced_loaded_job": sys.argv[2] == "1",
}, ensure_ascii=False))
PY
}

status_agent() {
  local loaded=0 installed=0
  require_macos
  validate_schedule
  if [[ -f "$PLIST_PATH" && ! -L "$PLIST_PATH" ]]; then
    installed=1
  fi
  if launchctl_command print "$SERVICE_TARGET" >/dev/null 2>&1; then
    loaded=1
  fi
  print_status "$loaded" "$installed"
}

uninstall_agent() {
  require_macos
  validate_absolute_path "launch_agent_dir" "$LAUNCH_AGENT_DIR"
  [[ ! -d "$PLIST_PATH" ]] || fail "unsafe_launchagent_path"
  if launchctl_command print "$SERVICE_TARGET" >/dev/null 2>&1; then
    launchctl_command bootout "$SERVICE_TARGET" \
      || fail "launchagent_bootout_failed"
  fi
  rm -f "$PLIST_PATH"
  printf '{"ok":true,"action":"uninstall","label":"%s"}\n' "$LABEL"
}

COMMAND="${1:-}"
case "$COMMAND" in
  install) install_agent ;;
  status) status_agent ;;
  uninstall) uninstall_agent ;;
  run) run_backup_and_drill ;;
  --help|-h|help) usage ;;
  "") usage; exit 2 ;;
  *) fail "unknown_command: $COMMAND" 2 ;;
esac
