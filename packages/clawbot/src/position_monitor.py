"""
ClawBot 持仓监控器 v2.0
自动监控所有持仓，实时检测止损/止盈/追踪止损触发

v2.0 变更 (2026-03-24):
  - 搬运 PanWatch (MIT) 通知节流模式 — 按 symbol+级别 冷却
  - 新增接近止损预警 (proximity alert): 80%/50%/20% 三级预警
  - 接入 EventBus 发布 trade.risk_alert 事件
  - 止损调整通知 (breakeven/trailing 上移推送到用户)
  - 激活 risk_manager.update_position_pnl() dead code
  - Bug fix: line 313 now_et() → _now_et()

功能：
1. 定时轮询持仓价格（可配置间隔）
2. 止损触发 -> 自动平仓
3. 止盈触发 -> 自动平仓
4. 追踪止损 -> 价格上涨时自动上移止损位
5. 时间止损 -> 持仓超时自动平仓
6. 接近止损预警 -> Telegram + EventBus 分级推送 (v2.0)
7. 止损调整通知 -> 保本/追踪上移推送 (v2.0)
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

from src.utils import now_et as _now_et_fn


def _now_et() -> datetime:
    return _now_et_fn()


logger = logging.getLogger(__name__)


class ExitReason(Enum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    TIME_STOP = "time_stop"
    MANUAL = "manual"
    DAILY_LIMIT = "daily_limit"
    CIRCUIT_BREAKER = "circuit_breaker"
    PARTIAL_TAKE_PROFIT = "partial_take_profit"


# ── v2.0: 接近止损预警级别 (搬运 PanWatch throttle 模式) ───────


class AlertLevel(Enum):
    """止损接近预警级别 — 距止损距离越近级别越高"""

    WARN = "warn"  # 距止损 ≤ 80% (已消耗 80% 的安全距离)
    DANGER = "danger"  # 距止损 ≤ 50%
    CRITICAL = "critical"  # 距止损 ≤ 20%


# 预警阈值: (距止损百分比, 级别, 冷却秒数)
_ALERT_THRESHOLDS = [
    (0.20, AlertLevel.CRITICAL, 300),  # 距止损≤20% → 5分钟冷却
    (0.50, AlertLevel.DANGER, 900),  # 距止损≤50% → 15分钟冷却
    (0.80, AlertLevel.WARN, 1800),  # 距止损≤80% → 30分钟冷却
]

_ALERT_EMOJI = {
    AlertLevel.WARN: "🟡",
    AlertLevel.DANGER: "🟠",
    AlertLevel.CRITICAL: "🔴",
}


@dataclass
class MonitoredPosition:
    trade_id: int
    symbol: str
    side: str
    quantity: float
    entry_price: float
    entry_time: datetime
    stop_loss: float = 0
    take_profit: float = 0
    trailing_stop_pct: float = 0
    trailing_stop_price: float = 0
    highest_price: float = 0
    max_hold_hours: float = 0
    current_price: float = 0
    unrealized_pnl: float = 0
    unrealized_pnl_pct: float = 0
    last_check: Optional[datetime] = None
    atr: float = 0  # ATR值，用于动态尾部止损
    breakeven_triggered: bool = False  # 保本止损是否已触发
    partial_exit_done: bool = False  # 分批止盈是否已执行（50%在1.5R）
    original_quantity: float = 0  # 原始数量（分批止盈后quantity会减少）
    # v2.0: 止损调整事件 (由 PositionMonitor 消费并推送通知)
    _pending_adjustments: List[str] = field(default_factory=list)

    def update_price(self, price: float):
        self.current_price = price
        self.last_check = _now_et()
        if self.side == "BUY":
            self.unrealized_pnl = (price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.quantity
        cost = self.entry_price * self.quantity
        self.unrealized_pnl_pct = (self.unrealized_pnl / cost * 100) if cost > 0 else 0

        if self.side == "BUY":
            # 保本止损：当盈利 >= 1R（入场价 - 原始止损）时，止损移到入场价 + 小缓冲
            if not self.breakeven_triggered and self.stop_loss > 0:
                risk_per_share = self.entry_price - self.stop_loss
                if risk_per_share > 0 and price >= self.entry_price + risk_per_share:
                    buffer = self.entry_price * 0.002  # 0.2% 缓冲防止噪音触发
                    new_stop = round(self.entry_price + buffer, 2)
                    if new_stop > self.stop_loss:
                        old = self.stop_loss
                        self.stop_loss = new_stop
                        self.breakeven_triggered = True
                        # v2.0: 记录调整事件供通知
                        self._pending_adjustments.append(
                            "🛡️ %s 保本止损触发\n止损上移: $%.2f → $%.2f\n当前价: $%.2f (盈利达1R)"
                            % (self.symbol, old, new_stop, price)
                        )
                        logger.info(
                            "[Monitor] %s 保本止损触发: $%.2f -> $%.2f (盈利达1R, 当前$%.2f)",
                            self.symbol,
                            old,
                            new_stop,
                            price,
                        )

        if self.side == "BUY":
            # BUY方向：价格创新高时上移追踪止损
            if price > self.highest_price:
                self.highest_price = price
                # ATR 动态尾部止损（优先）或固定百分比尾部止损
                if self.atr > 0:
                    new_trailing = round(price - 2.0 * self.atr, 2)
                elif self.trailing_stop_pct > 0:
                    new_trailing = round(price * (1 - self.trailing_stop_pct), 2)
                else:
                    new_trailing = 0

                if new_trailing > 0 and new_trailing > self.trailing_stop_price:
                    old = self.trailing_stop_price
                    self.trailing_stop_price = new_trailing
                    if old > 0:
                        # v2.0: 记录显著调整 (上移>0.5%) 供通知
                        move_pct = ((new_trailing - old) / old * 100) if old > 0 else 0
                        if move_pct >= 0.5:
                            self._pending_adjustments.append(
                                "📈 %s 追踪止损上移\n$%.2f → $%.2f (+%.1f%%)\n最高价: $%.2f"
                                % (self.symbol, old, new_trailing, move_pct, price)
                            )
                        logger.info(
                            "[Monitor] %s 追踪止损上移: $%.2f -> $%.2f (最高价$%.2f%s)",
                            self.symbol,
                            old,
                            self.trailing_stop_price,
                            price,
                            " ATR=%.2f" % self.atr if self.atr > 0 else "",
                        )
        else:
            # SELL方向（做空）：价格创新低时下移追踪止损
            # highest_price 在SELL模式下复用为 lowest_price（最低价格）
            if self.highest_price == 0 or price < self.highest_price:
                self.highest_price = price  # 复用字段记录最低价
                # ATR 动态追踪止损（在做空方向，止损在价格上方）
                if self.atr > 0:
                    new_trailing = round(price + 2.0 * self.atr, 2)
                elif self.trailing_stop_pct > 0:
                    new_trailing = round(price * (1 + self.trailing_stop_pct), 2)
                else:
                    new_trailing = 0

                # SELL方向追踪止损应越来越低（即止损价格下移）
                if new_trailing > 0 and (self.trailing_stop_price == 0 or new_trailing < self.trailing_stop_price):
                    old = self.trailing_stop_price
                    self.trailing_stop_price = new_trailing
                    if old > 0:
                        move_pct = ((old - new_trailing) / old * 100) if old > 0 else 0
                        if move_pct >= 0.5:
                            self._pending_adjustments.append(
                                "📉 %s 空单追踪止损下移\n$%.2f → $%.2f (-%.1f%%)\n最低价: $%.2f"
                                % (self.symbol, old, new_trailing, move_pct, price)
                            )
                        logger.info(
                            "[Monitor] %s 空单追踪止损下移: $%.2f -> $%.2f (最低价$%.2f%s)",
                            self.symbol,
                            old,
                            self.trailing_stop_price,
                            price,
                            " ATR=%.2f" % self.atr if self.atr > 0 else "",
                        )

    def drain_adjustments(self) -> List[str]:
        """取出并清空待通知的止损调整事件"""
        msgs = list(self._pending_adjustments)
        self._pending_adjustments.clear()
        return msgs


@dataclass
class ExitSignal:
    position: MonitoredPosition
    reason: ExitReason
    trigger_price: float
    message: str


class PositionMonitor:
    """持仓监控器 - 异步循环检查止损/止盈/追踪止损"""

    def __init__(
        self,
        check_interval: int = 30,
        get_quote_func: Optional[Callable] = None,
        execute_sell_func: Optional[Callable] = None,
        notify_func: Optional[Callable] = None,
        risk_manager: Any = None,
        journal: Any = None,
    ):
        self.check_interval = check_interval
        self.get_quote = get_quote_func
        self.execute_sell = execute_sell_func
        self.notify = notify_func
        self.risk_manager = risk_manager
        self.journal = journal
        self.positions: Dict[int, MonitoredPosition] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._exit_history: List[ExitSignal] = []
        self._exit_retry_count: Dict[int, int] = {}  # trade_id -> 重试次数
        self._max_exit_retries = 3  # 最大重试次数
        # v2.0: 通知节流 (搬运 PanWatch throttle 模式)
        # key: (trade_id, AlertLevel) -> last_alert_timestamp
        self._alert_cooldowns: Dict[tuple, float] = {}
        logger.info("[PositionMonitor] 初始化完成 | 检查间隔=%ds", check_interval)

    # ============ 持仓管理 ============

    def add_position(self, pos: MonitoredPosition) -> None:
        self.positions[pos.trade_id] = pos
        pos.highest_price = pos.entry_price
        if pos.original_quantity <= 0:
            pos.original_quantity = pos.quantity
        if pos.trailing_stop_pct > 0 and pos.side == "BUY":
            pos.trailing_stop_price = round(pos.entry_price * (1 - pos.trailing_stop_pct), 2)
        logger.info(
            "[Monitor] 添加监控: %s %s x%s @ $%s | SL=$%s TP=$%s TS=%.1f%%",
            pos.symbol,
            pos.side,
            pos.quantity,
            pos.entry_price,
            pos.stop_loss,
            pos.take_profit,
            pos.trailing_stop_pct * 100,
        )

    def remove_position(self, trade_id: int) -> None:
        if trade_id in self.positions:
            pos = self.positions.pop(trade_id)
            logger.info("[Monitor] 移除监控: %s (trade #%d)", pos.symbol, trade_id)

    def update_stop_loss(self, trade_id: int, new_stop: float) -> None:
        if trade_id in self.positions:
            old = self.positions[trade_id].stop_loss
            self.positions[trade_id].stop_loss = new_stop
            logger.info(
                "[Monitor] %s 止损更新: $%.2f -> $%.2f",
                self.positions[trade_id].symbol,
                old,
                new_stop,
            )

    def update_take_profit(self, trade_id: int, new_tp: float) -> None:
        if trade_id in self.positions:
            old = self.positions[trade_id].take_profit
            self.positions[trade_id].take_profit = new_tp
            logger.info(
                "[Monitor] %s 止盈更新: $%.2f -> $%.2f",
                self.positions[trade_id].symbol,
                old,
                new_tp,
            )

    # ============ 监控循环 ============

    async def start(self) -> None:
        if self._running:
            logger.warning("[Monitor] 已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

        def _monitor_done(t):
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.critical("[PositionMonitor] 监控循环崩溃: %s", exc)

        self._task.add_done_callback(_monitor_done)
        logger.info("[PositionMonitor] 监控循环已启动")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError as e:  # noqa: F841
                pass
        logger.info("[PositionMonitor] 监控循环已停止")

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                if self.positions:
                    await self._check_all_positions()
            except asyncio.CancelledError:
                logger.info("[Monitor] 监控循环被取消")
                raise  # 让 stop() 正常结束
            except Exception as e:
                logger.error("[Monitor] 监控循环异常: %s — 将在 %ds 后重试", e, self.check_interval, exc_info=True)
            await asyncio.sleep(self.check_interval)

    async def _check_all_positions(self) -> None:
        if not self.get_quote:
            return
        symbols = list(set(p.symbol for p in self.positions.values()))
        quotes: Dict[str, float] = {}
        try:
            results = await asyncio.gather(
                *[self.get_quote(sym) for sym in symbols],
                return_exceptions=True,
            )
            for sym, result in zip(symbols, results):
                if isinstance(result, dict) and "price" in result:
                    quotes[sym] = result["price"]
        except Exception as e:
            logger.error("[Monitor] 批量获取行情失败: %s", e)
            return

        exit_signals: List[ExitSignal] = []
        for trade_id, pos in list(self.positions.items()):
            try:
                price = quotes.get(pos.symbol)
                if price is None:
                    continue
                pos.update_price(price)

                # v2.0: 推送止损调整通知 (breakeven/trailing 上移)
                adjustments = pos.drain_adjustments()
                for adj_msg in adjustments:
                    await self._send_alert(adj_msg)

                # v2.0: 接近止损预警 (proximity alert)
                await self._check_proximity_alert(pos)

                # v2.0: 激活 risk_manager.update_position_pnl() (原 dead code)
                if self.risk_manager and hasattr(self.risk_manager, "update_position_pnl"):
                    try:
                        pnl_warning = self.risk_manager.update_position_pnl(pos.symbol, pos.unrealized_pnl)
                        if pnl_warning and pnl_warning.get("action"):
                            await self._send_alert(
                                "⚠️ %s 利润回撤预警\n%s\n当前浮盈: $%.2f"
                                % (pos.symbol, pnl_warning.get("action", ""), pos.unrealized_pnl)
                            )
                    except Exception as e:
                        logger.warning("[Monitor] 利润回撤预警检查失败 (%s): %s", pos.symbol, e)

                signal = self._check_exit_conditions(pos)
                if signal:
                    exit_signals.append(signal)
            except Exception as e:
                logger.error("[Monitor] 检查持仓 %s (trade #%d) 异常: %s", pos.symbol, trade_id, e, exc_info=True)

        for signal in exit_signals:
            await self._execute_exit(signal)

        # 定期清理过期的预警冷却记录（防止内存泄漏）
        self._cleanup_stale_cooldowns()

    def _check_exit_conditions(self, pos: MonitoredPosition) -> Optional[ExitSignal]:
        price = pos.current_price

        if pos.side == "BUY":
            # 止损
            if pos.stop_loss > 0 and price <= pos.stop_loss:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.STOP_LOSS,
                    trigger_price=price,
                    message=(
                        "止损触发! %s 当前$%.2f <= 止损$%.2f | 亏损$%.2f (%.1f%%)"
                        % (pos.symbol, price, pos.stop_loss, pos.unrealized_pnl, pos.unrealized_pnl_pct)
                    ),
                )
            # 追踪止损
            if pos.trailing_stop_price > 0 and price <= pos.trailing_stop_price:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.TRAILING_STOP,
                    trigger_price=price,
                    message=(
                        "追踪止损触发! %s 当前$%.2f <= 追踪$%.2f | 最高$%.2f | 盈亏$%.2f (%.1f%%)"
                        % (
                            pos.symbol,
                            price,
                            pos.trailing_stop_price,
                            pos.highest_price,
                            pos.unrealized_pnl,
                            pos.unrealized_pnl_pct,
                        )
                    ),
                )
            # 分批止盈: 盈利达1.5R时平掉50%，剩余用尾部止损
            if not pos.partial_exit_done and pos.stop_loss > 0 and pos.quantity >= 2:
                risk_per_share = pos.entry_price - pos.stop_loss
                if risk_per_share > 0 and price >= pos.entry_price + risk_per_share * 1.5:
                    return ExitSignal(
                        position=pos,
                        reason=ExitReason.PARTIAL_TAKE_PROFIT,
                        trigger_price=price,
                        message=(
                            "分批止盈触发! %s 盈利达1.5R | 当前$%.2f | 平仓50%% (%d股) | 盈亏$%.2f"
                            % (pos.symbol, price, int(pos.quantity * 0.5), pos.unrealized_pnl)
                        ),
                    )
            # 止盈（仅对未分批止盈的持仓触发全仓止盈）
            if pos.take_profit > 0 and price >= pos.take_profit:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.TAKE_PROFIT,
                    trigger_price=price,
                    message=(
                        "止盈触发! %s 当前$%.2f >= 止盈$%.2f | 盈利$%.2f (%.1f%%)"
                        % (pos.symbol, price, pos.take_profit, pos.unrealized_pnl, pos.unrealized_pnl_pct)
                    ),
                )

        elif pos.side == "SELL":
            # ── SELL方向（做空）止损止盈 ──
            # 做空止损：价格上涨超过止损价时触发（方向反转）
            if pos.stop_loss > 0 and price >= pos.stop_loss:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.STOP_LOSS,
                    trigger_price=price,
                    message=(
                        "空单止损触发! %s 当前$%.2f >= 止损$%.2f | 亏损$%.2f (%.1f%%)"
                        % (pos.symbol, price, pos.stop_loss, pos.unrealized_pnl, pos.unrealized_pnl_pct)
                    ),
                )
            # 做空追踪止损：价格回涨超过追踪止损价时触发
            if pos.trailing_stop_price > 0 and price >= pos.trailing_stop_price:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.TRAILING_STOP,
                    trigger_price=price,
                    message=(
                        "空单追踪止损触发! %s 当前$%.2f >= 追踪$%.2f | 最低$%.2f | 盈亏$%.2f (%.1f%%)"
                        % (
                            pos.symbol,
                            price,
                            pos.trailing_stop_price,
                            pos.highest_price,
                            pos.unrealized_pnl,
                            pos.unrealized_pnl_pct,
                        )
                    ),
                )
            # 做空分批止盈：盈利达1.5R时平掉50%
            if not pos.partial_exit_done and pos.stop_loss > 0 and pos.quantity >= 2:
                risk_per_share = pos.stop_loss - pos.entry_price  # SELL: 风险 = 止损价 - 入场价
                if risk_per_share > 0 and price <= pos.entry_price - risk_per_share * 1.5:
                    return ExitSignal(
                        position=pos,
                        reason=ExitReason.PARTIAL_TAKE_PROFIT,
                        trigger_price=price,
                        message=(
                            "空单分批止盈触发! %s 盈利达1.5R | 当前$%.2f | 平仓50%% (%d股) | 盈亏$%.2f"
                            % (pos.symbol, price, int(pos.quantity * 0.5), pos.unrealized_pnl)
                        ),
                    )
            # 做空止盈：价格下跌到目标价时触发
            if pos.take_profit > 0 and price <= pos.take_profit:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.TAKE_PROFIT,
                    trigger_price=price,
                    message=(
                        "空单止盈触发! %s 当前$%.2f <= 止盈$%.2f | 盈利$%.2f (%.1f%%)"
                        % (pos.symbol, price, pos.take_profit, pos.unrealized_pnl, pos.unrealized_pnl_pct)
                    ),
                )

        # 时间止损（仅对亏损/持平持仓触发，盈利持仓转为纯尾部止损）
        if pos.max_hold_hours > 0:
            # HI-570: 安全处理 naive/aware datetime 混合，防止 TypeError
            entry = pos.entry_time
            now = _now_et()
            if entry.tzinfo is None and now.tzinfo is not None:
                # entry 是 naive，now 是 aware → 统一为 naive 比较
                now = now.replace(tzinfo=None)
            elif entry.tzinfo is not None and now.tzinfo is None:
                # entry 是 aware，now 是 naive → 统一为 naive 比较
                entry = entry.replace(tzinfo=None)
            hold_hours = (now - entry).total_seconds() / 3600
            if hold_hours >= pos.max_hold_hours:
                if pos.unrealized_pnl <= 0:
                    # 亏损/持平: 触发时间止损平仓
                    return ExitSignal(
                        position=pos,
                        reason=ExitReason.TIME_STOP,
                        trigger_price=price,
                        message=(
                            "时间止损触发! %s 持仓%.1f小时 >= 上限%.0f小时 | 亏损$%.2f (%.1f%%)"
                            % (pos.symbol, hold_hours, pos.max_hold_hours, pos.unrealized_pnl, pos.unrealized_pnl_pct)
                        ),
                    )
                else:
                    # 盈利: 不平仓，但取消时间止损，完全依赖尾部止损
                    if pos.max_hold_hours > 0:
                        logger.info(
                            "[Monitor] %s 超时但盈利$%.2f，取消时间止损，转为纯尾部止损",
                            pos.symbol,
                            pos.unrealized_pnl,
                        )
                        pos.max_hold_hours = 0  # 取消时间止损，不再检查

        # 日亏损限额熔断：当日累计亏损触及限额时，强制平掉亏损持仓
        if self.risk_manager and pos.unrealized_pnl < 0:
            try:
                today_pnl = getattr(self.risk_manager, "_today_pnl", 0)
                daily_limit = getattr(self.risk_manager, "config", None)
                if daily_limit:
                    limit_val = getattr(daily_limit, "daily_loss_limit", 100)
                    # 已实现亏损 + 当前浮亏 超过限额
                    if today_pnl + pos.unrealized_pnl <= -limit_val:
                        return ExitSignal(
                            position=pos,
                            reason=ExitReason.DAILY_LIMIT,
                            trigger_price=price,
                            message=(
                                "日亏损限额熔断! %s 浮亏$%.2f + 今日已亏$%.2f >= 限额$%.0f | 强制平仓"
                                % (pos.symbol, pos.unrealized_pnl, today_pnl, limit_val)
                            ),
                        )
            except Exception as e:
                logger.warning("[Monitor] 日亏损检查异常: %s", e)

        return None

    async def _execute_exit(self, signal: ExitSignal) -> None:
        pos = signal.position
        trade_id = pos.trade_id
        logger.warning("[Monitor] %s", signal.message)

        # 检查重试次数，超过上限则标记为需手动处理并停止重试
        retry_count = self._exit_retry_count.get(trade_id, 0)
        if retry_count >= self._max_exit_retries:
            logger.error(
                "[Monitor] %s (trade #%d) 平仓已失败%d次，停止重试，需手动处理", pos.symbol, trade_id, retry_count
            )
            if self.notify:
                await self.notify(
                    "🚨 紧急：平仓多次失败 🚨\n\n"
                    "标的: %s\n"
                    "数量: %d 股\n"
                    "入场价: $%.2f\n"
                    "当前价: $%.2f\n"
                    "浮动盈亏: $%.2f (%.1f%%)\n"
                    "触发原因: %s\n\n"
                    "已重试 %d 次均失败，系统已停止自动平仓。\n"
                    "⚠️ 请立即手动卖出！"
                    % (
                        pos.symbol,
                        int(pos.quantity),
                        pos.entry_price,
                        pos.current_price,
                        pos.unrealized_pnl,
                        pos.unrealized_pnl_pct,
                        signal.reason.value,
                        retry_count,
                    )
                )
            # 移除监控，避免无限重试通知轰炸
            self.remove_position(trade_id)
            self._exit_retry_count.pop(trade_id, None)
            return

        # 1. 券商卖出
        sell_result = None
        # 分批止盈只卖50%
        sell_qty = pos.quantity
        is_partial = signal.reason == ExitReason.PARTIAL_TAKE_PROFIT
        if is_partial:
            sell_qty = max(1, int(pos.quantity * 0.5))

        if self.execute_sell:
            try:
                sell_result = await self.execute_sell(
                    symbol=pos.symbol,
                    quantity=sell_qty,
                    order_type="MKT",
                    decided_by="PositionMonitor",
                    reason="%s: %s" % (signal.reason.value, signal.message),
                )
                logger.info("[Monitor] 平仓执行结果: %s", sell_result)
            except Exception as e:
                self._exit_retry_count[trade_id] = retry_count + 1
                logger.error("[Monitor] 平仓执行失败 (第%d次): %s", retry_count + 1, e)
                if self.notify:
                    await self.notify(
                        "!! 平仓执行失败 (第%d/%d次) !!\n%s\n错误: %s\n%s秒后重试..."
                        % (retry_count + 1, self._max_exit_retries, signal.message, e, self.check_interval)
                    )
                return

        # 2. 更新交易日志
        if self.journal:
            try:
                exit_price = signal.trigger_price
                if sell_result and sell_result.get("avg_price", 0) > 0:
                    exit_price = sell_result["avg_price"]
                if is_partial:
                    # 分批止盈不关闭交易，只记录部分平仓
                    logger.info("[Monitor] %s 分批止盈记录: %d股 @ $%.2f", pos.symbol, sell_qty, exit_price)
                else:
                    self.journal.close_trade(
                        trade_id=trade_id,
                        exit_price=exit_price,
                        exit_reason=signal.reason.value,
                    )
            except Exception as e:
                logger.error("[Monitor] 更新交易日志失败: %s", e)

        # 3. 更新风控（用实际成交价计算PnL，而非报价浮亏）
        if self.risk_manager:
            # 部分平仓时按比例计算 PnL，避免用全仓浮亏误报
            actual_pnl = pos.unrealized_pnl * (sell_qty / pos.quantity) if pos.quantity > 0 else 0
            if sell_result and sell_result.get("avg_price", 0) > 0:
                actual_exit = sell_result["avg_price"]
                if pos.side == "BUY":
                    actual_pnl = (actual_exit - pos.entry_price) * sell_qty
                else:
                    actual_pnl = (pos.entry_price - actual_exit) * sell_qty
            self.risk_manager.record_trade_result(actual_pnl)

        # 4. 分批止盈: 减少数量，移除止盈目标，保留尾部止损继续监控
        if is_partial:
            pos.quantity -= sell_qty
            pos.partial_exit_done = True
            pos.take_profit = 0  # 移除固定止盈，剩余仓位靠尾部止损
            logger.info(
                "[Monitor] %s 分批止盈完成: 已卖%d股，剩余%d股，尾部止损$%.2f",
                pos.symbol,
                sell_qty,
                pos.quantity,
                pos.trailing_stop_price,
            )
        else:
            # 全部平仓: 移除监控
            self.remove_position(trade_id)
            self._exit_retry_count.pop(trade_id, None)  # 清理重试计数

        # 5. 记录历史
        self._exit_history.append(signal)
        if len(self._exit_history) > 100:
            self._exit_history = self._exit_history[-100:]

        # 6. 通知
        if self.notify:
            emoji_map = {
                ExitReason.STOP_LOSS: "!!",
                ExitReason.TAKE_PROFIT: "$$",
                ExitReason.TRAILING_STOP: "~~",
                ExitReason.TIME_STOP: ">>",
            }
            emoji = emoji_map.get(signal.reason, "**")
            msg = (
                "%s 自动平仓 %s\n\n%s\n\n"
                "标的: %s\n方向: %s\n数量: %s\n"
                "入场: $%.2f\n出场: $%.2f\n"
                "盈亏: $%.2f (%.1f%%)\n原因: %s"
            ) % (
                emoji,
                emoji,
                signal.message,
                pos.symbol,
                pos.side,
                pos.quantity,
                pos.entry_price,
                signal.trigger_price,
                pos.unrealized_pnl,
                pos.unrealized_pnl_pct,
                signal.reason.value,
            )
            await self.notify(msg)

    # ============ v2.0: 接近止损预警 (搬运 PanWatch throttle 模式) ============

    async def _check_proximity_alert(self, pos: MonitoredPosition) -> None:
        """检查持仓是否接近止损位，按级别发送预警

        搬运自 PanWatch (MIT) 的 throttle 模式:
        - 按 (trade_id, AlertLevel) 维度冷却
        - 越接近止损，冷却越短 (CRITICAL=5min, DANGER=15min, WARN=30min)
        - 支持 BUY 和 SELL(做空) 两个方向
        """
        if pos.stop_loss <= 0:
            return
        if pos.current_price <= 0 or pos.entry_price <= 0:
            return
        if pos.side not in ("BUY", "SELL"):
            return

        # 计算距止损的距离占比
        # distance_ratio = 0 表示已触及止损, 1.0 表示在入场价
        if pos.side == "BUY":
            # 做多: 止损在入场价下方，价格下跌接近止损
            total_distance = pos.entry_price - pos.stop_loss
            if total_distance <= 0:
                return
            remaining_distance = pos.current_price - pos.stop_loss
        else:
            # 做空(SELL): 止损在入场价上方，价格上涨接近止损
            total_distance = pos.stop_loss - pos.entry_price
            if total_distance <= 0:
                return
            remaining_distance = pos.stop_loss - pos.current_price

        if remaining_distance <= 0:
            return  # 已触及/穿越止损，由 _check_exit_conditions 处理
        distance_ratio = remaining_distance / total_distance

        # 检查阈值 (从高到低，取最高级别)
        now = time.monotonic()
        for threshold, level, cooldown_secs in _ALERT_THRESHOLDS:
            if distance_ratio <= threshold:
                cooldown_key = (pos.trade_id, level)
                last_alert = self._alert_cooldowns.get(cooldown_key, 0)
                if now - last_alert < cooldown_secs:
                    return  # 在冷却期内，不重复发送

                # 发送预警
                self._alert_cooldowns[cooldown_key] = now
                emoji = _ALERT_EMOJI.get(level, "⚠️")
                distance_pct = distance_ratio * 100
                direction_arrow = "▼" if pos.side == "BUY" else "▲"
                msg = (
                    "%s %s 接近止损位\n"
                    "━━━━━━━━━━━━━━━━\n"
                    "方向: %s | 现价: $%.2f (%s%.1f%%)\n"
                    "止损: $%.2f (距离 $%.2f, %.0f%%)\n"
                    "浮亏: $%.2f (%.1f%%)"
                ) % (
                    emoji,
                    pos.symbol,
                    pos.side,
                    pos.current_price,
                    direction_arrow,
                    abs(pos.unrealized_pnl_pct),
                    pos.stop_loss,
                    remaining_distance,
                    distance_pct,
                    pos.unrealized_pnl,
                    pos.unrealized_pnl_pct,
                )
                # 追踪止损信息
                if pos.trailing_stop_price > 0:
                    msg += "\n追踪止损: $%.2f" % pos.trailing_stop_price
                msg += "\n━━━━━━━━━━━━━━━━"
                if level == AlertLevel.CRITICAL:
                    msg += "\n💡 价格接近止损，请关注是否需要手动干预"

                await self._send_alert(msg, level=level, symbol=pos.symbol)

                # 发布 EventBus 事件 (如果可用)
                self._emit_event(
                    "trade.risk_alert",
                    {
                        "symbol": pos.symbol,
                        "level": level.value,
                        "current_price": pos.current_price,
                        "stop_loss": pos.stop_loss,
                        "distance_pct": distance_pct,
                        "unrealized_pnl": pos.unrealized_pnl,
                    },
                )
                return  # 只发最高级别

    async def _send_alert(self, message: str, level: AlertLevel = None, symbol: str = "") -> None:
        """发送预警通知 — 优先 NotificationManager，降级 notify_func"""
        # 尝试 NotificationManager (多渠道)
        try:
            from src.notifications import get_notification_manager, NotifyLevel

            nm = get_notification_manager()
            if nm:
                notify_level = NotifyLevel.NORMAL
                if level == AlertLevel.CRITICAL:
                    notify_level = NotifyLevel.CRITICAL
                elif level == AlertLevel.DANGER:
                    notify_level = NotifyLevel.HIGH
                await nm.send(
                    title="持仓风控预警" if level else "持仓监控通知",
                    body=message,
                    level=notify_level,
                    tags=["trading", "risk"],
                )
                return
        except Exception as e:
            logger.warning("[Monitor] NotificationManager 不可用，降级到 Telegram: %s", e)

        # 降级: 直接 Telegram callback
        if self.notify:
            try:
                await self.notify(message)
            except Exception as e:
                logger.warning("[Monitor] 通知发送失败: %s", e)

    def _emit_event(self, event_type: str, data: dict) -> None:
        """发布 EventBus 事件 (fire-and-forget)"""
        try:
            from src.core.event_bus import get_event_bus

            bus = get_event_bus()
            if bus:
                try:
                    loop = asyncio.get_running_loop()
                    _t = loop.create_task(bus.publish(event_type, data))
                    _t.add_done_callback(
                        lambda t: t.exception() and logger.debug("EventBus 发布异常: %s", t.exception())
                    )
                except RuntimeError as e:  # noqa: F841
                    pass  # 无运行中的事件循环，跳过
        except Exception as e:
            logger.debug("EventBus 不可用: %s", e)

    def _cleanup_stale_cooldowns(self) -> None:
        """清理过期的冷却记录 (防止内存泄漏)"""
        now = time.monotonic()
        max_cooldown = 3600  # 1小时后清理
        stale = [k for k, v in self._alert_cooldowns.items() if now - v > max_cooldown]
        for k in stale:
            del self._alert_cooldowns[k]

    # ============ 状态查询 ============

    def get_status(self) -> Dict:
        positions_info = []
        total_unrealized = 0.0
        for tid, pos in self.positions.items():
            total_unrealized += pos.unrealized_pnl
            positions_info.append(
                {
                    "trade_id": tid,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "unrealized_pnl": round(pos.unrealized_pnl, 2),
                    "unrealized_pnl_pct": round(pos.unrealized_pnl_pct, 1),
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "trailing_stop_price": pos.trailing_stop_price,
                    "highest_price": pos.highest_price,
                    "last_check": pos.last_check.isoformat() if pos.last_check else None,
                }
            )
        return {
            "running": self._running,
            "monitored_count": len(self.positions),
            "total_unrealized_pnl": round(total_unrealized, 2),
            "check_interval": self.check_interval,
            "positions": positions_info,
            "recent_exits": len(self._exit_history),
        }

    def format_status(self) -> str:
        s = self.get_status()
        running_text = "运行中" if s["running"] else "已停止"
        lines = [
            "持仓监控器 (%s)" % running_text,
            "监控持仓: %d个" % s["monitored_count"],
            "未实现盈亏: $%+.2f" % s["total_unrealized_pnl"],
            "检查间隔: %d秒" % s["check_interval"],
            "",
        ]
        if s["positions"]:
            lines.append("-- 监控中的持仓 --")
            for p in s["positions"]:
                sign = "+" if p["unrealized_pnl"] >= 0 else ""
                sl_info = "SL=$%.2f" % p["stop_loss"] if p["stop_loss"] > 0 else "SL=无"
                tp_info = "TP=$%.2f" % p["take_profit"] if p["take_profit"] > 0 else "TP=无"
                ts_info = ""
                if p["trailing_stop_price"] > 0:
                    ts_info = " TS=$%.2f" % p["trailing_stop_price"]
                lines.append(
                    "  %s %s x%s $%.2f->$%.2f (%s%.1f%%) %s %s%s"
                    % (
                        p["symbol"],
                        p["side"],
                        p["quantity"],
                        p["entry_price"],
                        p["current_price"],
                        sign,
                        p["unrealized_pnl_pct"],
                        sl_info,
                        tp_info,
                        ts_info,
                    )
                )
        else:
            lines.append("暂无监控持仓")
        if self._exit_history:
            lines.append("\n最近自动平仓: %d笔" % len(self._exit_history))
            for sig in self._exit_history[-3:]:
                lines.append("  %s %s @ $%.2f" % (sig.position.symbol, sig.reason.value, sig.trigger_price))
        return "\n".join(lines)

    async def check_once(self) -> List[ExitSignal]:
        if not self.positions:
            return []
        history_before = len(self._exit_history)
        await self._check_all_positions()
        return self._exit_history[history_before:]


# 全局实例（延迟初始化，需要注入依赖）
position_monitor: Optional[PositionMonitor] = None
