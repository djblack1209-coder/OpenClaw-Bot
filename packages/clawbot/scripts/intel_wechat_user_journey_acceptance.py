"""每日简报微信用户旅程验收器。

这个脚本站在普通微信用户角度验收编号菜单：菜单 → 700 → 701 → 705 两步式
→ 706 两步式 → 708 暂停 → 702 恢复。它只使用临时 SQLite，不调用微信网络、
不读取真实聊天、不写真实用户。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.routers.wechat import WeChatIncomingRequest, wechat_incoming  # noqa: E402
from src.intel.subscriptions import DEFAULT_MVP_CATEGORIES, grant_subscription, upsert_subscription_plan  # noqa: E402

DEFAULT_OUTPUT = ROOT / "data" / "intel_evidence" / "phasefix" / "wechat-user-journey" / "acceptance.json"
DEFAULT_DB = ROOT / "data" / "intel_evidence" / "phasefix" / "wechat-user-journey" / "acceptance.sqlite3"


def _now_iso() -> str:
    """返回当前 UTC 时间字符串。"""
    return datetime.now(UTC).isoformat()


def _clean(value: Any) -> str:
    """把任意值转成去空白字符串。"""
    return str(value or "").strip()


def _preview(text: str, limit: int = 160) -> str:
    """生成脱敏短预览，避免证据文件太长。"""
    cleaned = _clean(text).replace("\r", " ")
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


async def _send(from_user: str, text: str) -> str:
    """调用本地微信 handler，模拟用户发送一条微信文字。"""
    response = await wechat_incoming(WeChatIncomingRequest(from_user=from_user, text=text))
    return response.reply


def _step(name: str, text: str, reply: str, *, ok: bool, expectation: str) -> dict[str, Any]:
    """构造单步验收结果。"""
    return {
        "step": name,
        "sent": text,
        "ok": bool(ok),
        "expectation": expectation,
        "reply_preview": _preview(reply),
    }


def _seed_active_subscription(db_path: Path, *, user_id: str = "wechat:wechat-journey-user") -> None:
    """准备临时订阅与最近简报，确保 700/701 路径像真实用户一样可读。"""
    upsert_subscription_plan(
        db_path,
        plan_name="intel_mvp_monthly",
        categories=DEFAULT_MVP_CATEGORIES,
        price_cents=9900,
        duration_type="monthly",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO subscribers (user_id, channel_type, channel_user_id, status, updated_at)
            VALUES (?, 'wechat', 'wechat-journey-user', 'active', CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                channel_type='wechat',
                channel_user_id=excluded.channel_user_id,
                status='active',
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id,),
        )
        subscriber_id = int(conn.execute("SELECT id FROM subscribers WHERE user_id=?", (user_id,)).fetchone()[0])
        conn.commit()
    grant_subscription(
        db_path,
        user_id=user_id,
        plan_name="intel_mvp_monthly",
        starts_at="2026-07-08T00:00:00+00:00",
        expires_at="2026-08-08T00:00:00+00:00",
        source="wechat_user_journey_acceptance",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO delivery_log (subscriber_id, delivered_at, content_summary, channel_type, success)
            VALUES (?, '2026-07-08T08:30:00+00:00', ?, 'wechat', 1)
            """,
            (
                subscriber_id,
                "今日简报样例：A股资金流偏强；AI 模型更新活跃；天气预警正常。",
            ),
        )
        conn.commit()


