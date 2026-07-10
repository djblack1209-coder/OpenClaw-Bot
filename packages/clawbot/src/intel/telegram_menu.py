"""Telegram command handler contract for Intel Brief MVP.

This module intentionally does not import Telegram SDKs or call Bot API.  It
turns Telegram-shaped user input into subscription/profile mutations and
redaction-safe reply contracts that can be wired to the 8th bot later.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.intel.channel_menu import (
    CALLBACK_TO_NUMBER,
    build_schedule_prompt_text,
    handle_numbered_intel_command,
    parse_intel_schedule_text,
)
from src.intel.db.store import subscribe_tracking_target
from src.intel.subscriptions import (
    build_telegram_menu_contract,
    get_subscription_profile,
    set_delivery_preferences,
    set_source_preferences,
    upsert_telegram_subscriber,
)


@dataclass(frozen=True)
class TelegramUserContext:
    """Minimal Telegram user identity required by Intel Brief handlers."""

    telegram_user_id: str
    chat_id: str
    username: str = ""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _command_name(command: str) -> str:
    cleaned = _clean(command).lower()
    if cleaned.startswith("/"):
        cleaned = cleaned[1:]
    if len(cleaned) >= 3 and cleaned[:3].isdigit() and (len(cleaned) == 3 or cleaned[3].isspace()):
        return cleaned.split(maxsplit=1)[0]
    return cleaned.split("@", 1)[0]


def _args(values: list[str] | tuple[str, ...] | None) -> list[str]:
    return [_clean(value) for value in (values or []) if _clean(value)]


def _parse_schedule_args(values: list[str]) -> tuple[str, str, str]:
    """兼容普通用户只输入时间的写法，例如 /schedule 09:00。"""
    return parse_intel_schedule_text(" ".join(values))


def _subscription_status_label(status: Any) -> str:
    """把内部状态翻译成普通用户看得懂的话。"""
    mapping = {
        "active": "已开通",
        "inactive_or_expired": "未开通或已到期",
        "not_found": "未开通",
        "paused": "已暂停",
    }
    cleaned = _clean(status)
    return mapping.get(cleaned, cleaned or "未知")


def _numbered_command_reactivates(number: int, args: list[str]) -> bool:
    """判断用户这个动作是不是在明确恢复每日推送。"""
    return int(number) in {702, 703, 704} or (int(number) == 706 and bool(" ".join(args).strip()))


SLASH_TO_NUMBER = {
    "today": 700,
    "market": 702,
    "ai": 703,
    "weather": 704,
    "track": 706,
    "pause": 708,
}


def _telegram_command_reactivates(raw_cmd: str, parsed_args: list[str]) -> bool:
    """只有用户明确选择内容/追踪对象时，才从暂停状态恢复。"""
    if raw_cmd in CALLBACK_TO_NUMBER:
        return _numbered_command_reactivates(CALLBACK_TO_NUMBER[raw_cmd], parsed_args)
    if raw_cmd in SLASH_TO_NUMBER:
        return _numbered_command_reactivates(SLASH_TO_NUMBER[raw_cmd], parsed_args)
    if raw_cmd.isdigit() and int(raw_cmd) in CALLBACK_TO_NUMBER.values():
        return _numbered_command_reactivates(int(raw_cmd), parsed_args)
    if raw_cmd in MENU_BUTTON_CATEGORY_MAP:
        return True
    if raw_cmd in {"sources"} and parsed_args:
        return True
    return bool(raw_cmd == "custom" and parsed_args)


MENU_BUTTON_CATEGORY_MAP = {
    "github": ["github_trending"],
    "openai": ["ai_model_updates"],
    "claude": ["ai_model_updates"],
    "deepseek": ["ai_model_updates"],
    "微博": ["weibo"],
    "小红书": ["xiaohongshu"],
    "抖音": ["douyin"],
    "知乎": ["zhihu"],
    "b站": ["bilibili"],
    "bilibili": ["bilibili"],
    "天气": ["weather"],
    "空气": ["air_quality"],
    "air_quality": ["air_quality"],
    "降雨": ["rainfall"],
    "rainfall": ["rainfall"],
    "温度": ["temperature"],
    "temperature": ["temperature"],
    "湿度": ["humidity"],
    "humidity": ["humidity"],
    "灾害": ["disaster_alerts"],
    "disaster_alerts": ["disaster_alerts"],
    "投行": ["institutional_13f"],
    "科技": ["tech"],
    "股市": ["akshare", "senate_trading", "institutional_13f"],
    "加密": ["crypto"],
    "market": ["akshare", "senate_trading", "institutional_13f"],
    "ai_tech": ["ai_model_updates", "github_trending"],
    "weather_alerts": ["air_quality", "disaster_alerts", "humidity", "rainfall", "temperature", "weather"],
}

MENU_BUTTON_PROMPTS = {
    "search": ("search", "请直接发送关键词，我会按你的订阅范围检索相关情报。"),
    "🔍 备用搜索": ("search", "请直接发送关键词，我会按你的订阅范围检索相关情报。"),
    "🔍备用搜索": ("search", "请直接发送关键词，我会按你的订阅范围检索相关情报。"),
    "备用搜索": ("search", "请直接发送关键词，我会按你的订阅范围检索相关情报。"),
    "🔍 情报搜索": ("search", "请直接发送关键词，我会按你的订阅范围检索相关情报。"),
    "情报搜索": ("search", "请直接发送关键词，我会按你的订阅范围检索相关情报。"),
    "custom": ("custom", "请回复：706 周杰伦  来添加你想追踪的人、公司或项目。"),
    "自定义": ("custom", "请回复：706 周杰伦  来添加你想追踪的人、公司或项目。"),
    "🔎 自定义": ("custom", "请回复：706 周杰伦  来添加你想追踪的人、公司或项目。"),
    "schedule": ("schedule", "默认每天 08:30 推送。如需调整，请回复：705 09:00。"),
    "定时": ("schedule", "默认每天 08:30 推送。如需调整，请回复：705 09:00。"),
    "⏰ 定时": ("schedule", "默认每天 08:30 推送。如需调整，请回复：705 09:00。"),
}

MENU_BUTTON_COMMANDS = {
    "设置": "status",
    "settings": "status",
    "订阅": "status",
    "status": "status",
    "状态": "status",
    "👥 设置导航": "start",
    "设置导航": "start",
    "👥 功能导航": "start",
    "功能导航": "start",
    "🔥 热搜排行": "start",
    "🔥热搜排行": "start",
    "热搜排行": "start",
    "help": "help",
}

CATEGORY_DISPLAY_NAMES = {
    "github_trending": "GitHub趋势",
    "ai_model_updates": "AI模型动态",
    "weibo": "微博",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "zhihu": "知乎",
    "bilibili": "B站",
    "weather": "天气",
    "air_quality": "空气质量",
    "rainfall": "降雨",
    "temperature": "温度",
    "humidity": "湿度",
    "disaster_alerts": "灾害预警",
    "institutional_13f": "机构13F持仓",
    "tech": "科技",
    "akshare": "A股资金流向",
    "senate_trading": "国会持仓",
    "crypto": "加密",
}


def _category_display_name(category: str) -> str:
    cleaned = _clean(category)
    return CATEGORY_DISPLAY_NAMES.get(cleaned, cleaned)


def _category_display_text(categories: list[str] | tuple[str, ...] | None) -> str:
    labels = [_category_display_name(category) for category in (categories or []) if _clean(category)]
    return "、".join(labels) if labels else "未设置"


def _redacted_user(user: TelegramUserContext) -> dict[str, bool]:
    return {
        "telegram_user_id_present": bool(_clean(user.telegram_user_id)),
        "chat_id_present": bool(_clean(user.chat_id)),
    }


def _redacted_subscriber(subscriber: dict[str, Any]) -> dict[str, Any]:
    return {
        "subscriber_id": subscriber["subscriber_id"],
        "user_id": subscriber["user_id"],
        "channel_type": subscriber["channel_type"],
        "channel_user_id_present": bool(_clean(subscriber.get("channel_user_id"))),
    }


def _base_result(command: str, user: TelegramUserContext, subscriber: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": command,
        "network_calls": 0,
        "redacted_user": _redacted_user(user),
        "subscriber": _redacted_subscriber(subscriber),
    }


def _status_text(profile: dict[str, Any]) -> str:
    categories = _category_display_text(profile.get("enabled_categories") or [])
    delivery = profile.get("delivery_preferences") or {}
    lines = [
        f"订阅状态：{_subscription_status_label(profile.get('status', 'inactive_or_expired'))}",
        f"套餐：{profile.get('plan_name') or '未授权'}",
        f"到期时间：{profile.get('expires_at') or '无'}",
        f"已启用分类：{categories}",
        "推送："
        f"{delivery.get('frequency', 'daily')} "
        f"{delivery.get('delivery_time', '08:30')} "
        f"{delivery.get('timezone', 'America/Denver')}",
    ]
    return "\n".join(lines)


def _ensure_pending_actions_table(db_path: str | Path) -> None:
    """创建 Telegram 两步式操作状态表，兼容已有生产库。"""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_pending_actions (
                user_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _set_pending_action(db_path: str | Path, *, user_id: str, action: str) -> None:
    """记录用户下一条普通文字应该接着完成哪个操作。"""
    _ensure_pending_actions_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO telegram_pending_actions (user_id, action, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                action=excluded.action,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, action),
        )
        conn.commit()


def _get_pending_action(db_path: str | Path, *, user_id: str) -> str:
    """读取用户当前等待中的两步式操作。"""
    _ensure_pending_actions_table(db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT action FROM telegram_pending_actions WHERE user_id=?", (user_id,)).fetchone()
    return _clean(row[0]) if row else ""


def _clear_pending_action(db_path: str | Path, *, user_id: str) -> None:
    """清理用户两步式操作状态，避免下一条消息被误吃。"""
    _ensure_pending_actions_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM telegram_pending_actions WHERE user_id=?", (user_id,))
        conn.commit()


def _tracking_prompt_text() -> str:
    """返回给小白用户看的添加追踪提示。"""
    return "\n".join(
        [
            "你想追踪谁？",
            "下一条直接回复名字就行，例如：英伟达",
            "也可以复制完整格式：706 英伟达 / 706 周杰伦",
            "想取消就回复：取消。",
        ]
    )


def _schedule_prompt_text() -> str:
    """返回给小白用户看的推送时间设置提示。"""
    return build_schedule_prompt_text()


def _is_known_plain_command(raw_cmd: str) -> bool:
    """判断一条普通文字是不是菜单命令，而不是追踪词。"""
    if raw_cmd in CALLBACK_TO_NUMBER:
        return True
    if raw_cmd in SLASH_TO_NUMBER:
        return True
    if raw_cmd.isdigit() and int(raw_cmd) in CALLBACK_TO_NUMBER.values():
        return True
    return raw_cmd in MENU_BUTTON_CATEGORY_MAP or raw_cmd in MENU_BUTTON_PROMPTS or raw_cmd in MENU_BUTTON_COMMANDS


def _tracking_success_result(
    db_path: str | Path,
    *,
    base: dict[str, Any],
    subscriber: dict[str, Any],
    user: TelegramUserContext,
    target_name: str,
    source_channel: str,
) -> dict[str, Any]:
    """添加追踪对象并返回脱敏结果。"""
    target = subscribe_tracking_target(
        db_path,
        user_id=subscriber["user_id"],
        channel_type="telegram",
        channel_user_id=user.chat_id,
        target_name=target_name,
        source_channel=source_channel,
    )
    safe_target = {
        "name": target["name"],
        "normalized_name": target["normalized_name"],
        "active_subscription_count": target["active_subscription_count"],
    }
    return {
        **base,
        "command": "custom",
        "status": "success",
        "reply_text": f"✅ 已添加追踪：{target['name']}。以后简报会优先关注它。",
        "tracking_target": safe_target,
        "scrape_triggered": False,
    }


def _with_tracking_prompt(
    db_path: str | Path,
    *,
    user_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """把添加追踪提示升级成两步式，并保存等待状态。"""
    _set_pending_action(db_path, user_id=user_id, action="custom")
    return {**result, "status": "prompt", "command": "custom", "reply_text": _tracking_prompt_text()}


def _with_schedule_prompt(
    db_path: str | Path,
    *,
    user_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """保存两步式推送时间设置状态。"""
    _set_pending_action(db_path, user_id=user_id, action="schedule")
    return {**result, "status": "prompt", "command": "schedule", "reply_text": _schedule_prompt_text()}


def _schedule_success_result(
    db_path: str | Path,
    *,
    base: dict[str, Any],
    subscriber: dict[str, Any],
    schedule_text: str,
) -> dict[str, Any]:
    """按用户的小白输入更新推送频率和时间。"""
    frequency, delivery_time, timezone = parse_intel_schedule_text(schedule_text)
    preferences = set_delivery_preferences(
        db_path,
        user_id=subscriber["user_id"],
        frequency=frequency,
        delivery_time=delivery_time,
        timezone=timezone,
    )
    frequency_label = "每周" if preferences["frequency"] == "weekly" else "每天"
    return {
        **base,
        "command": "schedule",
        "status": "success",
        "reply_text": f"✅ 推送时间已设置：{frequency_label} {preferences['delivery_time']}（{preferences['timezone']}）。",
        "delivery_preferences": preferences,
    }


def handle_intel_telegram_command(
    db_path: str | Path,
    *,
    user: TelegramUserContext,
    command: str,
    args: list[str] | tuple[str, ...] | None = None,
    now: str = "9999-12-31T00:00:00+00:00",
) -> dict[str, Any]:
    """Handle an Intel Brief Telegram command without performing network I/O."""
    raw_cmd = _command_name(command)
    is_slash_command = _clean(command).startswith("/")
    parsed_args = _args(args)
    raw_text = _clean(command)
    if len(raw_text) >= 3 and raw_text[:3].isdigit() and (len(raw_text) == 3 or raw_text[3].isspace()):
        parts = raw_text.split(maxsplit=1)
        if len(parts) == 2 and not parsed_args:
            parsed_args = [parts[1]]
    subscriber = upsert_telegram_subscriber(
        db_path,
        telegram_user_id=user.telegram_user_id,
        chat_id=user.chat_id,
        reactivate=_telegram_command_reactivates(raw_cmd, parsed_args),
    )
    pending_action = _get_pending_action(db_path, user_id=subscriber["user_id"]) if not is_slash_command else ""
    if pending_action == "schedule" and raw_text:
        if raw_cmd in {"0", "取消", "cancel", "算了", "不用了"}:
            _clear_pending_action(db_path, user_id=subscriber["user_id"])
            return {
                **_base_result("schedule", user, subscriber),
                "status": "success",
                "reply_text": "已取消修改推送时间。需要时再点“推送时间”或回复 705。",
            }
        if not _is_known_plain_command(raw_cmd) or raw_cmd in {"1", "2", "3", "4", "5"}:
            _clear_pending_action(db_path, user_id=subscriber["user_id"])
            return _schedule_success_result(
                db_path,
                base=_base_result("schedule", user, subscriber),
                subscriber=subscriber,
                schedule_text=raw_text,
            )
    if not is_slash_command and raw_text and _get_pending_action(db_path, user_id=subscriber["user_id"]) == "custom":
        if raw_cmd in {"取消", "cancel", "算了", "不用了"}:
            _clear_pending_action(db_path, user_id=subscriber["user_id"])
            return {
                **_base_result("custom", user, subscriber),
                "status": "success",
                "reply_text": "已取消添加追踪。需要时再回复 706。",
            }
        if not _is_known_plain_command(raw_cmd):
            _clear_pending_action(db_path, user_id=subscriber["user_id"])
            return _tracking_success_result(
                db_path,
                base=_base_result("custom", user, subscriber),
                subscriber=subscriber,
                user=user,
                target_name=raw_text,
                source_channel="telegram_pending_custom",
            )
    if not is_slash_command and raw_cmd in CALLBACK_TO_NUMBER:
        numbered = handle_numbered_intel_command(
            db_path,
            channel="telegram",
            external_user_id=user.telegram_user_id,
            channel_user_id=user.chat_id,
            number=CALLBACK_TO_NUMBER[raw_cmd],
            arg=" ".join(parsed_args),
            now=now,
        )
        if numbered.get("command") == "custom" and numbered.get("status") == "prompt":
            numbered = _with_tracking_prompt(db_path, user_id=subscriber["user_id"], result=numbered)
        if numbered.get("command") == "schedule" and numbered.get("status") == "prompt":
            numbered = _with_schedule_prompt(db_path, user_id=subscriber["user_id"], result=numbered)
        base = _base_result(str(numbered.get("command") or raw_cmd), user, subscriber)
        return {
            **base,
            "command": numbered.get("command", raw_cmd),
            "status": numbered.get("status", "success"),
            "reply_text": numbered.get("reply_text", ""),
            "reply_markup": numbered.get("reply_markup"),
            "menu": numbered.get("menu"),
            "subscription_status": (numbered.get("menu") or {}).get("subscription_status"),
            "profile": numbered.get("profile"),
            "enabled_categories": numbered.get("enabled_categories"),
            "all_enabled_categories": numbered.get("all_enabled_categories"),
            "tracking_target": numbered.get("tracking_target"),
            "delivery_preferences": numbered.get("delivery_preferences"),
            "subscriber_status": numbered.get("subscriber_status"),
            "latest_delivery_present": numbered.get("latest_delivery_present"),
        }

    if raw_cmd in SLASH_TO_NUMBER:
        numbered = handle_numbered_intel_command(
            db_path,
            channel="telegram",
            external_user_id=user.telegram_user_id,
            channel_user_id=user.chat_id,
            number=SLASH_TO_NUMBER[raw_cmd],
            arg=" ".join(parsed_args),
            now=now,
        )
        if numbered.get("command") == "custom" and numbered.get("status") == "prompt":
            numbered = _with_tracking_prompt(db_path, user_id=subscriber["user_id"], result=numbered)
        base = _base_result(str(numbered.get("command") or raw_cmd), user, subscriber)
        return {
            **base,
            "command": numbered.get("command", raw_cmd),
            "status": numbered.get("status", "success"),
            "reply_text": numbered.get("reply_text", ""),
            "reply_markup": numbered.get("reply_markup"),
            "menu": numbered.get("menu"),
            "subscription_status": (numbered.get("menu") or {}).get("subscription_status"),
            "profile": numbered.get("profile"),
            "enabled_categories": numbered.get("enabled_categories"),
            "all_enabled_categories": numbered.get("all_enabled_categories"),
            "tracking_target": numbered.get("tracking_target"),
            "delivery_preferences": numbered.get("delivery_preferences"),
            "subscriber_status": numbered.get("subscriber_status"),
            "latest_delivery_present": numbered.get("latest_delivery_present"),
        }

    button_prompt = MENU_BUTTON_PROMPTS.get(raw_cmd)
    button_categories = MENU_BUTTON_CATEGORY_MAP.get(raw_cmd)
    if raw_cmd in MENU_BUTTON_CATEGORY_MAP:
        cmd = "sources"
        parsed_args = button_categories or []
    elif button_prompt:
        cmd = button_prompt[0]
    else:
        cmd = MENU_BUTTON_COMMANDS.get(raw_cmd, raw_cmd)
    base = _base_result(cmd, user, subscriber)

    if raw_cmd.isdigit() and int(raw_cmd) in CALLBACK_TO_NUMBER.values():
        numbered = handle_numbered_intel_command(
            db_path,
            channel="telegram",
            external_user_id=user.telegram_user_id,
            channel_user_id=user.chat_id,
            number=int(raw_cmd),
            arg=" ".join(parsed_args),
            now=now,
        )
        if numbered.get("command") == "custom" and numbered.get("status") == "prompt":
            numbered = _with_tracking_prompt(db_path, user_id=subscriber["user_id"], result=numbered)
        if numbered.get("command") == "schedule" and numbered.get("status") == "prompt":
            numbered = _with_schedule_prompt(db_path, user_id=subscriber["user_id"], result=numbered)
        return {
            **base,
            "command": numbered.get("command", cmd),
            "status": numbered.get("status", "success"),
            "reply_text": numbered.get("reply_text", ""),
            "reply_markup": numbered.get("reply_markup"),
            "menu": numbered.get("menu"),
            "subscription_status": (numbered.get("menu") or {}).get("subscription_status"),
            "profile": numbered.get("profile"),
            "enabled_categories": numbered.get("enabled_categories"),
            "all_enabled_categories": numbered.get("all_enabled_categories"),
            "tracking_target": numbered.get("tracking_target"),
            "delivery_preferences": numbered.get("delivery_preferences"),
            "subscriber_status": numbered.get("subscriber_status"),
            "latest_delivery_present": numbered.get("latest_delivery_present"),
        }

    if cmd == "start":
        profile = get_subscription_profile(db_path, user_id=subscriber["user_id"], now=now)
        menu = build_telegram_menu_contract(profile)
        return {
            **base,
            "status": "success",
            "reply_text": menu["text"],
            "reply_markup": menu["reply_markup"],
            "prelude_replies": menu["prelude_replies"],
            "menu": menu,
            "subscription_status": menu["subscription_status"],
        }

    if cmd == "status":
        profile = get_subscription_profile(db_path, user_id=subscriber["user_id"], now=now)
        menu = build_telegram_menu_contract(profile)
        return {
            **base,
            "status": "success",
            "reply_text": _status_text(profile),
            "menu": menu,
            "subscription_status": profile.get("status", "inactive_or_expired"),
            "profile": {k: v for k, v in profile.items() if k != "channel_user_id"},
        }

    if cmd == "sources":
        enabled_categories = parsed_args
        if button_categories is not None:
            profile = get_subscription_profile(db_path, user_id=subscriber["user_id"], now=now)
            current = {_clean(category) for category in profile.get("enabled_categories", []) if _clean(category)}
            selected = {_clean(category) for category in button_categories if _clean(category)}
            enabled_categories = sorted(current - selected) if selected and selected.issubset(current) else sorted(current | selected)
        preferences = set_source_preferences(
            db_path,
            user_id=subscriber["user_id"],
            enabled_categories=enabled_categories,
        )
        enabled = preferences["enabled_categories"]
        return {
            **base,
            "status": "success",
            "reply_text": f"已启用分类：{_category_display_text(enabled)}",
            "enabled_categories": enabled,
            "enabled_category_labels": [_category_display_name(category) for category in enabled],
        }

    if cmd == "schedule":
        if button_prompt and not parsed_args:
            return _with_schedule_prompt(db_path, user_id=subscriber["user_id"], result={
                **base,
                "status": "prompt",
                "reply_text": _schedule_prompt_text(),
            })
        if not parsed_args:
            return _with_schedule_prompt(db_path, user_id=subscriber["user_id"], result={
                **base,
                "status": "prompt",
                "reply_text": _schedule_prompt_text(),
            })
        frequency, delivery_time, timezone = _parse_schedule_args(parsed_args)
        preferences = set_delivery_preferences(
            db_path,
            user_id=subscriber["user_id"],
            frequency=frequency,
            delivery_time=delivery_time,
            timezone=timezone,
        )
        return {
            **base,
            "status": "success",
            "reply_text": (
                "推送设置已更新："
                f"{preferences['frequency']} {preferences['delivery_time']} {preferences['timezone']}"
            ),
            "delivery_preferences": preferences,
        }

    if cmd == "custom":
        target_name = " ".join(parsed_args).strip()
        if not target_name:
            return _with_tracking_prompt(db_path, user_id=subscriber["user_id"], result={
                **base,
                "status": "prompt" if button_prompt else "error",
                "error": "target_name_required",
                "reply_text": button_prompt[1] if button_prompt else "请在 /custom 后输入要追踪的人物姓名。",
            })
        _clear_pending_action(db_path, user_id=subscriber["user_id"])
        return _tracking_success_result(
            db_path,
            base=base,
            subscriber=subscriber,
            user=user,
            target_name=target_name,
            source_channel="telegram_menu",
        )

    if cmd == "search":
        keyword = " ".join(parsed_args).strip() or (raw_cmd if raw_cmd not in MENU_BUTTON_PROMPTS else "")
        return {
            **base,
            "status": "prompt",
            "reply_text": (
                f"已收到关键词：{keyword}。搜索索引接入后会按你的订阅范围返回结果。"
                if keyword
                else (button_prompt[1] if button_prompt else "请直接发送关键词，我会按你的订阅范围检索相关情报。")
            ),
        }

    if cmd == "help":
        profile = get_subscription_profile(db_path, user_id=subscriber["user_id"], now=now)
        menu = build_telegram_menu_contract(profile)
        return {
            **base,
            "status": "success",
            "reply_text": menu["text"],
            "reply_markup": menu["reply_markup"],
            "prelude_replies": menu["prelude_replies"],
            "menu": menu,
        }

    if cmd and not is_slash_command:
        return {
            **base,
            "status": "prompt",
            "reply_text": f"已收到关键词：{raw_cmd}。搜索索引接入后会按你的订阅范围返回结果。",
        }

    return {
        **base,
        "status": "error",
        "error": "unknown_command",
        "reply_text": "未知命令。请发送 /help 查看情报简报 Bot 可用命令。",
    }
