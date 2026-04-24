"""
ClawBot - 共享工具执行器
供 multi_main.py 中的 MultiBot 使用，让 Claude bot 在多 bot 模式下也能调用工具。
支持工具熔断、结果截断、危险命令检测。
"""

import logging
import time
from pathlib import Path
from typing import Any

from src.constants import FAMILY_CLAUDE

from .tools.bash_tool import BashTool
from .tools.code_tool import CodeTool
from .tools.file_tool import FileTool
from .tools.memory_tool import MemoryTool
from .tools.web_tool import WebTool

logger = logging.getLogger(__name__)


class ToolCircuitBreaker:
    """工具级别熔断器 - 连续失败的工具会被短路"""

    def __init__(self, max_failures: int = 3, cooldown: float = 120.0):
        self.max_failures = max_failures
        self.cooldown = cooldown
        self._failures: dict[str, int] = {}
        self._last_failure: dict[str, float] = {}

    def record_success(self, tool_name: str):
        self._failures.pop(tool_name, None)
        self._last_failure.pop(tool_name, None)

    def record_failure(self, tool_name: str):
        self._failures[tool_name] = self._failures.get(tool_name, 0) + 1
        self._last_failure[tool_name] = time.time()

    def is_available(self, tool_name: str) -> bool:
        failures = self._failures.get(tool_name, 0)
        if failures < self.max_failures:
            return True
        last = self._last_failure.get(tool_name, 0)
        if time.time() - last >= self.cooldown:
            self._failures[tool_name] = 0
            return True
        return False

    def get_status(self) -> dict[str, Any]:
        return {
            name: {"failures": count, "available": self.is_available(name)} for name, count in self._failures.items()
        }


