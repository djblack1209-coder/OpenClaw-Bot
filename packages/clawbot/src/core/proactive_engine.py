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

> 最后更新: 2026-03-25
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config.prompts import (
    PROACTIVE_GATE_PROMPT,
    PROACTIVE_GENERATE_PROMPT,
    PROACTIVE_CRITIC_PROMPT,
    SOUL_CORE,
)

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Pydantic 结构化输出模型 (搬运自 omi)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class GateResult(BaseModel):
    """Gate 判断结果 — 是否值得打扰严总"""
    is_relevant: bool = Field(
        default=False,
        description="True ONLY if there is a specific, concrete insight worth interrupting for",
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="0.85+: critical action needed; 0.70-0.84: non-obvious insight; below: skip",
    )
    reasoning: str = Field(
        default="",
        description="具体原因，必须引用具体数据点",
    )


class NotificationDraft(BaseModel):
    """通知草稿"""
    notification_text: str = Field(
        default="",
        description="通知文本, 100字以内, 像朋友发微信",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
    )
    category: str = Field(
        default="info",
        description="money/risk/opportunity/reminder",
    )


class CriticResult(BaseModel):
    """Critic 审查结果"""
    approved: bool = Field(
        default=False,
        description="True ONLY if you would genuinely want to receive this notification",
    )
    reasoning: str = Field(default="")


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
                del self._sent_log[uid]
        for uid in list(self._recent_notifications):
            if uid not in self._sent_log:
                del self._recent_notifications[uid]

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

        # 记录已发送
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
        model = os.environ.get("PROACTIVE_MODEL", "g4f" if cheap else "qwen")
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

            try:
                from src.resilience import api_limiter
            except ImportError:
                from contextlib import asynccontextmanager

                @asynccontextmanager
                async def api_limiter(service: str = "generic"):
                    yield

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
#  EventBus 集成 — 监听事件触发主动通知
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def setup_proactive_listeners(engine: "ProactiveEngine"):
    """注册 EventBus 监听器，在关键事件发生时触发主动通知评估。

    应在 multi_main.py 启动阶段调用。
    """
    try:
        from src.core.event_bus import get_event_bus, EventType
        bus = get_event_bus()

        async def on_trade_executed(event_data: Dict[str, Any]):
            """交易成交后评估是否需要通知其他关联信息。"""
            try:
                user_id = str(event_data.get("user_id", ""))
                symbol = event_data.get("symbol", "")
                action = event_data.get("action", "")
                context = f"严总刚刚 {action} 了 {symbol}。交易详情: {event_data}"

                notification = await engine.evaluate(
                    context_type="cross_domain",
                    current_context=context,
                    user_id=user_id,
                )
                if notification:
                    await _send_proactive(user_id, notification)
            except Exception as e:
                logger.debug(f"交易后主动通知评估失败: {e}")

        async def on_risk_alert(event_data: Dict[str, Any]):
            """风控预警触发主动通知。"""
            try:
                user_id = str(event_data.get("user_id", ""))
                context = f"风控预警: {event_data}"

                notification = await engine.evaluate(
                    context_type="risk_warning",
                    current_context=context,
                    user_id=user_id,
                )
                if notification:
                    await _send_proactive(user_id, notification)
            except Exception as e:
                logger.debug(f"风控主动通知评估失败: {e}")

        # 注册监听器
        if hasattr(EventType, "TRADE_EXECUTED"):
            await bus.subscribe(EventType.TRADE_EXECUTED, on_trade_executed)
        if hasattr(EventType, "RISK_ALERT"):
            await bus.subscribe(EventType.RISK_ALERT, on_risk_alert)

        # 自选股异动 → 情报级主动推送（新闻+K线图+RSI+持仓浮盈）
        async def on_watchlist_anomaly(event_data: Dict[str, Any]):
            """自选股异动触发富文本通知（v2.0: 从纯文本升级为情报卡片）。

            通知格式:
              ⚡ NVDA 暴涨 +5.2% | $135.80
              ━━━━━━━━━━━━━━━
              📰 可能原因: Nvidia发布新一代Blackwell芯片
              📊 RSI: 72.3 (超买区域)
              💰 你持有 100股，浮盈 +$520
              [附: 5日1小时K线图]
            """
            try:
                from src.bot.globals import ALLOWED_USER_IDS

                symbol = event_data.get("symbol", "")
                anomaly_type = event_data.get("anomaly_type", "")
                details = event_data.get("details", "")
                change_pct = event_data.get("change_pct", 0)
                price = event_data.get("price", 0)

                # 增强数据（由 watchlist_monitor._enrich_anomalies 注入）
                news_title = event_data.get("news_title", "")
                chart_png = event_data.get("chart_png", b"")
                rsi_value = event_data.get("rsi_value")
                holding_qty = event_data.get("holding_qty", 0)
                holding_avg_price = event_data.get("holding_avg_price", 0)

                # ── 构建情报卡片 ──
                # 标题行: 根据异动类型选择图标
                _type_emoji = {
                    "price_surge": "⚡",
                    "volume_surge": "📊",
                    "rsi_extreme": "📈",
                    "target_hit": "🎯",
                    "stoploss_hit": "⚠️",
                }
                emoji = _type_emoji.get(anomaly_type, "⚡")

                # 涨跌方向
                if anomaly_type == "price_surge":
                    direction = "暴涨" if change_pct > 0 else "暴跌"
                    headline = (
                        f"{emoji} <b>{symbol} {direction} "
                        f"{change_pct:+.1f}%</b> | ${price:.2f}"
                    )
                else:
                    # 非价格异动用原始 details 做标题
                    headline = f"{emoji} <b>{details}</b>"

                lines = [headline, "━━━━━━━━━━━━━━━"]

                # 新闻原因
                if news_title:
                    # 截断过长标题
                    title_display = (
                        news_title[:60] + "..." if len(news_title) > 60
                        else news_title
                    )
                    lines.append(f"📰 可能原因: {title_display}")

                # RSI 指标
                if rsi_value is not None:
                    if rsi_value > 70:
                        zone = " (超买区域)"
                    elif rsi_value < 30:
                        zone = " (超卖区域)"
                    else:
                        zone = ""
                    lines.append(f"📊 RSI: {rsi_value:.1f}{zone}")

                # 持仓浮盈
                if holding_qty > 0 and holding_avg_price > 0:
                    pnl = (price - holding_avg_price) * holding_qty
                    pnl_label = "浮盈" if pnl >= 0 else "浮亏"
                    lines.append(
                        f"💰 你持有 {holding_qty}股，"
                        f"{pnl_label} {'+'if pnl >= 0 else ''}"
                        f"${abs(pnl):,.0f}"
                    )

                alert_text = "\n".join(lines)

                # ── 确定通知目标（用第一个管理员 ID）──
                target_id = ""
                if ALLOWED_USER_IDS:
                    target_id = str(list(ALLOWED_USER_IDS)[0])
                if not target_id:
                    return  # 无接收者，跳过

                # ── 有图发图，无图发文 ──
                if chart_png:
                    await _send_proactive_photo(
                        target_id, chart_png, alert_text
                    )
                else:
                    await _send_proactive(target_id, alert_text)

                logger.info(
                    f"📡 异动情报已推送: {symbol} ({anomaly_type})"
                )

            except Exception as e:
                logger.debug(f"自选股异动通知失败: {e}")

        if hasattr(EventType, "WATCHLIST_ANOMALY"):
            await bus.subscribe(EventType.WATCHLIST_ANOMALY, on_watchlist_anomaly)

        # 任务闭环跟踪 — 搬运 Apple Reminders / Todoist 定时回看模式
        # 投资类任务执行完后，延迟 2 小时检查结果变化并主动推送
        async def on_task_completed(event_data: Dict[str, Any]):
            """任务完成后延迟回访 — 让 Bot 在时间轴上有延续性。"""
            try:
                task_type = event_data.get("goal", "")
                task_data = event_data.get("final_result", {})

                # 只对投资类任务做延迟回访（交易/分析/回测）
                _invest_keywords = ("investment", "trading", "backtest", "分析", "买入", "卖出")
                is_invest = any(kw in str(task_type).lower() for kw in _invest_keywords)
                if not is_invest:
                    return

                # 提取标的代码
                symbol = ""
                if isinstance(task_data, dict):
                    symbol = task_data.get("symbol", "")
                    if not symbol:
                        # 尝试从嵌套结果中提取
                        for v in task_data.values():
                            if isinstance(v, dict) and v.get("symbol"):
                                symbol = v["symbol"]
                                break
                if not symbol:
                    return

                # 延迟 2 小时后检查
                async def _delayed_followup():
                    await asyncio.sleep(7200)  # 2 小时
                    try:
                        from src.invest_tools import get_stock_quote
                        quote = await get_stock_quote(symbol)
                        if not quote or not quote.get("price"):
                            return
                        change_pct = quote.get("change_pct", 0)
                        price = quote.get("price", 0)

                        followup_context = (
                            f"2小时前严总执行了'{task_type}'相关任务，标的 {symbol}。"
                            f"当前 {symbol} 价格 ${price:.2f}，涨跌幅 {change_pct:+.1f}%。"
                            f"根据变化情况，判断是否值得通知严总。"
                        )
                        notification = await engine.evaluate(
                            context_type="task_followup",
                            current_context=followup_context,
                            user_id="default",
                        )
                        if notification:
                            await _send_proactive("default", notification)
                    except Exception as e:
                        logger.debug(f"任务闭环回访异常: {e}")

                _followup_t = asyncio.create_task(_delayed_followup())
                _followup_t.add_done_callback(lambda t: t.exception() and logger.debug("延迟回访后台任务异常: %s", t.exception()))
            except Exception as e:
                logger.debug(f"任务完成监听异常: {e}")

        if hasattr(EventType, "TASK_COMPLETED"):
            await bus.subscribe(EventType.TASK_COMPLETED, on_task_completed)

        # 流式进度反馈 — 搬运 Claude artifact 流式 / ChatGPT 思考过程
        # 多步任务每完成一步实时推送进度到用户
        async def on_brain_progress(event_data: Dict[str, Any]):
            """任务图执行进度 → 实时推送到用户。"""
            try:
                step = event_data.get("step", 0)
                total = event_data.get("total", 0)
                name = event_data.get("name", "")
                status = event_data.get("status", "")

                # 只在多步任务（>1步）时推送，避免单步任务刷屏
                if total <= 1:
                    return

                if status == "running":
                    emoji = "🔄"
                    text = f"{emoji} 进度 {step}/{total} — 正在执行: {name}"
                else:
                    return  # 只推送"正在执行"状态

                await _send_proactive("default", text)
            except Exception as e:
                logger.debug(f"进度推送异常: {e}")

        await bus.subscribe("brain.progress", on_brain_progress)

        logger.info("主动智能引擎已注册 EventBus 监听器")
    except Exception as e:
        logger.debug(f"EventBus 监听器注册失败 (非致命): {e}")


