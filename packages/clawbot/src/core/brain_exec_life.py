"""
Core — 生活服务领域执行器 Mixin

包含智能购物比价、平台搜索、预订服务、天气/提醒/汇率等方法。
从 brain_executors.py 拆分以降低扇出复杂度。
"""

import logging
from typing import Dict

from config.prompts import SOUL_CORE
from src.constants import FAMILY_DEEPSEEK, FAMILY_QWEN
from src.resilience import api_limiter

logger = logging.getLogger(__name__)


class LifeExecutorMixin:
    """生活服务领域执行器"""

    async def _exec_smart_shopping(self, params: Dict) -> Dict:
        """
        智能购物比价 — 三级降级链:
          1. crawl4ai 结构化抽取（CSS/LLM，实时爬取真实价格）
          2. Jina + LLM 分析（网页搜索 + LLM 总结）
          3. 纯 LLM 知识回答（最终降级）
        """
        product = params.get("product", "")
        if not product:
            return {"source": "error", "note": "未指定商品"}

        # ── 第〇级: Tavily 智能搜索 ──
        try:
            from src.tools.tavily_search import search_context, _HAS_TAVILY

            if _HAS_TAVILY:
                logger.info("[比价] 使用 Tavily 搜索: %s", product)
                tavily_ctx = await search_context(f"{product} 价格对比 京东 淘宝 拼多多", max_results=5)
                if tavily_ctx and len(tavily_ctx) > 200:
                    from src.litellm_router import free_pool

                    if free_pool:
                        async with api_limiter("llm"):
                            resp = await free_pool.acompletion(
                                model_family=FAMILY_DEEPSEEK,
                                messages=[
                                    {
                                        "role": "system",
                                        "content": (
                                            SOUL_CORE + "\n\n你现在在做购物比价任务。"
                                            "根据搜索结果提供各平台价格对比和购买建议。"
                                            '输出JSON格式: {"products":[{"name":"商品名","price":"价格",'
                                            '"platform":"平台","note":"备注"}],'
                                            '"recommendation":"购买建议","best_deal":"最佳选择",'
                                            '"tips":"省钱技巧"}'
                                        ),
                                    },
                                    {
                                        "role": "user",
                                        "content": (
                                            f"帮我比较 {product} 的价格。以下是搜索到的信息:\n{tavily_ctx[:3000]}"
                                        ),
                                    },
                                ],
                                max_tokens=600,
                                temperature=0.3,
                            )
                        content = resp.choices[0].message.content
                        if content:
                            try:
                                import json_repair

                                data = json_repair.loads(content)
                                if isinstance(data, dict):
                                    data["source"] = "tavily_smart_compare"
                                    data["product"] = product
                                    return data
                            except Exception:
                                logger.debug("Silenced exception", exc_info=True)
                            return {
                                "source": "tavily_smart_compare",
                                "product": product,
                                "raw": content,
                                "recommendation": content[:200],
                            }
        except ImportError:
            logger.debug("[比价] tavily_search 不可用")
        except Exception as e:
            logger.warning("[比价] Tavily 搜索异常: %s", e)

        # ── 第一级: crawl4ai 结构化比价 ──
        try:
            from src.shopping.crawl4ai_engine import smart_compare, HAS_CRAWL4AI

            if HAS_CRAWL4AI:
                logger.info("[比价] 使用 crawl4ai 引擎: %s", product)
                result = await smart_compare(product)
                if result.products and any(p.price > 0 for p in result.products):
                    data = result.to_dict()
                    data["product"] = product
                    return data
                else:
                    logger.info("[比价] crawl4ai 无有效结果，降级到 Jina+LLM")
        except ImportError:
            logger.debug("[比价] crawl4ai_engine 不可用")
        except Exception as e:
            logger.warning("[比价] crawl4ai 引擎异常: %s", e)

        # ── 第二级: Jina + LLM 分析 ──
        jina_context = ""
        try:
            from src.tools.jina_reader import jina_read
            import urllib.parse

            q = urllib.parse.quote(f"{product} 价格 对比")
            raw = await jina_read(f"https://cn.bing.com/shop?q={q}", max_length=3000)
            if raw and len(raw) > 200:
                jina_context = f"\n\n以下是网页搜索到的相关信息（用于参考）:\n{raw[:2000]}"
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        try:
            from src.litellm_router import free_pool

            if free_pool:
                async with api_limiter("llm"):
                    resp = await free_pool.acompletion(
                        model_family=FAMILY_DEEPSEEK,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    SOUL_CORE + "\n\n你现在在做购物比价任务。根据用户需求提供各平台价格对比和购买建议。"
                                    '输出JSON格式: {"products":[{"name":"商品名","price":"价格",'
                                    '"platform":"平台","note":"备注"}],'
                                    '"recommendation":"购买建议","best_deal":"最佳选择",'
                                    '"tips":"省钱技巧"}'
                                ),
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"帮我比较 {product} 在京东、淘宝、拼多多、苹果/官网等平台的价格。"
                                    f"给出购买建议和省钱技巧。{jina_context}"
                                ),
                            },
                        ],
                        max_tokens=600,
                        temperature=0.3,
                    )
                content = resp.choices[0].message.content
                if content:
                    try:
                        import json_repair

                        data = json_repair.loads(content)
                        if isinstance(data, dict):
                            data["source"] = "llm_smart_compare"
                            data["product"] = product
                            return data
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)
                    return {
                        "source": "llm_smart_compare",
                        "product": product,
                        "raw": content,
                        "recommendation": content[:200],
                    }
        except Exception as e:
            logger.warning("智能比价失败: %s", e)

        return {"source": "unavailable", "product": product, "note": "比价服务暂时不可用"}

    async def _exec_platform_search(self, params: Dict) -> Dict:
        """平台搜索 — 使用实际的 price_engine 函数"""
        platform = params.get("platform", "unknown")
        query = params.get("query", "")
        try:
            if platform == "smzdm":
                from src.shopping.price_engine import search_smzdm

                results = await search_smzdm(query)
                return {"source": "smzdm", "results": [r.__dict__ if hasattr(r, "__dict__") else r for r in results]}
            elif platform == "jd":
                from src.shopping.price_engine import search_jd

                results = await search_jd(query)
                return {"source": "jd", "results": [r.__dict__ if hasattr(r, "__dict__") else r for r in results]}
            else:
                from src.shopping.price_engine import compare_prices

                report = await compare_prices(query, limit_per_platform=5)
                if hasattr(report, "__dict__"):
                    return {"source": platform, "results": report.__dict__}
                return {"source": platform, "results": report if isinstance(report, dict) else str(report)}
        except ImportError as e:
            logger.warning("%s搜索: 模块不可用 (%s)", platform, e)
            return {"source": platform, "results": [], "note": f"{platform} 搜索模块未就绪"}
        except Exception as e:
            logger.warning("%s搜索失败: %s", platform, e)
            return {"source": platform, "results": [], "error": str(e)}

    async def _exec_rank_results(self, params: Dict) -> Dict:
        """排序筛选结果"""
        return {"source": "ranker", "ranked": [], "note": "汇总搜索结果并排序"}

    async def _exec_present_options(self, params: Dict) -> Dict:
        """展示选项给用户"""
        return {"source": "presenter", "options": [], "note": "生成Inline Keyboard"}

    async def _exec_booking_search(self, params: Dict) -> Dict:
        """预订搜索 — Tavily 优先, Jina 降级"""
        goal = params.get("goal", params.get("query", ""))
        if not goal:
            return {"source": "booking_search", "results": [], "note": "未指定搜索内容"}

        raw = None
        search_source = "jina"
        try:
            from src.tools.tavily_search import search_context, _HAS_TAVILY

            if _HAS_TAVILY:
                tavily_raw = await search_context(f"{goal} 预约 预订 价格", max_results=5)
                if tavily_raw and len(tavily_raw) > 100:
                    raw = tavily_raw
                    search_source = "tavily"
        except Exception as e:
            logger.debug("[预订] Tavily 搜索失败: %s", e)

        if not raw:
            try:
                from src.tools.jina_reader import jina_search

                raw = await jina_search(f"{goal} 预约 预订 价格")
            except Exception as e:
                logger.debug("[预订] Jina 搜索失败: %s", e)

        if raw and len(raw) > 100:
            try:
                from src.litellm_router import free_pool

                if free_pool:
                    resp = await free_pool.acompletion(
                        model_family=FAMILY_QWEN,
                        messages=[{"role": "user", "content": f"从以下搜索结果中提取预订选项:\n{raw[:3000]}"}],
                        system_prompt='提取预订选项列表。JSON格式: {"results": [{"name": "名称", "price": "价格", "address": "地址", "rating": "评分", "url": "链接"}]}',
                        temperature=0.2,
                        max_tokens=800,
                    )
                    content = resp.choices[0].message.content
                    try:
                        import json_repair

                        data = json_repair.loads(content)
                        if isinstance(data, dict):
                            data["source"] = f"{search_source}_llm_search"
                            return data
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)
                    return {"source": f"{search_source}_search", "results": [], "raw": content[:500]}
            except Exception as e:
                logger.warning("预订搜索 LLM 结构化失败: %s", e)
        return {"source": "booking_search", "results": [], "note": "预订搜索暂不可用"}

    async def _exec_detect_booking_method(self, params: Dict) -> Dict:
        """检测预订方式"""
        return {"method": "browser", "fallback": "phone"}

    async def _exec_booking_execute(self, params: Dict) -> Dict:
        """执行预订 — browser-use (81k⭐) 自然语言浏览器自动化"""
        goal = params.get("goal", params.get("query", ""))
        url = params.get("url", "")
        try:
            from src.browser_use_bridge import get_browser_use

            browser = get_browser_use()
            if browser:
                task_desc = f"在网页上完成预订操作: {goal}"
                if url:
                    task_desc += f". 目标网站: {url}"
                result = await browser.run_task(task=task_desc, url=url, max_steps=15)
                if result.get("success"):
                    return {"source": "browser_use", "success": True, "result": result}
                return {"source": "browser_use", "success": False, "details": result}
        except Exception as e:
            logger.warning("浏览器预订失败: %s", e)
        return {"source": "booking_fallback", "success": False, "note": "浏览器自动化未就绪"}

    async def _exec_booking_phone(self, params: Dict) -> Dict:
        """电话预订"""
        return {"source": "voice_call", "status": "pending", "note": "需要Retell AI"}

    async def _exec_booking_confirm(self, params: Dict) -> Dict:
        """预订确认 — 检查执行结果"""
        upstream = params.get("_upstream_results", {})
        booking_result = upstream.get("execute", {}) if isinstance(upstream, dict) else {}
        if booking_result.get("success"):
            return {"source": "confirmation", "confirmed": True, "details": booking_result}
        return {"source": "confirmation", "confirmed": False, "note": "预订执行未成功，无法确认"}

    async def _exec_life_service(self, params: Dict) -> Dict:
        """生活服务 — 天气查询等"""
        goal = params.get("goal", "")
        city = params.get("city_hint", "")

        # 天气查询
        if "天气" in goal or city:
            try:
                from src.tools.free_apis import get_weather

                if not city:
                    import re

                    m = re.search(r"(.{1,4})天气|天气(.{1,4})", goal)
                    city = (m.group(1) or m.group(2)).strip() if m else "杭州"
                data = await get_weather(city)
                if data.get("forecasts"):
                    forecast_text = f"📍 {data.get('city', city)} 天气预报:\n"
                    for f in data["forecasts"][:4]:
                        forecast_text += (
                            f"  {f.get('date', '')} {f.get('dayweather', '')}"
                            f" {f.get('nighttemp', '')}-{f.get('daytemp', '')}°C\n"
                        )
                    return {"source": "weather", "city": city, "text": forecast_text, "forecasts": data["forecasts"]}
                return {"source": "weather", "city": city, "note": "天气数据暂不可用"}
            except Exception as e:
                logger.warning("天气查询失败: %s", e)

        # 提醒/日程
        if any(kw in goal for kw in ["提醒", "闹钟", "备忘", "remind"]):
            try:
                from src.execution.life_automation import create_reminder

                reminder = await create_reminder(goal)
                return {"source": "reminder", "data": reminder}
            except Exception as e:
                logger.warning("提醒设置失败: %s", e)

        # 汇率查询
        if any(kw in goal for kw in ["汇率", "换算", "兑换", "exchange"]):
            try:
                from src.tools.free_apis import get_exchange_rate

                data = await get_exchange_rate()
                return {"source": "exchange_rate", "data": data}
            except Exception as e:
                logger.warning("汇率查询失败: %s", e)

        return {"source": "life", "note": "生活服务模块开发中"}
