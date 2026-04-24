"""Trading endpoints — positions, PnL, signals, team vote, system status, K线数据, 卖出, 自选股"""

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path as FilePath
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC
from ..schemas import (
    PnLSummary,
    TeamVoteRequest,
    TradingPositions,
    WSMessageType,
)
from .ws import push_event

logger = logging.getLogger(__name__)
router = APIRouter()


class SellRequest(BaseModel):
    """卖出请求体 — 替代手动 request.json() 解析，自动校验类型"""
    symbol: str = Field(..., min_length=1, max_length=10, description="股票代码")
    quantity: float = Field(..., gt=0, description="卖出数量")
    order_type: str = Field(default="MKT", max_length=10, description="订单类型")


class WatchlistAddRequest(BaseModel):
    """添加自选股请求体"""
    symbol: str = Field(..., min_length=1, max_length=10, description="股票代码")
    target_price: float = Field(..., gt=0, description="目标价格")
    direction: str = Field(default="above", pattern=r"^(above|below)$", description="方向")


@router.get("/trading/positions", response_model=TradingPositions)
async def get_positions():
    """获取当前交易持仓"""
    try:
        return await ClawBotRPC._rpc_trading_positions()
    except Exception as e:
        logger.exception("获取交易持仓失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/trading/pnl", response_model=PnLSummary)
async def get_pnl():
    """获取盈亏摘要"""
    try:
        return await ClawBotRPC._rpc_trading_pnl()
    except Exception as e:
        logger.exception("获取盈亏摘要失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/trading/signals", response_model=dict[str, Any])
def get_signals():
    """获取交易信号"""
    try:
        # RPC 返回 list，需要包裹为 dict 以匹配 response_model
        signals = ClawBotRPC._rpc_trading_signals()
        return {"signals": signals if isinstance(signals, list) else []}
    except Exception as e:
        logger.exception("获取交易信号失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/trading/system", response_model=dict[str, Any])
def get_trading_system():
    """获取交易系统状态"""
    try:
        result = ClawBotRPC._rpc_trading_system_status()
        # 确保返回 dict 类型，防止序列化失败导致 500
        return result if isinstance(result, dict) else {"status": "unknown"}
    except Exception as e:
        logger.exception("获取交易系统状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/trading/dashboard")
async def trading_dashboard():
    """盈利总控仪表盘：返回图表数据和资产列表"""
    try:
        result = await ClawBotRPC._rpc_trading_dashboard()
        if isinstance(result, dict):
            return result
        return {"chart_data": [], "assets": [], "connected": False}
    except Exception:
        logger.exception("获取交易仪表盘数据失败")
        return {"chart_data": [], "assets": [], "connected": False}


@router.post("/trading/vote", response_model=dict[str, Any])
async def trigger_vote(req: TeamVoteRequest):
    """触发 AI 团队投票

    搬运 freqtrade 的 analysis-before-vote 模式：
    先获取技术分析数据，再提交给团队投票。
    """
    # 第一步：获取技术分析数据（团队投票必须依赖分析结果）
    try:
        from src.ta_engine import get_full_analysis

        analysis = await get_full_analysis(
            symbol=req.symbol,
            period=req.period,
        )
    except Exception as e:
        logger.exception("获取 %s 技术分析失败", req.symbol)
        raise HTTPException(status_code=500, detail=_safe_error(e))

    if not analysis:
        raise HTTPException(status_code=422, detail=f"无法获取 {req.symbol} 的市场数据")

    # 第二步：用分析数据跑 AI 团队投票
    try:
        result = await ClawBotRPC._rpc_trigger_team_vote(
            symbol=req.symbol,
            analysis=analysis,
        )

        # Push trade signal via WebSocket (best-effort)
        try:
            push_event(WSMessageType.TRADE_SIGNAL, {
                "symbol": req.symbol,
                "consensus_signal": result.get("consensus_signal", ""),
                "consensus_score": result.get("consensus_score", 0),
                "passed": result.get("passed", False),
                "vote_count": len(result.get("votes", [])),
            })
        except Exception as e:
            logger.warning("[Trading] 交易信号WS推送失败: %s", e)

        return result
    except Exception as e:
        logger.exception("AI 团队投票失败 (symbol=%s)", req.symbol)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/trading/kline")
