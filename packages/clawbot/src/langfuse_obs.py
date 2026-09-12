"""Langfuse 2.60: safe copies before SDK/queue and final HTTP serialization."""
from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import os
import threading
import time
from contextlib import suppress
from functools import wraps
from urllib.parse import urlsplit

import httpx

from src.observability_policy import MAX_INPUT, ObservabilityPolicy, langfuse_event, safe_error_type, safe_label

logger = logging.getLogger(__name__)
_langfuse_client = None
_http_client = None
_init_attempted = False
_init_status = 'not_initialized'
_lock = threading.RLock()
_policy = ObservabilityPolicy()
_callback = None

try:
    from langfuse import Langfuse
    from langfuse.api.resources.ingestion.types.create_event_body import CreateEventBody
    from langfuse.api.resources.ingestion.types.create_generation_body import CreateGenerationBody
    from langfuse.api.resources.ingestion.types.create_span_body import CreateSpanBody
    from langfuse.api.resources.ingestion.types.trace_body import TraceBody
    from langfuse.api.resources.ingestion.types.update_generation_body import UpdateGenerationBody
    from langfuse.api.resources.ingestion.types.update_span_body import UpdateSpanBody

    _BODY_TYPES = (TraceBody, CreateGenerationBody, UpdateGenerationBody, CreateSpanBody,
                   UpdateSpanBody, CreateEventBody)
    _langfuse_available = True
except ImportError:
    Langfuse = None
    _BODY_TYPES = ()
    _langfuse_available = False


def _new_http_transport():
    return httpx.HTTPTransport(retries=0)


class FilteringTransport(httpx.BaseTransport):
    """Fail-closed check of the actual serialized Langfuse ingestion batch."""

    def __init__(self, transport, policy, base_path=''):
        self.transport = transport
        self.policy = policy
        self.base_path = base_path.rstrip('/')

    def handle_request(self, request):
        if request.method not in {'GET', 'HEAD'}:
            if request.url.path != self.base_path + '/api/public/ingestion':
                raise RuntimeError('unsupported_observability_write')
            try:
                body = request.read()
                if len(body) > MAX_INPUT * 128:
                    raise ValueError('telemetry_batch_too_large')
                if request.headers.get('content-encoding') == 'gzip':
                    with gzip.GzipFile(fileobj=io.BytesIO(body)) as compressed:
                        body = compressed.read(MAX_INPUT * 128 + 1)
                if len(body) > MAX_INPUT * 128:
                    raise ValueError('telemetry_batch_too_large')
                payload = json.loads(body)
                if type(payload) is not dict or type(payload.get('batch')) is not list or len(payload['batch']) > 128:
                    raise ValueError('invalid_telemetry_batch')
                safe = {'batch': [langfuse_event(event, self.policy) for event in payload['batch']],
                        'metadata': {'sdk_name': 'python', 'sdk_integration': 'openclaw-safe'}}
                serialized = json.dumps(safe, ensure_ascii=False, allow_nan=False).encode()
                headers = dict(request.headers)
                headers.pop('content-length', None)
                headers.pop('content-encoding', None)
                request = httpx.Request(request.method, request.url, headers=headers, content=serialized,
                                        extensions=request.extensions)
            except Exception:
                raise RuntimeError('observability_serialization_rejected') from None
        try:
            response = self.transport.handle_request(request)
            try:
                raw = response.read()
                if len(raw) > MAX_INPUT * 128:
                    raise ValueError('telemetry_response_too_large')
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeError):
                    payload = {}
                if type(payload) is not dict:
                    payload = {}
                if response.status_code >= 400:
                    safe_response = {'message': 'observability_remote_failed'}
                elif request.method in {'GET', 'HEAD'}:
                    projects = payload.get('data', [])
                    safe_response = {'data': [{'id': safe_label(item.get('id'), 'invalid'),
                                               'name': safe_label(item.get('name'), 'project')}
                                              for item in projects[:128] if type(item) is dict]} if type(projects) is list else {'data': []}
                else:
                    errors = payload.get('errors', [])
                    safe_response = {'successes': [], 'errors': [
                        {'status': item.get('status') if type(item.get('status')) is int else 500,
                         'message': 'observability_remote_failed', 'error': 'remote_error'}
                        for item in errors[:128] if type(item) is dict]} if type(errors) is list else {'successes': [], 'errors': []}
                return httpx.Response(response.status_code, json=safe_response)
            finally:
                response.close()
        except Exception:
            raise RuntimeError('observability_transport_failed') from None

    def close(self):
        self.transport.close()


