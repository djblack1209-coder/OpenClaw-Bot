"""
OpenClaw 图片理解 — 利用 LiteLLM 已有的 Vision 模型支持
零新依赖 — LiteLLM 原生支持 GPT-4o/Gemini/Claude Vision。

Usage:
    from src.tools.vision import analyze_image
    result = await analyze_image(image_bytes, "这张图里有什么？")
"""
import base64
import logging

from src.constants import FAMILY_GEMINI
from src.utils import scrub_secrets

logger = logging.getLogger(__name__)


async def analyze_image(
    image_bytes: bytes,
    prompt: str = "描述这张图片的内容",
    model_family: str = FAMILY_GEMINI,
) -> str | None:
    """用 Vision 模型分析图片。

    通过 litellm_router.free_pool 路由到支持 vision 的模型
    (Gemini Flash / GPT-4o / Claude 等)。

    Args:
        image_bytes: 原始图片字节
        prompt: 用户提示词
        model_family: 目标模型族 (默认 gemini，支持 vision 且免费)

    Returns:
        模型分析文本，失败返回 None
    """
    if not image_bytes:
        return None

    try:
        from src.litellm_router import free_pool

        b64 = base64.b64encode(image_bytes).decode()

        resp = await free_pool.acompletion(
            model_family=model_family,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                        },
                    },
                ],
            }],
            max_tokens=1000,
            no_cache=True,
        )
        content = resp.choices[0].message.content
        if content and content.strip():
            return content.strip()
        return None
    except Exception as e:
        logger.warning(f"Vision 分析失败: {scrub_secrets(str(e))}")
        return None
