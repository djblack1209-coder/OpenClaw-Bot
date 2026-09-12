"""Real locked Router with synthetic transport: retries must enter the ledger."""

import asyncio
from types import SimpleNamespace

import litellm
import pytest

from src.core.accounted_completion import accounted_completion
from src.core.accounted_router import AccountedRouter
from src.core.cost_control import CostController
from src.core.cost_ledger import BudgetDenied


@pytest.fixture(autouse=True)
async def finish_sdk_logging_tasks():
    """A test loop must finish the locked SDK's callbacks before it is closed."""
    yield
    from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER
    if GLOBAL_LOGGING_WORKER._bound_loop is asyncio.get_running_loop():
        await asyncio.wait_for(GLOBAL_LOGGING_WORKER.flush(), timeout=5)
        await GLOBAL_LOGGING_WORKER.stop()


def deployment(name="primary", price="1"):
    return {
        "model_name": name,
        "litellm_params": {"model": "openai/gpt-4o-mini", "api_key": "fixture"},
        "model_info": {
            "id": name,
            "accounting": {
                "provider": "fixture",
                "snapshot": "fixture-v1",
                "currency": "USD",
                "source": "synthetic-test",
                "input_per_million": price,
                "output_per_million": price,
                "max_input_tokens": 100,
                "max_output_tokens": 100,
            },
        },
    }


@pytest.fixture
def controller(tmp_path, monkeypatch):
    cc = CostController(1, ledger_path=tmp_path / "cost.sqlite3")
    cc.ledger.activate(opening_spend_usd=0)
    monkeypatch.setattr("src.core.accounted_router.get_cost_controller", lambda: cc)
    return cc


def response(call=None):
    if call is not None:
        call["litellm_logging_obj"].post_call(
            original_response={"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        )
    return litellm.ModelResponse(
        model="gpt-4o-mini",
        choices=[{"message": {"content": "ok"}}],
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )


@pytest.mark.asyncio
async def test_real_router_fallback_accounts_for_each_attempt(controller, monkeypatch):
    calls = []

    async def transport(**kwargs):
        calls.append(kwargs)
        assert kwargs["max_retries"] == kwargs["num_retries"] == 0
        if len(calls) == 1:
            raise litellm.AuthenticationError(message="fixture", model="gpt-4o-mini", llm_provider="openai")
        return response(kwargs)

    monkeypatch.setattr(litellm, "acompletion", transport)
    router = AccountedRouter(
        model_list=[deployment(), deployment("fallback")], fallbacks=[{"primary": ["fallback"]}], num_retries=0
    )
    await router.acompletion(model="primary", messages=[{"role": "user", "content": "test"}], max_tokens=10)
    rows = controller.ledger.attempts()
    assert len(calls) == len(rows) == 2
    assert {row["state"] for row in rows} == {"unknown", "settled"}
    assert len({row["request_id"] for row in rows}) == 1
    assert {row["deployment_id"] for row in rows} == {"primary", "fallback"}


@pytest.mark.asyncio
async def test_real_router_retry_accounts_for_each_attempt(controller, monkeypatch):
    calls = []

    async def transport(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise litellm.RateLimitError(message="fixture", model="gpt-4o-mini", llm_provider="openai")
        return response(kwargs)

    monkeypatch.setattr(litellm, "acompletion", transport)
    second = deployment()
    second["model_info"]["id"] = "primary-2"
    from litellm.router import RetryPolicy

    router = AccountedRouter(
        model_list=[deployment(), second],
        num_retries=1,
        retry_after=0,
        retry_policy=RetryPolicy(RateLimitErrorRetries=1),
    )
    await router.acompletion(model="primary", messages=[{"role": "user", "content": "test"}], max_tokens=10)
    assert len(calls) == len(controller.ledger.attempts()) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["budget", "price", "coverage"])
async def test_accounting_denial_never_falls_back_or_sends(controller, monkeypatch, problem):
    calls = []

    async def transport(**kwargs):
        calls.append(kwargs)
        return response(kwargs)

    monkeypatch.setattr(litellm, "acompletion", transport)
    dep = deployment()
    if problem == "budget":
        controller._daily_budget = 0
    elif problem == "price":
        dep["model_info"].pop("accounting")
    else:
        controller.ledger = type(controller.ledger)(controller.ledger.path.with_name("inactive.sqlite3"))
    router = AccountedRouter(
        model_list=[dep, deployment("fallback", "0")], fallbacks=[{"primary": ["fallback"]}], num_retries=3
    )
    with pytest.raises(BudgetDenied):
        await router.acompletion(model="primary", messages=[], max_tokens=10)
    assert not calls
    assert controller.ledger.attempts() == []


class Stream:
    def __init__(self, chunks, error=None):
        self.chunks, self.error, self.closed = list(chunks), error, False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.chunks:
            return self.chunks.pop(0)
        if self.error:
            raise self.error
        raise StopAsyncIteration

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["complete", "missing", "error", "cancel", "early", "unstarted"])
async def test_stream_lifecycle_never_releases_ambiguous_cost(controller, mode):
    chunk = SimpleNamespace(usage=response().usage if mode != "missing" else None)
    error = {"error": RuntimeError("fixture"), "cancel": asyncio.CancelledError()}.get(mode)
    raw = Stream([chunk, chunk], error)

    async def transport(**kwargs):
        return raw

    stream = await accounted_completion(
        deployment=deployment(),
        controller=controller,
        transport=transport,
        params={"messages": [], "max_tokens": 10, "stream": True},
    )
    if mode == "unstarted":
        await stream.aclose()
    elif mode == "early":
        await stream.__anext__()
        await stream.aclose()
    elif error:
        with pytest.raises(type(error)):
            async for _ in stream:
                pass
    else:
        async for _ in stream:
            pass
    await stream.aclose()
    (row,) = controller.ledger.attempts()
    assert row["state"] == ("settled" if mode == "complete" else "unknown")
    assert raw.closed
    assert controller.ledger.stats()["reserved_usd"] == (0 if mode == "complete" else pytest.approx(0.00011))


def test_pool_uses_accounted_router():
    from src.litellm_router import LiteLLMPool

    pool = LiteLLMPool()
    pool._router_model_list = [deployment()]
    assert isinstance(pool._create_router(), AccountedRouter)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["complete", "missing", "partial_usage", "error", "cancel", "early", "unstarted"])
