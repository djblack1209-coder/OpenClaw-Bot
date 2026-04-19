"""
凯利公式仓位计算 Mixin

从 risk_manager.py 提取的凯利公式相关方法：
- calc_kelly_quantity(): 基于凯利公式计算最优仓位
- _get_trade_stats(): 从交易历史计算胜率和盈亏比
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class KellyMixin:
    """凯利公式仓位计算混入类

    依赖 RiskManager.__init__ 中初始化的属性:
        self.config          — RiskConfig 实例
        self._trade_history  — 交易历史 deque
    依赖 RiskManager 的方法:
        self.calc_safe_quantity() — 基础仓位计算（回退方案）
    """

    def calc_kelly_quantity(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float = 0,
        capital: float = None,
    ) -> Dict:
        """
        基于凯利公式计算最优仓位（对标 freqtrade 的仓位优化）

        Kelly% = W - (1-W)/R
        其中 W=胜率, R=盈亏比

        使用 fractional Kelly（保守系数）避免过度下注
        """
        cap = capital or self.config.total_capital

        # 计算历史胜率和盈亏比
        stats = self._get_trade_stats()
        win_rate = stats["win_rate"]
        avg_win = stats["avg_win"]
        avg_loss = stats["avg_loss"]
        total_trades = stats["total_trades"]

        # 交易次数不足，回退到固定比例
        if total_trades < self.config.kelly_min_trades or not self.config.kelly_enabled:
            return self.calc_safe_quantity(entry_price, stop_loss, cap)

        # 计算盈亏比 R
        if avg_loss == 0:
            avg_loss = abs(entry_price - stop_loss)  # 用当前止损估算
        if avg_loss == 0:
            return self.calc_safe_quantity(entry_price, stop_loss, cap)

        if take_profit > 0 and entry_price > 0:
            # HI-523: 区分 BUY/SELL 方向的预期收益计算
            # 注意: calc_kelly_quantity 不接收 side 参数，通过止损/止盈位置推断方向
            # 如果 stop_loss < entry_price → BUY 方向，反之 → SELL 方向
            if stop_loss < entry_price:
                # BUY 方向: 收益 = 止盈 - 入场
                expected_reward = take_profit - entry_price
            else:
                # SELL 方向: 收益 = 入场 - 止盈
                expected_reward = entry_price - take_profit
        else:
            expected_reward = avg_win if avg_win > 0 else abs(entry_price - stop_loss) * 2

        R = expected_reward / avg_loss if avg_loss > 0 else 2.0

        # 凯利公式
        kelly_pct = win_rate - (1 - win_rate) / R if R > 0 else 0

        # 应用保守系数
        kelly_pct = max(0, kelly_pct * self.config.kelly_fraction)

        # 上限不超过单笔风险限制
        kelly_pct = min(kelly_pct, self.config.max_risk_per_trade_pct * 2)

        # 计算仓位
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return {"error": "止损价不能等于入场价", "shares": 0}

        kelly_amount = cap * kelly_pct
        shares = int(kelly_amount / risk_per_share)

        # 仍然受仓位上限约束
        max_position = cap * self.config.max_position_pct
        shares_by_position = int(max_position / entry_price)
        shares = min(shares, shares_by_position)

        if shares <= 0:
            # 凯利建议不交易（负期望值）
            return {
                "shares": 0,
                "kelly_pct": round(kelly_pct * 100, 2),
                "win_rate": round(win_rate * 100, 1),
                "avg_rr": round(R, 2),
                "recommendation": "凯利公式建议不交易（期望值为负或过低）",
            }

        total_cost = shares * entry_price
        max_loss = shares * risk_per_share

        return {
            "shares": shares,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "total_cost": round(total_cost, 2),
            "max_loss": round(max_loss, 2),
            "risk_pct": round(max_loss / cap * 100, 2),
            "position_pct": round(total_cost / cap * 100, 2),
            "kelly_pct": round(kelly_pct * 100, 2),
            "win_rate": round(win_rate * 100, 1),
            "avg_rr": round(R, 2),
            "total_trades_used": total_trades,
        }

    def _get_trade_stats(self) -> Dict:
        """从交易历史计算胜率和盈亏比"""
        if not self._trade_history:
            return {"win_rate": 0.5, "avg_win": 0, "avg_loss": 0, "total_trades": 0}

        wins = [t["pnl"] for t in self._trade_history if t["pnl"] > 0]
        losses = [t["pnl"] for t in self._trade_history if t["pnl"] <= 0]
        total = len(self._trade_history)

        win_rate = len(wins) / total if total > 0 else 0.5
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0

        return {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "total_trades": total,
        }
