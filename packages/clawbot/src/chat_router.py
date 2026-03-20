"""
ClawBot - 群聊智能路由 + 协作编排
基于消息内容的意图分类，自动路由到最合适的 bot
避免多个 bot 同时回复类似内容
支持 /collab 协作模式：规划 -> 执行 -> 汇总
"""
import re
import time
import logging
import asyncio
import os
import threading
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable, Awaitable, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    from src.utils import env_bool
    return env_bool(name, default)

# 链式讨论触发词（统一定义，避免重复）
CHAIN_DISCUSS_TRIGGERS = [
    "所有人", "所有bot", "所有机器人", "大家讨论", "大家说说",
    "每个人", "按顺序", "依次讨论", "轮流", "大家聊聊",
    "大家来聊聊", "大家来讨论", "一起讨论", "各位说说",
    "大家分析", "大家看看", "每个bot", "所有ai",
    "链式讨论", "客服模式", "协同处理", "ai团队处理", "大家一起做",
    "everyone discuss", "all bots",
]

SERVICE_WORKFLOW_ACTION_HINTS = [
    "帮我", "帮忙", "麻烦", "请你", "实现", "修复", "优化", "排查", "部署", "接入",
    "配置", "设计", "重构", "整理", "梳理", "写", "规划", "方案", "评审", "完善",
    "补充", "检查", "搭建", "迁移", "上线", "排版", "公告", "流程", "自动化", "更新",
]

SERVICE_WORKFLOW_NOUN_HINTS = [
    "代码", "功能", "接口", "页面", "系统", "项目", "文案", "排版", "公告", "流程",
    "群聊", "机器人", "配置", "部署", "bug", "报错", "任务", "执行", "结构", "方案",
    "脚本", "网站", "服务", "提示词", "工作流", "自动化",
]

SERVICE_WORKFLOW_SKIP_HINTS = [
    "直接回答", "直接说", "直接给结果", "一句话回答", "快答", "别问我", "不要问我",
    "不用问我", "不要方案", "不用方案", "先别分工", "单独回答",
]


@dataclass
class BotCapability:
    """Bot 能力描述"""
    bot_id: str
    name: str
    username: str
    keywords: List[str]           # 触发关键词
    domains: List[str]            # 擅长领域
    priority: int = 0             # 优先级（越高越优先）


@dataclass
class ServiceWorkflowSession:
    session_id: str
    chat_id: int
    original_text: str
    owner_bot_id: str
    intake_bot_id: str
    expert_bot_id: str
    director_bot_id: str
    stage: str = "awaiting_selection"
    active: bool = True
    options: List[Dict[str, Any]] = field(default_factory=list)
    intake_summary: str = ""
    missing_info: List[str] = field(default_factory=list)
    selected_option_id: int = 0
    selection_note: str = ""
    expert_plan: Dict[str, Any] = field(default_factory=dict)
    team_plan: Dict[str, Any] = field(default_factory=dict)
    execution_results: List[Dict[str, Any]] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    final_report: str = ""
    rating_hint: str = ""
    created_at: float = field(default_factory=time.time)


# 意图分类
class Intent:
    CODE = "code"                 # 编程相关
    MATH = "math"                 # 数学/逻辑
    CREATIVE = "creative"         # 创意/写作
    KNOWLEDGE = "knowledge"       # 知识/历史/文化
    GENERAL = "general"           # 通用问答
    IMAGE = "image"               # 图片生成
    ANALYSIS = "analysis"         # 分析/推理


# 意图 -> 最佳 bot 映射（每个 bot 至少有一个 rank 0 场景）
INTENT_BOT_MAP = {
    Intent.CODE: ["deepseek_v3", "qwen235b", "claude_opus"],
    Intent.MATH: ["deepseek_v3", "qwen235b"],
    Intent.CREATIVE: ["claude_sonnet", "claude_haiku"],
    Intent.KNOWLEDGE: ["qwen235b", "claude_haiku"],
    Intent.GENERAL: ["gptoss", "qwen235b"],
    Intent.IMAGE: ["claude_sonnet"],
    Intent.ANALYSIS: ["claude_opus", "claude_sonnet", "deepseek_v3"],
}

# 显式分流通道（topic/forum 不可用时的替代方案）
# 规则：用户在消息里带上 lane marker，即可强制路由到指定 bot。
LANE_ROUTE_RULES = [
    ("risk", "claude_sonnet", ["[risk]", "#risk", "#风控", "#风险"]),
    ("alpha", "qwen235b", ["[alpha]", "#alpha", "#研究", "#策略"]),
    ("exec", "deepseek_v3", ["[exec]", "#exec", "#执行", "#下单"]),
    ("fast", "gptoss", ["[fast]", "#fast", "#快问", "#速答"]),
    ("cn", "deepseek_v3", ["[cn]", "#cn", "#中文"]),
    ("brain", "claude_opus", ["[brain]", "#brain", "#终极", "#深度"]),
    ("creative", "claude_haiku", ["[creative]", "#creative", "#文案", "#创意"]),
]

# 兜底轮换列表（排除付费 Opus 和 Free-LLM，其余 5 个 bot 轮换）
_FALLBACK_ROTATION = ["qwen235b", "gptoss", "deepseek_v3", "claude_haiku", "claude_sonnet"]

