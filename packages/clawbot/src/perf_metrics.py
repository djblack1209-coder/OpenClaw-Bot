"""
性能度量模块 — 线程安全的性能追踪器 + 装饰器

提供:
  - PerfTracker: 环形缓冲区存储指标，自动计算统计数据
  - perf_timer: 装饰器，自动记录函数执行时间
  - get_tracker: 全局单例访问器

用法:
    from src.perf_metrics import perf_timer, get_tracker

    @perf_timer("my.operation")
    async def do_something():
        ...

    # 手动记录
    tracker = get_tracker()
    tracker.record("custom.metric", 1.23)
    logger.info(tracker.format_report())
"""

import asyncio
import functools
import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

logger = logging.getLogger(__name__)

# 每个指标最多保留的记录数（环形缓冲区大小）
_MAX_RECORDS_PER_METRIC = 1000

# 超过此阈值（秒）的调用会触发警告日志
_SLOW_THRESHOLD_SECONDS = 5.0


class PerfTracker:
    """线程安全的性能追踪器，使用环形缓冲区防止内存泄漏"""

    def __init__(self, max_records: int = _MAX_RECORDS_PER_METRIC):
        self._max_records = max_records
        # 指标名 → deque(maxlen=max_records) 存储耗时记录
        self._data: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._max_records)
        )
        self._lock = threading.Lock()

    def record(self, metric_name: str, duration_seconds: float) -> None:
        """记录一次耗时数据

        Args:
            metric_name: 指标名称（如 "brain.process_message"）
            duration_seconds: 耗时（秒）
        """
        with self._lock:
            self._data[metric_name].append(duration_seconds)

    def get_stats(self, metric_name: str) -> dict:
        """获取指定指标的统计数据

        Returns:
            包含 count, avg, p50, p95, max, min 的字典；
            指标不存在时返回 count=0 的空统计
        """
        with self._lock:
            records = list(self._data.get(metric_name, []))

        if not records:
            return {"count": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0, "min": 0.0}

        sorted_records = sorted(records)
        count = len(sorted_records)
        avg = sum(sorted_records) / count
        p50 = self._percentile(sorted_records, 50)
        p95 = self._percentile(sorted_records, 95)

        return {
            "count": count,
            "avg": round(avg, 4),
            "p50": round(p50, 4),
            "p95": round(p95, 4),
            "max": round(max(sorted_records), 4),
            "min": round(min(sorted_records), 4),
        }

    def get_all_stats(self) -> dict[str, dict]:
        """获取所有指标的统计数据"""
        with self._lock:
            metric_names = list(self._data.keys())
        return {name: self.get_stats(name) for name in metric_names}

    def format_report(self) -> str:
        """生成格式化的中文性能报告"""
        all_stats = self.get_all_stats()
        if not all_stats:
            return "📊 性能报告：暂无数据"

        lines = ["📊 性能度量报告", "=" * 40]
        for name, stats in sorted(all_stats.items()):
            lines.append(f"\n指标: {name}")
            lines.append(f"  调用次数: {stats['count']}")
            lines.append(f"  平均耗时: {stats['avg']:.4f}s")
            lines.append(f"  中位数(P50): {stats['p50']:.4f}s")
            lines.append(f"  P95: {stats['p95']:.4f}s")
            lines.append(f"  最大值: {stats['max']:.4f}s")
            lines.append(f"  最小值: {stats['min']:.4f}s")
        lines.append("\n" + "=" * 40)
        return "\n".join(lines)

    @staticmethod
    def _percentile(sorted_data: list, pct: float) -> float:
        """计算百分位数（线性插值法）"""
        n = len(sorted_data)
        if n == 1:
            return sorted_data[0]
        # 使用 statistics 模块的分位数计算（Python 3.8+）
        try:
            return statistics.quantiles(sorted_data, n=100, method="inclusive")[int(pct) - 1]
        except (statistics.StatisticsError, IndexError):
            # 数据太少时回退到简单索引
            idx = int(pct / 100 * (n - 1))
            return sorted_data[min(idx, n - 1)]


# ── 全局单例 ──────────────────────────────────────────

_global_tracker: PerfTracker | None = None
_tracker_lock = threading.Lock()


def get_tracker() -> PerfTracker:
    """获取全局 PerfTracker 单例"""
    global _global_tracker
    if _global_tracker is None:
        with _tracker_lock:
            if _global_tracker is None:
                _global_tracker = PerfTracker()
    return _global_tracker


# ── perf_timer 装饰器 ──────────────────────────────────


def perf_timer(
    metric_name: str,
    tracker: PerfTracker | None = None,
) -> Callable:
    """性能计时装饰器，自动记录函数执行时间

    支持同步和异步函数。耗时超过 5 秒时记录警告日志。

    Args:
        metric_name: 指标名称（如 "brain.process_message"）
        tracker: 可选的 PerfTracker 实例，默认使用全局单例

    用法:
        @perf_timer("my.operation")
        async def do_something():
            ...
    """

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                _tracker = tracker or get_tracker()
                start = time.monotonic()
                try:
                    return await func(*args, **kwargs)
                finally:
                    elapsed = time.monotonic() - start
                    _tracker.record(metric_name, elapsed)
                    if elapsed > _SLOW_THRESHOLD_SECONDS:
                        logger.warning(
                            "慢调用告警: %s 耗时 %.2f 秒 (阈值 %.1f 秒)",
                            metric_name,
                            elapsed,
                            _SLOW_THRESHOLD_SECONDS,
                        )

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                _tracker = tracker or get_tracker()
                start = time.monotonic()
                try:
                    return func(*args, **kwargs)
                finally:
                    elapsed = time.monotonic() - start
                    _tracker.record(metric_name, elapsed)
                    if elapsed > _SLOW_THRESHOLD_SECONDS:
                        logger.warning(
                            "慢调用告警: %s 耗时 %.2f 秒 (阈值 %.1f 秒)",
                            metric_name,
                            elapsed,
                            _SLOW_THRESHOLD_SECONDS,
                        )

            return sync_wrapper

    return decorator
