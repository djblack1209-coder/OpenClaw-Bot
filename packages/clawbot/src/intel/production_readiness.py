"""Intel Brief production readiness audit.

Read-only aggregator for the remaining production gates.  It consumes existing
evidence files and environment presence flags, but performs no network calls,
deployment, scheduler registration, or production DB writes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.execution._utils import parse_hhmm
from src.execution.intel_brief import build_intel_brief_scheduler_gate
from src.intel.private_env import load_private_env_file
from src.intel.telegram_delivery import build_telegram_sandbox_gate


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    return parsed


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _merge_private_env(env: dict[str, str], root: Path) -> dict[str, str]:
    private_env_text = str(env.get("INTEL_BRIEF_PRIVATE_ENV") or "").strip()
    if not private_env_text:
        return env
    private_env_path = Path(private_env_text)
    if not private_env_path.is_absolute():
        private_env_path = root / private_env_path
    if not private_env_path.exists():
        return env
    return {**load_private_env_file(private_env_path), **env, "INTEL_BRIEF_PRIVATE_ENV": str(private_env_path)}


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, "not_found"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "invalid_json"
    return payload if isinstance(payload, dict) else None, "ok" if isinstance(payload, dict) else "not_object"


def _collect_check(path: Path) -> dict[str, Any]:
    payload, state = _load_json(path)
    if state != "ok" or payload is None:
        return {"ready": False, "path": str(path), "reason": f"collect_evidence_{state}"}
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    success = int(summary.get("success") or 0)
    failed = int(summary.get("failed") or 0)
    runs = [run for run in payload.get("runs", []) if isinstance(run, dict)]
    ready = success > 0 and failed == 0 and bool(runs)
    return {
        "ready": ready,
        "path": str(path),
        "status": str(payload.get("status") or ""),
        "success": success,
        "failed": failed,
        "run_count": len(runs),
        "reason": "" if ready else "collect_evidence_not_successful",
    }


def _summary_check(path: Path) -> dict[str, Any]:
    payload, state = _load_json(path)
    if state != "ok" or payload is None:
        return {"ready": False, "path": str(path), "reason": f"summary_evidence_{state}"}
    items = [item for item in payload.get("items", []) if isinstance(item, dict)]
    llm = payload.get("llm", {}) if isinstance(payload.get("llm"), dict) else {}
    ready = bool(items) and str(payload.get("status") or "") in {"success", "partial_fallback"}
    return {
        "ready": ready,
        "path": str(path),
        "status": str(payload.get("status") or ""),
        "item_count": len(items),
        "llm_attempted": bool(llm.get("llm_attempted")),
        "llm_success": bool(llm.get("llm_success")),
        "reason": "" if ready else "summary_evidence_not_ready",
    }


def _missing_from_check(prefix: str, check: dict[str, Any]) -> list[str]:
    if check.get("ready"):
        return []
    reason = str(check.get("reason") or f"{prefix}_not_ready")
    return [reason]


def build_intel_production_readiness_report(
    *,
    collect_evidence_path: str | Path,
    summary_evidence_path: str | Path,
    now_iso: str,
    scheduled_time: str = "08:30",
    env: dict[str, str] | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Aggregate production-readiness gates into a redacted report."""
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2]
    env_map = _merge_private_env(dict(os.environ if env is None else env), root)
    collect_path = Path(collect_evidence_path)
    summary_path = Path(summary_evidence_path)
    if not collect_path.is_absolute():
        collect_path = root / collect_path
    if not summary_path.is_absolute():
        summary_path = root / summary_path

    collect = _collect_check(collect_path)
    summary = _summary_check(summary_path)
    telegram_gate = build_telegram_sandbox_gate(env_map)
    scheduler_gate = build_intel_brief_scheduler_gate(
        now=_parse_datetime(now_iso),
        scheduled_time=parse_hhmm(scheduled_time, (8, 30)),
        env={
            **env_map,
            "INTEL_BRIEF_ENABLED": env_map.get("INTEL_BRIEF_ENABLED", "true"),
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_SUMMARY_EVIDENCE": str(summary_path),
        },
        project_root=root,
    )
    worker_placement_ready = _truthy(env_map.get("INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED"))

    checks = {
        "collect_evidence": collect,
        "summary_evidence": summary,
        "telegram_sandbox_gate": {
            "ready": bool(telegram_gate.get("ready")),
            "gate": telegram_gate,
            "reason": "" if telegram_gate.get("ready") else "telegram_sandbox_gate_not_ready",
        },
        "scheduler_production_gate": {
            "ready": bool(scheduler_gate.get("should_run")),
            "gate": scheduler_gate,
            "reason": "" if scheduler_gate.get("should_run") else "scheduler_production_gate_not_ready",
        },
        "worker_placement": {
            "ready": worker_placement_ready,
            "reason": "" if worker_placement_ready else "worker_placement_not_confirmed",
        },
    }

    missing: list[str] = []
    missing.extend(_missing_from_check("collect_evidence", collect))
    missing.extend(_missing_from_check("summary_evidence", summary))
    missing.extend(telegram_gate.get("missing_gates", []))
    missing.extend(scheduler_gate.get("missing_gates", []))
    if not worker_placement_ready:
        missing.append("worker_placement_not_confirmed")
    missing = sorted(dict.fromkeys(str(item) for item in missing if item))
    ready_count = sum(1 for check in checks.values() if check.get("ready"))
    total_count = len(checks)

    return {
        "timestamp": _now_iso(),
        "phase": "M-production-readiness",
        "scope": "read_only_production_readiness_audit",
        "status": "ready" if not missing and ready_count == total_count else "blocked",
        "now_iso": now_iso,
        "scheduled_time": scheduled_time,
        "checks": checks,
        "missing_gates": missing,
        "readiness_score": {"ready": ready_count, "total": total_count},
        "network_calls": 0,
        "limits": [
            "Read-only production readiness audit; no deployment or external network calls.",
            "Does not register scheduler/cron/systemd or create persistent workers.",
            "Does not call Telegram Bot API or any data source.",
            "Does not write production DB.",
            "Secrets are represented only as boolean presence flags inside nested gates.",
        ],
    }


def write_intel_production_readiness_report(
    *,
    collect_evidence_path: str | Path,
    summary_evidence_path: str | Path,
    evidence_path: str | Path,
    now_iso: str,
    scheduled_time: str = "08:30",
    env: dict[str, str] | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build and write a readiness report."""
    report = build_intel_production_readiness_report(
        collect_evidence_path=collect_evidence_path,
        summary_evidence_path=summary_evidence_path,
        now_iso=now_iso,
        scheduled_time=scheduled_time,
        env=env,
        project_root=project_root,
    )
    path = Path(evidence_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
