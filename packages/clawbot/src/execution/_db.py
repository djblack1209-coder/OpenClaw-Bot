"""
Execution Hub — 数据库层
SQLite 连接管理和表结构定义
"""
import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "execution_hub.db"


def ensure_db_dir():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn(db_path=None):
    """获取数据库连接的上下文管理器"""
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path=None):
    """初始化所有数据库表"""
    with get_conn(db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS social_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            title TEXT,
            body TEXT,
            topic TEXT,
            status TEXT DEFAULT 'draft',
            sources TEXT,
            created_at TEXT,
            updated_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT,
            source TEXT DEFAULT 'news',
            enabled INTEGER DEFAULT 1,
            created_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS monitor_seen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id INTEGER,
            digest TEXT UNIQUE,
            seen_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS payout_watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT,
            issue_number INTEGER,
            label TEXT,
            status TEXT DEFAULT 'watching',
            created_at TEXT,
            last_checked_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS payout_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_id INTEGER,
            event_type TEXT,
            detail TEXT,
            created_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            updated_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            remind_at TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )""")
    logger.debug("[ExecutionDB] tables initialized")
