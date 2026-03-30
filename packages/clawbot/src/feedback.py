"""
用户反馈系统 — 搬运自 karfly/chatgpt_telegram_bot 的 InlineKeyboard 模式
+ n3d1117/chatgpt-telegram-bot 的 callback_data 编码

功能：
- 每条 AI 回复后附加 👍/👎/🔄 按钮
- 反馈联动 AdaptiveRouter 质量评分（闭环）
- 支持 /retry 重新生成
- SQLite 持久化反馈记录
"""
import logging
import time
import threading
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# ── 反馈按钮构建（搬运自 karfly 的 callback_data 编码模式）──

def build_feedback_keyboard(bot_id: str, model_used: str, chat_id: int) -> InlineKeyboardMarkup:
    """构建反馈按钮 — 附加到每条 AI 回复后
    
    callback_data 格式: fb|{action}|{bot_id}|{model}|{chat_id}
    用 | 分隔（karfly 模式），总长度 < 64 字节（Telegram 限制）
    """
    model_short = (model_used or "unknown").split("/")[-1][:20]
    prefix = f"fb|{{}}|{bot_id[:10]}|{model_short}|{chat_id}"
    
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("👍", callback_data=prefix.format("up")),
        InlineKeyboardButton("👎", callback_data=prefix.format("down")),
        InlineKeyboardButton("🔄", callback_data=prefix.format("retry")),
    ]])


def parse_feedback_data(data: str) -> Optional[dict]:
    """解析 callback_data"""
    try:
        parts = data.split("|")
        if len(parts) >= 5 and parts[0] == "fb":
            return {
                "action": parts[1],
                "bot_id": parts[2],
                "model": parts[3],
                "chat_id": int(parts[4]),
            }
    except (ValueError, IndexError) as e:  # noqa: F841
        pass
    return None


# ── 反馈存储 ──

class FeedbackStore:
    """SQLite 反馈存储 — 轻量，不引入额外依赖"""
    
    def __init__(self, db_path: str = ""):
        import sqlite3, atexit
        # 使用相对于项目根目录的规范路径，避免不同工作目录启动时路径错误
        if db_path:
            self.db_path = db_path
        else:
            from pathlib import Path
            self.db_path = str(Path(__file__).parent.parent / "data" / "feedback.db")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        atexit.register(self.close)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                bot_id TEXT,
                model TEXT,
                rating INTEGER,
                timestamp REAL
            )
        """)
        self._conn.commit()
    
    def record(self, user_id: int, chat_id: int, bot_id: str, model: str, rating: int):
        """记录反馈 — rating: 1=👍, -1=👎"""
        with self._lock:
            self._conn.execute(
                "INSERT INTO feedback (user_id, chat_id, bot_id, model, rating, timestamp) VALUES (?,?,?,?,?,?)",
                (user_id, chat_id, bot_id, model, rating, time.time()),
            )
            self._conn.commit()
    
    def get_model_score(self, model: str, window_hours: int = 24) -> dict:
        """获取模型在时间窗口内的评分统计"""
        cutoff = time.time() - window_hours * 3600
        with self._lock:
            rows = self._conn.execute(
                "SELECT rating, COUNT(*) FROM feedback WHERE model=? AND timestamp>? GROUP BY rating",
                (model, cutoff),
            ).fetchall()
        up = sum(c for r, c in rows if r > 0)
        down = sum(c for r, c in rows if r < 0)
        total = up + down
        return {
            "up": up, "down": down, "total": total,
            "score": round(up / max(total, 1), 3),
        }
    
    def get_stats(self) -> dict:
        """全局统计"""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN rating>0 THEN 1 ELSE 0 END) FROM feedback"
            ).fetchone()
        total = row[0] or 0
        positive = row[1] or 0
        return {"total": total, "positive": positive, "satisfaction": round(positive / max(total, 1), 3)}

    def cleanup(self, days: int = 90) -> int:
        """Delete feedback records older than N days. Returns deleted count."""
        cutoff = time.time() - days * 86400
        with self._lock:
            cursor = self._conn.execute("DELETE FROM feedback WHERE timestamp < ?", (cutoff,))
            self._conn.commit()
            deleted = cursor.rowcount
        if deleted:
            import logging as _logging
            _logging.getLogger(__name__).info(
                "[FeedbackStore] cleanup: deleted %d records older than %d days", deleted, days
            )
        return deleted

    def close(self):
        """关闭 SQLite 连接"""
        if self._conn:
            try:
                self._conn.close()
            except Exception as e:
                logger.debug("静默异常: %s", e)
            self._conn = None


# 全局实例
_feedback_store: Optional[FeedbackStore] = None


def get_feedback_store() -> FeedbackStore:
    global _feedback_store
    if _feedback_store is None:
        _feedback_store = FeedbackStore()
    return _feedback_store
