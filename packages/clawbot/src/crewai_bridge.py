"""
CrewAI 集成层 — 搬运自 CrewAI (46.6k⭐)

替换自研的 AI 团队投票硬编码角色分配，用 CrewAI 的 Agent/Task/Crew 框架：
- 动态角色定义（不再硬编码 6 个分析师）
- 结构化任务编排（顺序/并行/层级）
- 内置工具调用（搜索、计算、代码执行）
- 记忆和学习能力

保留 ClawBot 独有能力：
- ai_team_voter.py 的投票逻辑和否决权机制
- 现有 LLM 路由（litellm_router）
- Telegram 交互界面

集成方式：CrewAI 不可用时自动降级回原有 ai_team_voter。
"""
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.bot.config import SILICONFLOW_BASE, SILICONFLOW_KEYS

logger = logging.getLogger(__name__)

_crewai_available = False
try:
    from crewai import Agent, Crew, Process, Task
    _crewai_available = True
except ImportError:
    Agent = Task = Crew = Process = None  # type: ignore[assignment,misc]
    logger.info("[CrewAIBridge] crewai 未安装，使用原有 ai_team_voter 回退")


@dataclass
class AnalystRole:
    """分析师角色定义"""
    name: str
    role: str
    goal: str
    backstory: str
    model: str = ""
    has_veto: bool = False
    weight: float = 1.0


# 默认 6 位分析师（与 ai_team_voter.py 对齐）
DEFAULT_ANALYSTS = [
    AnalystRole(
        name="技术分析师", role="Technical Analyst",
        goal="通过技术指标和图表形态判断最佳入场时机",
        backstory="10年量化交易经验，擅长 RSI/MACD/布林带等指标组合分析",
        model="Qwen/Qwen3-235B-A22B", weight=1.2,
    ),
    AnalystRole(
        name="基本面分析师", role="Fundamental Analyst",
        goal="评估公司财务健康度和估值合理性",
        backstory="CFA持证人，专注价值投资，擅长财报分析和行业对比",
        model="Qwen/Qwen3-235B-A22B", weight=1.0,
    ),
    AnalystRole(
        name="情绪分析师", role="Sentiment Analyst",
        goal="捕捉市场情绪和资金流向的变化",
        backstory="社交媒体和新闻情绪分析专家，擅长识别市场恐慌和贪婪信号",
        model="Qwen/Qwen3-8B", weight=0.8,
    ),
    AnalystRole(
        name="宏观策略师", role="Macro Strategist",
        goal="从宏观经济和政策角度评估交易环境",
        backstory="前央行研究员，擅长利率、通胀、地缘政治对市场的影响分析",
        model="Qwen/Qwen3-8B", weight=0.9,
    ),
    AnalystRole(
        name="风控官", role="Risk Officer",
        goal="识别潜在风险，确保每笔交易的风险可控",
        backstory="20年风控经验，经历过多次金融危机，对尾部风险极度敏感",
        model="Qwen/Qwen3-235B-A22B", weight=1.5, has_veto=True,
    ),
    AnalystRole(
        name="首席策略师", role="Chief Strategist",
        goal="综合所有分析师意见，做出最终交易决策",
        backstory="对冲基金合伙人，擅长多维度信息整合和逆向思维",
        model="Qwen/Qwen3-235B-A22B", weight=1.5, has_veto=True,
    ),
]


