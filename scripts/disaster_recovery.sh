#!/usr/bin/env bash
# OpenEverything 灾备恢复：默认 dry-run，必须显式 --confirm 才会覆盖文件。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${OPENCLAW_BACKUP_DIR:-$HOME/Desktop/OpenEverything-backups}"
FROM_R2=0
DRY_RUN=0
CONFIRM=0
ARCHIVE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-r2) FROM_R2=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --confirm) CONFIRM=1 ;;
    --archive) ARCHIVE="${2:-}"; shift ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

if (( FROM_R2 == 1 )); then
  echo "R2 restore requested: 当前脚本不会读取密钥；请先用 R2 工具下载最近备份到 $BACKUP_DIR，再运行本脚本 restore。"
fi

if [[ -z "$ARCHIVE" ]]; then
  ARCHIVE=$(ls -t "$BACKUP_DIR"/openeverything-*.tgz 2>/dev/null | head -1 || true)
fi
if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo '{"ok":false,"error":"backup_archive_not_found"}'
  exit 1
fi

if (( DRY_RUN == 1 || CONFIRM == 0 )); then
  echo "restore dry-run: 将从 $ARCHIVE 恢复到 $ROOT_DIR"
  tar -tzf "$ARCHIVE" | sed -n '1,40p'
  echo "真正恢复请运行：scripts/disaster_recovery.sh --archive '$ARCHIVE' --confirm"
  exit 0
fi

tmp="$ROOT_DIR/.restore-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$tmp"
tar -xzf "$ARCHIVE" -C "$tmp"
rsync -a "$tmp"/ "$ROOT_DIR"/
rm -rf "$tmp"
echo "restore complete: $ARCHIVE"
