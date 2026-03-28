"""Memory endpoints — search, stats"""
import logging

from fastapi import APIRouter, Query
from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC
from ..schemas import MemorySearchResult, MemoryStats

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/memory/search", response_model=MemorySearchResult)
def search_memory(
    query: str,
    limit: int = Query(10, ge=1, le=100),
    mode: str = Query("hybrid", pattern="^(keyword|semantic|hybrid)$"),
    category: str = None,
):
    """搜索记忆库"""
    try:
        return ClawBotRPC._rpc_memory_search(
            query=query, limit=limit, mode=mode, category=category,
        )
    except Exception as e:
        logger.exception("记忆搜索失败 (query=%s)", query)
        return {"error": _safe_error(e)}


@router.get("/memory/stats", response_model=MemoryStats)
def get_memory_stats():
    """获取记忆库统计信息"""
    try:
        return ClawBotRPC._rpc_memory_stats()
    except Exception as e:
        logger.exception("获取记忆库统计失败")
        return {"error": _safe_error(e)}
