"""ClawBot API 中间件的来源信任与容量边界测试。"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.server import RateLimitMiddleware


def _request(direct_ip: str, headers: dict[str, str] | None = None):
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host=direct_ip),
    )


def test_untrusted_direct_client_cannot_spoof_forwarded_source():
    middleware = RateLimitMiddleware(AsyncMock(), trusted_proxy_ips=set())
    request = _request(
        "203.0.113.10",
        {"x-forwarded-for": "198.51.100.20", "x-real-ip": "198.51.100.21"},
    )

    assert middleware._get_client_ip(request) == "203.0.113.10"


def test_trusted_proxy_walks_forwarded_chain_from_the_socket_boundary():
    middleware = RateLimitMiddleware(
        AsyncMock(),
        trusted_proxy_ips={"127.0.0.1", "10.0.0.2"},
    )
    request = _request(
        "127.0.0.1",
        {"x-forwarded-for": "198.51.100.20, 10.0.0.2"},
    )

    assert middleware._get_client_ip(request) == "198.51.100.20"


@pytest.mark.asyncio
async def test_rate_limit_table_rejects_new_clients_at_hard_capacity():
    middleware = RateLimitMiddleware(
        AsyncMock(),
        max_requests=300,
        window_seconds=60,
        max_clients=2,
    )
    now = time.monotonic()
    middleware._request_log["198.51.100.1"] = [now]
    middleware._request_log["198.51.100.2"] = [now]
    call_next = AsyncMock()

    response = await middleware.dispatch(_request("198.51.100.3"), call_next)

    assert response.status_code == 429
    assert len(middleware._request_log) == 2
    call_next.assert_not_awaited()
