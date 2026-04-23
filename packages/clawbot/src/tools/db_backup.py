"""数据库自动备份服务 — SQLite 热备份（不需要停服）

通过 SQLite 的 VACUUM INTO 命令进行热备份，
不需要停止服务即可安全备份数据库文件。
每天凌晨2点自动执行，保留最近7天的备份。
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_DATA_DIR = Path.home() / ".openclaw"
DEFAULT_BACKUP_DIR = DEFAULT_DATA_DIR / "backups"
MAX_BACKUPS = 7  # 保留天数


class DatabaseBackupService:
    """SQLite 数据库自动备份服务"""

    def __init__(
        self,
        data_dir: Path | None = None,
        backup_dir: Path | None = None,
        max_backups: int = MAX_BACKUPS,
    ):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.backup_dir = backup_dir or DEFAULT_BACKUP_DIR
        self.max_backups = max_backups

    async def daily_backup(self) -> dict:
        """执行每日备份 — 适合通过 APScheduler 注册为定时任务

        Returns:
            dict: 备份结果摘要
        """
        try:
            return await self._do_backup()
        except Exception as e:
            logger.error("数据库备份失败: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    async def _do_backup(self) -> dict:
        """执行实际备份操作"""
        # 确保备份目录存在
        today = datetime.now().strftime("%Y%m%d")
        backup_path = self.backup_dir / today
        backup_path.mkdir(parents=True, exist_ok=True)

        # 查找所有 .db 文件
        db_files = list(self.data_dir.glob("*.db"))
        if not db_files:
            logger.info("未找到需要备份的数据库文件")
            return {"success": True, "backed_up": 0, "message": "无数据库文件"}

        backed_up = 0
        errors = []

        for db_file in db_files:
            dest = backup_path / db_file.name
            try:
                # 使用 VACUUM INTO 热备份（不锁表、不阻塞读写）
                import aiosqlite
                async with aiosqlite.connect(str(db_file)) as conn:
                    await conn.execute(f"VACUUM INTO '{dest}'")
                backed_up += 1
                logger.debug("已备份: %s → %s", db_file.name, dest)
            except ImportError:
                # aiosqlite 不可用时，用文件拷贝（次优方案，可能有锁冲突）
                try:
                    shutil.copy2(str(db_file), str(dest))
                    backed_up += 1
                    logger.debug("已备份(文件拷贝): %s → %s", db_file.name, dest)
                except OSError as e:
                    errors.append(f"{db_file.name}: {e}")
                    logger.warning("备份 %s 失败: %s", db_file.name, e)
            except Exception as e:
                errors.append(f"{db_file.name}: {e}")
                logger.warning("备份 %s 失败: %s", db_file.name, e)

        # 清理过期备份
        cleaned = await self._cleanup_old_backups()

        result = {
            "success": len(errors) == 0,
            "backed_up": backed_up,
            "total_db_files": len(db_files),
            "errors": errors,
            "backup_path": str(backup_path),
            "cleaned_old": cleaned,
        }

        if errors:
            logger.warning("数据库备份部分失败: %d/%d 成功", backed_up, len(db_files))
        else:
            logger.info("数据库备份完成: %d 个文件 → %s", backed_up, backup_path)

        return result

    async def _cleanup_old_backups(self) -> int:
        """清理超过保留天数的旧备份"""
        if not self.backup_dir.exists():
            return 0

        # 列出所有日期目录并排序
        backup_dirs = sorted(
            [d for d in self.backup_dir.iterdir() if d.is_dir() and d.name.isdigit()],
            key=lambda d: d.name,
            reverse=True,
        )

        cleaned = 0
        for old_dir in backup_dirs[self.max_backups:]:
            try:
                shutil.rmtree(str(old_dir))
                cleaned += 1
                logger.debug("已清理旧备份: %s", old_dir.name)
            except OSError as e:
                logger.warning("清理旧备份失败 %s: %s", old_dir.name, e)

        return cleaned

    async def get_backup_status(self) -> dict:
        """获取备份状态摘要 — 供 API 和 UI 展示"""
        if not self.backup_dir.exists():
            return {
                "configured": True,
                "last_backup": None,
                "backup_count": 0,
                "total_size_mb": 0,
            }

        backup_dirs = sorted(
            [d for d in self.backup_dir.iterdir() if d.is_dir() and d.name.isdigit()],
            key=lambda d: d.name,
            reverse=True,
        )

        total_size = sum(
            f.stat().st_size
            for d in backup_dirs
            for f in d.iterdir()
            if f.is_file()
        )

        last_backup = backup_dirs[0].name if backup_dirs else None
        if last_backup:
            # 转换 YYYYMMDD 为可读格式
            try:
                last_backup = datetime.strptime(last_backup, "%Y%m%d").strftime("%Y-%m-%d")
            except ValueError:
                pass

        return {
            "configured": True,
            "last_backup": last_backup,
            "backup_count": len(backup_dirs),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_backups": self.max_backups,
            "backup_dir": str(self.backup_dir),
        }
