"""
WorldMonitor API 路由 — 全球情报监控端点

搬运自 worldmonitor (koala73/worldmonitor)
端点:
  GET /api/monitor/news        — 新闻聚合
  GET /api/monitor/risk        — 国家风险指数
  GET /api/monitor/risk/global — 全球综合风险
  GET /api/monitor/finance     — 金融雷达（全部）
  GET /api/monitor/finance/crypto     — 加密货币
  GET /api/monitor/finance/indices    — 股指
  GET /api/monitor/finance/commodities — 大宗商品
  GET /api/monitor/finance/forex      — 外汇
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitor", tags=["WorldMonitor 全球情报"])


# ============================================================
# 新闻聚合
# ============================================================

@router.get("/news")
async def get_news(
    category: Optional[str] = Query(None, description="新闻分类过滤，如 finance/technology/geopolitics"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
):
    """获取 AI 聚合新闻列表"""
    from ..monitoring.world_monitor import get_news_fetcher, NewsCategory

    fetcher = get_news_fetcher()

    # 解析分类过滤
    categories = None
    if category:
        try:
            categories = [NewsCategory(category)]
        except ValueError:
            pass

    items = await fetcher.fetch_all(categories=categories)

    return {
        "success": True,
        "count": min(len(items), limit),
        "items": [
            {
                "title": item.title,
                "url": item.url,
                "source": item.source,
                "category": item.category.value,
                "published_at": item.published_at.isoformat(),
                "summary": item.summary,
                "threat_level": item.threat_level,
            }
            for item in items[:limit]
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# 国家风险指数
# ============================================================

@router.get("/risk")
async def get_risk_scores(
    country: Optional[str] = Query(None, description="ISO 国家代码过滤，如 US/CN/RU"),
):
    """获取国家风险指数评分"""
    from ..monitoring.world_monitor import get_risk_scorer

    scorer = get_risk_scorer()
    risks = scorer.compute_all()

    if country:
        risks = [r for r in risks if r.country_code == country.upper()]

    return {
        "success": True,
        "count": len(risks),
        "risks": [
            {
                "country_code": r.country_code,
                "country_name": r.country_name,
                "composite_score": r.composite_score,
                "severity": r.severity.value,
                "sub_scores": {
                    "unrest": r.unrest_score,
                    "conflict": r.conflict_score,
                    "economic": r.economic_score,
                    "cyber": r.cyber_score,
                    "climate": r.climate_score,
                },
                "change_24h": r.change_24h,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in risks
        ],
    }


@router.get("/risk/global")
async def get_global_risk():
    """获取全球综合风险评分"""
    from ..monitoring.world_monitor import get_risk_scorer

    scorer = get_risk_scorer()
    return {
        "success": True,
        **scorer.get_global_risk(),
    }


# ============================================================
# 金融雷达
# ============================================================

@router.get("/finance")
async def get_finance_all():
    """获取全部金融市场数据"""
    from ..monitoring.world_monitor import get_finance_radar

    radar = get_finance_radar()
    data = await radar.get_all()

    return {
        "success": True,
        **data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/finance/indices")
async def get_indices():
    """获取主要股指报价"""
    from ..monitoring.world_monitor import get_finance_radar

    radar = get_finance_radar()
    quotes = await radar.get_indices()

    return {
        "success": True,
        "count": len(quotes),
        "quotes": [radar._quote_to_dict(q) for q in quotes],
    }


@router.get("/finance/crypto")
async def get_crypto():
    """获取加密货币报价"""
    from ..monitoring.world_monitor import get_finance_radar

    radar = get_finance_radar()
    quotes = await radar.get_crypto()

    return {
        "success": True,
        "count": len(quotes),
        "quotes": [radar._quote_to_dict(q) for q in quotes],
    }


@router.get("/finance/commodities")
async def get_commodities():
    """获取大宗商品报价"""
    from ..monitoring.world_monitor import get_finance_radar

    radar = get_finance_radar()
    quotes = await radar.get_commodities()

    return {
        "success": True,
        "count": len(quotes),
        "quotes": [radar._quote_to_dict(q) for q in quotes],
    }


@router.get("/finance/forex")
async def get_forex():
    """获取外汇报价"""
    from ..monitoring.world_monitor import get_finance_radar

    radar = get_finance_radar()
    quotes = await radar.get_forex()

    return {
        "success": True,
        "count": len(quotes),
        "quotes": [radar._quote_to_dict(q) for q in quotes],
    }
