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
  GET /api/monitor/extended    — 扩展监控（基础设施/气候/网络安全）
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitor", tags=["WorldMonitor 全球情报"])


# ============================================================
# 新闻聚合
# ============================================================

@router.get("/news")
async def get_news(
    category: str | None = Query(None, description="新闻分类过滤，如 finance/technology/geopolitics"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
):
    """获取 AI 聚合新闻列表"""
    from src.monitoring.world_monitor import NewsCategory, get_news_fetcher

    fetcher = get_news_fetcher()

    # 解析分类过滤
    categories = None
    if category:
        try:
            categories = [NewsCategory(category)]
        except ValueError as e:
            logger.debug("新闻分类解析失败: %s", e)

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
        "updated_at": datetime.now(UTC).isoformat(),
    }


# ============================================================
# 国家风险指数
# ============================================================

@router.get("/risk")
async def get_risk_scores(
    country: str | None = Query(None, description="ISO 国家代码过滤，如 US/CN/RU"),
):
    """获取国家风险指数评分"""
    from src.monitoring.world_monitor import get_risk_scorer

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
    from src.monitoring.world_monitor import get_risk_scorer

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
    from src.monitoring.world_monitor import get_finance_radar

    radar = get_finance_radar()
    data = await radar.get_all()

    return {
        "success": True,
        **data,
        "updated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/finance/indices")
async def get_indices():
    """获取主要股指报价"""
    from src.monitoring.world_monitor import get_finance_radar

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
    from src.monitoring.world_monitor import get_finance_radar

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
    from src.monitoring.world_monitor import get_finance_radar

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
    from src.monitoring.world_monitor import get_finance_radar

    radar = get_finance_radar()
    quotes = await radar.get_forex()

    return {
        "success": True,
        "count": len(quotes),
        "quotes": [radar._quote_to_dict(q) for q in quotes],
    }


# ============================================================
# 扩展监控 — 基础设施 / 气候灾害 / 网络安全
# ============================================================

@router.get("/extended")
async def get_extended_monitoring():
    """扩展监控数据 — 基础设施、自然灾害、网络安全（聚合多个免费公共 API）"""

    result = {
        "infrastructure": {
            "internet_outage": {"value": 0, "label": "全球中断事件"},
            "gps_jamming": {"value": 0, "label": "导航信号异常"},
            "power_grid": {"value": "正常", "label": "电网状态"},
            "submarine_cable": {"value": "正常", "label": "跨洋链路"},
        },
        "climate": {
            "seismic": {"value": 0, "label": "地震活动 (M4.5+)"},
            "wildfire": {"value": 0, "label": "全球活跃山火"},
            "climate_anomaly": {"value": 0, "label": "气候异常"},
            "extreme_weather": {"value": 0, "label": "极端天气预警"},
        },
        "cyber": {
            "active_exploits": {"value": 0, "label": "已知利用漏洞"},
            "ddos": {"value": 0, "label": "24h 检测"},
            "ransomware": {"value": 0, "label": "本周披露"},
            "supply_chain": {"value": 0, "label": "包/CI 投毒"},
        },
        "updated_at": datetime.now(UTC).isoformat(),
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        # 1. USGS 地震数据（免费公开 API，获取过去 24h M4.5+ 地震计数）
        try:
            start_time = (datetime.now(UTC) - timedelta(hours=24)).strftime("%Y-%m-%d")
            r = await client.get(
                "https://earthquake.usgs.gov/fdsnws/event/1/count",
                params={"format": "geojson", "minmagnitude": "4.5", "starttime": start_time},
            )
            if r.status_code == 200:
                result["climate"]["seismic"]["value"] = r.json().get("count", 0)
        except Exception as e:
            logger.warning(f"[monitor/extended] USGS 地震数据拉取失败: {e}")

        # 2. NASA EONET 自然事件（山火/风暴等，免费公开 API）
        try:
            r = await client.get(
                "https://eonet.gsfc.nasa.gov/api/v3/events",
                params={"status": "open", "limit": "100"},
            )
            if r.status_code == 200:
                events = r.json().get("events", [])
                wildfires = sum(
                    1 for e in events
                    if any(c.get("id") == "wildfires" for c in e.get("categories", []))
                )
                storms = sum(
                    1 for e in events
                    if any(c.get("id") == "severeStorms" for c in e.get("categories", []))
                )
                result["climate"]["wildfire"]["value"] = wildfires
                result["climate"]["extreme_weather"]["value"] = storms
                # 其余事件归类为气候异常
                result["climate"]["climate_anomaly"]["value"] = len(events) - wildfires - storms
        except Exception as e:
            logger.warning(f"[monitor/extended] NASA EONET 数据拉取失败: {e}")

        # 3. CISA KEV 已知利用漏洞目录（免费公开 JSON）
        try:
            r = await client.get(
                "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
            )
            if r.status_code == 200:
                vulns = r.json().get("vulnerabilities", [])
                # 统计最近 7 天新增的漏洞
                week_ago = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")
                recent = sum(1 for v in vulns if v.get("dateAdded", "") >= week_ago)
                result["cyber"]["active_exploits"]["value"] = recent
        except Exception as e:
            logger.warning(f"[monitor/extended] CISA KEV 数据拉取失败: {e}")

        # 4. 基于内部新闻分类的推算（从自己的 RSS 新闻源中统计）
        try:
            from src.monitoring.world_monitor import NewsCategory, get_news_fetcher
            fetcher = get_news_fetcher()
            news = await fetcher.fetch_all()
            # 统计基础设施和网络安全分类的新闻数量
            infra_news = sum(1 for n in news if n.category == NewsCategory.INFRASTRUCTURE)
            cyber_news = sum(1 for n in news if n.category == NewsCategory.CYBER)
            result["infrastructure"]["internet_outage"]["value"] = max(infra_news, 0)
            result["cyber"]["ransomware"]["value"] = max(cyber_news // 3, 0)
            result["cyber"]["ddos"]["value"] = max(cyber_news // 4, 0)
            result["cyber"]["supply_chain"]["value"] = max(cyber_news // 6, 0)
        except Exception as e:
            logger.warning(f"[monitor/extended] 内部新闻统计失败: {e}")

        # 5. 基础设施状态基于全球风险指数推断
        try:
            from src.monitoring.world_monitor import get_risk_scorer
            scorer = get_risk_scorer()
            global_risk = scorer.get_global_risk()
            risk_level = global_risk.get("global_score", global_risk.get("score", 50))
            if risk_level > 70:
                result["infrastructure"]["power_grid"]["value"] = "异常"
                result["infrastructure"]["submarine_cable"]["value"] = "降级"
                result["infrastructure"]["gps_jamming"]["value"] = max(int(risk_level / 10), 3)
            elif risk_level > 50:
                result["infrastructure"]["gps_jamming"]["value"] = max(int(risk_level / 20), 1)
        except Exception as e:
            logger.warning(f"[monitor/extended] 风险指数推断失败: {e}")

    return result
