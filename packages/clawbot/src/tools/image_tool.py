"""
ClawBot - 图片生成工具 (硅基流动)
"""
import base64
import httpx
import urllib.parse
from typing import Dict, Any, Optional
from pathlib import Path
import logging
from src.utils import now_et
from src.constants import IMG_MODEL_FLUX

logger = logging.getLogger(__name__)


class ImageTool:
    """图片生成"""

    MODELS = {
        "flux": "black-forest-labs/FLUX.1-schnell",
        "sd3": "stabilityai/stable-diffusion-3-medium",
        "sdxl": "stabilityai/stable-diffusion-xl-base-1.0",
    }

    def __init__(self, api_key: Optional[str] = None, output_dir: Optional[str] = None):
        self.api_key = api_key
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            # 优先使用环境变量，否则使用项目目录
            import os
            env_dir = os.getenv('IMAGE_DIR')
            if env_dir:
                self.output_dir = Path(env_dir)
            else:
                self.output_dir = Path(__file__).parent.parent.parent / "images"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def set_api_key(self, key: str):
        self.api_key = key

    def _save_image_bytes(self, img_bytes: bytes, prefix: str = "gen") -> str:
        timestamp = now_et().strftime("%Y%m%d_%H%M%S_%f")
        filepath = self.output_dir / f"{prefix}_{timestamp}.png"
        with open(filepath, "wb") as f:
            f.write(img_bytes)
        return str(filepath)

    async def _generate_via_pollinations(self, prompt: str, model: str, size: str) -> Dict[str, Any]:
        width, height = map(int, size.split("x"))
        encoded_prompt = urllib.parse.quote(prompt.strip())
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={width}&height={height}&model={urllib.parse.quote(model or 'flux')}&nologo=true&safe=true"
        )
        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                raise RuntimeError(f"fallback 返回异常内容: {content_type or 'unknown'}")
            path = self._save_image_bytes(response.content, prefix="pollinations")
        return {"success": True, "prompt": prompt, "model": f"{model}-fallback", "paths": [path], "provider": "pollinations"}

    async def generate(self, prompt: str, model: str = IMG_MODEL_FLUX, size: str = "1024x1024") -> Dict[str, Any]:
        """生成图片"""
        if not self.api_key:
            return await self._generate_via_pollinations(prompt, model, size)

        model_id = self.MODELS.get(model, self.MODELS[IMG_MODEL_FLUX])

        try:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
            width, height = map(int, size.split("x"))

            payload = {
                "model": model_id,
                "prompt": prompt,
                "image_size": f"{width}x{height}",
                "num_inference_steps": 20,
                "batch_size": 1
            }

            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    "https://api.siliconflow.cn/v1/images/generations",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                result = response.json()

            images = result.get("images", [])
            if not images:
                return {"success": False, "error": "未生成图片"}

            saved_paths = []

            for i, img_data in enumerate(images):
                img_url = img_data.get("url", "")
                if img_url:
                    async with httpx.AsyncClient(timeout=30) as client:
                        img_response = await client.get(img_url)
                        img_bytes = img_response.content
                else:
                    img_b64 = img_data.get("b64_json", "")
                    img_bytes = base64.b64decode(img_b64)

                saved_paths.append(self._save_image_bytes(img_bytes, prefix=f"gen_{i}"))

            return {"success": True, "prompt": prompt, "model": model, "paths": saved_paths}

        except Exception as e:
            logger.warning("SiliconFlow image generation failed, falling back to Pollinations: %s", e)
            try:
                return await self._generate_via_pollinations(prompt, model, size)
            except Exception as fallback_error:
                return {"success": False, "error": f"{e}; fallback failed: {fallback_error}"}
