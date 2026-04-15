"""
ClawBot - 共享记忆层 v4.0 (Mem0 驱动)
基于 mem0ai (50k⭐) 重构，保持 v3.0 完全接口兼容。

核心变更：
- 记忆存储/搜索/冲突解决 → Mem0 驱动（向量索引 + LLM 事实提取）
- workflow_feedback / collab_result → 保留 SQLite（Mem0 不覆盖）
- Mem0 不可用时 → 自动降级回 SQLite 原有逻辑

所有调用方零改动：remember/recall/search/forget/get_context_for_prompt 签名不变。
"""

import sqlite3
import threading
import logging
import time
import json
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import timedelta
from src.utils import now_et

logger = logging.getLogger(__name__)


# ── v4.1: 记忆类型枚举（借鉴 Letta memory_blocks 分类体系）──


class MemoryType:
    """记忆类型枚举 — 不同类型有不同的衰减速率和检索权重

    借鉴 Letta 的分层设计:
    - fact: 客观事实（衰减慢，如"用户叫小王"）
    - preference: 用户偏好（衰减中，如"喜欢简洁回复"）
    - episodic: 情景记忆（衰减快，如"昨天讨论了AAPL"）
    - procedural: 程序性知识（不衰减，如"用/risk查风控"）
    - meta: 系统元数据（不衰减，如"上次对话时间"）
    """

    FACT = "fact"  # 客观事实 — 衰减率 0.01/天
    PREFERENCE = "preference"  # 用户偏好 — 衰减率 0.02/天
    EPISODIC = "episodic"  # 情景记忆 — 衰减率 0.05/天
    PROCEDURAL = "procedural"  # 程序性知识 — 不衰减
    META = "meta"  # 系统元数据 — 不衰减
    GENERAL = "general"  # 通用（向后兼容）— 衰减率 0.03/天

    # 每种类型的日衰减率
    DECAY_RATES = {
        FACT: 0.01,
        PREFERENCE: 0.02,
        EPISODIC: 0.05,
        PROCEDURAL: 0.0,
        META: 0.0,
        GENERAL: 0.03,
    }

    # 检索时的权重加成（乘以 importance）
    SEARCH_WEIGHTS = {
        FACT: 1.2,
        PREFERENCE: 1.1,
        EPISODIC: 0.8,
        PROCEDURAL: 1.0,
        META: 0.5,
        GENERAL: 1.0,
    }

    ALL_TYPES = {FACT, PREFERENCE, EPISODIC, PROCEDURAL, META, GENERAL}

    @classmethod
    def from_category(cls, category: str) -> str:
        """从旧版 category 推断 memory_type（向后兼容）"""
        _MAPPING = {
            "user_preference": cls.PREFERENCE,
            "user_profile": cls.FACT,
            "key_fact": cls.FACT,
            "collab": cls.EPISODIC,
            "tool_usage": cls.PROCEDURAL,
            "system": cls.META,
            "archival": cls.GENERAL,
        }
        return _MAPPING.get(category, cls.GENERAL)


# ── Mem0 可用性检测 ──

_mem0_available = False
try:
    from mem0 import Memory as Mem0Memory

    _mem0_available = True
except ImportError:
    Mem0Memory = None  # type: ignore[assignment,misc]
    logger.info("[SharedMemory] mem0ai 未安装，使用 SQLite 回退模式")


