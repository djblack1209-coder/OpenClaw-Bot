"""Durable delivery state: fencing, uncertain outcomes and restart safety."""
import concurrent.futures
import json
import subprocess
import sys
import threading
import time

import pytest

from src.execution.report_delivery_store import ReportDeliveryStore, StaleLease


@pytest.fixture
def clock():
    return [1000.0]


def store_at(path, clock):
    return ReportDeliveryStore(path, clock=lambda: clock[0], coverage_start=900, lease_seconds=30)


def job(store, **kwargs):
    return store.ensure('daily_brief', 1000, 1200, 'telegram', 'bot:1/chat:2', **kwargs)


def ready(store, ident):
    lease = store.claim(ident)
    store.begin_generation(ident, lease['token'])
    store.generated(ident, lease['token'], 'first sectionsecond section', ['first section', 'second section'])
    return lease['token']


def test_concurrent_claim_has_one_owner(tmp_path, clock):
    path = tmp_path / 'reports.db'
    store = store_at(path, clock)
    ident = job(store)
    barrier = threading.Barrier(8)

    def claim():
        instance = store_at(path, clock)
        barrier.wait()
        return instance.claim(ident)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: claim(), range(8)))
    assert sum(value is not None for value in claims) == 1


def test_generation_survives_restart_without_regeneration(tmp_path, clock):
    path = tmp_path / 'reports.db'
    store = store_at(path, clock)
    ident = job(store)
    token = ready(store, ident)
    store.release(ident, token)
    reopened = store_at(path, clock)
    lease = reopened.claim(ident)
    assert lease['job']['state'] == 'ready'
    assert lease['job']['generation_attempts'] == 1
    assert [part['text'] for part in reopened.get(ident)['parts']] == ['first section', 'second section']
    assert reopened.get(ident)['generation_quality'] == 'unverified'


def test_expired_generation_owner_is_fenced(tmp_path, clock):
    store = store_at(tmp_path / 'reports.db', clock)
    ident = job(store)
    old = store.claim(ident)
    store.begin_generation(ident, old['token'])
    clock[0] += 31
    new = store.claim(ident)
    assert new and new['token'] != old['token']
    store.begin_generation(ident, new['token'])
    with pytest.raises(StaleLease):
        store.generated(ident, old['token'], 'stale generated report', ['stale generated report'])
    store.generated(ident, new['token'], 'fresh generated report', ['fresh generated report'])


def test_crash_during_send_becomes_unknown_and_never_replays(tmp_path, clock):
    path = tmp_path / 'reports.db'
    store = store_at(path, clock)
    ident = job(store)
    token = ready(store, ident)
    attempt = store.begin_part(ident, token, 0)
    clock[0] += 31
    reopened = store_at(path, clock)
    assert reopened.claim(ident) is None
    assert reopened.get(ident)['state'] == 'unknown'
    assert reopened.get(ident)['parts'][0]['state'] == 'unknown'
    with pytest.raises(StaleLease):
        store.finish_part(ident, token, 0, attempt, 'sent', message_id=7)
    clock[0] = 1300
    assert reopened.claim(ident) is None
    assert reopened.get(ident)['state'] == 'unknown'


def test_confirmed_parts_are_not_resent_after_safe_retry(tmp_path, clock):
    store = store_at(tmp_path / 'reports.db', clock)
    ident = job(store)
    token = ready(store, ident)
    attempt = store.begin_part(ident, token, 0)
    store.finish_part(ident, token, 0, attempt, 'sent', message_id=10)
    attempt = store.begin_part(ident, token, 1)
    store.finish_part(ident, token, 1, attempt, 'retryable_failure', reason='rate_limited', retry_after=10)
    store.release(ident, token)
    assert store.claim(ident) is None
    clock[0] += 10
    token = store.claim(ident)['token']
    with pytest.raises(ValueError):
        store.begin_part(ident, token, 0)
    attempt = store.begin_part(ident, token, 1)
    store.finish_part(ident, token, 1, attempt, 'sent', message_id=11)
    assert store.get(ident)['state'] == 'sent'
    assert [part['message_id'] for part in store.get(ident)['parts']] == ['10', '11']
    assert store.claim(ident) is None


