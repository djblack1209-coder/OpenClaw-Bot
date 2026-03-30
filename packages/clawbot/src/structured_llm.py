"""
OpenClaw 结构化 LLM 输出 — 搬运 instructor (10k⭐)
用 Pydantic model 强制 LLM 返回类型安全的结构化数据。
替换所有手动 JSON 解析 + json_repair 的脆弱模式。

instructor 核心优势:
  1. 自动注入 JSON schema 到 prompt / function calling
  2. 验证失败自动重试（把 validation error 反馈给 LLM 修正）
  3. 支持 100+ provider（通过 litellm 桥接）

Usage:
    from src.structured_llm import structured_completion

    class MyOutput(BaseModel):
        answer: str
        confidence: float = Field(ge=0, le=1)

    result = await structured_completion(
        response_model=MyOutput,
        messages=[{"role": "user", "content": "..."}],
        model_family=FAMILY_QWEN,
    )
    # result is a validated MyOutput instance — guaranteed
"""
import json
import logging
import re
from typing import Any, Dict, List, Type, TypeVar

from pydantic import BaseModel
from src.constants import FAMILY_QWEN

logger = logging.getLogger(__name__)

# ── instructor 优雅降级 ──────────────────────────────────────

try:
    import instructor
    from instructor import Mode

    HAS_INSTRUCTOR = True
    logger.info("[structured_llm] instructor 已加载")
except ImportError:
    HAS_INSTRUCTOR = False
    logger.info("[structured_llm] instructor 未安装，降级到 json_repair 模式")

# ── 类型变量 ─────────────────────────────────────────────────

T = TypeVar("T", bound=BaseModel)

# ── 缓存 instructor client（避免每次调用都创建）─────────────

_instructor_client_cache: Dict[int, Any] = {}


def _get_instructor_client(router: Any) -> Any:
    """
    获取/缓存 instructor client。

    用 Router 实例的 id 做 cache key，
    避免 Router 重建后用到旧的 patched function。
    """
    router_id = id(router)
    if router_id not in _instructor_client_cache:
        # Mode.MD_JSON: 要求 LLM 在 markdown ```json``` 块中输出 JSON
        # 兼容性最好 — 不要求 model 支持 function calling 或 response_format
        # 所有 free tier 模型都能用
        _instructor_client_cache[router_id] = instructor.from_litellm(
            router.acompletion,
            mode=Mode.MD_JSON,
        )
        logger.debug("[structured_llm] instructor client 已创建 (MD_JSON mode)")
    return _instructor_client_cache[router_id]


# ── 公开 API ─────────────────────────────────────────────────


