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
