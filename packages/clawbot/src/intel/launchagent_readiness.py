"""Read-only readiness audit for the next Intel Brief LaunchAgent run.

This module does not start, reload, or modify launchd.  It proves whether the
installed plist will invoke the current production-cycle code with the expected
source set on the next calendar trigger, and compares that with the latest
controlled six-source production-cycle evidence.
"""

from __future__ import annotations

import json
import plistlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.production_cycle import DEFAULT_PRODUCTION_CYCLE_SOURCES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, "not_found"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "invalid_json"
    return (payload, "ok") if isinstance(payload, dict) else (None, "not_object")


def _load_plist(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, "not_found"
    try:
        payload = plistlib.loads(path.read_bytes())
    except Exception:
        return None, "invalid_plist"
    return (payload, "ok") if isinstance(payload, dict) else (None, "not_object")


def _source_args(program_args: list[Any]) -> list[str]:
    sources: list[str] = []
    for index, item in enumerate(program_args):
        if _clean(item) == "--source" and index + 1 < len(program_args):
            sources.append(_clean(program_args[index + 1]))
    return [source for source in sources if source]


def _plist_summary(path: Path, *, expected_sources: list[str]) -> dict[str, Any]:
    payload, state = _load_plist(path)
    base: dict[str, Any] = {"path": str(path), "exists": state != "not_found", "state": state}
    if payload is None:
        return base
    program_args = payload.get("ProgramArguments") if isinstance(payload.get("ProgramArguments"), list) else []
    source_args = _source_args(program_args)
    effective_sources = source_args or expected_sources
    calendar = payload.get("StartCalendarInterval") if isinstance(payload.get("StartCalendarInterval"), dict) else {}
    env = payload.get("EnvironmentVariables") if isinstance(payload.get("EnvironmentVariables"), dict) else {}
    return {
        **base,
        "label": _clean(payload.get("Label")),
        "working_directory": _clean(payload.get("WorkingDirectory")),
        "program_is_production_cycle": any("intel_production_cycle.py" in _clean(arg) for arg in program_args),
        "uses_default_sources": not source_args,
        "source_args": source_args,
        "effective_sources": effective_sources,
        "effective_sources_match_expected": effective_sources == expected_sources,
        "calendar_time": f"{int(calendar.get('Hour', -1)):02d}:{int(calendar.get('Minute', -1)):02d}" if calendar else "",
        "calendar_is_0830": int(calendar.get("Hour", -1)) == 8 and int(calendar.get("Minute", -1)) == 30,
        "run_at_load": bool(payload.get("RunAtLoad")),
        "stdout_path_present": bool(_clean(payload.get("StandardOutPath"))),
        "stderr_path_present": bool(_clean(payload.get("StandardErrorPath"))),
        "private_env_present": bool(_clean(env.get("INTEL_BRIEF_PRIVATE_ENV"))),
        "production_ack_present": bool(_clean(env.get("INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK"))),
    }


def _collect_summary_from_cycle(cycle: dict[str, Any], cycle_path: Path) -> dict[str, Any]:
    steps = cycle.get("steps") if isinstance(cycle.get("steps"), dict) else {}
    collect = steps.get("collect") if isinstance(steps.get("collect"), dict) else {}
    summary = collect.get("summary") if isinstance(collect.get("summary"), dict) else {}
    if summary:
        return summary
    artifacts = cycle.get("artifacts") if isinstance(cycle.get("artifacts"), dict) else {}
    collect_path_text = _clean(artifacts.get("collect_evidence"))
    if not collect_path_text:
        return {}
    collect_path = Path(collect_path_text)
    if not collect_path.is_absolute():
        collect_path = cycle_path.parent / collect_path
    collect_payload, state = _load_json(collect_path)
    if collect_payload is None:
        return {"state": state}
    found = collect_payload.get("summary") if isinstance(collect_payload.get("summary"), dict) else {}
    return found


def _controlled_cycle_summary(path: Path, *, expected_sources: list[str]) -> dict[str, Any]:
    payload, state = _load_json(path)
    base: dict[str, Any] = {"path": str(path), "exists": state != "not_found", "state": state}
    if payload is None:
        return base
    sources = list(payload.get("sources") or [])
    collect_summary = _collect_summary_from_cycle(payload, path)
    success_count = int(collect_summary.get("success", 0) or 0)
    failed_count = int(collect_summary.get("failed", 0) or 0)
    delivery = (payload.get("steps") or {}).get("production_once", {}) if isinstance(payload.get("steps"), dict) else {}
    return {
        **base,
        "status": _clean(payload.get("status")),
        "timestamp": _clean(payload.get("timestamp")),
        "sources": sources,
        "sources_match_expected": sources == expected_sources,
        "collect_summary": collect_summary,
        "collect_success_matches_expected": success_count == len(expected_sources) and failed_count == 0,
        "delivery_status": _clean(delivery.get("status")) if isinstance(delivery, dict) else "",
        "network_calls": int(payload.get("network_calls", 0) or 0),
    }


def _previous_natural_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": "", "provided": False}
    payload, state = _load_json(path)
    base: dict[str, Any] = {"path": str(path), "provided": True, "exists": state != "not_found", "state": state}
    if payload is None:
        return base
    run_evidence = payload.get("run_evidence") if isinstance(payload.get("run_evidence"), dict) else {}
    return {
        **base,
        "status": _clean(payload.get("status")),
        "verification_basis": _clean((payload.get("verification") or {}).get("basis"))
        if isinstance(payload.get("verification"), dict)
        else "",
        "run_sources_known": False,
        "run_timestamp": _clean(run_evidence.get("timestamp")),
        "collect_summary": run_evidence.get("collect_summary", {}),
        "telegram_send_success": bool(run_evidence.get("telegram_send_success")),
    }


def build_launchagent_next_run_readiness(
    *,
    plist_path: str | Path,
    controlled_cycle_path: str | Path,
    previous_natural_audit_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return read-only evidence for the next natural LaunchAgent run."""
    expected_sources = list(DEFAULT_PRODUCTION_CYCLE_SOURCES)
    plist = _plist_summary(Path(plist_path), expected_sources=expected_sources)
    controlled = _controlled_cycle_summary(Path(controlled_cycle_path), expected_sources=expected_sources)
    previous = _previous_natural_summary(Path(previous_natural_audit_path) if previous_natural_audit_path else None)
    ready = (
        plist.get("state") == "ok"
        and plist.get("program_is_production_cycle") is True
        and plist.get("effective_sources_match_expected") is True
        and plist.get("calendar_is_0830") is True
        and plist.get("private_env_present") is True
        and plist.get("production_ack_present") is True
        and controlled.get("status") == "success"
        and controlled.get("sources_match_expected") is True
        and controlled.get("collect_success_matches_expected") is True
    )
    missing = []
    if plist.get("state") != "ok":
        missing.append("plist_not_readable")
    if plist.get("program_is_production_cycle") is not True:
        missing.append("plist_not_pointing_to_production_cycle")
    if plist.get("effective_sources_match_expected") is not True:
        missing.append("plist_effective_sources_not_six_source_default")
    if plist.get("calendar_is_0830") is not True:
        missing.append("calendar_0830_missing")
    if plist.get("private_env_present") is not True:
        missing.append("private_env_missing_in_plist")
    if plist.get("production_ack_present") is not True:
        missing.append("production_ack_missing_in_plist")
    if controlled.get("status") != "success":
        missing.append("controlled_cycle_not_success")
    if controlled.get("sources_match_expected") is not True or controlled.get("collect_success_matches_expected") is not True:
        missing.append("controlled_cycle_not_six_source_success")
    return {
        "timestamp": _now_iso(),
        "phase": "BD-launchagent-next-run-six-source-readiness",
        "scope": "read_only_proof_next_calendar_run_uses_current_six_source_defaults",
        "status": "ready" if ready else "not_ready",
        "expected_sources": expected_sources,
        "missing": missing,
        "plist": plist,
        "controlled_cycle": controlled,
        "previous_natural_audit": previous,
        "network_calls": 0,
        "limits": [
            "Read-only audit; does not run launchctl kickstart/bootstrap/bootout.",
            "Does not modify plist, private env, production DB, VPS, remote worker, payment/marketplace, scraper, or Telegram state.",
            "This proves next-run readiness from installed plist plus controlled six-source evidence; it is not itself a natural calendar trigger.",
        ],
    }
