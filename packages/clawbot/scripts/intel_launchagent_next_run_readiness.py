"""Write read-only readiness evidence for the next Intel Brief LaunchAgent run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.launchagent_readiness import build_launchagent_next_run_readiness  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit next Intel Brief LaunchAgent run readiness")
    parser.add_argument(
        "--plist",
        default=str(
            ROOT
            / "data"
            / "intel_evidence"
            / "phaset"
            / "20260707T040135Z-launchd-production-cycle-install-package-absolute"
            / "ai.openclaw.intel-brief.scheduler.plist"
        ),
    )
    parser.add_argument(
        "--controlled-cycle",
        default=str(
            ROOT
            / "data"
            / "intel_evidence"
            / "phaseaz"
            / "20260707T205021Z-controlled-production-cycle-six-sources-weather"
            / "latest-production-cycle.json"
        ),
    )
    parser.add_argument(
        "--previous-natural-audit",
        default=str(
            ROOT
            / "data"
            / "intel_evidence"
            / "phaset"
            / "20260707T211424Z-launchagent-natural-0830-verified-with-artifact"
            / "evidence.json"
        ),
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    report = build_launchagent_next_run_readiness(
        plist_path=args.plist,
        controlled_cycle_path=args.controlled_cycle,
        previous_natural_audit_path=args.previous_natural_audit or None,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "missing": report["missing"],
                "expected_sources": report["expected_sources"],
                "network_calls": report["network_calls"],
                "output": str(output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
