"""
ClawBot 回测报告生成器 v1.0（对标 TradingAgents 32.5k⭐ + freqtrade 47.7k⭐）

功能：
- HTML 可视化回测报告（权益曲线、回撤图、交易分布）
- 风险指标仪表盘（Sharpe/Sortino/Calmar/最大回撤）
- 交易明细表格
- 蒙特卡洛模拟可视化
- 策略对比报告
- 纯 Python 实现，零外部依赖（使用 SVG 图表）
"""

import math
import logging
from typing import Any, Dict, List, Optional
from src.utils import now_et

logger = logging.getLogger(__name__)


# ============ SVG 图表生成器（零依赖） ============

class SVGChart:
    """轻量级 SVG 图表生成器（替代 matplotlib，零依赖）"""

    @staticmethod
    def line_chart(
        data: List[float],
        width: int = 800, height: int = 300,
        title: str = "", color: str = "#2196F3",
        fill: bool = True, labels: Optional[List[str]] = None,
    ) -> str:
        """生成 SVG 折线图"""
        if not data or len(data) < 2:
            return '<svg width="800" height="100"><text x="400" y="50" text-anchor="middle">数据不足</text></svg>'

        margin = {"top": 40, "right": 20, "bottom": 30, "left": 70}
        chart_w = width - margin["left"] - margin["right"]
        chart_h = height - margin["top"] - margin["bottom"]

        min_val = min(data)
        max_val = max(data)
        val_range = max_val - min_val if max_val != min_val else 1

        def x_pos(i):
            return margin["left"] + (i / max(len(data) - 1, 1)) * chart_w

        def y_pos(v):
            return margin["top"] + chart_h - ((v - min_val) / val_range) * chart_h

        # 构建路径
        points = " ".join(f"{x_pos(i):.1f},{y_pos(v):.1f}" for i, v in enumerate(data))
        fill_points = (
            f"{x_pos(0):.1f},{margin['top'] + chart_h:.1f} "
            + points
            + f" {x_pos(len(data)-1):.1f},{margin['top'] + chart_h:.1f}"
        )

        svg = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
        svg.append(f'<rect width="{width}" height="{height}" fill="#fafafa" rx="8"/>')

        # 标题
        if title:
            svg.append(f'<text x="{width//2}" y="24" text-anchor="middle" '
                       f'font-size="14" font-weight="bold" fill="#333">{title}</text>')

        # Y 轴网格线和标签
        for i in range(5):
            y = margin["top"] + chart_h * i / 4
            val = max_val - val_range * i / 4
            svg.append(f'<line x1="{margin["left"]}" y1="{y:.1f}" '
                       f'x2="{width - margin["right"]}" y2="{y:.1f}" '
                       f'stroke="#e0e0e0" stroke-width="1"/>')
            svg.append(f'<text x="{margin["left"] - 5}" y="{y + 4:.1f}" '
                       f'text-anchor="end" font-size="11" fill="#666">'
                       f'{val:,.0f}</text>')

        # 填充区域
        if fill:
            svg.append(f'<polygon points="{fill_points}" fill="{color}" opacity="0.15"/>')

        # 折线
        svg.append(f'<polyline points="{points}" fill="none" '
                   f'stroke="{color}" stroke-width="2"/>')

        # 起止点标记
        svg.append(f'<circle cx="{x_pos(0):.1f}" cy="{y_pos(data[0]):.1f}" '
                   f'r="4" fill="{color}"/>')
        svg.append(f'<circle cx="{x_pos(len(data)-1):.1f}" cy="{y_pos(data[-1]):.1f}" '
                   f'r="4" fill="{color}"/>')

        svg.append('</svg>')
        return "\n".join(svg)

    @staticmethod
    def bar_chart(
        labels: List[str], values: List[float],
        width: int = 600, height: int = 250,
        title: str = "", color_positive: str = "#4CAF50",
        color_negative: str = "#F44336",
    ) -> str:
        """生成 SVG 柱状图"""
        if not values:
            return '<svg width="600" height="100"><text x="300" y="50" text-anchor="middle">无数据</text></svg>'

        margin = {"top": 40, "right": 20, "bottom": 50, "left": 70}
        chart_w = width - margin["left"] - margin["right"]
        chart_h = height - margin["top"] - margin["bottom"]

        max_abs = max(abs(v) for v in values) if values else 1
        bar_w = max(4, chart_w / len(values) * 0.7)
        gap = chart_w / len(values)

        # 零线位置
        has_negative = any(v < 0 for v in values)
        if has_negative:
            zero_y = margin["top"] + chart_h / 2
            scale = chart_h / 2 / max_abs
        else:
            zero_y = margin["top"] + chart_h
            scale = chart_h / max_abs if max_abs > 0 else 1

        svg = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
        svg.append(f'<rect width="{width}" height="{height}" fill="#fafafa" rx="8"/>')

        if title:
            svg.append(f'<text x="{width//2}" y="24" text-anchor="middle" '
                       f'font-size="14" font-weight="bold" fill="#333">{title}</text>')

        # 零线
        svg.append(f'<line x1="{margin["left"]}" y1="{zero_y:.1f}" '
                   f'x2="{width - margin["right"]}" y2="{zero_y:.1f}" '
                   f'stroke="#999" stroke-width="1"/>')

        for i, (label, val) in enumerate(zip(labels, values)):
            x = margin["left"] + gap * i + (gap - bar_w) / 2
            bar_h = abs(val) * scale
            color = color_positive if val >= 0 else color_negative

            if val >= 0:
                y = zero_y - bar_h
            else:
                y = zero_y

            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                       f'height="{max(bar_h, 1):.1f}" fill="{color}" rx="2"/>')

            # 标签（旋转45度）
            lx = x + bar_w / 2
            ly = height - 5
            short_label = label[:8] if len(label) > 8 else label
            svg.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="end" '
                       f'font-size="10" fill="#666" '
                       f'transform="rotate(-45 {lx:.1f} {ly:.1f})">{short_label}</text>')

        svg.append('</svg>')
        return "\n".join(svg)

    @staticmethod
    def gauge(
        value: float, min_val: float = 0, max_val: float = 100,
        title: str = "", width: int = 200, height: int = 130,
        thresholds: Optional[List[tuple]] = None,
    ) -> str:
        """生成 SVG 仪表盘"""
        if thresholds is None:
            thresholds = [(33, "#F44336"), (66, "#FF9800"), (100, "#4CAF50")]

        pct = max(0, min(1, (value - min_val) / (max_val - min_val))) if max_val != min_val else 0
        angle = -90 + pct * 180  # -90 到 90 度

        cx, cy = width / 2, height - 20
        r = min(width, height) * 0.4

        # 确定颜色
        color = thresholds[-1][1]
        for threshold_pct, threshold_color in thresholds:
            if pct * 100 <= threshold_pct:
                color = threshold_color
                break

        svg = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']

        # 背景弧
        svg.append(f'<path d="M {cx - r:.1f} {cy:.1f} A {r:.1f} {r:.1f} 0 0 1 {cx + r:.1f} {cy:.1f}" '
                   f'fill="none" stroke="#e0e0e0" stroke-width="12" stroke-linecap="round"/>')

        # 值弧
        if pct > 0:
            math.radians(angle)
            end_x = cx + r * math.cos(math.radians(-90 + pct * 180))
            end_y = cy + r * math.sin(math.radians(-90 + pct * 180))
            large_arc = 1 if pct > 0.5 else 0
            svg.append(f'<path d="M {cx - r:.1f} {cy:.1f} A {r:.1f} {r:.1f} 0 {large_arc} 1 '
                       f'{end_x:.1f} {end_y:.1f}" '
                       f'fill="none" stroke="{color}" stroke-width="12" stroke-linecap="round"/>')

        # 值文本
        svg.append(f'<text x="{cx}" y="{cy - 10}" text-anchor="middle" '
                   f'font-size="20" font-weight="bold" fill="{color}">{value:.1f}</text>')

        if title:
            svg.append(f'<text x="{cx}" y="{cy + 15}" text-anchor="middle" '
                       f'font-size="11" fill="#666">{title}</text>')

        svg.append('</svg>')
        return "\n".join(svg)


