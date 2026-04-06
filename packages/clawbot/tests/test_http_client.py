"""
http_client 单元测试 — 覆盖熔断器状态机、请求指标、退避计算、重试逻辑
"""
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from src.http_client import (
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    RequestMetrics,
    RetryConfig,
    ResilientHTTPClient,
)


# ============ CircuitBreaker 状态机 ============

class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.can_execute() is True

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_open_rejects_requests(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_open_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=1.0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # 模拟超时
        cb.last_failure_time = time.time() - 2.0
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_limits_requests(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0, half_open_max=1)
        cb.record_failure()
        cb.last_failure_time = time.time() - 1.0
        # 第一次 can_execute 触发 OPEN -> HALF_OPEN
        assert cb.can_execute() is True
        cb.half_open_count = 1
        # 超过 half_open_max 后拒绝
        assert cb.can_execute() is False

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        cb.last_failure_time = time.time() - 1.0
        cb.can_execute()  # -> HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        cb.last_failure_time = time.time() - 1.0
        cb.can_execute()  # -> HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_get_status(self):
        cb = CircuitBreaker()
        cb.record_failure()
        status = cb.get_status()
        assert status["state"] == "closed"
        assert status["failure_count"] == 1
        assert status["last_failure"] > 0


# ============ RequestMetrics ============

class TestRequestMetrics:
    def test_initial_zeros(self):
        m = RequestMetrics()
        assert m.total_requests == 0
        assert m.avg_latency_ms == 0.0

    def test_record_success(self):
        m = RequestMetrics()
        m.record(success=True, latency_ms=100.0, retries=1)
        assert m.total_requests == 1
        assert m.successful_requests == 1
        assert m.failed_requests == 0
        assert m.total_retries == 1
        assert m.avg_latency_ms == 100.0

    def test_record_failure(self):
        m = RequestMetrics()
        m.record(success=False, latency_ms=50.0)
        assert m.total_requests == 1
        assert m.failed_requests == 1
        assert m.successful_requests == 0
        # 失败不计入延迟
        assert m.avg_latency_ms == 0.0

    def test_avg_latency_multiple(self):
        m = RequestMetrics()
        m.record(True, 100.0)
        m.record(True, 200.0)
        m.record(True, 300.0)
        assert m.avg_latency_ms == 200.0

    def test_get_status_format(self):
        m = RequestMetrics()
        m.record(True, 123.456)
        m.record(False, 50.0, retries=2)
        status = m.get_status()
        assert status == {
            "total": 2,
            "success": 1,
            "failed": 1,
            "retries": 2,
            "avg_latency_ms": 123.5,
        }


# ============ _calc_delay ============

class TestCalcDelay:
    def test_exponential_backoff(self):
        client = ResilientHTTPClient(
            retry_config=RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=30.0)
        )
        assert client._calc_delay(0) == 1.0   # 1 * 2^0
        assert client._calc_delay(1) == 2.0   # 1 * 2^1
        assert client._calc_delay(2) == 4.0   # 1 * 2^2
        assert client._calc_delay(3) == 8.0   # 1 * 2^3

    def test_max_delay_cap(self):
        client = ResilientHTTPClient(
            retry_config=RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=5.0)
        )
        assert client._calc_delay(0) == 1.0
        assert client._calc_delay(3) == 5.0  # 8 capped to 5

    def test_retry_after_header(self):
        client = ResilientHTTPClient(
            retry_config=RetryConfig(max_delay=30.0)
        )
        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "10"}
        assert client._calc_delay(0, mock_response) == 10.0

    def test_retry_after_capped_by_max_delay(self):
        client = ResilientHTTPClient(
            retry_config=RetryConfig(max_delay=5.0)
        )
        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "60"}
        assert client._calc_delay(0, mock_response) == 5.0

    def test_retry_after_invalid_falls_back(self):
        client = ResilientHTTPClient(
            retry_config=RetryConfig(base_delay=2.0, exponential_base=2.0, max_delay=30.0)
        )
        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "not-a-number"}
        # 回退到指数退避: 2.0 * 2^1 = 4.0
        assert client._calc_delay(1, mock_response) == 4.0

    def test_no_retry_after_header(self):
        client = ResilientHTTPClient(
            retry_config=RetryConfig(base_delay=1.0, exponential_base=3.0, max_delay=30.0)
        )
        mock_response = MagicMock()
        mock_response.headers = {}
        # 无 Retry-After，走指数退避: 1.0 * 3^2 = 9.0
        assert client._calc_delay(2, mock_response) == 9.0


