"""微信每日简报真实桥接证据读取与验收。

该模块只读取 OpenClaw Weixin 插件桥写出的脱敏证据文件，不读取微信聊天、
不调用微信网络、不保存原始用户 ID 或 Token。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE = ROOT / "data" / "intel_evidence" / "phasefix" / "wechat-bridge" / "runtime.json"
KNOWN_SHORTCUT_CLASSES = {
    "menu",
    "today",
    "status",
    "market",
    "ai",
    "weather",
    "schedule",
    "track",
    "help",
    "pause",
}


def default_wechat_bridge_evidence_path() -> Path:
    """返回微信桥接证据文件路径，允许环境变量覆盖。"""
    configured = os.environ.get("OPENCLAW_INTEL_BRIEF_WECHAT_EVIDENCE_FILE", "").strip()
    if configured:
        return Path(configured)
    return DEFAULT_EVIDENCE


def _now() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility


def _parse_dt(value: str) -> datetime | None:
    """解析 ISO 时间字符串。"""
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    try:
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
        return parsed.astimezone(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility
    except ValueError:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    """读取 JSON 文件，失败时抛出带路径的异常。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"未找到微信桥接证据文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"微信桥接证据文件不是合法 JSON：{path}") from exc


def build_wechat_bridge_runtime_acceptance(
    *,
    evidence_path: str | Path | None = None,
    max_age_seconds: int = 900,
    now: datetime | None = None,
) -> dict[str, Any]:
    """构建微信真实桥接验收报告。"""
    evidence_file = Path(evidence_path) if evidence_path is not None else default_wechat_bridge_evidence_path()
    current = now or _now()
    blockers: list[str] = []
    latest: dict[str, Any] = {}
    age_seconds: int | None = None

    try:
        payload = _load_json(evidence_file)
        raw_latest = payload.get("latest")
        if isinstance(raw_latest, dict):
            latest = raw_latest
        else:
            blockers.append("证据文件缺少 latest 对象")
    except Exception as exc:
        blockers.append(str(exc))

    recorded_at = _parse_dt(str(latest.get("recorded_at", ""))) if latest else None
    if latest and recorded_at is None:
        blockers.append("latest.recorded_at 无法解析")
    if recorded_at is not None:
        age_seconds = max(0, int((current - recorded_at).total_seconds()))
        if age_seconds > max_age_seconds:
            blockers.append(f"最近一次微信桥接证据已超过 {max_age_seconds} 秒")

    if latest:
        if latest.get("source") != "openclaw-weixin-intel-brief-bridge":
            blockers.append("证据来源不是 OpenClaw Weixin 每日简报桥")
        if latest.get("status") != "handled":
            blockers.append(f"最近一次桥接状态不是 handled：{latest.get('status')}")
        if latest.get("reason") != "sent_reply":
            blockers.append(f"最近一次桥接原因不是 sent_reply：{latest.get('reason')}")
        if latest.get("http_status") != 200:
            blockers.append(f"本机 /wechat/incoming 返回码不是 200：{latest.get('http_status')}")
        if latest.get("sent_reply_success") is not True:
            blockers.append("插件没有记录已成功把回复发回微信")
        if latest.get("reply_present") is not True:
            blockers.append("本机处理器没有返回可发送回复")
        if latest.get("reply_fell_to_llm") is True:
            blockers.append("回复疑似落入普通 LLM 闲聊")
        if latest.get("shortcut_class") not in KNOWN_SHORTCUT_CLASSES:
            blockers.append(f"快捷词类型不在每日简报范围：{latest.get('shortcut_class')}")
        if not latest.get("sender_hash"):
            blockers.append("证据缺少脱敏 sender_hash，无法确认来自真实入站")

    sanitized_latest = {
        "recorded_at": latest.get("recorded_at", ""),
        "source": latest.get("source", ""),
        "status": latest.get("status", ""),
        "reason": latest.get("reason", ""),
        "shortcut_class": latest.get("shortcut_class", ""),
        "sender_hash_present": bool(latest.get("sender_hash")),
        "text_length": latest.get("text_length"),
        "bridge_url": latest.get("bridge_url", ""),
        "api_token_present": bool(latest.get("api_token_present")),
        "http_status": latest.get("http_status"),
        "reply_present": bool(latest.get("reply_present")),
        "reply_length": latest.get("reply_length"),
        "reply_contains_menu": bool(latest.get("reply_contains_menu")),
        "reply_contains_status": bool(latest.get("reply_contains_status")),
        "reply_contains_schedule_prompt": bool(latest.get("reply_contains_schedule_prompt")),
        "reply_contains_tracking_prompt": bool(latest.get("reply_contains_tracking_prompt")),
        "reply_fell_to_llm": bool(latest.get("reply_fell_to_llm")),
        "sent_reply_success": bool(latest.get("sent_reply_success")),
    }
    return {
        "verified": not blockers,
        "checked_at": current.isoformat(),
        "evidence_path": str(evidence_file),
        "max_age_seconds": max_age_seconds,
        "age_seconds": age_seconds,
        "blockers": blockers,
        "latest": sanitized_latest,
        "privacy": {
            "stores_raw_wechat_text": False,
            "stores_raw_user_id": False,
            "stores_token": False,
            "sender_hash_only": True,
        },
    }


