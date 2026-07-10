"""Run Intel Brief subscription lifecycle maintenance safely.

Default mode is read-only.  Expiry mutation and Telegram reminders require
explicit command flags plus environment acknowledgements.  Evidence is redacted
and never includes raw Telegram token/chat/user ids.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

CLAWBOT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CLAWBOT_ROOT.parents[1]
if str(CLAWBOT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLAWBOT_ROOT))

from src.intel.private_env import default_private_env_path  # noqa: E402
from src.intel.subscription_lifecycle import (  # noqa: E402
    LIFECYCLE_APPLY_ACK_VALUE,
    run_subscription_lifecycle_maintenance,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _default_now() -> str:
    return _now_iso()


def _default_env_path() -> str:
    path = default_private_env_path(PROJECT_ROOT)
    return str(path) if path.exists() else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief subscription lifecycle maintenance")
    parser.add_argument("--db", default="", help="SQLite DB path. Defaults to env INTEL_BRIEF_DB_PATH or packages/clawbot/data/intel_brief.db")
    parser.add_argument("--env-path", default=_default_env_path(), help="Private env path; values are redacted in evidence")
    parser.add_argument("--now", default=_default_now())
    parser.add_argument("--reminder-days", type=int, default=7)
    parser.add_argument("--apply-expiry", action="store_true", help="Mark active expired subscriptions as expired; requires lifecycle apply ack")
    parser.add_argument("--send-reminders", action="store_true", help="Send Telegram expiry reminders; requires token, Telegram ack, and --allow-real-network")
    parser.add_argument("--allow-real-network", action="store_true", help="Allow real Telegram Bot API sends for reminders")
    parser.add_argument("--apply-ack", default="", help=f"Optional CLI ack value: {LIFECYCLE_APPLY_ACK_VALUE}")
    parser.add_argument("--source", default="subscription_lifecycle_cli")
    parser.add_argument("--evidence", default="")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if args.apply_ack:
        env["INTEL_BRIEF_SUBSCRIPTION_LIFECYCLE_APPLY_ACK"] = args.apply_ack
    result = run_subscription_lifecycle_maintenance(
        db_path=args.db,
        env=env,
        env_path=args.env_path or None,
        project_root=PROJECT_ROOT,
        now=args.now,
        reminder_days=args.reminder_days,
        apply_expiry=args.apply_expiry,
        send_reminders=args.send_reminders,
        allow_real_network=args.allow_real_network,
        source=args.source,
    )
    if args.evidence:
        evidence_path = Path(args.evidence)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = (result.get("audit") or {}).get("summary", {}) if isinstance(result.get("audit"), dict) else {}
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "gate_status": (result.get("gate") or {}).get("status"),
                "summary": summary,
                "network_calls": int(result.get("network_calls", 0) or 0),
                "evidence": args.evidence,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result.get("status") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
