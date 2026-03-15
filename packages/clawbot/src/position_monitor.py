"""
ClawBot 持仓监控器 v1.0
自动监控所有持仓，实时检测止损/止盈/追踪止损触发

功能：
1. 定时轮询持仓价格（可配置间隔）
2. 止损触发 -> 自动平仓
3. 止盈触发 -> 自动平仓
4. 追踪止损 -> 价格上涨时自动上移止损位
5. 时间止损 -> 持仓超时自动平仓
6. 事件回调 -> 触发时通知Telegram群
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
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
    atr: float = 0                    # ATR值，用于动态尾部止损
    breakeven_triggered: bool = False  # 保本止损是否已触发
    partial_exit_done: bool = False    # 分批止盈是否已执行（50%在1.5R）
    original_quantity: float = 0       # 原始数量（分批止盈后quantity会减少）

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
                        logger.info(
                            "[Monitor] %s 保本止损触发: $%.2f -> $%.2f (盈利达1R, 当前$%.2f)",
                            self.symbol, old, new_stop, price,
                        )

        if price > self.highest_price:
            self.highest_price = price
            if self.side == "BUY":
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
                        logger.info(
                            "[Monitor] %s 追踪止损上移: $%.2f -> $%.2f (最高价$%.2f%s)",
                            self.symbol, old, self.trailing_stop_price, price,
                            " ATR=%.2f" % self.atr if self.atr > 0 else "",
                        )


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
        logger.info("[PositionMonitor] 初始化完成 | 检查间隔=%ds", check_interval)

    # ============ 持仓管理 ============

    def add_position(self, pos: MonitoredPosition) -> None:
        self.positions[pos.trade_id] = pos
        pos.highest_price = pos.entry_price
        if pos.original_quantity <= 0:
            pos.original_quantity = pos.quantity
        if pos.trailing_stop_pct > 0 and pos.side == "BUY":
            pos.trailing_stop_price = round(
                pos.entry_price * (1 - pos.trailing_stop_pct), 2
            )
        logger.info(
            "[Monitor] 添加监控: %s %s x%s @ $%s | SL=$%s TP=$%s TS=%.1f%%",
            pos.symbol, pos.side, pos.quantity, pos.entry_price,
            pos.stop_loss, pos.take_profit, pos.trailing_stop_pct * 100,
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
                self.positions[trade_id].symbol, old, new_stop,
            )

    def update_take_profit(self, trade_id: int, new_tp: float) -> None:
        if trade_id in self.positions:
            old = self.positions[trade_id].take_profit
            self.positions[trade_id].take_profit = new_tp
            logger.info(
                "[Monitor] %s 止盈更新: $%.2f -> $%.2f",
                self.positions[trade_id].symbol, old, new_tp,
            )

    # ============ 监控循环 ============

    async def start(self) -> None:
        if self._running:
            logger.warning("[Monitor] 已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("[PositionMonitor] 监控循环已启动")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[PositionMonitor] 监控循环已停止")

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                if self.positions:
                    await self._check_all_positions()
            except Exception as e:
                logger.error("[Monitor] 监控循环异常: %s", e, exc_info=True)
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
                signal = self._check_exit_conditions(pos)
                if signal:
                    exit_signals.append(signal)
            except Exception as e:
                logger.error("[Monitor] 检查持仓 %s (trade #%d) 异常: %s",
                             pos.symbol, trade_id, e, exc_info=True)

        for signal in exit_signals:
            await self._execute_exit(signal)

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
                        % (pos.symbol, price, pos.stop_loss,
                           pos.unrealized_pnl, pos.unrealized_pnl_pct)
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
                        % (pos.symbol, price, pos.trailing_stop_price,
                           pos.highest_price, pos.unrealized_pnl, pos.unrealized_pnl_pct)
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
                            % (pos.symbol, price,
                               int(pos.quantity * 0.5),
                               pos.unrealized_pnl)
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
                        % (pos.symbol, price, pos.take_profit,
                           pos.unrealized_pnl, pos.unrealized_pnl_pct)
                    ),
                )

        # 时间止损（仅对亏损/持平持仓触发，盈利持仓转为纯尾部止损）
        if pos.max_hold_hours > 0:
            # P0#2: 安全处理 naive/aware datetime 混合
            entry = pos.entry_time
            if entry.tzinfo is None:
                # 旧数据用 naive datetime，保持 naive 比较
                now = datetime.now()
            else:
                now = _now_et()
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
                            % (pos.symbol, hold_hours, pos.max_hold_hours,
                               pos.unrealized_pnl, pos.unrealized_pnl_pct)
                        ),
                    )
                else:
                    # 盈利: 不平仓，但取消时间止损，完全依赖尾部止损
                    if pos.max_hold_hours > 0:
                        logger.info(
                            "[Monitor] %s 超时但盈利$%.2f，取消时间止损，转为纯尾部止损",
                            pos.symbol, pos.unrealized_pnl,
                        )
                        pos.max_hold_hours = 0  # 取消时间止损，不再检查

        # 日亏损限额熔断：当日累计亏损触及限额时，强制平掉亏损持仓
        if self.risk_manager and pos.unrealized_pnl < 0:
            try:
                today_pnl = getattr(self.risk_manager, '_today_pnl', 0)
                daily_limit = getattr(self.risk_manager, 'config', None)
                if daily_limit:
                    limit_val = getattr(daily_limit, 'daily_loss_limit', 100)
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
                logger.debug("[Monitor] 日亏损检查异常: %s", e)

        return None

    async def _execute_exit(self, signal: ExitSignal) -> None:
        pos = signal.position
        trade_id = pos.trade_id
        logger.warning("[Monitor] %s", signal.message)

        # 检查重试次数，超过上限则标记为需手动处理并停止重试
        retry_count = self._exit_retry_count.get(trade_id, 0)
        if retry_count >= self._max_exit_retries:
            logger.error("[Monitor] %s (trade #%d) 平仓已失败%d次，停止重试，需手动处理",
                         pos.symbol, trade_id, retry_count)
            if self.notify:
                await self.notify(
                    "!! 平仓多次失败，需手动处理 !!\n"
                    "标的: %s | 数量: %s\n"
                    "已重试%d次均失败，已停止自动平仓。\n"
                    "请手动卖出！" % (pos.symbol, pos.quantity, retry_count)
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
                logger.error("[Monitor] 平仓执行失败 (第%d次): %s",
                             retry_count + 1, e)
                if self.notify:
                    await self.notify(
                        "!! 平仓执行失败 (第%d/%d次) !!\n%s\n错误: %s\n%s秒后重试..."
                        % (retry_count + 1, self._max_exit_retries,
                           signal.message, e, self.check_interval)
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
                    logger.info("[Monitor] %s 分批止盈记录: %d股 @ $%.2f",
                                pos.symbol, sell_qty, exit_price)
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
            actual_pnl = pos.unrealized_pnl  # 默认用浮亏
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
                pos.symbol, sell_qty, pos.quantity, pos.trailing_stop_price,
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
                emoji, emoji, signal.message,
                pos.symbol, pos.side, pos.quantity,
                pos.entry_price, signal.trigger_price,
                pos.unrealized_pnl, pos.unrealized_pnl_pct,
                signal.reason.value,
            )
            await self.notify(msg)

    # ============ 状态查询 ============

    def get_status(self) -> Dict:
        positions_info = []
        total_unrealized = 0.0
        for tid, pos in self.positions.items():
            total_unrealized += pos.unrealized_pnl
            positions_info.append({
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
            })
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
                    % (p["symbol"], p["side"], p["quantity"],
                       p["entry_price"], p["current_price"],
                       sign, p["unrealized_pnl_pct"],
                       sl_info, tp_info, ts_info)
                )
        else:
            lines.append("暂无监控持仓")
        if self._exit_history:
            lines.append("\n最近自动平仓: %d笔" % len(self._exit_history))
            for sig in self._exit_history[-3:]:
                lines.append(
                    "  %s %s @ $%.2f"
                    % (sig.position.symbol, sig.reason.value, sig.trigger_price)
                )
        return "\n".join(lines)

    async def check_once(self) -> List[ExitSignal]:
        if not self.positions:
            return []
        history_before = len(self._exit_history)
        await self._check_all_positions()
        return self._exit_history[history_before:]


# 全局实例（延迟初始化，需要注入依赖）
position_monitor: Optional[PositionMonitor] = None