async def get_kline_data(
    symbol: str = Query(..., description="标的代码，如 AAPL"),
    interval: str = Query("1d", description="K线周期: 1m/5m/15m/1h/4h/1d/1w"),
    period: str = Query("3mo", description="回看周期: 1mo/3mo/6mo/1y/2y"),
):
    """获取 OHLCV K线数据 — 供前端 lightweight-charts 渲染

    返回格式与 TradingView lightweight-charts 兼容:
    {"symbol": "AAPL", "data": [{"time": unix_ts, "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}]}
    """
    try:
        import asyncio

        import yfinance as yf

        def _fetch():
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                return []
            records = []
            for idx, row in df.iterrows():
                # lightweight-charts 需要 Unix 时间戳（秒）
                ts = int(idx.timestamp())
                records.append(
                    {
                        "time": ts,
                        "open": round(float(row["Open"]), 2),
                        "high": round(float(row["High"]), 2),
                        "low": round(float(row["Low"]), 2),
                        "close": round(float(row["Close"]), 2),
                        "volume": int(row.get("Volume", 0)),
                    }
                )
            return records

        data = await asyncio.to_thread(_fetch)
        return {"symbol": symbol.upper(), "interval": interval, "period": period, "data": data}

    except Exception as e:
        logger.exception("获取K线数据失败 (symbol=%s)", symbol)
        return {"symbol": symbol, "data": [], "error": _safe_error(e)}


@router.get("/trading/portfolio-summary")
async def portfolio_summary():
    """持仓摘要 — 为首页和资产页提供聚合数据

    返回:
    - total_value: 总资产价值 (USD)
    - total_pnl: 总盈亏
    - total_pnl_pct: 总盈亏百分比
    - positions: [{symbol, qty, avg_cost, current_price, pnl, pnl_pct, weight}]
    - sector_allocation: [{sector, weight}] 行业分布
    - day_change: 今日涨跌
    - connected: IBKR 连接状态
    """
    try:
        # 获取持仓数据
        positions_data = await ClawBotRPC._rpc_trading_positions()
        pnl_data = await ClawBotRPC._rpc_trading_pnl()
        dashboard_data = await ClawBotRPC._rpc_trading_dashboard()

        positions_list = positions_data.get("positions", [])
        total_value = 0.0
        total_cost = 0.0
        enriched_positions = []

        for pos in positions_list:
            qty = pos.get("quantity", 0)
            avg_cost = pos.get("avg_price", 0)
            current_price = pos.get("current_price", 0)
            market_value = qty * current_price if qty and current_price else 0
            cost_basis = qty * avg_cost if qty and avg_cost else 0
            pnl = market_value - cost_basis
            pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0

            total_value += market_value
            total_cost += cost_basis

            enriched_positions.append(
                {
                    "symbol": pos.get("symbol", ""),
                    "name": pos.get("name", pos.get("symbol", "")),
                    "quantity": qty,
                    "avg_price": round(avg_cost, 2),
                    "current_price": round(current_price, 2),
                    "market_value": round(market_value, 2),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                }
            )

        # 计算各持仓权重
        for ep in enriched_positions:
            ep["weight"] = round(ep["market_value"] / total_value * 100, 1) if total_value else 0

        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

        # PnL 数据中的日盈亏
        day_change = pnl_data.get("today_pnl", 0)
        day_change_pct = pnl_data.get("today_pnl_pct", 0)

        return {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "day_change": round(day_change, 2) if day_change else 0,
            "day_change_pct": round(day_change_pct, 2) if day_change_pct else 0,
            "positions": enriched_positions,
            "position_count": len(enriched_positions),
            "connected": dashboard_data.get("connected", False),
        }

    except Exception as e:
        logger.exception("获取持仓摘要失败")
        # 降级返回空数据而非 500 错误（首页不应因交易系统离线而崩溃）
        return {
            "total_value": 0,
            "total_cost": 0,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "day_change": 0,
            "day_change_pct": 0,
            "positions": [],
            "position_count": 0,
            "connected": False,
            "error": _safe_error(e),
        }


