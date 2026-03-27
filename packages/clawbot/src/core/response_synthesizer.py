"""
OpenClaw 响应合成层 — 从"数据堆砌"到"对话式回复"

设计哲学:
  - 搬运自 BasedHardware/omi (17k⭐) 的 proactive_notification 三步模式
  - Brain 路径的数据结果不再直接吐给用户，而是经过人格层合成为自然对话
  - 保持 SOUL.md 定义的性格一致性

架构:
  Brain.process_message()
    → TaskGraph 执行得到原始数据
    → ResponseSynthesizer.synthesize() 转化为对话式回复
    → 用户看到的是"人话"而非"报表"

依赖: config/prompts.py (SOUL_CORE, RESPONSE_SYNTH_PROMPT)

> 最后更新: 2026-03-25
"""

import logging
from typing import Any, Dict, Optional

from config.prompts import SOUL_CORE, RESPONSE_SYNTH_PROMPT, FOLLOWUP_SUGGESTIONS_PROMPT

logger = logging.getLogger(__name__)


class ResponseSynthesizer:
    """将 Brain 路径的结构化数据结果合成为对话式回复。

    解决的核心问题:
      - Brain 路径执行结果是 dict/JSON，直接展示像报表
      - 用户期望的是"助手在跟我说话"，不是"系统在展示数据"
      - 合成后的回复保持 SOUL.md 定义的性格一致性

    使用方式:
        synth = ResponseSynthesizer()
        reply = await synth.synthesize(
            raw_data={"decision": "buy", "confidence": 0.85, ...},
            task_type="investment",
            user_profile="严总偏好超短线...",
            conversation_summary="刚才讨论了TSLA的走势...",
        )
        # reply = "TSLA 目前 RSI 超卖反弹，85% 把握建议买入..."
    """

    # 首次能力引导标志 — 每种能力第一次触发时加一句说明
    # 搬运灵感: Apple 新功能首次使用时的 one-time tooltip
    _first_time_flags: dict = {}

    # 任务类型 → 合成时的附加指引
    _TASK_HINTS: Dict[str, str] = {
        "investment": (
            "这是投资分析结果。重点说: 建议(买/卖/持有) + 核心理由(一句话) + 风险提醒。"
            "如果多个分析师意见不一致，要明确说出分歧。"
            "结尾建议下一步: 回测验证/设止损/继续观察。"
        ),
        "shopping": (
            "这是购物比价结果。重点说: 最便宜在哪 + 价差多大 + 值不值得买。"
            "结尾建议: 设降价提醒(告诉用户发'/pricewatch add 商品名 目标价')/直接买/再等等。"
        ),
        "social": (
            "这是社媒运营结果。重点说: 做了什么 + 效果预期。"
            "结尾建议: 何时发下一篇/要不要调整策略。"
        ),
        "info": (
            "这是信息查询结果。直接回答，不要重复问题。"
            "如果信息可能过时，标注数据日期。"
        ),
    }

    # 不需要合成的简单结果类型
    _SKIP_SYNTHESIS = {"forward_to_chat", "clarification_needed"}

    async def synthesize(
        self,
        raw_data: Dict[str, Any],
        task_type: str = "unknown",
        user_profile: str = "",
        conversation_summary: str = "",
        max_tokens: int = 300,
    ) -> Optional[str]:
        """将原始数据结果合成为对话式回复。

        Args:
            raw_data: Brain 执行的原始结果 (dict)
            task_type: 任务类型 (investment/shopping/social/info/...)
            user_profile: 用户画像文本 (来自 SmartMemory)
            conversation_summary: 近期对话摘要
            max_tokens: 合成回复的最大 token 数

        Returns:
            合成后的自然语言回复，或 None (表示跳过合成)
        """
        # 跳过不需要合成的简单结果
        if not raw_data:
            return None

        action = raw_data.get("action", "")
        if action in self._SKIP_SYNTHESIS:
            return None

        # 简单 answer 类型不需要再合成（已经是 LLM 直接回答）
        if list(raw_data.keys()) == ["answer"] and isinstance(raw_data["answer"], str):
            return None

        # 准备合成提示
        raw_text = self._format_raw_data(raw_data)

        # 数据太少不值得合成
        if len(raw_text) < 50:
            return None

        task_hint = self._TASK_HINTS.get(task_type, "")
        prompt = RESPONSE_SYNTH_PROMPT.format(
            user_profile=user_profile or "暂无画像",
            conversation_summary=conversation_summary or "新对话",
            raw_data=raw_text,
        )
        if task_hint:
            prompt = f"{task_hint}\n\n{prompt}"

        try:
            from src.litellm_router import free_pool

            if not free_pool:
                return None

            try:
                from src.resilience import api_limiter
            except ImportError:
                from contextlib import asynccontextmanager

                @asynccontextmanager
                async def api_limiter(service: str = "generic"):
                    yield

            async with api_limiter("llm"):
                resp = await free_pool.acompletion(
                    model_family="qwen",
                    messages=[
                        {"role": "system", "content": SOUL_CORE},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.6,
                    max_tokens=max_tokens,
                )
            answer = resp.choices[0].message.content
            if answer and len(answer.strip()) > 10:
                return answer.strip()
        except Exception as e:
            logger.debug(f"响应合成失败 (降级到原始格式): {e}")

        return None

    def _format_raw_data(self, data: Dict[str, Any], depth: int = 0) -> str:
        """将嵌套 dict 格式化为 LLM 可读的文本。"""
        if depth > 3:
            return str(data)[:200]

        lines = []
        for key, value in data.items():
            if isinstance(value, dict):
                nested = self._format_raw_data(value, depth + 1)
                lines.append(f"{key}:\n{nested}")
            elif isinstance(value, list):
                if not value:
                    lines.append(f"{key}: (空)")
                elif isinstance(value[0], dict):
                    for i, item in enumerate(value[:5]):
                        lines.append(f"{key}[{i}]: {self._format_raw_data(item, depth + 1)}")
                else:
                    lines.append(f"{key}: {', '.join(str(v) for v in value[:10])}")
            else:
                lines.append(f"{key}: {value}")

        indent = "  " * depth
        return "\n".join(f"{indent}{line}" for line in lines)

    # ── 智能追问引擎 — 搬运 khoj/open-webui follow_up 模式 ──────

    async def generate_suggestions(
        self, response_text: str, task_type: str = "", context: str = ""
    ) -> list[str]:
        """根据回复内容生成 2-3 个后续操作建议按钮文本。

        用最便宜的 g4f 模型生成，异常时返回空列表不影响主流程。
        搬运灵感: khoj follow_up / open-webui suggested actions
        """
        try:
            from src.litellm_router import free_pool

            if not free_pool:
                return []

            prompt = FOLLOWUP_SUGGESTIONS_PROMPT.format(
                task_type=task_type or "通用",
                response_text=(response_text or "")[:500],
            )

            try:
                from src.resilience import api_limiter as _limiter
            except ImportError:
                from contextlib import asynccontextmanager

                @asynccontextmanager
                async def _limiter(service: str = "generic"):
                    yield

            async with _limiter("llm"):
                resp = await free_pool.acompletion(
                    model_family="g4f",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=100,
                )

            raw = (resp.choices[0].message.content or "").strip()
            if not raw:
                return []

            # 解析: 每行一个建议，去掉编号/标点/空行
            lines = []
            for line in raw.splitlines():
                cleaned = line.strip().lstrip("0123456789.-、)）·• ").strip()
                if cleaned and 3 <= len(cleaned) <= 30:
                    lines.append(cleaned)
            result = lines[:3]
            # 首次引导: 追问建议第一次出现时加一个说明项
            if result and "suggestions" not in self._first_time_flags:
                self._first_time_flags["suggestions"] = True
                result.append("💡 这些是AI建议的下一步")
            return result

        except Exception as e:
            logger.debug(f"生成追问建议失败 (不影响主流程): {e}")
            return []

    async def generate_tldr(self, text: str, max_chars: int = 80) -> str:
        """为长文本生成 TL;DR 摘要（搬运 Perplexity 摘要先行模式）。

        仅当 text 长度 > 200 字符时生成，用最便宜的 g4f 模型。
        异常时返回空字符串不影响主流程。
        """
        if not text or len(text) <= 200:
            return ""

        try:
            from src.litellm_router import free_pool

            if not free_pool:
                return ""

            prompt = (
                f"用一句话（不超过{max_chars}字）总结以下内容的核心结论:\n\n"
                f"{text[:800]}\n\n"
                f"一句话总结:"
            )

            try:
                from src.resilience import api_limiter as _limiter
            except ImportError:
                from contextlib import asynccontextmanager

                @asynccontextmanager
                async def _limiter(service: str = "generic"):
                    yield

            async with _limiter("llm"):
                resp = await free_pool.acompletion(
                    model_family="g4f",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=60,
                )

            summary = (resp.choices[0].message.content or "").strip()
            # 去掉常见的前缀废话
            for prefix in ["总结：", "总结:", "摘要：", "摘要:", "核心结论："]:
                if summary.startswith(prefix):
                    summary = summary[len(prefix):].strip()
            if summary and len(summary) <= max_chars * 2:
                # 首次引导: TL;DR 第一次触发时加一句说明
                if "tldr" not in self._first_time_flags:
                    self._first_time_flags["tldr"] = True
                    summary += "\n(💡 长回复我会先说结论，方便你快速扫一眼)"
                return summary
            return ""

        except Exception as e:
            logger.debug(f"生成 TL;DR 摘要失败 (不影响主流程): {e}")
            return ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  上下文收集器 — 为 Brain 路径提供对话历史和用户画像
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BrainContextCollector:
    """为 Brain 路径收集对话上下文和用户画像。

    解决的核心问题:
      - Brain 路径之前完全无状态（每次都是全新的）
      - 用户说"那竞争对手呢"时 Brain 不知道"那"指什么
      - 用户画像生成了但没人用

    数据来源:
      - TieredContextManager → 对话历史摘要
      - SharedMemory → 用户画像 (SmartMemoryPipeline 生成)
      - HistoryStore → 最近 N 条消息
    """

    def __init__(self):
        self._profile_cache: Dict[str, str] = {}  # user_id → profile text
        self._profile_cache_ttl: Dict[str, float] = {}  # user_id → timestamp

    async def collect(
        self,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        bot_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """收集 Brain 需要的上下文。

        Returns:
            {
                "user_profile": "严总偏好超短线...",
                "conversation_summary": "刚才讨论了TSLA...",
                "recent_messages": "用户: 帮我分析TSLA\nAI: ...",
            }
        """
        result = {
            "user_profile": "",
            "conversation_summary": "",
            "recent_messages": "",
        }

        # 1. 获取用户画像 (从 SharedMemory)
        if user_id:
            result["user_profile"] = await self._get_user_profile(user_id)

        # 2. 获取对话历史摘要
        if chat_id and bot_id:
            result["conversation_summary"] = await self._get_conversation_summary(
                chat_id, bot_id
            )
            result["recent_messages"] = await self._get_recent_messages(
                chat_id, bot_id
            )

        # 3. 获取跨域关联信号（搬运 omi cross-context awareness）
        result["cross_domain_signals"] = self._get_cross_domain_signals()

        return result

    def _get_cross_domain_signals(self) -> str:
        """从 SynergyPipelines 获取跨域关联信号。

        搬运 omi cross-context awareness: 让 Brain 处理任何请求时
        都能"联想"到投资/社媒/风控等其他领域的相关信息。
        """
        try:
            from src.core.synergy_pipelines import get_synergy_pipelines

            sp = get_synergy_pipelines()
            if sp:
                return sp.get_context_enrichment()
        except Exception as e:
            logger.debug(f"获取跨域信号失败: {e}")
        return ""

    async def _get_user_profile(self, user_id: str) -> str:
        """从 SharedMemory 获取用户画像。"""
        import time

        # 缓存检查 (5分钟 TTL)
        cached_ts = self._profile_cache_ttl.get(user_id, 0)
        if time.time() - cached_ts < 300 and user_id in self._profile_cache:
            return self._profile_cache[user_id]

        try:
            from src.bot.globals import get_shared_memory

            sm = get_shared_memory()
            if not sm:
                return ""

            # SmartMemoryPipeline 将画像存储为 user_profile_{user_id}
            results = sm.search(
                f"user_profile_{user_id}",
                category="user_profile",
                limit=1,
            )
            if results:
                profile_text = results[0].get("content", "")
                self._profile_cache[user_id] = profile_text
                self._profile_cache_ttl[user_id] = time.time()
                return profile_text

            # 降级: 从记忆中搜索用户偏好
            results = sm.search(
                "user preference",
                user_id=user_id,
                limit=5,
            )
            if results:
                prefs = "; ".join(
                    r.get("content", "")[:100] for r in results if r.get("content")
                )
                self._profile_cache[user_id] = prefs
                self._profile_cache_ttl[user_id] = time.time()
                return prefs

        except Exception as e:
            logger.debug(f"获取用户画像失败: {e}")

        return ""

    async def _get_conversation_summary(self, chat_id: str, bot_id: str) -> str:
        """从 TieredContextManager 获取对话摘要。"""
        try:
            from src.bot.globals import get_context_managers

            managers = get_context_managers()
            tcm = managers.get("tiered") if managers else None
            if not tcm:
                return ""

            # TieredContextManager 的 core memory 包含当前任务和关键事实
            core = tcm.core_get_all(chat_id)
            if not core:
                return ""

            parts = []
            current_task = core.get("current_task", "")
            if current_task:
                parts.append(f"当前任务: {current_task}")

            key_facts = core.get("key_facts", [])
            if key_facts:
                facts_text = "; ".join(str(f) for f in key_facts[:5])
                parts.append(f"关键事实: {facts_text}")

            return "\n".join(parts)
        except Exception as e:
            logger.debug(f"获取对话摘要失败: {e}")
            return ""

    async def _get_recent_messages(
        self, chat_id: str, bot_id: str, limit: int = 5
    ) -> str:
        """获取最近 N 条消息文本。"""
        try:
            from src.bot.globals import get_history_store

            hs = get_history_store()
            if not hs:
                return ""

            messages = hs.get_messages(bot_id, int(chat_id), limit=limit)
            if not messages:
                return ""

            lines = []
            for msg in messages[-limit:]:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:200]
                speaker = "严总" if role == "user" else "OpenClaw"
                lines.append(f"[{speaker}]: {content}")

            return "\n".join(lines)
        except Exception as e:
            logger.debug(f"获取最近消息失败: {e}")
            return ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  单例
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_synthesizer: Optional[ResponseSynthesizer] = None
_context_collector: Optional[BrainContextCollector] = None


def get_response_synthesizer() -> ResponseSynthesizer:
    """获取全局 ResponseSynthesizer 实例。"""
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = ResponseSynthesizer()
    return _synthesizer


def get_context_collector() -> BrainContextCollector:
    """获取全局 BrainContextCollector 实例。"""
    global _context_collector
    if _context_collector is None:
        _context_collector = BrainContextCollector()
    return _context_collector