# Claude tool-use 格式的工具定义
MULTI_BOT_TOOLS = [
    {
        "name": "bash",
        "description": "执行 Bash 命令。可用于运行系统命令、安装软件、管理文件等。",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 Bash 命令"},
                "workdir": {"type": "string", "description": "工作目录（可选）"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "读取文件内容。支持指定起始行和行数。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "offset": {"type": "integer", "description": "起始行号（0-based）"},
                "limit": {"type": "integer", "description": "读取行数"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "写入文件内容。如果文件不存在则创建。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要写入的内容"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "编辑文件，将指定字符串替换为新字符串。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "old_string": {"type": "string", "description": "要替换的原始字符串"},
                "new_string": {"type": "string", "description": "替换后的新字符串"},
                "replace_all": {"type": "boolean", "description": "是否替换所有匹配"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_dir",
        "description": "列出目录内容。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"},
                "pattern": {"type": "string", "description": "glob 匹配模式"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_files",
        "description": "搜索文件。支持文件名模式和内容正则匹配。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "搜索目录"},
                "pattern": {"type": "string", "description": "文件名 glob 模式"},
                "content_pattern": {"type": "string", "description": "内容正则表达式"},
            },
            "required": ["path", "pattern"],
        },
    },
    {
        "name": "fetch_url",
        "description": "抓取网页内容，返回纯文本或 HTML。",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "网页 URL"},
                "format": {"type": "string", "description": "返回格式: text 或 html"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "web_search",
        "description": "搜索网络，返回搜索结果列表。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "num_results": {"type": "integer", "description": "返回结果数量"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "run_python",
        "description": "执行 Python 代码并返回输出。",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "run_shell",
        "description": "执行 Shell 脚本并返回输出。",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Shell 脚本内容"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "remember",
        "description": "将信息存入长期记忆（跨会话持久化）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "记忆键名"},
                "value": {"type": "string", "description": "记忆内容"},
                "category": {"type": "string", "description": "分类（默认 general）"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "recall",
        "description": "从长期记忆中回忆信息。",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "记忆键名"},
                "category": {"type": "string", "description": "分类（可选）"},
            },
            "required": ["key"],
        },
    },
    {
        "name": "search_memory",
        "description": "搜索长期记忆。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        },
    },
    # ========== MemGPT/Letta 风格分层记忆工具 (P2-3第二期) ==========
    {
        "name": "core_memory_append",
        "description": "向核心记忆追加信息。核心记忆始终在上下文中，用于存储用户画像、偏好、关键事实等需要随时参考的信息。",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "记忆块名称: user_profile / preferences / key_facts / current_task",
                },
                "value": {"type": "string", "description": "要追加的内容"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "core_memory_replace",
        "description": "替换核心记忆中的指定内容。用于更新过时信息（如用户改名、偏好变化）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "记忆块名称: user_profile / preferences / key_facts / current_task",
                },
                "old_value": {"type": "string", "description": "要被替换的旧内容"},
                "new_value": {"type": "string", "description": "替换后的新内容"},
            },
            "required": ["key", "old_value", "new_value"],
        },
    },
    {
        "name": "archival_memory_insert",
        "description": "将信息存入归档记忆（长期存储）。归档记忆不在上下文中，需搜索才能检索。适合存储详细对话记录、分析结果等。",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "要存储的内容"},
                "category": {"type": "string", "description": "分类标签（默认 archival）"},
                "importance": {"type": "integer", "description": "重要度 1-5（默认 2）"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "archival_memory_search",
        "description": "语义搜索归档记忆。根据查询语义匹配最相关的历史记忆。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询（支持自然语言语义匹配）"},
                "count": {"type": "integer", "description": "返回结果数量（默认 5）"},
            },
            "required": ["query"],
        },
    },
    # ========== 交易与市场分析工具 ==========
    {
        "name": "get_quote",
        "description": "获取股票/ETF/加密货币的实时行情。返回价格、涨跌幅、成交量等。支持美股(AAPL)、ETF(SPY)、加密货币(BTC, ETH)。",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "标的代码，如 AAPL, NVDA, BTC, ETH, SPY"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "technical_analysis",
        "description": "对标的进行完整技术分析。返回EMA/MACD/RSI/布林带/ATR/ADX/OBV/VWAP等全部指标、支撑阻力位、综合信号评分(-100到+100)。",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "标的代码，如 AAPL, NVDA, BTC-USD"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "scan_market",
        "description": "扫描全市场热门标的，返回按信号强度排序的候选列表。默认扫描26只热门美股+加密货币。可指定自定义标的列表。",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "自定义标的列表（可选，默认扫描全部热门标的）",
                },
            },
        },
    },
    {
        "name": "get_market_overview",
        "description": "获取全球市场概览：美股三大指数、恒生、上证、BTC、ETH、黄金、原油的实时行情。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_positions",
        "description": "查看当前持仓和未实现盈亏。包括每个持仓的成本、现价、盈亏比例。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "portfolio_summary",
        "description": "获取完整的投资组合摘要：持仓、现金、总资产、今日盈亏、交易历史统计。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "risk_status",
        "description": "查看当前风控状态：今日盈亏、剩余预算、持仓集中度、熔断状态、连续亏损次数等。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "search_news",
        "description": "搜索金融新闻。可搜索特定股票、行业、宏观事件的最新新闻。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词，如 'NVDA earnings' 或 '美联储降息'"},
                "count": {"type": "integer", "description": "返回新闻数量（默认5）"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "calculate_position_size",
        "description": "根据风控规则计算最优仓位大小。输入入场价和止损价，返回建议的股数、风险金额、占总资金比例。",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "标的代码"},
                "entry_price": {"type": "number", "description": "计划入场价"},
                "stop_loss": {"type": "number", "description": "止损价"},
            },
            "required": ["symbol", "entry_price", "stop_loss"],
        },
    },
]


