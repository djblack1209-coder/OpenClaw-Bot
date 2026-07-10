"""每日简报 Telegram /start 菜单真人验收器。

老板只需要在 Telegram 给机器人发送 /start；本脚本读取常驻监听器的脱敏心跳，
判断菜单是否真的发送成功。脚本不读取、不保存 Telegram 聊天内容、chat id、用户 id 或 token。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]

DEFAULT_HEARTBEAT = ROOT / "data" / "intel_evidence" / "phasefix" / "telegram-listener" / "heartbeat.json"
DEFAULT_OUTPUT = ROOT / "data" / "intel_evidence" / "phasefix" / "telegram-listener" / "start-menu-acceptance.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _parse_iso(value: str) -> datetime | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    try:
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_json_dict(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def evaluate_start_menu_acceptance(
    heartbeat: dict[str, Any],
    *,
    since: str = "",
    max_heartbeat_age_seconds: int = 90,
    now: str | None = None,
) -> dict[str, Any]:
    """根据脱敏心跳判断 /start 菜单是否已真人验收通过。"""
    checked_at = now or _now_iso()
    checked_dt = _parse_iso(checked_at) or datetime.now(timezone.utc)
    updated_at = _clean(heartbeat.get("updated_at"))
    updated_dt = _parse_iso(updated_at)
    success_at = _clean(heartbeat.get("last_start_menu_success_at"))
    success_dt = _parse_iso(success_at)
    since_dt = _parse_iso(since)

    heartbeat_age_seconds: int | None = None
    if updated_dt is not None:
        heartbeat_age_seconds = max(0, int((checked_dt - updated_dt).total_seconds()))

    listener_fresh = heartbeat_age_seconds is not None and heartbeat_age_seconds <= max(10, int(max_heartbeat_age_seconds or 90))
    success_after_since = bool(success_dt and (since_dt is None or success_dt >= since_dt))
    menu_shape_ok = bool(heartbeat.get("last_start_menu_inline_keyboard_sent")) and bool(
        heartbeat.get("last_start_menu_persistent_keyboard_sent")
    )
    raw_safe = heartbeat.get("raw_updates_persisted") is False and heartbeat.get("last_start_menu_raw_content_persisted") is False
    send_ok = success_after_since and menu_shape_ok and raw_safe

    blockers: list[str] = []
    if not heartbeat:
        blockers.append("还没有监听器心跳，请先确认 Telegram 监听器已启动")
    if heartbeat and not listener_fresh:
        blockers.append("监听器心跳不新鲜，可能没有在运行")
    if not success_after_since:
        blockers.append("还没看到你刚发的 /start 菜单成功证据")
    if success_after_since and not menu_shape_ok:
        blockers.append("/start 有回复，但没有同时带按钮菜单")
    if success_after_since and not raw_safe:
        blockers.append("验收证据安全边界异常：不应保存原始聊天内容")

    verified = listener_fresh and send_ok and not blockers
    next_action = "已验收：Telegram /start 菜单可用。" if verified else "请在 Telegram 给每日简报机器人发送 /start，然后重新运行本验收器。"
    return {
        "checked_at": checked_at,
        "status": "verified" if verified else "waiting_for_start",
        "verified": verified,
        "listener_fresh": listener_fresh,
        "heartbeat_updated_at": updated_at,
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "last_status": _clean(heartbeat.get("last_status")),
        "last_start_menu_success_at": success_at,
        "last_start_menu_success_after_since": success_after_since,
        "last_start_menu_inline_keyboard_sent": bool(heartbeat.get("last_start_menu_inline_keyboard_sent")),
        "last_start_menu_persistent_keyboard_sent": bool(heartbeat.get("last_start_menu_persistent_keyboard_sent")),
        "last_start_menu_reply_message_count": int(heartbeat.get("last_start_menu_reply_message_count", 0) or 0),
        "raw_updates_persisted": bool(heartbeat.get("raw_updates_persisted")),
        "last_start_menu_raw_content_persisted": bool(heartbeat.get("last_start_menu_raw_content_persisted")),
        "blockers": blockers,
        "next_action": next_action,
        "redaction": {
            "chat_id_persisted": False,
            "telegram_user_id_persisted": False,
            "token_persisted": False,
            "message_text_persisted": False,
        },
    }


def wait_for_start_menu_acceptance(
    *,
    heartbeat_path: str | Path = DEFAULT_HEARTBEAT,
    since: str = "",
    timeout_seconds: int = 0,
    poll_interval_seconds: float = 2.0,
    max_heartbeat_age_seconds: int = 90,
) -> dict[str, Any]:
    """等待 /start 菜单验收通过，超时则返回当前缺口。"""
    deadline = time.monotonic() + max(0, int(timeout_seconds or 0))
    latest: dict[str, Any] = {}
    while True:
        heartbeat = _read_json_dict(heartbeat_path)
        latest = evaluate_start_menu_acceptance(
            heartbeat,
            since=since,
            max_heartbeat_age_seconds=max_heartbeat_age_seconds,
        )
        if latest["verified"]:
            return latest
        if int(timeout_seconds or 0) <= 0 or time.monotonic() >= deadline:
            return latest
        time.sleep(max(0.5, float(poll_interval_seconds or 2.0)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Intel Brief Telegram /start menu acceptance from redacted heartbeat")
    parser.add_argument("--heartbeat", default=str(DEFAULT_HEARTBEAT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--since", default="", help="Only accept /start success after this ISO timestamp")
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--max-heartbeat-age-seconds", type=int, default=90)
    args = parser.parse_args(argv)

    result = wait_for_start_menu_acceptance(
        heartbeat_path=args.heartbeat,
        since=args.since,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        max_heartbeat_age_seconds=args.max_heartbeat_age_seconds,
    )
    _write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
