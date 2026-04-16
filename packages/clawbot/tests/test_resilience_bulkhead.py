"""
Bulkhead 并发隔离舱 — 单元测试

测试目标: src/resilience.py 中的 Bulkhead 模块
覆盖范围:
  - 基本 acquire/release 语义
  - 并发限制是否生效
  - 超时溢出行为（超过 max_concurrent 时）
  - 不同下游类别的独立隔离
  - 动态配置 configure_bulkhead
  - 统计信息 get_bulkhead_stats
  - 异常传播（yield 内部抛异常时 semaphore 仍能释放）
"""

import asyncio
import sys
import os
import time

import pytest

# 确保 src 可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.resilience import (
    bulkhead,
    configure_bulkhead,
    get_bulkhead_stats,
    _bulkhead_semaphores,
    _bulkhead_stats,
    _BULKHEAD_LIMITS,
    _bulkhead_lock,
)


# ══════════════════════════════════════════════════════
# 辅助工具
# ══════════════════════════════════════════════════════

# 用一个唯一前缀避免测试之间的状态污染
_TEST_PREFIX = "__test_bh_"
_counter = 0


def _fresh_service() -> str:
    """每次调用返回一个全新的服务名，避免测试间共享 semaphore"""
    global _counter
    _counter += 1
    return f"{_TEST_PREFIX}{_counter}"


def _cleanup_service(service: str):
    """清理测试用的 bulkhead 状态"""
    with _bulkhead_lock:
        _bulkhead_semaphores.pop(service, None)
        _bulkhead_stats.pop(service, None)
        _BULKHEAD_LIMITS.pop(service, None)


# ══════════════════════════════════════════════════════
# 基础功能测试
# ══════════════════════════════════════════════════════


class TestBulkheadBasic:
    """Bulkhead 基本 acquire/release 行为"""

    async def test_单次进入和退出(self):
        """单个任务能正常进入隔离舱并退出"""
        svc = _fresh_service()
        configure_bulkhead(svc, 5)
        try:
            async with bulkhead(svc):
                pass  # 正常进入和退出
            # 没有异常就算通过
        finally:
            _cleanup_service(svc)

    async def test_进入后可以执行异步操作(self):
        """隔离舱内可以正常执行 await 操作"""
        svc = _fresh_service()
        configure_bulkhead(svc, 5)
        result = None
        try:
            async with bulkhead(svc):
                await asyncio.sleep(0.01)
                result = "完成"
            assert result == "完成"
        finally:
            _cleanup_service(svc)

    async def test_退出后释放信号量(self):
        """退出隔离舱后 semaphore 应该被释放"""
        svc = _fresh_service()
        configure_bulkhead(svc, 1)
        try:
            # 第一次进入
            async with bulkhead(svc):
                pass
            # 第二次进入 — 如果没释放，这里会超时
            async with bulkhead(svc, timeout=1.0):
                pass
        finally:
            _cleanup_service(svc)

    async def test_返回值透传(self):
        """隔离舱不影响内部代码的返回值"""
        svc = _fresh_service()
        configure_bulkhead(svc, 5)
        try:
            result = []
            async with bulkhead(svc):
                result.append(42)
            assert result == [42]
        finally:
            _cleanup_service(svc)


# ══════════════════════════════════════════════════════
# 并发限制测试
# ══════════════════════════════════════════════════════


