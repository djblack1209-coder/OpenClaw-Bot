"""
PDF 报告生成服务 — 每日简报 / 交易报告
降级链: fpdf2 → 纯文本提示
"""
import io
import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── 可选依赖: fpdf2 ─────────────────────────────────────────
try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False
    logger.info("fpdf2 未安装，PDF 报告功能不可用")

# ── 颜色常量 ─────────────────────────────────────────────────
_CLR_HEADER = (31, 78, 121)       # 深蓝
_CLR_SUB_HEADER = (68, 114, 148)  # 中蓝
_CLR_TEXT = (33, 33, 33)          # 深灰
_CLR_GREEN = (0, 128, 0)
_CLR_RED = (192, 0, 0)
_CLR_LIGHT_BG = (240, 245, 250)  # 浅蓝灰
_CLR_WHITE = (255, 255, 255)
_CLR_BORDER = (180, 198, 220)


class _ReportPDF(FPDF):
    """带页眉页脚的 PDF 基类"""

    def __init__(self, title: str = "ClawBot Report"):
        super().__init__()
        self.report_title = title
        self._add_unicode_font()

    def _add_unicode_font(self):
        """注册 CJK 字体 — 优先系统中文字体，降级到内置 Helvetica"""
        import os
        # macOS 系统字体路径
        font_candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            # Linux
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        for path in font_candidates:
            if os.path.exists(path):
                try:
                    self.add_font("CJK", "", path, uni=True)
                    self.add_font("CJK", "B", path, uni=True)
                    self._cjk_font = "CJK"
                    return
                except Exception as e:
                    logger.debug("字体加载失败 %s: %s", path, e)
        # 降级: 使用内置字体 (不支持中文但不会崩溃)
        self._cjk_font = "Helvetica"

    def header(self):
        self.set_fill_color(*_CLR_HEADER)
        self.rect(0, 0, 210, 20, "F")
        self.set_font(self._cjk_font, "B", 12)
        self.set_text_color(*_CLR_WHITE)
        self.set_y(5)
        self.cell(0, 10, self.report_title, align="C")
        self.ln(18)

    def footer(self):
        self.set_y(-15)
        self.set_font(self._cjk_font, "", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"ClawBot | {datetime.now().strftime('%Y-%m-%d %H:%M')} | Page {self.page_no()}", align="C")

    def section_title(self, title: str):
        """节标题"""
        self.set_font(self._cjk_font, "B", 13)
        self.set_text_color(*_CLR_SUB_HEADER)
        self.cell(0, 10, title)
        self.ln(8)
        # 下划线
        self.set_draw_color(*_CLR_BORDER)
        self.line(self.get_x(), self.get_y(), 200, self.get_y())
        self.ln(4)

    def body_text(self, text: str):
        """正文段落"""
        self.set_font(self._cjk_font, "", 10)
        self.set_text_color(*_CLR_TEXT)
        self.multi_cell(0, 6, text)
        self.ln(2)

    def add_table(self, headers: List[str], rows: List[list], col_widths: Optional[List[int]] = None):
        """绘制带样式的表格"""
        if not col_widths:
            available = 190
            col_widths = [available // len(headers)] * len(headers)

        # 表头
        self.set_font(self._cjk_font, "B", 9)
        self.set_fill_color(*_CLR_HEADER)
        self.set_text_color(*_CLR_WHITE)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, h, border=1, align="C", fill=True)
        self.ln()

        # 数据行
        self.set_font(self._cjk_font, "", 9)
        self.set_text_color(*_CLR_TEXT)
        for row_idx, row in enumerate(rows):
            if row_idx % 2 == 0:
                self.set_fill_color(*_CLR_LIGHT_BG)
            else:
                self.set_fill_color(*_CLR_WHITE)
            for i, val in enumerate(row):
                # PnL 颜色
                text_val = str(val)
                try:
                    num = float(val)
                    if "%" in str(val) or (i == len(row) - 1 and isinstance(val, (int, float))):
                        if num > 0:
                            self.set_text_color(*_CLR_GREEN)
                        elif num < 0:
                            self.set_text_color(*_CLR_RED)
                except (ValueError, TypeError):
                    pass
                self.cell(col_widths[i], 7, text_val, border=1, align="C", fill=True)
                self.set_text_color(*_CLR_TEXT)
            self.ln()
        self.ln(4)


