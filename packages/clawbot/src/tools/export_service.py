"""
数据导出服务 — 交易记录/自选股/投资组合导出为 Excel/CSV
降级链: openpyxl → csv (标准库)
"""
import csv
import io
import logging
from datetime import datetime
from typing import Any, List, Optional
from src.utils import now_et

logger = logging.getLogger(__name__)

# ── 可选依赖: openpyxl ──────────────────────────────────────
try:
    import openpyxl
    from openpyxl.styles import (
        Alignment, Border, Font, PatternFill, Side, numbers,
    )
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False
    logger.info("openpyxl 未安装，导出将降级为 CSV")

# ── 样式常量 ─────────────────────────────────────────────────
if HAS_OPENPYXL:
    _HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    _HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    _HEADER_ALIGN = Alignment(horizontal="center", vertical="center")
    _THIN_BORDER = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    _GREEN_FONT = Font(color="006100")
    _GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    _RED_FONT = Font(color="9C0006")
    _RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    _NUM_FMT_USD = '#,##0.00'
    _NUM_FMT_PCT = '0.00%'


def _auto_width(ws) -> None:
    """自动调整列宽 (openpyxl)"""
    for col in ws.columns:
        max_len = 0
        col_letter = None
        for cell in col:
            if col_letter is None and hasattr(cell, 'column_letter'):
                col_letter = cell.column_letter
            try:
                cell_len = len(str(cell.value or ""))
                if cell_len > max_len:
                    max_len = cell_len
            except Exception:
                logger.debug("Silenced exception", exc_info=True)
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 10), 40)


def _style_header(ws, headers: List[str]) -> None:
    """统一表头样式"""
    ws.append(headers)
    for cell in ws[ws.max_row]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGN
        cell.border = _THIN_BORDER


def _style_pnl_cell(cell, value: float) -> None:
    """PnL 单元格颜色编码: 正值绿色，负值红色"""
    cell.border = _THIN_BORDER
    if value > 0:
        cell.font = _GREEN_FONT
        cell.fill = _GREEN_FILL
    elif value < 0:
        cell.font = _RED_FONT
        cell.fill = _RED_FILL


