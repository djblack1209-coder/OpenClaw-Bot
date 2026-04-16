"""Trading endpoints — positions, PnL, signals, team vote, system status, K线数据"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC
from ..schemas import (
    TradingPositions,
    PnLSummary,
    TeamVoteRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()


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


@router.get("/trading/signals", response_model=Dict[str, Any])
def get_signals():
    """获取交易信号"""
    try:
        # RPC 返回 list，需要包裹为 dict 以匹配 response_model
        signals = ClawBotRPC._rpc_trading_signals()
        return {"signals": signals if isinstance(signals, list) else []}
    except Exception as e:
        logger.exception("获取交易信号失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/trading/system", response_model=Dict[str, Any])
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
    except Exception as e:
        logger.exception("获取交易仪表盘数据失败")
        return {"chart_data": [], "assets": [], "connected": False}


@router.post("/trading/vote", response_model=Dict[str, Any])
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
        import yfinance as yf
        import asyncio

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