def wait_for_wechat_bridge_runtime_acceptance(
    *,
    evidence_path: str | Path | None = None,
    max_age_seconds: int = 900,
    wait_seconds: int = 0,
    poll_seconds: float = 2.0,
) -> dict[str, Any]:
    """等待真实微信桥接证据出现并通过验收。"""
    started_at = _now()
    deadline = time.monotonic() + max(0, int(wait_seconds))
    attempts = 0
    last_result: dict[str, Any] = {}
    sleep_interval = max(0.2, float(poll_seconds))

    while True:
        attempts += 1
        last_result = build_wechat_bridge_runtime_acceptance(
            evidence_path=evidence_path,
            max_age_seconds=max_age_seconds,
        )
        if last_result.get("verified") or time.monotonic() >= deadline:
            break
        time.sleep(sleep_interval)

    last_result["wait"] = {
        "started_at": started_at.isoformat(),
        "wait_seconds": max(0, int(wait_seconds)),
        "poll_seconds": sleep_interval,
        "attempts": attempts,
        "timed_out": not bool(last_result.get("verified")) and max(0, int(wait_seconds)) > 0,
    }
    if last_result["wait"]["timed_out"]:
        blockers = list(last_result.get("blockers") or [])
        blockers.append(f"等待 {max(0, int(wait_seconds))} 秒后仍未看到新的真实微信桥接成功证据")
        last_result["blockers"] = blockers
    return last_result


def summarize_wechat_bridge_status(result: dict[str, Any]) -> dict[str, Any]:
    """把验收结果转成老板看得懂的红黄绿状态。"""
    blockers = [str(item) for item in result.get("blockers") or []]
    latest = result.get("latest") if isinstance(result.get("latest"), dict) else {}
    if result.get("verified"):
        state = "verified"
        severity = "ok"
        title = "微信每日简报真实入站已闭环"
        next_action = "可以继续用微信菜单测试设置时间、添加追踪、暂停和恢复。"
    elif any("未找到微信桥接证据文件" in item for item in blockers):
        state = "waiting_real_wechat_message"
        severity = "warning"
        title = "等待真实微信消息"
        next_action = "在微信 ClawBot 会话发送“今日简报”或“700”，系统会自动写入验收证据。"
    elif latest.get("status") and latest.get("status") != "handled":
        state = "bridge_not_handled"
        severity = "danger"
        title = "微信桥接收到消息但未成功回发"
        next_action = "重启 OpenClaw Gateway 后，再在微信发送“今日简报”。"
    else:
        state = "not_verified"
        severity = "warning"
        title = "微信桥接还未通过验收"
        next_action = "在微信发送“今日简报”后重新检查；若仍失败，查看 blockers。"
    return {
        "state": state,
        "severity": severity,
        "title": title,
        "next_action": next_action,
        "verified": bool(result.get("verified")),
        "blockers": blockers,
        "age_seconds": result.get("age_seconds"),
        "latest": latest,
        "privacy": result.get("privacy") or {},
    }
