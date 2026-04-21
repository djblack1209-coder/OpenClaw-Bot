"""
Core — 工具 + 系统领域执行器 Mixin

包含 LLM 查询、代码执行、系统状态、进化扫描等方法。
从 brain_executors.py 拆分以降低扇出复杂度。
"""

import logging
from typing import Dict

from config.prompts import SOUL_CORE, INFO_QUERY_PROMPT
from src.bot.error_messages import error_ai_busy
from src.constants import FAMILY_DEEPSEEK, FAMILY_QWEN
from src.resilience import api_limiter
from src.utils import scrub_secrets

logger = logging.getLogger(__name__)


class ToolsExecutorMixin:
    """工具 + 系统领域执行器"""

    async def _exec_llm_query(self, params: Dict) -> Dict:
        """LLM 信息查询 — 注入 SOUL_CORE 人格 + 对话上下文"""
        question = params.get("question", "")
        try:
            from src.litellm_router import free_pool

            if free_pool:
                messages = [
                    {"role": "system", "content": INFO_QUERY_PROMPT},
                ]
                # 注入对话上下文
                ctx = params.get("_brain_context", {})
                recent = ctx.get("recent_messages", "")
                if recent:
                    messages.append(
                        {
                            "role": "system",
                            "content": f"最近对话:\n{recent}",
                        }
                    )
                messages.append({"role": "user", "content": question})

                # 先尝试 qwen 族，失败后降级到任意可用模型
                for _family in [FAMILY_QWEN, None]:
                    try:
                        async with api_limiter("llm"):
                            resp = await free_pool.acompletion(
                                model_family=_family,
                                messages=messages,
                                temperature=0.7,
                                max_tokens=1000,
                            )
                        answer = resp.choices[0].message.content
                        if answer:
                            return {"source": "llm", "answer": answer}
                    except Exception as e:
                        _fam_label = _family or "auto"
                        logger.warning("LLM查询失败 (family=%s): %s", _fam_label, scrub_secrets(str(e)))
                        continue
        except Exception as e:
            logger.warning(f"LLM查询失败: {scrub_secrets(str(e))}")
        return {"source": "llm_fallback", "answer": error_ai_busy()}

    async def _exec_system_status(self, params: Dict) -> Dict:
        """系统状态 — 复用现有 RPC"""
        try:
            from src.api.rpc import ClawBotRPC

            status = ClawBotRPC._rpc_system_status()
            return {"source": "rpc", "status": status}
        except Exception as e:
            logger.warning(f"获取系统状态失败: {scrub_secrets(str(e))}")
            return {"source": "status_error", "error": str(e)}

    async def _exec_evolution_scan(self, params: Dict) -> Dict:
        """进化扫描 — 复用现有 evolution engine"""
        try:
            from src.evolution.engine import EvolutionEngine

            engine = EvolutionEngine()
            proposals = await engine.daily_scan()
            return {
                "source": "evolution",
                "proposals_count": len(proposals),
                "proposals": [p.to_dict() for p in proposals[:5]],
            }
        except Exception as e:
            logger.warning(f"进化扫描失败: {scrub_secrets(str(e))}")
            return {"source": "evolution_error", "error": str(e)}

    async def _exec_code_task(self, params: Dict) -> Dict:
        """代码任务 — 调用 CodeTool 沙盒执行"""
        task_desc = params.get("task", "")
        try:
            from src.tools.code_tool import CodeTool

            tool = CodeTool()
            if any(kw in task_desc for kw in ["import ", "def ", "print(", "for ", "class "]):
                result = await tool.execute_python(task_desc)
                return {"source": "code_tool", "output": result, "type": "direct_execution"}
            else:
                # 用 LLM 生成代码再执行
                from src.litellm_router import free_pool

                if free_pool:
                    resp = await free_pool.acompletion(
                        model_family=FAMILY_DEEPSEEK,
                        messages=[{"role": "user", "content": task_desc}],
                        system_prompt=SOUL_CORE
                        + "\n\n你现在在做代码生成任务。只输出可执行的Python代码，不要解释。用```python代码块包裹。",
                        temperature=0.2,
                        max_tokens=2000,
                    )
                    code = resp.choices[0].message.content
                    import re

                    code_match = re.search(r"```python\s*(.*?)```", code, re.DOTALL)
                    if code_match:
                        code = code_match.group(1).strip()
                    result = await tool.execute_python(code)
                    return {"source": "code_tool_llm", "code": code[:500], "output": result}
        except Exception as e:
            logger.warning(f"代码任务失败: {scrub_secrets(str(e))}")
        return {"source": "code_fallback", "note": "代码执行模块异常"}
