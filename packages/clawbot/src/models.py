"""
ClawBot 共享数据模型
避免模块间循环依赖，所有跨模块共享的 dataclass / enum 放在这里。
"""
from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class TradeProposal:
    """交易提案 - AI分析后的结构化输出"""
    symbol: str
    action: str
    quantity: int = 0
    entry_price: float = 0
    stop_loss: float = 0
    take_profit: float = 0
    signal_score: int = 0
    confidence: float = 0
    reason: str = ""
    decided_by: str = ""
    trailing_stop_pct: float = 0.03
    max_hold_hours: float = 120
    atr: float = 0  # ATR值，传递给持仓监控用于动态尾部止损
    votes: List[Any] = field(default_factory=list)  # AI团队投票明细（BotVote列表），供记录个体预测准确率