# ── 公共 API ─────────────────────────────────────────────────


def generate_daily_report(
    market: dict,
    watchlist: List[dict],
    alerts: List[str],
) -> io.BytesIO:
    """生成每日简报 PDF

    Parameters
    ----------
    market : dict
        市场概要: indices(list[dict]), summary(str) 等
    watchlist : list[dict]
        自选股: symbol, price, change_pct 等
    alerts : list[str]
        今日提醒/告警文本列表

    Returns
    -------
    io.BytesIO
        PDF 字节流

    Raises
    ------
    RuntimeError
        如果 fpdf2 未安装
    """
    if not HAS_FPDF:
        raise RuntimeError("PDF 报告需要安装 fpdf2: pip install fpdf2")

    today = datetime.now().strftime("%Y-%m-%d")
    pdf = _ReportPDF(title=f"ClawBot Daily Report — {today}")
    pdf.add_page()

    # ── 市场概览 ──
    pdf.section_title("Market Overview")

    indices = market.get("indices", [])
    if indices:
        pdf.add_table(
            headers=["Index", "Price", "Change%"],
            rows=[[idx.get("name", ""), f"${idx.get('price', 0):,.2f}", f"{idx.get('change_pct', 0):+.2f}%"] for idx in indices],
            col_widths=[70, 60, 60],
        )

    summary_text = market.get("summary", "")
    if summary_text:
        pdf.body_text(summary_text)

    # ── 自选股 ──
    if watchlist:
        pdf.section_title("Watchlist")
        pdf.add_table(
            headers=["Symbol", "Price", "Change%", "Note"],
            rows=[
                [
                    w.get("symbol", ""),
                    f"${w.get('price', 0):,.2f}" if w.get("price") else "N/A",
                    f"{w.get('change_pct', 0):+.2f}%" if w.get("change_pct") is not None else "N/A",
                    w.get("reason", "")[:30],
                ]
                for w in watchlist
            ],
            col_widths=[40, 45, 45, 60],
        )

    # ── 提醒 ──
    if alerts:
        pdf.section_title("Alerts")
        for alert in alerts:
            pdf.body_text(f"  • {alert}")

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf


def generate_trade_report(
    trades: List[dict],
    summary: Optional[dict] = None,
) -> io.BytesIO:
    """生成交易报告 PDF

    Parameters
    ----------
    trades : list[dict]
        交易记录: symbol, action, quantity, price, total, profit, executed_at
    summary : dict, optional
        汇总: total_trades, buy_count, sell_count, total_profit 等

    Returns
    -------
    io.BytesIO
        PDF 字节流
    """
    if not HAS_FPDF:
        raise RuntimeError("PDF 报告需要安装 fpdf2: pip install fpdf2")

    today = datetime.now().strftime("%Y-%m-%d")
    pdf = _ReportPDF(title=f"Trade Report — {today}")
    pdf.add_page()

    # ── 交易汇总 ──
    if summary:
        pdf.section_title("Summary")
        lines = [
            f"Total Trades: {summary.get('total_trades', 0)}",
            f"Buy: {summary.get('buy_count', 0)}  |  Sell: {summary.get('sell_count', 0)}",
            f"Total Buy Amount: ${summary.get('total_buy_amount', 0):,.2f}",
            f"Total Sell Amount: ${summary.get('total_sell_amount', 0):,.2f}",
            f"Open Positions: {summary.get('open_positions', 0)}",
        ]
        for line in lines:
            pdf.body_text(line)

    # ── 交易明细 ──
    pdf.section_title("Trade Details")

    if trades:
        rows = []
        for t in trades:
            rows.append([
                t.get("executed_at", "")[:10],
                t.get("symbol", ""),
                t.get("action", ""),
                str(t.get("quantity", 0)),
                f"${t.get('price', 0):,.2f}",
                f"${t.get('total', 0):,.2f}",
                f"${t.get('profit', 0):,.2f}" if t.get("profit") else "",
            ])
        pdf.add_table(
            headers=["Date", "Symbol", "Side", "Qty", "Price", "Total", "P&L"],
            rows=rows,
            col_widths=[28, 25, 20, 20, 30, 35, 32],
        )
    else:
        pdf.body_text("No trades recorded.")

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf
