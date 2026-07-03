"""
Bot — 社媒发布 / 热点 / 人设 / 日历 命令 Mixin

包含功能:
  - 社媒发布 (X / 小红书 / 双平台)
  - 热点选题与 AI 草稿
  - 社媒人设管理
  - 社媒日历与报表
  - 预览确认回调
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta

from src.api.rpc import ClawBotRPC
from src.bot.auth import requires_auth
from src.bot.error_messages import error_service_failed
from src.bot.globals import execution_hub, get_siliconflow_key, image_tool, send_long_message
from src.constants import IMG_MODEL_FLUX
from src.message_format import format_error
from src.notify_style import (
    format_hotpost_result,
    format_social_dual_result,
    format_social_published,
)
from src.telegram_ux import with_typing

logger = logging.getLogger(__name__)


def _social_review_platform_label(platform: str) -> str:
    """把平台短码转成老板在 Telegram 里能看懂的名称。"""
    return {
        "x": "X",
        "twitter": "X",
        "xhs": "小红书",
        "xiaohongshu": "小红书",
        "xianyu": "闲鱼",
    }.get(str(platform or "").strip().lower(), "社媒")



_SOCIAL_STRATEGY_ALIASES = {
    "auto": "auto_mcn_growth",
    "auto_mcn_growth": "auto_mcn_growth",
    "自动": "auto_mcn_growth",
    "自动匹配": "auto_mcn_growth",
    "财富": "x_wealth_frontier",
    "财富前沿": "x_wealth_frontier",
    "赚钱": "x_wealth_frontier",
    "美股": "x_wealth_frontier",
    "x_wealth_frontier": "x_wealth_frontier",
    "抽象": "x_absurd_growth",
    "抽象热点": "x_absurd_growth",
    "梗": "x_absurd_growth",
    "x_absurd_growth": "x_absurd_growth",
    "小红书": "xhs_lifestyle_tutorial",
    "生活": "xhs_lifestyle_tutorial",
    "生活攻略": "xhs_lifestyle_tutorial",
    "女性向": "xhs_lifestyle_tutorial",
    "xhs_lifestyle_tutorial": "xhs_lifestyle_tutorial",
    "闲鱼": "xianyu_deal_closer",
    "成交": "xianyu_deal_closer",
    "客服": "xianyu_deal_closer",
    "xianyu_deal_closer": "xianyu_deal_closer",
}

_SOCIAL_STRATEGY_LABELS = {
    "auto_mcn_growth": "自动匹配平台涨粉打法",
    "x_wealth_frontier": "X 财富前沿实操",
    "x_absurd_growth": "X 抽象热点涨粉",
    "xhs_lifestyle_tutorial": "小红书生活攻略",
    "xianyu_deal_closer": "闲鱼成交客服",
}


def _normalize_social_strategy_args(raw: str) -> tuple[str, str]:
    """把 Telegram 输入的人话打法规整成 strategyPreset + platform。"""
    text = str(raw or "").strip()
    compact = re.sub(r"\s+", "", text).lower()
    platform = "x"
    if re.search("小红书|xhs|xiaohongshu", text, re.IGNORECASE):
        platform = "xhs"
    elif re.search("闲鱼|xianyu|goofish", text, re.IGNORECASE):
        platform = "xianyu"
    elif re.search(r"(?:^|\s)(?:x|twitter|推特)(?:\s|$)|X", text):
        platform = "x"

    candidates = [text, compact]
    candidates.extend(re.split(r"[\s,，/]+", text))
    for item in candidates:
        key = str(item or "").strip().lower()
        if key in _SOCIAL_STRATEGY_ALIASES:
            preset = _SOCIAL_STRATEGY_ALIASES[key]
            if preset == "xhs_lifestyle_tutorial":
                platform = "xhs"
            elif preset == "xianyu_deal_closer":
                platform = "xianyu"
            elif preset.startswith("x_"):
                platform = "x"
            return preset, platform

    if "抽象" in text or "梗" in text:
        return "x_absurd_growth", "x"
    if "财富" in text or "赚钱" in text or "美股" in text or "出海" in text:
        return "x_wealth_frontier", "x"
    if "小红书" in text or "生活" in text or "女性" in text:
        return "xhs_lifestyle_tutorial", "xhs"
    if "闲鱼" in text or "成交" in text or "客服" in text:
        return "xianyu_deal_closer", "xianyu"
    if "自动" in text or not text:
        return "auto_mcn_growth", platform
    return "auto_mcn_growth", platform


def _format_social_strategy_message(payload: dict) -> str:
    """格式化 no-code 运营打法切换结果；强调只改策略不外发。"""
    data = payload if isinstance(payload, dict) else {}
    summary = data.get("strategy_summary") if isinstance(data.get("strategy_summary"), dict) else {}
    preset = str(summary.get("preset") or data.get("settings", {}).get("strategyPreset") or "auto_mcn_growth")
    effective = str(summary.get("effective_preset") or preset)
    label = str(summary.get("label") or _SOCIAL_STRATEGY_LABELS.get(effective, effective))
    platform = _social_review_platform_label(str(data.get("platform") or summary.get("platform") or "x"))
    if not data.get("success", False):
        return "\n".join([
            "⚠️ 运营打法切换失败",
            "",
            f"- 原因: {data.get('error', '未知错误')}",
            "- 安全边界: 未改动任何发布/评论权限",
        ])

    lines = ["✅ no-code 运营打法已保存", ""]
    lines.append(f"- 平台: {platform}")
    lines.append(f"- 当前打法: {label}")
    lines.append(f"- Preset: {preset} → {effective}")
    if summary.get("audience"):
        lines.append(f"- 人群: {summary.get('audience')}")
    if summary.get("content_focus"):
        lines.append(f"- 内容重点: {summary.get('content_focus')}")
    if summary.get("growth_loop"):
        lines.append(f"- 增长闭环: {summary.get('growth_loop')}")
    lines.append("- 安全边界: 只影响后续待审草稿/素材计划/热点排序")
    lines.append("- 不会自动发布、评论、关注、私信、推广或刷量")
    lines.append("可选打法: 自动 / 财富前沿 / 抽象热点 / 小红书生活攻略 / 闲鱼成交客服")
    return "\n".join(lines)

def _format_social_strategy_status_message(payload: dict) -> str:
    """格式化当前 no-code 运营打法状态；用于 Telegram 无参数查询。"""
    data = payload if isinstance(payload, dict) else {}
    summary = data.get("strategy_summary") if isinstance(data.get("strategy_summary"), dict) else {}
    review_gate = data.get("review_gate") if isinstance(data.get("review_gate"), dict) else {}
    label = str(summary.get("short_label") or summary.get("label") or "自动匹配")
    effective = str(summary.get("effective_preset") or summary.get("preset") or "auto_mcn_growth")
    platform = _social_review_platform_label(str(summary.get("platform") or "x"))

    lines = ["📌 当前 no-code 运营打法", ""]
    lines.append(f"- 当前平台: {platform}")
    lines.append(f"- 当前打法: {label}")
    lines.append(f"- Effective Preset: {effective}")
    if summary.get("audience"):
        lines.append(f"- 人群: {summary.get('audience')}")
    if summary.get("content_focus"):
        lines.append(f"- 内容重点: {summary.get('content_focus')}")
    if summary.get("growth_loop"):
        lines.append(f"- 增长闭环: {summary.get('growth_loop')}")
    lines.append(f"- 待审草稿: {int(review_gate.get('needs_review') or 0)}")
    lines.append(f"- 可发布但未最终确认: {int(review_gate.get('ready_to_publish') or 0)}")
    lines.append(f"- 已排程提醒: {int(review_gate.get('scheduled') or 0)}")

    platforms = data.get("platforms") if isinstance(data.get("platforms"), list) else []
    if platforms:
        lines.append("")
        lines.append("平台打法:")
        for item in platforms[:3]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("id") or "平台")
            strategy = str(item.get("strategy_label") or "")
            needs_review = int(item.get("needs_review") or 0)
            growth_loop = str(item.get("growth_loop") or "")[:80]
            lines.append(f"- {name}: {strategy} · 待审 {needs_review} · {growth_loop}")

    lines.append("")
    lines.append("安全边界: 不会自动发布、评论、关注、私信、推广或刷量。")
    lines.append("切换示例: /social_strategy 抽象热点 / 财富前沿 / 小红书生活攻略 / 闲鱼成交客服")
    return "\n".join(lines)

def _format_social_review_drafts_message(payload: dict) -> str:
    """格式化社媒待审草稿队列；只展示和引导确认，不授权外部动作。"""
    data = payload if isinstance(payload, dict) else {}
    drafts = data.get("drafts") if isinstance(data.get("drafts"), list) else []
    count = int(data.get("count") or len(drafts) or 0)
    lines = ["🧾 社媒待审草稿", ""]
    lines.append(f"- 队列数量: {count} 条")
    lines.append("- 安全边界: 只审核/排程，不自动发布、不自动评论、不关注/私信")

    if not drafts:
        lines.append("")
        lines.append("暂无待审草稿：可以先在插件里点“生成待审草稿”或用 /social_growth_drafts 生成一批。")
        return "\n".join(lines)

    lines.append("")
    lines.append("草稿列表（可用序号或草稿 ID 操作）:")
    for idx, draft in enumerate(drafts[:10], 1):
        if not isinstance(draft, dict):
            continue
        draft_id = str(draft.get("id") or draft.get("draft_id") or f"序号 {idx}")
        platform = _social_review_platform_label(str(draft.get("platform") or ""))
        title = str(draft.get("title") or draft.get("topic") or "未命名草稿")[:80]
        text = str(draft.get("text") or draft.get("body") or draft.get("content") or "")[:120]
        review_status = str(draft.get("review_status") or "pending")
        status = str(draft.get("status") or "needs_review")
        lines.append(f"{idx}. [{platform}] {title}")
        lines.append(f"   ID: {draft_id} · 状态: {review_status}/{status}")
        if text:
            lines.append(f"   预览: {text}")

    lines.append("")
    lines.append("操作:")
    lines.append("- /social_review_approve <序号或ID>  确认内容")
    lines.append("- /social_review_reject <序号或ID>  打回草稿")
    lines.append("- /social_review_schedule <序号或ID> 明天8点  加入待发布排程")
    lines.append("到点后仍需要最终确认，不会自动外发。")
    return "\n".join(lines)


def _format_social_review_action_message(payload: dict, action_label: str = "操作") -> str:
    """格式化 Telegram 审核/排程动作结果；强调仍保留人工外发闸门。"""
    data = payload if isinstance(payload, dict) else {}
    success = bool(data.get("success"))
    draft = data.get("draft") if isinstance(data.get("draft"), dict) else {}
    schedule_item = data.get("schedule_item") if isinstance(data.get("schedule_item"), dict) else {}
    draft_id = str(draft.get("id") or schedule_item.get("draft_id") or data.get("draft_id") or "未知草稿")
    platform = _social_review_platform_label(str(draft.get("platform") or schedule_item.get("platform") or ""))
    title = str(draft.get("title") or schedule_item.get("title") or draft.get("text") or "未命名草稿")[:90]

    if not success:
        error = str(data.get("error") or "操作失败")
        lines = [f"⚠️ {action_label}失败", ""]
        lines.append(f"- 草稿: {draft_id}")
        lines.append(f"- 原因: {error}")
        lines.append("- 安全边界: 未完成确认前不会发布、不评论、不推广")
        next_action = str(data.get("next_action") or "请先查看 /social_review_drafts，确认草稿编号或 ID 后重试。")
        lines.append(f"下一步: {next_action}")
        return "\n".join(lines)

    lines = [f"✅ {action_label}成功", ""]
    lines.append(f"- 草稿: {draft_id}")
    lines.append(f"- 平台: {platform}")
    lines.append(f"- 标题: {title}")
    if draft:
        lines.append(f"- 状态: {draft.get('review_status', 'pending')}/{draft.get('status', 'needs_review')}")
    if schedule_item:
        lines.append(f"- 排程时间: {schedule_item.get('scheduled_at', '')}")
        lines.append(f"- 排程状态: {schedule_item.get('status', '')}")
    lines.append("- 安全边界: 不自动发布、不自动评论、不关注/私信")
    next_action = str(data.get("next_action") or "下一步：到点后仍需要你最终确认外发。")
    lines.append(f"下一步: {next_action}")
    return "\n".join(lines)


def _format_social_review_schedule_message(payload: dict) -> str:
    """格式化插件待发布排程队列；只提醒最终确认，不自动发布。"""
    data = payload if isinstance(payload, dict) else {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    count = int(data.get("count") or len(items) or 0)
    due_count = int(data.get("due_count") or 0)
    lines = ["🕒 社媒待发布排程", ""]
    lines.append(f"- 队列数量: {count} 条")
    lines.append(f"- 等待最终确认: {due_count} 条")
    lines.append("- 安全边界: 到点只提醒最终确认，不自动发布、不自动评论、不推广")

    if not items:
        lines.append("")
        lines.append("暂无排程：先确认草稿，再用 /social_review_schedule <序号或ID> 明天8点 加入排程。")
        return "\n".join(lines)

    lines.append("")
    lines.append("排程列表（可用序号或草稿 ID 最终确认）:")
    for idx, item in enumerate(items[:10], 1):
        if not isinstance(item, dict):
            continue
        draft = item.get("draft") if isinstance(item.get("draft"), dict) else {}
        draft_id = str(item.get("draft_id") or draft.get("id") or item.get("id") or f"序号 {idx}")
        platform = _social_review_platform_label(str(item.get("platform") or draft.get("platform") or ""))
        title = str(item.get("title") or draft.get("title") or draft.get("text") or "未命名草稿")[:80]
        status = str(item.get("status") or item.get("schedule_status") or "queued_for_owner_publish")
        scheduled_at = str(item.get("scheduled_at") or draft.get("scheduled_at") or "")
        text = str(draft.get("text") or item.get("text_preview") or "")[:100]
        lines.append(f"{idx}. [{platform}] {title}")
        lines.append(f"   ID: {draft_id} · 时间: {scheduled_at} · 状态: {status}")
        if text:
            lines.append(f"   预览: {text}")

    lines.append("")
    lines.append("操作:")
    lines.append("- /social_review_final_confirm <序号或ID>  标记为可手动发布")
    lines.append("注意：最终确认仍不点击平台发布按钮，只把状态交给插件/人工页面操作。")
    return "\n".join(lines)


def _normalize_social_review_schedule_time(value: str, now: datetime | None = None) -> str:
    """把“明天8点/2小时后/今天20:30”等口语时间规整为带时区 ISO 时间。"""
    raw = str(value or "").strip()
    if not raw:
        return ""

    current = now or datetime.now().astimezone()
    compact = raw.replace("：", ":").replace("/", "-")

    relative_hour = re.search(r"(\d{1,3})\s*小时后", compact)
    if relative_hour:
        return (current + timedelta(hours=int(relative_hour.group(1)))).isoformat(timespec="seconds")

    relative_minute = re.search(r"(\d{1,4})\s*分钟后", compact)
    if relative_minute:
        return (current + timedelta(minutes=int(relative_minute.group(1)))).isoformat(timespec="seconds")

    full_date = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})\s*(\d{1,2})(?::(\d{1,2}))?", compact)
    if full_date:
        year, month, day, hour, minute = full_date.groups()
        return current.replace(
            year=int(year),
            month=int(month),
            day=int(day),
            hour=int(hour),
            minute=int(minute or 0),
            second=0,
            microsecond=0,
        ).isoformat(timespec="seconds")

    short_date = re.search(r"(?<!\d)(\d{1,2})-(\d{1,2})\s*(\d{1,2})(?::(\d{1,2}))?", compact)
    if short_date:
        month, day, hour, minute = short_date.groups()
        return current.replace(
            month=int(month),
            day=int(day),
            hour=int(hour),
            minute=int(minute or 0),
            second=0,
            microsecond=0,
        ).isoformat(timespec="seconds")

    day_offset = 0
    if "后天" in compact:
        day_offset = 2
    elif "明天" in compact or "明日" in compact:
        day_offset = 1
    target = current + timedelta(days=day_offset)
    time_match = re.search(r"(\d{1,2})(?:点|:)(\d{1,2})?", compact)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        return target.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(timespec="seconds")

    return raw


def _resolve_social_review_target(identifier: str) -> dict:
    """把 Telegram 输入的序号或草稿 ID 解析成可执行审核目标。"""
    clean = str(identifier or "").strip()
    if not clean:
        return {"success": False, "error": "缺少草稿序号或 ID"}
    if clean.isdigit():
        display_index = int(clean)
        rpc_index = display_index - 1
        payload = ClawBotRPC._rpc_social_drafts()
        drafts = payload.get("drafts") if isinstance(payload.get("drafts"), list) else []
        if not (0 <= rpc_index < len(drafts)):
            return {"success": False, "error": f"找不到序号 {display_index} 对应的草稿"}
        draft = drafts[rpc_index] if isinstance(drafts[rpc_index], dict) else {}
        return {
            "success": True,
            "identifier": clean,
            "rpc_index": rpc_index,
            "draft_id": str(draft.get("id") or draft.get("draft_id") or ""),
            "source": str(draft.get("_state_source") or ""),
            "draft": draft,
        }
    try:
        payload = ClawBotRPC._rpc_social_drafts()
        drafts = payload.get("drafts") if isinstance(payload.get("drafts"), list) else []
        for idx, draft in enumerate(drafts):
            if not isinstance(draft, dict):
                continue
            visible_id = str(draft.get("id") or draft.get("draft_id") or "").strip()
            if visible_id != clean:
                continue
            return {
                "success": True,
                "identifier": clean,
                "rpc_index": idx,
                "draft_id": visible_id,
                "source": str(draft.get("_state_source") or ""),
                "draft": draft,
            }
    except Exception as e:
        logger.debug("按草稿 ID 查找统一草稿队列失败: %s", e)
    return {
        "success": True,
        "identifier": clean,
        "rpc_index": None,
        "draft_id": clean,
        "source": "x_auto_ops",
        "draft": {},
    }


def _resolve_social_schedule_target(identifier: str) -> dict:
    """把 Telegram 排程序号或草稿 ID 解析成最终确认用 draft_id。"""
    clean = str(identifier or "").strip()
    if not clean:
        return {"success": False, "error": "缺少排程序号或草稿 ID"}
    try:
        payload = ClawBotRPC._rpc_social_extension_schedule_queue(50)
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        if clean.isdigit():
            index = int(clean) - 1
            if not (0 <= index < len(items)):
                return {"success": False, "error": f"找不到序号 {clean} 对应的排程"}
            item = items[index] if isinstance(items[index], dict) else {}
            draft_id = str(item.get("draft_id") or (item.get("draft") or {}).get("id") or "").strip()
            if not draft_id:
                return {"success": False, "error": "该排程缺少草稿 ID"}
            return {"success": True, "draft_id": draft_id, "item": item}
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            draft_id = str(item.get("draft_id") or (item.get("draft") or {}).get("id") or "").strip()
            if clean in {item_id, draft_id}:
                return {"success": True, "draft_id": draft_id or clean, "item": item}
    except Exception as e:
        logger.debug("解析社媒排程目标失败: %s", e)
    return {"success": True, "draft_id": clean, "item": {}}


def _run_social_review_action(identifier: str, approved: bool) -> dict:
    """执行确认/打回：优先用插件草稿 ID，兼容旧序号审核。"""
    target = _resolve_social_review_target(identifier)
    if not target.get("success"):
        return {
            **target,
            "auto_publish_enabled": False,
            "external_actions_locked": True,
        }
    rpc_index = target.get("rpc_index")
    if isinstance(rpc_index, int):
        result = ClawBotRPC._rpc_social_draft_review(rpc_index, approved=approved, reviewer="telegram")
        result.setdefault("auto_publish_enabled", False)
        result.setdefault("external_actions_locked", True)
        result.setdefault(
            "next_action",
            "已更新审核状态；仍不会自动发布，外发需要后续明确确认。",
        )
        return result
    draft_id = str(target.get("draft_id") or "")
    if draft_id:
        return ClawBotRPC._rpc_social_extension_draft_review(draft_id, approved=approved, reviewer="telegram")
    return {
        "success": False,
        "error": "无法解析草稿目标",
        "auto_publish_enabled": False,
        "external_actions_locked": True,
    }


def _format_social_growth_feedback_message(payload: dict) -> str:
    """把增长复盘摘要格式化为 Telegram 可读文本；只读展示，不授权外部动作。"""
    data = payload if isinstance(payload, dict) else {}
    platform = str(data.get("platform") or "x").upper()
    signals = data.get("signals") if isinstance(data.get("signals"), list) else []
    recommendations = data.get("recommendations") if isinstance(data.get("recommendations"), list) else []
    top_tags = data.get("top_tags") if isinstance(data.get("top_tags"), list) else []
    high_count = int(data.get("high_signal_count") or len(signals) or 0)

    lines = [f"📈 社媒增长复盘 | {platform}", ""]
    lines.append(f"- 高信号内容: {high_count} 条")
    if top_tags:
        lines.append(f"- 优先标签: {' / '.join(str(tag) for tag in top_tags[:5])}")
    lines.append("- 安全边界: 只读复盘，不自动发布、不自动评论、不推广")

    if signals:
        lines.append("")
        lines.append("高信号样本:")
        for idx, signal in enumerate(signals[:3], 1):
            if not isinstance(signal, dict):
                continue
            metrics = signal.get("metrics") if isinstance(signal.get("metrics"), dict) else {}
            title = str(signal.get("title") or "未命名内容")[:80]
            likes = int(metrics.get("likes") or 0)
            comments = int(metrics.get("comments") or 0)
            shares = int(metrics.get("shares") or 0)
            impressions = int(metrics.get("impressions") or 0)
            lines.append(f"{idx}. {title}")
            lines.append(f"   {likes}赞 · {comments}评 · {shares}转 · {impressions}曝光")
            learning = str(signal.get("learning") or signal.get("growth_feedback_reason") or "复用该内容的 hook、标签和可执行步骤。")[:120]
            lines.append(f"   复用: {learning}")
            tags = signal.get("tags") if isinstance(signal.get("tags"), list) else []
            if tags:
                lines.append(f"   标签: {' / '.join(str(tag) for tag in tags[:4])}")
    else:
        lines.append("")
        lines.append("暂无高信号样本：先发布少量已审核内容，再在插件里点“采表现”建立基线。")

    if recommendations:
        lines.append("")
        lines.append("下一步建议:")
        for item in recommendations[:3]:
            lines.append(f"- {str(item)[:120]}")

    next_action = str(data.get("next_action") or "继续用 App/插件确认草稿；复盘只调选题权重。")
    lines.append("")
    lines.append(f"下一步: {next_action}")
    return "\n".join(lines)


def _format_social_growth_drafts_message(payload: dict) -> str:
    """把增长复盘反哺草稿结果格式化为 Telegram 文本；只展示待审稿。"""
    data = payload if isinstance(payload, dict) else {}
    platform = str(data.get("platform") or "x").upper()
    drafts = data.get("drafts") if isinstance(data.get("drafts"), list) else []
    created_count = int(data.get("created_count") or len(drafts) or 0)
    lines = [f"🧪 增长复盘反哺草稿 | {platform}", ""]
    lines.append(f"- 已生成待审草稿: {created_count} 条")
    lines.append("- 安全边界: 只进入待审，不自动发布、不自动评论、不推广")
    if drafts:
        lines.append("")
        lines.append("待审草稿:")
        for idx, draft in enumerate(drafts[:5], 1):
            if not isinstance(draft, dict):
                continue
            title = str(draft.get("title") or draft.get("topic") or "未命名草稿")[:80]
            text = str(draft.get("text") or draft.get("body") or "")[:100]
            status = str(draft.get("review_status") or "pending")
            lines.append(f"{idx}. {title} [{status}/待审]")
            if text:
                lines.append(f"   预览: {text}")
    else:
        lines.append("")
        lines.append("暂无可生成选题：先积累增长复盘样本，或刷新热点池。")
    lines.append("")
    lines.append(str(data.get("next_action") or "下一步：在 App/插件里逐条审核，确认前不会外发。"))
    return "\n".join(lines)



class SocialCommandsMixin:
    @staticmethod
    def _social_login_retry_hint(result, retry_command: str) -> str:
        if str(result.get("status", "") or "").strip().lower() != "login_required":
            return ""
        browser = result.get("browser", {}) or {}
        missing = []
        if browser.get("x_ready") is False:
            missing.append("X")
        if browser.get("xiaohongshu_ready") is False:
            missing.append("小红书")
        label = " / ".join(missing) if missing else "目标平台"
        return f"\nOpenClaw 专用浏览器已自动打开，请先登录{label}后重试 {retry_command}"

    @requires_auth
    async def cmd_hot(self, update, context):
        await self.cmd_hotpost(update, context)

    @requires_auth
    async def cmd_post_social(self, update, context):
        await self.cmd_post(update, context)

    @requires_auth
    async def cmd_post_x(self, update, context):
        await self.cmd_xpost(update, context)

    @requires_auth
    async def cmd_post_xhs(self, update, context):
        await self.cmd_xhspost(update, context)

    @requires_auth
    @with_typing
    async def cmd_social_persona(self, update, context):
        try:
            ret = await asyncio.to_thread(execution_hub.get_social_persona_summary)
            if not ret.get("success"):
                await update.message.reply_text(format_error(ret.get('error', '未知错误'), "读取社媒人设"))
                return
            lines = [f"当前社媒人设 | {ret.get('name', '')}", ""]
            if ret.get("headline"):
                lines.append(f"- 定位: {ret.get('headline')}")
            if ret.get("truth"):
                lines.append(f"- 真相声明: {ret.get('truth')}")
            if ret.get("background"):
                lines.append(f"- 外壳背景: {ret.get('background')}")
            keywords = ret.get("voice_keywords", []) or []
            if keywords:
                lines.append(f"- 声线关键词: {' / '.join(keywords[:6])}")
            must_keep = ret.get("must_keep", []) or []
            if must_keep:
                lines.append(f"- 必须保留: {'；'.join(must_keep[:3])}")
            avoid = ret.get("avoid", []) or []
            if avoid:
                lines.append(f"- 明确避免: {'；'.join(avoid[:3])}")
            if ret.get("x_style"):
                lines.append(f"- X 风格: {ret.get('x_style')}")
            if ret.get("xhs_style"):
                lines.append(f"- 小红书风格: {ret.get('xhs_style')}")
            if ret.get("path"):
                lines.append(f"- 人设文件: {ret.get('path')}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
        except Exception as e:
            logger.warning("[cmd_social_persona] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_social_launch(self, update, context):
        await update.message.reply_text("正在生成数字生命首发包并写入草稿...")
        ret = await asyncio.to_thread(execution_hub.create_social_launch_drafts)
        if not ret.get("success"):
            await update.message.reply_text(format_error(ret.get('error', '未知错误'), "生成首发包"))
            return
        persona = ret.get("persona", {}) or {}
        lines = [f"数字生命首发包 | {persona.get('name', '')}", ""]
        if persona.get("bio"):
            lines.append(f"- 简介: {persona.get('bio')}")
        x_ret = ret.get("x", {}) or {}
        xhs_ret = ret.get("xiaohongshu", {}) or {}
        lines.append(f"- X 草稿: {x_ret.get('draft_id') or x_ret.get('existing_id') or '未写入'}")
        lines.append(f"- X 首发: {x_ret.get('body', '')}")
        lines.append(f"- 小红书草稿: {xhs_ret.get('draft_id') or xhs_ret.get('existing_id') or '未写入'}")
        lines.append(f"- 小红书标题: {xhs_ret.get('title', '')}")
        lines.append(f"- 小红书正文: {xhs_ret.get('body', '')}")
        image_payload = ret.get("image", {}) or {}
        prompt = str(image_payload.get("prompt", "") or "").strip()
        negative_prompt = str(image_payload.get("negative_prompt", "") or "").strip()
        provider = ""
        generated_paths = []
        if prompt:
            key = get_siliconflow_key()
            image_tool.set_api_key(key or "")
            generation_prompt = f"{prompt}, avoid underage appearance, adult woman only"
            if negative_prompt:
                generation_prompt += f", negative prompt guidance: {negative_prompt}"
            image_ret = await image_tool.generate(generation_prompt, model=IMG_MODEL_FLUX, size=str(image_payload.get("size", "1024x1024") or "1024x1024"))
            provider = str(image_ret.get("provider", "siliconflow") or "siliconflow")
            generated_paths = list(image_ret.get("paths", []) or [])
            if image_ret.get("success"):
                for path in generated_paths[:3]:
                    try:
                        with open(path, "rb") as f:
                            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=f, caption=f"数字生命自拍 | {persona.get('name', '')}")
                    except Exception:
                        logger.exception("发送数字生命自拍失败: %s", path)
            else:
                lines.append(error_service_failed("自拍生成", image_ret.get('error', '')))
        lines.append(f"- 自拍 Prompt: {prompt}")
        lines.append(f"- 负面词: {(ret.get('image', {}) or {}).get('negative_prompt', '')}")
        if generated_paths:
            lines.append(f"- 自拍已生成: {generated_paths[0]}")
            lines.append(f"- 图片来源: {provider}")
        next_topics = ret.get("next_topics", []) or []
        if next_topics:
            lines.append(f"- 后续选题: {'；'.join(next_topics[:3])}")
        if x_ret.get("draft_id") or xhs_ret.get("draft_id") or x_ret.get("existing_id") or xhs_ret.get("existing_id"):
            lines.append("- 下一步: /post_x <X草稿ID> 或 /post_xhs <小红书草稿ID>")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    @requires_auth
    @with_typing
    async def cmd_topic(self, update, context):
        try:
            topic = " ".join(context.args or []).strip() or "AI出海"
            await update.message.reply_text(f"正在研究题材：{topic}")
            ret = await execution_hub.research_social_topic(topic, limit=5)
            if not ret.get("success"):
                await update.message.reply_text(format_error(ret.get('error', '未知错误'), "题材研究"))
                return
            research = ret.get("research", {}) or {}
            strategy = ret.get("strategy", {}) or {}
            lines = [f"题材研究 | {topic}", ""]
            lines.append("热点来源:")
            for item in (research.get("x") or [])[:3]:
                lines.append(f"- [X] {item.get('title', '')}")
            for item in (research.get("xiaohongshu") or [])[:3]:
                lines.append(f"- [小红书] {item.get('title', '')}")
            lines.append("")
            lines.append("学习结论:")
            lines.append(f"- 实用价值分: {strategy.get('utility_score', 0)}/100")
            if strategy.get("positioning"):
                lines.append(f"- 内容定位: {strategy.get('positioning')}")
            if strategy.get("audience"):
                lines.append(f"- 目标受众: {strategy.get('audience')}")
            if strategy.get("primary_format"):
                lines.append(f"- 推荐形式: {strategy.get('primary_format')}")
            lines.append(f"- 结构: {' / '.join(strategy.get('patterns', [])[:3]) or '短结论 + 清单展开'}")
            if strategy.get("opportunity"):
                lines.append(f"- 信息差: {strategy.get('opportunity')}")
            if strategy.get("mvp_rule"):
                lines.append(f"- MVP原则: {strategy.get('mvp_rule')}")
            if strategy.get("x_warning"):
                lines.append(f"- X提醒: {strategy.get('x_warning')}")
            if strategy.get("x_tactic"):
                lines.append(f"- X打法: {strategy.get('x_tactic')}")
            if strategy.get("xhs_tactic"):
                lines.append(f"- 小红书打法: {strategy.get('xhs_tactic')}")
            if strategy.get("lead_magnet"):
                lines.append(f"- 诱饵/资料包: {strategy.get('lead_magnet')}")
            if strategy.get("cta"):
                lines.append(f"- CTA: {strategy.get('cta')}")
            proof_assets = strategy.get("proof_assets", []) or []
            if proof_assets:
                lines.append(f"- 证明材料: {'；'.join(proof_assets[:3])}")
            repurpose_path = strategy.get("repurpose_path", []) or []
            if repurpose_path:
                lines.append(f"- 发布路径: {' -> '.join(repurpose_path[:4])}")
            if strategy.get("measurement_window"):
                lines.append(f"- 观察窗口: {strategy.get('measurement_window')}")
            metrics = strategy.get("validation_metrics", []) or []
            if metrics:
                lines.append(f"- 验证指标: {'；'.join(metrics[:2])}")
            triggers = strategy.get("investment_triggers", []) or []
            if triggers:
                lines.append(f"- 加预算触发点: {'；'.join(triggers[:2])}")
            if strategy.get("stale_points"):
                lines.append(f"- 需避开: {'；'.join(strategy.get('stale_points', [])[:2])}")
            lines.append(f"- 学习存档: {ret.get('memory_path', '')}")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
        except Exception as e:
            logger.warning("[cmd_topic] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_xhs(self, update, context):
        try:
            topic = " ".join(context.args or []).strip()
            if not topic:
                await update.message.reply_text("📕 小红书热点发布中...")
                ret = await execution_hub.autopost_hot_content("xiaohongshu")
                package = (ret.get("results", {}) or {}).get("xiaohongshu", {})
                if not package:
                    await update.message.reply_text(error_service_failed("小红书热点发布", package.get('error', ret.get('error', ''))))
                    return
                published = package.get("published", {}) or {}
                if not published.get("success"):
                    await update.message.reply_text(
                        f"小红书发布未完成: {published.get('error', published.get('raw', '未知错误'))}"
                        f"{self._social_login_retry_hint(published, '/post_xhs')}"
                    )
                    return
                text = format_social_published(
                    platform="xiaohongshu",
                    topic=package.get("topic", ""),
                    url=published.get("url", ""),
                    title=package.get("title", ""),
                    memory_path=package.get("memory_path", ""),
                )
                if package.get("trend_label"):
                    text = f" 📈 蹭热点: {package.get('trend_label')}\n{text}"
                await send_long_message(update.effective_chat.id, text, context)
                return

            await update.message.reply_text(f"📕 小红书发布: {topic}")
            ret = await execution_hub.autopost_topic_content("xiaohongshu", topic)
            if not ret.get("success"):
                await update.message.reply_text(
                    error_service_failed("小红书发帖", ret.get('error', ''))
                    + f"\n{self._social_login_retry_hint(ret.get('published', ret), '/post_xhs ' + topic if topic else '/post_xhs')}"
                )
                return
            published = ret.get("published", {}) or {}
            if not published.get("success"):
                await update.message.reply_text(
                    f"小红书发布未完成: {published.get('error', published.get('raw', '未知错误'))}"
                    f"{self._social_login_retry_hint(published, f"/post_xhs {topic}" if topic else '/post_xhs')}"
                )
                return
            text = format_social_published(
                platform="xiaohongshu",
                topic=topic,
                url=published.get("url", ""),
                title=ret.get("title", ""),
                memory_path=ret.get("memory_path", ""),
            )
            await send_long_message(update.effective_chat.id, text, context)
        except Exception as e:
            logger.warning("[cmd_xhs] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_post(self, update, context):
        try:
            topic = " ".join(context.args or []).strip()
            if not topic:
                await self.cmd_hotpost(update, context)
                return
            await update.message.reply_text(f"📱 双平台发文: {topic}")
            xhs = await execution_hub.autopost_topic_content("xiaohongshu", topic)
            xret = await execution_hub.autopost_topic_content("x", topic)
            mem = xhs.get('memory_path') or xret.get('memory_path') or ''
            hint = self._social_login_retry_hint(xhs.get('published', xhs), f"/post {topic}") or self._social_login_retry_hint(xret.get('published', xret), f"/post {topic}")
            text = format_social_dual_result(
                topic=topic,
                xhs_result=xhs,
                x_result=xret,
                memory_path=mem,
            )
            if hint:
                text += f"\n{hint.strip()}"
            await send_long_message(update.effective_chat.id, text, context)
        except Exception as e:
            logger.warning("[cmd_post] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_hotpost(self, update, context):
        args = context.args or []
        platform = "all"
        topic = ""
        preview_mode = False

        # 解析参数：支持 --preview 预览模式
        filtered_args = []
        for a in args:
            if a.lower() in {"--preview", "-p", "preview"}:
                preview_mode = True
            else:
                filtered_args.append(a)
        args = filtered_args

        # 用户偏好：如果设置了 social_preview=True，默认预览模式
        if not preview_mode:
            try:
                from src.bot.globals import user_prefs
                if user_prefs.get(update.effective_user.id, "social_preview", False):
                    preview_mode = True
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

        if args and str(args[0]).lower() in {"x", "xhs", "xiaohongshu", "all", "both", "dual"}:
            raw_platform = str(args[0]).lower()
            platform = "xiaohongshu" if raw_platform in {"xhs", "xiaohongshu"} else raw_platform
            topic = " ".join(args[1:]).strip()
        else:
            topic = " ".join(args).strip()

        if preview_mode:
            # 预览模式 — 搬运自 ConversationHandler 向导模式
            # 生成内容但不发布，用户确认后才发
            await update.message.reply_text("🔥 生成内容预览中...")
            try:
                package = await execution_hub.create_hot_social_package(
                    platform=platform, topic=topic,
                )
                if not package or not package.get("results"):
                    await update.message.reply_text(
                        error_service_failed("内容生成", package.get('error', '') if package else '无结果'))
                    return

                # 构建预览文本
                preview_lines = ["📝 <b>发文预览</b>\n"]
                results = package.get("results", {})
                for plat, content in results.items():
                    icon = "𝕏" if plat == "x" else "📕"
                    if isinstance(content, dict):
                        title = content.get("title", "")
                        body = content.get("body", "") or content.get("text", "")
                        if title:
                            preview_lines.append(f"{icon} <b>{plat}</b>\n标题: {title}\n{body[:300]}{'...' if len(body) > 300 else ''}\n")
                        else:
                            preview_lines.append(f"{icon} <b>{plat}</b>\n{body[:300]}{'...' if len(body) > 300 else ''}\n")
                    elif isinstance(content, str):
                        preview_lines.append(f"{icon} <b>{plat}</b>\n{content[:300]}{'...' if len(content) > 300 else ''}\n")

                preview_lines.append("━━━━━━━━━━━━━━━")
                preview_lines.append("确认发布？点击下方按钮")

                # 存储 package 到 user_data，等待确认
                context.user_data["pending_social_package"] = package

                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ 确认发布", callback_data="social_confirm:publish"),
                        InlineKeyboardButton("❌ 取消", callback_data="social_confirm:cancel"),
                    ],
                    [
                        InlineKeyboardButton("🔄 重新生成", callback_data="social_confirm:regenerate"),
                    ],
                ])
                from telegram.constants import ParseMode
                await update.message.reply_text(
                    "\n".join(preview_lines),
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            except Exception as e:
                from src.telegram_ux import send_error_with_retry
                await send_error_with_retry(update, context, e, retry_command=f"/hot --preview {topic}")
            return

        # 非预览模式 — 直接发布（原有逻辑）
        if topic:
            await update.message.reply_text(f"🔥 抓取「{topic}」热点并发文...")
        else:
            await update.message.reply_text("🔥 抓取今日热点并发文...")

        ret = await execution_hub.autopost_hot_content(platform=platform, topic=topic)
        if not ret.get("results"):
            await update.message.reply_text(format_error(ret.get('error', '未知错误'), "热点发文"))
            return

        # A/B 测试追踪 — 记录发布的内容变体
        try:
            from src.bot.globals import ab_test_manager
            if ab_test_manager:
                for plat, plat_result in (ret.get("results") or {}).items():
                    content = plat_result.get("content", "") or plat_result.get("title", "")
                    if content:
                        test = ab_test_manager.create_test(
                            name=f"hotpost_{plat}_{(topic or 'auto')[:20]}",
                            contents=[content],
                        )
                        variant_id, _ = ab_test_manager.get_content(test.test_id)
                        if plat_result.get("published", {}).get("success"):
                            ab_test_manager.record_engagement(test.test_id, variant_id, event="publish")
        except Exception:
            logger.debug("Silenced exception", exc_info=True)  # A/B 追踪不影响主流程

        hint = self._social_login_retry_hint(
            (ret.get("results", {}) or {}).get("xiaohongshu", {}).get("published", {}), "/hot"
        ) or self._social_login_retry_hint(
            (ret.get("results", {}) or {}).get("x", {}).get("published", {}), "/hot"
        )
        text = format_hotpost_result(
            topic=ret.get("topic", topic or "自动选题"),
            trend_label=ret.get("trend_label", ""),
            results=ret.get("results", {}),
            login_hint=hint or "",
        )
        await send_long_message(update.effective_chat.id, text, context)

    @requires_auth
    @with_typing
    async def cmd_social_plan(self, update, context):
        try:
            topic = " ".join(context.args or []).strip()
            if topic:
                await update.message.reply_text(f"正在生成题材发文计划：{topic}")
            else:
                await update.message.reply_text("正在生成今日社媒发文计划...")
            ret = await execution_hub.build_social_plan(topic=topic, limit=3)
            if not ret.get("success"):
                await update.message.reply_text(format_error(ret.get('error', '未知错误'), "生成发文计划"))
                return
            if ret.get("mode") == "topic":
                strategy = ret.get("strategy", {}) or {}
                lines = [f"社媒发文计划 | {ret.get('topic', topic)}", ""]
                lines.append(f"- 定位: {strategy.get('positioning', 'OpenClaw 实操内容')}" )
                if strategy.get("x_tactic"):
                    lines.append(f"- X: {strategy.get('x_tactic')}")
                if strategy.get("xhs_tactic"):
                    lines.append(f"- 小红书: {strategy.get('xhs_tactic')}")
                if strategy.get("cta"):
                    lines.append(f"- CTA: {strategy.get('cta')}")
                if strategy.get("measurement_window"):
                    lines.append(f"- 观察窗口: {strategy.get('measurement_window')}")
                for action in (ret.get("next_actions", []) or [])[:2]:
                    lines.append(f"- 下一步: {action}")
                await send_long_message(update.effective_chat.id, "\n".join(lines), context)
                return

            lines = ["今日社媒发文计划", ""]
            for idx, item in enumerate((ret.get("plans", []) or [])[:3], 1):
                lines.append(f"{idx}. {item.get('topic', '')} | {item.get('trend_label', '')}")
                if item.get("hook"):
                    lines.append(f"   切角: {item.get('hook')}")
                if item.get("x_tactic"):
                    lines.append(f"   X: {item.get('x_tactic')}")
                if item.get("xhs_tactic"):
                    lines.append(f"   小红书: {item.get('xhs_tactic')}")
            lines.append("")
            lines.append("下一步: /social_repost <题材> 或 /post_social <题材>")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
        except Exception as e:
            logger.warning("[cmd_social_plan] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_social_repost(self, update, context):
        try:
            topic = " ".join(context.args or []).strip()
            if topic:
                await update.message.reply_text(f"正在生成双平台改写草稿：{topic}")
            else:
                await update.message.reply_text("正在把今日热点改写成双平台草稿...")
            ret = await execution_hub.build_social_repost_bundle(topic=topic)
            if not ret.get("success"):
                await update.message.reply_text(format_error(ret.get('error', '未知错误'), "双平台改写"))
                return
            lines = [f"双平台改写 | {ret.get('topic', topic or '自动选题')}", ""]
            for name in ["xiaohongshu", "x"]:
                package = (ret.get("results", {}) or {}).get(name, {}) or {}
                label = "小红书" if name == "xiaohongshu" else "X"
                if package.get("success"):
                    if package.get("draft_id"):
                        lines.append(f"- {label}草稿ID: {package.get('draft_id')}")
                    if package.get("title"):
                        lines.append(f"- {label}标题: {package.get('title')}")
                    lines.append(f"- {label}预览: {str(package.get('body', '') or '')[:88]}")
                else:
                    lines.append(f"- {error_service_failed(label, package.get('error', ''))}")
            lines.append("")
            lines.append(f"下一步: /post_social {ret.get('topic', topic or '').strip()}".rstrip())
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
        except Exception as e:
            logger.warning("[cmd_social_repost] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)


    @requires_auth
    @with_typing
    async def cmd_xwatch(self, update, context):
        source = " ".join(context.args or []).strip()
        if not source:
            await update.message.reply_text("用法: /xwatch <X合集推文链接>")
            return
        await self._ops_tweet(update, context, ["watch", source])

    @requires_auth
    @with_typing
    async def cmd_xbrief(self, update, context):
        try:
            await update.message.reply_text("正在生成 X 博主更新摘要...")
            digest = await execution_hub.generate_x_monitor_brief()
            if not digest:
                await update.message.reply_text("当前没有 X 博主更新，先用 /xwatch 或 /ops monitor addx 添加监控")
                return
            await send_long_message(update.effective_chat.id, digest, context)
        except Exception as e:
            logger.warning("[cmd_xbrief] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_xdraft(self, update, context):
        try:
            topic = " ".join(context.args or []).strip()
            await update.message.reply_text("正在生成 X 草稿...")
            ret = await execution_hub.create_social_draft("x", topic=topic, max_items=3)
            if not ret.get("success"):
                await update.message.reply_text(format_error(ret.get('error', '未知错误'), "X 草稿生成"))
                return
            lines = ["X 草稿", ""]
            lines.append(f"草稿ID: {ret.get('draft_id')}")
            if topic:
                lines.append(f"主题: {topic}")
            lines.append(ret.get("body", ""))
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
        except Exception as e:
            logger.warning("[cmd_xdraft] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_xpost(self, update, context):
        try:
            args = context.args or []
            draft_id = 0
            topic = ""
            if args and str(args[0]).isdigit():
                draft_id = int(args[0])
            else:
                topic = " ".join(args).strip()
            if draft_id <= 0:
                draft = await execution_hub.create_social_draft("x", topic=topic, max_items=3)
                if not draft.get("success"):
                    await update.message.reply_text(error_service_failed("X 发帖", draft.get('error', '')))
                    return
                draft_id = int(draft.get("draft_id", 0) or 0)
            await update.message.reply_text("正在拉起 OpenClaw 专用浏览器并自动发 X...")
            ret = await asyncio.to_thread(execution_hub.publish_social_draft, "x", draft_id)
            if ret.get("success"):
                await update.message.reply_text(f"X 已尝试自动发出，草稿ID: {ret.get('draft_id')}\n页面: {ret.get('url', '')}")
            else:
                await update.message.reply_text(
                    f"X 自动发帖未完成: {ret.get('status', ret.get('error', '未知错误'))}\n"
                    f"页面: {ret.get('url', '')}"
                    f"{self._social_login_retry_hint(ret, f"/post_x {topic}" if topic else '/post_x')}"
                )
        except Exception as e:
            logger.warning("[cmd_xpost] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_xhsdraft(self, update, context):
        try:
            topic = " ".join(context.args or []).strip()
            await update.message.reply_text("正在生成小红书草稿...")
            ret = await execution_hub.create_social_draft("xiaohongshu", topic=topic, max_items=5)
            if not ret.get("success"):
                await update.message.reply_text(error_service_failed("小红书草稿", ret.get('error', '')))
                return
            lines = ["小红书草稿", ""]
            lines.append(f"草稿ID: {ret.get('draft_id')}")
            lines.append(f"标题: {ret.get('title', '')}")
            lines.append("")
            lines.append(ret.get("body", ""))
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
        except Exception as e:
            logger.warning("[cmd_xhsdraft] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_xhspost(self, update, context):
        try:
            args = context.args or []
            draft_id = 0
            topic = ""
            if args and str(args[0]).isdigit():
                draft_id = int(args[0])
            else:
                topic = " ".join(args).strip()
            if draft_id <= 0:
                draft = await execution_hub.create_social_draft("xiaohongshu", topic=topic, max_items=5)
                if not draft.get("success"):
                    await update.message.reply_text(error_service_failed("小红书发帖", draft.get('error', '')))
                    return
                draft_id = int(draft.get("draft_id", 0) or 0)
            await update.message.reply_text("正在拉起 OpenClaw 专用浏览器并自动发小红书...")
            ret = await asyncio.to_thread(execution_hub.publish_social_draft, "xiaohongshu", draft_id)
            if ret.get("success"):
                await update.message.reply_text(f"小红书已尝试自动发出，草稿ID: {ret.get('draft_id')}\n页面: {ret.get('url', '')}")
            else:
                await update.message.reply_text(
                    f"小红书自动发帖未完成: {ret.get('status', ret.get('error', '未知错误'))}\n"
                    f"页面: {ret.get('url', '')}"
                    f"{self._social_login_retry_hint(ret, f"/post_xhs {topic}" if topic else '/post_xhs')}"
                )
        except Exception as e:
            logger.warning("[cmd_xhspost] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    @requires_auth
    @with_typing
    async def cmd_publish(self, update, context):
        """发布内容到社交媒体 — /publish <平台> <视频/图片路径> [标题]"""
        try:
            from src.sau_bridge import PLATFORMS, get_supported_platforms, publish_note, publish_video

            args = context.args or []
            if len(args) < 2:
                platforms = get_supported_platforms()
                help_text = "📤 社媒发布\n\n用法:\n"
                help_text += "  /publish <平台> <文件路径> [标题]\n\n"
                help_text += "支持平台:\n"
                for key, info in platforms.items():
                    caps = []
                    if info["video"]:
                        caps.append("视频")
                    if info["note"]:
                        caps.append("图文")
                    help_text += f"  • {key} ({info['name']}) — {'/'.join(caps)}\n"
                help_text += "\n示例:\n  /publish douyin /path/to/video.mp4 我的视频标题"
                await update.message.reply_text(help_text)
                return

            platform = args[0].lower()
            file_path = args[1]
            title = " ".join(args[2:]) if len(args) > 2 else "OpenClaw 自动发布"

            if platform not in PLATFORMS:
                await update.message.reply_text(f"❓ 不支持的平台: {platform}\n支持: {', '.join(PLATFORMS.keys())}")
                return

            await update.message.reply_text(f"📤 正在发布到 {PLATFORMS[platform]['name']}...")

            if file_path.lower().endswith(('.mp4', '.mov', '.avi')):
                result = await publish_video(platform, file_path, title)
            else:
                result = await publish_note(platform, [file_path], title)

            if result.get("success"):
                await update.message.reply_text(f"✅ 发布到 {PLATFORMS[platform]['name']} 成功!")
            else:
                error = result.get("error", result.get("stderr", "未知错误"))
                await update.message.reply_text(f"⚠️ 发布失败: {error[:100]}")
        except Exception as e:
            logger.warning("[cmd_publish] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 命令执行失败，请稍后重试")
            except Exception as e:
                logger.debug("消息发送失败: %s", e)

    # ---- 闲鱼 AI 客服控制 ----

    @requires_auth
    @with_typing
    async def cmd_social_calendar(self, update, context):
        """生成/查看内容日历，支持 /social_calendar done N 标记完成"""
        args = context.args or []

        # 子命令: /social_calendar done 3 — 标记第3天已完成
        if args and args[0].lower() == "done":
            day_offset = 1
            if len(args) > 1:
                try:
                    day_offset = int(args[1])
                except ValueError as e:
                    logger.debug("用户输入解析失败: %s", e)
            result = execution_hub.mark_calendar_done(day_offset=day_offset)
            if result.get("success"):
                await update.message.reply_text(
                    f"✅ 第 {day_offset} 天（{result.get('date', '')}）已标记完成，"
                    f"更新 {result.get('updated', 0)} 条"
                )
            else:
                await update.message.reply_text(f"❌ {result.get('error', '标记失败')}")
            return

        days = 7
        if args:
            try:
                days = int(args[0])
            except ValueError as e:
                logger.debug("用户输入解析失败: %s", e)

        # 先查DB已有计划
        result = await execution_hub.generate_content_calendar(days=days)
        if not result.get("success"):
            await update.message.reply_text(format_error(result.get('error', '未知错误'), "生成内容日历"))
            return

        # 如果是从数据库返回的已有计划
        if result.get("from_db"):
            items = result.get("calendar_items", [])
            lines = [f"📅 内容日历（{days}天，已有计划）"]
            lines.append("")
            status_icon = {"planned": "⬜", "drafted": "📝", "published": "✅", "skipped": "⏭"}
            for item in items:
                icon = status_icon.get(item.get("status", "planned"), "⬜")
                plat = "𝕏" if item.get("platform") == "x" else ("📕" if item.get("platform") == "xhs" else "📱")
                time_str = item.get("scheduled_time", "")
                lines.append(
                    f"{icon} {item.get('plan_date', '')} {time_str} {plat} "
                    f"{item.get('topic', '')} [{item.get('content_type', '')}]"
                )
            lines.append("")
            lines.append("💡 用 /social_calendar done N 标记第N天已完成")
            await send_long_message(update.effective_chat.id, "\n".join(lines), context)
            return

        # AI 新生成的日历
        calendar = result.get("calendar", result.get("days", []))
        trending = result.get("trending", [])
        lines = [f"📅 内容日历（{days}天，新生成）"]
        if trending:
            lines.append(f"🔥 热点参考: {', '.join(trending[:3])}")
        lines.append("")
        for item in calendar:
            platform = "𝕏" if item.get("platform") == "x" else "📕"
            lines.append(f"Day {item.get('day', item.get('date', '?'))} {item.get('time', '')} {platform} {item.get('topic', '')}")
            lines.append(f"  → {item.get('hook', item.get('type', ''))}")
        lines.append("")
        lines.append("💡 用 /social_calendar done N 标记第N天已完成")
        await send_long_message(update.effective_chat.id, "\n".join(lines), context)


    @requires_auth
    @with_typing
    async def cmd_social_strategy(self, update, context):
        """Telegram 查询或切换 no-code 社媒运营打法；只改策略，不发布/评论。"""
        try:
            raw = " ".join(context.args or "").strip()
            if not raw:
                ret = await asyncio.to_thread(ClawBotRPC._rpc_social_ops_workspace)
                await send_long_message(update.effective_chat.id, _format_social_strategy_status_message(ret), context)
                return
            preset, platform = _normalize_social_strategy_args(raw)
            ret = await asyncio.to_thread(
                ClawBotRPC._rpc_social_extension_strategy_update,
                {
                    "strategyPreset": preset,
                    "platform": platform,
                    "source": "telegram",
                    "auto_publish_enabled": False,
                    "external_actions_locked": True,
                },
            )
            await send_long_message(update.effective_chat.id, _format_social_strategy_message(ret), context)
        except Exception as e:
            logger.warning("[cmd_social_strategy] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 运营打法切换失败，请稍后重试")
            except Exception as send_error:
                logger.debug("消息发送失败: %s", send_error)

    @requires_auth
    @with_typing
    async def cmd_social_growth_feedback(self, update, context):
        """Telegram 只读查看社媒增长复盘摘要。"""
        try:
            platform = " ".join(context.args or []).strip().lower() or "x"
            if platform in {"twitter", "推特"}:
                platform = "x"
            if platform in {"小红书", "xiaohongshu"}:
                platform = "xhs"
            ret = await asyncio.to_thread(
                ClawBotRPC._rpc_social_extension_growth_feedback,
                platform,
                6,
            )
            await send_long_message(update.effective_chat.id, _format_social_growth_feedback_message(ret), context)
        except Exception as e:
            logger.warning("[cmd_social_growth_feedback] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 增长复盘读取失败，请稍后重试")
            except Exception as send_error:
                logger.debug("消息发送失败: %s", send_error)

    @requires_auth
    @with_typing
    async def cmd_social_growth_drafts(self, update, context):
        """Telegram 触发增长复盘反哺待审草稿；不发布、不评论。"""
        try:
            platform = " ".join(context.args or []).strip().lower() or "x"
            if platform in {"twitter", "推特"}:
                platform = "x"
            if platform in {"小红书", "xiaohongshu"}:
                platform = "xhs"
            ret = await asyncio.to_thread(
                ClawBotRPC._rpc_social_extension_growth_draft_batch,
                platform,
                3,
            )
            await send_long_message(update.effective_chat.id, _format_social_growth_drafts_message(ret), context)
        except Exception as e:
            logger.warning("[cmd_social_growth_drafts] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 增长复盘反哺草稿生成失败，请稍后重试")
            except Exception as send_error:
                logger.debug("消息发送失败: %s", send_error)

    @requires_auth
    @with_typing
    async def cmd_social_review_drafts(self, update, context):
        """Telegram 查看社媒待审草稿队列；只读，不触发外部动作。"""
        try:
            ret = await asyncio.to_thread(ClawBotRPC._rpc_social_drafts)
            ret.setdefault("auto_publish_enabled", False)
            ret.setdefault("external_actions_locked", True)
            await send_long_message(update.effective_chat.id, _format_social_review_drafts_message(ret), context)
        except Exception as e:
            logger.warning("[cmd_social_review_drafts] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 待审草稿读取失败，请稍后重试")
            except Exception as send_error:
                logger.debug("消息发送失败: %s", send_error)

    @requires_auth
    @with_typing
    async def cmd_social_review_approve(self, update, context):
        """Telegram 确认一个待审草稿；只改审核状态，不发布。"""
        try:
            identifier = (context.args or [""])[0].strip() if context.args else ""
            if not identifier:
                await update.message.reply_text("用法：/social_review_approve <序号或草稿ID>")
                return
            ret = await asyncio.to_thread(_run_social_review_action, identifier, True)
            await send_long_message(
                update.effective_chat.id,
                _format_social_review_action_message(ret, action_label="确认"),
                context,
            )
        except Exception as e:
            logger.warning("[cmd_social_review_approve] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 草稿确认失败，请稍后重试")
            except Exception as send_error:
                logger.debug("消息发送失败: %s", send_error)

    @requires_auth
    @with_typing
    async def cmd_social_review_reject(self, update, context):
        """Telegram 打回一个待审草稿；只改审核状态，不删除、不发布。"""
        try:
            identifier = (context.args or [""])[0].strip() if context.args else ""
            if not identifier:
                await update.message.reply_text("用法：/social_review_reject <序号或草稿ID>")
                return
            ret = await asyncio.to_thread(_run_social_review_action, identifier, False)
            await send_long_message(
                update.effective_chat.id,
                _format_social_review_action_message(ret, action_label="打回"),
                context,
            )
        except Exception as e:
            logger.warning("[cmd_social_review_reject] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 草稿打回失败，请稍后重试")
            except Exception as send_error:
                logger.debug("消息发送失败: %s", send_error)

    @requires_auth
    @with_typing
    async def cmd_social_review_schedule(self, update, context):
        """Telegram 把已确认插件草稿加入排程；只登记，不自动外发。"""
        try:
            args = context.args or []
            identifier = args[0].strip() if args else ""
            if not identifier:
                await update.message.reply_text("用法：/social_review_schedule <序号或草稿ID> [明天8点]")
                return
            target = await asyncio.to_thread(_resolve_social_review_target, identifier)
            if not target.get("success"):
                await send_long_message(
                    update.effective_chat.id,
                    _format_social_review_action_message(target, action_label="排程"),
                    context,
                )
                return
            draft_id = str(target.get("draft_id") or "")
            source = str(target.get("source") or "")
            if not draft_id or source == "social_autopilot":
                await send_long_message(
                    update.effective_chat.id,
                    _format_social_review_action_message(
                        {
                            "success": False,
                            "draft_id": draft_id or identifier,
                            "error": "旧版社媒草稿暂不进入 Chrome 插件排程；请在插件或增长复盘入口生成新待审稿后排程。",
                            "auto_publish_enabled": False,
                            "external_actions_locked": True,
                        },
                        action_label="排程",
                    ),
                    context,
                )
                return
            raw_time = " ".join(args[1:]).strip()
            scheduled_at = _normalize_social_review_schedule_time(raw_time)
            ret = await asyncio.to_thread(
                ClawBotRPC._rpc_social_extension_draft_schedule,
                draft_id,
                scheduled_at,
                "telegram",
            )
            await send_long_message(
                update.effective_chat.id,
                _format_social_review_action_message(ret, action_label="排程"),
                context,
            )
        except Exception as e:
            logger.warning("[cmd_social_review_schedule] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 草稿排程失败，请稍后重试")
            except Exception as send_error:
                logger.debug("消息发送失败: %s", send_error)

    @requires_auth
    @with_typing
    async def cmd_social_review_schedule_queue(self, update, context):
        """Telegram 查看插件待发布排程队列；只读提醒最终确认。"""
        try:
            ret = await asyncio.to_thread(ClawBotRPC._rpc_social_extension_schedule_queue, 20)
            await send_long_message(
                update.effective_chat.id,
                _format_social_review_schedule_message(ret),
                context,
            )
        except Exception as e:
            logger.warning("[cmd_social_review_schedule_queue] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 排程队列读取失败，请稍后重试")
            except Exception as send_error:
                logger.debug("消息发送失败: %s", send_error)

    @requires_auth
    @with_typing
    async def cmd_social_review_final_confirm(self, update, context):
        """Telegram 排程到点后的最终确认；只标记可手动发布，不点击发布。"""
        try:
            identifier = (context.args or [""])[0].strip() if context.args else ""
            if not identifier:
                await update.message.reply_text("用法：/social_review_final_confirm <序号或草稿ID>")
                return
            target = await asyncio.to_thread(_resolve_social_schedule_target, identifier)
            if not target.get("success"):
                await send_long_message(
                    update.effective_chat.id,
                    _format_social_review_action_message(target, action_label="最终确认"),
                    context,
                )
                return
            ret = await asyncio.to_thread(
                ClawBotRPC._rpc_social_extension_schedule_final_confirm,
                str(target.get("draft_id") or identifier),
                "telegram",
            )
            await send_long_message(
                update.effective_chat.id,
                _format_social_review_action_message(ret, action_label="最终确认"),
                context,
            )
        except Exception as e:
            logger.warning("[cmd_social_review_final_confirm] 执行失败: %s", e)
            try:
                await update.message.reply_text("⚠️ 最终确认失败，请稍后重试")
            except Exception as send_error:
                logger.debug("消息发送失败: %s", send_error)

    # ---- 社媒发帖效果报告 ----

    @requires_auth
    @with_typing
    async def cmd_social_report(self, update, context):
        """查看社媒发帖效果报告 + A/B 测试数据"""
        days = 7
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError as e:
                logger.debug("用户输入解析失败: %s", e)
        result = execution_hub.get_post_performance_report(days=days)
        if not result.get("success"):
            await update.message.reply_text(f"❌ 报告生成失败: {result.get('error', '暂无数据')}")
            return
        lines = [f"📊 社媒效果报告（近 {days} 天）", ""]
        for platform, stats in result.get("by_platform", {}).items():
            icon = "𝕏" if platform == "x" else "📕"
            lines.append(f"{icon} {platform}: {stats['posts']} 篇 | ❤️ {stats['likes']} | 💬 {stats['comments']} | 👁 {stats['views']}")
        top = result.get("top_posts", [])
        if top:
            lines.append("\n🏆 Top 帖子:")
            for i, p in enumerate(top[:3], 1):
                lines.append(f"  {i}. [{p['platform']}] ❤️{p['likes']} 💬{p['comments']} {p.get('topic', '')[:30]}")
                if p.get("url"):
                    lines.append(f"     {p['url']}")

        # A/B 测试数据 — 展示活跃测试的效果对比
        try:
            from src.bot.globals import ab_test_manager
            if ab_test_manager:
                active_tests = ab_test_manager.get_active_tests()
                if active_tests:
                    lines.append("\n🧪 A/B 测试:")
                    for test in active_tests[:5]:
                        results_data = ab_test_manager.get_results(test.test_id)
                        if results_data:
                            winner = results_data.get("winner", "")
                            variants = results_data.get("variants", [])
                            status = "✅ 有赢家" if winner else "⏳ 进行中"
                            lines.append(f"  · {test.name} ({status})")
                            for v in variants[:3]:
                                ctr = v.get("ctr", 0)
                                imp = v.get("impressions", 0)
                                clk = v.get("clicks", 0)
                                lines.append(f"    变体{v.get('id', '?')[:6]}: {imp}曝光 {clk}点击 CTR={ctr:.1%}")
        except Exception:
            logger.debug("Silenced exception", exc_info=True)  # A/B 数据不影响主报告

        await send_long_message(update.effective_chat.id, "\n".join(lines), context)

    async def handle_social_confirm_callback(self, update, context):
        """处理社交发文预览的确认/取消/重新生成回调
        搬运自 ConversationHandler 向导模式 — 生成→预览→确认→发布
        """
        query = update.callback_query
        await query.answer()

        # 认证: 仅授权用户可操作
        if not self._is_authorized(update.effective_user.id):
            await query.answer("⛔ 未授权操作", show_alert=True)
            return

        data = query.data
        if not data.startswith("social_confirm:"):
            return

        action = data.split(":")[1]
        package = context.user_data.pop("pending_social_package", None)

        if action == "cancel":
            await query.edit_message_text("❌ 已取消发布。")
            return

        if action == "regenerate":
            await query.edit_message_text("🔄 重新生成中...")
            # 重新触发 /hot --preview
            context.args = ["--preview"]
            await self.cmd_hotpost(update, context)
            return

        if action == "publish":
            if not package:
                await query.edit_message_text("⚠️ 预览已过期，请重新执行 /hot --preview")
                return

            await query.edit_message_text("📤 正在发布...")
            try:
                ret = execution_hub._publish_social_package(package)
                if ret and ret.get("success"):
                    await query.edit_message_text(
                        "✅ 发布成功\n\n" +
                        "\n".join(
                            f"{'𝕏' if p == 'x' else '📕'} {p}: {r.get('url', '已发布')}"
                            for p, r in (ret.get("results") or {}).items()
                        )
                    )
                else:
                    error = ret.get("error", "未知错误") if ret else "无返回"
                    await query.edit_message_text(f"⚠️ 发布失败: {error}")
            except Exception as e:
                await query.edit_message_text(format_error(e, "发布内容"))