# 意图检测关键词
INTENT_KEYWORDS = {
    Intent.CODE: [
        "代码", "编程", "bug", "报错", "函数", "class", "def ", "import ",
        "python", "java", "javascript", "typescript", "rust", "go",
        "api", "接口", "数据库", "sql", "git", "docker", "部署",
        "调试", "debug", "编译", "运行", "脚本",
    ],
    Intent.MATH: [
        "计算", "数学", "公式", "方程", "概率", "统计", "证明",
        "算法", "复杂度", "推导", "求解", "积分", "微分",
        "逻辑", "推理", "矛盾", "悖论",
    ],
    Intent.CREATIVE: [
        "写一", "创作", "故事", "小说", "诗", "文案", "广告",
        "创意", "灵感", "想象", "设计", "策划", "营销",
        "感觉", "情感", "心情", "建议", "人生",
    ],
    Intent.KNOWLEDGE: [
        "历史", "文化", "哲学", "文学", "典故", "朝代",
        "科学", "物理", "化学", "生物", "地理",
        "解释", "为什么", "原理", "概念", "理论",
    ],
    Intent.IMAGE: [
        "画", "图片", "生成图", "draw", "图像", "照片",
    ],
    Intent.ANALYSIS: [
        "分析", "对比", "优缺点", "评估", "判断",
        "怎么选", "哪个好", "利弊", "风险",
    ],
}


