"""Run one Intel Brief production delivery if gates are ready."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.production_once import parse_now, run_intel_production_once  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one gated Intel Brief production delivery")
    parser.add_argument("--summary-evidence", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--now")
    parser.add_argument("--time", default="08:30")
    args = parser.parse_args(argv)

    result = run_intel_production_once(
        summary_evidence_path=args.summary_evidence,
        evidence_path=args.evidence,
        now=parse_now(args.now),
        scheduled_time=args.time,
        project_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "missing_gates": result["gate"].get("missing_gates", []),
                "network_calls": result["network_calls"],
                "evidence": args.evidence,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
