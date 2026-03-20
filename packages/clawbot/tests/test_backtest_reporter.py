"""测试回测报告生成器"""
import pytest
from src.backtest_reporter import BacktestReporter, SVGChart
from src.backtester import PerformanceReport


def test_svg_line_chart():
    """测试 SVG 折线图生成"""
    data = [100, 105, 103, 110, 108, 115]
    svg = SVGChart.line_chart(data, title="测试")
    assert "<svg" in svg
    assert "</svg>" in svg
    assert "polyline" in svg


def test_svg_bar_chart():
    """测试 SVG 柱状图生成"""
    labels = ["A", "B", "C"]
    values = [10, -5, 15]
    svg = SVGChart.bar_chart(labels, values, title="测试")
    assert "<svg" in svg
    assert "rect" in svg


def test_svg_gauge():
    """测试 SVG 仪表盘生成"""
    svg = SVGChart.gauge(75, 0, 100, "测试")
    assert "<svg" in svg
    assert "path" in svg


def test_generate_report():
    """测试 HTML 报告生成"""
    report = PerformanceReport(
        total_trades=10,
        winning_trades=6,
        losing_trades=4,
        win_rate=60.0,
        total_pnl=500.0,
        total_pnl_pct=5.0,
        avg_win=100.0,
        avg_loss=-50.0,
        profit_factor=1.5,
        avg_rr_ratio=2.0,
        max_drawdown=200.0,
        max_drawdown_pct=2.0,
        sharpe_ratio=1.2,
        start_date="2024-01-01",
        end_date="2024-12-31",
        trading_days=252,
        equity_curve=[10000, 10100, 10050, 10200, 10500],
    )
    
    html = BacktestReporter.generate_report(report, symbol="TEST")
    assert "<!DOCTYPE html>" in html
    assert "ClawBot 回测报告" in html
    assert "TEST" in html
    assert "$500.00" in html or "$+500.00" in html
    assert "60.0%" in html


def test_comparison_report():
    """测试对比报告生成"""
    r1 = PerformanceReport(total_trades=5, total_pnl=100, win_rate=60)
    r2 = PerformanceReport(total_trades=8, total_pnl=-50, win_rate=40)
    
    reports = {"AAPL": r1, "MSFT": r2}
    html = BacktestReporter.generate_comparison_report(reports)
    
    assert "策略对比报告" in html
    assert "AAPL" in html
    assert "MSFT" in html
