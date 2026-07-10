"""One-shot Intel Brief production runner.

This is the callable target for a future scheduler. It evaluates the same
production safety gate, writes evidence, and only calls the Telegram delivery
runner when all gates are present.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.execution._utils import parse_hhmm
from src.execution.intel_brief import build_intel_brief_scheduler_gate
from src.intel.private_env import load_private_env_file
from src.intel.telegram_delivery import build_telegram_summary_delivery_probe

DeliveryRunner = Callable[..., dict[str, Any]]
SubscriptionDeliveryRunner = Callable[..., dict[str, Any]]


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    return parsed


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


def run_intel_production_once(
    *,
    summary_evidence_path: str | Path,
    evidence_path: str | Path,
    now: datetime | None = None,
    scheduled_time: str = "08:30",
    env: dict[str, str] | None = None,
    project_root: str | Path | None = None,
    delivery_runner: DeliveryRunner | None = None,
    subscription_delivery_runner: SubscriptionDeliveryRunner | None = None,
) -> dict[str, Any]:
    """Run one production delivery if and only if the hard gate is ready."""
    now_value = now or _now()
    root = Path(project_root) if project_root is not None else Path.cwd()
    env_map = _merge_private_env(dict(os.environ if env is None else env), root)
    env_map.update(
        {
            "INTEL_BRIEF_ENABLED": env_map.get("INTEL_BRIEF_ENABLED", "true"),
            "INTEL_BRIEF_MODE": "production",
            "INTEL_BRIEF_SUMMARY_EVIDENCE": str(summary_evidence_path),
        }
    )
    gate = build_intel_brief_scheduler_gate(
        now=now_value,
        scheduled_time=parse_hhmm(scheduled_time, (8, 30)),
        env=env_map,
        project_root=root,
    )
    delivery: dict[str, Any] | None = None
    subscription_delivery_gate: dict[str, Any] | None = None
    network_calls = 0
    status = "blocked"
    delivery_mode = "subscription_filtered" if _truthy(env_map.get("INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED")) else "fixed_chat"
    if gate.get("should_run"):
        if delivery_mode == "subscription_filtered":
            db_text = str(env_map.get("INTEL_BRIEF_DB_PATH") or "").strip()
            token_present = bool(str(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN") or "").strip())
            missing = []
            if not token_present:
                missing.append("telegram_bot_token_missing")
            if not db_text:
                missing.append("intel_brief_db_path_missing")
            db_path = Path(db_text) if db_text else Path()
            if db_text and not db_path.is_absolute():
                db_path = root / db_path
            db_exists = db_path.exists() if db_text else False
            if db_text and not db_exists:
                missing.append("intel_brief_db_path_not_found")
            subscription_delivery_gate = {
                "ready": not missing,
                "status": "ready" if not missing else "blocked",
                "missing_gates": missing,
                "redacted_env": {
                    "INTEL_BRIEF_SUBSCRIPTION_DELIVERY_ENABLED": True,
                    "INTEL_BRIEF_DB_PATH": bool(db_text),
                    "INTEL_BRIEF_DB_PATH_EXISTS": db_exists,
                    "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": token_present,
                },
            }
            if missing:
                status = "blocked"
            else:
                if subscription_delivery_runner is None:
                    from src.intel.subscription_delivery import deliver_summary_to_eligible_subscribers
                    from src.intel.telegram_delivery import TelegramBotApiSender

                    sender = TelegramBotApiSender(token=str(env_map.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN") or ""))
                    delivery = deliver_summary_to_eligible_subscribers(
                        db_path=db_path,
                        summary_evidence_path=summary_evidence_path,
                        sender=sender,
                        now=now_value.isoformat(),
                    )
                else:
                    delivery = subscription_delivery_runner(
                        db_path=db_path,
                        summary_evidence_path=summary_evidence_path,
                        now=now_value.isoformat(),
                    )
                network_calls = int(delivery.get("network_calls") or 0)
                status = "success" if delivery.get("status") == "success" else "failed"
        else:
            runner = delivery_runner or build_telegram_summary_delivery_probe
            delivery = runner(
                summary_evidence_path=summary_evidence_path,
                evidence_path=evidence_path,
                env=env_map,
                allow_real_network=True,
            )
            network_calls = int(delivery.get("network_calls") or 0)
            status = "success" if delivery.get("status") == "success" else "failed"

    payload = {
        "timestamp": _now().isoformat(),
        "phase": "Q-production-once",
        "scope": "intel_brief_one_shot_production_delivery_runner",
        "status": status,
        "gate": gate,
        "summary_evidence": str(summary_evidence_path),
        "delivery_mode": delivery_mode,
        "subscription_delivery_gate": subscription_delivery_gate,
        "delivery": delivery,
        "network_calls": network_calls,
        "limits": [
            "Production-once runner; no scheduler installation or persistent worker creation.",
            "No Telegram call unless production gate is ready.",
            "Secrets are represented only by boolean presence flags in gate/delivery evidence.",
        ],
    }
    output = Path(evidence_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def parse_now(value: str | None) -> datetime | None:
    return _parse_datetime(value) if value else None
