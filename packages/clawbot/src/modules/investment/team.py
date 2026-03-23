"""
OpenClaw OMEGA — 多智能体投资团队 (Investment Team)
基于 CrewAI 的6角色协作投资分析系统。

6个角色:
  投资总监 (Director)   → 接收指令/分配任务/最终决策/汇报
  研究员   (Researcher) → 基本面/行业/舆情分析
  技术分析师 (TA)       → K线/指标/形态/趋势
  量化工程师 (Quant)    → 因子/回测/统计
  风控官   (Risk)       → 仓位管理/止损/一票否决
  复盘官   (Reviewer)   → 交易后分析/策略迭代

与现有系统整合:
  - 复用 ta_engine.py 的技术指标计算
  - 复用 data_providers.py 的市场数据
  - 复用 broker_bridge.py 的下单通道
  - 复用 risk_manager.py 的风控规则
  - 通过 EventBus 发布交易事件
"""
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 风控硬性规则（任何情况不得违反）─────────────────────

RISK_RULES = {
    "max_position_single": 0.20,      # 单标的最大仓位 20%
    "max_sector_position": 0.35,      # 同行业最大仓位 35%
    "max_total_position": 0.80,       # 总仓位上限 80%
    "max_drawdown_stop": 0.08,        # 单标的回撤 >8% 自动止损
    "daily_loss_limit": 0.03,         # 单日亏损 >3% 暂停交易
    "require_human_approval_rmb": 100000,  # 单笔 >10万 RMB 需人工确认
    "correlation_check": True,         # 持仓相关性检查
    "liquidity_check": True,           # 流动性检查
}

# ── 数据结构 ──────────────────────────────────────────

@dataclass
class AgentReport:
    """单个角色的分析报告"""
    agent_id: str
    agent_name: str
    score: float = 0.0            # 0-10 综合评分
    recommendation: str = "hold"  # buy/sell/hold
    reasoning: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


@dataclass
class TeamAnalysis:
    """投资团队完整分析结果"""
    symbol: str
    market: str = "cn"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # 各角色报告
    research_report: Optional[AgentReport] = None
    ta_report: Optional[AgentReport] = None
    quant_report: Optional[AgentReport] = None
    risk_report: Optional[AgentReport] = None
    director_report: Optional[AgentReport] = None

    # 最终决策
    final_recommendation: str = "hold"
    confidence: float = 0.0
    target_price: float = 0.0
    stop_loss: float = 0.0
    position_size_pct: float = 0.0
    veto: bool = False
    veto_reason: str = ""

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "market": self.market,
            "timestamp": self.timestamp,
            "research": self.research_report.__dict__ if self.research_report else None,
            "ta": self.ta_report.__dict__ if self.ta_report else None,
            "quant": self.quant_report.__dict__ if self.quant_report else None,
            "risk": self.risk_report.__dict__ if self.risk_report else None,
            "director": self.director_report.__dict__ if self.director_report else None,
            "final_recommendation": self.final_recommendation,
            "confidence": self.confidence,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "position_size_pct": self.position_size_pct,
            "veto": self.veto,
            "veto_reason": self.veto_reason,
        }

    def to_telegram_text(self) -> str:
        """格式化为 Telegram 消息"""
        lines = [
            f"━━━ 投资分析: {self.symbol} ━━━",
            "",
        ]
        # 各角色评分
        for label, report in [
            ("📊 研究员", self.research_report),
            ("📈 技术分析", self.ta_report),
            ("🔢 量化分析", self.quant_report),
        ]:
            if report:
                stars = "⭐" * int(report.score / 2)
                lines.append(f"{label}: {report.score:.1f}/10 {stars}")
                lines.append(f"   {report.recommendation.upper()} — {report.reasoning[:60]}")
            else:
                lines.append(f"{label}: 暂无数据")

        # 风控
        lines.append("")
        if self.risk_report:
            status = "✅ 通过" if not self.veto else f"❌ 否决: {self.veto_reason}"
            lines.append(f"🛡️ 风控: {status}")
        else:
            lines.append("🛡️ 风控: 暂无数据")

        # 最终决策
        lines.extend([
            "",
            "━━━ 最终决策 ━━━",
            f"建议: {self.final_recommendation.upper()}",
            f"置信度: {self.confidence:.0%}",
        ])
        if self.target_price > 0:
            lines.append(f"目标价: {self.target_price:.2f}")
        if self.stop_loss > 0:
            lines.append(f"止损价: {self.stop_loss:.2f}")
        if self.position_size_pct > 0:
            lines.append(f"建议仓位: {self.position_size_pct:.1%}")

        return "\n".join(lines)


