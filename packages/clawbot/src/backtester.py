"""
ClawBot 回测引擎 v2.0
用历史数据验证交易策略的有效性

核心功能：
1. 数据加载：从 yfinance 获取历史 OHLCV 数据
2. 信号生成：复用 ta_engine.compute_indicators + compute_signal_score
3. Bar-by-bar 模拟：逐K线推进，模拟真实交易流程
4. 风控集成：复用 RiskManager 的风控规则
5. 持仓管理：止损/止盈/追踪止损模拟
6. 绩效报告：胜率/盈亏比/夏普比率/最大回撤/权益曲线

v2.0 新增（对标 freqtrade 47.7k⭐）：
7. 蒙特卡洛模拟：随机打乱交易顺序评估策略稳健性
8. 参数优化（网格搜索）：自动寻找最优参数组合
9. Walk-Forward 分析：滚动窗口验证避免过拟合
10. 增强绩效指标：Sortino/Calmar比率、最大连续亏损
"""
import logging
import math
import random
import itertools
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from src.risk_manager import RiskManager, RiskConfig

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
    exit_time: Optional[datetime] = None
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
    allowed_trends: List[str] = field(default_factory=lambda: [
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
    equity_curve: List[float] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)

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
) -> List[Bar]:
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


def bars_to_dataframe(bars: List[Bar]):
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


# ============ 回测引擎 ============

