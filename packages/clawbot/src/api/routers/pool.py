"""API Pool endpoints — statistics"""

import logging

from fastapi import APIRouter, HTTPException
from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC
from ..schemas import PoolStats

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/pool/stats", response_model=PoolStats)
def get_pool_stats():
    """获取 API 池统计信息"""
    try:
        return ClawBotRPC._rpc_pool_stats()
    except Exception as e:
        logger.exception("获取 API 池统计失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))
