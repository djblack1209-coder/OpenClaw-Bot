"""
Core — 节点执行器 Mixin
包含所有 _exec_* 方法，负责执行各类 Agent 任务节点。
从 brain.py 拆分以改善可维护性。

> 最后更新: 2026-03-28
"""
import asyncio
import logging
import re
from typing import Dict

from config.prompts import SOUL_CORE, INFO_QUERY_PROMPT, INVEST_DIRECTOR_DECISION_PROMPT
from src.bot.error_messages import error_ai_busy

# 速率限制 — resilience 模块始终可导入，内部已做优雅降级
from src.resilience import api_limiter

logger = logging.getLogger(__name__)


class BrainExecutorMixin:
    """节点执行器 Mixin — 包含所有 _exec_* 方法"""

    async def _exec_investment_research(self, params: Dict) -> Dict:
        """投资研究 — 优先用 Pydantic AI 引擎，降级到原有 team"""
        symbol = params.get("symbol", "")
        if not symbol:
            return {"source": "no_symbol", "note": "未指定标的"}

        # 优先: Pydantic AI 结构化分析（iflow 无限 API）
        try:
            from src.modules.investment.pydantic_agents import get_pydantic_engine
            engine = get_pydantic_engine()
            if engine.available:
                result = await engine.full_analysis(symbol)
                return {
                    "source": "pydantic_engine",
                    "data": result.to_dict(),
                    "telegram_text": result.to_telegram_text(),
                    "recommendation": result.final_recommendation,
                    "vetoed": result.is_vetoed,
                }
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Pydantic 分析引擎失败: {e}")

        # 降级: 原有投资团队
        try:
            from src.modules.investment.team import get_investment_team
            team = get_investment_team()
            if team:
                analysis = await team.analyze(symbol)
                return {"source": "team", "data": analysis.to_dict()}
        except Exception as e:
            logger.warning(f"投资团队分析失败: {e}")

        return {"source": "unavailable", "note": "投资分析模块未就绪"}

    async def _exec_ta_analysis(self, params: Dict) -> Dict:
        """技术分析 — 复用现有 ta_engine"""
        try:
            from src.ta_engine import get_full_analysis
            symbol = params.get("symbol", "")
            if symbol:
                result = await get_full_analysis(symbol)
                return {"source": "ta_engine", "data": result}
        except Exception as e:
            logger.warning(f"技术分析失败: {e}")
        return {"source": "ta_unavailable", "note": "技术分析暂不可用"}

    async def _exec_quant_analysis(self, params: Dict) -> Dict:
        """量化分析 — 调用投资团队的量化工程师"""
        try:
            from src.modules.investment.team import get_investment_team
            team = get_investment_team()
            if team:
                return await team.quant_analysis(params.get("symbol", ""))
        except ImportError:
            pass
        return {"source": "quant_unavailable", "note": "量化分析模块未就绪"}

    async def _exec_risk_check(self, params: Dict) -> Dict:
        """风控审核 — 调用风控官"""
        try:
            from src.trading_system import get_risk_manager
            rm = get_risk_manager()
            if rm:
                check = rm.check_trade(
                    symbol=params.get("symbol", ""),
                    side="BUY",
                    quantity=100,
                    entry_price=0,
                )
                approved = check.approved if hasattr(check, 'approved') else True
                return {"source": "risk_manager", "approved": approved, "details": str(check)}
        except Exception as e:
            logger.warning(f"风控检查失败: {e}")
        # 降级：使用模块级单例
        try:
            from src.risk_manager import risk_manager
            check = risk_manager.check_trade(
                symbol=params.get("symbol", ""), side="BUY", quantity=100, entry_price=0,
            )
            approved = check.approved if hasattr(check, 'approved') else True
            return {"source": "risk_manager_singleton", "approved": approved}
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)
        # FAIL-CLOSED: 风控模块不可用时，拒绝交易而非默认放行
        return {"source": "risk_default", "approved": False,
                "note": "风控模块未就绪，安全起见默认拒绝（fail-closed）"}

    async def _exec_director_decision(self, params: Dict) -> Dict:
        """总监决策 — 汇总研究/TA/量化/风控结果做出最终决策"""
        symbol = params.get("symbol", "")
        try:
            from src.litellm_router import free_pool
            if free_pool:
                # Collect results from preceding nodes (passed via task graph context)
                context_summary = params.get("_upstream_results", "")
                async with api_limiter("llm"):
                    resp = await free_pool.acompletion(
                        model_family="deepseek",
                        messages=[{"role": "user", "content": f"Based on the analysis for {symbol}, give a final investment recommendation. Previous analysis: {context_summary}"}],
                        system_prompt=INVEST_DIRECTOR_DECISION_PROMPT,
                        temperature=0.3,
                        max_tokens=500,
                    )
                content = resp.choices[0].message.content
                try:
                    import json_repair
                    data = json_repair.loads(content)
                    if isinstance(data, dict):
                        data["source"] = "director_llm"
                        return data
                except Exception as e:
                    logger.debug("Silenced exception", exc_info=True)
                return {"source": "director_llm", "decision": "hold", "confidence": 0.5, "reasoning": content[:200]}
        except Exception as e:
            logger.warning(f"总监决策失败: {e}")
        return {"source": "director_fallback", "decision": "hold", "confidence": 0.0, "reasoning": "决策模块异常，默认持有"}

    async def _exec_trending_scan(self, params: Dict) -> Dict:
        """热点扫描 — 复用现有 real_trending"""
        try:
            from src.execution.social.real_trending import fetch_real_trending
            topics = await fetch_real_trending()
            return {"source": "real_trending", "topics": topics[:10]}
        except Exception as e:
            logger.warning(f"热点扫描失败: {e}")
            return {"source": "trending_fallback", "topics": []}

    async def _exec_social_intel(self, params: Dict) -> Dict:
        """社交数据采集 — MediaCrawler (46k⭐) 多平台爬虫"""
        platform = params.get("platform", "xhs")
        topic = params.get("content_hint", params.get("topic", ""))
        try:
            from src.execution.social.media_crawler_bridge import get_media_crawler, init_media_crawler
            crawler = get_media_crawler()
            if crawler is None:
                crawler = init_media_crawler()

            results = {}
            # Trending data for content inspiration
            try:
                trending = await asyncio.to_thread(crawler.get_trending, platform) if hasattr(crawler.get_trending, '__call__') else crawler.get_trending(platform)
                results["trending"] = trending[:10] if trending else []
            except Exception as e:  # noqa: F841
                results["trending"] = []

            # Search related content if topic provided
            if topic:
                try:
                    related = crawler.search_platform(platform, [topic], limit=5)
                    results["related_posts"] = related
                except Exception as e:  # noqa: F841
                    results["related_posts"] = []

            results["source"] = "media_crawler"
            results["platform"] = platform
            return results
        except Exception as e:
            logger.warning(f"社交数据采集失败: {e}")
        return {"source": "social_intel_unavailable", "trending": [], "related_posts": []}

    async def _exec_content_strategy(self, params: Dict) -> Dict:
        """内容策划 — 复用现有 content_strategy"""
        try:
            from src.execution.social.content_strategy import derive_content_strategy
            topic = params.get("content_hint", params.get("topic", "AI趋势"))
            result = await derive_content_strategy(topic=topic)
            return {"source": "content_strategy", "strategy": result}
        except Exception as e:
            logger.warning(f"内容策划失败: {e}")
            return {"source": "strategy_fallback", "strategy": {}}

    async def _exec_content_generate(self, params: Dict) -> Dict:
        """内容生成 — 调用 content_strategy.compose_post()"""
        try:
            from src.execution.social.content_strategy import compose_post
            topic = params.get("content_hint", params.get("topic", "AI趋势"))
            platform = params.get("platform", "x")
            strategy = params.get("strategy", {})
            draft = await compose_post(topic=topic, platform=platform, strategy=strategy)
            if draft:
                result_dict = {"source": "content_strategy", "draft": draft, "platform": platform, "topic": topic}
                # Try to generate an accompanying image
                try:
                    from src.tools.fal_client import generate_image
                    image_prompt = f"Social media post illustration for: {topic}"
                    image_url = await generate_image(image_prompt)
                    if image_url:
                        result_dict["image_url"] = image_url
                except Exception as e:
                    logger.debug("Silenced exception", exc_info=True)  # Image generation is optional
                return result_dict
        except Exception as e:
            logger.warning(f"内容生成失败: {e}")
        return {"source": "content_gen_fallback", "draft": "", "note": "内容生成模块异常"}

    async def _exec_social_publish(self, params: Dict) -> Dict:
        """社媒发布 — 调用对应平台发布函数"""
        platform = params.get("platform", "x")
        draft = params.get("draft", params.get("content", ""))
        if not draft:
            return {"source": "publish", "success": False, "note": "无内容可发布"}
        try:
            if platform in ("x", "twitter"):
                from src.execution.social.x_platform import publish_x_post
                result = await publish_x_post(content=draft)
                return {"source": "x_platform", "success": True, "result": result}
            elif platform in ("xhs", "xiaohongshu"):
                from src.execution.social.xhs_platform import publish_xhs_article
                result = await publish_xhs_article(title=draft[:30], content=draft)
                return {"source": "xhs_platform", "success": True, "result": result}
            else:
                # Generic: try worker bridge
                from src.execution.social.worker_bridge import run_social_worker_async
                result = await run_social_worker_async(f"publish_{platform}", {"content": draft})
                return {"source": "worker_bridge", "success": True, "result": result}
        except Exception as e:
            logger.warning(f"社媒发布失败 ({platform}): {e}")
        return {"source": "publish_fallback", "success": False, "note": f"{platform} 发布失败"}

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

        # ── 第〇级: Tavily 智能搜索（AI-native，最快）──
        try:
            from src.tools.tavily_search import search_context, _HAS_TAVILY
            if _HAS_TAVILY:
                logger.info(f"[比价] 使用 Tavily 搜索: {product}")
                tavily_ctx = await search_context(f"{product} 价格对比 京东 淘宝 拼多多", max_results=5)
                if tavily_ctx and len(tavily_ctx) > 200:
                    # 用 LLM 结构化 Tavily 结果
                    from src.litellm_router import free_pool
                    if free_pool:
                        async with api_limiter("llm"):
                            resp = await free_pool.acompletion(
                                model_family="deepseek",
                                messages=[
                                    {"role": "system", "content": (
                                        SOUL_CORE + "\n\n你现在在做购物比价任务。"
                                        "根据搜索结果提供各平台价格对比和购买建议。"
                                        "输出JSON格式: {\"products\":[{\"name\":\"商品名\",\"price\":\"价格\","
                                        "\"platform\":\"平台\",\"note\":\"备注\"}],"
                                        "\"recommendation\":\"购买建议\",\"best_deal\":\"最佳选择\","
                                        "\"tips\":\"省钱技巧\"}"
                                    )},
                                    {"role": "user", "content": (
                                        f"帮我比较 {product} 的价格。以下是搜索到的信息:\n{tavily_ctx[:3000]}"
                                    )},
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
                            except Exception as e:
                                logger.debug("Silenced exception", exc_info=True)
                            return {"source": "tavily_smart_compare", "product": product,
                                    "raw": content, "recommendation": content[:200]}
        except ImportError:
            logger.debug("[比价] tavily_search 不可用")
        except Exception as e:
            logger.warning(f"[比价] Tavily 搜索异常: {e}")

        # ── 第一级: crawl4ai 结构化比价 ──
        try:
            from src.shopping.crawl4ai_engine import smart_compare, HAS_CRAWL4AI
            if HAS_CRAWL4AI:
                logger.info(f"[比价] 使用 crawl4ai 引擎: {product}")
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
            logger.warning(f"[比价] crawl4ai 引擎异常: {e}")

        # ── 第二级: Jina + LLM 分析（原有方案）──
        # 1. 尝试 Jina 读取 Bing Shopping 获取实时数据
        jina_context = ""
        try:
            from src.tools.jina_reader import jina_read
            import urllib.parse
            q = urllib.parse.quote(f"{product} 价格 对比")
            raw = await jina_read(f"https://cn.bing.com/shop?q={q}", max_length=3000)
            if raw and len(raw) > 200:
                jina_context = f"\n\n以下是网页搜索到的相关信息（用于参考）:\n{raw[:2000]}"
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)

        # 2. 用 LLM 做智能比价分析（通过 litellm_router 统一路由）
        try:
            from src.litellm_router import free_pool
            if free_pool:
                async with api_limiter("llm"):
                    resp = await free_pool.acompletion(
                        model_family="deepseek",
                        messages=[
                            {"role": "system", "content": (
                                "你是专业购物比价助手。根据用户需求提供各平台价格对比和购买建议。"
                                "输出JSON格式: {\"products\":[{\"name\":\"商品名\",\"price\":\"价格\","
                                "\"platform\":\"平台\",\"note\":\"备注\"}],"
                                "\"recommendation\":\"购买建议\",\"best_deal\":\"最佳选择\","
                                "\"tips\":\"省钱技巧\"}"
                            )},
                            {"role": "user", "content": (
                                f"帮我比较 {product} 在京东、淘宝、拼多多、苹果/官网等平台的价格。"
                                f"给出购买建议和省钱技巧。{jina_context}"
                            )},
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
                    except Exception as e:
                        logger.debug("Silenced exception", exc_info=True)
                    return {"source": "llm_smart_compare", "product": product,
                            "raw": content, "recommendation": content[:200]}
        except Exception as e:
            logger.warning(f"智能比价失败: {e}")

        return {"source": "unavailable", "product": product, "note": "比价服务暂时不可用"}

    async def _exec_platform_search(self, params: Dict) -> Dict:
        """平台搜索 — 使用实际的 price_engine 函数"""
        platform = params.get("platform", "unknown")
        query = params.get("query", "")
        try:
            if platform == "smzdm":
                from src.shopping.price_engine import search_smzdm
                results = await search_smzdm(query)
                return {"source": "smzdm", "results": [r.__dict__ if hasattr(r, '__dict__') else r for r in results]}
            elif platform == "jd":
                from src.shopping.price_engine import search_jd
                results = await search_jd(query)
                return {"source": "jd", "results": [r.__dict__ if hasattr(r, '__dict__') else r for r in results]}
            else:
                # 其他平台用通用比价
                from src.shopping.price_engine import compare_prices
                report = await compare_prices(query, limit_per_platform=5)
                if hasattr(report, '__dict__'):
                    return {"source": platform, "results": report.__dict__}
                return {"source": platform, "results": report if isinstance(report, dict) else str(report)}
        except ImportError as e:
            logger.warning(f"{platform}搜索: 模块不可用 ({e})")
            return {"source": platform, "results": [], "note": f"{platform} 搜索模块未就绪"}
        except Exception as e:
            logger.warning(f"{platform}搜索失败: {e}")
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

        # 优先: Tavily search_context (AI-native, 结构化好)
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
            logger.debug(f"[预订] Tavily 搜索失败: {e}")

        # 降级: Jina search
        if not raw:
            try:
                from src.tools.jina_reader import jina_search
                raw = await jina_search(f"{goal} 预约 预订 价格")
            except Exception as e:
                logger.debug(f"[预订] Jina 搜索失败: {e}")

        if raw and len(raw) > 100:
            # Use LLM to structure the results
            try:
                from src.litellm_router import free_pool
                if free_pool:
                    resp = await free_pool.acompletion(
                        model_family="qwen",
                        messages=[{"role": "user", "content": f"从以下搜索结果中提取预订选项:\n{raw[:3000]}"}],
                        system_prompt='提取预订选项列表。JSON格式: {"results": [{"name": "名称", "price": "价格", "address": "地址", "rating": "评分", "url": "链接"}]}',
                        temperature=0.2, max_tokens=800,
                    )
                    content = resp.choices[0].message.content
                    try:
                        import json_repair
                        data = json_repair.loads(content)
                        if isinstance(data, dict):
                            data["source"] = f"{search_source}_llm_search"
                            return data
                    except Exception as e:
                        logger.debug("Silenced exception", exc_info=True)
                    return {"source": f"{search_source}_search", "results": [], "raw": content[:500]}
            except Exception as e:
                logger.warning(f"预订搜索 LLM 结构化失败: {e}")
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
            logger.warning(f"浏览器预订失败: {e}")
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

    async def _exec_llm_query(self, params: Dict) -> Dict:
        """LLM 信息查询 — 注入 SOUL_CORE 人格 + 对话上下文"""
        question = params.get("question", "")
        try:
            from src.litellm_router import free_pool
            if free_pool:
                messages = [
                    {"role": "system", "content": INFO_QUERY_PROMPT},
                ]
                # 注入对话上下文 (如果可用)
                ctx = params.get("_brain_context", {})
                recent = ctx.get("recent_messages", "")
                if recent:
                    messages.append({
                        "role": "system",
                        "content": f"最近对话:\n{recent}",
                    })
                messages.append({"role": "user", "content": question})

                async with api_limiter("llm"):
                    resp = await free_pool.acompletion(
                        model_family="qwen",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1000,
                    )
                answer = resp.choices[0].message.content
                return {"source": "llm", "answer": answer}
        except Exception as e:
            logger.warning(f"LLM查询失败: {e}")
        return {"source": "llm_fallback", "answer": error_ai_busy()}

    async def _exec_life_service(self, params: Dict) -> Dict:
        """生活服务 — 天气查询等"""
        goal = params.get("goal", "")
        city = params.get("city_hint", "")

        # 天气查询
        if "天气" in goal or city:
            try:
                from src.tools.free_apis import get_weather
                if not city:
                    # 从 goal 中提取城市名
                    import re
                    m = re.search(r'(.{1,4})天气|天气(.{1,4})', goal)
                    city = (m.group(1) or m.group(2)).strip() if m else "杭州"
                data = await get_weather(city)
                if data.get("forecasts"):
                    forecast_text = f"📍 {data.get('city', city)} 天气预报:\n"
                    for f in data["forecasts"][:4]:
                        forecast_text += (
                            f"  {f.get('date','')} {f.get('dayweather','')}"
                            f" {f.get('nighttemp','')}-{f.get('daytemp','')}°C\n"
                        )
                    return {"source": "weather", "city": city, "text": forecast_text, "forecasts": data["forecasts"]}
                return {"source": "weather", "city": city, "note": "天气数据暂不可用"}
            except Exception as e:
                logger.warning(f"天气查询失败: {e}")

        # 提醒/日程
        if any(kw in goal for kw in ["提醒", "闹钟", "备忘", "remind"]):
            try:
                from src.execution.life_automation import create_reminder
                reminder = await create_reminder(goal)
                return {"source": "reminder", "data": reminder}
            except Exception as e:
                logger.warning(f"提醒设置失败: {e}")

        # 汇率查询
        if any(kw in goal for kw in ["汇率", "换算", "兑换", "exchange"]):
            try:
                from src.tools.free_apis import get_exchange_rate
                data = await get_exchange_rate()
                return {"source": "exchange_rate", "data": data}
            except Exception as e:
                logger.warning(f"汇率查询失败: {e}")

        return {"source": "life", "note": "生活服务模块开发中"}

    async def _exec_portfolio_query(self, params: Dict) -> Dict:
        """持仓查询 — 先检查连接状态，避免超时等待"""
        try:
            from src.broker_selector import ibkr
            # 快速检查连接状态（不等待重连）
            if not getattr(ibkr, '_connected', False):
                return {"source": "portfolio", "positions": [],
                        "note": "券商未连接（IB Gateway 未运行）", "card_type": "portfolio"}
            positions = await ibkr.get_positions()
            summary = await ibkr.get_account_summary()
            return {"source": "ibkr", "positions": positions,
                    "summary": summary, "card_type": "portfolio"}
        except Exception as e:
            logger.warning(f"持仓查询失败: {e}")
        return {"source": "portfolio", "positions": [], "note": "券商未连接", "card_type": "portfolio"}

    async def _exec_system_status(self, params: Dict) -> Dict:
        """系统状态 — 复用现有 RPC"""
        try:
            from src.api.rpc import ClawBotRPC
            status = ClawBotRPC._rpc_system_status()
            return {"source": "rpc", "status": status}
        except Exception as e:
            logger.warning(f"获取系统状态失败: {e}")
            return {"source": "status_error", "error": str(e)}

    async def _exec_evolution_scan(self, params: Dict) -> Dict:
        """进化扫描 — 复用现有 evolution engine"""
        try:
            from src.evolution.engine import EvolutionEngine
            engine = EvolutionEngine()
            proposals = await engine.daily_scan()
            return {
                "source": "evolution",
                "proposals_count": len(proposals),
                "proposals": [p.to_dict() for p in proposals[:5]],
            }
        except Exception as e:
            logger.warning(f"进化扫描失败: {e}")
            return {"source": "evolution_error", "error": str(e)}

    async def _exec_code_task(self, params: Dict) -> Dict:
        """代码任务 — 调用 CodeTool 沙盒执行"""
        task_desc = params.get("task", "")
        try:
            from src.tools.code_tool import CodeTool
            tool = CodeTool()
            # If it looks like code, execute directly; otherwise ask LLM to generate code first
            if any(kw in task_desc for kw in ["import ", "def ", "print(", "for ", "class "]):
                result = await tool.execute_python(task_desc)
                return {"source": "code_tool", "output": result, "type": "direct_execution"}
            else:
                # Use LLM to generate code, then execute
                from src.litellm_router import free_pool
                if free_pool:
                    resp = await free_pool.acompletion(
                        model_family="deepseek",
                        messages=[{"role": "user", "content": task_desc}],
                        system_prompt=SOUL_CORE + "\n\n你现在在做代码生成任务。只输出可执行的Python代码，不要解释。用```python代码块包裹。",
                        temperature=0.2, max_tokens=2000,
                    )
                    code = resp.choices[0].message.content
                    # Extract code from markdown block
                    import re
                    code_match = re.search(r'```python\s*(.*?)```', code, re.DOTALL)
                    if code_match:
                        code = code_match.group(1).strip()
                    result = await tool.execute_python(code)
                    return {"source": "code_tool_llm", "code": code[:500], "output": result}
        except Exception as e:
            logger.warning(f"代码任务失败: {e}")
        return {"source": "code_fallback", "note": "代码执行模块异常"}
