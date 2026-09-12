"""Local report status and explicit reconciliation; never sends or generates."""
import argparse
import json
from pathlib import Path

from src.execution.report_delivery_store import DEFAULT_PATH, ReportDeliveryStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_PATH)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    resolve = commands.add_parser('resolve')
    resolve.add_argument('report_id')
    resolve.add_argument('--part', type=int, required=True)
    resolve.add_argument('--action', choices=['confirmed_sent', 'not_sent'], required=True)
    resolve.add_argument('--expected-state', choices=['unknown'], required=True)
    resolve.add_argument('--operation-id', required=True)
    resolve.add_argument('--evidence', required=True, help='Non-secret local ticket or evidence reference')
    resolve.add_argument('--message-id', type=int)
    args = parser.parse_args(argv)
    if args.command == 'status':
        result = ReportDeliveryStore(args.db, create=False).summary()
    else:
        if not args.db.is_file():
            parser.error('existing report database required')
        result = ReportDeliveryStore(args.db).resolve(args.report_id, args.part, args.action,
            expected_state=args.expected_state, operation_id=args.operation_id,
            evidence=args.evidence, message_id=args.message_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
