"""Run Intel Brief scheduled sandbox pipeline from existing collect evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.scheduled_pipeline import run_scheduled_sandbox_pipeline  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief scheduled sandbox rehearsal")
    parser.add_argument("--collect-evidence", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--now", required=True)
    parser.add_argument("--time", required=True)
    parser.add_argument("--stamp", required=True)
    parser.add_argument("--enabled", choices=["true", "false"], default="true")
    parser.add_argument("--last-run-date", default="")
    parser.add_argument("--llm-mode", choices=["real", "fallback-only"], default="real")
    args = parser.parse_args(argv)

    result = run_scheduled_sandbox_pipeline(
        collect_evidence_path=args.collect_evidence,
        output_dir=args.output_dir,
        evidence_path=args.output,
        now_iso=args.now,
        scheduled_time=args.time,
        stamp=args.stamp,
        enabled=args.enabled == "true",
        last_run_date=args.last_run_date,
        llm_mode=args.llm_mode,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "schedule": result["schedule"],
                "artifacts": result["artifacts"],
                "output": args.output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] in {"success", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
