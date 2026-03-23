"""
OpenClaw LLM 响应缓存 — 搬运 diskcache (2.8k⭐)
SQLite 持久化缓存，重启不丢失，按 TTL 自动过期。

策略:
  - 相同 prompt+model+temperature → 返回缓存（命中率高的闲聊/FAQ场景）
  - 交易分析类请求 → 不缓存（实时性要求高）
  - 市场数据 → 短 TTL 缓存（5分钟）
  - 系统状态 → 短 TTL 缓存（30秒）

Usage:
    from src.llm_cache import cached_completion, get_cache_stats

    # Automatic caching wrapper
    result = await cached_completion(
        model_family="qwen",
        messages=[...],
        cache_ttl=3600,  # 1 hour
    )
"""
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---- Graceful degradation ----
try:
    import diskcache
    HAS_DISKCACHE = True
except ImportError:
    HAS_DISKCACHE = False
    logger.warning("[LLM Cache] diskcache 未安装, 缓存功能禁用. pip install diskcache>=5.6.0")

# ---- Cache directory ----
# Resolve project root: clawbot/ is the package root, data/ lives alongside src/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _PROJECT_ROOT / "data" / "llm_cache"

# ---- Singleton cache instance ----
_cache: Optional["diskcache.Cache"] = None
_stats = {"hits": 0, "misses": 0, "errors": 0, "bypassed": 0}

# ---- Default TTLs ----
TTL_CHAT = 3600       # 闲聊/FAQ: 1 hour
TTL_MARKET = 300      # 市场数据: 5 minutes
TTL_STATUS = 30       # 系统状态: 30 seconds


def _get_cache() -> Optional["diskcache.Cache"]:
    """Lazy-init singleton cache. Thread-safe by diskcache design."""
    global _cache
    if not HAS_DISKCACHE:
        return None
    if _cache is None:
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _cache = diskcache.Cache(
                str(_CACHE_DIR),
                size_limit=512 * 1024 * 1024,  # 512 MB max
                eviction_policy="least-recently-used",
                statistics=True,
            )
            logger.info(f"[LLM Cache] 初始化完成: {_CACHE_DIR} (limit=512MB, LRU)")
        except Exception as e:
            logger.error(f"[LLM Cache] 初始化失败: {e}")
            return None
    return _cache


def _make_cache_key(
    messages: list,
    model_family: Optional[str],
    temperature: float,
) -> str:
    """Generate deterministic cache key from request parameters.

    Key composition: SHA-256 of (messages_content + model_family + temperature).
    max_tokens is excluded — same prompt at different lengths should share cache.
    system_prompt is already part of messages when passed through acompletion.
    """
    key_parts = {
        "messages": [
            {"role": m.get("role", ""), "content": m.get("content", "")}
            for m in messages
        ],
        "model": model_family or "",
        "temperature": round(temperature, 4),
    }
    raw = json.dumps(key_parts, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"llm:{digest}"


async def cached_completion(
    model_family: Optional[str] = None,
    messages: Optional[list] = None,
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stream: bool = False,
    cache_ttl: int = TTL_CHAT,
    no_cache: bool = False,
    **kwargs,
) -> Any:
    """Caching wrapper around free_pool.acompletion().

    Transparent drop-in: same signature as LiteLLMPool.acompletion(),
    plus cache_ttl and no_cache parameters.

    Args:
        model_family: LiteLLM model family name
        messages: Chat messages list
        system_prompt: Optional system prompt (prepended to messages)
        temperature: Sampling temperature
        max_tokens: Max output tokens
        stream: Streaming mode (cache is bypassed for streaming)
        cache_ttl: Cache time-to-live in seconds (default 3600)
        no_cache: Force bypass cache
        **kwargs: Passed through to acompletion()

    Returns:
        LiteLLM completion response (from cache or fresh)
    """
    from src.litellm_router import free_pool

    messages = messages or []

    # ---- Bypass conditions ----
    if stream or no_cache or not HAS_DISKCACHE:
        if no_cache or stream:
            _stats["bypassed"] += 1
        return await free_pool.acompletion(
            model_family=model_family,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            **kwargs,
        )

    cache = _get_cache()
    if cache is None:
        # Cache unavailable, fall through to direct call
        return await free_pool.acompletion(
            model_family=model_family,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            **kwargs,
        )

    # ---- Build cache key ----
    # Include system_prompt in messages for key generation (mirrors acompletion behavior)
    key_messages = (
        [{"role": "system", "content": system_prompt}] + messages
        if system_prompt
        else messages
    )
    cache_key = _make_cache_key(key_messages, model_family, temperature)

    # ---- Cache lookup ----
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            _stats["hits"] += 1
            logger.debug(f"[LLM Cache] HIT  key={cache_key[:16]}… model={model_family}")
            return cached
    except Exception as e:
        _stats["errors"] += 1
        logger.warning(f"[LLM Cache] 读取失败: {e}")

    # ---- Cache miss → call LLM ----
    _stats["misses"] += 1
    logger.debug(f"[LLM Cache] MISS key={cache_key[:16]}… model={model_family}")

    response = await free_pool.acompletion(
        model_family=model_family,
        messages=messages,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
        **kwargs,
    )

    # ---- Store in cache ----
    try:
        cache.set(cache_key, response, expire=cache_ttl)
        logger.debug(f"[LLM Cache] SET  key={cache_key[:16]}… ttl={cache_ttl}s")
    except Exception as e:
        _stats["errors"] += 1
        logger.warning(f"[LLM Cache] 写入失败: {e}")

    return response


def get_cache_stats() -> Dict[str, Any]:
    """Return cache statistics.

    Returns:
        Dict with keys: hits, misses, hit_rate, bypassed, errors,
                        entries, size_mb, size_limit_mb, directory
    """
    result: Dict[str, Any] = {
        "enabled": HAS_DISKCACHE,
        "hits": _stats["hits"],
        "misses": _stats["misses"],
        "bypassed": _stats["bypassed"],
        "errors": _stats["errors"],
        "hit_rate": 0.0,
        "entries": 0,
        "size_mb": 0.0,
        "size_limit_mb": 512.0,
        "directory": str(_CACHE_DIR),
    }

    total = _stats["hits"] + _stats["misses"]
    if total > 0:
        result["hit_rate"] = round(_stats["hits"] / total, 4)

    cache = _get_cache()
    if cache is not None:
        try:
            result["entries"] = len(cache)
            result["size_mb"] = round(cache.volume() / (1024 * 1024), 2)
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

    return result


def clear_cache() -> int:
    """Clear all cached LLM responses.

    Returns:
        Number of entries removed.
    """
    cache = _get_cache()
    if cache is None:
        return 0

    try:
        count = len(cache)
        cache.clear()
        # Reset stats
        _stats["hits"] = 0
        _stats["misses"] = 0
        _stats["errors"] = 0
        _stats["bypassed"] = 0
        logger.info(f"[LLM Cache] 已清空 {count} 条缓存")
        return count
    except Exception as e:
        logger.error(f"[LLM Cache] 清空失败: {e}")
        return 0


def close_cache() -> None:
    """Close the cache (call on shutdown for clean SQLite close)."""
    global _cache
    if _cache is not None:
        try:
            _cache.close()
        except Exception:
            logger.debug("Silenced exception", exc_info=True)
        _cache = None
