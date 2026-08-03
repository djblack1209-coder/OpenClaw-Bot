"""每日简报跨渠道菜单与数字命令路由。

这个模块只做“用户回复什么 → 系统改什么偏好/回什么文案”的本地逻辑，
不主动调用 Telegram、微信、飞书或钉钉网络接口。真实收发由各平台适配器负责。
"""

from __future__ import annotations

import html
import re
import sqlite3
from pathlib import Path
from typing import Any

from src.intel.db.store import get_latest_delivery_artifact, initialize_intel_db, subscribe_tracking_target
from src.intel.localization import DEFAULT_CONTENT_LANGUAGE, normalize_content_language, parse_content_language
from src.intel.runtime_policy import DEFAULT_INTEL_BRIEF_DELIVERY_TIME, DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE

INTEL_NUMBERED_COMMANDS_ZH: list[dict[str, Any]] = [
    {"number": 700, "title": "今日简报", "needs_arg": False, "hint": "打开简报主菜单"},
    {"number": 701, "title": "我的订阅", "needs_arg": False, "hint": "查看当前状态"},
    {"number": 702, "title": "市场资金", "needs_arg": False, "hint": "A股资金/国会/机构持仓"},
    {"number": 703, "title": "AI科技", "needs_arg": False, "hint": "AI动态/GitHub趋势"},
    {"number": 704, "title": "天气预警", "needs_arg": False, "hint": "天气/空气/灾害提醒"},
    {"number": 705, "title": "推送时间", "needs_arg": False, "hint": "默认每天 08:30"},
    {"number": 706, "title": "添加追踪", "needs_arg": True, "hint": "例如：706 英伟达"},
    {"number": 707, "title": "帮助", "needs_arg": False, "hint": "查看怎么用"},
    {"number": 708, "title": "暂停简报", "needs_arg": False, "hint": "不再每日推送"},
    {"number": 709, "title": "资讯语言", "needs_arg": False, "hint": "中文 / English"},
]

INTEL_NUMBERED_COMMANDS_EN: list[dict[str, Any]] = [
    {"number": 700, "title": "Today's Brief", "needs_arg": False, "hint": "Open the latest brief"},
    {"number": 701, "title": "My Subscription", "needs_arg": False, "hint": "View current status"},
    {"number": 702, "title": "Markets", "needs_arg": False, "hint": "A-shares, Congress and 13F"},
    {"number": 703, "title": "AI & Tech", "needs_arg": False, "hint": "AI updates and GitHub trends"},
    {"number": 704, "title": "Weather Alerts", "needs_arg": False, "hint": "Weather, air and hazards"},
    {"number": 705, "title": "Delivery Time", "needs_arg": False, "hint": "Default: daily at 08:30"},
    {"number": 706, "title": "Track a Topic", "needs_arg": True, "hint": "Example: 706 NVIDIA"},
    {"number": 707, "title": "Help", "needs_arg": False, "hint": "Show available actions"},
    {"number": 708, "title": "Pause Brief", "needs_arg": False, "hint": "Stop daily delivery"},
    {"number": 709, "title": "Language", "needs_arg": False, "hint": "中文 / English"},
]

INTEL_NUMBERED_COMMANDS = INTEL_NUMBERED_COMMANDS_ZH

INTEL_INLINE_MENU_BUTTONS_ZH: list[list[dict[str, str]]] = [
    [
        {"text": "🧭 今日简报", "callback_data": "today"},
        {"text": "📌 我的订阅", "callback_data": "status"},
    ],
    [
        {"text": "📈 市场资金", "callback_data": "market"},
        {"text": "🤖 AI科技", "callback_data": "ai_tech"},
    ],
    [
        {"text": "🌦 天气预警", "callback_data": "weather_alerts"},
        {"text": "⏰ 推送时间", "callback_data": "schedule"},
    ],
    [
        {"text": "➕ 添加追踪", "callback_data": "custom"},
        {"text": "❓ 帮助", "callback_data": "help"},
    ],
    [
        {"text": "中文", "callback_data": "language_zh"},
        {"text": "English", "callback_data": "language_en"},
    ],
]

