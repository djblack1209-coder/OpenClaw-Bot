"""
Core — 任务图构建器 Mixin
包含所有 _build_*_graph 方法，负责将用户意图映射到具体的 Agent 执行图。
从 brain.py 拆分以改善可维护性。

> 最后更新: 2026-03-28
"""
import logging
from typing import Dict, Optional

from src.core.task_graph import TaskGraph, TaskGraphBuilder, ExecutorType
from src.core.intent_parser import ParsedIntent, TaskType

logger = logging.getLogger(__name__)


class BrainGraphBuilderMixin:
    """任务图构建器 Mixin — 根据意图类型构建具体的执行DAG"""

    async def _build_investment_graph(self, intent: ParsedIntent) -> TaskGraph:
        """
        投资分析任务图:
          如果没有具体标的（如"持仓"），走持仓查询路径
          如果有标的，走完整分析:
          [研究员] ─┐
          [TA分析] ─┤→ [风控审核] → [总监决策]
          [量化]   ─┘
        """
        symbol = intent.known_params.get("symbol_hint", "")

        # 持仓/仓位查询 — 不需要标的
        if not symbol or intent.goal in ("查看持仓状态",):
            b = TaskGraphBuilder("持仓查询")
            b.add("portfolio", "获取持仓", ExecutorType.LOCAL,
                  self._exec_portfolio_query,
                  params={}, timeout=15)
            return b.build()
        b = TaskGraphBuilder(f"投资分析: {symbol}")

        b.add("research", "基本面研究", ExecutorType.CREW,
              self._exec_investment_research,
              params={"symbol": symbol, "intent": intent.known_params},
              timeout=60)
        b.add("ta", "技术面分析", ExecutorType.CREW,
              self._exec_ta_analysis,
              params={"symbol": symbol},
              timeout=45)
        b.add("quant", "量化指标计算", ExecutorType.CREW,
              self._exec_quant_analysis,
              params={"symbol": symbol},
              timeout=45)
        b.add("risk", "风控审核", ExecutorType.CREW,
              self._exec_risk_check,
              params={"symbol": symbol},
              after=["research", "ta", "quant"],
              timeout=30)
        b.add("decision", "总监决策", ExecutorType.CREW,
              self._exec_director_decision,
              params={"symbol": symbol},
              after=["risk"],
              timeout=30)

        return b.build()

    async def _build_social_graph(self, intent: ParsedIntent) -> TaskGraph:
        """
        社媒发帖任务图:
          [热点扫描] → [内容策划] → [素材生成] → [发布]
        """
        b = TaskGraphBuilder(f"社媒发帖: {intent.goal}")

        b.add("trending", "热点扫描", ExecutorType.LOCAL,
              self._exec_trending_scan,
              params=intent.known_params, timeout=30)
        b.add("social_intel", "社交数据采集", ExecutorType.LOCAL,
              self._exec_social_intel,
              params=intent.known_params, timeout=30)
        b.add("strategy", "内容策划", ExecutorType.LLM,
              self._exec_content_strategy,
              params=intent.known_params,
              after=["trending", "social_intel"], timeout=45)
        b.add("generate", "内容生成", ExecutorType.LLM,
              self._exec_content_generate,
              params=intent.known_params,
              after=["strategy"], timeout=60)
        b.add("publish", "发布执行", ExecutorType.BROWSER,
              self._exec_social_publish,
              params=intent.known_params,
              after=["generate"], timeout=120)

        return b.build()

    async def _build_shopping_graph(self, intent: ParsedIntent) -> TaskGraph:
        """
        购物比价任务图 — 三级降级链:
          1. crawl4ai 结构化抽取（CSS/LLM，实时爬取真实价格）
          2. Jina+LLM 分析（网页搜索 + LLM 总结）
          3. 纯 LLM 知识回答（最终降级）
        """
        product = intent.known_params.get("product_hint", intent.goal)
        b = TaskGraphBuilder(f"购物比价: {product}")

        b.add("compare", "智能比价分析", ExecutorType.LLM,
              self._exec_smart_shopping,
              params={"product": product}, timeout=60)

        return b.build()

    async def _build_booking_graph(self, intent: ParsedIntent) -> TaskGraph:
        """
        预订任务图:
          [搜索] → [排序] → [检测预订方式] → [执行预订] → [确认]
        """
        b = TaskGraphBuilder(f"预订: {intent.goal}")

        b.add("search", "搜索服务", ExecutorType.BROWSER,
              self._exec_booking_search,
              params=intent.known_params, timeout=45)
        b.add("rank", "筛选排序", ExecutorType.LOCAL,
              self._exec_rank_results,
              params=intent.known_params,
              after=["search"], timeout=15)
        b.add("detect", "检测预订方式", ExecutorType.LOCAL,
              self._exec_detect_booking_method,
              params={},
              after=["rank"], timeout=10)
        b.add("execute", "执行预订", ExecutorType.BROWSER,
              self._exec_booking_execute,
              params=intent.known_params,
              after=["detect"], timeout=120,
              fallback="execute_phone")
        b.add("execute_phone", "电话预订(备选)", ExecutorType.VOICE_CALL,
              self._exec_booking_phone,
              params=intent.known_params,
              timeout=180)
        b.add("confirm", "确认结果", ExecutorType.LOCAL,
              self._exec_booking_confirm,
              params={},
              after=["execute"], timeout=10)

        return b.build()

    async def _build_info_graph(self, intent: ParsedIntent) -> TaskGraph:
        """简单信息查询 — 单节点 LLM 调用"""
        b = TaskGraphBuilder(f"信息查询: {intent.goal}")
        b.add("query", "查询回答", ExecutorType.LLM,
              self._exec_llm_query,
              params={"question": intent.goal, **intent.known_params},
              timeout=30)
        return b.build()

    async def _build_life_graph(self, intent: ParsedIntent) -> TaskGraph:
        """生活服务任务图"""
        b = TaskGraphBuilder(f"生活服务: {intent.goal}")
        b.add("execute", "执行任务", ExecutorType.LOCAL,
              self._exec_life_service,
              params={"goal": intent.goal, **intent.known_params},
              timeout=60)
        return b.build()

    async def _build_system_graph(self, intent: ParsedIntent) -> TaskGraph:
        """系统状态查询"""
        b = TaskGraphBuilder("系统状态查询")
        b.add("status", "获取系统状态", ExecutorType.LOCAL,
              self._exec_system_status,
              params={}, timeout=15)
        return b.build()

    async def _build_evolution_graph(self, intent: ParsedIntent) -> TaskGraph:
        """进化扫描"""
        b = TaskGraphBuilder("进化扫描")
        b.add("scan", "GitHub趋势扫描", ExecutorType.LOCAL,
              self._exec_evolution_scan,
              params=intent.known_params, timeout=300)
        return b.build()

    async def _build_code_graph(self, intent: ParsedIntent) -> TaskGraph:
        """代码任务"""
        b = TaskGraphBuilder(f"代码任务: {intent.goal}")
        b.add("code", "执行代码任务", ExecutorType.LLM,
              self._exec_code_task,
              params={"task": intent.goal, **intent.known_params},
              timeout=120)
        return b.build()
