"""Shopping endpoints — price comparison across platforms"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/shopping/compare", response_model=Dict[str, Any])
async def compare_prices(
    query: str = Query(..., description="商品搜索关键词，例如 'iPhone 16 128GB'"),
    limit: int = Query(5, ge=1, le=20, description="每个平台的最大结果数"),
    ai_summary: bool = Query(True, description="是否包含 AI 购买建议"),
):
    """跨平台比价（什么值得买 + 京东）。

    搬运什么值得买的比价逻辑 + AI 分析总结。
    无需登录 — 仅使用公开搜索页面。
    """
    try:
        return await ClawBotRPC._rpc_compare_prices(
            query=query,
            limit_per_platform=limit,
            use_ai_summary=ai_summary,
        )
    except Exception as e:
        logger.exception("跨平台比价失败 (query=%s)", query)
        return {"error": _safe_error(e)}
