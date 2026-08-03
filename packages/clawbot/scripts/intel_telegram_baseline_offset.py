"""Seed Telegram update baseline offset for Intel Brief.

This is a one-shot safety step before automatic replies: it marks current
historical updates as seen without replying to them.
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
from src.intel.telegram_baseline_offset import build_telegram_baseline_offset_evidence  # noqa: E402
from src.intel.telegram_bot_runtime import TelegramBotApiRuntimeClient, build_bot_runtime_gate  # noqa: E402


def _blocked_payload(*, db_path: str, output: str, gate: dict[str, object]) -> dict[str, object]:
    return {
        "phase": "AD-telegram-baseline-offset",
        "scope": "telegram_historical_update_baseline_without_replying",
        "status": "blocked",
        "db_path": db_path,
        "gate": gate,
        "network_calls": 0,
        "reply_sent": False,
        "raw_updates_persisted": False,
        "limits": [
            "No Telegram Bot API call unless token, ack, and allow_real_network are present.",
            "No sendMessage call is made by baseline seeding.",
        ],
        "rollback": [],
        "output": output,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Intel Brief Telegram baseline offset without replying")
    parser.add_argument("--db", default=str(ROOT / "data" / "intel_brief.db"))
    parser.add_argument("--env-path", default=str(default_private_env_path(PROJECT_ROOT)))
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-real-network", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--max-batches", type=int, default=100)
    args = parser.parse_args(argv)

    env = load_private_env_file(args.env_path)
    gate = build_bot_runtime_gate(env, allow_real_network=args.allow_real_network)
    output_path = Path(args.output)
    if not gate["ready"]:
        payload = _blocked_payload(db_path=args.db, output=args.output, gate=gate)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"status": "blocked", "gate": gate, "network_calls": 0, "output": args.output},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2

    client = TelegramBotApiRuntimeClient(token=env.get("INTEL_BRIEF_TELEGRAM_BOT_TOKEN", ""))
    result = build_telegram_baseline_offset_evidence(
        db_path=args.db,
        evidence_path=args.output,
        client=client,
        limit=args.limit,
        timeout_seconds=args.timeout_seconds,
        max_batches=args.max_batches,
        source="real_bot_api_baseline",
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "previous_offset": result["previous_offset"],
                "baseline_update_id": result["baseline_update_id"],
                "new_offset": result["new_offset"],
                "network_calls": result["network_calls"],
                "reply_sent": result["reply_sent"],
                "output": args.output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
