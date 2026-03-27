"""
OpenClaw OMEGA — 成本控制 (Cost Control)
追踪每次 LLM 调用的成本，实施日预算限制，支持成本感知的模型路由。
"""
import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Dict, Optional

from src.utils import now_et

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
COST_DIR = _BASE_DIR / "data" / "cost"
COST_DIR.mkdir(parents=True, exist_ok=True)
DAILY_LOG = COST_DIR / "daily_costs.jsonl"

# 模型定价（每百万 token，美元）
MODEL_COSTS: Dict[str, Dict[str, float]] = {
    # 高端
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    # 中端
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    # 经济
    "claude-haiku-3.5": {"input": 0.8, "output": 4.0},
    # 免费池
    "qwen3-235b": {"input": 0.0, "output": 0.0},
    "deepseek-v3": {"input": 0.0, "output": 0.0},
    "qwen3-30b": {"input": 0.0, "output": 0.0},
    "gemini-2.5-flash": {"input": 0.0, "output": 0.0},
}

COMPLEXITY_TO_MODEL = {
    "simple": "qwen3-235b",            # 免费
    "moderate": "claude-haiku-3.5",     # $0.8/M
    "complex": "claude-sonnet-4",       # $3/M
    "critical": "claude-opus-4",        # $15/M
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
    """
    成本控制器 — 追踪、预算、路由。

    用法:
        cc = get_cost_controller()
        cost = cc.estimate_cost("claude-sonnet-4", 1000, 500)
        if not cc.is_over_budget():
            cc.record_cost("claude-sonnet-4", cost, "investment")
    """

    def __init__(self, daily_budget_usd: float = 50.0):
        self._daily_budget = daily_budget_usd
        self._today_spend: float = 0.0
        self._today_date: str = now_et().strftime("%Y-%m-%d")
        self._records: list = []
        self._by_model: Dict[str, float] = defaultdict(float)
        self._by_task: Dict[str, float] = defaultdict(float)
        self._load_today()
        logger.info(f"CostController 初始化: 日预算 ${daily_budget_usd:.2f}")

    def _load_today(self) -> None:
        """加载今日已有记录"""
        today = now_et().strftime("%Y-%m-%d")
        if not DAILY_LOG.exists():
            return
        try:
            with open(DAILY_LOG, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("date") == today:
                        cost = record.get("cost_usd", 0)
                        self._today_spend += cost
                        self._by_model[record.get("model", "unknown")] += cost
                        self._by_task[record.get("task_type", "unknown")] += cost
        except Exception as e:
            logger.warning(f"加载成本记录失败: {e}")

    def _check_date_rollover(self) -> None:
        """日期切换时重置"""
        today = now_et().strftime("%Y-%m-%d")
        if today != self._today_date:
            self._today_date = today
            self._today_spend = 0.0
            self._by_model.clear()
            self._by_task.clear()
            self._records.clear()

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """预估调用成本（美元）"""
        # 查找模型定价
        pricing = None
        for model_key, prices in MODEL_COSTS.items():
            if model_key in model.lower():
                pricing = prices
                break
        if pricing is None:
            return 0.0  # 未知模型假设免费

        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
        return cost

    def record_cost(self, model: str, cost: float, task_type: str = "unknown") -> None:
        """记录实际成本"""
        self._check_date_rollover()
        self._today_spend += cost
        self._by_model[model] += cost
        self._by_task[task_type] += cost

        record = {
            "timestamp": time.time(),
            "model": model,
            "cost_usd": round(cost, 6),
            "task_type": task_type,
            "date": self._today_date,
        }
        self._records.append(record)

        # 持久化
        try:
            with open(DAILY_LOG, "a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("[CostControl] 成本记录持久化失败: %s", e)

        # 预算告警
        if self._daily_budget > 0 and self._today_spend > self._daily_budget * 0.8:
            logger.warning(
                f"[成本告警] 今日花费 ${self._today_spend:.4f} "
                f"已达预算 {self._today_spend/self._daily_budget:.0%}"
            )
            # EventBus: 通知成本预警
            try:
                from src.core.event_bus import get_event_bus
                bus = get_event_bus()
                if bus:
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                        _t = loop.create_task(bus.publish("system.cost_warning", {
                            "daily_spend": self._today_spend,
                            "daily_budget": self._daily_budget,
                            "usage_pct": self._today_spend / self._daily_budget,
                        }))
                        _t.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
                    except RuntimeError as e:  # noqa: F841
                        pass
            except Exception as e:
                pass
                logger.debug("静默异常: %s", e)

    def get_daily_spend(self) -> float:
        self._check_date_rollover()
        return self._today_spend

    def is_over_budget(self) -> bool:
        self._check_date_rollover()
        return self._today_spend >= self._daily_budget

    def suggest_model(self, task_complexity: str = "moderate") -> str:
        """成本感知的模型推荐"""
        self._check_date_rollover()
        recommended = COMPLEXITY_TO_MODEL.get(task_complexity, "qwen3-235b")
        # 如果接近预算，降级到更便宜的模型
        budget_ratio = self._today_spend / self._daily_budget if self._daily_budget > 0 else 0
        if budget_ratio > 0.9:
            return "qwen3-235b"  # 强制免费
        elif budget_ratio > 0.7:
            if task_complexity == "critical":
                return "claude-sonnet-4"  # 降一级
            return "qwen3-235b"
        return recommended

    def get_weekly_report(self) -> Dict:
        """周报"""
        week_start = (now_et() - timedelta(days=7)).strftime("%Y-%m-%d")
        weekly_cost = 0.0
        daily_breakdown: Dict[str, float] = defaultdict(float)

        if DAILY_LOG.exists():
            try:
                with open(DAILY_LOG, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        date = record.get("date", "")
                        if date >= week_start:
                            cost = record.get("cost_usd", 0)
                            weekly_cost += cost
                            daily_breakdown[date] += cost
            except Exception as e:
                logger.warning("[CostControl] 周报文件读取失败: %s", e)

        return {
            "weekly_total_usd": round(weekly_cost, 4),
            "daily_budget_usd": self._daily_budget,
            "today_spend_usd": round(self._today_spend, 4),
            "by_model": dict(self._by_model),
            "by_task": dict(self._by_task),
            "daily_breakdown": dict(daily_breakdown),
        }

    def get_stats(self) -> Dict:
        self._check_date_rollover()
        return {
            "today_spend": round(self._today_spend, 4),
            "daily_budget": self._daily_budget,
            "budget_used_pct": round(self._today_spend / self._daily_budget * 100, 1)
                               if self._daily_budget > 0 else 0,
            "over_budget": self.is_over_budget(),
            "by_model": {k: round(v, 4) for k, v in self._by_model.items()},
            "by_task": {k: round(v, 4) for k, v in self._by_task.items()},
        }


_controller: Optional[CostController] = None


def get_cost_controller() -> CostController:
    global _controller
    if _controller is None:
        budget = float(os.environ.get("OMEGA_DAILY_BUDGET", "50.0"))
        _controller = CostController(daily_budget_usd=budget)
    return _controller