async def structured_completion(
    response_model: Type[T],
    messages: List[Dict[str, str]],
    model_family: str = FAMILY_QWEN,
    system_prompt: str = "",
    temperature: float = 0.1,
    max_tokens: int = 800,
    max_retries: int = 2,
) -> T:
    """
    结构化 LLM 调用 — 返回经过 Pydantic 验证的模型实例。

    优先用 instructor（自动重试 + schema 注入），
    不可用时降级到 free_pool + json_repair。

    Args:
        response_model: Pydantic BaseModel 子类，定义期望的输出结构
        messages: 消息列表 [{"role": "user", "content": "..."}]
        model_family: 模型族名称（Router 中的 model_name，如 "qwen"/"gemini"）
        system_prompt: 系统提示词（会自动插入到 messages 前面）
        temperature: 采样温度（结构化输出建议用低温 0.1）
        max_tokens: 最大输出 token
        max_retries: instructor 验证失败重试次数

    Returns:
        response_model 的实例，字段已经过 Pydantic 校验

    Raises:
        ValueError: LLM 返回内容无法解析为目标模型
        RuntimeError: LLM Router 未初始化
    """
    # Lazy import 避免循环依赖
    try:
        from src.litellm_router import free_pool
    except ImportError:
        free_pool = None  # type: ignore[assignment]

    if free_pool is None:
        raise RuntimeError("LLM router 未初始化，无法调用 structured_completion")

    # 合并 system prompt 到 messages
    all_msgs = (
        [{"role": "system", "content": system_prompt}] + messages
        if system_prompt
        else list(messages)
    )

    # ── 路径 1: instructor（优先） ──────────────────────────
    if HAS_INSTRUCTOR and free_pool._router is not None:
        try:
            return await _instructor_path(
                response_model=response_model,
                messages=all_msgs,
                model_family=model_family,
                router=free_pool._router,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=max_retries,
            )
        except Exception as e:
            logger.warning(
                f"[structured_llm] instructor 路径失败 ({type(e).__name__}: {e})，"
                f"降级到 json_repair"
            )
            # Fall through 到降级路径

    # ── 路径 2: json_repair 降级 ───────────────────────────
    return await _fallback_path(
        response_model=response_model,
        messages=messages,  # 用原始 messages，free_pool.acompletion 自己加 system
        model_family=model_family,
        pool=free_pool,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ── instructor 路径 ──────────────────────────────────────────


async def _instructor_path(
    response_model: Type[T],
    messages: List[Dict[str, str]],
    model_family: str,
    router: Any,
    temperature: float,
    max_tokens: int,
    max_retries: int,
) -> T:
    """
    通过 instructor + LiteLLM Router 获取结构化输出。

    instructor 自动:
      1. 将 Pydantic schema 注入 prompt
      2. 解析 LLM 输出为 Pydantic 对象
      3. 验证失败时将 ValidationError 反馈给 LLM 重试
    """
    client = _get_instructor_client(router)

    result = await client.chat.completions.create(
        model=model_family,
        messages=messages,
        response_model=response_model,
        max_retries=max_retries,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    logger.debug(
        f"[structured_llm] instructor 成功: {response_model.__name__} "
        f"(model={model_family})"
    )
    return result


# ── json_repair 降级路径 ─────────────────────────────────────


async def _fallback_path(
    response_model: Type[T],
    messages: List[Dict[str, str]],
    model_family: str,
    pool: Any,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
) -> T:
    """
    不使用 instructor 的降级路径。

    调用 free_pool.acompletion → 提取 raw text → json_repair → Pydantic 校验。
    与 intent_parser.py / pydantic_agents.py 原有的 JSON 提取逻辑一致。
    """
    response = await pool.acompletion(
        model_family=model_family,
        messages=messages,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    raw_text = response.choices[0].message.content.strip()

    # 去除 thinking 标签（某些模型会输出 <think>...</think>）
    raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

    # 尝试 1: json_repair（容错性最强）
    try:
        import json_repair

        data = json_repair.loads(raw_text)
        if isinstance(data, dict):
            result = response_model.model_validate(data)
            logger.debug(
                f"[structured_llm] fallback 成功 (json_repair): "
                f"{response_model.__name__}"
            )
            return result
    except Exception as e:
        logger.debug(f"[structured_llm] json_repair 失败: {e}")

    # 尝试 2: Pydantic model_validate_json（精确但严格）
    try:
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if json_match:
            result = response_model.model_validate_json(json_match.group())
            logger.debug(
                f"[structured_llm] fallback 成功 (regex+pydantic): "
                f"{response_model.__name__}"
            )
            return result
    except Exception as e:
        logger.debug(f"[structured_llm] regex+pydantic 失败: {e}")

    # 尝试 3: 从 markdown code block 中提取
    try:
        code_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL
        )
        if code_match:
            data = json.loads(code_match.group(1))
            result = response_model.model_validate(data)
            logger.debug(
                f"[structured_llm] fallback 成功 (code block): "
                f"{response_model.__name__}"
            )
            return result
    except Exception as e:
        logger.debug(f"[structured_llm] code block 提取失败: {e}")

    # 所有尝试都失败
    raise ValueError(
        f"无法将 LLM 输出解析为 {response_model.__name__}。"
        f"原始输出 (前 300 字符): {raw_text[:300]}"
    )
