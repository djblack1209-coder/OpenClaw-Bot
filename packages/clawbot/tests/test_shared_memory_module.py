"""
shared_memory.py 单元测试
覆盖 SharedMemory 的 remember / recall / search / forget / decay / stats 功能

- 所有测试使用临时 SQLite 数据库（tempfile.mkdtemp）
- 强制 SQLite 回退模式，不依赖 mem0ai / Qdrant / 外部 LLM
- now_et() 使用 mock 固定时间，消除时间敏感性
"""
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import src.shared_memory as sm_module

# 固定时间点
FIXED_NOW = datetime(2026, 3, 27, 12, 0, 0)


@pytest.fixture
def tmp_dir():
    """每个测试用例使用独立的临时目录"""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def mem(tmp_dir):
    """创建纯 SQLite 模式的 SharedMemory 实例（禁用 Mem0）"""
    db_path = os.path.join(tmp_dir, "test_memory.db")
    # 强制关闭 Mem0，使用 SQLite 回退
    original = sm_module._mem0_available
    sm_module._mem0_available = False
    try:
        m = sm_module.SharedMemory(db_path=db_path)
        m._using_mem0 = False
        m._mem0 = None
        yield m
    finally:
        sm_module._mem0_available = original
        m.close()


# ════════════════════════════════════════════
#  SharedMemory 测试
# ════════════════════════════════════════════

class TestSharedMemory:

    @patch("src.shared_memory.now_et", return_value=FIXED_NOW)
    def test_remember_and_recall(self, mock_now, mem):
        """存入记忆后，能通过 key 精确读取"""
        mem.remember("test_key", "test_value", category="general")
        result = mem.recall("test_key")

        assert result["success"] is True
        assert result["value"] == "test_value"
        assert result["category"] == "general"
        assert result["key"] == "test_key"

    @patch("src.shared_memory.now_et", return_value=FIXED_NOW)
    def test_remember_duplicate_key(self, mock_now, mem):
        """重复 key + category 存入时，值应被更新为最新"""
        mem.remember("dup_key", "old_value", category="general")
        mem.remember("dup_key", "new_value", category="general")

        result = mem.recall("dup_key")
        assert result["success"] is True
        # 第二次写入应覆盖第一次
        assert result["value"] == "new_value"

    @patch("src.shared_memory.now_et", return_value=FIXED_NOW)
    def test_forget(self, mock_now, mem):
        """删除记忆后，recall 返回 success=False"""
        mem.remember("temp_key", "temp_value")

        # 确认存入成功
        assert mem.recall("temp_key")["success"] is True

        # 删除
        forget_result = mem.forget("temp_key")
        assert forget_result["success"] is True

        # 确认已不可读
        assert mem.recall("temp_key")["success"] is False

    @patch("src.shared_memory.now_et", return_value=FIXED_NOW)
    def test_get_stats(self, mock_now, mem):
        """get_stats 返回正确的总数、分类和来源统计"""
        mem.remember("k1", "v1", category="cat_a", source_bot="bot1")
        mem.remember("k2", "v2", category="cat_a", source_bot="bot1")
        mem.remember("k3", "v3", category="cat_b", source_bot="bot2")

        stats = mem.get_stats()

        # 总数
        assert stats["total"] == 3
        # 按分类
        assert stats["categories"]["cat_a"] == 2
        assert stats["categories"]["cat_b"] == 1
        # 按来源
        assert stats["sources"]["bot1"] == 2
        assert stats["sources"]["bot2"] == 1
        # 引擎应为 sqlite（Mem0 已禁用）
        assert stats["engine"] == "sqlite"
        # 数据库文件大小 > 0
        assert stats["db_size_kb"] > 0
