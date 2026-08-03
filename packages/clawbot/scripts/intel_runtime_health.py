"""输出每日资讯中央运行健康 JSON。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.runtime_health import build_intel_runtime_health  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Intel Brief runtime health JSON")
    parser.add_argument("--db", default=str(ROOT / "data" / "intel_brief.db"))
    parser.add_argument(
        "--listener-evidence-dir",
        default=str(ROOT / "data" / "intel_evidence" / "phasefix" / "telegram-listener"),
    )
    args = parser.parse_args(argv)
    payload = build_intel_runtime_health(
        db_path=args.db,
        listener_evidence_dir=args.listener_evidence_dir,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
