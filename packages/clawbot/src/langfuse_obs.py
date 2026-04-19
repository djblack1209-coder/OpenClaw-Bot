"""
Langfuse 观测层 — 搬运自 langfuse (23.4k⭐)

替换 monitoring.py 中自研的 CostAnalyzer + PrometheusMetrics 的 LLM 追踪部分。
保留 monitoring.py 的 AutoRecovery + HealthChecker（Langfuse 不覆盖）。

功能：
- 每个 LLM 调用自动上报：模型、token 用量、延迟、成本
- 按 bot_id / user_id / chat_type 分维度追踪
- Web 面板查看全链路 trace（替代自研日志翻阅）
- Langfuse 不可用时静默降级，不影响业务

集成方式：
  1. pip install langfuse
  2. 设置环境变量 LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY / LANGFUSE_HOST
  3. 在 LLM 调用处用 trace_llm_call() 包装
"""

import os
import time
import logging
from typing import Optional, Dict, Any
from functools import wraps

logger = logging.getLogger(__name__)

# ── Langfuse 可用性检测 ──

_langfuse_available = False
_langfuse_client = None

try:
    from langfuse import Langfuse

    _langfuse_available = True
except ImportError:
    logger.info("[LangfuseObs] langfuse 未安装，观测层禁用")


def init_langfuse() -> bool:
    """初始化 Langfuse 客户端。需要环境变量：
    - LANGFUSE_SECRET_KEY
    - LANGFUSE_PUBLIC_KEY
    - LANGFUSE_HOST (默认 http://localhost:3000)
    """
    global _langfuse_client
    if not _langfuse_available:
        return False

    secret = os.getenv("LANGFUSE_SECRET_KEY", "")
    public = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    if not secret or not public:
        logger.info("[LangfuseObs] 未配置 LANGFUSE_SECRET_KEY/PUBLIC_KEY，观测层禁用")
        logger.info("[LangfuseObs] 启用方法: 注册 https://cloud.langfuse.com (免费 50k events/月)")
        logger.info("[LangfuseObs]   → 在 .env 中设置 LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY / LANGFUSE_HOST")
        return False

    try:
        _langfuse_client = Langfuse(
            secret_key=secret,
            public_key=public,
            host=host,
        )
        _langfuse_client.auth_check()
        logger.info("[LangfuseObs] 初始化成功 (host=%s)", host)
        return True
    except Exception as e:
        logger.warning("[LangfuseObs] 初始化失败: %s", e)
        _langfuse_client = None
        return False


