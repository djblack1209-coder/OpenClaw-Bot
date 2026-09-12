"""Bounded, copy-only policy for telemetry. This module imports no SDK or app state.

Only ``OPENCLAW_OBSERVABILITY_CONTENT=redacted`` enables content collection.
The default and invalid values use metadata only. This is selected-PII filtering,
not a claim that arbitrary prose can be anonymized.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit
from uuid import UUID

REDACTED = '[REDACTED]'
OMITTED = '[OMITTED]'
MAX_INPUT = 65536
MAX_TEXT = 2000
MAX_DEPTH = 6
MAX_ITEMS = 128
_NUMERIC_KEYS = frozenset({
    'input', 'output', 'total', 'input_tokens', 'output_tokens', 'total_tokens',
    'prompt_tokens', 'completion_tokens', 'latency_ms', 'duration_ms', 'attempt',
    'retry_count', 'status_code', 'count', 'error_count', 'batch_size',
    'reported_input_tokens', 'reported_output_tokens',
    'llm.token_count.prompt', 'llm.token_count.completion', 'llm.token_count.total',
    'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens',
})
_LABEL_KEYS = frozenset({
    'model', 'provider', 'operation', 'component', 'module', 'phase', 'status', 'reason_code',
    'usage_source', 'error_type', 'unit', 'service.name', 'openinference.span.kind',
    'llm.model_name', 'gen_ai.request.model', 'gen_ai.response.model', 'gen_ai.system',
    'exception.type', 'telemetry.sdk.language', 'telemetry.sdk.name', 'telemetry.sdk.version',
    'openinference.project.name',
})
_CONTENT_KEYS = frozenset({'input', 'output', 'prompt', 'completion', 'messages', 'content',
                           'tool_arguments', 'tool_result', 'tool_results', 'tools'})
_LABEL = re.compile(r'^[A-Za-z0-9_.:/-]{1,160}$')
_SECRET_PREFIX = re.compile(
    r'\b(?:sk-|key-|gsk_|ghp_|github_pat_|AIza|csk-|nvapi-|hf_|m0-)[A-Za-z0-9_.-]{6,}', re.I)
_ASSIGNMENT = re.compile(
    r'''(?ix)(["']?(?:api[-_]?key|access[-_]?token|refresh[-_]?token|id[-_]?token|token|password|passwd|secret|client[-_]?secret|authorization|proxy[-_]?authorization|x[-_]?api[-_]?key|key|account(?:[-_]?(?:id|number))?|user[-_]?id|chat[-_]?id|session[-_]?id)["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}&]+)''')
_PRIVATE_KEY = re.compile(r'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)', re.S | re.I)
_URL = re.compile(r'https?://[^\s<>"\']+', re.I)
_EMAIL = re.compile(r'(?<![\w.+-])[A-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)+(?![\w.-])', re.I)
_PHONE = re.compile(r'(?<![\w])(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)|\d{2,4})[ .-]\d{3,4}[ .-]\d{3,4}(?!\w)|(?<!\w)1[3-9]\d{9}(?!\w)')
_CARD = re.compile(r'(?<![\w])(?:\d[ -]?){12,18}\d(?![\w])')


def sensitive_key(key: str) -> bool:
    normalized = re.sub(r'[^a-z0-9]', '', unquote(key).casefold())
    if key.casefold() in _NUMERIC_KEYS:
        return False
    return normalized in {'key', 'authorization', 'proxyauthorization', 'cookie', 'setcookie',
                          'credentials', 'user', 'userid', 'username', 'email', 'phone',
                          'chatid', 'sessionid', 'account', 'accountid', 'accountnumber',
                          'card', 'cardnumber', 'pan', 'cvv', 'iban', 'ibanumber'} or any(
        part in normalized for part in ('apikey', 'password', 'passwd', 'secret', 'privatekey', 'accesstoken',
                                       'refreshtoken', 'bottoken', 'authtoken', 'idtoken')
    ) or normalized.endswith('token')


def _luhn(value: str) -> bool:
    digits = re.sub(r'\D', '', value)
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2:
            number *= 2
            number = number - 9 if number > 9 else number
        total += number
    return total % 10 == 0


def _plain(value: str) -> str:
    value = _PRIVATE_KEY.sub(REDACTED, value)
    value = re.sub(r'(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9_+/.=:-]+', 'AUTH ' + REDACTED, value)
    value = re.sub(r'(?im)\b(?:set-cookie|cookie)\s*[:=]\s*[^\r\n]+', 'Cookie: ' + REDACTED, value)
    value = re.sub(r'(?i)(?:/bot)?\b\d{5,14}:[A-Za-z0-9_-]{15,}', REDACTED, value)
    value = _SECRET_PREFIX.sub(REDACTED, value)
    def assignment(match):
        original = match[0][len(match[1]):]
        quote = original[0] if original and original[0] in {'"', "'"} else ''
        return match[1] + quote + REDACTED + quote

    value = _ASSIGNMENT.sub(assignment, value)
    value = _EMAIL.sub(REDACTED, value)
    value = _CARD.sub(lambda match: REDACTED if _luhn(match[0]) else match[0], value)
    value = _PHONE.sub(REDACTED, value)
    value = re.sub(r'(?i)\b(?:DU|U)\d{5,12}\b', REDACTED, value)
    value = re.sub(r'(?i)\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b', REDACTED, value)
    return value


def _url(match) -> str:
    try:
        parsed = urlsplit(match[0])
        if parsed.hostname in {'127.0.0.1', 'localhost', '::1'}:
            return 'http://[internal]'
        # User information and fragments are never useful for telemetry routing.
        host = parsed.hostname or ''
        if ':' in host:
            host = '[' + host + ']'
        if parsed.port:
            host += ':' + str(parsed.port)
        query = [(redact_text(key, urls=False), REDACTED if sensitive_key(key) else redact_text(value, urls=False))
                 for key, value in parse_qsl(parsed.query, keep_blank_values=True)[:MAX_ITEMS]]
        return urlunsplit((parsed.scheme, host, _plain(unquote(parsed.path)), urlencode(query), ''))
    except Exception:
        return '[REDACTED_URL]'


def redact_text(value, *, limit: int = MAX_TEXT, urls: bool = True) -> str:
    """Do not stringify opaque objects or truncate a secret before recognizing it."""
    if type(value) is not str:
        return OMITTED
    if len(value) > MAX_INPUT:
        return OMITTED
    if urls:
        value = _URL.sub(_url, value)
    value = _plain(value)
    return value[:limit] + ('[TRUNCATED]' if len(value) > limit else '')


def safe_label(value, default: str = 'unknown') -> str:
    if type(value) is not str or not _LABEL.fullmatch(value):
        return default
    cleaned = redact_text(value, limit=160)
    return cleaned if cleaned == value else default


def safe_error_type(error) -> str:
    # Never access exception messages, chains, repr, or traceback locals.
    return safe_label(type(error).__name__, 'Exception')


@dataclass(frozen=True)
class ObservabilityPolicy:
    mode: str = 'metadata'
    valid_config: bool = True

    @classmethod
    def from_environment(cls):
        value = os.getenv('OPENCLAW_OBSERVABILITY_CONTENT', 'metadata').strip().casefold()
        return cls(value if value in {'metadata', 'redacted'} else 'metadata', value in {'metadata', 'redacted'})

    def sanitize(self, value):
        """Copy primitives only, redact keys as well as values, bound total nodes."""
        seen = set()
        remaining = [MAX_ITEMS]

        def walk(item, depth):
            remaining[0] -= 1
            if remaining[0] < 0 or depth > MAX_DEPTH:
                return OMITTED
            kind = type(item)
            if item is None or kind is bool:
                return item
            if kind in {int, float}:
                return item if math.isfinite(item) else OMITTED
            if kind is str:
                return redact_text(item)
            if kind not in {dict, list, tuple}:
                return OMITTED
            if id(item) in seen:
                return OMITTED
            seen.add(id(item))
            if kind is dict:
                result = {}
                for index, (key, child) in enumerate(item.items()):
                    if index >= MAX_ITEMS or remaining[0] <= 0:
                        result['_truncated'] = True
                        break
                    if type(key) is not str:
                        continue
                    clean_key = redact_text(key, limit=128)
                    result[clean_key] = REDACTED if sensitive_key(key) else walk(child, depth + 1)
            else:
                result = []
                for child in item:
                    if remaining[0] <= 0:
                        result.append(OMITTED)
                        break
                    result.append(walk(child, depth + 1))
            seen.remove(id(item))
            return result

        try:
            return walk(value, 0)
        except Exception:
            return OMITTED

    def content(self, value):
        return self.sanitize(value) if self.mode == 'redacted' else OMITTED

    def metadata(self, value):
        if type(value) is not dict:
            return {}
        if self.mode == 'redacted':
            return self.sanitize(value)
        result = {}
        for index, (key, child) in enumerate(value.items()):
            if index >= MAX_ITEMS:
                break
            if type(key) is not str:
                continue
            if key in _NUMERIC_KEYS and type(child) in {int, float} and math.isfinite(child) and child >= 0:
                result[key] = child
            elif key in _LABEL_KEYS and type(child) is str:
                result[key] = safe_label(child)
            elif key in {'error', 'success'} and type(child) is bool:
                result[key] = child
        return result


def safe_protocol_id(value):
    if type(value) is str:
        try:
            UUID(value)
            return value
        except ValueError:
            pass
    return None


def safe_timestamp(value):
    if type(value) is datetime:
        return value.isoformat()
    if type(value) is str and len(value) <= 40:
        try:
            datetime.fromisoformat(value.replace('Z', '+00:00'))
            return value
        except ValueError:
            pass
    return None


def langfuse_event(event: dict, policy: ObservabilityPolicy) -> dict:
    """Allowlisted Langfuse 2.x event envelope, both before queue and on the wire."""
    if type(event) is not dict or event.get('type') not in {
        'trace-create', 'generation-create', 'generation-update', 'span-create', 'span-update', 'event-create',
    }:
        raise ValueError('unsupported_telemetry_event')
    identifier = safe_protocol_id(event.get('id'))
    if identifier is None or type(event.get('body')) is not dict:
        raise ValueError('invalid_telemetry_event')
    source = event['body']
    body = {}
    for index, (key, value) in enumerate(source.items()):
        if index >= MAX_ITEMS:
            raise ValueError('telemetry_event_too_large')
        if key in {'id', 'traceId', 'parentObservationId'}:
            if (identifier_value := safe_protocol_id(value)) is not None:
                body[key] = identifier_value
        elif key in {'timestamp', 'startTime', 'endTime', 'completionStartTime'}:
            if (stamp := safe_timestamp(value)) is not None:
                body[key] = stamp
        elif key in {'name', 'model', 'level', 'version', 'release', 'environment'}:
            if value is not None:
                body[key] = safe_label(value)
        elif key in {'input', 'output'}:
            body[key] = policy.content(value)
        elif key == 'metadata':
            body[key] = policy.metadata(value)
        elif key in {'usage', 'usageDetails'} and type(value) is dict:
            body[key] = ObservabilityPolicy().metadata(value)
        elif key == 'statusMessage':
            body[key] = redact_text(value) if policy.mode == 'redacted' else 'operation_failed'
        elif key == 'public':
            body[key] = False
    result = {'id': identifier, 'type': event['type'], 'body': body}
    if (stamp := safe_timestamp(event.get('timestamp'))) is not None:
        result['timestamp'] = stamp
    return result
