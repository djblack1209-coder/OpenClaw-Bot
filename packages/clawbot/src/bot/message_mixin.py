# message_mixin.py — 消息处理 Mixin (文本/语音/图片/文档/回调)
# 搬运自 n3d1117/chatgpt-telegram-bot (3.5k⭐) 流式模式

import asyncio
import importlib.util
import io
import json
import logging
import re
import time as _time
from src.bot.globals import collab_orchestrator, bot_registry, send_long_message, get_stock_quote, execute_trade_via_pipeline, get_trading_pipeline
from src.bot.error_messages import error_ai_busy, error_rate_limit, error_network, error_auth, error_generic
from src.notify_style import format_digest
from src.telegram_markdown import md_to_html
from src.bot.chinese_nlp_mixin import _match_chinese_command
logger = logging.getLogger(__name__)

# ── v3.0: 智能行动建议 — LLM回复后自动附加下一步按钮 ─────────
# 让 AI 不只给文字，还给"下一步能做什么"
# 搬运灵感: ChatGPT Suggested Actions / Google Gemini Quick Actions


def _detect_correction(text: str) -> bool:
    """检测用户是否在纠正上一轮的回复 — 搬运 ChatGPT correction handling 模式

    检测信号词: "不对/说错了/搞错了/纠正/你记错了/不是X是Y"
    返回 True 表示这条消息是纠正指令，需要特殊处理。
    """
    if not text or len(text) < 2:
        return False
    _CORRECTION_PATTERNS = [
        r"^(?:不对|错了|说错了|搞错了|弄错了|你[搞说弄]错了|你记错了)",
        r"(?:不是.*(?:是|而是|应该是))",
        r"^(?:纠正|更正|我说的是|我的意思是|我是说)",
        r"^(?:重新(?:来|说|分析|查))",
    ]
    for pattern in _CORRECTION_PATTERNS:
        if re.search(pattern, text.strip()):
            return True
    return False

