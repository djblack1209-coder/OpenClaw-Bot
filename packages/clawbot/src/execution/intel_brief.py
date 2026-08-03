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

from src.intel.runtime_policy import (
    DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE,
    DEFAULT_INTEL_BRIEF_WINDOW_END,
    IntelBriefRuntimePolicyError,
    evaluate_intel_brief_delivery_window,
    resolve_runtime_policy,
)
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


def _parse_hhmm_text(value: object, *, default: tuple[int, int]) -> tuple[int, int]:
    """解析调度窗口配置，非法值由安全门显式阻断。"""
    text = str(value or "").strip()
    if not text:
        return default
    parts = text.split(":")
    if len(parts) != 2:
        raise IntelBriefRuntimePolicyError("invalid_scheduler_window", "window end must use HH:MM")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise IntelBriefRuntimePolicyError("invalid_scheduler_window", "window end must use HH:MM") from exc


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
        "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": _truthy(env.get("INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED")),
        "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK": bool(
            str(env.get("INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK") or "").strip()
        ),
        "INTEL_BRIEF_SCHEDULER_TIMEZONE": (
            str(env.get("INTEL_BRIEF_SCHEDULER_TIMEZONE") or DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE).strip()
            or DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE
        ),
        "INTEL_BRIEF_SCHEDULER_WINDOW_END": (
            str(env.get("INTEL_BRIEF_SCHEDULER_WINDOW_END") or _hhmm_text(DEFAULT_INTEL_BRIEF_WINDOW_END)).strip()
            or _hhmm_text(DEFAULT_INTEL_BRIEF_WINDOW_END)
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
    """构建不含敏感值的每日资讯调度安全决策。

    安全门默认采用沙箱模式；只有显式生产条件齐全时才允许生产投递。
    网络条件判定前先按业务时区校验投递窗口，Token 和会话字段只返回布尔状态。
    """
    root = Path(project_root) if project_root is not None else _project_root()
    env_map = _merge_private_env(dict(os.environ if env is None else env), root)
    mode = str(env_map.get("INTEL_BRIEF_MODE") or "sandbox").strip().lower() or "sandbox"
    scheduled_label = _hhmm_text(scheduled_time)
    scheduler_timezone = (
        str(env_map.get("INTEL_BRIEF_SCHEDULER_TIMEZONE") or DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE).strip()
        or DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE
    )
    window_error = ""
    window_decision = None
    try:
        window_end = _parse_hhmm_text(
            env_map.get("INTEL_BRIEF_SCHEDULER_WINDOW_END"),
            default=DEFAULT_INTEL_BRIEF_WINDOW_END,
        )
        window_decision = evaluate_intel_brief_delivery_window(
            now=now,
            scheduler_timezone=scheduler_timezone,
            window_start=scheduled_time,
            window_end=window_end,
        )
    except IntelBriefRuntimePolicyError as exc:
        window_error = exc.code
        window_end = DEFAULT_INTEL_BRIEF_WINDOW_END

    run_date = window_decision.local_now.strftime("%Y-%m-%d") if window_decision else now.strftime("%Y-%m-%d")
    redacted = _redacted_env(env_map)
    base: dict[str, Any] = {
        "enabled": _truthy(env_map.get("INTEL_BRIEF_ENABLED")),
        "mode": mode,
        "should_run": False,
        "reason": "",
        "now_iso": now.isoformat(),
        "scheduler_now_iso": window_decision.local_now.isoformat() if window_decision is not None else "",
        "scheduler_timezone": scheduler_timezone,
        "run_date": run_date,
        "scheduled_time": scheduled_label,
        "window_start": scheduled_label,
        "window_end": _hhmm_text(window_end),
        "window_status": window_decision.reason if window_decision is not None else "invalid_configuration",
        "last_run_date": str(last_run_date or ""),
        "missing_gates": [],
        "redacted_env": redacted,
    }

    if not base["enabled"]:
        return {**base, "reason": "disabled"}
    if window_error:
        return {**base, "reason": "blocked_by_hard_gate", "missing_gates": [window_error]}
    if str(last_run_date or "").strip() == run_date:
        return {**base, "reason": "already_ran_today"}
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
        if window_decision is not None and not window_decision.should_run:
            return {**base, "reason": window_decision.reason}
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
    if window_decision is not None and not window_decision.should_run:
        return {**base, "reason": window_decision.reason, "collect_evidence": str(collect_path)}

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
