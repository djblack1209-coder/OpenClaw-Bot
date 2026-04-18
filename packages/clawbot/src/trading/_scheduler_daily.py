"""
Trading — 每日/周度定时任务 + Scheduler 配置
风控重置、收盘复盘、行情刷新、再平衡检查、资金同步、周利润守卫、IBKR 健康检查、调度器启动
"""

import json
import logging
from datetime import time, timedelta

from src.notify_style import format_notice, kv, bullet
from src.utils import env_bool, env_int, env_float
from src.trading._helpers import _parse_datetime

logger = logging.getLogger(__name__)


# ============ 每日任务 ============


async def _daily_risk_reset():
    """每日风控计数器重置 + IBKR 预算重置 + AutoTrader 日交易计数重置"""
    import src.trading_system as _ts

    if _ts._risk_manager:
        _ts._risk_manager.reset_daily()
        logger.info("[Scheduler] 每日风控重置完成")
    # 同时重置 IBKR 预算追踪
    try:
        from src.broker_selector import ibkr as _ibkr

        _ibkr.reset_budget(_ibkr.budget)  # 保留当前预算额度，仅重置 total_spent
        logger.info("[Scheduler] IBKR预算已重置")
    except Exception as e:
        logger.warning("[Scheduler] IBKR预算重置失败: %s", e)
    # 重置 AutoTrader 日交易计数
    if _ts._auto_trader:
        _ts._auto_trader._today_trades = 0
        _ts._auto_trader._today_date = ""
        logger.info("[Scheduler] AutoTrader日交易计数已重置")


async def _eod_auto_review():
    """收盘自动复盘 — 生成每日盈亏报告并广播"""
    import src.trading_system as _ts

    if _ts._auto_trader and _ts._auto_trader.notify:
        try:
            from src.trading_journal import journal as tj

            # 生成每日盈亏报告
            today_pnl = tj.get_today_pnl()
            perf = tj.format_performance(days=1)
            open_trades = tj.get_open_trades()
            closed = tj.get_closed_trades(days=1, limit=20)

            # 收盘验证AI预测准确率
            try:
                pred_result = tj.validate_predictions()
                if pred_result.get("validated", 0) > 0:
                    logger.info(
                        "[Scheduler] 预测验证: %d/%d 正确 (%.1f%%)",
                        pred_result.get("correct", 0),
                        pred_result.get("validated", 0),
                        pred_result.get("accuracy", 0),
                    )
            except Exception as e:
                logger.debug("[Scheduler] 预测验证失败: %s", e)

            lines = ["-- 每日自动复盘 --\n"]
            lines.append("今日盈亏: $%.2f (%d笔交易)" % (today_pnl.get("pnl", 0), today_pnl.get("trades", 0)))

            if closed:
                lines.append("\n已平仓:")
                for t in closed:
                    sign = "+" if t.get("pnl", 0) >= 0 else ""
                    lines.append(
                        "  %s %s %s$%.2f" % (t.get("side", "?"), t.get("symbol", "?"), sign, abs(t.get("pnl", 0)))
                    )

            if open_trades:
                lines.append("\n持仓中: %d笔" % len(open_trades))
                for t in open_trades:
                    lines.append(
                        "  %s x%s 入场$%s" % (t.get("symbol", "?"), t.get("quantity", "?"), t.get("entry_price", "?"))
                    )

            lines.append("\n" + perf)
            lines.append("\n系统将在明日开盘自动继续交易。")

            await _ts._auto_trader._safe_notify("\n".join(lines))
            # EventBus: 广播每日复盘数据
            try:
                from src.core.event_bus import get_event_bus

                bus = get_event_bus()
                if bus:
                    await bus.publish(
                        "trade.daily_review",
                        {
                            "summary": "\n".join(lines),
                        },
                    )
            except Exception as e:
                logger.debug("静默异常: %s", e)
        except Exception as e:
            logger.error("[Scheduler] 自动复盘失败: %s", e)
            await _ts._auto_trader._safe_notify("收盘复盘生成失败: %s\n发送 /review 手动复盘" % e)


async def _refresh_quotes():
    """定期刷新监控中标的的行情缓存"""
    import src.trading_system as _ts

    if _ts._quote_cache and _ts._position_monitor:
        # 监控中的标的加入缓存
        syms = [p.symbol for p in _ts._position_monitor.positions.values()]
        if _ts._rebalancer and _ts._rebalancer.get_targets():
            syms += [t.symbol for t in _ts._rebalancer.get_targets()]
        if syms:
            _ts._quote_cache.watch(list(set(syms)))
            await _ts._quote_cache.refresh()


