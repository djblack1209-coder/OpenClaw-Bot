"""
ChatRouter — 群聊消息智能路由器
从 chat_router.py 拆分而来，包含核心路由判断和意图分类。
会话管理（讨论/工作流）通过 SessionMixin 注入。
"""
import asyncio
import logging
import threading
import time
from collections.abc import Callable

from src.constants import BOT_DEEPSEEK, BOT_QWEN
from src.routing.constants import (
    CHAIN_DISCUSS_TRIGGERS,
    FALLBACK_ROTATION,
    INTENT_BOT_MAP,
    INTENT_KEYWORDS,
    LANE_ROUTE_RULES,
    Intent,
)
from src.routing.models import BotCapability
from src.routing.sessions import SessionMixin
from src.utils import env_bool

logger = logging.getLogger(__name__)


class ChatRouter(SessionMixin):
    """群聊消息智能路由器 — 继承 SessionMixin 获得讨论/工作流能力"""

    def __init__(self):
        self.bots: dict[str, BotCapability] = {}
        # 防重复回复：记录最近已回复的消息
        self._recent_responses: dict[int, dict] = {}  # msg_id -> {bot_id, time}
        self._response_window = 5.0  # 秒，同一消息的回复窗口
        self._response_lock = asyncio.Lock()  # 保护 _recent_responses 异步并发访问
        self._response_lock_sync = threading.Lock()  # 保护 sync should_respond 的竞态
        # 已注册的 bot user_id 集合，用于过滤 bot 消息
        self._bot_user_ids: set = set()
        # LLM 路由回调（可选，设置后用 LLM 做意图分类）
        self._llm_router_caller: Callable | None = None
        # LLM 路由结果缓存：message_id -> (intent, bot_id) 或 None
        self._llm_cache: dict[int, tuple[str, str] | None] = {}
        self._llm_cache_max = 200  # 最大缓存条目
        # 初始化会话管理（来自 SessionMixin）
        self._init_sessions()

    # ============ 注册方法 ============

    def register_bot(self, capability: BotCapability):
        """注册 bot 能力"""
        self.bots[capability.bot_id] = capability

    def register_bot_user_id(self, user_id: int):
        """注册 bot 的 Telegram user_id，用于过滤 bot 消息"""
        self._bot_user_ids.add(user_id)

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

    # ============ Lane 分流 ============

    def _extract_lane_override(self, text: str) -> tuple[str, str, str] | None:
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

    # ============ 意图分类 ============

    def classify_intent(self, text: str) -> list[tuple[str, float]]:
        """
        对消息进行意图分类（关键词版本，同步）。
        返回 [(intent, score), ...] 按分数降序排列。
        """
        text_lower = text.lower()
        scores: dict[str, float] = {}

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

    async def classify_intent_llm(self, text: str, message_id: int | None = None) -> tuple[str, str] | None:
        """
        使用 LLM 进行意图分类（异步，更准确）。
        结果按 message_id 缓存，同一消息不会重复调用 LLM。

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
            # 使用特殊 chat_id（0）表示路由调用，不污染正常对话历史
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

    # ============ 路由判断 ============

    def should_respond(
        self,
        bot_id: str,
        text: str,
        chat_type: str,
        message_id: int | None = None,
        from_user_id: int | None = None,
    ) -> tuple[bool, str]:
        """
        判断某个 bot 是否应该回复此消息（同步版本）。

        核心策略：
        - 私聊：总是回复
        - 群聊：人类发一轮 -> 仅一个最匹配的 Bot 回复一轮
        - Bot 的消息永远不回复（防止 Bot 互聊浪费 token）

        Returns:
            (should_respond, reason)
        """
        bot = self.bots.get(bot_id)
        if not bot:
            return False, "bot 未注册"

        group_intent_enabled = env_bool("CHAT_ROUTER_ENABLE_GROUP_INTENT", False)
        group_fallback_enabled = env_bool("CHAT_ROUTER_ENABLE_GROUP_FALLBACK", False)

        # 私聊总是回复
        if chat_type == "private":
            return True, "私聊"

        # ===== 群聊逻辑 =====

        # 0. 过滤 Bot 消息
        if from_user_id and self.is_bot_message(from_user_id):
            return False, "忽略Bot消息"

        text_lower = text.lower()

        # 1. 链式讨论检测
        for trigger in CHAIN_DISCUSS_TRIGGERS:
            if trigger in text_lower:
                return False, f"chain_discuss:{trigger}"

        # 2. 被 @ 提及
        if f"@{bot.username}" in text:
            any(
                f"@{other.username}" in text
                for bid, other in self.bots.items()
                if bid != bot_id
            )
            self._record_response(message_id, bot_id)
            return True, "被@提及"

        # 如果消息 @ 了其他 bot（不是自己），不要回复
        for bid, other in self.bots.items():
            if bid != bot_id and f"@{other.username}" in text:
                return False, "消息@了其他Bot"

        # 3. 显式 lane 分流
        lane_override = self._extract_lane_override(text)
        if lane_override:
            lane_name, lane_bot_id, marker = lane_override
            if bot_id == lane_bot_id:
                self._record_response(message_id, bot_id)
                return True, f"lane分流: {lane_name} ({marker})"
            return False, f"lane分流到 {lane_bot_id}"

        # 4. 名字被提到
        name_triggers = [bot.name.lower(), bot_id.lower()]
        for trigger in name_triggers:
            if trigger in text_lower:
                self._record_response(message_id, bot_id)
                return True, f"名字被提到: {trigger}"

        # 5. 已有其他 Bot 回复此消息
        if self._already_responded(message_id, bot_id):
            return False, "其他Bot已回复此消息"

        # 6. 关键词触发
        for kw in bot.keywords:
            if kw.lower() in text_lower:
                self._record_response(message_id, bot_id)
                return True, f"关键词触发: {kw}"

        # 7. 智能路由：关键词意图分类
        intents = self.classify_intent(text)
        if group_intent_enabled and intents:
            top_intent, top_score = intents[0]
            preferred_bots = INTENT_BOT_MAP.get(top_intent, [])
            if bot_id in preferred_bots:
                rank = preferred_bots.index(bot_id)
                if rank == 0:
                    self._record_response(message_id, bot_id)
                    return True, f"意图路由: {top_intent} (最佳匹配)"

        # 8. 兜底轮换
        if group_fallback_enabled:
            fallback_idx = (message_id or 0) % len(FALLBACK_ROTATION)
            fallback_bot = FALLBACK_ROTATION[fallback_idx]
            if bot_id == fallback_bot and not self._already_responded(message_id, bot_id):
                self._record_response(message_id, bot_id)
                return True, f"兜底轮换: {fallback_bot}"

        # 9. 自动服务工作流
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
        message_id: int | None = None,
        from_user_id: int | None = None,
    ) -> tuple[bool, str]:
        """
        异步版本的 should_respond，支持 LLM 路由。

        优先使用 LLM 路由（如果已注册），失败时回退到同步版本。
        使用 _response_lock 保护 _recent_responses 的读写。
        """
        bot = self.bots.get(bot_id)
        if not bot:
            return False, "bot 未注册"

        group_llm_enabled = env_bool("CHAT_ROUTER_ENABLE_GROUP_LLM", False)
        group_intent_enabled = env_bool("CHAT_ROUTER_ENABLE_GROUP_INTENT", False)
        group_fallback_enabled = env_bool("CHAT_ROUTER_ENABLE_GROUP_FALLBACK", False)

        # 私聊总是回复
        if chat_type == "private":
            return True, "私聊"

        # 过滤 Bot 消息
        if from_user_id and self.is_bot_message(from_user_id):
            return False, "忽略Bot消息"

        text_lower = text.lower()

        # 链式讨论检测
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
            if self._already_responded(message_id, bot_id):
                return False, "其他Bot已回复此消息"

            for kw in bot.keywords:
                if kw.lower() in text_lower:
                    self._record_response(message_id, bot_id)
                    return True, f"关键词触发: {kw}"

        # === LLM 路由（仅在无明确匹配时使用） ===
        if group_llm_enabled and self._llm_router_caller and len(text) > 5:
            llm_result = await self.classify_intent_llm(text, message_id)
            if llm_result:
                intent, best_bot = llm_result
                async with self._response_lock:
                    if self._already_responded(message_id, bot_id):
                        return False, "其他Bot已回复此消息(LLM后)"
                    if bot_id == best_bot:
                        self._record_response(message_id, bot_id)
                        return True, f"LLM路由: {intent} -> {best_bot}"
                    else:
                        return False, f"LLM路由: {intent} -> {best_bot} (非本bot)"

        # 回退到关键词意图分类 + 兜底（在锁内完成）
        async with self._response_lock:
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

            if group_fallback_enabled:
                fallback_idx = (message_id or 0) % len(FALLBACK_ROTATION)
                fallback_bot = FALLBACK_ROTATION[fallback_idx]
                if bot_id == fallback_bot and not self._already_responded(message_id, bot_id):
                    self._record_response(message_id, bot_id)
                    return True, f"兜底轮换: {fallback_bot}"

            starter_bot = self._select_service_workflow_starter()
            if starter_bot and self.should_auto_service_workflow(text, chat_type):
                if bot_id == starter_bot and not self._already_responded(message_id, bot_id):
                    self._record_response(message_id, bot_id)
                    return True, f"service_workflow:auto -> {starter_bot}"

        return False, "无匹配"

    # ============ 内部辅助方法 ============

    def _record_response(self, message_id: int | None, bot_id: str):
        """记录回复（sync 版本需要 threading.Lock 保护）"""
        if message_id is None:
            return
        with self._response_lock_sync:
            self._recent_responses[message_id] = {
                "bot_id": bot_id,
                "time": time.time(),
            }
            self._cleanup_old_responses()

    def _already_responded(self, message_id: int | None, current_bot_id: str) -> bool:
        """检查是否已有其他 bot 回复了此消息"""
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
            if now - record["time"] > 60.0
        ]
        for msg_id in expired:
            del self._recent_responses[msg_id]

    def get_routing_info(self, text: str) -> dict:
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
        技术/逻辑/数学类 -> deepseek_v3
        中文语境/文化/综合类 -> qwen235b
        """
        intents = self.classify_intent(text)
        if not intents:
            return BOT_QWEN

        top_intent = intents[0][0]
        tech_intents = {Intent.CODE, Intent.MATH, Intent.ANALYSIS}
        if top_intent in tech_intents:
            return BOT_DEEPSEEK

        return BOT_QWEN