def test_unknown_reconciliation_is_explicit_idempotent_and_bounded(tmp_path, clock):
    store = store_at(tmp_path / 'reports.db', clock)
    ident = job(store)
    token = ready(store, ident)
    attempt = store.begin_part(ident, token, 0)
    store.finish_part(ident, token, 0, attempt, 'unknown', reason='timeout')
    result = store.resolve(ident, 0, 'confirmed_sent', operation_id='op1', evidence='ticket:check-42', message_id=21)
    assert store.resolve(ident, 0, 'confirmed_sent', operation_id='op1', evidence='ticket:check-42', message_id=21) == result
    with pytest.raises(ValueError):
        store.resolve(ident, 0, 'not_sent', operation_id='op1', evidence='ticket:check-42')
    assert store.get(ident)['state'] == 'ready'
    assert store.get(ident)['parts'][0]['state'] == 'sent'
    with pytest.raises(ValueError):
        store.resolve(ident, 1, 'not_sent', operation_id='op2', evidence='ticket:new')


def test_cutoff_coverage_and_disable_are_not_sent(tmp_path, clock):
    store = store_at(tmp_path / 'reports.db', clock)
    old = store.ensure('daily_brief', 800, 1100, 'telegram', 'bot:1/chat:2')
    assert store.claim(old) is None
    assert store.get(old)['reason'] == 'before_coverage'
    ident = job(store)
    token = store.claim(ident)['token']
    store.defer(ident, token, 'disabled', 'user_disabled')
    assert store.claim(ident) is None
    later = store.ensure('morning_news', 1000, 1020, 'telegram', 'bot:1/chat:2')
    clock[0] = 1021
    assert store.claim(later) is None
    assert store.get(later)['state'] == 'expired'
    assert store.get(ident)['state'] == 'disabled'


def test_target_channel_and_full_schedule_are_distinct(tmp_path, clock):
    store = store_at(tmp_path / 'reports.db', clock)
    ids = {
        store.ensure('weekly_report', when, when + 100, channel, target)
        for when in (1000, 31537000)
        for channel in ('telegram', 'wechat')
        for target in ('owner:1', 'owner:2')
    }
    assert len(ids) == 8


def test_sent_requires_receipt_and_unknown_cannot_be_released(tmp_path, clock):
    store = store_at(tmp_path / 'reports.db', clock)
    ident = job(store)
    token = ready(store, ident)
    attempt = store.begin_part(ident, token, 0)
    with pytest.raises(ValueError):
        store.finish_part(ident, token, 0, attempt, 'sent')
    store.release(ident, token)
    assert store.get(ident)['state'] == 'unknown'
    assert store.claim(ident) is None


def test_status_omits_content_and_target_and_can_read_missing_db(tmp_path, clock):
    path = tmp_path / 'reports.db'
    missing = ReportDeliveryStore(path, create=False)
    assert not missing.summary()['configured']
    assert not path.exists()
    store = store_at(path, clock)
    ident = job(store)
    ready(store, ident)
    summary = str(store.summary())
    assert 'first section' not in summary and 'bot:1/chat:2' not in summary