class TestBulkheadConcurrency:
    """验证并发限制是否真正生效"""

    async def test_并发数不超过限制(self):
        """同时运行的任务数不应超过 max_concurrent"""
        svc = _fresh_service()
        max_concurrent = 3
        configure_bulkhead(svc, max_concurrent)

        # 记录同时在舱内的任务数
        current_count = 0
        peak_count = 0
        lock = asyncio.Lock()

        async def worker():
            nonlocal current_count, peak_count
            async with bulkhead(svc, timeout=10.0):
                async with lock:
                    current_count += 1
                    if current_count > peak_count:
                        peak_count = current_count
                # 模拟工作
                await asyncio.sleep(0.05)
                async with lock:
                    current_count -= 1

        try:
            # 启动 10 个并发任务
            tasks = [asyncio.create_task(worker()) for _ in range(10)]
            await asyncio.gather(*tasks)

            # 峰值并发不应超过限制
            assert peak_count <= max_concurrent, f"峰值并发 {peak_count} 超过了限制 {max_concurrent}"
            # 至少应该达到过满载（10个任务抢3个槽位，一定会满）
            assert peak_count == max_concurrent, f"峰值并发 {peak_count} 应该达到限制 {max_concurrent}"
        finally:
            _cleanup_service(svc)

    async def test_限制为1时串行执行(self):
        """max_concurrent=1 时任务应该串行执行"""
        svc = _fresh_service()
        configure_bulkhead(svc, 1)

        execution_order = []
        current_count = 0
        max_seen = 0
        lock = asyncio.Lock()

        async def worker(task_id: int):
            nonlocal current_count, max_seen
            async with bulkhead(svc, timeout=10.0):
                async with lock:
                    current_count += 1
                    if current_count > max_seen:
                        max_seen = current_count
                execution_order.append(f"start_{task_id}")
                await asyncio.sleep(0.02)
                execution_order.append(f"end_{task_id}")
                async with lock:
                    current_count -= 1

        try:
            tasks = [asyncio.create_task(worker(i)) for i in range(5)]
            await asyncio.gather(*tasks)

            # 同时在舱内的最多只有 1 个
            assert max_seen == 1, f"max_concurrent=1 但观测到 {max_seen} 个并发"
        finally:
            _cleanup_service(svc)

    async def test_所有任务最终都能完成(self):
        """即使并发受限，排队的任务最终都应该完成"""
        svc = _fresh_service()
        configure_bulkhead(svc, 2)
        completed = []

        async def worker(task_id: int):
            async with bulkhead(svc, timeout=10.0):
                await asyncio.sleep(0.01)
                completed.append(task_id)

        try:
            tasks = [asyncio.create_task(worker(i)) for i in range(8)]
            await asyncio.gather(*tasks)
            # 全部 8 个任务都应该完成
            assert len(completed) == 8
            assert set(completed) == set(range(8))
        finally:
            _cleanup_service(svc)


# ══════════════════════════════════════════════════════
# 溢出/超时行为测试
# ══════════════════════════════════════════════════════


class TestBulkheadOverflow:
    """当并发超过限制时的溢出行为"""

    async def test_超时抛出TimeoutError(self):
        """隔离舱满且等待超时时应抛出 asyncio.TimeoutError"""
        svc = _fresh_service()
        configure_bulkhead(svc, 1)

        entered = asyncio.Event()

        async def blocker():
            """占住唯一的槽位"""
            async with bulkhead(svc, timeout=10.0):
                entered.set()
                # 长时间占住
                await asyncio.sleep(5.0)

        try:
            # 启动阻塞任务
            blocker_task = asyncio.create_task(blocker())
            await entered.wait()  # 等阻塞任务进入隔离舱

            # 第二个任务应该超时
            with pytest.raises(asyncio.TimeoutError):
                async with bulkhead(svc, timeout=0.1):
                    pass  # 不应该到达这里

            blocker_task.cancel()
            try:
                await blocker_task
            except asyncio.CancelledError:
                pass
        finally:
            _cleanup_service(svc)

    async def test_超时后统计rejected递增(self):
        """超时被拒绝时 rejected 计数应该增加"""
        svc = _fresh_service()
        configure_bulkhead(svc, 1)

        entered = asyncio.Event()

        async def blocker():
            async with bulkhead(svc, timeout=10.0):
                entered.set()
                await asyncio.sleep(5.0)

        try:
            blocker_task = asyncio.create_task(blocker())
            await entered.wait()

            # 触发超时
            with pytest.raises(asyncio.TimeoutError):
                async with bulkhead(svc, timeout=0.1):
                    pass

            stats = get_bulkhead_stats()
            assert svc in stats
            assert stats[svc]["rejected"] >= 1, "超时后 rejected 应该 >= 1"

            blocker_task.cancel()
            try:
                await blocker_task
            except asyncio.CancelledError:
                pass
        finally:
            _cleanup_service(svc)

    async def test_短超时不影响后续任务(self):
        """一个任务超时不应影响后续任务正常进入"""
        svc = _fresh_service()
        configure_bulkhead(svc, 1)

        entered = asyncio.Event()

        async def blocker():
            async with bulkhead(svc, timeout=10.0):
                entered.set()
                await asyncio.sleep(0.3)

        try:
            blocker_task = asyncio.create_task(blocker())
            await entered.wait()

            # 这个会超时
            with pytest.raises(asyncio.TimeoutError):
                async with bulkhead(svc, timeout=0.05):
                    pass

            # 等阻塞任务结束
            await blocker_task

            # 现在应该能正常进入
            async with bulkhead(svc, timeout=1.0):
                pass  # 成功进入，没有异常
        finally:
            _cleanup_service(svc)


