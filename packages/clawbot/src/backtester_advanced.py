"""
ClawBot 回测引擎 — v2.0 高级分析功能

从 backtester.py 拆分出来的高级分析功能（对标 freqtrade 47.7k⭐）：
- run_monte_carlo: 蒙特卡洛模拟，评估策略稳健性
- run_parameter_optimization: 网格搜索参数优化
- run_walk_forward: Walk-Forward 分析，检测过拟合
- calc_enhanced_metrics: 增强绩效指标（Sortino/Calmar/SQN等）
"""
import math
import random
import logging
import itertools
from typing import Dict, List, Any

from src.backtester_models import (
    Bar,
    BacktestConfig,
    PerformanceReport,
    load_historical_data,
)
from src.risk_config import RiskConfig

logger = logging.getLogger(__name__)


# ============ 蒙特卡洛模拟 ============

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


# ============ 参数优化（网格搜索） ============

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
    # 延迟导入避免循环依赖
    from src.backtester import Backtester

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


# ============ Walk-Forward 分析 ============

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
    # 延迟导入避免循环依赖
    from src.backtester import Backtester

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


# ============ 增强绩效指标 ============

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
