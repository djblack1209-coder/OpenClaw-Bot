"""
全局 SQLite 连接工厂

统一的数据库连接管理：WAL 模式 + busy_timeout + 文件权限保护。
所有模块的 SQLite 连接都应通过此模块获取，避免样板代码重复。
"""

import logging
import os
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def _secure_db_permissions(db_path: str) -> None:
    """设置数据库文件权限为仅所有者可读写 (0o600)，防止其他用户读取敏感数据"""
    try:
        if os.path.exists(db_path):
            os.chmod(db_path, 0o600)
            for suffix in ("-wal", "-shm"):
                aux = db_path + suffix
                if os.path.exists(aux):
                    os.chmod(aux, 0o600)
    except OSError as e:
        logger.debug("设置数据库文件权限失败 (非致命): %s", e)


@contextmanager
def get_conn(db_path: str, *, row_factory: type | None = None):
    """获取 SQLite 连接的上下文管理器，异常时自动回滚。

    参数:
        db_path: 数据库文件路径（字符串）
        row_factory: 可选的行工厂，例如 sqlite3.Row

    使用示例::

        from src.db_utils import get_conn
        with get_conn("/path/to/db.sqlite", row_factory=sqlite3.Row) as conn:
            conn.execute("SELECT ...")
    """
    path = str(db_path)
    # 确保数据库目录存在
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    if row_factory is not None:
        conn.row_factory = row_factory
    _secure_db_permissions(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
