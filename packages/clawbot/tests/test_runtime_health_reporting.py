import json
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from src.monitoring.health import HealthChecker
from src.monitoring.metrics import start_metrics_server


def test_stopped_polling_does_not_refresh_bot_heartbeat():
    """轮询已经停止时，Bot 实例仍存在也不能伪造新心跳。"""
    checker = HealthChecker()
    with patch("src.monitoring.health.time.time", return_value=100.0):
        checker.register_bot("stopped-bot")

    app = SimpleNamespace(running=True, updater=SimpleNamespace(running=False))
    with patch("src.monitoring.health.time.time", return_value=200.0):
        refreshed = checker.heartbeat_if_polling("stopped-bot", app)
        status = checker.get_status()["stopped-bot"]

    assert refreshed is False
    assert status["last_heartbeat_ago"] == 100.0


def test_running_polling_refreshes_bot_heartbeat():
    """Application 与轮询器都运行时应正常刷新心跳。"""
    checker = HealthChecker()
    with patch("src.monitoring.health.time.time", return_value=100.0):
        checker.register_bot("running-bot")

    app = SimpleNamespace(running=True, updater=SimpleNamespace(running=True))
    with patch("src.monitoring.health.time.time", return_value=200.0):
        refreshed = checker.heartbeat_if_polling("running-bot", app)
        status = checker.get_status()["running-bot"]

    assert refreshed is True
    assert status["last_heartbeat_ago"] == 0.0


def test_health_endpoint_reads_live_component_state():
    """健康端点应按实时组件状态返回状态码和明细。"""
    components = {"bot": "running", "api": "stopped"}
    server = start_metrics_server(port=0, health_provider=lambda: dict(components))
    health_url = f"http://127.0.0.1:{server.server_port}/health"

    try:
        try:
            urlopen(health_url, timeout=2)
        except HTTPError as exc:
            degraded_code = exc.code
            degraded_payload = json.loads(exc.read())
        else:
            raise AssertionError("组件停止时 /health 不应返回成功状态码")

        components["api"] = "running"
        with urlopen(health_url, timeout=2) as response:
            healthy_code = response.status
            healthy_payload = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()

    assert degraded_code == 503
    assert degraded_payload["status"] == "degraded"
    assert degraded_payload["components"] == {"bot": "running", "api": "stopped"}
    assert healthy_code == 200
    assert healthy_payload["status"] == "ok"
    assert healthy_payload["components"] == {"bot": "running", "api": "running"}
