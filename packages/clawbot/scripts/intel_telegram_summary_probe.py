"""Probe Telegram delivery using a real Intel Brief summary evidence file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.telegram_delivery import build_telegram_summary_delivery_probe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe Telegram delivery from Intel Brief summary evidence")
    parser.add_argument("--summary-evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--allow-real-network",
        action="store_true",
        help="Call Telegram Bot API only when all env gates are ready.",
    )
    args = parser.parse_args(argv)

    result = build_telegram_summary_delivery_probe(
        summary_evidence_path=args.summary_evidence,
        evidence_path=args.output,
        allow_real_network=args.allow_real_network,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "network_calls": result["network_calls"],
                "summary_evidence": args.summary_evidence,
                "output": args.output,
                "gate": result["gate"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
