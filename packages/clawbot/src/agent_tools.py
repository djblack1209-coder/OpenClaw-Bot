"""
OpenClaw 自主 Agent — 搬运 smolagents (26.2k⭐, HuggingFace)
让 LLM 自主决定调用哪些工具，用代码串联多步操作。

用户说: "检查我的持仓，如果亏损超过5%就建议止损"
Agent: 调用 check_portfolio → 分析结果 → 调用 risk_analysis → 生成建议

降级链: smolagents CodeAgent → 直接 LLM 回答 (零中断)

Usage:
    from src.agent_tools import run_agent
    result = await run_agent("帮我分析比特币这周的走势")
"""
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# ── smolagents 导入 (graceful degradation) ──────────────────────────

HAS_SMOLAGENTS = False

try:
    from smolagents import Tool, CodeAgent, LiteLLMModel
    HAS_SMOLAGENTS = True
    logger.info("[SmolAgents] SDK 可用")
except ImportError:
    logger.debug("[SmolAgents] smolagents 未安装，/agent 命令将降级为直接 LLM 回答")

    # Stub classes so the module can be imported without smolagents
    class Tool:  # type: ignore[no-redef]
        name = ""
        description = ""
        inputs = {}
        output_type = "string"

        def forward(self, **kwargs):
            raise NotImplementedError


# ── Tool 定义 — 包装现有 bot 能力 ──────────────────────────────────

class StockQuoteTool(Tool):
    """获取股票/加密货币实时行情"""

    name = "stock_quote"
    description = (
        "获取股票或加密货币的实时行情数据，包括价格、涨跌幅、成交量等。"
        "股票代码示例: AAPL, TSLA, NVDA, GOOGL; "
        "加密货币示例: BTC-USD, ETH-USD; "
        "A股示例: 600519, 000858"
    )
    inputs = {
        "symbol": {
            "type": "string",
            "description": "股票/加密货币代码，如 AAPL, BTCUSDT, 600519",
        }
    }
    output_type = "string"

    def forward(self, symbol: str) -> str:
        from src.invest_tools import _sync_get_quote, format_quote

        # Normalize crypto symbols: BTCUSDT -> BTC-USD
        sym = symbol.upper().strip()
        if sym.endswith("USDT"):
            sym = sym.replace("USDT", "-USD")

        quote = _sync_get_quote(sym)
        return format_quote(quote)


class TechnicalAnalysisTool(Tool):
    """对股票/加密货币进行技术分析"""

    name = "technical_analysis"
    description = (
        "对指定标的进行完整技术分析，包括 RSI、MACD、布林带、EMA、"
        "支撑位/阻力位、综合信号评分 (-100 到 +100)，给出买入/卖出/中性信号。"
    )
    inputs = {
        "symbol": {
            "type": "string",
            "description": "股票/加密货币代码，如 AAPL, BTC-USD",
        }
    }
    output_type = "string"

    def forward(self, symbol: str) -> str:
        from src.ta_engine import _sync_full_analysis

        sym = symbol.upper().strip()
        if sym.endswith("USDT"):
            sym = sym.replace("USDT", "-USD")

        result = _sync_full_analysis(sym)
        if "error" in result:
            return result["error"]

        signal = result.get("signal", {})
        indicators = result.get("indicators", {})
        sr = result.get("support_resistance", {})

        lines = [
            f"=== {result.get('name', sym)} ({sym}) 技术分析 ===",
            f"价格: {result['price']}  涨跌: {result['change_pct']:+.2f}%",
            f"",
            f"信号评分: {signal.get('score', 0)} / 100  → {signal.get('signal_cn', '中性')}",
            f"市场状态: {signal.get('regime', 'N/A')}",
            f"",
            f"--- 指标 ---",
            f"RSI(14): {indicators.get('rsi_14', 'N/A')}  RSI(6): {indicators.get('rsi_6', 'N/A')}",
            f"MACD: {indicators.get('macd', 'N/A')}  Signal: {indicators.get('macd_signal', 'N/A')}",
            f"BB位置: {indicators.get('bb_position', 'N/A')} (0=下轨, 1=上轨)",
            f"EMA5: {indicators.get('ema_5', 'N/A')}  EMA20: {indicators.get('ema_20', 'N/A')}",
        ]

        if sr.get("supports"):
            lines.append(f"支撑位: {', '.join(str(s) for s in sr['supports'][:3])}")
        if sr.get("resistances"):
            lines.append(f"阻力位: {', '.join(str(r) for r in sr['resistances'][:3])}")

        reasons = signal.get("reasons", [])
        if reasons:
            lines.append(f"")
            lines.append(f"--- 信号理由 ---")
            for r in reasons[:5]:
                lines.append(f"• {r}")

        return "\n".join(lines)


