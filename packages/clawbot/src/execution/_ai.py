"""
Execution Hub — AI 调用层 (LiteLLM 版)
统一走 LiteLLM Router，不再手写 HTTP
"""
import logging
import os
import time
from typing import Dict, Callable

logger = logging.getLogger(__name__)

try:
    from src.langfuse_obs import log_generation
except ImportError:
    log_generation = None  # type: ignore[assignment]

# 与 task_graph.py 同名桩，待统一提取
try:
    from src.utils import emit_flow_event as _emit_flow
except Exception as e:  # noqa: F841
    def _emit_flow(src, tgt, status, msg, data=None):  # type: ignore[misc]
        pass


class AICallerPool:
    """管理 AI 调用 — 优先注入 caller，回退走 LiteLLM Router"""

    def __init__(self):
        self._callers: Dict[str, Callable] = {}

    def set_callers(self, callers: dict):
        self._callers = dict(callers or {})

    def pick_bot_id(self) -> str:
        preferred = os.getenv("OPS_SOCIAL_AI_BOT_ID", "qwen235b").strip()
        if preferred in self._callers:
            return preferred
        fallback_order = [
            "qwen235b", "gptoss", "deepseek_v3",
            "claude_haiku", "claude_sonnet", "free_llm",
        ]
        for candidate in fallback_order:
            if candidate in self._callers:
                return candidate
        return next(iter(self._callers.keys()), preferred)

    async def call(self, prompt: str, system_prompt: str = None) -> dict:
        """调用 AI：先尝试注入的 caller，失败则走 LiteLLM Router"""
        if not prompt:
            return {"success": False, "error": "empty prompt"}
        bot_id = self.pick_bot_id()
        caller = self._callers.get(bot_id)
        _emit_flow("hub", "llm", "running", f"AI 调用: {bot_id}", {"prompt_len": len(prompt)})
        if caller:
            try:
                result = await caller(0, prompt)
                text = str(result or "").strip()
                if text:
                    _emit_flow("llm", "hub", "success", f"AI 响应: {bot_id}", {"resp_len": len(text)})
                    return {"success": True, "raw": text, "bot_id": bot_id}
            except Exception as e:
                logger.warning(f"[AICallerPool] {bot_id} failed: {e}")
                _emit_flow("llm", "hub", "error", f"AI 失败: {bot_id}", {"error": str(e)[:100]})
        return await self.call_via_litellm(prompt, system_prompt)

    async def call_via_litellm(self, prompt: str, system_prompt: str = None) -> dict:
        """通过 LiteLLM Router 调用 — 替代手写 HTTP"""
        if not prompt:
            return {"success": False, "error": "empty prompt"}
        from src.litellm_router import free_pool
        messages = [{"role": "user", "content": prompt}]
        t0 = time.time()
        try:
            _emit_flow("hub", "llm", "running", "LiteLLM 路由调用", {"model_family": "qwen"})
            response = await free_pool.acompletion(
                model_family="qwen",  # 社交内容默认用 qwen
                messages=messages,
                system_prompt=system_prompt or "",
                temperature=0.7,
                max_tokens=4096,
            )
            text = response.choices[0].message.content or ""
            elapsed_ms = (time.time() - t0) * 1000
            input_tokens = getattr(response.usage, "prompt_tokens", 0) if response.usage else 0
            output_tokens = getattr(response.usage, "completion_tokens", 0) if response.usage else 0
            _emit_flow("llm", "hub", "success", "LiteLLM 响应完成", {"elapsed_ms": round(elapsed_ms), "tokens": output_tokens})
            if log_generation:
                try:
                    log_generation(
                        name="ai_pool/litellm",
                        model="qwen",
                        input_text=prompt[:1000],
                        output_text=text[:1000],
                        bot_id="ai_pool",
                        latency_ms=elapsed_ms,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )
                except Exception as e:
                    logger.debug("Silenced exception", exc_info=True)
            return {"success": True, "raw": text, "bot_id": "litellm/qwen", "provider": "litellm"}
        except Exception as e:
            logger.warning(f"[AICallerPool] LiteLLM call failed: {e}")
            return {"success": False, "error": str(e)}

    # 保留旧方法名兼容
    call_direct = call_via_litellm


# 全局单例
ai_pool = AICallerPool()
