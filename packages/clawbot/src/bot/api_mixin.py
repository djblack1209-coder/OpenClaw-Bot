"""
API 调用 Mixin — 重构版: 统一走 LiteLLM Router

变化:
- 删除 _call_siliconflow_api / _call_openai_compatible_api 等手写 HTTP 方法
- 统一通过 free_pool.acompletion() 调用，LiteLLM 处理路由/fallback/重试
- 保留 _call_claude_api (付费 Claude 工具调用循环，LiteLLM 不直接支持)
- 流式调用也走 LiteLLM stream=True
"""
import json
import logging
import time as _time
from typing import AsyncIterator

from src.bot.globals import (
    history_store, context_manager, metrics, health_checker,
    tool_executor,
    CLAUDE_BASE, CLAUDE_KEY,
)
from src.bot.rate_limiter import rate_limiter, token_budget, quality_gate
from src.bot.error_messages import error_generic, error_circuit_open, error_tool_abuse
from src.http_client import CircuitOpenError
from src.litellm_router import free_pool, BOT_MODEL_FAMILY

try:
    from src.langfuse_obs import log_generation
except ImportError:
    log_generation = None

logger = logging.getLogger(__name__)


def _detect_message_tone(text: str) -> str:
    """检测消息的紧急/悠闲语气 — 搬运 Google Gemini 情境适应模式

    返回: "urgent" (紧急) / "detailed" (详细) / "normal" (普通)
    零 LLM 成本，纯特征检测。
    """
    import re
    if not text or len(text) < 2:
        return "normal"

    # 紧急信号: 短消息 + 感叹号/问号连续 + 催促关键词
    urgent_signals = 0
    if len(text) < 15:
        urgent_signals += 1  # 短消息通常较急
    if re.search(r"[!！]{2,}|[?？]{2,}", text):
        urgent_signals += 2  # 连续感叹号/问号
    if re.search(r"(?:快|急|马上|立刻|赶紧|速度|紧急|立即|ASAP)", text):
        urgent_signals += 2  # 催促关键词
    if re.search(r"(?:怎么回事|出问题了|崩了|挂了|不行了)", text):
        urgent_signals += 1  # 问题信号
    if urgent_signals >= 2:
        return "urgent"

    # 详细信号: 长消息(>25中文字符) + 多个问题/逗号(结构化表达)
    if len(text) > 25:
        return "detailed"
    if text.count("？") + text.count("?") >= 2:
        return "detailed"  # 多个问题说明用户有耐心

    return "normal"


