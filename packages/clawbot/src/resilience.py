"""
OpenClaw 弹性工具集 — 搬运 stamina (1.4k⭐) + PyrateLimiter (485⭐)
统一重试和限流配置，替代分散的 tenacity 配置。

三层降级:
  1. stamina (首选) — 干净的 API、structlog 集成、类型安全
  2. tenacity (次选) — 已有依赖，功能完整
  3. 手写 try/except (保底) — 零依赖

Usage:
    from src.resilience import retry_api, retry_network, retry_llm, api_limiter

    @retry_api  # 3次重试，指数退避，httpx/timeout 错误
    async def call_api(): ...

    @retry_network  # 5次重试，更长等待，网络错误
    async def download(): ...

    @retry_llm  # 3次重试，排除 ValueError/TypeError
    async def ask_llm(): ...

    async with api_limiter("yfinance"):
        data = await fetch_stock_data()
"""
import asyncio
import functools
import importlib.util
import logging
import time
import threading
from contextlib import asynccontextmanager
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ══════════════════════════════════════════════════════
# 重试层 — stamina → tenacity → 手写
# ══════════════════════════════════════════════════════

# ── 依赖探测 ──────────────────────────────────────────

_RETRY_BACKEND: str = "manual"  # "stamina" | "tenacity" | "manual"

try:
    import stamina

    _RETRY_BACKEND = "stamina"
    logger.debug("[resilience] 使用 stamina 作为重试后端")
except ImportError:
    if importlib.util.find_spec("tenacity") is not None:
        _RETRY_BACKEND = "tenacity"
        logger.debug("[resilience] stamina 未安装，降级到 tenacity")
    else:
        logger.info(
            "[resilience] stamina 和 tenacity 均未安装，使用手写指数退避。"
            "pip install stamina>=2.0.0 以启用最佳重试体验。"
        )

# ── httpx 错误类型（可能未安装） ──────────────────────

try:
    import httpx

    _HTTPX_ERRORS: Tuple[Type[Exception], ...] = (
        httpx.HTTPError,
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.RemoteProtocolError,
    )
except ImportError:
    _HTTPX_ERRORS = ()


# ── 预定义错误组合 ────────────────────────────────────

def _api_errors() -> Tuple[Type[Exception], ...]:
    """API 调用常见可重试错误"""
    base: Tuple[Type[Exception], ...] = (
        ConnectionError,
        asyncio.TimeoutError,
        TimeoutError,
        OSError,
    )
    return base + _HTTPX_ERRORS


def _network_errors() -> Tuple[Type[Exception], ...]:
    """网络层可重试错误"""
    base: Tuple[Type[Exception], ...] = (
        ConnectionError,
        ConnectionResetError,
        ConnectionAbortedError,
        BrokenPipeError,
        OSError,
        TimeoutError,
        asyncio.TimeoutError,
    )
    # httpx 特有的连接错误
    httpx_net: Tuple[Type[Exception], ...] = ()
    try:
        import httpx as _httpx

        httpx_net = (
            _httpx.ConnectError,
            _httpx.ConnectTimeout,
            _httpx.ReadTimeout,
            _httpx.WriteTimeout,
            _httpx.RemoteProtocolError,
        )
    except ImportError:
        pass
    return base + httpx_net


def _llm_errors() -> Tuple[Type[Exception], ...]:
    """LLM API 可重试错误（排除编程错误）"""
    base: Tuple[Type[Exception], ...] = (
        ConnectionError,
        asyncio.TimeoutError,
        TimeoutError,
        OSError,
    )
    return base + _HTTPX_ERRORS


# 不应重试的错误（编程错误）
_NON_RETRYABLE: Tuple[Type[Exception], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    NotImplementedError,
    SyntaxError,
)


# ══════════════════════════════════════════════════════
# 统一重试装饰器工厂
# ══════════════════════════════════════════════════════

