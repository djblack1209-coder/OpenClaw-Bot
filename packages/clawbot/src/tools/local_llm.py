"""
本地 Hugging Face 轻量模型适配器

支持三种后端：Ollama / LM Studio / HF Inference Server
用于处理意图分类、摘要压缩等轻量任务，节省付费 API 配额

设计原则：
- 检测失败 → 静默返回 None → 调用方降级到付费 API
- 绝不参与涉及资金的决策（交易/风控）
- 后端检测结果缓存 60 秒，避免频繁探测
"""

import time
from typing import Optional

import httpx
from loguru import logger

# 支持的本地后端及其默认端点
_BACKENDS = {
    "ollama": {
        "health": "http://localhost:11434/api/tags",
        "generate": "http://localhost:11434/api/generate",
    },
    "lm_studio": {
        "health": "http://localhost:1234/v1/models",
        "generate": "http://localhost:1234/v1/chat/completions",
    },
    "hf_server": {
        "health": "http://localhost:8080/health",
        "generate": "http://localhost:8080/generate",
    },
}

# 适合本地模型的任务类型（轻量、规则性强、不涉及资金）
LOCAL_SUITABLE_TASKS = frozenset(
    {
        "intent_classify",  # 意图分类
        "summarize",  # 摘要压缩
        "keyword_extract",  # 关键词提取
        "sentiment_analysis",  # 情感分析
        "simple_reply",  # 简单回复（闲鱼客服等）
        "content_draft",  # 内容草稿
    }
)

# 后端检测缓存
_cached_backend: Optional[str] = None
_cache_time: float = 0.0
_CACHE_TTL = 60.0  # 缓存 60 秒


async def detect_backend(custom_endpoint: Optional[str] = None) -> Optional[str]:
    """
    自动检测可用的本地 LLM 后端

    优先级：自定义端点 > Ollama > LM Studio > HF Server
    检测结果缓存 60 秒，避免每次调用都探测

    Returns:
        后端名称（"ollama"/"lm_studio"/"hf_server"/"custom"）或 None
    """
    global _cached_backend, _cache_time

    # 缓存命中
    if _cached_backend and (time.monotonic() - _cache_time) < _CACHE_TTL:
        return _cached_backend

    async with httpx.AsyncClient(timeout=2.0) as client:
        # 优先检测自定义端点
        if custom_endpoint:
            try:
                resp = await client.get(custom_endpoint.rstrip("/"))
                if resp.status_code < 500:
                    _cached_backend = "custom"
                    _cache_time = time.monotonic()
                    logger.info("[LocalLLM] 检测到自定义后端: {}", custom_endpoint)
                    return "custom"
            except Exception:
                pass

        # 按优先级检测标准后端
        for name, urls in _BACKENDS.items():
            try:
                resp = await client.get(urls["health"])
                if resp.status_code < 500:
                    _cached_backend = name
                    _cache_time = time.monotonic()
                    logger.info("[LocalLLM] 检测到后端: {} ({})", name, urls["health"])
                    return name
            except Exception:
                continue

    _cached_backend = None
    _cache_time = time.monotonic()
    return None


