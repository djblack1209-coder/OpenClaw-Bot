"""Memory endpoints — search, stats"""
import logging

from fastapi import APIRouter, Body, HTTPException, Query
from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC
from ..schemas import MemorySearchResult, MemoryStats, WSMessageType
from .ws import push_event

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/memory/search", response_model=MemorySearchResult)
def search_memory(
    query: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(10, ge=1, le=100),
    mode: str = Query("hybrid", pattern="^(keyword|semantic|hybrid)$"),
    category: str | None = None,
):
    """搜索记忆库"""
    effective_query = query if query is not None else q
    if effective_query is None:
        raise HTTPException(status_code=422, detail="缺少 query 参数")
    try:
        return ClawBotRPC._rpc_memory_search(
            query=effective_query, limit=limit, mode=mode, category=category,
        )
    except Exception as e:
        logger.exception("记忆搜索失败 (query=%s)", effective_query)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.get("/memory/stats", response_model=MemoryStats)
def get_memory_stats():
    """获取记忆库统计信息"""
    try:
        return ClawBotRPC._rpc_memory_stats()
    except Exception as e:
        logger.exception("获取记忆库统计失败")
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/memory/delete")
def delete_memory(key: str = Body(..., embed=True)):
    """删除指定记忆条目"""
    try:
        result = ClawBotRPC._rpc_memory_delete(key)
        if result.get("success"):
            # Push memory updated event via WebSocket (best-effort)
            try:
                push_event(WSMessageType.MEMORY_UPDATED, {
                    "action": "delete",
                    "key": key,
                })
            except Exception as e:
                logger.warning("[Memory] 记忆删除事件WS推送失败: %s", e)
            return result
        raise HTTPException(status_code=404, detail=result.get("error", f"未找到: {key}"))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("删除记忆失败 (key=%s)", key)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e


@router.post("/memory/update")
def update_memory(
    key: str = Body(..., embed=True),
    value: str = Body(..., embed=True),
):
    """更新指定记忆条目"""
    try:
        result = ClawBotRPC._rpc_memory_update(key, value)
        if result.get("success"):
            # Push memory updated event via WebSocket (best-effort)
            try:
                push_event(WSMessageType.MEMORY_UPDATED, {
                    "action": "update",
                    "key": key,
                })
            except Exception as e:
                logger.warning("[Memory] 记忆更新事件WS推送失败: %s", e)
            return result
        raise HTTPException(status_code=404, detail=result.get("error", f"未找到: {key}"))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("更新记忆失败 (key=%s)", key)
        raise HTTPException(status_code=500, detail=_safe_error(e)) from e