def _make_retry_decorator(
    *,
    attempts: int = 3,
    on: Optional[Tuple[Type[Exception], ...]] = None,
    exclude: Optional[Tuple[Type[Exception], ...]] = None,
    wait_initial: float = 1.0,
    wait_max: float = 30.0,
    wait_exp_base: float = 2.0,
    wait_jitter: float = 1.0,
    name: str = "retry",
) -> Callable[[F], F]:
    """
    创建统一的重试装饰器，自动选择最佳后端。

    Args:
        attempts: 最大尝试次数（含首次）
        on: 要重试的异常类型元组
        exclude: 不重试的异常类型元组
        wait_initial: 首次重试前的初始等待（秒）
        wait_max: 最大等待时间（秒）
        wait_exp_base: 指数退避基数
        wait_jitter: 抖动范围（秒），避免惊群效应
        name: 装饰器名称（用于日志）
    """
    retry_on = on or (Exception,)
    no_retry_on = exclude or ()

    def should_retry(exc: Exception) -> bool:
        """检查异常是否应该重试"""
        if no_retry_on and isinstance(exc, no_retry_on):
            return False
        return isinstance(exc, retry_on)

    # ── stamina 后端 ──────────────────────────────
    if _RETRY_BACKEND == "stamina":

        def decorator(func: F) -> F:
            @stamina.retry(
                on=retry_on,
                attempts=attempts,
                wait_initial=wait_initial,
                wait_max=wait_max,
                wait_exp_base=wait_exp_base,
                wait_jitter=wait_jitter,
            )
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            @stamina.retry(
                on=retry_on,
                attempts=attempts,
                wait_initial=wait_initial,
                wait_max=wait_max,
                wait_exp_base=wait_exp_base,
                wait_jitter=wait_jitter,
            )
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                return func(*args, **kwargs)

            if asyncio.iscoroutinefunction(func):
                # 如果有排除列表，需要额外包装
                if no_retry_on:
                    @functools.wraps(func)
                    async def filtered_async(*args, **kwargs):
                        try:
                            return await async_wrapper(*args, **kwargs)
                        except Exception as e:
                            if isinstance(e, no_retry_on):
                                raise
                            raise
                    return filtered_async  # type: ignore[return-value]
                return async_wrapper  # type: ignore[return-value]
            else:
                if no_retry_on:
                    @functools.wraps(func)
                    def filtered_sync(*args, **kwargs):
                        try:
                            return sync_wrapper(*args, **kwargs)
                        except Exception as e:
                            if isinstance(e, no_retry_on):
                                raise
                            raise
                    return filtered_sync  # type: ignore[return-value]
                return sync_wrapper  # type: ignore[return-value]

        return decorator

    # ── tenacity 后端 ─────────────────────────────
    elif _RETRY_BACKEND == "tenacity":
        from tenacity import (
            retry as tenacity_retry,
            stop_after_attempt,
            wait_exponential_jitter,
            retry_if_exception,
        )

        def decorator(func: F) -> F:
            return tenacity_retry(  # type: ignore[return-value]
                stop=stop_after_attempt(attempts),
                wait=wait_exponential_jitter(
                    initial=wait_initial,
                    max=wait_max,
                    exp_base=wait_exp_base,
                    jitter=wait_jitter,
                ),
                retry=retry_if_exception(should_retry),
                reraise=True,
            )(func)

        return decorator

    # ── 手写后端 ──────────────────────────────────
    else:

        def decorator(func: F) -> F:
            if asyncio.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    last_exc: Optional[Exception] = None
                    for attempt in range(attempts):
                        try:
                            return await func(*args, **kwargs)
                        except Exception as e:
                            if not should_retry(e):
                                raise
                            last_exc = e
                            if attempt < attempts - 1:
                                delay = min(
                                    wait_initial * (wait_exp_base ** attempt),
                                    wait_max,
                                )
                                logger.warning(
                                    f"[{name}] {type(e).__name__}: {e}, "
                                    f"重试 {attempt + 1}/{attempts} "
                                    f"(等待 {delay:.1f}s)"
                                )
                                await asyncio.sleep(delay)
                    # 安全保护: attempts=0 时 last_exc 仍为 None
                    if last_exc is not None:
                        raise last_exc
                    raise RuntimeError(f"[{name}] 重试耗尽但未捕获异常 (attempts={attempts})")

                return async_wrapper  # type: ignore[return-value]
            else:

                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    import time as _time

                    last_exc: Optional[Exception] = None
                    for attempt in range(attempts):
                        try:
                            return func(*args, **kwargs)
                        except Exception as e:
                            if not should_retry(e):
                                raise
                            last_exc = e
                            if attempt < attempts - 1:
                                delay = min(
                                    wait_initial * (wait_exp_base ** attempt),
                                    wait_max,
                                )
                                logger.warning(
                                    f"[{name}] {type(e).__name__}: {e}, "
                                    f"重试 {attempt + 1}/{attempts} "
                                    f"(等待 {delay:.1f}s)"
                                )
                                _time.sleep(delay)
                    # 安全保护: attempts=0 时 last_exc 仍为 None
                    if last_exc is not None:
                        raise last_exc
                    raise RuntimeError(f"[{name}] 重试耗尽但未捕获异常 (attempts={attempts})")

                return sync_wrapper  # type: ignore[return-value]

        return decorator


