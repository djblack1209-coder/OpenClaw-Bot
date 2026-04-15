"""
Core — 投资/交易领域执行器 Mixin

包含投资研究、技术分析、量化分析、风控审核、总监决策、持仓查询等方法。
从 brain_executors.py 拆分以降低扇出复杂度。
"""

import logging
from typing import Dict

from config.prompts import INVEST_DIRECTOR_DECISION_PROMPT
from src.constants import FAMILY_DEEPSEEK
from src.resilience import api_limiter

logger = logging.getLogger(__name__)


class InvestExecutorMixin:
    """投资/交易领域执行器"""

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
                symbol = params.get("symbol", "")
                side = params.get("side", "BUY")
                quantity = params.get("quantity", 0)
                entry_price = params.get("entry_price", 0)
                check = rm.check_trade(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    entry_price=entry_price,
                )
                approved = check.approved if hasattr(check, "approved") else True
                return {"source": "risk_manager", "approved": approved, "details": str(check)}
        except Exception as e:
            logger.warning(f"风控检查失败: {e}")
        # 降级：使用模块级单例
        try:
            from src.risk_manager import risk_manager

            check = risk_manager.check_trade(
                symbol=params.get("symbol", ""),
                side=params.get("side", "BUY"),
                quantity=params.get("quantity", 0),
                entry_price=params.get("entry_price", 0),
            )
            approved = check.approved if hasattr(check, "approved") else True
            return {"source": "risk_manager_singleton", "approved": approved}
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)
        # FAIL-CLOSED: 风控模块不可用时，拒绝交易而非默认放行
        return {"source": "risk_default", "approved": False, "note": "风控模块未就绪，安全起见默认拒绝（fail-closed）"}

    async def _exec_director_decision(self, params: Dict) -> Dict:
        """总监决策 — 汇总研究/TA/量化/风控结果做出最终决策"""
        symbol = params.get("symbol", "")
        try:
            from src.litellm_router import free_pool

            if free_pool:
                context_summary = params.get("_upstream_results", "")
                async with api_limiter("llm"):
                    resp = await free_pool.acompletion(
                        model_family=FAMILY_DEEPSEEK,
                        messages=[
                            {
                                "role": "user",
                                "content": f"Based on the analysis for {symbol}, give a final investment recommendation. Previous analysis: {context_summary}",
                            }
                        ],
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
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)
                return {"source": "director_llm", "decision": "hold", "confidence": 0.5, "reasoning": content[:200]}
        except Exception as e:
            logger.warning(f"总监决策失败: {e}")
        return {
            "source": "director_fallback",
            "decision": "hold",
            "confidence": 0.0,
            "reasoning": "决策模块异常，默认持有",
        }

    async def _exec_portfolio_query(self, params: Dict) -> Dict:
        """持仓查询 — 先检查连接状态，避免超时等待"""
        try:
            from src.broker_selector import ibkr

            if not getattr(ibkr, "_connected", False):
                return {
                    "source": "portfolio",
                    "positions": [],
                    "note": "券商未连接（IB Gateway 未运行）",
                    "card_type": "portfolio",
                }
            positions = await ibkr.get_positions()
            summary = await ibkr.get_account_summary()
            return {"source": "ibkr", "positions": positions, "summary": summary, "card_type": "portfolio"}
        except Exception as e:
            logger.warning(f"持仓查询失败: {e}")
        return {"source": "portfolio", "positions": [], "note": "券商未连接", "card_type": "portfolio"}
