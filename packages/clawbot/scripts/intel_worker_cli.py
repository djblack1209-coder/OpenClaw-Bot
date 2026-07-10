"""Intel Brief worker CLI.

Target-worker entrypoint for executing one JSON-safe IntelWorkerRequest. The CLI
reads a request from stdin or --input, uses the default verified adapter registry,
writes optional source_health to --db, and prints one JSON-safe response to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.sources.registry import build_default_source_adapters  # noqa: E402
from src.intel.worker_runner import execute_worker_request_json  # noqa: E402


def _read_payload(input_path: str | None) -> str:
    if input_path:
        return Path(input_path).read_text(encoding="utf-8")
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute one Intel Brief worker request JSON")
    parser.add_argument("--input", help="request JSON file; defaults to stdin")
    parser.add_argument("--db", help="optional Intel Brief SQLite DB path for source_health updates")
    args = parser.parse_args(argv)

    payload = _read_payload(args.input)
    try:
        response_json = execute_worker_request_json(
            payload,
            adapters=build_default_source_adapters(),
            db_path=args.db,
        )
    except json.JSONDecodeError as exc:
        print(f"invalid request json: {exc}", file=sys.stderr)
        return 1
    print(response_json)
    return 0 if '"status": "success"' in response_json else 2


if __name__ == "__main__":
    raise SystemExit(main())
