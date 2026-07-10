"""Run Intel Brief subscription lifecycle sandbox evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.subscription_lifecycle import build_subscription_lifecycle_sandbox  # noqa: E402


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief subscription lifecycle sandbox")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--now", default="2026-07-07T18:30:00+00:00")
    parser.add_argument("--stamp", default="")
    args = parser.parse_args(argv)

    stamp = args.stamp or _stamp()
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "data" / "intel_evidence" / "phasean" / f"{stamp}-subscription-lifecycle-sandbox"
    evidence = build_subscription_lifecycle_sandbox(output_dir, now=args.now)
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "phase": evidence["phase"],
                "summary": evidence["audit"]["summary"],
                "network_calls": evidence["network_calls"],
                "output": str(output_dir / "evidence.json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if evidence["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
