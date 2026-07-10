from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.execution.intel_brief import PRODUCTION_ACK_VALUE, build_intel_brief_scheduler_gate
from src.execution.scheduler import ExecutionScheduler


def test_intel_scheduler_gate_defaults_to_disabled():
    gate = build_intel_brief_scheduler_gate(
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        scheduled_time=(8, 30),
        env={},
        last_run_date="",
    )

    assert gate["should_run"] is False
    assert gate["reason"] == "disabled"
    assert gate["mode"] == "sandbox"
    assert gate["redacted_env"]["INTEL_BRIEF_ENABLED"] is False


def test_intel_scheduler_gate_blocks_production_without_all_hard_gates(tmp_path):
    gate = build_intel_brief_scheduler_gate(
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        scheduled_time=(8, 30),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654",
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "false",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": "",
        },
        last_run_date="",
        project_root=tmp_path,
    )

    assert gate["should_run"] is False
    assert gate["reason"] == "blocked_by_hard_gate"
    assert "worker_placement_not_confirmed" in gate["missing_gates"]
    assert "production_ack_missing" in gate["missing_gates"]
    assert gate["redacted_env"]["INTEL_BRIEF_TELEGRAM_BOT_TOKEN"] is True
    assert "SECRET" not in str(gate)


def test_intel_scheduler_gate_blocks_production_when_summary_evidence_missing(tmp_path):
    gate = build_intel_brief_scheduler_gate(
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        scheduled_time=(8, 30),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654",
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
        },
        last_run_date="",
        project_root=tmp_path,
    )

    assert gate["should_run"] is False
    assert gate["reason"] == "blocked_by_hard_gate"
    assert "summary_evidence_missing" in gate["missing_gates"]


def test_intel_scheduler_gate_requires_telegram_sandbox_ack_for_production_send(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text('{"status":"partial_fallback","items":[{"title":"x"}]}', encoding="utf-8")

    gate = build_intel_brief_scheduler_gate(
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        scheduled_time=(8, 30),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654",
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
            "INTEL_BRIEF_SUMMARY_EVIDENCE": str(summary),
        },
        last_run_date="",
        project_root=tmp_path,
    )

    assert gate["should_run"] is False
    assert "sandbox_send_ack_missing" in gate["missing_gates"]


