"""System status endpoints — ping, version, full status"""

import logging

from fastapi import APIRouter, HTTPException
from ..error_utils import safe_error as _safe_error
from ..rpc import ClawBotRPC
from ..schemas import Ping, SystemStatus

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/ping", response_model=Ping)
def ping():
    """系统存活检测"""
    try:
        return ClawBotRPC._rpc_ping()
    except Exception as e:
        logger.exception("Ping 失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/status", response_model=SystemStatus)
def system_status():
    """获取完整系统状态"""
    try:
        return ClawBotRPC._rpc_system_status()
    except Exception as e:
        logger.exception("获取系统状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))
