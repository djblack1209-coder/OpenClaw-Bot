"""Shopping endpoints — price comparison across platforms"""
import logging
from fastapi import APIRouter, Query
from ..rpc import ClawBotRPC

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/shopping/compare")
async def compare_prices(
    query: str = Query(..., description="Product search keyword, e.g. 'iPhone 16 128GB'"),
    limit: int = Query(5, ge=1, le=20, description="Max results per platform"),
    ai_summary: bool = Query(True, description="Include AI-powered buying advice"),
):
    """Compare prices across multiple platforms (SMZDM + JD).

    搬运 什么值得买 的比价逻辑 + AI 分析总结。
    No login required — uses only public search pages.
    """
    return await ClawBotRPC._rpc_compare_prices(
        query=query,
        limit_per_platform=limit,
        use_ai_summary=ai_summary,
    )