class ToolExecutor:
    """
    共享工具执行器。

    在 multi_main.py 中作为全局单例使用，供 Claude bot 的 tool-use 循环调用。
    也可供其他 bot 通过委托机制间接使用。
    """

    def __init__(self, working_dir: str | None = None, siliconflow_key_func=None, shared_memory=None):
        self.working_dir = working_dir or str(Path.home())

        # 初始化工具实例
        self.bash_tool = BashTool(working_dir=self.working_dir)
        self.file_tool = FileTool(base_dir=self.working_dir)
        self.web_tool = WebTool()
        self.code_tool = CodeTool()
        self.memory_tool = MemoryTool()

        # 共享记忆（如果提供则用共享版，否则用本地 MemoryTool）
        self.shared_memory = shared_memory

        # 获取硅基流动 key 的回调（用于图片生成等需要 key 的工具）
        self._get_sf_key = siliconflow_key_func

        # 工具熔断器
        self.breaker = ToolCircuitBreaker(max_failures=3, cooldown=120.0)

        # 最大工具结果长度（防止超长结果撑爆上下文）
        self.max_result_length = 8000

    async def execute(self, tool_name: str, tool_input: dict) -> dict[str, Any]:
        """
        执行工具（带熔断检查和结果截断）。

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数

        Returns:
            工具执行结果 dict
        """
        # 熔断检查
        if not self.breaker.is_available(tool_name):
            return {
                "success": False,
                "error": f"工具 {tool_name} 暂时不可用（连续失败过多，冷却中）",
            }

        try:
            result = await self._dispatch(tool_name, tool_input)

            if result.get("success", False):
                self.breaker.record_success(tool_name)
            else:
                self.breaker.record_failure(tool_name)

            # 截断过长的结果
            return self._truncate_result(result)

        except Exception as e:
            self.breaker.record_failure(tool_name)
            logger.exception("[ToolExecutor] %s 执行异常", tool_name)
            return {"success": False, "error": str(e)}

    async def _dispatch(self, tool_name: str, tool_input: dict) -> dict[str, Any]:
        """分发工具调用到具体实现"""

        if tool_name == "bash":
            if self.bash_tool.is_dangerous(tool_input.get("command", "")):
                return {
                    "success": False,
                    "error": "检测到危险命令，已拒绝执行。请使用更安全的替代方案。",
                }
            return self.bash_tool.execute(tool_input["command"], tool_input.get("workdir"))

        elif tool_name == "read_file":
            return self.file_tool.read(
                tool_input["path"],
                tool_input.get("offset", 0),
                tool_input.get("limit", 2000),
            )

        elif tool_name == "write_file":
            return self.file_tool.write(tool_input["path"], tool_input["content"])

        elif tool_name == "edit_file":
            return self.file_tool.edit(
                tool_input["path"],
                tool_input["old_string"],
                tool_input["new_string"],
                tool_input.get("replace_all", False),
            )

        elif tool_name == "list_dir":
            return self.file_tool.list_dir(tool_input["path"], tool_input.get("pattern", "*"))

        elif tool_name == "search_files":
            return self.file_tool.search(
                tool_input["path"],
                tool_input["pattern"],
                tool_input.get("content_pattern"),
            )

        elif tool_name == "fetch_url":
            return await self.web_tool.fetch(tool_input["url"], tool_input.get("format", "text"))

        elif tool_name == "web_search":
            return await self.web_tool.search(tool_input["query"], tool_input.get("num_results", 5))

        elif tool_name == "run_python":
            return self.code_tool.execute_python(tool_input["code"])

        elif tool_name == "run_shell":
            return self.code_tool.execute_shell(tool_input["code"])

        elif tool_name == "remember":
            # 优先写入共享记忆（如果可用）
            if self.shared_memory:
                return self.shared_memory.remember(
                    tool_input["key"],
                    tool_input["value"],
                    tool_input.get("category", "general"),
                    source_bot=FAMILY_CLAUDE,
                )
            return self.memory_tool.remember(
                tool_input["key"],
                tool_input["value"],
                tool_input.get("category", "general"),
            )

        elif tool_name == "recall":
            # 优先从共享记忆读取
            if self.shared_memory:
                return self.shared_memory.recall(tool_input["key"], tool_input.get("category"))
            return self.memory_tool.recall(tool_input["key"], tool_input.get("category"))

        elif tool_name == "search_memory":
            # 优先搜索共享记忆
            if self.shared_memory:
                return self.shared_memory.search(tool_input["query"])
            return self.memory_tool.search(tool_input["query"])

        # ========== MemGPT/Letta 风格分层记忆工具 ==========
        elif tool_name == "core_memory_append":
            return await self._tool_core_memory_append(tool_input)
        elif tool_name == "core_memory_replace":
            return await self._tool_core_memory_replace(tool_input)
        elif tool_name == "archival_memory_insert":
            return await self._tool_archival_memory_insert(tool_input)
        elif tool_name == "archival_memory_search":
            return await self._tool_archival_memory_search(tool_input)

        # ========== 交易与市场分析工具 ==========
        elif tool_name == "get_quote":
            return await self._tool_get_quote(tool_input)

        elif tool_name == "technical_analysis":
            return await self._tool_technical_analysis(tool_input)

        elif tool_name == "scan_market":
            return await self._tool_scan_market(tool_input)

        elif tool_name == "get_market_overview":
            return await self._tool_market_overview(tool_input)

        elif tool_name == "get_positions":
            return await self._tool_get_positions(tool_input)

        elif tool_name == "portfolio_summary":
            return await self._tool_portfolio_summary(tool_input)

        elif tool_name == "risk_status":
            return await self._tool_risk_status(tool_input)

        elif tool_name == "search_news":
            return await self._tool_search_news(tool_input)

        elif tool_name == "calculate_position_size":
            return await self._tool_calc_position_size(tool_input)

        else:
            return {"success": False, "error": f"未知工具: {tool_name}"}

    def _truncate_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """截断过长的工具结果，防止撑爆上下文"""
        for key in ("content", "stdout", "stderr", "output"):
            if key in result and isinstance(result[key], str):
                if len(result[key]) > self.max_result_length:
                    result[key] = (
                        result[key][: self.max_result_length] + f"\n\n... [截断，原始长度 {len(result[key])} 字符]"
                    )
        return result

    def get_tools_schema(self) -> list[dict]:
        """返回工具定义列表（Claude API 格式）"""
        return MULTI_BOT_TOOLS

    def get_status(self) -> dict[str, Any]:
        """返回工具执行器状态"""
        return {
            "working_dir": self.working_dir,
            "breaker": self.breaker.get_status(),
            "memory_summary": self.memory_tool.get_context_summary()[:200],
        }

    # ========== 交易工具实现 ==========

    async def _tool_get_quote(self, tool_input: dict) -> dict:
        try:
            from .invest_tools import format_quote, get_crypto_quote, get_stock_quote

            symbol = tool_input["symbol"].upper().strip()
            crypto = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "DOT", "AVAX"}
            if symbol in crypto:
                quote = await get_crypto_quote(symbol)
            else:
                quote = await get_stock_quote(symbol)
            if "error" in quote:
                return {"success": False, "error": quote["error"]}
            return {"success": True, "content": format_quote(quote)}
        except Exception as e:
            logger.exception("[ToolExecutor] get_quote 失败 (symbol=%s)", tool_input.get("symbol"))
            return {"success": False, "error": str(e)}

    async def _tool_technical_analysis(self, tool_input: dict) -> dict:
        try:
            from .ta_engine import format_analysis, get_full_analysis

            symbol = tool_input["symbol"].upper().strip()
            crypto = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "DOT", "AVAX"}
            real_sym = f"{symbol}-USD" if symbol in crypto else symbol
            data = await get_full_analysis(real_sym)
            if isinstance(data, dict) and "error" in data:
                return {"success": False, "error": data["error"]}
            text = format_analysis(data)
            # 追加支撑阻力
            sr = data.get("support_resistance", {})
            if sr:
                sups = sr.get("supports", [])
                ress = sr.get("resistances", [])
                if sups:
                    text += f"\n支撑位: {', '.join(f'${s:.2f}' for s in sups[:3])}"
                if ress:
                    text += f"\n阻力位: {', '.join(f'${r:.2f}' for r in ress[:3])}"
            sig = data.get("signal", {})
            if sig:
                text += f"\n\n综合信号: {sig.get('signal_cn', '?')} (评分: {sig.get('score', 0):+d}/100)"
                text += f"\n信号详情: {sig.get('reason', '')}"
            return {"success": True, "content": text}
        except Exception as e:
            logger.exception("[ToolExecutor] technical_analysis 失败 (symbol=%s)", tool_input.get("symbol"))
            return {"success": False, "error": str(e)}

    async def _tool_scan_market(self, tool_input: dict) -> dict:
        try:
            from .ta_engine import scan_market

            symbols = tool_input.get("symbols") or None
            results = await scan_market(symbols) if symbols else await scan_market()
            if not results:
                return {"success": True, "content": "扫描完成，无有效信号。"}
            lines = ["-- 市场扫描结果 (按信号强度排序) --\n"]
            for i, r in enumerate(results[:15]):
                sig = r.get("signal", {})
                ind = r.get("indicators", {})
                score = sig.get("score", 0)
                icon = "🟢" if score >= 30 else "🟡" if score >= 0 else "🔴"
                lines.append(
                    f"{i + 1}. {icon} {r.get('symbol', '?')} ${r.get('price', 0):.2f} "
                    f"({r.get('change_pct', 0):+.1f}%) "
                    f"信号={score:+d} 趋势={ind.get('trend', '?')} "
                    f"RSI={ind.get('rsi_14', 0):.0f} 量比={ind.get('vol_ratio', 0):.1f}x"
                )
            return {"success": True, "content": "\n".join(lines)}
        except Exception as e:
            logger.exception("[ToolExecutor] scan_market 失败")
            return {"success": False, "error": str(e)}

    async def _tool_market_overview(self, _: dict) -> dict:
        try:
            from .invest_tools import get_market_summary

            text = await get_market_summary()
            return {"success": True, "content": text}
        except Exception as e:
            logger.exception("[ToolExecutor] market_overview 失败")
            return {"success": False, "error": str(e)}

    async def _tool_get_positions(self, _: dict) -> dict:
        try:
            from .broker_bridge import ibkr
            from .invest_tools import portfolio

            lines = []
            # IBKR 实盘持仓
            if ibkr.is_connected():
                positions = ibkr.get_positions()
                if positions:
                    lines.append("-- IBKR 实盘持仓 --")
                    for p in positions:
                        lines.append(
                            f"  {p['symbol']}: {p['quantity']}股 成本${p['avg_cost']:.2f} 现价${p.get('market_price', 0):.2f} 盈亏${p.get('unrealized_pnl', 0):.2f}"
                        )
                else:
                    lines.append("IBKR: 无持仓")
                lines.append(f"IBKR 预算: ${ibkr.budget - ibkr.total_spent:.0f} / ${ibkr.budget:.0f}")
            else:
                lines.append("IBKR: 未连接")
            # 模拟持仓
            sim_summary = await portfolio.get_portfolio_summary()
            if sim_summary:
                lines.append(f"\n-- 模拟组合 --\n{sim_summary}")
            return {"success": True, "content": "\n".join(lines) if lines else "无持仓数据"}
        except Exception as e:
            logger.exception("[ToolExecutor] get_positions 失败")
            return {"success": False, "error": str(e)}

    async def _tool_portfolio_summary(self, _: dict) -> dict:
        try:
            from .broker_bridge import ibkr

            lines = []
            if ibkr.is_connected():
                status = ibkr.get_connection_status()
                lines.append(status)
                lines.append(
                    f"预算: ${ibkr.budget:.0f} | 已用: ${ibkr.total_spent:.0f} | 剩余: ${ibkr.budget - ibkr.total_spent:.0f}"
                )
            # 交易系统状态
            try:
                from .trading_system import get_system_status

                sys_status = get_system_status()
                lines.append(f"\n{sys_status}")
            except Exception:
                logger.exception("[ToolExecutor] 交易系统状态获取失败")
            return {"success": True, "content": "\n".join(lines) if lines else "无组合数据"}
        except Exception as e:
            logger.exception("[ToolExecutor] portfolio_summary 失败")
            return {"success": False, "error": str(e)}

    async def _tool_risk_status(self, _: dict) -> dict:
        try:
            from .trading_system import _risk_manager

            if not _risk_manager:
                return {"success": True, "content": "风控系统未初始化"}
            status = _risk_manager.get_status()
            lines = [
                "-- 风控状态 --",
                f"今日盈亏: ${status.get('today_pnl', 0):.2f}",
                f"今日交易: {status.get('today_trades', 0)}笔",
                f"日亏损限额: ${status.get('daily_loss_limit', 100):.0f}",
                f"连续亏损: {status.get('consecutive_losses', 0)}次",
                f"熔断状态: {'触发' if status.get('circuit_breaker', False) else '正常'}",
                f"总资金: ${status.get('total_capital', 2000):.0f}",
                f"当前敞口: ${status.get('total_exposure', 0):.0f} ({status.get('exposure_pct', 0):.0f}%)",
                f"持仓数: {status.get('open_positions', 0)}/{status.get('max_positions', 5)}",
            ]
            return {"success": True, "content": "\n".join(lines)}
        except Exception as e:
            logger.exception("[ToolExecutor] risk_status 失败")
            return {"success": False, "error": str(e)}

    async def _tool_search_news(self, tool_input: dict) -> dict:
        try:
            from .news_fetcher import NewsFetcher
            from .notify_style import format_announcement

            fetcher = NewsFetcher()
            query = tool_input["query"]
            count = tool_input.get("count", 5)
            # 尝试 Google News RSS，失败则 Bing
            news = await fetcher.fetch_from_google_news_rss(query, count)
            if not news:
                news = await fetcher.fetch_from_bing(query, count)
            if not news:
                return {"success": True, "content": f"未找到关于 '{query}' 的新闻"}
            sections = []
            for i, n in enumerate(news[:count], 1):
                entries = [f"{i}. {n.get('title', '?')}"]
                if n.get("source"):
                    entries.append(f"来源：{n.get('source', '')}")
                if n.get("url"):
                    entries.append(f"详情：{n['url']}")
                sections.append((f"【第 {i} 条】", entries))
            return {
                "success": True,
                "content": format_announcement(
                    title=f"OpenClaw「资讯快讯」{query}",
                    intro=f"已整理 {min(len(news), count)} 条和“{query}”相关的资讯。",
                    sections=sections,
                    footer="如果你要继续深挖，可以再指定公司、板块或事件关键词。",
                ),
            }
        except Exception as e:
            logger.exception("[ToolExecutor] search_news 失败 (query=%s)", tool_input.get("query"))
            return {"success": False, "error": str(e)}

    async def _tool_calc_position_size(self, tool_input: dict) -> dict:
        try:
            from .broker_bridge import ibkr
            from .ta_engine import calc_position_size

            symbol = tool_input["symbol"].upper()
            entry = float(tool_input["entry_price"])
            stop = float(tool_input["stop_loss"])
            capital = ibkr.budget - ibkr.total_spent if ibkr.is_connected() else 2000.0
            result = calc_position_size(
                capital=capital,
                risk_pct=0.02,
                entry=entry,
                stop_loss=stop,
            )
            risk_per_share = abs(entry - stop)
            lines = [
                f"-- {symbol} 仓位计算 --",
                f"入场价: ${entry:.2f} | 止损价: ${stop:.2f}",
                f"每股风险: ${risk_per_share:.2f} ({risk_per_share / entry * 100:.1f}%)",
                f"可用资金: ${capital:.0f}",
                f"建议股数: {result.get('quantity', 0)}",
                f"总投入: ${result.get('total_cost', 0):.0f} ({result.get('capital_pct', 0):.0f}%资金)",
                f"最大亏损: ${result.get('max_loss', 0):.2f} ({result.get('risk_pct_actual', 0):.1f}%资金)",
                f"风险收益比: 1:{result.get('rr_ratio', 0):.1f}" if result.get("rr_ratio") else "",
            ]
            return {"success": True, "content": "\n".join(l for l in lines if l)}
        except Exception as e:
            logger.exception("[ToolExecutor] calc_position_size 失败 (symbol=%s)", tool_input.get("symbol"))
            return {"success": False, "error": str(e)}

    # ========== MemGPT/Letta 风格分层记忆工具实现 (P2-3第二期) ==========

    async def _tool_core_memory_append(self, tool_input: dict) -> dict:
        """向核心记忆追加内容 — 委托给 TieredContextManager.core_append"""
        try:
            from src.bot.globals import tiered_ctx

            if not tiered_ctx:
                return {"success": False, "error": "分层记忆管理器未初始化"}
            key = tool_input["key"]
            value = tool_input["value"]
            chat_id = tool_input.get("chat_id", 0)
            tiered_ctx.core_append(key, value, chat_id)
            current = tiered_ctx.core_get(key, chat_id)
            return {
                "success": True,
                "content": f"已追加到 [{key}]。当前内容:\n{current[:500]}",
            }
        except Exception as e:
            logger.exception("[ToolExecutor] core_memory_append 失败")
            return {"success": False, "error": str(e)}

    async def _tool_core_memory_replace(self, tool_input: dict) -> dict:
        """替换核心记忆中的指定内容"""
        try:
            from src.bot.globals import tiered_ctx

            if not tiered_ctx:
                return {"success": False, "error": "分层记忆管理器未初始化"}
            key = tool_input["key"]
            old_value = tool_input["old_value"]
            new_value = tool_input["new_value"]
            chat_id = tool_input.get("chat_id", 0)
            current = tiered_ctx.core_get(key, chat_id)
            if old_value not in current:
                return {
                    "success": False,
                    "error": f"在 [{key}] 中未找到要替换的内容。当前内容:\n{current[:300]}",
                }
            updated = current.replace(old_value, new_value, 1)
            tiered_ctx.core_set(key, updated, chat_id)
            return {
                "success": True,
                "content": f"已更新 [{key}]。当前内容:\n{updated[:500]}",
            }
        except Exception as e:
            logger.exception("[ToolExecutor] core_memory_replace 失败")
            return {"success": False, "error": str(e)}

    async def _tool_archival_memory_insert(self, tool_input: dict) -> dict:
        """存入归档记忆"""
        try:
            from src.bot.globals import tiered_ctx

            if not tiered_ctx:
                if self.shared_memory:
                    content = tool_input["content"]
                    category = tool_input.get("category", "archival")
                    importance = tool_input.get("importance", 2)
                    self.shared_memory.remember(
                        key=content[:30], value=content, category=category, importance=importance
                    )
                    return {"success": True, "content": "已存入归档记忆 (SharedMemory降级)"}
                return {"success": False, "error": "记忆系统未初始化"}
            content = tool_input["content"]
            category = tool_input.get("category", "archival")
            importance = tool_input.get("importance", 2)
            key_text = content[:30].replace(" ", "_").replace("\n", "_")
            tiered_ctx.archival_store(key=f"tool_{key_text}", value=content, category=category, importance=importance)
            return {
                "success": True,
                "content": f"已存入归档记忆 (分类={category}, 重要度={importance})",
            }
        except Exception as e:
            logger.exception("[ToolExecutor] archival_memory_insert 失败")
            return {"success": False, "error": str(e)}

    async def _tool_archival_memory_search(self, tool_input: dict) -> dict:
        """语义搜索归档记忆"""
        try:
            from src.bot.globals import tiered_ctx

            query = tool_input["query"]
            count = tool_input.get("count", 5)
            if tiered_ctx:
                result_text = tiered_ctx.archival_search(query, limit=count)
                if result_text:
                    return {"success": True, "content": result_text}
            if self.shared_memory:
                results = self.shared_memory.search(query, limit=count)
                if isinstance(results, list) and results:
                    lines = []
                    for r in results[:count]:
                        if isinstance(r, dict):
                            lines.append(
                                f"- [{r.get('category', '')}] {r.get('key', '')}: {str(r.get('value', ''))[:150]}"
                            )
                    if lines:
                        return {"success": True, "content": "\n".join(lines)}
            return {"success": True, "content": f"未找到与 '{query}' 相关的归档记忆"}
        except Exception as e:
            logger.exception("[ToolExecutor] archival_memory_search 失败")
            return {"success": False, "error": str(e)}
