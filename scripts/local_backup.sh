#!/usr/bin/env bash
# OpenEverything 本地备份：排除密钥、虚拟环境、node_modules 和运行日志。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_BACKUP_DIR="$HOME/Desktop/OpenEverything-backups"
ICLOUD_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/OpenEverythingBackups"
BACKUP_DIR="${OPENCLAW_BACKUP_DIR:-$([[ -d "$ICLOUD_DIR" ]] && echo "$ICLOUD_DIR" || echo "$DEFAULT_BACKUP_DIR") }"
BACKUP_DIR="${BACKUP_DIR% }"
RETENTION_DAYS="${OPENCLAW_BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$BACKUP_DIR/openeverything-$STAMP.tgz"

mkdir -p "$BACKUP_DIR"
cd "$ROOT_DIR"

tar -czf "$ARCHIVE" \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.venv*' \
  --exclude='*.env' \
  --exclude='*.env.*' \
  --exclude='logs' \
  --exclude='output' \
  --exclude='data/backups' \
  docs Makefile scripts apps/frist-api packages/clawbot/src packages/clawbot/scripts packages/clawbot/tests packages/clawbot/config/.env.example

find "$BACKUP_DIR" -name 'openeverything-*.tgz' -type f -mtime "+$RETENTION_DAYS" -delete
printf '{"ok":true,"archive":"%s","retention_days":%s}\n' "$ARCHIVE" "$RETENTION_DAYS"
