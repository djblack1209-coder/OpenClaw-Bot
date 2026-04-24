"""
Bot 发言质量与频率控制模块

功能:
1. RateLimiter — 每个 Bot 的请求频率限制（滑动窗口）
2. TokenBudget — 每日 Token 预算控制，防止滥用
3. QualityGate — 发言质量门控（最小长度、重复检测）
"""
import logging
import time
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """频率限制配置"""
    # 每个 Bot 每分钟最大请求数
    max_requests_per_minute: int = 10
    # 每个 Bot 每小时最大请求数
    max_requests_per_hour: int = 120
    # 每个 Bot 每天最大请求数
    max_requests_per_day: int = 500
    # 群聊中每个 Bot 的最小发言间隔（秒）
    min_interval_group: float = 5.0
    # 私聊中每个 Bot 的最小发言间隔（秒）
    min_interval_private: float = 1.0


@dataclass
class TokenBudgetConfig:
    """Token 预算配置"""
    # 每个 Bot 每日 Token 上限（输入+输出）
    daily_token_limit: int = 500_000
    # 单次请求最大 Token（输入）
    max_input_tokens: int = 30_000
    # 单次请求最大 Token（输出）
    max_output_tokens: int = 8192
    # 高成本模型（Claude）的额外限制倍率（0.5 = 预算减半）
    claude_budget_ratio: float = 0.5


class RateLimiter:
    """滑动窗口频率限制器"""

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        # {bot_id: [timestamp, ...]}
        self._requests: dict[str, list] = defaultdict(list)
        # {bot_id: last_response_timestamp}
        self._last_response: dict[str, float] = {}
        # 被限流的计数
        self._throttled_count: dict[str, int] = defaultdict(int)

    def check(self, bot_id: str, chat_type: str = "group") -> tuple[bool, str]:
        """
        检查是否允许请求。

        Returns:
            (allowed, reason) — allowed=True 表示放行
        """
        now = time.time()

        # 检查最小间隔
        last = self._last_response.get(bot_id, 0)
        min_interval = (self.config.min_interval_private
                        if chat_type == "private"
                        else self.config.min_interval_group)
        if now - last < min_interval:
            remaining = min_interval - (now - last)
            self._throttled_count[bot_id] += 1
            return False, f"发言间隔过短，请等待 {remaining:.1f}s"

        # 清理过期记录（只保留24h内的）
        cutoff_day = now - 86400
        self._requests[bot_id] = [
            ts for ts in self._requests[bot_id] if ts > cutoff_day
        ]

        timestamps = self._requests[bot_id]

        # 每分钟限制
        cutoff_min = now - 60
        recent_min = sum(1 for ts in timestamps if ts > cutoff_min)
        if recent_min >= self.config.max_requests_per_minute:
            self._throttled_count[bot_id] += 1
            return False, f"每分钟请求上限 ({self.config.max_requests_per_minute}/min)"

        # 每小时限制
        cutoff_hour = now - 3600
        recent_hour = sum(1 for ts in timestamps if ts > cutoff_hour)
        if recent_hour >= self.config.max_requests_per_hour:
            self._throttled_count[bot_id] += 1
            return False, f"每小时请求上限 ({self.config.max_requests_per_hour}/hr)"

        # 每天限制
        if len(timestamps) >= self.config.max_requests_per_day:
            self._throttled_count[bot_id] += 1
            return False, f"每日请求上限 ({self.config.max_requests_per_day}/day)"

        return True, ""

    def record(self, bot_id: str):
        """记录一次成功的请求"""
        now = time.time()
        self._requests[bot_id].append(now)
        self._last_response[bot_id] = now

    def get_status(self, bot_id: str) -> dict:
        """获取某个 Bot 的限流状态"""
        now = time.time()
        timestamps = self._requests.get(bot_id, [])
        cutoff_min = now - 60
        cutoff_hour = now - 3600
        return {
            "requests_last_minute": sum(1 for ts in timestamps if ts > cutoff_min),
            "requests_last_hour": sum(1 for ts in timestamps if ts > cutoff_hour),
            "requests_today": len(timestamps),
            "throttled_count": self._throttled_count.get(bot_id, 0),
            "limits": {
                "per_minute": self.config.max_requests_per_minute,
                "per_hour": self.config.max_requests_per_hour,
                "per_day": self.config.max_requests_per_day,
            },
        }

    def get_all_status(self) -> dict[str, dict]:
        """获取所有 Bot 的限流状态"""
        all_bots = set(self._requests.keys()) | set(self._last_response.keys())
        return {bot_id: self.get_status(bot_id) for bot_id in sorted(all_bots)}


