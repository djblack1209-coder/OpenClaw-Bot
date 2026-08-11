"""Build sandbox evidence for Intel Brief Telegram runtime adapter."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.subscriptions import (  # noqa: E402
    get_subscription_profile,
    grant_subscription,
    upsert_subscription_plan,
)
from src.intel.telegram_runtime import process_intel_telegram_updates  # noqa: E402

SANDBOX_CHAT_ID = "runtime-" + "sandbox-chat-redacted"
SANDBOX_USER_ID = "runtime-sandbox-user"


class FakeTelegramReplySender:
    def __init__(self) -> None:
        self.sent_count = 0
        self.network_calls = 0

    def send(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.sent_count += 1
        return {
            "success": True,
            "network": "fake_sender",
            "network_calls": 0,
            "chat_id_present": bool(str(chat_id or "").strip()),
            "message_id": f"fake-{self.sent_count}",
            "endpoint": "fake://telegram/sendMessage",
            "parse_mode": parse_mode,
            "text_chars": len(str(text or "")),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017 - Python 3.10 worker compatibility


def _update(update_id: int, text: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id + 100,
            "text": text,
            "from": {"id": SANDBOX_USER_ID, "username": "intel_runtime_sandbox"},
            "chat": {"id": SANDBOX_CHAT_ID, "type": "private"},
        },
    }


def _safe_profile(profile: dict[str, Any]) -> dict[str, Any]:
    safe = {key: value for key, value in profile.items() if key != "channel_user_id"}
    safe["channel_user_id_present"] = bool(profile.get("channel_user_id"))
    return safe


def _merge_runtime_results(*results: dict[str, Any]) -> dict[str, Any]:
    handled_updates: list[dict[str, Any]] = []
    replies: list[dict[str, Any]] = []
    tracking_targets: list[dict[str, Any]] = []
    for result in results:
        handled_updates.extend(result.get("handled_updates", []))
        replies.extend(result.get("replies", []))
        tracking_targets.extend(result.get("tracking_targets", []))
    handled_count = sum(int(result.get("handled_count", 0)) for result in results)
    send_success_count = sum(int(result.get("send_success_count", 0)) for result in results)
    return {
        "status": "success" if handled_count == send_success_count and handled_count else "partial_or_empty",
        "updates_seen": sum(int(result.get("updates_seen", 0)) for result in results),
        "handled_count": handled_count,
        "skipped_count": sum(int(result.get("skipped_count", 0)) for result in results),
        "send_success_count": send_success_count,
        "handled_updates": handled_updates,
        "replies": replies,
        "tracking_targets": tracking_targets,
        "network_calls": sum(int(result.get("network_calls", 0)) for result in results),
    }


def build_intel_telegram_runtime_sandbox_evidence(
    evidence_dir: str | Path,
    *,
    now: str = "2026-07-07T16:30:00+00:00",
) -> dict[str, Any]:
    """Replay a full Telegram user setup flow with fake sender and sandbox DB."""
    out_dir = Path(evidence_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "intel_telegram_runtime_sandbox.db"
    evidence_path = out_dir / "evidence.json"
    sender = FakeTelegramReplySender()

    start_result = process_intel_telegram_updates(
        db_path,
        updates=[_update(1, "/start")],
        sender=sender,
        now=now,
    )
    subscriber_user_id = start_result["handled_updates"][0]["subscriber_user_id"]
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare", "senate_trading"])
    grant = grant_subscription(
        db_path,
        user_id=subscriber_user_id,
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at="2026-08-07T00:00:00+00:00",
        source="runtime_sandbox_manual_grant",
    )
    config_result = process_intel_telegram_updates(
        db_path,
        updates=[
            _update(2, "/sources akshare senate_trading"),
            _update(3, "/schedule daily 08:30 America/Denver"),
            _update(4, "/custom 周杰伦"),
            _update(5, "/status"),
        ],
        sender=sender,
        now=now,
    )
    runtime = _merge_runtime_results(start_result, config_result)
    final_profile = get_subscription_profile(db_path, user_id=subscriber_user_id, now=now)
    evidence = {
        "timestamp": _now_iso(),
        "phase": "AA-telegram-runtime-adapter-sandbox",
        "scope": "telegram_update_to_intel_handler_to_reply_sender_contract",
        "status": runtime["status"],
        "now": now,
        "sandbox_db": str(db_path),
        "grant": {
            "status": grant["status"],
            "plan_name": grant["plan_name"],
            "expires_at": grant["expires_at"],
            "source": grant["source"],
        },
        "runtime": runtime,
        "final_profile": _safe_profile(final_profile),
        "tracking_targets": runtime["tracking_targets"],
        "network_calls": runtime["network_calls"],
        "redaction": {
            "telegram_user_id_present_only": True,
            "chat_id_present_only": True,
            "raw_chat_id_written": False,
            "token_written": False,
        },
        "rollback": [str(db_path), str(evidence_path)],
        "limits": [
            "Sandbox SQLite only; production intel_brief.db was not touched.",
            "No Telegram Bot API call; fake sender only.",
            "No scraper was triggered by /custom; target was only recorded for later rate-limited collection.",
            "No payment provider or marketplace automation call.",
        ],
    }
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief Telegram runtime adapter sandbox")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--now", default="2026-07-07T16:30:00+00:00")
    parser.add_argument("--stamp", default="")
    args = parser.parse_args(argv)

    stamp = args.stamp or _stamp()
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else ROOT / "data" / "intel_evidence" / "phaseaa" / f"{stamp}-telegram-runtime-adapter-sandbox"
    )
    evidence = build_intel_telegram_runtime_sandbox_evidence(output_dir, now=args.now)
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "phase": evidence["phase"],
                "network_calls": evidence["network_calls"],
                "output": str(output_dir / "evidence.json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if evidence["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