def _build_mem0_config() -> dict:
    """构建 Mem0 配置，优先使用环境变量中的 API。"""
    # 从 config 导入避免循环依赖 (globals.py 导入了 SharedMemory, 但 config.py 无此依赖)
    from src.bot.config import SILICONFLOW_KEYS, SILICONFLOW_BASE, DATA_DIR

    config: dict = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "clawbot_memory",
                "path": str(Path(DATA_DIR) / "qdrant_data"),
                "on_disk": True,
                "embedding_model_dims": 1024,  # BAAI/bge-m3 输出维度
            },
        },
    }

    # LLM 配置：优先 SILICONFLOW_UNLIMITED_KEY（无限额），回退 SILICONFLOW_KEYS，再回退 OpenAI
    sf_unlimited_key = os.getenv("SILICONFLOW_UNLIMITED_KEY", "").strip()
    sf_base = SILICONFLOW_BASE
    openai_key = os.getenv("OPENAI_API_KEY", "")

    # SILICONFLOW_UNLIMITED_URL 可能是完整路径如 https://apis.iflow.cn/v1/chat/completions
    # 提取 base URL（去掉 /chat/completions 后缀）
    sf_unlimited_url = os.getenv("SILICONFLOW_UNLIMITED_URL", "").strip()
    if sf_unlimited_url:
        # 去除 /chat/completions 等路径后缀，保留到 /v1
        if "/chat/completions" in sf_unlimited_url:
            sf_unlimited_base = sf_unlimited_url.split("/chat/completions")[0]
        else:
            sf_unlimited_base = sf_unlimited_url.rstrip("/")
    else:
        sf_unlimited_base = sf_base

    # 选择可用的 SiliconFlow key 和对应 base URL
    # 优先使用标准 siliconflow.cn（稳定，支持 LLM + embeddings）
    # UNLIMITED_KEY 仅当 iflow.cn 可用时使用，但 iflow 不支持 embeddings，故统一用 siliconflow
    _all_keys = list(SILICONFLOW_KEYS)
    # 取最后一个 key（通常是有余额的）
    active_sf_key = _all_keys[-1] if _all_keys else sf_unlimited_key
    active_sf_base = sf_base  # 始终用 api.siliconflow.cn/v1（稳定）

    if active_sf_key:
        first_key = active_sf_key
        config["llm"] = {
            "provider": "openai",
            "config": {
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "api_key": first_key,
                "openai_base_url": active_sf_base,
                "temperature": 0.1,
                "max_tokens": 2000,
            },
        }
        # embedder 必须用标准 SiliconFlow（支持 /v1/embeddings），
        # iflow.cn 只是 LLM 代理，不提供嵌入端点
        # 从 SILICONFLOW_KEYS 轮换选 key：尽量避开余额不足的 key（取最后一个作 fallback）
        _emb_keys = list(SILICONFLOW_KEYS)
        emb_key = _emb_keys[-1] if len(_emb_keys) > 1 else (_emb_keys[0] if _emb_keys else first_key)
        emb_base = sf_base  # 始终用 api.siliconflow.cn/v1
        config["embedder"] = {
            "provider": "openai",
            "config": {
                "model": "BAAI/bge-m3",
                "api_key": emb_key,
                "openai_base_url": emb_base,
            },
        }
    elif openai_key:
        config["llm"] = {
            "provider": "openai",
            "config": {"model": "gpt-4.1-mini", "temperature": 0.1},
        }
        # embedder 默认用 OpenAI text-embedding-3-small

    return config


