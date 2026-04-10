from fastapi.testclient import TestClient

from src.api.server import APIServer


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
