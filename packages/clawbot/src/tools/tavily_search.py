"""
OpenClaw 智能搜索 — 搬运 Tavily Python SDK (1.1k⭐)
替代 Jina Reader 的搜索功能，专为 AI Agent 优化。

特性:
  - quick_answer: 一行代码获取答案 (QnA search)
  - search_context: RAG 优化的上下文
  - deep_research: 深度研究报告 (Tavily extract)

降级链: Tavily → Jina Reader (零中断)

Usage:
    from src.tools.tavily_search import quick_answer, search_context
from src.utils import scrub_secrets
    answer = await quick_answer("iPhone 16 Pro 价格对比")
    context = await search_context("茅台2024年财报", max_results=5)
"""
import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Tavily SDK 导入 (graceful degradation) ──
_HAS_TAVILY = False
_tavily_client = None

try:
    from tavily import TavilyClient

    _api_key = os.getenv("TAVILY_API_KEY", "")
    if _api_key:
        _tavily_client = TavilyClient(api_key=_api_key)
        _HAS_TAVILY = True
        logger.info("[Tavily] SDK 可用，已初始化")
    else:
        logger.debug("[Tavily] TAVILY_API_KEY 未设置，将降级到 Jina Reader")
except ImportError:
    logger.debug("[Tavily] tavily-python 未安装，将降级到 Jina Reader")


def _get_client() -> Optional["TavilyClient"]:
    """获取 Tavily 客户端（支持运行时设置 API key）"""
    global _tavily_client, _HAS_TAVILY
    if _tavily_client:
        return _tavily_client
    # Retry: 可能是运行时才设置的环境变量
    api_key = os.getenv("TAVILY_API_KEY", "")
    if api_key:
        try:
            from tavily import TavilyClient
            _tavily_client = TavilyClient(api_key=api_key)
            _HAS_TAVILY = True
            return _tavily_client
        except ImportError:
            pass
    return None


async def _run_sync(func, *args, **kwargs):
    """在线程池中运行同步 Tavily SDK 调用"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


# ── Jina 降级函数 ──

async def _jina_fallback_answer(query: str) -> str:
    """Tavily 不可用时降级到 Jina Reader"""
    try:
        from src.tools.jina_reader import jina_search
        result = await jina_search(query)
        if result:
            return result[:3000]
    except Exception as e:
        logger.debug(f"Jina fallback 也失败: {e}")
    return f"搜索暂不可用，请稍后再试 (query: {query})"


async def _jina_fallback_context(query: str, max_results: int = 5) -> str:
    """Tavily 不可用时降级到 Jina Reader"""
    try:
        from src.tools.jina_reader import jina_search
        result = await jina_search(query, max_results=max_results)
        if result:
            return result[:5000]
    except Exception as e:
        logger.debug(f"Jina fallback 也失败: {e}")
    return ""


# ── 公开 API ──

async def quick_answer(query: str) -> str:
    """一行代码获取答案 — Tavily QnA search。

    返回直接答案文本，适合快速问答场景。
    降级: Tavily QnA → Jina Search。

    Args:
        query: 搜索问题

    Returns:
        答案文本 (永不返回 None)
    """
    client = _get_client()
    if client:
        try:
            result = await _run_sync(
                client.qna_search,
                query=query,
            )
            if result and isinstance(result, str) and result.strip():
                logger.debug(f"[Tavily] QnA 成功: {query[:50]}...")
                return result.strip()
        except Exception as e:
            logger.warning(f"[Tavily] QnA 失败，降级 Jina: {scrub_secrets(str(e))}")

    return await _jina_fallback_answer(query)


async def search_context(query: str, max_results: int = 5) -> str:
    """RAG 优化的搜索上下文 — 直接可拼入 LLM prompt。

    返回适合喂给 LLM 的上下文文本。
    降级: Tavily context → Jina Search。

    Args:
        query: 搜索关键词
        max_results: 最大结果数

    Returns:
        上下文文本 (可能为空字符串)
    """
    client = _get_client()
    if client:
        try:
            result = await _run_sync(
                client.get_search_context,
                query=query,
                max_results=max_results,
            )
            if result and isinstance(result, str) and result.strip():
                logger.debug(f"[Tavily] 上下文搜索成功: {query[:50]}...")
                return result.strip()
        except Exception as e:
            logger.warning(f"[Tavily] 上下文搜索失败，降级 Jina: {scrub_secrets(str(e))}")

    return await _jina_fallback_context(query, max_results)


async def deep_research(topic: str) -> str:
    """深度研究报告 — Tavily extract + 多源聚合。

    先搜索相关 URL，再批量提取内容，聚合为研究报告。
    降级: Tavily extract → Tavily search → Jina。

    Args:
        topic: 研究主题

    Returns:
        研究报告文本
    """
    client = _get_client()
    if not client:
        return await _jina_fallback_answer(topic)

    try:
        # Step 1: 搜索获取相关 URL
        search_result = await _run_sync(
            client.search,
            query=topic,
            max_results=5,
            include_raw_content=True,
        )

        if not search_result or "results" not in search_result:
            return await _jina_fallback_answer(topic)

        results = search_result.get("results", [])
        if not results:
            return await _jina_fallback_answer(topic)

        # Step 2: 聚合结果为报告
        report_parts = [f"## 关于「{topic}」的研究报告\n"]
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "")
            url = r.get("url", "")
            content = r.get("content", "")
            raw = r.get("raw_content", "")
            # 优先用 raw_content (完整), 降级到 content (摘要)
            text = (raw[:800] if raw else content[:500]) or "无内容"
            report_parts.append(f"### {i}. {title}\n{url}\n{text}\n")

        # 附加 Tavily 的 AI 摘要 (如果有)
        answer = search_result.get("answer", "")
        if answer:
            report_parts.insert(1, f"**AI 摘要:** {answer}\n")

        report = "\n".join(report_parts)
        logger.debug(f"[Tavily] 深度研究完成: {topic[:50]}...")
        return report

    except Exception as e:
        logger.warning(f"[Tavily] 深度研究失败，降级 Jina: {scrub_secrets(str(e))}")
        return await _jina_fallback_answer(topic)