# ══════════════════════════════════════════════════════
# 不同下游类别的隔离测试
# ══════════════════════════════════════════════════════


class TestBulkheadIsolation:
    """不同服务类别之间的隔离性"""

    async def test_不同服务使用独立信号量(self):
        """llm 和 browser 应该有各自独立的并发池"""
        svc_a = _fresh_service()
        svc_b = _fresh_service()
        configure_bulkhead(svc_a, 1)
        configure_bulkhead(svc_b, 1)

        # 两个不同服务应该能同时进入
        results = []

        async def worker_a():
            async with bulkhead(svc_a, timeout=2.0):
                results.append("a_start")
                await asyncio.sleep(0.1)
                results.append("a_end")

        async def worker_b():
            async with bulkhead(svc_b, timeout=2.0):
                results.append("b_start")
                await asyncio.sleep(0.1)
                results.append("b_end")

        try:
            await asyncio.gather(worker_a(), worker_b())
            # 两个都应该完成
            assert "a_start" in results
            assert "a_end" in results
            assert "b_start" in results
            assert "b_end" in results
        finally:
            _cleanup_service(svc_a)
            _cleanup_service(svc_b)

    async def test_一个服务满不影响另一个(self):
        """服务 A 满载时，服务 B 仍然可以正常进入"""
        svc_a = _fresh_service()
        svc_b = _fresh_service()
        configure_bulkhead(svc_a, 1)
        configure_bulkhead(svc_b, 1)

        a_entered = asyncio.Event()
        b_result = None

        async def blocker_a():
            async with bulkhead(svc_a, timeout=10.0):
                a_entered.set()
                await asyncio.sleep(5.0)

        async def worker_b():
            nonlocal b_result
            async with bulkhead(svc_b, timeout=2.0):
                b_result = "成功"

        try:
            blocker_task = asyncio.create_task(blocker_a())
            await a_entered.wait()

            # 服务 A 已满，但服务 B 应该不受影响
            await worker_b()
            assert b_result == "成功", "服务 A 满载不应阻塞服务 B"

            blocker_task.cancel()
            try:
                await blocker_task
            except asyncio.CancelledError:
                pass
        finally:
            _cleanup_service(svc_a)
            _cleanup_service(svc_b)

    async def test_默认类别有预设限制(self):
        """预定义的服务类别应该有正确的默认限制"""
        # 检查默认配置（不修改，只读取）
        assert _BULKHEAD_LIMITS.get("llm") == 10
        assert _BULKHEAD_LIMITS.get("browser") == 3
        assert _BULKHEAD_LIMITS.get("api") == 20
        assert _BULKHEAD_LIMITS.get("crawler") == 5
        assert _BULKHEAD_LIMITS.get("trading") == 5
        assert _BULKHEAD_LIMITS.get("generic") == 15


