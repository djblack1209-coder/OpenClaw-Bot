"""Generate a dry-run Intel Brief launchd package and redacted evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.launch_package import build_launchd_package  # noqa: E402
from src.intel.private_env import default_private_env_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Intel Brief launch package without installing it")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--env-path")
    parser.add_argument("--summary-evidence", default="")
    parser.add_argument("--label", default="ai.openclaw.intel-brief.scheduler")
    parser.add_argument("--include-production-ack", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root)
    env_path = Path(args.env_path) if args.env_path else default_private_env_path(project_root)
    report = build_launchd_package(
        output_dir=args.output_dir,
        project_root=project_root,
        env_path=env_path,
        summary_evidence_path=args.summary_evidence or None,
        label=args.label,
        include_production_ack=args.include_production_ack,
    )
    payload = {
        **report,
        "phase": "P-launch-package",
        "scope": "intel_brief_launchd_package_dry_run",
        "network_calls": 0,
    }
    evidence_path = Path(args.evidence)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "evidence": str(evidence_path), "output_dir": args.output_dir}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
