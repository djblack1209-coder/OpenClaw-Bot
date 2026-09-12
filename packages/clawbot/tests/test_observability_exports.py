"""Actual locked SDK queues, HTTP ingestion and OTLP serialization; no remote transport."""
import asyncio
import copy
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from src.observability_policy import OMITTED, ObservabilityPolicy

SECRET = 'sk-synthetic-export-secret-729483'
EMAIL = 'fixture.exports@example.invalid'
PHONE = '+1-202-555-0147'
CARD = '4111 1111 1111 1111'
ACCOUNT = 'DU1234567'
MARKERS = (SECRET, EMAIL, PHONE, CARD, ACCOUNT)


def assert_clean(value):
    rendered = json.dumps(value, ensure_ascii=False, default=lambda item: '<unsupported>')
    assert all(marker not in rendered for marker in MARKERS), rendered


@pytest.fixture
def langfuse_setup(monkeypatch):
    from src import langfuse_obs as obs
    obs.shutdown()
    monkeypatch.setenv('LANGFUSE_SECRET_KEY', 'sk-lf-synthetic')
    monkeypatch.setenv('LANGFUSE_PUBLIC_KEY', 'pk-lf-synthetic')
    monkeypatch.setenv('LANGFUSE_HOST', 'https://fixture.invalid')
    batches = []

    def handle(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'fixture-project', 'name': 'fixture'}]})
        batches.append(json.loads(request.content))
        return httpx.Response(200, json={'successes': [], 'errors': []})

    monkeypatch.setattr(obs, '_new_http_transport', lambda: httpx.MockTransport(handle))
    yield obs, batches
    obs.shutdown()


@pytest.mark.parametrize('mode', ['metadata', 'redacted', 'raw'])
def test_actual_langfuse_manual_event_queue_and_final_http(langfuse_setup, monkeypatch, mode):
    obs, batches = langfuse_setup
    monkeypatch.setenv('OPENCLAW_OBSERVABILITY_CONTENT', mode)
    assert obs.init_langfuse()
    client = obs._langfuse_client
    assert obs.init_langfuse() and obs._langfuse_client is client
    queued = []
    queue = client.task_manager._ingestion_queue
    original_put = queue.put

    def capture(event, *args, **kwargs):
        queued.append(copy.deepcopy(event))
        return original_put(event, *args, **kwargs)

    monkeypatch.setattr(queue, 'put', capture)
    metadata = {'nested': {'access_token': 'opaque-secret', 'message': ' '.join(MARKERS)},
                'model': 'fixture-model', 'latency_ms': 12}
    before = copy.deepcopy(metadata)
    obs.log_generation('fixture-operation', 'fixture-model', 'ordinary prompt ' + SECRET,
                       'ordinary completion ' + EMAIL, user_id=ACCOUNT, chat_id=EMAIL,
                       input_tokens=2, output_tokens=3, metadata=metadata)
    obs.log_event('event/' + EMAIL, metadata)
    obs.flush()
    assert metadata == before
    assert queued and batches, 'Actual SDK queue and final HTTP transport must both be reached'
    assert_clean(queued)
    assert_clean(batches)
    assert 'opaque-secret' not in json.dumps(queued, default=lambda value: value.isoformat() if type(value) is datetime else '<unsupported>')
    generations = [event['body'] for batch in batches for event in batch['batch'] if event['type'] == 'generation-create']
    assert generations and generations[0]['model'] == 'fixture-model'
    assert generations[0]['metadata']['reported_input_tokens'] == 2
    assert 'usage' not in generations[0] and 'usageDetails' not in generations[0]
    if mode != 'redacted':
        assert generations[0]['input'] == OMITTED and generations[0]['output'] == OMITTED
        assert 'ordinary prompt' not in json.dumps(batches)
    else:
        assert 'ordinary prompt' in generations[0]['input']
    obs.shutdown()
    assert_clean(batches)


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'error', 'cancelled'])
async def test_actual_langfuse_decorator_preserves_business_and_exception(langfuse_setup, monkeypatch, outcome):
    obs, batches = langfuse_setup
    monkeypatch.setenv('OPENCLAW_OBSERVABILITY_CONTENT', 'redacted')
    assert obs.init_langfuse()
    calls = []
    original_error = RuntimeError(SECRET + ' ' + EMAIL)

    @obs.trace_llm_call(name='fixture-operation', model='fixture-model', metadata={'nested': {'secret': SECRET}})
    async def observed(value):
        calls.append(value)
        if outcome == 'error':
            raise original_error
        if outcome == 'cancelled':
            raise asyncio.CancelledError(SECRET)
        return EMAIL

    if outcome == 'success':
        assert await observed(SECRET) == EMAIL
    elif outcome == 'error':
        with pytest.raises(RuntimeError) as caught:
            await observed(SECRET)
        assert caught.value is original_error
    else:
        with pytest.raises(asyncio.CancelledError):
            await observed(SECRET)
    assert calls == [SECRET]
    obs.flush()
    assert batches
    assert_clean(batches)


