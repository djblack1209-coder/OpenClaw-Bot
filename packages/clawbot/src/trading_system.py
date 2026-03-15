"""
ClawBot 自动交易系统集成层 v1.0
将 RiskManager / PositionMonitor / TradingPipeline / AutoTrader 接入现有系统
"""
import asyncio
import json
import logging
import os
from datetime import time, datetime, timedelta
from typing import Optional, Callable, Dict, List

from src.notify_style import (
    bullet,
    format_notice,
    format_pending_reentry,
    format_trade_fill_reconciled,
    kv,
)

logger = logging.getLogger(__name__)

# 全局实例（在 init_trading_system 中初始化）
_risk_manager = None
_position_monitor = None
_trading_pipeline = None
_auto_trader = None
_scheduler = None
_quote_cache = None
_rebalancer = None
_weekly_guard_last_week_key = ""
_weekly_kill_switch_triggered = False
_pending_reentry_queue: List[Dict] = []
_processed_fill_exec_ids = set()
_initialized = False
_ai_team_api_callers = {}  # {bot_id: async callable} — 由 multi_main.py 注入

_PENDING_REENTRY_CONFIG_KEY = "pending_reentry_queue_json"


def set_ai_team_callers(callers: dict):
    """注入AI团队的API调用函数（在bot启动后调用）"""
    global _ai_team_api_callers
    _ai_team_api_callers = callers
    logger.info("[TradingSystem] AI团队API callers已注入: %s", list(callers.keys()))


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _estimate_open_positions_exposure(portfolio) -> float:
    """估算当前组合已开仓总敞口（用于风控资金基准校准）"""
    if not portfolio:
        return 0.0
    try:
        positions = portfolio.get_positions()
    except Exception:
        return 0.0

    exposure = 0.0
    for p in positions or []:
        status = str(p.get("status", "open") or "open")
        if status != "open":
            continue
        qty = abs(float(p.get("quantity", 0) or 0))
        price = float(p.get("avg_price", 0) or p.get("avg_cost", 0) or 0)
        if qty > 0 and price > 0:
            exposure += qty * price
    return exposure


def _is_us_market_open_now() -> bool:
    """判断当前是否处于美股常规交易时段（美东 09:30-16:00）"""
    from src.utils import now_et
    from src.auto_trader import is_market_holiday

    now = now_et()
    if now.weekday() >= 5:
        return False
    if is_market_holiday(now.strftime("%Y-%m-%d")):
        return False

    hour = now.hour
    minute = now.minute
    market_open = (hour > 9) or (hour == 9 and minute >= 30)
    market_close = hour >= 16
    return market_open and not market_close


def _parse_datetime(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _load_pending_reentry_queue() -> List[Dict]:
    from src.trading_journal import journal as tj

    raw = tj.get_config(_PENDING_REENTRY_CONFIG_KEY, "[]")
    try:
        payload = json.loads(raw)
        if not isinstance(payload, list):
            return []
    except Exception:
        return []

    normalized = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "") or "").upper().strip()
        qty = int(float(item.get("quantity", 0) or 0))
        if not symbol or qty <= 0:
            continue
        normalized.append({
            "symbol": symbol,
            "quantity": qty,
            "stop_loss": float(item.get("stop_loss", 0) or 0),
            "take_profit": float(item.get("take_profit", 0) or 0),
            "signal_score": int(float(item.get("signal_score", 0) or 0)),
            "entry_reason": str(item.get("entry_reason", "") or ""),
            "decided_by": str(item.get("decided_by", "") or "AutoTrader"),
            "source_trade_id": int(float(item.get("source_trade_id", 0) or 0)),
            "retry_count": int(float(item.get("retry_count", 0) or 0)),
            "queued_at": str(item.get("queued_at", "") or ""),
            "next_retry_at": str(item.get("next_retry_at", "") or ""),
        })
    return normalized


def _save_pending_reentry_queue(queue: List[Dict]) -> None:
    from src.trading_journal import journal as tj

    safe_queue = []
    for item in queue:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "") or "").upper().strip()
        qty = int(float(item.get("quantity", 0) or 0))
        if not symbol or qty <= 0:
            continue
        safe_queue.append({
            "symbol": symbol,
            "quantity": qty,
            "stop_loss": float(item.get("stop_loss", 0) or 0),
            "take_profit": float(item.get("take_profit", 0) or 0),
            "signal_score": int(float(item.get("signal_score", 0) or 0)),
            "entry_reason": str(item.get("entry_reason", "") or ""),
            "decided_by": str(item.get("decided_by", "") or "AutoTrader"),
            "source_trade_id": int(float(item.get("source_trade_id", 0) or 0)),
            "retry_count": int(float(item.get("retry_count", 0) or 0)),
            "queued_at": str(item.get("queued_at", "") or ""),
            "next_retry_at": str(item.get("next_retry_at", "") or ""),
        })
    tj.set_config(_PENDING_REENTRY_CONFIG_KEY, json.dumps(safe_queue, ensure_ascii=False))


