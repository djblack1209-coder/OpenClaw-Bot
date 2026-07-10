"""Write a redacted Intel Brief commercial MVP E2E status audit."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.e2e_status_audit import build_intel_e2e_status_audit  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit current Intel Brief commercial MVP E2E status")
    parser.add_argument("--db", default=str(ROOT / "data" / "intel_brief.db"))
    parser.add_argument("--now", default=_now_iso())
    parser.add_argument(
        "--readiness-evidence",
        default=str(
            ROOT
            / "data"
            / "intel_evidence"
            / "phasebd"
            / "20260707T213012Z-launchagent-next-run-six-source-readiness"
            / "evidence.json"
        ),
    )
    parser.add_argument("--delivery-evidence", required=True)
    parser.add_argument(
        "--launchagent-audit-evidence",
        default="",
        help="Natural 08:30 LaunchAgent post-run audit evidence; must be six-source verified for final E2E status.",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    report = build_intel_e2e_status_audit(
        db_path=args.db,
        now=args.now,
        readiness_evidence_path=args.readiness_evidence,
        latest_delivery_evidence_path=args.delivery_evidence,
        launchagent_audit_evidence_path=args.launchagent_audit_evidence,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "summary": report["summary"],
                "network_calls": report["network_calls"],
                "output": str(output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
