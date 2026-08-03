"""Intel Brief scheduled sandbox pipeline.

This module rehearses the scheduled Intel Brief controller path without
registering cron/systemd, fetching external sources, calling real Telegram, or
touching production DBs.  It consumes an existing collect-once evidence file and
chains the already-verified dry-run builders.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any

from src.intel.brief_builder import build_brief_dry_run
from src.intel.delivery import build_delivery_sandbox
from src.intel.llm_summary import build_llm_summary_dry_run


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _parse_datetime(value: str) -> datetime:
    normalized = str(value or "").strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    return parsed


def _parse_hhmm(value: str) -> time:
    hour_text, minute_text = str(value or "").strip().split(":", 1)
    return time(hour=int(hour_text), minute=int(minute_text))


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_schedule_decision(
    *,
    now_iso: str,
    scheduled_time: str,
    enabled: bool = True,
    last_run_date: str = "",
) -> dict[str, Any]:
    """Decide whether the sandbox schedule should run for ``now_iso``."""
    now = _parse_datetime(now_iso)
    run_date = now.date().isoformat()
    scheduled = _parse_hhmm(scheduled_time)

    if not enabled:
        reason = "disabled"
        should_run = False
    elif str(last_run_date or "").strip() == run_date:
        reason = "already_ran_today"
        should_run = False
    elif now.timetz().replace(tzinfo=None) < scheduled:
        reason = "before_scheduled_time"
        should_run = False
    else:
        reason = "due"
        should_run = True

    return {
        "enabled": bool(enabled),
        "should_run": should_run,
        "reason": reason,
        "now_iso": now.isoformat(),
        "run_date": run_date,
        "scheduled_time": scheduled_time,
        "last_run_date": str(last_run_date or ""),
    }


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


def run_scheduled_sandbox_pipeline(
    *,
    collect_evidence_path: str | Path,
    output_dir: str | Path,
    evidence_path: str | Path,
    now_iso: str,
    scheduled_time: str,
    stamp: str,
    enabled: bool = True,
    last_run_date: str = "",
    llm_mode: str = "real",
) -> dict[str, Any]:
    """Run the local scheduled sandbox rehearsal and write evidence."""
    collect_path = Path(collect_evidence_path)
    out_dir = Path(output_dir)
    evidence = Path(evidence_path)
    decision = build_schedule_decision(
        now_iso=now_iso,
        scheduled_time=scheduled_time,
        enabled=enabled,
        last_run_date=last_run_date,
    )

    base: dict[str, Any] = {
        "timestamp": _now_iso(),
        "stamp": stamp,
        "phase": "I-scheduled-sandbox",
        "scope": "scheduled_controller_rehearsal_from_existing_collect_evidence",
        "schedule": decision,
        "input_collect_evidence": str(collect_path),
        "evidence_path": str(evidence),
        "limits": [
            "Scheduled sandbox only; no cron/systemd registration.",
            "Uses existing collect-once evidence only; does not call external data sources.",
            "Fake Telegram delivery only; real Bot API is not called.",
            "Sandbox SQLite DB only; production DB is not touched.",
        ],
    }

    if not decision["should_run"]:
        result = {
            **base,
            "status": "skipped",
            "steps": {},
            "artifacts": {},
            "rollback": [str(evidence)],
        }
        _write_json(evidence, result)
        return result

    out_dir.mkdir(parents=True, exist_ok=True)
    brief_md = out_dir / f"{stamp}-brief-dry-run.md"
    brief_json = out_dir / f"{stamp}-brief-dry-run.json"
    summary_md = out_dir / f"{stamp}-llm-summary-dry-run.md"
    summary_json = out_dir / f"{stamp}-llm-summary-dry-run.json"
    delivery_db = out_dir / f"{stamp}-delivery-sandbox.db"
    delivery_outbox = out_dir / f"{stamp}-fake-telegram-outbox.jsonl"
    delivery_evidence = out_dir / f"{stamp}-delivery-sandbox.json"

    brief = build_brief_dry_run(
        collect_evidence_path=collect_path,
        markdown_output_path=brief_md,
        json_output_path=brief_json,
        stamp=stamp,
        content_pipeline_v2=True,
    )
    summary = _run_async(
        build_llm_summary_dry_run(
            dry_run_json_path=brief_json,
            markdown_output_path=summary_md,
            json_output_path=summary_json,
            stamp=stamp,
            llm_attempted=llm_mode != "fallback-only",
        )
    )
    delivery = build_delivery_sandbox(
        summary_evidence_path=summary_json,
        db_path=delivery_db,
        outbox_path=delivery_outbox,
        evidence_path=delivery_evidence,
        stamp=stamp,
    )

    status = "success" if delivery.get("status") == "success" else "partial_failed"
    result = {
        **base,
        "status": status,
        "llm_mode": llm_mode,
        "steps": {
            "brief": brief,
            "llm_summary": summary,
            "delivery": delivery,
        },
        "artifacts": {
            "brief_markdown": str(brief_md),
            "brief_json": str(brief_json),
            "llm_summary_markdown": str(summary_md),
            "llm_summary_json": str(summary_json),
            "delivery_db": str(delivery_db),
            "delivery_outbox": str(delivery_outbox),
            "delivery_evidence": str(delivery_evidence),
        },
        "rollback": [
            str(brief_md),
            str(brief_json),
            str(summary_md),
            str(summary_json),
            str(delivery_db),
            str(delivery_outbox),
            str(delivery_evidence),
            str(evidence),
        ],
    }
    _write_json(evidence, result)
    return result
