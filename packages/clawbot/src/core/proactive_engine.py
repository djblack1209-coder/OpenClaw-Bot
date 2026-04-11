"""
OpenClaw 主动智能引擎 — 不再等用户开口

搬运自 BasedHardware/omi (17k⭐) 的 proactive_notification 三步管道:
  Gate(是否值得打扰) → Generate(生成通知) → Critic(人类视角审查)

与 omi 的差异:
  - omi 监听麦克风实时对话; 我们监听 EventBus 事件 + 定时检查
  - omi 用 langchain; 我们用 LiteLLM free_pool
  - 增加了频率控制: 每用户每小时最多 3 条主动通知
  - 增加了成本控制: Gate 用最便宜模型，只有通过后才用更好的模型

触发场景:
  1. 价格异动 — 持仓/关注标的价格剧烈变动
  2. 任务到期 — 定时任务/提醒即将触发
  3. 跨领域关联 — 闲鱼成交 + 资金可用于投资
  4. 风控预警 — 持仓接近止损位

集成方式:
  - multi_main.py 启动时注册到 EventBus
  - APScheduler 每 30 分钟做一次 proactive check
  - 结果通过 Telegram Bot 推送

模块拆分 (HI-358):
  - proactive_models.py    — Pydantic 结构化输出模型
  - proactive_notify.py    — Telegram 通知发送辅助函数
  - proactive_listeners.py — EventBus 事件监听器 (9个)
  - proactive_periodic.py  — 定时主动检查逻辑

> 最后更新: 2026-04-11
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from config.prompts import (
    PROACTIVE_GATE_PROMPT,
    PROACTIVE_GENERATE_PROMPT,
    PROACTIVE_CRITIC_PROMPT,
    SOUL_CORE,
)

# 速率限制 — resilience 模块始终可导入，内部已做优雅降级
from src.constants import FAMILY_G4F, FAMILY_QWEN
from src.resilience import api_limiter

# ── 从拆分模块导入，保持向后兼容 (HI-358) ──
from src.core.proactive_models import GateResult, NotificationDraft, CriticResult  # noqa: F401
from src.core.proactive_notify import _send_proactive, _send_proactive_photo, _safe_parse_time  # noqa: F401
from src.core.proactive_listeners import setup_proactive_listeners  # noqa: F401
from src.core.proactive_periodic import periodic_proactive_check  # noqa: F401

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  频率控制
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAX_NOTIFICATIONS_PER_HOUR = 3
GATE_THRESHOLD = 0.70  # relevance_score 必须超过此阈值


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  主引擎
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ProactiveEngine:
    """主动智能引擎 — 三步管道决定是否主动推送通知。

    使用方式:
        engine = ProactiveEngine()
        notification = await engine.evaluate(
            context_type="price_alert",
            current_context="TSLA 跌了 5%，严总持有 10 股",
            user_id="123",
        )
        if notification:
            await bot.send_message(chat_id, notification)
    """

    def __init__(self):
        self._sent_log: Dict[str, List[float]] = {}  # user_id → [timestamps]
        self._recent_notifications: Dict[str, List[str]] = {}  # user_id → [texts]
        self._last_cleanup = 0.0
        # asyncio 锁：保护 _sent_log/_recent_notifications 跨 await 的并发访问（HI-464）
        self._lock = asyncio.Lock()

    def _cleanup_old_entries(self):
        """清理 24 小时前的发送记录，防止内存无限增长"""
        import time as _time
        now = _time.time()
        if now - self._last_cleanup < 3600:  # 每小时最多清理一次
            return
        self._last_cleanup = now
        cutoff = now - 86400  # 24 小时
        for uid in list(self._sent_log):
            self._sent_log[uid] = [t for t in self._sent_log[uid] if t > cutoff]
            if not self._sent_log[uid]:
                self._sent_log.pop(uid, None)
        for uid in list(self._recent_notifications):
            if uid not in self._sent_log:
                self._recent_notifications.pop(uid, None)

    async def evaluate(
        self,
        context_type: str,
        current_context: str,
        user_id: str = "",
        user_profile: str = "",
    ) -> Optional[str]:
        """三步管道评估是否应该主动推送通知。

        Args:
            context_type: 触发类型 (price_alert/task_due/cross_domain/risk_warning)
            current_context: 当前上下文描述
            user_id: 用户 ID
            user_profile: 用户画像

        Returns:
            通知文本 (str) 或 None (表示不推送)
        """
        # 0. 频率限制
        async with self._lock:
            if self._is_rate_limited(user_id):
                logger.debug(f"主动通知频率限制: user={user_id}")
                return None

            recent = self._get_recent_notifications(user_id)

        # Step 1: Gate — 最便宜模型快速判断
        gate_result = await self._step_gate(
            current_context=current_context,
            user_profile=user_profile,
            recent_notifications=recent,
        )
        if not gate_result or not gate_result.is_relevant:
            logger.debug(f"Gate 拒绝: score={gate_result.relevance_score if gate_result else 0}")
            return None
        if gate_result.relevance_score < GATE_THRESHOLD:
            logger.debug(f"Gate 分数不足: {gate_result.relevance_score} < {GATE_THRESHOLD}")
            return None

        # Step 2: Generate — 生成通知文本
        draft = await self._step_generate(
            current_context=current_context,
            user_profile=user_profile,
            gate_reasoning=gate_result.reasoning,
            recent_notifications=recent,
        )
        if not draft or not draft.notification_text:
            return None

        # Step 3: Critic — 最后审查
        critic = await self._step_critic(
            notification_text=draft.notification_text,
            draft_reasoning=gate_result.reasoning,
        )
        if not critic or not critic.approved:
            logger.debug(f"Critic 拒绝: {critic.reasoning if critic else 'failed'}")
            return None

        # 记录已发送（锁保护，防止并发写入竞态）
        async with self._lock:
            self._record_sent(user_id, draft.notification_text)
        return draft.notification_text

    # ━━━━━━━━━━━━ Step 1: Gate ━━━━━━━━━━━━

    async def _step_gate(
        self,
        current_context: str,
        user_profile: str,
        recent_notifications: str,
    ) -> Optional[GateResult]:
        """Gate: 快速判断是否值得打扰。用最便宜的模型。"""
        prompt = PROACTIVE_GATE_PROMPT.format(
            user_profile=user_profile or "暂无画像",
            current_context=current_context,
            recent_notifications=recent_notifications or "无最近通知",
        )
        try:
            result = await self._llm_structured(prompt, GateResult, cheap=True)
            return result
        except Exception as e:
            logger.debug(f"Gate 调用失败: {e}")
            return None

    # ━━━━━━━━━━━━ Step 2: Generate ━━━━━━━━━━━━

    async def _step_generate(
        self,
        current_context: str,
        user_profile: str,
        gate_reasoning: str,
        recent_notifications: str,
    ) -> Optional[NotificationDraft]:
        """Generate: 生成通知文本。"""
        prompt = PROACTIVE_GENERATE_PROMPT.format(
            gate_reasoning=gate_reasoning,
            user_profile=user_profile or "暂无画像",
            current_context=current_context,
        )
        try:
            result = await self._llm_structured(prompt, NotificationDraft)
            return result
        except Exception as e:
            logger.debug(f"Generate 调用失败: {e}")
            return None

    # ━━━━━━━━━━━━ Step 3: Critic ━━━━━━━━━━━━

    async def _step_critic(
        self,
        notification_text: str,
        draft_reasoning: str,
    ) -> Optional[CriticResult]:
        """Critic: 最后一道关卡。"""
        prompt = PROACTIVE_CRITIC_PROMPT.format(
            notification_text=notification_text,
            draft_reasoning=draft_reasoning,
        )
        try:
            result = await self._llm_structured(prompt, CriticResult, cheap=True)
            return result
        except Exception as e:
            logger.debug(f"Critic 调用失败: {e}")
            return None

    # ━━━━━━━━━━━━ LLM 调用 ━━━━━━━━━━━━

    async def _llm_structured(self, prompt: str, model_class: type, cheap: bool = False) -> Any:
        """调用 LLM 并解析为 Pydantic 模型。
        
        Args:
            cheap: True 时使用最便宜模型 (g4f)，适用于 Gate 步骤节省 token
        """
        # 根据用途选择模型: Gate 步骤用最便宜模型，Generate/Critic 用 qwen
        model = os.environ.get("PROACTIVE_MODEL", FAMILY_G4F if cheap else FAMILY_QWEN)
        max_tok = 100 if cheap else 300
        
        try:
            from src.structured_llm import structured_completion
            result = await structured_completion(
                model_class=model_class,
                system_prompt=SOUL_CORE,
                user_prompt=prompt,
                model_family=model,
            )
            return result
        except ImportError:
            pass

        # 降级: 用 free_pool + json_repair
        try:
            from src.litellm_router import free_pool
            import json_repair

            if not free_pool:
                return None

            async with api_limiter("llm"):
                resp = await free_pool.acompletion(
                    model_family=model,
                    messages=[
                        {"role": "system", "content": SOUL_CORE},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=max_tok,
                )
            text = resp.choices[0].message.content or ""
            data = json_repair.loads(text)
            return model_class(**data)
        except Exception as e:
            logger.debug(f"LLM structured 降级失败: {e}")
            return None

    # ━━━━━━━━━━━━ 频率控制 ━━━━━━━━━━━━

    def _is_rate_limited(self, user_id: str) -> bool:
        """检查是否超过频率限制 (每小时 N 条)。"""
        now = time.time()
        cutoff = now - 3600  # 1 小时

        timestamps = self._sent_log.get(user_id, [])
        # 清理过期记录
        timestamps = [t for t in timestamps if t > cutoff]
        self._sent_log[user_id] = timestamps

        return len(timestamps) >= MAX_NOTIFICATIONS_PER_HOUR

    def _record_sent(self, user_id: str, text: str):
        """记录已发送的通知。"""
        now = time.time()
        self._sent_log.setdefault(user_id, []).append(now)

        recent = self._recent_notifications.setdefault(user_id, [])
        recent.append(text)
        # 只保留最近 10 条
        if len(recent) > 10:
            self._recent_notifications[user_id] = recent[-10:]

    def _get_recent_notifications(self, user_id: str) -> str:
        """获取最近通知文本 (供去重)。"""
        recent = self._recent_notifications.get(user_id, [])
        if not recent:
            return ""
        return "\n".join(f"- {text}" for text in recent[-5:])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  单例
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_engine: Optional[ProactiveEngine] = None


def get_proactive_engine() -> ProactiveEngine:
    """获取全局 ProactiveEngine 实例。"""
    global _engine
    if _engine is None:
        _engine = ProactiveEngine()
    return _engine
