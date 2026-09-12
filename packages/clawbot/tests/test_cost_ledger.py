"""费用账本的持久化、幂等与跨进程预算合同。"""

import concurrent.futures
import json
import multiprocessing
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from src.core.cost_ledger import BudgetDenied, CostLedger, LedgerError


def reserve(ledger, number, budget="1", amount="0.10"):
    return ledger.reserve(
        attempt_id=f"attempt-{number}",
        request_id=f"request-{number}",
        provider="fixture",
        deployment_id="fixture/gpt-4o-mini",
        model="gpt-4o-mini",
        price_snapshot="fixture-v1",
        budget_usd=budget,
        max_cost_usd=amount,
    )


def price_details(label="review-v1", rate="1000", deployment_id="priced"):
    return {
        "provider": "fixture",
        "deployment_id": deployment_id,
        "model": "fixture-model",
        "snapshot": label,
        "source": "synthetic-reviewed-price",
        "currency": "USD",
        "input_per_million": rate,
        "output_per_million": rate,
        "max_input_tokens": 100,
        "max_output_tokens": 100,
    }


def priced_reserve(ledger, number, details=None):
    details = details or price_details()
    return ledger.reserve(
        attempt_id=f"priced-{number}",
        request_id=f"request-{number}",
        provider=details["provider"],
        deployment_id=details["deployment_id"],
        model=details["model"],
        price_snapshot=details["snapshot"],
        price_details=details,
        budget_usd="1",
        max_cost_usd="0.1",
    )


def test_immutable_price_snapshot_replays_after_restart_and_rejects_conflicts(ledger):
    from decimal import Decimal

    details = price_details()
    priced_reserve(ledger, 1, details)
    ledger.dispatch("priced-1")
    ledger.settle("priced-1", "0.03", usage={"input_tokens": 20, "output_tokens": 10})
    details["input_per_million"] = "2000"
    with pytest.raises(LedgerError, match="conflict"):
        priced_reserve(ledger, 2, details)
    reopened = CostLedger(ledger.path)
    saved = reopened.price_for_attempt("priced-1")
    usage = json.loads(reopened.attempts()[0]["usage_json"])
    replay = (
        Decimal(saved["input_per_million"]) * usage["input_tokens"]
        + Decimal(saved["output_per_million"]) * usage["output_tokens"]
    ) / 1_000_000
    assert replay == Decimal("0.03")
    assert saved["source"] == "synthetic-reviewed-price"
    priced_reserve(ledger, 3, price_details(deployment_id="independent", rate="2000"))
    assert reopened.price_for_attempt("priced-3")["input_per_million"] == "2000"


