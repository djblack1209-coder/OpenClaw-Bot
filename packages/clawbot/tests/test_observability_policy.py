"""Copy boundaries, selected sensitive data and bounded failure behavior."""
import json

import pytest

from src.observability_policy import (
    MAX_INPUT,
    MAX_ITEMS,
    OMITTED,
    REDACTED,
    ObservabilityPolicy,
    redact_text,
)

MARKERS = [
    'sk-synthetic-observation-key-681729', 'fixture.person@example.invalid',
    '+1-202-555-0147', '4111 1111 1111 1111', 'DU1234567',
    '123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk',
]


@pytest.mark.parametrize('marker', MARKERS)
def test_selected_secret_and_pii_patterns(marker):
    assert marker not in redact_text('before ' + marker + ' after')


@pytest.mark.parametrize('name', ['API_KEY', 'aPi-KeY', 'access_token', 'Authorization', 'Cookie',
                                  'private_key', 'user_id', 'sessionId', 'accountNumber', 'card_number'])
def test_structured_sensitive_fields_do_not_require_a_recognizable_value(name):
    source = {'nested': [{name: 'synthetic-unpatterned-secret'}]}
    sanitized = ObservabilityPolicy('redacted').sanitize(source)
    assert 'synthetic-unpatterned-secret' not in json.dumps(sanitized)
    assert source['nested'][0][name] == 'synthetic-unpatterned-secret'


@pytest.mark.parametrize('mode,expected,valid', [(None, 'metadata', True), ('metadata', 'metadata', True),
                                               ('redacted', 'redacted', True), ('raw', 'metadata', False),
                                               ('', 'metadata', False)])
def test_content_policy_default_opt_in_and_invalid_config(monkeypatch, mode, expected, valid):
    if mode is None:
        monkeypatch.delenv('OPENCLAW_OBSERVABILITY_CONTENT', raising=False)
    else:
        monkeypatch.setenv('OPENCLAW_OBSERVABILITY_CONTENT', mode)
    policy = ObservabilityPolicy.from_environment()
    assert (policy.mode, policy.valid_config) == (expected, valid)
    assert policy.content('ordinary business prose') == ('ordinary business prose' if expected == 'redacted' else OMITTED)
    details = policy.metadata({'model': 'fixture-model', 'latency_ms': 12, 'arbitrary': 'ordinary business prose'})
    assert details['model'] == 'fixture-model' and details['latency_ms'] == 12
    if expected == 'metadata':
        assert 'arbitrary' not in details


def test_headers_url_userinfo_encoded_query_cookie_and_private_key():
    text = ('https://synthetic-login:synthetic-pass@fixture.invalid/path?%61ccess_token=opaque-query-value&ok=yes '
            '\nAUTHORIZATION: Bearer opaque-bearer-value\nCookie: a=opaque-cookie-value; b=second-cookie-value\n'
            '-----BEGIN PRIVATE KEY-----\nopaque-private-key-material\n-----END PRIVATE KEY-----')
    safe = redact_text(text)
    for value in ['synthetic-login', 'synthetic-pass', 'opaque-query-value', 'opaque-bearer-value',
                  'opaque-cookie-value', 'second-cookie-value', 'opaque-private-key-material']:
        assert value not in safe
    assert 'fixture.invalid' in safe


def test_no_repr_or_str_of_unknown_objects_cycles_and_bounds():
    class Opaque:
        def __repr__(self):
            raise AssertionError('repr must never run')

        def __str__(self):
            raise AssertionError('str must never run')

    cycle = {'opaque': Opaque()}
    cycle['cycle'] = cycle
    policy = ObservabilityPolicy('redacted')
    result = policy.sanitize(cycle)
    assert result == {'opaque': OMITTED, 'cycle': OMITTED}
    assert redact_text(Opaque()) == OMITTED
    assert len(policy.sanitize({f'secret-{index}': 'opaque' for index in range(1000)})) <= MAX_ITEMS + 1
    assert len(policy.sanitize([1] * 1000)) <= MAX_ITEMS + 1
    assert policy.sanitize(float('nan')) == OMITTED
    assert policy.content('x' * (MAX_INPUT + 1)) == OMITTED
    assert redact_text('x' * 1995 + ' ' + MARKERS[0], limit=2000).endswith('[TRUNCATED]')
    assert 'sk-' not in redact_text('x' * 1995 + ' ' + MARKERS[0], limit=2000)
    assert policy.sanitize({'key-with-' + MARKERS[1]: 'value'}) != {'key-with-' + MARKERS[1]: 'value'}


def test_plain_ordinary_diagnostics_and_internal_address_contract():
    assert redact_text('Connection timeout after 30s') == 'Connection timeout after 30s'
    assert '[internal]' in redact_text('http://localhost:3000/private')
    assert '[internal]' in redact_text('http://127.0.0.1:3000/private')
    assert REDACTED in redact_text('token=opaque-credential')


def test_text_json_quoted_secret_remains_parseable():
    value = '{"Authorization": "opaque-value", "model": "fixture"}'
    safe = json.loads(redact_text(value))
    assert safe['model'] == 'fixture'
    assert 'opaque-value' not in safe['Authorization']
