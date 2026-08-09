import pytest
from fastapi import HTTPException

from src.api.routers import newapi


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHttp:
    def __init__(self):
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _FakeResponse({"success": True, "data": {"ok": True}, "message": "success"})

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return _FakeResponse({"success": True, "data": {"online": True}})

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _FakeResponse({"success": True, "data": {"created": True}})


@pytest.fixture
def fake_newapi(monkeypatch):
    fake = _FakeHttp()
    monkeypatch.setattr(newapi, "_NEWAPI_BASE", "https://new-api.example")
    monkeypatch.setattr(newapi, "_NEWAPI_TOKEN", "root-token")
    monkeypatch.setattr(newapi, "_NEWAPI_USER_ID", "1")
    monkeypatch.setattr(newapi, "_http", fake)
    return fake


@pytest.mark.asyncio
async def test_newapi_proxy_keeps_latest_token_search_contract(fake_newapi):
    result = await newapi.search_tokens(keyword="demo", token="sk-demo", page=2, size=30)

    assert result["success"] is True
    method, url, kwargs = fake_newapi.calls[-1]
    assert method == "GET"
    assert url == "https://new-api.example/api/token/search"
    assert kwargs["headers"]["Authorization"] == "Bearer root-token"
    assert kwargs["headers"]["New-Api-User"] == "1"
    assert kwargs["params"] == {"keyword": "demo", "token": "sk-demo", "p": 2, "size": 30}


@pytest.mark.asyncio
async def test_newapi_proxy_maps_usage_subscription_and_affiliate_routes(fake_newapi):
    await newapi.self_log_stat(model_name="gpt-5.5", token_name="main", group="default")
    await newapi.self_quota_dates(start_timestamp=100, end_timestamp=200)
    await newapi.list_subscription_plans()
    await newapi.affiliate_transfer({"quota": 100})

    calls = [(method, url, kwargs.get("params"), kwargs.get("json")) for method, url, kwargs in fake_newapi.calls]
    assert calls[0][0:2] == ("GET", "https://new-api.example/api/log/self/stat")
    assert calls[0][2]["model_name"] == "gpt-5.5"
    assert calls[1] == ("GET", "https://new-api.example/api/data/self", {"start_timestamp": 100, "end_timestamp": 200}, None)
    assert calls[2][0:2] == ("GET", "https://new-api.example/api/subscription/plans")
    assert calls[3] == ("POST", "https://new-api.example/api/user/aff_transfer", None, {"quota": 100})


@pytest.mark.asyncio
async def test_newapi_proxy_rejects_admin_calls_without_token(monkeypatch):
    monkeypatch.setattr(newapi, "_NEWAPI_TOKEN", "")

    with pytest.raises(HTTPException) as exc:
        await newapi.create_redemption({"name": "day-card", "quota": 100})

    assert exc.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "proxy_call",
    [
        pytest.param(lambda: newapi.newapi_status(), id="status"),
        pytest.param(lambda: newapi.list_channels(), id="list-channels"),
        pytest.param(lambda: newapi.list_tokens(), id="list-tokens"),
        pytest.param(lambda: newapi.create_channel(newapi.ChannelCreate(name="test")), id="create-channel"),
        pytest.param(lambda: newapi.update_channel(newapi.ChannelCreate(name="test"), 1), id="update-channel"),
        pytest.param(lambda: newapi.delete_channel(1), id="delete-channel"),
        pytest.param(lambda: newapi.toggle_channel_status(1), id="toggle-channel"),
        pytest.param(lambda: newapi.delete_token(1), id="delete-token"),
        pytest.param(lambda: newapi.search_tokens(), id="search-tokens"),
        pytest.param(lambda: newapi.create_token(newapi.TokenCreate(name="test")), id="create-token"),
        pytest.param(lambda: newapi.update_token(newapi.TokenCreate(name="test"), 1), id="update-token"),
        pytest.param(lambda: newapi.update_token_status(1, 1), id="toggle-token"),
        pytest.param(lambda: newapi.list_self_logs(), id="list-logs"),
        pytest.param(lambda: newapi.self_log_stat(), id="log-stat"),
        pytest.param(lambda: newapi.self_quota_dates(1, 2), id="quota-dates"),
        pytest.param(lambda: newapi.list_subscription_plans(), id="subscription-plans"),
        pytest.param(lambda: newapi.subscription_self(), id="subscription-self"),
        pytest.param(lambda: newapi.list_redemptions(), id="list-redemptions"),
        pytest.param(lambda: newapi.create_redemption({"name": "test"}), id="create-redemption"),
        pytest.param(lambda: newapi.pricing(), id="pricing"),
        pytest.param(lambda: newapi.topup_info(), id="topup-info"),
        pytest.param(lambda: newapi.affiliate_code(), id="affiliate-code"),
        pytest.param(lambda: newapi.affiliate_transfer(), id="affiliate-transfer"),
    ],
)
async def test_newapi_proxies_fail_closed_without_base_url(monkeypatch, proxy_call):
    fake = _FakeHttp()
    monkeypatch.setattr(newapi, "_NEWAPI_BASE", "")
    monkeypatch.setattr(newapi, "_NEWAPI_TOKEN", "test-token")
    monkeypatch.setattr(newapi, "_http", fake)

    with pytest.raises(HTTPException) as exc:
        await proxy_call()

    assert exc.value.status_code == 503
    assert fake.calls == []
