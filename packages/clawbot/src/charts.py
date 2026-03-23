"""
OpenClaw 图表引擎 — 搬运 plotly (18.4k⭐) + kaleido
替换 telegram_ux.py 的 matplotlib 图表，更美观、更丰富。

新增:
  - K线图 (candlestick) — 配合 pandas-ta 技术指标叠加
  - 资产饼图 — 交互式颜色方案
  - PnL 瀑布图 — 替代简单柱状图
  - 收益曲线 — 基准对比 + 回撤阴影
  - 情绪仪表盘 — RSI/Fear&Greed 可视化
  - 任务 DAG 流程图 — mermaid.ink 渲染

所有图表输出 PNG bytes，直接发送到 Telegram。
plotly/kaleido 不可用时自动降级到 telegram_ux.py 的 matplotlib 实现。
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── plotly 可用性探测 ────────────────────────────────────
_PLOTLY_AVAILABLE = False
try:
    import plotly.graph_objects as go  # type: ignore[import-untyped]
    from plotly.subplots import make_subplots  # type: ignore[import-untyped]
    _PLOTLY_AVAILABLE = True
except ImportError:
    logger.info("[charts] plotly 未安装，将降级到 matplotlib")


# ── 公共常量 ─────────────────────────────────────────────

_WIDTH = 800
_HEIGHT = 500
_DARK_BG = "#1a1a2e"
_PANEL_BG = "#16213e"
_GRID_COLOR = "rgba(51,51,51,0.3)"
_TEXT_COLOR = "#e0e0e0"

# 品牌色板（金/绿/蓝 + 辅助色）
_COLORS = [
    "#f0b90b",  # 金
    "#00d4aa",  # 绿
    "#3498db",  # 蓝
    "#9b59b6",  # 紫
    "#e67e22",  # 橙
    "#1abc9c",  # 青
    "#e74c3c",  # 红
    "#2ecc71",  # 亮绿
]

_DARK_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor=_DARK_BG,
    plot_bgcolor=_PANEL_BG,
    font=dict(color=_TEXT_COLOR, size=13),
    margin=dict(l=60, r=30, t=50, b=50),
    width=_WIDTH,
    height=_HEIGHT,
    xaxis=dict(gridcolor=_GRID_COLOR),
    yaxis=dict(gridcolor=_GRID_COLOR),
)


# ── 工具函数 ─────────────────────────────────────────────

def _fig_to_png(fig: "go.Figure") -> bytes:
    """将 plotly Figure 导出为 PNG bytes (via kaleido)。"""
    try:
        return fig.to_image(format="png", width=_WIDTH, height=_HEIGHT, scale=2)
    except Exception as exc:
        logger.warning("[charts] kaleido 导出失败 (%s), 尝试 orca", exc)
        # 最后手段：写入 BytesIO
        buf = io.BytesIO()
        fig.write_image(buf, format="png", width=_WIDTH, height=_HEIGHT, scale=2)
        buf.seek(0)
        return buf.read()


def _matplotlib_fallback(fn_name: str):
    """返回 telegram_ux.py 中同名的 matplotlib 函数，找不到则返回 None。"""
    try:
        from src import telegram_ux
        fn = getattr(telegram_ux, fn_name, None)
        if fn is not None:
            logger.info("[charts] 降级到 matplotlib: %s", fn_name)
        return fn
    except ImportError:
        return None


# ============================================================
# a) K线图 — candlestick + volume + 技术指标叠加
# ============================================================

def generate_candlestick(
    ohlcv_data: List[Dict[str, Any]],
    symbol: str = "",
    indicators: Optional[Dict[str, Any]] = None,
) -> bytes:
    """K 线图 + 成交量 + 可选技术指标叠加。

    Args:
        ohlcv_data: [{"date": ..., "open": f, "high": f, "low": f, "close": f, "volume": f}, ...]
        symbol: 标的代码 (标题用)
        indicators: 可选叠加指标 — 支持的 key:
            "ma": [{"period": 20, "values": [...]}]
            "bbands": {"upper": [...], "middle": [...], "lower": [...]}
            "signals": [{"idx": int, "side": "buy"|"sell"}]

    Returns:
        PNG bytes
    """
    if not ohlcv_data:
        return b""

    if not _PLOTLY_AVAILABLE:
        # 没有对等的 matplotlib 降级；返回空
        logger.warning("[charts] plotly 不可用，candlestick 无降级")
        return b""

    dates = [d.get("date", i) for i, d in enumerate(ohlcv_data)]
    opens = [d["open"] for d in ohlcv_data]
    highs = [d["high"] for d in ohlcv_data]
    lows = [d["low"] for d in ohlcv_data]
    closes = [d["close"] for d in ohlcv_data]
    volumes = [d.get("volume", 0) for d in ohlcv_data]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
    )

    # ── 主图：K 线
    fig.add_trace(
        go.Candlestick(
            x=dates, open=opens, high=highs, low=lows, close=closes,
            increasing_line_color="#2ecc71",
            decreasing_line_color="#e74c3c",
            name=symbol or "OHLC",
        ),
        row=1, col=1,
    )

    # ── 叠加指标
    if indicators:
        # 均线
        for ma in indicators.get("ma", []):
            period = ma.get("period", "?")
            vals = ma.get("values", [])
            if vals:
                fig.add_trace(
                    go.Scatter(
                        x=dates[:len(vals)], y=vals,
                        mode="lines", name=f"MA{period}",
                        line=dict(width=1.2),
                    ),
                    row=1, col=1,
                )

        # 布林带
        bb = indicators.get("bbands")
        if bb:
            for key, color, dash in [
                ("upper", "#f0b90b", "dash"),
                ("middle", "#3498db", "solid"),
                ("lower", "#f0b90b", "dash"),
            ]:
                vals = bb.get(key, [])
                if vals:
                    fig.add_trace(
                        go.Scatter(
                            x=dates[:len(vals)], y=vals,
                            mode="lines", name=f"BB-{key}",
                            line=dict(width=1, color=color, dash=dash),
                        ),
                        row=1, col=1,
                    )

        # 买卖信号标记
        for sig in indicators.get("signals", []):
            idx = sig.get("idx", 0)
            side = sig.get("side", "buy")
            if 0 <= idx < len(dates):
                fig.add_trace(
                    go.Scatter(
                        x=[dates[idx]],
                        y=[lows[idx] * 0.995] if side == "buy" else [highs[idx] * 1.005],
                        mode="markers",
                        marker=dict(
                            symbol="triangle-up" if side == "buy" else "triangle-down",
                            size=12,
                            color="#2ecc71" if side == "buy" else "#e74c3c",
                        ),
                        name=side.upper(),
                        showlegend=False,
                    ),
                    row=1, col=1,
                )

    # ── 副图：成交量
    vol_colors = [
        "#2ecc71" if c >= o else "#e74c3c"
        for o, c in zip(opens, closes)
    ]
    fig.add_trace(
        go.Bar(x=dates, y=volumes, marker_color=vol_colors, name="Volume", showlegend=False),
        row=2, col=1,
    )

    fig.update_layout(
        **_DARK_LAYOUT,
        title=dict(text=f"{symbol} K线图" if symbol else "K线图", x=0.5),
        xaxis_rangeslider_visible=False,
        height=600,  # K 线图稍高一点
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)

    return _fig_to_png(fig)


# ============================================================
# b) 持仓分布饼图
# ============================================================

def generate_portfolio_pie(
    positions: List[Dict[str, Any]],
    title: str = "持仓分布",
) -> bytes:
    """交互式持仓饼图 — 最大仓位自动 pull-out。

    Args:
        positions: [{"symbol": "AAPL", "market_value": 5000}, ...]
        title: 图表标题

    Returns:
        PNG bytes
    """
    if not positions:
        return b""

    if not _PLOTLY_AVAILABLE:
        fallback = _matplotlib_fallback("generate_portfolio_pie")
        if fallback:
            buf = fallback(positions, title)
            return buf.read() if hasattr(buf, "read") else bytes(buf)
        return b""

    symbols = [p.get("symbol", "?") for p in positions]
    values = [abs(p.get("market_value", 0)) for p in positions]
    total = sum(values) or 1

    # 最大仓位 pull-out
    max_idx = values.index(max(values)) if values else 0
    pull = [0.08 if i == max_idx else 0 for i in range(len(values))]

    colors = [_COLORS[i % len(_COLORS)] for i in range(len(symbols))]

    fig = go.Figure(
        go.Pie(
            labels=symbols,
            values=values,
            pull=pull,
            hole=0.35,
            marker=dict(colors=colors, line=dict(color=_DARK_BG, width=2)),
            textinfo="label+percent",
            textfont=dict(size=12, color="#ffffff"),
            hovertemplate="%{label}: $%{value:,.0f} (%{percent})<extra></extra>",
        )
    )

    fig.update_layout(
        **_DARK_LAYOUT,
        title=dict(text=f"{title}  |  总值 ${total:,.0f}", x=0.5),
        showlegend=True,
        legend=dict(font=dict(size=11)),
    )

    return _fig_to_png(fig)


# ============================================================
# c) PnL 瀑布图
# ============================================================

def generate_pnl_waterfall(
    trades: List[Dict[str, Any]],
    title: str = "交易盈亏",
) -> bytes:
    """瀑布图 — 逐笔 PnL + 累计总额。

    Args:
        trades: [{"symbol": "AAPL", "pnl": 50.0}, {"symbol": "NVDA", "pnl": -20.0}, ...]
        title: 图表标题

    Returns:
        PNG bytes
    """
    if not trades:
        return b""

    if not _PLOTLY_AVAILABLE:
        fallback = _matplotlib_fallback("generate_pnl_chart")
        if fallback:
            buf = fallback(trades, title)
            return buf.read() if hasattr(buf, "read") else bytes(buf)
        return b""

    symbols = [t.get("symbol", "?") for t in trades]
    pnls = [t.get("pnl", 0.0) for t in trades]

    # Waterfall: measures = "relative" for each trade, "total" for final
    measures = ["relative"] * len(pnls) + ["total"]
    labels = symbols + ["合计"]
    values = pnls + [sum(pnls)]

    fig = go.Figure(
        go.Waterfall(
            x=labels,
            y=values,
            measure=measures,
            increasing=dict(marker_color="#2ecc71"),
            decreasing=dict(marker_color="#e74c3c"),
            totals=dict(marker_color="#3498db"),
            connector=dict(line=dict(color="#555555", width=1)),
            textposition="outside",
            text=[f"${v:+,.0f}" for v in values],
            textfont=dict(size=11, color=_TEXT_COLOR),
        )
    )

    fig.update_layout(
        **_DARK_LAYOUT,
        title=dict(text=title, x=0.5),
        yaxis_title="盈亏 ($)",
        showlegend=False,
    )

    return _fig_to_png(fig)


# ============================================================
# d) 权益曲线 — 基准对比 + 回撤阴影
# ============================================================

def generate_equity_curve(
    equity_data: List[float],
    benchmark: Optional[List[float]] = None,
    title: str = "权益曲线",
) -> bytes:
    """权益曲线 + 可选基准对比 + 回撤阴影。

    Args:
        equity_data: [10000, 10050, 9980, ...]
        benchmark: 可选基准净值序列 (长度应与 equity_data 一致)
        title: 图表标题

    Returns:
        PNG bytes
    """
    if not equity_data:
        return b""

    if not _PLOTLY_AVAILABLE:
        fallback = _matplotlib_fallback("generate_equity_chart")
        if fallback:
            buf = fallback(equity_data, title)
            return buf.read() if hasattr(buf, "read") else bytes(buf)
        return b""

    x = list(range(len(equity_data)))

    fig = go.Figure()

    # ── 回撤阴影 (drawdown fill)
    peak = equity_data[0]
    drawdown_y = []
    for val in equity_data:
        peak = max(peak, val)
        drawdown_y.append(peak)

    # 峰值线（透明，用于 fill between）
    fig.add_trace(
        go.Scatter(
            x=x, y=drawdown_y,
            mode="lines", line=dict(width=0), showlegend=False,
            hoverinfo="skip",
        )
    )
    # 权益线 + 回撤填充
    fig.add_trace(
        go.Scatter(
            x=x, y=equity_data,
            mode="lines", name="权益",
            line=dict(color="#00d4aa", width=2.5),
            fill="tonexty",
            fillcolor="rgba(239, 68, 68, 0.15)",  # 回撤区域红色半透
        )
    )

    # ── 基准线
    if benchmark and len(benchmark) > 0:
        bm_x = list(range(len(benchmark)))
        fig.add_trace(
            go.Scatter(
                x=bm_x, y=benchmark,
                mode="lines", name="基准",
                line=dict(color="#f0b90b", width=1.5, dash="dash"),
            )
        )

    # ── 标注最高/最低
    if equity_data:
        max_val = max(equity_data)
        min_val = min(equity_data)
        max_idx = equity_data.index(max_val)
        min_idx = equity_data.index(min_val)

        fig.add_annotation(
            x=max_idx, y=max_val,
            text=f"${max_val:,.0f}",
            showarrow=True, arrowhead=2, arrowcolor="#2ecc71",
            font=dict(color="#2ecc71", size=11),
            ax=0, ay=-25,
        )
        fig.add_annotation(
            x=min_idx, y=min_val,
            text=f"${min_val:,.0f}",
            showarrow=True, arrowhead=2, arrowcolor="#e74c3c",
            font=dict(color="#e74c3c", size=11),
            ax=0, ay=25,
        )

    fig.update_layout(
        **_DARK_LAYOUT,
        title=dict(text=title, x=0.5),
        xaxis_title="交易日",
        yaxis_title="权益 ($)",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    return _fig_to_png(fig)


# ============================================================
# e) 情绪仪表盘 — RSI / Fear&Greed
# ============================================================

def generate_sentiment_gauge(
    score: float,
    label: str = "市场情绪",
) -> bytes:
    """仪表盘可视化 — 适用于 RSI、恐贪指数等 0-100 分值。

    Args:
        score: 0-100 分值
        label: 显示标签 (如 "RSI", "Fear & Greed")

    Returns:
        PNG bytes
    """
    if not _PLOTLY_AVAILABLE:
        logger.warning("[charts] plotly 不可用，gauge 无降级")
        return b""

    score = max(0.0, min(100.0, float(score)))

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=score,
            title=dict(text=label, font=dict(size=18, color=_TEXT_COLOR)),
            number=dict(font=dict(size=40, color=_TEXT_COLOR)),
            gauge=dict(
                axis=dict(range=[0, 100], tickcolor=_TEXT_COLOR),
                bar=dict(color="#f0b90b", thickness=0.3),
                bgcolor=_PANEL_BG,
                borderwidth=2,
                bordercolor="#333333",
                steps=[
                    dict(range=[0, 25], color="#ef4444"),     # 极度恐惧 — 红
                    dict(range=[25, 45], color="#f97316"),     # 恐惧 — 橙
                    dict(range=[45, 55], color="#eab308"),     # 中性 — 黄
                    dict(range=[55, 75], color="#84cc16"),     # 贪婪 — 黄绿
                    dict(range=[75, 100], color="#22c55e"),    # 极度贪婪 — 绿
                ],
                threshold=dict(
                    line=dict(color="#ffffff", width=3),
                    thickness=0.8,
                    value=score,
                ),
            ),
        )
    )

    fig.update_layout(
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_PANEL_BG,
        font=dict(color=_TEXT_COLOR),
        width=_WIDTH,
        height=_HEIGHT,
        margin=dict(l=40, r=40, t=80, b=30),
    )

    return _fig_to_png(fig)


# ============================================================
# f) 任务 DAG 流程图 — mermaid.ink 渲染
# ============================================================

async def render_task_dag(
    nodes: Dict[str, Any],
    title: str = "",
) -> bytes:
    """将任务 DAG 渲染为流程图 (via mermaid.ink API)。

    兼容两种输入格式:
      1. TaskGraph.nodes (Dict[str, TaskNode]) — 直接访问 .name / .status / .dependencies
      2. 序列化后的 dict — {"node_id": {"name": ..., "status": ..., "dependencies": [...]}}

    Args:
        nodes: 节点映射 {node_id: TaskNode | dict}
        title: 可选标题 (会加到图头部注释)

    Returns:
        PNG bytes (渲染失败时返回 b"")
    """
    if not nodes:
        return b""

    lines = ["graph TD"]

    if title:
        lines.append(f"    %% {title}")

    status_styles = {
        "success": ":::green",
        "failed": ":::red",
        "running": ":::yellow",
        "pending": ":::gray",
        "waiting": ":::gray",
        "skipped": ":::gray",
        "cancelled": ":::red",
    }

    for node_id, node in nodes.items():
        # 兼容 TaskNode 对象和 dict
        if hasattr(node, "name"):
            name = node.name
            status = node.status.value if hasattr(node.status, "value") else str(node.status)
            deps = node.dependencies
        else:
            name = node.get("name", node_id)
            status = node.get("status", "pending")
            deps = node.get("dependencies", [])

        style = status_styles.get(status.lower(), ":::gray")
        # 转义 Mermaid 特殊字符
        safe_label = str(name).replace('"', "'").replace("\n", " ")
        lines.append(f'    {node_id}["{safe_label}"]{style}')

        for dep in deps:
            lines.append(f"    {dep} --> {node_id}")

    # classDef 颜色定义
    lines.append("    classDef green fill:#22c55e,color:#fff,stroke:#16a34a")
    lines.append("    classDef red fill:#ef4444,color:#fff,stroke:#dc2626")
    lines.append("    classDef yellow fill:#eab308,color:#000,stroke:#ca8a04")
    lines.append("    classDef gray fill:#6b7280,color:#fff,stroke:#4b5563")

    diagram = "\n".join(lines)

    # ── 渲染: mermaid.ink API ──
    import base64

    try:
        import httpx
    except ImportError:
        logger.warning("[charts] httpx 不可用，无法渲染 DAG")
        return b""

    encoded = base64.urlsafe_b64encode(diagram.encode("utf-8")).decode("ascii")
    url = f"https://mermaid.ink/img/{encoded}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.content
            logger.warning(
                "[charts] mermaid.ink 返回 %s, diagram=%s",
                resp.status_code, diagram[:200],
            )
    except Exception as exc:
        logger.warning("[charts] mermaid.ink 请求失败: %s", exc)

    return b""


# ============================================================
# 便捷入口: 从 TaskGraph 对象直接渲染
# ============================================================

async def render_graph(graph: Any, title: str = "") -> bytes:
    """从 TaskGraph 对象渲染 DAG 图。

    Args:
        graph: core.task_graph.TaskGraph 实例
        title: 可选标题 (默认取 graph.name)

    Returns:
        PNG bytes
    """
    if hasattr(graph, "nodes") and isinstance(graph.nodes, dict):
        return await render_task_dag(graph.nodes, title=title or getattr(graph, "name", ""))
    return b""
