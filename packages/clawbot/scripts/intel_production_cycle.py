"""Run one fresh Intel Brief production cycle behind hard gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.production_cycle import (  # noqa: E402
    DEFAULT_PRODUCTION_CYCLE_SOURCES,
    parse_now,
    run_intel_production_cycle,
)
from src.intel.scheduled_cycle import run_scheduled_intel_cycle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one fresh Intel Brief production cycle", allow_abbrev=False)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--now")
    parser.add_argument("--time", default="08:30")
    parser.add_argument("--stamp")
    parser.add_argument("--scheduled", action="store_true", help="Use the real Singapore delivery window and daily claim")
    parser.add_argument("--source", action="append", dest="sources")
    parser.add_argument("--llm-mode", choices=["real", "fallback-only"], default="fallback-only")
    args = parser.parse_args(argv)

    if args.scheduled and (args.now is not None or args.stamp is not None or args.time != "08:30"):
        parser.error("--scheduled uses the real clock at 08:30 Asia/Singapore; --now/--stamp/custom --time are not allowed")
    common = {
        "output_dir": args.output_dir,
        "evidence_path": args.evidence,
        "sources": args.sources or list(DEFAULT_PRODUCTION_CYCLE_SOURCES),
        "llm_mode": args.llm_mode,
        "project_root": Path.cwd(),
    }
    if args.scheduled:
        result = run_scheduled_intel_cycle(**common)
    else:
        result = run_intel_production_cycle(**common, now=parse_now(args.now), scheduled_time=args.time, stamp=args.stamp)
    print(
        json.dumps(
            {
                "status": result["status"],
                "preflight_missing_gates": result.get("preflight", {}).get("missing_gates", []),
                "network_calls": result["network_calls"],
                "evidence": args.evidence,
                "artifacts": result.get("artifacts", {}),
                "reason": result.get("reason", ""),
                "scheduler": result.get("scheduler", {}),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] in {"success", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
