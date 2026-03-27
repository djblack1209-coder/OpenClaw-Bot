"""
ClawBot 行情缓存 v1.0
减少 yfinance API 调用，为 PositionMonitor / Rebalancer 提供低延迟报价

核心功能：
1. 内存缓存：TTL 过期机制，默认60秒
2. 批量刷新：一次性更新所有监控标的
3. 回退机制：缓存过期时仍返回旧数据（标记 stale）
4. 统计：命中率、API调用次数
"""
import asyncio
import logging
import time as _time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CachedQuote:
    """缓存的报价"""
    symbol: str
    price: float
    timestamp: float  # time.time()
    source: str = "yfinance"  # yfinance / manual / stale


@dataclass
class CacheConfig:
    """缓存配置"""
    ttl_seconds: float = 60.0       # 缓存有效期
    stale_ttl_seconds: float = 300.0  # 过期数据保留时间
    refresh_interval: float = 30.0   # 自动刷新间隔（秒）
    max_batch_size: int = 20         # 单次批量请求上限


class QuoteCache:
    """行情缓存"""

    def __init__(self, config: CacheConfig = None, get_quote_func=None):
        self.config = config or CacheConfig()
        self._get_quote_func = get_quote_func  # async (symbol) -> {"price": float}
        self._cache: Dict[str, CachedQuote] = {}
        self._watch_symbols: Set[str] = set()
        self._running = False
        self._task = None

        # 统计
        self._hits = 0
        self._misses = 0
        self._api_calls = 0
        self._errors = 0

    def set_quote_func(self, func):
        """设置报价获取函数"""
        self._get_quote_func = func

    def watch(self, symbols: List[str]):
        """添加监控标的"""
        for s in symbols:
            self._watch_symbols.add(s.upper())

    def unwatch(self, symbol: str):
        """移除监控标的"""
        self._watch_symbols.discard(symbol.upper())

    def get(self, symbol: str) -> Optional[float]:
        """获取缓存报价（同步，用于非异步上下文）"""
        symbol = symbol.upper()
        entry = self._cache.get(symbol)
        if entry is None:
            self._misses += 1
            return None

        age = _time.time() - entry.timestamp
        if age <= self.config.ttl_seconds:
            self._hits += 1
            return entry.price
        elif age <= self.config.stale_ttl_seconds:
            self._hits += 1
            return entry.price  # Stale but usable
        else:
            self._misses += 1
            return None

    async def get_async(self, symbol: str) -> Optional[float]:
        """获取报价（异步，缓存未命中时自动拉取）"""
        symbol = symbol.upper()
        price = self.get(symbol)
        if price is not None:
            return price

        # Cache miss -> fetch
        if self._get_quote_func:
            try:
                self._api_calls += 1
                result = await self._get_quote_func(symbol)
                if isinstance(result, dict) and "price" in result:
                    p = float(result["price"])
                    self._cache[symbol] = CachedQuote(
                        symbol=symbol, price=p,
                        timestamp=_time.time(), source="yfinance",
                    )
                    return p
            except Exception as e:
                self._errors += 1
                logger.debug("[QuoteCache] %s 获取失败: %s", symbol, e)

        return None

    def get_all(self) -> Dict[str, float]:
        """获取所有缓存报价"""
        now = _time.time()
        result = {}
        for sym, entry in self._cache.items():
            age = now - entry.timestamp
            if age <= self.config.stale_ttl_seconds:
                result[sym] = entry.price
        return result

    def put(self, symbol: str, price: float, source: str = "manual"):
        """手动写入缓存"""
        symbol = symbol.upper()
        self._cache[symbol] = CachedQuote(
            symbol=symbol, price=price,
            timestamp=_time.time(), source=source,
        )

    async def refresh(self, symbols: List[str] = None):
        """批量刷新报价"""
        if not self._get_quote_func:
            return

        targets = sorted(s.upper() for s in (symbols or list(self._watch_symbols)))
        if not targets:
            return

        # 分批请求
        for i in range(0, len(targets), self.config.max_batch_size):
            batch = targets[i:i + self.config.max_batch_size]
            tasks = []
            for sym in batch:
                tasks.append(self._fetch_one(sym))
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_one(self, symbol: str):
        """获取单个标的报价"""
        try:
            self._api_calls += 1
            result = await self._get_quote_func(symbol)
            if isinstance(result, dict) and "price" in result:
                self._cache[symbol] = CachedQuote(
                    symbol=symbol,
                    price=float(result["price"]),
                    timestamp=_time.time(),
                    source="yfinance",
                )
        except Exception as e:
            self._errors += 1
            logger.debug("[QuoteCache] %s 刷新失败: %s", symbol, e)

    async def start(self):
        """启动自动刷新循环"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._refresh_loop())
        def _quote_refresh_done(t):
            if not t.cancelled() and t.exception():
                logger.warning("[QuoteCache] 刷新循环崩溃: %s", t.exception())
        self._task.add_done_callback(_quote_refresh_done)
        logger.info("[QuoteCache] 自动刷新已启动 (间隔%.0fs)", self.config.refresh_interval)

    async def stop(self):
        """停止自动刷新"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError as e:  # noqa: F841
                pass
        logger.info("[QuoteCache] 已停止")

    async def _refresh_loop(self):
        """自动刷新循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config.refresh_interval)
                if self._watch_symbols:
                    await self.refresh()
            except asyncio.CancelledError as e:  # noqa: F841
                break
            except Exception as e:
                logger.error("[QuoteCache] 刷新循环错误: %s", e)

    def format_status(self) -> str:
        """格式化状态"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        fresh = 0
        stale = 0
        now = _time.time()
        for entry in self._cache.values():
            age = now - entry.timestamp
            if age <= self.config.ttl_seconds:
                fresh += 1
            elif age <= self.config.stale_ttl_seconds:
                stale += 1

        lines = [
            "-- 行情缓存 --",
            "监控标的: %d" % len(self._watch_symbols),
            "缓存条目: %d (新鲜%d / 过期%d)" % (len(self._cache), fresh, stale),
            "命中率: %.1f%% (%d/%d)" % (hit_rate, self._hits, total),
            "API调用: %d (错误%d)" % (self._api_calls, self._errors),
            "自动刷新: %s" % ("运行中" if self._running else "停止"),
        ]
        return "\n".join(lines)


# 全局实例
quote_cache = QuoteCache()
