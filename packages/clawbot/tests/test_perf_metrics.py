"""
PerfTracker + perf_timer 装饰器的单元测试
"""

import asyncio
import pytest

from src.perf_metrics import PerfTracker, perf_timer, get_tracker


class TestPerfTracker:
    """PerfTracker 核心功能测试"""

    def test_record_and_get_stats(self):
        """记录 3 个值后验证统计数据正确"""
        tracker = PerfTracker()
        tracker.record("test.metric", 1.0)
        tracker.record("test.metric", 2.0)
        tracker.record("test.metric", 3.0)

        stats = tracker.get_stats("test.metric")
        assert stats["count"] == 3
        assert stats["avg"] == 2.0
        assert stats["min"] == 1.0
        assert stats["max"] == 3.0
        # P50 应该是中位数 2.0
        assert stats["p50"] == 2.0

    def test_get_all_stats(self):
        """记录多个指标，验证 get_all_stats 返回全部"""
        tracker = PerfTracker()
        tracker.record("metric.a", 1.0)
        tracker.record("metric.a", 2.0)
        tracker.record("metric.b", 3.0)

        all_stats = tracker.get_all_stats()
        assert "metric.a" in all_stats
        assert "metric.b" in all_stats
        assert all_stats["metric.a"]["count"] == 2
        assert all_stats["metric.b"]["count"] == 1

    def test_empty_stats(self):
        """不存在的指标返回 count=0"""
        tracker = PerfTracker()
        stats = tracker.get_stats("nonexistent")
        assert stats["count"] == 0
        assert stats["avg"] == 0.0
        assert stats["p50"] == 0.0
        assert stats["p95"] == 0.0
        assert stats["max"] == 0.0
        assert stats["min"] == 0.0

    def test_ring_buffer_limit(self):
        """验证环形缓冲区不超过最大记录数"""
        tracker = PerfTracker(max_records=10)
        for i in range(20):
            tracker.record("buffer.test", float(i))
        stats = tracker.get_stats("buffer.test")
        # 最多保留 10 条
        assert stats["count"] == 10
        # 保留的是最后 10 条（10~19）
        assert stats["min"] == 10.0
        assert stats["max"] == 19.0


class TestPerfTimer:
    """perf_timer 装饰器测试"""

    @pytest.mark.asyncio
    async def test_async_timer_records_duration(self):
        """异步函数装饰器正确记录耗时"""
        tracker = PerfTracker()

        @perf_timer("async.test", tracker=tracker)
        async def slow_func():
            await asyncio.sleep(0.1)
            return "done"

        result = await slow_func()
        assert result == "done"

        stats = tracker.get_stats("async.test")
        assert stats["count"] == 1
        # sleep(0.1) 应该至少耗时 0.09 秒
        assert stats["avg"] >= 0.09

    def test_sync_timer_records_duration(self):
        """同步函数装饰器正确记录耗时"""
        tracker = PerfTracker()

        @perf_timer("sync.test", tracker=tracker)
        def fast_func():
            return 42

        result = fast_func()
        assert result == 42

        stats = tracker.get_stats("sync.test")
        assert stats["count"] == 1
        assert stats["avg"] >= 0.0

    def test_timer_preserves_exceptions(self):
        """装饰器不吞异常，且异常时也记录耗时"""
        tracker = PerfTracker()

        @perf_timer("error.test", tracker=tracker)
        def failing_func():
            raise ValueError("测试异常")

        with pytest.raises(ValueError, match="测试异常"):
            failing_func()

        # 即使抛异常，也应记录了耗时
        stats = tracker.get_stats("error.test")
        assert stats["count"] == 1


class TestFormatReport:
    """格式化报告测试"""

    def test_format_report(self):
        """报告包含中文文本和指标名"""
        tracker = PerfTracker()
        tracker.record("brain.process", 1.5)
        tracker.record("brain.process", 2.5)
        tracker.record("llm.call", 0.3)

        report = tracker.format_report()
        # 验证包含中文文本
        assert "性能" in report
        assert "调用次数" in report
        assert "平均耗时" in report
        # 验证包含指标名
        assert "brain.process" in report
        assert "llm.call" in report

    def test_format_report_empty(self):
        """空报告也有中文标题"""
        tracker = PerfTracker()
        report = tracker.format_report()
        assert "暂无数据" in report


class TestGlobalSingleton:
    """全局单例测试"""

    def test_get_tracker_returns_same_instance(self):
        """get_tracker 返回同一个实例"""
        t1 = get_tracker()
        t2 = get_tracker()
        assert t1 is t2