class Backtester:
    """
    Bar-by-bar 回测引擎

    复用 RiskManager 的风控规则，模拟真实交易流程：
    1. 每根K线计算技术指标
    2. 生成信号 -> 过滤 -> 风控审核
    3. 模拟开仓（用 close 价格）
    4. 检查持仓止损/止盈/追踪止损（用 high/low）
    5. 记录交易结果
    """

    def __init__(
        self,
        config: BacktestConfig = None,
        risk_config: RiskConfig = None,
    ):
        self.config = config or BacktestConfig()
        self.risk_config = risk_config or RiskConfig(
            total_capital=self.config.initial_capital,
        )
        self.risk_manager = RiskManager(config=self.risk_config)

        # 状态
        self._capital = self.config.initial_capital
        self._open_trades: List[BacktestTrade] = []
        self._closed_trades: List[BacktestTrade] = []
        self._trade_counter = 0
        self._equity_curve: List[float] = []
        self._peak_equity: float = self.config.initial_capital
        self._max_drawdown: float = 0
        self._max_drawdown_pct: float = 0
        self._trades_today: int = 0
        self._current_date: Optional[str] = None

    def run(self, symbol: str, bars: List[Bar], lookback: int = 50) -> PerformanceReport:
        """
        执行回测

        Args:
            symbol: 标的代码
            bars: 历史K线数据
            lookback: 技术指标计算所需的最小K线数
        """
        if len(bars) < lookback:
            logger.error("[Backtest] K线不足: %d < %d", len(bars), lookback)
            return PerformanceReport()

        logger.info("[Backtest] 开始回测 %s | %d根K线 | 初始资金$%.2f",
                     symbol, len(bars), self.config.initial_capital)

        from src.ta_engine import compute_indicators, compute_signal_score

        for i in range(lookback, len(bars)):
            bar = bars[i]
            window = bars[max(0, i - lookback):i + 1]

            # 日期变更 -> 重置日内计数
            bar_date = bar.timestamp.strftime('%Y-%m-%d')
            if bar_date != self._current_date:
                self._current_date = bar_date
                self._trades_today = 0
                self.risk_manager.reset_daily()

            # Step 1: 检查持仓止损/止盈
            self._check_exits(bar)

            # Step 2: 计算技术指标
            df = bars_to_dataframe(window)
            indicators = compute_indicators(df)
            if "error" in indicators:
                self._record_equity(bar)
                continue

            signal = compute_signal_score(indicators)
            score = signal.get("score", 0)
            trend = indicators.get("trend", "sideways")
            rsi6 = indicators.get("rsi_6", 50)
            atr_pct = indicators.get("atr_pct", 2.0)

            # Step 3: 信号过滤
            if not self._should_enter(score, trend, rsi6):
                self._record_equity(bar)
                continue

            # Step 4: 计算止损止盈
            entry_price = bar.close
            atr_mult = max(atr_pct / 100, 0.02)
            stop_loss = round(entry_price * (1 - atr_mult * self.config.atr_sl_mult), 2)
            take_profit = round(entry_price * (1 + atr_mult * self.config.atr_tp_mult), 2)

            # Step 5: 风控审核
            current_positions = self._get_positions_for_risk()
            sizing = self.risk_manager.calc_safe_quantity(
                entry_price=entry_price,
                stop_loss=stop_loss,
                capital=self._capital,
            )
            if "error" in sizing:
                self._record_equity(bar)
                continue

            quantity = sizing["shares"]
            if quantity <= 0:
                self._record_equity(bar)
                continue

            check = self.risk_manager.check_trade(
                symbol=symbol,
                side="BUY",
                quantity=quantity,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                signal_score=score,
                current_positions=current_positions,
            )

            if not check.approved:
                self._record_equity(bar)
                continue

            if check.adjusted_quantity is not None:
                quantity = int(check.adjusted_quantity)
                if quantity <= 0:
                    self._record_equity(bar)
                    continue

            # Step 6: 开仓
            self._open_trade(
                symbol=symbol,
                quantity=quantity,
                entry_price=entry_price,
                entry_time=bar.timestamp,
                stop_loss=stop_loss,
                take_profit=take_profit,
                signal_score=score,
            )

            self._record_equity(bar)

        # 回测结束：强制平仓所有持仓
        if bars:
            last_bar = bars[-1]
            for trade in list(self._open_trades):
                self._close_trade(trade, last_bar.close, last_bar.timestamp, "backtest_end")

        return self._generate_report(bars)

    # ============ 信号过滤 ============

    def _should_enter(self, score: int, trend: str, rsi6: float) -> bool:
        """判断是否应该入场"""
        if score < self.config.min_score:
            return False
        if trend not in self.config.allowed_trends:
            return False
        if rsi6 > self.config.max_rsi6:
            return False
        if len(self._open_trades) >= self.config.max_concurrent:
            return False
        if self._trades_today >= self.config.max_trades_per_day:
            return False
        return True

    # ============ 持仓管理 ============

    def _open_trade(self, symbol, quantity, entry_price, entry_time,
                    stop_loss, take_profit, signal_score):
        """开仓"""
        self._trade_counter += 1
        trade = BacktestTrade(
            trade_id=self._trade_counter,
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            entry_price=entry_price,
            entry_time=entry_time,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_pct=self.config.trailing_stop_pct,
            trailing_stop_price=round(entry_price * (1 - self.config.trailing_stop_pct), 2),
            highest_price=entry_price,
            signal_score=signal_score,
        )
        cost = quantity * entry_price + self.config.commission_per_trade
        self._capital -= cost
        self._open_trades.append(trade)
        self._trades_today += 1

        logger.debug("[Backtest] 开仓 #%d: %s x%d @ $%.2f SL=$%.2f TP=$%.2f",
                      trade.trade_id, symbol, quantity, entry_price, stop_loss, take_profit)

    def _close_trade(self, trade, exit_price, exit_time, exit_reason):
        """平仓"""
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.exit_reason = exit_reason

        if trade.side == "BUY":
            trade.pnl = (exit_price - trade.entry_price) * trade.quantity
        else:
            trade.pnl = (trade.entry_price - exit_price) * trade.quantity

        trade.pnl -= self.config.commission_per_trade  # 出场手续费
        cost = trade.entry_price * trade.quantity
        trade.pnl_pct = (trade.pnl / cost * 100) if cost > 0 else 0

        # 返还资金
        self._capital += trade.quantity * exit_price - self.config.commission_per_trade

        # 更新风控
        self.risk_manager.record_trade_result(trade.pnl)

        if trade in self._open_trades:
            self._open_trades.remove(trade)
        self._closed_trades.append(trade)

        logger.debug("[Backtest] 平仓 #%d: %s @ $%.2f PnL=$%.2f (%s)",
                      trade.trade_id, trade.symbol, exit_price, trade.pnl, exit_reason)

    def _check_exits(self, bar):
        """检查所有持仓的止损/止盈/追踪止损"""
        for trade in list(self._open_trades):
            trade.bars_held += 1

            # 更新最高价和追踪止损
            if bar.high > trade.highest_price:
                trade.highest_price = bar.high
                if trade.trailing_stop_pct > 0:
                    new_ts = round(bar.high * (1 - trade.trailing_stop_pct), 2)
                    if new_ts > trade.trailing_stop_price:
                        trade.trailing_stop_price = new_ts

            # 止损检查（用 bar.low 模拟最差价格）
            if trade.stop_loss > 0 and bar.low <= trade.stop_loss:
                self._close_trade(trade, trade.stop_loss, bar.timestamp, "stop_loss")
                continue

            # 追踪止损检查
            if trade.trailing_stop_price > 0 and bar.low <= trade.trailing_stop_price:
                self._close_trade(trade, trade.trailing_stop_price, bar.timestamp, "trailing_stop")
                continue

            # 止盈检查（用 bar.high 模拟最好价格）
            if trade.take_profit > 0 and bar.high >= trade.take_profit:
                self._close_trade(trade, trade.take_profit, bar.timestamp, "take_profit")
                continue

    def _record_equity(self, bar):
        """记录当前权益"""
        unrealized = sum(
            (bar.close - t.entry_price) * t.quantity
            for t in self._open_trades
        )
        equity = self._capital + sum(
            t.quantity * t.entry_price for t in self._open_trades
        ) + unrealized
        self._equity_curve.append(equity)

        # 更新最大回撤
        if equity > self._peak_equity:
            self._peak_equity = equity
        drawdown = self._peak_equity - equity
        if drawdown > self._max_drawdown:
            self._max_drawdown = drawdown
            self._max_drawdown_pct = (drawdown / self._peak_equity * 100) if self._peak_equity > 0 else 0

    def _get_positions_for_risk(self):
        """将持仓转为风控检查格式"""
        return [
            {
                "symbol": t.symbol,
                "quantity": t.quantity,
                "avg_price": t.entry_price,
                "status": "open",
            }
            for t in self._open_trades
        ]

    # ============ 绩效报告 ============

    def _generate_report(self, bars):
        """生成绩效报告"""
        trades = self._closed_trades
        report = PerformanceReport()

        if not trades:
            report.equity_curve = self._equity_curve
            return report

        report.total_trades = len(trades)
        report.winning_trades = len([t for t in trades if t.pnl > 0])
        report.losing_trades = len([t for t in trades if t.pnl <= 0])
        report.win_rate = (report.winning_trades / report.total_trades * 100) if report.total_trades > 0 else 0

        report.total_pnl = sum(t.pnl for t in trades)
        report.total_pnl_pct = (report.total_pnl / self.config.initial_capital * 100)

        wins = [t.pnl for t in trades if t.pnl > 0]
        losses = [t.pnl for t in trades if t.pnl <= 0]
        report.avg_win = (sum(wins) / len(wins)) if wins else 0
        report.avg_loss = (sum(losses) / len(losses)) if losses else 0

        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 0
        report.profit_factor = (total_wins / total_losses) if total_losses > 0 else float('inf')

        report.avg_rr_ratio = (report.avg_win / abs(report.avg_loss)) if report.avg_loss != 0 else 0

        report.max_drawdown = self._max_drawdown
        report.max_drawdown_pct = self._max_drawdown_pct

        report.avg_hold_bars = sum(t.bars_held for t in trades) / len(trades)

        # 夏普比率（简化：用每笔交易收益率）
        if len(trades) >= 2:
            returns = [t.pnl_pct for t in trades]
            avg_ret = sum(returns) / len(returns)
            std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in returns) / (len(returns) - 1))
            report.sharpe_ratio = (avg_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0
        else:
            report.sharpe_ratio = 0

        # 日收益率序列
        if len(self._equity_curve) >= 2:
            daily_returns = []
            for i in range(1, len(self._equity_curve)):
                prev = self._equity_curve[i - 1]
                if prev > 0:
                    daily_returns.append((self._equity_curve[i] - prev) / prev * 100)
            report.daily_returns = daily_returns

        report.equity_curve = self._equity_curve

        if bars:
            report.start_date = bars[0].timestamp.strftime('%Y-%m-%d')
            report.end_date = bars[-1].timestamp.strftime('%Y-%m-%d')
            dates = set(b.timestamp.strftime('%Y-%m-%d') for b in bars)
            report.trading_days = len(dates)

        return report


# ============ 便捷函数 ============

def run_backtest(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
    initial_capital: float = 10000.0,
    config: BacktestConfig = None,
    risk_config: RiskConfig = None,
) -> PerformanceReport:
    """
    一键回测

    用法:
        from src.backtester import run_backtest
        report = run_backtest("AAPL", period="1y")
        print(report.format())
    """
    if config is None:
        config = BacktestConfig(initial_capital=initial_capital)
    if risk_config is None:
        risk_config = RiskConfig(total_capital=initial_capital)

    bars = load_historical_data(symbol, period=period, interval=interval)
    if not bars:
        return PerformanceReport()

    bt = Backtester(config=config, risk_config=risk_config)
    return bt.run(symbol, bars)


def run_multi_backtest(
    symbols: List[str],
    period: str = "1y",
    interval: str = "1d",
    initial_capital: float = 10000.0,
) -> Dict[str, PerformanceReport]:
    """
    多标的回测

    用法:
        reports = run_multi_backtest(["AAPL", "MSFT", "NVDA"])
        for sym, r in reports.items():
            print("%s: PnL=$%+.2f WR=%.0f%%" % (sym, r.total_pnl, r.win_rate))
    """
    results = {}
    for sym in symbols:
        logger.info("[Backtest] === %s ===", sym)
        results[sym] = run_backtest(sym, period=period, interval=interval,
                                     initial_capital=initial_capital)
    return results


def format_multi_report(reports: Dict[str, PerformanceReport]) -> str:
    """格式化多标的回测汇总"""
    lines = [
        "=" * 60,
        "ClawBot 多标的回测汇总",
        "=" * 60,
        "",
        "%-8s %6s %6s %10s %8s %6s" % ("标的", "交易数", "胜率", "总PnL", "回撤", "夏普"),
        "-" * 60,
    ]

    total_pnl = 0
    total_trades = 0
    for sym, r in sorted(reports.items()):
        total_pnl += r.total_pnl
        total_trades += r.total_trades
        lines.append(
            "%-8s %6d %5.1f%% $%+9.2f %6.1f%% %6.2f"
            % (sym, r.total_trades, r.win_rate, r.total_pnl, r.max_drawdown_pct, r.sharpe_ratio)
        )

    lines.append("-" * 60)
    lines.append("%-8s %6d %6s $%+9.2f" % ("合计", total_trades, "", total_pnl))
    lines.append("=" * 60)
    return "\n".join(lines)


# ============ v2.0 蒙特卡洛模拟 ============

def run_monte_carlo(
    base_report: PerformanceReport,
    initial_capital: float = 10000.0,
    simulations: int = 1000,
    confidence_levels: List[float] = None,
) -> Dict[str, Any]:
    """
    蒙特卡洛模拟（对标 freqtrade 的策略稳健性验证）
    
    原理：将已完成的交易PnL随机打乱顺序，模拟N次，
    观察不同运气下的权益曲线分布，评估策略稳健性。
    
    Args:
        base_report: 原始回测报告
        initial_capital: 初始资金
        simulations: 模拟次数
        confidence_levels: 置信区间 [5%, 25%, 50%, 75%, 95%]
    
    Returns:
        {
            "median_pnl": 中位数PnL,
            "worst_case_pnl": 最差5%情况PnL,
            "best_case_pnl": 最好5%情况PnL,
            "ruin_probability": 破产概率（资金归零）,
            "max_drawdown_distribution": 最大回撤分布,
            "final_equity_distribution": 最终权益分布,
        }
    """
    if confidence_levels is None:
        confidence_levels = [0.05, 0.25, 0.50, 0.75, 0.95]
    
    if not base_report.daily_returns and base_report.total_trades == 0:
        return {"error": "无交易数据，无法进行蒙特卡洛模拟"}
    
    # 从权益曲线提取每步收益率
    equity = base_report.equity_curve
    if len(equity) < 2:
        return {"error": "权益曲线数据不足"}
    
    step_returns = []
    for i in range(1, len(equity)):
        if equity[i - 1] > 0:
            step_returns.append((equity[i] - equity[i - 1]) / equity[i - 1])
    
    if not step_returns:
        return {"error": "无有效收益率数据"}
    
    final_equities = []
    max_drawdowns = []
    ruin_count = 0
    
    for _ in range(simulations):
        shuffled = step_returns.copy()
        random.shuffle(shuffled)
        
        eq = initial_capital
        peak = eq
        max_dd = 0
        ruined = False
        
        for ret in shuffled:
            eq *= (1 + ret)
            if eq <= 0:
                ruined = True
                eq = 0
                break
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        
        final_equities.append(eq)
        max_drawdowns.append(max_dd * 100)
        if ruined:
            ruin_count += 1
    
    final_equities.sort()
    max_drawdowns.sort()
    
    def percentile(data, pct):
        idx = int(len(data) * pct)
        idx = max(0, min(idx, len(data) - 1))
        return data[idx]
    
    result = {
        "simulations": simulations,
        "original_pnl": base_report.total_pnl,
        "median_pnl": round(percentile(final_equities, 0.5) - initial_capital, 2),
        "worst_5pct_pnl": round(percentile(final_equities, 0.05) - initial_capital, 2),
        "best_5pct_pnl": round(percentile(final_equities, 0.95) - initial_capital, 2),
        "ruin_probability": round(ruin_count / simulations * 100, 2),
        "median_max_drawdown": round(percentile(max_drawdowns, 0.5), 1),
        "worst_5pct_max_drawdown": round(percentile(max_drawdowns, 0.95), 1),
        "confidence_intervals": {},
    }
    
    for level in confidence_levels:
        eq_val = percentile(final_equities, level)
        dd_val = percentile(max_drawdowns, level)
        result["confidence_intervals"][f"{int(level*100)}%"] = {
            "final_equity": round(eq_val, 2),
            "pnl": round(eq_val - initial_capital, 2),
            "max_drawdown_pct": round(dd_val, 1),
        }
    
    return result


def format_monte_carlo(mc_result: Dict) -> str:
    """格式化蒙特卡洛模拟结果"""
    if "error" in mc_result:
        return f"蒙特卡洛模拟失败: {mc_result['error']}"
    
    lines = [
        "=" * 50,
        "蒙特卡洛模拟结果 (%d次模拟)" % mc_result["simulations"],
        "=" * 50,
        "",
        "原始回测PnL: $%+.2f" % mc_result["original_pnl"],
        "模拟中位数PnL: $%+.2f" % mc_result["median_pnl"],
        "最差5%%情况: $%+.2f" % mc_result["worst_5pct_pnl"],
        "最好5%%情况: $%+.2f" % mc_result["best_5pct_pnl"],
        "",
        "破产概率: %.2f%%" % mc_result["ruin_probability"],
        "中位数最大回撤: %.1f%%" % mc_result["median_max_drawdown"],
        "最差5%%最大回撤: %.1f%%" % mc_result["worst_5pct_max_drawdown"],
        "",
        "-- 置信区间 --",
    ]
    
    for level, data in mc_result.get("confidence_intervals", {}).items():
        lines.append(
            "  %s: 权益$%.2f  PnL$%+.2f  回撤%.1f%%"
            % (level, data["final_equity"], data["pnl"], data["max_drawdown_pct"])
        )
    
    lines.append("=" * 50)
    return "\n".join(lines)


# ============ v2.0 参数优化（网格搜索） ============

def run_parameter_optimization(
    symbol: str,
    param_grid: Dict[str, List],
    period: str = "1y",
    interval: str = "1d",
    initial_capital: float = 10000.0,
    optimize_metric: str = "sharpe_ratio",
    max_combinations: int = 200,
) -> Dict[str, Any]:
    """
    网格搜索参数优化（对标 freqtrade hyperopt）
    
    Args:
        symbol: 标的代码
        param_grid: 参数网格，例如:
            {
                "min_score": [20, 30, 40],
                "atr_sl_mult": [1.0, 1.5, 2.0],
                "atr_tp_mult": [2.0, 3.0, 4.0],
                "trailing_stop_pct": [0.02, 0.03, 0.05],
            }
        optimize_metric: 优化目标 ("sharpe_ratio", "total_pnl", "profit_factor", "win_rate")
        max_combinations: 最大组合数（防止爆炸）
    
    Returns:
        {
            "best_params": 最优参数,
            "best_metric": 最优指标值,
            "all_results": 所有结果排序列表,
            "total_combinations": 总组合数,
        }
    """
    bars = load_historical_data(symbol, period=period, interval=interval)
    if not bars:
        return {"error": f"{symbol} 无历史数据"}
    
    # 生成参数组合
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))
    
    if len(combinations) > max_combinations:
        logger.warning(
            "[Backtest] 参数组合%d超过上限%d，随机采样",
            len(combinations), max_combinations
        )
        combinations = random.sample(combinations, max_combinations)
    
    logger.info("[Backtest] 参数优化: %s | %d种组合", symbol, len(combinations))
    
    results = []
    for combo in combinations:
        params = dict(zip(keys, combo))
        
        # 构建配置
        config = BacktestConfig(initial_capital=initial_capital)
        for k, v in params.items():
            if hasattr(config, k):
                setattr(config, k, v)
        
        risk_config = RiskConfig(total_capital=initial_capital)
        
        # 运行回测
        bt = Backtester(config=config, risk_config=risk_config)
        report = bt.run(symbol, bars)
        
        metric_value = getattr(report, optimize_metric, 0)
        
        results.append({
            "params": params,
            "metric": metric_value,
            "total_pnl": report.total_pnl,
            "win_rate": report.win_rate,
            "sharpe_ratio": report.sharpe_ratio,
            "profit_factor": report.profit_factor,
            "max_drawdown_pct": report.max_drawdown_pct,
            "total_trades": report.total_trades,
        })
    
    # 按优化指标排序
    results.sort(key=lambda x: x["metric"], reverse=True)
    
    best = results[0] if results else {}
    
    return {
        "best_params": best.get("params", {}),
        "best_metric": best.get("metric", 0),
        "optimize_metric": optimize_metric,
        "all_results": results[:20],  # 只返回前20
        "total_combinations": len(combinations),
        "symbol": symbol,
    }