def test_final_langfuse_serialization_rechecks_payload_and_drops_unknown_write():
    from src.langfuse_obs import FilteringTransport
    sent = []
    transport = FilteringTransport(httpx.MockTransport(lambda request: sent.append(request.content) or httpx.Response(200)),
                                   ObservabilityPolicy('redacted'))
    with httpx.Client(transport=transport) as client:
        payload = {'batch': [{'id': str(uuid4()), 'type': 'trace-create',
                             'body': {'id': str(uuid4()), 'name': EMAIL, 'input': SECRET,
                                      'metadata': {'authorization': 'opaque-secret'}}}]}
        assert client.post('https://fixture.invalid/api/public/ingestion', json=payload).status_code == 200
        assert sent and SECRET.encode() not in sent[0] and EMAIL.encode() not in sent[0]
        assert b'opaque-secret' not in sent[0]
        with pytest.raises(RuntimeError, match='unsupported_observability_write'):
            client.post('https://fixture.invalid/api/public/media', json={'input': SECRET})
        with pytest.raises(RuntimeError, match='observability_serialization_rejected'):
            client.post('https://fixture.invalid/api/public/ingestion', content=SECRET)
        assert len(sent) == 1


def test_litellm_callback_registration_preserves_existing_callbacks(langfuse_setup):
    obs, batches = langfuse_setup
    existing = object()
    sdk = SimpleNamespace(success_callback=[existing, 'langfuse'], failure_callback=['langfuse', existing],
                          callbacks=[existing, 'langfuse_otel'], input_callback=['langfuse', existing])
    callback = obs.register_litellm_callbacks(sdk)
    assert obs.register_litellm_callbacks(sdk) is callback
    assert sdk.success_callback == [existing, callback] and sdk.failure_callback == [callback, existing]
    assert sdk.callbacks == [existing, callback] and sdk.input_callback == [callback, existing]
    import litellm
    response = litellm.ModelResponse(model='fixture-model', choices=[{'message': {'role': 'assistant', 'content': EMAIL}}],
                                    usage={'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 5})
    kwargs = {'model': 'fixture-model', 'messages': [{'role': 'user', 'content': SECRET}],
              'litellm_params': {'metadata': {'trace_name': EMAIL, 'nested': {'secret': SECRET}}}}
    before = copy.deepcopy(kwargs)
    now = datetime.now(UTC)
    callback.log_success_event(kwargs, response, now, now)
    callback.log_failure_event(kwargs, RuntimeError(SECRET), now, now)
    obs.flush()
    assert kwargs == before and response.choices[0].message.content == EMAIL
    assert batches
    assert_clean(batches)


@pytest.fixture
def otel_setup(monkeypatch):
    from google.protobuf.json_format import MessageToDict
    from opentelemetry.exporter.otlp.proto.common._internal.trace_encoder import encode_spans
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

    from src import observability as obs
    obs.shutdown()
    encoded = []
    spans = []

    class Sink(SpanExporter):
        def export(self, values):
            spans.extend(values)
            payload = encode_spans(values)
            # Execute the actual OTLP protobuf serializer, not span.to_json alone.
            assert payload.SerializeToString()
            encoded.append(MessageToDict(payload))
            return SpanExportResult.SUCCESS

    monkeypatch.setattr(obs, '_new_phoenix_exporter', lambda endpoint: Sink())
    monkeypatch.setenv('PHOENIX_ENDPOINT', 'https://fixture.invalid/v1/traces')
    yield obs, encoded, spans
    obs.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['metadata', 'redacted'])
async def test_actual_otel_decorator_and_queued_span_serialization(otel_setup, monkeypatch, mode):
    obs, encoded, spans = otel_setup
    monkeypatch.setenv('OPENCLAW_OBSERVABILITY_CONTENT', mode)
    assert obs.init_phoenix(), obs.get_stats()
    provider = obs._provider
    assert obs.init_phoenix() and obs._provider is provider
    calls = []
    failure = RuntimeError(SECRET + ' ' + EMAIL)

    @obs.trace_function(name='fixture-span', attributes={'model': 'fixture-model', 'input.value': SECRET,
                                                       'nested.secret': SECRET, 'user.id': EMAIL})
    async def work(value):
        calls.append(value)
        raise failure

    with pytest.raises(RuntimeError) as caught:
        await work(SECRET)
    assert caught.value is failure and calls == [SECRET]
    # The real BatchSpanProcessor queue already contains sanitized copies.
    processor = provider._active_span_processor._span_processors[0].processor
    pending = list(processor._batch_processor._queue)
    assert pending
    assert_clean([json.loads(span.to_json()) for span in pending])
    assert obs.flush()
    assert encoded and spans
    assert_clean(encoded)
    assert any(span.attributes.get('model') == 'fixture-model' for span in spans)


def test_final_otel_export_filters_resource_events_links_scope_and_status():
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import Event, ReadableSpan
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
    from opentelemetry.sdk.util.instrumentation import InstrumentationScope
    from opentelemetry.trace import Link, SpanContext, Status, StatusCode, TraceState

    from src import observability as obs
    captured = []

    class Sink(SpanExporter):
        def export(self, values):
            captured.extend(values)
            return SpanExportResult.SUCCESS

    context = SpanContext(1, 2, False, trace_state=TraceState([('fixture', SECRET)]))
    span = ReadableSpan(name=EMAIL, context=context, parent=context,
                        resource=Resource({'service.name': 'fixture', 'host.name': EMAIL, 'secret': SECRET}),
                        attributes={'model': 'fixture-model', 'nested.secret': SECRET},
                        events=[Event(EMAIL, {'exception.message': SECRET, 'exception.stacktrace': EMAIL})],
                        links=[Link(context, {'user_id': EMAIL})], status=Status(StatusCode.ERROR, SECRET),
                        instrumentation_scope=InstrumentationScope(EMAIL, attributes={'secret': SECRET}))
    exporter = obs.FilteringSpanExporter(Sink(), ObservabilityPolicy('redacted'))
    assert exporter.export([span]) == SpanExportResult.SUCCESS
    assert captured and captured[0] is not span
    assert_clean([json.loads(value.to_json()) for value in captured])
    assert span.status.description == SECRET and span.resource.attributes['host.name'] == EMAIL


@pytest.mark.asyncio
@pytest.mark.filterwarnings('error::pytest.PytestUnraisableExceptionWarning')
@pytest.mark.filterwarnings('error:coroutine .* was never awaited:RuntimeWarning')
@pytest.mark.parametrize('mode', ['success', 'stream', 'stream_missing', 'stream_partial',
                                 'stream_error', 'stream_cancel', 'stream_early', 'stream_unstarted',
                                 'error', 'cancelled', 'fallback', 'retry', 'export_failure'])
async def test_actual_router_http_callbacks_instrumentation_and_ledger(
        langfuse_setup, otel_setup, tmp_path, monkeypatch, mode):
    import litellm
    from litellm.integrations.custom_logger import CustomLogger
    from litellm.router import RetryPolicy
    from openai import AsyncOpenAI
    from test_litellm_accounting import deployment

    from src.core.accounted_router import AccountedRouter
    from src.core.cost_control import CostController

    lf, batches = langfuse_setup
    otel, encoded, spans = otel_setup
    monkeypatch.setenv('OPENCLAW_OBSERVABILITY_CONTENT', 'redacted')
    for name in ('callbacks', 'success_callback', 'failure_callback', '_async_success_callback',
                 '_async_failure_callback', 'input_callback', '_async_input_callback'):
        monkeypatch.setattr(litellm, name, [])
    observed = []

    class ExistingCallback(CustomLogger):
        def log_success_event(self, kwargs, response_obj, start_time, end_time):
            observed.append('success')

        def log_failure_event(self, kwargs, response_obj, start_time, end_time):
            observed.append('failure')

        async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
            observed.append('success')

        async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
            observed.append('failure')

    existing = ExistingCallback()
    litellm.callbacks.append(existing)
    litellm.callbacks.append('langfuse')
    litellm.success_callback.append(existing)
    litellm.failure_callback.append(existing)
    lf.register_litellm_callbacks(litellm)
    assert lf.init_langfuse() and otel.init_phoenix(), otel.get_stats()
    if mode == 'export_failure':
        def broken(*args, **kwargs):
            raise RuntimeError(SECRET)
        monkeypatch.setattr(lf._http_client._transport.transport, 'handle_request', broken)
        batch = otel._provider._active_span_processor._span_processors[0].processor
        monkeypatch.setattr(batch.span_exporter.exporter, 'export', broken)
    assert otel.get_stats()['instrumentors']['litellm']
    controller = CostController(1, ledger_path=tmp_path / 'ledger.sqlite3')
    controller.ledger.activate(opening_spend_usd=0)
    monkeypatch.setattr('src.core.accounted_router.get_cost_controller', lambda: controller)
    requests = []
    streaming = mode.startswith('stream')
    payload = {'id': 'fixture', 'object': 'chat.completion', 'created': 1, 'model': 'gpt-4o-mini',
               'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': EMAIL}, 'finish_reason': 'stop'}],
               'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}

    class Body(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            chunk = {**payload, 'object': 'chat.completion.chunk',
                     'choices': [{'index': 0, 'delta': {'content': EMAIL}, 'finish_reason': None}]}
            chunk.pop('usage')
            yield ('data: ' + json.dumps(chunk) + '\n\n').encode()
            if mode == 'stream_error':
                raise httpx.ReadError(SECRET)
            if mode == 'stream_cancel':
                raise asyncio.CancelledError(SECRET)
            if mode != 'stream_missing':
                usage = dict(payload['usage'])
                if mode == 'stream_partial':
                    usage.pop('prompt_tokens')
                yield ('data: ' + json.dumps({**payload, 'usage': usage, 'choices': []}) + '\n\n').encode()
            yield b'data: [DONE]\n\n'

        async def aclose(self):
            self.closed = True

    body = Body()

    def handle(request):
        requests.append(json.loads(request.content))
        if mode == 'cancelled':
            raise asyncio.CancelledError(SECRET)
        if mode == 'error' or (mode in {'fallback', 'retry'} and len(requests) == 1):
            return httpx.Response(429 if mode == 'retry' else 401, json={'error': {'message': SECRET + EMAIL}})
        if streaming:
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=body)
        return httpx.Response(200, json=payload)

    client = AsyncOpenAI(api_key='fixture', http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    dep = deployment()
    second = deployment('fallback') if mode == 'fallback' else deployment()
    second['model_info']['id'] = 'secondary'
    router = AccountedRouter(model_list=[dep, second] if mode in {'fallback', 'retry'} else [dep],
                             fallbacks=[{'primary': ['fallback']}] if mode == 'fallback' else [],
                             num_retries=1 if mode == 'retry' else 0, retry_after=0,
                             retry_policy=RetryPolicy(RateLimitErrorRetries=1 if mode == 'retry' else 0))
    monkeypatch.setattr(router, '_get_async_openai_model_client', lambda **kwargs: client)
    try:
        call = router.acompletion(model='primary', messages=[{'role': 'user', 'content': SECRET}],
                                  max_tokens=10, stream=streaming, caching=False)
        if mode in {'error', 'cancelled'}:
            with pytest.raises(asyncio.CancelledError if mode == 'cancelled' else litellm.AuthenticationError):
                await call
        else:
            result = await call
            if mode == 'stream_unstarted':
                await result.aclose()
            elif mode == 'stream_early':
                await result.__anext__()
                await result.aclose()
            elif mode in {'stream_error', 'stream_cancel'}:
                with pytest.raises(asyncio.CancelledError if mode == 'stream_cancel' else Exception):
                    async for _ in result:
                        pass
            elif streaming:
                content = ''.join([chunk.choices[0].delta.content or '' async for chunk in result if chunk.choices])
                assert content == EMAIL
            else:
                assert result.choices[0].message.content == EMAIL
        # LiteLLM schedules its async success handlers after returning the response.
        for _ in range(100):
            if (observed and batches) or mode == 'cancelled':
                break
            await asyncio.sleep(0.01)
        lf.flush()
        assert otel.flush()
        assert len(requests) == (2 if mode in {'fallback', 'retry'} else 1)
        assert all(request['messages'][0]['content'] == SECRET for request in requests)
        rows = controller.ledger.attempts()
        assert len(rows) == len(requests)
        assert sum(row['state'] == 'settled' for row in rows) == (1 if mode in {'success', 'stream', 'fallback', 'retry', 'export_failure'} else 0)
        assert all(row['usage_source'] == 'provider_reported' for row in rows if row['state'] == 'settled')
        if streaming:
            assert body.closed, 'Instrumentation must preserve underlying SDK resource closure'
        assert existing in litellm.success_callback and existing in litellm.failure_callback
        if mode not in {'cancelled', 'stream_error', 'stream_cancel', 'stream_early', 'stream_unstarted', 'export_failure'}:
            assert observed and batches, 'Actual SDK callback must execute'
        if mode != 'export_failure':
            assert encoded and spans, 'Actual OpenInference instrumentation must export'
        else:
            assert not encoded and not batches
        assert_clean(batches)
        assert_clean(encoded)
    finally:
        from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER
        # The locked SDK schedules _client_async_logging_helper after returning.
        # Let that producer enqueue the last success event before draining; a
        # retry's earlier failure callback can already satisfy the assertions.
        await asyncio.sleep(0)
        await GLOBAL_LOGGING_WORKER.flush()
        await GLOBAL_LOGGING_WORKER.stop()
        await client.close()


@pytest.mark.parametrize('status', [207, 400, 500])
def test_langfuse_remote_error_body_never_reaches_sdk_diagnostics(status):
    from src.langfuse_obs import FilteringTransport
    body = {'message': SECRET, 'errors': [{'status': EMAIL, 'message': SECRET, 'error': ACCOUNT}]}
    transport = FilteringTransport(httpx.MockTransport(lambda request: httpx.Response(status, json=body)),
                                   ObservabilityPolicy('redacted'))
    payload = {'batch': [{'id': str(uuid4()), 'type': 'trace-create', 'body': {'id': str(uuid4()), 'input': SECRET}}]}
    with httpx.Client(transport=transport) as client:
        response = client.post('https://fixture.invalid/api/public/ingestion', json=payload)
        assert response.status_code == status
        assert_clean(response.json())


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['sanitizer', 'exporter', 'initialization'])
async def test_observability_failures_preserve_business_result_and_never_export_raw(
        langfuse_setup, otel_setup, monkeypatch, failure):
    lf, batches = langfuse_setup
    otel, encoded, _spans = otel_setup
    calls = []

    def broken(*args, **kwargs):
        raise RuntimeError(SECRET + EMAIL)

    if failure == 'initialization':
        monkeypatch.setattr(lf, '_new_http_transport', broken)
        monkeypatch.setattr(otel, '_new_phoenix_exporter', broken)
        assert not lf.init_langfuse() and not otel.init_phoenix()
    else:
        assert lf.init_langfuse() and otel.init_phoenix()
        if failure == 'sanitizer':
            monkeypatch.setattr(lf, 'langfuse_event', broken)
            monkeypatch.setattr(otel, 'sanitized_span', broken)
        else:
            monkeypatch.setattr(lf._http_client._transport.transport, 'handle_request', broken)
            batch = otel._provider._active_span_processor._span_processors[0].processor
            monkeypatch.setattr(batch.span_exporter.exporter, 'export', broken)

    @otel.trace_function(name='fixture')
    @lf.trace_llm_call(name='fixture')
    async def work(value):
        calls.append(value)
        return EMAIL

    assert await work(SECRET) == EMAIL
    assert calls == [SECRET]
    lf.flush()
    otel.flush()
    lf.shutdown()
    otel.shutdown()
    lf.shutdown()
    otel.shutdown()
    assert_clean(batches)
    assert_clean(encoded)
    assert not batches and not encoded
