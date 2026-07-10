"""Probe Intel Brief Telegram Bot API runtime readiness.

The probe can register bot commands and read getUpdates, but it never sends
messages and never writes token/chat id/update text values to evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.private_env import default_private_env_path, load_private_env_file  # noqa: E402
from src.intel.telegram_bot_runtime import build_telegram_bot_runtime_probe  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe Intel Brief Telegram Bot API runtime readiness")
    parser.add_argument("--env-path", default=str(default_private_env_path(PROJECT_ROOT)))
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-real-network", action="store_true")
    parser.add_argument("--skip-set-commands", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=0)
    args = parser.parse_args(argv)

    env = load_private_env_file(args.env_path)
    result = build_telegram_bot_runtime_probe(
        evidence_path=args.output,
        env=env,
        allow_real_network=args.allow_real_network,
        limit=args.limit,
        timeout_seconds=args.timeout_seconds,
        set_commands=not args.skip_set_commands,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "network_calls": result["network_calls"],
                "gate": result["gate"],
                "set_my_commands_success": bool((result.get("set_my_commands") or {}).get("success")),
                "get_updates_success": bool((result.get("get_updates") or {}).get("success")),
                "output": args.output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
