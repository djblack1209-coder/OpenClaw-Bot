"""Memory endpoints — search, stats"""
from fastapi import APIRouter, Query
from ..rpc import ClawBotRPC
from ..schemas import MemorySearchResult, MemoryStats

router = APIRouter()


@router.get("/memory/search", response_model=MemorySearchResult)
def search_memory(
    query: str,
    limit: int = Query(10, ge=1, le=100),
    mode: str = Query("hybrid", pattern="^(keyword|semantic|hybrid)$"),
    category: str = None,
):
    return ClawBotRPC._rpc_memory_search(
        query=query, limit=limit, mode=mode, category=category,
    )


@router.get("/memory/stats", response_model=MemoryStats)
def get_memory_stats():
    return ClawBotRPC._rpc_memory_stats()
