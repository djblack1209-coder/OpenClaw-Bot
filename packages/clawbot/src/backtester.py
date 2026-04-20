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

文件拆分说明（HI-358）：
- backtester_models.py: 数据结构 + 数据加载
- backtester.py: 核心回测引擎 + 便捷函数（本文件）
- backtester_advanced.py: v2.0 高级分析功能
所有符号均通过本文件 re-export，外部 import 路径无需修改。
"""
import logging
import math
from typing import Dict, List, Optional

from src.risk_config import RiskConfig
from src.risk_manager import RiskManager

# === re-export: 数据模型和数据加载（从 backtester_models 导入并暴露） ===
from src.backtester_models import (  # noqa: F401
    Bar,
    BacktestTrade,
    BacktestConfig,
    PerformanceReport,
    load_historical_data,
    bars_to_dataframe,
)

# === re-export: v2.0 高级分析功能（从 backtester_advanced 导入并暴露） ===
from src.backtester_advanced import (  # noqa: F401
    run_monte_carlo,
    format_monte_carlo,
    run_parameter_optimization,
    format_optimization_result,
    run_walk_forward,
    format_walk_forward,
    calc_enhanced_metrics,
)

logger = logging.getLogger(__name__)


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
        logger.info(report.format())
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
            logger.info("%s: PnL=$%+.2f WR=%.0f%%", sym, r.total_pnl, r.win_rate)
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
