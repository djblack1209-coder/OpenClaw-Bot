"""每日简报 Telegram 用户旅程验收器。

这个脚本站在普通用户角度验收：/start → 点击/斜杠菜单 → 今日简报 → 我的订阅
→ 两步式改时间 → 添加追踪 → 暂停 → 查看暂停状态 → 选择内容恢复。
它只使用临时 SQLite，不调用 Telegram、不写真实用户。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
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

DEFAULT_OUTPUT = ROOT / "data" / "intel_evidence" / "phasefix" / "telegram-user-journey" / "acceptance.json"
DEFAULT_DB = ROOT / "data" / "intel_evidence" / "phasefix" / "telegram-user-journey" / "acceptance.sqlite3"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_reply_preview(text: str, limit: int = 140) -> str:
    cleaned = _clean(text).replace("\r", " ")
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def _step(name: str, result: dict[str, Any], *, ok: bool, expectation: str) -> dict[str, Any]:
    return {
        "step": name,
        "ok": bool(ok),
        "status": _clean(result.get("status")),
        "command": _clean(result.get("command")),
        "expectation": expectation,
        "reply_preview": _safe_reply_preview(_clean(result.get("reply_text"))),
        "reply_markup_present": bool(result.get("reply_markup")),
        "network_calls": int(result.get("network_calls", 0) or 0),
    }


def _seed_latest_delivery(db_path: Path, *, subscriber_id: int) -> None:
    """写入一条临时最近简报，验证“今日简报”真的展示内容。"""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO delivery_log (subscriber_id, delivered_at, content_summary, channel_type, success)
            VALUES (?, '2026-07-08T08:30:00+00:00', ?, 'telegram', 1)
            """,
            (
                subscriber_id,
                "今日简报样例：A股资金流偏强；AI 模型更新活跃；国会持仓有新披露。",
            ),
        )
        conn.commit()


