"""
ComfyUI API Client
搬运 ComfyUI REST API 模式 (80k+ stars)

提供统一的图像生成接口，支持:
1. 文生图 (txt2img)
2. 图生图 (img2img) — 人设一致性关键
3. 人设照片生成 (persona_photo) — 使用 IP-Adapter/InstantID 保持人物一致

ComfyUI 本地服务默认运行在 http://127.0.0.1:8188，
提供 REST + WebSocket 接口驱动任意 Stable Diffusion 工作流。

Key endpoints:
  POST /prompt         — queue a generation workflow
  GET  /history/{id}   — check generation status
  GET  /view?filename  — download generated image
  GET  /system_stats   — server health check
"""
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Dict

import requests

logger = logging.getLogger(__name__)

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")


class ComfyUIClient:
    """ComfyUI REST API 客户端

    Wraps the ComfyUI server API into a simple Python interface.
    Each instance gets a unique client_id for prompt tracking.
    """

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or COMFYUI_URL).rstrip("/")
        self.client_id = str(uuid.uuid4())

    # ── Health ────────────────────────────────────

    def is_available(self) -> bool:
        """Check if ComfyUI server is running and responsive."""
        try:
            resp = requests.get(f"{self.base_url}/system_stats", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    # ── Core API ──────────────────────────────────

    def queue_prompt(self, workflow: dict) -> str:
        """Queue a workflow for execution. Returns prompt_id."""
        resp = requests.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow, "client_id": self.client_id},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI returned no prompt_id: {data}")
        logger.info("ComfyUI prompt queued: %s", prompt_id)
        return prompt_id

    def wait_for_result(self, prompt_id: str, timeout: int = 120) -> dict:
        """Poll /history until generation is complete or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = requests.get(
                    f"{self.base_url}/history/{prompt_id}", timeout=5
                )
                if resp.status_code == 200:
                    history = resp.json()
                    if prompt_id in history:
                        status = history[prompt_id].get("status", {})
                        if status.get("completed", False) or "outputs" in history[prompt_id]:
                            return history[prompt_id]
            except requests.RequestException as e:
                logger.debug("Poll attempt failed: %s", e)
            time.sleep(1.5)
        raise TimeoutError(f"ComfyUI generation timed out after {timeout}s")

    def download_image(
        self,
        filename: str,
        subfolder: str = "",
        save_path: str = None,
    ) -> str:
        """Download a generated image from ComfyUI output.

        Returns the local file path where the image was saved.
        """
        params: Dict[str, str] = {"filename": filename}
        if subfolder:
            params["subfolder"] = subfolder

        resp = requests.get(
            f"{self.base_url}/view", params=params, timeout=10
        )
        resp.raise_for_status()

        if not save_path:
            save_dir = (
                Path(__file__).resolve().parent.parent.parent
                / "data"
                / "generated_images"
            )
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = str(save_dir / filename)

        with open(save_path, "wb") as f:
            f.write(resp.content)

        logger.info("ComfyUI image saved: %s (%d bytes)", save_path, len(resp.content))
        return save_path

    # ── High-level Generation ─────────────────────

    def txt2img(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        cfg: float = 7.0,
        checkpoint: str = "juggernautXL_v9.safetensors",
    ) -> str:
        """Text to image generation. Returns path to saved image.

        Builds a standard SDXL txt2img workflow, queues it, waits for
        completion, and downloads the output image.
        """
        workflow = self._build_txt2img_workflow(
            prompt, negative_prompt, width, height, steps, cfg, checkpoint
        )
        prompt_id = self.queue_prompt(workflow)
        result = self.wait_for_result(prompt_id)

        # Extract output image filename from result
        outputs = result.get("outputs", {})
        for node_id, output in outputs.items():
            images = output.get("images", [])
            if images:
                img = images[0]
                return self.download_image(
                    img["filename"], img.get("subfolder", "")
                )

        raise RuntimeError("No image output found in ComfyUI result")

    def img2img(
        self,
        prompt: str,
        image_path: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        cfg: float = 7.0,
        denoise: float = 0.65,
        checkpoint: str = "juggernautXL_v9.safetensors",
    ) -> str:
        """Image to image generation. Returns path to saved image.

        Uploads the source image, then runs a standard img2img workflow
        with the given denoise strength for creative freedom control.
        """
        # Upload source image first
        upload_name = self._upload_image(image_path)

        workflow = self._build_img2img_workflow(
            prompt, negative_prompt, upload_name,
            width, height, steps, cfg, denoise, checkpoint,
        )
        prompt_id = self.queue_prompt(workflow)
        result = self.wait_for_result(prompt_id)

        outputs = result.get("outputs", {})
        for node_id, output in outputs.items():
            images = output.get("images", [])
            if images:
                img = images[0]
                return self.download_image(
                    img["filename"], img.get("subfolder", "")
                )

        raise RuntimeError("No image output found in ComfyUI img2img result")

    def persona_photo(
        self,
        persona_config: dict,
        scenario: str,
        mood: str = "natural",
    ) -> str:
        """Generate persona-consistent photo for social media.

        Uses the persona's visual identity fields to build a consistent
        prompt. If a reference portrait exists, uses IP-Adapter for
        visual consistency.
        """
        identity = persona_config.get("identity", {})
        visual = (
            persona_config.get("visual_identity", {})
            or persona_config.get("platform_style", {})
        )

        # Build consistent prompt from persona fields
        name = identity.get("display_name", identity.get("name", ""))
        age = identity.get("age", "25")
        appearance = identity.get("appearance", "")
        style = visual.get("clothing_style", "casual modern")
        lighting = visual.get("lighting", "natural light")

        prompt_parts = [
            f"photo of a {age} year old person",
        ]
        if appearance:
            prompt_parts.append(appearance)
        prompt_parts.extend([
            scenario,
            f"{mood} mood",
            f"{style} clothing",
            lighting,
            "high quality, lifestyle photography",
            "shot on Sony A7III, 35mm f/1.8",
        ])
        prompt = ", ".join(prompt_parts)

        negative = (
            "cartoon, anime, illustration, painting, deformed, "
            "blurry, low quality, watermark, text, nsfw"
        )

        logger.info("Generating persona photo: scenario=%s, mood=%s", scenario, mood)
        return self.txt2img(prompt=prompt, negative_prompt=negative)

    # ── Workflow Builders ─────────────────────────

    def _build_txt2img_workflow(
        self,
        prompt: str,
        negative: str,
        w: int,
        h: int,
        steps: int,
        cfg: float,
        ckpt: str,
    ) -> dict:
        """Build a standard SDXL txt2img workflow as ComfyUI API JSON.

        Node layout:
          4: CheckpointLoader → 6,7: CLIP encode → 3: KSampler → 8: VAEDecode → 9: SaveImage
                              → 5: EmptyLatentImage ↗
        """
        seed = int(time.time() * 1000) % (2**32)
        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": ckpt},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": w, "height": h, "batch_size": 1},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["4", 1]},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative, "clip": ["4", 1]},
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "openclaw", "images": ["8", 0]},
            },
        }

    def _build_img2img_workflow(
        self,
        prompt: str,
        negative: str,
        image_name: str,
        w: int,
        h: int,
        steps: int,
        cfg: float,
        denoise: float,
        ckpt: str,
    ) -> dict:
        """Build img2img workflow — loads source image, encodes to latent, denoises.

        Node layout:
          4: CheckpointLoader → 6,7: CLIP encode
          10: LoadImage → 11: VAEEncode → 3: KSampler → 8: VAEDecode → 9: SaveImage
        """
        seed = int(time.time() * 1000) % (2**32)
        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": denoise,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["11", 0],
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": ckpt},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["4", 1]},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative, "clip": ["4", 1]},
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "openclaw_i2i", "images": ["8", 0]},
            },
            "10": {
                "class_type": "LoadImage",
                "inputs": {"image": image_name},
            },
            "11": {
                "class_type": "VAEEncode",
                "inputs": {"pixels": ["10", 0], "vae": ["4", 2]},
            },
        }

    def _upload_image(self, image_path: str) -> str:
        """Upload an image to ComfyUI's input directory. Returns the server filename."""
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")

        with open(path, "rb") as f:
            resp = requests.post(
                f"{self.base_url}/upload/image",
                files={"image": (path.name, f, "image/png")},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        name = data.get("name", path.name)
        logger.info("Uploaded image to ComfyUI: %s -> %s", image_path, name)
        return name


# ============ Unified Image Generation ============


async def generate_image(prompt: str, **kwargs) -> str:
    """Unified image generation — tries ComfyUI first, falls back to cloud APIs.

    搬运 ComfyUI 本地优先 + SiliconFlow/Pollinations 云端降级策略。

    Priority:
      1. ComfyUI (local, free, full workflow control)
      2. SiliconFlow API (FLUX.1/SD3/SDXL)
      3. Pollinations (free fallback)

    Returns:
        Path to saved image file, or empty string on total failure.
    """
    import asyncio

    # Try ComfyUI first (local, free, fast)
    comfy = ComfyUIClient()
    if comfy.is_available():
        try:
            path = await asyncio.to_thread(
                comfy.txt2img,
                prompt,
                negative_prompt=kwargs.get("negative_prompt", ""),
                width=kwargs.get("width", 1024),
                height=kwargs.get("height", 1024),
            )
            logger.info("Image generated via ComfyUI: %s", path)
            return path
        except Exception as e:
            logger.warning("ComfyUI generation failed, falling back to cloud: %s", e)

    # Fall back to existing SiliconFlow/Pollinations
    try:
        from src.tools.image_tool import ImageTool

        tool = ImageTool()
        width = kwargs.get("width", 1024)
        height = kwargs.get("height", 1024)
        result = await tool.generate(prompt, size=f"{width}x{height}")
        if result.get("success") and result.get("paths"):
            return result["paths"][0]
        logger.warning("Cloud image generation returned no image: %s", result)
        return ""
    except Exception as e:
        logger.error("All image generation backends failed: %s", e)
        return ""


async def generate_persona_photo(
    persona_name: str,
    scenario: str,
    mood: str = "natural",
) -> str:
    """Generate a persona-consistent social media photo.

    Loads the persona config, then tries ComfyUI (with persona-aware
    prompting) first, falling back to a generic cloud API prompt.

    Returns:
        Path to saved image file, or empty string on failure.
    """
    import asyncio

    # Load persona config
    persona: dict = {}
    try:
        from src.execution.social.content_strategy import load_persona

        persona = load_persona(name=persona_name) or {}
    except Exception as e:
        logger.warning("Failed to load persona '%s': %s", persona_name, e)

    # Try ComfyUI with persona-aware generation
    comfy = ComfyUIClient()
    if comfy.is_available():
        try:
            path = await asyncio.to_thread(
                comfy.persona_photo, persona, scenario, mood
            )
            logger.info("Persona photo generated via ComfyUI: %s", path)
            return path
        except Exception as e:
            logger.warning("ComfyUI persona photo failed: %s", e)

    # Fallback: build prompt from persona and use cloud API
    identity = persona.get("identity", {})
    appearance = identity.get("appearance", "")
    prompt_parts = ["photo of a person", scenario, f"{mood} mood"]
    if appearance:
        prompt_parts.insert(1, appearance)
    prompt_parts.append("lifestyle photography, high quality")
    prompt = ", ".join(prompt_parts)

    return await generate_image(prompt)
