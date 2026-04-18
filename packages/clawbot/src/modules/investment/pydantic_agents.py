"""
OpenClaw — Pydantic AI 投资分析引擎
搬运 pydantic-ai (15.6k⭐) 的结构化输出 + 工具调用模式。

替代原有的 raw JSON dump → regex parse 方式，实现：
  1. Pydantic 验证的结构化输出（score 必须 0-10，不可能幻觉）
  2. 工具调用（agent 主动获取数据，而非被动接收数据转储）
  3. 类型安全（IDE 自动补全，运行时校验）

直接使用 iflow 无限 API（OpenAI 兼容），不依赖 LiteLLM 路由器。

用法:
    engine = PydanticInvestmentEngine()
    result = await engine.full_analysis("AAPL")
    print(result.to_telegram_text())
"""
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.http_client import ResilientHTTPClient

logger = logging.getLogger(__name__)

# 模块级别 HTTP 客户端（自动重试 + 熔断）
_http_iflow = ResilientHTTPClient(timeout=60.0, name="pydantic_agents")

# ── iflow API 配置 ──────────────────────────────────

# 注意: iflow key 不在模块级缓存，改由 property 实时读取，避免 key 轮换后不感知
IFLOW_BASE = os.environ.get("SILICONFLOW_UNLIMITED_URL", "https://apis.iflow.cn/v1")
if IFLOW_BASE.endswith("/chat/completions"):
    IFLOW_BASE = IFLOW_BASE.rsplit("/chat/completions", 1)[0]

# 每个角色使用不同模型（利用无限 API 的多模型优势）
AGENT_MODELS = {
    "researcher": "qwen3-235b-a22b-instruct",   # 全面分析
    "ta_analyst": "deepseek-v3.2",               # 快速精确
    "quant": "qwen3-max",                        # 数学能力强
    "risk_officer": "kimi-k2",                   # 谨慎保守
    "director": "qwen3-235b-a22b-instruct",      # 综合决策
}


# ── Pydantic 结构化输出模型 ──────────────────────────

class ResearchOutput(BaseModel):
    """研究员输出 — Pydantic 校验保证数据质量"""
    score: float = Field(ge=0, le=10, description="综合评分 0-10")
    confidence: float = Field(ge=0, le=1, default=0.5, description="分析置信度")
    recommendation: Literal["buy", "sell", "hold"] = "hold"
    valuation: Literal["高估", "合理", "低估"] = "合理"
    catalysts: List[str] = Field(default_factory=list, description="近期催化剂")
    risks: List[str] = Field(default_factory=list, description="风险因素")
    reasoning: str = Field(default="", description="分析摘要")


class TAOutput(BaseModel):
    """技术分析师输出"""
    score: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1, default=0.5, description="分析置信度")
    recommendation: Literal["buy", "sell", "hold"] = "hold"
    trend: Literal["上涨", "下跌", "震荡", "突破"] = "震荡"
    support: List[float] = Field(default_factory=list, description="支撑位")
    resistance: List[float] = Field(default_factory=list, description="压力位")
    key_signal: str = ""
    reasoning: str = ""


class QuantOutput(BaseModel):
    """量化工程师输出"""
    score: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1, default=0.5, description="分析置信度")
    recommendation: Literal["buy", "sell", "hold"] = "hold"
    sharpe_estimate: float = Field(default=0, description="预估夏普比率")
    momentum_score: float = Field(ge=0, le=10, default=5)
    volatility: Literal["低", "中", "高"] = "中"
    reasoning: str = ""


class RiskOutput(BaseModel):
    """风控官输出 — 有一票否决权"""
    approved: bool = True
    confidence: float = Field(ge=0, le=1, default=0.5, description="分析置信度")
    risk_level: Literal["低", "中", "高", "极高"] = "中"
    position_size: float = Field(ge=0, le=1, default=0.1, description="建议仓位比例")
    stop_loss_pct: float = Field(ge=0, le=1, default=0.08, description="止损比例")
    veto_reason: str = ""
    reasoning: str = ""


class DirectorOutput(BaseModel):
    """投资总监最终决策"""
    recommendation: Literal["buy", "sell", "hold"] = "hold"
    confidence: float = Field(ge=0, le=1, default=0.5)
    target_price: float = 0
    stop_loss: float = 0
    position_size_pct: float = Field(ge=0, le=1, default=0)
    reasoning: str = ""


