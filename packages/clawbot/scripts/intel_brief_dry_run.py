"""Build Intel Brief dry-run Markdown/JSON from collect-once evidence.

This script is controller-local only: it does not call external data sources,
LLMs, Telegram, schedulers, or production services.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.brief_builder import build_brief_dry_run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Intel Brief dry-run brief from collect evidence")
    parser.add_argument("--collect-evidence", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--stamp")
    args = parser.parse_args(argv)

    result = build_brief_dry_run(
        collect_evidence_path=args.collect_evidence,
        markdown_output_path=args.markdown_output,
        json_output_path=args.json_output,
        stamp=args.stamp,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "summary": result["summary"],
                "markdown_output": args.markdown_output,
                "json_output": args.json_output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] in {"success", "empty"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
