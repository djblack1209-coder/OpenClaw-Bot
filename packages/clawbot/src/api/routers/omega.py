"""
OMEGA API Router — Brain状态 / 成本控制 / 安全 / 事件总线
挂载到 /api/v1/omega/*
"""

import logging
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query

from ..error_utils import safe_error as _safe_error

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/omega")


@router.get("/status", response_model=Dict[str, Any])
async def omega_status():
    """OMEGA 系统状态"""
    result = {"omega": True}

    try:
        from src.core.brain import get_brain

        brain = get_brain()
        result["brain"] = {
            "active_tasks": len(brain._active_tasks),
            "pending_callbacks": len(brain._pending_callbacks),
        }
    except Exception as e:
        logger.exception("获取 Brain 状态失败")
        result["brain"] = {"error": _safe_error(e)}

    try:
        from src.core.event_bus import get_event_bus

        bus = get_event_bus()
        result["event_bus"] = bus.get_stats()
    except Exception as e:
        logger.exception("获取 EventBus 状态失败")
        result["event_bus"] = {"error": _safe_error(e)}

    try:
        from src.core.cost_control import get_cost_controller

        cc = get_cost_controller()
        result["cost"] = cc.get_stats()
    except Exception as e:
        logger.exception("获取成本控制状态失败")
        result["cost"] = {"error": _safe_error(e)}

    try:
        from src.core.security import get_security_gate

        gate = get_security_gate()
        result["security"] = gate.get_stats()
    except Exception as e:
        logger.exception("获取安全网关状态失败")
        result["security"] = {"error": _safe_error(e)}

    try:
        from src.core.self_heal import get_self_heal_engine

        engine = get_self_heal_engine()
        result["self_heal"] = engine.get_stats()
    except Exception as e:
        logger.exception("获取自愈引擎状态失败")
        result["self_heal"] = {"error": _safe_error(e)}

    try:
        from src.core.executor import get_executor

        executor = get_executor()
        result["executor"] = executor.get_stats()
    except Exception as e:
        logger.exception("获取执行器状态失败")
        result["executor"] = {"error": _safe_error(e)}

    return result


@router.get("/cost", response_model=Dict[str, Any])
async def omega_cost():
    """成本详情"""
    try:
        from src.core.cost_control import get_cost_controller

        cc = get_cost_controller()
        return cc.get_weekly_report()
    except Exception as e:
        logger.exception("获取成本周报失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/events", response_model=Dict[str, Any])
async def omega_events(event_type: str = "", limit: int = Query(default=50, ge=1, le=500)):
    """事件历史"""
    try:
        from src.core.event_bus import get_event_bus

        bus = get_event_bus()
        return {"events": bus.get_recent_events(event_type, limit)}
    except Exception as e:
        logger.exception("获取事件历史失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/audit", response_model=Dict[str, Any])
async def omega_audit(limit: int = Query(default=50, ge=1, le=500)):
    """审计日志"""
    try:
        from src.core.security import get_security_gate

        gate = get_security_gate()
        return {"operations": gate.get_recent_operations(limit)}
    except Exception as e:
        logger.exception("获取审计日志失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/tasks", response_model=Dict[str, Any])
async def omega_tasks():
    """活跃任务"""
    try:
        from src.core.brain import get_brain

        brain = get_brain()
        return {"tasks": brain.get_active_tasks()}
    except Exception as e:
        logger.exception("获取活跃任务失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/process", response_model=Dict[str, Any])
async def omega_process(message: str = Query(max_length=1000), source: str = "api"):
    """通过 API 发送消息给 Brain"""
    try:
        from src.core.brain import get_brain

        brain = get_brain()
        result = await brain.process_message(source=source, message=message)
        return result.to_dict()
    except Exception as e:
        logger.exception("Brain API 消息处理失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/investment/team", response_model=Dict[str, Any])
async def omega_investment_team():
    """投资团队状态"""
    try:
        from src.modules.investment.team import get_investment_team

        team = get_investment_team()
        return {
            "initialized": team._initialized,
            "strategy_health": team._strategy_monitor.get_status(),
            "portfolio": team.get_portfolio_status(),
        }
    except Exception as e:
        logger.exception("获取投资团队状态失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/investment/analyze", response_model=Dict[str, Any])
async def omega_investment_analyze(symbol: str, market: str = "cn"):
    """触发投资分析（优先 Pydantic AI 引擎）"""
    # 优先: Pydantic AI 结构化分析
    try:
        from src.modules.investment.pydantic_agents import get_pydantic_engine

        engine = get_pydantic_engine()
        if engine.available:
            result = await engine.full_analysis(symbol)
            return result.to_dict()
    except Exception as e:
        # Pydantic AI 引擎不可用，降级到原有团队
        logger.exception("Pydantic AI 投资分析引擎调用失败，降级到原有团队")
    # 降级: 原有团队
    try:
        from src.modules.investment.team import get_investment_team

        team = get_investment_team()
        analysis = await team.analyze(symbol, market)
        return analysis.to_dict()
    except Exception as e:
        logger.exception("投资分析失败 (symbol=%s, market=%s)", symbol, market)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/investment/backtest", response_model=Dict[str, Any])