def format_optimization_result(opt_result: Dict) -> str:
    """格式化参数优化结果"""
    if "error" in opt_result:
        return f"参数优化失败: {opt_result['error']}"
    
    lines = [
        "=" * 60,
        "参数优化结果 (%s | %d种组合)" % (
            opt_result.get("symbol", "?"),
            opt_result.get("total_combinations", 0)
        ),
        "=" * 60,
        "",
        "优化目标: %s" % opt_result.get("optimize_metric", "?"),
        "",
        "-- 最优参数 --",
    ]
    
    for k, v in opt_result.get("best_params", {}).items():
        lines.append("  %s = %s" % (k, v))
    
    lines.append("")
    lines.append("-- Top 10 结果 --")
    lines.append("%-4s %8s %6s %6s %10s %6s" % (
        "#", "指标", "胜率", "夏普", "PnL", "回撤"
    ))
    lines.append("-" * 50)
    
    for i, r in enumerate(opt_result.get("all_results", [])[:10]):
        lines.append("%-4d %8.2f %5.1f%% %6.2f $%+9.2f %5.1f%%" % (
            i + 1, r["metric"], r["win_rate"], r["sharpe_ratio"],
            r["total_pnl"], r["max_drawdown_pct"]
        ))
    
    lines.append("=" * 60)
    return "\n".join(lines)


