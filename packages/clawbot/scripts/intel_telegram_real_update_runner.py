"""Run one gated Intel Brief real Telegram update processing cycle."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.private_env import default_private_env_path, load_private_env_file  # noqa: E402
from src.intel.telegram_real_update_runner import build_real_update_runner_evidence  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one gated Intel Brief Telegram update processing cycle")
    parser.add_argument("--db", default=str(ROOT / "data" / "intel_brief.db"))
    parser.add_argument("--env-path", default=str(default_private_env_path(PROJECT_ROOT)))
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-real-network", action="store_true")
    parser.add_argument("--allow-send-message", action="store_true")
    parser.add_argument("--now", default=_now_iso())
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=0)
    args = parser.parse_args(argv)

    env = load_private_env_file(args.env_path)
    result = build_real_update_runner_evidence(
        db_path=args.db,
        evidence_path=args.output,
        env=env,
        allow_real_network=args.allow_real_network,
        allow_send_message=args.allow_send_message,
        now=args.now,
        limit=args.limit,
        timeout_seconds=args.timeout_seconds,
    )
    processor = result.get("processor") or {}
    runtime = processor.get("runtime") if isinstance(processor, dict) else {}
    print(
        json.dumps(
            {
                "status": result["status"],
                "network_calls": result["network_calls"],
                "send_message_attempted": result["send_message_attempted"],
                "handled_count": int((runtime or {}).get("handled_count", 0) or 0) if isinstance(runtime, dict) else 0,
                "new_offset": processor.get("new_offset") if isinstance(processor, dict) else None,
                "output": args.output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] in {"success", "no_new_updates"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