class SharedMemory:
    """
    跨 Agent 共享记忆 v4.1（Mem0 驱动，接口兼容 v3.0）

    Mem0 模式：向量索引 + LLM 事实提取 + 自动冲突解决
    SQLite 始终用于：workflow_feedback、collab_result 等结构化数据 + 元数据索引
    """

    # 记忆总量上限 — 超过时按 LRU 淘汰低价值记忆
    MAX_MEMORIES = 2000

    def __init__(self, db_path: Optional[str] = None, embedding_fn=None):
        # SQLite 路径（始终需要，用于 workflow_feedback 等）
        if db_path:
            self.db_path = Path(db_path)
        else:
            # 从 config 导入避免循环依赖 (globals.py 导入了 SharedMemory, 但 config.py 无此依赖)
            from src.bot.config import DATA_DIR

            self.db_path = Path(DATA_DIR) / "shared_memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._last_cleanup_time = 0.0
        self._cleanup_interval = 60

        # Mem0 初始化
        self._mem0 = None
        self._using_mem0 = False
        # 记忆系统运行模式标记，初始为 SQLite 降级
        self._memory_mode: str = "sqlite_basic"
        if _mem0_available and Mem0Memory is not None:
            try:
                # 优先使用 Mem0 Cloud API（无需本地 qdrant + embedding）
                mem0_api_key = os.getenv("MEM0_API_KEY", "").strip()
                if mem0_api_key:
                    try:
                        from mem0 import MemoryClient

                        self._mem0 = MemoryClient(api_key=mem0_api_key)
                        self._using_mem0 = True
                        self._memory_mode = "mem0_cloud"
                        logger.info("[SharedMemory] v4.1 Mem0 Cloud API 模式启动成功")
                    except (ImportError, Exception) as e:
                        logger.debug(f"[SharedMemory] Mem0 Cloud 初始化失败，尝试本地模式: {e}")

                # 回退到本地 Mem0（qdrant + SiliconFlow LLM）
                if not self._using_mem0:
                    config = _build_mem0_config()
                    # 临时屏蔽 OPENROUTER_API_KEY，防止 mem0 自动路由到 OpenRouter
                    # mem0 会扫描环境变量自动选 LLM provider，优先级高于显式 config
                    _or_key = os.environ.pop("OPENROUTER_API_KEY", None)
                    try:
                        self._mem0 = Mem0Memory.from_config(config)
                        self._using_mem0 = True
                        self._memory_mode = "mem0_local"
                        logger.info("[SharedMemory] v4.0 Mem0 本地模式启动成功")
                    finally:
                        if _or_key is not None:
                            os.environ["OPENROUTER_API_KEY"] = _or_key
            except Exception as e:
                logger.warning("[SharedMemory] Mem0 初始化失败，回退 SQLite: %s", e)

        # 初始化 SQLite 表（始终需要）
        self._init_db()

        # 输出当前记忆系统运行模式
        _mode_desc = {
            "mem0_cloud": "☁️ Mem0 Cloud 语义搜索（最佳）",
            "mem0_local": "💾 Mem0 本地向量搜索（良好）",
            "sqlite_basic": "⚠️ SQLite 关键词匹配（基础模式，语义搜索不可用）",
        }
        logger.info(f"[记忆系统] 运行模式: {_mode_desc.get(self._memory_mode, '未知')}")

    def get_memory_mode_description(self) -> str:
        """返回当前记忆系统运行模式的中文描述，供日报或状态查询使用。"""
        _mode_desc = {
            "mem0_cloud": "☁️ Mem0 Cloud 语义搜索（最佳） — 支持跨语言语义匹配，自动事实提取",
            "mem0_local": "💾 Mem0 本地向量搜索（良好） — 本地向量索引，无需外部 API",
            "sqlite_basic": "⚠️ SQLite 关键词匹配（基础模式） — 仅支持精确关键词搜索，语义搜索不可用",
        }
        return _mode_desc.get(self._memory_mode, f"未知模式: {self._memory_mode}")

    # ── SQLite 连接管理 ──

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), timeout=10, check_same_thread=False)
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
                last_decay_at TEXT,
                mem0_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_shared_mem_key ON shared_memories(key);
            CREATE INDEX IF NOT EXISTS idx_shared_mem_category ON shared_memories(category);
            CREATE INDEX IF NOT EXISTS idx_shared_mem_importance ON shared_memories(importance DESC);
            CREATE INDEX IF NOT EXISTS idx_shared_mem_source ON shared_memories(source_bot);

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
        # 确保 mem0_id 列存在（升级兼容）
        try:
            conn.execute("SELECT mem0_id FROM shared_memories LIMIT 1")
        except sqlite3.OperationalError as e:  # noqa: F841
            conn.execute("ALTER TABLE shared_memories ADD COLUMN mem0_id TEXT")
        # mem0_id 索引必须在列确认存在后创建
        conn.execute("CREATE INDEX IF NOT EXISTS idx_shared_mem_mem0id ON shared_memories(mem0_id)")
        conn.commit()

    # ════════════════════════════════════════════
    #  写入
    # ════════════════════════════════════════════

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
        memory_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """存入共享记忆。接口与 v3.0 完全兼容。

        v4.1 新增: memory_type 参数（fact/preference/episodic/procedural/meta）
        不传则从 category 自动推断。
        """
        # v4.1: 推断 memory_type
        if memory_type is None:
            memory_type = MemoryType.from_category(category)

        mem0_id = None

        # ── Mem0 写入（自动事实提取 + 向量索引）──
        if self._using_mem0 and self._mem0:
            try:
                content = f"[{category}] {key}: {value}"
                metadata = {
                    "category": category,
                    "source_bot": source_bot,
                    "importance": importance,
                    "key": key,
                }
                if chat_id is not None:
                    metadata["chat_id"] = str(chat_id)
                # 检查是否是 Cloud 模式 (MemoryClient)
                try:
                    from mem0 import MemoryClient

                    is_cloud = isinstance(self._mem0, MemoryClient)
                except ImportError:
                    is_cloud = False

                if is_cloud:
                    # Cloud API: 第一个参数是字符串
                    result = self._mem0.add(
                        content,
                        user_id=str(chat_id) if chat_id is not None else "global",
                        metadata=metadata,
                    )
                else:
                    # 本地 Memory 模式: 第一个参数是消息列表
                    messages = [{"role": "user", "content": content}]
                    result = self._mem0.add(
                        messages,
                        agent_id="clawbot",
                        user_id=str(chat_id) if chat_id is not None else "global",
                        metadata=metadata,
                        infer=False,  # 直接存储，不做 LLM 提取（保持与 v3 行为一致）
                    )
                # 提取 mem0 返回的 ID
                if isinstance(result, dict):
                    results_list = result.get("results", [])
                    if results_list and isinstance(results_list[0], dict):
                        mem0_id = results_list[0].get("id")
                elif isinstance(result, list) and result:
                    mem0_id = result[0].get("id") if isinstance(result[0], dict) else None
            except Exception as e:
                logger.warning("[SharedMemory] Mem0 写入失败，回退 SQLite: %s", e)

        # ── SQLite 写入（索引 + 元数据 + 过期管理）──
        conn = self._get_conn()
        now = now_et().isoformat()
        expires_at = None
        if ttl_hours:
            expires_at = (now_et() + timedelta(hours=ttl_hours)).isoformat()

        with self._lock:
            existing = conn.execute(
                "SELECT id FROM shared_memories WHERE key = ? AND category = ?",
                (key, category),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE shared_memories SET value = ?, source_bot = ?, chat_id = ?, "
                    "importance = ?, updated_at = ?, expires_at = ?, "
                    "last_decay_at = ?, mem0_id = ? WHERE id = ?",
                    (value, source_bot, chat_id, importance, now, expires_at, now, mem0_id, existing["id"]),
                )
                mem_id = existing["id"]
            else:
                cursor = conn.execute(
                    "INSERT INTO shared_memories "
                    "(key, value, category, source_bot, chat_id, importance, "
                    "created_at, updated_at, expires_at, last_decay_at, mem0_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        key,
                        value,
                        category,
                        source_bot,
                        chat_id,
                        importance,
                        now,
                        now,
                        expires_at,
                        now,
                        mem0_id,
                    ),
                )
                mem_id = cursor.lastrowid
            conn.commit()

            if related_keys and mem_id:
                self._link_memories(conn, mem_id, related_keys)

        logger.debug("[SharedMemory] %s 写入: [%s] %s (mem0=%s)", source_bot, category, key, bool(mem0_id))
        return {"success": True, "key": key, "category": category, "source": source_bot, "id": mem_id}

    def _link_memories(self, conn, from_id: int, related_keys: List[str]):
        """建立记忆间的关联"""
        for rk in related_keys:
            row = conn.execute(
                "SELECT id FROM shared_memories WHERE key = ? ORDER BY importance DESC LIMIT 1",
                (rk,),
            ).fetchone()
            if row and row["id"] != from_id:
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
                    conn.execute(
                        "INSERT INTO memory_relations (from_id, to_id, relation_type, strength) "
                        "VALUES (?, ?, 'related', 1.0)",
                        (row["id"], from_id),
                    )
        conn.commit()

    def recall(self, key: str, category: Optional[str] = None) -> Dict[str, Any]:
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

    def search(
        self, query: str, limit: int = 10, mode: str = "hybrid", chat_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """混合搜索记忆。Mem0 模式下使用向量索引，SQLite 模式下使用关键词+本地嵌入。"""
        conn = self._get_conn()
        self._cleanup_expired(conn)

        # ── Mem0 语义搜索 ──
        mem0_results = []
        if self._using_mem0 and self._mem0 and mode in ("semantic", "hybrid"):
            try:
                user_id = str(chat_id) if chat_id else "global"
                raw = self._mem0.search(
                    query,
                    limit=limit * 2,
                    agent_id="clawbot",
                    user_id=user_id,
                )
                items = raw.get("results", raw) if isinstance(raw, dict) else raw
                for r in items or []:
                    if not isinstance(r, dict):
                        continue
                    content = r.get("memory", r.get("text", ""))
                    meta = r.get("metadata", {}) or {}
                    mem0_results.append(
                        {
                            "id": r.get("id", ""),
                            "key": meta.get("key", content[:50]),
                            "value": content[:200],
                            "category": meta.get("category", "general"),
                            "source_bot": meta.get("source_bot", "unknown"),
                            "importance": int(meta.get("importance", 1)),
                            "score": float(r.get("score", 0)),
                            "similarity": round(float(r.get("score", 0)), 3),
                            "match_type": "mem0_semantic",
                            "search_mode": "semantic",  # 标记为语义搜索
                        }
                    )
            except Exception as e:
                logger.warning("[SharedMemory] Mem0 搜索失败: %s", e)

        # ── SQLite 关键词搜索（含 chat_id 隔离）──
        keyword_results = []
        if mode in ("keyword", "hybrid"):
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            # 按 chat_id 隔离搜索，防止跨用户记忆泄漏
            if chat_id is not None:
                rows = conn.execute(
                    "SELECT * FROM shared_memories "
                    "WHERE (key LIKE ? ESCAPE '\\' OR value LIKE ? ESCAPE '\\') "
                    "AND chat_id = ? "
                    "ORDER BY importance DESC, updated_at DESC LIMIT ?",
                    (f"%{escaped}%", f"%{escaped}%", str(chat_id), limit * 2),
                ).fetchall()
            else:
                # 安全修复: chat_id 未提供时，仅搜索全局记忆(chat_id IS NULL)，
                # 防止跨用户记忆泄漏
                rows = conn.execute(
                    "SELECT * FROM shared_memories "
                    "WHERE (key LIKE ? ESCAPE '\\' OR value LIKE ? ESCAPE '\\') "
                    "AND chat_id IS NULL "
                    "ORDER BY importance DESC, updated_at DESC LIMIT ?",
                    (f"%{escaped}%", f"%{escaped}%", limit * 2),
                ).fetchall()
            for r in rows:
                keyword_results.append(
                    {
                        "id": r["id"],
                        "key": r["key"],
                        "value": r["value"][:200],
                        "category": r["category"],
                        "source_bot": r["source_bot"],
                        "importance": r["importance"],
                        "score": r["importance"] * 0.2,
                        "match_type": "keyword",
                        "search_mode": "basic",  # 标记为基础关键词搜索
                    }
                )

        # ── 合并排序 ──
        semantic_pool = mem0_results
        if mode == "hybrid":
            seen_keys = set()
            merged = []
            for r in semantic_pool:
                r["score"] = r["score"] * 0.6 + r["importance"] * 0.08
                rk = r.get("key", "")
                if rk not in seen_keys:
                    seen_keys.add(rk)
                    merged.append(r)
            for r in keyword_results:
                rk = r.get("key", "")
                if rk not in seen_keys:
                    r["score"] = r["score"] * 0.4
                    seen_keys.add(rk)
                    merged.append(r)
            merged.sort(key=lambda x: -x["score"])
            results = merged[:limit]
        elif mode == "semantic":
            results = semantic_pool[:limit]
        else:
            results = keyword_results[:limit]

        return {"success": True, "query": query, "mode": mode, "results": results, "count": len(results)}

    def semantic_search(
        self, query: str, limit: int = 5, category: Optional[str] = None, chat_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """纯语义搜索。Mem0 模式下直接用向量索引。"""
        # ── Mem0 路径 ──
        if self._using_mem0 and self._mem0:
            try:
                filters = {}
                if category:
                    filters["category"] = category
                raw = self._mem0.search(
                    query,
                    limit=limit,
                    filters=filters if filters else None,
                    user_id=str(chat_id) if chat_id else "global",
                )
                items = raw.get("results", raw) if isinstance(raw, dict) else raw
                results = []
                for r in items or []:
                    if not isinstance(r, dict):
                        continue
                    content = r.get("memory", r.get("text", ""))
                    meta = r.get("metadata", {}) or {}
                    results.append(
                        {
                            "key": meta.get("key", content[:50]),
                            "value": content,
                            "category": meta.get("category", "general"),
                            "source_bot": meta.get("source_bot", "unknown"),
                            "importance": int(meta.get("importance", 1)),
                            "similarity": round(float(r.get("score", 0)), 3),
                            "search_mode": "semantic",  # 标记为语义搜索
                        }
                    )
                return results
            except Exception as e:
                logger.warning("[SharedMemory] Mem0 semantic_search 失败: %s", e)

        # ── SQLite 关键词回退（Mem0 不可用时）──
        # 首次降级搜索时发出警告，提醒用户当前搜索质量有限
        if not hasattr(self, "_sqlite_search_warned"):
            self._sqlite_search_warned = True
            logger.warning("[记忆系统] 当前使用 SQLite 基础搜索，语义匹配不可用。配置 MEM0_API_KEY 可启用完整语义搜索")
        conn = self._get_conn()
        self._cleanup_expired(conn)
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql = (
            "SELECT key, value, category, source_bot, importance "
            "FROM shared_memories WHERE (key LIKE ? ESCAPE '\\' OR value LIKE ? ESCAPE '\\')"
        )
        params: list = [f"%{escaped}%", f"%{escaped}%"]
        if chat_id is not None:
            sql += " AND (chat_id = ? OR chat_id IS NULL)"
            params.append(str(chat_id))
        else:
            sql += " AND chat_id IS NULL"
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY importance DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "key": r["key"],
                "value": r["value"],
                "category": r["category"],
                "source_bot": r["source_bot"],
                "importance": r["importance"],
                "similarity": 0.5,  # 关键词匹配给固定分数
                "search_mode": "basic",  # 标记为基础搜索，调用方可据此判断搜索质量
            }
            for r in rows
        ]

    # ════════════════════════════════════════════
    #  删除
    # ════════════════════════════════════════════

    def forget(self, key: str, category: Optional[str] = None) -> Dict[str, Any]:
        """删除记忆"""
        conn = self._get_conn()

        # 先查 mem0_id，如果有则同步删除 Mem0 中的记忆
        if self._using_mem0 and self._mem0:
            try:
                if category:
                    row = conn.execute(
                        "SELECT mem0_id FROM shared_memories WHERE key = ? AND category = ? AND mem0_id IS NOT NULL",
                        (key, category),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT mem0_id FROM shared_memories WHERE key = ? AND mem0_id IS NOT NULL",
                        (key,),
                    ).fetchone()
                if row and row["mem0_id"]:
                    self._mem0.delete(row["mem0_id"])
            except Exception as e:
                logger.debug("[SharedMemory] Mem0 删除失败: %s", e)

        if category:
            result = conn.execute(
                "DELETE FROM shared_memories WHERE key = ? AND category = ?",
                (key, category),
            )
        else:
            result = conn.execute("DELETE FROM shared_memories WHERE key = ?", (key,))
        conn.commit()

        if result.rowcount > 0:
            return {"success": True, "deleted": result.rowcount}
        return {"success": False, "error": f"未找到: {key}"}

    # ════════════════════════════════════════════
    #  /collab 结论存储
    # ════════════════════════════════════════════

    def save_collab_result(
        self,
        task_text: str,
        plan_result: str,
        exec_result: str,
        summary_result: str,
        planner_id: str,
        chat_id: Optional[int] = None,
    ):
        short_task = task_text[:80]
        timestamp = now_et().strftime("%m/%d %H:%M")
        self.remember(
            key=f"collab_{timestamp}_{short_task}",
            value=summary_result[:2000],
            category="collab",
            source_bot="collab_system",
            chat_id=chat_id,
            importance=3,
            ttl_hours=72,
        )
        self.remember(
            key=f"collab_brief_{timestamp}",
            value=f"任务: {short_task} | 规划: {planner_id} | 结论: {summary_result[:300]}",
            category="collab_brief",
            source_bot="collab_system",
            chat_id=chat_id,
            importance=2,
            ttl_hours=48,
        )

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
            "INSERT INTO workflow_feedback (workflow_id, chat_id, original_text, "
            "selected_option, stage1_score, stage2_score, stage3_score, summary, "
            "improvement_focus, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        params: list = []
        query = (
            "SELECT workflow_id, selected_option, stage1_score, stage2_score, "
            "stage3_score, improvement_focus, created_at FROM workflow_feedback"
        )
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
        avg1 = round(sum(int(r["stage1_score"]) for r in rows) / count, 2)
        avg2 = round(sum(int(r["stage2_score"]) for r in rows) / count, 2)
        avg3 = round(sum(int(r["stage3_score"]) for r in rows) / count, 2)
        stage_map = {"客服接待": avg1, "方案评审": avg2, "任务交付": avg3}
        weakest = min(stage_map.items(), key=lambda item: item[1])[0]
        focus = [str(r["improvement_focus"] or "").strip() for r in rows if str(r["improvement_focus"] or "").strip()]
        return {
            "count": count,
            "avg_stage1": avg1,
            "avg_stage2": avg2,
            "avg_stage3": avg3,
            "weakest_stage": weakest,
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

    # ════════════════════════════════════════════
    #  System Prompt 注入
    # ════════════════════════════════════════════

    def get_context_for_prompt(self, max_tokens: int = 500, chat_id: Optional[int] = None) -> str:
        """生成注入到 system_prompt 的记忆索引（L0 地图模型）。

        采用递归索引架构，只注入最浅层的"世界地图"（分类统计+高亮条目），
        不平铺所有记忆。需要细节时通过 search()/semantic_search() 按需加载。

        L0 世界地图 (~80 token): 分类名+条数 + 最重要的3条高亮
        L1 区域地图 (按需): search(category=xxx) 加载某个分类
        L2 具体记忆 (按需): recall(key) 或 semantic_search() 加载单条
        """
        conn = self._get_conn()
        self._cleanup_expired(conn)

        # ── L0: 分类统计（世界地图）──
        chat_filter = "chat_id = ? OR chat_id IS NULL" if chat_id else "chat_id IS NULL"
        params: list = [str(chat_id)] if chat_id else []

        category_rows = conn.execute(
            f"SELECT category, COUNT(*) as cnt, MAX(importance) as max_imp "
            f"FROM shared_memories WHERE {chat_filter} "
            f"GROUP BY category ORDER BY cnt DESC",
            params,
        ).fetchall()

        if not category_rows:
            return ""

        total_count = sum(r["cnt"] for r in category_rows)
        cat_summary = ", ".join(f"{r['category']}({r['cnt']}条)" for r in category_rows[:8])

        # ── L0: 高亮条目（最重要的3条，每条≤60字）──
        highlight_rows = conn.execute(
            f"SELECT key, value, category FROM shared_memories "
            f"WHERE {chat_filter} "
            f"ORDER BY importance DESC, access_count DESC, updated_at DESC LIMIT 3",
            params,
        ).fetchall()

        highlights = ""
        if highlight_rows:
            hl_parts = [f"· {r['key']}: {r['value'][:60]}" for r in highlight_rows]
            highlights = "\n" + "\n".join(hl_parts)

        return (
            f"\n\n<memory-index>\n"
            f"[记忆索引] 共{total_count}条: {cat_summary}{highlights}\n"
            f"需要细节时用 search()/recall() 按需查找，不要猜测记忆内容。\n"
            f"</memory-index>"
        )

    # ════════════════════════════════════════════
    #  内部方法
    # ════════════════════════════════════════════

    def _cleanup_expired(self, conn: sqlite3.Connection):
        """清理过期记忆 + LRU 淘汰超量记忆 + v4.1 记忆衰减"""
        now_ts = time.time()
        if now_ts - self._last_cleanup_time < self._cleanup_interval:
            return
        self._last_cleanup_time = now_ts
        now = now_et().isoformat()

        # 阶段1: TTL 过期清理
        conn.execute(
            "DELETE FROM shared_memories WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )

        # 阶段1.5 (v4.1): 记忆重要性衰减 — 每次清理时降低旧记忆的 importance
        # 借鉴 Letta 的记忆衰减机制，不同类型衰减速率不同
        try:
            # 获取超过1天未衰减的记忆
            yesterday = (now_et() - timedelta(days=1)).isoformat()
            old_memories = conn.execute(
                "SELECT id, category, importance FROM shared_memories "
                "WHERE (last_decay_at IS NULL OR last_decay_at < ?) "
                "AND importance > 0",
                (yesterday,),
            ).fetchall()

            decayed_count = 0
            for row in old_memories:
                mem_id = row["id"]
                category = row["category"]
                importance = row["importance"]
                # 根据记忆类型确定衰减率
                mem_type = MemoryType.from_category(category)
                decay_rate = MemoryType.DECAY_RATES.get(mem_type, 0.03)
                if decay_rate <= 0:
                    continue  # 不衰减的类型（procedural/meta）
                # 计算新 importance（最低为0）
                new_importance = max(0, importance - 1) if decay_rate >= 0.05 else importance
                # 低衰减率只在 importance > 2 时衰减
                if decay_rate < 0.05 and importance > 2:
                    new_importance = importance  # 低衰减率暂不降级
                elif decay_rate >= 0.05 and importance > 0:
                    new_importance = max(0, importance - 1)
                    decayed_count += 1

                if new_importance != importance:
                    conn.execute(
                        "UPDATE shared_memories SET importance = ?, last_decay_at = ? WHERE id = ?",
                        (new_importance, now, mem_id),
                    )
                else:
                    # 只更新 last_decay_at 避免重复处理
                    conn.execute(
                        "UPDATE shared_memories SET last_decay_at = ? WHERE id = ?",
                        (now, mem_id),
                    )

            if decayed_count > 0:
                logger.info(f"[SharedMemory] 记忆衰减: {decayed_count} 条情景记忆 importance 降级")
        except Exception as e:
            logger.debug(f"[SharedMemory] 记忆衰减失败: {e}")

        # 阶段2: LRU 淘汰 — 超过总量上限时，按低重要性+低访问+旧时间淘汰
        total = conn.execute("SELECT COUNT(*) FROM shared_memories").fetchone()[0]
        if total > self.MAX_MEMORIES:
            overflow = total - self.MAX_MEMORIES
            # 保留 importance >= 4 的高价值记忆，淘汰低价值的
            conn.execute(
                "DELETE FROM shared_memories WHERE id IN ("
                "  SELECT id FROM shared_memories"
                "  WHERE importance < 4"
                "  ORDER BY importance ASC, access_count ASC, updated_at ASC"
                "  LIMIT ?"
                ")",
                (overflow,),
            )
            logger.info("[SharedMemory] LRU 淘汰 %d 条低价值记忆 (总量 %d → %d)", overflow, total, self.MAX_MEMORIES)

        conn.commit()

    def close(self):
        """关闭所有数据库连接"""
        try:
            if hasattr(self._local, "conn") and self._local.conn:
                self._local.conn.close()
                self._local.conn = None
        except Exception as e:
            logger.debug(f"关闭连接时出错: {e}")

    # ════════════════════════════════════════════
    #  统计
    # ════════════════════════════════════════════

    def get_stats(self) -> Dict[str, Any]:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as cnt FROM shared_memories").fetchone()["cnt"]
        embedded = conn.execute("SELECT COUNT(*) as cnt FROM shared_memories WHERE embedding IS NOT NULL").fetchone()[
            "cnt"
        ]
        relations = conn.execute("SELECT COUNT(*) as cnt FROM memory_relations").fetchone()["cnt"]
        categories = conn.execute("SELECT category, COUNT(*) as cnt FROM shared_memories GROUP BY category").fetchall()
        sources = conn.execute("SELECT source_bot, COUNT(*) as cnt FROM shared_memories GROUP BY source_bot").fetchall()
        mem0_count = 0
        if self._using_mem0:
            mem0_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM shared_memories WHERE mem0_id IS NOT NULL"
            ).fetchone()["cnt"]
        return {
            "total": total,
            "embedded": embedded,
            "embedding_coverage": round(embedded / max(total, 1) * 100, 1),
            "relations": relations,
            "categories": {r["category"]: r["cnt"] for r in categories},
            "sources": {r["source_bot"]: r["cnt"] for r in sources},
            "engine": "mem0" if self._using_mem0 else "sqlite",
            "mem0_synced": mem0_count,
            "db_size_kb": round(self.db_path.stat().st_size / 1024, 1) if self.db_path.exists() else 0,
        }