# ============ v2.0 Walk-Forward 分析 ============

def run_walk_forward(
    symbol: str,
    period: str = "2y",
    interval: str = "1d",
    initial_capital: float = 10000.0,
    train_ratio: float = 0.7,
    n_splits: int = 3,
    param_grid: Dict[str, List] = None,
    optimize_metric: str = "sharpe_ratio",
) -> Dict[str, Any]:
    """
    Walk-Forward 分析（对标 freqtrade 的过拟合检测）
    
    原理：将数据分为多个训练/测试窗口，在训练集上优化参数，
    在测试集上验证，检测策略是否过拟合。
    
    Args:
        train_ratio: 训练集占比
        n_splits: 分割数
        param_grid: 参数网格（None则用默认）
    """
    bars = load_historical_data(symbol, period=period, interval=interval)
    if not bars or len(bars) < 100:
        return {"error": "数据不足，需要至少100根K线"}
    
    if param_grid is None:
        param_grid = {
            "min_score": [20, 30, 40],
            "atr_sl_mult": [1.0, 1.5, 2.0],
            "atr_tp_mult": [2.0, 3.0, 4.0],
        }
    
    total_bars = len(bars)
    split_size = total_bars // n_splits
    
    walk_results = []
    
    for i in range(n_splits):
        start = i * split_size
        end = min(start + split_size, total_bars)
        split_bars = bars[start:end]
        
        if len(split_bars) < 60:
            continue
        
        train_end = int(len(split_bars) * train_ratio)
        train_bars = split_bars[:train_end]
        test_bars = split_bars[train_end:]
        
        if len(train_bars) < 50 or len(test_bars) < 10:
            continue
        
        # 训练阶段：在训练集上找最优参数
        best_params = {}
        best_metric = -float('inf')
        
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        for combo in itertools.product(*values):
            params = dict(zip(keys, combo))
            config = BacktestConfig(initial_capital=initial_capital)
            for k, v in params.items():
                if hasattr(config, k):
                    setattr(config, k, v)
            
            bt = Backtester(config=config, risk_config=RiskConfig(total_capital=initial_capital))
            report = bt.run(symbol, train_bars)
            metric_val = getattr(report, optimize_metric, 0)
            
            if metric_val > best_metric:
                best_metric = metric_val
                best_params = params
        
        # 测试阶段：用最优参数在测试集上验证
        config = BacktestConfig(initial_capital=initial_capital)
        for k, v in best_params.items():
            if hasattr(config, k):
                setattr(config, k, v)
        
        bt = Backtester(config=config, risk_config=RiskConfig(total_capital=initial_capital))
        test_report = bt.run(symbol, test_bars)
        
        walk_results.append({
            "split": i + 1,
            "train_bars": len(train_bars),
            "test_bars": len(test_bars),
            "best_params": best_params,
            "train_metric": round(best_metric, 4),
            "test_pnl": round(test_report.total_pnl, 2),
            "test_win_rate": round(test_report.win_rate, 1),
            "test_sharpe": round(test_report.sharpe_ratio, 2),
            "test_max_dd": round(test_report.max_drawdown_pct, 1),
            "test_trades": test_report.total_trades,
        })
    
    # 计算 Walk-Forward 效率
    profitable_splits = sum(1 for r in walk_results if r["test_pnl"] > 0)
    wf_efficiency = (profitable_splits / len(walk_results) * 100) if walk_results else 0
    
    return {
        "symbol": symbol,
        "n_splits": n_splits,
        "walk_results": walk_results,
        "wf_efficiency": round(wf_efficiency, 1),
        "is_robust": wf_efficiency >= 60,  # 60%以上视为稳健
        "total_test_pnl": round(sum(r["test_pnl"] for r in walk_results), 2),
    }