INTEL_INLINE_MENU_BUTTONS_EN: list[list[dict[str, str]]] = [
    [
        {"text": "🧭 Today's Brief", "callback_data": "today"},
        {"text": "📌 Subscription", "callback_data": "status"},
    ],
    [
        {"text": "📈 Markets", "callback_data": "market"},
        {"text": "🤖 AI & Tech", "callback_data": "ai_tech"},
    ],
    [
        {"text": "🌦 Weather", "callback_data": "weather_alerts"},
        {"text": "⏰ Delivery Time", "callback_data": "schedule"},
    ],
    [
        {"text": "➕ Track", "callback_data": "custom"},
        {"text": "❓ Help", "callback_data": "help"},
    ],
    [
        {"text": "中文", "callback_data": "language_zh"},
        {"text": "English", "callback_data": "language_en"},
    ],
]

INTEL_INLINE_MENU_BUTTONS = INTEL_INLINE_MENU_BUTTONS_ZH

CALLBACK_TO_NUMBER: dict[str, int] = {
    "today": 700,
    "🧭 今日简报": 700,
    "今日简报": 700,
    "🧭 today's brief": 700,
    "today's brief": 700,
    "status": 701,
    "📌 我的订阅": 701,
    "我的订阅": 701,
    "📌 subscription": 701,
    "subscription": 701,
    "market": 702,
    "ai_tech": 703,
    "weather_alerts": 704,
    "schedule": 705,
    "custom": 706,
    "help": 707,
    "pause": 708,
    "暂停简报": 708,
    "language": 709,
    "language_zh": 709,
    "language_en": 709,
    "中文": 709,
    "english": 709,
}

CALLBACK_LANGUAGE_ARGS = {
    "language_zh": "zh",
    "language_en": "en",
    "中文": "zh",
    "english": "en",
}

MARKET_CATEGORIES = ["akshare", "institutional_13f", "senate_trading"]
AI_TECH_CATEGORIES = ["ai_model_updates", "github_trending"]
WEATHER_CATEGORIES = ["air_quality", "disaster_alerts", "humidity", "rainfall", "temperature", "weather"]