async def test_real_sdk_sse_lifecycle(controller, monkeypatch, mode):
    """Exercise real LiteLLM/OpenAI stream wrappers down to HTTP resource closure."""
    import json

    import httpx
    from openai import AsyncOpenAI

    class Body(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            chunk = {
                "id": "fixture",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}],
            }
            yield ("data: " + json.dumps(chunk) + "\n\n").encode()
            if mode == "error":
                raise httpx.ReadError("synthetic disconnect")
            if mode == "cancel":
                raise asyncio.CancelledError()
            chunk["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            yield ("data: " + json.dumps(chunk) + "\n\n").encode()
            if mode != "missing":
                chunk["choices"] = []
                chunk["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                if mode == "partial_usage":
                    chunk["usage"].pop("prompt_tokens")
                yield ("data: " + json.dumps(chunk) + "\n\n").encode()
            yield b"data: [DONE]\n\n"

        async def aclose(self):
            self.closed = True

    body, requests = Body(), []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=body)

    client = AsyncOpenAI(api_key="fixture", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    router = AccountedRouter(model_list=[deployment()], num_retries=0)
    monkeypatch.setattr(router, "_get_async_openai_model_client", lambda **kwargs: client)
    from src.litellm_router import LiteLLMPool

    pool = LiteLLMPool()
    pool._router = router
    try:
        stream = await pool.acompletion(
            model_family="primary",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=10,
            stream=True,
            stream_options={"include_usage": True},
        )
        if mode == "unstarted":
            await stream.aclose()
        elif mode == "early":
            await stream.__anext__()
            await stream.aclose()
        elif mode in {"error", "cancel"}:
            with pytest.raises(asyncio.CancelledError if mode == "cancel" else Exception):
                async for _ in stream:
                    pass
        else:
            async for _ in stream:
                pass
        await stream.aclose()
        assert body.closed
        assert len(requests) == 1
        (row,) = controller.ledger.attempts()
        assert row["state"] == ("settled" if mode == "complete" else "unknown")
        assert controller.ledger.stats()["accounting_complete"] is (mode == "complete")
        if mode == "complete":
            assert row["usage_source"] == "provider_reported"
            assert pool._total_input_tokens == 10
            assert pool._total_output_tokens == 5
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "test", "cache_control": {"type": "ephemeral"}}]}
            ]
        },
        {"system": [{"type": "text", "text": "test", "cache_control": {"type": "ephemeral"}}]},
        {"tools": [{"name": "test", "input_schema": {}, "cache_control": {"type": "ephemeral"}}]},
        {"tools": [{"type": "web_search_20250305", "name": "web_search"}]},
        {"tools": [{"type": "code_execution_20250522", "name": "code_execution"}]},
    ],
)
async def test_extra_billing_requests_are_denied_before_send(controller, payload):
    from unittest.mock import AsyncMock

    send = AsyncMock()
    with pytest.raises(BudgetDenied):
        await accounted_completion(
            deployment=deployment(), controller=controller, transport=send, params={"max_tokens": 10, **payload}
        )
    send.assert_not_awaited()
    assert controller.ledger.attempts() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("price", ["0", "1"])
