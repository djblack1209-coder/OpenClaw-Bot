"""
简易磁盘缓存 — 替代有 CVE-2025-69872 的 diskcache

基于 SQLite3 (标准库) 实现，零外部依赖，接口兼容 diskcache.Cache 的常用方法。
支持: get / set(expire=) / len / volume / close / __contains__ / __getitem__ / __setitem__ / __delitem__

线程安全: 内部使用 threading.Lock 保护所有写操作。
"""

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 序列化/反序列化使用 pickle，与 diskcache 行为一致
# diskcache 默认用 pickle 存储复杂 Python 对象（如 LiteLLM Response）
import pickle


class DiskCache:
    """SQLite3 实现的磁盘缓存，接口兼容 diskcache.Cache 常用方法。

    Args:
        directory: 缓存文件存放目录
        size_limit: 最大缓存体积（字节），超过后写入仍成功但 cull() 会清理
        eviction_policy: 淘汰策略名称（仅记录，实际固定使用 LRU）
        statistics: 是否启用统计（仅记录，不影响行为）
    """

    def __init__(
        self,
        directory: str = "/tmp/openclaw-cache",
        size_limit: int = 512 * 1024 * 1024,
        eviction_policy: str = "least-recently-used",
        statistics: bool = False,
    ):
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._db_path = str(self._directory / "cache.db")
        self._size_limit = size_limit
        self._lock = threading.Lock()

        # 使用 check_same_thread=False 允许多线程共享连接
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        # 启用 WAL 模式提升并发读写性能
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL,
                expire REAL,
                access_time REAL NOT NULL,
                size INTEGER NOT NULL
            )"""
        )
        # 为过期时间建索引，加速清理
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expire ON cache(expire)"
        )
        self._conn.commit()
        logger.debug("[DiskCache] 初始化完成: %s", directory)

    # ---- 核心读写 ----

    def get(self, key: str, default: Any = None) -> Any:
        """读取缓存值，过期则自动删除并返回 default。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT value, expire FROM cache WHERE key=?", (key,)
            ).fetchone()
            if row is None:
                return default
            blob, expire = row
            # 检查是否过期
            if expire is not None and expire < time.time():
                self._conn.execute("DELETE FROM cache WHERE key=?", (key,))
                self._conn.commit()
                return default
            # 更新访问时间（LRU 支持）
            self._conn.execute(
                "UPDATE cache SET access_time=? WHERE key=?",
                (time.time(), key),
            )
            self._conn.commit()
            try:
                return pickle.loads(blob)
            except Exception as e:
                logger.warning("[DiskCache] 反序列化失败 key=%s: %s", key, e)
                return default

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        """写入缓存值，可选设置 TTL（秒）。"""
        exp_time = time.time() + expire if expire else None
        try:
            blob = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            logger.warning("[DiskCache] 序列化失败 key=%s: %s", key, e)
            return
        size = len(blob)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expire, access_time, size) "
                "VALUES (?, ?, ?, ?, ?)",
                (key, blob, exp_time, time.time(), size),
            )
            self._conn.commit()

    # ---- 字典风格访问 ----

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __getitem__(self, key: str) -> Any:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache WHERE key=?", (key,))
            self._conn.commit()

    def __len__(self) -> int:
        """返回缓存条目数（不含已过期的）。"""
        with self._lock:
            # 先清理过期条目
            now = time.time()
            self._conn.execute(
                "DELETE FROM cache WHERE expire IS NOT NULL AND expire < ?",
                (now,),
            )
            self._conn.commit()
            row = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()
            return row[0] if row else 0

    # ---- 统计 ----

    def volume(self) -> int:
        """返回缓存总体积（字节），兼容 diskcache.Cache.volume()。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(size), 0) FROM cache"
            ).fetchone()
            return row[0] if row else 0

    # ---- 清理 ----

    def cull(self) -> int:
        """按 LRU 策略淘汰条目直到体积低于 size_limit。返回删除条目数。"""
        deleted = 0
        with self._lock:
            # 先清理过期的
            now = time.time()
            cur = self._conn.execute(
                "DELETE FROM cache WHERE expire IS NOT NULL AND expire < ?",
                (now,),
            )
            deleted += cur.rowcount

            # 检查是否还需要按 LRU 淘汰
            total_size = self._conn.execute(
                "SELECT COALESCE(SUM(size), 0) FROM cache"
            ).fetchone()[0]

            while total_size > self._size_limit:
                # 删除最久未访问的一条
                oldest = self._conn.execute(
                    "SELECT key, size FROM cache ORDER BY access_time ASC LIMIT 1"
                ).fetchone()
                if oldest is None:
                    break
                self._conn.execute(
                    "DELETE FROM cache WHERE key=?", (oldest[0],)
                )
                total_size -= oldest[1]
                deleted += 1

            self._conn.commit()
        return deleted

    def clear(self) -> None:
        """清空所有缓存。"""
        with self._lock:
            self._conn.execute("DELETE FROM cache")
            self._conn.commit()

    # ---- 生命周期 ----

    def close(self) -> None:
        """关闭数据库连接，确保数据刷盘。"""
        try:
            self._conn.close()
            logger.debug("[DiskCache] 已关闭: %s", self._directory)
        except Exception as e:
            logger.debug("[DiskCache] 关闭时异常(可忽略): %s", e)


# ---- 便捷别名，兼容 diskcache.Cache 的使用方式 ----
Cache = DiskCache
