#!/usr/bin/env python3
"""
OpenClaw 数据库自动备份 — 使用 SQLite 在线备份 API (安全, 不影响运行中的服务).

用法:
  python3 scripts/backup_databases.py              # 手动运行
  # 或: 由 ExecutionScheduler 自动调用 (每日 04:00 ET)

备份策略:
  - 每日备份: 保留 7 天
  - 每周备份 (周日): 保留 4 周
  - 备份目录: data/backups/
  - 格式: {db_name}_{YYYY-MM-DD}.db
"""
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
BACKUP_DIR = DATA_DIR / "backups"

# All known databases to back up (order: critical first)
DATABASES = [
    "trading.db",
    "portfolio.db",
    "history.db",
    "shared_memory.db",
    "execution_hub.db",
    "xianyu_chat.db",
    "feedback.db",
    "cost_analytics.db",
    "deploy_licenses.db",
]


def backup_all() -> dict:
    """Back up all databases. Returns status dict."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results = {}

    for db_name in DATABASES:
        src = DATA_DIR / db_name
        if not src.exists():
            results[db_name] = "skipped (not found)"
            continue

        dst = BACKUP_DIR / f"{db_name.replace('.db', '')}_{today}.db"
        if dst.exists():
            results[db_name] = "skipped (already exists today)"
            continue

        try:
            # 使用 SQLite 在线备份 API（并发写入安全）
            with sqlite3.connect(str(src)) as source_conn, \
                 sqlite3.connect(str(dst)) as backup_conn:
                source_conn.backup(backup_conn)

            # 验证备份完整性
            try:
                with sqlite3.connect(str(dst)) as check_conn:
                    result = check_conn.execute("PRAGMA integrity_check").fetchone()
                    if result[0] != "ok":
                        logger.error("[备份] 完整性检查失败: %s → %s", db_name, result[0])
                        dst.unlink(missing_ok=True)  # 删除损坏的备份
                        results[db_name] = f"FAILED: integrity check ({result[0]})"
                        continue
            except Exception as e:
                logger.error("[备份] 完整性检查异常: %s", e)

            size_mb = dst.stat().st_size / (1024 * 1024)
            results[db_name] = f"OK ({size_mb:.1f} MB)"
            logger.info("[Backup] %s → %s (%.1f MB)", db_name, dst.name, size_mb)
        except Exception as e:
            results[db_name] = f"FAILED: {e}"
            logger.error("[Backup] %s failed: %s", db_name, e)

    # Cleanup old backups
    cleanup_count = _cleanup_old_backups()
    results["_cleanup"] = f"Removed {cleanup_count} old backups"

    return results


def _cleanup_old_backups(daily_keep: int = 7, weekly_keep: int = 4) -> int:
    """Remove backups older than retention policy.

    Retention:
    - Sunday backups (weekly): keep ``weekly_keep`` weeks
    - Other days (daily): keep ``daily_keep`` days
    """
    if not BACKUP_DIR.exists():
        return 0

    removed = 0
    cutoff_daily = datetime.now(timezone.utc) - timedelta(days=daily_keep)
    cutoff_weekly = datetime.now(timezone.utc) - timedelta(weeks=weekly_keep)

    for f in sorted(BACKUP_DIR.glob("*.db")):
        try:
            # Extract date from filename: dbname_2026-03-24.db
            date_str = f.stem.rsplit("_", 1)[-1]
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            is_sunday = file_date.weekday() == 6  # Weekly backup

            if is_sunday and file_date < cutoff_weekly:
                f.unlink()
                removed += 1
                logger.debug("[Backup] Removed old weekly: %s", f.name)
            elif not is_sunday and file_date < cutoff_daily:
                f.unlink()
                removed += 1
                logger.debug("[Backup] Removed old daily: %s", f.name)
        except (ValueError, IndexError):
            continue  # Skip files that don't match naming convention

    return removed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("=== OpenClaw Database Backup ===")
    print(f"Source: {DATA_DIR}")
    print(f"Target: {BACKUP_DIR}")
    print()
    results = backup_all()
    for db, status in results.items():
        print(f"  {db}: {status}")