def _build_smart_reply_keyboard(response_text: str, bot_id: str, model_used: str, chat_id: int, ai_suggestions: list = None):
    """分析 LLM 回复内容，生成上下文相关的行动按钮

    规则:
    1. 如果有 AI 生成的追问建议，优先显示在最前面
    2. 检测回复中提到的股票代码 → 技术分析/报价按钮
    3. 检测交易关键词 → 买入/卖出/止损按钮
    4. 检测商品/购物关键词 → 比价按钮
    5. 始终保留反馈按钮 (👍👎🔄)
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from src.feedback import build_feedback_keyboard

    text = (response_text or "").lower()
    action_buttons = []
    suggest_row = []  # AI 追问建议独立一行

    # 0. AI 追问建议按钮（智能追问引擎生成）
    if ai_suggestions:
        for suggestion in ai_suggestions[:3]:
            # Telegram callback_data 限制 64 字节
            # 中文 UTF-8 每字符 3 字节，截断到 ~18 字符确保安全
            cb_text = suggestion[:18]
            cb_data = f"suggest:{cb_text}"
            # 二次检查: callback_data 编码后不超过 64 字节
            if len(cb_data.encode("utf-8")) > 64:
                cb_data = f"suggest:{suggestion[:12]}"
            suggest_row.append(
                InlineKeyboardButton(f"💬 {suggestion[:15]}", callback_data=cb_data)
            )

    # 1. 检测股票代码 (英文ticker)
    tickers_found = re.findall(r'\b([A-Z]{1,5})\b', response_text)
    # 过滤掉常见非ticker词
    skip_words = {'AI', 'ETF', 'RSI', 'MACD', 'KDJ', 'EMA', 'SMA', 'ATR', 'VWAP',
                  'API', 'USD', 'BTC', 'OK', 'VS', 'PDF', 'URL', 'VIA', 'BOT', 'LLM',
                  'HTML', 'CSS', 'SQL', 'NLP', 'RPC', 'SOP', 'ROI', 'PNL', 'IPO',
                  'CEO', 'CTO', 'GDP', 'CPI', 'FED', 'SEC', 'NYSE', 'PRO', 'MAX', 'MIN'}
    valid_tickers = [t for t in tickers_found if t not in skip_words and len(t) >= 2]

    if valid_tickers:
        ticker = valid_tickers[0]  # 取第一个
        action_buttons.append(
            InlineKeyboardButton(f"📊 分析{ticker}", callback_data=f"ta_{ticker}")
        )
        if any(kw in text for kw in ['买入', '建仓', '加仓', '推荐买', '可以买', '值得买', 'buy']):
            action_buttons.append(
                InlineKeyboardButton(f"💰 买入{ticker}", callback_data=f"buy_{ticker}")
            )
        elif any(kw in text for kw in ['卖出', '减仓', '止盈', '清仓', '平仓', 'sell']):
            action_buttons.append(
                InlineKeyboardButton(f"📉 卖出{ticker}", callback_data=f"cmd:sell {ticker}")
            )
        else:
            action_buttons.append(
                InlineKeyboardButton(f"💹 报价{ticker}", callback_data=f"cmd:quote {ticker}")
            )

    # 2. 检测持仓/投资主题 (无特定ticker时)
    if not action_buttons and any(kw in text for kw in ['持仓', '仓位', '组合', '盈亏', '浮盈', '浮亏']):
        action_buttons.append(
            InlineKeyboardButton("📋 查看持仓", callback_data="cmd:portfolio")
        )
        action_buttons.append(
            InlineKeyboardButton("📊 查看绩效", callback_data="cmd:performance")
        )

    # 3. 检测市场/行情主题
    if not action_buttons and any(kw in text for kw in ['大盘', '市场', '指数', '行情', '美股', 'a股']):
        action_buttons.append(
            InlineKeyboardButton("💹 市场概览", callback_data="cmd:market")
        )
        action_buttons.append(
            InlineKeyboardButton("📰 今日简报", callback_data="cmd:brief")
        )

    # 4. 检测购物/商品主题
    if not action_buttons and any(kw in text for kw in ['价格', '元', '优惠', '打折', '推荐', '购买',
                                                         '京东', '淘宝', '拼多多', '亚马逊']):
        # 尝试提取商品名
        product_match = re.search(r'([\w\-]+\s*(?:Pro|Max|Plus|Ultra)?)', response_text)
        if product_match and len(product_match.group(1)) > 2:
            product = product_match.group(1).strip()[:20]
            action_buttons.append(
                InlineKeyboardButton(f"🛒 比价{product}", callback_data=f"shop:{product}")
            )

    # 4.5 中文商品名检测 (补充英文正则覆盖不到的场景)
    cn_product_match = re.search(
        r'(?:买|推荐|比价|搜|找)\s*(?:一[个台只双部条])?'
        r'([\u4e00-\u9fff]{2,8}(?:Pro|Max|Plus|Ultra|mini)?)',
        response_text,
    )
    if cn_product_match and not action_buttons:
        product = cn_product_match.group(1)
        action_buttons.append(
            InlineKeyboardButton(f"🛒 比价 {product}", callback_data=f"shop:{product}")
        )

    # 5. 检测社媒主题
    if not action_buttons and any(kw in text for kw in ['发文', '小红书', '推特', '热点', '社媒', '内容']):
        action_buttons.append(
            InlineKeyboardButton("🔥 热点发文", callback_data="cmd:hotpost")
        )
        action_buttons.append(
            InlineKeyboardButton("📱 社媒计划", callback_data="cmd:social_plan")
        )

    # 通用聊天: 无特定领域按钮时，展示能力发现按钮（替代无用的"继续聊"）
    # 搬运灵感: ChatGPT 首页的 suggested prompts / Google Gemini 推荐操作
    if not action_buttons:
        _capability_buttons = [
            InlineKeyboardButton("📊 分析股票", callback_data="suggest:帮我分析一只股票"),
            InlineKeyboardButton("🛒 比价购物", callback_data="suggest:帮我比价一个商品"),
            InlineKeyboardButton("📱 社媒发文", callback_data="suggest:帮我写一篇小红书"),
        ]
        action_buttons.extend(_capability_buttons[:2])  # 最多展示2个

    # 组装键盘: AI建议行(如有) + 行动按钮(最多3个) + 反馈按钮
    rows = []
    if suggest_row:
        rows.append(suggest_row[:3])  # AI 追问建议放最前
    if action_buttons:
        rows.append(action_buttons[:3])  # 最多3个行动按钮

    # 反馈行 (简化)
    fb_keyboard = build_feedback_keyboard(bot_id, model_used, chat_id)
    rows.extend(fb_keyboard.inline_keyboard)

    return InlineKeyboardMarkup(rows)

from src.bot.workflow_mixin import WorkflowMixin
from src.bot.callback_mixin import CallbackMixin


class MessageHandlerMixin(WorkflowMixin, CallbackMixin):
    async def handle_message(self, update, context):
        """处理文本消息 — 流式输出到 Telegram
        
        搬运自 n3d1117/chatgpt-telegram-bot (3.5k⭐) 的流式模式:
        - 发送占位消息 → 流式编辑 → 最终消息
        - 自适应编辑频率（群聊更保守，私聊更激进）
        - Markdown 降级（流式中 Markdown 可能断裂）
        - RetryAfter 退避
        """
        from telegram import constants
        from telegram.error import BadRequest, RetryAfter, TimedOut
        from src.smart_memory import get_smart_memory
        from src.feedback import build_feedback_keyboard

        TG_MSG_LIMIT = 4096
        # ── HI-011 flood 根治: 时间门控 + 编辑次数上限 ──
        # Telegram 群聊 editMessageText 限制约 20次/分钟
        EDIT_INTERVAL_GROUP = 3.0     # 群聊: 每条消息最少间隔 3 秒
        EDIT_INTERVAL_PRIVATE = 1.0   # 私聊: 每条消息最少间隔 1 秒
        MAX_EDITS_GROUP = 15          # 群聊: 单条消息最多编辑 15 次
        MAX_EDITS_PRIVATE = 30        # 私聊: 单条消息最多编辑 30 次

        chat_id = update.effective_chat.id
        user = update.effective_user
        text = (update.message.text or "").strip()
        if not text:
            return

        chat_type = update.effective_chat.type
        is_group = chat_type in ("group", "supergroup")

        if not self._is_authorized(user.id):
            return

        # ── 会话恢复问候 — 搬运 Apple Intelligence 摘要 / Slack Catch Up ──
        # 用户超过 4 小时没互动后回来，在首条回复前生成"离线期间发生了什么"摘要
        try:
            _session_gap_handled = await self._check_session_resumption(chat_id, user.id, update, context)
        except Exception as e:
            pass  # 会话恢复失败不影响主流程
            logger.debug("静默异常: %s", e)

        # ── 纠错检测 — 搬运 ChatGPT correction handling ──────
        # 用户说"不对/说错了/我说的是X不是Y"时，把上一轮上下文 + 纠正指令合并重新处理
        # 优先级高于追问路由（用户可能在纠正追问的前提）
        try:
            _correction = _detect_correction(text)
            if _correction:
                await update.message.chat.send_action("typing")
                # 从历史获取上一轮对话，作为纠正上下文
                _prev_context = ""
                try:
                    from src.history_store import get_history_store
                    _hs = get_history_store()
                    if _hs:
                        _recent = _hs.get_messages(self.bot_id, chat_id, limit=2)
                        if _recent:
                            _prev_context = " | ".join(
                                m.get("content", "")[:200] for m in _recent
                            )
                except Exception as e:
                    pass
                    logger.debug("静默异常: %s", e)
                # 拼接纠正上下文到消息，让 LLM/Brain 理解这是纠正
                _corrected_msg = f"[纠正上一条] {text}"
                if _prev_context:
                    _corrected_msg += f"\n[上轮上下文] {_prev_context[:300]}"
                # 替换 text 继续走正常路由
                text = _corrected_msg
                # 发送确认
                from src.bot.error_messages import correction_ack
                await update.message.reply_text(correction_ack())
        except Exception as e:
            pass  # 纠错检测失败不影响主流程
            logger.debug("静默异常: %s", e)

        # ── Brain 追问回答路由 ──────────────────────────────
        # 如果上一条消息是 Brain 的追问（如"请问要分析哪只股票？"），
        # 本条消息作为回答路由回 Brain，而不是当作新消息处理。
        try:
            from src.core.brain import get_brain
            _brain = get_brain()
            _clarify_task_id = _brain.get_pending_clarification(chat_id)
            if _clarify_task_id:
                await update.message.chat.send_action("typing")
                _clarify_result = await _brain.resume_with_answer(
                    _clarify_task_id, text,
                    {"user_id": user.id, "chat_id": chat_id, "bot_id": self.bot_id},
                )
                if _clarify_result.success and _clarify_result.final_result:
                    _clarify_msg = _clarify_result.to_user_message()
                    if _clarify_msg:
                        _clarify_markup = None
                        try:
                            _clarify_markup = _build_smart_reply_keyboard(
                                _clarify_msg, self.bot_id, getattr(self, 'model', ''), chat_id
                            )
                        except Exception as e:
                            pass
                            logger.debug("静默异常: %s", e)
                        try:
                            safe = md_to_html(_clarify_msg)
                            await update.message.reply_text(
                                safe, parse_mode="HTML", reply_markup=_clarify_markup,
                            )
                        except Exception as e:  # noqa: F841
                            await update.message.reply_text(
                                _clarify_msg, reply_markup=_clarify_markup,
                            )
                        return
                elif _clarify_result.error:
                    await update.message.reply_text(f"❌ {_clarify_result.error}")
                    return
                # 如果 result 既不 success 也不 error (罕见)，继续正常流程
        except Exception as _ce:
            logger.debug(f"Brain 追问路由失败: {_ce}")

        # 中文自然语言命令匹配 — 在 LLM 调用前拦截
        chinese_action = _match_chinese_command(text)
        if chinese_action:
            action_type, action_arg = chinese_action
            await update.effective_chat.send_action("typing")
            await self._dispatch_chinese_action(update, context, action_type, action_arg)
            # 记录命令上下文到对话历史 (修复跟进断裂)
            try:
                _sm = get_smart_memory()
                if _sm:
                    action_label = f"[命令:{action_type}] {text}"
                    _cmd_task = asyncio.create_task(
                        _sm.on_message(chat_id, user.id, "user", action_label, self.bot_id)
                    )
                    def _cmd_task_done(t):
                        if not t.cancelled() and t.exception():
                            logger.debug("[MessageMixin] 后台任务异常: %s", t.exception())
                    _cmd_task.add_done_callback(_cmd_task_done)
            except Exception as e:
                logger.debug("SmartMemory 命令记录失败", exc_info=True)
            return  # Chinese command handled, skip LLM call

        # ── Brain 路由 (v3.0: 默认启用) ──────────────────────────
        # 中文命令未匹配时，用 OMEGA brain.py 处理可执行请求。
        # v3.0: 默认启用。使用 _try_fast_parse()（纯正则，零 LLM/token 成本）。
        # 只有可执行意图才路由到 brain；闲聊仍走下方 LLM 流式路径。
        # 设置 ENABLE_BRAIN_ROUTING=0 可关闭。
        import os
        if os.environ.get("ENABLE_BRAIN_ROUTING", "1").lower() not in ("0", "false", "no", "off"):
            try:
                # GAP 5: Brain 路径 typing 指示器 — 用户不再看到死寂
                await update.message.chat.send_action("typing")

                from src.core.intent_parser import IntentParser
                _parser = IntentParser()
                quick_intent = _parser._try_fast_parse(text)
                # 降级: fast_parse 未命中时，用轻量 LLM 分类器再试一次
                if not quick_intent or not quick_intent.is_actionable:
                    try:
                        quick_intent = await _parser._try_llm_classify(text)
                    except Exception as e:  # noqa: F841
                        quick_intent = None
                if quick_intent and quick_intent.is_actionable:
                    from src.core.brain import get_brain
                    brain = get_brain()
                    result = await brain.process_message(
                        source="telegram",
                        message=text,
                        context={"user_id": user.id, "chat_id": chat_id, "bot_id": self.bot_id},
                        pre_parsed_intent=quick_intent,
                        skip_chat_fallback=True,
                    )
                    if result.success and result.final_result:
                        user_msg = result.to_user_message()
                        if user_msg and user_msg != "✅ 操作已完成":
                            # Brain 回复带智能操作按钮 + AI 追问建议
                            reply_markup = None
                            try:
                                # 从 Brain 结果中提取 AI 生成的追问建议
                                _ai_suggestions = result.extra_data.get("followup_suggestions", [])
                                reply_markup = _build_smart_reply_keyboard(
                                    user_msg, self.bot_id, getattr(self, 'model', ''), chat_id,
                                    ai_suggestions=_ai_suggestions,
                                )
                            except Exception as e:
                                pass
                                logger.debug("静默异常: %s", e)

                            try:
                                safe = md_to_html(user_msg)
                                await update.message.reply_text(
                                    safe, parse_mode="HTML",
                                    reply_markup=reply_markup,
                                )
                            except Exception as e:  # noqa: F841
                                await update.message.reply_text(
                                    user_msg,
                                    reply_markup=reply_markup,
                                )

                            # Gap 2 修复: Brain 路径也记录到 SmartMemory
                            try:
                                _sm = get_smart_memory()
                                if _sm:
                                    def _brain_mem_done(t):
                                        if not t.cancelled() and t.exception():
                                            logger.debug("[MessageMixin] 后台任务异常: %s", t.exception())
                                    _brain_t1 = asyncio.create_task(
                                        _sm.on_message(chat_id, user.id, "user", text, self.bot_id)
                                    )
                                    _brain_t1.add_done_callback(_brain_mem_done)
                                    _brain_t2 = asyncio.create_task(
                                        _sm.on_message(chat_id, user.id, "assistant", user_msg[:1500], self.bot_id)
                                    )
                                    _brain_t2.add_done_callback(_brain_mem_done)
                            except Exception as e:
                                logger.debug("Brain 路径 SmartMemory 写入失败", exc_info=True)

                            return
                    elif result.needs_clarification:
                        # Brain 需要追问 — 显示追问消息，等待用户下一条消息回答
                        clarify_text = result.to_user_message()
                        if clarify_text:
                            try:
                                safe = md_to_html(clarify_text)
                                await update.message.reply_text(safe, parse_mode="HTML")
                            except Exception as e:  # noqa: F841
                                await update.message.reply_text(clarify_text)
                            return
            except Exception as e:
                logger.debug(f"Brain routing failed, falling through to LLM: {e}")

        # ── 模糊输入智能引导 — 无法识别明确意图时提供快捷操作按钮 ──
        # 在 LLM 闲聊之前先发一组常用操作按钮，用户可以直接点击
        # 条件: Brain 路由启用 + 私聊 + 未被上方 return 拦截（说明意图不明确）
        if os.environ.get("ENABLE_BRAIN_ROUTING", "1").lower() not in ("0", "false", "no", "off") and not is_group:
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                # 基于系统活跃模块推荐常用操作
                _fuzzy_suggestions = [
                    ("📊 看持仓", "cmd:portfolio"),
                    ("📋 今日简报", "cmd:brief"),
                    ("📱 账单状态", "cmd:bill"),
                ]
                # 闲鱼模块可用时追加
                if importlib.util.find_spec("src.xianyu.xianyu_context"):
                    _fuzzy_suggestions.append(("🐟 闲鱼状态", "cmd:xianyu"))
                _fuzzy_rows = [
                    [InlineKeyboardButton(t, callback_data=cb)
                     for t, cb in _fuzzy_suggestions[:3]],
                ]
                if len(_fuzzy_suggestions) > 3:
                    _fuzzy_rows.append(
                        [InlineKeyboardButton(t, callback_data=cb)
                         for t, cb in _fuzzy_suggestions[3:]]
                    )
                await update.message.reply_text(
                    "我不太确定你想做什么，试试这些？👇\n\n"
                    "（或者直接告诉我更具体的需求）",
                    reply_markup=InlineKeyboardMarkup(_fuzzy_rows),
                )
            except Exception as e:
                logger.debug("模糊引导按钮发送失败", exc_info=True)

        # 消息频率限制 — 防止用户刷屏导致 API 过载
        from src.bot.globals import rate_limiter
        if rate_limiter:
            allowed, reason = rate_limiter.check(self.bot_id, "private" if not is_group else "group")
            if not allowed:
                logger.info("[%s] 消息频率限制: %s (user=%s)", self.name, reason, user.id)
                try:
                    await update.message.reply_text("⏳ 请稍等，消息发送过于频繁。")
                except Exception as e:
                    logger.debug("频率限制回复失败", exc_info=True)
                return

        # 群聊：检查是否应该回复
        if is_group:
            should, reason = await self._should_respond_async(
                text, chat_type, update.message.message_id, user.id
            )
            if not should:
                return

        # 优先级分类 — 关键消息（止损/风控/紧急）优先处理
        from src.bot.globals import priority_message_queue
        _msg_priority = None
        if priority_message_queue:
            try:
                _msg_priority = priority_message_queue.classify_priority(
                    text=text,
                    chat_id=chat_id,
                    user_id=user.id,
                    is_private=not is_group,
                    is_mentioned=not is_group,  # 私聊视为 mentioned
                )
                # 入队追踪（不阻塞处理，仅用于统计和优先级感知）
                from src.chat_router import PrioritizedMessage
                import time as _ptime
                await priority_message_queue.enqueue(PrioritizedMessage(
                    priority=_msg_priority.value,
                    timestamp=_ptime.time(),
                    chat_id=chat_id,
                    user_id=user.id,
                    text=text[:200],
                    bot_id=getattr(self, 'bot_id', ''),
                ))
            except Exception as e:
                logger.debug("Silenced exception", exc_info=True)  # 优先级队列不影响主流程

        # 智能记忆管道 — 记录用户消息（异步，不阻塞）
        _sm = get_smart_memory()
        if _sm:
            _t = asyncio.create_task(_sm.on_message(chat_id, user.id, "user", text, self.bot_id))
            _t.add_done_callback(lambda t: t.exception() and logger.debug("智能记忆(用户消息)后台任务异常: %s", t.exception()))

        # 发送 typing 指示器
        typing_task = asyncio.create_task(self._keep_typing(chat_id, context))
        typing_task.add_done_callback(lambda t: t.exception() and logger.debug("typing指示器后台任务异常: %s", t.exception()))

        try:
            sent_message = None
            prev_text = ""
            backoff_multiplier = 1.0   # HI-011: 指数退避乘数
            chunk_idx = 0
            final_content = ""
            model_used = getattr(self, 'model', 'unknown') or 'unknown'
            edit_interval = EDIT_INTERVAL_GROUP if is_group else EDIT_INTERVAL_PRIVATE
            max_edits = MAX_EDITS_GROUP if is_group else MAX_EDITS_PRIVATE
            last_edit_time = 0.0       # HI-011: 上次编辑时间 (monotonic)

            # Phase 1: "思考中" 占位符（搬运自 karfly/chatgpt_telegram_bot）
            sent_message = await update.message.reply_text(
                "🤔 思考中...",
                reply_to_message_id=update.message.message_id if is_group else None,
            )

            # P0-B: 思考动画 — 让等待不再死寂
            _thinking_phases = ["🔍 搜索中...", "🧠 分析中...", "✍️ 撰写中..."]
            _thinking_active = True

            async def _animate_thinking():
                """后台循环更新思考占位符，每3秒切换一个阶段"""
                try:
                    phase_idx = 0
                    while _thinking_active:
                        await asyncio.sleep(3.0)
                        if not _thinking_active:
                            break
                        phase_idx = min(phase_idx + 1, len(_thinking_phases) - 1)
                        try:
                            await sent_message.edit_text(_thinking_phases[phase_idx])
                        except Exception as e:  # noqa: F841
                            break
                except asyncio.CancelledError as e:  # noqa: F841
                    pass

            _thinking_task = asyncio.create_task(_animate_thinking())

            async for content, status in self._call_api_stream(
                chat_id, text, save_history=True, chat_type=chat_type
            ):
                if not content:
                    continue
                final_content = content

                # Telegram 消息长度限制 — 超长时分割发送
                if len(content) > TG_MSG_LIMIT:
                    if sent_message and prev_text:
                        try:
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=sent_message.message_id,
                                text=prev_text[:TG_MSG_LIMIT],
                            )
                        except BadRequest as e:  # noqa: F841
                            pass
                    # P1-A: 溢出分段保留格式化渲染
                    remaining = content[TG_MSG_LIMIT:]
                    while remaining:
                        chunk = remaining[:TG_MSG_LIMIT]
                        remaining = remaining[TG_MSG_LIMIT:]
                        try:
                            safe_chunk = md_to_html(chunk)
                            sent_message = await update.message.reply_text(
                                safe_chunk, parse_mode="HTML"
                            )
                        except Exception as e:
                            try:
                                sent_message = await update.message.reply_text(chunk)
                            except Exception as e:
                                logger.warning(f"[{self.bot_id}] 发送溢出消息失败: {e}")
                                break
                        prev_text = chunk
                    continue

                cutoff = self._stream_cutoff(is_group, content)

                if chunk_idx == 0:
                    # P0-B: 首个 token 到达，停止思考动画
                    _thinking_active = False
                    _thinking_task.cancel()
                    # Phase 2: 首个 token — 替换"思考中"为实际内容
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=content + " ▌",
                        )
                        prev_text = content
                        last_edit_time = _time.monotonic()
                        chunk_idx += 1
                    except Exception as e:
                        logger.warning(f"[{self.bot_id}] 替换占位符失败: {e}")
                        break

                elif abs(len(content) - len(prev_text)) > cutoff or status == "finished":
                    if not sent_message:
                        break

                    # ── HI-011: 时间门控 + 编辑次数上限 ──
                    now = _time.monotonic()
                    effective_interval = edit_interval * backoff_multiplier
                    time_ok = (now - last_edit_time) >= effective_interval
                    under_cap = chunk_idx < max_edits

                    # 非完成状态: 必须同时满足时间门控和编辑上限
                    if status != "finished" and (not time_ok or not under_cap):
                        continue

                    if status != "finished":
                        display = (content + " ▌")[:TG_MSG_LIMIT]

                    try:
                        # Phase 3: 完成时用 md_to_html 安全渲染 + HTML parse_mode
                        if status == "finished":
                            try:
                                display = md_to_html(content) + f"\n\n<code>— {getattr(self, 'name', self.bot_id)}</code>"
                                display = display[:TG_MSG_LIMIT]
                                parse_mode = constants.ParseMode.HTML
                            except Exception as e:  # noqa: F841
                                display = (content + f"\n\n`— {getattr(self, 'name', self.bot_id)}`")[:TG_MSG_LIMIT]
                                parse_mode = constants.ParseMode.MARKDOWN
                        else:
                            parse_mode = None
                        reply_markup = _build_smart_reply_keyboard(
                            content, self.bot_id, model_used, chat_id
                        ) if status == "finished" else None
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=display,
                            parse_mode=parse_mode,
                            reply_markup=reply_markup,
                        )
                        # LLM 流式路径补齐追问建议 — 先发消息，再异步更新按钮
                        # 搬运灵感: khoj follow_up / 前四轮只在 Brain 路径有，这里覆盖 80% 对话
                        if status == "finished" and sent_message:
                            _sug_t = asyncio.create_task(self._async_update_suggestions(
                                context, chat_id, sent_message.message_id,
                                content, display, parse_mode, model_used,
                            ))
                            _sug_t.add_done_callback(lambda t: t.exception() and logger.debug("追问建议更新后台任务异常: %s", t.exception()))
                        prev_text = content
                        last_edit_time = _time.monotonic()
                    except BadRequest as e:
                        err_msg = str(e)
                        if "Message is not modified" in err_msg:
                            pass
                        elif "parse" in err_msg.lower() or "can't" in err_msg.lower():
                            try:
                                await context.bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=sent_message.message_id,
                                    text=display,
                                    reply_markup=reply_markup,
                                )
                                prev_text = content
                                last_edit_time = _time.monotonic()
                            except BadRequest as e:  # noqa: F841
                                pass
                        else:
                            backoff_multiplier = min(backoff_multiplier * 2, 16.0)
                            logger.debug(f"[{self.bot_id}] edit_message BadRequest: {err_msg}")
                    except RetryAfter as e:
                        backoff_multiplier = min(backoff_multiplier * 2, 16.0)
                        await asyncio.sleep(e.retry_after)
                    except TimedOut as e:  # noqa: F841
                        backoff_multiplier = min(backoff_multiplier * 2, 16.0)
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        backoff_multiplier = min(backoff_multiplier * 2, 16.0)
                        logger.debug(f"[{self.bot_id}] edit_message 异常: {e}")

                    chunk_idx += 1

            # 流式没有产出任何内容 → 降级到非流式
            if chunk_idx == 0:
                # P0-B: 流式无输出，也要停止思考动画
                _thinking_active = False
                _thinking_task.cancel()
                reply = await self._call_api(chat_id, text, save_history=True, chat_type=chat_type)
                if reply:
                    final_content = reply
                    fb_markup = build_feedback_keyboard(self.bot_id, model_used, chat_id)
                    try:
                        safe_reply = md_to_html(reply)
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=safe_reply[:TG_MSG_LIMIT],
                            parse_mode=constants.ParseMode.HTML,
                            reply_markup=fb_markup,
                        )
                    except BadRequest as e:
                        try:
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=sent_message.message_id,
                                text=reply[:TG_MSG_LIMIT],
                                reply_markup=fb_markup,
                            )
                        except Exception as e:
                            logger.debug("Silenced exception", exc_info=True)
                else:
                    # 空回复 — 更新占位符
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=error_ai_busy(),
                        )
                    except Exception as e:
                        logger.debug("Silenced exception", exc_info=True)
                    logger.info(f"[{self.bot_id}] 空回复 (chat={chat_id})")

            # 记录 AI 回复到智能记忆 (1500字截断，保留更多分析上下文)
            if _sm and final_content:
                _t2 = asyncio.create_task(_sm.on_message(chat_id, user.id, "assistant", final_content[:1500], self.bot_id))
                _t2.add_done_callback(lambda t: t.exception() and logger.debug("智能记忆(AI回复)后台任务异常: %s", t.exception()))

            # 可选语音回复 — 用户通过 /voice 开启后，短回复自动附带语音
            try:
                if final_content and context.user_data.get("voice_reply") and len(final_content) < 500:
                    from src.tts_engine import text_to_voice
                    audio_bytes = await text_to_voice(final_content)
                    if audio_bytes:
                        await update.message.reply_voice(io.BytesIO(audio_bytes))
            except Exception as e:
                logger.debug("Silenced exception", exc_info=True)  # 语音是可选功能，不阻塞主流程

        except Exception as e:
            logger.error(f"[{self.bot_id}] handle_message 异常: {e}", exc_info=True)

            # 清理流式光标 ▌ — 防止异常时光标永久残留
            if sent_message and prev_text:
                try:
                    clean_text = prev_text.rstrip(" ▌")
                    if clean_text:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=clean_text + "\n\n⚠️ 回复中断",
                        )
                except Exception as e:
                    logger.debug("Silenced exception", exc_info=True)

            # 分类错误提示 — 比"出错了"更有信息量
            err_str = str(e).lower()
            if "timeout" in err_str or "timed out" in err_str:
                user_msg = error_ai_busy()
            elif "rate" in err_str or "429" in err_str or "quota" in err_str:
                user_msg = error_rate_limit()
            elif "connect" in err_str or "network" in err_str or "ssl" in err_str:
                user_msg = error_network()
            elif "auth" in err_str or "401" in err_str or "403" in err_str:
                user_msg = error_auth()
            else:
                user_msg = error_generic()
            try:
                from src.telegram_ux import send_error_with_retry
                await send_error_with_retry(update, context, e, retry_command="")
            except Exception as e:
                try:
                    await update.message.reply_text(user_msg)
                except Exception as e:
                    logger.debug("Silenced exception", exc_info=True)
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError as e:  # noqa: F841
                pass

    async def handle_voice(self, update, context):
        """处理语音消息 — 搬运自 father-bot/chatgpt-telegram-bot 的 Whisper 模式
        
        下载语音 → OpenAI Whisper 转文字 → 当作文本消息处理
        """
        if not self._is_authorized(update.effective_user.id):
            return

        chat_id = update.effective_chat.id
        voice = update.message.voice or update.message.audio
        if not voice:
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            # 下载语音文件
            file = await context.bot.get_file(voice.file_id)
            buf = io.BytesIO()
            await file.download_to_memory(buf)
            buf.seek(0)
            buf.name = "voice.ogg"

            # 尝试 OpenAI Whisper API
            transcribed = None
            try:
                import os
                openai_key = os.environ.get("OPENAI_API_KEY", "")
                if openai_key:
                    import httpx
                    async with httpx.AsyncClient(timeout=30) as client:
                        resp = await client.post(
                            "https://api.openai.com/v1/audio/transcriptions",
                            headers={"Authorization": f"Bearer {openai_key}"},
                            files={"file": ("voice.ogg", buf, "audio/ogg")},
                            data={"model": "whisper-1"},
                        )
                        if resp.status_code == 200:
                            transcribed = resp.json().get("text", "")
            except Exception as whisper_err:
                logger.debug("[Voice] Whisper API 失败: %s", whisper_err)

            if not transcribed:
                await update.message.reply_text(
                    "🎤 语音识别暂不可用（需要 OPENAI_API_KEY）\n请发送文字消息",
                    reply_to_message_id=update.message.message_id,
                )
                return

            # 显示识别结果，然后当作文本处理
            await update.message.reply_text(
                f"🎤 识别: {transcribed[:200]}",
                reply_to_message_id=update.message.message_id,
            )

            # 伪造文本消息，复用 handle_message 流程
            update.message.text = transcribed
            await self.handle_message(update, context)

        except Exception as e:
            logger.error("[Voice] 语音处理失败: %s", e)
            await update.message.reply_text("🎤 语音处理失败，请发送文字消息")


    @staticmethod
    def _stream_cutoff(is_group: bool, content: str) -> int:
        """自适应编辑频率 — 搬运自 n3d1117/chatgpt-telegram-bot
        
        群聊更保守（Telegram 对群聊有更严格的 flood 限制），
        私聊更激进（用户体验优先）。
        
        HI-011 根治: 群聊 cutoff 全面提升，配合时间门控使用。
        """
        content_len = len(content)
        if is_group:
            if content_len > 1000: return 300   # was 180
            if content_len > 200: return 200    # was 120
            if content_len > 50: return 150     # was 90
            return 80                 # was 50
        else:
            if content_len > 1000: return 120   # was 90
            if content_len > 200: return 60     # was 45
            if content_len > 50: return 30      # was 25
            return 15

    async def _keep_typing(self, chat_id: int, context):
        """持续发送 typing 指示器 — 搬运自 n3d1117 的 wrap_with_indicator"""
        from telegram.constants import ChatAction
        try:
            while True:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(4.5)
        except asyncio.CancelledError as e:  # noqa: F841
            raise  # 让 finally 正常处理
        except Exception as e:
            # 网络错误等 — 静默退出但记录，不影响主流程
            logger.debug(f"[typing] chat={chat_id} 停止: {e}")

    # ── LLM 流式路径追问建议异步更新 ────────────────────────────
    # Brain 路径已有追问建议（第一轮交付），但 LLM 流式路径（80%对话）没有
    # 这里在消息发出后异步生成建议，再更新按钮

    async def _async_update_suggestions(self, context, chat_id, message_id,
                                         raw_content, display_html, parse_mode, model_used):
        """异步生成追问建议并更新消息按钮 — 不阻塞主流程。"""
        try:
            from src.core.response_synthesizer import get_response_synthesizer
            synth = get_response_synthesizer()
            suggestions = await synth.generate_suggestions(raw_content)
            if not suggestions:
                return

            # 用建议重新构建键盘
            new_markup = _build_smart_reply_keyboard(
                raw_content, self.bot_id, model_used, chat_id,
                ai_suggestions=suggestions,
            )
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=new_markup,
            )
        except Exception as e:
            logger.debug(f"异步追问建议更新失败 (不影响主流程): {e}")

    # ── 会话恢复问候 — 搬运 Apple Intelligence 摘要 / Slack Catch Up ──────
    # 用户超过 SESSION_GAP_THRESHOLD 小时没互动，回来时生成离线摘要

    _SESSION_GAP_THRESHOLD = 4 * 3600  # 4 小时
    _last_interaction: dict = {}  # chat_id → monotonic timestamp

    async def _check_session_resumption(self, chat_id: int, user_id: int, update, context) -> bool:
        """检测用户是否从长时间离线中回来，如果是则发送离线摘要。

        搬运灵感: Apple Intelligence notification summary / Slack Catch Up
        返回 True 表示发送了恢复摘要。
        """
        import time as _t

        now = _t.monotonic()
        last = self._last_interaction.get(chat_id, 0)
        self._last_interaction[chat_id] = now

        # 首次互动或间隔不够长，跳过
        if last == 0 or (now - last) < self._SESSION_GAP_THRESHOLD:
            return False

        gap_hours = (now - last) / 3600

        # 收集离线期间的变化（异步、轻量）
        summary_parts = []
        try:
            # 1. 持仓变化
            from src.invest_tools import get_stock_quote
            from src.watchlist import get_watchlist_symbols
            symbols = get_watchlist_symbols()[:5]
            if symbols:
                movers = []
                import asyncio as _aio
                quotes = await _aio.gather(
                    *[get_stock_quote(s) for s in symbols],
                    return_exceptions=True,
                )
                for sym, q in zip(symbols, quotes):
                    if isinstance(q, Exception) or not q:
                        continue
                    pct = q.get("change_pct", 0)
                    if abs(pct) > 1.5:
                        movers.append(f"{sym} {pct:+.1f}%")
                if movers:
                    summary_parts.append(f"📊 自选股异动: {', '.join(movers)}")
        except Exception as e:
            pass
            logger.debug("静默异常: %s", e)

        try:
            # 2. 闲鱼未读消息
            from src.xianyu.xianyu_live_session import get_xianyu_live
            xy = get_xianyu_live()
            if xy:
                unread = xy.get_unread_count() if hasattr(xy, 'get_unread_count') else 0
                if unread and unread > 0:
                    summary_parts.append(f"🛍️ 闲鱼 {unread} 条未读消息")
        except Exception as e:
            pass
            logger.debug("静默异常: %s", e)

        if not summary_parts:
            return False

        # 发送恢复摘要
        try:
            gap_text = f"{gap_hours:.0f}小时" if gap_hours < 24 else f"{gap_hours/24:.0f}天"
            greeting = f"👋 你离开了 {gap_text}，这期间发生了：\n" + "\n".join(summary_parts)
            await update.message.reply_text(greeting)
            return True
        except Exception as e:  # noqa: F841
            return False