async def local_complete(
    prompt: str,
    task_type: str = "general",
    max_tokens: int = 512,
    system: str = "你是一个简洁高效的助手，用中文回答。",
    custom_endpoint: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Optional[str]:
    """
    调用本地轻量模型完成任务

    如果本地模型不可用或任务类型不适合，返回 None（调用方降级到付费 API）

    Args:
        prompt: 用户提示词
        task_type: 任务类型，必须在 LOCAL_SUITABLE_TASKS 中
        max_tokens: 最大生成 token 数
        system: 系统提示词
        custom_endpoint: 自定义后端地址（覆盖自动检测）
        model_name: 指定模型名称（Ollama 用，如 "qwen2.5:1.5b"）

    Returns:
        生成的文本，或 None（表示需要降级到付费 API）
    """
    # 任务类型过滤
    if task_type not in LOCAL_SUITABLE_TASKS:
        return None

    backend = await detect_backend(custom_endpoint)
    if not backend:
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if backend == "ollama":
                resp = await client.post(
                    _BACKENDS["ollama"]["generate"],
                    json={
                        "model": model_name or "qwen2.5:1.5b",
                        "prompt": f"{system}\n\n{prompt}",
                        "stream": False,
                        "options": {"num_predict": max_tokens},
                    },
                )
                resp.raise_for_status()
                return resp.json().get("response", "").strip()

            elif backend == "lm_studio":
                resp = await client.post(
                    _BACKENDS["lm_studio"]["generate"],
                    json={
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.3,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()

            elif backend == "hf_server":
                resp = await client.post(
                    _BACKENDS["hf_server"]["generate"],
                    json={
                        "inputs": f"{system}\n\n{prompt}",
                        "parameters": {"max_new_tokens": max_tokens, "temperature": 0.3},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                # HF TGI 返回格式可能是 list 或 dict
                if isinstance(data, list) and data:
                    return data[0].get("generated_text", "").strip()
                elif isinstance(data, dict):
                    return data.get("generated_text", "").strip()
                return None

            elif backend == "custom" and custom_endpoint:
                # 自定义端点默认走 OpenAI 兼容格式
                base = custom_endpoint.rstrip("/")
                # 智能判断是否需要加 /v1/chat/completions
                url = base if "/v1/" in base else f"{base}/v1/chat/completions"
                resp = await client.post(
                    url,
                    json={
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.3,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logger.warning("[LocalLLM] 调用失败: {}，将降级到远程模型", e)
        # 清除缓存，下次重新检测
        _clear_cache()
        return None

    return None


def _clear_cache():
    """清除后端检测缓存"""
    global _cached_backend, _cache_time
    _cached_backend = None
    _cache_time = 0.0


# ──────────────────────────────────────────────
#  具体任务函数
# ──────────────────────────────────────────────


async def classify_intent(text: str, **kwargs) -> Optional[str]:
    """
    用本地模型做初步意图分类，减少送往付费 API 的流量

    返回 TaskType 枚举值（如 "INVESTMENT"）或 None（降级到付费 API）
    """
    prompt = (
        "判断以下用户消息属于哪个类别，只返回类别名称，不要解释：\n\n"
        "类别：INVESTMENT(投资交易) | SOCIAL(社媒运营) | SHOPPING(购物比价) | "
        "BOOKING(预订服务) | LIFE(生活服务) | CODE(代码开发) | INFO(信息查询) | "
        "COMMUNICATION(通信代理) | SYSTEM(系统管理)\n\n"
        f"用户消息：{text}\n类别："
    )
    result = await local_complete(prompt, task_type="intent_classify", max_tokens=20, **kwargs)
    if result:
        # 清理输出，只保留有效的类别名
        cleaned = result.strip().upper().split()[0] if result.strip() else None
        valid_types = {
            "INVESTMENT",
            "SOCIAL",
            "SHOPPING",
            "BOOKING",
            "LIFE",
            "CODE",
            "INFO",
            "COMMUNICATION",
            "SYSTEM",
        }
        if cleaned in valid_types:
            return cleaned
    return None


async def summarize_context(messages: list, max_chars: int = 500, **kwargs) -> Optional[str]:
    """
    压缩历史对话上下文，节省付费 token

    用于 /compact 命令，将最近 20 条消息压缩为摘要
    """
    joined = "\n".join(str(m) for m in messages[-20:])
    prompt = f"请用{max_chars}字以内总结以下对话的核心内容，保留关键信息：\n\n{joined}"
    return await local_complete(prompt, task_type="summarize", max_tokens=300, **kwargs)


async def extract_sentiment(text: str, **kwargs) -> Optional[str]:
    """
    分析文本情感倾向，用于投资新闻情绪分析

    Returns:
        "positive" | "negative" | "neutral" 或 None
    """
    prompt = f"分析以下文本的情感倾向，只回答 positive、negative 或 neutral：\n{text}"
    result = await local_complete(prompt, task_type="sentiment_analysis", max_tokens=10, **kwargs)
    if result:
        cleaned = result.lower().strip()
        if cleaned in ("positive", "negative", "neutral"):
            return cleaned
    return None


async def xianyu_quick_reply(buyer_message: str, floor_price: float, **kwargs) -> Optional[str]:
    """
    闲鱼客服：用本地模型生成快速应对砍价的回复

    底价相关的最终决策仍由规则引擎控制，本地模型只负责生成友好话术
    """
    prompt = (
        f"你是闲鱼卖家AI客服，底价是 {floor_price} 元。\n"
        f'买家说："{buyer_message}"\n'
        "生成一条礼貌友好的中文回复（不超过50字），不要主动降价："
    )
    return await local_complete(
        prompt,
        task_type="simple_reply",
        max_tokens=100,
        system="你是一个友好专业的二手交易卖家。",
        **kwargs,
    )


async def extract_keywords(text: str, top_n: int = 5, **kwargs) -> Optional[list]:
    """
    从文本中提取关键词，可替代部分 jieba 分词逻辑

    Returns:
        关键词列表 或 None
    """
    prompt = f"从以下文本中提取最重要的{top_n}个关键词，用逗号分隔，不要解释：\n{text}"
    result = await local_complete(prompt, task_type="keyword_extract", max_tokens=50, **kwargs)
    if result:
        keywords = [kw.strip() for kw in result.split(",") if kw.strip()]
        return keywords[:top_n] if keywords else None
    return None