SCHEDULE_QUICK_CHOICES: dict[str, tuple[str, str, str]] = {
    "1": ("daily", "08:30", "Asia/Singapore"),
    "2": ("weekly", "08:30", "Asia/Singapore"),
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

CATEGORY_DISPLAY_NAMES_EN = {
    "github_trending": "GitHub trends",
    "ai_model_updates": "AI model updates",
    "weibo": "Weibo",
    "xiaohongshu": "Xiaohongshu",
    "douyin": "Douyin",
    "zhihu": "Zhihu",
    "bilibili": "Bilibili",
    "weather": "weather",
    "air_quality": "air quality",
    "rainfall": "rainfall",
    "temperature": "temperature",
    "humidity": "humidity",
    "disaster_alerts": "hazard alerts",
    "institutional_13f": "institutional 13F filings",
    "tech": "technology",
    "akshare": "A-share capital flows",
    "senate_trading": "Congressional trading",
    "crypto": "crypto",
}

_CHANNEL_ALIASES = {
    "tg": "telegram",
    "telegram": "telegram",
    "wx": "wechat",
    "wechat": "wechat",
    "weixin": "wechat",
    "feishu": "feishu",
    "lark": "feishu",
    "dingtalk": "dingtalk",
    "dingding": "dingtalk",
}

_USER_PREFIX = {
    "telegram": "tg",
    "wechat": "wechat",
    "feishu": "feishu",
    "dingtalk": "dingtalk",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_channel(channel: str) -> str:
    """把平台别名统一成内部渠道名。"""
    cleaned = _clean(channel).lower().replace("-", "_")
    return _CHANNEL_ALIASES.get(cleaned, cleaned or "unknown")


def intel_numbered_commands(content_language: str = DEFAULT_CONTENT_LANGUAGE) -> list[dict[str, Any]]:
    """返回指定语言的数字命令定义副本。"""
    commands = (
        INTEL_NUMBERED_COMMANDS_EN
        if normalize_content_language(content_language) == "en"
        else INTEL_NUMBERED_COMMANDS_ZH
    )
    return [dict(item) for item in commands]


def intel_inline_menu_buttons(content_language: str = DEFAULT_CONTENT_LANGUAGE) -> list[list[dict[str, str]]]:
    """返回指定语言的 Telegram 按钮定义副本。"""
    rows = (
        INTEL_INLINE_MENU_BUTTONS_EN
        if normalize_content_language(content_language) == "en"
        else INTEL_INLINE_MENU_BUTTONS_ZH
    )
    return [[dict(button) for button in row] for row in rows]


def category_display_name(category: str, content_language: str = DEFAULT_CONTENT_LANGUAGE) -> str:
    """返回老板和用户看得懂的分类名。"""
    cleaned = _clean(category)
    names = (
        CATEGORY_DISPLAY_NAMES_EN if normalize_content_language(content_language) == "en" else CATEGORY_DISPLAY_NAMES
    )
    return names.get(cleaned, cleaned)


def category_display_text(
    categories: list[str] | tuple[str, ...] | None,
    content_language: str = DEFAULT_CONTENT_LANGUAGE,
) -> str:
    """把分类列表格式化成中文。"""
    language = normalize_content_language(content_language)
    labels = [category_display_name(category, language) for category in (categories or []) if _clean(category)]
    if language == "en":
        return ", ".join(labels) if labels else "Not set"
    return "、".join(labels) if labels else "未设置"


def _status_label(status: str, content_language: str = DEFAULT_CONTENT_LANGUAGE) -> str:
    mapping_zh = {
        "active": "已开通",
        "inactive_or_expired": "未开通或已到期",
        "not_found": "未开通",
        "paused": "已暂停",
    }
    mapping_en = {
        "active": "Active",
        "inactive_or_expired": "Inactive or expired",
        "not_found": "Not activated",
        "paused": "Paused",
    }
    language = normalize_content_language(content_language)
    mapping = mapping_en if language == "en" else mapping_zh
    return mapping.get(_clean(status), _clean(status) or ("Unknown" if language == "en" else "未知"))


def _command_lines(content_language: str = DEFAULT_CONTENT_LANGUAGE) -> list[str]:
    return [f"{item['number']} {item['title']}" for item in intel_numbered_commands(content_language)]


def build_intel_menu_text(
    *,
    channel: str,
    subscription_status: str = "inactive_or_expired",
    content_language: str = DEFAULT_CONTENT_LANGUAGE,
) -> str:
    """生成跨平台共用菜单文案。"""
    normalized = normalize_channel(channel)
    language = normalize_content_language(content_language)
    if language == "en":
        action_hint = (
            "Tap a button or reply with a number, for example: 706 NVIDIA."
            if normalized == "telegram"
            else "Reply with a number, for example: 706 NVIDIA."
        )
        lines = [
            "CARVEN Intelligence Brief",
            "High-value signals you care about, delivered every morning.",
            f"Status: {_status_label(subscription_status, language)}",
            "",
            action_hint,
            "",
        ]
    else:
        action_hint = (
            "可点击按钮，也可直接回复数字（例如：706 英伟达）。"
            if normalized == "telegram"
            else "回复数字即可操作，例如：706 英伟达。"
        )
        lines = [
            "CARVEN 情报简报",
            "每天早上自动发你关心的高价值信息。",
            f"当前状态：{_status_label(subscription_status, language)}",
            "",
            action_hint,
            "",
        ]
    lines.extend(_command_lines(language))
    return "\n".join(lines)


def build_intel_channel_menu(
    *,
    channel: str,
    subscription_status: str = "inactive_or_expired",
    enabled_categories: list[str] | None = None,
    delivery_preferences: dict[str, Any] | None = None,
    content_language: str | None = None,
) -> dict[str, Any]:
    """构建某个平台可展示的每日简报菜单。"""
    normalized = normalize_channel(channel)
    delivery = dict(delivery_preferences or {})
    language = normalize_content_language(content_language or delivery.get("content_language"))
    supports_click_menu = normalized == "telegram"
    inline_keyboard = intel_inline_menu_buttons(language) if supports_click_menu else []
    return {
        "channel": normalized,
        "supports_click_menu": supports_click_menu,
        "text": build_intel_menu_text(
            channel=normalized,
            subscription_status=subscription_status,
            content_language=language,
        ),
        "inline_keyboard": inline_keyboard,
        "inline_buttons": inline_keyboard,
        "reply_markup": {"inline_keyboard": inline_keyboard} if supports_click_menu else None,
        "numbered_commands": intel_numbered_commands(language),
        "subscription_status": subscription_status,
        "enabled_categories": sorted({_clean(item) for item in (enabled_categories or []) if _clean(item)}),
        "delivery_preferences": delivery,
        "content_language": language,
    }


def _subscriber_user_id(channel: str, external_user_id: str) -> str:
    normalized = normalize_channel(channel)
    prefix = _USER_PREFIX.get(normalized, normalized or "user")
    external = _clean(external_user_id)
    if not external:
        external = "anonymous"
    return f"{prefix}:{external}"


def _upsert_channel_subscriber(
    db_path: str | Path,
    *,
    channel: str,
    external_user_id: str,
    channel_user_id: str = "",
    reactivate: bool = True,
) -> dict[str, Any]:
    """确保跨平台订阅者存在，返回脱敏安全的订阅者记录。"""
    initialize_intel_db(db_path)
    normalized = normalize_channel(channel)
    user_id = _subscriber_user_id(normalized, external_user_id)
    channel_user = _clean(channel_user_id) or _clean(external_user_id) or "anonymous"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO subscribers (user_id, channel_type, channel_user_id, status, updated_at)
            VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                channel_type=excluded.channel_type,
                channel_user_id=excluded.channel_user_id,
                status=CASE WHEN ? THEN 'active' ELSE subscribers.status END,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, normalized, channel_user, 1 if reactivate else 0),
        )
        row = conn.execute(
            "SELECT id, user_id, channel_type, channel_user_id, status FROM subscribers WHERE user_id=?",
            (user_id,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise RuntimeError("订阅者写入失败")
    return {
        "subscriber_id": int(row[0]),
        "user_id": str(row[1]),
        "channel_type": str(row[2]),
        "channel_user_id": str(row[3]),
        "status": str(row[4]),
    }


def _set_subscriber_status(db_path: str | Path, *, user_id: str, status: str) -> dict[str, Any]:
    """更新订阅者启停状态。"""
    initialize_intel_db(db_path)
    cleaned = _clean(status) or "active"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE subscribers SET status=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (cleaned, user_id)
        )
        conn.commit()
    return {"user_id": user_id, "status": cleaned}


def _merge_categories(current: list[str], selected: list[str]) -> list[str]:
    """把用户新开的分类追加到已有偏好里。"""
    return sorted({_clean(item) for item in [*current, *selected] if _clean(item)})


def _parse_schedule_arg(arg: str) -> tuple[str, str, str]:
    """解析推送时间参数，默认每天 08:30。"""
    return parse_intel_schedule_text(arg)


def _frequency_label(frequency: str) -> str:
    """把频率字段翻译成普通用户看得懂的中文。"""
    return "每周" if _clean(frequency).lower() == "weekly" else "每天"


def build_schedule_prompt_text(content_language: str = DEFAULT_CONTENT_LANGUAGE) -> str:
    """生成普通用户看得懂的推送时间设置提示。"""
    if normalize_content_language(content_language) == "en":
        return "\n".join(
            [
                "⏰ Set delivery time",
                "Reply with a number:",
                "1 Daily at 08:30 (default)",
                "2 Weekly on Monday at 08:30",
                "",
                "Timezone: Asia/Singapore",
                "Reply 0 to cancel.",
            ]
        )
    return "\n".join(
        [
            "⏰ 设置推送时间",
            "回复数字即可设置：",
            "1 每天 08:30（默认）",
            "2 每周一 08:30",
            "",
            "时区：Asia/Singapore",
            "想取消就回复：0",
        ]
    )


def parse_intel_schedule_text(arg: str) -> tuple[str, str, str]:
    """解析小白输入的推送频率和时间。"""
    cleaned = _clean(arg)
    if not cleaned:
        return "daily", "08:30", "Asia/Singapore"
    if cleaned in SCHEDULE_QUICK_CHOICES:
        return SCHEDULE_QUICK_CHOICES[cleaned]
    if cleaned.startswith("705"):
        cleaned = _clean(cleaned[3:])
    if cleaned in SCHEDULE_QUICK_CHOICES:
        return SCHEDULE_QUICK_CHOICES[cleaned]
    original_parts = cleaned.split()
    normalized = (
        cleaned.lower().replace("：", ":").replace("每日", "每天").replace("一周一次", "每周").replace("每星期", "每周")
    )
    parts = cleaned.split()
    frequency = "daily"
    delivery_time = "08:30"
    timezone = "Asia/Singapore"
    if "weekly" in normalized or "每周" in normalized or "周报" in normalized:
        frequency = "weekly"
    if "daily" in normalized or "每天" in normalized or "日报" in normalized:
        frequency = "daily"
    time_match = re.search(r"(\d{1,2})\s*[:]\s*(\d{2})", normalized)
    if time_match:
        hour = max(0, min(23, int(time_match.group(1))))
        minute = max(0, min(59, int(time_match.group(2))))
        delivery_time = f"{hour:02d}:{minute:02d}"
    elif point_match := re.search(r"(\d{1,2})\s*点(半)?", normalized):
        hour = max(0, min(23, int(point_match.group(1))))
        minute = 30 if point_match.group(2) else 0
        delivery_time = f"{hour:02d}:{minute:02d}"
    parts = normalized.split()
    if parts and parts[0] in {"daily", "weekly"}:
        frequency = parts.pop(0)
    if parts and re.match(r"^\d{1,2}:\d{2}$", parts[0]):
        hour, minute = parts.pop(0).split(":", 1)
        delivery_time = f"{max(0, min(23, int(hour))):02d}:{max(0, min(59, int(minute))):02d}"
    if original_parts:
        timezone_candidate = original_parts[-1]
        if "/" in timezone_candidate or timezone_candidate.upper() in {"UTC", "GMT"}:
            timezone = timezone_candidate
    return frequency, delivery_time, timezone


def _format_status(profile: dict[str, Any]) -> str:
    delivery = profile.get("delivery_preferences") or {}
    language = normalize_content_language(delivery.get("content_language"))
    if language == "en":
        frequency = "Weekly" if _clean(delivery.get("frequency")).lower() == "weekly" else "Daily"
        return "\n".join(
            [
                "📌 My brief status",
                f"Subscription: {_status_label(str(profile.get('status') or 'inactive_or_expired'), language)}",
                f"Plan: {profile.get('plan_name') or 'Not activated'}",
                f"Expires: {profile.get('expires_at') or 'None'}",
                f"Topics: {category_display_text(profile.get('enabled_categories') or [], language)}",
                f"Delivery: {frequency} {delivery.get('delivery_time', '08:30')}",
                "Language: English",
                "",
                "To track a topic, reply: 706 NVIDIA",
            ]
        )
    return "\n".join(
        [
            "📌 我的简报状态",
            f"订阅状态：{_status_label(str(profile.get('status') or 'inactive_or_expired'))}",
            f"套餐：{profile.get('plan_name') or '未开通'}",
            f"到期：{profile.get('expires_at') or '无'}",
            f"已选内容：{category_display_text(profile.get('enabled_categories') or [])}",
            f"推送时间：{_frequency_label(str(delivery.get('frequency') or 'daily'))} {delivery.get('delivery_time', '08:30')}",
            "资讯语言：中文",
            "",
            "想添加追踪对象，回复：706 英伟达",
        ]
    )


def _latest_delivery_for_subscriber(db_path: str | Path, *, subscriber_id: int) -> dict[str, Any] | None:
    """读取这个用户最近一次成功收到的简报。"""
    initialize_intel_db(db_path)
    artifact = get_latest_delivery_artifact(db_path, subscriber_id=int(subscriber_id))
    if artifact:
        envelope = artifact.get("envelope") if isinstance(artifact.get("envelope"), dict) else {}
        full_text = _clean(envelope.get("full_text_html"))
        if full_text:
            return {
                "delivered_at": str(artifact.get("created_at") or ""),
                "channel_type": "telegram",
                "content_summary": full_text,
                "brief_ref": str(artifact.get("public_ref") or ""),
                "structured_replay": True,
                "reply_markup": envelope.get("reply_markup")
                if isinstance(envelope.get("reply_markup"), dict)
                else None,
            }
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT delivered_at, channel_type, content_summary
            FROM delivery_log
            WHERE subscriber_id=? AND success=1
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(subscriber_id),),
        ).fetchone()
    if row is None:
        return None
    return {
        "delivered_at": str(row[0] or ""),
        "channel_type": str(row[1] or ""),
        "content_summary": str(row[2] or ""),
    }