def format_walk_forward(wf_result: Dict) -> str:
    """格式化 Walk-Forward 分析结果"""
    if "error" in wf_result:
        return f"Walk-Forward 分析失败: {wf_result['error']}"
    
    lines = [
        "=" * 60,
        "Walk-Forward 分析 (%s | %d折)" % (
            wf_result.get("symbol", "?"),
            wf_result.get("n_splits", 0)
        ),
        "=" * 60,
        "",
    ]
    
    for r in wf_result.get("walk_results", []):
        lines.append(
            "第%d折: 训练%d根 测试%d根 | "
            "测试PnL=$%+.2f 胜率%.1f%% 夏普%.2f 回撤%.1f%%"
            % (r["split"], r["train_bars"], r["test_bars"],
               r["test_pnl"], r["test_win_rate"], r["test_sharpe"], r["test_max_dd"])
        )
    
    lines.append("")
    efficiency = wf_result.get("wf_efficiency", 0)
    robust = wf_result.get("is_robust", False)
    lines.append("Walk-Forward 效率: %.1f%% %s" % (
        efficiency, "(稳健)" if robust else "(可能过拟合)"
    ))
    lines.append("测试集总PnL: $%+.2f" % wf_result.get("total_test_pnl", 0))
    lines.append("=" * 60)
    return "\n".join(lines)


