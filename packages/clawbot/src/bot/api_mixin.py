"""
API 调用 Mixin — 从 multi_main.py L564-L788 提取
处理所有 LLM API 调用逻辑：硅基流动、OpenAI兼容、Claude
"""
import json
import logging
import time as _time

from src.bot.globals import (
    history_store, context_manager, metrics, health_checker,
    tool_executor, get_siliconflow_key,
    SILICONFLOW_BASE, G4F_BASE, G4F_KEY, KIRO_BASE, KIRO_KEY,
    CLAUDE_BASE, CLAUDE_KEY,
)
from src.bot.rate_limiter import rate_limiter, token_budget, quality_gate
from src.http_client import CircuitOpenError

logger = logging.getLogger(__name__)


class APIMixin:
    """LLM API 调用能力"""

    async def _call_api(self, chat_id: int, user_message: str, save_history: bool = True,
                        chat_type: str = "group") -> str:
        """调用 API（使用增强 HTTP 客户端 + SQLite 历史 + 智能上下文压缩 + 频率/预算控制）"""
        start = _time.time()

        # 频率限制检查
        allowed, reason = rate_limiter.check(self.bot_id, chat_type)
        if not allowed:
            logger.info(f"[{self.name}] 频率限制: {reason}")
            return ""  # 静默跳过，不返回错误消息

        # Token 预算检查
        is_claude = getattr(self, "is_claude", False)
        budget_ok, budget_reason = token_budget.check(self.bot_id, is_claude)
        if not budget_ok:
            logger.warning(f"[{self.name}] Token预算: {budget_reason}")
            return f"今日额度已用完，明天再来~"

        if save_history:
            messages = history_store.get_messages(self.bot_id, chat_id, limit=100)
        else:
            messages = []
        messages.append({"role": "user", "content": user_message})

        # 智能上下文压缩
        messages, was_compressed = context_manager.prepare_messages_for_api(messages)
        if was_compressed:
            context_manager.update_history_store(
                history_store, self.bot_id, chat_id, messages
            )
            logger.info(f"[{self.name}] 上下文已自动压缩 (chat={chat_id})")

        try:
            if self.api_type == "g4f":
                reply = await self._call_openai_compatible_api(messages, G4F_BASE, G4F_KEY)
            elif self.api_type == "kiro":
                reply = await self._call_openai_compatible_api(messages, KIRO_BASE, KIRO_KEY)
            elif self.is_claude:
                reply = await self._call_claude_api(messages)
            else:
                reply = await self._call_siliconflow_api(messages)

            # 记录频率和 Token 使用
            rate_limiter.record(self.bot_id)
            # 粗略估算 token 数（1 token ≈ 4 chars 英文 / 2 chars 中文）
            input_tokens = sum(len(str(m.get("content", ""))) // 2 for m in messages)
            output_tokens = len(reply) // 2
            token_budget.record(self.bot_id, input_tokens, output_tokens)

            # 质量门控检查
            qok, qreason = quality_gate.check_response(self.bot_id, reply)
            if not qok:
                logger.info(f"[{self.name}] 质量门控拦截: {qreason}")
                return ""  # 静默跳过低质量回复
            quality_gate.record_response(self.bot_id, reply)

            if save_history and not was_compressed:
                history_store.add_message(self.bot_id, chat_id, "user", user_message)
            if save_history:
                history_store.add_message(self.bot_id, chat_id, "assistant", reply)

            latency = (_time.time() - start) * 1000
            metrics.log_api_call(self.bot_id, self.model, latency, success=True)
            health_checker.record_success(self.bot_id)
            health_checker.heartbeat(self.bot_id)
            return reply

        except CircuitOpenError as e:
            metrics.log_api_call(self.bot_id, self.model, 0, success=False, error=str(e))
            health_checker.record_error(self.bot_id, str(e))
            return f"服务暂时不可用（熔断保护中），请稍后再试"

        except Exception as e:
            latency = (_time.time() - start) * 1000
            metrics.log_api_call(self.bot_id, self.model, latency, success=False, error=str(e))
            health_checker.record_error(self.bot_id, str(e))
            logger.error(f"[{self.name}] API错误: {e}")
            return f"抱歉，出错了: {e}"

    async def _call_siliconflow_api(self, messages: list) -> str:
        """调用硅基流动 API"""
        api_key = get_siliconflow_key()
        if not api_key:
            raise Exception("没有可用的 API Key")

        all_messages = [{"role": "system", "content": self.system_prompt}] + messages

        response = await self.http_client.post(
            f"{SILICONFLOW_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model,
                "messages": all_messages,
                "max_tokens": 4096,
                "temperature": 0.7
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def _call_openai_compatible_api(self, messages: list, base_url: str, api_key: str) -> str:
        """调用 OpenAI 兼容 API（g4f / Kiro Gateway），带 fallback"""
        all_messages = [{"role": "system", "content": self.system_prompt}] + messages

        if base_url == G4F_BASE:
            # 用 provider 参数锁死纯 API provider，禁止 g4f 自动选浏览器类 provider
            _G4F_FALLBACK = {
                "qwen-3-235b": [
                    ("qwen-3-235b", "OperaAria"),
                    ("qwen-3-235b", "GradientNetwork"),
                    ("aria", "OperaAria"),
                ],
                "gpt-oss-120b": [
                    ("gpt-oss-120b", "OperaAria"),
                    ("gpt-oss-120b", "GradientNetwork"),
                    ("aria", "OperaAria"),
                ],
                "claude-opus-4-6": [
                    ("claude-opus-4-6", "OperaAria"),
                    ("claude-opus-4.6", "OperaAria"),
                    ("claude-opus-4-6", "GradientNetwork"),
                ],
                "claude-opus-4.6": [
                    ("claude-opus-4.6", "OperaAria"),
                    ("claude-opus-4-6", "OperaAria"),
                    ("claude-opus-4.6", "GradientNetwork"),
                ],
                "aria": [
                    ("aria", "OperaAria"),
                    ("qwen-3-235b", "OperaAria"),
                ],
            }
            models_to_try = _G4F_FALLBACK.get(self.model, [(self.model, "GradientNetwork"), ("aria", "OperaAria")])
        else:
            models_to_try = [(self.model, None)]

        last_error = None
        for model, provider in models_to_try:
            try:
                payload = {
                    "model": model,
                    "messages": all_messages,
                    "max_tokens": 4096,
                    "temperature": 0.7
                }
                if provider:
                    payload["provider"] = provider
                response = await self.http_client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                # g4f 有时返回 HTTP 200 但内容是错误信息
                if "error" in data:
                    raise Exception(f"g4f error: {data['error']}")
                content = data["choices"][0]["message"]["content"]
                # 检测假 200：上游返回错误文本而非真实回复
                _bad = (
                    "model does not exist", "model not found", "rate limit",
                    "unauthorized", "missingautherror", "invalid x-api-key",
                )
                if content and any(m in content.lower() for m in _bad):
                    raise Exception(f"g4f fake-200: {content[:100]}")
                if model != self.model:
                    logger.info(f"[{self.bot_id}] 主模型 {self.model} 不可用，fallback 到 {model}")
                return content
            except Exception as e:
                last_error = e
                logger.warning(f"[{self.bot_id}] 模型 {model} 失败: {e}, 尝试下一个")
                continue

        raise last_error or Exception("所有 fallback 模型均失败")

    async def _call_claude_api(self, messages: list, use_tools: bool = True) -> str:
        """调用 Claude API，支持工具调用循环"""
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
                    logger.info(
                        f"[{self.name}] 工具调用完成，共 {iteration} 轮迭代"
                    )
                return final_text if final_text else "(无文本响应)"

            tool_results = []
            for tu in tool_uses:
                tool_name = tu["name"]
                tool_input = tu["input"]
                tool_id = tu["id"]

                logger.info(
                    f"[{self.name}] 工具调用: {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:100]})"
                )

                result = await tool_executor.execute(tool_name, tool_input)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            working_messages.append({"role": "user", "content": tool_results})

        logger.warning(f"[{self.name}] 工具调用达到最大迭代次数 ({max_tool_iterations})")
        if text_parts:
            return "\n".join(text_parts) + "\n\n[已达到工具调用上限]"
        return "任务处理中使用了过多工具调用，已中止。请简化任务后重试。"