@pytest.mark.parametrize(
    "extra,stored",
    [
        ({"cache_creation_input_tokens": 5}, "cache_write_tokens"),
        ({"server_tool_use": {"web_search_requests": 2}}, "web_search_requests"),
        ({"web_search_requests": 2}, "web_search_requests"),
        ({"server_tool_use": {"code_execution_requests": 1}}, "code_execution_requests"),
        ({"prompt_tokens_details": {"audio_tokens": 3}}, "audio_input_tokens"),
    ],
)
async def test_extra_usage_retains_reservation_and_safe_numeric_evidence(controller, price, extra, stored):
    import json

    async def send(**kwargs):
        return SimpleNamespace(usage={"prompt_tokens": 10, "completion_tokens": 5, **extra})

    await accounted_completion(
        deployment=deployment(price=price), controller=controller, transport=send, params={"max_tokens": 10}
    )
    (row,) = controller.ledger.attempts()
    assert row["state"] == "unknown"
    assert json.loads(row["usage_json"])[stored] > 0
    assert json.loads(row["usage_json"])["input_tokens"] == 10
    assert not controller.ledger.stats()["accounting_complete"]
    assert controller.ledger.stats()["reserved_usd"] == pytest.approx(float(price) * 110 / 1_000_000)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["missing", "empty", "missing_input", "missing_output", "zero", "positive"])
