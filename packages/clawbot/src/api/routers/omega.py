"""
OMEGA API Router — Brain状态 / 成本控制 / 安全 / 事件总线
挂载到 /api/v1/omega/*
"""
from fastapi import APIRouter

router = APIRouter(prefix="/omega")


@router.get("/status")
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
        result["brain"] = {"error": str(e)}

    try:
        from src.core.event_bus import get_event_bus
        bus = get_event_bus()
        result["event_bus"] = bus.get_stats()
    except Exception as e:
        result["event_bus"] = {"error": str(e)}

    try:
        from src.core.cost_control import get_cost_controller
        cc = get_cost_controller()
        result["cost"] = cc.get_stats()
    except Exception as e:
        result["cost"] = {"error": str(e)}

    try:
        from src.core.security import get_security_gate
        gate = get_security_gate()
        result["security"] = gate.get_stats()
    except Exception as e:
        result["security"] = {"error": str(e)}

    try:
        from src.core.self_heal import get_self_heal_engine
        engine = get_self_heal_engine()
        result["self_heal"] = engine.get_stats()
    except Exception as e:
        result["self_heal"] = {"error": str(e)}

    try:
        from src.core.executor import get_executor
        executor = get_executor()
        result["executor"] = executor.get_stats()
    except Exception as e:
        result["executor"] = {"error": str(e)}

    return result


@router.get("/cost")
async def omega_cost():
    """成本详情"""
    try:
        from src.core.cost_control import get_cost_controller
        cc = get_cost_controller()
        return cc.get_weekly_report()
    except Exception as e:
        return {"error": str(e)}


@router.get("/events")
async def omega_events(event_type: str = "", limit: int = 50):
    """事件历史"""
    try:
        from src.core.event_bus import get_event_bus
        bus = get_event_bus()
        return {"events": bus.get_recent_events(event_type, limit)}
    except Exception as e:
        return {"error": str(e)}


@router.get("/audit")
async def omega_audit(limit: int = 50):
    """审计日志"""
    try:
        from src.core.security import get_security_gate
        gate = get_security_gate()
        return {"operations": gate.get_recent_operations(limit)}
    except Exception as e:
        return {"error": str(e)}


@router.get("/tasks")
async def omega_tasks():
    """活跃任务"""
    try:
        from src.core.brain import get_brain
        brain = get_brain()
        return {"tasks": brain.get_active_tasks()}
    except Exception as e:
        return {"error": str(e)}


@router.post("/process")
async def omega_process(message: str, source: str = "api"):
    """通过 API 发送消息给 Brain"""
    try:
        from src.core.brain import get_brain
        brain = get_brain()
        result = await brain.process_message(source=source, message=message)
        return result.to_dict()
    except Exception as e:
        return {"error": str(e)}


@router.get("/investment/team")
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
        return {"error": str(e)}


@router.post("/investment/analyze")
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
        pass
    # 降级: 原有团队
    try:
        from src.modules.investment.team import get_investment_team
        team = get_investment_team()
        analysis = await team.analyze(symbol, market)
        return analysis.to_dict()
    except Exception as e:
        return {"error": str(e)}


@router.get("/investment/backtest")
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
            return {"error": "vectorbt 未安装 (pip install vectorbt[full])"}

        if strategy == "ma_cross":
            if optimize:
                result = await bt.run_ma_cross_optimized(symbol, period=period)
            else:
                result = await bt.run_ma_cross(symbol, fast=fast, slow=slow, period=period)
        elif strategy == "rsi":
            result = await bt.run_rsi_strategy(
                symbol, period=period,
                rsi_window=rsi_window, oversold=oversold, overbought=overbought
            )
        elif strategy == "macd":
            result = await bt.run_macd_strategy(
                symbol, period=period,
                fast=macd_fast, slow=macd_slow, signal=macd_signal
            )
        elif strategy == "bbands":
            result = await bt.run_bbands_strategy(
                symbol, period=period, window=bb_window, std=bb_std
            )
        elif strategy == "volume":
            result = await bt.run_volume_strategy(symbol, period=period)
        elif strategy == "compare":
            cmp = await bt.run_multi_strategy_comparison(symbol, period=period)
            return cmp.to_dict()
        else:
            return {"error": f"未知策略: {strategy}. 支持: ma_cross|rsi|macd|bbands|volume|compare"}

        return result.to_dict()
    except Exception as e:
        return {"error": str(e)}


@router.get("/tools/jina-read")
async def omega_jina_read(url: str):
    """读取URL内容（Jina Reader）"""
    try:
        from src.tools.jina_reader import jina_read
        content = await jina_read(url)
        return {"url": url, "content": content or "无法获取内容"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/tools/jina-search")
async def omega_jina_search(query: str):
    """Web搜索（Jina Search）"""
    try:
        from src.tools.jina_reader import jina_search
        content = await jina_search(query)
        return {"query": query, "results": content or "无搜索结果"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/tools/generate-image")
async def omega_generate_image(prompt: str, model: str = "fal-ai/flux/schnell"):
    """AI 图像生成 (fal.ai)"""
    try:
        from src.tools.fal_client import generate_image
        url = await generate_image(prompt, model=model)
        return {"prompt": prompt, "image_url": url, "model": model}
    except Exception as e:
        return {"error": str(e)}


@router.post("/tools/generate-video")
async def omega_generate_video(prompt: str, model: str = "fal-ai/kling-video/v1/standard/text-to-video"):
    """AI 视频生成 (fal.ai)"""
    try:
        from src.tools.fal_client import generate_video
        url = await generate_video(prompt, model=model)
        return {"prompt": prompt, "video_url": url, "model": model}
    except Exception as e:
        return {"error": str(e)}


@router.get("/tools/media-models")
async def omega_media_models():
    """可用的图像/视频模型列表"""
    try:
        from src.tools.fal_client import get_available_models
        return {"models": get_available_models()}
    except Exception as e:
        return {"error": str(e)}