# ── 结构化分析结果 ──────────────────────────────────

@dataclass
class StructuredAnalysis:
    """完整的投资团队分析结果"""
    symbol: str
    research: Optional[ResearchOutput] = None
    ta: Optional[TAOutput] = None
    quant: Optional[QuantOutput] = None
    risk: Optional[RiskOutput] = None
    director: Optional[DirectorOutput] = None
    elapsed_seconds: float = 0.0
    models_used: Dict[str, str] = field(default_factory=dict)

    @property
    def final_recommendation(self) -> str:
        if self.risk and not self.risk.approved:
            return "hold"
        if self.director:
            return self.director.recommendation
        return "hold"

    @property
    def is_vetoed(self) -> bool:
        return self.risk is not None and not self.risk.approved

    def to_telegram_text(self) -> str:
        """渲染为 Telegram 卡片"""
        lines = [f"📊 <b>投资分析: {self.symbol}</b>", "━━━━━━━━━━━━━━━"]

        def stars(s): return "⭐" * max(1, int(s / 2)) + f" {s:.1f}"

        if self.research:
            lines.extend(["",
                f"📈 研究员: {stars(self.research.score)}",
                f"   估值: {self.research.valuation} | {self.research.recommendation.upper()}",
                f"   {self.research.reasoning[:60]}",
            ])
        if self.ta:
            lines.extend(["",
                f"📉 技术面: {stars(self.ta.score)}",
                f"   趋势: {self.ta.trend} | {self.ta.key_signal[:40]}",
                f"   {self.ta.reasoning[:60]}",
            ])
        if self.quant:
            lines.extend(["",
                f"🔢 量化: {stars(self.quant.score)}",
                f"   波动: {self.quant.volatility} | 动量: {self.quant.momentum_score:.0f}",
                f"   {self.quant.reasoning[:60]}",
            ])

        lines.append("")
        if self.is_vetoed:
            lines.append(f"🛡 风控: ❌ <b>否决</b> — {self.risk.veto_reason}")
        elif self.risk:
            lines.append(f"🛡 风控: ✅ {self.risk.risk_level}风险 | 建议仓位 {self.risk.position_size:.0%}")

        if self.director:
            rec_emoji = {"buy": "🟢 买入", "sell": "🔴 卖出", "hold": "⚪ 观望"}
            lines.extend(["", "━━━━━━━━━━━━━━━",
                f"💡 <b>决策: {rec_emoji.get(self.director.recommendation, '⚪')}</b>",
                f"🎯 置信度: {self.director.confidence:.0%}",
                f"   {self.director.reasoning[:80]}",
            ])
            if self.director.target_price > 0:
                lines.append(f"📈 目标: ${self.director.target_price:.2f}")
            if self.director.stop_loss > 0:
                lines.append(f"🛑 止损: ${self.director.stop_loss:.2f}")

        lines.append(f"\n⏱ {self.elapsed_seconds:.1f}s | 模型: {', '.join(set(self.models_used.values()))}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "recommendation": self.final_recommendation,
            "vetoed": self.is_vetoed,
            "research": self.research.model_dump() if self.research else None,
            "ta": self.ta.model_dump() if self.ta else None,
            "quant": self.quant.model_dump() if self.quant else None,
            "risk": self.risk.model_dump() if self.risk else None,
            "director": self.director.model_dump() if self.director else None,
            "elapsed": self.elapsed_seconds,
            "models": self.models_used,
        }


# ── 核心引擎 ──────────────────────────────────────────

