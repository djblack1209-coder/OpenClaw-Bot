"""
OpenClaw OMEGA — 成本控制 (Cost Control)
追踪每次 LLM 调用的成本，实施日预算限制，支持成本感知的模型路由。
"""

import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
COST_DIR = _BASE_DIR / "data" / "cost"
DAILY_LOG = COST_DIR / "daily_costs.jsonl"

# 旧版本参考报价（每百万 token，美元）；仅供兼容估算，非供应商现价或预算授权。
MODEL_COSTS: dict[str, dict[str, float]] = {
    # 高端
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    # 中端
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    # 经济
    "claude-haiku-3.5": {"input": 0.8, "output": 4.0},
}

COMPLEXITY_TO_MODEL = {
    "simple": "qwen3-235b",  # 免费
    "moderate": "claude-haiku-3.5",  # $0.8/M
    "complex": "claude-sonnet-4",  # $3/M
    "critical": "claude-opus-4",  # $15/M
}


@dataclass
class CostRecord:
    timestamp: float
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    task_type: str
    date: str


class CostController:
    """费用查询门面。启用前显示覆盖未知；实际调用使用事务化尝试账本。"""

    def __init__(self, daily_budget_usd: float = 50.0, *, ledger_path=None, clock=None):
        from src.core.cost_ledger import CostLedger, money_units

        money_units(daily_budget_usd)
        self._daily_budget = daily_budget_usd
        self.ledger = CostLedger(ledger_path or COST_DIR / "cost.sqlite3", clock=clock)

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        """旧表仅作明确模型 ID 的估价参考，不用于部署的预算授权。"""
        from src.core.cost_policy import tokens

        tokens(input_tokens)
        tokens(output_tokens)
        pricing = MODEL_COSTS.get(model)
        if pricing is None:
            return None
        return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

    def record_cost(self, model: str, cost: float, task_type: str = "unknown") -> None:
        """兼容显式手工记录；主链必须通过 reserve/dispatch/settle。"""
        from uuid import uuid4

        from src.core.cost_ledger import money_units

        money_units(cost)
        attempt = uuid4().hex
        self.ledger.reserve(
            attempt_id=attempt,
            request_id=attempt,
            provider="manual",
            deployment_id=model,
            model=model,
            price_snapshot="manual-unverified",
            task_type=task_type,
            budget_usd=self._daily_budget,
            max_cost_usd=cost,
        )
        self.ledger.dispatch(attempt)
        self.ledger.settle(attempt, cost)

    def get_daily_spend(self) -> float | None:
        return self.ledger.stats()["today_spend"]

    def is_over_budget(self) -> bool:
        stats = self.get_stats()
        return stats["over_budget"]

    def suggest_model(self, task_complexity: str = "moderate") -> str:
        stats = self.get_stats()
        available = stats["available_usd"]
        if available is None or self._daily_budget <= 0:
            return "qwen3-235b"
        ratio = 1 - available / self._daily_budget
        if ratio > 0.9:
            return "qwen3-235b"
        if ratio > 0.7:
            return "claude-sonnet-4" if task_complexity == "critical" else "qwen3-235b"
        return COMPLEXITY_TO_MODEL.get(task_complexity, "qwen3-235b")

    def get_weekly_report(self) -> dict:
        stats = self.get_stats()
        week_start = (date.fromisoformat(stats["budget_day"]) - timedelta(days=6)).isoformat()
        daily = {
            day: value for day, value in stats["daily_breakdown"].items() if week_start <= day <= stats["budget_day"]
        }
        return {
            **stats,
            "weekly_total_usd": sum(daily.values())
            if stats["accounting_complete"] and stats["coverage_started_day"] <= week_start
            else None,
            "known_weekly_total_usd": sum(daily.values()),
            "daily_budget_usd": self._daily_budget,
            "today_spend_usd": stats["today_spend"],
            "daily_breakdown": daily,
        }

    def get_stats(self) -> dict:
        stats = self.ledger.stats(budget_usd=self._daily_budget)
        available = stats["available_usd"]
        return {
            **stats,
            "daily_budget": self._daily_budget,
            "budget_used_pct": (
                100 * (1 - available / self._daily_budget) if available is not None and self._daily_budget > 0 else None
            ),
            "over_budget": available is None or available <= 0 or stats["bound_exceeded"],
        }


_controller: CostController | None = None


def get_cost_controller() -> CostController:
    global _controller
    if _controller is None:
        budget = float(os.environ.get("OMEGA_DAILY_BUDGET", "50.0"))
        _controller = CostController(daily_budget_usd=budget)
    return _controller
