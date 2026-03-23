"""System status endpoints — ping, version, full status"""
from fastapi import APIRouter
from ..rpc import ClawBotRPC
from ..schemas import Ping, SystemStatus

router = APIRouter()


@router.get("/ping", response_model=Ping)
def ping():
    return ClawBotRPC._rpc_ping()


@router.get("/status", response_model=SystemStatus)
def system_status():
    return ClawBotRPC._rpc_system_status()