def _protect_queue(client, policy):
    manager = client.task_manager
    original = manager.add_task

    def add_safe_task(event):
        try:
            copied = dict(event)
            body = copied.get('body')
            if type(body) in _BODY_TYPES:
                copied['body'] = body.dict(exclude_none=True)
            safe = langfuse_event(copied, policy)
            return original(safe)
        except Exception:
            return False

    manager.add_task = add_safe_task


def init_langfuse() -> bool:
    global _langfuse_client, _http_client, _init_attempted, _init_status, _policy
    with _lock:
        if _init_attempted:
            return _langfuse_client is not None
        _init_attempted = True
        _policy = ObservabilityPolicy.from_environment()
        if not _langfuse_available:
            _init_status = 'sdk_unavailable'
            return False
        secret = os.getenv('LANGFUSE_SECRET_KEY', '')
        public = os.getenv('LANGFUSE_PUBLIC_KEY', '')
        if not secret or not public:
            _init_status = 'not_configured'
            return False
        transport_client = None
        candidate = None
        try:
            host = os.getenv('LANGFUSE_HOST', 'http://localhost:3000')
            parsed = urlsplit(host)
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError('invalid_telemetry_endpoint')
            transport_client = httpx.Client(transport=FilteringTransport(_new_http_transport(), _policy, parsed.path),
                                            timeout=10, follow_redirects=False)
            candidate = Langfuse(secret_key=secret, public_key=public,
                                 host=host,
                                 release='openclaw', environment='default', debug=False,
                                 httpx_client=transport_client, mask=lambda *, data: _policy.content(data),
                                 threads=1, max_retries=1, flush_at=64, flush_interval=0.1)
            _protect_queue(candidate, _policy)
            if not candidate.auth_check():
                raise RuntimeError('observability_auth_failed')
            _langfuse_client = candidate
            _http_client = transport_client
            _init_status = 'safe_export_enabled'
            return True
        except Exception:
            _init_status = 'initialization_failed'
            if candidate is not None:
                with suppress(Exception):
                    candidate.shutdown()
            if transport_client is not None:
                with suppress(Exception):
                    transport_client.close()
            logger.warning('[LangfuseObs] initialization_failed; telemetry disabled')
            return False


def _usage_metadata(input_tokens, output_tokens, source):
    result = {'usage_source': safe_label(source, 'unverified')}
    for name, value in [('reported_input_tokens', input_tokens), ('reported_output_tokens', output_tokens)]:
        if type(value) is int and 0 <= value < 10**12:
            result[name] = value
    return result


def log_generation(name, model, input_text, output_text, bot_id='', user_id='', chat_id='',
                   latency_ms=0, input_tokens=None, output_tokens=None, metadata=None,
                   usage_source='application_unverified', outcome='success', error_type=None):
    """Unverified token numbers cannot become automatic billed usage."""
    if _langfuse_client is None:
        return
    try:
        details = _policy.metadata(metadata or {})
        details.update(_usage_metadata(input_tokens, output_tokens, usage_source))
        details.update(ObservabilityPolicy().metadata({'latency_ms': latency_ms}))
        details['status'] = safe_label(outcome)
        if error_type:
            details['error_type'] = safe_label(error_type, 'Exception')
        trace = _langfuse_client.trace(name=safe_label(name, 'llm-call'), metadata=details, public=False)
        generation = {'name': safe_label(name, 'llm-call') + '/generation',
                      'model': safe_label(model), 'input': _policy.content(input_text),
                      'output': _policy.content(output_text), 'metadata': details}
        if (usage_source == 'provider_reported' and type(input_tokens) is int and type(output_tokens) is int
                and 0 <= input_tokens < 10**12 and 0 <= output_tokens < 10**12):
            generation['usage'] = {'input': input_tokens, 'output': output_tokens}
        if outcome != 'success':
            generation.update(level='ERROR', status_message=safe_label(error_type, 'operation_failed'))
        trace.generation(**generation)
    except Exception:
        logger.debug('[LangfuseObs] event_dropped')


def _safe_input(args, kwargs):
    if type(kwargs.get('messages')) is list:
        return kwargs['messages']
    for value in args:
        if type(value) in {str, list, dict}:
            return value
    return kwargs


def _extract_output(result):
    if type(result) is str:
        return result
    if type(result) is dict:
        return result.get('raw', result.get('text', result.get('content', result)))
    return None


