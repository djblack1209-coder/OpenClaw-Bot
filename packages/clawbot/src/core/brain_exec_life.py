"""
Core — 生活服务领域执行器 Mixin

包含智能购物比价、平台搜索、预订服务、天气/提醒/汇率等方法。
从 brain_executors.py 拆分以降低扇出复杂度。
"""

import logging

from src.constants import FAMILY_QWEN

logger = logging.getLogger(__name__)


class LifeExecutorMixin:
    """生活服务领域执行器"""

    async def _exec_smart_shopping(self, params: dict) -> dict:
        """智能购物比价 — 委托给统一比价引擎 smart_compare_prices()

        降级链由 price_engine.smart_compare_prices() 内部管理:
          1. SMZDM+JD 直接爬取
          2. Tavily 智能搜索
          3. crawl4ai 结构化提取
          4. Jina+LLM 分析
        """
        product = params.get("product", "")
        if not product:
            return {"source": "error", "note": "未指定商品"}

        try:
            from src.shopping.price_engine import smart_compare_prices

            report = await smart_compare_prices(
                product, use_ai_summary=True
            )

            # 将 ComparisonReport 转为 brain 层期望的 dict 格式
            data: dict = {
                "source": "smart_compare",
                "product": product,
                "platforms_searched": report.searched_platforms,
            }

            if report.results:
                # 转换为 brain 层的产品列表格式
                data["products"] = [
                    {
                        "name": r.get("title", ""),
                        "price": str(r.get("price", 0)),
                        "platform": r.get("platform", ""),
                        "note": r.get("shop", ""),
                    }
                    for r in report.results[:10]
                    if r.get("price", 0) > 0
                ]

            if report.best_deal:
                best = report.best_deal
                data["best_deal"] = (
                    f"{best.get('title', '')} — ¥{best.get('price', 0)} "
                    f"({best.get('platform', '')})"
                )

            if report.ai_summary:
                data["recommendation"] = report.ai_summary

            return data

        except ImportError:
            logger.warning("[比价] price_engine.smart_compare_prices 不可用")
        except Exception as e:
            logger.warning("[比价] 智能比价异常: %s", e)

        return {"source": "unavailable", "product": product, "note": "比价服务暂时不可用"}

    async def _exec_platform_search(self, params: dict) -> dict:
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

    async def _exec_rank_results(self, params: dict) -> dict:
        """排序筛选结果"""
        return {"source": "ranker", "ranked": [], "note": "汇总搜索结果并排序"}

    async def _exec_present_options(self, params: dict) -> dict:
        """展示选项给用户"""
        return {"source": "presenter", "options": [], "note": "生成Inline Keyboard"}

    async def _exec_booking_search(self, params: dict) -> dict:
        """预订搜索 — Tavily 优先, Jina 降级"""
        goal = params.get("goal", params.get("query", ""))
        if not goal:
            return {"source": "booking_search", "results": [], "note": "未指定搜索内容"}

        raw = None
        search_source = "jina"
        try:
            from src.tools.tavily_search import _HAS_TAVILY, search_context

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

    async def _exec_detect_booking_method(self, params: dict) -> dict:
        """检测预订方式"""
        return {"method": "browser", "fallback": "phone"}

    async def _exec_booking_execute(self, params: dict) -> dict:
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

    async def _exec_booking_phone(self, params: dict) -> dict:
        """电话预订"""
        return {"source": "voice_call", "status": "pending", "note": "需要Retell AI"}

    async def _exec_booking_confirm(self, params: dict) -> dict:
        """预订确认 — 检查执行结果"""
        upstream = params.get("_upstream_results", {})
        booking_result = upstream.get("execute", {}) if isinstance(upstream, dict) else {}
        if booking_result.get("success"):
            return {"source": "confirmation", "confirmed": True, "details": booking_result}
        return {"source": "confirmation", "confirmed": False, "note": "预订执行未成功，无法确认"}

    async def _exec_life_service(self, params: dict) -> dict:
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
