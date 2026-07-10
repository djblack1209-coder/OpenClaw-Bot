"""Build sandbox evidence for offset-safe Intel Brief Telegram update processing."""

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

from src.intel.subscriptions import get_subscription_profile, grant_subscription, upsert_subscription_plan  # noqa: E402
from src.intel.telegram_update_processor import get_telegram_offset, process_telegram_updates_once  # noqa: E402

SANDBOX_CHAT_ID = "processor-" + "chat-should-not-leak"
SANDBOX_USER_ID = "processor-sandbox-user"


class FakeBotClient:
    def __init__(self, updates: list[dict[str, Any]]) -> None:
        self.updates = updates
        self.network_calls = 0

    def get_updates(self, *, limit: int = 20, offset: int | None = None, timeout_seconds: int = 0) -> dict[str, Any]:
        self.network_calls += 0
        selected = [item for item in self.updates if offset is None or int(item.get("update_id", 0) or 0) >= offset]
        return {
            "success": True,
            "method": "getUpdates",
            "network": "fake_client",
            "network_calls": 0,
            "update_count": len(selected),
            "command_update_count": len(selected),
            "max_update_id_present": bool(selected),
            "redacted": {"update_count": len(selected), "chat_id_values_persisted": False},
            "updates": selected,
            "error_code": "",
            "error": "",
        }


class FakeReplySender:
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
            "from": {"id": SANDBOX_USER_ID, "username": "processor_sandbox"},
            "chat": {"id": SANDBOX_CHAT_ID, "type": "private"},
        },
    }


def _safe_profile(profile: dict[str, Any]) -> dict[str, Any]:
    safe = {key: value for key, value in profile.items() if key != "channel_user_id"}
    safe["channel_user_id_present"] = bool(profile.get("channel_user_id"))
    return safe


def build_intel_telegram_update_processor_sandbox_evidence(
    evidence_dir: str | Path,
    *,
    now: str = "2026-07-07T17:00:00+00:00",
) -> dict[str, Any]:
    out_dir = Path(evidence_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "intel_telegram_update_processor_sandbox.db"
    evidence_path = out_dir / "evidence.json"
    sender = FakeReplySender()

    first = process_telegram_updates_once(
        db_path,
        client=FakeBotClient([_update(100, "/start")]),
        sender=sender,
        now=now,
    )
    user_id = first["runtime"]["handled_updates"][0]["subscriber_user_id"]
    upsert_subscription_plan(db_path, plan_name="intel_mvp_monthly", categories=["akshare", "senate_trading"])
    grant = grant_subscription(
        db_path,
        user_id=user_id,
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at="2026-08-07T00:00:00+00:00",
        source="update_processor_sandbox_manual_grant",
    )
    second = process_telegram_updates_once(
        db_path,
        client=FakeBotClient(
            [
                _update(100, "/start"),
                _update(101, "/sources akshare senate_trading"),
                _update(102, "/schedule daily 08:30 America/Denver"),
                _update(103, "/custom 周杰伦"),
            ]
        ),
        sender=sender,
        now=now,
    )
    duplicate = process_telegram_updates_once(
        db_path,
        client=FakeBotClient([_update(100, "/start"), _update(101, "/sources akshare")]),
        sender=sender,
        now=now,
    )
    final_profile = get_subscription_profile(db_path, user_id=user_id, now=now)
    final_offset = get_telegram_offset(db_path)
    evidence = {
        "timestamp": _now_iso(),
        "phase": "AC-telegram-update-processor-offset-sandbox",
        "scope": "telegram_update_offset_persistence_and_duplicate_safe_processing",
        "status": "success" if first["status"] == "success" and second["status"] == "success" and duplicate["status"] == "no_new_updates" else "failed",
        "now": now,
        "sandbox_db": str(db_path),
        "grant": {
            "status": grant["status"],
            "plan_name": grant["plan_name"],
            "expires_at": grant["expires_at"],
            "source": grant["source"],
        },
        "runs": [first, second],
        "duplicate_replay": duplicate,
        "final_offset": final_offset,
        "final_profile": _safe_profile(final_profile),
        "tracking_targets": second.get("tracking_targets", []),
        "network_calls": int(first.get("network_calls", 0)) + int(second.get("network_calls", 0)) + int(duplicate.get("network_calls", 0)),
        "redaction": {
            "telegram_user_id_present_only": True,
            "chat_id_present_only": True,
            "raw_chat_id_written": False,
            "token_written": False,
        },
        "rollback": [str(db_path), str(evidence_path)],
        "limits": [
            "Sandbox SQLite only; production intel_brief.db was not touched.",
            "No Telegram Bot API call; fake client and fake sender only.",
            "No scraper was triggered by /custom; target was only recorded for later rate-limited collection.",
            "No payment provider or Xianyu automation call.",
        ],
    }
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief Telegram update processor offset sandbox")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--now", default="2026-07-07T17:00:00+00:00")
    parser.add_argument("--stamp", default="")
    args = parser.parse_args(argv)

    stamp = args.stamp or _stamp()
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else ROOT / "data" / "intel_evidence" / "phaseac" / f"{stamp}-telegram-update-processor-offset-sandbox"
    )
    evidence = build_intel_telegram_update_processor_sandbox_evidence(output_dir, now=args.now)
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "phase": evidence["phase"],
                "network_calls": evidence["network_calls"],
                "final_offset": evidence["final_offset"],
                "output": str(output_dir / "evidence.json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if evidence["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