def trace_llm_call(name='llm-call', model='', bot_id='', user_id='', chat_id='', chat_type='', metadata=None):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            started = time.monotonic()
            try:
                result = await fn(*args, **kwargs)
            except BaseException as error:
                if isinstance(error, (Exception, asyncio.CancelledError)):
                    log_generation(name, model, _safe_input(args, kwargs), None,
                                   latency_ms=(time.monotonic() - started) * 1000, metadata=metadata,
                                   outcome='cancelled' if isinstance(error, asyncio.CancelledError) else 'error',
                                   error_type=safe_error_type(error))
                raise
            log_generation(name, model, _safe_input(args, kwargs), _extract_output(result),
                           latency_ms=(time.monotonic() - started) * 1000, metadata=metadata)
            return result
        return wrapper
    return decorator


def log_event(name, metadata=None):
    if _langfuse_client is not None:
        try:
            _langfuse_client.trace(name=safe_label(name, 'event'), metadata=_policy.metadata(metadata or {}), public=False)
        except Exception:
            logger.debug('[LangfuseObs] event_dropped')


def flush():
    if _langfuse_client is not None:
        try:
            _langfuse_client.flush()
        except Exception:
            logger.debug('[LangfuseObs] flush_failed')


def shutdown():
    global _langfuse_client, _http_client, _init_attempted, _init_status
    with _lock:
        client, transport = _langfuse_client, _http_client
        _langfuse_client = None
        _http_client = None
        try:
            if client is not None:
                client.shutdown()
        except Exception:
            logger.debug('[LangfuseObs] shutdown_failed')
        finally:
            if transport is not None:
                with suppress(Exception):
                    transport.close()
        _init_attempted = False
        _init_status = 'not_initialized'


def get_stats():
    return {'available': _langfuse_available, 'connected': _langfuse_client is not None,
            'status': _init_status, 'content_mode': _policy.mode, 'content_config_valid': _policy.valid_config,
            'native_callback': 'safe_adapter' if _callback is not None else 'not_registered'}


def register_litellm_callbacks(litellm):
    """Replace only Langfuse's unsafe callback, preserving unrelated callback identities."""
    global _callback
    from litellm.integrations.custom_logger import CustomLogger
    from litellm.types.utils import ModelResponse

    with _lock:
        if _callback is None:
            class SafeLangfuseCallback(CustomLogger):
                def _record(self, kwargs, response, start_time, end_time, failed=False):
                    try:
                        if not init_langfuse():
                            return
                        if kwargs.get('stream'):
                            response = kwargs.get('async_complete_streaming_response') or kwargs.get('complete_streaming_response')
                            if response is None and not failed:
                                return
                        content = None
                        input_tokens = output_tokens = None
                        if type(response) is ModelResponse:
                            content = [{'content': choice.message.content,
                                        'tool_calls': _policy.content(choice.message.tool_calls)}
                                       for choice in response.choices]
                            if response.usage is not None:
                                input_tokens = response.usage.prompt_tokens
                                output_tokens = response.usage.completion_tokens
                        elapsed = (end_time - start_time).total_seconds() * 1000
                        log_generation('litellm-call', kwargs.get('model', ''), kwargs.get('messages'), content,
                                       latency_ms=elapsed, input_tokens=input_tokens, output_tokens=output_tokens,
                                       usage_source='sdk_reported_unverified', outcome='error' if failed else 'success',
                                       error_type=safe_error_type(response) if failed else None)
                    except Exception:
                        logger.debug('[LangfuseObs] callback_event_dropped')

                def log_success_event(self, kwargs, response_obj, start_time, end_time):
                    self._record(kwargs, response_obj, start_time, end_time)

                def log_failure_event(self, kwargs, response_obj, start_time, end_time):
                    self._record(kwargs, response_obj, start_time, end_time, True)

                async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
                    self._record(kwargs, response_obj, start_time, end_time)

                async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
                    self._record(kwargs, response_obj, start_time, end_time, True)

            _callback = SafeLangfuseCallback()
        for name in ('callbacks', 'input_callback', '_async_input_callback',
                     'success_callback', 'failure_callback', '_async_success_callback', '_async_failure_callback'):
            callbacks = getattr(litellm, name, None)
            if callbacks is None:
                continue
            result = []
            present = False
            for callback in callbacks:
                native = (type(callback) is str and callback in {'langfuse', 'langfuse_otel'}) or (
                    (type(callback).__module__, type(callback).__name__) in {
                        ('litellm.integrations.langfuse.langfuse', 'LangFuseLogger'),
                        ('litellm.integrations.langfuse.langfuse_otel', 'LangfuseOtelLogger'),
                    })
                if native or callback is _callback:
                    if not present:
                        result.append(_callback)
                        present = True
                else:
                    result.append(callback)
            if not present and name in {'success_callback', 'failure_callback', '_async_success_callback', '_async_failure_callback'}:
                result.append(_callback)
            if type(callbacks) is list:
                callbacks[:] = result
            else:
                setattr(litellm, name, result)
        return _callback
