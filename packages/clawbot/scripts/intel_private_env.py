"""Create/audit the private Intel Brief runtime env file.

This script writes secrets only to a gitignored private env path and writes a
separate redacted evidence file. It does not enable schedulers or send messages.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.private_env import (  # noqa: E402
    build_private_env_audit,
    default_private_env_path,
    write_private_env_file,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: object) -> str:
    return str(value or "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write or audit Intel Brief private env")
    parser.add_argument("--env-path", default=str(default_private_env_path(Path.cwd())))
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--worker-placement-confirmed", action="store_true")
    args = parser.parse_args(argv)

    env_path = Path(args.env_path)
    evidence_path = Path(args.evidence)
    if args.audit_only:
        report = build_private_env_audit(env_path)
        action = "audit"
    else:
        values = {
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": _clean(os.environ.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN")),
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": _clean(os.environ.get("INTEL_BRIEF_TELEGRAM_CHAT_ID")),
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": _clean(os.environ.get("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK")),
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true" if args.worker_placement_confirmed else _clean(
                os.environ.get("INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED")
            ),
        }
        report = write_private_env_file(env_path, values=values)
        action = "write"

    payload = {
        "timestamp": _now_iso(),
        "phase": "P-private-env",
        "scope": "intel_brief_private_env_write_or_audit",
        "status": report["status"],
        "action": action,
        "private_env": report,
        "network_calls": 0,
        "limits": [
            "Evidence is redacted and does not include token or chat id values.",
            "This script does not enable production scheduler/cron/systemd.",
            "Production ack is intentionally not written by this helper.",
        ],
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "action": action,
                "env_path": str(env_path),
                "evidence": str(evidence_path),
                "missing_keys": report.get("missing_keys", []),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
