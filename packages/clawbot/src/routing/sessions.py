"""
SessionMixin — 讨论会话 + 服务工作流管理
从 router.py 拆分而来，以 Mixin 方式注入 ChatRouter，管理所有会话类状态。
"""
import re
import time
import logging
import asyncio
from typing import Dict, List, Optional, Tuple

from src.constants import (
    BOT_QWEN, BOT_DEEPSEEK, BOT_GPTOSS,
    BOT_CLAUDE_HAIKU, BOT_CLAUDE_SONNET,
)
from src.routing.constants import (
    SERVICE_WORKFLOW_ACTION_HINTS,
    SERVICE_WORKFLOW_NOUN_HINTS,
    SERVICE_WORKFLOW_SKIP_HINTS,
)
from src.routing.models import ServiceWorkflowSession

logger = logging.getLogger(__name__)


class SessionMixin:
    """讨论会话 + 服务工作流管理 Mixin — 由 ChatRouter 继承使用"""

    def _init_sessions(self):
        """初始化会话相关的状态（由 ChatRouter.__init__ 调用）"""
        self._discuss_sessions: Dict[int, Dict] = {}
        self._discuss_lock = asyncio.Lock()
        self._service_workflows: Dict[int, ServiceWorkflowSession] = {}
        self._service_workflow_lock = asyncio.Lock()

    # ============ 讨论模式 ============

    async def start_discuss(self, chat_id: int, topic: str, rounds: int, participants: Optional[List[str]] = None, discuss_type: str = "discuss") -> str:
        """
        启动讨论模式。

        Args:
            chat_id: 群组 chat_id
            topic: 讨论主题
            rounds: 讨论轮数
            participants: 参与的 bot_id 列表，None 表示全部
            discuss_type: "discuss" 或 "chain"

        Returns:
            启动信息
        """
        async with self._discuss_lock:
            # 防止并发：如果已有活跃讨论，拒绝启动
            existing = self._discuss_sessions.get(chat_id)
            if existing and existing.get("active"):
                return "当前已有进行中的讨论，请先 /stop_discuss 结束后再开始新讨论。"

            if participants is None:
                participants = list(self.bots.keys())

            self._discuss_sessions[chat_id] = {
                "topic": topic,
                "rounds_total": rounds,
                "rounds_left": rounds,
                "round_current": 0,
                "participants": participants,
                "current_bot_idx": 0,
                "history": [],
                "active": True,
                "type": discuss_type,
                "created_at": time.time(),
            }

            bot_names = [self.bots[bid].name for bid in participants if bid in self.bots]
            return (
                f"📢 讨论模式启动\n"
                f"主题: {topic}\n"
                f"轮数: {rounds}\n"
                f"参与者: {', '.join(bot_names)}\n\n"
                f"每轮每个 Bot 依次发言，共 {rounds} 轮。\n"
                f"发送 /stop_discuss 可提前结束。"
            )

    async def stop_discuss(self, chat_id: int) -> str:
        """停止讨论模式"""
        async with self._discuss_lock:
            if chat_id in self._discuss_sessions:
                del self._discuss_sessions[chat_id]
                return "讨论模式已结束。"
            return "当前没有进行中的讨论。"

    def get_discuss_session(self, chat_id: int) -> Optional[Dict]:
        """获取讨论会话"""
        session = self._discuss_sessions.get(chat_id)
        if session and session.get("active"):
            return session
        return None

    async def next_discuss_turn(self, chat_id: int) -> Optional[Tuple[str, str]]:
        """
        获取讨论模式的下一个发言者和提示。

        Returns:
            (bot_id, prompt) 或 None（讨论结束）
        """
        async with self._discuss_lock:
            session = self._discuss_sessions.get(chat_id)
            if not session or not session["active"]:
                return None

            participants = session["participants"]
            idx = session["current_bot_idx"]

            # 当前轮所有 bot 都发言完毕，进入下一轮
            if idx >= len(participants):
                session["rounds_left"] -= 1
                session["round_current"] += 1
                session["current_bot_idx"] = 0
                idx = 0

                if session["rounds_left"] <= 0:
                    session["active"] = False
                    return None

            bot_id = participants[idx]
            session["current_bot_idx"] = idx + 1

            # 构造讨论提示
            round_num = session["round_current"] + 1
            total_rounds = session["rounds_total"]
            history_text = "\n".join(session["history"][-10:])  # 最近10条

            prompt = (
                f"【群组讨论 第{round_num}/{total_rounds}轮】\n"
                f"主题: {session['topic']}\n"
            )
            if history_text:
                prompt += f"\n之前的讨论:\n{history_text}\n"
            prompt += (
                "\n请就此主题发表你的观点。"
                "如果之前有其他人发言，请回应或补充，不要重复已有观点。"
                "保持简洁，每次发言控制在200字以内。"
            )

            return bot_id, prompt

    def record_discuss_message(self, chat_id: int, bot_name: str, message: str):
        """记录讨论中的发言"""
        session = self._discuss_sessions.get(chat_id)
        if session:
            # 截取前200字记录
            short = message[:200] + "..." if len(message) > 200 else message
            session["history"].append(f"[{bot_name}]: {short}")

    # ============ 服务工作流 ============

    async def start_service_workflow(
        self,
        chat_id: int,
        original_text: str,
        owner_bot_id: str,
        intake_bot_id: str,
        expert_bot_id: str,
        director_bot_id: str,
    ) -> Tuple[bool, str, Optional[ServiceWorkflowSession]]:
        """启动服务工作流会话"""
        async with self._service_workflow_lock:
            current = self._service_workflows.get(chat_id)
            if current and current.active:
                return False, "当前已有进行中的链式服务流程，请先完成选择或评分。", current

            session = ServiceWorkflowSession(
                session_id=f"service_{chat_id}_{int(time.time())}",
                chat_id=chat_id,
                original_text=original_text,
                owner_bot_id=owner_bot_id,
                intake_bot_id=intake_bot_id,
                expert_bot_id=expert_bot_id,
                director_bot_id=director_bot_id,
            )
            self._service_workflows[chat_id] = session
            return True, "", session

    def _select_service_workflow_starter(self) -> str:
        """选择服务工作流的启动 bot（按优先级挑选已注册的 bot）"""
        preferred = [BOT_QWEN, BOT_CLAUDE_HAIKU, BOT_CLAUDE_SONNET, BOT_DEEPSEEK, BOT_GPTOSS]
        for bot_id in preferred:
            if bot_id in self.bots:
                return bot_id
        return next(iter(self.bots.keys()), "")

    def should_auto_service_workflow(self, text: str, chat_type: str, route_reason: str = "") -> bool:
        """判断是否应自动触发服务工作流"""
        raw = (text or "").strip()
        if chat_type not in {"group", "supergroup"}:
            return False
        if not raw or raw.startswith("/"):
            return False
        if route_reason.startswith("chain_discuss:"):
            return False
        if re.fullmatch(r"[123\s,，/]+", raw):
            return False

        lowered = raw.lower()
        if any(token in lowered for token in SERVICE_WORKFLOW_SKIP_HINTS):
            return False

        action_hits = [token for token in SERVICE_WORKFLOW_ACTION_HINTS if token in raw]
        noun_hits = [token for token in SERVICE_WORKFLOW_NOUN_HINTS if token in raw]
        looks_like_task_request = any(token in raw for token in ["我想", "我要", "我需要", "给我", "替我", "想让你"])
        has_process_signal = any(token in raw for token in ["怎么做", "如何做", "怎么办", "下一步", "方案", "流程"])

        if action_hits and noun_hits:
            return True
        if len(action_hits) >= 2:
            return True
        if looks_like_task_request and (noun_hits or has_process_signal) and len(raw) >= 16:
            return True
        if len(raw) >= 36 and action_hits:
            return True
        if len(raw) >= 48 and has_process_signal:
            return True
        return False

    def get_service_workflow(self, chat_id: int) -> Optional[ServiceWorkflowSession]:
        """获取活跃的服务工作流会话"""
        session = self._service_workflows.get(chat_id)
        if session and session.active:
            return session
        return None

    async def stop_service_workflow(self, chat_id: int) -> str:
        """停止服务工作流"""
        async with self._service_workflow_lock:
            session = self._service_workflows.pop(chat_id, None)
            if session:
                session.active = False
                return "链式服务流程已结束。"
            return "当前没有进行中的链式服务流程。"

    # ============ 会话清理 ============

    def cleanup_stale_sessions(self, max_age_seconds: int = 1800):
        """清理超时的讨论会话和服务工作流"""
        now = time.time()
        stale_discuss = [k for k, v in self._discuss_sessions.items()
                         if now - v.get("created_at", 0) > max_age_seconds]
        for k in stale_discuss:
            del self._discuss_sessions[k]
        stale_workflows = [k for k, v in self._service_workflows.items()
                           if now - v.created_at > max_age_seconds]
        for k in stale_workflows:
            del self._service_workflows[k]
        if stale_discuss or stale_workflows:
            logger.debug("Cleaned %d discuss + %d workflow sessions",
                         len(stale_discuss), len(stale_workflows))
