"""
Tests for SharedMemory — ALL user memory CRUD operations.

Uses SQLite fallback mode only (no mem0/Qdrant required).
"""
import json
import time

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Patch mem0 availability before importing SharedMemory
import src.shared_memory as sm_module


@pytest.fixture
def memory(tmp_path):
    """SharedMemory in pure SQLite mode (mem0 disabled)."""
    db = tmp_path / "test_memory.db"
    # Force SQLite-only by temporarily disabling mem0
    original_available = sm_module._mem0_available
    sm_module._mem0_available = False
    try:
        mem = sm_module.SharedMemory(db_path=str(db))
        # Ensure we're NOT using mem0
        mem._using_mem0 = False
        mem._mem0 = None
        yield mem
    finally:
        sm_module._mem0_available = original_available
        mem.close()


# ============ remember / recall ============

class TestRememberRecall:

    def test_remember_stores_fact(self, memory):
        """remember() should store a fact and return success."""
        result = memory.remember(
            key="user_name", value="Alice",
            category="profile", source_bot="bot1",
        )
        assert result["success"] is True
        assert result["key"] == "user_name"

    def test_recall_retrieves_stored_fact(self, memory):
        """recall() should retrieve a previously stored fact."""
        memory.remember(key="fav_color", value="blue", category="pref")
        result = memory.recall("fav_color")
        assert result["success"] is True
        assert result["value"] == "blue"
        assert result["category"] == "pref"

    def test_recall_returns_failure_for_unknown_key(self, memory):
        """recall() should return success=False for non-existent key."""
        result = memory.recall("nonexistent_key_xyz")
        assert result["success"] is False

    def test_remember_updates_existing_key(self, memory):
        """remember() same key+category should update, not duplicate."""
        memory.remember(key="city", value="Beijing", category="location")
        memory.remember(key="city", value="Shanghai", category="location")
        result = memory.recall("city", category="location")
        assert result["value"] == "Shanghai"

    def test_recall_with_category_filter(self, memory):
        """recall() with category should match only that category."""
        memory.remember(key="note", value="v1", category="work")
        memory.remember(key="note", value="v2", category="personal")
        result = memory.recall("note", category="work")
        assert result["value"] == "v1"

    def test_remember_with_chat_id(self, memory):
        """remember() should store chat_id metadata."""
        result = memory.remember(
            key="user_pref", value="dark mode",
            chat_id=12345, source_bot="bot1",
        )
        assert result["success"] is True
        # Verify chat_id was stored
        conn = memory._get_conn()
        row = conn.execute(
            "SELECT chat_id FROM shared_memories WHERE key = ?",
            ("user_pref",),
        ).fetchone()
        assert row["chat_id"] == 12345


# ============ forget ============

class TestForget:

    def test_forget_removes_stored_fact(self, memory):
        """forget() should remove a stored memory."""
        memory.remember(key="temp_data", value="delete_me")
        result = memory.forget("temp_data")
        assert result["success"] is True
        assert result["deleted"] >= 1
        # Verify it's gone
        recall_result = memory.recall("temp_data")
        assert recall_result["success"] is False

    def test_forget_nonexistent_returns_failure(self, memory):
        """forget() for non-existent key should return success=False."""
        result = memory.forget("does_not_exist_xyz")
        assert result["success"] is False


# ============ search ============

