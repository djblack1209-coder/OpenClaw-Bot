"""社媒人设确认状态。

该模块只负责“用户是否确认了热点抽象号人设”，不负责外发内容。
外部发布仍必须经过草稿级审核，避免人设确认被误解为自动发布许可。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.utils import now_et

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_STATE_FILE = _PACKAGE_ROOT / "data" / "social_persona_review_state.json"

PERSONA_PROPOSAL_ID = "hotspot-absurdist-v1"

PERSONA_PROPOSAL: dict[str, Any] = {
    "proposal_id": PERSONA_PROPOSAL_ID,
    "display_name": "热点抽象观察员",
    "one_liner": "中英热点观察员 + 抽象吐槽 + 低风险追梗，先积累关注，再沉淀系列内容。",
    "positioning": "不做 AI 教程号，不装专家；追中文/英文趋势，用短、怪、有反差的表达制造互动。",
    "audience": ["喜欢互联网梗的人", "X 信息流重度用户", "小红书轻娱乐/生活观察用户", "想看中英热点互文的人"],
    "tone": ["短", "怪", "有反差", "轻微阴阳怪气但不恶毒", "像朋友吐槽不是媒体通稿"],
    "content_mix": {
        "x": "70% 热点短吐槽 / 20% 中英互译梗 / 10% 互动提问",
        "xhs": "50% 生活化热点笔记 / 30% 梗图式标题 / 20% 评论区互动话题",
    },
    "do": [
        "抓微博/百度/知乎/B站/Google News/HN 的低风险热点",
        "优先选择能引发共鸣、吐槽、二创、评论接龙的话题",
        "用一句话/三行/反差类模板输出，避免长篇解释",
        "每条发布前保留人工确认，确认后才允许外发",
    ],
    "dont": [
        "不默认做 AI 工具教程或 OpenClaw 工程日志",
        "不碰严肃政治、灾难、战争、枪击、伤亡和造谣风险话题",
        "不批量关注/评论/点赞，不做刷量和平台风控绕过",
        "不使用客服腔、营销号口号和假装权威的媒体腔",
    ],
    "sample_posts": [
        {
            "platform": "x",
            "text": "今天热搜最大的共同点：大家不是在解决问题，是在给问题起一个更抽象的名字。",
        },
        {
            "platform": "x",
            "text": "Every timeline has become a group chat where nobody knows who added the adults.",
        },
        {
            "platform": "xhs",
            "title": "互联网新型精神状态：把生活过成副本",
            "body": "今天刷到好几个热点，突然发现大家不是不努力，是每天都在打一些没有任务奖励的支线。评论区说说，你今天卡在哪个关？",
        },
    ],
}


def _default_state() -> dict[str, Any]:
    """返回默认人设确认状态。"""
    return {
        "proposal_id": PERSONA_PROPOSAL_ID,
        "approved": False,
        "approved_by": "",
        "approved_at": "",
        "rejected_at": "",
        "notes": "",
    }


def load_persona_review_state(path: Path = _STATE_FILE) -> dict[str, Any]:
    """读取人设确认状态，文件不存在或损坏时安全降级。"""
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                state = _default_state()
                state.update(data)
                state.setdefault("proposal_id", PERSONA_PROPOSAL_ID)
                return state
    except Exception:
        return _default_state()
    return _default_state()


def save_persona_review_state(state: dict[str, Any], path: Path = _STATE_FILE) -> None:
    """保存人设确认状态。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_persona_review(path: Path = _STATE_FILE) -> dict[str, Any]:
    """返回人设提案和当前确认状态。"""
    state = load_persona_review_state(path)
    approved = bool(state.get("approved")) and state.get("proposal_id") == PERSONA_PROPOSAL_ID
    return {
        "success": True,
        "proposal": PERSONA_PROPOSAL,
        "state": state,
        "approved": approved,
        "needs_confirmation": not approved,
        "verdict": "人设已确认，可继续逐条审核内容。" if approved else "现有人设偏 AI/程序员，需要确认热点抽象号人设后再恢复自动外发。",
    }


def review_persona(approved: bool, reviewer: str = "owner", notes: str = "", path: Path = _STATE_FILE) -> dict[str, Any]:
    """确认或打回热点抽象号人设。"""
    state = load_persona_review_state(path)
    state["proposal_id"] = PERSONA_PROPOSAL_ID
    state["approved"] = bool(approved)
    state["notes"] = notes or ""
    if approved:
        state["approved_by"] = reviewer or "owner"
        state["approved_at"] = now_et().isoformat()
        state["rejected_at"] = ""
    else:
        state["approved_by"] = ""
        state["approved_at"] = ""
        state["rejected_at"] = now_et().isoformat()
    save_persona_review_state(state, path)
    return get_persona_review(path)
