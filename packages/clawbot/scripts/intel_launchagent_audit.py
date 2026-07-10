"""Audit Intel Brief LaunchAgent post-run artifacts without triggering it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.launchagent_audit import (  # noqa: E402
    build_launchagent_post_run_audit,
    collect_launchctl_text,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Intel Brief LaunchAgent post-run evidence")
    parser.add_argument("--label", default="ai.openclaw.intel-brief.scheduler")
    parser.add_argument("--run-evidence", required=True)
    parser.add_argument("--stdout-log", required=True)
    parser.add_argument("--stderr-log", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--launchctl-text", help="Test hook: provide launchctl print text instead of running launchctl")
    parser.add_argument(
        "--expected-source",
        action="append",
        default=[],
        help="Require a source to be present and successful in latest-production-cycle.json; repeat for each source.",
    )
    args = parser.parse_args(argv)

    if args.launchctl_text is None:
        launchctl_text, _returncode = collect_launchctl_text(args.label)
    else:
        launchctl_text = args.launchctl_text
    report = build_launchagent_post_run_audit(
        label=args.label,
        run_evidence_path=args.run_evidence,
        stdout_path=args.stdout_log,
        stderr_path=args.stderr_log,
        launchctl_text=launchctl_text,
        expected_sources=args.expected_source,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output), "network_calls": report["network_calls"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "verified_success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
