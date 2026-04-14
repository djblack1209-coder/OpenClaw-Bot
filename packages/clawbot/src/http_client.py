"""
ClawBot - 增强 HTTP 客户端
支持指数退避重试、熔断器、请求级别追踪
"""

import time
import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


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

    def get_status(self) -> Dict[str, Any]:
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

    def get_status(self) -> Dict[str, Any]:
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
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        name: str = "default",
        verify_ssl: bool = True,
    ):
        self.timeout = timeout
        self.retry = retry_config or RetryConfig()
        self.breaker = circuit_breaker or CircuitBreaker()
        self.metrics = RequestMetrics()
        self.name = name
        self.verify_ssl = verify_ssl  # SSL 证书验证开关

    def _new_client(self, follow_redirects: bool = False, verify: bool = True) -> httpx.AsyncClient:
        """每次请求创建全新的 AsyncClient（模拟 curl 行为）

        核弹方案：g4f/Kiro 网关会主动关闭空闲连接，httpx 连接池
        即使设置 max_keepalive_connections=0 仍会复用底层 transport，
        导致 RemoteProtocolError。唯一可靠方案是每次请求用全新 client。
        对 localhost 网关，新建 TCP 连接开销可忽略（<1ms）。

        Args:
            follow_redirects: 是否自动跟随重定向
            verify: 是否验证 SSL 证书（默认 True）
        """
        return httpx.AsyncClient(
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            follow_redirects=follow_redirects,
            verify=verify,
            # 显式禁用代理：防止领券等场景被 mitmproxy 系统代理干扰
            proxy=None,
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
        headers: Optional[Dict] = None,
        json: Optional[Dict] = None,
        params: Optional[Dict] = None,
        content: Optional[bytes] = None,
        data: Optional[Dict] = None,
        files: Optional[Any] = None,
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
        # SSRF 防护: 当调用方明确要求检查时，拦截指向内网/元数据服务的请求
        if ssrf_check:
            from src.core.security import check_ssrf, SSRFError

            if not check_ssrf(url):
                raise SSRFError(f"[{self.name}] SSRF 安全检查未通过: {url} (禁止访问内网/元数据服务地址)")

        if not self.breaker.can_execute():
            raise CircuitOpenError(
                f"[{self.name}] 熔断器开启，拒绝请求 (将在 {self.breaker.recovery_timeout}s 后尝试恢复)"
            )

        last_exception = None
        retries = 0
        start_time = time.time()

        for attempt in range(self.retry.max_retries + 1):
            client = self._new_client(follow_redirects=follow_redirects, verify=self.verify_ssl)
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                    content=content,
                    data=data,
                    files=files,
                )

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

            except httpx.HTTPStatusError as e:
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

    def _calc_delay(self, attempt: int, response: Optional[httpx.Response] = None) -> float:
        """计算退避延迟，支持 Retry-After 头"""
        # 优先使用服务端的 Retry-After
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), self.retry.max_delay)
                except ValueError as e:  # noqa: F841
                    pass

        delay = self.retry.base_delay * (self.retry.exponential_base**attempt)
        return min(delay, self.retry.max_delay)

    # 便捷方法
    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "metrics": self.metrics.get_status(),
            "circuit_breaker": self.breaker.get_status(),
        }


class CircuitOpenError(Exception):
    """熔断器开启异常"""

    pass
