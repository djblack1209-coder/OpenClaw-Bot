"""Local Telegram bootstrap for one Intel Brief sandbox summary send.

The script can prompt for a token without echoing it.  It never writes token or
chat id values into evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.telegram_bootstrap import build_telegram_local_bootstrap_probe, token_from_env_or_prompt  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap local Telegram chat id and send Intel Brief sandbox summary")
    parser.add_argument("--summary-evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bot-username", default="carven_Jianbao_bot")
    parser.add_argument("--start-payload", default="intel_brief_sandbox")
    parser.add_argument("--allow-real-network", action="store_true")
    parser.add_argument("--open-telegram", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument(
        "--prompt-token",
        action="store_true",
        help="Prompt for token with hidden input if INTEL_BRIEF_TELEGRAM_BOT_TOKEN is not set.",
    )
    args = parser.parse_args(argv)

    token = token_from_env_or_prompt() if args.prompt_token else os.environ.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN", "")
    result = build_telegram_local_bootstrap_probe(
        token=token,
        bot_username=args.bot_username,
        summary_evidence_path=args.summary_evidence,
        evidence_path=args.output,
        ack=os.environ.get("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK", ""),
        allow_real_network=args.allow_real_network,
        open_deep_link=args.open_telegram,
        start_payload=args.start_payload,
        wait_seconds=args.wait_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "missing_gates": result["missing_gates"],
                "network_calls": result["network_calls"],
                "chat_candidate": result["chat_candidate"],
                "get_me": result["get_me"],
                "get_updates": result["get_updates"],
                "output": args.output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