# ══════════════════════════════════════════════════════
# 预配置的重试装饰器（直接使用）
# ══════════════════════════════════════════════════════

retry_api = _make_retry_decorator(
    attempts=3,
    on=_api_errors(),
    wait_initial=1.0,
    wait_max=15.0,
    name="retry_api",
)
"""API 调用重试 — 3次，指数退避 1s→2s→4s，上限15s。
捕获: httpx.HTTPError, asyncio.TimeoutError, ConnectionError, OSError"""

retry_network = _make_retry_decorator(
    attempts=5,
    on=_network_errors(),
    wait_initial=2.0,
    wait_max=60.0,
    wait_exp_base=2.0,
    name="retry_network",
)
"""网络操作重试 — 5次，指数退避 2s→4s→8s→16s→32s，上限60s。
捕获: ConnectionError, OSError, httpx.ConnectError 等"""

retry_llm = _make_retry_decorator(
    attempts=3,
    on=_llm_errors(),
    exclude=_NON_RETRYABLE,
    wait_initial=2.0,
    wait_max=30.0,
    name="retry_llm",
)
"""LLM API 重试 — 3次，指数退避 2s→4s→8s，上限30s。
捕获: 网络/超时错误，但 NOT ValueError/TypeError/KeyError 等编程错误"""


def retry_custom(
    *,
    attempts: int = 3,
    on: Tuple[Type[Exception], ...] = (Exception,),
    exclude: Optional[Tuple[Type[Exception], ...]] = None,
    wait_initial: float = 1.0,
    wait_max: float = 30.0,
    name: str = "retry_custom",
) -> Callable[[F], F]:
    """
    自定义重试装饰器。

    Usage:
        @retry_custom(attempts=5, on=(httpx.HTTPError,), name="my_api")
        async def call_my_api(): ...
    """
    return _make_retry_decorator(
        attempts=attempts,
        on=on,
        exclude=exclude,
        wait_initial=wait_initial,
        wait_max=wait_max,
        name=name,
    )


# ══════════════════════════════════════════════════════
# 限流层 — PyrateLimiter → 手写令牌桶
# ══════════════════════════════════════════════════════

# ── 依赖探测 ──────────────────────────────────────────

_LIMITER_BACKEND: str = "manual"  # "pyrate" | "manual"

try:
    from pyrate_limiter import (
        Duration,
        Limiter,
        Rate,
        BucketFullException,
    )

    _LIMITER_BACKEND = "pyrate"
    logger.debug("[resilience] 使用 pyrate_limiter 作为限流后端")
except ImportError:
    logger.info(
        "[resilience] pyrate_limiter 未安装，使用手写令牌桶限流。"
        "pip install pyrate-limiter>=3.0.0 以启用精确限流。"
    )


# ── 预配置的服务限流规则 ──────────────────────────────

# (名称, 最大请求数, 时间窗口秒数)
_SERVICE_LIMITS: Dict[str, Sequence[Tuple[int, float]]] = {
    # yfinance: 2000/hour（官方限制）
    "yfinance": [(2000, 3600)],
    # akshare: 100/minute（经验值，防封）
    "akshare": [(100, 60)],
    # telegram: 30/second（官方限制），20 messages/minute to same group
    "telegram": [(30, 1), (20, 60)],
    # LLM API: 60/minute（通用默认值）
    "llm": [(60, 60)],
    # 通用默认: 60/minute
    "generic": [(60, 60)],
    # ccxt 加密货币: 10/second（交易所通用）
    "ccxt": [(10, 1), (1200, 60)],
    # crawl4ai 爬虫: 5/second（礼貌爬取）
    "crawl4ai": [(5, 1), (100, 60)],
}


# ── PyrateLimiter 后端 ────────────────────────────────