class CrewAIBridge:
    """
    CrewAI 桥接层

    将 ClawBot 的 AI 团队投票升级为 CrewAI 的结构化多 Agent 协作。
    CrewAI 不可用时自动降级回原有 ai_team_voter。
    """

    def __init__(self, analysts: list[AnalystRole] | None = None,
                 llm_fn: Callable | None = None):
        self.analysts = analysts or DEFAULT_ANALYSTS
        self.llm_fn = llm_fn
        self._crew = None
        self._using_crewai = False

        if _crewai_available:
            try:
                self._build_crew()
                self._using_crewai = True
                logger.info("[CrewAIBridge] CrewAI 模式启动 (%d agents)", len(self.analysts))
            except Exception as e:
                logger.warning("[CrewAIBridge] CrewAI 初始化失败: %s", e)

    def _build_crew(self):
        """构建 CrewAI Crew — 通过 LiteLLM 使用免费模型"""
        if not _crewai_available:
            return

        # CrewAI 原生支持 litellm 前缀: "litellm/model_name"
        # 配置环境变量让 CrewAI 走 LiteLLM Router
        if SILICONFLOW_KEYS:
            os.environ.setdefault("OPENAI_API_KEY", SILICONFLOW_KEYS[0])
            os.environ.setdefault("OPENAI_API_BASE", SILICONFLOW_BASE)

        agents = []
        for a in self.analysts:
            # 用 LiteLLM 前缀指定模型，CrewAI 会自动走 litellm
            llm_model = f"openai/{a.model}" if a.model else "openai/Qwen/Qwen3-235B-A22B"
            agent = Agent(
                role=a.role,
                goal=a.goal,
                backstory=a.backstory,
                verbose=False,
                allow_delegation=False,
                llm=llm_model,
            )
            agents.append(agent)
        self._agents = agents

    async def analyze_trade(
        self, symbol: str, analysis_data: dict[str, Any],
        notify_fn: Callable | None = None,
    ) -> dict[str, Any]:
        """
        用 CrewAI 多 Agent 分析交易机会。

        返回格式与 ai_team_voter 兼容：
        {
            "decision": "BUY" | "HOLD" | "SKIP",
            "confidence": 0.0-1.0,
            "votes": [...],
            "vetoed": bool,
            "engine": "crewai" | "fallback",
        }
        """
        if not self._using_crewai:
            return await self._fallback_analyze(symbol, analysis_data, notify_fn)

        try:
            tasks = []
            for i, agent in enumerate(self._agents):
                analyst = self.analysts[i]
                task = Task(
                    description=(
                        f"分析 {symbol} 的交易机会。\n"
                        f"技术数据: {_format_analysis(analysis_data)}\n\n"
                        f"请从你的专业角度（{analyst.role}）给出：\n"
                        f"1. 投票: BUY / HOLD / SKIP\n"
                        f"2. 信心分: 1-10\n"
                        f"3. 理由: 一句话\n"
                        f"输出 JSON: {{\"vote\": \"BUY\", \"confidence\": 8, \"reason\": \"...\"}}"
                    ),
                    expected_output="JSON with vote, confidence, reason",
                    agent=agent,
                )
                tasks.append(task)

            crew = Crew(
                agents=self._agents,
                tasks=tasks,
                process=Process.sequential,
                verbose=False,
            )
            result = crew.kickoff()

            # 解析投票结果
            votes = self._parse_crew_result(result, symbol)
            return self._tally_votes(votes, symbol)

        except Exception as e:
            logger.warning("[CrewAIBridge] CrewAI 分析失败: %s，回退原有模式", e)
            return await self._fallback_analyze(symbol, analysis_data, notify_fn)

    async def _fallback_analyze(
        self, symbol: str, analysis_data: dict, notify_fn: Callable | None,
    ) -> dict[str, Any]:
        """降级回原有 ai_team_voter"""
        try:
            from src.ai_team_voter import run_team_vote
            result = await run_team_vote(
                symbol=symbol,
                analysis=analysis_data,
                notify_func=notify_fn,
            )
            if result:
                result["engine"] = "fallback"
            return result or {"decision": "SKIP", "confidence": 0, "engine": "fallback"}
        except ImportError:
            return {"decision": "SKIP", "confidence": 0, "engine": "none",
                    "error": "ai_team_voter 不可用"}

    def _parse_crew_result(self, result, symbol: str) -> list[dict]:
        """解析 CrewAI 输出为投票列表"""
        from json_repair import loads as jloads
        votes = []
        raw = str(result)
        # 尝试从输出中提取多个 JSON 块
        import re
        json_blocks = re.findall(r'\{[^{}]*"vote"[^{}]*\}', raw)
        for i, block in enumerate(json_blocks):
            try:
                data = jloads(block)
                analyst = self.analysts[i] if i < len(self.analysts) else self.analysts[-1]
                votes.append({
                    "analyst": analyst.name,
                    "role": analyst.role,
                    "vote": data.get("vote", "HOLD").upper(),
                    "confidence": min(10, max(1, int(data.get("confidence", 5)))),
                    "reason": data.get("reason", ""),
                    "has_veto": analyst.has_veto,
                    "weight": analyst.weight,
                })
            except Exception as e:  # noqa: F841
                continue

        # 如果解析不足，补充默认 HOLD 票
        while len(votes) < len(self.analysts):
            idx = len(votes)
            a = self.analysts[idx]
            votes.append({
                "analyst": a.name, "role": a.role,
                "vote": "HOLD", "confidence": 5,
                "reason": "分析超时", "has_veto": a.has_veto, "weight": a.weight,
            })
        return votes

    def _tally_votes(self, votes: list[dict], symbol: str) -> dict[str, Any]:
        """计票（与 ai_team_voter 逻辑一致）"""
        buy_count = sum(1 for v in votes if v["vote"] == "BUY")
        threshold = max(4, len(votes) * 2 // 3)

        # 否决权检查
        vetoed = False
        veto_reason = ""
        for v in votes:
            if v["has_veto"] and v["vote"] == "SKIP":
                vetoed = True
                veto_reason = f"{v['analyst']} 行使否决权: {v['reason']}"
                break

        # 加权置信度
        total_weight = sum(v["weight"] for v in votes)
        weighted_conf = sum(v["confidence"] * v["weight"] for v in votes) / max(total_weight, 1)

        if vetoed:
            decision = "SKIP"
        elif buy_count >= threshold:
            decision = "BUY"
        elif buy_count >= threshold - 1:
            decision = "HOLD"
        else:
            decision = "SKIP"

        return {
            "decision": decision,
            "confidence": round(weighted_conf / 10, 2),
            "buy_votes": buy_count,
            "total_votes": len(votes),
            "threshold": threshold,
            "vetoed": vetoed,
            "veto_reason": veto_reason,
            "votes": votes,
            "engine": "crewai",
            "symbol": symbol,
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            "available": _crewai_available,
            "using_crewai": self._using_crewai,
            "analyst_count": len(self.analysts),
            "analysts": [a.name for a in self.analysts],
        }


def _format_analysis(data: dict) -> str:
    """格式化分析数据为简洁文本"""
    parts = []
    for k, v in list(data.items())[:15]:
        if isinstance(v, float):
            parts.append(f"{k}: {v:.2f}")
        else:
            parts.append(f"{k}: {v}")
    return " | ".join(parts)


# ── 全局实例 ──

_bridge: CrewAIBridge | None = None


def init_crewai_bridge(analysts=None, llm_fn=None) -> CrewAIBridge:
    global _bridge
    _bridge = CrewAIBridge(analysts=analysts, llm_fn=llm_fn)
    return _bridge


def get_crewai_bridge() -> CrewAIBridge | None:
    return _bridge