# ============ v2.0 增强绩效指标 ============

def calc_enhanced_metrics(report: PerformanceReport, risk_free_rate: float = 0.05) -> Dict:
    """
    计算增强绩效指标（对标 freqtrade 的完整指标体系）
    
    新增: Sortino比率、Calmar比率、最大连续亏损、期望值、恢复因子
    """
    trades_pnl = []
    if report.equity_curve and len(report.equity_curve) >= 2:
        for i in range(1, len(report.equity_curve)):
            prev = report.equity_curve[i - 1]
            if prev > 0:
                trades_pnl.append((report.equity_curve[i] - prev) / prev)
    
    if not trades_pnl:
        return {"error": "无足够数据计算增强指标"}
    
    avg_return = sum(trades_pnl) / len(trades_pnl)
    
    # Sortino 比率（只惩罚下行波动）
    downside_returns = [r for r in trades_pnl if r < 0]
    if downside_returns and len(downside_returns) > 1:
        downside_std = math.sqrt(
            sum(r ** 2 for r in downside_returns) / len(downside_returns)
        )
        daily_rf = risk_free_rate / 252
        sortino = (avg_return - daily_rf) / downside_std * math.sqrt(252) if downside_std > 0 else 0
    else:
        sortino = 0
    
    # Calmar 比率（年化收益 / 最大回撤）
    annual_return = avg_return * 252
    calmar = (annual_return / (report.max_drawdown_pct / 100)) if report.max_drawdown_pct > 0 else 0
    
    # 最大连续亏损/盈利
    max_consec_loss = 0
    max_consec_win = 0
    current_loss = 0
    current_win = 0
    for r in trades_pnl:
        if r <= 0:
            current_loss += 1
            current_win = 0
            max_consec_loss = max(max_consec_loss, current_loss)
        else:
            current_win += 1
            current_loss = 0
            max_consec_win = max(max_consec_win, current_win)
    
    # 期望值（每笔交易的数学期望）
    expectancy = avg_return * len(trades_pnl) / max(report.total_trades, 1)
    
    # 恢复因子（总盈利 / 最大回撤）
    recovery_factor = (report.total_pnl / report.max_drawdown) if report.max_drawdown > 0 else 0
    
    # 系统质量指数 SQN = sqrt(N) * expectancy / std
    if len(trades_pnl) > 1:
        std_ret = math.sqrt(sum((r - avg_return) ** 2 for r in trades_pnl) / (len(trades_pnl) - 1))
        sqn = math.sqrt(len(trades_pnl)) * avg_return / std_ret if std_ret > 0 else 0
    else:
        sqn = 0
    
    return {
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "max_consecutive_losses": max_consec_loss,
        "max_consecutive_wins": max_consec_win,
        "expectancy_per_trade": round(expectancy * 100, 4),
        "recovery_factor": round(recovery_factor, 2),
        "sqn": round(sqn, 2),
        "sqn_rating": (
            "优秀" if sqn >= 2.5 else
            "良好" if sqn >= 1.7 else
            "一般" if sqn >= 0.7 else
            "较差"
        ),
        "annual_return_pct": round(annual_return * 100, 2),
        "total_periods": len(trades_pnl),
    }