if _LIMITER_BACKEND == "pyrate":

    _pyrate_limiters: Dict[str, Limiter] = {}
    _pyrate_lock = threading.Lock()

    def _get_pyrate_limiter(service: str) -> Limiter:
        """获取或创建 PyrateLimiter 实例（线程安全）"""
        if service not in _pyrate_limiters:
            with _pyrate_lock:
                if service not in _pyrate_limiters:
                    limits = _SERVICE_LIMITS.get(service, _SERVICE_LIMITS["generic"])
                    rates = []
                    for count, window_secs in limits:
                        rates.append(Rate(count, Duration.SECOND * int(window_secs)))
                    _pyrate_limiters[service] = Limiter(*rates)
        return _pyrate_limiters[service]

    @asynccontextmanager
    async def api_limiter(service: str = "generic"):
        """
        异步限流上下文管理器 — PyrateLimiter 后端。

        Usage:
            async with api_limiter("yfinance"):
                data = await fetch_stock_data()
        """
        limiter = _get_pyrate_limiter(service)
        while True:
            try:
                limiter.try_acquire(service)
                break
            except BucketFullException as e:
                # 从异常消息中提取等待时间，或使用默认 1s
                wait_time = 1.0
                # BucketFullException 有 meta_info 属性
                meta = getattr(e, "meta_info", None)
                if meta and hasattr(meta, "remaining_time"):
                    remaining = meta.remaining_time
                    if remaining and remaining > 0:
                        wait_time = remaining
                logger.debug(
                    f"[rate_limit] {service} 触发限流，等待 {wait_time:.2f}s"
                )
                await asyncio.sleep(wait_time)
        yield

else:

    # ── 手写令牌桶后端 ────────────────────────────

    class _TokenBucket:
        """简单的令牌桶限流器 — 线程安全"""

        def __init__(self, rate: float, capacity: int):
            """
            Args:
                rate: 每秒补充的令牌数
                capacity: 桶容量（最大突发）
            """
            self._rate = rate
            self._capacity = capacity
            self._tokens = float(capacity)
            self._last_refill = time.monotonic()
            self._lock = threading.Lock()

        def _refill(self):
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._capacity, self._tokens + elapsed * self._rate
            )
            self._last_refill = now

        def try_acquire(self) -> float:
            """
            尝试获取一个令牌。

            Returns:
                0.0 如果成功获取
                > 0 需要等待的秒数
            """
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return 0.0
                # 计算需要等待的时间
                deficit = 1.0 - self._tokens
                return deficit / self._rate

    _manual_buckets: Dict[str, list[_TokenBucket]] = {}
    _manual_lock = threading.Lock()

    def _get_manual_buckets(service: str) -> list[_TokenBucket]:
        """获取或创建令牌桶（线程安全）"""
        if service not in _manual_buckets:
            with _manual_lock:
                if service not in _manual_buckets:
                    limits = _SERVICE_LIMITS.get(
                        service, _SERVICE_LIMITS["generic"]
                    )
                    buckets = []
                    for count, window_secs in limits:
                        rate = count / window_secs  # 每秒令牌补充速率
                        buckets.append(_TokenBucket(rate=rate, capacity=count))
                    _manual_buckets[service] = buckets
        return _manual_buckets[service]

    @asynccontextmanager
    async def api_limiter(service: str = "generic"):
        """
        异步限流上下文管理器 — 手写令牌桶后端。

        Usage:
            async with api_limiter("yfinance"):
                data = await fetch_stock_data()
        """
        buckets = _get_manual_buckets(service)
        while True:
            max_wait = 0.0
            for bucket in buckets:
                wait = bucket.try_acquire()
                max_wait = max(max_wait, wait)
            if max_wait <= 0:
                break
            logger.debug(
                f"[rate_limit] {service} 触发限流，等待 {max_wait:.2f}s"
            )
            await asyncio.sleep(max_wait)
            # 重新尝试所有桶（等待后令牌已补充）
        yield


# ══════════════════════════════════════════════════════
# 限流工具函数
# ══════════════════════════════════════════════════════

def configure_service_limit(
    service: str,
    limits: Sequence[Tuple[int, float]],
) -> None:
    """
    动态配置服务限流规则。

    Args:
        service: 服务名称
        limits: [(最大请求数, 时间窗口秒数), ...]

    Usage:
        configure_service_limit("my_api", [(100, 60)])  # 100/min
    """
    _SERVICE_LIMITS[service] = list(limits)
    # 清除缓存，下次使用时会重新创建
    if _LIMITER_BACKEND == "pyrate":
        with _pyrate_lock:
            _pyrate_limiters.pop(service, None)
    else:
        with _manual_lock:
            _manual_buckets.pop(service, None)
    logger.info(f"[rate_limit] 更新 {service} 限流规则: {limits}")


def get_retry_backend() -> str:
    """返回当前使用的重试后端名称"""
    return _RETRY_BACKEND


def get_limiter_backend() -> str:
    """返回当前使用的限流后端名称"""
    return _LIMITER_BACKEND


def get_service_limits() -> Dict[str, Sequence[Tuple[int, float]]]:
    """返回所有已配置的服务限流规则"""
    return dict(_SERVICE_LIMITS)
