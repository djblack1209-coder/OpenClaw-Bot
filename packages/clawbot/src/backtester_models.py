"""
ClawBot 回测引擎 — 数据模型与数据加载

从 backtester.py 拆分出来的数据结构和数据加载功能：
- Bar: 单根K线数据
- BacktestTrade: 回测交易记录
- BacktestConfig: 回测配置参数
- PerformanceReport: 绩效报告
- load_historical_data: 从 yfinance 加载历史数据
- bars_to_dataframe: K线转 pandas DataFrame
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# ============ 数据结构 ============

@dataclass
class Bar:
    """单根K线"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class BacktestTrade:
    """回测交易记录"""
    trade_id: int
    symbol: str
    side: str
    quantity: int
    entry_price: float
    entry_time: datetime
    stop_loss: float = 0
    take_profit: float = 0
    trailing_stop_pct: float = 0.03
    trailing_stop_price: float = 0
    highest_price: float = 0
    exit_price: float = 0
    exit_time: datetime | None = None
    exit_reason: str = ""
    pnl: float = 0
    pnl_pct: float = 0
    signal_score: int = 0
    bars_held: int = 0


@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 10000.0
    # 信号过滤
    min_score: int = 30
    allowed_trends: list[str] = field(default_factory=lambda: [
        "strong_up", "up", "sideways"
    ])
    max_rsi6: float = 75.0
    # 止损止盈
    atr_sl_mult: float = 1.5       # ATR倍数止损
    atr_tp_mult: float = 3.0       # ATR倍数止盈
    trailing_stop_pct: float = 0.03  # 追踪止损百分比
    # 交易限制
    max_trades_per_day: int = 3
    max_concurrent: int = 5
    # 手续费
    commission_per_trade: float = 1.0  # 每笔固定手续费


@dataclass
class PerformanceReport:
    """绩效报告"""
    # 基本统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0
    # 盈亏
    total_pnl: float = 0
    total_pnl_pct: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    profit_factor: float = 0       # 总盈利/总亏损
    avg_rr_ratio: float = 0        # 平均盈亏比
    # 风险指标
    max_drawdown: float = 0
    max_drawdown_pct: float = 0
    sharpe_ratio: float = 0
    # 时间
    avg_hold_bars: float = 0
    start_date: str = ""
    end_date: str = ""
    trading_days: int = 0
    # 权益曲线
    equity_curve: list[float] = field(default_factory=list)
    daily_returns: list[float] = field(default_factory=list)

    def format(self) -> str:
        """格式化绩效报告"""
        lines = [
            "=" * 50,
            "ClawBot 回测绩效报告",
            "=" * 50,
            "",
            "回测区间: %s ~ %s (%d个交易日)" % (self.start_date, self.end_date, self.trading_days),
            "",
            "-- 交易统计 --",
            "总交易数: %d" % self.total_trades,
            "盈利: %d | 亏损: %d" % (self.winning_trades, self.losing_trades),
            "胜率: %.1f%%" % self.win_rate,
            "",
            "-- 盈亏分析 --",
            "总盈亏: $%+.2f (%+.1f%%)" % (self.total_pnl, self.total_pnl_pct),
            "平均盈利: $%.2f" % self.avg_win,
            "平均亏损: $%.2f" % self.avg_loss,
            "盈亏比: %.2f" % self.avg_rr_ratio,
            "利润因子: %.2f" % self.profit_factor,
            "",
            "-- 风险指标 --",
            "最大回撤: $%.2f (%.1f%%)" % (self.max_drawdown, self.max_drawdown_pct),
            "夏普比率: %.2f" % self.sharpe_ratio,
            "平均持仓: %.1f根K线" % self.avg_hold_bars,
            "=" * 50,
        ]
        return "\n".join(lines)


# ============ 数据加载 ============

def load_historical_data(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> list[Bar]:
    """从 yfinance 加载历史数据，返回 Bar 列表"""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df is None or df.empty:
        logger.error("[Backtest] %s 无历史数据", symbol)
        return []

    bars = []
    for idx, row in df.iterrows():
        bars.append(Bar(
            timestamp=idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx,
            open=float(row['Open']),
            high=float(row['High']),
            low=float(row['Low']),
            close=float(row['Close']),
            volume=float(row['Volume']),
        ))

    logger.info("[Backtest] %s 加载 %d 根K线 (%s ~ %s)",
                symbol, len(bars),
                bars[0].timestamp.strftime('%Y-%m-%d') if bars else "?",
                bars[-1].timestamp.strftime('%Y-%m-%d') if bars else "?")
    return bars


def bars_to_dataframe(bars: list[Bar]):
    """将 Bar 列表转为 pandas DataFrame（供 ta_engine 使用）"""
    import pandas as pd
    data = {
        'Open': [b.open for b in bars],
        'High': [b.high for b in bars],
        'Low': [b.low for b in bars],
        'Close': [b.close for b in bars],
        'Volume': [b.volume for b in bars],
    }
    index = [b.timestamp for b in bars]
    return pd.DataFrame(data, index=index)