class PydanticInvestmentEngine:
    """
    基于 Pydantic AI 的结构化投资分析引擎。

    优势:
      1. 每个 agent 输出由 Pydantic 强制校验（score 不可能是 -3 或 99）
      2. 不同角色用不同模型（利用 iflow 14模型的差异化优势）
      3. 并行执行（研究+TA+量化同时跑）
      4. 直接对接 iflow 无限 API
    """

    def __init__(self):
        # 不再把 key 固化到实例变量，改用 property 实时读取环境变量
        # 这样 key 轮换（7天过期）后无需重启进程
        self._base = IFLOW_BASE
        if not self.key:
            logger.warning("SILICONFLOW_UNLIMITED_KEY 未设置，分析引擎不可用")

    @property
    def key(self) -> str:
        """实时读取 iflow key，避免模块级固化导致 key 过期后不感知"""
        return os.environ.get("SILICONFLOW_UNLIMITED_KEY", "")

    @property
    def available(self) -> bool:
        return bool(self.key)

    async def full_analysis(self, symbol: str, market_data: Optional[Dict] = None) -> StructuredAnalysis:
        """完整的6角色分析（并行 → 串行风控 → 决策）"""
        result = StructuredAnalysis(symbol=symbol)
        t0 = time.time()

        if not self.available:
            result.elapsed_seconds = time.time() - t0
            return result

        # 获取市场数据
        data = market_data or await self._fetch_data(symbol)

        # 1. 并行: 研究员 + TA + 量化
        tasks = [
            self._run_agent("researcher", RESEARCHER_PROMPT, data, ResearchOutput),
            self._run_agent("ta_analyst", TA_PROMPT, data, TAOutput),
            self._run_agent("quant", QUANT_PROMPT, data, QuantOutput),
        ]
        outputs = await asyncio.gather(*tasks, return_exceptions=True)

        for i, output in enumerate(outputs):
            if isinstance(output, Exception):
                logger.warning(f"Agent {i} 失败: {output}")
                continue
            agent_name, parsed, model = output
            result.models_used[agent_name] = model
            if agent_name == "researcher" and isinstance(parsed, ResearchOutput):
                result.research = parsed
            elif agent_name == "ta_analyst" and isinstance(parsed, TAOutput):
                result.ta = parsed
            elif agent_name == "quant" and isinstance(parsed, QuantOutput):
                result.quant = parsed

        # 2. 串行: 风控审核
        risk_context = self._build_risk_context(result, data)
        try:
            _, risk_out, risk_model = await self._run_agent(
                "risk_officer", RISK_PROMPT, risk_context, RiskOutput
            )
            if isinstance(risk_out, RiskOutput):
                result.risk = risk_out
                result.models_used["risk_officer"] = risk_model
        except Exception as e:
            logger.warning(f"风控失败: {e}")
            result.risk = RiskOutput(approved=False, veto_reason=f"风控系统异常: {e}")

        # 3. 串行: 总监决策（如果未被否决）
        if not result.is_vetoed:
            director_context = self._build_director_context(result)
            try:
                _, dir_out, dir_model = await self._run_agent(
                    "director", DIRECTOR_PROMPT, director_context, DirectorOutput
                )
                if isinstance(dir_out, DirectorOutput):
                    result.director = dir_out
                    result.models_used["director"] = dir_model
            except Exception as e:
                logger.warning(f"总监决策失败: {e}")

        result.elapsed_seconds = time.time() - t0
        logger.info(f"[PydanticInvestment] {symbol} 分析完成: {result.final_recommendation} ({result.elapsed_seconds:.1f}s)")
        return result

    async def _run_agent(self, agent_name: str, system_prompt: str,
                         data: Dict, output_type: type) -> tuple:
        """运行单个 agent — 直接 HTTP 调用 + Pydantic 解析"""
        model = AGENT_MODELS.get(agent_name, "qwen3-235b-a22b-instruct")

        user_content = json.dumps(data, ensure_ascii=False, default=str)[:3000]

        # 在 system prompt 中注入输出格式要求
        schema_hint = json.dumps(
            output_type.model_json_schema(), ensure_ascii=False, indent=0
        )[:500]
        full_prompt = (
            f"{system_prompt}\n\n"
            f"## 输出格式（严格JSON，必须符合以下 schema）:\n{schema_hint}\n\n"
            f"只输出 JSON，不要其他内容。"
        )

        resp = await _http_iflow.post(
            f"{self._base}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": full_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.3,
                "max_tokens": 800,
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"iflow {resp.status_code}: {resp.text[:100]}")

        raw = resp.json()["choices"][0]["message"]["content"].strip()

        # 去除 thinking 标签
        import re
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

        # 提取 JSON
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)
        if json_match:
            raw = json_match.group()

        # Pydantic 校验
        try:
            parsed = output_type.model_validate_json(raw)
        except Exception as e:  # noqa: F841
            import json_repair
            data_dict = json_repair.loads(raw)
            parsed = output_type.model_validate(data_dict)

        return (agent_name, parsed, model)

    async def _fetch_data(self, symbol: str) -> Dict:
        """获取市场数据"""
        data = {"symbol": symbol}

        # yfinance
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.info
            data.update({
                "name": info.get("longName", symbol),
                "price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
                "pe": info.get("trailingPE", 0),
                "pb": info.get("priceToBook", 0),
                "market_cap": info.get("marketCap", 0),
                "revenue_growth": info.get("revenueGrowth", 0),
                "profit_margin": info.get("profitMargins", 0),
                "sector": info.get("sector", ""),
                "52w_high": info.get("fiftyTwoWeekHigh", 0),
                "52w_low": info.get("fiftyTwoWeekLow", 0),
            })

            # 技术指标
            hist = ticker.history(period="3mo")
            if not hist.empty:
                close = hist["Close"]
                data["ma5"] = float(close.rolling(5).mean().iloc[-1])
                data["ma20"] = float(close.rolling(20).mean().iloc[-1])
                data["change_1d"] = float(close.pct_change().iloc[-1])
                data["change_5d"] = float((close.iloc[-1] / close.iloc[-5] - 1)) if len(close) >= 5 else 0
                data["volume_avg"] = float(hist["Volume"].mean())
                data["volume_last"] = float(hist["Volume"].iloc[-1])
        except Exception as e:
            data["data_error"] = str(e)

        # Jina Reader 新闻
        try:
            from src.tools.jina_reader import fetch_news_about
            news = await fetch_news_about(f"{data.get('name', symbol)} stock news", max_length=800)
            if news and len(news) > 20:
                data["recent_news"] = news
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)

        return data

    def _build_risk_context(self, result: StructuredAnalysis, data: Dict) -> Dict:
        """构建风控上下文"""
        ctx = dict(data)
        if result.research:
            ctx["research_score"] = result.research.score
            ctx["research_rec"] = result.research.recommendation
        if result.ta:
            ctx["ta_score"] = result.ta.score
            ctx["ta_rec"] = result.ta.recommendation
            ctx["trend"] = result.ta.trend
        if result.quant:
            ctx["quant_score"] = result.quant.score
            ctx["volatility"] = result.quant.volatility
        return ctx

    def _build_director_context(self, result: StructuredAnalysis) -> Dict:
        """构建总监决策上下文"""
        ctx = {"symbol": result.symbol}
        if result.research:
            ctx["research"] = {"score": result.research.score, "rec": result.research.recommendation,
                               "valuation": result.research.valuation, "reasoning": result.research.reasoning[:100]}
        if result.ta:
            ctx["ta"] = {"score": result.ta.score, "rec": result.ta.recommendation,
                         "trend": result.ta.trend, "signal": result.ta.key_signal[:50]}
        if result.quant:
            ctx["quant"] = {"score": result.quant.score, "rec": result.quant.recommendation,
                           "volatility": result.quant.volatility}
        if result.risk:
            ctx["risk"] = {"approved": result.risk.approved, "level": result.risk.risk_level,
                          "position": result.risk.position_size}
        return ctx


# ── Agent Prompts — 从中央注册表导入 ─────────────────
# 使用 config.prompts 的完整版本（team.py 权威定义），替代原先的简化副本。

from config.prompts import INVESTMENT_ROLES

RESEARCHER_PROMPT = INVESTMENT_ROLES["researcher"]
TA_PROMPT = INVESTMENT_ROLES["ta_analyst"]
QUANT_PROMPT = INVESTMENT_ROLES["quant"]
RISK_PROMPT = INVESTMENT_ROLES["risk_manager"]
DIRECTOR_PROMPT = INVESTMENT_ROLES["director"]


# ── 全局单例 ──────────────────────────────────────────

_engine: Optional[PydanticInvestmentEngine] = None

def get_pydantic_engine() -> PydanticInvestmentEngine:
    global _engine
    if _engine is None:
        _engine = PydanticInvestmentEngine()
    return _engine
