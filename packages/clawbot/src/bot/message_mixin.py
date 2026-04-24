# message_mixin.py — 消息处理 Mixin (文本/语音/图片/文档/回调)
# 搬运自 n3d1117/chatgpt-telegram-bot (3.5k⭐) 流式模式

import asyncio
import importlib.util
import io
import logging
import time as _time

from src.bot.chinese_nlp_mixin import _match_chinese_command
from src.bot.error_messages import error_ai_busy, error_auth, error_generic, error_network, error_rate_limit
from src.constants import TG_MSG_LIMIT
from src.telegram_markdown import md_to_html
from src.utils import scrub_secrets

logger = logging.getLogger(__name__)

# ── 输入预处理函数从 input_processor.py 导入（向后兼容）──
from src.bot.callback_mixin import CallbackMixin
from src.bot.input_processor import _build_smart_reply_keyboard, _detect_correction
from src.bot.session_tracker import SessionTrackerMixin
from src.bot.stream_manager import StreamManagerMixin
from src.bot.voice_handler import VoiceHandlerMixin
from src.bot.workflow_mixin import WorkflowMixin
from src.perf_metrics import perf_timer


class MessageHandlerMixin(WorkflowMixin, CallbackMixin, VoiceHandlerMixin, SessionTrackerMixin, StreamManagerMixin):
    @perf_timer("bot.handle_message")
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

        from src.feedback import build_feedback_keyboard
        from src.smart_memory import get_smart_memory

        # ── HI-011 flood 根治: 时间门控 + 编辑次数上限 ──
        # Telegram 群聊 editMessageText 限制约 20次/分钟
        EDIT_INTERVAL_GROUP = 3.0  # 群聊: 每条消息最少间隔 3 秒
        EDIT_INTERVAL_PRIVATE = 1.0  # 私聊: 每条消息最少间隔 1 秒
        MAX_EDITS_GROUP = 15  # 群聊: 单条消息最多编辑 15 次
        MAX_EDITS_PRIVATE = 30  # 私聊: 单条消息最多编辑 30 次

        chat_id = update.effective_chat.id
        user = update.effective_user
        text = (update.message.text or "").strip()
        if not text:
            return

        chat_type = update.effective_chat.type
        is_group = chat_type in ("group", "supergroup")

        if not self._is_authorized(user.id):
            return

        # ── 输入消毒 — 拦截 XSS/SQL注入/命令注入等攻击载荷 (HI-037) ──
        # 所有用户消息在进入 LLM/Brain 处理前先过安全过滤
        # 安全策略: fail-close — 消毒失败时拒绝处理，防止恶意输入绕过
        try:
            from src.core.security import get_security_gate

            _sec_gate = get_security_gate()
            text = _sec_gate.sanitize_input(text)
        except Exception as _sanitize_err:
            logger.warning("输入消毒失败（fail-close，拒绝处理）: %s", _sanitize_err)
            await update.message.reply_text("⚠️ 消息处理出现异常，请稍后重试。")
            return

        # ── 会话恢复问候 — 搬运 Apple Intelligence 摘要 / Slack Catch Up ──
        # 用户超过 4 小时没互动后回来，在首条回复前生成"离线期间发生了什么"摘要
        try:
            _session_gap_handled = await self._check_session_resumption(chat_id, user.id, update, context)
        except Exception as e:
            logger.warning("静默异常: %s", e)

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
                            _prev_context = " | ".join(m.get("content", "")[:200] for m in _recent)
                except Exception as e:
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
            # 纠错检测失败不影响主流程
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
                    _clarify_task_id,
                    text,
                    {"user_id": user.id, "chat_id": chat_id, "bot_id": self.bot_id},
                )
                if _clarify_result.success and _clarify_result.final_result:
                    _clarify_msg = _clarify_result.to_user_message()
                    if _clarify_msg:
                        _clarify_markup = None
                        try:
                            _clarify_markup = _build_smart_reply_keyboard(
                                _clarify_msg, self.bot_id, getattr(self, "model", ""), chat_id
                            )
                        except Exception as e:
                            logger.debug("静默异常: %s", e)
                        try:
                            safe = md_to_html(_clarify_msg)
                            await update.message.reply_text(
                                safe,
                                parse_mode="HTML",
                                reply_markup=_clarify_markup,
                            )
                        except Exception:
                            logger.exception("Brain 追问回答 HTML 渲染失败")
                            await update.message.reply_text(
                                _clarify_msg,
                                reply_markup=_clarify_markup,
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
                    _cmd_task = asyncio.create_task(_sm.on_message(chat_id, user.id, "user", action_label, self.bot_id))

                    def _cmd_task_done(t):
                        if not t.cancelled() and t.exception():
                            logger.debug("[MessageMixin] 后台任务异常: %s", t.exception())

                    _cmd_task.add_done_callback(_cmd_task_done)
            except Exception:
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
                    except Exception:
                        logger.exception("LLM 轻量分类器调用失败")
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
                                    user_msg,
                                    self.bot_id,
                                    getattr(self, "model", ""),
                                    chat_id,
                                    ai_suggestions=_ai_suggestions,
                                )
                            except Exception as e:
                                logger.debug("静默异常: %s", e)

                            try:
                                safe = md_to_html(user_msg)
                                await update.message.reply_text(
                                    safe,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup,
                                )
                            except Exception:
                                logger.exception("Brain 路由回复 HTML 渲染失败")
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
                            except Exception:
                                logger.debug("Brain 路径 SmartMemory 写入失败", exc_info=True)

                            return
                    elif result.needs_clarification:
                        # Brain 需要追问 — 显示追问消息，等待用户下一条消息回答
                        clarify_text = result.to_user_message()
                        if clarify_text:
                            try:
                                safe = md_to_html(clarify_text)
                                await update.message.reply_text(safe, parse_mode="HTML")
                            except Exception:
                                logger.exception("Brain 追问消息 HTML 渲染失败")
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
                    [InlineKeyboardButton(t, callback_data=cb) for t, cb in _fuzzy_suggestions[:3]],
                ]
                if len(_fuzzy_suggestions) > 3:
                    _fuzzy_rows.append([InlineKeyboardButton(t, callback_data=cb) for t, cb in _fuzzy_suggestions[3:]])
                await update.message.reply_text(
                    "严总，我不太确定你想做什么，试试这些？👇\n\n（或者直接告诉我更具体的需求）",
                    reply_markup=InlineKeyboardMarkup(_fuzzy_rows),
                )
            except Exception:
                logger.debug("模糊引导按钮发送失败", exc_info=True)

        # 消息频率限制 — 防止用户刷屏导致 API 过载
        # 幻影导入修复: rate_limiter 从实际定义模块导入
        from src.bot.rate_limiter import rate_limiter

        if rate_limiter:
            allowed, reason = rate_limiter.check(self.bot_id, "private" if not is_group else "group")
            if not allowed:
                logger.info("[%s] 消息频率限制: %s (user=%s)", self.name, reason, user.id)
                try:
                    await update.message.reply_text("⏳ 严总，您发得太快啦，等几秒再发就好。")
                except Exception:
                    logger.debug("频率限制回复失败", exc_info=True)
                return

        # 群聊：检查是否应该回复
        if is_group:
            should, reason = await self._should_respond_async(text, chat_type, update.message.message_id, user.id)
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
                import time as _ptime

                from src.routing import PrioritizedMessage

                await priority_message_queue.enqueue(
                    PrioritizedMessage(
                        priority=_msg_priority.value,
                        timestamp=_ptime.time(),
                        chat_id=chat_id,
                        user_id=user.id,
                        text=text[:200],
                        bot_id=getattr(self, "bot_id", ""),
                    )
                )
            except Exception:
                logger.debug("Silenced exception", exc_info=True)  # 优先级队列不影响主流程

        # 智能记忆管道 — 记录用户消息（异步，不阻塞）
        _sm = get_smart_memory()
        if _sm:
            _t = asyncio.create_task(_sm.on_message(chat_id, user.id, "user", text, self.bot_id))
            _t.add_done_callback(
                lambda t: t.exception() and logger.debug("智能记忆(用户消息)后台任务异常: %s", t.exception())
            )

        # 发送 typing 指示器
        typing_task = asyncio.create_task(self._keep_typing(chat_id, context))
        typing_task.add_done_callback(
            lambda t: t.exception() and logger.debug("typing指示器后台任务异常: %s", t.exception())
        )

        try:
            sent_message = None
            prev_text = ""
            backoff_multiplier = 1.0  # HI-011: 指数退避乘数
            chunk_idx = 0
            final_content = ""
            model_used = getattr(self, "model", "unknown") or "unknown"
            edit_interval = EDIT_INTERVAL_GROUP if is_group else EDIT_INTERVAL_PRIVATE
            max_edits = MAX_EDITS_GROUP if is_group else MAX_EDITS_PRIVATE
            last_edit_time = 0.0  # HI-011: 上次编辑时间 (monotonic)

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
                        except Exception:
                            logger.exception("思考动画更新失败")
                            break
                except asyncio.CancelledError as e:  # noqa: F841
                    pass

            from src.core.async_utils import create_monitored_task
            _thinking_task = create_monitored_task(
                _animate_thinking(), name="thinking_animation"
            )

            async for content, status in self._call_api_stream(chat_id, text, save_history=True, chat_type=chat_type):
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
                        except BadRequest as e:
                            logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)
                    # P1-A: 溢出分段保留格式化渲染
                    remaining = content[TG_MSG_LIMIT:]
                    while remaining:
                        chunk = remaining[:TG_MSG_LIMIT]
                        remaining = remaining[TG_MSG_LIMIT:]
                        try:
                            safe_chunk = md_to_html(chunk)
                            sent_message = await update.message.reply_text(safe_chunk, parse_mode="HTML")
                        except Exception:
                            try:
                                sent_message = await update.message.reply_text(chunk)
                            except Exception as e:
                                logger.warning(f"[{self.bot_id}] 发送溢出消息失败: {scrub_secrets(str(e))}")
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
                        logger.warning(f"[{self.bot_id}] 替换占位符失败: {scrub_secrets(str(e))}")
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
                                display = (
                                    md_to_html(content) + f"\n\n<code>— {getattr(self, 'name', self.bot_id)}</code>"
                                )
                                display = display[:TG_MSG_LIMIT]
                                parse_mode = constants.ParseMode.HTML
                            except Exception:
                                logger.exception("流式消息 HTML 渲染失败，降级为 Markdown")
                                display = (content + f"\n\n`— {getattr(self, 'name', self.bot_id)}`")[:TG_MSG_LIMIT]
                                parse_mode = constants.ParseMode.MARKDOWN
                        else:
                            parse_mode = None
                        reply_markup = (
                            _build_smart_reply_keyboard(content, self.bot_id, model_used, chat_id)
                            if status == "finished"
                            else None
                        )
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
                            _sug_t = asyncio.create_task(
                                self._async_update_suggestions(
                                    context,
                                    chat_id,
                                    sent_message.message_id,
                                    content,
                                    display,
                                    parse_mode,
                                    model_used,
                                )
                            )
                            _sug_t.add_done_callback(
                                lambda t: t.exception() and logger.debug("追问建议更新后台任务异常: %s", t.exception())
                            )
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
                            except BadRequest as e:
                                logger.debug("Telegram消息操作失败(用户可能已删除): %s", e)
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
                    except BadRequest:
                        try:
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=sent_message.message_id,
                                text=reply[:TG_MSG_LIMIT],
                                reply_markup=fb_markup,
                            )
                        except Exception:
                            logger.debug("Silenced exception", exc_info=True)
                else:
                    # 空回复 — 更新占位符
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=error_ai_busy(),
                        )
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)
                    logger.info(f"[{self.bot_id}] 空回复 (chat={chat_id})")

            # 记录 AI 回复到智能记忆 (1500字截断，保留更多分析上下文)
            if _sm and final_content:
                _t2 = asyncio.create_task(
                    _sm.on_message(chat_id, user.id, "assistant", final_content[:1500], self.bot_id)
                )
                _t2.add_done_callback(
                    lambda t: t.exception() and logger.debug("智能记忆(AI回复)后台任务异常: %s", t.exception())
                )

            # 语音回复 — 两种触发条件:
            # 1. 用户通过 /voice 手动开启语音回复模式 (短回复 <500字)
            # 2. 用户发送的是语音消息 (_voice_input 标记)，自动以语音回复 (闭环)
            #    语音输入时放宽长度限制到 2000 字，超长文本 TTS 会自动截断
            try:
                _is_voice_input = context.user_data.get("_voice_input", False)
                _voice_mode = context.user_data.get("voice_reply", False)
                _voice_len_limit = 2000 if _is_voice_input else 500
                if final_content and (_is_voice_input or _voice_mode) and len(final_content) < _voice_len_limit:
                    from src.tts_engine import text_to_voice

                    audio_bytes = await text_to_voice(final_content)
                    if audio_bytes:
                        await update.message.reply_voice(io.BytesIO(audio_bytes))
            except Exception as e:
                logger.debug("语音回复生成失败 (不影响文字回复): %s", e)

        except Exception as e:
            logger.error(f"[{self.bot_id}] handle_message 异常: {scrub_secrets(str(e))}", exc_info=True)

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
            except Exception:
                try:
                    await update.message.reply_text(user_msg)
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError as e:  # noqa: F841
                pass
