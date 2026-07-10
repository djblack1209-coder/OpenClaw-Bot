"""Intel Brief full one-shot production cycle.

This runner is the next step after ``production_once``: it collects fresh
verified sources, builds a fresh sanitized brief and summary, then calls the
same gated production-once delivery runner.  It does not install schedulers or
create persistent workers.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.intel_collect_once import collect_once
from src.execution._utils import parse_hhmm
from src.execution.intel_brief import build_intel_brief_scheduler_gate
from src.intel.brief_builder import build_brief_dry_run
from src.intel.llm_summary import build_llm_summary_dry_run
from src.intel.production_once import parse_now, run_intel_production_once
from src.intel.subscription_lifecycle import audit_subscription_lifecycle

CollectRunner = Callable[..., dict[str, Any]]
ProductionOnceRunner = Callable[..., dict[str, Any]]

DEFAULT_PRODUCTION_CYCLE_SOURCES = (
    "senate_trading",
    "akshare",
    "github_trending",
    "ai_model_updates",
    "institutional_13f",
    "weather",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _redacted_preflight_env(env: dict[str, str]) -> dict[str, bool]:
    return {
        "INTEL_BRIEF_PRIVATE_ENV": bool(str(env.get("INTEL_BRIEF_PRIVATE_ENV") or "").strip()),
        "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": bool(
            str(env.get("INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK") or "").strip()
        ),
    }




def _merge_private_env(env: dict[str, str], root: Path) -> dict[str, str]:
    private_env_text = str(env.get("INTEL_BRIEF_PRIVATE_ENV") or "").strip()
    if not private_env_text:
        return env
    private_env_path = Path(private_env_text)
    if not private_env_path.is_absolute():
        private_env_path = root / private_env_path
    if not private_env_path.exists():
        return env
    from src.intel.private_env import load_private_env_file

    return {**load_private_env_file(private_env_path), **env, "INTEL_BRIEF_PRIVATE_ENV": str(private_env_path)}


def _subscription_lifecycle_readonly_audit(
    *,
    env: dict[str, str],
    root: Path,
    now: datetime,
) -> dict[str, Any]:
    merged_env = _merge_private_env(env, root)
    db_text = str(merged_env.get("INTEL_BRIEF_DB_PATH") or "").strip()
    if not db_text:
        return {
            "status": "skipped",
            "reason": "intel_brief_db_path_missing",
            "network_calls": 0,
            "redacted_env": {"INTEL_BRIEF_DB_PATH": False},
            "limits": [
                "Lifecycle audit is read-only and skipped when INTEL_BRIEF_DB_PATH is not configured.",
                "No subscription status mutation and no Telegram reminder send.",
            ],
        }
    db_path = Path(db_text)
    if not db_path.is_absolute():
        db_path = root / db_path
    if not db_path.exists():
        return {
            "status": "skipped",
            "reason": "intel_brief_db_path_not_found",
            "network_calls": 0,
            "redacted_env": {"INTEL_BRIEF_DB_PATH": True, "INTEL_BRIEF_DB_PATH_EXISTS": False},
            "limits": [
                "Lifecycle audit is read-only and skipped when INTEL_BRIEF_DB_PATH does not exist.",
                "No subscription status mutation and no Telegram reminder send.",
            ],
        }
    audit = audit_subscription_lifecycle(
        db_path=db_path,
        now=now,
        reminder_days=7,
        apply_expiry=False,
        send_reminders=False,
        sender=None,
        source="production_cycle_readonly_audit",
    )
    return {
        "status": audit.get("status", "success"),
        "reason": "readonly_audit_complete",
        "db_path_present": True,
        "db_path_exists": True,
        "audit": audit,
        "network_calls": int(audit.get("network_calls", 0) or 0),
        "limits": [
            "Lifecycle audit runs read-only inside production_cycle: apply_expiry=False and send_reminders=False.",
            "No subscription status mutation and no Telegram reminder send.",
        ],
    }


def _production_preflight_gate(
    *,
    now: datetime,
    scheduled_time: str,
    env: dict[str, str],
    project_root: str | Path | None,
) -> dict[str, Any]:
    return build_intel_brief_scheduler_gate(
        now=now,
        scheduled_time=parse_hhmm(scheduled_time, (8, 30)),
        env={
            **env,
            "INTEL_BRIEF_ENABLED": env.get("INTEL_BRIEF_ENABLED", "true"),
            "INTEL_BRIEF_MODE": "production",
            # Preflight only needs to prove hard gates before remote collection.
            # A real summary path is generated later and checked again by production_once.
            "INTEL_BRIEF_SUMMARY_EVIDENCE": __file__,
        },
        project_root=project_root,
    )


def run_intel_production_cycle(
    *,
    output_dir: str | Path,
    evidence_path: str | Path,
    now: datetime | None = None,
    scheduled_time: str = "08:30",
    env: dict[str, str] | None = None,
    project_root: str | Path | None = None,
    stamp: str | None = None,
    sources: list[str] | None = None,
    llm_mode: str = "fallback-only",
    collect_runner: CollectRunner | None = None,
    production_once_runner: ProductionOnceRunner | None = None,
) -> dict[str, Any]:
    """Run fresh collect -> brief -> summary -> gated Telegram production delivery."""
    now_value = now or _now()
    run_stamp = stamp or _stamp(now_value)
    env_map = dict(os.environ if env is None else env)
    root = Path(project_root) if project_root is not None else Path.cwd()
    out_dir = Path(output_dir)
    evidence = Path(evidence_path)
    selected_sources = list(sources or DEFAULT_PRODUCTION_CYCLE_SOURCES)

    preflight = _production_preflight_gate(
        now=now_value,
        scheduled_time=scheduled_time,
        env=env_map,
        project_root=root,
    )
    base: dict[str, Any] = {
        "timestamp": _now().isoformat(),
        "stamp": run_stamp,
        "phase": "S-production-cycle",
        "scope": "fresh_collect_to_summary_to_gated_telegram_production_delivery",
        "status": "blocked",
        "preflight": preflight,
        "sources": selected_sources,
        "llm_mode": llm_mode,
        "redacted_env": _redacted_preflight_env(env_map),
        "steps": {},
        "artifacts": {},
        "subscription_lifecycle": {},
        "network_calls": 0,
        "limits": [
            "One-shot production cycle; does not install launchd/cron/systemd.",
            "Remote collection uses existing temporary worker runner cleanup boundaries.",
            "No Telegram call before production gates are ready.",
            "Secrets are represented only as booleans in evidence.",
        ],
    }
    if not preflight.get("should_run"):
        result = {
            **base,
            "status": "blocked",
            "rollback": [str(evidence)],
        }
        _write_json(evidence, result)
        return result

    lifecycle = _subscription_lifecycle_readonly_audit(env=env_map, root=root, now=now_value)

    out_dir.mkdir(parents=True, exist_ok=True)
    child_dir = out_dir / f"{run_stamp}-child-runs"
    collect_evidence = out_dir / f"{run_stamp}-collect-once.json"
    brief_md = out_dir / f"{run_stamp}-brief-dry-run.md"
    brief_json = out_dir / f"{run_stamp}-brief-dry-run.json"
    summary_md = out_dir / f"{run_stamp}-llm-summary-dry-run.md"
    summary_json = out_dir / f"{run_stamp}-llm-summary-dry-run.json"
    delivery_evidence = out_dir / f"{run_stamp}-production-once-delivery.json"

    collect_fn = collect_runner or collect_once
    collect_payload = collect_fn(
        sources=selected_sources,
        output_path=collect_evidence,
        evidence_dir=child_dir,
        stamp=run_stamp,
    )
    if str(collect_payload.get("status")) != "success":
        result = {
            **base,
            "status": "failed",
            "steps": {"collect": collect_payload},
            "artifacts": {"collect_evidence": str(collect_evidence), "child_evidence_dir": str(child_dir)},
            "subscription_lifecycle": lifecycle,
            "rollback": [str(collect_evidence), str(child_dir), str(evidence)],
        }
        _write_json(evidence, result)
        return result

    brief = build_brief_dry_run(
        collect_evidence_path=collect_evidence,
        markdown_output_path=brief_md,
        json_output_path=brief_json,
        stamp=run_stamp,
    )
    import asyncio

    summary = asyncio.run(
        build_llm_summary_dry_run(
            dry_run_json_path=brief_json,
            markdown_output_path=summary_md,
            json_output_path=summary_json,
            stamp=run_stamp,
            llm_attempted=llm_mode != "fallback-only",
        )
    )
    production_fn = production_once_runner or run_intel_production_once
    delivery = production_fn(
        summary_evidence_path=summary_json,
        evidence_path=delivery_evidence,
        now=now_value,
        scheduled_time=scheduled_time,
        env=env_map,
        project_root=root,
    )
    network_calls = int(delivery.get("network_calls") or 0)
    status = "success" if delivery.get("status") == "success" else "failed"
    result = {
        **base,
        "status": status,
        "steps": {
            "collect": collect_payload,
            "brief": brief,
            "llm_summary": summary,
            "production_once": delivery,
        },
        "subscription_lifecycle": lifecycle,
        "artifacts": {
            "collect_evidence": str(collect_evidence),
            "child_evidence_dir": str(child_dir),
            "brief_markdown": str(brief_md),
            "brief_json": str(brief_json),
            "llm_summary_markdown": str(summary_md),
            "llm_summary_json": str(summary_json),
            "production_once_delivery": str(delivery_evidence),
        },
        "network_calls": network_calls,
        "rollback": [
            str(child_dir),
            str(collect_evidence),
            str(brief_md),
            str(brief_json),
            str(summary_md),
            str(summary_json),
            str(delivery_evidence),
            str(evidence),
        ],
    }
    _write_json(evidence, result)
    return result


__all__ = ["DEFAULT_PRODUCTION_CYCLE_SOURCES", "parse_now", "run_intel_production_cycle"]
