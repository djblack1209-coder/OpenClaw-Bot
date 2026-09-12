"""Actual application bind/auth contract; no listening sockets or live services."""
import ast
import types
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.auth import verify_api_token
from src.api.server import APIServer


@pytest.mark.parametrize(('host', 'env_host', 'mode', 'token', 'given', 'status'), [
    ('0.0.0.0', '127.0.0.1', 'development', '', '', 503),
    ('127.0.0.1', '0.0.0.0', 'development', '', '', 200),
    ('::', '::1', 'development', '', '', 503),
    ('::1', '::', 'development', '', '', 200),
    ('[::1]', '0.0.0.0', 'development', '', '', 200),
    ('localhost', '0.0.0.0', 'development', '', '', 200),
    ('127.0.0.1', '127.0.0.1', 'production', '', '', 503),
    ('::1', '::1', 'prod', '', '', 503),
    ('127.0.0.1', '127.0.0.1', 'unknown-mode', '', '', 503),
    ('0.0.0.0', '127.0.0.1', 'production', 'synthetic-token', '', 401),
    ('0.0.0.0', '127.0.0.1', 'production', 'synthetic-token', 'wrong', 401),
    ('0.0.0.0', '127.0.0.1', 'production', 'synthetic-token', 'synthetic-token', 200),
    ('127.0.0.1', '0.0.0.0', 'development', 'synthetic-token', 'wrong', 401),
    ('::1', '::', 'development', 'synthetic-token', 'synthetic-token', 200),
    (None, '0.0.0.0', 'development', '', '', 503),
])
def test_actual_http_and_websocket_bind_policy(monkeypatch, host, env_host, mode, token, given, status):
    monkeypatch.setenv('API_HOST', env_host)
    monkeypatch.setenv('ENV', mode)
    monkeypatch.setenv('OPENCLAW_API_TOKEN', token)
    monkeypatch.setattr('src.api.rpc.ClawBotRPC._rpc_system_status', lambda: {'synthetic': True})
    server = APIServer(**({'host': host} if host is not None else {}))
    with TestClient(server.app) as client:
        assert client.get('/api/v1/ping', headers={'X-API-Token': given, 'Host': 'localhost', 'X-Forwarded-Host': 'localhost'}).status_code == status
        if status == 200:
            with client.websocket_connect('/api/v1/events?token=' + given) as websocket:
                assert websocket.receive_json()['data'] == {'synthetic': True}
        else:
            with pytest.raises(WebSocketDisconnect) as error:
                with client.websocket_connect('/api/v1/events?token=' + given):
                    pytest.fail('Unauthenticated WebSocket accepted')
            assert error.value.code == 1008
        # Legacy HTTP aliases have the same dependency, even before body validation.
        if status != 200:
            assert client.post('/wechat/incoming', json={}, headers={'X-API-Token': given}).status_code == status


def test_instances_snapshot_configuration_without_global_contamination(monkeypatch):
    monkeypatch.setenv('API_HOST', '127.0.0.1')
    monkeypatch.setenv('ENV', 'development')
    monkeypatch.setenv('OPENCLAW_API_TOKEN', 'synthetic-first')
    first = APIServer()
    monkeypatch.setenv('API_HOST', '0.0.0.0')
    monkeypatch.setenv('ENV', 'production')
    monkeypatch.setenv('OPENCLAW_API_TOKEN', 'synthetic-second')
    second = APIServer()
    monkeypatch.setenv('OPENCLAW_API_TOKEN', '')
    with TestClient(first.app) as a, TestClient(second.app) as b:
        for client, own, other in [(a, 'synthetic-first', 'synthetic-second'), (b, 'synthetic-second', 'synthetic-first')]:
            assert client.get('/api/v1/ping', headers={'X-API-Token': own}).status_code == 200
            assert client.get('/api/v1/ping', headers={'X-API-Token': other}).status_code == 401
            assert client.get('/api/v1/ping').status_code == 401
    assert first.host == '127.0.0.1'
    assert second.host == '0.0.0.0'
    assert 'synthetic-first' not in repr(first.auth_context)


def test_missing_trusted_application_context_rejects(monkeypatch):
    monkeypatch.setenv('ENV', 'development')
    monkeypatch.setenv('API_HOST', '127.0.0.1')
    monkeypatch.setenv('OPENCLAW_API_TOKEN', '')
    app = FastAPI(dependencies=[Depends(verify_api_token)])
    app.get('/probe')(lambda: {'ok': True})
    with TestClient(app) as client:
        assert client.get('/probe').status_code == 503


def test_start_passes_same_effective_host_to_uvicorn(monkeypatch):
    from src.api import server as module
    monkeypatch.setenv('API_HOST', '::1')
    monkeypatch.setenv('ENV', 'development')
    monkeypatch.setenv('OPENCLAW_API_TOKEN', '')
    seen = {}
    monkeypatch.setattr(module.uvicorn, 'Config', lambda **kwargs: seen.update(kwargs) or kwargs)
    monkeypatch.setattr(module.uvicorn, 'Server', lambda config: types.SimpleNamespace(run=lambda: None))
    monkeypatch.setattr(module.threading, 'Thread', lambda **kwargs: types.SimpleNamespace(start=lambda: None))
    server = APIServer()
    server.start()
    assert seen['host'] == '::1' == server.host == server.auth_context.host
    assert seen['app'] is server.app


def test_main_api_wiring_uses_configured_address_without_startup(monkeypatch):
    """Execute only the actual startup statement through an inert launcher."""
    import os
    source = Path('multi_main.py').read_text()
    tree = ast.parse(source)
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                and node.value.func.id == 'start_api_server')
    monkeypatch.setenv('API_HOST', '0.0.0.0')
    seen = {}
    exec(compile(ast.Module(body=[call], type_ignores=[]), '<api startup wiring>', 'exec'),
         {'os': os, 'api_port': 18790, 'start_api_server': lambda **kwargs: seen.update(kwargs)})
    # A None/omitted host delegates environment resolution to the shared constructor.
    app = APIServer(**seen)
    assert app.host == '0.0.0.0'
