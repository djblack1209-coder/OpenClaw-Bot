from fastapi.testclient import TestClient

from src.api.server import APIServer
from src.xianyu import xianyu_admin


def test_memory_search_accepts_q_alias(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)

    monkeypatch.setattr(
        "src.api.routers.memory.ClawBotRPC._rpc_memory_search",
        lambda query, limit=10, mode="hybrid", category=None: {
            "query": query,
            "mode": mode,
            "results": [],
            "total_count": 0,
        },
    )

    response = client.get("/api/v1/memory/search?q=test&limit=5")

    assert response.status_code == 200
    assert response.json()["query"] == "test"


def test_memory_delete_route_exists(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)

    monkeypatch.setattr(
        "src.api.routers.memory.ClawBotRPC._rpc_memory_delete",
        lambda key: {"success": True, "deleted": 1, "key": key},
    )

    response = client.post("/api/v1/memory/delete", json={"key": "demo_key"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["key"] == "demo_key"


def test_memory_update_route_exists(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)

    monkeypatch.setattr(
        "src.api.routers.memory.ClawBotRPC._rpc_memory_update",
        lambda key, value: {"success": True, "key": key, "value": value},
    )

    response = client.post(
        "/api/v1/memory/update",
        json={"key": "demo_key", "value": "updated"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["value"] == "updated"


def test_social_browser_status_route_exists(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)

    monkeypatch.setattr(
        "src.api.routers.social.ClawBotRPC._rpc_social_browser_status",
        lambda: {"x": "ready", "xhs": "login_needed", "browser_running": True},
    )

    response = client.get("/api/v1/social/browser-status")

    assert response.status_code == 200
    assert response.json()["x"] == "ready"
    assert response.json()["xhs"] == "login_needed"


def test_social_analytics_route_exists(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)

    monkeypatch.setattr(
        "src.api.routers.social.ClawBotRPC._rpc_social_analytics",
        lambda days=7: {"engagement": {}, "follower_growth": {}, "top_posts": [], "days": days},
    )

    response = client.get("/api/v1/social/analytics?days=7")

    assert response.status_code == 200
    assert response.json()["days"] == 7
    assert response.json()["top_posts"] == []


def test_trading_dashboard_returns_chart_data_when_assets_exist(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)

    async def _fake_dashboard():
        return {
            "chart_data": [{"name": "现在", "value": 12345.67}],
            "assets": [{"name": "AAPL", "value": 12345.67, "pnl": 5.2}],
            "connected": True,
        }

    monkeypatch.setattr(
        "src.api.routers.trading.ClawBotRPC._rpc_trading_dashboard",
        _fake_dashboard,
    )

    response = client.get("/api/v1/trading/dashboard")

    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert response.json()["chart_data"][0]["value"] == 12345.67


def test_trading_dashboard_builds_chart_from_journal(monkeypatch):
    from src.api.rpc import ClawBotRPC

    class _FakeIbkr:
        connected = False

    class _FakeJournal:
        def get_equity_curve(self, days=30):
            return ([10000.0, 10125.5], ["04-09", "04-10"])

    monkeypatch.setattr("src.broker_selector.ibkr", _FakeIbkr(), raising=False)
    monkeypatch.setattr("src.trading_journal.journal", _FakeJournal(), raising=False)

    # 直接调用 RPC，验证它不再返回永久空图
    import asyncio
    result = asyncio.run(ClawBotRPC._rpc_trading_dashboard())

    assert result["chart_data"] == [
        {"name": "04-09", "value": 10000.0},
        {"name": "04-10", "value": 10125.5},
    ]
    assert result["connected"] is False


def test_xianyu_admin_masks_internal_errors(monkeypatch):
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._ctx",
        object(),
    )

    class _BrokenContext:
        def daily_stats(self, _date):
            raise RuntimeError("/secret/path/db.sqlite boom")

    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._get_ctx",
        lambda: _BrokenContext(),
    )

    client = TestClient(xianyu_admin.app)
    response = client.get("/api/dashboard")

    assert response.status_code == 500
    assert response.json()["detail"] == "内部服务错误，请稍后重试"