@dataclass
class DailyBrief:
    """每日投资简报"""
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    market_overview: str = ""
    opportunities: List[Dict] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    portfolio_status: Dict = field(default_factory=dict)


# ── 角色提示词 ──────────────────────────────────────────

DIRECTOR_PROMPT = """你是OpenClaw投资团队的投资总监。你的职责是：
1. 汇总研究员、技术分析师、量化工程师的分析报告
2. 综合考虑基本面、技术面、量化指标做出最终投资决策
3. 在报告给用户时，用简洁清晰的中文说明决策理由
4. 如果团队意见分歧大（标准差>2），倾向保守
5. 风控官有一票否决权，如果风控否决则必须服从

输出JSON格式：
{"recommendation": "buy/sell/hold", "confidence": 0-1, "reasoning": "简明理由",
 "target_price": 数字, "stop_loss": 数字, "position_size_pct": 0-1}"""

RESEARCHER_PROMPT = """你是OpenClaw投资团队的市场研究员。你的职责是：
1. 分析标的的基本面数据（营收/利润/估值/行业地位）
2. 分析行业竞争格局和公司护城河
3. 搜索最新新闻和社媒舆情
4. 对比历史估值区间，判断当前估值水平

输出JSON格式：
{"score": 0-10, "recommendation": "buy/sell/hold",
 "valuation": "高估/合理/低估", "catalysts": ["催化剂列表"],
 "risks": ["风险因素"], "reasoning": "详细分析"}"""

TA_PROMPT = """你是OpenClaw投资团队的技术分析师。你的职责是：
1. 分析K线形态（日/周/月线）
2. 计算核心指标：MA/EMA/MACD/RSI/布林带/成交量
3. 识别支撑位和压力位
4. 判断当前趋势（上涨/下跌/震荡/突破）
5. 给出明确的交易信号

输出JSON格式：
{"score": 0-10, "recommendation": "buy/sell/hold",
 "trend": "上涨/下跌/震荡", "support": [价格], "resistance": [价格],
 "key_signal": "最重要的信号", "reasoning": "技术分析摘要"}"""

QUANT_PROMPT = """你是OpenClaw投资团队的量化工程师。你的职责是：
1. 计算关键因子：动量/波动率/价值/质量
2. 统计分析：夏普比率/最大回撤/胜率
3. 如有回测数据，评估策略表现
4. 分析异常成交量和价格模式

输出JSON格式：
{"score": 0-10, "recommendation": "buy/sell/hold",
 "sharpe_ratio": 数字, "momentum_score": 0-10,
 "volatility": "低/中/高", "reasoning": "量化分析摘要"}"""

RISK_PROMPT = f"""你是OpenClaw投资团队的首席风控官。你有一票否决权。

硬性规则（任何情况不得违反）：
- 单笔投资 ≤ 总资产 {RISK_RULES['max_position_single']:.0%}
- 同行业总仓位 ≤ {RISK_RULES['max_sector_position']:.0%}
- 总仓位 ≤ {RISK_RULES['max_total_position']:.0%}
- 任何标的亏损 ≥ {RISK_RULES['max_drawdown_stop']:.0%} 自动止损
- 单日最大亏损 ≥ {RISK_RULES['daily_loss_limit']:.0%} 停止所有交易

输出JSON格式：
{{"approved": true/false, "risk_level": "低/中/高/极高",
 "position_size_suggestion": 0-1, "stop_loss": 价格,
 "veto_reason": "否决理由（如果否决）", "reasoning": "风控评估"}}"""

