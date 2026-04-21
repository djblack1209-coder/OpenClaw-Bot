"""
ClawBot - SQLite 历史记录存储
替代 JSON 文件，支持并发安全、高效查询
"""
import json
import sqlite3
import threading
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from src.utils import now_et, scrub_secrets

logger = logging.getLogger(__name__)


class HistoryStore:
    """基于 SQLite 的对话历史存储"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            # 从 config 导入避免循环依赖 (globals.py 导入了 HistoryStore, 但 config.py 无此依赖)
            from src.bot.config import DATA_DIR
            self.db_path = Path(DATA_DIR) / "history.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """每个线程一个连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                timeout=10,
                check_same_thread=False
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                metadata TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_messages_bot_chat
                ON messages(bot_id, chat_id);

            CREATE INDEX IF NOT EXISTS idx_messages_created
                ON messages(created_at);
        """)
        conn.commit()

    def add_message(
        self,
        bot_id: str,
        chat_id: int,
        role: str,
        content: Any,
        metadata: Optional[Dict] = None
    ):
        """添加一条消息"""
        conn = self._get_conn()
        content_str = json.dumps(content, ensure_ascii=False) if not isinstance(content, str) else content
        meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else None

        conn.execute(
            "INSERT INTO messages (bot_id, chat_id, role, content, created_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (bot_id, chat_id, role, content_str, now_et().isoformat(), meta_str)
        )
        conn.commit()

    def get_messages(
        self,
        bot_id: str,
        chat_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取最近的消息"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, content FROM messages "
            "WHERE bot_id = ? AND chat_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (bot_id, chat_id, limit)
        ).fetchall()

        messages = []
        for row in reversed(rows):
            content = row["content"]
            try:
                content = json.loads(content)
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug("历史消息JSON解析失败(使用原始文本): %s", e)
            messages.append({"role": row["role"], "content": content})
        return messages

    def clear_messages(self, bot_id: str, chat_id: int):
        """清空某个对话的历史"""
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM messages WHERE bot_id = ? AND chat_id = ?",
            (bot_id, chat_id)
        )
        conn.commit()

    def get_message_count(self, bot_id: str, chat_id: int) -> int:
        """获取消息数量"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE bot_id = ? AND chat_id = ?",
            (bot_id, chat_id)
        ).fetchone()
        return row["cnt"] if row else 0

    def trim_messages(self, bot_id: str, chat_id: int, keep: int = 50):
        """保留最近 N 条消息，删除更早的"""
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM messages WHERE id NOT IN ("
            "  SELECT id FROM messages WHERE bot_id = ? AND chat_id = ? "
            "  ORDER BY id DESC LIMIT ?"
            ") AND bot_id = ? AND chat_id = ?",
            (bot_id, chat_id, keep, bot_id, chat_id)
        )
        conn.commit()

    def get_all_chat_ids(self, bot_id: str) -> List[int]:
        """获取某个 bot 的所有 chat_id"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT chat_id FROM messages WHERE bot_id = ?",
            (bot_id,)
        ).fetchall()
        return [row["chat_id"] for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计"""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as cnt FROM messages").fetchone()["cnt"]
        bots = conn.execute("SELECT DISTINCT bot_id FROM messages").fetchall()
        chats = conn.execute("SELECT COUNT(DISTINCT chat_id) as cnt FROM messages").fetchone()["cnt"]
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        return {
            "total_messages": total,
            "bots": [r["bot_id"] for r in bots],
            "total_chats": chats,
            "db_size_kb": round(db_size / 1024, 1),
        }

    def migrate_from_json(self, history_dir: str, bot_id: str):
        """从 JSON 文件迁移历史记录"""
        history_path = Path(history_dir)
        if not history_path.exists():
            return 0

        count = 0
        for f in history_path.glob(f"{bot_id}_*.json"):
            try:
                chat_id_str = f.stem.split('_')[-1]
                chat_id = int(chat_id_str)

                with open(f, 'r', encoding='utf-8') as file:
                    messages = json.load(file)

                for msg in messages:
                    self.add_message(bot_id, chat_id, msg["role"], msg["content"])
                    count += 1

            except Exception as e:
                logger.warning(f"迁移 {f.name} 失败: {scrub_secrets(str(e))}")

        logger.info(f"从 JSON 迁移 {count} 条消息 (bot: {bot_id})")
        return count

    def close(self):
        """关闭所有数据库连接"""
        try:
            if hasattr(self._local, 'conn') and self._local.conn:
                self._local.conn.close()
                self._local.conn = None
        except Exception as e:
            logger.debug(f"关闭连接时出错: {e}")