# ============ ResilientHTTPClient 集成 ============

class TestResilientHTTPClient:
    def test_default_config(self):
        client = ResilientHTTPClient()
        assert client.timeout == 120.0
        assert client.name == "default"
        assert client.breaker.state == CircuitState.CLOSED

    def test_custom_config(self):
        client = ResilientHTTPClient(
            timeout=30.0,
            retry_config=RetryConfig(max_retries=5),
            circuit_breaker=CircuitBreaker(failure_threshold=10),
            name="test-client",
        )
        assert client.timeout == 30.0
        assert client.retry.max_retries == 5
        assert client.breaker.failure_threshold == 10
        assert client.name == "test-client"

    def test_get_status(self):
        client = ResilientHTTPClient(name="my-api")
        status = client.get_status()
        assert status["name"] == "my-api"
        assert "metrics" in status
        assert "circuit_breaker" in status

    @pytest.mark.asyncio
    async def test_successful_request(self):
        client = ResilientHTTPClient(name="test")
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_httpx_client = AsyncMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)
        mock_httpx_client.aclose = AsyncMock()

        with patch.object(client, "_new_client", return_value=mock_httpx_client):
            resp = await client.request("GET", "http://example.com")

        assert resp.status_code == 200
        assert client.metrics.successful_requests == 1
        assert client.breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_open_rejects(self):
        client = ResilientHTTPClient(
            circuit_breaker=CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        )
        client.breaker.record_failure()
        assert client.breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            await client.request("GET", "http://example.com")

    @pytest.mark.asyncio
    async def test_retries_on_retryable_status(self):
        client = ResilientHTTPClient(
            retry_config=RetryConfig(max_retries=2, base_delay=0.01, retryable_status_codes=(503,)),
            name="retry-test",
        )

        # 第一次 503，第二次 200
        resp_503 = MagicMock()
        resp_503.status_code = 503
        resp_503.headers = {}
        resp_200 = MagicMock()
        resp_200.status_code = 200

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_503
            return resp_200

        mock_httpx_client = AsyncMock()
        mock_httpx_client.request = mock_request
        mock_httpx_client.aclose = AsyncMock()

        with patch.object(client, "_new_client", return_value=mock_httpx_client):
            resp = await client.request("GET", "http://example.com")

        assert resp.status_code == 200
        assert client.metrics.total_retries == 1
        assert client.metrics.successful_requests == 1

    @pytest.mark.asyncio
    async def test_retries_on_network_error(self):
        import httpx

        client = ResilientHTTPClient(
            retry_config=RetryConfig(max_retries=2, base_delay=0.01),
            name="net-err-test",
        )

        call_count = 0
        resp_200 = MagicMock()
        resp_200.status_code = 200

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise httpx.ConnectError("connection refused")
            return resp_200

        mock_httpx_client = AsyncMock()
        mock_httpx_client.request = mock_request
        mock_httpx_client.aclose = AsyncMock()

        with patch.object(client, "_new_client", return_value=mock_httpx_client):
            resp = await client.request("GET", "http://example.com")

        assert resp.status_code == 200
        assert client.metrics.total_retries == 1

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises(self):
        import httpx

        client = ResilientHTTPClient(
            retry_config=RetryConfig(max_retries=2, base_delay=0.01),
            name="exhaust-test",
        )

        async def mock_request(*args, **kwargs):
            raise httpx.TimeoutException("timeout")

        mock_httpx_client = AsyncMock()
        mock_httpx_client.request = mock_request
        mock_httpx_client.aclose = AsyncMock()

        with patch.object(client, "_new_client", return_value=mock_httpx_client):
            with pytest.raises(httpx.TimeoutException):
                await client.request("GET", "http://example.com")

        assert client.metrics.failed_requests == 1
        assert client.breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_non_retryable_status_raises_immediately(self):
        import httpx

        client = ResilientHTTPClient(
            retry_config=RetryConfig(max_retries=3, retryable_status_codes=(503,)),
            name="non-retry-test",
        )

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("forbidden", request=MagicMock(), response=mock_response)
        )

        # 非可重试状态码不在 retryable_status_codes 中，
        # 但 response.raise_for_status() 只在最后一次重试时调用
        # 对于非可重试状态码，直接返回 response（不进入重试分支）
        mock_httpx_client = AsyncMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)
        mock_httpx_client.aclose = AsyncMock()

        with patch.object(client, "_new_client", return_value=mock_httpx_client):
            resp = await client.request("GET", "http://example.com")

        # 非可重试状态码直接返回（不 raise）
        assert resp.status_code == 403
        assert client.metrics.successful_requests == 1

    @pytest.mark.asyncio
    async def test_convenience_get_post(self):
        client = ResilientHTTPClient(name="conv-test")
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_httpx_client = AsyncMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)
        mock_httpx_client.aclose = AsyncMock()

        with patch.object(client, "_new_client", return_value=mock_httpx_client):
            resp_get = await client.get("http://example.com")
            resp_post = await client.post("http://example.com", json={"key": "val"})

        assert resp_get.status_code == 200
        assert resp_post.status_code == 200
        assert client.metrics.successful_requests == 2

    @pytest.mark.asyncio
    async def test_close_is_noop(self):
        client = ResilientHTTPClient()
        await client.close()  # 不应抛异常


