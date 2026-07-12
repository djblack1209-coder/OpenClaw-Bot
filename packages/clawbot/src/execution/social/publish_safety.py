"""社媒外部写操作的统一安全闸门。"""

from __future__ import annotations

from typing import Any

_EXTERNAL_WRITE_ACTIONS = (
    "publish",
    "post",
    "reply",
    "comment",
    "follow",
    "unfollow",
    "like",
    "unlike",
    "message",
    "dm",
    "delete",
    "profile",
    "promote",
    "boost",
)


def is_external_social_write(action: str) -> bool:
    """判断 worker/桥接动作是否会修改外部社媒状态。"""
    normalized = str(action or "").strip().lower().replace("-", "_")
    return any(
        normalized == prefix
        or normalized.startswith(f"{prefix}_")
        or normalized.endswith(f"_{prefix}")
        for prefix in _EXTERNAL_WRITE_ACTIONS
    )


def confirmation_required(action: str = "publish") -> dict[str, Any]:
    """返回统一、可被 UI 和测试识别的人工确认结果。"""
    return {
        "success": False,
        "error": "社媒外部写操作需要当前操作的最终人工确认",
        "code": "social_publish_confirmation_required",
        "requires_human_confirmation": True,
        "external_action_blocked": True,
        "action": str(action or "publish"),
    }


def enforce_external_write_confirmation(
    action: str,
    *,
    final_confirmed: bool,
) -> dict[str, Any] | None:
    """未确认的外部写操作返回阻断结果；只读动作返回 None。"""
    if is_external_social_write(action) and not final_confirmed:
        return confirmation_required(action)
    return None
