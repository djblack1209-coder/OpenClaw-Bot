"""
Trading — 系统初始化
init_trading_system 和 set_ai_team_callers 的实现
"""
import logging
from typing import Optional

from src.trading._helpers import (
    _env_bool,
    _env_int,
    _env_float,
    _estimate_open_positions_exposure,
)

logger = logging.getLogger(__name__)


def set_ai_team_callers(callers: dict):
    """注入AI团队的API调用函数（在bot启动后调用）"""
    import src.trading_system as _ts
    _ts._ai_team_api_callers = callers
    logger.info("[TradingSystem] AI团队API callers已注入: %s", list(callers.keys()))


def init_trading_system(
    broker=None,
    journal=None,
    portfolio=None,
    get_quote_func=None,
    notify_func=None,
    capital=2000.0,
    auto_mode=False,
    scan_interval=30,
):
    """
    初始化完整的自动交易系统

    参数:
        broker: IBKRBridge 实例（可选，无则用模拟组合）
        journal: TradingJournal 实例
        portfolio: Portfolio 实例
        get_quote_func: 异步获取行情函数 async (symbol) -> dict
        notify_func: 异步通知函数 async (text) -> None
        capital: 总资金
        auto_mode: 是否开启全自动模式
        scan_interval: 扫描间隔（分钟）
    """
    import src.trading_system as _ts

    if _ts._initialized:
        logger.warning("[TradingSystem] 已初始化，跳过重复初始化")
        return

    async def _noop_quote(_symbol):
        return {"price": 0}

    quote_func = get_quote_func or _noop_quote

    # 1. 风控引擎 — 根据已有持仓自动校准资金基准
    from src.risk_config import RiskConfig
    from src.risk_manager import RiskManager
    effective_capital = float(capital)
    if portfolio and _env_bool("AUTO_SCALE_CAPITAL_FROM_PORTFOLIO", True):
        exposure = _estimate_open_positions_exposure(portfolio)
        exposure_limit = max(0.3, min(0.95, _env_float("AUTO_SCALE_CAPITAL_EXPOSURE_LIMIT", 0.8)))
        buffer_ratio = max(1.0, _env_float("AUTO_SCALE_CAPITAL_BUFFER", 1.25))
        required_capital = (exposure / exposure_limit) * buffer_ratio if exposure > 0 else 0
        if required_capital > effective_capital:
            logger.warning(
                "[TradingSystem] 检测到现有敞口$%.2f 超过资金基准$%.2f，自动上调风控资金到$%.2f",
                exposure,
                effective_capital,
                required_capital,
            )
            effective_capital = required_capital

    config = RiskConfig(total_capital=effective_capital)
    _ts._risk_manager = RiskManager(config=config, journal=journal)
    logger.info("[TradingSystem] 风控引擎已初始化 (资金基准=$%.0f)", effective_capital)

    # 2. 持仓监控器 — 包含卖出降级逻辑
    from src.position_monitor import PositionMonitor
    sell_func = None
    if broker:
        # 包装 broker.sell 为带重连和降级的版本
        async def _resilient_sell(symbol, quantity, order_type="MKT", decided_by="", reason=""):
            """先尝试 IBKR 卖出，失败则重连一次，再失败降级到模拟卖出"""
            # 第一次尝试
            try:
                result = await broker.sell(symbol, quantity, order_type, decided_by=decided_by, reason=reason)
                if "error" not in result:
                    return result
                logger.warning("[TradingSystem] IBKR卖出返回错误: %s，尝试重连", result.get("error"))
            except Exception as e:
                logger.warning("[TradingSystem] IBKR卖出异常: %s，尝试重连", e)

            # 重连后重试
            try:
                reconnected = await broker.ensure_connected()
                if reconnected:
                    result = await broker.sell(symbol, quantity, order_type, decided_by=decided_by, reason=reason)
                    if "error" not in result:
                        return result
            except Exception as e:
                logger.error("[TradingSystem] IBKR重连卖出失败: %s", e)

            # 降级到模拟卖出
            if portfolio and get_quote_func:
                logger.warning("[TradingSystem] IBKR不可用，降级到模拟卖出 %s", symbol)
                if notify_func:
                    try:
                        await notify_func("!! IBKR卖出失败，降级模拟卖出 %s x%s !!" % (symbol, quantity))
                    except Exception as e:
                        logger.debug("[TradingSystem] 降级卖出通知失败: %s", e)
                price_data = await get_quote_func(symbol)
                price = price_data.get("price", 0) if isinstance(price_data, dict) else 0
                if price > 0:
                    return portfolio.sell(symbol, quantity, price, decided_by, reason)
            return {"error": "IBKR和模拟卖出均失败: %s" % symbol}
        sell_func = _resilient_sell
    elif portfolio:
        # 包装 portfolio.sell 为异步函数
        async def _sim_sell(symbol, quantity, order_type="MKT", decided_by="", reason=""):
            price_data = await get_quote_func(symbol) if get_quote_func else {"price": 0}
            price = price_data.get("price", 0) if isinstance(price_data, dict) else 0
            if price <= 0:
                return {"error": "无法获取 %s 价格" % symbol}
            return portfolio.sell(symbol, quantity, price, decided_by, reason)
        sell_func = _sim_sell

    _ts._position_monitor = PositionMonitor(
        check_interval=30,
        get_quote_func=quote_func,
        execute_sell_func=sell_func,
        notify_func=notify_func,
        risk_manager=_ts._risk_manager,
        journal=journal,
    )
    logger.info("[TradingSystem] 持仓监控器已初始化")

    # 3. 交易执行管道 — 含决策验证层
    from src.auto_trader import TradingPipeline
    from src.decision_validator import DecisionValidator
    _decision_validator = DecisionValidator(
        get_quote_func=quote_func,
        portfolio=portfolio,
        journal=journal,
    )
    logger.info("[TradingSystem] 决策验证器已初始化")

    _ts._trading_pipeline = TradingPipeline(
        risk_manager=_ts._risk_manager,
        broker=broker,
        journal=journal,
        portfolio=portfolio,
        monitor=_ts._position_monitor,
        notify_func=notify_func,
        decision_validator=_decision_validator,
    )
    logger.info("[TradingSystem] 交易执行管道已初始化 (含决策验证层)")

    # 4. 自主交易调度器 — 全市场扫描 + AI团队投票
    from src.auto_trader import AutoTrader
    max_scan_candidates = _env_int("MAX_SCAN_CANDIDATES", 50, minimum=10)
    max_vote_candidates = _env_int("MAX_VOTE_CANDIDATES", 10, minimum=3)
    scan_func = None
    analyze_func = None
    ai_team_func = None
    try:
        from src.ta_engine import scan_market, get_full_analysis
        from src.universe import full_market_scan

        # 使用全市场扫描（600+标的，多层漏斗筛选）替代小 watchlist
        async def _full_scan():
            """全市场扫描漏斗: 600+ -> 快速筛选 -> 技术分析 -> Top候选"""
            try:
                dynamic_symbols = None
                if broker and _env_bool("USE_IBKR_DYNAMIC_UNIVERSE", True):
                    try:
                        if hasattr(broker, "get_market_scanner_symbols"):
                            dynamic_symbols = await broker.get_market_scanner_symbols(
                                max_symbols=_env_int("IBKR_SCANNER_MAX_SYMBOLS", 800, minimum=100),
                                include_us=_env_bool("IBKR_SCANNER_INCLUDE_US", True),
                                include_hk=_env_bool("IBKR_SCANNER_INCLUDE_HK", True),
                            )
                    except Exception as scan_err:
                        logger.warning("[TradingSystem] IBKR 动态标的池获取失败: %s", scan_err)

                if dynamic_symbols:
                    logger.info("[TradingSystem] 使用 IBKR 动态标的池扫描: %d", len(dynamic_symbols))
                    result = await full_market_scan(
                        top_n=max_scan_candidates,
                        symbols=dynamic_symbols,
                    )
                else:
                    result = await full_market_scan(top_n=max_scan_candidates)
                # 返回格式与 scan_market 兼容的列表
                candidates = result.get("top_candidates", [])
                logger.info(
                    "[TradingSystem] 全市场扫描: %d标的 -> 层1:%d -> 层2:%d -> Top:%d (%.1fs)",
                    result.get("total_scanned", 0),
                    result.get("layer1_passed", 0),
                    result.get("layer2_passed", 0),
                    len(candidates),
                    result.get("scan_time", 0),
                )
                return candidates
            except Exception as e:
                logger.warning("[TradingSystem] 全市场扫描失败(%s)，降级为小watchlist", e, exc_info=True)
                try:
                    return await scan_market()
                except Exception as e2:
                    logger.error("[TradingSystem] 降级扫描也失败: %s", e2, exc_info=True)
                    return []

        scan_func = _full_scan

        # AI分析函数：获取完整技术分析 + 策略引擎信号增强
        async def _analyze_candidate(symbol):
            """为候选标的获取完整技术分析，并融合策略引擎信号"""
            try:
                data = await get_full_analysis(symbol)
                if isinstance(data, dict) and "error" not in data:
                    # 策略引擎增强：将量化策略信号注入分析结果
                    try:
                        from src.bot.globals import strategy_engine_instance
                        if strategy_engine_instance and "closes" in data:
                            from src.strategy_engine import MarketData
                            md = MarketData(
                                symbol=symbol,
                                timeframe="1d",
                                closes=data["closes"] if isinstance(data.get("closes"), list) else [],
                                volumes=data.get("volumes", []),
                            )
                            if md.closes and len(md.closes) >= 10:
                                se_result = strategy_engine_instance.analyze(md)
                                data["strategy_engine"] = {
                                    "consensus_signal": str(se_result.get("consensus_signal", "HOLD")),
                                    "consensus_score": se_result.get("consensus_score", 0),
                                    "confidence": se_result.get("confidence", 0),
                                    "signals": [
                                        {"name": s.strategy_name, "signal": str(s.signal.value), "score": s.score}
                                        for s in se_result.get("signals", [])
                                    ],
                                }
                    except Exception as se_err:
                        logger.debug("[TradingSystem] 策略引擎增强失败 %s: %s", symbol, se_err)
                    return data
            except Exception as e:
                logger.warning("[TradingSystem] 分析 %s 失败: %s", symbol, e)
            return None
        analyze_func = _analyze_candidate
    except ImportError:
        logger.warning("[TradingSystem] ta_engine 不可用")

    # AI团队投票函数 — CrewAI 优先，降级到原生投票
    try:
        from src.crewai_bridge import get_crewai_bridge
        _crewai = get_crewai_bridge()
    except ImportError:
        _crewai = None

    try:
        from src.ai_team_voter import run_team_vote_batch
        _ai_team_vote_batch = run_team_vote_batch

        async def _ai_team_wrapper(candidates, analyses, notify_func=None, max_candidates=5, account_context=""):
            """包装AI团队投票，优先 CrewAI，降级到原生投票"""
            if not _ts._ai_team_api_callers:
                logger.warning("[TradingSystem] AI团队API callers未注入，跳过投票")
                return []

            # 获取AI历史预测准确率，供投票时自我校准
            vote_history = None
            try:
                from src.trading_journal import journal as _tj
                _acc = _tj.get_prediction_accuracy(days=30)
                if _acc.get("total_predictions", 0) > 0:
                    vote_history = _acc.get("by_ai", {})
            except Exception as e:
                logger.debug("[TradingSystem] 获取预测准确率失败: %s", e)

            # 注入最近复盘教训（让全部6位 AI 投票时都能参考历史教训）
            try:
                from src.trading_journal import journal as _tj_lessons
                latest_review = _tj_lessons.get_latest_review()
                if latest_review and latest_review.get("lessons_learned"):
                    lessons = str(latest_review["lessons_learned"])[:500]
                    account_context += f"\n\n⚠️ 上次复盘教训 (必须遵守):\n{lessons}"
            except Exception as e:
                pass  # 教训获取失败不影响投票主流程
                logger.debug("静默异常: %s", e)

            # 尝试 CrewAI 多 Agent 协作
            if _crewai:
                try:
                    crewai_results = []
                    for cand in candidates[:max_candidates]:
                        sym = cand.get("symbol", "")
                        analysis = analyses.get(sym, {})
                        result = await _crewai.analyze_trade(sym, analysis, notify_func)
                        if result:
                            crewai_results.append(result)
                    if crewai_results:
                        logger.info("[TradingSystem] CrewAI 投票完成: %d 个结果", len(crewai_results))
                        return crewai_results
                except Exception as crew_err:
                    logger.warning("[TradingSystem] CrewAI 投票失败，降级到原生: %s", crew_err)

            # 降级到原生 AI 团队投票
            return await _ai_team_vote_batch(
                candidates=candidates,
                analyses=analyses,
                api_callers=_ts._ai_team_api_callers,
                notify_func=notify_func,
                max_candidates=max_candidates,
                account_context=account_context,
                vote_history=vote_history,
            )
        ai_team_func = _ai_team_wrapper
        logger.info("[TradingSystem] AI团队投票模块已加载 (CrewAI: %s)", "可用" if _crewai else "不可用，使用原生")
    except ImportError:
        logger.warning("[TradingSystem] ai_team_voter 不可用，使用机械策略")

    _ts._auto_trader = AutoTrader(
        pipeline=_ts._trading_pipeline,
        scan_func=scan_func,
        analyze_func=analyze_func,
        get_quote_func=quote_func,
        notify_func=notify_func,
        risk_manager=_ts._risk_manager,
        scan_interval_minutes=scan_interval,
        max_trades_per_cycle=2,
        max_trades_per_day=3,
        max_candidates_for_vote=max_vote_candidates,
        auto_mode=auto_mode,
        ai_team_func=ai_team_func,
    )
    logger.info(
        "[TradingSystem] AutoTrader已初始化 (auto=%s, interval=%dmin, 日限3笔, 扫描Top=%d, 投票候选=%d)",
        auto_mode,
        scan_interval,
        max_scan_candidates,
        max_vote_candidates,
    )

    # 5. 行情缓存
    from src.quote_cache import QuoteCache, CacheConfig
    _ts._quote_cache = QuoteCache(
        config=CacheConfig(ttl_seconds=60, refresh_interval=30),
        get_quote_func=quote_func,
    )
    logger.info("[TradingSystem] 行情缓存已初始化")

    # 6. 组合再平衡器
    from src.rebalancer import Rebalancer
    _ts._rebalancer = Rebalancer()
    logger.info("[TradingSystem] 再平衡器已初始化")

    _ts._initialized = True
    logger.info("[TradingSystem] === 全部初始化完成 ===")
