"""
Execution Hub — 会议纪要提炼
场景4: 从文本或文件中提取会议摘要、行动事项、关键决策
"""
import logging
from pathlib import Path

from src.execution._utils import extract_json_object
from src.execution._ai import ai_pool

logger = logging.getLogger(__name__)


async def summarize_meeting(text=None, file_path=None) -> dict:
    """总结会议纪要，提取摘要、行动事项、关键决策"""
    content = text or ""
    if file_path:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            return {"success": False, "error": f"无法读取文件: {e}"}
    if not str(content).strip():
        return {"success": False, "error": "没有提供会议内容"}
    prompt = (
        "请总结以下会议纪要，提取：1) 摘要 2) 行动事项 3) 关键决策。"
        '以 JSON 返回: {"summary":"...", "action_items":[], "decisions":[]}\n\n'
        + str(content).strip()[:4000]
    )
    try:
        result = await ai_pool.call_direct(prompt=prompt)
        if result.get("success"):
            raw = result.get("raw", "")
            parsed = extract_json_object(raw)
            if parsed:
                return {
                    "success": True,
                    "summary": parsed.get("summary", raw),
                    "action_items": parsed.get("action_items", []),
                    "decisions": parsed.get("decisions", []),
                }
            return {"success": True, "summary": raw, "action_items": [], "decisions": []}
        return {"success": False, "error": result.get("error", "AI 调用失败")}
    except Exception as e:
        logger.error(f"[SummarizeMeeting] failed: {e}")
        return {"success": False, "error": str(e)}
