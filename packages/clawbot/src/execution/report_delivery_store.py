"""Durable ordinary-report delivery, with fenced leases and explicit uncertainty."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from src.db_utils import get_conn

DEFAULT_PATH = Path(__file__).resolve().parents[2] / 'data' / 'report_delivery.sqlite3'
KINDS = {'daily_brief', 'morning_news', 'weekly_report'}
TERMINAL = {'sent', 'permanent_failure', 'unknown', 'disabled', 'expired'}


class StaleLease(RuntimeError):
    """The caller no longer owns this operation; it must not send or update."""


def _number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('timestamp must be finite')
    return value


def _reason(value):
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', value):
        raise ValueError('reason must be a non-secret code')
    return value


def _message_id(value):
    if value is None or isinstance(value, bool) or not re.fullmatch(r'[1-9][0-9]{0,127}', str(value)):
        raise ValueError('a confirmed receipt is required')
    return str(value)


class ReportDeliveryStore:
    def __init__(self, path=DEFAULT_PATH, *, clock=time.time, coverage_start=None,
                 lease_seconds=180, max_attempts=3, create=True):
        self.path = Path(path)
        self.clock = clock
        self.lease_seconds = max(1, min(int(lease_seconds), 900))
        self.max_attempts = max(1, min(int(max_attempts), 3))
        self.writable = create
        if create:
            with self._write() as conn:
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS report_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS reports(
                        id TEXT PRIMARY KEY,kind TEXT NOT NULL,scheduled_at REAL NOT NULL,deadline REAL NOT NULL,
                        channel TEXT NOT NULL,target TEXT NOT NULL,state TEXT NOT NULL,
                        generation_state TEXT NOT NULL DEFAULT 'pending',generation_quality TEXT NOT NULL DEFAULT 'unverified',
                        generation_attempts INTEGER NOT NULL DEFAULT 0,text TEXT,content_sha TEXT,
                        lease_token TEXT,lease_until REAL,retry_at REAL NOT NULL DEFAULT 0,
                        reason TEXT NOT NULL DEFAULT '',updated_at REAL NOT NULL,
                        UNIQUE(kind,scheduled_at,channel,target));
                    CREATE TABLE IF NOT EXISTS report_parts(
                        report_id TEXT NOT NULL,seq INTEGER NOT NULL,text TEXT NOT NULL,content_sha TEXT NOT NULL,
                        state TEXT NOT NULL DEFAULT 'ready',attempts INTEGER NOT NULL DEFAULT 0,
                        retry_at REAL NOT NULL DEFAULT 0,message_id TEXT,reason TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY(report_id,seq),FOREIGN KEY(report_id) REFERENCES reports(id));
                    CREATE TABLE IF NOT EXISTS report_attempts(
                        id TEXT PRIMARY KEY,report_id TEXT NOT NULL,seq INTEGER NOT NULL,
                        started_at REAL NOT NULL,finished_at REAL,outcome TEXT,reason TEXT NOT NULL DEFAULT '');
                    CREATE TABLE IF NOT EXISTS report_operations(
                        id TEXT PRIMARY KEY,intent TEXT NOT NULL,result TEXT NOT NULL,created_at REAL NOT NULL);
                ''')
                start = _number(self.clock() if coverage_start is None else coverage_start)
                conn.execute('INSERT OR IGNORE INTO report_meta VALUES (?,?)', ('coverage_start', str(start)))
                if coverage_start is not None and float(conn.execute(
                    "SELECT value FROM report_meta WHERE key='coverage_start'"
                ).fetchone()[0]) != start:
                    raise ValueError('coverage start is immutable')

    @contextmanager
    def _write(self):
        if not self.writable:
            raise ValueError('read-only report store')
        with get_conn(str(self.path), row_factory=sqlite3.Row) as conn:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('BEGIN IMMEDIATE')
            yield conn

    @contextmanager
    def _read(self):
        conn = sqlite3.connect(f'file:{quote(str(self.path.absolute()))}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('BEGIN')
            yield conn
        finally:
            conn.close()

    def ensure(self, kind, scheduled_at, deadline, channel, target):
        scheduled_at, deadline = _number(scheduled_at), _number(deadline)
        if kind not in KINDS or channel not in {'telegram', 'wechat'} or not target or len(target) > 256:
            raise ValueError('invalid delivery identity')
        if not scheduled_at < deadline <= scheduled_at + 6 * 3600:
            raise ValueError('invalid delivery window')
        identity = json.dumps([kind, scheduled_at, channel, target], separators=(',', ':'))
        ident = hashlib.sha256(identity.encode()).hexdigest()
        with self._write() as conn:
            start = float(conn.execute("SELECT value FROM report_meta WHERE key='coverage_start'").fetchone()[0])
            state, reason = ('expired', 'before_coverage') if scheduled_at < start else ('pending', '')
            conn.execute('''INSERT OR IGNORE INTO reports
                (id,kind,scheduled_at,deadline,channel,target,state,reason,updated_at) VALUES (?,?,?,?,?,?,?,?,?)''',
                (ident, kind, scheduled_at, deadline, channel, target, state, reason, self.clock()))
        return ident

    @staticmethod
    def _owned(conn, ident, token, now):
        row = conn.execute('SELECT * FROM reports WHERE id=?', (ident,)).fetchone()
        if not row or row['lease_token'] != token or row['lease_until'] is None or row['lease_until'] <= now:
            raise StaleLease('delivery lease is no longer owned')
        return row

    @staticmethod
    def _unknown(conn, ident, now, reason):
        conn.execute("UPDATE report_parts SET state='unknown',reason=? WHERE report_id=? AND state='sending'", (reason, ident))
        conn.execute("UPDATE report_attempts SET finished_at=?,outcome='unknown',reason=? WHERE report_id=? AND finished_at IS NULL", (now, reason, ident))
        conn.execute("UPDATE reports SET state='unknown',reason=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?", (reason, now, ident))

    def claim(self, ident):
        now = _number(self.clock())
        with self._write() as conn:
            row = conn.execute('SELECT * FROM reports WHERE id=?', (ident,)).fetchone()
            if not row:
                raise ValueError('unknown report')
            if row['state'] in TERMINAL:
                return None
            if row['lease_token'] and row['lease_until'] > now:
                return None
            if row['state'] == 'sending':
                self._unknown(conn, ident, now, 'expired_send_lease')
                return None
            if now >= row['deadline']:
                conn.execute("UPDATE reports SET state='expired',reason='window_expired',lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?", (now, ident))
                return None
            if now < row['scheduled_at'] or now < row['retry_at']:
                return None
            next_part = conn.execute("SELECT attempts FROM report_parts WHERE report_id=? AND state!='sent' ORDER BY seq LIMIT 1", (ident,)).fetchone()
            if next_part and next_part['attempts'] >= self.max_attempts:
                conn.execute("UPDATE reports SET state='permanent_failure',reason='retry_exhausted',lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?", (now, ident))
                return None
            if row['text'] is None and row['generation_attempts'] >= self.max_attempts:
                conn.execute("UPDATE reports SET state='permanent_failure',reason='generation_exhausted',lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?", (now, ident))
                return None
            token = uuid.uuid4().hex
            generating = row['text'] is None
            conn.execute('''UPDATE reports SET state=?,generation_state=?,
                lease_token=?,lease_until=?,reason='',updated_at=? WHERE id=?''',
                ('generating' if generating else 'ready', 'pending' if generating else row['generation_state'],
                 token, now + self.lease_seconds, now, ident))
            return {'token': token, 'job': dict(conn.execute('SELECT * FROM reports WHERE id=?', (ident,)).fetchone())}

    def begin_generation(self, ident, token):
        """Count a durable generation attempt only after target/preference checks."""
        now = self.clock()
        with self._write() as conn:
            row = self._owned(conn, ident, token, now)
            if row['state'] != 'generating' or row['generation_state'] != 'pending' or row['generation_attempts'] >= self.max_attempts:
                raise ValueError('generation is not ready')
            conn.execute("UPDATE reports SET generation_state='generating',generation_attempts=generation_attempts+1,updated_at=? WHERE id=?", (now, ident))

    def recover(self):
        """Reconcile abandoned effects even when their schedule is no longer current."""
        now = self.clock()
        with self._write() as conn:
            for row in conn.execute("SELECT id FROM reports WHERE state='sending' AND lease_until<=?", (now,)).fetchall():
                self._unknown(conn, row['id'], now, 'expired_send_lease')
            conn.execute("""UPDATE reports SET state='expired',reason='window_expired',lease_token=NULL,lease_until=NULL,updated_at=?
                WHERE deadline<=? AND state IN ('pending','generating','ready','retryable_failure','blocked')
                AND (lease_until IS NULL OR lease_until<=?)""", (now, now, now))

    def generated(self, ident, token, text, chunks, *, quality='unverified'):
        if not isinstance(text, str) or len(text.strip()) <= 20 or not chunks or ''.join(chunks) != text:
            raise ValueError('report content is insufficient or chunks changed content')
        if quality not in {'unverified', 'degraded', 'verified'}:
            raise ValueError('invalid generation quality')
        now = self.clock()
        with self._write() as conn:
            row = self._owned(conn, ident, token, now)
            if row['state'] != 'generating' or row['generation_state'] != 'generating' or row['text'] is not None:
                raise ValueError('generation is not pending')
            conn.execute("UPDATE reports SET state='ready',generation_state='generated',generation_quality=?,text=?,content_sha=?,updated_at=? WHERE id=?",
                         (quality, text, hashlib.sha256(text.encode()).hexdigest(), now, ident))
            for seq, part in enumerate(chunks):
                if not isinstance(part, str) or not part:
                    raise ValueError('empty report part')
                conn.execute('INSERT INTO report_parts(report_id,seq,text,content_sha) VALUES (?,?,?,?)',
                             (ident, seq, part, hashlib.sha256(part.encode()).hexdigest()))

    def generation_failed(self, ident, token, reason, *, retry_after=60, permanent=False):
        now = self.clock()
        with self._write() as conn:
            row = self._owned(conn, ident, token, now)
            if row['state'] != 'generating' or row['generation_state'] != 'generating':
                raise ValueError('generation is not owned')
            retry_at = now + max(1, min(_number(retry_after), 3600))
            state = 'permanent_failure' if permanent or row['generation_attempts'] >= self.max_attempts else 'retryable_failure'
            if retry_at >= row['deadline']:
                state = 'expired'
            conn.execute("UPDATE reports SET state=?,generation_state='failed',reason=?,retry_at=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                         (state, _reason(reason), retry_at, now, ident))

    def defer(self, ident, token, state, reason, *, retry_after=60):
        if state not in {'disabled', 'blocked', 'expired', 'permanent_failure'}:
            raise ValueError('invalid deferred state')
        now = self.clock()
        with self._write() as conn:
            self._owned(conn, ident, token, now)
            conn.execute('UPDATE reports SET state=?,reason=?,retry_at=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?',
                         (state, _reason(reason), now + max(1, min(_number(retry_after), 3600)), now, ident))

    def begin_part(self, ident, token, seq):
        now = self.clock()
        with self._write() as conn:
            row = self._owned(conn, ident, token, now)
            part = conn.execute('SELECT * FROM report_parts WHERE report_id=? AND seq=?', (ident, seq)).fetchone()
            if row['state'] not in {'ready', 'retryable_failure'} or not part or part['state'] not in {'ready', 'retryable_failure'}:
                raise ValueError('part is not ready to send')
            if now >= row['deadline'] or now < part['retry_at'] or part['attempts'] >= self.max_attempts:
                raise ValueError('part is outside its retry policy')
            if conn.execute("SELECT 1 FROM report_parts WHERE report_id=? AND seq<? AND state!='sent'", (ident, seq)).fetchone():
                raise ValueError('an earlier part is not confirmed')
            attempt = uuid.uuid4().hex
            conn.execute("UPDATE report_parts SET state='sending',attempts=attempts+1,reason='' WHERE report_id=? AND seq=?", (ident, seq))
            conn.execute('INSERT INTO report_attempts(id,report_id,seq,started_at) VALUES (?,?,?,?)', (attempt, ident, seq, now))
            conn.execute("UPDATE reports SET state='sending',lease_until=?,updated_at=? WHERE id=?", (now + self.lease_seconds, now, ident))
            return attempt

    def finish_part(self, ident, token, seq, attempt, status, *, message_id=None, reason='', retry_after=60):
        if status not in {'sent', 'retryable_failure', 'permanent_failure', 'unknown'}:
            raise ValueError('invalid receipt outcome')
        receipt_id = _message_id(message_id) if status == 'sent' else None
        reason = _reason(reason) if reason else ''
        now = self.clock()
        with self._write() as conn:
            row = self._owned(conn, ident, token, now)
            part = conn.execute('SELECT * FROM report_parts WHERE report_id=? AND seq=?', (ident, seq)).fetchone()
            sending = conn.execute('SELECT * FROM report_attempts WHERE id=? AND report_id=? AND seq=? AND finished_at IS NULL', (attempt, ident, seq)).fetchone()
            if not part or part['state'] != 'sending' or not sending:
                raise ValueError('send attempt is not pending')
            retry_at = now + max(1, _number(retry_after)) if status == 'retryable_failure' else 0
            if status == 'retryable_failure' and part['attempts'] >= self.max_attempts:
                status, reason = 'permanent_failure', 'retry_exhausted'
            if status == 'retryable_failure' and retry_at >= row['deadline']:
                status, reason = 'expired', 'retry_after_window'
            conn.execute('UPDATE report_parts SET state=?,message_id=?,reason=?,retry_at=? WHERE report_id=? AND seq=?',
                         (status, receipt_id, reason, retry_at, ident, seq))
            conn.execute('UPDATE report_attempts SET finished_at=?,outcome=?,reason=? WHERE id=?', (now, status, reason, attempt))
            state = status
            if status == 'sent':
                state = 'ready' if conn.execute("SELECT 1 FROM report_parts WHERE report_id=? AND state!='sent'", (ident,)).fetchone() else 'sent'
            conn.execute('UPDATE reports SET state=?,reason=?,retry_at=?,updated_at=? WHERE id=?', (state, reason, retry_at, now, ident))

    def release(self, ident, token):
        now = self.clock()
        with self._write() as conn:
            row = conn.execute('SELECT * FROM reports WHERE id=? AND lease_token=?', (ident, token)).fetchone()
            if not row:
                return
            if row['state'] == 'sending':
                self._unknown(conn, ident, now, 'sender_left_without_receipt')
            else:
                state = 'pending' if row['state'] == 'generating' else row['state']
                generation = 'pending' if row['generation_state'] == 'generating' else row['generation_state']
                conn.execute('UPDATE reports SET state=?,generation_state=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?',
                             (state, generation, now, ident))

    def resolve(self, ident, seq, action, *, operation_id, evidence, message_id=None, expected_state='unknown'):
        if action not in {'confirmed_sent', 'not_sent'} or expected_state != 'unknown':
            raise ValueError('only an explicitly checked unknown part can be resolved')
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', operation_id):
            raise ValueError('invalid operation id')
        if not re.fullmatch(r'[A-Za-z0-9 /_.:-]{1,256}', evidence) or any(word in evidence.lower() for word in ('token', 'secret', 'password')):
            raise ValueError('use a non-secret evidence reference without URL query credentials')
        receipt = _message_id(message_id) if action == 'confirmed_sent' else None
        intent = json.dumps([ident, seq, action, evidence, receipt, expected_state], separators=(',', ':'))
        now = self.clock()
        with self._write() as conn:
            existing = conn.execute('SELECT * FROM report_operations WHERE id=?', (operation_id,)).fetchone()
            if existing:
                if existing['intent'] != intent:
                    raise ValueError('operation id conflicts with its original intent')
                return json.loads(existing['result'])
            row = conn.execute('SELECT * FROM reports WHERE id=?', (ident,)).fetchone()
            part = conn.execute('SELECT * FROM report_parts WHERE report_id=? AND seq=?', (ident, seq)).fetchone()
            if not row or row['state'] != expected_state or not part or part['state'] != expected_state:
                raise ValueError('expected unknown state no longer matches')
            state = 'sent' if action == 'confirmed_sent' else 'ready'
            conn.execute('UPDATE report_parts SET state=?,message_id=?,reason=?,retry_at=0 WHERE report_id=? AND seq=?',
                         (state, receipt, 'operator_' + action, ident, seq))
            all_sent = not conn.execute("SELECT 1 FROM report_parts WHERE report_id=? AND state!='sent'", (ident,)).fetchone()
            report_state = 'sent' if all_sent else ('expired' if now >= row['deadline'] else 'ready')
            conn.execute("UPDATE reports SET state=?,reason=?,retry_at=0,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                         (report_state, 'operator_' + action, now, ident))
            result = {'report_id': ident, 'seq': seq, 'state': report_state, 'operation_id': operation_id}
            conn.execute('INSERT INTO report_operations VALUES (?,?,?,?)', (operation_id, intent, json.dumps(result), now))
            return result

    def get(self, ident):
        with self._read() as conn:
            row = conn.execute('SELECT * FROM reports WHERE id=?', (ident,)).fetchone()
            if not row:
                raise ValueError('unknown report')
            result = dict(row)
            result['parts'] = [dict(part) for part in conn.execute('SELECT * FROM report_parts WHERE report_id=? ORDER BY seq', (ident,))]
            return result

    def summary(self):
        if not self.path.exists():
            return {'configured': False, 'coverage_start': None, 'reports': [], 'counts': {}}
        with self._read() as conn:
            start = float(conn.execute("SELECT value FROM report_meta WHERE key='coverage_start'").fetchone()[0])
            rows = conn.execute('''SELECT id,kind,scheduled_at,deadline,channel,state,generation_state,generation_quality,
                generation_attempts,content_sha,reason,retry_at,updated_at FROM reports ORDER BY scheduled_at DESC LIMIT 50''').fetchall()
            counts = {row[0]: row[1] for row in conn.execute('SELECT state,count(*) FROM reports GROUP BY state')}
            reports = []
            for row in rows:
                report = dict(row)
                report['parts'] = [dict(part) for part in conn.execute(
                    'SELECT seq,state,attempts,message_id,reason,retry_at FROM report_parts WHERE report_id=? ORDER BY seq', (row['id'],))]
                reports.append(report)
            return {'configured': True, 'coverage_start': start, 'reports': reports, 'counts': counts}
