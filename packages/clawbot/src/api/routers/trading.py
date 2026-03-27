"""Trading endpoints — positions, PnL, signals, team vote, system status"""
import logging
from typing import Any, Dict

from fastapi import APIRouter
from ..rpc import ClawBotRPC
from ..schemas import (
    TradingPositions, PnLSummary,
    TeamVoteRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/trading/positions", response_model=TradingPositions)
async def get_positions():
    return await ClawBotRPC._rpc_trading_positions()


@router.get("/trading/pnl", response_model=PnLSummary)
async def get_pnl():
    return await ClawBotRPC._rpc_trading_pnl()


@router.get("/trading/signals", response_model=Dict[str, Any])
def get_signals():
    return ClawBotRPC._rpc_trading_signals()


@router.get("/trading/system", response_model=Dict[str, Any])
def get_trading_system():
    return ClawBotRPC._rpc_trading_system_status()


@router.post("/trading/vote", response_model=Dict[str, Any])
async def trigger_vote(req: TeamVoteRequest):
    """Trigger AI team vote for a symbol.
    
    Automatically fetches technical analysis first (搬运 freqtrade 的
    analysis-before-vote 模式), then passes to team voting.
    """
    # Step 1: Fetch technical analysis (required by run_team_vote)
    try:
        from src.ta_engine import get_full_analysis
        analysis = await get_full_analysis(
            symbol=req.symbol, period=req.period,
        )
    except Exception as e:
        logger.error("Failed to get analysis for %s: %s", req.symbol, e)
        return {"error": f"Technical analysis failed: {e}"}

    if not analysis:
        return {"error": f"No market data available for {req.symbol}"}

    # Step 2: Run AI team vote with analysis
    result = await ClawBotRPC._rpc_trigger_team_vote(
        symbol=req.symbol,
        analysis=analysis,
    )
    return result
