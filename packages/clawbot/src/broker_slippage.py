"""
IBKR 滑点估算 Mixin（基于 yfinance，不依赖 ib_insync）

从 broker_bridge.py 提取，包含：
- SlippageEstimate 数据类：滑点估算结果
- BrokerSlippageMixin：滑点估算与格式化方法
"""
import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SlippageEstimate:
    """滑点估算结果"""
    estimated_slippage_pct: float = 0.0  # 预估滑点百分比
    estimated_fill_price: float = 0.0     # 预估成交价
    liquidity_score: str = "unknown"      # "high", "medium", "low", "unknown"
    avg_volume: float = 0.0               # 平均日成交量
    avg_spread_pct: float = 0.0           # 平均买卖价差百分比
    warnings: list = field(default_factory=list)


class BrokerSlippageMixin:
    """滑点估算与格式化功能 Mixin — 通过 yfinance 获取历史数据"""

    async def estimate_slippage(self, symbol: str, quantity: float, side: str = "BUY") -> SlippageEstimate:
        """
        估算交易滑点和流动性
        基于历史成交量和价格波动估算
        """
        estimate = SlippageEstimate()
        try:
            # 通过 yfinance 获取成交量数据
            import yfinance as yf

            loop = asyncio.get_running_loop()
            ticker = await loop.run_in_executor(None, lambda: yf.Ticker(symbol))
            hist = await loop.run_in_executor(None, lambda: ticker.history(period="5d"))

            if hist is not None and not hist.empty:
                avg_vol = hist['Volume'].mean()
                estimate.avg_volume = avg_vol

                # 根据成交量评估流动性
                if avg_vol > 10_000_000:
                    estimate.liquidity_score = "high"
                elif avg_vol > 1_000_000:
                    estimate.liquidity_score = "medium"
                elif avg_vol > 100_000:
                    estimate.liquidity_score = "low"
                else:
                    estimate.liquidity_score = "very_low"
                    estimate.warnings.append(f"极低流动性: 日均成交量仅 {avg_vol:,.0f}")

                # 根据日内波幅估算价差
                avg_range_pct = ((hist['High'] - hist['Low']) / hist['Close']).mean() * 100
                estimate.avg_spread_pct = avg_range_pct * 0.1  # 粗略价差估算

                # 根据订单量占日均成交量比例估算滑点
                volume_pct = (quantity * hist['Close'].iloc[-1]) / (avg_vol * hist['Close'].iloc[-1]) * 100

                if volume_pct < 0.01:  # < 0.01% of daily volume
                    estimate.estimated_slippage_pct = 0.01
                elif volume_pct < 0.1:
                    estimate.estimated_slippage_pct = 0.05
                elif volume_pct < 1.0:
                    estimate.estimated_slippage_pct = 0.15
                else:
                    estimate.estimated_slippage_pct = 0.5
                    estimate.warnings.append(f"大单警告: 订单占日均成交量 {volume_pct:.2f}%")

                # 预估成交价
                last_price = hist['Close'].iloc[-1]
                if side == "BUY":
                    estimate.estimated_fill_price = round(last_price * (1 + estimate.estimated_slippage_pct / 100), 2)
                else:
                    estimate.estimated_fill_price = round(last_price * (1 - estimate.estimated_slippage_pct / 100), 2)

        except ImportError:
            estimate.warnings.append("yfinance 未安装，无法估算滑点")
        except Exception as e:
            logger.warning("[IBKR] 滑点估算失败(%s): %s", symbol, e)
            estimate.warnings.append(f"估算失败: {e}")

        return estimate

    def format_slippage(self, est: SlippageEstimate) -> str:
        """格式化滑点估算结果"""
        liquidity_cn = {
            "high": "高 (日均>1000万股)",
            "medium": "中 (日均>100万股)",
            "low": "低 (日均>10万股)",
            "very_low": "极低 (日均<10万股)",
            "unknown": "未知",
        }
        lines = [
            "滑点估算",
            f"  流动性: {liquidity_cn.get(est.liquidity_score, est.liquidity_score)}",
            f"  日均成交量: {est.avg_volume:,.0f}",
            f"  预估滑点: {est.estimated_slippage_pct:.2f}%",
        ]
        if est.estimated_fill_price > 0:
            lines.append(f"  预估成交价: ${est.estimated_fill_price:.2f}")
        for w in est.warnings:
            lines.append(f"  [!] {w}")
        return "\n".join(lines)