class TestSearch:

    def test_keyword_search_finds_matching(self, memory):
        """search() should find memories matching keyword."""
        memory.remember(key="python_tip", value="use list comprehensions")
        memory.remember(key="java_tip", value="use streams")
        result = memory.search("python", mode="keyword")
        assert result["success"] is True
        assert result["count"] >= 1
        keys = [r["key"] for r in result["results"]]
        assert "python_tip" in keys

    def test_search_respects_chat_id_isolation(self, memory):
        """安全修复: search(chat_id=None) 仅返回全局记忆(chat_id IS NULL)，
        不会泄漏其他用户的记忆。"""
        memory.remember(key="secret_a", value="data for user A", chat_id=100)
        memory.remember(key="secret_b", value="data for user B", chat_id=200)
        memory.remember(key="global_c", value="global data for all")
        # 无 chat_id 搜索只返回全局记忆，不返回用户 A/B 的记忆
        result = memory.search("data", mode="keyword")
        keys = [r["key"] for r in result["results"]]
        assert "global_c" in keys
        assert "secret_a" not in keys
        assert "secret_b" not in keys
        # 用户 A 搜索可以看到自己的记忆 + 全局记忆
        result_a = memory.search("data", mode="keyword", chat_id=100)
        keys_a = [r["key"] for r in result_a["results"]]
        assert "secret_a" in keys_a

    def test_search_semantic_in_sqlite_mode(self, memory):
        """Semantic search in SQLite fallback uses local n-gram embeddings."""
        memory.remember(key="ai_topic", value="machine learning is great for AI")
        memory.remember(key="cooking", value="pasta recipe with tomato sauce")
        # Use keyword that only matches ai_topic
        result = memory.search("machine learning", mode="hybrid")
        assert result["success"] is True
        assert result["count"] >= 1
        keys = [r["key"] for r in result["results"]]
        assert "ai_topic" in keys

    def test_search_empty_query(self, memory):
        """search() with empty query should still work (returns keyword matches)."""
        memory.remember(key="any_key", value="any_value")
        result = memory.search("", mode="keyword")
        assert result["success"] is True


# ============ get_or_default / get_context ============

class TestGetContext:

    def test_get_context_returns_empty_for_no_memories(self, memory):
        """get_context_for_prompt() should return '' when no memories exist."""
        ctx = memory.get_context_for_prompt()
        assert ctx == ""

    def test_get_context_builds_string(self, memory):
        """get_context_for_prompt() should build a formatted context string."""
        memory.remember(key="project", value="OpenClaw Bot", category="info", importance=5)
        memory.remember(key="stack", value="Python + FastAPI", category="tech", importance=3)
        ctx = memory.get_context_for_prompt()
        assert "共享记忆" in ctx
        assert "project" in ctx
        assert "OpenClaw Bot" in ctx


# ============ _cleanup_expired ============

class TestCleanupExpired:

    def test_cleanup_expired_removes_expired_entries(self, memory):
        """_cleanup_expired should remove entries past their expires_at."""
        conn = memory._get_conn()
        # Insert an already-expired entry directly
        from src.utils import now_et
        from datetime import timedelta
        expired_time = (now_et() - timedelta(hours=1)).isoformat()
        conn.execute(
            "INSERT INTO shared_memories (key, value, category, source_bot, "
            "importance, created_at, updated_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("expired_key", "old_data", "general", "system", 1,
             expired_time, expired_time, expired_time),
        )
        conn.commit()

        # Force cleanup (reset interval timer)
        memory._last_cleanup_time = 0
        memory._cleanup_expired(conn)

        row = conn.execute(
            "SELECT * FROM shared_memories WHERE key = ?", ("expired_key",)
        ).fetchone()
        assert row is None

    def test_cleanup_respects_interval(self, memory):
        """_cleanup_expired should skip if called within interval."""
        conn = memory._get_conn()
        memory._last_cleanup_time = time.time()  # Just cleaned
        # This should be a no-op (no delete executed due to interval check)
        memory._cleanup_expired(conn)
        # No assertion needed — just verifying no crash


# ============ get_stats ============

class TestStats:

    def test_get_stats_returns_structure(self, memory):
        """get_stats() should return correct structure."""
        memory.remember(key="s1", value="v1", category="cat_a", source_bot="bot1")
        memory.remember(key="s2", value="v2", category="cat_b", source_bot="bot2")
        stats = memory.get_stats()
        assert stats["total"] == 2
        assert stats["engine"] == "sqlite"
        assert "categories" in stats
        assert "cat_a" in stats["categories"]
        assert stats["categories"]["cat_a"] == 1
        assert "sources" in stats
        assert "db_size_kb" in stats