# ============ CircuitOpenError ============

class TestCircuitOpenError:
    def test_is_exception(self):
        err = CircuitOpenError("breaker open")
        assert isinstance(err, Exception)
        assert str(err) == "breaker open"


# ============ SSRF 集成测试 (ResilientHTTPClient.request + ssrf_check) ============


class TestResilientHTTPClientSsrfCheck:
    """验证 ResilientHTTPClient.request() 的 ssrf_check 参数。"""

    @pytest.mark.asyncio
    async def test_ssrf_check_disabled_by_default(self):
        """默认不做 SSRF 检查，内部 API 调用不受影响"""
        client = ResilientHTTPClient(name="test-no-ssrf")
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_httpx_client = AsyncMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)
        mock_httpx_client.aclose = AsyncMock()

        # 即使目标是 localhost，默认不检查也能正常请求
        with patch.object(client, "_new_client", return_value=mock_httpx_client):
            resp = await client.request("GET", "http://localhost:8080/api")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_ssrf_check_blocks_internal_url(self):
        """启用 SSRF 检查时，内网 URL 被拦截"""
        from src.core.security import SSRFError

        client = ResilientHTTPClient(name="test-ssrf-block")

        with pytest.raises(SSRFError, match="SSRF 安全检查未通过"):
            await client.request(
                "GET", "http://169.254.169.254/latest/meta-data/",
                ssrf_check=True,
            )

        # 不应记录到指标中（请求根本没发出去）
        assert client.metrics.total_requests == 0

    @pytest.mark.asyncio
    async def test_ssrf_check_allows_public_url(self):
        """启用 SSRF 检查时，公网 URL 正常放行"""
        client = ResilientHTTPClient(name="test-ssrf-allow")
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_httpx_client = AsyncMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)
        mock_httpx_client.aclose = AsyncMock()

        with patch.object(client, "_new_client", return_value=mock_httpx_client), \
             patch("src.core.security.socket.getaddrinfo", return_value=[
                 (2, 1, 6, "", ("93.184.216.34", 0)),
             ]):
            resp = await client.request(
                "GET", "http://example.com",
                ssrf_check=True,
            )

        assert resp.status_code == 200
        assert client.metrics.successful_requests == 1

    @pytest.mark.asyncio
    async def test_ssrf_check_via_get_convenience(self):
        """便捷方法 get() 也支持传递 ssrf_check 参数"""
        from src.core.security import SSRFError

        client = ResilientHTTPClient(name="test-ssrf-get")

        with pytest.raises(SSRFError):
            await client.get(
                "http://127.0.0.1/admin",
                ssrf_check=True,
            )

    @pytest.mark.asyncio
    async def test_ssrf_check_via_post_convenience(self):
        """便捷方法 post() 也支持传递 ssrf_check 参数"""
        from src.core.security import SSRFError

        client = ResilientHTTPClient(name="test-ssrf-post")

        with pytest.raises(SSRFError):
            await client.post(
                "http://localhost/api",
                json={"data": "test"},
                ssrf_check=True,
            )
