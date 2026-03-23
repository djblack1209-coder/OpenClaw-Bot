"""闲鱼对话上下文管理 — SQLite 持久化"""
import json
import os
import sqlite3
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from src.utils import now_et

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DB_PATH = os.path.join(DB_DIR, "xianyu_chat.db")


class XianyuContextManager:
    def __init__(self, max_history: int = 80, db_path: str = DB_PATH):
        self.max_history = max_history
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts TEXT DEFAULT (datetime('now'))
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_chat ON messages(chat_id)")
            c.execute("""CREATE TABLE IF NOT EXISTS bargain_counts (
                chat_id TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                updated TEXT DEFAULT (datetime('now'))
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS items (
                item_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated TEXT DEFAULT (datetime('now'))
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                user_id TEXT,
                item_id TEXT,
                status TEXT NOT NULL,
                ts TEXT DEFAULT (datetime('now')),
                notified INTEGER DEFAULT 0
            )""")
            # 咨询追踪表
            c.execute("""CREATE TABLE IF NOT EXISTS consultations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT DEFAULT '',
                item_id TEXT DEFAULT '',
                first_msg TEXT DEFAULT '',
                first_ts TEXT DEFAULT (datetime('now')),
                last_ts TEXT DEFAULT (datetime('now')),
                msg_count INTEGER DEFAULT 1,
                converted INTEGER DEFAULT 0,
                UNIQUE(chat_id, item_id)
            )""")

    # ---- messages ----
    def add_message(self, chat_id: str, user_id: str, item_id: str, role: str, content: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO messages(chat_id,user_id,item_id,role,content) VALUES(?,?,?,?,?)",
                (chat_id, user_id, item_id, role, content),
            )
            c.execute(
                "DELETE FROM messages WHERE chat_id=? AND id NOT IN "
                "(SELECT id FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?)",
                (chat_id, chat_id, self.max_history),
            )

    def get_context(self, chat_id: str) -> List[Dict[str, str]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id ASC LIMIT ?",
                (chat_id, self.max_history),
            ).fetchall()
        msgs = [{"role": r, "content": ct} for r, ct in rows]
        bc = self.get_bargain_count(chat_id)
        if bc > 0:
            msgs.append({"role": "system", "content": f"议价次数: {bc}"})
        return msgs

    # ---- bargain ----
    def incr_bargain(self, chat_id: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO bargain_counts(chat_id,count) VALUES(?,1) "
                "ON CONFLICT(chat_id) DO UPDATE SET count=count+1, updated=datetime('now')",
                (chat_id,),
            )

    def get_bargain_count(self, chat_id: str) -> int:
        with self._conn() as c:
            row = c.execute("SELECT count FROM bargain_counts WHERE chat_id=?", (chat_id,)).fetchone()
        return row[0] if row else 0

    # ---- items ----
    def save_item(self, item_id: str, data: dict):
        with self._conn() as c:
            c.execute(
                "INSERT INTO items(item_id,data) VALUES(?,?) "
                "ON CONFLICT(item_id) DO UPDATE SET data=?, updated=datetime('now')",
                (item_id, json.dumps(data, ensure_ascii=False), json.dumps(data, ensure_ascii=False)),
            )

    def get_item(self, item_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT data FROM items WHERE item_id=?", (item_id,)).fetchone()
        return json.loads(row[0]) if row else None

    # ---- orders ----
    def record_order(self, chat_id: str, user_id: str, item_id: str, status: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO orders(chat_id,user_id,item_id,status) VALUES(?,?,?,?)",
                (chat_id, user_id, item_id, status),
            )

    def get_unnotified_orders(self) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id,chat_id,user_id,item_id,status,ts FROM orders WHERE notified=0"
            ).fetchall()
        return [{"id": r[0], "chat_id": r[1], "user_id": r[2], "item_id": r[3], "status": r[4], "ts": r[5]} for r in rows]

    def mark_notified(self, order_id: int):
        with self._conn() as c:
            c.execute("UPDATE orders SET notified=1 WHERE id=?", (order_id,))

    # ---- consultations ----
    def track_consultation(self, chat_id: str, user_id: str, user_name: str, item_id: str, message: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO consultations(chat_id,user_id,user_name,item_id,first_msg) VALUES(?,?,?,?,?) "
                "ON CONFLICT(chat_id,item_id) DO UPDATE SET msg_count=msg_count+1, last_ts=datetime('now')",
                (chat_id, user_id, user_name, item_id, message[:200]),
            )

    def mark_converted(self, chat_id: str, item_id: str = ""):
        with self._conn() as c:
            if item_id:
                c.execute("UPDATE consultations SET converted=1 WHERE chat_id=? AND item_id=?", (chat_id, item_id))
            else:
                c.execute("UPDATE consultations SET converted=1 WHERE chat_id=?", (chat_id,))

    def daily_stats(self, date: str = "") -> Dict[str, Any]:
        """获取某天的统计数据，默认今天"""
        if not date:
            date = now_et().strftime("%Y-%m-%d")
        with self._conn() as c:
            # 咨询数
            consult_total = c.execute(
                "SELECT COUNT(DISTINCT chat_id) FROM consultations WHERE first_ts LIKE ?", (f"{date}%",)
            ).fetchone()[0]
            # 下单数
            order_total = c.execute(
                "SELECT COUNT(*) FROM orders WHERE ts LIKE ?", (f"{date}%",)
            ).fetchone()[0]
            # 付款数
            paid_total = c.execute(
                "SELECT COUNT(*) FROM orders WHERE ts LIKE ? AND status LIKE '%付款%'", (f"{date}%",)
            ).fetchone()[0]
            # 消息总数
            msg_total = c.execute(
                "SELECT COUNT(*) FROM messages WHERE ts LIKE ? AND role='user'", (f"{date}%",)
            ).fetchone()[0]
            # 转化数
            converted = c.execute(
                "SELECT COUNT(*) FROM consultations WHERE first_ts LIKE ? AND converted=1", (f"{date}%",)
            ).fetchone()[0]
        rate = f"{converted/consult_total*100:.1f}%" if consult_total > 0 else "0%"
        return {
            "date": date,
            "consultations": consult_total,
            "messages": msg_total,
            "orders": order_total,
            "paid": paid_total,
            "converted": converted,
            "conversion_rate": rate,
        }
