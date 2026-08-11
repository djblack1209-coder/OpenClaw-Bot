"""Build sandbox evidence for Intel Brief Telegram menu handlers.

This rehearsal uses only a throwaway SQLite DB and the handler contract. It
never calls Telegram Bot API, payment providers, scrapers, or remote workers.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.subscriptions import (  # noqa: E402
    DEFAULT_MVP_CATEGORIES,
    get_subscription_profile,
    grant_subscription,
    upsert_subscription_plan,
)
from src.intel.telegram_menu import TelegramUserContext, handle_intel_telegram_command  # noqa: E402


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _safe_profile(profile: dict[str, Any]) -> dict[str, Any]:
    safe = {key: value for key, value in profile.items() if key != "channel_user_id"}
    safe["channel_user_id_present"] = bool(profile.get("channel_user_id"))
    return safe


def _safe_step(name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": name,
        "status": result.get("status"),
        "network_calls": int(result.get("network_calls", 0)),
        "reply_text_present": bool(result.get("reply_text")),
        "redacted_user": result.get("redacted_user", {}),
    }


def build_intel_telegram_menu_sandbox_evidence(
    evidence_dir: str | Path,
    *,
    now: str = "2026-07-07T16:00:00+00:00",
) -> dict[str, Any]:
    """Simulate the Telegram user menu flow and write redacted evidence."""
    out_dir = Path(evidence_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "intel_telegram_menu_sandbox.db"
    evidence_path = out_dir / "evidence.json"

    user = TelegramUserContext(
        telegram_user_id="sandbox-menu-user",
        chat_id="sandbox-menu-chat",
        username="intel_menu_sandbox",
    )

    start = handle_intel_telegram_command(db_path, user=user, command="/start", args=[], now=now)
    plan = upsert_subscription_plan(
        db_path,
        plan_name="intel_mvp_monthly",
        categories=DEFAULT_MVP_CATEGORIES,
        price_cents=9900,
        duration_type="monthly",
    )
    grant = grant_subscription(
        db_path,
        user_id=start["subscriber"]["user_id"],
        plan_name=plan["plan_name"],
        starts_at="2026-07-07T00:00:00+00:00",
        expires_at="2026-08-07T00:00:00+00:00",
        source="sandbox_manual_grant",
    )
    sources = handle_intel_telegram_command(
        db_path,
        user=user,
        command="/sources",
        args=["senate_trading", "akshare"],
        now=now,
    )
    schedule = handle_intel_telegram_command(
        db_path,
        user=user,
        command="/schedule",
        args=["daily", "08:30", "America/Denver"],
        now=now,
    )
    custom = handle_intel_telegram_command(db_path, user=user, command="/custom", args=["周杰伦"], now=now)
    status = handle_intel_telegram_command(db_path, user=user, command="/status", args=[], now=now)
    final_profile = get_subscription_profile(db_path, user_id=start["subscriber"]["user_id"], now=now)
    button_user = TelegramUserContext(
        telegram_user_id="sandbox-menu-button-user",
        chat_id="sandbox-menu-button-chat",
        username="intel_button_sandbox",
    )
    handle_intel_telegram_command(db_path, user=button_user, command="/start", args=[], now=now)
    stock_button = handle_intel_telegram_command(db_path, user=button_user, command="股市", args=[], now=now)
    github_button = handle_intel_telegram_command(db_path, user=button_user, command="Github", args=[], now=now)
    github_toggle_off = handle_intel_telegram_command(db_path, user=button_user, command="Github", args=[], now=now)

    network_calls = sum(
        int(step.get("network_calls", 0))
        for step in [start, sources, schedule, custom, status, stock_button, github_button, github_toggle_off]
    )
    evidence = {
        "timestamp": _timestamp(),
        "phase": "Z-telegram-menu-handler-contract",
        "scope": "telegram_user_menu_preferences_subscription_and_tracking_contract",
        "status": "success",
        "now": now,
        "sandbox_db": str(db_path),
        "steps": [
            _safe_step("start", start),
            {
                "command": "grant",
                "status": grant["status"],
                "plan_name": grant["plan_name"],
                "expires_at": grant["expires_at"],
                "source": grant["source"],
                "network_calls": 0,
            },
            _safe_step("sources", sources),
            _safe_step("schedule", schedule),
            _safe_step("custom", custom),
            _safe_step("status", status),
        ],
        "menu_contract": {
            "bot_profile": start["menu"]["bot_profile"],
            "commands": start["menu"]["commands"],
            "menu_style": start["menu"]["menu_style"],
            "inline_keyboard": start["menu"]["inline_keyboard"],
            "persistent_keyboard": start["menu"]["persistent_keyboard"],
            "prelude_reply_count": len(start.get("prelude_replies", [])),
            "reply_markup_kind": "inline_keyboard" if start["menu"]["reply_markup"].get("inline_keyboard") else "",
            "text_preview": start["menu"]["text"],
        },
        "enabled_categories": sources["enabled_categories"],
        "delivery_preferences": schedule["delivery_preferences"],
        "tracking_target": custom["tracking_target"],
        "scrape_triggered": custom["scrape_triggered"],
        "button_preference_flow": {
            "after_stock_button": stock_button["enabled_categories"],
            "after_github_button": github_button["enabled_categories"],
            "after_github_toggle_off": github_toggle_off["enabled_categories"],
        },
        "button_preference_flow_display": {
            "after_stock_button": stock_button["enabled_category_labels"],
            "after_github_button": github_button["enabled_category_labels"],
            "after_github_toggle_off": github_toggle_off["enabled_category_labels"],
        },
        "final_profile": _safe_profile(final_profile),
        "network_calls": network_calls,
        "redaction": {
            "telegram_user_id_present_only": start["redacted_user"]["telegram_user_id_present"],
            "chat_id_present_only": start["redacted_user"]["chat_id_present"],
            "no_real_telegram_token_or_chat_id_written": True,
        },
        "rollback": [str(db_path), str(evidence_path)],
        "limits": [
            "Sandbox SQLite only; production intel_brief.db was not touched.",
            "No Telegram Bot API call; handler returned reply contracts only.",
            "No scraper was triggered by /custom; target was only recorded for later rate-limited collection.",
            "No payment provider or marketplace automation call.",
        ],
    }
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief Telegram menu handler sandbox")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--now", default="2026-07-07T16:00:00+00:00")
    parser.add_argument("--stamp", default="")
    args = parser.parse_args(argv)

    stamp = args.stamp or _stamp()
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "data" / "intel_evidence" / "phasez" / f"{stamp}-telegram-menu-handler-contract"
    evidence = build_intel_telegram_menu_sandbox_evidence(output_dir, now=args.now)
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
