"""Post-run audit for the Intel Brief LaunchAgent.

The audit is read-only: it inspects launchctl text, run evidence, and log files;
it never starts/kickstarts the LaunchAgent and never calls Telegram or workers.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, "not_found"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(payload, dict):
        return None, "not_object"
    return payload, "ok"


def _tail(path: Path, limit: int = 1200) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "bytes": 0, "tail": ""}
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"exists": True, "bytes": path.stat().st_size, "tail": text[-limit:]}


def _parse_runs(launchctl_text: str) -> int | None:
    match = re.search(r"runs = (\d+)", launchctl_text)
    return int(match.group(1)) if match else None


def _parse_last_exit_code(launchctl_text: str) -> str:
    match = re.search(r"last exit code = ([^\n]+)", launchctl_text)
    return match.group(1).strip() if match else ""


def _stdout_success(stdout: Path) -> bool:
    if not stdout.exists():
        return False
    text = stdout.read_text(encoding="utf-8", errors="replace")
    return '"status": "success"' in text or '"status":"success"' in text


def _clean_list(values: list[Any] | tuple[Any, ...] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _summary_count(summary: dict[str, Any], key: str) -> int | None:
    value = summary.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_list(payload: dict[str, Any], collect: dict[str, Any]) -> list[str]:
    top_sources = payload.get("sources")
    if isinstance(top_sources, list):
        return _clean_list(top_sources)
    collect_sources = collect.get("sources")
    if isinstance(collect_sources, list):
        return _clean_list(collect_sources)
    runs = collect.get("runs")
    if isinstance(runs, list):
        return _clean_list([run.get("source") for run in runs if isinstance(run, dict)])
    return []


def _successful_run_sources(collect: dict[str, Any]) -> list[str]:
    runs = collect.get("runs")
    if not isinstance(runs, list):
        return []
    return _clean_list(
        [
            run.get("source")
            for run in runs
            if isinstance(run, dict) and str(run.get("status") or "").strip() == "success"
        ]
    )


def _run_evidence_summary(path: Path, *, expected_sources: list[str] | None = None) -> dict[str, Any]:
    payload, state = _load_json(path)
    base: dict[str, Any] = {"path": str(path), "exists": state != "not_found", "state": state}
    if payload is None:
        return base
    collect = payload.get("steps", {}).get("collect", {}) if isinstance(payload.get("steps"), dict) else {}
    production_once = payload.get("steps", {}).get("production_once", {}) if isinstance(payload.get("steps"), dict) else {}
    delivery = production_once.get("delivery", {}) if isinstance(production_once, dict) else {}
    send = delivery.get("send_result", {}) if isinstance(delivery, dict) else {}
    delivery_summary = delivery.get("summary", {}) if isinstance(delivery, dict) else {}
    collect_summary = collect.get("summary", {}) if isinstance(collect, dict) else {}
    sources = _source_list(payload, collect if isinstance(collect, dict) else {})
    expected = _clean_list(expected_sources)
    successful_sources = _successful_run_sources(collect if isinstance(collect, dict) else {})
    missing_expected = [source for source in expected if source not in sources]
    unexpected = [source for source in sources if source not in expected] if expected else []
    failed_sources = [
        str(run.get("source") or "").strip()
        for run in (collect.get("runs") if isinstance(collect, dict) else []) or []
        if isinstance(run, dict)
        and str(run.get("source") or "").strip()
        and str(run.get("status") or "").strip() != "success"
    ]
    sources_match_expected = bool(expected) and sources == expected
    collect_success_matches_expected = True
    if expected:
        collect_success_matches_expected = (
            int(collect_summary.get("success", 0) or 0) == len(expected)
            and int(collect_summary.get("failed", 0) or 0) == 0
            and not failed_sources
            and all(source in successful_sources for source in expected)
        )
    delivery_status = str(delivery.get("status") or "") if isinstance(delivery, dict) else ""
    telegram_send_success = bool(send.get("success")) if isinstance(send, dict) else False
    delivery_counts = {
        key: _summary_count(delivery_summary, key)
        for key in ("eligible", "sent", "failed", "deliveries_count")
    } if isinstance(delivery_summary, dict) else {}
    zero_recipient_delivery_success = (
        delivery_status == "success"
        and isinstance(delivery_summary, dict)
        and _summary_count(delivery_summary, "eligible") == 0
        and _summary_count(delivery_summary, "sent") == 0
        and _summary_count(delivery_summary, "failed") == 0
    )
    return {
        **base,
        "status": str(payload.get("status") or ""),
        "timestamp": str(payload.get("timestamp") or ""),
        "network_calls": int(payload.get("network_calls") or 0),
        "sources": sources,
        "expected_sources": expected,
        "sources_match_expected": sources_match_expected if expected else None,
        "collect_success_matches_expected": collect_success_matches_expected if expected else None,
        "missing_expected_sources": missing_expected,
        "unexpected_sources": unexpected,
        "failed_sources": failed_sources,
        "collect_summary": collect_summary,
        "production_once_status": str(production_once.get("status") or "") if isinstance(production_once, dict) else "",
        "delivery_status": delivery_status,
        "delivery_summary": delivery_counts,
        "telegram_send_success": telegram_send_success,
        "delivery_success": telegram_send_success or zero_recipient_delivery_success,
        "zero_recipient_delivery_success": zero_recipient_delivery_success,
        "message_id_present": bool(send.get("message_id")) if isinstance(send, dict) else False,
    }


def build_launchagent_post_run_audit(
    *,
    label: str,
    run_evidence_path: str | Path,
    stdout_path: str | Path,
    stderr_path: str | Path,
    launchctl_text: str,
    expected_sources: list[str] | tuple[str, ...] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a read-only post-run audit from launchctl text and artifacts."""
    run_path = Path(run_evidence_path)
    stdout = Path(stdout_path)
    stderr = Path(stderr_path)
    expected = _clean_list(list(expected_sources or []))
    run_summary = _run_evidence_summary(run_path, expected_sources=expected)
    runs = _parse_runs(launchctl_text)
    last_exit_code = _parse_last_exit_code(launchctl_text)
    artifact_success = run_summary.get("status") == "success" and bool(run_summary.get("delivery_success"))
    artifact_source_success = not expected or (
        bool(run_summary.get("sources_match_expected"))
        and bool(run_summary.get("collect_success_matches_expected"))
    )
    launchctl_counter_success = runs is not None and runs > 0 and last_exit_code == "0"
    loaded_calendar_job = (
        "intel_production_cycle.py" in launchctl_text
        and "com.apple.launchd.calendarinterval" in launchctl_text
        and "state = not running" in launchctl_text
    )
    stdout_success = _stdout_success(stdout)
    artifact_verified_despite_counter = (
        artifact_success
        and artifact_source_success
        and stdout_success
        and loaded_calendar_job
        and (runs in (0, None) or last_exit_code in {"", "(never exited)"})
    )
    success = artifact_success and artifact_source_success and (launchctl_counter_success or artifact_verified_despite_counter)
    status = "verified_success" if success else "pending_calendar_trigger"
    if run_summary.get("exists") and run_summary.get("status") not in {"", "success"}:
        status = "failed_or_incomplete"
    if run_summary.get("exists") and run_summary.get("status") == "success" and not artifact_source_success:
        status = "failed_or_incomplete"
    return {
        "timestamp": (now or _now()).isoformat(),
        "phase": "U-launchagent-post-run-audit",
        "scope": "intel_brief_launchagent_calendar_trigger_post_run_audit",
        "status": status,
        "label": label,
        "launchctl": {
            "runs": runs,
            "last_exit_code": last_exit_code,
            "state_not_running": "state = not running" in launchctl_text,
            "program_is_production_cycle": "intel_production_cycle.py" in launchctl_text,
            "calendar_interval_present": "com.apple.launchd.calendarinterval" in launchctl_text,
            "counter_success": launchctl_counter_success,
            "counter_mismatch": bool(artifact_verified_despite_counter and not launchctl_counter_success),
        },
        "run_evidence": run_summary,
        "verification": {
            "artifact_success": bool(artifact_success),
            "artifact_source_success": bool(artifact_source_success),
            "stdout_success": bool(stdout_success),
            "launchctl_counter_success": bool(launchctl_counter_success),
            "artifact_verified_despite_launchctl_counter": bool(artifact_verified_despite_counter),
            "expected_sources_checked": bool(expected),
            "basis": "launchctl_counter_and_artifact" if launchctl_counter_success else (
                "artifact_and_standard_output" if artifact_verified_despite_counter else "not_verified"
            ),
        },
        "logs": {"stdout": _tail(stdout), "stderr": _tail(stderr)},
        "network_calls": 0,
        "limits": [
            "Read-only audit; does not call launchctl kickstart/bootstrap/bootout.",
            "Does not call Telegram, remote workers, LLM providers, or production DB.",
            "Token/chat id values are not read or printed.",
        ],
    }


def collect_launchctl_text(label: str, *, uid: str | None = None) -> tuple[str, int]:
    uid_text = uid or subprocess.check_output(["id", "-u"], text=True).strip()
    proc = subprocess.run(
        ["launchctl", "print", f"gui/{uid_text}/{label}"],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout + proc.stderr, proc.returncode