async def build_wechat_user_journey_acceptance(
    *,
    db_path: str | Path = DEFAULT_DB,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    """执行微信编号菜单用户旅程，并写入脱敏验收证据。"""
    db = Path(db_path)
    output = Path(output_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    os.environ["INTEL_BRIEF_DB_PATH"] = str(db)

    from_user = "wechat-journey-user"
    _seed_active_subscription(db)

    menu = await _send(from_user, "菜单")
    today_text = await _send(from_user, "今日简报")
    status_text = await _send(from_user, "我的订阅")
    today = await _send(from_user, "700")
    status = await _send(from_user, "701")
    schedule_prompt = await _send(from_user, "705")
    schedule_menu_escape = await _send(from_user, "菜单")
    schedule_prompt_after_escape = await _send(from_user, "705")
    schedule_quick = await _send(from_user, "2")
    schedule_prompt_again = await _send(from_user, "705")
    schedule_weekly = await _send(from_user, "每周 09:00")
    custom_prompt = await _send(from_user, "706")
    custom_today_escape = await _send(from_user, "今日简报")
    custom_prompt_after_escape = await _send(from_user, "706")
    custom_follow = await _send(from_user, "英伟达")
    pause = await _send(from_user, "708")
    paused_status = await _send(from_user, "701")
    resume = await _send(from_user, "702")
    final_status = await _send(from_user, "701")

    steps = [
        _step("打开菜单", "菜单", menu, ok="发数字编号即可快速操作" in menu and "700 每日简报" in menu, expectation="微信没有点击菜单，所以先告诉用户回复数字即可。"),
        _step("中文快捷今日简报", "今日简报", today_text, ok="今日简报样例" in today_text or "700 今日简报" in today_text, expectation="用户不记数字也能看今日简报。"),
        _step("中文快捷我的订阅", "我的订阅", status_text, ok="订阅状态" in status_text and "推送时间" in status_text, expectation="用户不记数字也能查看订阅。"),
        _step("查看今日简报", "700", today, ok="今日简报样例" in today or "700 今日简报" in today, expectation="用户回复 700 后进入每日简报，不落到普通聊天。"),
        _step("查看我的订阅", "701", status, ok="订阅状态" in status and "推送时间" in status, expectation="用户能看懂当前订阅和推送时间。"),
        _step("推送时间两步式提示", "705", schedule_prompt, ok="回复数字即可设置" in schedule_prompt, expectation="用户只发 705 时，系统提示下一条回复数字。"),
        _step("推送时间中途打开菜单", "菜单", schedule_menu_escape, ok="发数字编号即可快速操作" in schedule_menu_escape and "700 每日简报" in schedule_menu_escape, expectation="用户中途发菜单应跳转菜单，不会把菜单当成时间。"),
        _step("推送时间恢复两步式", "705", schedule_prompt_after_escape, ok="回复数字即可设置" in schedule_prompt_after_escape, expectation="菜单跳转后，再发 705 仍能继续设置。"),
        _step("推送时间快捷选择", "2", schedule_quick, ok="09:00" in schedule_quick and "已设置" in schedule_quick, expectation="用户回复 2 能完成设置。"),
        _step("推送时间自然语言", "每周 09:00", schedule_weekly, ok="每周 09:00" in schedule_weekly and "已设置" in schedule_weekly and "回复数字即可设置" in schedule_prompt_again, expectation="用户能用人话设置每周 09:00。"),
        _step("添加追踪两步式提示", "706", custom_prompt, ok="下一条直接回复名字" in custom_prompt, expectation="用户只发 706 时，不要求记完整格式。"),
        _step("添加追踪中途看简报", "今日简报", custom_today_escape, ok="今日简报样例" in custom_today_escape or "700 今日简报" in custom_today_escape, expectation="用户中途发今日简报应跳转，不会把今日简报当成追踪词。"),
        _step("添加追踪恢复两步式", "706", custom_prompt_after_escape, ok="下一条直接回复名字" in custom_prompt_after_escape, expectation="跳转后重新发 706 仍可添加追踪。"),
        _step("添加追踪对象", "英伟达", custom_follow, ok="已添加追踪：英伟达" in custom_follow, expectation="用户下一条直接发名字即可完成追踪。"),
        _step("暂停简报", "708", pause, ok="已暂停每日简报" in pause, expectation="用户可以随时暂停。"),
        _step("暂停后查看状态", "701", paused_status, ok="paused" in paused_status or "已暂停" in paused_status or "暂停" in paused_status, expectation="被动查看状态不会偷偷恢复推送。"),
        _step("选择内容恢复", "702", resume, ok="市场资金" in resume and "已开启" in resume, expectation="用户重新选择内容时恢复 active。"),
        _step("恢复后查看状态", "701", final_status, ok="订阅状态：active" in final_status or "订阅状态：已开通" in final_status, expectation="恢复后状态回到可推送。"),
    ]
    failed = [item for item in steps if not item["ok"]]
    result = {
        "verified": not failed,
        "checked_at": _now_iso(),
        "scope": "local_wechat_handler_user_journey",
        "real_wechat_network_calls": 0,
        "real_wechat_inbound_verified": False,
        "passed_steps": len(steps) - len(failed),
        "failed_steps": failed,
        "steps": steps,
        "notes": [
            "本验收只证明本项目微信编号菜单处理器闭环，不代表真实微信入站网络已打通。",
            "真实微信闭环还需要 OpenClaw Weixin 插件收到用户消息后路由到本项目处理器。",
        ],
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="每日简报微信编号菜单用户旅程验收")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="临时 SQLite 路径")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="证据 JSON 输出路径")
    args = parser.parse_args()
    result = asyncio.run(build_wechat_user_journey_acceptance(db_path=args.db, output_path=args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("verified") else 1


if __name__ == "__main__":
    raise SystemExit(main())
