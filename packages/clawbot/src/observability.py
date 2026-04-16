"""
OpenClaw LLM 可观测性 — 搬运 Arize Phoenix OTEL (9k⭐)
与现有 Langfuse 并行运行，通过 OpenTelemetry 标准协议。

提供:
  - LiteLLM 自动追踪（所有 completion/embedding 调用）
  - CrewAI 自动追踪（多 Agent 协作可视化）
  - 自定义 span 装饰器（任意函数追踪）
  - MCP Server 配置生成

启用:
  - 设置环境变量 PHOENIX_ENDPOINT=http://localhost:6006
  - 或 docker run -p 6006:6006 arizephoenix/phoenix:latest

架构说明:
  Langfuse — LiteLLM success_callback，HTTP 上报，Langfuse 私有协议
  Phoenix  — OpenTelemetry SDK，OTLP gRPC/HTTP，OTEL 标准协议
  两者独立运行，互不干扰。
"""

import logging
import os
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

# ── 类型变量 ──
F = TypeVar("F", bound=Callable[..., Any])

# ── Phoenix / OTEL 可用性检测 ──

_phoenix_available = False
_phoenix_initialized = False
_tracer = None  # OpenTelemetry tracer instance

try:
    from phoenix.otel import register as _phoenix_register

    _phoenix_available = True
except ImportError:
    _phoenix_register = None  # type: ignore[assignment]

_litellm_instrumentor_cls = None
try:
    from openinference.instrumentation.litellm import LiteLLMInstrumentor

    _litellm_instrumentor_cls = LiteLLMInstrumentor
except ImportError:
    logger.info("[Observability] openinference-instrumentation-litellm 未安装，跳过 LiteLLM instrumentor")

# CrewAI instrumentor — 可选，仅在安装了 openinference-instrumentation-crewai 时生效
_crewai_instrumentor_cls = None
try:
    from openinference.instrumentation.crewai import CrewAIInstrumentor  # type: ignore[import-untyped]

    _crewai_instrumentor_cls = CrewAIInstrumentor
except ImportError:
    logger.info("[Observability] openinference-instrumentation-crewai 未安装，跳过 CrewAI instrumentor")

# OpenTelemetry trace API — 用于自定义 span
_otel_trace = None
try:
    from opentelemetry import trace as _otel_trace
except ImportError:
    logger.info("[Observability] opentelemetry 未安装，跳过自定义 span 追踪")


# ============================================================
# 初始化
# ============================================================


def init_phoenix(
    project_name: str = "openclaw-bot",
    endpoint: Optional[str] = None,
) -> bool:
    """初始化 Phoenix OTEL 追踪。

    Args:
        project_name: Phoenix 项目名称，用于 UI 分组。
        endpoint: Phoenix collector endpoint。
                  默认读取 PHOENIX_ENDPOINT 环境变量。

    Returns:
        True 初始化成功，False 跳过或失败。
    """
    global _phoenix_initialized, _tracer

    if _phoenix_initialized:
        logger.debug("[Phoenix] 已初始化，跳过重复调用")
        return True

    if not _phoenix_available:
        logger.debug("[Phoenix] phoenix-otel 未安装，观测层禁用")
        return False

    endpoint = endpoint or os.getenv("PHOENIX_ENDPOINT", "")
    if not endpoint:
        logger.info("[Phoenix] 未配置 PHOENIX_ENDPOINT，观测层禁用")
        return False

    try:
        # phoenix.otel.register 会配置 OTEL TracerProvider + OTLP exporter
        tracer_provider = _phoenix_register(
            project_name=project_name,
            auto_instrument=True,
            endpoint=endpoint,
        )
        logger.info("[Phoenix] OTEL TracerProvider 已注册 (endpoint=%s)", endpoint)
    except Exception as e:
        logger.warning("[Phoenix] TracerProvider 注册失败: %s", e)
        return False

    # ── 安装 LiteLLM instrumentor ──
    if _litellm_instrumentor_cls:
        try:
            _litellm_instrumentor_cls().instrument(tracer_provider=tracer_provider)
            logger.info("[Phoenix] LiteLLM instrumentor 已安装")
        except Exception as e:
            logger.warning("[Phoenix] LiteLLM instrumentor 安装失败: %s", e)
    else:
        logger.debug("[Phoenix] openinference-instrumentation-litellm 未安装，跳过")

    # ── 安装 CrewAI instrumentor (可选) ──
    if _crewai_instrumentor_cls:
        try:
            _crewai_instrumentor_cls().instrument(tracer_provider=tracer_provider)
            logger.info("[Phoenix] CrewAI instrumentor 已安装")
        except Exception as e:
            logger.debug("[Phoenix] CrewAI instrumentor 安装失败: %s", e)

    # ── 获取 tracer 用于自定义 span ──
    if _otel_trace:
        _tracer = _otel_trace.get_tracer("openclaw-bot")

    _phoenix_initialized = True
    logger.info("[Phoenix] 初始化完成 (project=%s, endpoint=%s)", project_name, endpoint)
    return True


# ============================================================
# 自定义 span 装饰器
# ============================================================


def trace_function(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, str]] = None,
) -> Callable[[F], F]:
    """装饰器：为任意 async 函数创建 OTEL span。

    Phoenix 未初始化时透明退化为 noop。

    用法::

        @trace_function(name="parse_intent")
        async def parse_intent(text: str) -> dict:
            ...

        @trace_function(attributes={"component": "trading"})
        async def execute_trade(order):
            ...
    """

    def decorator(fn: F) -> F:
        span_name = name or f"{fn.__module__}.{fn.__qualname__}"

        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _tracer:
                return await fn(*args, **kwargs)

            with _tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    result = await fn(*args, **kwargs)
                    return result
                except Exception as e:
                    span.set_attribute("error", True)
                    span.set_attribute("error.message", str(e))
                    raise

        return wrapper  # type: ignore[return-value]

    return decorator


# ============================================================
# MCP Server 配置
# ============================================================


def get_mcp_config() -> Dict[str, Any]:
    """返回 Phoenix MCP Server 配置 dict，可直接写入 OpenCode / Cursor 配置。

    Phoenix MCP Server 允许 AI 编辑器直接查询 trace 数据。

    Returns:
        MCP server 配置字典。未配置 endpoint 时返回空 dict。
    """
    endpoint = os.getenv("PHOENIX_ENDPOINT", "")
    if not endpoint:
        return {}

    return {
        "phoenix": {
            "command": "npx",
            "args": ["-y", "arize-phoenix-mcp"],
            "env": {
                "PHOENIX_API_URL": endpoint,
            },
        }
    }


# ============================================================
# 工具函数
# ============================================================


def get_phoenix_url() -> Optional[str]:
    """返回 Phoenix UI 地址，未配置时返回 None。"""
    endpoint = os.getenv("PHOENIX_ENDPOINT", "")
    if not endpoint:
        return None
    # Phoenix UI 默认与 collector 同端口
    return endpoint.rstrip("/")


def get_stats() -> Dict[str, Any]:
    """获取 Phoenix 观测层状态。"""
    return {
        "available": _phoenix_available,
        "initialized": _phoenix_initialized,
        "endpoint": os.getenv("PHOENIX_ENDPOINT", "not configured"),
        "ui_url": get_phoenix_url(),
        "instrumentors": {
            "litellm": _litellm_instrumentor_cls is not None,
            "crewai": _crewai_instrumentor_cls is not None,
        },
    }
