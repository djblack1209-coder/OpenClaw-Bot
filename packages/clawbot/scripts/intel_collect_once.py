"""Intel Brief one-shot multi-source collector.

This controller-side script orchestrates already verified worker sources through
`intel_worker_remote_run.py`, aggregates their evidence, and writes one collection
report. It does not register a scheduler, start services, or store secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.intel_worker_remote_run import RemoteRunResult, run_remote_worker_request  # noqa: E402


@dataclass(frozen=True)
class WorkerProfile:
    source: str
    ssh_target: str
    worker_label: str
    limit: int = 1
    ssh_args: list[str] = field(default_factory=list)
    pip_packages: list[str] = field(default_factory=list)
    fallback_profiles: tuple[WorkerProfile, ...] = field(default_factory=tuple)


def default_worker_profiles() -> dict[str, WorkerProfile]:
    """Return non-secret profiles for sources already verified by Phase E evidence."""
    oracle_arm1_fallback = WorkerProfile(
        source="senate_trading",
        ssh_target="oracle-arm1",
        worker_label="oracle-arm1-overseas-fallback",
    )
    github_oracle_arm1_fallback = WorkerProfile(
        source="github_trending",
        ssh_target="oracle-arm1",
        worker_label="oracle-arm1-overseas-fallback",
        limit=3,
    )
    ai_oracle_arm1_fallback = WorkerProfile(
        source="ai_model_updates",
        ssh_target="oracle-arm1",
        worker_label="oracle-arm1-overseas-fallback",
        limit=6,
    )
    institutional_oracle_arm1_fallback = WorkerProfile(
        source="institutional_13f",
        ssh_target="oracle-arm1",
        worker_label="oracle-arm1-overseas-fallback",
        limit=10,
    )
    weather_oracle_arm1_fallback = WorkerProfile(
        source="weather",
        ssh_target="oracle-arm1",
        worker_label="oracle-arm1-overseas-fallback",
        limit=6,
    )
    return {
        "senate_trading": WorkerProfile(
            source="senate_trading",
            ssh_target="oracle-sg-west",
            worker_label="oracle-sg-west-preferred-overseas",
            ssh_args=["-o", "BatchMode=yes", "-o", "ConnectTimeout=12"],
            fallback_profiles=(oracle_arm1_fallback,),
        ),
        "akshare": WorkerProfile(
            source="akshare",
            ssh_target="root@160.202.231.11",
            worker_label="yanhuoyun-domestic",
            ssh_args=[
                "-i",
                "/Users/blackdj/.ssh/jmgo_iptv_ed25519",
                "-p",
                "21433",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=12",
            ],
            pip_packages=["-i", "https://pypi.tuna.tsinghua.edu.cn/simple", "akshare==1.18.64"],
        ),
        "github_trending": WorkerProfile(
            source="github_trending",
            ssh_target="oracle-sg-west",
            worker_label="oracle-sg-west-preferred-overseas",
            limit=3,
            ssh_args=["-o", "BatchMode=yes", "-o", "ConnectTimeout=12"],
            fallback_profiles=(github_oracle_arm1_fallback,),
        ),
        "ai_model_updates": WorkerProfile(
            source="ai_model_updates",
            ssh_target="oracle-sg-west",
            worker_label="oracle-sg-west-preferred-overseas",
            limit=6,
            ssh_args=["-o", "BatchMode=yes", "-o", "ConnectTimeout=12"],
            fallback_profiles=(ai_oracle_arm1_fallback,),
        ),
        "institutional_13f": WorkerProfile(
            source="institutional_13f",
            ssh_target="oracle-sg-west",
            worker_label="oracle-sg-west-preferred-overseas",
            limit=10,
            ssh_args=["-o", "BatchMode=yes", "-o", "ConnectTimeout=12"],
            fallback_profiles=(institutional_oracle_arm1_fallback,),
        ),
        "weather": WorkerProfile(
            source="weather",
            ssh_target="oracle-sg-west",
            worker_label="oracle-sg-west-preferred-overseas",
            limit=6,
            ssh_args=["-o", "BatchMode=yes", "-o", "ConnectTimeout=12"],
            fallback_profiles=(weather_oracle_arm1_fallback,),
        ),
    }


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # evidence aggregation should retain child failure
        return {"status": "failed", "error": f"cannot_read_child_evidence: {exc}"}


def _child_path_for_attempt(evidence_root: Path, *, stamp: str, source: str, attempt_index: int) -> Path:
    if attempt_index == 0:
        return evidence_root / f"{stamp}-{source}.json"
    return evidence_root / f"{stamp}-{source}-fallback{attempt_index}.json"


def _run_profile_attempt(
    *,
    source: str,
    profile: WorkerProfile,
    role: str,
    child_path: Path,
    stamp: str,
    remote_run: Callable[..., RemoteRunResult],
) -> dict[str, Any]:
    result = remote_run(
        source=source,
        ssh_target=profile.ssh_target,
        worker_label=profile.worker_label,
        output_path=child_path,
        request_id=f"collect-{stamp}-{source}-{role}",
        limit=profile.limit,
        ssh_args=profile.ssh_args,
        pip_packages=profile.pip_packages,
    )
    child = _load_json(result.evidence_path)
    return {
        "role": role,
        "source": source,
        "status": result.status,
        "worker": profile.worker_label,
        "ssh_target": profile.ssh_target,
        "evidence_path": result.evidence_path,
        "cleanup": result.cleanup,
        "cleanup_verify": result.cleanup_verify,
        "remote_returncode": child.get("remote_returncode", ""),
        "stderr_excerpt": child.get("stderr_excerpt", ""),
        "response": child.get("response", {}),
        "source_health": child.get("source_health", {}),
    }


def collect_once(
    *,
    sources: list[str],
    output_path: str | Path,
    evidence_dir: str | Path,
    profiles: dict[str, WorkerProfile] | None = None,
    remote_run: Callable[..., RemoteRunResult] = run_remote_worker_request,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Run multiple verified sources once and aggregate child evidence."""
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017 - Python 3.10 worker compatibility
    profiles = profiles or default_worker_profiles()
    evidence_root = Path(evidence_dir)
    evidence_root.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []

    for source in sources:
        profile = profiles.get(source)
        if profile is None:
            runs.append(
                {
                    "source": source,
                    "status": "failed",
                    "error": f"unsupported_collect_source: {source}",
                    "cleanup": "not_applicable",
                    "cleanup_verify": "not_applicable",
                }
            )
            continue
        attempts: list[dict[str, Any]] = []
        attempt_profiles = (profile, *profile.fallback_profiles)
        final_attempt: dict[str, Any] | None = None
        for attempt_index, attempt_profile in enumerate(attempt_profiles):
            role = "primary" if attempt_index == 0 else f"fallback_{attempt_index}"
            attempt = _run_profile_attempt(
                source=source,
                profile=attempt_profile,
                role=role,
                child_path=_child_path_for_attempt(evidence_root, stamp=stamp, source=source, attempt_index=attempt_index),
                stamp=stamp,
                remote_run=remote_run,
            )
            attempts.append(attempt)
            if attempt["status"] == "success":
                final_attempt = attempt
                break

        final = final_attempt or attempts[-1]
        runs.append(
            {
                "source": source,
                "status": final["status"],
                "worker": final["worker"],
                "evidence_path": final["evidence_path"],
                "cleanup": final["cleanup"],
                "cleanup_verify": final["cleanup_verify"],
                "response": final["response"],
                "source_health": final["source_health"],
                "attempts": attempts,
                "fallback": {
                    "used": final["role"] != "primary",
                    "primary_worker": profile.worker_label,
                    "final_worker": final["worker"],
                    "attempted_workers": [attempt["worker"] for attempt in attempts],
                },
            }
        )

    success = sum(1 for run in runs if run.get("status") == "success")
    failed = len(runs) - success
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Python 3.10 worker compatibility
        "phase": "F-pre",
        "scope": "intel_collect_once_multi_source",
        "status": "success" if failed == 0 else "failed",
        "sources": sources,
        "summary": {"success": success, "failed": failed},
        "runs": runs,
        "limits": [
            "One-shot collection only; no scheduler registration or service deployment.",
            "Only sources present in default_worker_profiles are eligible.",
            "Child remote runners use temporary /tmp staging and cleanup.",
        ],
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief verified sources once and aggregate evidence")
    parser.add_argument("--source", action="append", dest="sources", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args(argv)
    result = collect_once(sources=args.sources, output_path=args.output, evidence_dir=args.evidence_dir)
    print(json.dumps({"status": result["status"], "summary": result["summary"], "output": args.output}, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