class TokenBudget:
    """每日 Token 预算管理器"""

    def __init__(self, config: TokenBudgetConfig | None = None):
        self.config = config or TokenBudgetConfig()
        # {bot_id: {"date": "YYYY-MM-DD", "input": N, "output": N}}
        self._usage: dict[str, dict] = {}

    def _today(self) -> str:
        import datetime
        return datetime.date.today().isoformat()

    def _get_usage(self, bot_id: str) -> dict:
        today = self._today()
        usage = self._usage.get(bot_id)
        if not usage or usage.get("date") != today:
            usage = {"date": today, "input": 0, "output": 0}
            self._usage[bot_id] = usage
        return usage

    def check(self, bot_id: str, is_claude: bool = False) -> tuple[bool, str]:
        """检查是否还有 Token 预算"""
        usage = self._get_usage(bot_id)
        total = usage["input"] + usage["output"]
        limit = self.config.daily_token_limit
        if is_claude:
            limit = int(limit * self.config.claude_budget_ratio)
        if total >= limit:
            return False, f"今日 Token 预算已用完 ({total:,}/{limit:,})"
        return True, ""

    def record(self, bot_id: str, input_tokens: int, output_tokens: int):
        """记录 Token 使用量"""
        usage = self._get_usage(bot_id)
        usage["input"] += input_tokens
        usage["output"] += output_tokens

    def get_status(self, bot_id: str, is_claude: bool = False) -> dict:
        """获取某个 Bot 的 Token 使用状态"""
        usage = self._get_usage(bot_id)
        total = usage["input"] + usage["output"]
        limit = self.config.daily_token_limit
        if is_claude:
            limit = int(limit * self.config.claude_budget_ratio)
        return {
            "date": usage["date"],
            "input_tokens": usage["input"],
            "output_tokens": usage["output"],
            "total_tokens": total,
            "daily_limit": limit,
            "remaining": max(0, limit - total),
            "usage_pct": f"{total / limit * 100:.1f}%" if limit > 0 else "N/A",
        }

    def get_all_status(self) -> dict[str, dict]:
        """获取所有 Bot 的 Token 使用状态"""
        return {bot_id: self.get_status(bot_id) for bot_id in sorted(self._usage.keys())}


class QualityGate:
    """发言质量门控"""

    def __init__(self, min_response_length: int = 2, max_duplicate_ratio: float = 0.8):
        self.min_response_length = min_response_length
        self.max_duplicate_ratio = max_duplicate_ratio
        # {bot_id: [last_N_responses]}
        self._recent_responses: dict[str, list] = defaultdict(list)
        self._max_history = 20

    def check_response(self, bot_id: str, response: str) -> tuple[bool, str]:
        """
        检查回复质量。

        Returns:
            (ok, reason) — ok=True 表示质量合格
        """
        if not response or len(response.strip()) < self.min_response_length:
            return False, "回复过短或为空"

        # 检查是否与最近回复高度重复
        recent = self._recent_responses.get(bot_id, [])
        response_stripped = response.strip()
        for prev in recent[-5:]:  # 只检查最近5条
            if prev == response_stripped:
                return False, "与最近回复完全重复"
            # 简单的相似度检查：共同字符比例
            if len(prev) > 20 and len(response_stripped) > 20:
                shorter = min(len(prev), len(response_stripped))
                common = sum(1 for a, b in zip(prev, response_stripped) if a == b)
                ratio = common / shorter
                if ratio > self.max_duplicate_ratio:
                    return False, f"与最近回复高度相似 ({ratio:.0%})"

        return True, ""

    def record_response(self, bot_id: str, response: str):
        """记录回复用于后续重复检测"""
        self._recent_responses[bot_id].append(response.strip())
        # 保持历史长度
        if len(self._recent_responses[bot_id]) > self._max_history:
            self._recent_responses[bot_id] = self._recent_responses[bot_id][-self._max_history:]


# ============ 全局单例 ============

rate_limiter = RateLimiter()
token_budget = TokenBudget()
quality_gate = QualityGate()