def _queue_reentry_from_trade(trade: Dict, reason: str = "") -> bool:
    """将撤单后的交易加入次日重挂队列（持久化到 config）"""
    global _pending_reentry_queue

    symbol = str(trade.get("symbol", "") or "").upper().strip()
    quantity = int(float(trade.get("quantity", 0) or 0))
    source_trade_id = int(float(trade.get("id", 0) or 0))
    if not symbol or quantity <= 0:
        return False

    for item in _pending_reentry_queue:
        if int(item.get("source_trade_id", 0) or 0) == source_trade_id:
            return False

    from src.utils import now_et
    now = now_et().isoformat()
    entry_reason = str(trade.get("entry_reason", "") or "")
    if reason:
        entry_reason = f"{entry_reason} | 重挂原因: {reason}".strip(" |")

    _pending_reentry_queue.append({
        "symbol": symbol,
        "quantity": quantity,
        "stop_loss": float(trade.get("stop_loss", 0) or 0),
        "take_profit": float(trade.get("take_profit", 0) or 0),
        "signal_score": int(float(trade.get("signal_score", 0) or 0)),
        "entry_reason": entry_reason,
        "decided_by": str(trade.get("decided_by", "") or "AutoTrader"),
        "source_trade_id": source_trade_id,
        "retry_count": 0,
        "queued_at": now,
        "next_retry_at": now,
    })
    _save_pending_reentry_queue(_pending_reentry_queue)
    return True