def trace_llm_call(
    name: str = "llm-call",
    model: str = "",
    bot_id: str = "",
    user_id: str = "",
    chat_id: str = "",
    chat_type: str = "",
    metadata: Optional[Dict] = None,
):
    """
    装饰器：追踪 LLM 调用。

    用法：
        @trace_llm_call(name="chat", bot_id="qwen235b")
        async def my_llm_call(messages):
            ...
            return reply_text

    自动记录：调用时间、延迟、输入/输出、模型、token 估算。
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if not _langfuse_client:
                return await fn(*args, **kwargs)

            start = time.time()
            trace = None
            generation = None
            try:
                trace = _langfuse_client.trace(
                    name=name,
                    user_id=user_id or bot_id,
                    session_id=chat_id,
                    metadata={
                        "bot_id": bot_id,
                        "chat_type": chat_type,
                        **(metadata or {}),
                    },
                    tags=[bot_id, chat_type] if bot_id else [],
                )
                generation = trace.generation(
                    name=f"{name}/generation",
                    model=model,
                    input=_safe_input(args, kwargs),
                )
            except Exception as e:
                logger.debug("[LangfuseObs] trace 创建失败: %s", e)

            try:
                result = await fn(*args, **kwargs)
                elapsed = time.time() - start

                if generation:
                    try:
                        output_text = _extract_output(result)
                        generation.end(
                            output=output_text[:2000] if output_text else "",
                            usage={
                                "input": _estimate_tokens(_safe_input(args, kwargs)),
                                "output": _estimate_tokens(output_text),
                            },
                            metadata={"latency_ms": round(elapsed * 1000)},
                        )
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)

                return result

            except Exception as e:
                if generation:
                    try:
                        generation.end(
                            output=f"ERROR: {e}",
                            level="ERROR",
                            status_message=str(e),
                        )
                    except Exception as e:
                        logger.debug("Silenced exception", exc_info=True)
                raise

        return wrapper

    return decorator


def log_generation(
    name: str,
    model: str,
    input_text: str,
    output_text: str,
    bot_id: str = "",
    user_id: str = "",
    chat_id: str = "",
    latency_ms: float = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    metadata: Optional[Dict] = None,
):
    """
    手动记录一次 LLM 调用（非装饰器模式）。

    适用于无法用装饰器包装的场景（如 free_api_pool 的回调式调用）。
    """
    if not _langfuse_client:
        return

    try:
        trace = _langfuse_client.trace(
            name=name,
            user_id=user_id or bot_id,
            session_id=chat_id,
            metadata={"bot_id": bot_id, **(metadata or {})},
            tags=[bot_id] if bot_id else [],
        )
        trace.generation(
            name=f"{name}/generation",
            model=model,
            input=input_text[:2000],
            output=output_text[:2000],
            usage={
                "input": input_tokens or _estimate_tokens(input_text),
                "output": output_tokens or _estimate_tokens(output_text),
            },
            metadata={"latency_ms": round(latency_ms)},
        )
    except Exception as e:
        logger.debug("[LangfuseObs] log_generation 失败: %s", e)


def log_event(name: str, metadata: Dict[str, Any] = None):
    """记录非 LLM 事件（如工具调用、错误等）"""
    if not _langfuse_client:
        return
    try:
        _langfuse_client.trace(
            name=name,
            metadata=metadata or {},
        )
    except Exception:
        logger.debug("Silenced exception", exc_info=True)


def flush():
    """刷新待发送的观测数据"""
    if _langfuse_client:
        try:
            _langfuse_client.flush()
        except Exception:
            logger.debug("Silenced exception", exc_info=True)


def shutdown():
    """关闭 Langfuse 客户端"""
    global _langfuse_client
    if _langfuse_client:
        try:
            _langfuse_client.flush()
            _langfuse_client.shutdown()
        except Exception:
            logger.debug("Silenced exception", exc_info=True)
        _langfuse_client = None


def get_stats() -> Dict[str, Any]:
    """获取观测层状态"""
    return {
        "available": _langfuse_available,
        "connected": _langfuse_client is not None,
        "host": os.getenv("LANGFUSE_HOST", "not configured"),
    }


# ── 内部工具 ──


def _safe_input(args, kwargs) -> str:
    """安全提取调用输入"""
    try:
        # 尝试从 messages 参数提取
        messages = None
        if args:
            for a in args:
                if isinstance(a, list) and a and isinstance(a[0], dict):
                    messages = a
                    break
        if not messages:
            messages = kwargs.get("messages", [])
        if messages:
            last = messages[-1] if messages else {}
            return str(last.get("content", ""))[:1000]
        # 回退：取第一个字符串参数
        for a in args:
            if isinstance(a, str):
                return a[:1000]
        return str(kwargs)[:500]
    except Exception as e:  # noqa: F841
        return ""


def _extract_output(result) -> str:
    """从各种返回格式中提取输出文本"""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return str(result.get("raw", result.get("text", result.get("content", ""))))
    return str(result)[:500] if result else ""


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文约 1.5 字/token，英文约 4 字符/token）"""
    if not text:
        return 0
    # 简单启发式：中文字符数 * 0.7 + 英文单词数
    cn_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    en_words = len(text.encode("ascii", "ignore").split())
    return max(1, int(cn_chars * 0.7 + en_words + len(text) / 6))