def test_intel_scheduler_gate_loads_private_env_file_for_production(tmp_path):
    summary = tmp_path / "summary.json"
    private_env = tmp_path / ".openclaw" / "intel-brief.production.env"
    summary.write_text('{"status":"partial_fallback","items":[{"title":"x"}]}', encoding="utf-8")
    private_env.parent.mkdir(parents=True)
    private_env.write_text(
        "\n".join(
            [
                "INTEL_BRIEF_TELEGRAM_BOT_TOKEN='123456:SECRET-DO-NOT-LEAK'",
                "INTEL_BRIEF_TELEGRAM_CHAT_ID='987654'",
                "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK='I_UNDERSTAND_TELEGRAM_SANDBOX_SEND'",
                "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    gate = build_intel_brief_scheduler_gate(
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        scheduled_time=(8, 30),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_PRIVATE_ENV": str(private_env),
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
            "INTEL_BRIEF_SUMMARY_EVIDENCE": str(summary),
        },
        last_run_date="",
        project_root=tmp_path,
    )

    assert gate["should_run"] is True
    assert gate["reason"] == "production_ready"
    assert gate["redacted_env"]["INTEL_BRIEF_TELEGRAM_BOT_TOKEN"] is True
    assert "SECRET" not in str(gate)


def test_intel_scheduler_gate_allows_production_when_all_external_gates_present(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text('{"status":"partial_fallback","items":[{"title":"x"}]}', encoding="utf-8")

    gate = build_intel_brief_scheduler_gate(
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        scheduled_time=(8, 30),
        env={
            "INTEL_BRIEF_ENABLED": "true",
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654",
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
            "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": PRODUCTION_ACK_VALUE,
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": "I_UNDERSTAND_TELEGRAM_SANDBOX_SEND",
            "INTEL_BRIEF_SUMMARY_EVIDENCE": str(summary),
            "INTEL_BRIEF_EVIDENCE_DIR": str(tmp_path / "phaseprod"),
        },
        last_run_date="",
        project_root=tmp_path,
    )

    assert gate["should_run"] is True
    assert gate["reason"] == "production_ready"
    assert gate["missing_gates"] == []
    assert "production_runner_not_implemented" not in gate["missing_gates"]
    assert gate["summary_evidence"] == str(summary)
    assert gate["evidence_dir"] == str(tmp_path / "phaseprod")
    assert "SECRET" not in str(gate)


@pytest.mark.asyncio
async def test_execution_scheduler_runs_intel_production_through_injected_runner(monkeypatch, tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text('{"status":"partial_fallback","items":[{"title":"x"}]}', encoding="utf-8")
    calls: list[dict[str, object]] = []

    def runner(**kwargs):
        calls.append(kwargs)
        return {"status": "success", "network_calls": 1, "evidence_path": str(kwargs["evidence_path"])}

    monkeypatch.setenv("INTEL_BRIEF_ENABLED", "true")
    monkeypatch.setenv("INTEL_BRIEF_MODE", "production")
    monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_BOT_TOKEN", "123456:SECRET-DO-NOT-LEAK")
    monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_CHAT_ID", "987654")
    monkeypatch.setenv("INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED", "true")
    monkeypatch.setenv("INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK", PRODUCTION_ACK_VALUE)
    monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK", "I_UNDERSTAND_TELEGRAM_SANDBOX_SEND")
    monkeypatch.setenv("INTEL_BRIEF_SUMMARY_EVIDENCE", str(summary))
    monkeypatch.setenv("INTEL_BRIEF_EVIDENCE_DIR", str(tmp_path / "phaseprod"))

    scheduler = ExecutionScheduler()
    scheduler.intel_brief_production_runner = runner
    now = datetime(2026, 7, 7, 8, 31, tzinfo=UTC)

    result = await scheduler._run_intel_brief(now, (8, 30))

    assert result["status"] == "success"
    assert len(calls) == 1
    assert Path(calls[0]["summary_evidence_path"]) == summary
    assert calls[0]["allow_real_network"] is True
    assert scheduler._last_intel_brief_date == "2026-07-07"


def test_intel_scheduler_gate_allows_sandbox_when_collect_evidence_exists(tmp_path):
    collect = tmp_path / "collect.json"
    collect.write_text('{"status":"success","runs":[]}', encoding="utf-8")

    gate = build_intel_brief_scheduler_gate(
        now=datetime(2026, 7, 7, 8, 31, tzinfo=UTC),
        scheduled_time=(8, 30),
        env={
            "INTEL_BRIEF_ENABLED": "1",
            "INTEL_BRIEF_MODE": "sandbox",
            "INTEL_BRIEF_COLLECT_EVIDENCE": str(collect),
            "INTEL_BRIEF_EVIDENCE_DIR": str(tmp_path / "phasej"),
        },
        last_run_date="2026-07-06",
        project_root=tmp_path,
    )

    assert gate["should_run"] is True
    assert gate["reason"] == "sandbox_ready"
    assert gate["collect_evidence"] == str(collect)
    assert gate["evidence_dir"] == str(tmp_path / "phasej")


def test_intel_scheduler_gate_prevents_duplicate_run_same_day(tmp_path):
    collect = tmp_path / "collect.json"
    collect.write_text('{"status":"success","runs":[]}', encoding="utf-8")

    gate = build_intel_brief_scheduler_gate(
        now=datetime(2026, 7, 7, 9, 0, tzinfo=UTC),
        scheduled_time=(8, 30),
        env={
            "INTEL_BRIEF_ENABLED": "1",
            "INTEL_BRIEF_MODE": "sandbox",
            "INTEL_BRIEF_COLLECT_EVIDENCE": str(collect),
        },
        last_run_date="2026-07-07",
        project_root=tmp_path,
    )

    assert gate["should_run"] is False
    assert gate["reason"] == "already_ran_today"


@pytest.mark.asyncio
async def test_execution_scheduler_runs_intel_sandbox_only_through_injected_runner(monkeypatch, tmp_path):
    collect = tmp_path / "collect.json"
    collect.write_text('{"status":"success","runs":[]}', encoding="utf-8")
    calls: list[dict[str, object]] = []

    def runner(**kwargs):
        calls.append(kwargs)
        return {"status": "success", "evidence_path": str(kwargs["evidence_path"])}

    monkeypatch.setenv("INTEL_BRIEF_ENABLED", "true")
    monkeypatch.setenv("INTEL_BRIEF_MODE", "sandbox")
    monkeypatch.setenv("INTEL_BRIEF_COLLECT_EVIDENCE", str(collect))
    monkeypatch.setenv("INTEL_BRIEF_EVIDENCE_DIR", str(tmp_path / "phasej"))

    scheduler = ExecutionScheduler()
    scheduler.intel_brief_sandbox_runner = runner
    now = datetime(2026, 7, 7, 8, 31, tzinfo=UTC)

    result = await scheduler._run_intel_brief(now, (8, 30))

    assert result["status"] == "success"
    assert len(calls) == 1
    assert Path(calls[0]["collect_evidence_path"]) == collect
    assert calls[0]["llm_mode"] == "fallback-only"
    assert scheduler._last_intel_brief_date == "2026-07-07"


@pytest.mark.asyncio
async def test_execution_scheduler_marks_blocked_gate_without_running(monkeypatch):
    calls: list[object] = []

    monkeypatch.setenv("INTEL_BRIEF_ENABLED", "true")
    monkeypatch.setenv("INTEL_BRIEF_MODE", "production")

    scheduler = ExecutionScheduler()
    scheduler.intel_brief_sandbox_runner = lambda **kwargs: calls.append(kwargs)
    now = datetime(2026, 7, 7, 8, 31, tzinfo=UTC)

    result = await scheduler._run_intel_brief(now, (8, 30))

    assert result["status"] == "blocked"
    assert result["gate"]["reason"] == "blocked_by_hard_gate"
    assert calls == []
    assert scheduler._last_intel_brief_date == "2026-07-07"


def test_intel_scheduler_gate_probe_cli_writes_redacted_evidence(monkeypatch, tmp_path):
    from scripts.intel_scheduler_gate_probe import main

    output = tmp_path / "gate.json"
    monkeypatch.setenv("INTEL_BRIEF_ENABLED", "true")
    monkeypatch.setenv("INTEL_BRIEF_MODE", "production")
    monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_BOT_TOKEN", "123456:SECRET-DO-NOT-LEAK")

    exit_code = main(
        [
            "--output",
            str(output),
            "--now",
            "2026-07-07T08:31:00+00:00",
            "--time",
            "08:30",
        ]
    )

    saved_text = output.read_text(encoding="utf-8")
    assert exit_code == 2
    assert "SECRET" not in saved_text
    assert "123456" not in saved_text
    assert '"INTEL_BRIEF_TELEGRAM_BOT_TOKEN": true' in saved_text


@pytest.mark.asyncio
async def test_execution_scheduler_default_sandbox_runner_works_inside_async_loop(monkeypatch, tmp_path):
    collect = tmp_path / "collect.json"
    collect.write_text(
        '{"timestamp":"2026-07-07T00:00:00+00:00","status":"success","runs":[]}',
        encoding="utf-8",
    )
    evidence_dir = tmp_path / "phasej"

    monkeypatch.setenv("INTEL_BRIEF_ENABLED", "true")
    monkeypatch.setenv("INTEL_BRIEF_MODE", "sandbox")
    monkeypatch.setenv("INTEL_BRIEF_COLLECT_EVIDENCE", str(collect))
    monkeypatch.setenv("INTEL_BRIEF_EVIDENCE_DIR", str(evidence_dir))
    monkeypatch.setenv("INTEL_BRIEF_LLM_MODE", "fallback-only")

    scheduler = ExecutionScheduler()
    result = await scheduler._run_intel_brief(datetime(2026, 7, 7, 8, 31, tzinfo=UTC), (8, 30))

    assert result["status"] == "success"
    assert (evidence_dir / "20260707T083100Z-scheduled-sandbox.json").exists()
    assert result["steps"]["llm_summary"]["llm"]["llm_attempted"] is False
    assert result["steps"]["delivery"]["network_calls"] == 0