# ══════════════════════════════════════════════════════
# 动态配置测试
# ══════════════════════════════════════════════════════


class TestBulkheadConfigure:
    """configure_bulkhead 动态配置"""

    async def test_配置新服务(self):
        """可以为新服务配置并发限制"""
        svc = _fresh_service()
        try:
            configure_bulkhead(svc, 7)
            assert _BULKHEAD_LIMITS[svc] == 7

            # 应该能正常使用
            async with bulkhead(svc, timeout=1.0):
                pass
        finally:
            _cleanup_service(svc)

    async def test_重新配置清除旧缓存(self):
        """重新配置后旧的 semaphore 应该被清除"""
        svc = _fresh_service()
        try:
            configure_bulkhead(svc, 2)

            # 先使用一次，触发 semaphore 创建
            async with bulkhead(svc, timeout=1.0):
                pass

            assert svc in _bulkhead_semaphores

            # 重新配置
            configure_bulkhead(svc, 5)

            # 旧的 semaphore 应该被清除
            assert svc not in _bulkhead_semaphores

            # 新配置应该生效
            assert _BULKHEAD_LIMITS[svc] == 5
        finally:
            _cleanup_service(svc)

    async def test_重新配置后新限制生效(self):
        """重新配置后新的并发限制应该生效"""
        svc = _fresh_service()
        try:
            # 初始限制 1
            configure_bulkhead(svc, 1)

            current_count = 0
            peak_count = 0
            lock = asyncio.Lock()

            async def worker():
                nonlocal current_count, peak_count
                async with bulkhead(svc, timeout=5.0):
                    async with lock:
                        current_count += 1
                        if current_count > peak_count:
                            peak_count = current_count
                    await asyncio.sleep(0.03)
                    async with lock:
                        current_count -= 1

            # 限制为 1 时跑 3 个任务
            tasks = [asyncio.create_task(worker()) for _ in range(3)]
            await asyncio.gather(*tasks)
            assert peak_count == 1

            # 提高限制到 3
            configure_bulkhead(svc, 3)
            peak_count = 0
            current_count = 0

            tasks = [asyncio.create_task(worker()) for _ in range(6)]
            await asyncio.gather(*tasks)
            assert peak_count <= 3
        finally:
            _cleanup_service(svc)


# ══════════════════════════════════════════════════════
# 统计信息测试
# ══════════════════════════════════════════════════════


class TestBulkheadStats:
    """get_bulkhead_stats 统计信息"""

    async def test_acquired计数递增(self):
        """每次成功进入隔离舱，acquired 应该递增"""
        svc = _fresh_service()
        configure_bulkhead(svc, 5)
        try:
            for _ in range(3):
                async with bulkhead(svc, timeout=1.0):
                    pass

            stats = get_bulkhead_stats()
            assert svc in stats
            assert stats[svc]["acquired"] == 3
        finally:
            _cleanup_service(svc)

    async def test_peak记录峰值(self):
        """peak 应该记录历史最高并发数"""
        svc = _fresh_service()
        configure_bulkhead(svc, 5)

        try:

            async def worker():
                async with bulkhead(svc, timeout=5.0):
                    await asyncio.sleep(0.05)

            # 同时启动 4 个任务
            tasks = [asyncio.create_task(worker()) for _ in range(4)]
            await asyncio.gather(*tasks)

            stats = get_bulkhead_stats()
            assert svc in stats
            # 峰值应该 > 0（至少有过并发）
            assert stats[svc]["peak"] > 0
        finally:
            _cleanup_service(svc)

    async def test_available和in_use正确(self):
        """进入隔离舱时 available 减少，in_use 增加"""
        svc = _fresh_service()
        configure_bulkhead(svc, 3)

        inside_event = asyncio.Event()
        release_event = asyncio.Event()

        async def holder():
            async with bulkhead(svc, timeout=5.0):
                inside_event.set()
                await release_event.wait()

        try:
            task = asyncio.create_task(holder())
            await inside_event.wait()

            stats = get_bulkhead_stats()
            assert svc in stats
            # 1 个任务在舱内
            assert stats[svc]["in_use"] == 1
            assert stats[svc]["available"] == 2  # 3 - 1

            release_event.set()
            await task
        finally:
            _cleanup_service(svc)

    async def test_未使用的服务不在统计中(self):
        """从未使用过的服务不应出现在统计信息中"""
        svc = _fresh_service()
        stats = get_bulkhead_stats()
        assert svc not in stats


