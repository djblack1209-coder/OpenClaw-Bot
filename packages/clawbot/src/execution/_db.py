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
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
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

        # v2.0: 新增重复提醒 + 用户隔离字段
        for col_sql in [
            "ALTER TABLE reminders ADD COLUMN recurrence_rule TEXT DEFAULT ''",
            "ALTER TABLE reminders ADD COLUMN user_chat_id INTEGER DEFAULT 0",
        ]:
            try:
                conn.execute(col_sql)
            except sqlite3.OperationalError as e:  # noqa: F841
                pass  # 列已存在

        # v2.1: 社媒互动数据表 — 记录帖子的点赞/评论/转发/浏览
        conn.execute("""CREATE TABLE IF NOT EXISTS post_engagement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id INTEGER,
            platform TEXT NOT NULL,
            post_url TEXT DEFAULT '',
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            checked_at REAL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (draft_id) REFERENCES social_drafts(id),
            UNIQUE(draft_id, platform)
        )""")

        # v2.2: 简易记账表
        conn.execute("""CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            category TEXT DEFAULT '其他',
            amount REAL NOT NULL,
            note TEXT DEFAULT '',
            ts REAL DEFAULT (strftime('%s','now'))
        )""")

        # v2.2.1: 给 expenses 表新增 type 列区分收入/支出 (安全 ALTER)
        try:
            conn.execute("ALTER TABLE expenses ADD COLUMN type TEXT DEFAULT 'expense'")
        except sqlite3.OperationalError as e:  # noqa: F841
            pass  # 列已存在

        # v2.2.2: 月预算表 — 存储用户的月度预算设定
        conn.execute("""CREATE TABLE IF NOT EXISTS budgets (
            user_id TEXT PRIMARY KEY,
            monthly_budget REAL DEFAULT 0,
            updated_at REAL DEFAULT (strftime('%s','now'))
        )""")

        # v2.3: 粉丝增长时序表 — 每天每平台存一条快照，用于计算周/月增长趋势
        conn.execute("""CREATE TABLE IF NOT EXISTS follower_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            followers INTEGER DEFAULT 0,
            following INTEGER DEFAULT 0,
            total_likes INTEGER DEFAULT 0,
            total_views INTEGER DEFAULT 0,
            snapshot_date TEXT NOT NULL DEFAULT (date('now')),
            snapshot_at REAL DEFAULT (strftime('%s','now')),
            UNIQUE(platform, snapshot_date)
        )""")
        # v2.4: 账单追踪表 — 话费/水电费余额检测提醒
        conn.execute("""CREATE TABLE IF NOT EXISTS bill_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            account_type TEXT NOT NULL,
            account_name TEXT DEFAULT '',
            provider TEXT DEFAULT '',
            balance REAL DEFAULT 0,
            low_threshold REAL DEFAULT 30,
            last_updated REAL DEFAULT 0,
            last_alert_ts REAL DEFAULT 0,
            remind_day INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at REAL DEFAULT (strftime('%s','now'))
        )""")

        # v2.6: 内容日历表 — 持久化社媒内容排期，UNIQUE 防重复
        conn.execute("""CREATE TABLE IF NOT EXISTS content_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_date TEXT NOT NULL,
            topic TEXT NOT NULL,
            content_type TEXT DEFAULT '',
            platform TEXT DEFAULT 'all',
            scheduled_time TEXT DEFAULT '',
            status TEXT DEFAULT 'planned',
            draft_id INTEGER DEFAULT 0,
            created_at REAL DEFAULT (strftime('%s','now')),
            UNIQUE(plan_date, topic)
        )""")

        # v2.5: 降价监控表 — 用户设定目标价，系统每6小时检查并推送降价通知
        conn.execute("""CREATE TABLE IF NOT EXISTS price_watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            target_price REAL NOT NULL,
            current_price REAL DEFAULT 0,
            lowest_price REAL DEFAULT 0,
            platform TEXT DEFAULT 'all',
            status TEXT DEFAULT 'active',
            created_at REAL DEFAULT (strftime('%s','now')),
            last_checked REAL DEFAULT 0,
            triggered_at REAL DEFAULT 0
        )""")
    logger.debug("[ExecutionDB] tables initialized")
