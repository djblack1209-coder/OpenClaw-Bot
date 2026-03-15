"""
Tests for QuoteCache - caching, TTL, refresh, statistics.
"""
import pytest
import time as _time
from unittest.mock import AsyncMock

from src.quote_cache import QuoteCache, CacheConfig, CachedQuote


@pytest.fixture
def mock_quote_func():
    f = AsyncMock()
    f.return_value = {"price": 150.0}
    return f


@pytest.fixture
def cache(mock_quote_func):
    return QuoteCache(
        config=CacheConfig(ttl_seconds=5, stale_ttl_seconds=30, refresh_interval=10),
        get_quote_func=mock_quote_func,
    )


class TestGet:
    """Synchronous get from cache."""

    def test_miss_returns_none(self, cache):
        assert cache.get("AAPL") is None

    def test_hit_after_put(self, cache):
        cache.put("AAPL", 150.0)
        assert cache.get("AAPL") == 150.0

    def test_case_insensitive(self, cache):
        cache.put("aapl", 150.0)
        assert cache.get("AAPL") == 150.0

    def test_expired_returns_stale(self, cache):
        cache._cache["AAPL"] = CachedQuote(
            symbol="AAPL", price=150.0,
            timestamp=_time.time() - 10,  # 10s old, TTL=5s
        )
        # Still within stale_ttl (30s), so returns price
        assert cache.get("AAPL") == 150.0

    def test_fully_expired_returns_none(self, cache):
        cache._cache["AAPL"] = CachedQuote(
            symbol="AAPL", price=150.0,
            timestamp=_time.time() - 60,  # 60s old, stale_ttl=30s
        )
        assert cache.get("AAPL") is None


class TestGetAsync:
    """Async get with auto-fetch on miss."""

    @pytest.mark.asyncio
    async def test_cache_miss_fetches(self, cache, mock_quote_func):
        price = await cache.get_async("AAPL")
        assert price == 150.0
        mock_quote_func.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_cache_hit_no_fetch(self, cache, mock_quote_func):
        cache.put("AAPL", 155.0)
        price = await cache.get_async("AAPL")
        assert price == 155.0
        mock_quote_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_none(self, cache, mock_quote_func):
        mock_quote_func.side_effect = ConnectionError("network down")
        price = await cache.get_async("AAPL")
        assert price is None
        assert cache._errors == 1

    @pytest.mark.asyncio
    async def test_fetch_bad_response_returns_none(self, cache, mock_quote_func):
        mock_quote_func.return_value = {"error": "not found"}
        price = await cache.get_async("AAPL")
        assert price is None


class TestPut:

    def test_put_and_get(self, cache):
        cache.put("MSFT", 420.0, source="manual")
        assert cache.get("MSFT") == 420.0

    def test_put_overwrites(self, cache):
        cache.put("AAPL", 150.0)
        cache.put("AAPL", 155.0)
        assert cache.get("AAPL") == 155.0


class TestGetAll:

    def test_get_all_returns_fresh(self, cache):
        cache.put("AAPL", 150.0)
        cache.put("MSFT", 420.0)
        all_quotes = cache.get_all()
        assert all_quotes == {"AAPL": 150.0, "MSFT": 420.0}

    def test_get_all_excludes_fully_expired(self, cache):
        cache.put("AAPL", 150.0)
        cache._cache["OLD"] = CachedQuote(
            symbol="OLD", price=10.0,
            timestamp=_time.time() - 60,  # Fully expired
        )
        all_quotes = cache.get_all()
        assert "AAPL" in all_quotes
        assert "OLD" not in all_quotes


class TestWatch:

    def test_watch_adds_symbols(self, cache):
        cache.watch(["AAPL", "MSFT", "NVDA"])
        assert cache._watch_symbols == {"AAPL", "MSFT", "NVDA"}

    def test_watch_deduplicates(self, cache):
        cache.watch(["AAPL", "aapl", "AAPL"])
        assert len(cache._watch_symbols) == 1

    def test_unwatch_removes(self, cache):
        cache.watch(["AAPL", "MSFT"])
        cache.unwatch("AAPL")
        assert cache._watch_symbols == {"MSFT"}

    def test_unwatch_nonexistent_no_error(self, cache):
        cache.unwatch("AAPL")  # Should not raise


class TestRefresh:

    @pytest.mark.asyncio
    async def test_refresh_updates_cache(self, cache, mock_quote_func):
        cache.watch(["AAPL", "MSFT"])
        mock_quote_func.side_effect = [
            {"price": 150.0},
            {"price": 420.0},
        ]
        await cache.refresh()
        assert cache.get("AAPL") == 150.0
        assert cache.get("MSFT") == 420.0
        assert cache._api_calls == 2

    @pytest.mark.asyncio
    async def test_refresh_empty_watchlist(self, cache, mock_quote_func):
        await cache.refresh()
        mock_quote_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_partial_failure(self, cache, mock_quote_func):
        cache.watch(["AAPL", "BAD"])
        mock_quote_func.side_effect = [
            {"price": 150.0},
            ConnectionError("fail"),
        ]
        await cache.refresh()
        assert cache.get("AAPL") == 150.0
        assert cache.get("BAD") is None
        assert cache._errors == 1


class TestStatistics:

    def test_hit_miss_tracking(self, cache):
        cache.put("AAPL", 150.0)
        cache.get("AAPL")  # hit
        cache.get("AAPL")  # hit
        cache.get("MSFT")  # miss
        assert cache._hits == 2
        assert cache._misses == 1

    def test_format_status(self, cache):
        cache.put("AAPL", 150.0)
        cache.watch(["AAPL", "MSFT"])
        cache.get("AAPL")
        text = cache.format_status()
        assert "行情缓存" in text
        assert "监控标的: 2" in text
        assert "缓存条目: 1" in text