async def _daily_rebalance_check():
    """每日再平衡检查 — 如果组合偏离目标，发送通知"""
    import src.trading_system as _ts

    if _ts._rebalancer and _ts._rebalancer.get_targets() and _ts._auto_trader and _ts._auto_trader.notify:
        try:
            from src.invest_tools import portfolio

            positions = portfolio.get_positions()
            cash = portfolio.get_cash()
            quotes = _ts._quote_cache.get_all() if _ts._quote_cache else {}
            plan = _ts._rebalancer.analyze(positions, quotes, cash)
            if not plan.is_balanced and plan.trades_needed:
                await _ts._auto_trader._safe_notify("每日再平衡检查\n\n" + plan.format())
        except Exception as e:
            logger.warning("[Scheduler] 再平衡检查失败: %s", e)


async def _daily_capital_sync():
    """每日从 IBKR 同步实际资金到风控引擎"""
    import src.trading_system as _ts

    if _ts._risk_manager:
        try:
            from src.broker_selector import ibkr as _ibkr

            if _ibkr.is_connected():
                actual = await _ibkr.sync_capital()
                if actual > 0:
                    _ts._risk_manager.config.total_capital = actual
                    logger.info("[Scheduler] 资金同步: $%.2f", actual)
            else:
                logger.warning("[Scheduler] IBKR未连接，跳过资金同步")
        except Exception as e:
            logger.warning("[Scheduler] 资金同步失败: %s", e)


# ============ 周利润守卫 ============


