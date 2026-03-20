"""
Execution Hub — 邮件自动整理
场景1: 邮件分类、摘要、行动事项提取
"""
import asyncio
import logging

from src.execution._utils import extract_json_object
from src.execution._ai import ai_pool
from src.notify_style import format_announcement

logger = logging.getLogger(__name__)


async def triage_email(max_messages=20, only_unread=True) -> dict:
    """整理邮件，按类别分组并提取行动事项"""
    prompt = (
        f"请帮我整理最近 {max_messages} 封{'未读' if only_unread else ''}邮件，"
        "按重要事务、会议协作、系统通知、营销订阅、其他分类，"
        "并列出需要行动的事项。以 JSON 返回: "
        '{"grouped":{}, "highlights":[], "action_items":[]}'
    )
    try:
        result = await ai_pool.call_direct(prompt=prompt)
        if result.get("success"):
            raw = result.get("raw", "")
            parsed = extract_json_object(raw)
            if parsed:
                return {
                    "success": True,
                    "total": max_messages,
                    "summary": raw,
                    "action_items": parsed.get("action_items", []),
                    "grouped": parsed.get("grouped", {}),
                    "highlights": parsed.get("highlights", []),
                }
            return {
                "success": True,
                "total": max_messages,
                "summary": raw,
                "action_items": [],
                "grouped": {},
                "highlights": [],
            }
        return {"success": False, "error": result.get("error", "AI 调用失败")}
    except Exception as e:
        logger.error(f"[TriageEmail] failed: {e}")
        return {"success": False, "error": str(e)}


def format_email_triage(triage: dict) -> str:
    """格式化邮件整理结果"""
    if not triage.get("success"):
        return f"邮件整理失败: {triage.get('error', '未知错误')}"
    grouped = triage.get("grouped", {})
    lines = ["邮件自动整理", ""]
    lines.append(f"总计邮件: {triage.get('total', 0)}")
    for cat in ("重要事务", "会议协作", "系统通知", "营销订阅", "其他"):
        lines.append(f"- {cat}: {len(grouped.get(cat, []))}")
    highlights = triage.get("highlights", [])
    if highlights:
        lines.append("\n重点摘要:")
        for i, item in enumerate(highlights[:3], 1):
            subj = item.get("subject", "")
            sender = item.get("from", "")
            lines.append(f"{i}. [{item.get('category', '其他')}] {subj}")
            lines.append(f"   发件人: {sender}")
    return "\n".join(lines)
