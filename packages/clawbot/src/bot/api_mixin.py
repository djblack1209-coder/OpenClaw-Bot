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
from src.http_client import CircuitOpenError
from src.litellm_router import free_pool, BOT_MODEL_FAMILY

try:
    from src.langfuse_obs import log_generation
except ImportError:
    log_generation = None

logger = logging.getLogger(__name__)


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
        except Exception:
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
                return ""
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
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)

            return reply

        except CircuitOpenError as e:
            metrics.log_api_call(self.bot_id, self.model, 0, success=False, error=str(e))
            health_checker.record_error(self.bot_id, str(e))
            return "服务暂时不可用（熔断保护中），请稍后再试"

        except Exception as e:
            latency = (_time.time() - start) * 1000
            metrics.log_api_call(self.bot_id, self.model, latency, success=False, error=str(e))
            health_checker.record_error(self.bot_id, str(e))
            logger.error(f"[{self.name}] API错误: {e}")
            return f"抱歉，出错了: {e}"

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
        """Opus 智能路由: 优先免费 Claude → g4f → 付费 Claude API

        尝试顺序:
        1. LiteLLM Router 的 claude family (Kiro Gateway)
        2. LiteLLM Router 的 g4f family
        3. 付费 Claude API (最后手段)
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

        # 3. 付费 Claude API
        if CLAUDE_KEY:
            logger.info(f"[{bot_name}] 降级到付费 Claude API")
            return await self._call_claude_api(messages)

        # 4. 任意可用模型
        try:
            response = await free_pool.acompletion(
                model_family=None, messages=messages,
                system_prompt=getattr(self, 'system_prompt', ''),
            )
            return response.choices[0].message.content or "(无响应)"
        except Exception:
            raise Exception("所有 API 渠道均不可用")

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
        return "任务处理中使用了过多工具调用，已中止。"

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
                )
                was_compressed = meta.get("compressed", False)
            except Exception:
                messages, was_compressed = context_manager.prepare_messages_for_api(messages)
        else:
            messages, was_compressed = context_manager.prepare_messages_for_api(messages)
        if was_compressed:
            context_manager.update_history_store(history_store, self.bot_id, chat_id, messages)

        bot_id = getattr(self, "bot_id", "")
        family = BOT_MODEL_FAMILY.get(bot_id)

        try:
            response = await free_pool.acompletion(
                model_family=family,
                messages=messages,
                system_prompt=getattr(self, 'system_prompt', ''),
                stream=True,
            )

            full_text = ""
            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    full_text += delta.content
                    yield (full_text, "streaming")

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
                except Exception:
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
                yield (f"抱歉，出错了: {e2}", "error")
