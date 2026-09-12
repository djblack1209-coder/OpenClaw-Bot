"""日志最终渲染脱敏与文件权限测试。"""

import logging
import stat
from collections import namedtuple
from io import StringIO

import pytest

from src import log_config


def test_loguru_record_patcher_scrubs_message_and_exception_value():
    record_exception = namedtuple("RecordException", "type value traceback")
    record = {
        "message": "request token=topsecretvalue",
        "exception": record_exception(
            ValueError,
            ValueError("Bearer abcdefghijklmnop"),
            None,
        ),
    }

    log_config._scrub_loguru_record(record)

    assert "topsecretvalue" not in record["message"]
    assert "abcdefghijklmnop" not in str(record["exception"].value)
    assert "REDACTED" in record["message"]
    assert "REDACTED" in str(record["exception"].value)


def test_setup_logging_creates_private_directory_and_files(tmp_path, monkeypatch):
    monkeypatch.setattr(log_config, "_SETUP_DONE", False)

    log_config.setup_logging(json_log_dir=str(tmp_path / "logs"), console=False)
    logging.getLogger("security-test").error("token=topsecretvalue")
    try:
        raise ValueError("Bearer abcdefghijklmnop")
    except ValueError:
        logging.getLogger("security-test").exception("API failure token=anothersecretvalue")

    log_dir = tmp_path / "logs"
    files = list(log_dir.glob("*.log"))
    assert stat.S_IMODE(log_dir.stat().st_mode) == 0o700
    assert files
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in files)
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "topsecretvalue" not in rendered
    assert "anothersecretvalue" not in rendered
    assert "abcdefghijklmnop" not in rendered

    log_config._loguru_logger.remove()
    monkeypatch.setattr(log_config, "_SETUP_DONE", False)

@pytest.fixture
def restore_loggers(monkeypatch):
    root = (logging.root.handlers[:], logging.root.level)
    original = {name: (item.handlers[:], item.propagate, item.level) for name, item in logging.root.manager.loggerDict.items()
                if isinstance(item, logging.Logger)}
    monkeypatch.setattr(log_config, '_SETUP_DONE', False)
    yield
    if log_config._loguru_logger is not None:
        log_config._loguru_logger.remove()
    logging.root.handlers, logging.root.level = root
    for name, item in list(logging.root.manager.loggerDict.items()):
        if isinstance(item, logging.Logger):
            handlers, propagate, level = original.get(name, ([], True, logging.NOTSET))
            item.handlers, item.propagate, item.level = handlers, propagate, level
    log_config._SETUP_DONE = False


@pytest.mark.parametrize('mode', ['metadata', 'redacted'])
def test_loguru_serialized_extra_never_contains_sensitive_fields(tmp_path, monkeypatch, restore_loggers, mode):
    monkeypatch.setenv('OPENCLAW_OBSERVABILITY_CONTENT', mode)
    secret = 'sk-synthetic-log-extra-secret-918372'
    email = 'fixture.log@example.invalid'
    payload = {'nested': {'access_token': secret, 'reply': email}, 'account': 'DU1234567'}
    log_config.setup_logging(json_log_dir=str(tmp_path / 'logs'), console=False)
    log_config._loguru_logger.bind(payload=payload).error('synthetic event')
    rendered = '\n'.join(path.read_text() for path in (tmp_path / 'logs').glob('*.log'))
    assert rendered and 'synthetic event' in rendered
    for marker in [secret, email, 'DU1234567']:
        assert marker not in rendered
    assert payload['nested']['access_token'] == secret


def test_loguru_unknown_extra_never_calls_repr_and_chains_do_not_escape(tmp_path, monkeypatch, restore_loggers):
    monkeypatch.setenv('OPENCLAW_OBSERVABILITY_CONTENT', 'redacted')
    calls = []

    class Opaque:
        def __repr__(self):
            calls.append('repr')
            return 'opaque-business-value'

    payload = {'opaque': Opaque()}
    payload['cycle'] = payload
    log_config.setup_logging(json_log_dir=str(tmp_path / 'logs'), console=False)
    try:
        try:
            raise ValueError('sk-synthetic-log-chain-secret-591873')
        except ValueError as cause:
            raise RuntimeError('fixture.chain@example.invalid') from cause
    except RuntimeError:
        log_config._loguru_logger.bind(payload=payload).exception('synthetic failure')
    rendered = '\n'.join(path.read_text() for path in (tmp_path / 'logs').glob('*.log'))
    assert rendered and calls == []
    for marker in ['sk-synthetic-log-chain-secret-591873', 'fixture.chain@example.invalid', 'opaque-business-value']:
        assert marker not in rendered


def test_stdlib_fallback_has_equivalent_message_exception_and_extra_filtering(monkeypatch, restore_loggers):
    import sys
    stream = StringIO()
    monkeypatch.setattr(log_config, '_HAS_LOGURU', False)
    monkeypatch.setattr(sys, 'stderr', stream)
    monkeypatch.setenv('OPENCLAW_OBSERVABILITY_CONTENT', 'redacted')
    log_config.setup_logging()
    logger = logging.getLogger('fixture.stdlib')
    logger.error('Authorization: Bearer opaque-bearer-value; email=%s', 'fixture.fallback@example.invalid')
    try:
        raise RuntimeError('sk-synthetic-stdlib-secret-812493')
    except RuntimeError:
        logger.exception('failure')
    rendered = stream.getvalue()
    for marker in ['opaque-bearer-value', 'fixture.fallback@example.invalid', 'sk-synthetic-stdlib-secret-812493']:
        assert marker not in rendered
    formatter = log_config.SafeFormatter('%(message)s %(payload)s')
    record = logging.makeLogRecord({'msg': 'fixture', 'payload': {'access_token': 'opaque-extra-value'}})
    assert 'opaque-extra-value' not in formatter.format(record)
    assert record.payload['access_token'] == 'opaque-extra-value'


def test_stdlib_unknown_message_arguments_and_formatting_failure_are_safe():
    calls = []

    class Opaque:
        def __str__(self):
            calls.append('str')
            return 'opaque-business-value'

        def __repr__(self):
            calls.append('repr')
            return 'opaque-business-value'

    formatter = log_config.SafeFormatter('%(message)s')
    for message, args in [('argument=%s', (Opaque(),)), ('argument=%d', (Opaque(),)), (Opaque(), ())]:
        record = logging.makeLogRecord({'msg': message, 'args': args})
        assert 'opaque-business-value' not in formatter.format(record)
    assert calls == []


def test_loguru_thread_name_and_failed_sanitizer_cannot_escape(tmp_path, monkeypatch, restore_loggers):
    import threading
    log_config.setup_logging(json_log_dir=str(tmp_path / 'logs'), console=False)
    monkeypatch.setattr(threading.current_thread(), 'name', 'fixture.thread@example.invalid')
    log_config._loguru_logger.info('thread event')

    def broken(*args, **kwargs):
        raise ValueError('sk-synthetic-sanitizer-failure-913782')

    monkeypatch.setattr(log_config, 'redact_text', broken)
    log_config._loguru_logger.bind(secret='opaque-value').error('sk-synthetic-original-value-813792')
    record = logging.makeLogRecord({'msg': 'sk-synthetic-original-value-813792'})
    assert 'sk-synthetic' not in log_config.SafeFormatter('%(message)s').format(record)
    rendered = '\n'.join(path.read_text() for path in (tmp_path / 'logs').glob('*.log'))
    assert 'thread event' in rendered and '[OMITTED]' in rendered
    for marker in ('sk-synthetic', 'opaque-value', 'fixture.thread@example.invalid'):
        assert marker not in rendered
