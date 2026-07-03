import sys
import types
import pytest
from fastapi.testclient import TestClient

from src.api.server import APIServer
from src.xianyu import xianyu_admin

# starlette TestClient 在旧版 httpx 上会报 app kwarg 不兼容
# Python 3.9 + starlette 0.27 环境下无法初始化，跳过整个文件
_skip = False
try:
    _server = APIServer()
    _client = TestClient(_server.app)
    del _server, _client
except TypeError:
    _skip = True

pytestmark = pytest.mark.skipif(_skip, reason="starlette/httpx 版本与 Python 3.9 不兼容")


@pytest.fixture(autouse=True)
def api_dev_auth_mode(monkeypatch):
    """固定 API 回归测试为无 Token 开发模式，避免本机 .env 污染鉴权状态。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "")
    monkeypatch.setattr("src.api.auth._warned_no_token", False)


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


def test_cookiecloud_sync_all_treats_unconfigured_service_as_optional(monkeypatch):
    """CookieCloud 未配置时一键同步不报错，明确提示这是可选增强。"""
    for name in ("COOKIECLOUD_HOST", "COOKIECLOUD_UUID", "COOKIECLOUD_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    server = APIServer()
    client = TestClient(server.app)

    response = client.post("/api/v1/cookies/sync-all")

    assert response.status_code == 200
    body = response.json()
    assert body["sync_results"]["cookiecloud"]["success"] is False
    assert "可选" in body["sync_results"]["cookiecloud"]["message"]


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




def test_social_extension_trends_route_returns_candidates(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)

    monkeypatch.setattr(
        'src.api.routers.social.ClawBotRPC._rpc_social_extension_trends',
        lambda platform='x', limit=8: {
            'success': True,
            'platform': platform,
            'count': 1,
            'trends': [{'title': 'GitHub 一周异常 Star 工具榜'}],
            'auto_publish_enabled': False,
            'external_actions_locked': True,
        },
    )

    response = client.get('/api/v1/social/extension/trends?platform=x&limit=3')

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['platform'] == 'x'
    assert data['trends'][0]['title'] == 'GitHub 一周异常 Star 工具榜'
    assert data['auto_publish_enabled'] is False

def test_social_extension_draft_patch_accepts_json_body(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_update(draft_id, text='', title=''):
        captured['draft_id'] = draft_id
        captured['text'] = text
        captured['title'] = title
        return {
            'success': True,
            'draft': {'id': draft_id, 'text': text, 'title': title},
            'auto_publish_enabled': False,
            'external_actions_locked': True,
        }

    monkeypatch.setattr(
        'src.api.routers.social.ClawBotRPC._rpc_social_extension_draft_update',
        _fake_update,
    )

    response = client.patch(
        '/api/v1/social/extension/drafts/ext-x-demo',
        json={'title': '美股回调别慌', 'text': '这是从插件编辑器保存的长正文。'},
    )

    assert response.status_code == 200
    assert response.json()['success'] is True
    assert captured == {
        'draft_id': 'ext-x-demo',
        'title': '美股回调别慌',
        'text': '这是从插件编辑器保存的长正文。',
    }

def test_store_catalog_route_exists_and_returns_summary():
    server = APIServer()
    client = TestClient(server.app)

    response = client.get("/api/v1/store/catalog")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["skills"], list)
    assert isinstance(data["extensions"], list)
    assert isinstance(data["bot_skills"], list)
    assert data["summary"]["total"] == (
        data["summary"]["total_skills"]
        + data["summary"]["total_extensions"]
        + data["summary"]["total_bot_skills"]
    )


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


def test_rpc_yfinance_price_helper_deduplicates_and_uses_previous_close(monkeypatch):
    from src.api import rpc

    class _FastInfo:
        last_price = 0
        previous_close = 123.45

    class _Ticker:
        fast_info = _FastInfo()

    class _Tickers:
        def __init__(self, symbols):
            assert symbols == "AAPL MSFT"
            self.tickers = {"AAPL": _Ticker(), "MSFT": _Ticker()}

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Tickers=_Tickers))

    assert rpc._fetch_yfinance_prices(["AAPL", "AAPL", "MSFT"]) == {
        "AAPL": 123.45,
        "MSFT": 123.45,
    }


def test_social_cookie_helper_supports_known_cookie_formats(monkeypatch, tmp_path):
    from src.api import rpc

    cookie_dir = tmp_path / ".openclaw"
    cookie_dir.mkdir()
    monkeypatch.setattr(rpc.Path, "home", lambda: tmp_path)

    (cookie_dir / "x_cookies.json").write_text("{}", encoding="utf-8")
    assert rpc._is_social_cookie_ready("x") is False

    (cookie_dir / "x_cookies.json").write_text('{"auth": "ok"}', encoding="utf-8")
    assert rpc._is_social_cookie_ready("x") is True

    (cookie_dir / "xhs_cookies.json").write_text('{"a1": "token"}', encoding="utf-8")
    assert rpc._is_social_cookie_ready("xhs") is True
    assert rpc._is_social_cookie_ready("xhs", allow_xhs_a1=False) is False

    (cookie_dir / "xhs_cookies.json").write_text('{"cookie": "web_session=ok"}', encoding="utf-8")
    assert rpc._is_social_cookie_ready("xhs", allow_xhs_a1=False) is True


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


def test_xianyu_admin_page_escapes_dynamic_fields():
    client = TestClient(xianyu_admin.app)

    response = client.get("/")
    page = response.text

    assert "function escapeHtml(value)" in page
    assert "${escapeHtml(String(c.last_msg||'').slice(0,40))}" in page
    assert "${escapeHtml(o.status)}" in page
    assert "${c.last_msg.slice(0,40)}" not in page
    assert "${o.status}" not in page


def test_social_extension_page_probe_route_accepts_json_body(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_probe(payload):
        captured.update(payload)
        return {
            'success': True,
            'platform': payload.get('platform'),
            'ready': bool(payload.get('ready')),
            'auto_publish_enabled': False,
            'external_actions_locked': True,
        }

    monkeypatch.setattr(
        'src.api.routers.social.ClawBotRPC._rpc_social_extension_page_probe_update',
        _fake_probe,
    )

    response = client.post(
        '/api/v1/social/extension/page-probe',
        json={'platform': 'xhs', 'ready': True, 'availableFields': [{'name': 'title'}]},
    )

    assert response.status_code == 200
    assert response.json()['success'] is True
    assert captured['platform'] == 'xhs'
    assert captured['ready'] is True


def test_social_persona_review_route_accepts_json_body(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_review(approved=True, reviewer='owner', notes=''):
        captured['approved'] = approved
        captured['reviewer'] = reviewer
        captured['notes'] = notes
        return {
            'success': True,
            'approved': approved,
            'auto_publish_enabled': False,
            'external_actions_locked': True,
        }

    monkeypatch.setattr(
        'src.api.routers.social.ClawBotRPC._rpc_social_persona_review_update',
        _fake_review,
    )

    response = client.post(
        '/api/v1/social/persona-review',
        json={'approved': False, 'reviewer': 'owner', 'notes': '方向太 AI，继续追热点抽象。'},
    )

    assert response.status_code == 200
    assert response.json()['success'] is True
    assert captured == {
        'approved': False,
        'reviewer': 'owner',
        'notes': '方向太 AI，继续追热点抽象。',
    }


def test_social_extension_draft_schedule_route_accepts_json_body(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_schedule(draft_id, scheduled_at='', reviewer='owner'):
        captured['draft_id'] = draft_id
        captured['scheduled_at'] = scheduled_at
        captured['reviewer'] = reviewer
        return {
            'success': True,
            'schedule_item': {'draft_id': draft_id, 'scheduled_at': scheduled_at},
            'auto_publish_enabled': False,
            'external_actions_locked': True,
        }

    monkeypatch.setattr(
        'src.api.routers.social.ClawBotRPC._rpc_social_extension_draft_schedule',
        _fake_schedule,
    )

    response = client.post(
        '/api/v1/social/extension/drafts/ext-x-demo/schedule',
        json={'scheduled_at': '2026-06-24T08:30:00-06:00', 'reviewer': 'owner'},
    )

    assert response.status_code == 200
    assert response.json()['success'] is True
    assert captured == {
        'draft_id': 'ext-x-demo',
        'scheduled_at': '2026-06-24T08:30:00-06:00',
        'reviewer': 'owner',
    }


def test_social_extension_schedule_route_returns_queue(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_queue(limit=20):
        captured['limit'] = limit
        return {
            'success': True,
            'count': 1,
            'due_count': 1,
            'queue': [
                {
                    'draft_id': 'ext-x-due',
                    'platform': 'x',
                    'title': '到点提醒',
                    'status': 'awaiting_final_confirmation',
                    'draft': {'id': 'ext-x-due', 'title': '到点提醒'},
                }
            ],
            'auto_publish_enabled': False,
            'external_actions_locked': True,
        }

    monkeypatch.setattr(
        'src.api.routers.social.ClawBotRPC._rpc_social_extension_schedule_queue',
        _fake_queue,
    )

    response = client.get('/api/v1/social/extension/schedule?limit=12')

    assert response.status_code == 200
    assert response.json()['success'] is True
    assert response.json()['queue'][0]['draft']['id'] == 'ext-x-due'
    assert response.json()['auto_publish_enabled'] is False
    assert captured == {'limit': 12}


def test_social_extension_schedule_final_confirm_route_exists(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_confirm(draft_id, reviewer='owner'):
        captured['draft_id'] = draft_id
        captured['reviewer'] = reviewer
        return {
            'success': True,
            'manual_publish_ready': True,
            'auto_publish_enabled': False,
            'external_actions_locked': True,
        }

    monkeypatch.setattr(
        'src.api.routers.social.ClawBotRPC._rpc_social_extension_schedule_final_confirm',
        _fake_confirm,
    )

    response = client.post(
        '/api/v1/social/extension/drafts/ext-x-final/final-confirm',
        json={'reviewer': 'owner'},
    )

    assert response.status_code == 200
    assert response.json()['success'] is True
    assert captured == {'draft_id': 'ext-x-final', 'reviewer': 'owner'}