class WebSearchTool(Tool):
    """搜索互联网获取最新信息"""

    name = "web_search"
    description = (
        "搜索互联网获取最新信息，适用于查询新闻、价格、事件等实时信息。"
        "降级链: Tavily AI搜索 → Jina Reader。"
    )
    inputs = {
        "query": {
            "type": "string",
            "description": "搜索关键词，如 '比特币最新价格', 'AAPL earnings 2024'",
        }
    }
    output_type = "string"

    def forward(self, query: str) -> str:
        # smolagents tools are sync; run async search in a new event loop
        try:
            from src.tools.tavily_search import quick_answer
            return _run_async_in_sync(quick_answer(query))
        except Exception as e:
            logger.exception("Agent 网络搜索失败")
            return f"搜索失败: {e}"


class PortfolioTool(Tool):
    """查看当前投资组合持仓和盈亏"""

    name = "check_portfolio"
    description = (
        "查看当前模拟投资组合的持仓、现金、总资产和盈亏情况。"
        "不需要任何参数。"
    )
    inputs = {}
    output_type = "string"

    def forward(self) -> str:
        try:
            from src.invest_tools import portfolio
            summary = _run_async_in_sync(portfolio.get_portfolio_summary())
            return summary
        except Exception as e:
            logger.exception("Agent 投资组合查询失败")
            return f"获取投资组合失败: {e}"


class NewsSearchTool(Tool):
    """搜索特定主题的最新新闻"""

    name = "news_search"
    description = (
        "搜索特定主题或股票的最新新闻。支持主题: "
        "google, nvidia, claude, musk, market, fed, crypto；"
        "也可以直接输入自定义关键词搜索。"
    )
    inputs = {
        "topic": {
            "type": "string",
            "description": "新闻主题或关键词，如 'nvidia', 'BTC', '美联储加息'",
        }
    }
    output_type = "string"

    def forward(self, topic: str) -> str:
        try:
            # Use Tavily for news search (more reliable for current events)
            from src.tools.tavily_search import search_context
            result = _run_async_in_sync(
                search_context(f"{topic} 最新新闻 latest news", max_results=5)
            )
            if result and len(result) > 50:
                return f"=== {topic} 最新新闻 ===\n\n{result[:3000]}"
            # Fallback to news_fetcher
            from src.news_fetcher import NewsFetcher
            fetcher = NewsFetcher()
            items = _run_async_in_sync(fetcher.fetch_topic_news(topic, count=5))
            if items:
                lines = NewsFetcher.format_news_items(items, max_items=5)
                return f"=== {topic} 新闻 ===\n" + "\n".join(lines)
            return f"未找到关于 {topic} 的新闻"
        except Exception as e:
            logger.exception("Agent 新闻搜索失败")
            return f"新闻搜索失败: {e}"


class MarketOverviewTool(Tool):
    """获取全球市场概览"""

    name = "market_overview"
    description = (
        "获取全球市场概览，包括标普500、纳斯达克、道琼斯、恒生指数、"
        "上证指数、比特币、以太坊、黄金、原油等主要指数/资产的实时行情。"
        "不需要任何参数。"
    )
    inputs = {}
    output_type = "string"

    def forward(self) -> str:
        try:
            from src.invest_tools import get_market_summary
            return _run_async_in_sync(get_market_summary())
        except Exception as e:
            logger.exception("Agent 市场概览获取失败")
            return f"获取市场概览失败: {e}"


class RiskAnalysisTool(Tool):
    """查看风控系统状态"""

    name = "risk_analysis"
    description = (
        "查看当前风控系统状态，包括资金使用情况、日亏损、连续亏损次数、"
        "熔断状态、回撤比例、历史胜率等风控指标。不需要任何参数。"
    )
    inputs = {}
    output_type = "string"

    def forward(self) -> str:
        try:
            from src.risk_manager import RiskManager
            rm = RiskManager()
            return rm.format_status()
        except Exception as e:
            logger.exception("Agent 风控状态获取失败")
            return f"获取风控状态失败: {e}"


