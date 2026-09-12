"""Durable manual-order authorization and dispatch, independent of cost accounting."""

import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

PROTOCOL = 'manual-sell-v1'
ACTIVE = ('claimed', 'dispatched', 'submitted', 'partially_filled', 'unknown')
TERMINAL = ('filled', 'rejected', 'cancelled', 'expired')


class ManualTradeError(RuntimeError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def request_identity(value):
    try:
        parsed = UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise ManualTradeError('invalid_request_id', 422) from None
    return value


class ManualTradeStore:
    """A claim is single use; dispatched work is never made eligible for replay."""

    def __init__(self, path, *, clock=time.time):
        self.path, self.clock = Path(path).absolute(), clock
        try:
            for parent in (self.path, *self.path.parents):
                if parent.is_symlink():
                    raise OSError('symlink')
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.path.parent.stat().st_uid != os.getuid():
                raise OSError('owner')
            self.path.parent.chmod(0o700)
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                    raise OSError('unsafe_file')
                os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
        except OSError:
            raise ManualTradeError('manual_trade_store_unavailable', 503) from None
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('schema_version','1')")
            if db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] != '1':
                raise ManualTradeError('unsupported_manual_trade_schema', 503)
            db.execute('''CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY, payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
                account TEXT NOT NULL, con_id INTEGER NOT NULL, environment TEXT NOT NULL,
                state TEXT NOT NULL, challenge_hash TEXT NOT NULL, expires_at REAL NOT NULL,
                owner TEXT, lease_until REAL, order_ref TEXT NOT NULL UNIQUE,
                result TEXT, reason TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL
            )''')
            db.execute('CREATE INDEX IF NOT EXISTS request_scope ON requests(account,con_id,environment,state)')
            db.execute('''CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, state TEXT NOT NULL,
                reason TEXT NOT NULL, detail TEXT NOT NULL, recorded_at REAL NOT NULL
            )''')

    @contextmanager
    def connection(self):
        db = None
        try:
            if self.path.is_symlink():
                raise ManualTradeError('manual_trade_store_unavailable', 503)
            db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except sqlite3.Error:
            if db is not None and db.in_transaction:
                db.rollback()
            raise ManualTradeError('manual_trade_store_unavailable', 503) from None
        except BaseException:
            if db is not None and db.in_transaction:
                db.rollback()
            raise
        finally:
            if db is not None:
                db.close()

    def now(self):
        value = self.clock()
        if type(value) not in {int, float} or not math.isfinite(value):
            raise ManualTradeError('invalid_clock', 503)
        return value

    def _append(self, db, request_id, state, reason, detail=None):
        db.execute('INSERT INTO evidence(request_id,state,reason,detail,recorded_at) VALUES (?,?,?,?,?)',
                   (request_id, state, reason, canonical_json(detail or {}), self.now()))

    def _expire(self, db):
        now = self.now()
        rows = db.execute("SELECT request_id FROM requests WHERE (state='prepared' AND expires_at<=?) "
                          "OR (state='claimed' AND (lease_until<=? OR expires_at<=?))", (now, now, now)).fetchall()
        for row in rows:
            db.execute("UPDATE requests SET state='expired',owner=NULL,reason='authorization_expired',updated_at=? WHERE request_id=?",
                       (now, row['request_id']))
            self._append(db, row['request_id'], 'expired', 'authorization_expired')

    def _row(self, db, request_id):
        row = db.execute('SELECT * FROM requests WHERE request_id=?', (request_identity(request_id),)).fetchone()
        if row is None:
            raise ManualTradeError('request_not_found', 404)
        return row

    def _conflict(self, db, payload, request_id):
        placeholders = ','.join('?' for _ in ACTIVE)
        if db.execute(f'SELECT 1 FROM requests WHERE account=? AND con_id=? AND environment=? '
                      f'AND request_id!=? AND state IN ({placeholders}) LIMIT 1',
                      (payload['account'], payload['con_id'], payload['environment'], request_id, *ACTIVE)).fetchone():
            raise ManualTradeError('unresolved_order_for_contract')

    def prepare(self, request_id, payload, *, ttl=120):
        request_identity(request_id)
        if type(ttl) is not int or not 1 <= ttl <= 120:
            raise ManualTradeError('invalid_confirmation_expiry', 422)
        encoded = canonical_json(payload)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        challenge = secrets.token_urlsafe(32)
        with self.connection() as db:
            self._expire(db)
            existing = db.execute('SELECT * FROM requests WHERE request_id=?', (request_id,)).fetchone()
            if existing is not None:
                if existing['payload_hash'] != digest:
                    raise ManualTradeError('request_payload_conflict')
                return self.public(existing), None
            self._conflict(db, payload, request_id)
            now = self.now()
            db.execute('''INSERT INTO requests(request_id,payload,payload_hash,account,con_id,environment,state,
                        challenge_hash,expires_at,order_ref,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (request_id, encoded, digest, payload['account'], payload['con_id'], payload['environment'],
                        'prepared', hashlib.sha256(challenge.encode()).hexdigest(), now + ttl,
                        'oe' + uuid4().hex, now, now))
            self._append(db, request_id, 'prepared', 'confirmation_required')
            return self.public(self._row(db, request_id)), challenge

    def claim(self, request_id, payload, challenge, confirmed):
        if confirmed is not True:
            raise ManualTradeError('explicit_confirmation_required', 422)
        with self.connection() as db:
            self._expire(db)
            row = self._row(db, request_id)
            if row['payload'] != canonical_json(payload):
                raise ManualTradeError('request_payload_conflict')
            if row['state'] != 'prepared':
                return dict(row), None
            if type(challenge) is not str or not 20 <= len(challenge) <= 128 or not hmac.compare_digest(
                    row['challenge_hash'], hashlib.sha256(challenge.encode()).hexdigest()):
                raise ManualTradeError('confirmation_invalid', 403)
            self._conflict(db, payload, request_id)
            owner = uuid4().hex
            now = self.now()
            db.execute("UPDATE requests SET state='claimed',challenge_hash='',owner=?,lease_until=?,updated_at=? WHERE request_id=?",
                       (owner, min(now + 120, row['expires_at']), now, request_id))
            self._append(db, request_id, 'claimed', 'confirmation_consumed')
            return dict(self._row(db, request_id)), owner

    def dispatch(self, request_id, owner):
        """Called synchronously immediately before placeOrder, on the broker loop."""
        with self.connection() as db:
            self._expire(db)
            row = self._row(db, request_id)
            if row['state'] != 'claimed' or row['owner'] != owner:
                raise ManualTradeError('execution_authority_lost')
            self._conflict(db, json.loads(row['payload']), request_id)
            db.execute("UPDATE requests SET state='dispatched',updated_at=? WHERE request_id=?", (self.now(), request_id))
            self._append(db, request_id, 'dispatched', 'broker_call_may_have_effect')

    def finish(self, request_id, owner, state, result=None, *, reason='broker_result'):
        if state not in (*TERMINAL, 'submitted', 'partially_filled', 'unknown'):
            raise ManualTradeError('invalid_order_state', 503)
        with self.connection() as db:
            row = self._row(db, request_id)
            if row['owner'] != owner or row['state'] not in {'claimed', 'dispatched'}:
                return self.public(row)
            if row['state'] == 'claimed' and state not in {'rejected', 'expired'}:
                state, result, reason = 'unknown', None, 'unexpected_execution_state'
            db.execute('UPDATE requests SET state=?,result=?,reason=?,updated_at=? WHERE request_id=?',
                       (state, canonical_json(result or {}), reason, self.now(), request_id))
            self._append(db, request_id, state, reason, result)
            return self.public(self._row(db, request_id))

    def get(self, request_id):
        with self.connection() as db:
            self._expire(db)
            return dict(self._row(db, request_id))

    def reconcile(self, request_id, result):
        """Only broker-matched, append-only evidence; this method never submits."""
        state = result['state']
        if state not in {'submitted', 'partially_filled', 'filled', 'cancelled', 'rejected'}:
            raise ManualTradeError('inconclusive_broker_evidence')
        with self.connection() as db:
            row = self._row(db, request_id)
            if row['state'] not in {'dispatched', 'unknown', 'submitted', 'partially_filled'}:
                return self.public(row)
            prior = json.loads(row['result'] or '{}')
            if (float(result.get('filled_qty', 0)) < float(prior.get('filled_qty', 0))
                    or (prior.get('perm_id') and prior['perm_id'] != result.get('perm_id'))):
                raise ManualTradeError('conflicting_broker_evidence')
            serialized = canonical_json(result)
            if row['result'] != serialized or row['state'] != state:
                db.execute("UPDATE requests SET state=?,result=?,reason='broker_reconciled',updated_at=? WHERE request_id=?",
                           (state, serialized, self.now(), request_id))
                self._append(db, request_id, state, 'broker_reconciled', result)
            return self.public(self._row(db, request_id))

    @staticmethod
    def public(row):
        state = row['state']
        result = json.loads(row['result'] or '{}')
        return {'request_id': row['request_id'], 'protocol': PROTOCOL, 'state': state,
                'summary': json.loads(row['payload']), 'expires_at': row['expires_at'],
                'success': state in {'submitted', 'partially_filled', 'filled'},
                'requires_reconciliation': state in {'dispatched', 'unknown'},
                'reason': row['reason'], **result}
