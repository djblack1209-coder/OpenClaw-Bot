#!/usr/bin/env python3
"""X 自动运营发布入口。

文件名保留 morning 是为了兼容已安装 LaunchAgent；实际能力已升级为全天多时段发布。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.execution.social.x_auto_ops import (  # noqa: E402
    DEFAULT_DAILY_TIMES,
    build_daily_drafts,
    build_next_draft,
    get_next_reviewable_drafts,
    get_or_build_next_ready_draft,
    is_draft_approved,
    next_scheduled_at,
    parse_daily_times,
    require_draft_review,
    write_launchd_plist,
)


async def publish_once(use_existing_ready: bool = True) -> dict:
    """旧 CLI 发布入口永久 fail-closed，只返回待审草稿。"""
    draft = get_or_build_next_ready_draft() if use_existing_ready else build_next_draft()
    if not is_draft_approved(draft):
        return require_draft_review(draft)
    return {
        "success": False,
        "requires_final_confirmation": True,
        "external_actions_locked": True,
        "error": "CLI/LaunchAgent 发布已禁用；请在 App 或 Telegram 完成最终确认",
        "draft": draft,
    }


def pending_review(limit: int = 8) -> dict:
    """返回等待用户确认的人设/内容草稿。"""
    drafts = get_next_reviewable_drafts(limit=limit)
    return {"success": True, "requires_review": bool(drafts), "drafts": drafts, "count": len(drafts)}


def schedule_daily(times: list[tuple[int, int]] | None = None, posts_per_day: int = 6) -> dict:
    """生成全天多时段 launchd 草稿准备任务，不执行外部发布。"""
    daily_times = times or DEFAULT_DAILY_TIMES
    drafts = build_daily_drafts(count=max(posts_per_day, len(daily_times)))
    target = next_scheduled_at(daily_times)
    plist = write_launchd_plist(Path(__file__).resolve(), target_time=target, daily_times=daily_times)
    # 先卸载旧任务再加载新任务，保证修改生效。
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True, text=True, check=False)
    load = subprocess.run(["launchctl", "load", str(plist)], capture_output=True, text=True, check=False)
    return {
        "success": load.returncode == 0,
        "next_time": target.isoformat(),
        "times": [f"{h:02d}:{m:02d}" for h, m in daily_times],
        "drafts_prepared": len(drafts),
        "plist": str(plist),
        "stdout": load.stdout.strip(),
        "stderr": load.stderr.strip(),
        "returncode": load.returncode,
    }


# 兼容旧函数名。
def schedule_morning(hour: int = 8, minute: int = 30) -> dict:
    """兼容旧入口：注册单个早上发布时间。"""
    return schedule_daily(times=[(hour, minute)], posts_per_day=1)


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenClaw X 自动运营任务")
    parser.add_argument("--publish", action="store_true", help="旧参数：现已禁用，只返回待确认草稿")
    parser.add_argument("--publish-next", action="store_true", help="旧参数：现已禁用，只返回待确认草稿")
    parser.add_argument("--draft", action="store_true", help="只生成 1 条草稿不发布")
    parser.add_argument("--draft-count", type=int, default=6, help="生成多条草稿，默认 6 条")
    parser.add_argument("--pending-review", action="store_true", help="列出等待确认的人设/内容草稿")
    parser.add_argument("--schedule", action="store_true", help="注册自动发布任务")
    parser.add_argument("--schedule-daily", action="store_true", help="注册全天多时段自动发布任务")
    parser.add_argument("--posts-per-day", type=int, default=6, help="每天准备多少条内容，建议 5-8")
    parser.add_argument("--times", default="08:30,10:30,12:30,15:00,17:30,20:30", help="每日发布时间，逗号分隔")
    parser.add_argument("--hour", type=int, default=8, help="兼容旧单时段小时")
    parser.add_argument("--minute", type=int, default=30, help="兼容旧单时段分钟")
    args = parser.parse_args()

    if args.schedule_daily:
        print(json.dumps(schedule_daily(parse_daily_times(args.times), args.posts_per_day), ensure_ascii=False, indent=2))
        return 0
    if args.schedule:
        # 旧 --schedule 现在默认也升级为全天多时段；如果显式传 hour/minute，则保留单时段兼容。
        default_single = args.hour != 8 or args.minute != 30
        result = schedule_morning(args.hour, args.minute) if default_single else schedule_daily(parse_daily_times(args.times), args.posts_per_day)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.draft:
        count = max(1, args.draft_count)
        data = build_daily_drafts(count=count) if count > 1 else [build_next_draft()]
        print(json.dumps(data if count > 1 else data[0], ensure_ascii=False, indent=2))
        return 0
    if args.pending_review:
        print(json.dumps(pending_review(limit=args.draft_count), ensure_ascii=False, indent=2))
        return 0
    if args.publish or args.publish_next:
        print(json.dumps(asyncio.run(publish_once(use_existing_ready=True)), ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
