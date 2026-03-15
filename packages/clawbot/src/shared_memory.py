"""
ClawBot - 共享记忆层
所有 bot 共享的持久化记忆系统，基于 SQLite。
支持：
- 跨 bot 读写共享知识
- 按来源（bot_id）追踪记忆归属
- 按分类组织记忆
- 自动过期清理
- /collab 结论自动存储
- 注入 system_prompt 的上下文摘要
"""
import sqlite3
import threading
import logging
import time
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SharedMemory:
    """
    跨 Agent 共享记忆。

    与 MemoryTool（JSON 文件、单 bot）不同，SharedMemory：
    - 使用 SQLite，并发安全
    - 所有 bot 共享同一个存储
    - 记录来源 bot_id，可追溯
    - 支持 TTL 过期
    - 提供 system_prompt 注入摘要
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            import os
            env_dir = os.getenv("DATA_DIR")
            if env_dir:
                self.db_path = Path(env_dir) / "shared_memory.db"
            else:
                self.db_path = (
                    Path(__file__).parent.parent / "data" / "shared_memory.db"
                )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._last_cleanup_time = 0.0  # 上次清理时间戳
        self._cleanup_interval = 60    # 清理间隔（秒）
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path), timeout=10, check_same_thread=False
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS shared_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                source_bot TEXT NOT NULL DEFAULT 'system',
                chat_id INTEGER,
                importance INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT,
                access_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_shared_mem_key
                ON shared_memories(key);

            CREATE INDEX IF NOT EXISTS idx_shared_mem_category
                ON shared_memories(category);

            CREATE INDEX IF NOT EXISTS idx_shared_mem_importance
                ON shared_memories(importance DESC);

            CREATE INDEX IF NOT EXISTS idx_shared_mem_source
                ON shared_memories(source_bot);

            CREATE TABLE IF NOT EXISTS workflow_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                chat_id INTEGER,
                original_text TEXT NOT NULL,
                selected_option TEXT NOT NULL DEFAULT '',
                stage1_score INTEGER NOT NULL,
                stage2_score INTEGER NOT NULL,
                stage3_score INTEGER NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                improvement_focus TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_workflow_feedback_created_at
                ON workflow_feedback(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_workflow_feedback_chat_id
                ON workflow_feedback(chat_id);
        """)
        conn.commit()

    # ============ 写入 ============

    def remember(
        self,
        key: str,
        value: str,
        category: str = "general",
        source_bot: str = "system",
        chat_id: Optional[int] = None,
        importance: int = 1,
        ttl_hours: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        存入共享记忆。如果 key+category 已存在则更新。

        Args:
            key: 记忆键名
            value: 记忆内容
            category: 分类 (general/collab/user_pref/knowledge/task)
            source_bot: 写入来源 bot_id
            chat_id: 关联的 chat_id（可选）
            importance: 重要性 1-5（5 最重要）
            ttl_hours: 过期时间（小时），None 表示永不过期
        """
        conn = self._get_conn()
        now = datetime.now().isoformat()
        expires_at = None
        if ttl_hours:
            expires_at = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()

        # Upsert: 如果 key+category 已存在则更新
        existing = conn.execute(
            "SELECT id FROM shared_memories WHERE key = ? AND category = ?",
            (key, category),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE shared_memories SET value = ?, source_bot = ?, chat_id = ?, "
                "importance = ?, updated_at = ?, expires_at = ? WHERE id = ?",
                (value, source_bot, chat_id, importance, now, expires_at, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO shared_memories "
                "(key, value, category, source_bot, chat_id, importance, created_at, updated_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (key, value, category, source_bot, chat_id, importance, now, now, expires_at),
            )
        conn.commit()

        logger.debug(f"[SharedMemory] {source_bot} 写入: [{category}] {key}")
        return {"success": True, "key": key, "category": category, "source": source_bot}

    # ============ 读取 ============

    def recall(
        self, key: str, category: Optional[str] = None
    ) -> Dict[str, Any]:
        """按 key 精确查找记忆"""
        conn = self._get_conn()
        self._cleanup_expired(conn)

        if category:
            row = conn.execute(
                "SELECT * FROM shared_memories WHERE key = ? AND category = ?",
                (key, category),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM shared_memories WHERE key = ? ORDER BY importance DESC LIMIT 1",
                (key,),
            ).fetchone()

        if row:
            # 更新访问计数
            conn.execute(
                "UPDATE shared_memories SET access_count = access_count + 1 WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
            return {
                "success": True,
                "key": row["key"],
                "value": row["value"],
                "category": row["category"],
                "source_bot": row["source_bot"],
                "importance": row["importance"],
                "updated_at": row["updated_at"],
            }

        return {"success": False, "error": f"未找到: {key}"}

    def search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """模糊搜索记忆（key 和 value 都搜）"""
        conn = self._get_conn()
        self._cleanup_expired(conn)

        # Escape LIKE wildcards to prevent injection
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = conn.execute(
            "SELECT * FROM shared_memories "
            "WHERE key LIKE ? ESCAPE '\\' OR value LIKE ? ESCAPE '\\' "
            "ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (f"%{escaped}%", f"%{escaped}%", limit),
        ).fetchall()

        results = [
            {
                "key": r["key"],
                "value": r["value"][:200],
                "category": r["category"],
                "source_bot": r["source_bot"],
                "importance": r["importance"],
            }
            for r in rows
        ]
        return {"success": True, "query": query, "results": results, "count": len(results)}

    def get_by_category(
        self, category: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """按分类获取记忆"""
        conn = self._get_conn()
        self._cleanup_expired(conn)

        rows = conn.execute(
            "SELECT * FROM shared_memories WHERE category = ? "
            "ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (category, limit),
        ).fetchall()

        return [
            {
                "key": r["key"],
                "value": r["value"],
                "source_bot": r["source_bot"],
                "importance": r["importance"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近更新的记忆"""
        conn = self._get_conn()
        self._cleanup_expired(conn)

        rows = conn.execute(
            "SELECT * FROM shared_memories ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        return [
            {
                "key": r["key"],
                "value": r["value"][:100],
                "category": r["category"],
                "source_bot": r["source_bot"],
            }
            for r in rows
        ]

    # ============ 删除 ============

    def forget(self, key: str, category: Optional[str] = None) -> Dict[str, Any]:
        """删除记忆"""
        conn = self._get_conn()
        if category:
            result = conn.execute(
                "DELETE FROM shared_memories WHERE key = ? AND category = ?",
                (key, category),
            )
        else:
            result = conn.execute(
                "DELETE FROM shared_memories WHERE key = ?", (key,)
            )
        conn.commit()

        if result.rowcount > 0:
            return {"success": True, "deleted": result.rowcount}
        return {"success": False, "error": f"未找到: {key}"}

    # ============ /collab 结论存储 ============

    def save_collab_result(
        self,
        task_text: str,
        plan_result: str,
        exec_result: str,
        summary_result: str,
        planner_id: str,
        chat_id: Optional[int] = None,
    ):
        """
        保存 /collab 协作任务的结论到共享记忆。
        自动提取关键信息，供后续任何 bot 引用。
        """
        # 保存完整结论
        short_task = task_text[:80]
        timestamp = datetime.now().strftime("%m/%d %H:%M")

        self.remember(
            key=f"collab_{timestamp}_{short_task}",
            value=summary_result[:2000],
            category="collab",
            source_bot="collab_system",
            chat_id=chat_id,
            importance=3,
            ttl_hours=72,  # 协作结论保留 3 天
        )

        # 保存任务摘要（更短，用于 system_prompt 注入）
        self.remember(
            key=f"collab_brief_{timestamp}",
            value=f"任务: {short_task} | 规划: {planner_id} | 结论: {summary_result[:300]}",
            category="collab_brief",
            source_bot="collab_system",
            chat_id=chat_id,
            importance=2,
            ttl_hours=48,
        )

        logger.info(f"[SharedMemory] 保存协作结论: {short_task}")

    def save_service_workflow_feedback(
        self,
        workflow_id: str,
        original_text: str,
        selected_option: str,
        stage1_score: int,
        stage2_score: int,
        stage3_score: int,
        summary: str = "",
        improvement_focus: str = "",
        chat_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        conn = self._get_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO workflow_feedback (workflow_id, chat_id, original_text, selected_option, stage1_score, stage2_score, stage3_score, summary, improvement_focus, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                workflow_id,
                chat_id,
                original_text,
                selected_option,
                max(1, min(3, int(stage1_score))),
                max(1, min(3, int(stage2_score))),
                max(1, min(3, int(stage3_score))),
                summary,
                improvement_focus,
                now,
            ),
        )
        conn.commit()

        payload = {
            "workflow_id": workflow_id,
            "selected_option": selected_option,
            "scores": [int(stage1_score), int(stage2_score), int(stage3_score)],
            "improvement_focus": improvement_focus,
        }
        self.remember(
            key=f"workflow_feedback_{workflow_id}",
            value=json.dumps(payload, ensure_ascii=False),
            category="workflow_feedback",
            source_bot="workflow_system",
            chat_id=chat_id,
            importance=2,
            ttl_hours=24 * 30,
        )
        return {"success": True, "workflow_id": workflow_id}

    def get_service_workflow_feedback_stats(self, limit: int = 20, chat_id: Optional[int] = None) -> Dict[str, Any]:
        conn = self._get_conn()
        params: List[Any] = []
        query = "SELECT workflow_id, selected_option, stage1_score, stage2_score, stage3_score, improvement_focus, created_at FROM workflow_feedback"
        if chat_id is not None:
            query += " WHERE chat_id = ?"
            params.append(chat_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        rows = conn.execute(query, params).fetchall()
        if not rows:
            return {
                "count": 0,
                "avg_stage1": 0.0,
                "avg_stage2": 0.0,
                "avg_stage3": 0.0,
                "weakest_stage": "",
                "recent_focus": [],
            }

        count = len(rows)
        avg_stage1 = round(sum(int(r["stage1_score"]) for r in rows) / count, 2)
        avg_stage2 = round(sum(int(r["stage2_score"]) for r in rows) / count, 2)
        avg_stage3 = round(sum(int(r["stage3_score"]) for r in rows) / count, 2)
        stage_map = {
            "客服接待": avg_stage1,
            "方案评审": avg_stage2,
            "任务交付": avg_stage3,
        }
        weakest_stage = min(stage_map.items(), key=lambda item: item[1])[0]
        focus = [str(r["improvement_focus"] or "").strip() for r in rows if str(r["improvement_focus"] or "").strip()]
        return {
            "count": count,
            "avg_stage1": avg_stage1,
            "avg_stage2": avg_stage2,
            "avg_stage3": avg_stage3,
            "weakest_stage": weakest_stage,
            "recent_focus": focus[:3],
        }

    def get_service_workflow_feedback_summary(self, limit: int = 20, chat_id: Optional[int] = None) -> str:
        stats = self.get_service_workflow_feedback_stats(limit=limit, chat_id=chat_id)
        if not stats.get("count"):
            return ""

        focus = stats.get("recent_focus", []) or []
        focus_text = "；".join(focus[:2]) if focus else "优先优化评分最低的环节。"
        return (
            f"最近 {stats['count']} 次链式协作评分：客服接待 {stats['avg_stage1']}/3，"
            f"方案评审 {stats['avg_stage2']}/3，任务交付 {stats['avg_stage3']}/3。"
            f"当前最弱环节：{stats['weakest_stage']}。"
            f"近期迭代重点：{focus_text}"
        )

    # ============ System Prompt 注入 ============

    def get_context_for_prompt(self, max_tokens: int = 500) -> str:
        """
        生成注入到 system_prompt 的共享记忆摘要。
        按重要性排序，控制总长度。
        """
        conn = self._get_conn()
        self._cleanup_expired(conn)

        # 获取高重要性记忆
        rows = conn.execute(
            "SELECT key, value, category, source_bot FROM shared_memories "
            "ORDER BY importance DESC, access_count DESC, updated_at DESC "
            "LIMIT 20",
        ).fetchall()

        if not rows:
            return ""

        parts = []
        current_len = 0
        seen_categories = {}

        for r in rows:
            cat = r["category"]
            entry = f"- [{cat}] {r['key']}: {r['value'][:100]}"

            if current_len + len(entry) > max_tokens * 2:  # 粗略估算
                break

            if cat not in seen_categories:
                seen_categories[cat] = 0
            seen_categories[cat] += 1

            # 每个分类最多 3 条
            if seen_categories[cat] <= 3:
                parts.append(entry)
                current_len += len(entry)

        if parts:
            return "\n\n【共享记忆（团队共享知识）】\n" + "\n".join(parts)
        return ""

    # ============ 统计 ============

    def get_stats(self) -> Dict[str, Any]:
        """获取共享记忆统计"""
        conn = self._get_conn()
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM shared_memories"
        ).fetchone()["cnt"]

        categories = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM shared_memories GROUP BY category"
        ).fetchall()

        sources = conn.execute(
            "SELECT source_bot, COUNT(*) as cnt FROM shared_memories GROUP BY source_bot"
        ).fetchall()

        return {
            "total": total,
            "categories": {r["category"]: r["cnt"] for r in categories},
            "sources": {r["source_bot"]: r["cnt"] for r in sources},
            "db_size_kb": round(
                self.db_path.stat().st_size / 1024, 1
            ) if self.db_path.exists() else 0,
        }

    # ============ 内部方法 ============

    def _cleanup_expired(self, conn: sqlite3.Connection):
        """清理过期记忆（节流：每分钟最多执行一次）"""
        now_ts = time.time()
        if now_ts - self._last_cleanup_time < self._cleanup_interval:
            return
        self._last_cleanup_time = now_ts
        now = datetime.now().isoformat()
        conn.execute(
            "DELETE FROM shared_memories WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        conn.commit()

    def close(self):
        """Close all thread-local connections."""
        # Close the current thread's connection
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