def _format_today_brief(latest: dict[str, Any] | None, fallback_menu: dict[str, Any]) -> str:
    """把最近简报整理成用户能直接看的“今日简报”。"""
    language = normalize_content_language(fallback_menu.get("content_language"))
    if latest and _clean(latest.get("content_summary")):
        content = _clean(latest.get("content_summary"))
        if content.startswith(("🧭 今日情报简报", "🧭 情报简报")):
            return content
        if language == "en":
            return "\n".join(
                [
                    "🧭 Today's Brief",
                    f"Last delivered: {latest.get('delivered_at') or 'Unknown'}",
                    "",
                    content,
                    "",
                    "Reply 701 for subscription status or 706 NVIDIA to track a topic.",
                ]
            )
        return "\n".join(
            [
                "🧭 今日简报",
                f"最近推送时间：{latest.get('delivered_at') or '未知'}",
                "",
                content,
                "",
                "回复 701 看订阅状态，回复 706 英伟达 添加追踪。",
            ]
        )
    if language == "en":
        return "\n".join(
            [
                "🧭 Today's Brief",
                "No recent brief was found for your subscription.",
                "Select the topics you care about and they will appear in the next scheduled brief.",
                "",
                fallback_menu["text"],
            ]
        )
    return "\n".join(
        [
            "🧭 今日简报",
            "暂时没找到你最近收到的简报记录。",
            "你可以先选关注内容，系统会在下一次定时推送时发送。",
            "",
            fallback_menu["text"],
        ]
    )


