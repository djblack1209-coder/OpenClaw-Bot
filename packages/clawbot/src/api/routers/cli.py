"""CLI-Anything API 端点 — 桌面软件远程控制

提供 REST API 让 Tauri 桌面端和其他客户端管理 CLI-Anything 工具:
- GET  /api/v1/cli/tools    — 列出已安装工具
- POST /api/v1/cli/run      — 执行工具命令
- POST /api/v1/cli/install  — 安装新工具
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.integrations.cli_anything_bridge import CLIAnythingManager

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 请求/响应模型 ──────────────────────────────────────────


class CLIRunRequest(BaseModel):
    """执行 CLI 命令的请求体"""
    tool: str = Field(..., description="工具名称", min_length=1, max_length=64)
    args: List[str] = Field(default_factory=list, description="命令参数列表")
    timeout: int = Field(default=30, ge=1, le=300, description="超时秒数")


class CLIRunResponse(BaseModel):
    """执行 CLI 命令的响应体"""
    success: bool
    output: str
    exit_code: int
    duration_ms: int


class CLIInstallRequest(BaseModel):
    """安装 CLI 工具的请求体"""
    tool: str = Field(..., description="要安装的工具名称", min_length=1, max_length=64)


class CLIInstallResponse(BaseModel):
    """安装 CLI 工具的响应体"""
    success: bool
    message: str


class CLIToolInfo(BaseModel):
    """单个 CLI 工具信息"""
    name: str
    path: str
    description: str


# ── 端点 ──────────────────────────────────────────────────


@router.get("/cli/tools", response_model=List[CLIToolInfo])
def list_cli_tools():
    """列出所有已安装的 CLI-Anything 工具"""
    try:
        mgr = CLIAnythingManager.get_instance()
        tools = mgr.discover()
        return [CLIToolInfo(**t) for t in tools]
    except Exception as e:
        logger.exception("列出 CLI 工具失败")
        raise HTTPException(status_code=500, detail="获取工具列表失败")


@router.post("/cli/run", response_model=CLIRunResponse)
async def run_cli_command(req: CLIRunRequest):
    """执行一个 CLI-Anything 工具命令

    安全: 工具名会被验证，只能执行已安装的工具。
    """
    try:
        mgr = CLIAnythingManager.get_instance()
        result = await mgr.run(
            tool_name=req.tool,
            args=req.args,
            timeout=req.timeout,
        )
        return CLIRunResponse(**result)
    except Exception as e:
        logger.exception("执行 CLI 命令失败: tool=%s", req.tool)
        raise HTTPException(status_code=500, detail="命令执行失败")


@router.post("/cli/install", response_model=CLIInstallResponse)
async def install_cli_tool(req: CLIInstallRequest):
    """安装一个 CLI-Anything 工具

    通过 pip install cli-anything-<tool> 安装。
    """
    try:
        mgr = CLIAnythingManager.get_instance()
        result = await mgr.install(req.tool)
        return CLIInstallResponse(**result)
    except Exception as e:
        logger.exception("安装 CLI 工具失败: tool=%s", req.tool)
        raise HTTPException(status_code=500, detail="安装失败")
