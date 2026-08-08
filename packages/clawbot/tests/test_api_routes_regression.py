import json
import re
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import auth as api_auth
from src.api.routers import trading as trading_router
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


def _connected_xianyu_runtime_snapshot(timeout: float = 5.0) -> dict:
    assert timeout == 5.0
    return {
        "ws_connected": True,
        "cookie_ok": True,
        "last_heartbeat": 0.0,
        "token_ts": 0.0,
        "manual_chats": 0,
    }


@pytest.fixture(autouse=True)
def api_dev_auth_mode(monkeypatch, tmp_path):
    """固定 API 回归测试为无 Token 开发模式，避免本机 .env 污染鉴权状态。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("CC_OPERATOR_STATE_FILE", str(tmp_path / "cc-operator-state.json"))
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_PAUSED", "0")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "")
    monkeypatch.setattr("src.api.auth._warned_no_token", False)
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_cc_strict_audit", {})
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_cc_readiness_audit", {})
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_background_strict_audit_at", 0.0)
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_background_strict_audit_result", {})
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_background_readiness_audit_at", 0.0)
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_ops_notify_signature", "")
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_ops_notify_at", 0.0)
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_ops_notify_result", {})


@pytest.mark.parametrize(
    ("env_mode", "bind_host"),
    [
        ("production", "127.0.0.1"),
        ("prod", "127.0.0.1"),
        ("development", "0.0.0.0"),
    ],
)
def test_websocket_without_token_fails_closed_outside_local_development(
    monkeypatch,
    env_mode,
    bind_host,
):
    """生产环境或外网绑定时，WebSocket 未配置 Token 必须拒绝连接。"""
    monkeypatch.setattr(api_auth, "_API_TOKEN", "")
    monkeypatch.setenv("ENV", env_mode)
    monkeypatch.setenv("API_HOST", bind_host)
    websocket = types.SimpleNamespace(query_params={})

    assert api_auth.verify_ws_token(websocket) is False


def test_websocket_without_token_allows_local_development(monkeypatch):
    """本机开发模式可保持无 Token 调试能力。"""
    monkeypatch.setattr(api_auth, "_API_TOKEN", "")
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "localhost")
    websocket = types.SimpleNamespace(query_params={})

    assert api_auth.verify_ws_token(websocket) is True


@pytest.mark.parametrize(
    ("env_mode", "actual_bind_host"),
    [
        ("production", "127.0.0.1"),
        ("prod", "127.0.0.1"),
        ("development", "0.0.0.0"),
    ],
)
def test_xianyu_admin_without_token_fails_closed_from_actual_bind_host(
    monkeypatch,
    env_mode,
    actual_bind_host,
):
    """闲鱼独立管理面必须使用真实监听地址，并识别 production/prod。"""
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", env_mode)
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr(xianyu_admin.app.state, "bind_host", actual_bind_host, raising=False)
    client = TestClient(xianyu_admin.app)

    response = client.get("/api/auth-contract-probe")

    assert response.status_code == 503
    assert "拒绝所有请求" in response.json()["detail"]


def test_websocket_configured_token_accepts_only_exact_match(monkeypatch):
    """配置 Token 后，仅精确匹配的查询参数可通过。"""
    monkeypatch.setattr(api_auth, "_API_TOKEN", "unit-secret")

    assert api_auth.verify_ws_token(types.SimpleNamespace(query_params={"token": "wrong-secret"})) is False
    assert api_auth.verify_ws_token(types.SimpleNamespace(query_params={"token": "unit-secret"})) is True


@pytest.mark.asyncio
async def test_http_and_websocket_share_no_token_fail_closed_policy(monkeypatch):
    """HTTP 与 WebSocket 必须复用同一条无 Token 生产安全策略。"""
    monkeypatch.setattr(api_auth, "_API_TOKEN", "")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    connection = types.SimpleNamespace(scope={"type": "http"}, headers={})
    websocket = types.SimpleNamespace(query_params={})

    with pytest.raises(HTTPException) as error:
        await api_auth.verify_api_token(connection)

    assert error.value.status_code == 503
    assert api_auth.verify_ws_token(websocket) is False


@pytest.mark.parametrize(
    "broker_result",
    [
        {"status": "Cancelled", "filled_qty": 0, "avg_price": 0, "order_id": 1},
        {"status": "Inactive", "filled_qty": 0, "avg_price": 0, "order_id": 2},
        {"status": "Filled", "filled_qty": 0, "avg_price": 0, "order_id": 3},
        {
            "status": "Submitted",
            "filled_qty": 0,
            "avg_price": 0,
            "order_id": 4,
            "broker_result_ambiguous": True,
        },
    ],
)
async def test_manual_sell_fails_closed_for_rejected_or_ambiguous_broker_result(
    monkeypatch,
    broker_result,
):
    bridge = MagicMock()
    bridge.is_connected.return_value = True
    bridge.sell = AsyncMock(return_value=broker_result)
    monkeypatch.setattr("src.broker_selector.ibkr", bridge)
    monkeypatch.setattr(trading_router, "push_event", MagicMock())

    result = await trading_router.sell_position(
        trading_router.SellRequest(symbol="AAPL", quantity=1, order_type="MKT")
    )

    assert result["success"] is False


async def test_manual_sell_reports_only_explicitly_accepted_order_as_success(monkeypatch):
    bridge = MagicMock()
    bridge.is_connected.return_value = True
    bridge.sell = AsyncMock(
        return_value={
            "status": "Submitted",
            "filled_qty": 0,
            "avg_price": 0,
            "order_id": 5,
            "order_type": "MKT",
        }
    )
    monkeypatch.setattr("src.broker_selector.ibkr", bridge)
    monkeypatch.setattr(trading_router, "push_event", MagicMock())

    result = await trading_router.sell_position(
        trading_router.SellRequest(symbol="AAPL", quantity=1, order_type="MKT")
    )

    assert result["success"] is True
    assert result["status"] == "Submitted"


def test_api_cors_allows_chrome_extension_origin_for_social_status():
    """Chrome 扩展页需要访问本机 18790，同步发货助手能力。"""
    server = APIServer()
    client = TestClient(server.app)

    response = client.options(
        "/api/v1/social/extension/status",
        headers={
            "Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-token, content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "chrome-extension://abcdefghijklmnopabcdefghijklmnop"


def test_api_cors_rejects_unlisted_web_origin_for_social_status():
    """不能为了插件把所有外部网页来源放开。"""
    server = APIServer()
    client = TestClient(server.app)

    response = client.options(
        "/api/v1/social/extension/status",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-token, content-type",
        },
    )

    assert response.status_code == 400


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
        "src.api.routers.social.ClawBotRPC._rpc_social_extension_trends",
        lambda platform="x", limit=8: {
            "success": True,
            "platform": platform,
            "count": 1,
            "trends": [{"title": "GitHub 一周异常 Star 工具榜"}],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        },
    )

    response = client.get("/api/v1/social/extension/trends?platform=x&limit=3")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["platform"] == "x"
    assert data["trends"][0]["title"] == "GitHub 一周异常 Star 工具榜"
    assert data["auto_publish_enabled"] is False


def test_social_extension_draft_patch_accepts_json_body(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_update(draft_id, text="", title=""):
        captured["draft_id"] = draft_id
        captured["text"] = text
        captured["title"] = title
        return {
            "success": True,
            "draft": {"id": draft_id, "text": text, "title": title},
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }

    monkeypatch.setattr(
        "src.api.routers.social.ClawBotRPC._rpc_social_extension_draft_update",
        _fake_update,
    )

    response = client.patch(
        "/api/v1/social/extension/drafts/ext-x-demo",
        json={"title": "美股回调别慌", "text": "这是从插件编辑器保存的长正文。"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured == {
        "draft_id": "ext-x-demo",
        "title": "美股回调别慌",
        "text": "这是从插件编辑器保存的长正文。",
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
        data["summary"]["total_skills"] + data["summary"]["total_extensions"] + data["summary"]["total_bot_skills"]
    )


def test_store_project_root_supports_flat_container_layout():
    """容器把 ClawBot 放在 /app 时，商店路由必须可导入并安全降级。"""
    from src.api.routers import store

    assert store._resolve_project_root(Path("/app/src/api/routers/store.py")) == Path("/app")


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

    assert "CC中转操作台" in page
    assert "/static/layui/css/layui.css" in page
    assert "/static/layui/layui.js" in page
    assert "layui.use" in page
    assert "layui-card" in page
    assert "layui-table" in page
    assert "https://cdn" not in page
    assert "unpkg.com" not in page
    assert "今天能不能卖，一眼看懂" in page
    assert "首屏只回答老板每天关心的 6 件事" in page
    assert "function escapeHtml(value)" in page
    assert "需要本机 API Token" in page
    assert "function apiFetch" in page
    assert "老板日常状态卡" in page
    assert "当前能不能卖" in page
    assert "人工预检证据" in page
    assert "CF、邮箱、重复发卡、自动发货、1:1 额度、严格门" in page
    assert "function renderPrecheck" in page
    assert "function mergeLockWithPrecheck" in page
    assert "precheck?.state==='paused_after_strict_gate'" in page
    assert "const displayLock=mergeLockWithPrecheck(lock,precheck)" in page
    assert "/api/cc-manual-precheck-evidence" in page
    assert "不发卡、不点击闲鱼发货、不恢复自动发货" in page
    assert 'id="top-alerts"' in page
    assert "function renderTopAlerts" in page
    assert "function scrollToSection" in page
    assert "有卡密没成功发给买家" in page
    assert "自动发货仍处于暂停保护" in page
    assert "严格门已通过，自动发货暂停保护" in page
    assert "不是系统故障，只是防重复发卡保护" in page
    assert "待你恢复自动发货" in page
    assert "恢复后第 1 单会自动暂停观察" in page
    assert "严格门已过，等待恢复自动发货" in page
    assert "闲鱼登录或连接需要检查" in page
    assert "可售卡密库存不足" in page
    assert "怎么办" in page
    assert 'aria-live="polite"' in page
    assert "上游余额" in page
    assert "正式售卖资格" in page
    assert "已付款漏单兜底" in page
    assert "真实待发货扫单" in page
    assert "只读扫真实待发货订单" in page
    assert "/api/cc-paid-order-probe" in page
    assert "function probePaidOrders" in page
    assert "商品绑定" in page
    assert "补救队列" in page
    assert "暂停自动发货" in page
    assert "只放行一次发卡" in page
    assert "一键跑当前页" in page
    assert "只读检查当前页" in page
    assert "请只保留 1 个真实已付款闲鱼页" in page
    assert "打开闲鱼消息" in page
    assert "https://www.goofish.com/im?spm=a21ybx.seo.sitemap.3" in page
    assert "打开卖家工作台" in page
    assert "https://seller.goofish.com/" in page
    assert "function xianyuPageShortcutHtml" in page
    assert "function renderSellerScanMessage" in page
    assert "function openSellerPage" in page
    assert "/api/cc-seller-bridge/open-page" in page
    assert "打开卖家 Chromium 的闲鱼消息" in page
    assert "打开卖家 Chromium 的工作台" in page
    assert "恢复自动发货" in page
    assert "/api/cc-operator-mode/one-shot-delivery" in page
    assert "/api/cc-seller-bridge/one-shot-delivery" in page
    assert "/api/cc-seller-bridge/page-scan" in page
    assert "function authorizeOneShotDelivery" in page
    assert "function runOneShotBridge" in page
    assert "function scanSellerPage" in page
    assert "data.nextAction||first.reason" in page
    assert "first.reason||data.nextAction" not in page
    assert "商品模板与巡检" in page
    assert "高级排障" in page
    assert "运行内测巡检" in page
    assert "运行正式售卖严格门" in page
    assert "/api/cc-ops-snapshot" in page
    assert "/api/cc-public-sale-lock" in page
    assert "/api/cc-operator-mode" in page
    assert "/api/status" in page
    assert "/api/cc-product-template?" in page
    assert "/api/cc-readiness-audit?mode=" in page
    assert "apiFetch('/api/items')" in page
    assert "function resendShipment" in page
    assert "function confirmShipmentBackend" in page
    assert "/confirm-xianyu-backend" in page
    assert "后端确认发货" in page
    assert "function runReadinessAudit" in page
    assert "function generateProductTemplate" in page
    assert "function renderMode" in page
    assert "const strictPaused=lock.state==='paused_after_strict_gate'" in page
    assert "function renderMappings" in page
    assert "function renderShipments" in page
    assert "!['confirmed','skipped'].includes(String(s.xianyu_confirm_status||''))" in page
    assert "function setPause" in page
    assert "恢复前安全检查" in page
    assert "function checkResumePreflight" in page
    assert "/api/cc-operator-mode/resume-preflight" in page
    assert "function explainApiError" in page
    assert "恢复前预检未通过" in page
    assert "系统会先检查严格门、库存、补救队列和闲鱼登录状态" in page
    assert "系统已开启首单观察" in page
    assert "第 1 单发卡成功后会自动暂停" in page
    assert "function saveMapping" in page
    assert "function extractItemId" in page
    assert "重试发送" in page
    assert "${c.last_msg.slice(0,40)}" not in page
    assert "${o.status}" not in page


def test_xianyu_admin_serves_local_layui_assets():
    """18800 操作台使用本机 layui 资源，避免本机 Token 页面加载外部 CDN。"""
    client = TestClient(xianyu_admin.app)

    css = client.get("/static/layui/css/layui.css")
    js = client.get("/static/layui/layui.js")

    assert css.status_code == 200
    assert js.status_code == 200
    assert "layui" in css.text.lower()
    assert "layui" in js.text.lower()


def test_xianyu_admin_serves_local_layui_assets_without_api_token(monkeypatch):
    """页面可免登录打开时，layui 静态资源也必须免 Token，否则浏览器会白屏降级。"""
    monkeypatch.setattr("src.api.auth._API_TOKEN", "unit-secret")
    client = TestClient(xianyu_admin.app)

    css = client.get("/static/layui/css/layui.css")
    js = client.get("/static/layui/layui.js")

    assert css.status_code == 200
    assert js.status_code == 200
    assert "layui" in css.text.lower()
    assert "layui" in js.text.lower()


def test_xianyu_admin_page_opens_without_token_but_api_requires_token(monkeypatch):
    monkeypatch.setattr("src.api.auth._API_TOKEN", "unit-secret")
    client = TestClient(xianyu_admin.app)

    page = client.get("/")
    assert page.status_code == 200
    assert "需要本机 API Token" in page.text
    ops_links = client.get("/ops-links")
    assert ops_links.status_code == 200
    assert "CC中转状态中心" in ops_links.text
    assert "这个页面只给你看结论" in ops_links.text
    assert "闭环进度" in ops_links.text
    assert "自动发货" in ops_links.text
    assert "库存与渠道" in ops_links.text
    assert "买家链路" in ops_links.text
    assert "下一步" in ops_links.text
    assert "高级排障信息" in ops_links.text
    assert "OPENCLAW_API_TOKEN" in ops_links.text
    assert "function renderSnapshot" in ops_links.text
    assert "api('/api/cc-ops-snapshot'" in ops_links.text
    assert "api('/api/cc-operator-mode')" in ops_links.text
    assert "https://jiyu.245334.xyz/" in ops_links.text
    assert "http://127.0.0.1:18800/" in ops_links.text
    assert "/v1 是程序接口，不是人工页面" in ops_links.text
    assert "https://jiyu.245334.xyz/admin.html" not in ops_links.text
    assert "https://frist-api-oracle.245334.xyz/admin.html" not in ops_links.text

    no_token = client.get("/api/status")
    assert no_token.status_code == 401

    with_token = client.get("/api/status", headers={"X-API-Token": "unit-secret"})
    assert with_token.status_code == 200


def test_xianyu_admin_exchanges_global_token_for_scoped_http_only_session(monkeypatch):
    monkeypatch.setattr("src.api.auth._API_TOKEN", "unit-secret")
    client = TestClient(xianyu_admin.app)

    session = client.post(
        "/api/session",
        headers={"X-API-Token": "unit-secret"},
    )

    assert session.status_code == 200
    assert session.json() == {"ok": True, "expires_in": 900}
    set_cookie = session.headers["set-cookie"]
    assert "xianyu_admin_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert "Path=/api" in set_cookie
    assert "Max-Age=900" in set_cookie
    assert "unit-secret" not in set_cookie

    status = client.get("/api/status")
    assert status.status_code == 200

    page = client.get("/")
    assert "localStorage" not in page.text
    assert "sessionStorage" not in page.text
    assert "/api/session" in page.text


def test_xianyu_admin_session_rejects_cross_origin_write(monkeypatch):
    monkeypatch.setattr("src.api.auth._API_TOKEN", "unit-secret")
    client = TestClient(xianyu_admin.app)
    session = client.post(
        "/api/session",
        headers={"X-API-Token": "unit-secret"},
    )
    assert session.status_code == 200

    response = client.post(
        "/api/cc-operator-mode",
        headers={"Origin": "https://attacker.example"},
        json={"auto_ship_paused": True, "reason": "cross-origin"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "管理会话只允许同源写请求"}


def test_xianyu_admin_session_capacity_fails_closed(monkeypatch):
    """短时会话达到硬上限后拒绝新会话，避免认证客户端撑大内存。"""
    monkeypatch.setattr("src.api.auth._API_TOKEN", "unit-secret")
    monkeypatch.setattr(xianyu_admin, "_ADMIN_SESSION_MAX_ACTIVE", 1)
    client = TestClient(xianyu_admin.app)
    with xianyu_admin._admin_sessions_lock:
        xianyu_admin._admin_sessions.clear()

    try:
        assert client.post("/api/session", headers={"X-API-Token": "unit-secret"}).status_code == 200
        response = client.post("/api/session", headers={"X-API-Token": "unit-secret"})

        assert response.status_code == 429
        assert response.json() == {"detail": "短时管理会话已达上限，请稍后重试"}
    finally:
        with xianyu_admin._admin_sessions_lock:
            xianyu_admin._admin_sessions.clear()


def test_xianyu_admin_pages_enforce_nonce_csp_and_safe_dom_updates(monkeypatch):
    """管理页必须拒绝内联事件，并用一次性 nonce 约束页面脚本。"""
    monkeypatch.setattr("src.api.auth._API_TOKEN", "unit-secret")
    client = TestClient(xianyu_admin.app)

    for path in ("/", "/dashboard", "/ops-links"):
        response = client.get(path)

        assert response.status_code == 200
        csp = response.headers["content-security-policy"]
        script_policy = next(part.strip() for part in csp.split(";") if part.strip().startswith("script-src"))
        nonce_match = re.search(r"'nonce-([^']+)'", script_policy)
        assert nonce_match is not None
        assert "'self'" in script_policy
        assert "'unsafe-inline'" not in script_policy
        assert f'<script nonce="{nonce_match.group(1)}">' in response.text
        assert "onclick=" not in response.text
        assert "onerror=" not in response.text
        assert ".innerHTML" not in response.text
        assert "localStorage" not in response.text
        assert "sessionStorage" not in response.text
        assert 'autocomplete="current-password"' not in response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"


def test_xianyu_admin_runs_readonly_cc_readiness_audit(monkeypatch, tmp_path):
    script = tmp_path / "scripts" / "cc_zhongzhuan_readiness_audit.mjs"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    calls = []

    def _fake_run(args, cwd, text, capture_output, timeout, check):
        calls.append(args)
        return types.SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "schema_version": 2,
                    "ok": True,
                    "software_ready": True,
                    "checks": {
                        "chromeBookmarks": {"ok": True},
                        "localXianyu": {"ok": True},
                        "localXianyuGui": {
                            "ok": True,
                            "wsConnected": True,
                            "cookieOk": True,
                            "autoShipConfigured": True,
                            "pendingRescue": 0,
                        },
                        "realXianyuOrderProof": {"sentRealOrders": 0},
                        "oracle": {
                            "ok": True,
                            "config_contract": {
                                "ok": True,
                                "active_channels": 10,
                                "enabled_monitors": 10,
                            },
                            "inventory": {"redeem_available": 5, "active_keys": 1, "usage_logs": 6},
                            "provider_health": [],
                            "public": {
                                "home": {"http": 200},
                                "models": {"http": 401},
                                "webhook_no_token": {"http": 401},
                                "docs_route": {"http": 200},
                            },
                        },
                    },
                    "nextHumanGate": "跑 1 单小额真实付款",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("src.xianyu.xianyu_admin._project_root", lambda: tmp_path)
    monkeypatch.setattr("src.xianyu.xianyu_admin.subprocess.run", _fake_run)

    client = TestClient(xianyu_admin.app)
    response = client.get("/api/cc-readiness-audit?mode=read_only")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["summary"]["redeem_available"] == 5
    assert body["summary"]["sub2api_active_channels"] == 10
    assert body["summary"]["sub2api_enabled_monitors"] == 10
    assert body["summary"]["model_log_delta"] == 6
    smoke = xianyu_admin._cc_buyer_site_smoke_summary()
    assert smoke["state"] == "partial"
    assert smoke["redeemed_delta"] == 0
    assert smoke["active_token_delta"] == 1
    assert smoke["model_log_delta"] == 6
    assert calls[0][0] == "node"
    assert "--json" in calls[0]
    assert "--webhook-smoke" not in calls[0]
    assert "--require-real-order" not in calls[0]

    strict = client.get("/api/cc-readiness-audit?mode=strict")
    assert strict.status_code == 200
    assert "--require-real-order" in calls[1]
    assert "--webhook-smoke" not in calls[1]


def test_xianyu_admin_lists_and_resolves_cc_shipments(monkeypatch):
    class _Context:
        def __init__(self):
            self.resolved = []

        def list_cc_shipments(self, status="", limit=50, include_message=False):
            assert status == "message_send_failed"
            assert limit == 20
            assert include_message is True
            return [
                {
                    "id": 7,
                    "order_id": "order-admin-001",
                    "buyer_id": "buyer-admin",
                    "status": "message_send_failed",
                    "delivery_message": "兑换网址：https://jiyu.245334.xyz，卡密：CC-ADMIN",
                    "error": "websocket closed",
                }
            ]

        def resolve_cc_shipment(self, shipment_id, note=""):
            self.resolved.append((shipment_id, note))
            return shipment_id == 7

    ctx = _Context()
    monkeypatch.setattr("src.xianyu.xianyu_admin._get_ctx", lambda: ctx)

    client = TestClient(xianyu_admin.app)
    response = client.get("/api/cc-shipments?status=message_send_failed&limit=20&include_message=true")
    assert response.status_code == 200
    assert response.json()[0]["delivery_message"].endswith("CC-ADMIN")

    resolve = client.post("/api/cc-shipments/7/resolve", json={"note": "已人工补发"})
    assert resolve.status_code == 200
    assert resolve.json() == {"ok": True, "id": 7}
    assert ctx.resolved == [(7, "已人工补发")]


def test_xianyu_admin_resends_cc_shipment(monkeypatch):
    monkeypatch.setattr("src.api.auth._API_TOKEN", "")

    class _Live:
        def __init__(self):
            self.called = []

        async def resend_cc_shipment(self, shipment_id):
            self.called.append(shipment_id)
            return {"ok": True, "id": shipment_id, "order_id": "order-admin-resend"}

        async def call_on_owner(self, operation, **kwargs):
            assert operation == "resend_cc_shipment"
            assert kwargs.pop("timeout") == 45.0
            return await self.resend_cc_shipment(**kwargs)

    live = _Live()
    monkeypatch.setattr("src.xianyu.xianyu_admin._live", live)

    client = TestClient(xianyu_admin.app)
    response = client.post("/api/cc-shipments/9/resend")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert live.called == [9]


def test_xianyu_admin_status_reports_cc_auto_ship_summary(monkeypatch):
    monkeypatch.setattr("src.api.auth._API_TOKEN", "unit-secret")
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_ENABLED", "1")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_URL", "https://frist-api-oracle.245334.xyz/api/ops/xianyu/paid-order")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_TOKEN", "secret-token")
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_DELAY_SECONDS", "0")
    monkeypatch.setenv("CC_XIANYU_DEFAULT_PLAN_ID", "day|quotaUsd=30|source=xianyu")
    monkeypatch.setattr("src.xianyu.xianyu_admin._live", None)

    class _Context:
        def cc_shipment_summary(self):
            return {
                "total": 3,
                "sent": 1,
                "pending_rescue": 2,
                "resolved": 0,
                "by_status": {"message_sent": 1, "message_send_failed": 2},
                "latest": [],
            }

        def cc_final_sale_gate_summary(self):
            return {
                "local_ready": False,
                "sent_real_orders": 0,
                "pending_rescue": 0,
                "strict_audit_command": "node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order",
                "buyer_chain_required": {
                    "redeemed_redemptions_delta_gt_0": True,
                    "active_api_tokens_delta_gt_0": True,
                    "model_call_logs_delta_gt_0": True,
                },
                "latest": [],
            }

    monkeypatch.setattr("src.xianyu.xianyu_admin._ctx", _Context())

    client = TestClient(xianyu_admin.app)
    response = client.get("/api/status", headers={"X-API-Token": "unit-secret"})

    assert response.status_code == 200
    body = response.json()
    assert body["cc_auto_ship"]["configured"] is True
    assert body["cc_auto_ship"]["token_present"] is True
    assert body["cc_auto_ship"]["endpoint"].endswith("/api/ops/xianyu/paid-order")
    assert body["cc_auto_plan_routing"]["mode"] == "default_plan"
    assert body["cc_auto_plan_routing"]["default_plan_id_present"] is True
    assert body["cc_auto_plan_routing"]["risk"] == "low"
    assert body["cc_shipments"]["pending_rescue"] == 2
    assert body["cc_final_sale_gate"]["local_ready"] is False
    assert body["cc_final_sale_gate"]["strict_audit_command"].endswith("--require-real-order")


def test_xianyu_admin_sale_readiness_and_product_template(monkeypatch):
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_ENABLED", "1")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_URL", "https://frist-api-oracle.245334.xyz/api/ops/xianyu/paid-order")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_TOKEN", "secret-token")
    monkeypatch.setenv("CC_XIANYU_DEFAULT_PLAN_ID", "day|quotaUsd=30|source=xianyu")

    class _Live:
        runtime_snapshot_sync = staticmethod(_connected_xianyu_runtime_snapshot)

    class _Context:
        def cc_shipment_summary(self):
            return {"pending_rescue": 0, "sent": 1, "resolved": 0, "total": 1, "latest": []}

        def cc_final_sale_gate_summary(self):
            return {
                "local_ready": True,
                "sent_real_orders": 1,
                "pending_rescue": 0,
                "strict_audit_command": "node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order",
                "buyer_chain_required": {"same_xy_order_redeemed": True},
                "latest": [{"order_id_prefix": "xy_buyer", "status": "message_sent"}],
            }

        def list_cc_item_mappings(self, include_disabled=True):
            return [{"item_id": "item-001", "plan_id": "starter", "enabled": True}]

    monkeypatch.setattr("src.xianyu.xianyu_admin._live", _Live())
    monkeypatch.setattr("src.xianyu.xianyu_admin._ctx", _Context())
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._should_run_background_strict_audit",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._last_cc_readiness_audit",
        {
            "ok": True,
            "mode": "read_only",
            "updated_at": "2026-07-05T12:00:00",
            "redeem_available": 5,
            "sub2api_active_channels": 10,
            "sub2api_enabled_monitors": 10,
            "config_contract_ok": True,
            "pending_rescue": 0,
            "oracle": True,
            "local_gui": True,
            "chrome_bookmarks": True,
            "buyer_self_service_ok": True,
            "webhook_public_locked": True,
            "public_main_http": 200,
            "public_models_no_auth_http": 401,
            "public_webhook_no_token_http": 401,
            "ccswitch_entry_ok": True,
            "ccswitch_entry_http": 200,
            "ccswitch_has_cc_switch_text": True,
            "ccswitch_has_ccswitch_marker": True,
            "ccswitch_has_import_link_marker": True,
            "redeemed_delta": 1,
            "active_token_delta": 1,
            "model_log_delta": 2,
        },
    )

    client = TestClient(xianyu_admin.app)
    readiness = client.get("/api/cc-sale-readiness")

    assert readiness.status_code == 200
    body = readiness.json()
    assert body["can_auto_ship_paid_orders"] is True
    assert body["ready_for_public_sale"] is False
    assert body["checks"]["enabled_item_mappings"] == 1
    assert body["plan_routing"]["mode"] == "item_mapping_then_default"
    assert body["plan_routing"]["risk"] == "low"
    assert body["buyer_self_service"]["known"] is True
    assert body["buyer_self_service"]["ok"] is True
    assert body["buyer_self_service"]["main_http"] == 200
    assert body["ccswitch_import"]["known"] is True
    assert body["ccswitch_import"]["ok"] is True
    assert body["ccswitch_import"]["page_http"] == 200
    assert body["ccswitch_import"]["has_import_link_marker"] is True
    assert any("兑换/API/调模型" in item for item in body["human_required"])

    watch = client.get("/api/cc-loop-watch")
    assert watch.status_code == 200
    watch_body = watch.json()
    assert watch_body["stage"] == "waiting_buyer_chain"
    assert watch_body["can_auto_ship_paid_orders"] is True
    assert watch_body["ready_for_public_sale"] is False
    assert watch_body["checks"]["sent_real_orders"] == 1
    assert watch_body["strict_audit_command"].endswith("--require-real-order")
    assert watch_body["auto_strict_audit_enabled"] is True
    assert watch_body["auto_strict_audit_interval_ms"] >= 60000
    assert watch_body["background_strict_audit_enabled"] is True
    assert watch_body["background_strict_audit_scan_seconds"] >= 30

    progress = client.get("/api/cc-buyer-chain-progress")
    assert progress.status_code == 200
    progress_body = progress.json()
    assert progress_body["stage"] == "waiting_strict_audit"
    assert progress_body["steps"]["paid_order_shipped"] is True
    assert progress_body["steps"]["card_redeemed"] is False
    assert progress_body["steps"]["api_key_created"] is False
    assert progress_body["counts"]["sent_real_orders"] == 1

    next_action = client.get("/api/cc-operator-next-action")
    assert next_action.status_code == 200
    action_body = next_action.json()
    assert action_body["state"] == "waiting_strict_audit"
    assert action_body["severity"] == "warning"
    assert "严格门" in action_body["title"]
    assert any(item["key"] == "real_paid_order" and item["ok"] is True for item in action_body["checklist"])
    assert any(item["key"] == "buyer_chain_verified" and item["ok"] is False for item in action_body["checklist"])
    assert any(item["key"] == "buyer_site_smoke" and item["ok"] is True for item in action_body["checklist"])
    assert action_body["buyer_site_smoke"]["state"] == "complete"
    assert action_body["buyer_site_smoke_plan"]["executes_now"] is False

    smoke_plan = client.get("/api/cc-buyer-site-smoke-plan")
    assert smoke_plan.status_code == 200
    smoke_plan_body = smoke_plan.json()
    assert smoke_plan_body["ok"] is True
    assert smoke_plan_body["state"] == "already_proven"
    assert smoke_plan_body["executes_now"] is False
    assert smoke_plan_body["requires_owner_confirmation"] is True
    assert "创建临时买家账号" in smoke_plan_body["would_write"]

    snapshot = client.get("/api/cc-ops-snapshot")
    assert snapshot.status_code == 200
    snapshot_body = snapshot.json()
    assert snapshot_body["ok"] is True
    assert snapshot_body["next_action"]["state"] == "waiting_strict_audit"
    assert snapshot_body["status"]["cc_auto_ship"]["configured"] is True
    assert snapshot_body["loop_watch"]["stage"] == "waiting_buyer_chain"
    assert snapshot_body["buyer_progress"]["stage"] == "waiting_strict_audit"
    assert snapshot_body["auto_strict_audit_status"]["enabled"] is True
    assert snapshot_body["auto_strict_audit_status"]["state"] == "armed"
    assert "自动观察" in snapshot_body["auto_strict_audit_status"]["label"]
    assert snapshot_body["buyer_site_smoke"]["ok"] is True
    assert snapshot_body["buyer_site_smoke"]["redeemed_delta"] == 1
    assert snapshot_body["buyer_site_smoke"]["active_token_delta"] == 1
    assert snapshot_body["buyer_site_smoke"]["model_log_delta"] == 2
    assert snapshot_body["buyer_site_smoke_plan"]["executes_now"] is False

    pack = client.get("/api/cc-real-order-test-pack")
    assert pack.status_code == 200
    pack_body = pack.json()
    assert pack_body["title"] == "真实小额单验收包"
    assert pack_body["can_public_sale"] is False
    assert any(item["key"] == "publish_paid_order" for item in pack_body["checkpoints"])
    assert any(item["key"] == "strict_gate" for item in pack_body["checkpoints"])
    assert "不自动砍价" in pack_body["safety_boundaries"]
    assert "CC Switch" in pack_body["product_template"]["template"]
    assert pack_body["addresses"]["user_site"].startswith("https://jiyu.245334.xyz")
    assert any(item["key"] == "buyer_site_smoke" and item["ok"] is True for item in pack_body["checkpoints"])
    assert pack_body["buyer_site_smoke"]["state"] == "complete"
    assert pack_body["buyer_site_smoke_plan"]["executes_now"] is False

    coverage = client.get("/api/cc-automation-coverage")
    assert coverage.status_code == 200
    coverage_body = coverage.json()
    assert coverage_body["ok"] is True
    assert coverage_body["internal_automation_ready"] is True
    assert coverage_body["public_sale_ready"] is False
    assert coverage_body["external_blocker"] is True
    assert coverage_body["auto_strict_audit_status"]["enabled"] is True
    assert "严格门" in coverage_body["auto_strict_audit_status"]["label"]
    assert coverage_body["buyer_site_smoke"]["ok"] is True
    assert coverage_body["buyer_site_smoke"]["state"] == "complete"
    assert coverage_body["buyer_site_smoke_plan"]["executes_now"] is False
    assert any(item["key"] == "chrome_bookmark_folder" and item["ok"] is True for item in coverage_body["items"])
    assert any(
        item["key"] == "real_order_strict_gate" and item["external"] is True and item["ok"] is False
        for item in coverage_body["items"]
    )
    assert "真实付款" in coverage_body["next_action"]

    precheck = client.get("/api/cc-manual-precheck-evidence")
    assert precheck.status_code == 200
    precheck_body = precheck.json()
    assert precheck_body["ok"] is True
    assert precheck_body["title"] == "人工预检闭环证据"
    assert precheck_body["safety"] == {
        "read_only": True,
        "does_not_send_card": True,
        "does_not_click_xianyu_ship": True,
        "does_not_resume_auto_ship": True,
    }
    assert any(item["key"] == "cf_inside_auth_container" and item["ok"] is True for item in precheck_body["items"])
    assert any(item["key"] == "branded_email_templates" and item["ok"] is True for item in precheck_body["items"])
    assert any(item["key"] == "duplicate_delivery_guard" and item["ok"] is True for item in precheck_body["items"])
    assert any(item["key"] == "xianyu_auto_ship_strategy" and item["ok"] is True for item in precheck_body["items"])
    assert any(item["key"] == "strict_real_order_chain" for item in precheck_body["items"])

    sale_lock = client.get("/api/cc-public-sale-lock")
    assert sale_lock.status_code == 200
    lock_body = sale_lock.json()
    assert lock_body["state"] == "internal_test_ready"
    assert lock_body["can_internal_test"] is True
    assert lock_body["can_public_sale"] is False
    assert lock_body["inventory"]["unused_cards"] == 5
    assert lock_body["inventory"]["buyer_self_service_ok"] is True
    assert lock_body["inventory"]["public_main_http"] == 200
    assert lock_body["gates"]["ccswitch_import_ready"] is True
    assert lock_body["inventory"]["ccswitch_entry_ok"] is True
    assert lock_body["inventory"]["ccswitch_has_import_link_marker"] is True
    assert lock_body["auto_readiness_audit"]["enabled"] is True
    assert lock_body["auto_readiness_audit"]["interval_ms"] >= 300000
    assert any("真实闲鱼小额单" in item for item in lock_body["blockers"])

    template = client.get("/api/cc-product-template?title=CC中转日卡&plan_id=starter&price=9.9")
    assert template.status_code == 200
    text = template.json()["template"]
    assert "CC中转日卡" in text
    assert "starter" in text
    assert "注册或登录" in text
    assert "CC Switch" in text
    assert "/v1" not in text
    assert "官方合作" not in text


def test_xianyu_resume_preflight_refreshes_inventory_when_cache_cold(monkeypatch):
    """恢复前安全检查应自动只读刷新库存证据，不让老板多记一个按钮。"""
    calls = []

    def _fake_lock(refresh=False):
        if refresh:
            calls.append("refresh")
            return {
                "state": "paused_after_strict_gate",
                "state_label": "严格门已通过，自动发货暂停保护",
                "can_internal_test": True,
                "can_public_sale": False,
                "blockers": ["自动发货被手动暂停保护（防重复发卡）"],
                "gates": {
                    "webhook_configured": True,
                    "ws_connected": True,
                    "cookie_ok": True,
                    "pending_rescue_clear": True,
                    "inventory_known": True,
                    "inventory_ready": True,
                    "redemptions_ready": True,
                    "channels_ready": True,
                    "buyer_self_service_ready": True,
                    "webhook_public_locked": True,
                    "ccswitch_import_ready": True,
                    "strict_real_order_ready": True,
                },
            }
        return {
            "state": "paused_after_strict_gate",
            "state_label": "严格门已通过，自动发货暂停保护",
            "can_internal_test": True,
            "can_public_sale": False,
            "blockers": ["自动发货被手动暂停保护（防重复发卡）"],
            "gates": {
                "webhook_configured": True,
                "ws_connected": True,
                "cookie_ok": True,
                "pending_rescue_clear": True,
                "inventory_known": False,
                "buyer_self_service_ready": True,
                "webhook_public_locked": True,
                "ccswitch_import_ready": True,
                "strict_real_order_ready": True,
            },
        }

    monkeypatch.setattr("src.xianyu.xianyu_admin._cc_public_sale_lock_summary", _fake_lock)

    preflight = xianyu_admin._cc_auto_ship_resume_preflight()

    assert calls == ["refresh"]
    assert preflight["safe_to_resume"] is True
    assert preflight["refreshed_inventory"] is True
    assert "库存/渠道证据未刷新" not in preflight["blockers"]


def test_xianyu_operator_mode_can_pause_auto_ship(monkeypatch):
    """暂停后只在库存证据刷新且严格门未通过时拒绝恢复。"""
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_ENABLED", "1")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_URL", "https://frist-api-oracle.245334.xyz/api/ops/xianyu/paid-order")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_TOKEN", "secret-token")
    monkeypatch.setenv("CC_XIANYU_DEFAULT_PLAN_ID", "day|quotaUsd=30|source=xianyu")

    class _Live:
        runtime_snapshot_sync = staticmethod(_connected_xianyu_runtime_snapshot)

    class _Context:
        def cc_shipment_summary(self):
            return {"pending_rescue": 0, "sent": 1, "resolved": 0, "total": 1, "latest": []}

        def cc_final_sale_gate_summary(self):
            return {"local_ready": False, "sent_real_orders": 0, "pending_rescue": 0, "latest": []}

        def list_cc_item_mappings(self, include_disabled=True):
            return [{"item_id": "item-001", "plan_id": "starter", "enabled": True}]

    monkeypatch.setattr("src.xianyu.xianyu_admin._live", _Live())
    monkeypatch.setattr("src.xianyu.xianyu_admin._ctx", _Context())

    def _fake_lock(refresh=False):
        gates = {
            "webhook_configured": True,
            "ws_connected": True,
            "cookie_ok": True,
            "pending_rescue_clear": True,
            "inventory_known": bool(refresh),
            "inventory_ready": True,
            "redemptions_ready": True,
            "channels_ready": True,
            "buyer_self_service_ready": True,
            "webhook_public_locked": True,
            "ccswitch_import_ready": True,
            "strict_real_order_ready": False,
        }
        return {
            "state": "internal_test_only",
            "state_label": "仅允许内测",
            "can_internal_test": True,
            "can_public_sale": False,
            "blockers": ["真实小额单严格门未通过"],
            "gates": gates,
        }

    monkeypatch.setattr("src.xianyu.xianyu_admin._cc_public_sale_lock_summary", _fake_lock)

    client = TestClient(xianyu_admin.app)
    before = client.get("/api/cc-operator-mode")
    assert before.status_code == 200
    assert before.json()["auto_ship_paused"] is False
    assert before.json()["can_auto_ship_paid_orders"] is True

    paused = client.post(
        "/api/cc-operator-mode",
        json={"auto_ship_paused": True, "reason": "unit test pause"},
    )
    assert paused.status_code == 200
    paused_body = paused.json()
    assert paused_body["auto_ship_paused"] is True
    assert paused_body["can_auto_ship_paid_orders"] is False

    preflight = client.get("/api/cc-operator-mode/resume-preflight")
    assert preflight.status_code == 200
    assert preflight.json()["safe_to_resume"] is False
    assert preflight.json()["refreshed_inventory"] is True
    assert all("库存/渠道证据未刷新" not in blocker for blocker in preflight.json()["blockers"])
    assert any("真实小额单严格门" in blocker for blocker in preflight.json()["blockers"])
    assert client.get("/api/cc-operator-mode").json()["auto_ship_paused"] is True

    unsafe_resume = client.post(
        "/api/cc-operator-mode",
        json={"auto_ship_paused": False, "reason": "unit test resume"},
    )
    assert unsafe_resume.status_code == 409
    assert unsafe_resume.json()["detail"]["safe_to_resume"] is False
    unsafe_detail = unsafe_resume.json()["detail"]
    assert "真实小额单严格门" in unsafe_detail["nextAction"]
    assert all("库存/渠道证据未刷新" not in blocker for blocker in unsafe_detail["blockers"])
    assert any("真实小额单严格门" in blocker for blocker in unsafe_detail["blockers"])
    assert client.get("/api/cc-operator-mode").json()["auto_ship_paused"] is True

    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_auto_ship_resume_preflight",
        lambda: {
            "ok": True,
            "safe_to_resume": True,
            "nextAction": "可以恢复自动发货；恢复后建议先小流量观察。",
            "blockers": [],
        },
    )
    resumed = client.post(
        "/api/cc-operator-mode",
        json={"auto_ship_paused": False, "reason": "unit test resume"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["auto_ship_paused"] is False
    assert resumed.json()["auto_resume_canary_active"] is True
    assert resumed.json()["resume_preflight"]["safe_to_resume"] is True


def test_xianyu_admin_automation_coverage_refreshes_missing_readiness(monkeypatch):
    """覆盖清单冷启动时应只读刷新一次证据，避免把库存/书签误判为未就绪。"""
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_cc_readiness_audit", {})
    calls = []

    def fake_readiness_audit(mode="read_only"):
        calls.append(mode)
        xianyu_admin._last_cc_readiness_audit = {
            "updated_at": "2026-07-05T12:00:00",
            "chrome_bookmarks": True,
            "redeem_available": 5,
            "sub2api_active_channels": 10,
            "sub2api_enabled_monitors": 10,
            "config_contract_ok": True,
            "public_main_http": 200,
            "ccswitch_entry_http": 200,
            "ccswitch_has_import_link_marker": True,
        }
        return {"ok": True}

    class _Context:
        def cc_shipment_summary(self):
            return {"pending_rescue": 0}

    monkeypatch.setattr("src.xianyu.xianyu_admin._ctx", _Context())
    monkeypatch.setattr("src.xianyu.xianyu_admin._run_cc_readiness_audit", fake_readiness_audit)
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_public_sale_lock_summary",
        lambda refresh=False: {
            "can_public_sale": False,
            "gates": {
                "inventory_ready": True,
                "redemptions_ready": True,
                "buyer_self_service_ready": True,
                "ccswitch_import_ready": True,
                "channels_ready": True,
            },
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda: {
            "stage": "waiting_paid_order",
            "can_auto_ship_paid_orders": True,
            "checks": {"pending_rescue": 0, "sent_real_orders": 0},
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_buyer_chain_progress_summary",
        lambda: {"steps": {"same_order_verified": False}, "counts": {"same_order_ready": 0}},
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_sale_readiness_summary",
        lambda: {
            "checks": {"webhook_configured": True, "ws_connected": True, "cookie_ok": True},
            "buyer_self_service": {"main_http": 200},
            "ccswitch_import": {"page_http": 200, "has_import_link_marker": True},
            "plan_routing": {"mode": "default_plan"},
        },
    )

    body = xianyu_admin._cc_automation_coverage_summary()

    assert calls == ["read_only"]
    assert body["audit_error"] == ""
    assert body["internal_automation_ready"] is True
    assert body["public_sale_ready"] is False
    assert body["external_blocker"] is True
    assert body["completed"] == 10
    assert body["total"] == 11
    assert any(item["key"] == "chrome_bookmark_folder" and item["ok"] is True for item in body["items"])


def test_xianyu_admin_automation_coverage_runs_strict_audit_after_real_order(monkeypatch):
    """真实订单已发货后，覆盖清单应触发现有严格门只读观察，减少人工点击。"""
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._last_cc_readiness_audit",
        {
            "updated_at": "2026-07-05T12:00:00",
            "chrome_bookmarks": True,
            "redeem_available": 5,
            "sub2api_active_channels": 10,
            "sub2api_enabled_monitors": 10,
            "config_contract_ok": True,
            "public_main_http": 200,
            "ccswitch_entry_http": 200,
            "ccswitch_has_import_link_marker": True,
        },
    )
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_background_strict_audit_at", 0.0)
    calls = []

    class _Context:
        def cc_shipment_summary(self):
            return {"pending_rescue": 0}

    monkeypatch.setattr("src.xianyu.xianyu_admin._ctx", _Context())

    def fake_strict_once():
        calls.append("strict")
        xianyu_admin._last_cc_strict_audit = {
            "ok": False,
            "exit_code": 1,
            "same_order_ready": 0,
            "same_order_matched": 1,
            "real_orders": 1,
            "summary": {"same_order_latest": [{"orderIdPrefix": "xy_oid_", "ready": False}]},
        }
        return {"ran": True, "ok": False, "stage": "waiting_buyer_chain", "same_order_ready": 0}

    monkeypatch.setattr("src.xianyu.xianyu_admin._run_background_strict_audit_once", fake_strict_once)
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_public_sale_lock_summary",
        lambda refresh=False: {
            "can_public_sale": False,
            "gates": {
                "inventory_ready": True,
                "redemptions_ready": True,
                "buyer_self_service_ready": True,
                "ccswitch_import_ready": True,
                "channels_ready": True,
            },
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda: {
            "stage": "waiting_buyer_chain",
            "can_auto_ship_paid_orders": True,
            "ready_for_public_sale": False,
            "checks": {"pending_rescue": 0, "sent_real_orders": 1},
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_buyer_chain_progress_summary",
        lambda: {
            "stage": "waiting_redeem",
            "steps": {
                "paid_order_shipped": True,
                "card_redeemed": False,
                "api_key_created": False,
                "model_called": False,
                "same_order_verified": False,
            },
            "counts": {"same_order_ready": 0, "sent_real_orders": 1},
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_sale_readiness_summary",
        lambda: {
            "checks": {"webhook_configured": True, "ws_connected": True, "cookie_ok": True},
            "buyer_self_service": {"main_http": 200},
            "ccswitch_import": {"page_http": 200, "has_import_link_marker": True},
            "plan_routing": {"mode": "default_plan"},
        },
    )

    body = xianyu_admin._cc_automation_coverage_summary()

    assert calls == ["strict"]
    assert body["auto_strict_audit"]["ran"] is True
    assert body["auto_strict_audit"]["stage"] == "waiting_buyer_chain"
    assert body["auto_strict_audit_status"]["state"] == "ran"
    assert body["auto_strict_audit_status"]["reason"] == "waiting_buyer_chain"
    assert body["internal_automation_ready"] is True
    assert body["public_sale_ready"] is False
    assert any(item["key"] == "real_order_strict_gate" and item["ok"] is False for item in body["items"])


def test_xianyu_ops_snapshot_treats_pause_after_strict_gate_as_healthy(monkeypatch):
    """严格门已过但自动发货人为暂停时，总快照应显示系统健康待恢复，不应误报故障。"""

    class _Live:
        runtime_snapshot_sync = staticmethod(_connected_xianyu_runtime_snapshot)

    class _Context:
        def cc_shipment_summary(self):
            return {
                "pending_rescue": 0,
                "sent": 2,
                "resolved": 0,
                "total": 2,
                "xianyu_confirm_page_pending": 0,
                "xianyu_confirm_failed": 0,
                "latest": [],
            }

        def cc_final_sale_gate_summary(self):
            return {"local_ready": True, "sent_real_orders": 1, "pending_rescue": 0, "latest": []}

        def list_cc_item_mappings(self, include_disabled=True):
            return [{"item_id": "item-001", "plan_id": "xianyu-test-1", "enabled": True}]

    monkeypatch.setattr("src.xianyu.xianyu_admin._live", _Live())
    monkeypatch.setattr("src.xianyu.xianyu_admin._ctx", _Context())
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_auto_ship_status",
        lambda: {
            "enabled": True,
            "configured": True,
            "operational": False,
            "paused": True,
            "one_shot_delivery": {"active": False},
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_public_sale_lock_summary",
        lambda refresh=False: {
            "state": "paused_after_strict_gate",
            "state_label": "严格门已通过，自动发货暂停保护",
            "can_internal_test": True,
            "can_public_sale": False,
            "blockers": ["自动发货被手动暂停保护（防重复发卡）"],
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_operator_next_action_summary",
        lambda: {
            "state": "paused_after_strict_gate",
            "severity": "warning",
            "title": "严格门已通过，自动发货暂停保护",
            "primary_action": "确认准备正式售卖后，在操作台点恢复自动发货。",
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda: {"stage": "operator_paused", "can_auto_ship_paid_orders": False, "checks": {"pending_rescue": 0}},
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_buyer_chain_progress_summary",
        lambda: {"stage": "verified", "steps": {"same_order_verified": True}},
    )
    monkeypatch.setattr("src.xianyu.xianyu_admin._cc_buyer_site_smoke_summary", lambda: {"ok": True})
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_buyer_site_smoke_plan_summary",
        lambda: {"executes_now": False},
    )

    snapshot = xianyu_admin._cc_ops_snapshot_summary()

    assert snapshot["ok"] is True
    assert snapshot["sale_lock"]["state"] == "paused_after_strict_gate"
    assert snapshot["status"]["cc_auto_ship"]["paused"] is True
    assert snapshot["status"]["cc_shipments"]["pending_rescue"] == 0


def test_xianyu_ops_snapshot_uses_precheck_when_inventory_cache_cold(monkeypatch):
    """冷启动未刷新库存缓存时，严格门已过的暂停保护态也不能误报系统故障。"""
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_cc_readiness_audit", {})
    monkeypatch.setattr("src.xianyu.xianyu_admin._strict_audit_ready", lambda: True)
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_auto_ship_status",
        lambda: {
            "enabled": True,
            "configured": True,
            "operational": False,
            "paused": True,
            "one_shot_delivery": {"active": False},
        },
    )

    class _Live:
        runtime_snapshot_sync = staticmethod(_connected_xianyu_runtime_snapshot)

    class _Context:
        def cc_shipment_summary(self):
            return {
                "pending_rescue": 0,
                "sent": 2,
                "resolved": 0,
                "total": 2,
                "xianyu_confirm_page_pending": 0,
                "xianyu_confirm_failed": 0,
                "latest": [],
            }

        def cc_final_sale_gate_summary(self):
            return {"local_ready": True, "sent_real_orders": 1, "pending_rescue": 0, "latest": []}

        def list_cc_item_mappings(self, include_disabled=True):
            return [{"item_id": "item-001", "plan_id": "xianyu-test-1", "enabled": True}]

    monkeypatch.setattr("src.xianyu.xianyu_admin._live", _Live())
    monkeypatch.setattr("src.xianyu.xianyu_admin._ctx", _Context())
    monkeypatch.setattr("src.xianyu.xianyu_admin._cc_buyer_site_smoke_summary", lambda: {"ok": True})
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_buyer_site_smoke_plan_summary",
        lambda: {"executes_now": False},
    )

    snapshot = xianyu_admin._cc_ops_snapshot_summary()

    assert snapshot["ok"] is True
    assert snapshot["sale_lock"]["state"] == "paused_after_strict_gate"
    assert snapshot["sale_lock"]["can_internal_test"] is True
    assert snapshot["next_action"]["state"] == "paused_after_strict_gate"
    assert snapshot["next_action"]["severity"] == "warning"


def test_xianyu_operator_next_action_treats_pause_after_strict_gate_as_resume_prompt(monkeypatch):
    """严格门已过但自动发货人为暂停时，下一步应提示恢复保护，不应报自动发货故障。"""
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_public_sale_lock_summary",
        lambda refresh=False: {
            "state": "paused_after_strict_gate",
            "state_label": "严格门已通过，自动发货暂停保护",
            "can_internal_test": True,
            "can_public_sale": False,
            "next_action": "确认准备正式售卖后，在操作台点“恢复自动发货”。",
            "blockers": ["自动发货被手动暂停保护（防重复发卡）"],
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda: {
            "stage": "operator_paused",
            "stage_label": "自动发货已暂停",
            "can_auto_ship_paid_orders": False,
            "next_action": "需要继续售卖时，在本机操作台点“恢复自动发货”。",
            "checks": {"pending_rescue": 0, "sent_real_orders": 1},
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_buyer_chain_progress_summary",
        lambda: {"stage": "verified", "steps": {"same_order_verified": True}},
    )
    monkeypatch.setattr("src.xianyu.xianyu_admin._cc_buyer_site_smoke_summary", lambda: {"ok": True})
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_buyer_site_smoke_plan_summary",
        lambda: {"executes_now": False},
    )

    action = xianyu_admin._cc_operator_next_action_summary()

    assert action["state"] == "paused_after_strict_gate"
    assert action["severity"] == "warning"
    assert action["title"] == "严格门已通过，自动发货暂停保护"
    assert "恢复自动发货" in action["primary_action"]
    assert action["primary_action"] != "自动发货还没完全就绪"


def test_xianyu_operator_next_action_waits_for_inventory_evidence(monkeypatch):
    monkeypatch.setenv("CC_XIANYU_AUTO_SHIP_ENABLED", "1")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_URL", "https://frist-api-oracle.245334.xyz/api/ops/xianyu/paid-order")
    monkeypatch.setenv("CC_XIANYU_WEBHOOK_TOKEN", "secret-token")

    class _Live:
        runtime_snapshot_sync = staticmethod(_connected_xianyu_runtime_snapshot)

    class _Context:
        def cc_shipment_summary(self):
            return {"pending_rescue": 0, "sent": 0, "resolved": 0, "total": 0, "latest": []}

        def cc_final_sale_gate_summary(self):
            return {
                "local_ready": False,
                "sent_real_orders": 0,
                "pending_rescue": 0,
                "strict_audit_command": "node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order",
                "buyer_chain_required": {"same_xy_order_redeemed": True},
                "latest": [],
            }

        def list_cc_item_mappings(self, include_disabled=True):
            return [{"item_id": "item-001", "plan_id": "starter", "enabled": True}]

    monkeypatch.setattr("src.xianyu.xianyu_admin._live", _Live())
    monkeypatch.setattr("src.xianyu.xianyu_admin._ctx", _Context())

    client = TestClient(xianyu_admin.app)
    response = client.get("/api/cc-operator-next-action")

    assert response.status_code == 200
    body = response.json()
    assert body["severity"] == "danger"
    assert body["state"] == "locked"
    assert "库存/渠道证据未刷新" in body["primary_action"]
    assert any(item["key"] == "inventory_ready" and item["ok"] is False for item in body["checklist"])


def test_xianyu_admin_background_strict_audit_gate(monkeypatch):
    monkeypatch.setenv("CC_XIANYU_AUTO_STRICT_AUDIT_ENABLED", "1")
    monkeypatch.setenv("CC_XIANYU_AUTO_STRICT_AUDIT_INTERVAL_MS", "60000")

    ready_summary = {
        "stage": "waiting_buyer_chain",
        "ready_for_public_sale": False,
        "can_auto_ship_paid_orders": True,
        "checks": {
            "pending_rescue": 0,
            "sent_real_orders": 1,
        },
    }

    assert xianyu_admin._should_run_background_strict_audit(ready_summary, now_ts=120, last_run_at=0) is True
    assert xianyu_admin._should_run_background_strict_audit(ready_summary, now_ts=120, last_run_at=90) is False

    no_order = dict(ready_summary)
    no_order["checks"] = {"pending_rescue": 0, "sent_real_orders": 0}
    assert xianyu_admin._should_run_background_strict_audit(no_order, now_ts=120, last_run_at=0) is False

    rescue = dict(ready_summary)
    rescue["checks"] = {"pending_rescue": 1, "sent_real_orders": 1}
    assert xianyu_admin._should_run_background_strict_audit(rescue, now_ts=120, last_run_at=0) is False

    waiting_paid = dict(ready_summary)
    waiting_paid["stage"] = "waiting_paid_order"
    assert xianyu_admin._should_run_background_strict_audit(waiting_paid, now_ts=120, last_run_at=0) is False

    monkeypatch.setenv("CC_XIANYU_AUTO_STRICT_AUDIT_ENABLED", "0")
    assert xianyu_admin._should_run_background_strict_audit(ready_summary, now_ts=120, last_run_at=0) is False


def test_xianyu_admin_public_sale_lock_refreshes_readonly_audit(monkeypatch):
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_cc_readiness_audit", {})
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_sale_readiness_summary",
        lambda *_args, **_kwargs: {
            "can_auto_ship_paid_orders": True,
            "ready_for_public_sale": True,
            "checks": {"pending_rescue": 0},
            "last_strict_audit": {"ok": True, "same_order_ready": 1},
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda *_args, **_kwargs: {"stage": "closed_loop_verified"},
    )
    calls = []

    def _fake_audit(mode):
        calls.append(mode)
        xianyu_admin._remember_readiness_audit(
            {
                "ok": True,
                "mode": mode,
                "exit_code": 0,
                "summary": {
                    "redeem_available": 2,
                    "sub2api_active_channels": 10,
                    "sub2api_enabled_monitors": 10,
                    "config_contract_ok": True,
                    "pending_rescue": 0,
                    "oracle": True,
                    "local_gui": True,
                    "chrome_bookmarks": True,
                    "buyer_self_service_ok": True,
                    "webhook_public_locked": True,
                    "public_main_http": 200,
                    "public_models_no_auth_http": 401,
                    "public_webhook_no_token_http": 401,
                    "ccswitch_entry_ok": True,
                    "ccswitch_entry_http": 200,
                    "ccswitch_has_cc_switch_text": True,
                    "ccswitch_has_ccswitch_marker": True,
                    "ccswitch_has_import_link_marker": True,
                },
            }
        )
        return {"ok": True}

    monkeypatch.setattr("src.xianyu.xianyu_admin._run_cc_readiness_audit", _fake_audit)

    lock = xianyu_admin._cc_public_sale_lock_summary(refresh=True)

    assert calls == ["read_only"]
    assert lock["state"] == "public_sale_unlocked"
    assert lock["can_public_sale"] is True
    assert lock["inventory"]["unused_cards"] == 2
    assert lock["inventory"]["buyer_self_service_ok"] is True
    assert lock["gates"]["buyer_self_service_ready"] is True
    assert lock["gates"]["webhook_public_locked"] is True
    assert lock["gates"]["ccswitch_import_ready"] is True
    assert lock["inventory"]["ccswitch_entry_http"] == 200
    assert lock["blockers"] == []


def test_xianyu_admin_public_sale_lock_explains_manual_pause_after_strict_gate(monkeypatch):
    """严格门已过但老板手动暂停时，售卖锁要说人话，不能误报链路坏了。"""
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_sale_readiness_summary",
        lambda *_args, **_kwargs: {
            "can_auto_ship_paid_orders": False,
            "ready_for_public_sale": True,
            "checks": {
                "pending_rescue": 0,
                "auto_ship_paused": True,
                "webhook_configured": True,
                "ws_connected": True,
                "cookie_ok": True,
            },
            "last_strict_audit": {"ok": True, "same_order_ready": 1},
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda *_args, **_kwargs: {"stage": "closed_loop_verified", "ready_for_public_sale": True},
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._last_cc_readiness_audit",
        {
            "ok": True,
            "mode": "read_only",
            "updated_at": "2026-07-08T08:40:00-06:00",
            "redeem_available": 5,
            "sub2api_active_channels": 10,
            "sub2api_enabled_monitors": 10,
            "config_contract_ok": True,
            "buyer_self_service_ok": True,
            "webhook_public_locked": True,
            "public_main_http": 200,
            "public_models_no_auth_http": 401,
            "public_webhook_no_token_http": 401,
            "ccswitch_entry_ok": True,
            "ccswitch_entry_http": 200,
            "ccswitch_has_cc_switch_text": True,
            "ccswitch_has_ccswitch_marker": True,
            "ccswitch_has_import_link_marker": True,
        },
    )

    lock = xianyu_admin._cc_public_sale_lock_summary(refresh=False)

    assert lock["can_internal_test"] is True
    assert lock["can_public_sale"] is False
    assert lock["gates"]["strict_real_order_ready"] is True
    assert lock["gates"]["auto_ship_paused"] is True
    assert lock["state"] == "paused_after_strict_gate"
    assert lock["state_label"] == "严格门已通过，自动发货暂停保护"
    assert "自动发货被手动暂停保护" in lock["blockers"][0]
    assert "自动发货链路未完全就绪" not in lock["blockers"]
    assert "恢复自动发货" in lock["next_action"]


def test_xianyu_admin_public_sale_lock_blocks_bad_buyer_entry(monkeypatch):
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_sale_readiness_summary",
        lambda *_args, **_kwargs: {
            "can_auto_ship_paid_orders": True,
            "ready_for_public_sale": True,
            "checks": {"pending_rescue": 0},
            "last_strict_audit": {"ok": True, "same_order_ready": 1},
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda *_args, **_kwargs: {"stage": "closed_loop_verified"},
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._last_cc_readiness_audit",
        {
            "ok": False,
            "mode": "read_only",
            "updated_at": "2026-07-05T18:50:00-04:00",
            "redeem_available": 2,
            "sub2api_active_channels": 10,
            "sub2api_enabled_monitors": 10,
            "config_contract_ok": True,
            "pending_rescue": 0,
            "oracle": True,
            "local_gui": True,
            "chrome_bookmarks": True,
            "buyer_self_service_ok": False,
            "webhook_public_locked": True,
            "public_main_http": 502,
            "public_models_no_auth_http": 0,
            "public_webhook_no_token_http": 401,
        },
    )

    lock = xianyu_admin._cc_public_sale_lock_summary(refresh=False)

    assert lock["can_internal_test"] is False
    assert lock["can_public_sale"] is False
    assert lock["gates"]["buyer_self_service_ready"] is False
    assert "买家主站或 API 网关公网入口异常" in lock["blockers"]


def test_xianyu_admin_public_sale_lock_blocks_bad_ccswitch_entry(monkeypatch):
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_sale_readiness_summary",
        lambda *_args, **_kwargs: {
            "can_auto_ship_paid_orders": True,
            "ready_for_public_sale": True,
            "checks": {"pending_rescue": 0},
            "last_strict_audit": {"ok": True, "same_order_ready": 1},
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda *_args, **_kwargs: {"stage": "closed_loop_verified"},
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._last_cc_readiness_audit",
        {
            "ok": False,
            "mode": "read_only",
            "updated_at": "2026-07-05T18:58:00-04:00",
            "redeem_available": 2,
            "sub2api_active_channels": 10,
            "sub2api_enabled_monitors": 10,
            "config_contract_ok": True,
            "pending_rescue": 0,
            "oracle": True,
            "local_gui": True,
            "chrome_bookmarks": True,
            "buyer_self_service_ok": True,
            "webhook_public_locked": True,
            "public_main_http": 200,
            "public_models_no_auth_http": 401,
            "public_webhook_no_token_http": 401,
            "ccswitch_entry_ok": False,
            "ccswitch_entry_http": 200,
            "ccswitch_has_cc_switch_text": True,
            "ccswitch_has_ccswitch_marker": True,
            "ccswitch_has_import_link_marker": False,
        },
    )

    lock = xianyu_admin._cc_public_sale_lock_summary(refresh=False)

    assert lock["can_internal_test"] is False
    assert lock["can_public_sale"] is False
    assert lock["gates"]["ccswitch_import_ready"] is False
    assert lock["inventory"]["ccswitch_entry_http"] == 200
    assert "CC Switch 导入入口异常" in lock["blockers"]


def test_xianyu_admin_background_readiness_audit_gate(monkeypatch):
    monkeypatch.setenv("CC_XIANYU_AUTO_READINESS_AUDIT_ENABLED", "1")
    monkeypatch.setenv("CC_XIANYU_AUTO_READINESS_AUDIT_INTERVAL_MS", "300000")

    assert xianyu_admin._should_run_background_readiness_audit(now_ts=400, last_run_at=0) is True
    assert xianyu_admin._should_run_background_readiness_audit(now_ts=400, last_run_at=200) is False

    monkeypatch.setenv("CC_XIANYU_AUTO_READINESS_AUDIT_ENABLED", "0")
    assert xianyu_admin._should_run_background_readiness_audit(now_ts=400, last_run_at=0) is False


def test_xianyu_admin_background_readiness_audit_runs_readonly(monkeypatch):
    monkeypatch.setenv("CC_XIANYU_AUTO_READINESS_AUDIT_ENABLED", "1")
    monkeypatch.setenv("CC_XIANYU_AUTO_READINESS_AUDIT_INTERVAL_MS", "300000")
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_background_readiness_audit_at", 0.0)
    monkeypatch.setattr("src.xianyu.xianyu_admin.time.time", lambda: 400.0)
    calls = []

    def _fake_audit(mode):
        calls.append(mode)
        return {
            "ok": True,
            "summary": {
                "redeem_available": 5,
                "sub2api_active_channels": 10,
                "sub2api_enabled_monitors": 10,
                "config_contract_ok": True,
            },
        }

    monkeypatch.setattr("src.xianyu.xianyu_admin._run_cc_readiness_audit", _fake_audit)

    result = xianyu_admin._run_background_readiness_audit_once()

    assert result == {"ran": True, "ok": True}
    assert calls == ["read_only"]
    assert xianyu_admin._last_background_readiness_audit_at == 400.0


def test_xianyu_admin_background_strict_audit_runs_once(monkeypatch):
    monkeypatch.setenv("CC_XIANYU_AUTO_STRICT_AUDIT_ENABLED", "1")
    monkeypatch.setenv("CC_XIANYU_AUTO_STRICT_AUDIT_INTERVAL_MS", "60000")
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_background_strict_audit_at", 0.0)
    calls = []

    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda: {
            "stage": "waiting_buyer_chain",
            "ready_for_public_sale": False,
            "can_auto_ship_paid_orders": True,
            "checks": {
                "pending_rescue": 0,
                "sent_real_orders": 1,
            },
        },
    )
    monkeypatch.setattr("src.xianyu.xianyu_admin.time.time", lambda: 120.0)

    def _fake_strict(mode):
        calls.append(mode)
        return {
            "ok": False,
            "exit_code": 1,
            "summary": {"same_order_ready": 0},
        }

    monkeypatch.setattr("src.xianyu.xianyu_admin._run_cc_readiness_audit", _fake_strict)

    result = xianyu_admin._run_background_strict_audit_once()

    assert result["ran"] is True
    assert result["ok"] is False
    assert result["stage"] == "waiting_buyer_chain"
    assert result["same_order_ready"] == 0
    assert result["updated_at"]
    assert calls == ["strict"]
    assert xianyu_admin._last_background_strict_audit_at == 120.0
    assert xianyu_admin._last_background_strict_audit_result["ran"] is True


def test_xianyu_admin_status_and_loop_watch_expose_background_strict_audit(monkeypatch):
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._last_background_strict_audit_result",
        {
            "ran": True,
            "ok": False,
            "stage": "waiting_buyer_chain",
            "same_order_ready": 0,
            "updated_at": "2026-07-05T18:40:00-04:00",
        },
    )
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_background_strict_audit_at", 123.0)
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda: {
            "stage": "waiting_buyer_chain",
            "stage_label": "已自动发货，等待买家完成兑换/API/调模型严格闭环",
            "next_action": "等待后台观察",
            "can_auto_ship_paid_orders": True,
            "ready_for_public_sale": False,
            "checks": {"pending_rescue": 0, "sent_real_orders": 1},
            "last_background_strict_audit": xianyu_admin._last_background_strict_audit_result,
        },
    )

    client = TestClient(xianyu_admin.app)
    status = client.get("/api/status")
    watch = client.get("/api/cc-loop-watch")

    assert status.status_code == 200
    assert status.json()["cc_background_strict_audit"]["last"]["ran"] is True
    assert status.json()["cc_background_strict_audit"]["last_at"] == 123.0
    assert watch.status_code == 200
    assert watch.json()["last_background_strict_audit"]["stage"] == "waiting_buyer_chain"


def test_xianyu_admin_restores_strict_audit_from_context(monkeypatch):
    class _Context:
        def cc_final_sale_gate_summary(self):
            return {"sent_real_orders": 1, "buyer_chain_verified_orders": 1, "pending_rescue": 0}

        def latest_cc_strict_audit(self):
            return {
                "id": 8,
                "ok": True,
                "exit_code": 0,
                "same_order_ready": 1,
                "same_order_matched": 1,
                "real_orders": 1,
                "updated_at": "2026-07-05 12:00:00",
                "source": "sqlite",
                "summary": {
                    "same_order_ready": 1,
                    "same_order_matched": 1,
                    "real_orders": 1,
                    "same_order_latest": [
                        {
                            "orderIdPrefix": "xy_oid_",
                            "orderIdHash": "abc123",
                            "balanceRedeemed": True,
                            "activeTokens": 1,
                            "modelLogsAfterRedeem": 2,
                            "ready": True,
                            "apiKey": "should-not-leak",
                        }
                    ],
                },
            }

    monkeypatch.setattr("src.xianyu.xianyu_admin._ctx", _Context())
    monkeypatch.setattr("src.xianyu.xianyu_admin._last_cc_strict_audit", {})

    latest = xianyu_admin._latest_strict_audit()

    assert latest["ok"] is True
    assert latest["same_order_ready"] == 1
    assert latest["persisted"] is True
    assert latest["audit_id"] == 8
    assert latest["summary"]["same_order_latest"][0]["ready"] is True
    assert "apiKey" not in latest["summary"]["same_order_latest"][0]
    assert xianyu_admin._strict_audit_ready() is True


def test_xianyu_admin_buyer_progress_marks_verified_chain_from_strict_summary(monkeypatch):
    """严格门通过后，买家进度必须显示完整闭环，不能误报未兑换。"""
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._last_cc_strict_audit",
        {
            "ok": True,
            "exit_code": 0,
            "same_order_ready": 1,
            "same_order_matched": 1,
            "real_orders": 1,
            "summary": {
                "same_order_ready": 1,
                "same_order_matched": 1,
                "real_orders": 1,
                "same_order_latest": [
                    {
                        "orderIdPrefix": "xy_oid_",
                        "balanceRedeemed": True,
                        "activeTokens": 1,
                        "modelLogsAfterRedeem": 2,
                        "ready": True,
                    }
                ],
            },
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda: {
            "stage": "closed_loop_verified",
            "checks": {
                "sent_real_orders": 1,
                "buyer_chain_verified_orders": 1,
            },
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._ctx",
        type(
            "Ctx",
            (),
            {
                "cc_final_sale_gate_summary": lambda self: {
                    "sent_real_orders": 1,
                    "buyer_chain_verified_orders": 1,
                    "pending_rescue": 0,
                }
            },
        )(),
    )

    progress = xianyu_admin._cc_buyer_chain_progress_summary()

    assert progress["stage"] == "verified"
    assert progress["steps"] == {
        "paid_order_shipped": True,
        "card_redeemed": True,
        "api_key_created": True,
        "model_called": True,
        "same_order_verified": True,
    }
    assert progress["latest_orders"][0]["modelLogsAfterRedeem"] == 2


def test_xianyu_admin_buyer_progress_does_not_unlock_from_old_summary(monkeypatch):
    """旧严格门缓存缺少 xy_oid_ 明细时，只能作为内测历史，不能显示正式闭环。"""
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._last_cc_strict_audit",
        {
            "ok": True,
            "exit_code": 0,
            "same_order_ready": 1,
            "same_order_matched": 1,
            "real_orders": 1,
            "summary": {"same_order_ready": 1},
        },
    )
    monkeypatch.setattr(
        "src.xianyu.xianyu_admin._cc_loop_watch_summary",
        lambda: {
            "stage": "closed_loop_verified",
            "checks": {
                "sent_real_orders": 1,
                "buyer_chain_verified_orders": 1,
            },
        },
    )

    progress = xianyu_admin._cc_buyer_chain_progress_summary()

    assert progress["stage"] == "waiting_redeem"
    assert progress["steps"]["same_order_verified"] is False
    assert progress["counts"]["same_order_ready"] == 0


def test_social_extension_page_probe_route_accepts_json_body(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_probe(payload):
        captured.update(payload)
        return {
            "success": True,
            "platform": payload.get("platform"),
            "ready": bool(payload.get("ready")),
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }

    monkeypatch.setattr(
        "src.api.routers.social.ClawBotRPC._rpc_social_extension_page_probe_update",
        _fake_probe,
    )

    response = client.post(
        "/api/v1/social/extension/page-probe",
        json={"platform": "xhs", "ready": True, "availableFields": [{"name": "title"}]},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured["platform"] == "xhs"
    assert captured["ready"] is True


def test_social_persona_review_route_accepts_json_body(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_review(approved=True, reviewer="owner", notes=""):
        captured["approved"] = approved
        captured["reviewer"] = reviewer
        captured["notes"] = notes
        return {
            "success": True,
            "approved": approved,
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }

    monkeypatch.setattr(
        "src.api.routers.social.ClawBotRPC._rpc_social_persona_review_update",
        _fake_review,
    )

    response = client.post(
        "/api/v1/social/persona-review",
        json={"approved": False, "reviewer": "owner", "notes": "方向太 AI，继续追热点抽象。"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured == {
        "approved": False,
        "reviewer": "owner",
        "notes": "方向太 AI，继续追热点抽象。",
    }


def test_social_extension_draft_schedule_route_accepts_json_body(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_schedule(draft_id, scheduled_at="", reviewer="owner"):
        captured["draft_id"] = draft_id
        captured["scheduled_at"] = scheduled_at
        captured["reviewer"] = reviewer
        return {
            "success": True,
            "schedule_item": {"draft_id": draft_id, "scheduled_at": scheduled_at},
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }

    monkeypatch.setattr(
        "src.api.routers.social.ClawBotRPC._rpc_social_extension_draft_schedule",
        _fake_schedule,
    )

    response = client.post(
        "/api/v1/social/extension/drafts/ext-x-demo/schedule",
        json={"scheduled_at": "2026-06-24T08:30:00-06:00", "reviewer": "owner"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured == {
        "draft_id": "ext-x-demo",
        "scheduled_at": "2026-06-24T08:30:00-06:00",
        "reviewer": "owner",
    }


def test_social_extension_schedule_route_returns_queue(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_queue(limit=20):
        captured["limit"] = limit
        return {
            "success": True,
            "count": 1,
            "due_count": 1,
            "queue": [
                {
                    "draft_id": "ext-x-due",
                    "platform": "x",
                    "title": "到点提醒",
                    "status": "awaiting_final_confirmation",
                    "draft": {"id": "ext-x-due", "title": "到点提醒"},
                }
            ],
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }

    monkeypatch.setattr(
        "src.api.routers.social.ClawBotRPC._rpc_social_extension_schedule_queue",
        _fake_queue,
    )

    response = client.get("/api/v1/social/extension/schedule?limit=12")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["queue"][0]["draft"]["id"] == "ext-x-due"
    assert response.json()["auto_publish_enabled"] is False
    assert captured == {"limit": 12}


def test_social_extension_schedule_final_confirm_route_exists(monkeypatch):
    server = APIServer()
    client = TestClient(server.app)
    captured = {}

    def _fake_confirm(draft_id, reviewer="owner"):
        captured["draft_id"] = draft_id
        captured["reviewer"] = reviewer
        return {
            "success": True,
            "manual_publish_ready": True,
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }

    monkeypatch.setattr(
        "src.api.routers.social.ClawBotRPC._rpc_social_extension_schedule_final_confirm",
        _fake_confirm,
    )

    response = client.post(
        "/api/v1/social/extension/drafts/ext-x-final/final-confirm",
        json={"reviewer": "owner"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert captured == {"draft_id": "ext-x-final", "reviewer": "owner"}
