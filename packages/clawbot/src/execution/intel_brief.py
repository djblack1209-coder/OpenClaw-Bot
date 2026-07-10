"""Intel Brief execution scene.

This module is intentionally plan-only for the current phase: it resolves which
worker should run each source, but does not start remote execution, mutate
scheduler configuration, or push messages. Production dispatch will be layered on
top after target-worker evidence exists for each source.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from src.intel.runtime_policy import resolve_runtime_policy
from src.intel.telegram_delivery import TELEGRAM_SANDBOX_ACK_VALUE
from src.intel.worker_contract import build_worker_request

DEFAULT_INTEL_BRIEF_SOURCES = (
    "github_trending",
    "senate_trading",
    "sec_edgar",
    "akshare",
    "weibo",
    "xiaohongshu",
    "openai_rss",
    "anthropic_news",
)

PRODUCTION_ACK_VALUE = "I_UNDERSTAND_REAL_DELIVERY"
DEFAULT_INTEL_BRIEF_EVIDENCE_DIR = "data/intel_evidence/phasej"


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _hhmm_text(scheduled_time: tuple[int, int]) -> str:
    return f"{int(scheduled_time[0]):02d}:{int(scheduled_time[1]):02d}"


def _redacted_env(env: dict[str, str]) -> dict[str, object]:
    return {
        "INTEL_BRIEF_ENABLED": _truthy(env.get("INTEL_BRIEF_ENABLED")),
        "INTEL_BRIEF_MODE": str(env.get("INTEL_BRIEF_MODE") or "sandbox").strip().lower() or "sandbox",
        "INTEL_BRIEF_COLLECT_EVIDENCE": bool(str(env.get("INTEL_BRIEF_COLLECT_EVIDENCE") or "").strip()),
        "INTEL_BRIEF_SUMMARY_EVIDENCE": bool(str(env.get("INTEL_BRIEF_SUMMARY_EVIDENCE") or "").strip()),
        "INTEL_BRIEF_EVIDENCE_DIR": bool(str(env.get("INTEL_BRIEF_EVIDENCE_DIR") or "").strip()),
        "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": bool(str(env.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN") or "").strip()),
        "INTEL_BRIEF_TELEGRAM_CHAT_ID": bool(str(env.get("INTEL_BRIEF_TELEGRAM_CHAT_ID") or "").strip()),
        "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": (
            str(env.get("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK") or "").strip() == TELEGRAM_SANDBOX_ACK_VALUE
        ),
        "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": _truthy(
            env.get("INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED")
        ),
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

    loaded = load_private_env_file(private_env_path)
    return {**loaded, **env, "INTEL_BRIEF_PRIVATE_ENV": str(private_env_path)}


def build_intel_brief_scheduler_gate(
    *,
    now: datetime,
    scheduled_time: tuple[int, int],
    env: dict[str, str] | None = None,
    last_run_date: str = "",
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build a redacted scheduler safety decision for Intel Brief.

    This gate intentionally defaults to sandbox mode and blocks production mode
    until every explicit production guard is present. It never returns secret
    values; token/chat fields are represented as booleans only.
    """
    root = Path(project_root) if project_root is not None else _project_root()
    env_map = _merge_private_env(dict(os.environ if env is None else env), root)
    mode = str(env_map.get("INTEL_BRIEF_MODE") or "sandbox").strip().lower() or "sandbox"
    run_date = now.strftime("%Y-%m-%d")
    scheduled_label = _hhmm_text(scheduled_time)
    redacted = _redacted_env(env_map)
    base: dict[str, Any] = {
        "enabled": _truthy(env_map.get("INTEL_BRIEF_ENABLED")),
        "mode": mode,
        "should_run": False,
        "reason": "",
        "now_iso": now.isoformat(),
        "run_date": run_date,
        "scheduled_time": scheduled_label,
        "last_run_date": str(last_run_date or ""),
        "missing_gates": [],
        "redacted_env": redacted,
    }

    if not base["enabled"]:
        return {**base, "reason": "disabled"}
    if str(last_run_date or "").strip() == run_date:
        return {**base, "reason": "already_ran_today"}
    if (now.hour, now.minute) < (int(scheduled_time[0]), int(scheduled_time[1])):
        return {**base, "reason": "before_scheduled_time"}
    if mode not in {"sandbox", "production"}:
        return {**base, "reason": "blocked_by_hard_gate", "missing_gates": ["invalid_mode"]}

    if mode == "production":
        missing = []
        if not redacted["INTEL_BRIEF_TELEGRAM_BOT_TOKEN"]:
            missing.append("telegram_bot_token_missing")
        if not redacted["INTEL_BRIEF_TELEGRAM_CHAT_ID"]:
            missing.append("telegram_chat_id_missing")
        if not redacted["INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED"]:
            missing.append("worker_placement_not_confirmed")
        if env_map.get("INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK") != PRODUCTION_ACK_VALUE:
            missing.append("production_ack_missing")
        if env_map.get("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK") != TELEGRAM_SANDBOX_ACK_VALUE:
            missing.append("sandbox_send_ack_missing")
        summary_text = str(env_map.get("INTEL_BRIEF_SUMMARY_EVIDENCE") or "").strip()
        summary_path = Path(summary_text) if summary_text else Path()
        if summary_path and not summary_path.is_absolute():
            summary_path = root / summary_path
        if not summary_text:
            missing.append("summary_evidence_missing")
        elif not summary_path.exists():
            missing.append("summary_evidence_not_found")
        if missing:
            return {**base, "reason": "blocked_by_hard_gate", "missing_gates": missing}
        evidence_dir_text = str(env_map.get("INTEL_BRIEF_EVIDENCE_DIR") or DEFAULT_INTEL_BRIEF_EVIDENCE_DIR).strip()
        evidence_dir = Path(evidence_dir_text)
        if not evidence_dir.is_absolute():
            evidence_dir = root / evidence_dir
        return {
            **base,
            "should_run": True,
            "reason": "production_ready",
            "summary_evidence": str(summary_path),
            "evidence_dir": str(evidence_dir),
        }

    collect_text = str(env_map.get("INTEL_BRIEF_COLLECT_EVIDENCE") or "").strip()
    collect_path = Path(collect_text) if collect_text else Path()
    if collect_path and not collect_path.is_absolute():
        collect_path = root / collect_path
    missing = []
    if not collect_text:
        missing.append("collect_evidence_missing")
    elif not collect_path.exists():
        missing.append("collect_evidence_not_found")
    if missing:
        return {
            **base,
            "reason": "blocked_by_hard_gate",
            "missing_gates": missing,
            "collect_evidence": collect_text,
        }

    evidence_dir_text = str(env_map.get("INTEL_BRIEF_EVIDENCE_DIR") or DEFAULT_INTEL_BRIEF_EVIDENCE_DIR).strip()
    evidence_dir = Path(evidence_dir_text)
    if not evidence_dir.is_absolute():
        evidence_dir = root / evidence_dir
    return {
        **base,
        "should_run": True,
        "reason": "sandbox_ready",
        "collect_evidence": str(collect_path),
        "evidence_dir": str(evidence_dir),
    }


def dispatch_source_job(
    source_name: str,
    *,
    limit: int = 20,
    request_id: str | None = None,
) -> dict[str, object]:
    """Build the dispatch plan for one source without executing it remotely."""
    policy = resolve_runtime_policy(source_name)
    worker_request = build_worker_request(
        policy.source_name,
        limit=limit,
        request_id=request_id,
    ).to_public_dict()
    return {
        "source": policy.source_name,
        "worker": policy.preferred_worker,
        "region_hint": policy.region_hint,
        "reason": policy.reason,
        "status": "planned",
        "dispatch_mode": "plan_only",
        "worker_request": worker_request,
    }


def build_intel_brief_run_plan(sources: Iterable[str] | None = None) -> dict[str, object]:
    """Build a multi-source Intel Brief run plan.

    The return value is safe to log as deployment evidence because it contains no
    secrets and does not include any remote command or credential material.
    """
    selected_sources = list(sources or DEFAULT_INTEL_BRIEF_SOURCES)
    jobs = [dispatch_source_job(source) for source in selected_sources]
    worker_counts = dict(sorted(Counter(job["worker"] for job in jobs).items()))
    return {
        "dispatch_mode": "plan_only",
        "jobs": jobs,
        "worker_counts": worker_counts,
    }