@router.post("/trading/sell")
async def sell_position(req: SellRequest):
    """手动卖出持仓"""
    try:
        symbol = req.symbol.strip().upper()
        quantity = req.quantity
        order_type = req.order_type.upper()

        # Pydantic 已验证 symbol 非空和 quantity > 0

        # 懒加载 broker bridge 获取 IBKRBridge 实例
        from src.broker_selector import ibkr

        if not ibkr or not ibkr.is_connected():
            return {"success": False, "message": "IBKR 未连接"}

        result = await ibkr.sell(
            symbol=symbol,
            quantity=quantity,
            order_type=order_type,
            decided_by="manual_ui",
            reason="用户通过 Portfolio 页面手动卖出",
        )

        if "error" in result:
            return {"success": False, "message": result["error"]}

        # 推送系统通知
        try:
            from .system import push_notification

            push_notification(
                title=f"卖出 {symbol}",
                body=f"已提交卖出 {quantity:.0f} 股 {symbol}（{order_type}），订单号 #{result.get('order_id', 'N/A')}",
                category="trading",
                level="success",
            )
        except Exception as e:
            logger.warning("[Trading] 卖出通知推送失败: %s", e)

        # Push trade executed via WebSocket (best-effort)
        try:
            push_event(WSMessageType.TRADE_EXECUTED, {
                "symbol": symbol,
                "action": "SELL",
                "quantity": quantity,
                "order_type": order_type,
                "order_id": str(result.get("order_id", "")),
                "status": result.get("status", ""),
                "filled_qty": result.get("filled_qty", 0),
                "avg_price": result.get("avg_price", 0),
                "source": "manual_ui",
            })
        except Exception as e:
            logger.warning("[Trading] 卖出执行WS推送失败: %s", e)

        return {
            "success": True,
            "message": "卖出订单已提交",
            "order_id": str(result.get("order_id", "")),
            "status": result.get("status", ""),
            "filled_qty": result.get("filled_qty", 0),
            "avg_price": result.get("avg_price", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("卖出持仓失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


# ══════════════════════════════════════════════
#  自选股监控 (Watchlist)
# ══════════════════════════════════════════════

# 存储路径：项目 data/ 目录下
_WATCHLIST_DIR = FilePath(os.path.dirname(__file__)).resolve().parents[2] / "data"
_WATCHLIST_FILE = _WATCHLIST_DIR / "watchlist.json"


def _load_watchlist() -> list[dict[str, Any]]:
    """从 JSON 文件加载自选股列表"""
    try:
        if _WATCHLIST_FILE.exists():
            return json.loads(_WATCHLIST_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("读取自选股文件失败: %s", e)
    return []


def _save_watchlist(watchlist: list[dict[str, Any]]) -> None:
    """保存自选股列表到 JSON 文件"""
    _WATCHLIST_DIR.mkdir(parents=True, exist_ok=True)
    _WATCHLIST_FILE.write_text(
        json.dumps(watchlist, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@router.get("/trading/watchlist")
def get_watchlist():
    """获取自选股列表"""
    try:
        return _load_watchlist()
    except Exception as e:
        logger.exception("获取自选股列表失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/trading/watchlist")
async def add_to_watchlist(req: WatchlistAddRequest):
    """添加自选股"""
    try:
        symbol = req.symbol.strip().upper()
        target_price = req.target_price
        direction = req.direction

        watchlist = _load_watchlist()

        # 检查是否已存在
        for item in watchlist:
            if item.get("symbol") == symbol:
                raise HTTPException(status_code=409, detail=f"{symbol} 已在自选股列表中")

        watchlist.append({
            "symbol": symbol,
            "target_price": target_price,
            "direction": direction,
            "added_at": datetime.now(UTC).isoformat(),
        })
        _save_watchlist(watchlist)
        return watchlist

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("添加自选股失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.delete("/trading/watchlist/{symbol}")
def remove_from_watchlist(symbol: str = Path(..., description="要删除的标的代码")):
    """删除自选股"""
    try:
        symbol = symbol.strip().upper()
        watchlist = _load_watchlist()
        new_list = [item for item in watchlist if item.get("symbol") != symbol]

        if len(new_list) == len(watchlist):
            raise HTTPException(status_code=404, detail=f"{symbol} 不在自选股列表中")

        _save_watchlist(new_list)
        return new_list

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("删除自选股失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


# ========== 交易日志 ==========

@router.get("/trading/journal")
def get_trade_journal(
    offset: int = Query(default=0, ge=0, description="偏移量"),
    limit: int = Query(default=20, ge=1, le=100, description="每页条数"),
    status: str = Query(default="", description="状态筛选: open/closed/pending，空=全部"),
    symbol: str = Query(default="", description="标的筛选"),
    side: str = Query(default="", description="方向筛选: BUY/SELL"),
):
    """分页获取交易日志"""
    try:
        from src.trading_journal import journal
        result = journal.get_trades_paginated(
            offset=offset,
            limit=limit,
            status=status or None,
            symbol=symbol or None,
            side=side or None,
        )
        return result
    except Exception as e:
        logger.exception("获取交易日志失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


# ========== 估值分析 ==========

@router.get("/trading/valuation")
def get_valuation(
    symbol: str = Query(..., min_length=1, max_length=10, description="股票代码"),
):
    """对指定标的运行 4 大估值模型（DCF/持有人收益/EV-EBITDA/残余收入）"""
    try:
        import yfinance as yf

        from src.trading.valuation_models import (
            calculate_wacc,
            get_valuation_summary,
        )

        symbol = symbol.strip().upper()
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        # 提取财务数据（yfinance 字段名）
        fcf = info.get("freeCashflow") or info.get("operatingCashflow", 0)
        revenue_growth = info.get("revenueGrowth", 0.05) or 0.05
        net_income = info.get("netIncomeToCommon") or info.get("netIncome", 0)
        depreciation = info.get("totalCashFromDepreciationAndAmortization") or abs(info.get("depreciation", 0))
        capex = abs(info.get("capitalExpenditures", 0))
        wc_change = info.get("changeInWorkingCapital", 0)
        ebitda = info.get("ebitda", 0)
        ev = info.get("enterpriseValue", 0)
        bvps = info.get("bookValue", 0)
        roe = info.get("returnOnEquity", 0.1) or 0.1
        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        market_cap = info.get("marketCap", 0)
        total_debt = info.get("totalDebt", 0)
        tax_rate = info.get("effectiveTaxRate", 0.21) or 0.21

        # 计算 WACC
        cost_of_equity = 0.08 + max(0, info.get("beta", 1.0) - 1) * 0.05
        cost_of_debt = 0.04
        wacc = calculate_wacc(
            market_cap=max(market_cap, 1),
            total_debt=max(total_debt, 0),
            tax_rate=tax_rate,
            cost_of_equity=cost_of_equity,
            cost_of_debt=cost_of_debt,
        )

        # 综合估值
        result = get_valuation_summary(
            free_cash_flow=fcf,
            revenue_growth_rate=revenue_growth,
            discount_rate=max(wacc, 0.06),
            net_income=net_income,
            depreciation=depreciation,
            capex=capex,
            working_capital_change=wc_change,
            ebitda=max(ebitda, 1),
            enterprise_value=max(ev, 1),
            book_value_per_share=max(bvps, 0.01),
            roe=roe,
            cost_of_equity=cost_of_equity,
            current_price=max(current_price, 0.01),
        )

        return {
            "symbol": symbol,
            "current_price": current_price,
            "company_name": info.get("longName") or info.get("shortName", symbol),
            "wacc": round(wacc, 4),
            **result,
            "financial_data": {
                "free_cash_flow": fcf,
                "revenue_growth": revenue_growth,
                "net_income": net_income,
                "ebitda": ebitda,
                "enterprise_value": ev,
                "book_value_per_share": bvps,
                "roe": roe,
                "market_cap": market_cap,
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "dividend_yield": info.get("dividendYield"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("估值分析失败: %s", symbol)
        raise HTTPException(status_code=500, detail=_safe_error(e))
