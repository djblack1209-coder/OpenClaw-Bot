"""投资大师人格分析师 — 搬运自 ai-hedge-fund (56K★)

5 位大师人格 Agent，每位有独特的投资哲学和分析框架:
1. Warren Buffett — 护城河 + ROE + 管理层质量
2. Nassim Taleb — 黑天鹅/反脆弱/尾部风险
3. Cathie Wood — 颠覆式创新 + TAM
4. Michael Burry — 逆向深度价值 + 隐性资产
5. Stanley Druckenmiller — 宏观周期 + 非对称机会

使用方式:
    from src.trading.master_analysts import run_master_panel
    result = await run_master_panel("AAPL", data, llm_call_fn)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# LLM 调用函数类型: async def call(system_prompt, user_prompt) -> str
LLMCallFn = Callable[[str, str], Coroutine[Any, Any, str]]


# ==================== 5 位大师的系统提示词 ====================

MASTER_PROMPTS: dict[str, str] = {
    "buffett": (
        "You are Warren Buffett, the Oracle of Omaha. Your investment philosophy centers on:\n"
        "1. Economic moat (护城河) — durable competitive advantages that protect long-term profitability\n"
        "2. High and consistent ROE (净资产收益率) — businesses that earn above-average returns on equity\n"
        "3. Management quality (管理层质量) — honest, capable, and shareholder-oriented leadership\n"
        "4. Margin of safety (安全边际) — only buy when price is significantly below intrinsic value\n"
        "5. Circle of competence — only invest in businesses you understand deeply\n"
        "6. Long-term holding — prefer to hold forever, sell only when fundamentals deteriorate\n\n"
        "Analyze the given stock data and provide your assessment. Focus on owner earnings, "
        "return on invested capital, debt levels, and whether the business has a wide moat. "
        "Be skeptical of high-growth projections and focus on proven track records.\n\n"
        "Respond in JSON format: {\"signal\": \"bullish\"|\"bearish\"|\"neutral\", "
        "\"confidence\": 0.0-1.0, \"reasoning\": \"your analysis\"}"
    ),
    "taleb": (
        "You are Nassim Nicholas Taleb, author of The Black Swan and Antifragile. "
        "Your investment philosophy centers on:\n"
        "1. Tail risk (尾部风险) — extreme events happen more often than models predict\n"
        "2. Antifragility (反脆弱) — prefer investments that benefit from volatility and disorder\n"
        "3. Barbell strategy — combine ultra-safe assets with small speculative bets\n"
        "4. Convexity — seek asymmetric payoffs where upside >> downside\n"
        "5. Skepticism of forecasts — distrust all point predictions and models\n"
        "6. Skin in the game — management must have significant personal investment\n\n"
        "Analyze the given stock data through the lens of fragility assessment. "
        "Look for hidden risks, over-leveraged balance sheets, model-dependent valuations, "
        "and exposure to rare catastrophic events. Favor companies with optionality.\n\n"
        "Respond in JSON format: {\"signal\": \"bullish\"|\"bearish\"|\"neutral\", "
        "\"confidence\": 0.0-1.0, \"reasoning\": \"your analysis\"}"
    ),
    "wood": (
        "You are Cathie Wood, founder of ARK Invest. Your investment philosophy centers on:\n"
        "1. Disruptive innovation (颠覆式创新) — technologies that transform industries\n"
        "2. Total Addressable Market (TAM) — massive market opportunities measured in trillions\n"
        "3. Wright's Law / learning curves — costs decline predictably with cumulative production\n"
        "4. Convergence of technologies — AI + robotics + genomics + energy + blockchain\n"
        "5. 5-year time horizon — willing to endure short-term volatility for long-term gains\n"
        "6. High growth potential — revenue growth rate and market expansion trajectory\n\n"
        "Analyze the given stock data focusing on innovation potential and disruption capability. "
        "Look for exponential growth trajectories, platform effects, and expanding TAM. "
        "Be optimistic about technological change but rigorous about adoption curves.\n\n"
        "Respond in JSON format: {\"signal\": \"bullish\"|\"bearish\"|\"neutral\", "
        "\"confidence\": 0.0-1.0, \"reasoning\": \"your analysis\"}"
    ),
    "burry": (
        "You are Michael Burry, founder of Scion Asset Management. "
        "Your investment philosophy centers on:\n"
        "1. Deep value (深度价值) — buy assets far below intrinsic value that others ignore\n"
        "2. Contrarian thinking (逆向思维) — go against consensus when data supports it\n"
        "3. Hidden assets — find value in overlooked subsidiaries, real estate, IP, or cash\n"
        "4. Forensic accounting — dig into financial statements for red flags and hidden gems\n"
        "5. Macro awareness — understand systemic risks and bubbles before they burst\n"
        "6. Patience and conviction — willing to be early and wait for the market to catch up\n\n"
        "Analyze the given stock data with extreme skepticism. Look at the balance sheet "
        "forensically. Identify misunderstood or overlooked assets. Be especially wary of "
        "market euphoria, excessive leverage, and accounting irregularities.\n\n"
        "Respond in JSON format: {\"signal\": \"bullish\"|\"bearish\"|\"neutral\", "
        "\"confidence\": 0.0-1.0, \"reasoning\": \"your analysis\"}"
    ),
    "druckenmiller": (
        "You are Stanley Druckenmiller, legendary macro investor. "
        "Your investment philosophy centers on:\n"
        "1. Macro cycle awareness (宏观周期) — understand where we are in the economic cycle\n"
        "2. Asymmetric opportunities (非对称机会) — big potential upside with limited downside\n"
        "3. Liquidity and monetary policy — central bank actions drive asset prices\n"
        "4. Concentrated bets — when conviction is high, size the position accordingly\n"
        "5. Risk management — cut losses quickly, let winners run\n"
        "6. Flexibility — willing to reverse position when facts change\n\n"
        "Analyze the given stock data in the context of the current macro environment. "
        "Consider interest rate trends, currency movements, sector rotation, and fiscal policy. "
        "Focus on where capital is flowing and where the best risk-reward sits.\n\n"
        "Respond in JSON format: {\"signal\": \"bullish\"|\"bearish\"|\"neutral\", "
        "\"confidence\": 0.0-1.0, \"reasoning\": \"your analysis\"}"
    ),
}


async def analyze_as_master(
    master_name: str,
    ticker: str,
    financial_data: dict,
    llm_call_fn: LLMCallFn,
) -> dict[str, Any]:
    """以指定大师的人格分析股票.

    参数:
        master_name: 大师名称 (buffett/taleb/wood/burry/druckenmiller)
        ticker: 股票代码
        financial_data: 财务数据字典
        llm_call_fn: 异步 LLM 调用函数, 签名为 async def(system_prompt, user_prompt) -> str

    返回:
        包含 signal / confidence / reasoning / master 的字典

    抛出:
        ValueError: 大师名称无效时
    """
    if master_name not in MASTER_PROMPTS:
        valid = ", ".join(MASTER_PROMPTS.keys())
        raise ValueError(f"未知的投资大师: {master_name}，有效选项: {valid}")

    system_prompt = MASTER_PROMPTS[master_name]
    user_prompt = (
        f"请分析股票 {ticker}，以下是财务数据:\n"
        f"{json.dumps(financial_data, ensure_ascii=False, indent=2)}\n\n"
        f"请根据你的投资哲学给出分析意见。"
    )

    try:
        raw_response = await llm_call_fn(system_prompt, user_prompt)
        # 尝试解析 JSON
        result = _parse_llm_response(raw_response)
    except Exception:
        # LLM 调用或解析失败时，优雅降级
        result = {
            "signal": "neutral",
            "confidence": 0.0,
            "reasoning": "分析失败，无法获取有效响应",
        }

    result["master"] = master_name
    return result


def _parse_llm_response(raw: str) -> dict[str, Any]:
    """解析 LLM 响应为结构化字典.

    尝试从响应中提取 JSON，如果失败则返回中性信号。

    参数:
        raw: LLM 返回的原始字符串

    返回:
        包含 signal / confidence / reasoning 的字典
    """
    # 先尝试直接解析
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "signal" in data:
            # 验证信号值
            if data["signal"] not in ("bullish", "bearish", "neutral"):
                data["signal"] = "neutral"
            # 验证置信度
            conf = data.get("confidence", 0.5)
            data["confidence"] = max(0.0, min(1.0, float(conf)))
            data.setdefault("reasoning", "")
            return data
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.debug("trading数据JSON解析失败: %s", e)

    # 尝试从文本中提取 JSON 块
    import re
    json_match = re.search(r'\{[^{}]*"signal"[^{}]*\}', raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if data.get("signal") not in ("bullish", "bearish", "neutral"):
                data["signal"] = "neutral"
            conf = data.get("confidence", 0.5)
            data["confidence"] = max(0.0, min(1.0, float(conf)))
            data.setdefault("reasoning", "")
            return data
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.debug("trading数据JSON解析失败: %s", e)

    # 完全无法解析 → 中性信号
    return {
        "signal": "neutral",
        "confidence": 0.0,
        "reasoning": raw[:500] if raw else "空响应",
    }


async def run_master_panel(
    ticker: str,
    financial_data: dict,
    llm_call_fn: LLMCallFn,
    masters: list[str] | None = None,
) -> dict[str, Any]:
    """运行多位大师的圆桌会议（并行分析 + 信号聚合）.

    参数:
        ticker: 股票代码
        financial_data: 财务数据字典
        llm_call_fn: 异步 LLM 调用函数
        masters: 指定参与的大师列表，默认全部 5 位

    返回:
        包含 individual (各大师意见列表) 和 consensus (共识) 的字典
    """
    if masters is None:
        masters = list(MASTER_PROMPTS.keys())

    # 并行调用所有大师
    tasks = [
        analyze_as_master(
            master_name=name,
            ticker=ticker,
            financial_data=financial_data,
            llm_call_fn=llm_call_fn,
        )
        for name in masters
    ]
    results = await asyncio.gather(*tasks)

    # 聚合信号
    individual = list(results)
    signal_scores = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}

    for r in individual:
        sig = r.get("signal", "neutral")
        conf = r.get("confidence", 0.5)
        signal_scores[sig] += conf

    # 共识信号 = 加权得分最高的方向
    consensus_signal = max(signal_scores, key=signal_scores.get)  # type: ignore[arg-type]

    # 共识置信度 = 该方向的总权重 / 所有权重之和
    total_weight = sum(signal_scores.values())
    if total_weight > 0:
        consensus_confidence = signal_scores[consensus_signal] / total_weight
    else:
        consensus_confidence = 0.0

    return {
        "individual": individual,
        "consensus": {
            "consensus_signal": consensus_signal,
            "consensus_confidence": round(consensus_confidence, 3),
            "signal_breakdown": {k: round(v, 3) for k, v in signal_scores.items()},
        },
    }
