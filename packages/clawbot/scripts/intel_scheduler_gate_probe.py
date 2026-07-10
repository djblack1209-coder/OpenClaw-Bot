"""Write a redacted Intel Brief scheduler-gate evidence JSON.

This is a read-only controller probe: it evaluates environment switches and
hard gates, but it never registers a scheduler, calls Telegram, fetches sources,
or writes production DBs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.execution._utils import parse_hhmm  # noqa: E402
from src.execution.intel_brief import build_intel_brief_scheduler_gate  # noqa: E402


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write Intel Brief scheduler gate evidence")
    parser.add_argument("--output", required=True)
    parser.add_argument("--now", required=True)
    parser.add_argument("--time", required=True)
    parser.add_argument("--last-run-date", default="")
    args = parser.parse_args(argv)

    gate = build_intel_brief_scheduler_gate(
        now=_parse_datetime(args.now),
        scheduled_time=parse_hhmm(args.time, (8, 30)),
        last_run_date=args.last_run_date,
    )
    status = "ready" if gate["should_run"] else "blocked" if gate["reason"] == "blocked_by_hard_gate" else "skipped"
    payload = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "phase": "J-scheduler-gate",
        "scope": "intel_brief_scheduler_gate_probe",
        "status": status,
        "gate": gate,
        "limits": [
            "Read-only scheduler gate evaluation.",
            "No scheduler/cron/systemd registration.",
            "No Telegram Bot API call.",
            "No external data-source fetch.",
            "No production DB write.",
            "Secrets are represented only as boolean presence flags.",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "output": str(output)}, ensure_ascii=False, sort_keys=True))
    return 0 if status in {"ready", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
