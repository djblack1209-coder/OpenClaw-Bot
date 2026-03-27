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
    def test_search_by_category(self, mock_now, mem):
        """按分类获取记忆，只返回对应分类的条目"""
        # 存入不同分类的记忆
        mem.remember("task_a", "写报告", category="work")
        mem.remember("task_b", "写代码", category="work")
        mem.remember("hobby_a", "打篮球", category="hobby")

        # 按 work 分类获取
        work_items = mem.get_by_category("work")
        assert len(work_items) == 2
        work_keys = {item["key"] for item in work_items}
        assert work_keys == {"task_a", "task_b"}

        # 按 hobby 分类获取
        hobby_items = mem.get_by_category("hobby")
        assert len(hobby_items) == 1
        assert hobby_items[0]["key"] == "hobby_a"

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

    def test_importance_decay(self, mem):
        """重要性衰减：高重要性记忆超过 1 天未访问后，重要性应下降"""
        ten_days_ago = FIXED_NOW - timedelta(days=10)

        # 第一步：用 10 天前的时间存入高重要性记忆
        with patch("src.shared_memory.now_et", return_value=ten_days_ago):
            mem.remember("decay_test", "some value", importance=5)

        # 第二步：用"现在"的时间执行衰减
        with patch("src.shared_memory.now_et", return_value=FIXED_NOW):
            mem.decay_importance()
            result = mem.recall("decay_test")

        assert result["success"] is True
        # 衰减公式: decay = 0.05 × 10天 × 1.0 = 0.5
        # new_importance = max(1, int(5 - 0.5)) = 4
        assert result["importance"] == 4
        assert result["importance"] < 5

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