def test_statistics_use_one_read_snapshot_during_concurrent_settlement(ledger, monkeypatch):
    with sqlite3.connect(ledger.path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    reserve(ledger, 1)
    ledger.dispatch("attempt-1")
    writer = CostLedger(ledger.path)
    reached, finished = threading.Event(), threading.Event()
    original = ledger._connection

    @contextmanager
    def instrumented(**kwargs):
        with original(**kwargs) as connection:

            def trace(statement):
                if statement == "SELECT budget_day,amount_units FROM opening_balances":
                    reached.set()
                    assert finished.wait(5)

            connection.set_trace_callback(trace)
            yield connection

    monkeypatch.setattr(ledger, "_connection", instrumented)

    def settle():
        assert reached.wait(5)
        writer.settle("attempt-1", "0.03")
        finished.set()

    with concurrent.futures.ThreadPoolExecutor(1) as executor:
        future = executor.submit(settle)
        stats = ledger.stats(budget_usd=1)
        future.result(5)
    assert stats["today_spend"] == 0
    assert stats["reserved_usd"] == pytest.approx(0.1)
    assert stats["available_usd"] == pytest.approx(0.9)
    assert not stats["accounting_complete"]
    assert writer.stats()["today_spend"] == pytest.approx(0.03)


def test_reconciliation_preserves_estimate_usage_and_all_adjustments(ledger):
    priced_reserve(ledger, 1)
    ledger.dispatch("priced-1")
    ledger.settle("priced-1", "0.03", usage={"input_tokens": 30})
    first = ledger.reconcile("priced-1", "0.04", reconciliation_id="invoice-1", evidence="provider-invoice-1")
    assert first["previous_units"] == 30_000_000
    assert first["previous_kind"] == "estimated"
    assert first == ledger.reconcile("priced-1", "0.04", reconciliation_id="invoice-1", evidence="provider-invoice-1")
    with pytest.raises(LedgerError, match="conflict"):
        ledger.reconcile("priced-1", "0.05", reconciliation_id="invoice-1", evidence="provider-invoice-1")
    ledger.reconcile("priced-1", "0.035", reconciliation_id="invoice-corrected", evidence="credit-note-1")
    assert ledger.stats()["today_spend"] == pytest.approx(0.035)
    assert json.loads(ledger.attempts()[0]["usage_json"]) == {"input_tokens": 30}


def test_bound_recovery_requires_actuals_corrected_prices_and_retires_old_config(ledger):
    priced_reserve(ledger, 1)
    ledger.dispatch("priced-1")
    ledger.settle("priced-1", "0.3")
    corrected = price_details("review-v2", "2000")
    args = {"recovery_id": "recovery-1", "evidence": "price-review-1", "replacements": {"priced-1": corrected}}
    with pytest.raises(LedgerError, match="verify"):
        ledger.recover_bounds(**args)
    ledger.reconcile("priced-1", "0.3", reconciliation_id="invoice-1", evidence="invoice-1")
    with pytest.raises(LedgerError):
        ledger.recover_bounds(**{**args, "replacements": {"priced-1": price_details("review-v2")}})
    first = ledger.recover_bounds(**args)
    assert first == CostLedger(ledger.path).recover_bounds(**args)
    with pytest.raises(BudgetDenied, match="retired"):
        priced_reserve(ledger, 2)
    priced_reserve(ledger, 2, corrected)
    assert not ledger.stats()["bound_exceeded"]


def _race_accounting(path, barrier, action, amount):
    ledger = CostLedger(path)
    barrier.wait(timeout=10)
    try:
        if action == "reconcile":
            ledger.reconcile("attempt-1", amount, reconciliation_id="shared-invoice", evidence="same-invoice")
        elif action == "release":
            ledger.release("attempt-1")
        else:
            ledger.dispatch("attempt-1")
        return "ok"
    except LedgerError:
        return "conflict"


@pytest.mark.parametrize("race", ["reconcile", "release-dispatch"])
def test_cross_process_reconciliation_and_release_are_atomic(ledger, race):
    reserve(ledger, 1)
    if race == "reconcile":
        ledger.dispatch("attempt-1")
    context = multiprocessing.get_context("spawn")
    with context.Manager() as manager:
        barrier = manager.Barrier(2)
        actions = ["reconcile", "reconcile"] if race == "reconcile" else ["release", "dispatch"]
        with concurrent.futures.ProcessPoolExecutor(2, mp_context=context) as pool:
            futures = [
                pool.submit(_race_accounting, ledger.path, barrier, action, amount)
                for action, amount in zip(actions, ["0.03", "0.04"])
            ]
            assert sorted(future.result(20) for future in futures) == ["conflict", "ok"]


def test_version_one_upgrade_preserves_attempts_and_uncertain_costs(ledger):
    reserve(ledger, 1)
    ledger.dispatch("attempt-1")
    ledger.mark_unknown("attempt-1", "crashed")
    before = ledger.attempts()
    with sqlite3.connect(ledger.path) as connection:
        for table in ("price_snapshots", "reconciliations", "bound_violations", "recoveries"):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("UPDATE metadata SET value='1' WHERE key='schema_version'")
    reopened = CostLedger(ledger.path)
    assert reopened.attempts() == before
    assert reopened.stats()["reserved_usd"] == pytest.approx(0.1)


def test_cli_reconcile_release_and_controlled_recovery(ledger, tmp_path, capsys):
    from src.core.cost_ledger_cli import main

    reserve(ledger, 1)
    main(["--db", str(ledger.path), "release-reserved", "attempt-1"])
    assert json.loads(capsys.readouterr().out)["state"] == "released"
    priced_reserve(ledger, 1)
    ledger.dispatch("priced-1")
    ledger.settle("priced-1", "0.3", usage={"input_tokens": 300})
    main(
        [
            "--db",
            str(ledger.path),
            "reconcile",
            "priced-1",
            "--actual-usd",
            "0.3",
            "--reconciliation-id",
            "receipt-1",
            "--evidence",
            "invoice-1",
        ]
    )
    assert json.loads(capsys.readouterr().out)["previous_kind"] == "estimated"
    replacements = tmp_path / "corrected-price.json"
    replacements.write_text(json.dumps({"priced-1": price_details("review-v2", "2000")}))
    main(
        [
            "--db",
            str(ledger.path),
            "recover-bounds",
            "--recovery-id",
            "review-1",
            "--evidence",
            "pricing-notice",
            "--replacements",
            str(replacements),
        ]
    )
    assert json.loads(capsys.readouterr().out)["recovery_id"] == "review-1"
    assert not ledger.stats()["bound_exceeded"]


@pytest.fixture
def ledger(tmp_path):
    result = CostLedger(tmp_path / "cost.sqlite3")
    result.activate(opening_spend_usd="0")
    return result


def test_new_ledger_is_not_evidence_of_zero_historical_spend(tmp_path):
    ledger = CostLedger(tmp_path / "new.sqlite3")
    assert ledger.stats()["coverage_status"] == "uninitialized"
    with pytest.raises(BudgetDenied, match="coverage"):
        reserve(ledger, 1)


def test_reservation_settlement_and_reopen_are_idempotent(ledger):
    reserve(ledger, 1)
    ledger.dispatch("attempt-1")
    ledger.settle("attempt-1", "0.03", usage={"input_tokens": 100})
    ledger.settle("attempt-1", "0.03", usage={"input_tokens": 100})
    reopened = CostLedger(ledger.path)
    assert reopened.stats()["today_spend"] == pytest.approx(0.03)
    assert reopened.stats()["reserved_usd"] == 0
    assert len(reopened.attempts()) == 1
    with pytest.raises(LedgerError, match="conflict"):
        reopened.settle("attempt-1", "0.04")


def test_different_attempts_of_same_logical_request_are_separate(ledger):
    reserve(ledger, 1)
    ledger.dispatch("attempt-1")
    ledger.mark_unknown("attempt-1", "transport_timeout")
    ledger.reserve(
        attempt_id="retry",
        request_id="request-1",
        provider="fixture",
        deployment_id="fixture/gpt-4o-mini",
        model="gpt-4o-mini",
        price_snapshot="fixture-v1",
        budget_usd="1",
        max_cost_usd="0.10",
    )
    assert ledger.stats()["reserved_usd"] == pytest.approx(0.20)
    assert ledger.stats()["unknown_attempts"] == 1


def test_only_provably_undispatched_reservations_can_be_released(ledger):
    reserve(ledger, 1)
    ledger.release("attempt-1")
    reserve(ledger, 2)
    ledger.dispatch("attempt-2")
    with pytest.raises(LedgerError):
        ledger.release("attempt-2")
    ledger.mark_unknown("attempt-2", "cancelled")
    assert CostLedger(ledger.path).stats()["reserved_usd"] == pytest.approx(0.10)


@pytest.mark.parametrize("amount", ["-1", "NaN", "Infinity", "-Infinity", None, True])
def test_invalid_amounts_never_increase_available_budget(ledger, amount):
    with pytest.raises((LedgerError, ValueError)):
        reserve(ledger, 1, amount=amount)
    assert ledger.attempts() == []


def test_zero_budget_and_subprecision_reservations(ledger):
    with pytest.raises(BudgetDenied):
        reserve(ledger, 1, budget="0", amount="0.0000000001")
    reserve(ledger, 2, budget="0", amount="0")
    reserve(ledger, 3, budget="0.000000001", amount="0.0000000001")
    assert ledger.stats()["reserved_usd"] == pytest.approx(0.000000001)


def test_overrun_is_recorded_in_full_and_blocks_further_calls(ledger):
    reserve(ledger, 1)
    ledger.dispatch("attempt-1")
    ledger.settle("attempt-1", "0.2")
    assert ledger.stats()["today_spend"] == pytest.approx(0.2)
    with pytest.raises(BudgetDenied, match="bound"):
        reserve(ledger, 2)


def test_et_midnight_keeps_unresolved_exposure(tmp_path):
    moment = [datetime(2026, 9, 10, 3, 59, tzinfo=UTC)]
    ledger = CostLedger(tmp_path / "clock.sqlite3", clock=lambda: moment[0])
    ledger.activate(opening_spend_usd="0.30")
    reserve(ledger, 1)
    ledger.dispatch("attempt-1")
    moment[0] += timedelta(minutes=2)
    assert ledger.stats()["budget_day"] == "2026-09-10"
    assert ledger.stats()["today_spend"] == 0
    assert ledger.stats()["reserved_usd"] == pytest.approx(0.10)
    ledger.mark_unknown("attempt-1", "process_lost")
    with pytest.raises(BudgetDenied):
        reserve(ledger, 2, budget="0.15")
    ledger.settle("attempt-1", "0.08")
    assert ledger.stats()["today_spend"] == 0
    assert ledger.stats()["total_cost_usd"] == pytest.approx(0.38)


def _process_reservations(path, barrier, offset):
    ledger = CostLedger(path)
    barrier.wait(timeout=15)
    allowed = 0
    for number in range(offset, offset + 16):
        try:
            reserve(ledger, number)
            allowed += 1
        except BudgetDenied:
            pass
    return allowed


def test_two_processes_cannot_oversubscribe_budget(ledger):
    context = multiprocessing.get_context("spawn")
    with context.Manager() as manager:
        barrier = manager.Barrier(2)
        with concurrent.futures.ProcessPoolExecutor(2, mp_context=context) as pool:
            jobs = [pool.submit(_process_reservations, ledger.path, barrier, offset) for offset in (0, 16)]
            assert sum(job.result(timeout=25) for job in jobs) == 10
    assert ledger.stats()["reserved_usd"] == 1


def test_legacy_preview_and_import_preserve_identical_distinct_lines(tmp_path):
    ledger = CostLedger(tmp_path / "legacy.sqlite3")
    old = tmp_path / "daily_costs.jsonl"
    line = json.dumps({"date": "2026-09-09", "cost_usd": 0.01, "model": "old", "task_type": "chat"}) + "\n"
    old.write_text(line + line)
    assert ledger.import_legacy(old, dry_run=True)["valid_records"] == 2
    assert ledger.attempts() == []
    ledger.import_legacy(old, dry_run=False)
    ledger.import_legacy(old, dry_run=False)
    assert len(ledger.attempts()) == 2
    assert ledger.stats()["total_cost_usd"] is None
    assert ledger.stats()["known_total_cost_usd"] == pytest.approx(0.02)
    assert old.read_text() == line + line
    assert ledger.stats()["coverage_status"] == "uninitialized"


@pytest.mark.parametrize("bad", ["{broken", '{"date":"2026-09-09","cost_usd":-5}'])
def test_invalid_legacy_records_prevent_partial_import(tmp_path, bad):
    ledger = CostLedger(tmp_path / "legacy.sqlite3")
    old = tmp_path / "daily_costs.jsonl"
    old.write_text('{"date":"2026-09-09","cost_usd":1}\n' + bad + "\n")
    assert ledger.import_legacy(old, dry_run=True)["invalid_lines"] == [2]
    with pytest.raises(LedgerError):
        ledger.import_legacy(old, dry_run=False)
    assert ledger.attempts() == []


def test_independent_threads_and_event_loops_compete_for_one_budget(ledger):
    import asyncio

    barrier = threading.Barrier(32)

    def run(number):
        own = CostLedger(ledger.path)
        barrier.wait(timeout=15)

        async def attempt():
            try:
                reserve(own, number)
                return 1
            except BudgetDenied:
                return 0

        return asyncio.run(attempt())

    with concurrent.futures.ThreadPoolExecutor(32) as pool:
        assert sum(pool.map(run, range(32))) == 10
    assert ledger.stats()["reserved_usd"] == 1


@pytest.mark.parametrize(
    "before,after",
    [
        ("2026-03-08T06:59:00+00:00", "2026-03-08T07:01:00+00:00"),
        ("2026-11-01T05:59:00+00:00", "2026-11-01T06:01:00+00:00"),
    ],
)
def test_dst_change_does_not_reset_spend(tmp_path, before, after):
    moment = [datetime.fromisoformat(before)]
    ledger = CostLedger(tmp_path / "dst.sqlite3", clock=lambda: moment[0])
    ledger.activate(opening_spend_usd="0.30")
    day = ledger.stats()["budget_day"]
    moment[0] = datetime.fromisoformat(after)
    assert ledger.stats()["budget_day"] == day
    assert ledger.stats()["today_spend"] == pytest.approx(0.30)


def test_database_write_failure_cannot_create_a_reservation(ledger, monkeypatch):
    import sqlite3

    original = sqlite3.connect

    def readonly(*args, **kwargs):
        conn = original(*args, **kwargs)
        conn.execute("PRAGMA query_only=ON")
        return conn

    monkeypatch.setattr(sqlite3, "connect", readonly)
    with pytest.raises(LedgerError, match="unavailable"):
        reserve(ledger, 1)
    assert ledger.attempts() == []


def test_explicit_cli_preview_preserves_source_and_requires_activation(tmp_path, capsys):
    from src.core.cost_ledger_cli import main

    source = tmp_path / "old.jsonl"
    source.write_text('{"date":"2026-09-09","cost_usd":0.2}\n')
    db = tmp_path / "cli.sqlite3"
    main(["--db", str(db), "import-legacy", str(source)])
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert CostLedger(db).attempts() == []
    main(["--db", str(db), "import-legacy", str(source), "--apply"])
    assert len(CostLedger(db).attempts()) == 1
    assert CostLedger(db).stats()["coverage_status"] == "uninitialized"
