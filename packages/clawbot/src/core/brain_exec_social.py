"""
Core — 社媒运营领域执行器 Mixin

包含热点扫描、社交数据采集、内容策划、内容生成、社媒发布等方法。
从 brain_executors.py 拆分以降低扇出复杂度。
"""

import asyncio
import logging

from src.utils import scrub_secrets

logger = logging.getLogger(__name__)


class SocialExecutorMixin:
    """社媒运营领域执行器"""

    async def _exec_trending_scan(self, params: dict) -> dict:
        """热点扫描 — 复用现有 real_trending"""
        try:
            from src.execution.social.real_trending import fetch_real_trending

            topics = await fetch_real_trending()
            return {"source": "real_trending", "topics": topics[:10]}
        except Exception as e:
            logger.warning(f"热点扫描失败: {scrub_secrets(str(e))}")
            return {"source": "trending_fallback", "topics": []}

    async def _exec_social_intel(self, params: dict) -> dict:
        """社交数据采集 — MediaCrawler (46k⭐) 多平台爬虫"""
        platform = params.get("platform", "xhs")
        topic = params.get("content_hint", params.get("topic", ""))
        try:
            from src.execution.social.media_crawler_bridge import get_media_crawler, init_media_crawler

            crawler = get_media_crawler()
            if crawler is None:
                crawler = init_media_crawler()

            results = {}
            try:
                trending = (
                    await asyncio.to_thread(crawler.get_trending, platform)
                    if hasattr(crawler.get_trending, "__call__")
                    else crawler.get_trending(platform)
                )
                results["trending"] = trending[:10] if trending else []
            except Exception:
                results["trending"] = []

            if topic:
                try:
                    related = crawler.search_platform(platform, [topic], limit=5)
                    results["related_posts"] = related
                except Exception:
                    results["related_posts"] = []

            results["source"] = "media_crawler"
            results["platform"] = platform
            return results
        except Exception as e:
            logger.warning(f"社交数据采集失败: {scrub_secrets(str(e))}")
        return {"source": "social_intel_unavailable", "trending": [], "related_posts": []}

    async def _exec_content_strategy(self, params: dict) -> dict:
        """内容策划 — 复用现有 content_strategy"""
        try:
            from src.execution.social.content_strategy import derive_content_strategy

            topic = params.get("content_hint", params.get("topic", "AI趋势"))
            result = await derive_content_strategy(topic=topic)
            return {"source": "content_strategy", "strategy": result}
        except Exception as e:
            logger.warning(f"内容策划失败: {scrub_secrets(str(e))}")
            return {"source": "strategy_fallback", "strategy": {}}

    async def _exec_content_generate(self, params: dict) -> dict:
        """内容生成 — 调用 content_strategy.compose_post()"""
        try:
            from src.execution.social.content_strategy import compose_post

            topic = params.get("content_hint", params.get("topic", "AI趋势"))
            platform = params.get("platform", "x")
            strategy = params.get("strategy", {})
            draft = await compose_post(topic=topic, platform=platform, strategy=strategy)
            if draft:
                result_dict = {"source": "content_strategy", "draft": draft, "platform": platform, "topic": topic}
                # 尝试生成配图
                try:
                    from src.tools.fal_client import generate_image

                    image_prompt = f"Social media post illustration for: {topic}"
                    image_url = await generate_image(image_prompt)
                    if image_url:
                        result_dict["image_url"] = image_url
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)
                return result_dict
        except Exception as e:
            logger.warning(f"内容生成失败: {scrub_secrets(str(e))}")
        return {"source": "content_gen_fallback", "draft": "", "note": "内容生成模块异常"}

    async def _exec_social_publish(self, params: dict) -> dict:
        """社媒发布 — 通过适配器统一分发到对应平台"""
        platform = params.get("platform", "x")
        draft = params.get("draft", params.get("content", ""))
        if not draft:
            return {"source": "publish", "success": False, "note": "无内容可发布"}
        try:
            from src.execution.social.platform_adapter import get_adapter

            adapter = get_adapter(platform)
            if adapter:
                result = await adapter.publish(content=draft)
                return {"source": f"{adapter.platform_id}_platform", "success": True, "result": result}
            else:
                # 未注册的平台 — 降级到 worker_bridge
                from src.execution.social.worker_bridge import run_social_worker_async

                result = await run_social_worker_async(f"publish_{platform}", {"content": draft})
                return {"source": "worker_bridge", "success": True, "result": result}
        except Exception as e:
            logger.warning(f"社媒发布失败 ({platform}): {scrub_secrets(str(e))}")
        return {"source": "publish_fallback", "success": False, "note": f"{platform} 发布失败"}