# ══════════════════════════════════════════════════════
# 异常处理测试
# ══════════════════════════════════════════════════════


class TestBulkheadExceptionHandling:
    """隔离舱内异常时的行为"""

    async def test_内部异常正常传播(self):
        """隔离舱内抛出的异常应该正常传播到外部"""
        svc = _fresh_service()
        configure_bulkhead(svc, 5)
        try:
            with pytest.raises(ValueError, match="测试异常"):
                async with bulkhead(svc, timeout=1.0):
                    raise ValueError("测试异常")
        finally:
            _cleanup_service(svc)

    async def test_异常后信号量仍然释放(self):
        """即使内部抛异常，semaphore 也应该被释放"""
        svc = _fresh_service()
        configure_bulkhead(svc, 1)
        try:
            # 第一次进入并抛异常
            with pytest.raises(RuntimeError):
                async with bulkhead(svc, timeout=1.0):
                    raise RuntimeError("模拟故障")

            # 如果 semaphore 没释放，这里会超时
            async with bulkhead(svc, timeout=0.5):
                pass  # 能进来说明释放成功
        finally:
            _cleanup_service(svc)

    async def test_连续异常不泄漏信号量(self):
        """多次异常后 semaphore 不应泄漏"""
        svc = _fresh_service()
        configure_bulkhead(svc, 1)
        try:
            for i in range(5):
                with pytest.raises(Exception):
                    async with bulkhead(svc, timeout=1.0):
                        raise Exception(f"第 {i} 次故障")

            # 5 次异常后仍然能正常进入
            async with bulkhead(svc, timeout=0.5):
                pass
        finally:
            _cleanup_service(svc)

    async def test_取消任务时释放信号量(self):
        """任务被 cancel 时 semaphore 也应该释放"""
        svc = _fresh_service()
        configure_bulkhead(svc, 1)

        entered = asyncio.Event()

        async def cancellable_worker():
            async with bulkhead(svc, timeout=5.0):
                entered.set()
                await asyncio.sleep(10.0)  # 会被取消

        try:
            task = asyncio.create_task(cancellable_worker())
            await entered.wait()

            # 取消任务
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # 等一小会让 finally 块执行完
            await asyncio.sleep(0.05)

            # semaphore 应该已释放
            async with bulkhead(svc, timeout=0.5):
                pass
        finally:
            _cleanup_service(svc)


# ══════════════════════════════════════════════════════
# 未知服务回退测试
# ══════════════════════════════════════════════════════


class TestBulkheadFallback:
    """未配置的服务应该回退到 generic 默认值"""

    async def test_未知服务使用generic限制(self):
        """未在 _BULKHEAD_LIMITS 中配置的服务应使用 generic 的默认值"""
        svc = _fresh_service()
        # 不调用 configure_bulkhead，直接使用
        try:
            async with bulkhead(svc, timeout=1.0):
                pass

            stats = get_bulkhead_stats()
            assert svc in stats
            # generic 默认限制是 15
            assert stats[svc]["limit"] == 15
        finally:
            _cleanup_service(svc)
