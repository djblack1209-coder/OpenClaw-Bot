"""Write a read-only Intel Brief production readiness audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.production_readiness import write_intel_production_readiness_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write Intel Brief production readiness evidence")
    parser.add_argument("--collect-evidence", required=True)
    parser.add_argument("--summary-evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--now", required=True)
    parser.add_argument("--time", default="08:30")
    args = parser.parse_args(argv)

    report = write_intel_production_readiness_report(
        collect_evidence_path=args.collect_evidence,
        summary_evidence_path=args.summary_evidence,
        evidence_path=args.output,
        now_iso=args.now,
        scheduled_time=args.time,
        project_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "missing_gates": report["missing_gates"],
                "readiness_score": report["readiness_score"],
                "network_calls": report["network_calls"],
                "output": args.output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