async def _send_proactive(user_id: str, text: str):
    """通过 Telegram 发送主动通知。"""
    try:
        from src.bot.globals import bot_registry
        bots = bot_registry
        if not bots:
            return

        # 用第一个可用 bot 发送
        bot = next(iter(bots.values()), None)
        if bot and hasattr(bot, "application"):
            admin_chat_id = int(user_id) if user_id.isdigit() else None
            if admin_chat_id:
                await bot.application.bot.send_message(
                    chat_id=admin_chat_id,
                    text=f"💡 {text}",
                )
    except Exception as e:
        logger.debug(f"主动通知发送失败: {e}")


async def _send_proactive_photo(user_id: str, photo_bytes: bytes, caption: str):
    """通过 Telegram 发送带图主动通知（异动K线图等）。

    降级: 图片发送失败时自动降级为纯文本通知。
    """
    try:
        import io as _io
        from src.bot.globals import bot_registry
        bots = bot_registry
        if not bots:
            return

        bot = next(iter(bots.values()), None)
        if bot and hasattr(bot, "application"):
            admin_chat_id = int(user_id) if user_id.isdigit() else None
            if admin_chat_id:
                buf = _io.BytesIO(photo_bytes)
                buf.name = "anomaly_chart.png"
                await bot.application.bot.send_photo(
                    chat_id=admin_chat_id,
                    photo=buf,
                    caption=caption,
                    parse_mode="HTML",
                )
    except Exception as e:
        logger.debug(f"主动图表通知发送失败: {e}, 降级到纯文本")
        # 降级到纯文本
        await _send_proactive(user_id, caption)


def _safe_parse_time(iso_str: str):
    """安全解析 ISO 时间字符串"""
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None


async def periodic_proactive_check(engine: "ProactiveEngine"):
    """定时主动检查 — 收集系统上下文，评估是否值得主动推送。

    由 multi_main.py 主循环每 30 分钟调用一次。
    """
    try:
        from src.bot.globals import bot_registry, ALLOWED_USER_IDS

        if not bot_registry:
            return

        # 收集系统上下文
        context_parts = []

        # 1. 持仓状态
        try:
            from src.invest_tools import get_portfolio_summary
            portfolio = get_portfolio_summary()
            if portfolio:
                context_parts.append(f"当前持仓: {portfolio}")
        except Exception as e:
            logger.debug(f"[Proactive] 持仓数据获取失败: {e}")

        # 2. 未读闲鱼消息
        try:
            from src.xianyu.xianyu_live import get_unread_count
            unread = get_unread_count()
            if unread and unread > 0:
                context_parts.append(f"闲鱼未读消息: {unread} 条")
        except Exception as e:
            logger.debug(f"[Proactive] 闲鱼未读获取失败: {e}")

        # 3. 今日交易汇总
        try:
            from src.trading_journal import TradingJournal
            journal = TradingJournal()
            today_trades = journal.get_today_trades()
            if today_trades:
                context_parts.append(f"今日交易: {len(today_trades)} 笔")
            journal.close()
        except Exception as e:
            logger.debug(f"[Proactive] 交易汇总获取失败: {e}")

        # 4. 今日待触发提醒
        try:
            from src.execution.life_automation import list_reminders
            pending = list_reminders(status="pending")
            if pending:
                from datetime import datetime as _dt
                _now = _dt.now()
                _today_end = _now.replace(hour=23, minute=59, second=59)
                today_count = sum(
                    1 for r in pending
                    if _safe_parse_time(r.get("remind_at", "")) and
                    _safe_parse_time(r.get("remind_at", "")) <= _today_end
                )
                if today_count > 0:
                    context_parts.append(f"今日待提醒: {today_count} 条")
                    # 列出最近的 2 条
                    for r in pending[:2]:
                        context_parts.append(f"  → {r.get('message', '')[:50]}")
        except Exception as e:
            logger.debug(f"[Proactive] 待提醒获取失败: {e}")

        # 5. 持仓盈亏警报 (接近止盈/止损)
        try:
            from src.risk_manager import RiskManager
            rm = RiskManager()
            alerts = rm.check_position_alerts() if hasattr(rm, 'check_position_alerts') else []
            for alert in (alerts or [])[:2]:
                context_parts.append(f"持仓警报: {alert}")
        except Exception as e:
            logger.debug(f"[Proactive] 持仓警报获取失败: {e}")

        # 6. 关注股票大幅变动 (>3%)
        try:
            from src.invest_tools import get_quick_quotes
            try:
                from src.watchlist import get_watchlist_symbols
                wl = get_watchlist_symbols()
            except Exception:
                wl = []
            if wl:
                quotes = await get_quick_quotes(wl[:5])
                for sym, data in (quotes or {}).items():
                    change = data.get("change_pct", 0)
                    if abs(change) >= 3.0:
                        direction = "大涨" if change > 0 else "大跌"
                        context_parts.append(
                            f"关注股票{direction}: {sym} {change:+.1f}% (${data.get('price', 0):,.2f})"
                        )
        except Exception as e:
            logger.debug(f"[Proactive] 关注股票获取失败: {e}")

        # 7. 重复提醒统计
        try:
            from src.execution.life_automation import list_reminders
            all_pending = list_reminders(status="pending")
            recurring = [r for r in (all_pending or []) if r.get("recurrence_rule")]
            if len(recurring) > 0:
                context_parts.append(f"活跃重复提醒: {len(recurring)} 个")
        except Exception as e:
            logger.debug(f"[Proactive] 重复提醒统计失败: {e}")

        # 8. 闲鱼最近成交 (跨域关联: 成交→有闲钱→投资机会)
        try:
            from src.xianyu.xianyu_live import get_recent_sales
            sales = get_recent_sales(hours=24) if callable(getattr(get_recent_sales, '__call__', None)) else []
            if sales:
                total = sum(s.get("price", 0) for s in sales)
                if total > 0:
                    context_parts.append(f"闲鱼24h成交: ¥{total:.0f} ({len(sales)}笔)")
        except Exception as e:
            logger.debug(f"[Proactive] 闲鱼成交获取失败: {e}")

        # 9. 使用行为洞察 — 搬运 Spotify Wrapped / Apple 屏幕使用时间洞察模式
        # 从历史消息中检测行为模式，生成主动建议
        try:
            from src.bot.globals import get_history_store
            _hs = get_history_store()
            if _hs:
                # 获取最近 100 条用户消息，提取频繁操作模式
                _any_bot = next(iter(bot_registry.keys()), "")
                _admin = admin_ids[0] if admin_ids else 0
                if _any_bot and _admin:
                    recent = _hs.get_messages(_any_bot, int(_admin), limit=100)
                    user_msgs = [m.get("content", "") for m in (recent or []) if m.get("role") == "user"]
                    if user_msgs:
                        # 统计频繁提及的标的
                        import re as _re
                        _ticker_counts: Dict[str, int] = {}
                        for msg in user_msgs:
                            tickers = _re.findall(r'\b([A-Z]{2,5})\b', msg)
                            _skip = {'AI', 'ETF', 'RSI', 'MACD', 'OK', 'VS', 'API', 'BOT', 'LLM'}
                            for t in tickers:
                                if t not in _skip:
                                    _ticker_counts[t] = _ticker_counts.get(t, 0) + 1
                        # 找频繁提及但不在 watchlist 的标的
                        if _ticker_counts:
                            from src.watchlist import get_watchlist_symbols
                            wl_syms = set(get_watchlist_symbols())
                            frequent_not_in_wl = [
                                (sym, cnt) for sym, cnt in sorted(
                                    _ticker_counts.items(), key=lambda x: -x[1]
                                )
                                if cnt >= 3 and sym not in wl_syms
                            ]
                            if frequent_not_in_wl:
                                top = frequent_not_in_wl[0]
                                context_parts.append(
                                    f"行为洞察: 你最近频繁提及 {top[0]}（{top[1]}次），但它不在自选股里，要加入吗？"
                                )
        except Exception as e:
            logger.debug(f"[Proactive] 行为洞察失败: {e}")

        if not context_parts:
            logger.debug("[Proactive] 定时检查: 无有价值上下文，跳过")
            return

        context = "定时系统状态检查:\n" + "\n".join(f"- {p}" for p in context_parts)

        # 获取用户画像
        user_profile = ""
        try:
            from src.bot.globals import tiered_context_manager as _tcm
            if _tcm:
                user_profile = _tcm.core_get("user_profile")
        except Exception as e:
            logger.debug(f"[Proactive] 用户画像获取失败: {e}")

        # 对每个管理员用户评估
        admin_ids = ALLOWED_USER_IDS or []
        for uid in admin_ids[:3]:  # 最多3个管理员
            notification = await engine.evaluate(
                context_type="periodic_check",
                current_context=context,
                user_id=str(uid),
                user_profile=user_profile,
            )
            if notification:
                await _send_proactive(str(uid), notification)

    except Exception as e:
        logger.debug(f"[Proactive] 定时检查异常: {e}")


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