def _category_success_reply(
    title: str,
    selected: list[str],
    all_enabled: list[str],
    content_language: str = DEFAULT_CONTENT_LANGUAGE,
) -> str:
    if normalize_content_language(content_language) == "en":
        return "\n".join(
            [
                f"✅ {title} enabled",
                f"Added: {category_display_text(selected, 'en')}",
                f"Current topics: {category_display_text(all_enabled, 'en')}",
                "Future briefs will use these preferences.",
            ]
        )
    return "\n".join(
        [
            f"✅ 已开启{title}",
            f"本次新增：{category_display_text(selected, 'zh')}",
            f"当前已选：{category_display_text(all_enabled, 'zh')}",
            "以后每日简报会按这些内容推送。",
        ]
    )


def handle_numbered_intel_command(
    db_path: str | Path,
    *,
    channel: str,
    external_user_id: str,
    number: int,
    arg: str = "",
    now: str = "9999-12-31T00:00:00+00:00",
    channel_user_id: str = "",
) -> dict[str, Any]:
    """处理 700-709 每日简报数字命令。"""
    from src.intel.subscriptions import (
        get_subscription_profile,
        set_content_language,
        set_delivery_preferences,
        set_source_preferences,
    )

    normalized = normalize_channel(channel)
    command_number = int(number)
    should_reactivate = command_number in {702, 703, 704} or (command_number == 706 and bool(_clean(arg)))
    subscriber = _upsert_channel_subscriber(
        db_path,
        channel=normalized,
        external_user_id=external_user_id,
        channel_user_id=channel_user_id,
        reactivate=should_reactivate,
    )
    user_id = subscriber["user_id"]
    profile = get_subscription_profile(db_path, user_id=user_id, now=now)
    delivery = profile.get("delivery_preferences") or {}
    language = normalize_content_language(delivery.get("content_language"))

    if command_number == 700:
        menu = build_intel_channel_menu(
            channel=normalized,
            subscription_status=str(profile.get("status") or "inactive_or_expired"),
            enabled_categories=profile.get("enabled_categories") or [],
            delivery_preferences=profile.get("delivery_preferences") or {},
            content_language=language,
        )
        latest = _latest_delivery_for_subscriber(db_path, subscriber_id=int(subscriber["subscriber_id"]))
        return {
            "status": "success",
            "command": "today",
            "reply_text": _format_today_brief(latest, menu),
            "menu": menu,
            "reply_markup": (
                latest.get("reply_markup")
                if isinstance(latest, dict) and isinstance(latest.get("reply_markup"), dict)
                else menu.get("reply_markup")
            ),
            "latest_delivery_present": latest is not None,
        }

    if command_number == 701:
        return {"status": "success", "command": "status", "reply_text": _format_status(profile), "profile": profile}

    category_groups = (
        {
            702: ("Markets", MARKET_CATEGORIES),
            703: ("AI & Tech", AI_TECH_CATEGORIES),
            704: ("Weather alerts", WEATHER_CATEGORIES),
        }
        if language == "en"
        else {
            702: ("市场资金", MARKET_CATEGORIES),
            703: ("AI科技", AI_TECH_CATEGORIES),
            704: ("天气预警", WEATHER_CATEGORIES),
        }
    )
    if command_number in category_groups:
        title, selected = category_groups[command_number]
        current = list(profile.get("enabled_categories") or [])
        merged = _merge_categories(current, selected)
        preferences = set_source_preferences(db_path, user_id=user_id, enabled_categories=merged)
        return {
            "status": "success",
            "command": "sources",
            "reply_text": _category_success_reply(title, selected, preferences["enabled_categories"], language),
            "enabled_categories": selected,
            "all_enabled_categories": preferences["enabled_categories"],
            "enabled_category_labels": [category_display_name(item, language) for item in selected],
        }

    if command_number == 705:
        if not _clean(arg):
            return {
                "status": "prompt",
                "command": "schedule",
                "reply_text": build_schedule_prompt_text(language),
            }
        frequency, delivery_time, timezone = _parse_schedule_arg(arg)
        if delivery_time != DEFAULT_INTEL_BRIEF_DELIVERY_TIME or timezone != DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE:
            return {
                "status": "error",
                "command": "schedule",
                "error": "unsupported_delivery_schedule",
                "reply_text": (
                    "This deployment currently supports 08:30 Asia/Singapore only. Reply 1 for daily or 2 for weekly."
                    if language == "en"
                    else "当前仅支持新加坡时间 08:30 推送。回复 1 设置每天，或回复 2 设置每周一。"
                ),
            }
        preferences = set_delivery_preferences(
            db_path,
            user_id=user_id,
            frequency=frequency,
            delivery_time=delivery_time,
            timezone=timezone,
        )
        return {
            "status": "success",
            "command": "schedule",
            "reply_text": (
                f"✅ Delivery time updated: {'Weekly' if preferences['frequency'] == 'weekly' else 'Daily'} "
                f"{preferences['delivery_time']} ({preferences['timezone']})."
                if language == "en"
                else f"✅ 推送时间已设置：{_frequency_label(preferences['frequency'])} {preferences['delivery_time']}（{preferences['timezone']}）。"
            ),
            "delivery_preferences": preferences,
        }

    if command_number == 706:
        target_name = _clean(arg)
        if not target_name:
            return {
                "status": "prompt",
                "command": "custom",
                "reply_text": (
                    "What would you like to track?\nReply with a name, for example: NVIDIA\n"
                    "You can also use: 706 NVIDIA\nReply 0 to cancel."
                    if language == "en"
                    else "你想追踪谁？\n下一条直接回复名字就行，例如：英伟达\n也可以复制完整格式：706 英伟达 / 706 周杰伦\n想取消就回复：0"
                ),
            }
        target = subscribe_tracking_target(
            db_path,
            user_id=user_id,
            channel_type=normalized,
            channel_user_id=_clean(channel_user_id) or _clean(external_user_id),
            target_name=target_name,
            source_channel=f"{normalized}_numbered_menu",
        )
        safe_target = {
            "name": target["name"],
            "normalized_name": target["normalized_name"],
            "active_subscription_count": target["active_subscription_count"],
        }
        escaped_target_name = html.escape(target["name"], quote=False)
        return {
            "status": "success",
            "command": "custom",
            "reply_text": (
                f"✅ Tracking added: {escaped_target_name}. Future briefs will prioritize it."
                if language == "en"
                else f"✅ 已添加追踪：{escaped_target_name}。以后简报会优先关注它。"
            ),
            "tracking_target": safe_target,
        }

    if command_number == 707:
        menu = build_intel_channel_menu(
            channel=normalized,
            subscription_status=str(profile.get("status") or "inactive_or_expired"),
            enabled_categories=profile.get("enabled_categories") or [],
            delivery_preferences=profile.get("delivery_preferences") or {},
            content_language=language,
        )
        return {
            "status": "success",
            "command": "help",
            "reply_text": menu["text"],
            "menu": menu,
            "reply_markup": menu.get("reply_markup"),
        }

    if command_number == 708:
        paused = _set_subscriber_status(db_path, user_id=user_id, status="paused")
        return {
            "status": "success",
            "command": "pause",
            "reply_text": (
                "Daily briefs are paused. Reply 700 and select a topic when you want to resume."
                if language == "en"
                else "已暂停每日简报。想恢复时回复 700 打开菜单，再选择你要的内容。"
            ),
            "subscriber_status": paused["status"],
        }

    if command_number == 709:
        requested_language = parse_content_language(arg)
        if requested_language is None:
            return {
                "status": "prompt" if not _clean(arg) else "error",
                "command": "language",
                "error": "" if not _clean(arg) else "unsupported_content_language",
                "reply_text": (
                    "Choose the language used for your brief:\n709 中文\n709 English"
                    if language == "en"
                    else "请选择资讯语言：\n709 中文\n709 English"
                ),
                "reply_markup": {"inline_keyboard": [intel_inline_menu_buttons(language)[-1]]}
                if normalized == "telegram"
                else None,
                "content_language": language,
            }
        preferences = set_content_language(db_path, user_id=user_id, content_language=requested_language)
        return {
            "status": "success",
            "command": "language",
            "reply_text": "News language switched to English."
            if requested_language == "en"
            else "资讯语言已切换为中文。",
            "delivery_preferences": preferences,
            "content_language": requested_language,
            "reply_markup": {"inline_keyboard": [intel_inline_menu_buttons(requested_language)[-1]]}
            if normalized == "telegram"
            else None,
        }

    return {
        "status": "error",
        "command": "unknown",
        "reply_text": (
            "Unknown number. Reply 700 to open the brief menu."
            if language == "en"
            else "这个编号我还不认识。回复 700 查看每日简报菜单。"
        ),
    }
