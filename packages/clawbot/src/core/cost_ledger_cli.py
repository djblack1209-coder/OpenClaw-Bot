"""Explicit, local accounting inspection/migration; never auto-runs on startup."""

import argparse
import json
from pathlib import Path

from src.core.cost_ledger import CostLedger


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("stats")
    preview = sub.add_parser("import-legacy")
    preview.add_argument("source", type=Path)
    preview.add_argument("--apply", action="store_true", help="default is validation only")
    activate = sub.add_parser("activate")
    activate.add_argument(
        "--opening-spend-usd",
        required=True,
        help="confirmed total spend for the current ET day, including imported records",
    )
    settle = sub.add_parser("reconcile")
    settle.add_argument("attempt_id")
    settle.add_argument("--actual-usd", required=True, help="verified provider charge; never inferred from timeout")
    settle.add_argument("--reconciliation-id", required=True)
    settle.add_argument("--evidence", required=True, help="non-secret invoice/reference identifier")
    release = sub.add_parser("release-reserved")
    release.add_argument("attempt_id")
    recovery = sub.add_parser("recover-bounds")
    recovery.add_argument("--recovery-id", required=True)
    recovery.add_argument("--evidence", required=True)
    recovery.add_argument(
        "--replacements", type=Path, required=True, help="JSON map of attempt IDs to corrected price snapshots"
    )
    args = parser.parse_args(argv)
    ledger = CostLedger(args.db)
    if args.command == "import-legacy":
        result = ledger.import_legacy(args.source, dry_run=not args.apply)
    elif args.command == "activate":
        ledger.activate(opening_spend_usd=args.opening_spend_usd)
        result = ledger.stats()
    elif args.command == "reconcile":
        result = ledger.reconcile(
            args.attempt_id, args.actual_usd, reconciliation_id=args.reconciliation_id, evidence=args.evidence
        )
    elif args.command == "release-reserved":
        result = ledger.release(args.attempt_id)
    elif args.command == "recover-bounds":
        result = ledger.recover_bounds(
            recovery_id=args.recovery_id, evidence=args.evidence, replacements=json.loads(args.replacements.read_text())
        )
    else:
        result = ledger.stats()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
