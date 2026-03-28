"""
Trading — 生命周期管理
系统启停、状态恢复、便捷访问器、系统状态报告
"""
import logging

from src.trading._helpers import (
    _parse_datetime,
    _load_pending_reentry_queue,
)

logger = logging.getLogger(__name__)


# ============ 状态恢复（启动时调用） ============


async def _restore_open_positions():
    """从 journal 恢复未平仓持仓到 PositionMonitor"""
    import src.trading_system as _ts

    if _ts._position_monitor and _ts._risk_manager:
        try:
            from src.trading_journal import journal as tj
            from src.position_monitor import MonitoredPosition
            from src.utils import now_et
            open_trades = tj.get_open_trades()
            for t in open_trades:
                try:
                    pos = MonitoredPosition(
                        trade_id=t["id"],
                        symbol=t["symbol"],
                        side=t.get("side", "BUY"),
                        quantity=float(t.get("quantity", 0)),
                        entry_price=float(t.get("entry_price", 0)),
                        entry_time=_parse_datetime(t["created_at"]) or now_et() if t.get("created_at") else now_et(),
                        stop_loss=float(t.get("stop_loss", 0) or 0),
                        take_profit=float(t.get("take_profit", 0) or 0),
                        trailing_stop_pct=0.03,
                    )
                    _ts._position_monitor.add_position(pos)
                except Exception as e:
                    logger.warning("[TradingSystem] 恢复持仓 %s 失败: %s", t.get("symbol"), e)
            if open_trades:
                logger.info("[TradingSystem] 从journal恢复了 %d 个持仓到监控器", len(open_trades))
        except Exception as e:
            logger.error("[TradingSystem] 恢复持仓失败: %s", e)


async def _restore_today_pnl():
    """从 journal 恢复今日PnL到 RiskManager"""
    import src.trading_system as _ts

    if _ts._risk_manager:
        try:
            from src.trading_journal import journal as tj
            today_data = tj.get_today_pnl()
            _ts._risk_manager._today_pnl = today_data.get("pnl", 0)
            _ts._risk_manager._today_trades = today_data.get("trades", 0)
            logger.info("[TradingSystem] 恢复今日PnL: $%.2f (%d笔)",
                        _ts._risk_manager._today_pnl, _ts._risk_manager._today_trades)
        except Exception as e:
            logger.error("[TradingSystem] 恢复PnL失败: %s", e)


async def _restore_autotrader_count():
    """恢复今日已执行交易数到 AutoTrader"""
    import src.trading_system as _ts

    if _ts._auto_trader:
        try:
            from src.trading_journal import journal as tj
            from src.utils import today_et_str
            today_str = today_et_str()
            today_trades = tj.get_today_pnl().get("trades", 0)
            if today_trades > 0:
                _ts._auto_trader._today_trades = today_trades
                _ts._auto_trader._today_date = today_str
                logger.info("[TradingSystem] 恢复AutoTrader今日交易计数: %d笔", today_trades)
        except Exception as e:
            logger.error("[TradingSystem] 恢复AutoTrader交易计数失败: %s", e)


async def _sync_ibkr_capital():
    """从 IBKR 同步实际资金到 RiskManager"""
    import src.trading_system as _ts

    if _ts._risk_manager:
        try:
            from src.broker_selector import ibkr as _ibkr
            if _ibkr.is_connected():
                actual_capital = await _ibkr.sync_capital()
                if actual_capital > 0:
                    _ts._risk_manager.config.total_capital = actual_capital
                    logger.info("[TradingSystem] 从IBKR同步资金: $%.2f", actual_capital)
        except Exception as e:
            logger.warning("[TradingSystem] IBKR资金同步失败，使用默认值: %s", e)


# ============ 系统启停 ============


async def start_trading_system():
    """启动持仓监控和自动交易（在 main() 中调用）"""
    import src.trading_system as _ts
    from src.trading._scheduler_daily import _setup_scheduler

    if not _ts._initialized:
        logger.error("[TradingSystem] 未初始化，无法启动")
        return

    # 1. 恢复持久化状态
    _ts._pending_reentry_queue = _load_pending_reentry_queue()
    if _ts._pending_reentry_queue:
        logger.info("[TradingSystem] 恢复待重挂队列: %d 条", len(_ts._pending_reentry_queue))

    await _restore_open_positions()
    await _restore_today_pnl()
    await _restore_autotrader_count()

    # 2. 启动持仓监控
    if _ts._position_monitor:
        await _ts._position_monitor.start()
        logger.info("[TradingSystem] 持仓监控器已启动")

    # 3. 同步 IBKR 资金
    await _sync_ibkr_capital()

    # 4. 启动 AutoTrader
    if _ts._auto_trader:
        await _ts._auto_trader.start()
        logger.info("[TradingSystem] AutoTrader 已自动启动 (auto_mode=%s, 间隔=%d分钟)",
                    _ts._auto_trader.auto_mode, _ts._auto_trader.scan_interval)

    # 5. 启动定时任务调度器
    await _setup_scheduler()


async def stop_trading_system():
    """停止所有交易子系统"""
    import src.trading_system as _ts

    if _ts._position_monitor:
        await _ts._position_monitor.stop()
    if _ts._auto_trader:
        await _ts._auto_trader.stop()
    if _ts._quote_cache:
        await _ts._quote_cache.stop()
    if _ts._scheduler:
        _ts._scheduler.stop()
    logger.info("[TradingSystem] 已停止")


# ============ 便捷访问函数 ============


def get_risk_manager():
    """获取风控引擎实例"""
    import src.trading_system as _ts
    return _ts._risk_manager


def get_position_monitor():
    """获取持仓监控器实例"""
    import src.trading_system as _ts
    return _ts._position_monitor


def get_trading_pipeline():
    """获取交易执行管道实例"""
    import src.trading_system as _ts
    return _ts._trading_pipeline


def get_auto_trader():
    """获取自主交易调度器实例"""
    import src.trading_system as _ts
    return _ts._auto_trader


def get_quote_cache():
    """获取行情缓存实例"""
    import src.trading_system as _ts
    return _ts._quote_cache


def get_rebalancer():
    """获取再平衡器实例"""
    import src.trading_system as _ts
    return _ts._rebalancer


def get_system_status():
    """获取完整系统状态（用于 /status 命令展示）"""
    import src.trading_system as _ts

    parts = []

    # IBKR 连接状态
    try:
        from src.broker_selector import ibkr as _ibkr
        parts.append(_ibkr.get_connection_status())
        if _ibkr.is_connected():
            remaining = _ibkr.budget - _ibkr.total_spent
            parts.append("预算: $%.2f / $%.2f (剩余$%.2f)" % (
                _ibkr.total_spent, _ibkr.budget, remaining))
        parts.append("")
    except Exception as e:
        logger.debug("[SystemStatus] IBKR状态获取失败: %s", e)

    if _ts._risk_manager:
        parts.append(_ts._risk_manager.format_status())
    if _ts._position_monitor:
        parts.append("")
        parts.append(_ts._position_monitor.format_status())
    if _ts._auto_trader:
        parts.append("")
        parts.append(_ts._auto_trader.format_status())
    if _ts._pending_reentry_queue:
        parts.append("")
        parts.append("待重挂队列: %d 条" % len(_ts._pending_reentry_queue))
    if _ts._quote_cache:
        parts.append("")
        parts.append(_ts._quote_cache.format_status())
    if _ts._rebalancer and _ts._rebalancer.get_targets():
        parts.append("")
        parts.append(_ts._rebalancer.format_targets())
    if not parts:
        return "交易系统未初始化"
    return "\n".join(parts)
