"""
OpenClaw — fal.ai 多模态生成客户端
搬运 fal-client (874⭐) 的核心模式。

统一接口: 图像生成 / 视频生成 / 语音识别 / 图像编辑。
零本地GPU: 所有推理在 fal.ai 云端运行。

用法:
    url = await generate_image("一只可爱的猫咪在喝咖啡")
    url = await generate_video("dancing robot in cyberpunk city")
"""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_fal_key() -> str:
    return os.environ.get("FAL_KEY", "")


async def generate_image(
    prompt: str,
    model: str = "fal-ai/flux/schnell",
    size: str = "landscape_16_9",
    num_images: int = 1,
) -> Optional[str]:
    """
    AI 图像生成 — fal.ai 云端。

    可用模型:
      - fal-ai/flux/schnell (快速, 免费额度)
      - fal-ai/flux/dev (高质量)
      - fal-ai/seedream-3 (Seedream 3.0)
      - fal-ai/stable-diffusion-v35-large (SD 3.5)

    Args:
        prompt: 图像描述
        model: fal.ai 模型 endpoint
        size: 尺寸 (square_hd/landscape_16_9/portrait_4_3)
        num_images: 生成数量

    Returns:
        图像 URL，失败返回 None
    """
    key = _get_fal_key()
    if not key:
        logger.warning("FAL_KEY 未设置")
        return None

    # 优先 fal_client SDK
    try:
        import fal_client
        os.environ["FAL_KEY"] = key
        result = await fal_client.run_async(
            model,
            arguments={
                "prompt": prompt,
                "image_size": size,
                "num_images": num_images,
            },
        )
        images = result.get("images", [])
        if images:
            url = images[0].get("url", "")
            logger.info(f"fal.ai 图像生成成功: {model}")
            return url
        return None
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"fal_client 失败: {e}")

    # 降级: HTTP 直调
    try:
        import httpx
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"https://queue.fal.run/{model}",
                headers={"Authorization": f"Key {key}", "Content-Type": "application/json"},
                json={"prompt": prompt, "image_size": size, "num_images": num_images},
            )
            if resp.status_code == 200:
                data = resp.json()
                images = data.get("images", [])
                if images:
                    return images[0].get("url", "")
            else:
                logger.warning(f"fal.ai HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"fal.ai HTTP 失败: {e}")
    return None


async def generate_video(
    prompt: str,
    duration: str = "5",
    model: str = "fal-ai/kling-video/v1/standard/text-to-video",
) -> Optional[str]:
    """
    AI 视频生成 — fal.ai 云端 (Kling/Seedance)。

    可用模型:
      - fal-ai/kling-video/v1/standard/text-to-video
      - fal-ai/kling-video/v1.5/pro/text-to-video
      - fal-ai/minimax-video

    Returns:
        视频 URL
    """
    key = _get_fal_key()
    if not key:
        logger.warning("FAL_KEY 未设置")
        return None

    try:
        import fal_client
        os.environ["FAL_KEY"] = key
        result = await fal_client.run_async(
            model,
            arguments={"prompt": prompt, "duration": duration},
        )
        video = result.get("video", {})
        url = video.get("url", "") if isinstance(video, dict) else ""
        if url:
            logger.info(f"fal.ai 视频生成成功: {model}")
            return url
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"fal.ai 视频生成失败: {e}")

    # HTTP fallback
    try:
        import httpx
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"https://queue.fal.run/{model}",
                headers={"Authorization": f"Key {key}", "Content-Type": "application/json"},
                json={"prompt": prompt, "duration": duration},
            )
            if resp.status_code == 200:
                data = resp.json()
                video = data.get("video", {})
                return video.get("url", "") if isinstance(video, dict) else None
    except Exception as e:
        logger.warning(f"fal.ai 视频 HTTP 失败: {e}")
    return None


async def image_to_image(
    image_url: str,
    prompt: str,
    model: str = "fal-ai/flux/dev/image-to-image",
    strength: float = 0.75,
) -> Optional[str]:
    """图像编辑/风格转换"""
    key = _get_fal_key()
    if not key:
        return None
    try:
        import fal_client
        os.environ["FAL_KEY"] = key
        result = await fal_client.run_async(
            model,
            arguments={
                "prompt": prompt,
                "image_url": image_url,
                "strength": strength,
            },
        )
        images = result.get("images", [])
        return images[0].get("url") if images else None
    except Exception as e:
        logger.warning(f"fal.ai img2img 失败: {e}")
    return None


def get_available_models() -> Dict[str, str]:
    """列出可用模型"""
    return {
        "flux_schnell": "fal-ai/flux/schnell",
        "flux_dev": "fal-ai/flux/dev",
        "seedream_3": "fal-ai/seedream-3",
        "sd_35": "fal-ai/stable-diffusion-v35-large",
        "kling_video": "fal-ai/kling-video/v1/standard/text-to-video",
        "kling_video_pro": "fal-ai/kling-video/v1.5/pro/text-to-video",
        "minimax_video": "fal-ai/minimax-video",
    }
