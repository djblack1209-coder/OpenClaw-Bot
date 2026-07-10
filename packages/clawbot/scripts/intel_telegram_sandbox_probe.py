"""Probe Intel Brief Telegram sandbox delivery gates.

By default this script is gate-only and does not call the Telegram Bot API.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.telegram_delivery import build_telegram_sandbox_probe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write Intel Brief Telegram sandbox gate evidence")
    parser.add_argument("--output", required=True)
    parser.add_argument("--message", default="Intel Brief Telegram sandbox probe")
    parser.add_argument(
        "--allow-real-network",
        action="store_true",
        help="Call Telegram Bot API only when all env gates are ready.",
    )
    args = parser.parse_args(argv)

    result = build_telegram_sandbox_probe(
        evidence_path=args.output,
        message=args.message,
        allow_real_network=args.allow_real_network,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "network_calls": result["network_calls"],
                "output": args.output,
                "gate": result["gate"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] in {"success"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