class SentimentAnalysisTool(Tool):
    """对特定主题进行市场情绪分析"""

    name = "sentiment_analysis"
    description = (
        "通过搜索最新信息并分析市场情绪，判断某个股票、加密货币或话题的"
        "市场情绪是看多、看空还是中性。"
    )
    inputs = {
        "topic": {
            "type": "string",
            "description": "分析对象，如 'AAPL', 'Bitcoin', '半导体行业'",
        }
    }
    output_type = "string"

    def forward(self, topic: str) -> str:
        try:
            from src.tools.tavily_search import search_context
            context = _run_async_in_sync(
                search_context(
                    f"{topic} market sentiment analysis bullish bearish 市场情绪",
                    max_results=5,
                )
            )
            if context and len(context) > 50:
                return (
                    f"=== {topic} 情绪分析原始数据 ===\n\n"
                    f"{context[:3000]}\n\n"
                    f"请基于以上信息综合判断 {topic} 的市场情绪"
                )
            return f"未能获取 {topic} 的情绪数据，搜索服务暂不可用"
        except Exception as e:
            logger.exception("Agent 情绪分析数据获取失败")
            return f"情绪分析数据获取失败: {e}"


# ── 辅助函数 ──────────────────────────────────────────────────────

def _run_async_in_sync(coro):
    """在同步上下文中运行协程 — smolagents tools 是同步的。

    如果已有事件循环在运行，创建新线程来运行；否则直接 asyncio.run。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as e:  # noqa: F841
        loop = None

    if loop and loop.is_running():
        # We're inside an existing event loop (common in bot context).
        # Run the coroutine in a new thread with its own loop.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=60)
    else:
        return asyncio.run(coro)


def _get_all_tools() -> list:
    """返回所有 Agent Tool 实例"""
    return [
        StockQuoteTool(),
        TechnicalAnalysisTool(),
        WebSearchTool(),
        PortfolioTool(),
        NewsSearchTool(),
        MarketOverviewTool(),
        RiskAnalysisTool(),
        SentimentAnalysisTool(),
    ]


# ── 公开 API ──────────────────────────────────────────────────────

async def run_agent(query: str, model_name: str = "") -> str:
    """运行智能 Agent — 用自然语言驱动多工具链。

    Args:
        query: 用户的自然语言指令
        model_name: LiteLLM 模型名 (为空则自动选择)

    Returns:
        Agent 的最终回答文本

    Raises:
        RuntimeError: smolagents 未安装
    """
    if not HAS_SMOLAGENTS:
        raise RuntimeError(
            "smolagents 未安装。请运行: pip install 'smolagents>=1.0.0'\n"
            "安装后重启 Bot 即可使用 /agent 命令。"
        )

    # Resolve model
    if not model_name:
        model_name = os.getenv("AGENT_MODEL", "")
    if not model_name:
        # Try to pick a sensible default from environment
        if os.getenv("OPENAI_API_KEY"):
            model_name = "openai/gpt-4o-mini"
        elif os.getenv("ANTHROPIC_API_KEY"):
            model_name = "anthropic/claude-sonnet-4-20250514"
        else:
            # Fallback: use whatever LiteLLM router can provide
            model_name = "openai/gpt-4o-mini"

    tools = _get_all_tools()

    # Run the sync smolagents CodeAgent in a thread executor
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_agent_sync, query, model_name, tools)
    return result


def _run_agent_sync(query: str, model_name: str, tools: list) -> str:
    """同步执行 Agent (在线程池中运行)"""
    try:
        model = LiteLLMModel(model_id=model_name)

        agent = CodeAgent(
            tools=tools,
            model=model,
            max_steps=6,
            verbosity_level=0,
            additional_authorized_imports=[
                "json", "math", "statistics", "datetime", "re",
            ],
        )

        result = agent.run(query)

        # CodeAgent.run() may return various types
        if result is None:
            return "Agent 执行完成，但未产生输出。"
        return str(result)

    except Exception as e:
        logger.error("[SmolAgent] 执行失败: %s", e, exc_info=True)
        return f"Agent 执行出错: {e}"