@pytest.mark.timeout(90)
def test_separate_processes_claim_the_same_sqlite_job_once(tmp_path, clock):
    path = tmp_path / 'reports.db'
    store = store_at(path, clock)
    ident = job(store)
    script = '''import sys
from src.execution.report_delivery_store import ReportDeliveryStore
s = ReportDeliveryStore(sys.argv[1], clock=lambda: 1000)
print(int(s.claim(sys.argv[2]) is not None))
'''
    processes = [subprocess.Popen([sys.executable, '-c', script, str(path), ident],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
    # Cold amd64 imports under Rosetta need a bounded shared startup allowance.
    deadline = time.monotonic() + 60
    try:
        outputs = [process.communicate(timeout=max(0.1, deadline - time.monotonic()))
                   for process in processes]
        assert all(process.returncode == 0 for process in processes), outputs
        assert sum(int(out[0].strip()) for out in outputs) == 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate()


def test_recovery_reconciles_old_jobs_after_their_scheduled_day(tmp_path, clock):
    store = store_at(tmp_path / 'reports.db', clock)
    ident = job(store)
    token = ready(store, ident)
    store.begin_part(ident, token, 0)
    pending = store.ensure('morning_news', 1000, 1200, 'telegram', 'bot:1/chat:2')
    clock[0] += 86400
    store.recover()
    assert store.get(ident)['state'] == 'unknown'
    assert store.get(pending)['state'] == 'expired'


@pytest.mark.parametrize('value', [0, -1, True, 1.2, 'receipt', '0'])
def test_receipt_ids_must_be_positive_integers(tmp_path, clock, value):
    store = store_at(tmp_path / 'reports.db', clock)
    ident = job(store)
    token = ready(store, ident)
    attempt = store.begin_part(ident, token, 0)
    with pytest.raises(ValueError):
        store.finish_part(ident, token, 0, attempt, 'sent', message_id=value)


def test_retry_after_is_never_shortened_and_expires_at_window(tmp_path, clock):
    store = store_at(tmp_path / 'reports.db', clock)
    ident = store.ensure('daily_brief', 1000, 10000, 'telegram', 'target')
    token = ready(store, ident)
    attempt = store.begin_part(ident, token, 0)
    store.finish_part(ident, token, 0, attempt, 'retryable_failure', retry_after=7200)
    store.release(ident, token)
    assert store.get(ident)['retry_at'] == 8200
    clock[0] = 4601
    assert store.claim(ident) is None
    clock[0] = 8200
    token = store.claim(ident)['token']
    attempt = store.begin_part(ident, token, 0)
    store.finish_part(ident, token, 0, attempt, 'retryable_failure', retry_after=7200)
    assert store.get(ident)['state'] == 'expired'


def test_manual_not_sent_does_not_reset_attempt_budget(tmp_path, clock):
    store = ReportDeliveryStore(tmp_path / 'reports.db', clock=lambda: clock[0], coverage_start=900, max_attempts=1)
    ident = job(store)
    token = ready(store, ident)
    attempt = store.begin_part(ident, token, 0)
    store.finish_part(ident, token, 0, attempt, 'unknown')
    store.resolve(ident, 0, 'not_sent', operation_id='op1', evidence='ticket:checked')
    assert store.claim(ident) is None
    assert store.get(ident)['state'] == 'permanent_failure'


def test_cli_status_is_read_only_and_resolution_has_required_proof(tmp_path, clock, capsys):
    from src.execution.report_delivery_cli import main
    path = tmp_path / 'reports.db'
    assert main(['--db', str(path), 'status']) == 0
    assert not json.loads(capsys.readouterr().out)['configured'] and not path.exists()
    store = store_at(path, clock)
    ident = job(store)
    token = ready(store, ident)
    store.begin_part(ident, token, 0)
    store.release(ident, token)
    args = ['--db', str(path), 'resolve', ident, '--part', '0', '--action', 'confirmed_sent',
            '--expected-state', 'unknown', '--operation-id', 'check-001', '--evidence', 'ticket:checked', '--message-id', '33']
    assert main(args) == main(args) == 0
    assert store.get(ident)['parts'][0]['message_id'] == '33'
    with pytest.raises(SystemExit):
        main(['--db', str(path), 'resolve', ident])


def test_blocked_preflight_does_not_consume_generation_attempts(tmp_path, clock):
    store = store_at(tmp_path / 'reports.db', clock)
    ident = store.ensure('daily_brief', 1000, 2000, 'telegram', 'target')
    for _ in range(4):
        claim = store.claim(ident)
        assert claim is not None
        store.defer(ident, claim['token'], 'blocked', 'preference_unavailable', retry_after=10)
        clock[0] += 11
    assert store.get(ident)['generation_attempts'] == 0
