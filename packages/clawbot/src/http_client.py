"""
ClawBot - 增强 HTTP 客户端
支持指数退避重试、熔断器、请求级别追踪
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpcore
import httpx

from src.core import security as security_core
from src.core.security import SSRFError, resolve_public_addresses

logger = logging.getLogger(__name__)

_SSRF_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_MAX_SSRF_REDIRECTS = 5


class PinnedPublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """把域名解析为已验证公网 IP，并让真实 TCP 直接连接该 IP。"""

    def __init__(self, network_backend=None, resolver=resolve_public_addresses):
        if network_backend is None:
            from httpcore._backends.auto import AutoBackend

            network_backend = AutoBackend()
        self._network_backend = network_backend
        self._resolver = resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        """在线程中解析一次，并仅连接这次校验得到的 IP。"""
        addresses = await asyncio.to_thread(self._resolver, host, port)
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._network_backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise SSRFError("目标域名没有可连接的公网地址")

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        """面向公网的安全传输层不允许 Unix Socket。"""
        raise SSRFError("公网请求不允许 Unix Socket")

    async def sleep(self, seconds: float) -> None:
        """复用底层后端的异步休眠实现。"""
        await self._network_backend.sleep(seconds)


def create_ssrf_safe_async_client(timeout: float) -> httpx.AsyncClient:
    """创建禁用环境代理、连接时固定已校验 IP 的 HTTPX 客户端。"""
    transport = httpx.AsyncHTTPTransport(
        verify=True,
        trust_env=False,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=0),
    )
    transport._pool._network_backend = PinnedPublicNetworkBackend()
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        transport=transport,
        trust_env=False,
    )


async def request_with_ssrf_protection(
    client,
    method: str,
    url: str,
    *,
    follow_redirects: bool = False,
    max_redirects: int = _MAX_SSRF_REDIRECTS,
    **kwargs,
) -> httpx.Response:
    """逐跳校验重定向目标；客户端本身负责在连接层固定公网 IP。"""
    if not security_core.check_ssrf(url):
        raise SSRFError(f"SSRF 安全检查未通过: {url}")

    normalized_method = method.upper()
    response = await client.request(normalized_method, url, **kwargs)

    redirect_count = 0
    while follow_redirects and response.status_code in _SSRF_REDIRECT_STATUS_CODES:
        next_request = response.next_request
        if next_request is None:
            return response
        if redirect_count >= max_redirects:
            await response.aclose()
            raise httpx.TooManyRedirects(
                f"重定向超过安全上限 {max_redirects}",
                request=next_request,
            )
        next_url = str(next_request.url)
        if not security_core.check_ssrf(next_url):
            await response.aclose()
            raise SSRFError(f"重定向目标 SSRF 安全检查未通过: {next_url}")
        await response.aclose()
        response = await client.send(next_request, follow_redirects=False)
        redirect_count += 1
    return response


class CircuitState(Enum):
    CLOSED = "closed"  # 正常
    OPEN = "open"  # 熔断（拒绝请求）
    HALF_OPEN = "half_open"  # 半开（试探性放行）


@dataclass
class CircuitBreaker:
    """熔断器"""

    failure_threshold: int = 5  # 连续失败次数触发熔断
    recovery_timeout: float = 60.0  # 熔断恢复等待时间（秒）
    half_open_max: int = 1  # 半开状态最大试探请求数

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    half_open_count: int = 0

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_count = 0
                logger.info("熔断器 -> HALF_OPEN")
                return True
            return False
        # HALF_OPEN
        return self.half_open_count < self.half_open_max

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            logger.info("熔断器 -> CLOSED (恢复)")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_count = 0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("熔断器 -> OPEN (半开失败)")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"熔断器 -> OPEN (连续失败 {self.failure_count} 次)")

    def get_status(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time,
        }


@dataclass
class RetryConfig:
    """重试配置"""

    max_retries: int = 3
    base_delay: float = 1.0  # 基础延迟（秒）
    max_delay: float = 30.0  # 最大延迟（秒）
    exponential_base: float = 2.0  # 指数基数
    retryable_status_codes: tuple = (429, 500, 502, 503, 504)


@dataclass
class RequestMetrics:
    """请求级别指标"""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_retries: int = 0
    total_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency_ms / self.successful_requests

    def record(self, success: bool, latency_ms: float, retries: int = 0):
        self.total_requests += 1
        self.total_retries += retries
        if success:
            self.successful_requests += 1
            self.total_latency_ms += latency_ms
        else:
            self.failed_requests += 1

    def get_status(self) -> dict[str, Any]:
        return {
            "total": self.total_requests,
            "success": self.successful_requests,
            "failed": self.failed_requests,
            "retries": self.total_retries,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


class ResilientHTTPClient:
    """
    带重试、熔断、指标追踪的 HTTP 客户端。

    用法:
        client = ResilientHTTPClient()
        response = await client.post(url, headers=..., json=...)
        data = response.json()
    """

    def __init__(
        self,
        timeout: float = 120.0,
        retry_config: RetryConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        name: str = "default",
        verify_ssl: bool = True,
    ):
        self.timeout = timeout
        self.retry = retry_config or RetryConfig()
        self.breaker = circuit_breaker or CircuitBreaker()
        self.metrics = RequestMetrics()
        self.name = name
        self.verify_ssl = verify_ssl  # SSL 证书验证开关

    def _new_client(
        self,
        follow_redirects: bool = False,
        verify: bool = True,
        ssrf_check: bool = False,
    ) -> httpx.AsyncClient:
        """每次请求创建全新的 AsyncClient（模拟 curl 行为）

        核弹方案：g4f/Kiro 网关会主动关闭空闲连接，httpx 连接池
        即使设置 max_keepalive_connections=0 仍会复用底层 transport，
        导致 RemoteProtocolError。唯一可靠方案是每次请求用全新 client。
        对 localhost 网关，新建 TCP 连接开销可忽略（<1ms）。

        Args:
            follow_redirects: 是否自动跟随重定向
            verify: 是否验证 SSL 证书（默认 True）
            ssrf_check: 是否启用连接层公网 IP 固定
        """
        transport = None
        if ssrf_check:
            transport = httpx.AsyncHTTPTransport(
                verify=verify,
                trust_env=False,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            )
            transport._pool._network_backend = PinnedPublicNetworkBackend()
        return httpx.AsyncClient(
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            follow_redirects=follow_redirects and not ssrf_check,
            verify=verify,
            transport=transport,
            trust_env=False,
        )

    async def close(self):
        """关闭客户端：重置熔断器和指标状态。

        核弹模式下没有持久连接需要关闭（每次请求创建新的 AsyncClient），
        但仍需重置内部状态以便对象可安全复用或垃圾回收。
        """
        # 重置熔断器到正常状态
        self.breaker.state = CircuitState.CLOSED
        self.breaker.failure_count = 0
        self.breaker.half_open_count = 0
        # 记录关闭日志
        logger.debug("[%s] HTTP 客户端已关闭，熔断器和指标已重置", self.name)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
        params: dict | None = None,
        content: bytes | None = None,
        data: dict | None = None,
        files: Any | None = None,
        follow_redirects: bool = False,
        ssrf_check: bool = False,
    ) -> httpx.Response:
        """发送 HTTP 请求，带重试和熔断。

        Args:
            data: 表单数据（multipart/form-data 或 application/x-www-form-urlencoded）。
            files: 文件上传（multipart/form-data），格式同 httpx。
            follow_redirects: 是否自动跟随重定向（默认 False）。
            ssrf_check: 是否对 URL 执行 SSRF 安全检查。
                默认 False（内部已知安全的 API 调用无需检查）。
                接受用户输入 URL 的场景应设为 True。
        """
        # SSRF 防护: 初始目标、每次重定向和真实 TCP 连接均执行独立校验。
        if ssrf_check and not security_core.check_ssrf(url):
            raise SSRFError(f"[{self.name}] SSRF 安全检查未通过: {url} (禁止访问内网/元数据服务地址)")

        if not self.breaker.can_execute():
            raise CircuitOpenError(
                f"[{self.name}] 熔断器开启，拒绝请求 (将在 {self.breaker.recovery_timeout}s 后尝试恢复)"
            )

        last_exception = None
        retries = 0
        start_time = time.time()

        for attempt in range(self.retry.max_retries + 1):
            client = self._new_client(
                follow_redirects=follow_redirects,
                verify=self.verify_ssl,
                ssrf_check=ssrf_check,
            )
            try:
                request_kwargs = {
                    "headers": headers,
                    "json": json,
                    "params": params,
                    "content": content,
                    "data": data,
                    "files": files,
                }
                if ssrf_check:
                    response = await request_with_ssrf_protection(
                        client,
                        method,
                        url,
                        follow_redirects=follow_redirects,
                        **request_kwargs,
                    )
                else:
                    response = await client.request(method, url, **request_kwargs)

                # 检查是否需要重试
                if response.status_code in self.retry.retryable_status_codes:
                    if attempt < self.retry.max_retries:
                        delay = self._calc_delay(attempt, response)
                        retries += 1
                        logger.warning(
                            f"[{self.name}] HTTP {response.status_code}, "
                            f"重试 {attempt + 1}/{self.retry.max_retries} "
                            f"(等待 {delay:.1f}s)"
                        )
                        await asyncio.sleep(delay)
                        continue
                    # 最后一次重试也失败
                    response.raise_for_status()

                # 成功
                latency = (time.time() - start_time) * 1000
                self.metrics.record(True, latency, retries)
                self.breaker.record_success()
                return response

            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.WriteError,
                httpx.CloseError,
            ) as e:
                last_exception = e
                if attempt < self.retry.max_retries:
                    delay = self._calc_delay(attempt)
                    retries += 1
                    logger.warning(
                        f"[{self.name}] 网络错误: {type(e).__name__}, "
                        f"重试 {attempt + 1}/{self.retry.max_retries} "
                        f"(等待 {delay:.1f}s)"
                    )
                    await asyncio.sleep(delay)
                    continue

            except httpx.HTTPStatusError:
                # 非可重试状态码，直接失败
                latency = (time.time() - start_time) * 1000
                self.metrics.record(False, latency, retries)
                self.breaker.record_failure()
                raise

            finally:
                await client.aclose()

        # 所有重试都失败
        latency = (time.time() - start_time) * 1000
        self.metrics.record(False, latency, retries)
        self.breaker.record_failure()

        if last_exception:
            raise last_exception
        raise Exception(f"[{self.name}] 请求失败，已重试 {retries} 次")

    def _calc_delay(self, attempt: int, response: httpx.Response | None = None) -> float:
        """计算退避延迟，支持 Retry-After 头"""
        # 优先使用服务端的 Retry-After
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), self.retry.max_delay)
                except ValueError as e:
                    logger.debug("值解析失败: %s", e)

        delay = self.retry.base_delay * (self.retry.exponential_base**attempt)
        return min(delay, self.retry.max_delay)

    # 便捷方法
    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "metrics": self.metrics.get_status(),
            "circuit_breaker": self.breaker.get_status(),
        }


class CircuitOpenError(Exception):
    """熔断器开启异常"""