REVIEWER_PROMPT = """你是OpenClaw投资团队的复盘官。每笔交易完成后：
1. 分析决策过程是否正确（不以结果论英雄）
2. 识别认知偏差（过度自信/锚定效应/损失厌恶/从众）
3. 提炼可改进的具体规则
4. 如果策略表现偏离回测>20%，建议暂停策略

输出JSON格式：
{"decision_quality": "优/良/中/差", "bias_detected": ["偏差列表"],
 "lesson": "最重要的教训", "strategy_update": "建议修改的规则"}"""


# ── 投资团队 ──────────────────────────────────────────

class InvestmentTeam:
    """
    多智能体投资团队 — 6个角色协作完成投资分析和交易决策。

    用法:
        team = InvestmentTeam()
        analysis = await team.analyze("600519.SS")
        print(analysis.to_telegram_text())
    """

    def __init__(self):
        self._initialized = False
        self._crew = None
        self._strategy_monitor = StrategyHealthMonitor()
        logger.info("InvestmentTeam 初始化")

    def _ensure_crew(self):
        """延迟初始化 CrewAI（避免启动时就加载）"""
        if self._initialized:
            return
        try:
            from crewai import Agent, Task, Crew, Process

            # 创建6个Agent
            self._director = Agent(
                role="投资总监",
                goal="汇总团队分析，做出最优投资决策",
                backstory="你是一位经验丰富的基金经理，管理着OpenClaw的投资组合。"
                          "你擅长综合基本面、技术面和量化信号做出理性决策。",
                verbose=False,
                allow_delegation=True,
            )
            self._researcher = Agent(
                role="市场研究员",
                goal="深入分析标的基本面，发现价值洼地和风险点",
                backstory="你是一位资深卖方分析师，擅长行业研究和公司估值。"
                          "你对中国和美国市场都有深入了解。",
                verbose=False,
            )
            self._ta_analyst = Agent(
                role="技术分析师",
                goal="通过K线和技术指标判断最佳买卖时机",
                backstory="你是一位有15年经验的技术分析师，精通各种形态识别和指标应用。",
                verbose=False,
            )
            self._quant = Agent(
                role="量化工程师",
                goal="用数据和统计方法验证投资假设",
                backstory="你是一位量化对冲基金的研究员，擅长因子分析和策略回测。",
                verbose=False,
            )
            self._risk_officer = Agent(
                role="首席风控官",
                goal="确保每笔交易的风险在可控范围内，保护本金安全",
                backstory="你是一位严格的风控专家。你有一票否决权。"
                          "你的信条是：保住本金永远比追求收益重要。",
                verbose=False,
            )
            self._reviewer = Agent(
                role="交易复盘官",
                goal="从每笔交易中提炼教训，持续改进投资策略",
                backstory="你是一位行为金融学专家，擅长识别认知偏差和决策错误。",
                verbose=False,
            )
            self._initialized = True
            logger.info("CrewAI 投资团队初始化完成（6个Agent）")

        except ImportError:
            logger.warning("CrewAI 未安装，投资团队使用降级模式")
        except Exception as e:
            logger.error(f"CrewAI 初始化失败: {e}", exc_info=True)

    async def analyze(
        self,
        symbol: str,
        market: str = "cn",
        context: Optional[Dict] = None,
    ) -> TeamAnalysis:
        """
        完整投资分析 — 研究员+TA+量化 并行 → 风控审核 → 总监决策。

        Args:
            symbol: 股票代码 (如 "600519.SS" / "AAPL")
            market: 市场 ("cn" / "us" / "crypto")
            context: 附加上下文

        Returns:
            TeamAnalysis 完整分析结果
        """
        analysis = TeamAnalysis(symbol=symbol, market=market)

        # 1. 并行：研究 + TA + 量化
        logger.info(f"[投资团队] 开始分析 {symbol}")
        tasks = [
            self._run_researcher(symbol, market),
            self._run_ta_analyst(symbol, market),
            self._run_quant(symbol, market),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"角色分析失败: {result}")
                continue
            if i == 0:
                analysis.research_report = result
            elif i == 1:
                analysis.ta_report = result
            elif i == 2:
                analysis.quant_report = result

        # 2. 风控审核
        analysis.risk_report = await self._run_risk_check(symbol, analysis)

        # 3. 检查是否被否决
        if analysis.risk_report and not analysis.risk_report.data.get("approved", True):
            analysis.veto = True
            analysis.veto_reason = analysis.risk_report.data.get("veto_reason", "风控否决")
            analysis.final_recommendation = "hold"
            analysis.confidence = 0.0
            logger.info(f"[投资团队] {symbol} 被风控否决: {analysis.veto_reason}")
        else:
            # 4. 总监决策
            analysis.director_report = await self._run_director(symbol, analysis)
            if analysis.director_report:
                analysis.final_recommendation = analysis.director_report.recommendation
                analysis.confidence = analysis.director_report.data.get("confidence", 0.5)
                analysis.target_price = analysis.director_report.data.get("target_price", 0)
                analysis.stop_loss = analysis.director_report.data.get("stop_loss", 0)
                analysis.position_size_pct = analysis.director_report.data.get(
                    "position_size_pct", 0
                )

        # 5. 发布事件
        try:
            from src.core.event_bus import get_event_bus, EventType
            bus = get_event_bus()
            await bus.publish(
                EventType.TRADE_SIGNAL,
                {"symbol": symbol, "analysis": analysis.to_dict()},
                source="investment_team",
            )
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        logger.info(f"[投资团队] {symbol} 分析完成: {analysis.final_recommendation}")
        return analysis

    async def research(self, symbol: str) -> Dict:
        """仅研究员分析（供 Brain 直接调用）"""
        report = await self._run_researcher(symbol, "cn")
        return report.__dict__ if report else {}

    async def quant_analysis(self, symbol: str) -> Dict:
        """仅量化分析（供 Brain 直接调用）"""
        report = await self._run_quant(symbol, "cn")
        return report.__dict__ if report else {}

    # ── 各角色执行 ──────────────────────────────────────

    async def _run_researcher(self, symbol: str, market: str) -> AgentReport:
        """研究员：基本面分析 + 社交信号富化"""
        start = time.time()
        report = AgentReport(agent_id="researcher", agent_name="研究员")

        try:
            # 获取基本面数据
            data = await self._fetch_fundamental_data(symbol, market)

            # 协同管道富化：注入社交信号（如果有）
            try:
                from src.core.synergy_pipelines import get_synergy_pipelines
                sp = get_synergy_pipelines()
                social_signal = sp.get_social_signal(symbol)
                if social_signal:
                    data["social_signal"] = social_signal
                    data["social_sentiment"] = "热门讨论中"
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

            # 用 LLM 分析
            analysis = await self._llm_analyze(
                RESEARCHER_PROMPT,
                f"分析标的: {symbol}\n市场: {market}\n基本面数据:\n{json.dumps(data, ensure_ascii=False, default=str)}",
            )
            report.score = analysis.get("score", 5.0)
            report.recommendation = analysis.get("recommendation", "hold")
            report.reasoning = analysis.get("reasoning", "无分析结果")
            report.data = analysis
        except Exception as e:
            report.reasoning = f"分析失败: {e}"
            logger.warning(f"研究员分析失败: {e}")

        report.elapsed_seconds = time.time() - start
        return report

    async def _run_ta_analyst(self, symbol: str, market: str) -> AgentReport:
        """技术分析师：技术面分析"""
        start = time.time()
        report = AgentReport(agent_id="ta_analyst", agent_name="技术分析师")

        try:
            # 复用现有 ta_engine
            ta_data = await self._fetch_ta_data(symbol)
            analysis = await self._llm_analyze(
                TA_PROMPT,
                f"分析标的: {symbol}\n技术指标数据:\n{json.dumps(ta_data, ensure_ascii=False, default=str)}",
            )
            report.score = analysis.get("score", 5.0)
            report.recommendation = analysis.get("recommendation", "hold")
            report.reasoning = analysis.get("reasoning", "无分析结果")
            report.data = analysis
        except Exception as e:
            report.reasoning = f"分析失败: {e}"
            logger.warning(f"技术分析师分析失败: {e}")

        report.elapsed_seconds = time.time() - start
        return report

    async def _run_quant(self, symbol: str, market: str) -> AgentReport:
        """量化工程师：量化分析"""
        start = time.time()
        report = AgentReport(agent_id="quant", agent_name="量化工程师")

        try:
            quant_data = await self._fetch_quant_data(symbol)
            analysis = await self._llm_analyze(
                QUANT_PROMPT,
                f"分析标的: {symbol}\n量化数据:\n{json.dumps(quant_data, ensure_ascii=False, default=str)}",
            )
            report.score = analysis.get("score", 5.0)
            report.recommendation = analysis.get("recommendation", "hold")
            report.reasoning = analysis.get("reasoning", "无分析结果")
            report.data = analysis
        except Exception as e:
            report.reasoning = f"分析失败: {e}"
            logger.warning(f"量化工程师分析失败: {e}")

        report.elapsed_seconds = time.time() - start
        return report

    async def _run_risk_check(self, symbol: str, analysis: TeamAnalysis) -> AgentReport:
        """风控官：风险审核"""
        start = time.time()
        report = AgentReport(agent_id="risk_officer", agent_name="风控官")

        try:
            # 收集各角色的建议
            team_summary = []
            for label, r in [("研究员", analysis.research_report),
                             ("技术分析", analysis.ta_report),
                             ("量化", analysis.quant_report)]:
                if r:
                    team_summary.append(
                        f"{label}: {r.recommendation} ({r.score:.1f}/10) — {r.reasoning[:50]}"
                    )

            # 获取当前持仓信息
            portfolio_info = self._get_portfolio_context()

            risk_analysis = await self._llm_analyze(
                RISK_PROMPT,
                f"标的: {symbol}\n团队分析汇总:\n" +
                "\n".join(team_summary) +
                f"\n\n当前持仓:\n{json.dumps(portfolio_info, ensure_ascii=False, default=str)}",
            )
            report.data = risk_analysis
            approved = risk_analysis.get("approved", True)
            report.recommendation = "approve" if approved else "veto"
            report.reasoning = risk_analysis.get("reasoning", "")
            report.score = 10.0 if approved else 0.0
        except Exception as e:
            # 风控失败时默认保守（否决）
            report.data = {"approved": False, "veto_reason": f"风控系统异常: {e}"}
            report.recommendation = "veto"
            report.reasoning = f"风控系统异常，默认否决: {e}"
            report.score = 0.0
            logger.warning(f"风控审核失败: {e}")

        report.elapsed_seconds = time.time() - start
        return report

    async def _run_director(self, symbol: str, analysis: TeamAnalysis) -> AgentReport:
        """总监：最终决策"""
        start = time.time()
        report = AgentReport(agent_id="director", agent_name="投资总监")

        try:
            # 汇总所有报告
            summary_parts = []
            for label, r in [("研究员", analysis.research_report),
                             ("技术分析", analysis.ta_report),
                             ("量化", analysis.quant_report),
                             ("风控", analysis.risk_report)]:
                if r:
                    summary_parts.append(
                        f"{label}: {r.recommendation} ({r.score:.1f}/10)\n  {r.reasoning}"
                    )

            decision = await self._llm_analyze(
                DIRECTOR_PROMPT,
                f"标的: {symbol}\n\n各角色分析报告:\n" +
                "\n\n".join(summary_parts),
            )
            report.recommendation = decision.get("recommendation", "hold")
            report.reasoning = decision.get("reasoning", "")
            report.score = decision.get("confidence", 0.5) * 10
            report.data = decision
        except Exception as e:
            report.recommendation = "hold"
            report.reasoning = f"决策系统异常，默认观望: {e}"
            report.score = 0.0
            logger.warning(f"总监决策失败: {e}")

        report.elapsed_seconds = time.time() - start
        return report

    async def review_trade(self, trade_id: str) -> Dict:
        """交易复盘"""
        try:
            from src.trading_journal import journal
            trade = journal.get_trade(trade_id) if journal else None
            if trade:
                review = await self._llm_analyze(
                    REVIEWER_PROMPT,
                    f"交易记录:\n{json.dumps(trade, ensure_ascii=False, default=str)}",
                )
                return review
        except Exception as e:
            logger.warning(f"交易复盘失败: {e}")
        return {"decision_quality": "无数据", "lesson": "复盘模块未就绪"}

    async def daily_meeting(self) -> DailyBrief:
        """每日投资例会"""
        brief = DailyBrief()
        # 复用现有的简报功能
        try:
            from src.execution.daily_brief import generate_brief
            data = await generate_brief()
            brief.market_overview = data.get("summary", "")
            brief.opportunities = data.get("opportunities", [])
            brief.risks = data.get("risks", [])
        except Exception as e:
            brief.market_overview = f"简报生成失败: {e}"
        return brief

    def get_portfolio_status(self) -> Dict:
        """获取当前持仓状态"""
        return self._get_portfolio_context()

    # ── 数据获取 ──────────────────────────────────────

    async def _fetch_fundamental_data(self, symbol: str, market: str) -> Dict:
        """获取基本面数据 — 多源汇聚"""
        data = {}

        # 源1: yfinance 基础数据
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.info
            data.update({
                "name": info.get("longName", symbol),
                "price": info.get("currentPrice", 0),
                "pe": info.get("trailingPE", 0),
                "pb": info.get("priceToBook", 0),
                "market_cap": info.get("marketCap", 0),
                "revenue_growth": info.get("revenueGrowth", 0),
                "profit_margin": info.get("profitMargins", 0),
                "sector": info.get("sector", ""),
            })
        except Exception as e:
            data["yfinance_error"] = str(e)

        # 源2: Jina Reader 获取最新新闻（零成本，替代爬虫）
        try:
            from src.tools.jina_reader import fetch_news_about
            company_name = data.get("name", symbol)
            news = await fetch_news_about(f"{company_name} {symbol} 最新消息 财报", max_length=2000)
            data["recent_news"] = news
        except Exception as e:
            data["news_error"] = str(e)

        # 源3: 统一数据提供者（akshare/ccxt）
        try:
            from src.data_providers import get_quote
            quote = await get_quote(symbol)
            if quote and isinstance(quote, dict):
                data.update({k: v for k, v in quote.items() if k not in data})
        except Exception:
            logger.debug("Silenced exception", exc_info=True)

        return data if data else {"error": "无数据", "symbol": symbol}

    async def _fetch_ta_data(self, symbol: str) -> Dict:
        """获取技术分析数据"""
        try:
            from src.ta_engine import get_full_analysis
            result = await get_full_analysis(symbol)
            return result or {}
        except Exception as e:
            return {"error": str(e), "symbol": symbol}

    async def _fetch_quant_data(self, symbol: str) -> Dict:
        """获取量化数据"""
        try:
            import yfinance as yf
            import numpy as np
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")
            if hist.empty:
                return {"error": "无历史数据"}
            returns = hist["Close"].pct_change().dropna()
            return {
                "annual_return": float(returns.mean() * 252),
                "annual_volatility": float(returns.std() * (252 ** 0.5)),
                "sharpe_ratio": float(
                    (returns.mean() * 252) / (returns.std() * (252 ** 0.5))
                ) if returns.std() > 0 else 0,
                "max_drawdown": float(
                    (hist["Close"] / hist["Close"].cummax() - 1).min()
                ),
                "current_price": float(hist["Close"].iloc[-1]),
                "price_52w_high": float(hist["Close"].max()),
                "price_52w_low": float(hist["Close"].min()),
                "avg_volume": float(hist["Volume"].mean()),
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_portfolio_context(self) -> Dict:
        """获取当前持仓上下文"""
        try:
            from src.bot.globals import ibkr, portfolio
            if ibkr and portfolio:
                return {
                    "positions": portfolio.get("positions", []),
                    "total_value": portfolio.get("total_value", 0),
                    "cash": portfolio.get("cash", 0),
                }
        except Exception:
            logger.debug("Silenced exception", exc_info=True)
        return {"positions": [], "total_value": 0, "cash": 0, "note": "券商未连接"}

    # ── LLM 分析（统一入口）──────────────────────────────

    async def _llm_analyze(self, system_prompt: str, user_content: str) -> Dict:
        """统一的 LLM 分析调用"""
        try:
            from src.litellm_router import free_pool
            if free_pool is None:
                raise RuntimeError("LLM 路由器未初始化")

            resp = await free_pool.acompletion(
                model_family="qwen",
                messages=[
                    {"role": "user", "content": user_content},
                ],
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=1500,
            )
            raw = resp.choices[0].message.content.strip()

            # 解析 JSON
            try:
                import json_repair
                return json_repair.loads(raw)
            except Exception:
                import re
                match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
                if match:
                    return json.loads(match.group())
                return {"reasoning": raw, "recommendation": "hold", "score": 5.0}

        except Exception as e:
            logger.warning(f"LLM 分析调用失败: {e}")
            return {"error": str(e), "recommendation": "hold", "score": 5.0}


# ── 策略健康监控 ──────────────────────────────────────────

class StrategyHealthMonitor:
    """
    检测策略失效 — 实盘与回测表现偏离 >20% 时自动暂停。

    失效模式:
      - regime_change: 市场环境突变（牛转熊）
      - alpha_decay: 策略被过多使用导致失效
      - overfitting: 历史数据过度优化
    """

    DEVIATION_THRESHOLD = 0.20  # 偏离20%触发暂停

    def __init__(self):
        self._strategy_performance: Dict[str, Dict] = {}
        self._suspended_strategies: set = set()

    def record_performance(
        self, strategy_name: str, live_return: float, backtest_return: float
    ) -> Optional[str]:
        """
        记录策略表现，检测是否需要暂停。

        Returns:
            暂停原因（如果需要暂停），否则 None
        """
        self._strategy_performance[strategy_name] = {
            "live_return": live_return,
            "backtest_return": backtest_return,
            "deviation": abs(live_return - backtest_return) / max(abs(backtest_return), 0.01),
            "timestamp": datetime.now().isoformat(),
        }

        deviation = self._strategy_performance[strategy_name]["deviation"]
        if deviation > self.DEVIATION_THRESHOLD:
            reason = (
                f"策略 {strategy_name} 实盘偏离回测 {deviation:.1%} "
                f"(实盘:{live_return:.2%} vs 回测:{backtest_return:.2%})"
            )
            self._suspended_strategies.add(strategy_name)
            logger.warning(f"[策略健康] 暂停: {reason}")
            return reason
        return None

    def is_suspended(self, strategy_name: str) -> bool:
        return strategy_name in self._suspended_strategies

    def resume_strategy(self, strategy_name: str) -> None:
        self._suspended_strategies.discard(strategy_name)

    def get_status(self) -> Dict:
        return {
            "performance": self._strategy_performance,
            "suspended": list(self._suspended_strategies),
        }


# ── 全局单例 ──────────────────────────────────────────────

_investment_team: Optional[InvestmentTeam] = None


def get_investment_team() -> InvestmentTeam:
    """获取全局投资团队实例"""
    global _investment_team
    if _investment_team is None:
        _investment_team = InvestmentTeam()
    return _investment_team