async def _weekly_profit_guard():
    """周利润守卫 — 如果上周盈利未达标，强制停机"""
    import src.trading_system as _ts

    enabled = env_bool("WEEKLY_KILL_SWITCH", True)
    target = env_float("WEEKLY_PROFIT_TARGET", 50.0)
    if not enabled:
        return

    from src.utils import now_et

    now = now_et()

    # 从持久化存储恢复 kill switch 状态
    from src.trading_journal import journal as tj

    _saved_ks = tj.get_config("weekly_kill_switch_state")
    if _saved_ks:
        try:
            _ks_data = json.loads(_saved_ks)
            if _ks_data.get("triggered") and _ks_data.get("week_key"):
                # 检查是否仍在同一周（周一重置）
                current_week_start = now.date() - timedelta(days=now.weekday())
                if _ks_data["week_key"] >= current_week_start.isoformat():
                    if not _ts._weekly_kill_switch_triggered:
                        _ts._weekly_kill_switch_triggered = True
                        if _ts._auto_trader:
                            await _ts._auto_trader.stop()
                            try:
                                from src.auto_trader import TraderState

                                _ts._auto_trader.state = TraderState.PAUSED
                            except Exception as e:
                                logger.debug("[TradingSystem] 异常: %s", e)
                        logger.warning("[Scheduler] 从持久化恢复周度熔断状态 (week_key=%s)", _ks_data["week_key"])
                    return
        except Exception as e:
            logger.debug("[Scheduler] 解析 weekly_kill_switch_state 失败: %s", e)

    if now.weekday() != 0:  # 仅周一执行完整检查
        return

    current_week_start = now.date() - timedelta(days=now.weekday())
    last_week_start = current_week_start - timedelta(days=7)
    last_week_end = current_week_start - timedelta(days=1)
    week_key = f"{last_week_start.isoformat()}::{last_week_end.isoformat()}"
    if _ts._weekly_guard_last_week_key == week_key:
        return

    _ts._weekly_guard_last_week_key = week_key

    trades = tj.get_closed_trades(days=14, limit=1000)
    week_trades = []
    for trade in trades:
        exit_time = trade.get("exit_time")
        if not exit_time:
            continue
        try:
            exit_dt = _parse_datetime(str(exit_time))
            if not exit_dt:
                continue
            exit_date = exit_dt.date()
        except Exception as e:
            logger.debug("[TradingSystem] 异常: %s", e)
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
        _ts._weekly_kill_switch_triggered = False
        # 清除持久化状态
        tj.set_config("weekly_kill_switch_state", "")
        return

    _ts._weekly_kill_switch_triggered = True
    # 持久化 kill switch 状态
    tj.set_config(
        "weekly_kill_switch_state",
        json.dumps(
            {
                "triggered": True,
                "week_key": current_week_start.isoformat(),
                "week_pnl": week_pnl,
                "target": target,
            }
        ),
    )

    if _ts._auto_trader:
        await _ts._auto_trader.stop()
        try:
            from src.auto_trader import TraderState

            _ts._auto_trader.state = TraderState.PAUSED
        except Exception as e:
            logger.error("[Scheduler] 设置 AutoTrader PAUSED 状态失败: %s", e)

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
    if _ts._auto_trader and _ts._auto_trader.notify:
        try:
            await _ts._auto_trader._safe_notify(
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


# ============ IBKR 健康检查 ============

# 连续断连计数器 — 用于日志降频和智能退避
_ibkr_health_fail_count = 0


async def _ibkr_health_check():
    """定期检查 IBKR 连接状态，断连时自动重连。

    日志降频策略: 第1次打 WARNING，之后每10次(≈30分钟)打一次 WARNING，其余 DEBUG。
    避免 Gateway 未运行时每3分钟一条 WARNING/ERROR 造成日志洪泛。
    """
    global _ibkr_health_fail_count
    try:
        from src.broker_selector import ibkr as _ibkr

        if not _ibkr.is_connected():
            _ibkr_health_fail_count += 1
            # 降频: 第1次 + 每10次(≈30分钟)打 WARNING，其余 DEBUG
            if _ibkr_health_fail_count == 1 or _ibkr_health_fail_count % 10 == 0:
                logger.warning("[Scheduler] IBKR断连，尝试重连（第%d次）...", _ibkr_health_fail_count)
            else:
                logger.debug("[Scheduler] IBKR断连，尝试重连（第%d次）...", _ibkr_health_fail_count)
            reconnected = await _ibkr.ensure_connected()
            if reconnected:
                logger.info("[Scheduler] IBKR重连成功（断连共%d轮）", _ibkr_health_fail_count)
                _ibkr_health_fail_count = 0
            # 失败不再额外打 ERROR — connect() 方法内部已有降频日志
        else:
            if _ibkr_health_fail_count > 0:
                logger.info("[Scheduler] IBKR连接已恢复（曾断连%d轮）", _ibkr_health_fail_count)
            _ibkr_health_fail_count = 0
    except Exception as e:
        logger.warning("[Scheduler] IBKR健康检查失败: %s", e)
    # 清理过期的待确认交易
    try:
        from src.bot.globals import _cleanup_pending_trades

        _cleanup_pending_trades()
    except Exception as e:
        logger.debug("[Scheduler] 清理待确认交易失败: %s", e)


# ============ Scheduler 配置与启动 ============


async def _setup_scheduler():
    """配置并启动所有定时任务"""
    import src.trading_system as _ts
    from src.trading._scheduler_tasks import (
        _reconcile_ibkr_entry_fills,
        _cancel_stale_pending_entries,
        _submit_pending_reentry_queue,
    )

    try:
        from src.scheduler import Scheduler

        _ts._scheduler = Scheduler()

        _ts._scheduler.add_task("daily_risk_reset", _daily_risk_reset, schedule_time=time(9, 0))
        _ts._scheduler.add_task("eod_auto_review", _eod_auto_review, schedule_time=time(16, 5))
        _ts._scheduler.add_task("quote_refresh", _refresh_quotes, interval_minutes=5)
        _ts._scheduler.add_task("daily_rebalance", _daily_rebalance_check, schedule_time=time(9, 35))
        _ts._scheduler.add_task("daily_capital_sync", _daily_capital_sync, schedule_time=time(9, 25))
        _ts._scheduler.add_task(
            "weekly_profit_guard",
            _weekly_profit_guard,
            schedule_time=time(9, 20),
        )
        _ts._scheduler.add_task(
            "ibkr_fill_reconcile",
            _reconcile_ibkr_entry_fills,
            interval_minutes=env_int("IBKR_FILL_RECONCILE_INTERVAL_MIN", 2, minimum=1),
        )
        _ts._scheduler.add_task(
            "pending_entry_cancel",
            _cancel_stale_pending_entries,
            interval_minutes=env_int("PENDING_ENTRY_CANCEL_CHECK_INTERVAL_MIN", 5, minimum=1),
        )
        _ts._scheduler.add_task(
            "pending_reentry_submit",
            _submit_pending_reentry_queue,
            interval_minutes=env_int("PENDING_REENTRY_CHECK_INTERVAL_MIN", 3, minimum=1),
        )
        _ts._scheduler.add_task(
            "ibkr_health_check",
            _ibkr_health_check,
            interval_minutes=env_int("IBKR_HEALTH_CHECK_INTERVAL_MIN", 3, minimum=1),
        )

        # 每日成本报告 — 23:00 ET 发送当日 LLM 花费汇总
        async def _cost_daily_report():
            try:
                from src.core.cost_control import get_cost_controller
                from src.core.event_bus import get_event_bus

                cc = get_cost_controller()
                if cc:
                    bus = get_event_bus()
                    if bus:
                        await bus.publish(
                            "system.cost_daily_report",
                            {
                                "daily_spend": cc.get_daily_spend(),
                                "report": cc.get_weekly_report() if hasattr(cc, "get_weekly_report") else {},
                            },
                        )
            except Exception as e:
                logger.debug("[Scheduler] 每日成本报告失败: %s", e)

        _ts._scheduler.add_task("cost_daily_report", _cost_daily_report, schedule_time=time(23, 0))

        _ts._scheduler.start()
        logger.info(
            "[TradingSystem] Scheduler已启动 "
            "(重置09:00, 周守卫09:20, 资金09:25, 再平衡09:35, 复盘16:05, "
            "成交回写2min, 撤单5min, 重挂3min, IBKR健康3min)"
        )
    except Exception as e:
        logger.warning("[TradingSystem] Scheduler启动失败: %s", e)