def _ensure_monitor_position_from_trade(trade: Dict) -> None:
    """确保指定交易存在于持仓监控器中（用于成交回写后补监控）"""
    if not _position_monitor or not isinstance(trade, dict):
        return

    trade_id = int(float(trade.get("id", 0) or 0))
    if trade_id <= 0:
        return

    qty = float(trade.get("quantity", 0) or 0)
    entry_price = float(trade.get("entry_price", 0) or 0)
    if qty <= 0 or entry_price <= 0:
        return

    existing = _position_monitor.positions.get(trade_id)
    if existing:
        existing.quantity = qty
        existing.entry_price = entry_price
        existing.stop_loss = float(trade.get("stop_loss", 0) or 0)
        existing.take_profit = float(trade.get("take_profit", 0) or 0)
        return

    from src.position_monitor import MonitoredPosition

    entry_dt = _parse_datetime(str(trade.get("entry_time", "") or ""))
    if entry_dt is None:
        entry_dt = datetime.now()

    mon = MonitoredPosition(
        trade_id=trade_id,
        symbol=str(trade.get("symbol", "") or "").upper(),
        side=str(trade.get("side", "BUY") or "BUY"),
        quantity=qty,
        entry_price=entry_price,
        entry_time=entry_dt,
        stop_loss=float(trade.get("stop_loss", 0) or 0),
        take_profit=float(trade.get("take_profit", 0) or 0),
        trailing_stop_pct=0.03,
        atr=0.0,
    )
    _position_monitor.add_position(mon)


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
    global _risk_manager, _position_monitor, _trading_pipeline, _auto_trader, _quote_cache, _rebalancer, _initialized

    if _initialized:
        logger.warning("[TradingSystem] 已初始化，跳过重复初始化")
        return

    async def _noop_quote(_symbol):
        return {"price": 0}

    quote_func = get_quote_func or _noop_quote

    # 1. 风控引擎
    from src.risk_manager import RiskManager, RiskConfig
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
    _risk_manager = RiskManager(config=config, journal=journal)
    logger.info("[TradingSystem] 风控引擎已初始化 (资金基准=$%.0f)", effective_capital)

    # 2. 持仓监控器
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

    _position_monitor = PositionMonitor(
        check_interval=30,
        get_quote_func=quote_func,
        execute_sell_func=sell_func,
        notify_func=notify_func,
        risk_manager=_risk_manager,
        journal=journal,
    )
    logger.info("[TradingSystem] 持仓监控器已初始化")

    # 3. 交易执行管道
    from src.auto_trader import TradingPipeline
    from src.decision_validator import DecisionValidator
    _decision_validator = DecisionValidator(
        get_quote_func=quote_func,
        portfolio=portfolio,
        journal=journal,
    )
    logger.info("[TradingSystem] 决策验证器已初始化")

    _trading_pipeline = TradingPipeline(
        risk_manager=_risk_manager,
        broker=broker,
        journal=journal,
        portfolio=portfolio,
        monitor=_position_monitor,
        notify_func=notify_func,
        decision_validator=_decision_validator,
    )
    logger.info("[TradingSystem] 交易执行管道已初始化 (含决策验证层)")

    # 4. 自主交易调度器
    from src.auto_trader import AutoTrader
    max_scan_candidates = _env_int("MAX_SCAN_CANDIDATES", 50, minimum=10)
    max_vote_candidates = _env_int("MAX_VOTE_CANDIDATES", 10, minimum=3)
    scan_func = None
    analyze_func = None
    ai_team_func = None
    try:
        from src.ta_engine import scan_market, get_full_analysis
        from src.universe import full_market_scan, get_full_universe

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

        # AI分析函数：获取完整技术分析并生成摘要
        async def _analyze_candidate(symbol):
            """为候选标的获取完整技术分析"""
            try:
                data = await get_full_analysis(symbol)
                if isinstance(data, dict) and "error" not in data:
                    return data
            except Exception as e:
                logger.warning("[TradingSystem] 分析 %s 失败: %s", symbol, e)
            return None
        analyze_func = _analyze_candidate
    except ImportError:
        logger.warning("[TradingSystem] ta_engine 不可用")

    # AI团队投票函数 — 延迟绑定，等 bot 启动后注入 api_callers
    try:
        from src.ai_team_voter import run_team_vote_batch
        _ai_team_vote_batch = run_team_vote_batch

        async def _ai_team_wrapper(candidates, analyses, notify_func=None, max_candidates=5, account_context=""):
            """包装AI团队投票，注入api_callers"""
            # api_callers 在 multi_main.py 启动后通过 set_ai_team_callers() 注入
            if not _ai_team_api_callers:
                logger.warning("[TradingSystem] AI团队API callers未注入，跳过投票")
                return []
            return await _ai_team_vote_batch(
                candidates=candidates,
                analyses=analyses,
                api_callers=_ai_team_api_callers,
                notify_func=notify_func,
                max_candidates=max_candidates,
                account_context=account_context,
            )
        ai_team_func = _ai_team_wrapper
        logger.info("[TradingSystem] AI团队投票模块已加载")
    except ImportError:
        logger.warning("[TradingSystem] ai_team_voter 不可用，使用机械策略")

    _auto_trader = AutoTrader(
        pipeline=_trading_pipeline,
        scan_func=scan_func,
        analyze_func=analyze_func,
        get_quote_func=quote_func,
        notify_func=notify_func,
        risk_manager=_risk_manager,
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
    _quote_cache = QuoteCache(
        config=CacheConfig(ttl_seconds=60, refresh_interval=30),
        get_quote_func=quote_func,
    )
    logger.info("[TradingSystem] 行情缓存已初始化")

    # 6. 组合再平衡器
    from src.rebalancer import Rebalancer
    _rebalancer = Rebalancer()
    logger.info("[TradingSystem] 再平衡器已初始化")

    _initialized = True
    logger.info("[TradingSystem] === 全部初始化完成 ===")


async def start_trading_system():
    """启动持仓监控和自动交易（在 main() 中调用）"""
    global _pending_reentry_queue, _processed_fill_exec_ids

    if not _initialized:
        logger.error("[TradingSystem] 未初始化，无法启动")
        return

    _pending_reentry_queue = _load_pending_reentry_queue()
    _processed_fill_exec_ids = set()
    if _pending_reentry_queue:
        logger.info("[TradingSystem] 恢复待重挂队列: %d 条", len(_pending_reentry_queue))

    # P0-3: 从 journal 恢复未平仓持仓到 PositionMonitor
    if _position_monitor and _risk_manager:
        try:
            from src.trading_journal import journal as tj
            from src.position_monitor import MonitoredPosition
            open_trades = tj.get_open_trades()
            for t in open_trades:
                try:
                    pos = MonitoredPosition(
                        trade_id=t["id"],
                        symbol=t["symbol"],
                        side=t.get("side", "BUY"),
                        quantity=float(t.get("quantity", 0)),
                        entry_price=float(t.get("entry_price", 0)),
                        entry_time=datetime.fromisoformat(t["created_at"]) if t.get("created_at") else datetime.now(),
                        stop_loss=float(t.get("stop_loss", 0) or 0),
                        take_profit=float(t.get("take_profit", 0) or 0),
                        trailing_stop_pct=0.03,
                    )
                    _position_monitor.add_position(pos)
                except Exception as e:
                    logger.warning("[TradingSystem] 恢复持仓 %s 失败: %s", t.get("symbol"), e)
            if open_trades:
                logger.info("[TradingSystem] 从journal恢复了 %d 个持仓到监控器", len(open_trades))
        except Exception as e:
            logger.error("[TradingSystem] 恢复持仓失败: %s", e)

    # P0-4: 从 journal 恢复今日PnL到 RiskManager
    if _risk_manager:
        try:
            from src.trading_journal import journal as tj
            today_data = tj.get_today_pnl()
            _risk_manager._today_pnl = today_data.get("pnl", 0)
            _risk_manager._today_trades = today_data.get("trades", 0)
            logger.info("[TradingSystem] 恢复今日PnL: $%.2f (%d笔)",
                        _risk_manager._today_pnl, _risk_manager._today_trades)
        except Exception as e:
            logger.error("[TradingSystem] 恢复PnL失败: %s", e)

    # P0-5: 从 journal 恢复今日已执行交易数到 AutoTrader (P1#17: 用ET时间)
    if _auto_trader:
        try:
            from src.trading_journal import journal as tj
            from src.utils import today_et_str
            today_str = today_et_str()
            today_trades = tj.get_today_pnl().get("trades", 0)
            if today_trades > 0:
                _auto_trader._today_trades = today_trades
                _auto_trader._today_date = today_str
                logger.info("[TradingSystem] 恢复AutoTrader今日交易计数: %d笔", today_trades)
        except Exception as e:
            logger.error("[TradingSystem] 恢复AutoTrader交易计数失败: %s", e)

    if _position_monitor:
        await _position_monitor.start()
        logger.info("[TradingSystem] 持仓监控器已启动")

    # P0-6: 从 IBKR 同步实际资金到 RiskManager 和 broker budget
    if _risk_manager:
        try:
            from src.broker_bridge import ibkr as _ibkr
            if _ibkr.is_connected():
                actual_capital = await _ibkr.sync_capital()
                if actual_capital > 0:
                    _risk_manager.config.total_capital = actual_capital
                    logger.info("[TradingSystem] 从IBKR同步资金: $%.2f", actual_capital)
        except Exception as e:
            logger.warning("[TradingSystem] IBKR资金同步失败，使用默认值: %s", e)

    # AutoTrader 自动启动（全自动模式）
    if _auto_trader:
        await _auto_trader.start()
        logger.info("[TradingSystem] AutoTrader 已自动启动 (auto_mode=%s, 间隔=%d分钟)",
                    _auto_trader.auto_mode, _auto_trader.scan_interval)

    # P4: 启动 Scheduler 定时任务
    global _scheduler, _weekly_guard_last_week_key, _weekly_kill_switch_triggered
    try:
        from src.scheduler import Scheduler
        _scheduler = Scheduler()

        # 每日风控重置（每天09:00）
        async def _daily_risk_reset():
            if _risk_manager:
                _risk_manager.reset_daily()
                logger.info("[Scheduler] 每日风控重置完成")
            # 同时重置 IBKR 预算追踪
            try:
                from src.broker_bridge import ibkr as _ibkr
                _ibkr.reset_budget()
                logger.info("[Scheduler] IBKR预算已重置")
            except Exception as e:
                logger.warning("[Scheduler] IBKR预算重置失败: %s", e)
            # 重置 AutoTrader 日交易计数
            if _auto_trader:
                _auto_trader._today_trades = 0
                _auto_trader._today_date = ""
                logger.info("[Scheduler] AutoTrader日交易计数已重置")
        _scheduler.add_task("daily_risk_reset", _daily_risk_reset,
                            schedule_time=time(9, 0))

        # 每日收盘自动复盘 + 盈亏报告（每天16:05 美东）
        async def _eod_auto_review():
            if _auto_trader and _auto_trader.notify:
                try:
                    from src.trading_journal import journal as tj
                    # 生成每日盈亏报告
                    today_pnl = tj.get_today_pnl()
                    perf = tj.format_performance(days=1)
                    open_trades = tj.get_open_trades()
                    closed = tj.get_closed_trades(days=1, limit=20)

                    lines = ["-- 每日自动复盘 --\n"]
                    lines.append("今日盈亏: $%.2f (%d笔交易)" % (
                        today_pnl.get("pnl", 0), today_pnl.get("trades", 0)))

                    if closed:
                        lines.append("\n已平仓:")
                        for t in closed:
                            sign = "+" if t.get("pnl", 0) >= 0 else ""
                            lines.append("  %s %s %s$%.2f" % (
                                t.get("side", "?"), t.get("symbol", "?"),
                                sign, abs(t.get("pnl", 0))))

                    if open_trades:
                        lines.append("\n持仓中: %d笔" % len(open_trades))
                        for t in open_trades:
                            lines.append("  %s x%s 入场$%s" % (
                                t.get("symbol", "?"),
                                t.get("quantity", "?"),
                                t.get("entry_price", "?")))

                    lines.append("\n" + perf)
                    lines.append("\n系统将在明日开盘自动继续交易。")

                    await _auto_trader._safe_notify("\n".join(lines))
                except Exception as e:
                    logger.error("[Scheduler] 自动复盘失败: %s", e)
                    await _auto_trader._safe_notify("收盘复盘生成失败: %s\n发送 /review 手动复盘" % e)
        _scheduler.add_task("eod_auto_review", _eod_auto_review,
                            schedule_time=time(16, 5))

        # 行情缓存定期刷新（每5分钟）
        async def _refresh_quotes():
            if _quote_cache and _position_monitor:
                # 监控中的标的加入缓存
                syms = [p.symbol for p in _position_monitor.positions.values()]
                if _rebalancer and _rebalancer.get_targets():
                    syms += [t.symbol for t in _rebalancer.get_targets()]
                if syms:
                    _quote_cache.watch(list(set(syms)))
                    await _quote_cache.refresh()
        _scheduler.add_task("quote_refresh", _refresh_quotes,
                            interval_minutes=5)

        # 每日再平衡检查（09:35，开盘后5分钟）
        async def _daily_rebalance_check():
            if _rebalancer and _rebalancer.get_targets() and _auto_trader and _auto_trader.notify:
                try:
                    from src.invest_tools import portfolio
                    positions = portfolio.get_positions()
                    cash = portfolio.get_cash()
                    quotes = _quote_cache.get_all() if _quote_cache else {}
                    plan = _rebalancer.analyze(positions, quotes, cash)
                    if not plan.is_balanced and plan.trades_needed:
                        await _auto_trader._safe_notify(
                            "每日再平衡检查\n\n" + plan.format()
                        )
                except Exception as e:
                    logger.warning("[Scheduler] 再平衡检查失败: %s", e)
        _scheduler.add_task("daily_rebalance", _daily_rebalance_check,
                            schedule_time=time(9, 35))

        # 每日资金同步（09:25 ET，开盘前5分钟从IBKR同步实际资金）
        async def _daily_capital_sync():
            if _risk_manager:
                try:
                    from src.broker_bridge import ibkr as _ibkr
                    if _ibkr.is_connected():
                        actual = await _ibkr.sync_capital()
                        if actual > 0:
                            _risk_manager.config.total_capital = actual
                            logger.info("[Scheduler] 资金同步: $%.2f", actual)
                    else:
                        logger.warning("[Scheduler] IBKR未连接，跳过资金同步")
                except Exception as e:
                    logger.warning("[Scheduler] 资金同步失败: %s", e)
        _scheduler.add_task("daily_capital_sync", _daily_capital_sync,
                            schedule_time=time(9, 25))

        # 每周利润硬规则（周一 09:20 ET，检查上周已平仓PnL）
        async def _weekly_profit_guard():
            global _weekly_guard_last_week_key, _weekly_kill_switch_triggered

            enabled = _env_bool("WEEKLY_KILL_SWITCH", True)
            target = _env_float("WEEKLY_PROFIT_TARGET", 50.0)
            if not enabled:
                return

            from src.utils import now_et
            now = now_et()
            if now.weekday() != 0:  # 仅周一执行
                return

            current_week_start = now.date() - timedelta(days=now.weekday())
            last_week_start = current_week_start - timedelta(days=7)
            last_week_end = current_week_start - timedelta(days=1)
            week_key = f"{last_week_start.isoformat()}::{last_week_end.isoformat()}"
            if _weekly_guard_last_week_key == week_key:
                return

            _weekly_guard_last_week_key = week_key

            from src.trading_journal import journal as tj
            trades = tj.get_closed_trades(days=14, limit=1000)
            week_trades = []
            for trade in trades:
                exit_time = trade.get("exit_time")
                if not exit_time:
                    continue
                try:
                    exit_dt = datetime.fromisoformat(str(exit_time))
                    exit_date = exit_dt.date()
                except Exception:
                    continue
                if last_week_start <= exit_date <= last_week_end:
                    week_trades.append(trade)

            week_pnl = sum(float(t.get("pnl", 0) or 0) for t in week_trades)
            logger.info(
                "[Scheduler] 周利润守卫检查 %s~%s: pnl=$%.2f, target=$%.2f, trades=%d",
                last_week_start,
                last_week_end,
                week_pnl,
                target,
                len(week_trades),
            )

            if week_pnl >= target:
                _weekly_kill_switch_triggered = False
                return

            _weekly_kill_switch_triggered = True

            if _auto_trader:
                await _auto_trader.stop()
                try:
                    from src.auto_trader import TraderState
                    _auto_trader.state = TraderState.PAUSED
                except Exception:
                    pass

            msg = (
                "!! 周盈利硬规则触发，自动停机 !!\n"
                "上周区间: %s ~ %s\n"
                "上周已平仓PnL: $%.2f\n"
                "最低目标: $%.2f\n"
                "动作: AutoTrader 已强制停止 (state=PAUSED)"
            ) % (
                last_week_start,
                last_week_end,
                week_pnl,
                target,
            )
            logger.warning("[Scheduler] %s", msg.replace("\n", " | "))
            if _auto_trader and _auto_trader.notify:
                try:
                    await _auto_trader._safe_notify(
                        format_notice(
                            "周盈利守卫触发",
                            bullets=[
                                kv("周期", f"{last_week_start} ~ {last_week_end}"),
                                kv("上周已平仓PnL", f"${week_pnl:.2f}"),
                                kv("最低目标", f"${target:.2f}"),
                                bullet("动作: AutoTrader 已强制停止 (state=PAUSED)"),
                            ],
                        )
                    )
                except Exception as e:
                    logger.warning("[Scheduler] 周利润守卫通知失败: %s", e)

        _scheduler.add_task(
            "weekly_profit_guard",
            _weekly_profit_guard,
            schedule_time=time(9, 20),
        )

        # 成交回写校验器：pending 入场订单 -> 成交回写到 journal + monitor
        async def _reconcile_ibkr_entry_fills():
            global _processed_fill_exec_ids

            if not _env_bool("IBKR_FILL_RECONCILE_ENABLED", True):
                return
            if not _trading_pipeline or not _trading_pipeline.broker:
                return

            broker = _trading_pipeline.broker
            if not hasattr(broker, "get_recent_fills"):
                return

            from src.trading_journal import journal as tj
            pending = tj.get_pending_trades(
                limit=_env_int("IBKR_PENDING_RECONCILE_LIMIT", 300, minimum=50)
            )
            open_with_order = [
                t for t in tj.get_open_trades()
                if str(t.get("entry_order_id", "") or "").strip()
            ]

            if not pending and not open_with_order:
                return

            fills = await broker.get_recent_fills(
                lookback_hours=_env_int("IBKR_FILL_LOOKBACK_HOURS", 48, minimum=1)
            )
            fills = fills or []

            aggregated = {}
            new_exec = 0
            for fill in fills:
                exec_id = str(fill.get("exec_id", "") or "")
                if not exec_id or exec_id in _processed_fill_exec_ids:
                    continue

                _processed_fill_exec_ids.add(exec_id)
                new_exec += 1

                order_id = str(fill.get("order_id", "") or "").strip()
                shares = float(fill.get("shares", 0) or 0)
                price = float(fill.get("price", 0) or 0)
                if not order_id or shares <= 0 or price <= 0:
                    continue

                item = aggregated.setdefault(order_id, {
                    "shares": 0.0,
                    "notional": 0.0,
                    "symbol": str(fill.get("symbol", "") or "").upper(),
                    "latest_time": str(fill.get("time", "") or ""),
                })
                item["shares"] += shares
                item["notional"] += shares * price
                if fill.get("time"):
                    item["latest_time"] = str(fill.get("time"))

            if len(_processed_fill_exec_ids) > 8000:
                _processed_fill_exec_ids = set(list(_processed_fill_exec_ids)[-4000:])

            pending_by_order = {}
            for trade in pending:
                oid = str(trade.get("entry_order_id", "") or "").strip()
                if oid:
                    pending_by_order[oid] = trade

            for order_id, fill_info in aggregated.items():
                trade = pending_by_order.get(order_id)
                if not trade:
                    continue

                shares = float(fill_info.get("shares", 0) or 0)
                notional = float(fill_info.get("notional", 0) or 0)
                avg_price = notional / shares if shares > 0 else 0
                if shares <= 0 or avg_price <= 0:
                    continue

                trade_id = int(float(trade.get("id", 0) or 0))
                update = tj.mark_trade_entry_filled(
                    trade_id=trade_id,
                    filled_qty=shares,
                    fill_price=avg_price,
                    entry_order_id=order_id,
                    fill_time=str(fill_info.get("latest_time", "") or ""),
                )
                if "error" in update:
                    logger.warning("[Reconcile] 回写失败 trade#%s: %s", trade_id, update["error"])
                    continue

                refreshed = tj.get_trade(trade_id)
                if refreshed:
                    _ensure_monitor_position_from_trade(refreshed)

                logger.info(
                    "[Reconcile] 成交回写成功 trade#%d order#%s qty=%.4f @ %.4f",
                    trade_id,
                    order_id,
                    shares,
                    avg_price,
                )

                if _auto_trader and _auto_trader.notify:
                    try:
                        await _auto_trader._safe_notify(
                            format_trade_fill_reconciled(
                                trade_id,
                                order_id,
                                str(trade.get("symbol", "?") or "?").upper(),
                                shares,
                                avg_price,
                            )
                        )
                    except Exception as e:
                        logger.debug("[Reconcile] 成交通知失败: %s", e)

            # 兼容旧逻辑：open + entry_order_id 但无持仓/无挂单时，自动修正状态
            if open_with_order:
                open_orders = await broker.get_open_orders() if hasattr(broker, "get_open_orders") else []
                open_order_ids = {
                    str(o.get("order_id", "") or "")
                    for o in open_orders
                    if o.get("order_id") is not None
                }
                snapshots = await broker.get_trade_snapshots() if hasattr(broker, "get_trade_snapshots") else []
                snapshot_map = {
                    str(o.get("order_id", "") or ""): o
                    for o in snapshots
                    if o.get("order_id") is not None
                }
                positions = await broker.get_positions() if hasattr(broker, "get_positions") else []
                pos_symbols = {
                    str(p.get("symbol", "") or "").upper(): abs(float(p.get("quantity", 0) or 0))
                    for p in positions
                }
                grace_minutes = _env_int("IBKR_LEGACY_ORDER_RECONCILE_GRACE_MIN", 30, minimum=5)

                for trade in open_with_order:
                    trade_id = int(float(trade.get("id", 0) or 0))
                    order_id = str(trade.get("entry_order_id", "") or "").strip()
                    symbol = str(trade.get("symbol", "") or "").upper().strip()
                    if trade_id <= 0 or not order_id or not symbol:
                        continue

                    # 如果有真实持仓，视为已成交，无需处理
                    if pos_symbols.get(symbol, 0) > 0:
                        continue

                    entry_dt = _parse_datetime(str(trade.get("entry_time", "") or ""))
                    age_min = 0
                    if entry_dt is not None:
                        age_min = int(max(0, (datetime.now() - entry_dt.replace(tzinfo=None)).total_seconds() / 60))

                    if order_id in open_order_ids:
                        # 旧记录修正为 pending，避免被误当成已持仓
                        if age_min >= grace_minutes:
                            tj.set_trade_status(trade_id, "pending", reason="legacy_open_order_pending")
                            if _position_monitor:
                                _position_monitor.remove_position(trade_id)
                            logger.info("[Reconcile] trade#%d 状态修正为 pending (order#%s)", trade_id, order_id)
                        continue

                    snap_status = str(snapshot_map.get(order_id, {}).get("status", "") or "")
                    # 既无持仓也无挂单，且过了宽限期 -> 取消旧记录
                    if age_min >= grace_minutes and snap_status in ("", "Cancelled", "ApiCancelled", "Inactive"):
                        tj.cancel_trade(trade_id, reason="reconcile_no_fill_no_position")
                        if _position_monitor:
                            _position_monitor.remove_position(trade_id)
                        logger.info(
                            "[Reconcile] trade#%d 无成交且无持仓，已取消 (order#%s)",
                            trade_id,
                            order_id,
                        )

            if new_exec > 0:
                logger.info("[Reconcile] 本轮处理新成交回报: %d 条", new_exec)

        _scheduler.add_task(
            "ibkr_fill_reconcile",
            _reconcile_ibkr_entry_fills,
            interval_minutes=_env_int("IBKR_FILL_RECONCILE_INTERVAL_MIN", 2, minimum=1),
        )

        # 非交易时段 pending 订单自动撤单 + 加入次日重挂队列
        async def _cancel_stale_pending_entries():
            if not _env_bool("AUTO_CANCEL_PENDING_ENTRY_ORDERS", True):
                return
            if not _trading_pipeline or not _trading_pipeline.broker:
                return

            broker = _trading_pipeline.broker
            if not hasattr(broker, "get_open_orders"):
                return

            from src.trading_journal import journal as tj
            pending = tj.get_pending_trades(
                limit=_env_int("PENDING_ENTRY_SCAN_LIMIT", 300, minimum=50)
            )
            if not pending:
                return

            market_open = _is_us_market_open_now()
            stale_minutes = _env_int("PENDING_ENTRY_CANCEL_AFTER_MINUTES", 20, minimum=1)
            deep_timeout = max(stale_minutes * 3, 60)

            open_orders = await broker.get_open_orders()
            open_map = {
                str(o.get("order_id", "") or ""): o
                for o in open_orders
                if o.get("order_id") is not None
            }

            snapshots = []
            if hasattr(broker, "get_trade_snapshots"):
                snapshots = await broker.get_trade_snapshots()
            snapshot_map = {
                str(o.get("order_id", "") or ""): o
                for o in snapshots
                if o.get("order_id") is not None
            }

            cancelled_statuses = {"Cancelled", "ApiCancelled", "Inactive"}
            now = datetime.now()

            for trade in pending:
                trade_id = int(float(trade.get("id", 0) or 0))
                order_id = str(trade.get("entry_order_id", "") or "").strip()
                if trade_id <= 0 or not order_id:
                    continue

                entry_dt = _parse_datetime(str(trade.get("entry_time", "") or ""))
                age_min = 9999
                if entry_dt is not None:
                    age_min = max(0, int((now - entry_dt.replace(tzinfo=None)).total_seconds() / 60))

                live_order = open_map.get(order_id)
                snap = snapshot_map.get(order_id, {})
                status = str((live_order or snap).get("status", "") or "")

                need_cancel_api = False
                cancel_reason = ""

                if live_order and (not market_open) and age_min >= stale_minutes:
                    need_cancel_api = True
                    cancel_reason = f"offhours_pending_timeout_{age_min}m"
                elif (not live_order) and status in cancelled_statuses:
                    cancel_reason = f"broker_{status.lower()}"
                elif (not live_order) and (not status) and age_min >= deep_timeout:
                    cancel_reason = f"pending_timeout_{age_min}m"

                if need_cancel_api:
                    try:
                        cancel_ret = await broker.cancel_order(int(float(order_id)))
                    except Exception as e:
                        logger.warning("[PendingCancel] 订单#%s 撤单异常: %s", order_id, e)
                        continue
                    if "error" in cancel_ret:
                        logger.warning("[PendingCancel] 订单#%s 撤单失败: %s", order_id, cancel_ret["error"])
                        continue

                if not cancel_reason:
                    continue

                tj.cancel_trade(trade_id, cancel_reason)
                queued = False
                if _env_bool("AUTO_RESUBMIT_PENDING_NEXT_SESSION", True):
                    queued = _queue_reentry_from_trade(trade, reason=cancel_reason)

                if _position_monitor:
                    _position_monitor.remove_position(trade_id)

                logger.info(
                    "[PendingCancel] trade#%d order#%s 已取消，原因=%s，重挂=%s",
                    trade_id,
                    order_id,
                    cancel_reason,
                    queued,
                )

                if _auto_trader and _auto_trader.notify:
                    try:
                        await _auto_trader._safe_notify(
                            format_notice(
                                "待成交订单已撤单",
                                bullets=[
                                    kv("Trade / Order", f"#{trade_id} / #{order_id}"),
                                    kv("原因", cancel_reason),
                                    kv("次日重挂", "已加入" if queued else "未加入"),
                                ],
                            )
                        )
                    except Exception as e:
                        logger.debug("[PendingCancel] 通知失败: %s", e)

        _scheduler.add_task(
            "pending_entry_cancel",
            _cancel_stale_pending_entries,
            interval_minutes=_env_int("PENDING_ENTRY_CANCEL_CHECK_INTERVAL_MIN", 5, minimum=1),
        )

        # 次日重挂：交易时段开启后按队列重提单
        async def _submit_pending_reentry_queue():
            global _pending_reentry_queue

            if not _env_bool("AUTO_RESUBMIT_PENDING_NEXT_SESSION", True):
                return
            if not _pending_reentry_queue:
                return
            if not _is_us_market_open_now():
                return
            if not _trading_pipeline:
                return

            max_per_cycle = _env_int("PENDING_REENTRY_MAX_PER_CYCLE", 1, minimum=1)
            max_retries = _env_int("PENDING_REENTRY_MAX_RETRIES", 2, minimum=1)
            retry_interval_min = _env_int("PENDING_REENTRY_RETRY_INTERVAL_MIN", 5, minimum=1)

            from src.models import TradeProposal
            from src.utils import now_et
            from src.invest_tools import get_stock_quote

            now_dt = now_et()
            submitted_count = 0
            next_queue = []

            for item in list(_pending_reentry_queue):
                if submitted_count >= max_per_cycle:
                    next_queue.append(item)
                    continue

                next_retry_at = _parse_datetime(str(item.get("next_retry_at", "") or ""))
                if next_retry_at and now_dt < next_retry_at:
                    next_queue.append(item)
                    continue

                symbol = str(item.get("symbol", "") or "").upper().strip()
                qty = int(float(item.get("quantity", 0) or 0))
                if not symbol or qty <= 0:
                    continue

                try:
                    quote_ret = get_stock_quote(symbol)
                    if asyncio.iscoroutine(quote_ret):
                        price_data = await quote_ret
                    else:
                        price_data = quote_ret
                except Exception as e:
                    logger.warning("[ReEntry] %s 获取行情失败: %s", symbol, e)
                    price_data = {}

                price = float(price_data.get("price", 0) or 0) if isinstance(price_data, dict) else 0
                if price <= 0:
                    retry_count = int(float(item.get("retry_count", 0) or 0)) + 1
                    if retry_count <= max_retries:
                        item["retry_count"] = retry_count
                        item["next_retry_at"] = (now_dt + timedelta(minutes=retry_interval_min)).isoformat()
                        next_queue.append(item)
                    continue

                stop = float(item.get("stop_loss", 0) or 0)
                if stop <= 0 or stop >= price:
                    stop = round(price * 0.97, 2)
                target = float(item.get("take_profit", 0) or 0)
                if target <= 0 or target <= price:
                    target = round(price * 1.06, 2)

                proposal = TradeProposal(
                    symbol=symbol,
                    action="BUY",
                    quantity=qty,
                    entry_price=price,
                    stop_loss=stop,
                    take_profit=target,
                    signal_score=int(float(item.get("signal_score", 0) or 0)),
                    confidence=0.55,
                    reason=str(item.get("entry_reason", "") or "")[:180] or "次日重挂执行",
                    decided_by=f"ReEntry/{str(item.get('decided_by', 'AutoTrader') or 'AutoTrader')}",
                )

                try:
                    exec_result = await _trading_pipeline.execute_proposal(proposal)
                except Exception as e:
                    logger.warning("[ReEntry] %s 执行异常: %s", symbol, e)
                    exec_result = {"status": "error", "reason": str(e)}

                status = str(exec_result.get("status", "") or "")
                if status in ("executed", "submitted"):
                    submitted_count += 1
                    if _auto_trader and _auto_trader.notify:
                        try:
                            await _auto_trader._safe_notify(
                                format_pending_reentry(symbol, qty, price, status)
                            )
                        except Exception:
                            pass
                    continue

                retry_count = int(float(item.get("retry_count", 0) or 0)) + 1
                if retry_count <= max_retries:
                    item["retry_count"] = retry_count
                    item["next_retry_at"] = (now_dt + timedelta(minutes=retry_interval_min)).isoformat()
                    next_queue.append(item)
                else:
                    logger.warning("[ReEntry] %s 重挂失败超限，放弃: %s", symbol, exec_result)

            _pending_reentry_queue = next_queue
            _save_pending_reentry_queue(_pending_reentry_queue)

        _scheduler.add_task(
            "pending_reentry_submit",
            _submit_pending_reentry_queue,
            interval_minutes=_env_int("PENDING_REENTRY_CHECK_INTERVAL_MIN", 3, minimum=1),
        )

        # IBKR 连接健康检查（每10分钟）
        async def _ibkr_health_check():
            try:
                from src.broker_bridge import ibkr as _ibkr
                if not _ibkr.is_connected():
                    logger.warning("[Scheduler] IBKR断连，尝试重连...")
                    reconnected = await _ibkr.ensure_connected()
                    if reconnected:
                        logger.info("[Scheduler] IBKR重连成功")
                    else:
                        logger.error("[Scheduler] IBKR重连失败")
            except Exception as e:
                logger.warning("[Scheduler] IBKR健康检查失败: %s", e)
            # P0#10: 清理过期的待确认交易
            try:
                from src.bot.globals import _cleanup_pending_trades
                _cleanup_pending_trades()
            except Exception as e:
                logger.debug("[Scheduler] 清理待确认交易失败: %s", e)
        _scheduler.add_task("ibkr_health_check", _ibkr_health_check,
                            interval_minutes=3)

        _scheduler.start()
        logger.info(
            "[TradingSystem] Scheduler已启动 "
            "(重置09:00, 周守卫09:20, 资金09:25, 再平衡09:35, 复盘16:05, "
            "成交回写2min, 撤单5min, 重挂3min, IBKR健康3min)"
        )
    except Exception as e:
        logger.warning("[TradingSystem] Scheduler启动失败: %s", e)


async def stop_trading_system():
    """停止所有交易子系统"""
    if _position_monitor:
        await _position_monitor.stop()
    if _auto_trader:
        await _auto_trader.stop()
    if _quote_cache:
        await _quote_cache.stop()
    if _scheduler:
        _scheduler.stop()
    logger.info("[TradingSystem] 已停止")


# ============ 便捷访问函数 ============

def get_risk_manager():
    return _risk_manager

def get_position_monitor():
    return _position_monitor

def get_trading_pipeline():
    return _trading_pipeline

def get_auto_trader():
    return _auto_trader

def get_quote_cache():
    return _quote_cache

def get_rebalancer():
    return _rebalancer

def get_system_status():
    """获取完整系统状态"""
    parts = []

    # IBKR 连接状态
    try:
        from src.broker_bridge import ibkr as _ibkr
        parts.append(_ibkr.get_connection_status())
        if _ibkr.is_connected():
            remaining = _ibkr.budget - _ibkr.total_spent
            parts.append("预算: $%.2f / $%.2f (剩余$%.2f)" % (
                _ibkr.total_spent, _ibkr.budget, remaining))
        parts.append("")
    except Exception as e:
        logger.debug("[SystemStatus] IBKR状态获取失败: %s", e)

    if _risk_manager:
        parts.append(_risk_manager.format_status())
    if _position_monitor:
        parts.append("")
        parts.append(_position_monitor.format_status())
    if _auto_trader:
        parts.append("")
        parts.append(_auto_trader.format_status())
    if _pending_reentry_queue:
        parts.append("")
        parts.append("待重挂队列: %d 条" % len(_pending_reentry_queue))
    if _quote_cache:
        parts.append("")
        parts.append(_quote_cache.format_status())
    if _rebalancer and _rebalancer.get_targets():
        parts.append("")
        parts.append(_rebalancer.format_targets())
    if not parts:
        return "交易系统未初始化"
    return "\n".join(parts)
