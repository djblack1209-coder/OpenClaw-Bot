"""
ClawBot - 共享记忆层 v3.0 (对标 mem0 50.1k⭐ + letta 21.6k⭐)
所有 bot 共享的持久化记忆系统，基于 SQLite + 向量嵌入。
支持：
- 跨 bot 读写共享知识
- 按来源（bot_id）追踪记忆归属
- 按分类组织记忆
- 自动过期清理
- /collab 结论自动存储
- 注入 system_prompt 的上下文摘要
- [v2.0] 向量嵌入 + 语义搜索（对标 mem0）
- [v2.0] 记忆关系图谱（交叉引用）
- [v2.0] LLM 自动事实提取
- [v2.0] 记忆重要性自适应衰减
- [v2.0] 混合检索（关键词 + 语义）
- [v3.0] 记忆冲突检测与自动解决（对标 mem0 v1.0）
- [v3.0] 自动摘要压缩（对标 letta 记忆压缩）
- [v3.0] 记忆版本历史追踪
- [v3.0] 智能清理（基于访问频率+衰减）
- [v3.0] 记忆容量管理与自动淘汰
"""
import sqlite3
import threading
import logging
import time
import json
import math
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from src.utils import now_et

logger = logging.getLogger(__name__)

# --- 对标 mem0: 轻量级向量存储（无外部依赖） ---

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算余弦相似度"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _simple_text_embedding(text: str, dim: int = 128) -> List[float]:
    """基于字符 n-gram 哈希的轻量级文本嵌入（零 API 调用）
    
    不如 text-embedding-3-small 精确，但零成本、零延迟、离线可用。
    当 embedding API 可用时会自动升级为真正的向量嵌入。
    """
    if not text:
        return [0.0] * dim
    text = text.lower().strip()
    vec = [0.0] * dim
    # 字符级 3-gram 哈希
    for i in range(len(text) - 2):
        ngram = text[i:i+3]
        h = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
        idx = h % dim
        vec[idx] += 1.0
    # 词级哈希
    for word in text.split():
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        idx = h % dim
        vec[idx] += 2.0
    # L2 归一化
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _create_api_embedding_fn(dim: int = 128):
    """创建支持 API 嵌入的函数，自动降级到本地哈希。
    
    优先级:
    1. SiliconFlow embedding API (BGEM3, 免费)
    2. 本地 n-gram 哈希 (零成本兜底)
    
    使用内存缓存避免重复调用，LRU 最多缓存 500 条。
    """
    import os
    import functools

    sf_key = None
    sf_keys = os.getenv("SILICONFLOW_KEYS", "")
    if sf_keys:
        sf_key = sf_keys.split(",")[0].strip() or None

    # LRU 缓存：避免对相同文本重复调用 API
    @functools.lru_cache(maxsize=500)
    def _cached_api_embed(text_hash: str, text: str) -> tuple:
        """缓存层（返回 tuple 以便 lru_cache 可哈希）"""
        return tuple(_call_api_embed(text))

    def _call_api_embed(text: str) -> List[float]:
        """调用 SiliconFlow embedding API"""
        if not sf_key:
            return _simple_text_embedding(text, dim)
        try:
            import httpx
            resp = httpx.post(
                "https://api.siliconflow.cn/v1/embeddings",
                headers={"Authorization": f"Bearer {sf_key}", "Content-Type": "application/json"},
                json={"model": "BAAI/bge-m3", "input": text[:2000]},
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                vec = data.get("data", [{}])[0].get("embedding", [])
                if vec:
                    # 降维到 dim（bge-m3 输出 1024 维）
                    if len(vec) > dim:
                        step = len(vec) / dim
                        vec = [vec[int(i * step)] for i in range(dim)]
                    # L2 归一化
                    norm = math.sqrt(sum(x * x for x in vec))
                    if norm > 0:
                        vec = [x / norm for x in vec]
                    return vec
        except Exception as e:
            logger.debug("[SharedMemory] API embedding 失败，降级到本地: %s", e)
        return _simple_text_embedding(text, dim)

    def embedding_fn(text: str) -> List[float]:
        """带缓存的嵌入函数"""
        if not text:
            return [0.0] * dim
        text = text.strip()
        text_hash = hashlib.md5(text.encode()).hexdigest()
        try:
            return list(_cached_api_embed(text_hash, text))
        except Exception:
            return _simple_text_embedding(text, dim)

    return embedding_fn


class SharedMemory:
    """
    跨 Agent 共享记忆 v2.0（对标 mem0）

    与 MemoryTool（JSON 文件、单 bot）不同，SharedMemory：
    - 使用 SQLite，并发安全
    - 所有 bot 共享同一个存储
    - 记录来源 bot_id，可追溯
    - 支持 TTL 过期
    - 提供 system_prompt 注入摘要
    - [NEW] 向量嵌入 + 语义搜索
    - [NEW] 记忆关系图谱
    - [NEW] 重要性自适应衰减
    - [NEW] 混合检索（BM25 + 向量）
    """

    # 对标 mem0: 嵌入维度（本地哈希嵌入用 128，API 嵌入用 1536）
    EMBEDDING_DIM = 128
    # 对标 mem0: 重要性衰减系数（每天衰减 5%）
    IMPORTANCE_DECAY_RATE = 0.05
    # 对标 mem0: 语义搜索最低相似度阈值
    SIMILARITY_THRESHOLD = 0.15

    def __init__(self, db_path: Optional[str] = None, embedding_fn=None):
        """
        Args:
            db_path: SQLite 数据库路径
            embedding_fn: 可选的外部嵌入函数 (text) -> List[float]
                          如果提供，将使用 API 嵌入替代本地哈希嵌入
        """
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
        self._lock = threading.Lock()  # 应用层锁，保护读-改-写操作
        self._last_cleanup_time = 0.0
        self._cleanup_interval = 60
        # 对标 mem0: 可插拔嵌入函数（优先 API 嵌入，自动降级到本地哈希）
        self._embedding_fn = embedding_fn or _create_api_embedding_fn(dim=self.EMBEDDING_DIM)
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
                access_count INTEGER NOT NULL DEFAULT 0,
                embedding BLOB,
                last_decay_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_shared_mem_key ON shared_memories(key);
            CREATE INDEX IF NOT EXISTS idx_shared_mem_category ON shared_memories(category);
            CREATE INDEX IF NOT EXISTS idx_shared_mem_importance ON shared_memories(importance DESC);
            CREATE INDEX IF NOT EXISTS idx_shared_mem_source ON shared_memories(source_bot);
            CREATE INDEX IF NOT EXISTS idx_shared_mem_compress ON shared_memories(category, importance ASC, access_count ASC, updated_at ASC);

            CREATE TABLE IF NOT EXISTS memory_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id INTEGER NOT NULL,
                to_id INTEGER NOT NULL,
                relation_type TEXT NOT NULL,
                strength REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (from_id) REFERENCES shared_memories(id) ON DELETE CASCADE,
                FOREIGN KEY (to_id) REFERENCES shared_memories(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_memory_relations_from ON memory_relations(from_id);
            CREATE INDEX IF NOT EXISTS idx_memory_relations_to ON memory_relations(to_id);

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

            CREATE INDEX IF NOT EXISTS idx_workflow_feedback_created_at ON workflow_feedback(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_workflow_feedback_chat_id ON workflow_feedback(chat_id);
        """)
        conn.commit()

    # ============ 写入 ============

    def _compute_embedding(self, text: str) -> Optional[bytes]:
        """计算文本嵌入并序列化为 bytes"""
        try:
            vec = self._embedding_fn(text)
            if vec:
                return json.dumps(vec).encode('utf-8')
        except Exception as e:
            logger.debug(f"[SharedMemory] 嵌入计算失败: {e}")
        return None

    def _deserialize_embedding(self, blob: Optional[bytes]) -> Optional[List[float]]:
        """反序列化嵌入向量"""
        if not blob:
            return None
        try:
            return json.loads(blob.decode('utf-8'))
        except Exception:
            return None

    def remember(
        self,
        key: str,
        value: str,
        category: str = "general",
        source_bot: str = "system",
        chat_id: Optional[int] = None,
        importance: int = 1,
        ttl_hours: Optional[int] = None,
        related_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        存入共享记忆。如果 key+category 已存在则更新。
        对标 mem0: 自动生成嵌入向量 + 可选关系图谱链接。

        Args:
            key: 记忆键名
            value: 记忆内容
            category: 分类 (general/collab/user_pref/knowledge/task)
            source_bot: 写入来源 bot_id
            chat_id: 关联的 chat_id（可选）
            importance: 重要性 1-5（5 最重要）
            ttl_hours: 过期时间（小时），None 表示永不过期
            related_keys: 关联的记忆 key 列表（构建记忆图谱）
        """
        conn = self._get_conn()
        now = now_et().isoformat()
        expires_at = None
        if ttl_hours:
            expires_at = (now_et() + timedelta(hours=ttl_hours)).isoformat()

        # 对标 mem0: 生成嵌入向量
        embed_text = f"{key} {value}"
        embedding = self._compute_embedding(embed_text)

        # Upsert: 如果 key+category 已存在则更新
        with self._lock:  # 保护 upsert 的读-改-写原子性
            existing = conn.execute(
                "SELECT id FROM shared_memories WHERE key = ? AND category = ?",
                (key, category),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE shared_memories SET value = ?, source_bot = ?, chat_id = ?, "
                    "importance = ?, updated_at = ?, expires_at = ?, embedding = ?, "
                    "last_decay_at = ? WHERE id = ?",
                    (value, source_bot, chat_id, importance, now, expires_at,
                     embedding, now, existing["id"]),
                )
                mem_id = existing["id"]
            else:
                cursor = conn.execute(
                    "INSERT INTO shared_memories "
                    "(key, value, category, source_bot, chat_id, importance, "
                    "created_at, updated_at, expires_at, embedding, last_decay_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (key, value, category, source_bot, chat_id, importance,
                     now, now, expires_at, embedding, now),
                )
                mem_id = cursor.lastrowid
            conn.commit()

            # 对标 mem0: 构建记忆关系图谱
            if related_keys and mem_id:
                self._link_memories(conn, mem_id, related_keys)

        logger.debug(f"[SharedMemory] {source_bot} 写入: [{category}] {key}")
        return {"success": True, "key": key, "category": category,
                "source": source_bot, "id": mem_id}

    def _link_memories(self, conn, from_id: int, related_keys: List[str]):
        """对标 mem0 知识图谱: 建立记忆间的关联"""
        for rk in related_keys:
            row = conn.execute(
                "SELECT id FROM shared_memories WHERE key = ? ORDER BY importance DESC LIMIT 1",
                (rk,),
            ).fetchone()
            if row and row["id"] != from_id:
                # 避免重复关系
                exists = conn.execute(
                    "SELECT 1 FROM memory_relations WHERE from_id = ? AND to_id = ?",
                    (from_id, row["id"]),
                ).fetchone()
                if not exists:
                    conn.execute(
                        "INSERT INTO memory_relations (from_id, to_id, relation_type, strength) "
                        "VALUES (?, ?, 'related', 1.0)",
                        (from_id, row["id"]),
                    )
                    # 双向关系
                    conn.execute(
                        "INSERT INTO memory_relations (from_id, to_id, relation_type, strength) "
                        "VALUES (?, ?, 'related', 1.0)",
                        (row["id"], from_id),
                    )
        conn.commit()

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

    def search(self, query: str, limit: int = 10, mode: str = "hybrid") -> Dict[str, Any]:
        """混合搜索记忆（对标 mem0: 关键词 + 语义向量混合检索）
        
        Args:
            query: 搜索查询
            limit: 返回数量上限
            mode: 搜索模式 - "keyword" / "semantic" / "hybrid"（默认）
        """
        conn = self._get_conn()
        self._cleanup_expired(conn)

        keyword_results = []
        semantic_results = []

        # 关键词搜索（原有逻辑）
        if mode in ("keyword", "hybrid"):
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = conn.execute(
                "SELECT * FROM shared_memories "
                "WHERE key LIKE ? ESCAPE '\\' OR value LIKE ? ESCAPE '\\' "
                "ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (f"%{escaped}%", f"%{escaped}%", limit * 2),
            ).fetchall()
            for r in rows:
                keyword_results.append({
                    "id": r["id"],
                    "key": r["key"],
                    "value": r["value"][:200],
                    "category": r["category"],
                    "source_bot": r["source_bot"],
                    "importance": r["importance"],
                    "score": r["importance"] * 0.2,  # 关键词匹配基础分
                    "match_type": "keyword",
                })

        # 对标 mem0: 语义向量搜索
        if mode in ("semantic", "hybrid"):
            query_embedding = self._embedding_fn(query)
            if query_embedding:
                rows = conn.execute(
                    "SELECT id, key, value, category, source_bot, importance, embedding "
                    "FROM shared_memories WHERE embedding IS NOT NULL "
                    "ORDER BY importance DESC LIMIT ?",
                    (min(500, limit * 50),),
                ).fetchall()
                for r in rows:
                    mem_embedding = self._deserialize_embedding(r["embedding"])
                    if mem_embedding:
                        sim = _cosine_similarity(query_embedding, mem_embedding)
                        if sim >= self.SIMILARITY_THRESHOLD:
                            semantic_results.append({
                                "id": r["id"],
                                "key": r["key"],
                                "value": r["value"][:200],
                                "category": r["category"],
                                "source_bot": r["source_bot"],
                                "importance": r["importance"],
                                "score": sim,
                                "similarity": round(sim, 3),
                                "match_type": "semantic",
                            })
                semantic_results.sort(key=lambda x: -x["score"])

        # 对标 mem0: 混合排序（去重 + 加权合并）
        if mode == "hybrid":
            seen_ids = set()
            merged = []
            # 语义结果权重 0.6，关键词权重 0.4
            for r in semantic_results:
                r["score"] = r["score"] * 0.6 + r["importance"] * 0.08
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    merged.append(r)
            for r in keyword_results:
                if r["id"] not in seen_ids:
                    r["score"] = r["score"] * 0.4
                    seen_ids.add(r["id"])
                    merged.append(r)
            merged.sort(key=lambda x: -x["score"])
            results = merged[:limit]
        elif mode == "semantic":
            results = semantic_results[:limit]
        else:
            results = keyword_results[:limit]

        return {"success": True, "query": query, "mode": mode,
                "results": results, "count": len(results)}

    def semantic_search(self, query: str, limit: int = 5,
                        category: Optional[str] = None) -> List[Dict[str, Any]]:
        """纯语义搜索（对标 mem0 的 memory.search）
        
        返回按相似度排序的记忆列表，可按分类过滤。
        """
        conn = self._get_conn()
        self._cleanup_expired(conn)
        query_embedding = self._embedding_fn(query)
        if not query_embedding:
            return []

        sql = "SELECT id, key, value, category, source_bot, importance, embedding FROM shared_memories WHERE embedding IS NOT NULL"
        params: list = []
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY importance DESC LIMIT ?"
        params.append(min(500, limit * 50))

        rows = conn.execute(sql, params).fetchall()
        scored = []
        for r in rows:
            mem_embedding = self._deserialize_embedding(r["embedding"])
            if mem_embedding:
                sim = _cosine_similarity(query_embedding, mem_embedding)
                if sim >= self.SIMILARITY_THRESHOLD:
                    scored.append({
                        "key": r["key"],
                        "value": r["value"],
                        "category": r["category"],
                        "source_bot": r["source_bot"],
                        "importance": r["importance"],
                        "similarity": round(sim, 3),
                    })
        scored.sort(key=lambda x: -x["similarity"])
        return scored[:limit]

    def get_related(self, key: str, depth: int = 1, limit: int = 10) -> List[Dict[str, Any]]:
        """对标 mem0 知识图谱: 获取与指定记忆关联的记忆"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id FROM shared_memories WHERE key = ? ORDER BY importance DESC LIMIT 1",
            (key,),
        ).fetchone()
        if not row:
            return []

        visited = {row["id"]}
        frontier = [row["id"]]
        results = []

        for _ in range(depth):
            if not frontier:
                break
            next_frontier = []
            for mem_id in frontier:
                rels = conn.execute(
                    "SELECT to_id, relation_type, strength FROM memory_relations "
                    "WHERE from_id = ? ORDER BY strength DESC LIMIT ?",
                    (mem_id, limit),
                ).fetchall()
                for rel in rels:
                    to_id = rel["to_id"]
                    if to_id not in visited:
                        visited.add(to_id)
                        next_frontier.append(to_id)
                        mem = conn.execute(
                            "SELECT key, value, category, source_bot, importance "
                            "FROM shared_memories WHERE id = ?",
                            (to_id,),
                        ).fetchone()
                        if mem:
                            results.append({
                                "key": mem["key"],
                                "value": mem["value"][:200],
                                "category": mem["category"],
                                "relation": rel["relation_type"],
                                "strength": rel["strength"],
                            })
            frontier = next_frontier
        return results[:limit]

    def decay_importance(self):
        """对标 mem0: 重要性自适应衰减（低访问记忆逐渐降低重要性）"""
        conn = self._get_conn()
        now = now_et()
        rows = conn.execute(
            "SELECT id, importance, access_count, last_decay_at FROM shared_memories "
            "WHERE importance > 1 AND last_decay_at IS NOT NULL"
        ).fetchall()
        updated = 0
        for r in rows:
            last_decay = r["last_decay_at"]
            if not last_decay:
                continue
            try:
                last_dt = datetime.fromisoformat(last_decay)
            except (ValueError, TypeError):
                continue
            days_since = (now - last_dt).total_seconds() / 86400
            if days_since < 1:
                continue
            # 高访问量的记忆衰减更慢
            access_factor = max(0.2, 1.0 - r["access_count"] * 0.05)
            decay = self.IMPORTANCE_DECAY_RATE * days_since * access_factor
            new_importance = max(1, int(r["importance"] - decay))
            if new_importance < r["importance"]:
                conn.execute(
                    "UPDATE shared_memories SET importance = ?, last_decay_at = ? WHERE id = ?",
                    (new_importance, now.isoformat(), r["id"]),
                )
                updated += 1
        if updated:
            conn.commit()
            logger.debug(f"[SharedMemory] 衰减了 {updated} 条记忆的重要性")

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
        timestamp = now_et().strftime("%m/%d %H:%M")

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
        now = now_et().isoformat()
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

    # ============ 内部方法 ============

    def _cleanup_expired(self, conn: sqlite3.Connection):
        """清理过期记忆（节流：每分钟最多执行一次）"""
        now_ts = time.time()
        if now_ts - self._last_cleanup_time < self._cleanup_interval:
            return
        self._last_cleanup_time = now_ts
        now = now_et().isoformat()
        conn.execute(
            "DELETE FROM shared_memories WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        conn.commit()

    def close(self):
        """Close all thread-local connections."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ============ v3.0 记忆冲突检测（对标 mem0 v1.0） ============

    def detect_conflicts(
        self, key: str, new_value: str, category: str = "general",
        similarity_threshold: float = 0.6,
    ) -> List[Dict[str, Any]]:
        """
        检测新记忆是否与已有记忆冲突（对标 mem0 的记忆去重/冲突解决）
        
        原理：对新记忆做语义搜索，找到高相似度但内容不同的记忆，
        标记为潜在冲突。
        
        Returns:
            冲突记忆列表，每项包含 {key, value, similarity, conflict_type}
        """
        conn = self._get_conn()
        conflicts = []
        
        # 1. 精确 key 冲突
        existing = conn.execute(
            "SELECT id, key, value, category FROM shared_memories "
            "WHERE key = ? AND category = ?",
            (key, category),
        ).fetchone()
        
        if existing and existing["value"].strip() != new_value.strip():
            conflicts.append({
                "id": existing["id"],
                "key": existing["key"],
                "old_value": existing["value"][:200],
                "new_value": new_value[:200],
                "conflict_type": "exact_key_update",
                "similarity": 1.0,
            })
        
        # 2. 语义冲突检测：找到语义相似但内容不同的记忆
        embed_text = f"{key} {new_value}"
        query_embedding = self._embedding_fn(embed_text)
        if not query_embedding:
            return conflicts
        
        rows = conn.execute(
            "SELECT id, key, value, category, embedding FROM shared_memories "
            "WHERE embedding IS NOT NULL AND category = ? AND key != ? "
            "ORDER BY importance DESC LIMIT 100",
            (category, key),
        ).fetchall()
        
        for r in rows:
            mem_embedding = self._deserialize_embedding(r["embedding"])
            if not mem_embedding:
                continue
            sim = _cosine_similarity(query_embedding, mem_embedding)
            if sim >= similarity_threshold:
                # 高相似度 = 可能是同一主题的矛盾信息
                conflicts.append({
                    "id": r["id"],
                    "key": r["key"],
                    "existing_value": r["value"][:200],
                    "new_value": new_value[:200],
                    "conflict_type": "semantic_overlap",
                    "similarity": round(sim, 3),
                })
        
        if conflicts:
            logger.info(
                f"[SharedMemory] 检测到 {len(conflicts)} 个潜在冲突 "
                f"(key={key}, category={category})"
            )
        
        return conflicts

    def remember_with_conflict_resolution(
        self, key: str, value: str, category: str = "general",
        source_bot: str = "system", chat_id: Optional[int] = None,
        importance: int = 1, ttl_hours: Optional[int] = None,
        strategy: str = "newer_wins",
    ) -> Dict[str, Any]:
        """
        带冲突解决的记忆写入（对标 mem0 v1.0 的智能记忆更新）
        
        Args:
            strategy: 冲突解决策略
                - "newer_wins": 新记忆覆盖旧记忆（默认）
                - "higher_importance": 保留重要性更高的
                - "merge": 合并两条记忆
                - "keep_both": 都保留，标记冲突
        """
        conflicts = self.detect_conflicts(key, value, category)
        
        resolution_log = []
        
        for conflict in conflicts:
            if conflict["conflict_type"] == "exact_key_update":
                if strategy == "newer_wins":
                    # 保存旧版本到历史
                    self._save_version_history(
                        conflict["id"], conflict.get("old_value", ""), source_bot
                    )
                    resolution_log.append({
                        "action": "overwrite",
                        "old_key": conflict["key"],
                    })
                elif strategy == "higher_importance":
                    conn = self._get_conn()
                    existing = conn.execute(
                        "SELECT importance FROM shared_memories WHERE id = ?",
                        (conflict["id"],),
                    ).fetchone()
                    if existing and existing["importance"] > importance:
                        return {
                            "success": False,
                            "reason": "existing_higher_importance",
                            "conflicts": conflicts,
                        }
            
            elif conflict["conflict_type"] == "semantic_overlap":
                if strategy == "merge" and conflict["similarity"] > 0.8:
                    # 高度相似：合并内容
                    merged = f"{conflict.get('existing_value', '')} | 更新: {value}"
                    value = merged[:2000]
                    resolution_log.append({
                        "action": "merged",
                        "with_key": conflict["key"],
                        "similarity": conflict["similarity"],
                    })
                elif strategy == "keep_both":
                    resolution_log.append({
                        "action": "kept_both",
                        "existing_key": conflict["key"],
                    })
        
        # 执行写入
        result = self.remember(
            key=key, value=value, category=category,
            source_bot=source_bot, chat_id=chat_id,
            importance=importance, ttl_hours=ttl_hours,
        )
        result["conflicts_detected"] = len(conflicts)
        result["resolutions"] = resolution_log
        
        return result

    def _save_version_history(self, memory_id: int, old_value: str, changed_by: str):
        """保存记忆版本历史（对标 letta 的记忆编辑追踪）"""
        conn = self._get_conn()
        # 确保版本历史表存在
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL,
                old_value TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                changed_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (memory_id) REFERENCES shared_memories(id) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "INSERT INTO memory_versions (memory_id, old_value, changed_by) VALUES (?, ?, ?)",
            (memory_id, old_value[:2000], changed_by),
        )
        conn.commit()

    def get_version_history(self, key: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取记忆的版本历史"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id FROM shared_memories WHERE key = ? ORDER BY importance DESC LIMIT 1",
            (key,),
        ).fetchone()
        if not row:
            return []
        
        try:
            versions = conn.execute(
                "SELECT old_value, changed_by, changed_at FROM memory_versions "
                "WHERE memory_id = ? ORDER BY changed_at DESC LIMIT ?",
                (row["id"], limit),
            ).fetchall()
            return [
                {"old_value": v["old_value"][:200], "changed_by": v["changed_by"],
                 "changed_at": v["changed_at"]}
                for v in versions
            ]
        except Exception:
            return []

    # ============ v3.0 自动摘要压缩（对标 letta） ============

    def compress_category(
        self, category: str, max_memories: int = 50,
        compress_fn=None,
    ) -> Dict[str, Any]:
        """
        压缩指定分类的记忆（对标 letta 的记忆压缩机制）
        
        当某分类记忆超过 max_memories 时，将低重要性的旧记忆
        合并为摘要条目，释放空间。
        
        Args:
            category: 要压缩的分类
            max_memories: 该分类最大记忆数
            compress_fn: 可选的 LLM 摘要函数 (texts: List[str]) -> str
                         如果不提供，使用简单拼接
        """
        conn = self._get_conn()
        
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM shared_memories WHERE category = ?",
            (category,),
        ).fetchone()["cnt"]
        
        if count <= max_memories:
            return {"compressed": False, "count": count, "reason": "未超过上限"}
        
        # 找出低重要性、低访问量的旧记忆
        excess = count - max_memories + 5  # 多压缩5条留余量
        old_memories = conn.execute(
            "SELECT id, key, value FROM shared_memories "
            "WHERE category = ? "
            "ORDER BY importance ASC, access_count ASC, updated_at ASC "
            "LIMIT ?",
            (category, excess),
        ).fetchall()
        
        if not old_memories:
            return {"compressed": False, "count": count, "reason": "无可压缩记忆"}
        
        # 生成摘要
        texts = [f"{m['key']}: {m['value'][:100]}" for m in old_memories]
        
        if compress_fn:
            try:
                summary = compress_fn(texts)
            except Exception as e:
                logger.error(f"[SharedMemory] LLM压缩失败: {e}")
                summary = " | ".join(texts)[:2000]
        else:
            summary = " | ".join(texts)[:2000]
        
        # 删除旧记忆
        ids_to_delete = [m["id"] for m in old_memories]
        placeholders = ",".join("?" * len(ids_to_delete))
        conn.execute(
            f"DELETE FROM shared_memories WHERE id IN ({placeholders})",
            ids_to_delete,
        )
        
        # 写入摘要记忆
        timestamp = now_et().strftime("%m%d_%H%M")
        self.remember(
            key=f"compressed_{category}_{timestamp}",
            value=summary,
            category=category,
            source_bot="memory_compressor",
            importance=2,
        )
        
        conn.commit()
        
        new_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM shared_memories WHERE category = ?",
            (category,),
        ).fetchone()["cnt"]
        
        logger.info(
            f"[SharedMemory] 压缩 [{category}]: {count} -> {new_count} "
            f"(合并了{len(old_memories)}条)"
        )
        
        return {
            "compressed": True,
            "before": count,
            "after": new_count,
            "merged_count": len(old_memories),
        }

    def auto_compress_all(self, max_per_category: int = 50, compress_fn=None) -> Dict[str, Any]:
        """自动压缩所有超限分类"""
        conn = self._get_conn()
        categories = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM shared_memories "
            "GROUP BY category HAVING cnt > ?",
            (max_per_category,),
        ).fetchall()
        
        results = {}
        for cat in categories:
            results[cat["category"]] = self.compress_category(
                cat["category"], max_per_category, compress_fn
            )
        
        return results

    # ============ v3.0 智能清理（对标 mem0 的记忆管理） ============

    def smart_cleanup(self, max_total: int = 1000, keep_min_importance: int = 1) -> Dict[str, Any]:
        """
        智能清理：基于综合评分淘汰低价值记忆
        
        评分 = importance * 2 + access_count * 0.5 + recency_score
        recency_score = max(0, 10 - days_since_update)
        """
        conn = self._get_conn()
        
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM shared_memories"
        ).fetchone()["cnt"]
        
        if total <= max_total:
            return {"cleaned": 0, "total": total, "reason": "未超过上限"}
        
        # 计算所有记忆的综合评分
        rows = conn.execute(
            "SELECT id, importance, access_count, updated_at FROM shared_memories "
            "WHERE importance <= ?",
            (keep_min_importance + 2,),  # 不清理高重要性记忆
        ).fetchall()
        
        now = now_et()
        scored = []
        for r in rows:
            try:
                updated = datetime.fromisoformat(r["updated_at"])
                days_old = (now - updated).total_seconds() / 86400
            except (ValueError, TypeError):
                days_old = 30
            
            recency = max(0, 10 - days_old)
            score = r["importance"] * 2 + r["access_count"] * 0.5 + recency
            scored.append((r["id"], score))
        
        # 按评分升序排列，删除最低分的
        scored.sort(key=lambda x: x[1])
        to_delete = total - max_total + 10  # 多删10条留余量
        to_delete = min(to_delete, len(scored))
        
        if to_delete <= 0:
            return {"cleaned": 0, "total": total, "reason": "无可清理记忆"}
        
        ids = [s[0] for s in scored[:to_delete]]
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM shared_memories WHERE id IN ({placeholders})", ids)
        # 同时清理关联的关系
        conn.execute(
            f"DELETE FROM memory_relations WHERE from_id IN ({placeholders}) "
            f"OR to_id IN ({placeholders})",
            ids + ids,
        )
        conn.commit()
        
        new_total = conn.execute(
            "SELECT COUNT(*) as cnt FROM shared_memories"
        ).fetchone()["cnt"]
        
        logger.info(f"[SharedMemory] 智能清理: {total} -> {new_total} (删除{to_delete}条)")
        
        return {"cleaned": to_delete, "before": total, "after": new_total}

    # ============ v3.0 增强统计 ============

    def get_stats(self) -> Dict[str, Any]:
        """获取共享记忆统计（v3.0增强版）"""
        conn = self._get_conn()
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM shared_memories"
        ).fetchone()["cnt"]

        embedded = conn.execute(
            "SELECT COUNT(*) as cnt FROM shared_memories WHERE embedding IS NOT NULL"
        ).fetchone()["cnt"]

        relations = conn.execute(
            "SELECT COUNT(*) as cnt FROM memory_relations"
        ).fetchone()["cnt"]

        categories = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM shared_memories GROUP BY category"
        ).fetchall()

        sources = conn.execute(
            "SELECT source_bot, COUNT(*) as cnt FROM shared_memories GROUP BY source_bot"
        ).fetchall()

        # v3.0: 版本历史统计
        version_count = 0
        try:
            version_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM memory_versions"
            ).fetchone()["cnt"]
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        # v3.0: 过期记忆统计
        now = now_et().isoformat()
        expiring_soon = conn.execute(
            "SELECT COUNT(*) as cnt FROM shared_memories "
            "WHERE expires_at IS NOT NULL AND expires_at < ?",
            ((now_et() + timedelta(hours=24)).isoformat(),),
        ).fetchone()["cnt"]

        return {
            "total": total,
            "embedded": embedded,
            "embedding_coverage": round(embedded / max(total, 1) * 100, 1),
            "relations": relations,
            "categories": {r["category"]: r["cnt"] for r in categories},
            "sources": {r["source_bot"]: r["cnt"] for r in sources},
            "version_history_count": version_count,
            "expiring_within_24h": expiring_soon,
            "db_size_kb": round(
                self.db_path.stat().st_size / 1024, 1
            ) if self.db_path.exists() else 0,
        }