def build_user_journey_acceptance(
    *,
    db_path: str | Path = DEFAULT_DB,
    output_path: str | Path = DEFAULT_OUTPUT,
    now: str = "2026-07-08T18:00:00+00:00",
) -> dict[str, Any]:
    """执行普通用户完整菜单旅程，并写入脱敏验收证据。"""
    db = Path(db_path)
    output = Path(output_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()

    user = TelegramUserContext(
        telegram_user_id="journey-user",
        chat_id="journey-chat",
        username="journey_tester",
    )

    start = handle_intel_telegram_command(db, user=user, command="/start", args=[], now=now)
    user_id = start["subscriber"]["user_id"]
    plan = upsert_subscription_plan(
        db,
        plan_name="intel_mvp_monthly",
        categories=DEFAULT_MVP_CATEGORIES,
        price_cents=9900,
        duration_type="monthly",
    )
    grant_subscription(
        db,
        user_id=user_id,
        plan_name=plan["plan_name"],
        starts_at="2026-07-08T00:00:00+00:00",
        expires_at="2026-08-08T00:00:00+00:00",
        source="telegram_user_journey_acceptance",
    )
    _seed_latest_delivery(db, subscriber_id=int(start["subscriber"]["subscriber_id"]))

    today = handle_intel_telegram_command(db, user=user, command="🧭 今日简报", args=[], now=now)
    slash_today = handle_intel_telegram_command(db, user=user, command="/today", args=[], now=now)
    status = handle_intel_telegram_command(db, user=user, command="📌 我的订阅", args=[], now=now)
    schedule_prompt = handle_intel_telegram_command(db, user=user, command="/schedule", args=[], now=now)
    schedule_quick = handle_intel_telegram_command(db, user=user, command="1", args=[], now=now)
    schedule_prompt_again = handle_intel_telegram_command(db, user=user, command="705", args=[], now=now)
    schedule_weekly = handle_intel_telegram_command(db, user=user, command="每周 08:30", args=[], now=now)
    custom = handle_intel_telegram_command(db, user=user, command="706 英伟达", args=[], now=now)
    custom_prompt = handle_intel_telegram_command(db, user=user, command="706", args=[], now=now)
    custom_follow_up = handle_intel_telegram_command(db, user=user, command="周杰伦", args=[], now=now)
    slash_market = handle_intel_telegram_command(db, user=user, command="/market", args=[], now=now)
    slash_ai = handle_intel_telegram_command(db, user=user, command="/ai", args=[], now=now)
    slash_weather = handle_intel_telegram_command(db, user=user, command="/weather", args=[], now=now)
    slash_track_prompt = handle_intel_telegram_command(db, user=user, command="/track", args=[], now=now)
    slash_track_follow_up = handle_intel_telegram_command(db, user=user, command="OpenEverything", args=[], now=now)
    pause = handle_intel_telegram_command(db, user=user, command="/pause", args=[], now=now)
    paused_status = handle_intel_telegram_command(db, user=user, command="701", args=[], now=now)
    paused_menu = handle_intel_telegram_command(db, user=user, command="/start", args=[], now=now)
    profile_after_passive_checks = get_subscription_profile(db, user_id=user_id, now=now)
    resume = handle_intel_telegram_command(db, user=user, command="702", args=[], now=now)
    final_profile = get_subscription_profile(db, user_id=user_id, now=now)

    start_keyboard = start.get("menu", {}).get("persistent_keyboard") if isinstance(start.get("menu"), dict) else []
    steps = [
        _step(
            "打开菜单 /start",
            start,
            ok=start.get("status") == "success"
            and "700 今日简报" in _clean(start.get("reply_text"))
            and "可点击按钮" in _clean(start.get("reply_text"))
            and start_keyboard == [["🧭 今日简报", "📌 我的订阅"]],
            expectation="Telegram 用户优先看到可点击按钮，数字只是备用入口。",
        ),
        _step(
            "点今日简报",
            today,
            ok=today.get("command") == "today" and "今日简报样例" in _clean(today.get("reply_text")),
            expectation="用户点今日简报后看到最近简报内容，不是又打开一遍菜单。",
        ),
        _step(
            "清聊天后点左侧命令 /today",
            slash_today,
            ok=slash_today.get("command") == "today" and "今日简报样例" in _clean(slash_today.get("reply_text")),
            expectation="清理聊天记录后，Telegram 左侧斜杠菜单仍能进入今日简报。",
        ),
        _step(
            "点我的订阅",
            status,
            ok=status.get("command") == "status" and "订阅状态" in _clean(status.get("reply_text")),
            expectation="用户能看懂自己是否开通、选了什么、几点推送。",
        ),
        _step(
            "点推送时间 /schedule → 回复 1",
            schedule_quick,
            ok=schedule_prompt.get("status") == "prompt"
            and "回复数字即可设置" in _clean(schedule_prompt.get("reply_text"))
            and schedule_quick.get("delivery_preferences", {}).get("delivery_time") == "08:30",
            expectation="小白用户不用记格式，点推送时间后回复数字就能设置。",
        ),
        _step(
            "数字备用 705 → 回复 每周 08:30",
            schedule_weekly,
            ok=schedule_prompt_again.get("status") == "prompt"
            and schedule_weekly.get("delivery_preferences", {}).get("frequency") == "weekly"
            and schedule_weekly.get("delivery_preferences", {}).get("delivery_time") == "08:30",
            expectation="数字备用菜单也支持自然语言式频率和时间。",
        ),
        _step(
            "左侧命令 /market /ai /weather",
            slash_weather,
            ok=slash_market.get("command") == "sources"
            and slash_ai.get("command") == "sources"
            and slash_weather.get("command") == "sources"
            and "天气" in _clean(slash_weather.get("reply_text")),
            expectation="Telegram 左侧命令菜单与按钮菜单保持同一批核心功能。",
        ),
        _step(
            "添加追踪 706 英伟达",
            custom,
            ok=custom.get("command") == "custom" and custom.get("tracking_target", {}).get("name") == "英伟达",
            expectation="用户按编号加追踪对象，系统确认已添加。",
        ),
        _step(
            "两步式添加追踪 706→周杰伦",
            custom_follow_up,
            ok=custom_prompt.get("command") == "custom"
            and custom_prompt.get("status") == "prompt"
            and "下一条直接回复" in _clean(custom_prompt.get("reply_text"))
            and custom_follow_up.get("command") == "custom"
            and custom_follow_up.get("tracking_target", {}).get("name") == "周杰伦",
            expectation="用户先回复 706 后，下一条直接发名字也能添加追踪，不需要记完整格式。",
        ),
        _step(
            "左侧命令 /track → OpenEverything",
            slash_track_follow_up,
            ok=slash_track_prompt.get("status") == "prompt"
            and slash_track_follow_up.get("tracking_target", {}).get("name") == "OpenEverything",
            expectation="清聊天后用户也能通过左侧命令添加追踪。",
        ),
        _step(
            "暂停简报 708",
            pause,
            ok=pause.get("command") == "pause" and pause.get("subscriber_status") == "paused",
            expectation="用户能暂停每日推送。",
        ),
        _step(
            "暂停后查看状态 701",
            paused_status,
            ok=paused_status.get("profile", {}).get("status") == "paused"
            and "已暂停" in _clean(paused_status.get("reply_text")),
            expectation="暂停后看状态，不会偷偷恢复。",
        ),
        _step(
            "暂停后打开菜单 /start",
            paused_menu,
            ok=profile_after_passive_checks.get("status") == "paused"
            and "当前状态：已暂停" in _clean(paused_menu.get("reply_text")),
            expectation="暂停后只是打开菜单，也不会偷偷恢复。",
        ),
        _step(
            "选择市场资金 702 恢复",
            resume,
            ok=resume.get("command") == "sources" and final_profile.get("status") == "active",
            expectation="用户明确重新选择内容时，系统恢复每日推送。",
        ),
    ]
    failed = [item for item in steps if not item["ok"]]
    report = {
        "timestamp": _now_iso(),
        "phase": "telegram-user-journey-acceptance",
        "scope": "start_today_status_schedule_custom_pause_resume",
        "status": "verified" if not failed else "needs_attention",
        "verified": not failed,
        "steps": steps,
        "summary": {
            "total_steps": len(steps),
            "passed_steps": len(steps) - len(failed),
            "failed_steps": len(failed),
            "final_subscription_status": final_profile.get("status"),
            "final_frequency": final_profile.get("delivery_preferences", {}).get("frequency"),
            "final_delivery_time": final_profile.get("delivery_preferences", {}).get("delivery_time"),
            "final_enabled_categories": final_profile.get("enabled_categories"),
        },
        "redaction": {
            "uses_sandbox_db_only": True,
            "real_telegram_network_calls": 0,
            "raw_telegram_token_written": False,
            "raw_chat_id_written": False,
            "raw_user_id_written": False,
            "raw_message_text_written": False,
        },
        "limits": [
            "这是本地临时库用户旅程验收，不调用真实 Telegram。",
            "真实 /start 发送已由 start-menu-acceptance.json 验收；本脚本补齐菜单后续操作体验。",
            "微信只覆盖编号命令代码路径；飞书/钉钉仍未接真实 webhook/token。",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Intel Brief Telegram user journey without real network")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--now", default="2026-07-08T18:00:00+00:00")
    args = parser.parse_args(argv)

    report = build_user_journey_acceptance(db_path=args.db, output_path=args.output, now=args.now)
    print(
        json.dumps(
            {
                "status": report["status"],
                "verified": report["verified"],
                "summary": report["summary"],
                "output": args.output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
