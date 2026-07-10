"""Run Intel Brief subscriber + fake Telegram delivery sandbox."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.delivery import build_delivery_sandbox  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief fake Telegram delivery sandbox")
    parser.add_argument("--summary-evidence", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--outbox", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--stamp")
    args = parser.parse_args(argv)

    result = build_delivery_sandbox(
        summary_evidence_path=args.summary_evidence,
        db_path=args.db,
        outbox_path=args.outbox,
        evidence_path=args.output,
        stamp=args.stamp,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "summary": result["delivery"]["summary"],
                "network_calls": result["network_calls"],
                "output": args.output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
