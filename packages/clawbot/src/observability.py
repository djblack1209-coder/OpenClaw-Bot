"""Phoenix/OpenTelemetry with filtering before queueing and before export.

Only the explicitly installed LiteLLM/CrewAI instrumentors use this private
provider; no automatic entry-point discovery or unrelated global exporter is
registered. Business calls keep their original inputs, results and exceptions.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import threading
from functools import wraps
from itertools import islice

from src.observability_policy import ObservabilityPolicy, redact_text, safe_error_type, safe_label

logger = logging.getLogger(__name__)
_phoenix_available = False
_phoenix_initialized = False
_init_attempted = False
_status = 'not_initialized'
_tracer = None
_provider = None
_owned_instrumentors = []
_lock = threading.RLock()
_policy = ObservabilityPolicy()

try:
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import Event, ReadableSpan, SpanProcessor, TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
    from opentelemetry.sdk.util.instrumentation import InstrumentationScope
    from opentelemetry.trace import Link, SpanContext, Status, StatusCode, TraceState
    from phoenix.otel import SimpleSpanProcessor as PhoenixSimpleSpanProcessor

    _phoenix_available = True
except ImportError:
    # No exporter or instrumentor can be installed through this module.
    SpanProcessor = SpanExporter = object

_litellm_instrumentor_cls = None
_crewai_instrumentor_cls = None
try:
    from openinference.instrumentation.litellm import LiteLLMInstrumentor
    _litellm_instrumentor_cls = LiteLLMInstrumentor
except ImportError:
    pass
try:
    from openinference.instrumentation.crewai import CrewAIInstrumentor
    _crewai_instrumentor_cls = CrewAIInstrumentor
except ImportError:
    pass


def _attributes(values, policy, *, strict=False):
    copied = dict(islice((values or {}).items(), 128))
    # Exception text/stack frames never carry essential metrics, even in content mode.
    copied = {key: value for key, value in copied.items()
              if key not in {'exception.message', 'exception.stacktrace', 'error.message'}
              and not key.startswith(('llm.cost.', 'gen_ai.usage.cost'))}
    if any(key.startswith(('llm.token_count.', 'gen_ai.usage.')) for key in copied):
        copied['usage_source'] = 'sdk_reported_unverified'
    sanitized = (ObservabilityPolicy() if strict else policy).metadata(copied)
    if type(sanitized) is not dict:
        return {}
    result = {}
    for key, value in sanitized.items():
        if type(value) in {str, bool, int, float} or (type(value) is list and value and len({type(item) for item in value}) == 1
              and type(value[0]) in {str, bool, int, float}):
            result[key] = value
    return result


def _context(context):
    if context is None:
        return None
    return SpanContext(trace_id=context.trace_id, span_id=context.span_id, is_remote=context.is_remote,
                       trace_flags=context.trace_flags, trace_state=TraceState())


def sanitized_span(span, policy):
    """Build a ReadableSpan copy; no mutations of live spans, shared resources, or links."""
    scope = span.instrumentation_scope
    safe_scope = None
    if scope is not None:
        safe_scope = InstrumentationScope(name=safe_label(scope.name, 'instrumentation'),
                                          version=safe_label(scope.version) if scope.version else None,
                                          schema_url='',
                                          attributes=_attributes(scope.attributes, policy, strict=True))
    events = [Event(name=safe_label(event.name, 'event'), timestamp=event.timestamp,
                    attributes=_attributes(event.attributes, policy)) for event in islice(span.events, 128)]
    links = [Link(context=_context(link.context), attributes=_attributes(link.attributes, policy))
             for link in islice(span.links, 128)]
    status = Status(span.status.status_code,
                    'operation_failed' if span.status.status_code == StatusCode.ERROR else None)
    return ReadableSpan(name=safe_label(span.name, 'operation'), context=_context(span.context),
                        parent=_context(span.parent), kind=span.kind, status=status,
                        resource=Resource(_attributes(span.resource.attributes, policy, strict=True)),
                        attributes=_attributes(span.attributes, policy), events=events, links=links,
                        start_time=span.start_time, end_time=span.end_time, instrumentation_scope=safe_scope)


class FilteringSpanExporter(SpanExporter):
    """The final exporter receives only reconstructed, bounded ReadableSpan copies."""

    def __init__(self, exporter, policy):
        self.exporter = exporter
        self.policy = policy

    def export(self, spans):
        try:
            copied = tuple(sanitized_span(span, self.policy) for span in spans)
            return self.exporter.export(copied)
        except Exception:
            return SpanExportResult.FAILURE

    def shutdown(self):
        with contextlib.suppress(Exception):
            self.exporter.shutdown()

    def force_flush(self, timeout_millis=30000):
        try:
            return self.exporter.force_flush(timeout_millis)
        except Exception:
            return False


class FilteringSpanProcessor(SpanProcessor):
    """Sanitize before the BatchSpanProcessor puts an ended span on its queue."""

    def __init__(self, processor, policy):
        self.processor = processor
        self.policy = policy

    def on_start(self, span, parent_context=None):
        # The owned inner processor is a BatchSpanProcessor; it needs only on_end.
        pass

    def on_end(self, span):
        with contextlib.suppress(Exception):
            self.processor.on_end(sanitized_span(span, self.policy))

    def shutdown(self):
        self.processor.shutdown()

    def force_flush(self, timeout_millis=30000):
        return self.processor.force_flush(timeout_millis)


def _new_phoenix_exporter(endpoint):
    # Public Phoenix factory preserves the locked SDK's HTTP/gRPC endpoint and
    # authentication rules. This unused simple processor has no worker/queue;
    # only its exporter is attached to the filtered batch pipeline.
    return PhoenixSimpleSpanProcessor(endpoint=endpoint).span_exporter


def _preserve_litellm_stream_identity(instrumentor):
    """OI 0.1.34 wraps streams in generators, hiding raw usage and aclose.

    Record only opening the stream here. The final Langfuse callback observes
    completion separately; neither adapter may replace the SDK stream object.
    The instrumentor still owns restoration of its original acompletion.
    """
    import litellm
    original = instrumentor.original_litellm_funcs['acompletion']
    instrumented = litellm.acompletion

    @wraps(original)
    async def call(*args, **kwargs):
        if not kwargs.get('stream'):
            return await instrumented(*args, **kwargs)
        observed = trace_function(name='litellm.stream.open',
                                  attributes={'model': safe_label(kwargs.get('model')), 'phase': 'stream_open'})(original)
        return await observed(*args, **kwargs)

    litellm.acompletion = call


def init_phoenix(project_name='openclaw-bot', endpoint=None) -> bool:
    global _phoenix_initialized, _init_attempted, _status, _provider, _tracer, _policy
    with _lock:
        if _init_attempted:
            return _phoenix_initialized
        _init_attempted = True
        _policy = ObservabilityPolicy.from_environment()
        if not _phoenix_available:
            _status = 'sdk_unavailable'
            return False
        endpoint = endpoint or os.getenv('PHOENIX_ENDPOINT', '')
        if not endpoint:
            _status = 'not_configured'
            return False
        provider = None
        try:
            exporter = FilteringSpanExporter(_new_phoenix_exporter(endpoint), _policy)
            provider = TracerProvider(resource=Resource({'service.name': 'openclaw-bot',
                                      'openinference.project.name': safe_label(project_name, 'openclaw-bot')}))
            batch = BatchSpanProcessor(exporter, max_queue_size=512, max_export_batch_size=64,
                                       schedule_delay_millis=500, export_timeout_millis=10000)
            provider.add_span_processor(FilteringSpanProcessor(batch, _policy))
            _tracer = provider.get_tracer('openclaw-bot')
            _provider = provider
            for cls in (_litellm_instrumentor_cls, _crewai_instrumentor_cls):
                if cls is None:
                    continue
                instrumentor = cls()
                if instrumentor.is_instrumented_by_opentelemetry:
                    logger.warning('[Phoenix] existing_unmanaged_instrumentor; not replaced')
                    continue
                try:
                    instrumentor.instrument(tracer_provider=provider)
                    if instrumentor.is_instrumented_by_opentelemetry:
                        if cls is _litellm_instrumentor_cls:
                            _preserve_litellm_stream_identity(instrumentor)
                        _owned_instrumentors.append(instrumentor)
                except Exception:
                    # This instance was uninstrumented before our attempt.
                    with contextlib.suppress(Exception):
                        instrumentor.uninstrument()
                    logger.warning('[Phoenix] instrumentor_unavailable')
            _phoenix_initialized = True
            _status = 'safe_export_enabled'
            return True
        except Exception:
            if provider is not None:
                with contextlib.suppress(Exception):
                    provider.shutdown()
            _provider = _tracer = None
            _status = 'initialization_failed'
            logger.warning('[Phoenix] initialization_failed; telemetry disabled')
            return False


def trace_function(name=None, attributes=None):
    def decorator(fn):
        span_name = safe_label(name or f'{fn.__module__}.{fn.__qualname__}', 'operation')

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            manager = span = None
            if _tracer is not None:
                try:
                    manager = _tracer.start_as_current_span(span_name, record_exception=False,
                                                            set_status_on_exception=False)
                    span = manager.__enter__()
                    for key, value in _attributes(attributes, _policy).items():
                        span.set_attribute(key, value)
                except Exception:
                    if manager is not None and span is not None:
                        with contextlib.suppress(Exception):
                            manager.__exit__(None, None, None)
                    manager = span = None
            try:
                return await fn(*args, **kwargs)
            except BaseException as error:
                if span is not None and isinstance(error, (Exception, asyncio.CancelledError)):
                    try:
                        span.set_attribute('error', True)
                        span.set_attribute('exception.type', safe_error_type(error))
                        span.set_status(Status(StatusCode.ERROR, 'operation_failed'))
                    except Exception:
                        pass
                raise
            finally:
                if manager is not None:
                    with contextlib.suppress(Exception):
                        manager.__exit__(None, None, None)
        return wrapper
    return decorator


def flush():
    if _provider is not None:
        try:
            return _provider.force_flush()
        except Exception:
            return False
    return True


def shutdown():
    global _tracer, _provider, _phoenix_initialized, _init_attempted, _status
    with _lock:
        _tracer = None
        for instrumentor in reversed(_owned_instrumentors):
            with contextlib.suppress(Exception):
                instrumentor.uninstrument()
        _owned_instrumentors.clear()
        if _provider is not None:
            with contextlib.suppress(Exception):
                _provider.shutdown()
        _provider = None
        _phoenix_initialized = _init_attempted = False
        _status = 'not_initialized'


def get_mcp_config():
    endpoint = os.getenv('PHOENIX_ENDPOINT', '')
    if not endpoint:
        return {}
    return {'phoenix': {'command': 'npx', 'args': ['-y', 'arize-phoenix-mcp'],
                        'env': {'PHOENIX_API_URL': endpoint}}}


def get_phoenix_url():
    endpoint = os.getenv('PHOENIX_ENDPOINT', '')
    return redact_text(endpoint.rstrip('/')) if endpoint else None


def get_stats():
    return {'available': _phoenix_available, 'initialized': _phoenix_initialized,
            'status': _status, 'content_mode': _policy.mode, 'content_config_valid': _policy.valid_config,
            'endpoint_configured': bool(os.getenv('PHOENIX_ENDPOINT')),
            'litellm_stream_spans': 'open_only',
            'instrumentors': {'litellm': any(type(item) is _litellm_instrumentor_cls for item in _owned_instrumentors),
                              'crewai': any(type(item) is _crewai_instrumentor_cls for item in _owned_instrumentors)}}
