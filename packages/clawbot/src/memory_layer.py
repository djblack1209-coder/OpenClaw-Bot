"""
Memory Layer — 基于 mem0 的统一记忆层

替换 shared_memory.py 中的自研 RAG 部分:
- 向量嵌入 + 语义搜索 → mem0 处理
- 记忆提取 + 冲突消解 → mem0 处理
- 保留: SQLite 基础存储、记忆索引协议、重要性衰减

当 mem0 未安装时，自动回退到原有 SharedMemory。
"""
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

_mem0_available = False
_memory_instance = None

try:
    from mem0 import Memory as Mem0Memory
    _mem0_available = True
except ImportError:
    _mem0_available = False
    logger.info("[MemoryLayer] mem0 未安装, 使用原有 SharedMemory 回退")


class MemoryLayer:
    """
    统一记忆层。优先使用 mem0，回退到 SharedMemory。
    
    mem0 处理: 向量嵌入、语义搜索、记忆提取、冲突消解
    保留自定义: 记忆索引协议(INDEX.md)、分类体系、重要性衰减
    """

    def __init__(self, config: Dict = None):
        self._mem0 = None
        self._shared_memory = None
        self._config = config or {}
        self._using_mem0 = False

    def initialize(self):
        """初始化记忆层"""
        if _mem0_available:
            try:
                mem0_config = self._config.get("mem0", {})
                if not mem0_config:
                    # 默认配置: 使用 Qdrant 内存模式 + OpenAI 兼容嵌入
                    mem0_config = {
                        "vector_store": {
                            "provider": "qdrant",
                            "config": {"collection_name": "clawbot_memory", "on_disk": True},
                        },
                    }
                    # 如果有 SiliconFlow 或其他嵌入 API
                    import os
                    embed_base = os.getenv("EMBEDDING_BASE_URL", "")
                    embed_key = os.getenv("EMBEDDING_API_KEY", "")
                    if embed_base and embed_key:
                        mem0_config["embedder"] = {
                            "provider": "openai",
                            "config": {
                                "api_key": embed_key,
                                "openai_base_url": embed_base,
                                "model": "text-embedding-3-small",
                            },
                        }

                self._mem0 = Mem0Memory.from_config(mem0_config)
                self._using_mem0 = True
                logger.info("[MemoryLayer] mem0 初始化成功")
            except Exception as e:
                logger.warning(f"[MemoryLayer] mem0 初始化失败: {e}, 回退到 SharedMemory")
                self._init_fallback()
        else:
            self._init_fallback()

    def _init_fallback(self):
        """回退到原有 SharedMemory"""
        try:
            from src.shared_memory import SharedMemory
            self._shared_memory = SharedMemory()
            self._using_mem0 = False
            logger.info("[MemoryLayer] 使用 SharedMemory 回退模式")
        except Exception as e:
            logger.error(f"[MemoryLayer] SharedMemory 初始化也失败: {e}")

    def add(self, content: str, user_id: str = "boss", metadata: Dict = None) -> Dict:
        """添加记忆"""
        if self._using_mem0 and self._mem0:
            try:
                messages = [{"role": "user", "content": content}]
                result = self._mem0.add(messages, user_id=user_id, metadata=metadata)
                return {"success": True, "engine": "mem0", "result": result}
            except Exception as e:
                logger.warning(f"[MemoryLayer] mem0 add failed: {e}")

        if self._shared_memory:
            try:
                category = (metadata or {}).get("category", "general")
                self._shared_memory.remember(
                    key=content[:64], value=content, category=category,
                )
                return {"success": True, "engine": "shared_memory"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "no memory backend available"}

    def search(
        self, query: str, user_id: str = "boss", limit: int = 5
    ) -> List[Dict]:
        """搜索记忆"""
        if self._using_mem0 and self._mem0:
            try:
                results = self._mem0.search(query, user_id=user_id, limit=limit)
                items = results.get("results", results) if isinstance(results, dict) else results
                return [
                    {
                        "content": r.get("memory", r.get("text", "")) if isinstance(r, dict) else str(r),
                        "score": r.get("score", 0) if isinstance(r, dict) else 0,
                        "metadata": r.get("metadata", {}) if isinstance(r, dict) else {},
                        "engine": "mem0",
                    }
                    for r in (items or [])
                ]
            except Exception as e:
                logger.warning(f"[MemoryLayer] mem0 search failed: {e}")

        if self._shared_memory:
            try:
                results = self._shared_memory.search(query, limit=limit, mode="hybrid")
                return [
                    {
                        "content": r.get("value", ""),
                        "score": r.get("similarity", 0),
                        "metadata": {"category": r.get("category", "")},
                        "engine": "shared_memory",
                    }
                    for r in results
                ]
            except Exception as e:
                logger.warning(f"[MemoryLayer] SharedMemory search failed: {e}")

        return []

    def get_all(self, user_id: str = "boss") -> List[Dict]:
        """获取所有记忆"""
        if self._using_mem0 and self._mem0:
            try:
                return self._mem0.get_all(user_id=user_id)
            except Exception as e:
                logger.warning(f"[MemoryLayer] mem0 get_all failed: {e}")

        if self._shared_memory:
            try:
                return self._shared_memory.get_all()
            except Exception:
                pass
        return []

    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        if self._using_mem0 and self._mem0:
            try:
                self._mem0.delete(memory_id)
                return True
            except Exception:
                pass
        return False

    @property
    def engine(self) -> str:
        if self._using_mem0:
            return "mem0"
        if self._shared_memory:
            return "shared_memory"
        return "none"

    def get_stats(self) -> Dict:
        return {
            "engine": self.engine,
            "mem0_available": _mem0_available,
        }


# 全局单例
memory_layer = MemoryLayer()