async def omega_investment_backtest(
    symbol: str,
    strategy: str = "ma_cross",
    period: str = "2y",
    fast: int = 10,
    slow: int = 30,
    rsi_window: int = 14,
    oversold: int = 30,
    overbought: int = 70,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_window: int = 20,
    bb_std: float = 2.0,
    optimize: bool = False,
):
    """
    策略回测 (v2.0 — VectorBT 增强版)

    strategy: ma_cross | rsi | macd | bbands | volume | compare
    optimize: 仅对 ma_cross 有效，启用 Optuna 超参数优化
    """
    try:
        from src.modules.investment.backtester_vbt import get_backtester

        bt = get_backtester()
        if not bt.available:
            raise HTTPException(status_code=503, detail="vectorbt 未安装 (pip install vectorbt[full])")

        if strategy == "ma_cross":
            if optimize:
                result = await bt.run_ma_cross_optimized(symbol, period=period)
            else:
                result = await bt.run_ma_cross(symbol, fast=fast, slow=slow, period=period)
        elif strategy == "rsi":
            result = await bt.run_rsi_strategy(
                symbol, period=period, rsi_window=rsi_window, oversold=oversold, overbought=overbought
            )
        elif strategy == "macd":
            result = await bt.run_macd_strategy(
                symbol, period=period, fast=macd_fast, slow=macd_slow, signal=macd_signal
            )
        elif strategy == "bbands":
            result = await bt.run_bbands_strategy(symbol, period=period, window=bb_window, std=bb_std)
        elif strategy == "volume":
            result = await bt.run_volume_strategy(symbol, period=period)
        elif strategy == "compare":
            cmp = await bt.run_multi_strategy_comparison(symbol, period=period)
            return cmp.to_dict()
        else:
            raise HTTPException(
                status_code=400, detail=f"未知策略: {strategy}. 支持: ma_cross|rsi|macd|bbands|volume|compare"
            )

        return result.to_dict()
    except Exception as e:
        logger.exception("策略回测失败 (symbol=%s, strategy=%s)", symbol, strategy)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/tools/jina-read", response_model=Dict[str, Any])
async def omega_jina_read(url: str = Query(max_length=2048, description="要读取的URL")):
    """读取URL内容（Jina Reader）"""
    # SSRF 防护: 校验 URL 协议 + 解析域名 IP 后再次校验（防 DNS 重绑定）
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only HTTP(S) URLs allowed")
    if parsed.hostname:
        import ipaddress
        import socket

        # 第一层: 静态黑名单（已知内网/云元数据地址）
        if parsed.hostname in {
            "169.254.169.254",
            "metadata.google.internal",
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "::1",
        }:
            raise HTTPException(status_code=400, detail="Access to internal networks is not allowed")
        # 第二层: 直接 IP 检查
        try:
            ip = ipaddress.ip_address(parsed.hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise HTTPException(status_code=400, detail="Access to internal networks is not allowed")
        except ValueError:
            # 域名而非 IP — 做 DNS 解析后检查实际 IP（防 DNS 重绑定攻击）
            try:
                resolved_ips = socket.getaddrinfo(parsed.hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for family, _type, _proto, _canonname, sockaddr in resolved_ips:
                    resolved_ip = ipaddress.ip_address(sockaddr[0])
                    if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local:
                        logger.warning("[SSRF] 域名 %s 解析到内网 IP %s，已拦截", parsed.hostname, resolved_ip)
                        raise HTTPException(status_code=400, detail="Access to internal networks is not allowed")
            except socket.gaierror:
                raise HTTPException(status_code=400, detail=f"无法解析域名: {parsed.hostname}")
    try:
        from src.tools.jina_reader import jina_read

        content = await jina_read(url)
        return {"url": url, "content": content or "无法获取内容"}
    except Exception as e:
        logger.exception("Jina Reader 读取URL失败: %s", url)
        raise HTTPException(status_code=502, detail=_safe_error(e))


@router.get("/tools/jina-search", response_model=Dict[str, Any])
async def omega_jina_search(query: str = Query(max_length=500, description="搜索关键词")):
    """Web搜索（Jina Search）"""
    try:
        from src.tools.jina_reader import jina_search

        content = await jina_search(query)
        return {"query": query, "results": content or "无搜索结果"}
    except Exception as e:
        logger.exception("Jina Search 搜索失败: %s", query)
        raise HTTPException(status_code=502, detail=_safe_error(e))


@router.post("/tools/generate-image", response_model=Dict[str, Any])
async def omega_generate_image(
    prompt: str = Query(max_length=1000, description="图像描述"), model: str = "fal-ai/flux/schnell"
):
    """AI 图像生成 (fal.ai)"""
    try:
        from src.tools.fal_client import generate_image

        url = await generate_image(prompt, model=model)
        return {"prompt": prompt, "image_url": url, "model": model}
    except Exception as e:
        logger.exception("AI 图像生成失败")
        raise HTTPException(status_code=502, detail=_safe_error(e))


@router.post("/tools/generate-video", response_model=Dict[str, Any])
async def omega_generate_video(
    prompt: str = Query(max_length=1000, description="视频描述"),
    model: str = "fal-ai/kling-video/v1/standard/text-to-video",
):
    """AI 视频生成 (fal.ai)"""
    try:
        from src.tools.fal_client import generate_video

        url = await generate_video(prompt, model=model)
        return {"prompt": prompt, "video_url": url, "model": model}
    except Exception as e:
        logger.exception("AI 视频生成失败")
        raise HTTPException(status_code=502, detail=_safe_error(e))


@router.get("/tools/media-models", response_model=Dict[str, Any])
async def omega_media_models():
    """可用的图像/视频模型列表"""
    try:
        from src.tools.fal_client import get_available_models

        return {"models": get_available_models()}
    except Exception as e:
        logger.exception("获取媒体模型列表失败")
        raise HTTPException(status_code=500, detail=_safe_error(e))