def _write_csv(headers: List[str], rows: List[List[Any]]) -> io.BytesIO:
    """CSV 降级输出"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    result = io.BytesIO(buf.getvalue().encode("utf-8-sig"))  # BOM for Excel
    result.seek(0)
    return result


# ── 公共 API ─────────────────────────────────────────────────


def export_trades(trades: List[dict], format: str = "xlsx") -> io.BytesIO:
    """导出交易记录

    Parameters
    ----------
    trades : list[dict]
        每条交易包含: symbol, action, quantity, price, total, executed_at, profit(可选)
    format : str
        "xlsx" (默认) 或 "csv"

    Returns
    -------
    io.BytesIO
        可直接发送给 Telegram 的文件字节流
    """
    headers = ["日期", "代码", "方向", "数量", "价格", "总额", "盈亏"]

    rows = []
    for t in trades:
        row = [
            t.get("executed_at", "")[:19],
            t.get("symbol", ""),
            t.get("action", ""),
            t.get("quantity", 0),
            t.get("price", 0),
            t.get("total", 0),
            t.get("profit", 0),
        ]
        rows.append(row)

    if format == "csv" or not HAS_OPENPYXL:
        return _write_csv(headers, rows)

    # Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "交易记录"

    # 标题行
    ws.append([f"交易记录导出 — {now_et().strftime('%Y-%m-%d %H:%M')}"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws[1][0].font = Font(name="Arial", bold=True, size=14)
    ws.append([])  # 空行

    _style_header(ws, headers)

    for row in rows:
        ws.append(row)
        row_idx = ws.max_row
        # 价格/总额格式
        ws.cell(row=row_idx, column=5).number_format = _NUM_FMT_USD
        ws.cell(row=row_idx, column=6).number_format = _NUM_FMT_USD
        # 盈亏颜色
        pnl_cell = ws.cell(row=row_idx, column=7)
        pnl_cell.number_format = _NUM_FMT_USD
        _style_pnl_cell(pnl_cell, row[6] or 0)
        # 方向颜色
        action_cell = ws.cell(row=row_idx, column=3)
        if row[2] == "BUY":
            action_cell.font = Font(color="006100", bold=True)
        elif row[2] == "SELL":
            action_cell.font = Font(color="9C0006", bold=True)
        # 通用边框
        for col_idx in range(1, len(headers) + 1):
            ws.cell(row=row_idx, column=col_idx).border = _THIN_BORDER

    _auto_width(ws)
    ws.freeze_panes = "A4"  # 冻结标题行

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def export_watchlist(items: List[dict], format: str = "xlsx") -> io.BytesIO:
    """导出自选股列表

    Parameters
    ----------
    items : list[dict]
        每项包含: symbol, reason(可选), added_by(可选), added_at(可选)
    """
    headers = ["代码", "添加原因", "添加人", "添加时间"]

    rows = []
    for item in items:
        rows.append([
            item.get("symbol", ""),
            item.get("reason", ""),
            item.get("added_by", ""),
            item.get("added_at", "")[:19] if item.get("added_at") else "",
        ])

    if format == "csv" or not HAS_OPENPYXL:
        return _write_csv(headers, rows)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "自选股"

    ws.append([f"自选股列表 — {now_et().strftime('%Y-%m-%d %H:%M')}"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws[1][0].font = Font(name="Arial", bold=True, size=14)
    ws.append([])

    _style_header(ws, headers)

    for row in rows:
        ws.append(row)
        for col_idx in range(1, len(headers) + 1):
            ws.cell(row=ws.max_row, column=col_idx).border = _THIN_BORDER

    _auto_width(ws)
    ws.freeze_panes = "A4"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def export_portfolio(
    positions: List[dict],
    summary: Optional[dict] = None,
    format: str = "xlsx",
) -> io.BytesIO:
    """导出投资组合

    Parameters
    ----------
    positions : list[dict]
        每个持仓: symbol, quantity, avg_cost, market_value, pnl_pct
    summary : dict, optional
        现金 / 总资产等汇总信息
    """
    headers = ["代码", "持仓数量", "平均成本", "市值", "盈亏%"]

    rows = []
    for p in positions:
        rows.append([
            p.get("symbol", ""),
            p.get("quantity", 0),
            p.get("avg_cost", 0),
            p.get("market_value", 0),
            p.get("pnl_pct", 0),
        ])

    if format == "csv" or not HAS_OPENPYXL:
        # 在 CSV 末尾追加汇总
        if summary:
            rows.append([])
            rows.append(["现金", summary.get("cash", 0)])
            rows.append(["总资产", summary.get("total_value", 0)])
        return _write_csv(headers, rows)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "投资组合"

    ws.append([f"投资组合 — {now_et().strftime('%Y-%m-%d %H:%M')}"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws[1][0].font = Font(name="Arial", bold=True, size=14)
    ws.append([])

    _style_header(ws, headers)

    for row in rows:
        ws.append(row)
        row_idx = ws.max_row
        ws.cell(row=row_idx, column=3).number_format = _NUM_FMT_USD
        ws.cell(row=row_idx, column=4).number_format = _NUM_FMT_USD
        # 盈亏百分比颜色
        pnl_cell = ws.cell(row=row_idx, column=5)
        pnl_cell.number_format = '0.00"%"'
        _style_pnl_cell(pnl_cell, row[4] or 0)
        for col_idx in range(1, len(headers) + 1):
            ws.cell(row=row_idx, column=col_idx).border = _THIN_BORDER

    # 汇总区域
    if summary:
        ws.append([])
        summary_start = ws.max_row + 1
        ws.append(["现金", "", "", summary.get("cash", 0)])
        ws.cell(row=ws.max_row, column=4).number_format = _NUM_FMT_USD
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        ws.append(["总资产", "", "", summary.get("total_value", 0)])
        ws.cell(row=ws.max_row, column=4).number_format = _NUM_FMT_USD
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)

    _auto_width(ws)
    ws.freeze_panes = "A4"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