class ChatRouter:
    """群聊消息智能路由器"""

    def __init__(self):
        self.bots: Dict[str, BotCapability] = {}
        # 防重复回复：记录最近已回复的消息
        self._recent_responses: Dict[int, Dict] = {}  # msg_id -> {bot_id, time}
        self._response_window = 5.0  # 秒，同一消息的回复窗口
        self._response_lock = asyncio.Lock()  # 保护 _recent_responses 异步并发访问
        self._response_lock_sync = threading.Lock()  # 保护 sync should_respond 的竞态
        # 已注册的 bot user_id 集合，用于过滤 bot 消息
        self._bot_user_ids: set = set()
        # 讨论模式：chat_id -> {topic, rounds_left, participants, round_current, history, type}
        # type: "discuss" | "chain" — 统一管理 /discuss 和链式讨论
        self._discuss_sessions: Dict[int, Dict] = {}
        self._discuss_lock = asyncio.Lock()
        self._service_workflows: Dict[int, ServiceWorkflowSession] = {}
        self._service_workflow_lock = asyncio.Lock()
        # LLM 路由回调（可选，设置后用 LLM 做意图分类）
        self._llm_router_caller: Optional[Callable] = None
        # LLM 路由结果缓存：message_id -> (intent, bot_id) 或 None
        self._llm_cache: Dict[int, Optional[Tuple[str, str]]] = {}
        self._llm_cache_max = 200  # 最大缓存条目

    def register_bot(self, capability: BotCapability):
        """注册 bot 能力"""
        self.bots[capability.bot_id] = capability

    def register_bot_user_id(self, user_id: int):
        """注册 bot 的 Telegram user_id，用于过滤 bot 消息"""
        self._bot_user_ids.add(user_id)

    def _extract_lane_override(self, text: str) -> Optional[Tuple[str, str, str]]:
        """
        从文本中提取显式 lane 分流标记。

        Returns:
            (lane_name, bot_id, marker) 或 None
        """
        text_lower = (text or "").lower()
        for lane_name, bot_id, markers in LANE_ROUTE_RULES:
            for marker in markers:
                if marker in text_lower and bot_id in self.bots:
                    return lane_name, bot_id, marker
        return None

    def register_llm_router(self, caller: Callable):
        """
        注册 LLM 路由回调。
        caller 签名: async def caller(chat_id: int, prompt: str) -> str
        设置后，意图分类将优先使用 LLM 而非关键词匹配。
        """
        self._llm_router_caller = caller

    def is_bot_message(self, user_id: int) -> bool:
        """判断消息是否来自已注册的 bot"""
        return user_id in self._bot_user_ids

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

    async def start_service_workflow(
        self,
        chat_id: int,
        original_text: str,
        owner_bot_id: str,
        intake_bot_id: str,
        expert_bot_id: str,
        director_bot_id: str,
    ) -> Tuple[bool, str, Optional[ServiceWorkflowSession]]:
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
        preferred = ["qwen235b", "claude_haiku", "claude_sonnet", "deepseek_v3", "gptoss"]
        for bot_id in preferred:
            if bot_id in self.bots:
                return bot_id
        return next(iter(self.bots.keys()), "")

    def should_auto_service_workflow(self, text: str, chat_type: str, route_reason: str = "") -> bool:
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
        session = self._service_workflows.get(chat_id)
        if session and session.active:
            return session
        return None

    async def stop_service_workflow(self, chat_id: int) -> str:
        async with self._service_workflow_lock:
            session = self._service_workflows.pop(chat_id, None)
            if session:
                session.active = False
                return "链式服务流程已结束。"
            return "当前没有进行中的链式服务流程。"

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
                f"\n请就此主题发表你的观点。"
                f"如果之前有其他人发言，请回应或补充，不要重复已有观点。"
                f"保持简洁，每次发言控制在200字以内。"
            )

            return bot_id, prompt

    def record_discuss_message(self, chat_id: int, bot_name: str, message: str):
        """记录讨论中的发言"""
        session = self._discuss_sessions.get(chat_id)
        if session:
            # 截取前200字记录
            short = message[:200] + "..." if len(message) > 200 else message
            session["history"].append(f"[{bot_name}]: {short}")

    def classify_intent(self, text: str) -> List[Tuple[str, float]]:
        """
        对消息进行意图分类（关键词版本，同步）。
        返回 [(intent, score), ...] 按分数降序排列。
        """
        text_lower = text.lower()
        scores: Dict[str, float] = {}

        for intent, keywords in INTENT_KEYWORDS.items():
            score = 0.0
            for kw in keywords:
                if kw.lower() in text_lower:
                    # 关键词越长，权重越高
                    score += len(kw) * 0.5
            if score > 0:
                scores[intent] = score

        # 没有匹配到任何意图，归为通用
        if not scores:
            scores[Intent.GENERAL] = 1.0

        sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_intents

    async def classify_intent_llm(self, text: str, message_id: Optional[int] = None) -> Optional[Tuple[str, str]]:
        """
        使用 LLM 进行意图分类（异步，更准确）。
        结果按 message_id 缓存，同一消息不会重复调用 LLM。

        调用最便宜的模型（clawbot/DeepSeek-V3），一次 API 调用返回：
        - intent: 意图类别
        - best_bot: 最适合回答的 bot_id

        Returns:
            (intent, best_bot_id) 或 None（LLM 调用失败时回退到关键词）
        """
        if not self._llm_router_caller:
            return None

        # 检查缓存
        if message_id is not None and message_id in self._llm_cache:
            return self._llm_cache[message_id]

        # 构造精简的路由 prompt
        bot_descriptions = []
        for bid, bcap in self.bots.items():
            domains = ", ".join(bcap.domains[:3]) if bcap.domains else "通用"
            bot_descriptions.append(f"- {bid} ({bcap.name}): {domains}")
        bots_info = "\n".join(bot_descriptions)

        router_prompt = f"""你是一个消息路由器。根据用户消息，判断最适合回答的Bot。

可用Bot:
{bots_info}

意图类别: code(编程), math(数学逻辑), creative(创意写作), knowledge(知识文化), analysis(分析推理), image(图片), general(通用)

用户消息: {text[:200]}

请只输出一行，格式: intent|bot_id
例如: code|clawbot 或 creative|claude
不要输出其他内容。"""

        try:
            # 使用一个特殊的 chat_id（0）表示路由调用，不污染正常对话历史
            result = await self._llm_router_caller(0, router_prompt)
            result = result.strip().lower()

            # 解析结果
            if "|" in result:
                parts = result.split("|", 1)
                intent = parts[0].strip()
                bot_id = parts[1].strip()

                # 验证 intent 和 bot_id 合法性
                valid_intents = {"code", "math", "creative", "knowledge", "analysis", "image", "general"}
                if intent in valid_intents and bot_id in self.bots:
                    logger.debug(f"[LLM Router] '{text[:30]}...' -> {intent}|{bot_id}")
                    # 缓存结果
                    if message_id is not None:
                        self._llm_cache[message_id] = (intent, bot_id)
                        # 限制缓存大小
                        if len(self._llm_cache) > self._llm_cache_max:
                            oldest = next(iter(self._llm_cache))
                            del self._llm_cache[oldest]
                    return intent, bot_id

            logger.debug(f"[LLM Router] 解析失败: '{result}', 回退到关键词")
            # 缓存失败结果，避免重复调用
            if message_id is not None:
                self._llm_cache[message_id] = None
            return None

        except Exception as e:
            logger.debug(f"[LLM Router] 调用失败: {e}, 回退到关键词")
            # 不缓存异常，下次可重试
            return None

    def should_respond(
        self,
        bot_id: str,
        text: str,
        chat_type: str,
        message_id: Optional[int] = None,
        from_user_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        判断某个 bot 是否应该回复此消息。

        核心策略：
        - 私聊：总是回复
        - 群聊：人类发一轮 -> 仅一个最匹配的 Bot 回复一轮
        - Bot 的消息永远不回复（防止 Bot 互聊浪费 token）
        - /discuss N 模式下才允许多 Bot 多轮讨论

        Returns:
            (should_respond, reason)
        """
        bot = self.bots.get(bot_id)
        if not bot:
            return False, "bot 未注册"

        group_intent_enabled = _env_bool("CHAT_ROUTER_ENABLE_GROUP_INTENT", False)
        group_fallback_enabled = _env_bool("CHAT_ROUTER_ENABLE_GROUP_FALLBACK", False)

        # 私聊总是回复
        if chat_type == "private":
            return True, "私聊"

        # ===== 群聊逻辑 =====

        # 0. 过滤 Bot 消息 - 防止 Bot 互相回复导致无限循环浪费 token
        if from_user_id and self.is_bot_message(from_user_id):
            return False, "忽略Bot消息"

        text_lower = text.lower()

        # 1. 检测「所有人讨论」类指令 -> 触发链式讨论，不走普通路由
        for trigger in CHAIN_DISCUSS_TRIGGERS:
            if trigger in text_lower:
                # 标记为链式讨论消息，由 handle_message 中特殊处理
                return False, f"chain_discuss:{trigger}"

        # 2. 被 @ 提及 -> 仅被 @ 的这个 Bot 回复
        if f"@{bot.username}" in text:
            # 检查是否同时 @ 了其他 bot，如果是则只让被 @ 的回复
            other_bots_mentioned = any(
                f"@{other.username}" in text
                for bid, other in self.bots.items()
                if bid != bot_id
            )
            # 即使 @ 了多个 bot，每个被 @ 的都可以回复
            self._record_response(message_id, bot_id)
            return True, "被@提及"

        # 如果消息 @ 了其他 bot（不是自己），不要回复
        for bid, other in self.bots.items():
            if bid != bot_id and f"@{other.username}" in text:
                return False, "消息@了其他Bot"

        # 3. 显式 lane 分流（在话题群不可用时作为手动分流）
        lane_override = self._extract_lane_override(text)
        if lane_override:
            lane_name, lane_bot_id, marker = lane_override
            if bot_id == lane_bot_id:
                self._record_response(message_id, bot_id)
                return True, f"lane分流: {lane_name} ({marker})"
            return False, f"lane分流到 {lane_bot_id}"

        # 4. 名字被提到 -> 仅被提到的这个 Bot 回复
        name_triggers = [bot.name.lower(), bot_id.lower()]
        for trigger in name_triggers:
            if trigger in text_lower:
                self._record_response(message_id, bot_id)
                return True, f"名字被提到: {trigger}"

        # 5. 已有其他 Bot 回复此消息 -> 不再回复（严格一人一轮）
        if self._already_responded(message_id, bot_id):
            return False, "其他Bot已回复此消息"

        # 6. 关键词触发（仅第一个匹配的 Bot 回复）
        for kw in bot.keywords:
            if kw.lower() in text_lower:
                self._record_response(message_id, bot_id)
                return True, f"关键词触发: {kw}"

        # 7. 智能路由：优先 LLM 路由，回退到关键词
        # 注意：LLM 路由是异步的，但 should_respond 是同步的
        # 所以这里仍用关键词，LLM 路由在 should_respond_async 中使用
        intents = self.classify_intent(text)
        if group_intent_enabled and intents:
            top_intent, top_score = intents[0]
            preferred_bots = INTENT_BOT_MAP.get(top_intent, [])

            if bot_id in preferred_bots:
                rank = preferred_bots.index(bot_id)
                if rank == 0:
                    self._record_response(message_id, bot_id)
                    return True, f"意图路由: {top_intent} (最佳匹配)"
                # 不再让次选 Bot 回复，严格一人一轮

        # 8. 兜底：轮换 bot 回复（按 message_id 取模，避免永远同一个 bot）
        if group_fallback_enabled:
            fallback_idx = (message_id or 0) % len(_FALLBACK_ROTATION)
            fallback_bot = _FALLBACK_ROTATION[fallback_idx]
            if bot_id == fallback_bot and not self._already_responded(message_id, bot_id):
                self._record_response(message_id, bot_id)
                return True, f"兜底轮换: {fallback_bot}"

        starter_bot = self._select_service_workflow_starter()
        if starter_bot and self.should_auto_service_workflow(text, chat_type):
            if bot_id == starter_bot and not self._already_responded(message_id, bot_id):
                self._record_response(message_id, bot_id)
                return True, f"service_workflow:auto -> {starter_bot}"

        return False, "无匹配"

    async def should_respond_async(
        self,
        bot_id: str,
        text: str,
        chat_type: str,
        message_id: Optional[int] = None,
        from_user_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        异步版本的 should_respond，支持 LLM 路由。

        优先使用 LLM 路由（如果已注册），失败时回退到同步版本。
        仅在群聊、无 @mention、无关键词命中时才调用 LLM。

        使用 _response_lock 保护 _recent_responses 的读写，
        防止多个 bot 协程在 await 点交错导致重复回复。
        """
        bot = self.bots.get(bot_id)
        if not bot:
            return False, "bot 未注册"

        group_llm_enabled = _env_bool("CHAT_ROUTER_ENABLE_GROUP_LLM", False)
        group_intent_enabled = _env_bool("CHAT_ROUTER_ENABLE_GROUP_INTENT", False)
        group_fallback_enabled = _env_bool("CHAT_ROUTER_ENABLE_GROUP_FALLBACK", False)

        # 私聊总是回复
        if chat_type == "private":
            return True, "私聊"

        # 过滤 Bot 消息
        if from_user_id and self.is_bot_message(from_user_id):
            return False, "忽略Bot消息"

        text_lower = text.lower()

        # 链式讨论检测（无需锁，不涉及 _recent_responses）
        for trigger in CHAIN_DISCUSS_TRIGGERS:
            if trigger in text_lower:
                return False, f"chain_discuss:{trigger}"

        # @mention 检测
        if f"@{bot.username}" in text:
            async with self._response_lock:
                self._record_response(message_id, bot_id)
            return True, "被@提及"

        for bid, other in self.bots.items():
            if bid != bot_id and f"@{other.username}" in text:
                return False, "消息@了其他Bot"

        # 显式 lane 分流
        lane_override = self._extract_lane_override(text)
        if lane_override:
            lane_name, lane_bot_id, marker = lane_override
            if bot_id != lane_bot_id:
                return False, f"lane分流到 {lane_bot_id}"
            async with self._response_lock:
                if self._already_responded(message_id, bot_id):
                    return False, "其他Bot已回复此消息"
                self._record_response(message_id, bot_id)
            return True, f"lane分流: {lane_name} ({marker})"

        # 名字检测
        name_triggers = [bot.name.lower(), bot_id.lower()]
        for trigger in name_triggers:
            if trigger in text_lower:
                async with self._response_lock:
                    self._record_response(message_id, bot_id)
                return True, f"名字被提到: {trigger}"

        # 以下逻辑涉及 check-then-act 模式，必须在锁内完成
        async with self._response_lock:
            # 已有其他 Bot 回复
            if self._already_responded(message_id, bot_id):
                return False, "其他Bot已回复此消息"

            # 关键词触发
            for kw in bot.keywords:
                if kw.lower() in text_lower:
                    self._record_response(message_id, bot_id)
                    return True, f"关键词触发: {kw}"

        # === LLM 路由（仅在无明确匹配时使用） ===
        # LLM 调用在锁外执行（避免长时间持锁），结果在锁内写入
        if group_llm_enabled and self._llm_router_caller and len(text) > 5:
            llm_result = await self.classify_intent_llm(text, message_id)
            if llm_result:
                intent, best_bot = llm_result
                async with self._response_lock:
                    # 再次检查：LLM 调用期间可能已有其他 bot 抢先回复
                    if self._already_responded(message_id, bot_id):
                        return False, "其他Bot已回复此消息(LLM后)"
                    if bot_id == best_bot:
                        self._record_response(message_id, bot_id)
                        return True, f"LLM路由: {intent} -> {best_bot}"
                    else:
                        return False, f"LLM路由: {intent} -> {best_bot} (非本bot)"

        # 回退到关键词意图分类 + 兜底（在锁内完成）
        async with self._response_lock:
            # 再次检查（可能在 LLM 调用期间已有回复）
            if self._already_responded(message_id, bot_id):
                return False, "其他Bot已回复此消息"

            intents = self.classify_intent(text)
            if group_intent_enabled and intents:
                top_intent, top_score = intents[0]
                preferred_bots = INTENT_BOT_MAP.get(top_intent, [])
                if bot_id in preferred_bots:
                    rank = preferred_bots.index(bot_id)
                    if rank == 0:
                        self._record_response(message_id, bot_id)
                        return True, f"意图路由: {top_intent} (最佳匹配)"

            # 兜底轮换
            if group_fallback_enabled:
                fallback_idx = (message_id or 0) % len(_FALLBACK_ROTATION)
                fallback_bot = _FALLBACK_ROTATION[fallback_idx]
                if bot_id == fallback_bot and not self._already_responded(message_id, bot_id):
                    self._record_response(message_id, bot_id)
                    return True, f"兜底轮换: {fallback_bot}"

            starter_bot = self._select_service_workflow_starter()
            if starter_bot and self.should_auto_service_workflow(text, chat_type):
                if bot_id == starter_bot and not self._already_responded(message_id, bot_id):
                    self._record_response(message_id, bot_id)
                    return True, f"service_workflow:auto -> {starter_bot}"

        return False, "无匹配"

    def _record_response(self, message_id: Optional[int], bot_id: str):
        """记录回复（sync 版本需要 threading.Lock 保护）"""
        if message_id is None:
            return
        with self._response_lock_sync:
            self._recent_responses[message_id] = {
                "bot_id": bot_id,
                "time": time.time(),
            }
            # 清理过期记录
            self._cleanup_old_responses()

    def _already_responded(self, message_id: Optional[int], current_bot_id: str) -> bool:
        """检查是否已有其他 bot 回复了此消息（sync 版本需要 threading.Lock 保护）"""
        if message_id is None:
            return False
        with self._response_lock_sync:
            record = self._recent_responses.get(message_id)
            if record and record["bot_id"] != current_bot_id:
                if time.time() - record["time"] < self._response_window:
                    return True
            return False

    def _cleanup_old_responses(self):
        """清理过期的回复记录"""
        now = time.time()
        expired = [
            msg_id for msg_id, record in self._recent_responses.items()
            if now - record["time"] > 60.0  # 60秒后清理
        ]
        for msg_id in expired:
            del self._recent_responses[msg_id]

    def get_routing_info(self, text: str) -> Dict:
        """获取路由信息（调试用）"""
        intents = self.classify_intent(text)
        top_intent = intents[0] if intents else (Intent.GENERAL, 0)
        preferred = INTENT_BOT_MAP.get(top_intent[0], [])
        return {
            "intents": [(i, round(s, 2)) for i, s in intents[:3]],
            "preferred_bots": preferred,
        }

    def select_planner(self, text: str) -> str:
        """
        根据任务内容选择规划者。
        技术/逻辑/数学类 -> deepseek_r1
        中文语境/文化/综合类 -> qwen
        """
        intents = self.classify_intent(text)
        if not intents:
            return "qwen235b"  # 默认用 Qwen 235B

        top_intent = intents[0][0]

        # 技术类任务用 DeepSeek V3 规划
        tech_intents = {Intent.CODE, Intent.MATH, Intent.ANALYSIS}
        if top_intent in tech_intents:
            return "deepseek_v3"

        # 其他任务用 Qwen 235B 规划
        return "qwen235b"


# ============ 协作编排器 ============

class CollabPhase(Enum):
    """协作阶段"""
    PLANNING = "planning"       # 规划阶段
    EXECUTING = "executing"     # 执行阶段
    REVIEWING = "reviewing"     # 审查阶段（新增）
    SUMMARIZING = "summarizing" # 汇总阶段
    DONE = "done"               # 完成


@dataclass
class CollabTask:
    """协作任务"""
    task_id: str                    # 唯一任务ID
    chat_id: int                    # Telegram chat ID
    original_text: str              # 用户原始指令
    phase: CollabPhase = CollabPhase.PLANNING
    planner_id: str = ""            # 规划者 bot_id
    executor_id: str = "claude_sonnet"     # 执行者（默认 Claude Sonnet 4.5）
    reviewer_id: str = ""           # 审查者（新增，默认由规划者审查）
    summarizer_id: str = "qwen235b"  # 汇总者（默认 Qwen 235B）
    plan_result: str = ""           # 规划结果
    exec_result: str = ""           # 执行结果
    review_result: str = ""         # 审查结果（新增）
    review_passed: bool = True      # 审查是否通过（新增）
    summary_result: str = ""        # 汇总结果
    retry_count: int = 0            # 执行重试次数（新增）
    max_retries: int = 1            # 最大重试次数（新增）
    created_at: float = 0.0
    error: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()


class CollabOrchestrator:
    """
    协作编排器 - 实现"规划-执行-汇总"三阶段协作流程

    流程：
    1. 用户发送 /collab <任务描述>
    2. 路由器选择规划者（DeepSeek-R1 或 Qwen）
    3. 规划者分析任务，输出结构化执行计划
    4. Claude Opus 4.6 根据计划执行核心部分
    5. ClawBot 汇总所有结果，输出最终答案
    """

    def __init__(self, router: ChatRouter):
        self.router = router
        self.active_tasks: Dict[str, CollabTask] = {}  # task_id -> CollabTask
        self._api_callers: Dict[str, Callable] = {}    # bot_id -> async api call func
        self._lock = asyncio.Lock()

    def register_api_caller(self, bot_id: str, caller: Callable[..., Awaitable[str]]):
        """注册 bot 的 API 调用函数"""
        self._api_callers[bot_id] = caller

    async def start_collab(
        self,
        chat_id: int,
        task_text: str,
        planner_override: Optional[str] = None,
    ) -> CollabTask:
        """
        启动协作任务。

        Args:
            chat_id: Telegram chat ID
            task_text: 用户的任务描述
            planner_override: 强制指定规划者（可选）

        Returns:
            CollabTask 对象
        """
        task_id = f"collab_{chat_id}_{int(time.time())}"

        # 选择规划者
        planner_id = planner_override or self.router.select_planner(task_text)

        task = CollabTask(
            task_id=task_id,
            chat_id=chat_id,
            original_text=task_text,
            planner_id=planner_id,
            reviewer_id=planner_id,  # 审查者默认与规划者相同
        )

        async with self._lock:
            self.active_tasks[task_id] = task

        logger.info(f"[Collab] 启动协作任务 {task_id}: 规划者={planner_id}, 任务={task_text[:50]}...")
        return task

    async def run_planning(self, task: CollabTask) -> str:
        """第一阶段：规划"""
        task.phase = CollabPhase.PLANNING
        planner = self._api_callers.get(task.planner_id)
        if not planner:
            task.error = f"规划者 {task.planner_id} 未注册"
            return task.error

        # 构造规划提示
        plan_prompt = f"""【协作任务 - 规划阶段】

你现在是协作团队的"规划师"。用户提出了以下任务，请你：

1. 分析任务的核心需求和难点
2. 将任务分解为具体的执行步骤
3. 标注哪些步骤是核心难点（将交给 Claude Opus 4.6 执行）
4. 标注哪些步骤是辅助性的

请用以下格式输出你的规划：

## 任务分析
（简要分析任务需求和难点）

## 执行计划
### 核心任务（交给 Claude Opus 4.6）
1. ...
2. ...

### 辅助任务
1. ...

## 注意事项
（执行时需要注意的要点）

---
用户任务：{task.original_text}"""

        try:
            result = await planner(task.chat_id, plan_prompt)
            task.plan_result = result
            logger.info(f"[Collab] {task.task_id} 规划完成 by {task.planner_id}")
            return result
        except Exception as e:
            task.error = f"规划失败: {e}"
            logger.error(f"[Collab] {task.task_id} 规划失败: {e}")
            return task.error

    async def run_execution(self, task: CollabTask) -> str:
        """第二阶段：执行（Claude Opus 4.6）"""
        task.phase = CollabPhase.EXECUTING
        executor = self._api_callers.get(task.executor_id)
        if not executor:
            task.error = f"执行者 {task.executor_id} 未注册"
            return task.error

        if not task.plan_result:
            task.error = "没有规划结果，无法执行"
            return task.error

        # 构造执行提示
        exec_prompt = f"""【协作任务 - 执行阶段】

你是协作团队的核心执行者（Claude Opus 4.6），团队中的规划师已经为以下任务制定了执行计划。
请你根据规划，高质量地完成核心任务部分。

## 原始任务
{task.original_text}

## 规划师的执行计划
{task.plan_result}

---
请根据以上规划，完成核心任务。输出你的执行结果，要求：
- 高质量、深入、全面
- 如果是代码任务，给出完整可运行的代码
- 如果是分析任务，给出深度分析
- 如果是创作任务，给出精心打磨的作品"""

        try:
            result = await executor(task.chat_id, exec_prompt)
            task.exec_result = result
            logger.info(f"[Collab] {task.task_id} 执行完成 by {task.executor_id}")
            return result
        except Exception as e:
            task.error = f"执行失败: {e}"
            logger.error(f"[Collab] {task.task_id} 执行失败: {e}")
            return task.error

    async def run_review(self, task: CollabTask) -> str:
        """
        审查阶段：规划者审查执行结果，判断是否达标。

        返回审查意见。如果不通过，task.review_passed = False，
        调用方可据此决定是否重新执行。
        """
        task.phase = CollabPhase.REVIEWING
        reviewer = self._api_callers.get(task.reviewer_id)
        if not reviewer:
            # 没有审查者，默认通过
            task.review_passed = True
            task.review_result = "（无审查者，自动通过）"
            return task.review_result

        review_prompt = f"""【协作任务 - 审查阶段】

你是协作团队的审查者。执行者（Claude Opus 4.6）已根据规划完成了任务，请你审查执行结果的质量。

## 原始任务
{task.original_text}

## 规划（你之前制定的）
{task.plan_result[:1500]}

## 执行结果
{task.exec_result[:3000]}

---
请审查执行结果，输出格式：

**审查结论**: PASS 或 REVISE
**评分**: 1-10
**评价**: （简要评价执行质量）
**改进建议**: （如果 REVISE，列出需要改进的具体点）

注意：
- 只有明显质量不足、遗漏关键内容、或有明显错误时才给 REVISE
- 一般性的小瑕疵给 PASS 即可，不要过于苛刻
- 评分 7 分以上应该给 PASS"""

        try:
            result = await reviewer(task.chat_id, review_prompt)
            task.review_result = result

            # 解析审查结论（使用正则匹配，更健壮）
            # 匹配 "审查结论: PASS" 或 "**审查结论**: PASS" 等格式
            conclusion_match = re.search(
                r'审查结论[*\s:：]*\s*(PASS|REVISE)',
                result,
                re.IGNORECASE
            )
            if conclusion_match:
                task.review_passed = conclusion_match.group(1).upper() == "PASS"
            else:
                # 回退：如果没有匹配到格式化结论，检查全文
                # REVISE 出现且 PASS 未出现 -> 不通过
                has_revise = bool(re.search(r'\bREVISE\b', result, re.IGNORECASE))
                has_pass = bool(re.search(r'\bPASS\b', result, re.IGNORECASE))
                if has_revise and not has_pass:
                    task.review_passed = False
                else:
                    # 默认通过（宁可放行也不误拦）
                    task.review_passed = True

            logger.info(
                f"[Collab] {task.task_id} 审查完成 by {task.reviewer_id}, "
                f"passed={task.review_passed}"
            )
            return result
        except Exception as e:
            # 审查失败不阻塞流程，默认通过
            task.review_passed = True
            task.review_result = f"审查异常（自动通过）: {e}"
            logger.warning(f"[Collab] {task.task_id} 审查失败: {e}")
            return task.review_result

    async def run_revised_execution(self, task: CollabTask) -> str:
        """
        修订执行：根据审查意见重新执行。
        """
        task.phase = CollabPhase.EXECUTING
        task.retry_count += 1
        executor = self._api_callers.get(task.executor_id)
        if not executor:
            task.error = f"执行者 {task.executor_id} 未注册"
            return task.error

        revise_prompt = f"""【协作任务 - 修订执行】

你之前的执行结果未通过审查，请根据审查意见进行修订。

## 原始任务
{task.original_text}

## 规划
{task.plan_result[:1500]}

## 你之前的执行结果
{task.exec_result[:2000]}

## 审查意见
{task.review_result[:1500]}

---
请根据审查意见修订你的执行结果。重点改进审查中指出的问题。"""

        try:
            result = await executor(task.chat_id, revise_prompt)
            task.exec_result = result
            logger.info(f"[Collab] {task.task_id} 修订执行完成 (retry={task.retry_count})")
            return result
        except Exception as e:
            task.error = f"修订执行失败: {e}"
            logger.error(f"[Collab] {task.task_id} 修订执行失败: {e}")
            return task.error

    async def run_summary(self, task: CollabTask) -> str:
        """汇总阶段（ClawBot）- 包含审查信息"""
        task.phase = CollabPhase.SUMMARIZING
        summarizer = self._api_callers.get(task.summarizer_id)
        if not summarizer:
            task.error = f"汇总者 {task.summarizer_id} 未注册"
            return task.error

        # 构造汇总提示（包含审查信息）
        review_section = ""
        if task.review_result and task.review_result != "（无审查者，自动通过）":
            review_section = f"""
## 审查意见（{task.reviewer_id}）
{task.review_result[:1000]}
审查结论: {'通过' if task.review_passed else '修订后通过'}
{'修订次数: ' + str(task.retry_count) if task.retry_count > 0 else ''}
"""

        summary_prompt = f"""【协作任务 - 汇总阶段】

你是协作团队的汇总者。以下是一个协作任务的完整过程，请你：
1. 整合规划和执行的结果
2. 检查是否有遗漏或需要补充的地方
3. 输出一份清晰、完整的最终答案

## 原始任务
{task.original_text}

## 规划师（{task.planner_id}）的分析
{task.plan_result[:2000]}

## 执行者（Claude Opus 4.6）的结果
{task.exec_result[:4000]}
{review_section}
---
请输出最终的汇总结果。格式要求：
- 开头简要说明协作过程
- 然后给出完整的最终答案
- 如有必要，补充规划和执行中遗漏的内容"""

        try:
            result = await summarizer(task.chat_id, summary_prompt)
            task.summary_result = result
            task.phase = CollabPhase.DONE
            logger.info(f"[Collab] {task.task_id} 汇总完成 by {task.summarizer_id}")
            return result
        except Exception as e:
            task.error = f"汇总失败: {e}"
            logger.error(f"[Collab] {task.task_id} 汇总失败: {e}")
            return task.error

    async def run_full_pipeline(self, task: CollabTask) -> CollabTask:
        """运行完整的协作流程（含审查循环）"""
        await self.run_planning(task)
        if task.error:
            return task

        await self.run_execution(task)
        if task.error:
            return task

        # 审查循环
        await self.run_review(task)
        while not task.review_passed and task.retry_count < task.max_retries:
            await self.run_revised_execution(task)
            if task.error:
                return task
            await self.run_review(task)

        await self.run_summary(task)
        return task

    def get_active_task(self, chat_id: int) -> Optional[CollabTask]:
        """获取某个 chat 的活跃协作任务"""
        for task in self.active_tasks.values():
            if task.chat_id == chat_id and task.phase != CollabPhase.DONE:
                return task
        return None

    def cleanup_old_tasks(self, max_age: float = 3600.0):
        """清理超时的协作任务"""
        now = time.time()
        expired = [
            tid for tid, task in self.active_tasks.items()
            if now - task.created_at > max_age
        ]
        for tid in expired:
            del self.active_tasks[tid]


# ============ 对标 LiteLLM: 流式传输支持 ============

class StreamingResponse:
    """流式响应包装器 — 支持 SSE 风格的逐 chunk 传输
    
    对标 LiteLLM 的 streaming 支持，让 Telegram bot 可以
    逐步更新消息而不是等待完整响应。
    """

    def __init__(self):
        self._chunks: List[str] = []
        self._queue: asyncio.Queue = asyncio.Queue()
        self._done = False
        self._full_text = ""
        self._start_time = time.time()

    async def add_chunk(self, text: str):
        """添加一个文本 chunk"""
        self._chunks.append(text)
        self._full_text += text
        await self._queue.put(text)

    async def finish(self):
        """标记流结束"""
        self._done = True
        await self._queue.put(None)

    async def __aiter__(self):
        """异步迭代 chunks"""
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            yield chunk

    @property
    def full_text(self) -> str:
        return self._full_text

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self._start_time) * 1000

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)


async def stream_llm_to_telegram(
    llm_stream_func: Callable,
    send_func: Callable,
    chat_id: int,
    edit_interval: float = 1.0,
    min_chars_per_edit: int = 50,
):
    """将 LLM 流式输出实时推送到 Telegram 消息
    
    Args:
        llm_stream_func: async generator，yield 文本 chunks
        send_func: async (chat_id, text) -> message_id，发送/编辑消息
        chat_id: Telegram chat ID
        edit_interval: 最小编辑间隔（秒），避免 Telegram rate limit
        min_chars_per_edit: 每次编辑的最小新增字符数
    """
    full_text = ""
    message_id = None
    last_edit_time = 0
    pending_chars = 0

    try:
        async for chunk in llm_stream_func():
            full_text += chunk
            pending_chars += len(chunk)
            now = time.time()

            should_edit = (
                now - last_edit_time >= edit_interval
                and pending_chars >= min_chars_per_edit
            )

            if message_id is None:
                # 首次发送
                if len(full_text) >= 10:
                    message_id = await send_func(chat_id, full_text + " ▌")
                    last_edit_time = now
                    pending_chars = 0
            elif should_edit:
                try:
                    await send_func(chat_id, full_text + " ▌", edit_message_id=message_id)
                    last_edit_time = now
                    pending_chars = 0
                except Exception:
                    pass  # Telegram edit 偶尔失败，忽略

        # 最终更新（去掉光标）
        if message_id and full_text:
            try:
                await send_func(chat_id, full_text, edit_message_id=message_id)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"[Streaming] 流式传输失败: {e}")
        if full_text and message_id:
            try:
                await send_func(chat_id, full_text + "\n\n⚠️ 流式传输中断",
                                edit_message_id=message_id)
            except Exception:
                pass

    return full_text


# ============ 优先级消息队列 ============

class MessagePriority(Enum):
    """消息优先级"""
    CRITICAL = 0    # 系统告警、风控通知
    HIGH = 1        # 直接 @bot、私聊
    NORMAL = 2      # 群聊普通消息
    LOW = 3         # 自动化任务、定时消息
    BACKGROUND = 4  # 后台分析、日志


@dataclass(order=True)
class PrioritizedMessage:
    """带优先级的消息"""
    priority: int
    timestamp: float = field(compare=True)
    chat_id: int = field(compare=False)
    user_id: int = field(compare=False)
    text: str = field(compare=False)
    bot_id: str = field(compare=False, default="")
    metadata: Dict[str, Any] = field(compare=False, default_factory=dict)


class PriorityMessageQueue:
    """优先级消息队列 — 确保高优先级消息优先处理
    
    解决问题：当多个群同时发消息时，确保 @bot 的直接请求
    和风控告警优先于普通群聊消息被处理。
    """

    def __init__(self, max_size: int = 1000):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        self._stats = {
            "total_enqueued": 0,
            "total_processed": 0,
            "by_priority": {p.name: 0 for p in MessagePriority},
        }

    async def enqueue(self, msg: PrioritizedMessage):
        """入队"""
        await self._queue.put(msg)
        self._stats["total_enqueued"] += 1
        for p in MessagePriority:
            if p.value == msg.priority:
                self._stats["by_priority"][p.name] += 1
                break

    async def dequeue(self) -> PrioritizedMessage:
        """出队（阻塞等待）"""
        msg = await self._queue.get()
        self._stats["total_processed"] += 1
        return msg

    def classify_priority(self, text: str, chat_id: int, user_id: int,
                          is_private: bool = False, is_mentioned: bool = False) -> MessagePriority:
        """自动分类消息优先级"""
        text_lower = text.lower()

        # 风控/告警关键词
        if any(kw in text_lower for kw in ["止损", "爆仓", "风控", "紧急", "urgent", "alert"]):
            return MessagePriority.CRITICAL

        # 私聊或直接 @
        if is_private or is_mentioned:
            return MessagePriority.HIGH

        # 命令
        if text.startswith("/"):
            return MessagePriority.HIGH

        # 链式讨论触发
        if any(trigger in text_lower for trigger in CHAIN_DISCUSS_TRIGGERS[:5]):
            return MessagePriority.HIGH

        return MessagePriority.NORMAL

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "pending": self.pending,
        }
