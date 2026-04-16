"""Evolution API endpoints — scan, proposals, capability gaps"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from ..error_utils import safe_error as _safe_error

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evolution")

# 延迟初始化引擎（避免在 import 时就触发网络请求）
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from src.evolution.engine import EvolutionEngine

        _engine = EvolutionEngine()
    return _engine


# ──────────────── Response Models ────────────────


class ProposalOut(BaseModel):
    id: str
    repo_url: str
    repo_name: str
    stars: int
    growth_rate: int
    description: str
    target_module: str
    value_score: float
    difficulty: float
    risk_level: str
    integration_approach: str
    status: str
    created_at: str
    evaluated_by: str
    repo_language: str = ""
    matched_gap: str = ""


class ScanResponse(BaseModel):
    status: str
    message: str
    proposals: list[ProposalOut] = []


class GapOut(BaseModel):
    module: str
    gap: str
    description: str
    keywords: str = ""


class StatsOut(BaseModel):
    total_proposals: int = 0
    total_scans: int = 0
    by_status: dict = {}
    by_module: dict = {}
    capability_gaps: int = 0
    last_scan_time: str = ""
    config: dict = {}


class StatusUpdateRequest(BaseModel):
    status: str  # approved / rejected / integrated


# ──────────────── Endpoints ────────────────


@router.post("/scan", response_model=ScanResponse)
async def trigger_scan(background_tasks: BackgroundTasks):
    """手动触发一次进化扫描（后台运行）。

    扫描会采集 GitHub trending 和快速增长仓库，用 LLM 评估后生成集成提案。
    由于扫描耗时较长，此端点立即返回，扫描在后台执行。
    """
    try:
        engine = _get_engine()
    except Exception as e:
        logger.exception("初始化进化引擎失败")
        return ScanResponse(status="error", message=_safe_error(e))

    # 在后台运行扫描
    async def _run_scan():
        try:
            proposals = await engine.daily_scan()
            logger.info("[evolution-api] 后台扫描完成: %d 个提案", len(proposals))
        except Exception as e:
            logger.error("[evolution-api] 后台扫描失败: %s", e)

    background_tasks.add_task(_run_scan)

    return ScanResponse(
        status="started",
        message="进化扫描已在后台启动，查看 /evolution/proposals 获取结果。",
    )


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(
    status: Optional[str] = Query(None, description="按状态过滤: proposed/approved/integrated/rejected"),
    limit: int = Query(50, ge=1, le=200),
):
    """列出最近的进化提案"""
    try:
        engine = _get_engine()
        proposals = engine.list_proposals(status=status, limit=limit)
        return [
            ProposalOut(
                id=p.id,
                repo_url=p.repo_url,
                repo_name=p.repo_name,
                stars=p.stars,
                growth_rate=p.growth_rate,
                description=p.description,
                target_module=p.target_module,
                value_score=p.value_score,
                difficulty=p.difficulty,
                risk_level=p.risk_level,
                integration_approach=p.integration_approach,
                status=p.status,
                created_at=p.created_at,
                evaluated_by=p.evaluated_by,
                repo_language=p.repo_language,
                matched_gap=p.matched_gap,
            )
            for p in proposals
        ]
    except Exception as e:
        logger.exception("列出进化提案失败")
        return []


@router.patch("/proposals/{proposal_id}")
def update_proposal(proposal_id: str, req: StatusUpdateRequest):
    """更新提案状态 (approve / reject / integrate)"""
    try:
        engine = _get_engine()
        valid = {"proposed", "approved", "rejected", "integrated"}
        if req.status not in valid:
            raise HTTPException(status_code=422, detail=f"无效状态，必须是: {valid}")

        ok = engine.update_proposal_status(proposal_id, req.status)
        if ok:
            return {"status": "ok", "message": f"提案 {proposal_id} 已更新为 '{req.status}'"}
        raise HTTPException(status_code=404, detail=f"提案 {proposal_id} 未找到")
    except Exception as e:
        logger.exception("更新提案状态失败 (proposal_id=%s)", proposal_id)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/gaps", response_model=list[GapOut])
def list_capability_gaps():
    """列出 OpenClaw 已知的能力缺口"""
    try:
        engine = _get_engine()
        gaps = engine.get_capability_gaps()
        return [GapOut(**g) for g in gaps]
    except Exception as e:
        logger.exception("列出能力缺口失败")
        return []


@router.get("/stats", response_model=StatsOut)
def evolution_stats():
    """返回进化引擎统计摘要"""
    try:
        engine = _get_engine()
        stats = engine.get_stats()
        return StatsOut(**stats)
    except Exception as e:
        logger.exception("获取进化引擎统计失败")
        return StatsOut()


@router.get("/history")
def scan_history(limit: int = Query(20, ge=1, le=100)):
    """返回最近的扫描历史"""
    try:
        engine = _get_engine()
        return engine.get_scan_history(limit=limit)
    except Exception as e:
        logger.exception("获取扫描历史失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))
