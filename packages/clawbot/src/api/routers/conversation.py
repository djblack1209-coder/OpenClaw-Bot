"""
会话 API Router — C 端 AI 助手对话接口
挂载到 /api/v1/conversation/*

功能:
- SSE 流式对话: 包装 Brain.process_message，通过 Server-Sent Events 推送状态和结果
- 会话历史: SQLite 存储，按日期分组
- 日志友好化: 将技术日志翻译为用户友好文本
"""

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..error_utils import safe_error as _safe_error

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/conversation")


# ============ 内存会话存储（轻量实现，后续可升级为 SQLite） ============


class ConversationStore:
    """会话历史存储 — 内存实现，重启后清空"""

    def __init__(self) -> None:
        # 会话列表: {session_id: {id, title, created_at, updated_at, messages: [...]}}
        self._sessions: Dict[str, Dict[str, Any]] = {}

    # 会话上限保护：防止无限创建导致内存耗尽
    MAX_SESSIONS = 200

    def create_session(self, title: str = "新对话") -> Dict[str, Any]:
        """创建新会话"""
        # 超过上限时自动淘汰最旧会话
        if len(self._sessions) >= self.MAX_SESSIONS:
            oldest = min(self._sessions.values(), key=lambda s: s["updated_at"])
            del self._sessions[oldest["id"]]
        # 标题长度限制
        title = title[:100]
        session_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()
        session = {
            "id": session_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取单个会话"""
        return self._sessions.get(session_id)

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取会话列表（按最近更新排序，不含消息体）"""
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: s["updated_at"],
            reverse=True,
        )[:limit]
        # 返回摘要，不含完整消息列表
        return [
            {
                "id": s["id"],
                "title": s["title"],
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
                "message_count": len(s["messages"]),
                "last_message": s["messages"][-1]["content"][:80] if s["messages"] else "",
            }
            for s in sessions
        ]

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """向会话追加消息"""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")

        msg = {
            "id": uuid.uuid4().hex[:8],
            "role": role,  # "user" | "assistant" | "system"
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        session["messages"].append(msg)
        session["updated_at"] = msg["timestamp"]

        # 第一条用户消息作为会话标题
        if role == "user" and len(session["messages"]) == 1:
            session["title"] = content[:30] + ("..." if len(content) > 30 else "")

        return msg

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        return self._sessions.pop(session_id, None) is not None


# 全局会话存储实例
_store = ConversationStore()


# ============ 日志友好化翻译 ============

# 技术文本 → 用户友好文本的映射
_LOG_TRANSLATIONS = {
    "brain.process_message": "AI 正在思考...",
    "intent_parser": "正在理解你的意思...",
    "task_graph": "正在规划执行步骤...",
    "executor": "正在执行任务...",
    "browser_use": "正在浏览网页...",
    "litellm": "AI 模型处理中...",
    "self_heal": "正在自动修复...",
    "xianyu": "闲鱼系统处理中...",
    "trading": "交易系统处理中...",
    "social": "社媒系统处理中...",
}


def _friendly_status(stage: str) -> str:
    """将内部执行阶段名翻译为用户友好文本"""
    for key, text in _LOG_TRANSLATIONS.items():
        if key in stage.lower():
            return text
    return "处理中..."


def _friendly_error(error: str) -> str:
    """将技术错误信息翻译为用户友好文本"""
    if "timeout" in error.lower():
        return "操作超时了，请稍后再试"
    if "rate_limit" in error.lower() or "429" in error:
        return "AI 服务暂时繁忙，请稍后再试"
    if "budget" in error.lower():
        return "今日 AI 预算已用完，明天再来"
    if "connection" in error.lower():
        return "网络连接出了问题，请检查网络"
    return "出了点小问题，请重新试试"


# ============ API 路由 ============


@router.get("/sessions")
async def list_sessions(limit: int = Query(default=50, ge=1, le=200)):
    """获取会话列表"""
    return {"sessions": _store.list_sessions(limit)}


@router.post("/sessions")
async def create_session(title: str = "新对话"):
    """创建新会话"""
    session = _store.create_session(title)
    return session


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话详情（含全部消息）"""
    session = _store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    if _store.delete_session(session_id):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="会话不存在")


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, body: dict = Body(...)):
    """更新会话属性（目前仅支持修改标题）"""
    session = _store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    new_title = body.get("title", "").strip()
    if not new_title:
        raise HTTPException(status_code=422, detail="标题不能为空")
    session["title"] = new_title[:100]
    return {"ok": True, "title": session["title"]}


@router.post("/sessions/{session_id}/send")
async def send_message(
    session_id: str,
    message: str = Body(max_length=2000, embed=True, description="用户消息内容"),
):
    """
    发送消息并获取 SSE 流式响应。

    事件类型:
    - status: 执行状态更新（用户友好文本）
    - chunk: 响应文本片段（流式输出）
    - result: 完整结果（JSON，含 task_type/cost 等元数据）
    - error: 错误信息（用户友好文本）
    - done: 流结束标记
    """
    session = _store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 记录用户消息
    _store.add_message(session_id, "user", message)

    async def event_stream():
        """SSE 事件生成器"""
        start_time = time.time()

        try:
            # 发送"正在思考"状态
            yield _sse_event("status", {"text": "AI 正在思考..."})
            await asyncio.sleep(0.1)

            # 调用 Brain 处理
            from src.core.brain import get_brain

            brain = get_brain()

            yield _sse_event("status", {"text": "正在理解你的意思..."})

            result = await brain.process_message(
                source="app",
                message=message,
            )

            result_dict = result.to_dict()
            elapsed = round(time.time() - start_time, 2)

            # 提取友好响应文本
            response_text = ""
            if result_dict.get("result"):
                if isinstance(result_dict["result"], str):
                    response_text = result_dict["result"]
                elif isinstance(result_dict["result"], dict):
                    # 尝试从结果字典中提取文本
                    response_text = (
                        result_dict["result"].get("response")
                        or result_dict["result"].get("text")
                        or result_dict["result"].get("message")
                        or json.dumps(result_dict["result"], ensure_ascii=False, indent=2)
                    )
                else:
                    response_text = str(result_dict["result"])
            elif result_dict.get("error"):
                response_text = _friendly_error(result_dict["error"])
            elif result_dict.get("needs_clarification"):
                params = result_dict.get("clarification_params", [])
                response_text = f"我需要你补充一些信息：{', '.join(params)}"
            else:
                response_text = "处理完成，但没有生成回复内容。"

            # 模拟流式输出 — 按句子分段发送（给用户更好的体验）
            sentences = _split_text(response_text)
            for sentence in sentences:
                yield _sse_event("chunk", {"text": sentence})
                await asyncio.sleep(0.05)  # 50ms 间隔模拟打字效果

            # 记录助手消息
            _store.add_message(
                session_id,
                "assistant",
                response_text,
                metadata={
                    "task_type": result_dict.get("task_type", ""),
                    "cost_usd": result_dict.get("cost_usd", 0),
                    "elapsed": elapsed,
                    "goal": result_dict.get("goal", ""),
                },
            )

            # 发送完整结果元数据
            yield _sse_event(
                "result",
                {
                    "task_type": result_dict.get("task_type", ""),
                    "goal": result_dict.get("goal", ""),
                    "cost_usd": result_dict.get("cost_usd", 0),
                    "elapsed": elapsed,
                    "success": result_dict.get("success", False),
                },
            )

        except Exception as e:
            logger.exception("会话消息处理失败")
            error_text = _friendly_error(str(e))
            _store.add_message(session_id, "assistant", error_text, metadata={"error": True})
            yield _sse_event("error", {"text": error_text})

        # 流结束
        yield _sse_event("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event_type: str, data: dict) -> str:
    """格式化 SSE 事件"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _split_text(text: str) -> List[str]:
    """将文本按句子/段落分段，用于模拟流式输出"""
    if not text:
        return [""]

    # 按换行分段
    paragraphs = text.split("\n")
    chunks = []
    for para in paragraphs:
        if not para.strip():
            chunks.append("\n")
            continue
        # 按中文句号、问号、感叹号分句
        sentences = re.split(r"([。！？\n])", para)
        buffer = ""
        for s in sentences:
            buffer += s
            if s in ("。", "！", "？", "\n"):
                chunks.append(buffer)
                buffer = ""
        if buffer:
            chunks.append(buffer)

    return chunks if chunks else [text]