class APIMixin:
    """LLM API 调用能力 — LiteLLM Router 版"""

    async def _call_api(self, chat_id: int, user_message: str, save_history: bool = True,
                        chat_type: str = "group") -> str:
        """调用 API — 统一走 LiteLLM Router

        路由策略:
        - 群聊: 所有 bot 走免费模型 (LiteLLM 自动路由)
        - 私聊 claude_opus: 优先免费 Claude，兜底付费 Claude API
        - 其他: 免费模型
        """
        start = _time.time()

        # 频率限制
        allowed, reason = rate_limiter.check(self.bot_id, chat_type)
        if not allowed:
            return ""

        # Token 预算
        is_claude = getattr(self, "is_claude", False)
        budget_ok, budget_reason = token_budget.check(self.bot_id, is_claude)
        if not budget_ok:
            return "今日额度已用完，明天再来~"

        # 构建消息
        if save_history:
            messages = history_store.get_messages(self.bot_id, chat_id, limit=100)
        else:
            messages = []
        messages.append({"role": "user", "content": user_message})

        # 上下文压缩
        from src.bot.globals import tiered_context_manager
        if tiered_context_manager:
            try:
                messages, meta = tiered_context_manager.build_context(
                    messages=messages,
                    system_prompt=getattr(self, 'system_prompt', ''),
                    query_hint=user_message,
                    chat_id=chat_id,
                )
                was_compressed = meta.get("compressed", False)
            except Exception as e:
                logger.warning(f"[{self.name}] TieredContext fallback: {e}")
                messages, was_compressed = context_manager.prepare_messages_for_api(messages)
        else:
            messages, was_compressed = context_manager.prepare_messages_for_api(messages)

        if was_compressed:
            context_manager.update_history_store(history_store, self.bot_id, chat_id, messages)

        # chat_mode 个性化
        try:
            chat_mode_extra = self._get_chat_mode_prompt(chat_id)
            if chat_mode_extra:
                messages.insert(0, {"role": "system", "content": chat_mode_extra})
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)

        try:
            # 路由决策
            if chat_type == "private" and self.api_type == "free_first":
                reply = await self._call_opus_smart(messages)
            else:
                reply = await self._call_via_litellm(messages)

            # 记录使用
            rate_limiter.record(self.bot_id)
            input_tokens = sum(len(str(m.get("content", ""))) // 2 for m in messages)
            output_tokens = len(reply) // 2
            token_budget.record(self.bot_id, input_tokens, output_tokens)

            # 质量门控
            qok, qreason = quality_gate.check_response(self.bot_id, reply)
            if not qok:
                logger.warning("[%s] quality_gate rejected: %s", self.bot_id, qreason)
                return f"⚠️ 回复未通过质量检查，请重新提问。\n原因: {qreason}"
            quality_gate.record_response(self.bot_id, reply)

            # 保存历史
            if save_history and not was_compressed:
                history_store.add_message(self.bot_id, chat_id, "user", user_message)
            if save_history:
                history_store.add_message(self.bot_id, chat_id, "assistant", reply)

            latency = (_time.time() - start) * 1000
            metrics.log_api_call(self.bot_id, self.model, latency, success=True)
            health_checker.record_success(self.bot_id)
            health_checker.heartbeat(self.bot_id)

            # Langfuse
            if log_generation:
                try:
                    log_generation(
                        name=f"chat/{self.bot_id}", model=self.model,
                        input_text=user_message[:2000], output_text=reply[:2000],
                        bot_id=self.bot_id, chat_id=str(chat_id),
                        latency_ms=latency, input_tokens=input_tokens,
                        output_tokens=output_tokens, metadata={"chat_type": chat_type},
                    )
                except Exception as e:
                    logger.debug("Silenced exception", exc_info=True)

            return reply

        except CircuitOpenError as e:
            metrics.log_api_call(self.bot_id, self.model, 0, success=False, error=str(e))
            health_checker.record_error(self.bot_id, str(e))
            return error_circuit_open()

        except Exception as e:
            latency = (_time.time() - start) * 1000
            metrics.log_api_call(self.bot_id, self.model, latency, success=False, error=str(e))
            health_checker.record_error(self.bot_id, str(e))
            logger.error(f"[{self.name}] API错误: {e}")
            return error_generic(str(e))

    # ---- 核心调用: LiteLLM Router ----

    async def _call_via_litellm(self, messages: list) -> str:
        """通过 LiteLLM Router 调用，自动路由+fallback+重试"""
        bot_id = getattr(self, "bot_id", "")
        family = BOT_MODEL_FAMILY.get(bot_id)

        response = await free_pool.acompletion(
            model_family=family,
            messages=messages,
            system_prompt=getattr(self, 'system_prompt', ''),
        )
        return response.choices[0].message.content or "(无响应)"

    async def _call_opus_smart(self, messages: list) -> str:
        """Opus 智能路由: 仅使用免费模型，付费 API 需显式调用

        v3.0: 移除付费 Claude API 自动回落。用户需发 /claude 显式调用。
        尝试顺序:
        1. LiteLLM Router 的 claude family (Kiro Gateway, 免费)
        2. LiteLLM Router 的 g4f family (免费)
        3. 任意可用免费模型 (qwen/deepseek/gemini 等)
        """
        bot_name = getattr(self, "name", "claude_opus")

        # 1. 免费 Claude (Kiro)
        try:
            response = await free_pool.acompletion(
                model_family="claude", messages=messages,
                system_prompt=getattr(self, 'system_prompt', ''),
            )
            logger.info(f"[{bot_name}] 免费 Claude 成功")
            return response.choices[0].message.content or "(无响应)"
        except Exception as e:
            logger.warning(f"[{bot_name}] 免费 Claude 失败: {e}")

        # 2. g4f
        try:
            response = await free_pool.acompletion(
                model_family="g4f", messages=messages,
                system_prompt=getattr(self, 'system_prompt', ''),
            )
            logger.info(f"[{bot_name}] g4f 成功")
            return response.choices[0].message.content or "(无响应)"
        except Exception as e:
            logger.warning(f"[{bot_name}] g4f 也失败: {e}")

        # 3. 任意可用免费模型 (不再自动回落到付费 Claude)
        # v3.0: 付费 Claude API 需用户发 /claude 显式调用
        try:
            response = await free_pool.acompletion(
                model_family=None, messages=messages,
                system_prompt=getattr(self, 'system_prompt', ''),
            )
            return response.choices[0].message.content or "(无响应)"
        except Exception as e:  # noqa: F841
            raise Exception("所有免费 API 渠道均不可用，如需使用付费模型请发 /claude")

    async def _call_claude_api(self, messages: list, use_tools: bool = True) -> str:
        """付费 Claude API，支持工具调用循环 (保留原实现，LiteLLM 不直接支持多轮工具循环)"""
        tools = tool_executor.get_tools_schema() if use_tools else None
        max_tool_iterations = 8
        working_messages = list(messages)
        text_parts = []

        for iteration in range(max_tool_iterations):
            payload = {
                "model": self.model,
                "max_tokens": 8192,
                "system": self.system_prompt,
                "messages": working_messages,
            }
            if tools:
                payload["tools"] = tools

            response = await self.http_client.post(
                f"{CLAUDE_BASE}/messages",
                headers={
                    "x-api-key": CLAUDE_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            content_blocks = data.get("content", [])
            stop_reason = data.get("stop_reason", "end_turn")

            assistant_content = []
            text_parts = []
            tool_uses = []

            for block in content_blocks:
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                    assistant_content.append(block)
                elif block.get("type") == "tool_use":
                    tool_uses.append(block)
                    assistant_content.append(block)

            working_messages.append({"role": "assistant", "content": assistant_content})

            if not tool_uses or stop_reason == "end_turn":
                final_text = "\n".join(text_parts)
                if iteration > 0 and text_parts:
                    logger.info(f"[{self.name}] 工具调用完成，共 {iteration} 轮")
                return final_text if final_text else "(无文本响应)"

            tool_results = []
            for tu in tool_uses:
                logger.info(f"[{self.name}] 工具: {tu['name']}({json.dumps(tu['input'], ensure_ascii=False)[:100]})")
                result = await tool_executor.execute(tu["name"], tu["input"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })
            working_messages.append({"role": "user", "content": tool_results})

        if text_parts:
            return "\n".join(text_parts) + "\n\n[已达到工具调用上限]"
        return error_tool_abuse()

    # ---- 流式调用 ----

    async def _call_api_stream(self, chat_id: int, user_message: str,
                                save_history: bool = True,
                                chat_type: str = "group") -> AsyncIterator[tuple]:
        """流式调用 — 走 LiteLLM stream=True"""
        start = _time.time()

        allowed, _ = rate_limiter.check(self.bot_id, chat_type)
        if not allowed:
            yield ("", "error")
            return

        budget_ok, _ = token_budget.check(self.bot_id, getattr(self, "is_claude", False))
        if not budget_ok:
            yield ("今日额度已用完，明天再来~", "finished")
            return

        messages = history_store.get_messages(self.bot_id, chat_id, limit=100) if save_history else []
        messages.append({"role": "user", "content": user_message})

        from src.bot.globals import tiered_context_manager as _tcm
        if _tcm:
            try:
                messages, meta = _tcm.build_context(
                    messages=messages,
                    system_prompt=getattr(self, 'system_prompt', ''),
                    query_hint=user_message,
                    chat_id=chat_id,
                )
                was_compressed = meta.get("compressed", False)
            except Exception as e:  # noqa: F841
                messages, was_compressed = context_manager.prepare_messages_for_api(messages)
        else:
            messages, was_compressed = context_manager.prepare_messages_for_api(messages)
        if was_compressed:
            context_manager.update_history_store(history_store, self.bot_id, chat_id, messages)

        bot_id = getattr(self, "bot_id", "")
        family = BOT_MODEL_FAMILY.get(bot_id)

        # 画像驱动回复: 从 core memory 读取用户偏好，注入 system prompt
        # 搬运灵感: omi personality-driven responses
        _sys_prompt = getattr(self, 'system_prompt', '')
        try:
            if _tcm:
                _user_profile = _tcm.core_get("user_profile", chat_id=chat_id) or ""
                if _user_profile:
                    _sys_prompt += f"\n\n[用户偏好] {_user_profile[:300]}"
        except Exception as e:
            pass  # 画像获取失败不影响主流程
            logger.debug("静默异常: %s", e)

        # 消息温度感知: 检测用户紧急/悠闲语气，调整回复风格
        # 搬运灵感: Google Gemini contextual response adaptation
        try:
            _tone = _detect_message_tone(user_message)
            if _tone == "urgent":
                _sys_prompt += "\n\n[语气感知] 用户当前很着急，请极简直给，不超过2句话，先给结论。"
            elif _tone == "detailed":
                _sys_prompt += "\n\n[语气感知] 用户当前很有耐心，可以详细展开分析。"
        except Exception as e:
            logger.debug("静默异常: %s", e)

        try:
            response = await free_pool.acompletion(
                model_family=family,
                messages=messages,
                system_prompt=_sys_prompt,
                stream=True,
            )

            full_text = ""
            _last_yield = _time.monotonic()
            _MIN_YIELD_INTERVAL = 0.3   # HI-011: 生产端最少 300ms 才 yield 一次
            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    full_text += delta.content
                    _now = _time.monotonic()
                    if _now - _last_yield >= _MIN_YIELD_INTERVAL:
                        yield (full_text, "streaming")
                        _last_yield = _now

            # 记录
            rate_limiter.record(self.bot_id)
            input_tokens = sum(len(str(m.get("content", ""))) // 2 for m in messages)
            output_tokens = len(full_text) // 2
            token_budget.record(self.bot_id, input_tokens, output_tokens)

            if save_history and not was_compressed:
                history_store.add_message(self.bot_id, chat_id, "user", user_message)
            if save_history:
                history_store.add_message(self.bot_id, chat_id, "assistant", full_text)

            latency = (_time.time() - start) * 1000
            metrics.log_api_call(self.bot_id, self.model, latency, success=True)
            health_checker.record_success(self.bot_id)
            health_checker.heartbeat(self.bot_id)

            if log_generation:
                try:
                    log_generation(
                        name=f"stream/{self.bot_id}", model=self.model,
                        input_text=user_message[:2000], output_text=full_text[:2000],
                        bot_id=self.bot_id, chat_id=str(chat_id),
                        latency_ms=latency, input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        metadata={"chat_type": chat_type, "stream": True},
                    )
                except Exception as e:
                    logger.debug("Silenced exception", exc_info=True)

            yield (full_text, "finished")

        except Exception as e:
            latency = (_time.time() - start) * 1000
            metrics.log_api_call(self.bot_id, self.model, latency, success=False, error=str(e))
            health_checker.record_error(self.bot_id, str(e))
            logger.warning(f"[{getattr(self, 'name', bot_id)}] 流式失败: {e}, 降级非流式")
            try:
                reply = await self._call_api(chat_id, user_message, save_history, chat_type)
                yield (reply, "finished")
            except Exception as e2:
                yield (error_generic(str(e2)), "error")