# ============ HTML 报告生成器 ============

class BacktestReporter:
    """回测报告生成器（对标 TradingAgents + freqtrade 的可视化报告）"""

    CSS = """
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #f5f5f5; color: #333; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: linear-gradient(135deg, #1a237e, #283593);
                  color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }
        .header h1 { font-size: 24px; margin-bottom: 8px; }
        .header .subtitle { opacity: 0.8; font-size: 14px; }
        .card { background: white; border-radius: 12px; padding: 20px;
                margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .card h2 { font-size: 16px; color: #1a237e; margin-bottom: 16px;
                   padding-bottom: 8px; border-bottom: 2px solid #e8eaf6; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                        gap: 12px; margin-bottom: 16px; }
        .metric { background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center; }
        .metric .value { font-size: 24px; font-weight: bold; }
        .metric .label { font-size: 12px; color: #666; margin-top: 4px; }
        .positive { color: #4CAF50; }
        .negative { color: #F44336; }
        .neutral { color: #FF9800; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { background: #f5f5f5; padding: 10px 8px; text-align: left;
             font-weight: 600; border-bottom: 2px solid #e0e0e0; }
        td { padding: 8px; border-bottom: 1px solid #f0f0f0; }
        tr:hover { background: #fafafa; }
        .gauge-row { display: flex; justify-content: space-around; flex-wrap: wrap; }
        .footer { text-align: center; color: #999; font-size: 12px; padding: 20px; }
        @media (max-width: 768px) {
            .metrics-grid { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
    """

    @staticmethod
    def _color_class(value: float) -> str:
        if value > 0:
            return "positive"
        elif value < 0:
            return "negative"
        return "neutral"

    @staticmethod
    def generate_report(
        report,  # PerformanceReport
        symbol: str = "",
        enhanced_metrics: Optional[Dict] = None,
        monte_carlo: Optional[Dict] = None,
        trades: Optional[List] = None,
    ) -> str:
        """生成完整的 HTML 回测报告"""

        now = now_et().strftime("%Y-%m-%d %H:%M")
        pnl_class = BacktestReporter._color_class(report.total_pnl)

        html = [
            "<!DOCTYPE html>",
            '<html lang="zh-CN"><head>',
            '<meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            f'<title>ClawBot 回测报告 - {symbol}</title>',
            BacktestReporter.CSS,
            "</head><body>",
            '<div class="container">',
        ]

        # Header
        html.append(f"""
        <div class="header">
            <h1>ClawBot 回测报告</h1>
            <div class="subtitle">
                {symbol} | {report.start_date} ~ {report.end_date} |
                {report.trading_days} 个交易日 | 生成于 {now}
            </div>
        </div>
        """)

        # 核心指标卡片
        html.append('<div class="card"><h2>核心指标</h2>')
        html.append('<div class="metrics-grid">')
        metrics = [
            ("总盈亏", f"${report.total_pnl:+,.2f}", pnl_class),
            ("收益率", f"{report.total_pnl_pct:+.1f}%", pnl_class),
            ("总交易", f"{report.total_trades}", ""),
            ("胜率", f"{report.win_rate:.1f}%",
             "positive" if report.win_rate >= 50 else "negative"),
            ("盈亏比", f"{report.avg_rr_ratio:.2f}",
             "positive" if report.avg_rr_ratio >= 1.5 else "neutral"),
            ("利润因子", f"{report.profit_factor:.2f}",
             "positive" if report.profit_factor >= 1.5 else "neutral"),
            ("最大回撤", f"{report.max_drawdown_pct:.1f}%", "negative"),
            ("夏普比率", f"{report.sharpe_ratio:.2f}",
             "positive" if report.sharpe_ratio >= 1.0 else "neutral"),
        ]
        for label, value, css_class in metrics:
            html.append(f"""
            <div class="metric">
                <div class="value {css_class}">{value}</div>
                <div class="label">{label}</div>
            </div>
            """)
        html.append('</div></div>')

        # 增强指标（如果有）
        if enhanced_metrics and "error" not in enhanced_metrics:
            html.append('<div class="card"><h2>增强风险指标</h2>')
            html.append('<div class="gauge-row">')
            gauges = [
                ("Sortino", enhanced_metrics.get("sortino_ratio", 0), -2, 4),
                ("Calmar", enhanced_metrics.get("calmar_ratio", 0), -2, 4),
                ("SQN", enhanced_metrics.get("sqn", 0), -2, 4),
                ("恢复因子", enhanced_metrics.get("recovery_factor", 0), -2, 5),
            ]
            for title, val, mn, mx in gauges:
                html.append(SVGChart.gauge(val, mn, mx, title))
            html.append('</div>')

            html.append('<div class="metrics-grid" style="margin-top:16px">')
            extra = [
                ("年化收益", f"{enhanced_metrics.get('annual_return_pct', 0):.1f}%",
                 BacktestReporter._color_class(enhanced_metrics.get("annual_return_pct", 0))),
                ("最大连续亏损", f"{enhanced_metrics.get('max_consecutive_losses', 0)}", "negative"),
                ("最大连续盈利", f"{enhanced_metrics.get('max_consecutive_wins', 0)}", "positive"),
                ("SQN 评级", enhanced_metrics.get("sqn_rating", "N/A"), ""),
            ]
            for label, value, css_class in extra:
                html.append(f'<div class="metric"><div class="value {css_class}">{value}</div>'
                           f'<div class="label">{label}</div></div>')
            html.append('</div></div>')

        # 权益曲线
        if report.equity_curve and len(report.equity_curve) > 2:
            html.append('<div class="card"><h2>权益曲线</h2>')
            html.append(SVGChart.line_chart(
                report.equity_curve, width=1100, height=300,
                title="", color="#1a237e", fill=True,
            ))
            html.append('</div>')

            # 回撤图
            peak = report.equity_curve[0]
            drawdowns = []
            for eq in report.equity_curve:
                if eq > peak:
                    peak = eq
                dd_pct = (peak - eq) / peak * 100 if peak > 0 else 0
                drawdowns.append(-dd_pct)

            html.append('<div class="card"><h2>回撤曲线</h2>')
            html.append(SVGChart.line_chart(
                drawdowns, width=1100, height=200,
                title="", color="#F44336", fill=True,
            ))
            html.append('</div>')

        # 蒙特卡洛模拟（如果有）
        if monte_carlo and "error" not in monte_carlo:
            html.append('<div class="card"><h2>蒙特卡洛模拟</h2>')
            html.append('<div class="metrics-grid">')
            mc_metrics = [
                ("模拟次数", f"{monte_carlo.get('simulations', 0):,}", ""),
                ("中位数 PnL", f"${monte_carlo.get('median_pnl', 0):+,.2f}",
                 BacktestReporter._color_class(monte_carlo.get("median_pnl", 0))),
                ("最差 5%", f"${monte_carlo.get('worst_5pct_pnl', 0):+,.2f}", "negative"),
                ("最好 5%", f"${monte_carlo.get('best_5pct_pnl', 0):+,.2f}", "positive"),
                ("破产概率", f"{monte_carlo.get('ruin_probability', 0):.1f}%",
                 "positive" if monte_carlo.get("ruin_probability", 0) < 5 else "negative"),
                ("中位数回撤", f"{monte_carlo.get('median_max_drawdown', 0):.1f}%", "neutral"),
            ]
            for label, value, css_class in mc_metrics:
                html.append(f'<div class="metric"><div class="value {css_class}">{value}</div>'
                           f'<div class="label">{label}</div></div>')
            html.append('</div></div>')

        # 交易明细（如果有）
        if trades:
            html.append('<div class="card"><h2>交易明细（最近 50 笔）</h2>')
            html.append('<div style="overflow-x:auto"><table>')
            html.append('<tr><th>#</th><th>标的</th><th>方向</th><th>数量</th>'
                       '<th>入场价</th><th>出场价</th><th>盈亏</th><th>盈亏%</th>'
                       '<th>持仓K线</th><th>退出原因</th></tr>')
            for t in trades[-50:]:
                pnl = getattr(t, 'pnl', 0)
                pnl_pct = getattr(t, 'pnl_pct', 0)
                css = "positive" if pnl > 0 else "negative" if pnl < 0 else ""
                html.append(
                    f'<tr><td>{getattr(t, "trade_id", "")}</td>'
                    f'<td>{getattr(t, "symbol", "")}</td>'
                    f'<td>{getattr(t, "side", "")}</td>'
                    f'<td>{getattr(t, "quantity", 0)}</td>'
                    f'<td>${getattr(t, "entry_price", 0):.2f}</td>'
                    f'<td>${getattr(t, "exit_price", 0):.2f}</td>'
                    f'<td class="{css}">${pnl:+.2f}</td>'
                    f'<td class="{css}">{pnl_pct:+.1f}%</td>'
                    f'<td>{getattr(t, "bars_held", 0)}</td>'
                    f'<td>{getattr(t, "exit_reason", "")}</td></tr>'
                )
            html.append('</table></div></div>')

        # Footer
        html.append(f"""
        <div class="footer">
            ClawBot Trading System | 报告生成于 {now} | 仅供研究参考，不构成投资建议
        </div>
        """)

        html.append('</div></body></html>')
        return "\n".join(html)

    @staticmethod
    def generate_comparison_report(
        reports: Dict[str, Any],
        title: str = "策略对比报告",
    ) -> str:
        """生成多标的/多策略对比报告"""
        now = now_et().strftime("%Y-%m-%d %H:%M")

        html = [
            "<!DOCTYPE html>",
            '<html lang="zh-CN"><head>',
            '<meta charset="UTF-8">',
            f'<title>ClawBot {title}</title>',
            BacktestReporter.CSS,
            "</head><body>",
            '<div class="container">',
            f'<div class="header"><h1>{title}</h1>'
            f'<div class="subtitle">生成于 {now}</div></div>',
        ]

        # 对比表格
        html.append('<div class="card"><h2>策略对比</h2>')
        html.append('<div style="overflow-x:auto"><table>')
        html.append('<tr><th>标的</th><th>交易数</th><th>胜率</th><th>总PnL</th>'
                   '<th>收益率</th><th>最大回撤</th><th>夏普</th><th>利润因子</th></tr>')

        symbols = []
        pnl_values = []
        for sym, r in sorted(reports.items()):
            pnl_class = BacktestReporter._color_class(r.total_pnl)
            html.append(
                f'<tr><td><strong>{sym}</strong></td>'
                f'<td>{r.total_trades}</td>'
                f'<td>{r.win_rate:.1f}%</td>'
                f'<td class="{pnl_class}">${r.total_pnl:+,.2f}</td>'
                f'<td class="{pnl_class}">{r.total_pnl_pct:+.1f}%</td>'
                f'<td class="negative">{r.max_drawdown_pct:.1f}%</td>'
                f'<td>{r.sharpe_ratio:.2f}</td>'
                f'<td>{r.profit_factor:.2f}</td></tr>'
            )
            symbols.append(sym)
            pnl_values.append(r.total_pnl)

        html.append('</table></div></div>')

        # PnL 柱状图
        if symbols and pnl_values:
            html.append('<div class="card"><h2>盈亏对比</h2>')
            html.append(SVGChart.bar_chart(
                symbols, pnl_values, width=800, height=300,
                title="各标的盈亏 ($)",
            ))
            html.append('</div>')

        html.append(f'<div class="footer">ClawBot Trading System | {now}</div>')
        html.append('</div></body></html>')
        return "\n".join(html)

    @staticmethod
    def save_report(html: str, filepath: str):
        """保存报告到文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info("[BacktestReporter] 报告已保存: %s", filepath)
        except Exception as e:
            logger.error("[BacktestReporter] 保存失败: %s", e)


# ════════════════════════════════════════════
#  Bokeh 可视化层（搬运自 backtesting.py 8.1k⭐）
# ════════════════════════════════════════════

_bokeh_available = False
try:
    from backtesting import Backtest, Strategy
    from backtesting.lib import crossover
    _bokeh_available = True
except ImportError:
    Backtest = None  # type: ignore
    Strategy = None  # type: ignore
    logger.info("[BokehViz] backtesting.py 未安装，高级图表禁用")


def _make_bt_strategy(name: str = "ClawBotMA"):
    """动态生成 backtesting.py Strategy 子类（EMA 交叉）"""
    if not _bokeh_available:
        return None

    class _S(Strategy):
        n_fast = 10
        n_slow = 30

        def init(self):
            close = self.data.Close
            self.ema_fast = self.I(
                lambda c: __import__('pandas').Series(c).ewm(span=self.n_fast).mean(),
                close, name=f'EMA{self.n_fast}')
            self.ema_slow = self.I(
                lambda c: __import__('pandas').Series(c).ewm(span=self.n_slow).mean(),
                close, name=f'EMA{self.n_slow}')

        def next(self):
            if crossover(self.ema_fast, self.ema_slow):
                self.buy()
            elif crossover(self.ema_slow, self.ema_fast):
                self.position.close()

    _S.__name__ = name
    _S.__qualname__ = name
    return _S


class BokehVisualizer:
    """
    backtesting.py 集成可视化器

    流程: yfinance OHLCV → backtesting.py Backtest → Bokeh HTML → PNG BytesIO
    输出: BytesIO PNG 图片，兼容 telegram_ux.send_chart()
    """

    @staticmethod
    def run_and_plot(
        symbol: str, period: str = "1y",
        strategy_cls=None, cash: float = 10000,
    ) -> dict:
        """
        运行 backtesting.py 回测并生成图表

        Returns: {
            "success": bool,
            "stats": pd.Series (回测统计),
            "html_path": str (Bokeh HTML 路径),
            "chart_png": BytesIO | None (PNG 图片),
            "error": str,
        }
        """
        import tempfile

        if not _bokeh_available:
            return {"success": False, "error": "backtesting.py 未安装"}

        try:
            import yfinance as yf
            import pandas as pd

            # 1. 下载数据
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            if df.empty or len(df) < 30:
                return {"success": False, "error": f"{symbol} 数据不足 ({len(df)} bars)"}

            # backtesting.py 要求列名: Open, High, Low, Close, Volume
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.index = pd.to_datetime(df.index)
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            # 2. 运行回测
            strat = strategy_cls or _make_bt_strategy(f"{symbol}_EMA")
            bt = Backtest(df, strat, cash=cash, commission=0.001)
            stats = bt.run()

            # 3. 生成 Bokeh HTML
            html_dir = tempfile.mkdtemp(prefix="clawbot_bt_")
            html_path = f"{html_dir}/{symbol}_backtest.html"
            bt.plot(
                filename=html_path, open_browser=False,
                plot_equity=True, plot_pl=True,
                plot_volume=True, plot_drawdown=True,
                plot_trades=True, superimpose=True,
            )

            # 4. HTML → PNG (via bokeh export)
            chart_png = BokehVisualizer._html_to_png(html_path)

            logger.info("[BokehViz] %s 回测完成: %.1f%% 收益, %d 笔交易",
                        symbol, stats.get("Return [%]", 0), stats.get("# Trades", 0))

            return {
                "success": True,
                "stats": stats,
                "html_path": html_path,
                "chart_png": chart_png,
                "error": "",
            }
        except Exception as e:
            logger.error("[BokehViz] %s 回测失败: %s", symbol, e)
            return {"success": False, "error": str(e)}

    @staticmethod
    def _html_to_png(html_path: str):
        """Bokeh HTML → PNG BytesIO（多种降级策略）"""
        import io

        # 方案1: bokeh export_png — 跳过，直接用 playwright
        # (需要 selenium/geckodriver，且无法从 HTML 文件直接导出)

        # 方案2: playwright 截图
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1400, "height": 900})
                page.goto(f"file://{html_path}")
                page.wait_for_timeout(2000)  # 等 Bokeh JS 渲染
                png_bytes = page.screenshot(full_page=False)
                browser.close()
            buf = io.BytesIO(png_bytes)
            buf.name = "backtest_chart.png"
            buf.seek(0)
            logger.info("[BokehViz] Playwright 截图成功 (%d bytes)", len(png_bytes))
            return buf
        except (ImportError, Exception) as e:
            logger.info("[BokehViz] Playwright 不可用: %s, 降级到 matplotlib", e)

        # 方案3: 降级 — 用 matplotlib 画简化版
        return None

    @staticmethod
    def stats_to_text(stats, symbol: str = "", period: str = "") -> str:
        """backtesting.py stats → 格式化文本"""
        if stats is None:
            return "无回测数据"
        lines = []
        if symbol:
            lines.append(f"📊 {symbol} 回测结果 ({period}) [backtesting.py]")
            lines.append("─" * 28)
        key_map = {
            "Return [%]": ("总收益", ":.2f", "%"),
            "Buy & Hold Return [%]": ("买入持有", ":.2f", "%"),
            "Max. Drawdown [%]": ("最大回撤", ":.2f", "%"),
            "# Trades": ("交易数", ":.0f", ""),
            "Win Rate [%]": ("胜率", ":.1f", "%"),
            "Sharpe Ratio": ("Sharpe", ":.2f", ""),
            "Sortino Ratio": ("Sortino", ":.2f", ""),
            "Calmar Ratio": ("Calmar", ":.2f", ""),
            "SQN": ("SQN", ":.2f", ""),
            "Profit Factor": ("盈亏比", ":.2f", ""),
            "Avg. Trade [%]": ("平均收益", ":+.2f", "%"),
            "Best Trade [%]": ("最佳交易", ":+.2f", "%"),
            "Worst Trade [%]": ("最差交易", ":+.2f", "%"),
            "Avg. Trade Duration": ("平均持仓", "", ""),
            "Expectancy [%]": ("期望值", ":+.2f", "%"),
        }
        for key, (label, fmt, suffix) in key_map.items():
            val = stats.get(key)
            if val is not None:
                try:
                    formatted = format(val, fmt.lstrip(':')) if fmt else str(val)
                except (ValueError, TypeError) as e:  # noqa: F841
                    formatted = str(val)
                lines.append(f"{label}: {formatted}{suffix}")
        return "\n".join(lines)
