"""本地费用唯一账本：事务预留、逐次尝试、未知结果及显式历史导入。"""

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

SCALE = 1_000_000_000
ET = ZoneInfo("America/New_York")


class LedgerError(RuntimeError):
    """账本不可用或状态合同不成立；调用者不得转为绕过预算的重试。"""


class BudgetDenied(LedgerError):
    """请求未获得费用预算，不得发送到上游。"""


def money_units(value) -> int:
    """金额以纳美元存储，预留和结算均向上取整，避免微小正费用变为零。"""
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError
        units = int((number * SCALE).to_integral_value(rounding=ROUND_CEILING))
        if units > 2**63 - 1:
            raise ValueError
        return units
    except (ValueError, TypeError, InvalidOperation, OverflowError) as exc:
        raise LedgerError("invalid nonnegative USD amount") from exc


def _identity(value: str) -> str:
    # 这里只保存模型和内部标识，不接受 URL、正文或异常消息。
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_./:+-]{1,256}", value):
        raise LedgerError("invalid accounting identity")
    return value


class CostLedger:
    def __init__(self, path: Path, *, clock=None):
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(UTC))
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LedgerError("cost ledger unavailable") from exc
        with self._connection(write=True) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            version = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if version is not None and version["value"] not in {"1", "2"}:
                raise LedgerError("unsupported cost ledger schema")
            conn.execute("INSERT OR IGNORE INTO metadata VALUES ('schema_version', '1')")
            conn.execute("""CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY, request_id TEXT NOT NULL,
                provider TEXT NOT NULL, deployment_id TEXT NOT NULL, model TEXT NOT NULL,
                price_snapshot TEXT NOT NULL, task_type TEXT NOT NULL,
                budget_day TEXT NOT NULL, reserved_units INTEGER NOT NULL CHECK(reserved_units >= 0),
                amount_units INTEGER CHECK(amount_units >= 0),
                state TEXT NOT NULL CHECK(state IN ('reserved','dispatched','settled','released','unknown')),
                amount_kind TEXT NOT NULL DEFAULT 'unknown', usage_json TEXT,
                reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS attempts_day_state ON attempts(budget_day, state)")
            if "usage_source" not in {row["name"] for row in conn.execute("PRAGMA table_info(attempts)")}:
                conn.execute("ALTER TABLE attempts ADD COLUMN usage_source TEXT NOT NULL DEFAULT 'unknown'")
            conn.execute("""CREATE TABLE IF NOT EXISTS opening_balances (
                budget_day TEXT PRIMARY KEY, amount_units INTEGER NOT NULL CHECK(amount_units >= 0),
                recorded_at TEXT NOT NULL
            )""")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS legacy_imports (source_hash TEXT PRIMARY KEY, imported_at TEXT NOT NULL)"
            )
            conn.execute("""CREATE TABLE IF NOT EXISTS price_snapshots (
                provider TEXT NOT NULL, deployment_id TEXT NOT NULL, label TEXT NOT NULL,
                digest TEXT NOT NULL, payload TEXT NOT NULL, retired INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(provider,deployment_id,label))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS reconciliations (
                reconciliation_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL,
                previous_units INTEGER, previous_kind TEXT NOT NULL,
                actual_units INTEGER NOT NULL, evidence TEXT NOT NULL, recorded_at TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS bound_violations (
                attempt_id TEXT PRIMARY KEY, recovered_by TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS recoveries (
                recovery_id TEXT PRIMARY KEY, evidence TEXT NOT NULL,
                payload TEXT NOT NULL, recorded_at TEXT NOT NULL)""")
            # Version 1 data is preserved, including unresolved overruns.
            conn.execute(
                "INSERT OR IGNORE INTO bound_violations SELECT attempt_id,NULL FROM attempts WHERE amount_units>reserved_units"
            )
            conn.execute("UPDATE metadata SET value='2' WHERE key='schema_version'")

    @contextmanager
    def _connection(self, *, write=False):
        conn = None
        try:
            conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            conn.row_factory = sqlite3.Row
            # 网络调用不在事务内；SQLite 串行化不同进程的准入判断与预留。
            if write:
                conn.execute("BEGIN IMMEDIATE")
            else:
                conn.execute("BEGIN")
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            if conn is not None and conn.in_transaction:
                conn.rollback()
            raise LedgerError("cost ledger unavailable") from exc
        except BaseException:
            if conn is not None and conn.in_transaction:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def _time(self):
        now = self.clock()
        if now.tzinfo is None:
            raise LedgerError("accounting clock must be timezone aware")
        return now.astimezone(UTC).isoformat(), now.astimezone(ET).date().isoformat()

    def activate(self, *, opening_spend_usd):
        """显式确认切换日已花费总额；空数据库不能自行证明当天零消费。"""
        opening = money_units(opening_spend_usd)
        timestamp, day = self._time()
        with self._connection(write=True) as conn:
            if conn.execute("SELECT 1 FROM metadata WHERE key='coverage_started_at'").fetchone():
                raise LedgerError("coverage already activated")
            recorded = conn.execute(
                "SELECT COALESCE(SUM(amount_units),0) FROM attempts WHERE budget_day=? AND state='settled'", (day,)
            ).fetchone()[0]
            if opening < recorded:
                raise LedgerError("opening spend is below recorded costs")
            conn.execute("INSERT INTO opening_balances VALUES (?,?,?)", (day, opening - recorded, timestamp))
            conn.execute("INSERT INTO metadata VALUES ('coverage_started_at',?)", (timestamp,))

    def reserve(
        self,
        *,
        attempt_id,
        request_id,
        provider,
        deployment_id,
        model,
        price_snapshot,
        budget_usd,
        max_cost_usd,
        task_type="unknown",
        price_details=None,
    ):
        budget, amount = money_units(budget_usd), money_units(max_cost_usd)
        identity = tuple(
            _identity(x) for x in (attempt_id, request_id, provider, deployment_id, model, price_snapshot, task_type)
        )
        timestamp, day = self._time()
        with self._connection(write=True) as conn:
            if price_details is not None:
                if (
                    price_details.get("provider"),
                    price_details.get("deployment_id"),
                    price_details.get("model"),
                    price_details.get("snapshot"),
                ) != (provider, deployment_id, model, price_snapshot):
                    raise LedgerError("price snapshot identity mismatch")
                self._store_price(conn, price_details)
            existing = conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if existing is not None:
                same = (
                    tuple(
                        existing[k]
                        for k in (
                            "attempt_id",
                            "request_id",
                            "provider",
                            "deployment_id",
                            "model",
                            "price_snapshot",
                            "task_type",
                        )
                    )
                    == identity
                )
                if not same or existing["reserved_units"] != amount:
                    raise LedgerError("reservation identity conflict")
                return dict(existing)
            if not conn.execute("SELECT 1 FROM metadata WHERE key='coverage_started_at'").fetchone():
                raise BudgetDenied("coverage not initialized")
            if conn.execute("SELECT 1 FROM metadata WHERE key='bound_exceeded'").fetchone():
                raise BudgetDenied("price bound exceeded; reconciliation required")
            spent = conn.execute(
                "SELECT COALESCE(SUM(amount_units),0) FROM attempts WHERE budget_day=? AND state='settled'", (day,)
            ).fetchone()[0]
            spent += conn.execute(
                "SELECT COALESCE(SUM(amount_units),0) FROM opening_balances WHERE budget_day=?", (day,)
            ).fetchone()[0]
            # 跨日未决尝试继续占用风险额度，不能靠日切丢失预留。
            held = conn.execute(
                "SELECT COALESCE(SUM(reserved_units),0) FROM attempts WHERE state IN ('reserved','dispatched','unknown')"
            ).fetchone()[0]
            if amount > 0 and spent + held + amount > budget:
                raise BudgetDenied("daily budget exhausted")
            conn.execute(
                """INSERT INTO attempts
                (attempt_id,request_id,provider,deployment_id,model,price_snapshot,task_type,
                 budget_day,reserved_units,state,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,'reserved',?,?)""",
                (*identity, day, amount, timestamp, timestamp),
            )
            return dict(conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone())

    @staticmethod
    def _store_price(conn, details):
        from src.core.cost_policy import DeploymentPrice

        allowed = {
            "provider",
            "deployment_id",
            "model",
            "snapshot",
            "source",
            "currency",
            "input_per_million",
            "output_per_million",
            "max_input_tokens",
            "max_output_tokens",
        }
        if not isinstance(details, dict) or set(details) != allowed:
            raise LedgerError("invalid price snapshot fields")
        checked = DeploymentPrice.from_deployment(
            {
                "litellm_params": {"model": details["model"]},
                "model_info": {"id": details["deployment_id"], "accounting": details},
            }
        ).snapshot_data()
        payload = json.dumps(checked, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        identity = (checked["provider"], checked["deployment_id"], checked["snapshot"])
        old = conn.execute(
            "SELECT * FROM price_snapshots WHERE provider=? AND deployment_id=? AND label=?", identity
        ).fetchone()
        if old is not None:
            if old["digest"] != digest:
                raise LedgerError("price snapshot content conflict")
            if old["retired"]:
                raise BudgetDenied("price snapshot retired after bound failure")
        else:
            conn.execute(
                "INSERT INTO price_snapshots(provider,deployment_id,label,digest,payload) VALUES (?,?,?,?,?)",
                (*identity, digest, payload),
            )
        return checked

    def price_for_attempt(self, attempt_id):
        with self._connection() as conn:
            row = conn.execute(
                """SELECT p.payload FROM attempts a JOIN price_snapshots p
                ON a.provider=p.provider AND a.deployment_id=p.deployment_id AND a.price_snapshot=p.label
                WHERE a.attempt_id=?""",
                (attempt_id,),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def _transition(self, attempt_id, target, allowed, reason=None):
        timestamp, _ = self._time()
        with self._connection(write=True) as conn:
            row = conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None:
                raise LedgerError("attempt not found")
            if row["state"] == target:
                return dict(row)
            if row["state"] not in allowed:
                raise LedgerError("invalid attempt transition")
            conn.execute(
                "UPDATE attempts SET state=?,reason=?,updated_at=? WHERE attempt_id=?",
                (target, reason, timestamp, attempt_id),
            )
            return dict(conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone())

    def dispatch(self, attempt_id):
        return self._transition(attempt_id, "dispatched", {"reserved"})

    def release(self, attempt_id):
        return self._transition(attempt_id, "released", {"reserved"}, "not_dispatched")

    def mark_unknown(self, attempt_id, reason, *, usage=None, usage_source="unknown"):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason):
            raise LedgerError("invalid accounting reason")
        usage_json = self._usage_json(usage) if usage is not None else None
        self._validate_usage_source(usage_source)
        timestamp, _ = self._time()
        with self._connection(write=True) as conn:
            row = conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row["state"] not in {"dispatched", "unknown"}:
                raise LedgerError("invalid unknown transition")
            conn.execute(
                "UPDATE attempts SET state='unknown',reason=?,usage_json=COALESCE(?,usage_json),usage_source=?,updated_at=? WHERE attempt_id=?",
                (reason, usage_json, usage_source, timestamp, attempt_id),
            )
            return dict(conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone())

    @staticmethod
    def _validate_usage_source(value):
        if value not in {"unknown", "provider_reported", "configured_zero", "manual"}:
            raise LedgerError("invalid usage source")

    @staticmethod
    def _usage_json(usage):
        usage = usage or {}
        allowed = {
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "audio_input_tokens",
            "audio_output_tokens",
            "web_search_requests",
            "code_execution_requests",
        }
        if (
            not isinstance(usage, dict)
            or set(usage) - allowed
            or any(type(v) is not int or v < 0 for v in usage.values())
        ):
            raise LedgerError("invalid token usage")
        return json.dumps(usage, sort_keys=True)

    def settle(self, attempt_id, cost_usd, *, usage=None, kind="estimated", usage_source="manual"):
        amount = money_units(cost_usd)
        if kind not in {"estimated", "verified_actual", "configured_zero"}:
            raise LedgerError("invalid amount kind")
        usage_json = self._usage_json(usage)
        self._validate_usage_source(usage_source)
        timestamp, _ = self._time()
        with self._connection(write=True) as conn:
            row = conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None:
                raise LedgerError("attempt not found")
            if row["state"] == "settled":
                if (
                    row["amount_units"] != amount
                    or row["amount_kind"] != kind
                    or row["usage_json"] != usage_json
                    or row["usage_source"] != usage_source
                ):
                    raise LedgerError("settlement conflict")
                return dict(row)
            if row["state"] not in {"dispatched", "unknown"}:
                raise LedgerError("invalid settlement transition")
            if amount > row["reserved_units"]:
                conn.execute("INSERT OR REPLACE INTO metadata VALUES ('bound_exceeded',?)", (timestamp,))
                conn.execute("INSERT OR REPLACE INTO bound_violations VALUES (?,NULL)", (attempt_id,))
            conn.execute(
                "UPDATE attempts SET state='settled',amount_units=?,amount_kind=?,usage_json=?,usage_source=?,reason=NULL,updated_at=? WHERE attempt_id=?",
                (amount, kind, usage_json, usage_source, timestamp, attempt_id),
            )
            return dict(conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone())

    def attempts(self):
        with self._connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM attempts ORDER BY created_at,attempt_id")]

    def reconcile(self, attempt_id, actual_usd, *, reconciliation_id, evidence):
        """Append a provider verification/adjustment; retain the original estimate and usage."""
        amount = money_units(actual_usd)
        reconciliation_id, evidence = _identity(reconciliation_id), _identity(evidence)
        timestamp, _ = self._time()
        with self._connection(write=True) as conn:
            prior = conn.execute(
                "SELECT * FROM reconciliations WHERE reconciliation_id=?", (reconciliation_id,)
            ).fetchone()
            if prior:
                if (prior["attempt_id"], prior["actual_units"], prior["evidence"]) != (attempt_id, amount, evidence):
                    raise LedgerError("reconciliation identity conflict")
                return dict(prior)
            row = conn.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row["state"] not in {"settled", "dispatched", "unknown"}:
                raise LedgerError("invalid reconciliation transition")
            conn.execute(
                "INSERT INTO reconciliations VALUES (?,?,?,?,?,?,?)",
                (reconciliation_id, attempt_id, row["amount_units"], row["amount_kind"], amount, evidence, timestamp),
            )
            conn.execute(
                "UPDATE attempts SET state='settled',amount_units=?,amount_kind='verified_actual',reason=NULL,updated_at=? WHERE attempt_id=?",
                (amount, timestamp, attempt_id),
            )
            if amount > row["reserved_units"]:
                conn.execute("INSERT OR REPLACE INTO metadata VALUES ('bound_exceeded',?)", (timestamp,))
                conn.execute("INSERT OR REPLACE INTO bound_violations VALUES (?,NULL)", (attempt_id,))
            return dict(
                conn.execute("SELECT * FROM reconciliations WHERE reconciliation_id=?", (reconciliation_id,)).fetchone()
            )

    def recover_bounds(self, *, recovery_id, evidence, replacements):
        """Recover only reconciled overruns with new, larger immutable price bounds.

        Retire the failed snapshots so stale runtime configuration cannot reopen
        calls. There must be no in-flight or unknown attempts during recovery.
        """
        recovery_id, evidence = _identity(recovery_id), _identity(evidence)
        if not isinstance(replacements, dict) or not replacements:
            raise LedgerError("corrected price snapshots required")
        payload = json.dumps(replacements, sort_keys=True)
        timestamp, _ = self._time()
        with self._connection(write=True) as conn:
            prior = conn.execute("SELECT * FROM recoveries WHERE recovery_id=?", (recovery_id,)).fetchone()
            if prior:
                if prior["payload"] != payload or prior["evidence"] != evidence:
                    raise LedgerError("recovery identity conflict")
                return dict(prior)
            violations = conn.execute("""SELECT a.* FROM attempts a JOIN bound_violations v
                ON a.attempt_id=v.attempt_id WHERE v.recovered_by IS NULL""").fetchall()
            if not violations or set(replacements) != {row["attempt_id"] for row in violations}:
                raise LedgerError("recovery must cover every unresolved bound violation")
            if conn.execute("SELECT 1 FROM attempts WHERE state IN ('reserved','dispatched','unknown')").fetchone():
                raise LedgerError("recovery requires no pending attempts")
            for row in violations:
                if row["amount_kind"] != "verified_actual":
                    raise LedgerError("verify actual charge before recovery")
                old = conn.execute(
                    "SELECT payload FROM price_snapshots WHERE provider=? AND deployment_id=? AND label=?",
                    (row["provider"], row["deployment_id"], row["price_snapshot"]),
                ).fetchone()
                if old is None:
                    raise LedgerError("original price snapshot unavailable; manual investigation required")
                replacement = self._store_price(conn, replacements[row["attempt_id"]])
                previous = json.loads(old[0])
                if any(replacement[key] != previous[key] for key in ("provider", "deployment_id", "model")):
                    raise LedgerError("corrected price identity mismatch")

                def upper(price):
                    return money_units(
                        (
                            Decimal(price["input_per_million"]) * price["max_input_tokens"]
                            + Decimal(price["output_per_million"]) * price["max_output_tokens"]
                        )
                        / 1_000_000
                    )

                if (
                    replacement["snapshot"] == previous["snapshot"]
                    or upper(replacement) <= upper(previous)
                    or upper(replacement) < row["amount_units"]
                ):
                    raise LedgerError("corrected price must increase and cover the failed upper bound")
            for row in violations:
                conn.execute(
                    "UPDATE price_snapshots SET retired=1 WHERE provider=? AND deployment_id=? AND label=?",
                    (row["provider"], row["deployment_id"], row["price_snapshot"]),
                )
                conn.execute(
                    "UPDATE bound_violations SET recovered_by=? WHERE attempt_id=?", (recovery_id, row["attempt_id"])
                )
            conn.execute("INSERT INTO recoveries VALUES (?,?,?,?)", (recovery_id, evidence, payload, timestamp))
            conn.execute("DELETE FROM metadata WHERE key='bound_exceeded'")
            return dict(conn.execute("SELECT * FROM recoveries WHERE recovery_id=?", (recovery_id,)).fetchone())

    def stats(self, *, budget_usd=None):
        _, day = self._time()
        with self._connection() as conn:
            meta = dict(conn.execute("SELECT key,value FROM metadata"))
            rows = conn.execute(
                "SELECT budget_day,model,task_type,amount_units FROM attempts WHERE state='settled'"
            ).fetchall()
            openings = conn.execute("SELECT budget_day,amount_units FROM opening_balances").fetchall()
            holds = conn.execute(
                "SELECT state,reserved_units FROM attempts WHERE state IN ('reserved','dispatched','unknown')"
            ).fetchall()
        today = sum(row["amount_units"] for row in (*rows, *openings) if row["budget_day"] == day)
        total = sum(row["amount_units"] for row in (*rows, *openings))
        held = sum(row["reserved_units"] for row in holds)
        by_model, by_task, daily = {}, {}, {}
        for row in rows:
            daily[row["budget_day"]] = daily.get(row["budget_day"], 0) + row["amount_units"]
            if row["budget_day"] == day:
                by_model[row["model"]] = by_model.get(row["model"], 0) + row["amount_units"]
                by_task[row["task_type"]] = by_task.get(row["task_type"], 0) + row["amount_units"]
        for row in openings:
            daily[row["budget_day"]] = daily.get(row["budget_day"], 0) + row["amount_units"]
        active = "coverage_started_at" in meta
        return {
            "budget_day": day,
            "today_spend": today / SCALE if active else None,
            "known_today_spend": today / SCALE,
            "total_cost_usd": total / SCALE if active and not holds else None,
            "known_total_cost_usd": total / SCALE,
            "reserved_usd": held / SCALE,
            "pending_attempts": len(holds),
            "unknown_attempts": sum(row["state"] == "unknown" for row in holds),
            "coverage_status": "active" if active else "uninitialized",
            "coverage_started_at": meta.get("coverage_started_at"),
            "coverage_started_day": datetime.fromisoformat(meta["coverage_started_at"])
            .astimezone(ET)
            .date()
            .isoformat()
            if active
            else None,
            "historical_complete": False,
            "accounting_complete": active and not holds,
            "bound_exceeded": "bound_exceeded" in meta,
            "available_usd": max(0, money_units(budget_usd) - today - held) / SCALE
            if active and budget_usd is not None
            else None,
            "by_model": {key: value / SCALE for key, value in by_model.items()},
            "by_task": {key: value / SCALE for key, value in by_task.items()},
            "daily_breakdown": {key: value / SCALE for key, value in daily.items()},
        }

    def import_legacy(self, source: Path, *, dry_run=True):
        """显式导入不可变快照；相同内容的不同行仍是不同的历史记录。"""
        source = Path(source)
        try:
            raw = source.read_bytes()
            lines = raw.decode("utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise LedgerError("legacy source unreadable") from exc
        fingerprint = hashlib.sha256(raw).hexdigest()
        records, invalid = [], []
        for position, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                day = row["date"]
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                    raise ValueError
                datetime.strptime(day, "%Y-%m-%d")
                amount = money_units(row["cost_usd"])
                model = _identity(row.get("model", "unknown"))
                task = _identity(row.get("task_type", "unknown"))
                records.append((position, day, amount, model, task))
            except (ValueError, TypeError, KeyError, LedgerError):
                invalid.append(position)
        result = {
            "source_hash": fingerprint,
            "valid_records": len(records),
            "invalid_lines": invalid,
            "dry_run": dry_run,
        }
        if dry_run:
            return result
        if invalid:
            raise LedgerError("legacy import contains invalid records; no rows imported")
        timestamp, _ = self._time()
        with self._connection(write=True) as conn:
            if conn.execute("SELECT 1 FROM legacy_imports WHERE source_hash=?", (fingerprint,)).fetchone():
                return {**result, "already_imported": True}
            if conn.execute("SELECT 1 FROM metadata WHERE key='coverage_started_at'").fetchone():
                raise LedgerError("import legacy data before activating coverage")
            for position, day, amount, model, task in records:
                identifier = f"legacy:{fingerprint}:{position}"
                conn.execute(
                    """INSERT INTO attempts
                    (attempt_id,request_id,provider,deployment_id,model,price_snapshot,task_type,budget_day,
                     reserved_units,amount_units,state,amount_kind,created_at,updated_at)
                    VALUES (?,?,'legacy','legacy',?,'legacy-unverified',?,?,?,?, 'settled','legacy_estimate',?,?)""",
                    (identifier, identifier, model, task, day, amount, amount, timestamp, timestamp),
                )
            conn.execute("INSERT INTO legacy_imports VALUES (?,?)", (fingerprint, timestamp))
        return {**result, "already_imported": False}