async def test_real_sdk_nonstream_does_not_settle_default_usage(controller, monkeypatch, mode):
    import json

    import httpx
    from openai import AsyncOpenAI

    from src.litellm_router import LiteLLMPool

    requests = []
    raw_usage = {
        "missing": None,
        "empty": {},
        "missing_input": {"completion_tokens": 5},
        "missing_output": {"prompt_tokens": 10},
        "zero": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "positive": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }[mode]

    def handle(request):
        requests.append(request)
        body = {
            "id": "fixture",
            "object": "chat.completion",
            "created": 1,
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
        }
        if raw_usage is not None:
            body["usage"] = raw_usage
        return httpx.Response(200, json=body)

    client = AsyncOpenAI(api_key="fixture", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    router = AccountedRouter(model_list=[deployment()], num_retries=0)
    monkeypatch.setattr(router, "_get_async_openai_model_client", lambda **kwargs: client)
    pool = LiteLLMPool()
    pool._router = router
    try:
        await pool.acompletion(model_family="primary", messages=[{"role": "user", "content": "test"}], max_tokens=10, no_cache=True)
        (row,) = controller.ledger.attempts()
        complete = mode in {"zero", "positive"}
        assert row["state"] == ("settled" if complete else "unknown")
        assert row["usage_source"] == ("unknown" if mode == "missing" else "provider_reported")
        assert controller.ledger.stats()["accounting_complete"] is complete
        assert controller.ledger.stats()["reserved_usd"] == pytest.approx(0 if complete else 0.00011)
        assert row["amount_units"] == ({"zero": 0, "positive": 15000}.get(mode))
        if mode == "missing_input":
            assert json.loads(row["usage_json"]) == {"output_tokens": 5}
        if mode == "missing_output":
            assert json.loads(row["usage_json"]) == {"input_tokens": 10}
        assert len(requests) == 1
        # Let SDK background success hooks finish before pytest closes the loop.
        await asyncio.sleep(0.01)
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("price", ["0", "1"])
@pytest.mark.parametrize("sdk_usage", [False, True])
@pytest.mark.parametrize(
    "details,stored",
    [
        ({"prompt_tokens_details": {"web_search_requests": 2}}, "web_search_requests"),
        ({"prompt_tokens_details": {"cache_creation_tokens": 7}}, "cache_write_tokens"),
        (
            {"prompt_tokens_details": {"cache_creation_token_details": {"ephemeral_5m_input_tokens": 7}}},
            "cache_write_tokens",
        ),
        ({"prompt_tokens_details": {"image_count": 2}}, None),
        ({"prompt_tokens_details": {"video_length_seconds": 1.5}}, None),
        ({"completion_tokens_details": {"accepted_prediction_tokens": 3}}, None),
        ({"completion_tokens_details": {"future_service": {"requests": 1}}}, None),
    ],
)
async def test_nested_usage_never_silently_settles(controller, price, sdk_usage, details, stored):
    import json

    data = {"prompt_tokens": 10, "completion_tokens": 5, **details}
    value = litellm.Usage(**data) if sdk_usage else data

    async def send(**kwargs):
        return SimpleNamespace(usage=value)

    await accounted_completion(
        deployment=deployment(price=price), controller=controller, transport=send, params={"max_tokens": 10}
    )
    (row,) = controller.ledger.attempts()
    assert row["state"] == "unknown"
    evidence = json.loads(row["usage_json"])
    assert evidence["input_tokens"] == 10
    if stored:
        assert evidence[stored] > 0
    assert not controller.ledger.stats()["accounting_complete"]
    assert controller.ledger.stats()["reserved_usd"] == pytest.approx(float(price) * 110 / 1_000_000)


@pytest.mark.asyncio
async def test_real_sdk_http_attempt_has_no_hidden_retries(controller, monkeypatch):
    import httpx
    from openai import AsyncOpenAI

    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(429, json={"error": {"message": "fixture", "type": "rate_limit_error"}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    client = AsyncOpenAI(api_key="fixture", http_client=http, max_retries=2)
    router = AccountedRouter(model_list=[deployment()], num_retries=0)
    monkeypatch.setattr(router, "_get_async_openai_model_client", lambda **kwargs: client)
    try:
        with pytest.raises(litellm.RateLimitError):
            await router.acompletion(model="primary", messages=[{"role": "user", "content": "test"}], max_tokens=10)
        assert len(requests) == len(controller.ledger.attempts()) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_native_http_retries_are_separate_attempts(controller, monkeypatch):
    import httpx

    from src.http_client import ResilientHTTPClient, RetryConfig

    monkeypatch.setattr("src.core.cost_control.get_cost_controller", lambda: controller)
    requests = []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503, json={"error": "fixture"})
        return httpx.Response(200, json={"usage": {"input_tokens": 10, "output_tokens": 5}})

    client = ResilientHTTPClient(name="fixture", retry_config=RetryConfig(max_retries=1, base_delay=0))
    monkeypatch.setattr(
        client, "_new_client", lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    await client.post(
        "https://fixture.invalid/messages", json={"messages": [], "max_tokens": 10}, llm_accounting=deployment()
    )
    assert len(requests) == len(controller.ledger.attempts()) == 2
    assert {row["state"] for row in controller.ledger.attempts()} == {"unknown", "settled"}
    assert len({row["request_id"] for row in controller.ledger.attempts()}) == 1


@pytest.mark.asyncio
async def test_settlement_failure_does_not_resend(controller, monkeypatch):
    from src.core.cost_ledger import LedgerError

    calls = []

    async def send(**kwargs):
        calls.append(kwargs)
        return response(kwargs)

    def unavailable(*args, **kwargs):
        raise LedgerError("fixture write failure")

    monkeypatch.setattr(litellm, "acompletion", send)
    monkeypatch.setattr(controller.ledger, "settle", unavailable)
    router = AccountedRouter(
        model_list=[deployment(), deployment("fallback")], fallbacks=[{"primary": ["fallback"]}], num_retries=3
    )
    with pytest.raises(LedgerError):
        await router.acompletion(model="primary", messages=[], max_tokens=10)
    assert len(calls) == 1
    assert controller.ledger.attempts()[0]["state"] == "dispatched"


@pytest.mark.asyncio
async def test_pool_cache_hit_does_not_charge_previous_usage(controller, monkeypatch):
    from src.litellm_router import LiteLLMPool

    calls = []
    cache = {}

    async def send(**kwargs):
        calls.append(kwargs)
        return response(kwargs)

    monkeypatch.setattr(litellm, "acompletion", send)
    monkeypatch.setattr("src.litellm_router._llm_cache_get", cache.get)
    monkeypatch.setattr("src.litellm_router._llm_cache_set", lambda key, value, ttl: cache.update({key: value}))
    pool = LiteLLMPool()
    pool._router = AccountedRouter(model_list=[deployment()])
    request = {"model_family": "primary", "messages": [], "max_tokens": 10}
    await pool.acompletion(**request)
    await pool.acompletion(**request)
    assert len(calls) == len(controller.ledger.attempts()) == 1
    await pool.acompletion(**request, no_cache=True)
    await pool.acompletion(**{**request, "max_tokens": 20})
    assert len(calls) == len(controller.ledger.attempts()) == 3


@pytest.mark.asyncio
async def test_unknown_price_probe_is_not_a_dead_key(controller, monkeypatch):
    from src.litellm_router import LiteLLMPool

    pool = LiteLLMPool()
    dep = pool._dep("fixture", "openai/gpt-4o-mini", "fixture")
    pool._router_model_list = [dep]
    status = await pool.health_check()
    assert status["healthy"] == 0
    assert status["not_executed"] == ["fixture"]
    assert status["disabled"] == []
    assert not pool._sources["fixture"][0].disabled
    assert controller.ledger.attempts() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"api_base": "https://other.invalid"},
        {"n": 2},
        {"max_tokens": -1},
        {"max_tokens": 10, "max_completion_tokens": 20},
        {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": "fixture"}]}]},
    ],
)
async def test_unbounded_or_reidentified_request_is_never_sent(controller, extra):
    from unittest.mock import AsyncMock

    from src.core.cost_ledger import LedgerError

    transport = AsyncMock()
    with pytest.raises(LedgerError):
        await accounted_completion(
            deployment=deployment(),
            controller=controller,
            transport=transport,
            params={"messages": [], "max_tokens": 10, **extra},
        )
    transport.assert_not_awaited()
    assert controller.ledger.attempts() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing_usage", "cache_usage", "configured_zero"])
async def test_unknown_billing_is_distinct_from_configured_zero(controller, kind):
    value = response()
    if kind == "cache_usage":
        value.usage = litellm.Usage(prompt_tokens=10, completion_tokens=5, prompt_tokens_details={"cached_tokens": 4})
    else:
        value.usage = None

    async def send(**kwargs):
        return value

    await accounted_completion(
        deployment=deployment(price="0" if kind == "configured_zero" else "1"),
        controller=controller,
        transport=send,
        params={"max_tokens": 10},
    )
    (row,) = controller.ledger.attempts()
    assert row["state"] == ("settled" if kind == "configured_zero" else "unknown")
    assert row["amount_units"] == (0 if kind == "configured_zero" else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("deny", [False, True])
async def test_real_instructor_validation_retry_and_accounting_denial(controller, monkeypatch, deny):
    from unittest.mock import AsyncMock

    from pydantic import BaseModel

    import src.litellm_router as routing
    import src.structured_llm as structured

    class Answer(BaseModel):
        answer: str

    calls = []

    async def send(**kwargs):
        calls.append(kwargs)
        value = response(kwargs)
        value.choices[0].message.content = '{"wrong":true}' if len(calls) == 1 else '{"answer":"ok"}'
        return value

    monkeypatch.setattr(litellm, "acompletion", send)
    router = AccountedRouter(model_list=[deployment()])
    monkeypatch.setattr(routing, "free_pool", SimpleNamespace(router_for_current_loop=lambda: router))
    fallback = AsyncMock()
    monkeypatch.setattr(structured, "_fallback_path", fallback)
    if deny:
        controller._daily_budget = 0
        with pytest.raises(BudgetDenied):
            await structured.structured_completion(Answer, [], model_family="primary", max_tokens=10)
        assert not calls
    else:
        result = await structured.structured_completion(Answer, [], model_family="primary", max_tokens=10)
        assert result.answer == "ok"
        assert len(calls) == len(controller.ledger.attempts()) == 2
    fallback.assert_not_awaited()
