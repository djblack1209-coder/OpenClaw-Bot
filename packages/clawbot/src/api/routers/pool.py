"""API Pool endpoints — statistics"""
from fastapi import APIRouter
from ..rpc import ClawBotRPC
from ..schemas import PoolStats

router = APIRouter()


@router.get("/pool/stats", response_model=PoolStats)
def get_pool_stats():
    return ClawBotRPC._rpc_pool_stats()
