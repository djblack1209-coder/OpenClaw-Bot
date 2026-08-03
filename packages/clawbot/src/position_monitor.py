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
import copy
import json
import logging
import math
import os
import secrets
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from src.cross_process_lock import CrossProcessFileRLock, cross_process_file_lock
from src.utils import now_et as _now_et_fn


def _now_et() -> datetime:
    return _now_et_fn()


logger = logging.getLogger(__name__)

PENDING_EXIT_STATE_FILE = Path(__file__).resolve().parents[1] / "data" / "position_monitor_exit_state.json"


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
    last_check: datetime | None = None
    atr: float = 0  # ATR值，用于动态尾部止损
    breakeven_triggered: bool = False  # 保本止损是否已触发
    partial_exit_done: bool = False  # 分批止盈是否已执行（50%在1.5R）
    original_quantity: float = 0  # 原始数量（分批止盈后quantity会减少）
    # v2.0: 止损调整事件 (由 PositionMonitor 消费并推送通知)
    _pending_adjustments: list[str] = field(default_factory=list)

    def update_price(self, price: float):
        self.current_price = price
        self.last_check = _now_et()
        if self.side == "BUY":
            self.unrealized_pnl = (price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.quantity
        cost = self.entry_price * self.quantity
        self.unrealized_pnl_pct = (self.unrealized_pnl / cost * 100) if cost > 0 else 0

        if self.side == "BUY":  # noqa: SIM102
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
                            f'🛡️ {self.symbol} 保本止损触发\n止损上移: ${float(old):.2f} → ${float(new_stop):.2f}\n当前价: ${float(price):.2f} (盈利达1R)'
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
                                f'📈 {self.symbol} 追踪止损上移\n${float(old):.2f} → ${float(new_trailing):.2f} (+{float(move_pct):.1f}%)\n最高价: ${float(price):.2f}'
                            )
                        logger.info(
                            "[Monitor] %s 追踪止损上移: $%.2f -> $%.2f (最高价$%.2f%s)",
                            self.symbol,
                            old,
                            self.trailing_stop_price,
                            price,
                            f' ATR={float(self.atr):.2f}' if self.atr > 0 else "",
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
                                f'📉 {self.symbol} 空单追踪止损下移\n${float(old):.2f} → ${float(new_trailing):.2f} (-{float(move_pct):.1f}%)\n最低价: ${float(price):.2f}'
                            )
                        logger.info(
                            "[Monitor] %s 空单追踪止损下移: $%.2f -> $%.2f (最低价$%.2f%s)",
                            self.symbol,
                            old,
                            self.trailing_stop_price,
                            price,
                            f' ATR={float(self.atr):.2f}' if self.atr > 0 else "",
                        )

    def drain_adjustments(self) -> list[str]:
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
        get_quote_func: Callable | None = None,
        execute_sell_func: Callable | None = None,
        notify_func: Callable | None = None,
        risk_manager: Any = None,
        journal: Any = None,
        get_order_snapshots_func: Callable | None = None,
        pending_exit_state_path: str | Path | None = None,
    ):
        self.check_interval = check_interval
        self.get_quote = get_quote_func
        self.execute_sell = execute_sell_func
        self.notify = notify_func
        self.risk_manager = risk_manager
        self.journal = journal
        self.get_order_snapshots = get_order_snapshots_func
        self._pending_exit_state_path = (
            Path(pending_exit_state_path) if pending_exit_state_path is not None else None
        )
        self.positions: dict[int, MonitoredPosition] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._exit_history: list[ExitSignal] = []
        self._exit_retry_count: dict[int, int] = {}  # trade_id -> 重试次数
        self._max_exit_retries = 3  # 最大重试次数
        self._pending_exit_orders: dict[int, dict] = {}
        self._manual_exit_required: set[int] = set()
        self._completed_exit_trades: set[int] = set()
        self._exit_fill_totals: dict[int, dict[str, float]] = {}
        self._load_pending_exit_state()
        # v2.0: 通知节流 (搬运 PanWatch throttle 模式)
        # key: (trade_id, AlertLevel) -> last_alert_timestamp
        self._alert_cooldowns: dict[tuple, float] = {}
        logger.info("[PositionMonitor] 初始化完成 | 检查间隔=%ds", check_interval)

    def _pending_exit_state_lock(self) -> CrossProcessFileRLock | None:
        """返回与未决平仓账本绑定的跨进程锁。"""
        path = self._pending_exit_state_path
        if path is None:
            return None
        return cross_process_file_lock(path.with_name(f".{path.name}.lock"))

    def _load_pending_exit_state_locked(self, *, reset_if_missing: bool = False) -> None:
        """持锁读取未决平仓账本并更新内存状态。"""
        path = self._pending_exit_state_path
        if path is None:
            return
        if not path.exists():
            if reset_if_missing:
                self._pending_exit_orders = {}
                self._exit_fill_totals = {}
                self._exit_retry_count = {}
                self._manual_exit_required = set()
                self._completed_exit_trades = set()
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("待确认平仓状态根节点必须是对象")
        pending = raw.get("pending_exit_orders", {})
        fill_totals = raw.get("exit_fill_totals", {})
        retry_count = raw.get("exit_retry_count", {})
        manual_required = raw.get("manual_exit_required", [])
        completed_trades = raw.get("completed_exit_trades", [])
        if not isinstance(pending, dict) or not isinstance(fill_totals, dict):
            raise ValueError("待确认平仓状态字段格式无效")
        if (
            not isinstance(retry_count, dict)
            or not isinstance(manual_required, list)
            or not isinstance(completed_trades, list)
        ):
            raise ValueError("待确认平仓重试字段格式无效")
        self._pending_exit_orders = {
            int(trade_id): dict(order)
            for trade_id, order in pending.items()
            if str(trade_id).isdigit() and isinstance(order, dict)
        }
        self._exit_fill_totals = {
            int(trade_id): {
                "quantity": float(total.get("quantity", 0) or 0),
                "notional": float(total.get("notional", 0) or 0),
            }
            for trade_id, total in fill_totals.items()
            if str(trade_id).isdigit() and isinstance(total, dict)
        }
        self._exit_retry_count = {
            int(trade_id): int(count)
            for trade_id, count in retry_count.items()
            if str(trade_id).isdigit()
        }
        self._manual_exit_required = {
            int(trade_id)
            for trade_id in manual_required
            if str(trade_id).isdigit()
        }
        self._completed_exit_trades = {
            int(trade_id)
            for trade_id in completed_trades
            if str(trade_id).isdigit()
        }

    def _load_pending_exit_state(self) -> None:
        """恢复未决平仓订单，确保进程重启后不会重复下单。"""
        lock = self._pending_exit_state_lock()
        if lock is None:
            return
        try:
            with lock:
                self._load_pending_exit_state_locked()
            if self._pending_exit_orders:
                logger.warning(
                    "[Monitor] 从磁盘恢复 %d 个待确认平仓单，将先向券商对账",
                    len(self._pending_exit_orders),
                )
        except Exception as exc:
            logger.error("[Monitor] 恢复待确认平仓状态失败，已进入禁止覆盖模式: %s", exc)
            raise RuntimeError("待确认平仓状态损坏，拒绝启动自动平仓") from exc

    def _persist_pending_exit_state_locked(self) -> None:
        """持锁原子保存未决订单及累计成交。"""
        path = self._pending_exit_state_path
        if path is None:
            return
        for trade_id, pending in self._pending_exit_orders.items():
            pos = self.positions.get(trade_id)
            if pos is not None and not pending.get("reconcile_claim"):
                pending["remaining_position_qty"] = float(pos.quantity)
                pending["symbol"] = pos.symbol
                pending["position_side"] = pos.side
        payload = {
            "version": 2,
            "pending_exit_orders": {
                str(trade_id): order for trade_id, order in self._pending_exit_orders.items()
            },
            "exit_fill_totals": {
                str(trade_id): total for trade_id, total in self._exit_fill_totals.items()
            },
            "exit_retry_count": {
                str(trade_id): count for trade_id, count in self._exit_retry_count.items()
            },
            "manual_exit_required": sorted(self._manual_exit_required),
            "completed_exit_trades": sorted(self._completed_exit_trades),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _persist_pending_exit_state(self) -> None:
        """在跨进程锁内保存当前未决平仓状态。"""
        lock = self._pending_exit_state_lock()
        if lock is None:
            return
        with lock:
            self._persist_pending_exit_state_locked()

    def _pending_exit_state_snapshot(
        self,
    ) -> tuple[dict, dict, dict, set[int], set[int]]:
        """复制未决平仓账本，事务失败时恢复内存状态。"""
        return (
            copy.deepcopy(self._pending_exit_orders),
            copy.deepcopy(self._exit_fill_totals),
            copy.deepcopy(self._exit_retry_count),
            set(self._manual_exit_required),
            set(self._completed_exit_trades),
        )

    def _restore_pending_exit_state_snapshot(
        self,
        snapshot: tuple[dict, dict, dict, set[int], set[int]],
    ) -> None:
        """恢复事务开始时的未决平仓内存账本。"""
        (
            self._pending_exit_orders,
            self._exit_fill_totals,
            self._exit_retry_count,
            self._manual_exit_required,
            self._completed_exit_trades,
        ) = snapshot

    @contextmanager
    def _pending_exit_state_transaction(self) -> Iterator[None]:
        """持锁重载、修改并原子保存最新未决平仓账本。"""
        lock = self._pending_exit_state_lock()
        if lock is None:
            yield
            return
        with lock:
            self._load_pending_exit_state_locked(reset_if_missing=True)
            snapshot = self._pending_exit_state_snapshot()
            try:
                yield
                self._persist_pending_exit_state_locked()
            except Exception:
                self._restore_pending_exit_state_snapshot(snapshot)
                raise

    def _claim_exit_submission(
        self,
        signal: ExitSignal,
        sell_qty: float,
    ) -> dict:
        """在下单前持久化唯一 claim，阻断其他进程重复平仓。"""
        trade_id = signal.position.trade_id
        submission_id = secrets.token_hex(16)
        result: dict = {}
        with self._pending_exit_state_transaction():
            if trade_id in self._completed_exit_trades:
                result = {
                    "claimed": False,
                    "status": "already_closed",
                    "success": True,
                }
                return result
            pending = self._pending_exit_orders.get(trade_id)
            if pending:
                result = {
                    "claimed": False,
                    "status": "pending_confirmation",
                    "order": dict(pending),
                }
                return result
            if trade_id in self._manual_exit_required:
                result = {
                    "claimed": False,
                    "status": "manual_action_required",
                    "error": "自动平仓多次失败，真实仓位仍在监控中",
                }
                return result
            retry_count = self._exit_retry_count.get(trade_id, 0)
            if retry_count >= self._max_exit_retries:
                self._manual_exit_required.add(trade_id)
                result = {
                    "claimed": False,
                    "status": "manual_action_required",
                    "error": "自动平仓重试耗尽，真实仓位未确认关闭",
                    "retry_count": retry_count,
                    "newly_exhausted": True,
                }
                return result
            self._pending_exit_orders[trade_id] = {
                "status": "Submitting",
                "submission_claim": True,
                "submission_id": submission_id,
                "requested_qty": float(sell_qty),
                "remaining_position_qty": float(signal.position.quantity),
                "symbol": signal.position.symbol,
                "position_side": signal.position.side,
                "reason": signal.reason.value,
                "trigger_price": float(signal.trigger_price),
                "message": signal.message,
                "claimed_at": _now_et().isoformat(),
            }
            result = {
                "claimed": True,
                "submission_id": submission_id,
                "retry_count": retry_count,
            }
        return result

    def _release_exit_submission(
        self,
        trade_id: int,
        submission_id: str,
        *,
        increment_retry: bool,
        clear_trade_state: bool = False,
    ) -> None:
        """释放本人持有的下单 claim，并按需累计失败次数。"""
        local_fill_total = copy.deepcopy(self._exit_fill_totals.get(trade_id))
        with self._pending_exit_state_transaction():
            pending = self._pending_exit_orders.get(trade_id, {})
            if pending.get("submission_id") != submission_id:
                return
            self._pending_exit_orders.pop(trade_id, None)
            if clear_trade_state:
                self._exit_retry_count.pop(trade_id, None)
                self._manual_exit_required.discard(trade_id)
                self._exit_fill_totals.pop(trade_id, None)
                self._completed_exit_trades.add(trade_id)
            elif increment_retry:
                self._exit_retry_count[trade_id] = self._exit_retry_count.get(trade_id, 0) + 1
            elif local_fill_total is not None:
                self._exit_fill_totals[trade_id] = local_fill_total

    def _replace_exit_submission(
        self,
        trade_id: int,
        submission_id: str,
        pending_order: dict,
    ) -> None:
        """把本人持有的下单 claim 原子替换为券商未决订单。"""
        local_fill_total = copy.deepcopy(self._exit_fill_totals.get(trade_id))
        with self._pending_exit_state_transaction():
            pending = self._pending_exit_orders.get(trade_id, {})
            if pending.get("submission_id") != submission_id:
                raise RuntimeError("平仓 submission claim 已变化，拒绝覆盖")
            self._pending_exit_orders[trade_id] = dict(pending_order)
            if local_fill_total is not None:
                self._exit_fill_totals[trade_id] = local_fill_total

    def _claim_pending_exit_reconciliation(
        self,
        trade_id: int,
        order_result: dict,
    ) -> dict:
        """原子占用一次券商累计成交增量，防止多实例重复结算。"""
        result: dict = {}
        with self._pending_exit_state_transaction():
            pending = self._pending_exit_orders.get(trade_id)
            pos = self.positions.get(trade_id)
            if not pending or not pos:
                return {
                    "claimed": False,
                    "status": "not_found",
                    "error": "没有对应的待确认平仓单",
                }
            if pending.get("submission_claim"):
                return {
                    "claimed": False,
                    "status": "pending_confirmation",
                    "error": "平仓单仍处于提交确认阶段",
                }
            active_claim = pending.get("reconcile_claim")
            if isinstance(active_claim, dict) and active_claim.get("claim_id"):
                return {
                    "claimed": False,
                    "status": "reconcile_in_progress",
                    "error": "同一平仓成交增量正在由另一个实例结算",
                }

            expected_order_id = str(pending.get("order_id") or "")
            actual_order_id = str(order_result.get("order_id") or "")
            if expected_order_id and actual_order_id and expected_order_id != actual_order_id:
                return {
                    "claimed": False,
                    "status": "error",
                    "error": "订单 ID 与待确认记录不一致",
                }
            if order_result.get("error"):
                return {
                    "claimed": False,
                    "status": "pending_confirmation",
                    "error": str(order_result.get("error")),
                }
            if order_result.get("simulated"):
                return {
                    "claimed": False,
                    "status": "pending_confirmation",
                    "error": "模拟结果不能回写真实平仓单",
                }

            normalized_status = str(order_result.get("status") or "").strip().lower()
            try:
                cumulative_filled = float(order_result.get("filled_qty", 0) or 0)
                cumulative_avg_price = float(order_result.get("avg_price", 0) or 0)
                applied_filled = float(pending.get("applied_filled_qty", 0) or 0)
                requested_qty = float(pending.get("requested_qty", 0) or 0)
                remaining_before = float(
                    pending.get("remaining_position_qty", pos.quantity) or pos.quantity
                )
                applied_order_notional = float(
                    pending.get("applied_order_notional")
                    or applied_filled * float(pending.get("avg_price", 0) or 0)
                )
            except (TypeError, ValueError) as exc:
                return {
                    "claimed": False,
                    "status": "error",
                    "error": f"平仓对账数值无效: {exc}",
                }
            numeric_values = (
                cumulative_filled,
                cumulative_avg_price,
                applied_filled,
                requested_qty,
                remaining_before,
                applied_order_notional,
            )
            if any(not math.isfinite(value) or value < 0 for value in numeric_values):
                return {
                    "claimed": False,
                    "status": "error",
                    "error": "平仓对账数值必须是有限非负数",
                }
            if cumulative_filled < applied_filled - 1e-9:
                return {
                    "claimed": False,
                    "status": "error",
                    "error": "券商累计成交数量小于已结算数量",
                }
            if requested_qty > 0 and cumulative_filled > requested_qty + 1e-9:
                return {
                    "claimed": False,
                    "status": "error",
                    "error": "券商累计成交数量超过请求平仓数量",
                }

            incremental_fill = max(0.0, cumulative_filled - applied_filled)
            if (
                normalized_status in {"cancelled", "apicancelled", "inactive"}
                and incremental_fill <= 0
            ):
                self._pending_exit_orders.pop(trade_id, None)
                self._exit_retry_count[trade_id] = self._exit_retry_count.get(trade_id, 0) + 1
                return {
                    "claimed": False,
                    "status": "error",
                    "error": f"平仓单已终止且无新增成交 (status={order_result.get('status')})",
                }
            if incremental_fill <= 0:
                pending.update(
                    {key: value for key, value in order_result.items() if key != "filled_qty"}
                )
                return {
                    "claimed": False,
                    "status": "pending_confirmation",
                    "filled_qty": 0.0,
                    "remaining_qty": remaining_before,
                }
            if cumulative_avg_price <= 0 or incremental_fill > remaining_before + 1e-9:
                return {
                    "claimed": False,
                    "status": "error",
                    "error": "平仓新增成交价格或数量无效",
                }

            cumulative_order_notional = cumulative_filled * cumulative_avg_price
            incremental_notional = cumulative_order_notional - applied_order_notional
            if not math.isfinite(incremental_notional) or incremental_notional <= 0:
                return {
                    "claimed": False,
                    "status": "error",
                    "error": "平仓新增成交金额无效",
                }
            incremental_avg_price = incremental_notional / incremental_fill
            remaining_after = max(0.0, remaining_before - incremental_fill)
            claim_id = secrets.token_hex(16)
            pending["applied_filled_qty"] = cumulative_filled
            pending["applied_order_notional"] = cumulative_order_notional
            pending["remaining_position_qty"] = remaining_after
            pending.update(
                {key: value for key, value in order_result.items() if key != "filled_qty"}
            )
            pending["reconcile_claim"] = {
                "claim_id": claim_id,
                "incremental_fill": incremental_fill,
                "incremental_notional": incremental_notional,
                "claimed_at": _now_et().isoformat(),
            }
            fill_total = self._exit_fill_totals.setdefault(
                trade_id,
                {"quantity": 0.0, "notional": 0.0},
            )
            fill_total["quantity"] += incremental_fill
            fill_total["notional"] += incremental_notional
            result = {
                "claimed": True,
                "claim_id": claim_id,
                "pending": copy.deepcopy(pending),
                "incremental_fill": incremental_fill,
                "incremental_avg_price": incremental_avg_price,
                "remaining_before": remaining_before,
                "remaining_after": remaining_after,
                "normalized_status": normalized_status,
                "requested_qty": requested_qty,
                "cumulative_filled": cumulative_filled,
            }
        return result

    def _finalize_pending_exit_reconciliation(
        self,
        trade_id: int,
        claim_id: str,
        order_result: dict,
    ) -> dict:
        """原子完成本人占用的成交增量，并保留其他交易的最新状态。"""
        result: dict = {}
        with self._pending_exit_state_transaction():
            pending = self._pending_exit_orders.get(trade_id)
            if not pending:
                return {
                    "status": "not_found",
                    "error": "待确认平仓单已不存在",
                }
            claim = pending.get("reconcile_claim")
            if not isinstance(claim, dict) or claim.get("claim_id") != claim_id:
                raise RuntimeError("平仓 reconcile claim 已变化，拒绝覆盖")
            pending.pop("reconcile_claim", None)
            pending.update(
                {key: value for key, value in order_result.items() if key != "filled_qty"}
            )
            normalized_status = str(order_result.get("status") or "").strip().lower()
            cumulative_filled = float(pending.get("applied_filled_qty", 0) or 0)
            requested_qty = float(pending.get("requested_qty", 0) or 0)
            remaining_qty = float(pending.get("remaining_position_qty", 0) or 0)
            terminal_order = normalized_status in {
                "filled",
                "cancelled",
                "apicancelled",
                "inactive",
            }
            if terminal_order or cumulative_filled >= requested_qty > 0:
                self._pending_exit_orders.pop(trade_id, None)
                if remaining_qty <= 1e-9:
                    self._completed_exit_trades.add(trade_id)
                    self._exit_retry_count.pop(trade_id, None)
                    self._manual_exit_required.discard(trade_id)
                    self._exit_fill_totals.pop(trade_id, None)
                result["status"] = (
                    "partially_filled_terminal"
                    if remaining_qty > 1e-9 and normalized_status != "filled"
                    else "filled"
                )
            else:
                self._pending_exit_orders[trade_id] = pending
                result["status"] = "partially_filled_pending"
            result["remaining_qty"] = remaining_qty
        return result

    # ============ 持仓管理 ============

    def add_position(self, pos: MonitoredPosition) -> None:
        restored_pending = self._pending_exit_orders.get(pos.trade_id)
        if restored_pending:
            try:
                remaining_qty = float(restored_pending.get("remaining_position_qty", 0) or 0)
            except (TypeError, ValueError):
                remaining_qty = 0.0
            if 0 < remaining_qty <= float(pos.quantity):
                pos.quantity = remaining_qty
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

    def remove_position(
        self,
        trade_id: int,
        *,
        preserve_pending_exit: bool = False,
    ) -> None:
        if trade_id in self.positions:
            pos = self.positions.pop(trade_id)
            logger.info("[Monitor] 移除监控: %s (trade #%d)", pos.symbol, trade_id)
        if preserve_pending_exit:
            return
        with self._pending_exit_state_transaction():
            self._pending_exit_orders.pop(trade_id, None)
            self._manual_exit_required.discard(trade_id)
            self._exit_fill_totals.pop(trade_id, None)

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
        with self._pending_exit_state_transaction():
            orphaned = set(self._pending_exit_orders) - set(self.positions)
            for trade_id in orphaned:
                self._pending_exit_orders.pop(trade_id, None)
                self._exit_fill_totals.pop(trade_id, None)
        if orphaned:
            logger.info("[Monitor] 清理 %d 个已不在 journal 开仓列表的待确认订单", len(orphaned))
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
            try:  # noqa: SIM105
                await self._task
            except asyncio.CancelledError as e:  # noqa: F841
                pass  # 合理保留：任务取消是正常停止流程
        logger.info("[PositionMonitor] 监控循环已停止")

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                if self._pending_exit_orders:
                    await self._reconcile_pending_exit_orders()
                if self.positions:
                    await self._check_all_positions()
            except asyncio.CancelledError:
                logger.info("[Monitor] 监控循环被取消")
                raise  # 让 stop() 正常结束
            except Exception as e:
                logger.error("[Monitor] 监控循环异常: %s — 将在 %ds 后重试", e, self.check_interval, exc_info=True)
            await asyncio.sleep(self.check_interval)

    async def _reconcile_pending_exit_orders(self) -> None:
        """每轮从券商订单快照对账未决平仓单。"""
        if not self.get_order_snapshots or not self._pending_exit_orders:
            return
        try:
            snapshots = await self.get_order_snapshots()
        except Exception as exc:
            logger.warning("[Monitor] 获取券商平仓订单快照失败: %s", exc)
            return
        if not isinstance(snapshots, list):
            logger.warning("[Monitor] 券商订单快照格式无效，本轮保留未决状态")
            return

        snapshot_map = {
            str(snapshot.get("order_id") or ""): snapshot
            for snapshot in snapshots
            if isinstance(snapshot, dict) and snapshot.get("order_id") is not None
        }
        for trade_id, pending in list(self._pending_exit_orders.items()):
            order_id = str(pending.get("order_id") or "")
            snapshot = snapshot_map.get(order_id)
            if snapshot is None:
                continue
            normalized = dict(snapshot)
            normalized["filled_qty"] = snapshot.get(
                "filled_qty",
                snapshot.get("filled", 0),
            )
            try:
                await self.reconcile_pending_exit(trade_id, normalized)
            except Exception as exc:
                logger.error(
                    "[Monitor] 平仓订单对账失败 trade#%d order#%s: %s",
                    trade_id,
                    order_id,
                    exc,
                    exc_info=True,
                )

    async def _check_all_positions(self) -> None:
        if not self.get_quote:
            return
        symbols = list(set(p.symbol for p in self.positions.values()))
        quotes: dict[str, float] = {}
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

        exit_signals: list[ExitSignal] = []
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
                                '⚠️ {} 利润回撤预警\n{}\n当前浮盈: ${:.2f}'.format(pos.symbol, pnl_warning.get("action", ""), float(pos.unrealized_pnl))
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

    def _check_exit_conditions(self, pos: MonitoredPosition) -> ExitSignal | None:
        price = pos.current_price

        if pos.side == "BUY":
            # 止损
            if pos.stop_loss > 0 and price <= pos.stop_loss:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.STOP_LOSS,
                    trigger_price=price,
                    message=f'止损触发! {pos.symbol} 当前${float(price):.2f} <= 止损${float(pos.stop_loss):.2f} | 亏损${float(pos.unrealized_pnl):.2f} ({float(pos.unrealized_pnl_pct):.1f}%)',
                )
            # 追踪止损
            if pos.trailing_stop_price > 0 and price <= pos.trailing_stop_price:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.TRAILING_STOP,
                    trigger_price=price,
                    message=f'追踪止损触发! {pos.symbol} 当前${float(price):.2f} <= 追踪${float(pos.trailing_stop_price):.2f} | 最高${float(pos.highest_price):.2f} | 盈亏${float(pos.unrealized_pnl):.2f} ({float(pos.unrealized_pnl_pct):.1f}%)',
                )
            # 分批止盈: 盈利达1.5R时平掉50%，剩余用尾部止损
            if not pos.partial_exit_done and pos.stop_loss > 0 and pos.quantity >= 2:
                risk_per_share = pos.entry_price - pos.stop_loss
                if risk_per_share > 0 and price >= pos.entry_price + risk_per_share * 1.5:
                    return ExitSignal(
                        position=pos,
                        reason=ExitReason.PARTIAL_TAKE_PROFIT,
                        trigger_price=price,
                        message=f'分批止盈触发! {pos.symbol} 盈利达1.5R | 当前${float(price):.2f} | 平仓50% ({int(pos.quantity * 0.5):d}股) | 盈亏${float(pos.unrealized_pnl):.2f}',
                    )
            # 止盈（仅对未分批止盈的持仓触发全仓止盈）
            if pos.take_profit > 0 and price >= pos.take_profit:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.TAKE_PROFIT,
                    trigger_price=price,
                    message=f'止盈触发! {pos.symbol} 当前${float(price):.2f} >= 止盈${float(pos.take_profit):.2f} | 盈利${float(pos.unrealized_pnl):.2f} ({float(pos.unrealized_pnl_pct):.1f}%)',
                )

        elif pos.side == "SELL":
            # ── SELL方向（做空）止损止盈 ──
            # 做空止损：价格上涨超过止损价时触发（方向反转）
            if pos.stop_loss > 0 and price >= pos.stop_loss:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.STOP_LOSS,
                    trigger_price=price,
                    message=f'空单止损触发! {pos.symbol} 当前${float(price):.2f} >= 止损${float(pos.stop_loss):.2f} | 亏损${float(pos.unrealized_pnl):.2f} ({float(pos.unrealized_pnl_pct):.1f}%)',
                )
            # 做空追踪止损：价格回涨超过追踪止损价时触发
            if pos.trailing_stop_price > 0 and price >= pos.trailing_stop_price:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.TRAILING_STOP,
                    trigger_price=price,
                    message=f'空单追踪止损触发! {pos.symbol} 当前${float(price):.2f} >= 追踪${float(pos.trailing_stop_price):.2f} | 最低${float(pos.highest_price):.2f} | 盈亏${float(pos.unrealized_pnl):.2f} ({float(pos.unrealized_pnl_pct):.1f}%)',
                )
            # 做空分批止盈：盈利达1.5R时平掉50%
            if not pos.partial_exit_done and pos.stop_loss > 0 and pos.quantity >= 2:
                risk_per_share = pos.stop_loss - pos.entry_price  # SELL: 风险 = 止损价 - 入场价
                if risk_per_share > 0 and price <= pos.entry_price - risk_per_share * 1.5:
                    return ExitSignal(
                        position=pos,
                        reason=ExitReason.PARTIAL_TAKE_PROFIT,
                        trigger_price=price,
                        message=f'空单分批止盈触发! {pos.symbol} 盈利达1.5R | 当前${float(price):.2f} | 平仓50% ({int(pos.quantity * 0.5):d}股) | 盈亏${float(pos.unrealized_pnl):.2f}',
                    )
            # 做空止盈：价格下跌到目标价时触发
            if pos.take_profit > 0 and price <= pos.take_profit:
                return ExitSignal(
                    position=pos,
                    reason=ExitReason.TAKE_PROFIT,
                    trigger_price=price,
                    message=f'空单止盈触发! {pos.symbol} 当前${float(price):.2f} <= 止盈${float(pos.take_profit):.2f} | 盈利${float(pos.unrealized_pnl):.2f} ({float(pos.unrealized_pnl_pct):.1f}%)',
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
                        message=f'时间止损触发! {pos.symbol} 持仓{float(hold_hours):.1f}小时 >= 上限{float(pos.max_hold_hours):.0f}小时 | 亏损${float(pos.unrealized_pnl):.2f} ({float(pos.unrealized_pnl_pct):.1f}%)',
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
                            message=f'日亏损限额熔断! {pos.symbol} 浮亏${float(pos.unrealized_pnl):.2f} + 今日已亏${float(today_pnl):.2f} >= 限额${float(limit_val):.0f} | 强制平仓',
                        )
            except Exception as e:
                logger.warning("[Monitor] 日亏损检查异常: %s", e)

        return None

    async def _execute_exit(self, signal: ExitSignal) -> dict:
        pos = signal.position
        trade_id = pos.trade_id
        logger.warning("[Monitor] %s", signal.message)

        # 分批止盈只卖 50%，其余退出信号卖出当前全部仓位。
        sell_qty = pos.quantity
        is_partial = signal.reason == ExitReason.PARTIAL_TAKE_PROFIT
        if is_partial:
            sell_qty = max(1, int(pos.quantity * 0.5))

        claim = self._claim_exit_submission(signal, sell_qty)
        if not claim.get("claimed"):
            if claim.get("status") == "already_closed":
                self.positions.pop(trade_id, None)
                return {
                    "success": True,
                    "status": "already_closed",
                    "filled_qty": 0.0,
                }
            if claim.get("status") == "pending_confirmation":
                pending = claim.get("order", {})
                logger.warning(
                    "[Monitor] %s (trade #%d) 已有待确认平仓单 %s，保留监控且不重复下单",
                    pos.symbol,
                    trade_id,
                    pending.get("order_id") or pending.get("submission_id") or "?",
                )
                return {
                    "success": False,
                    "status": "pending_confirmation",
                    "order": pending,
                }
            retry_count = int(claim.get("retry_count", 0) or 0)
            if claim.get("newly_exhausted"):
                logger.error(
                    "[Monitor] %s (trade #%d) 平仓已失败%d次，停止重试，需手动处理",
                    pos.symbol,
                    trade_id,
                    retry_count,
                )
                if self.notify:
                    await self.notify(
                        "🚨 紧急：平仓多次失败 🚨\n\n"  # noqa: UP031
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
            return {
                "success": False,
                "status": "manual_action_required",
                "error": str(claim.get("error") or "自动平仓已转人工处理"),
            }

        submission_id = str(claim["submission_id"])
        retry_count = int(claim.get("retry_count", 0) or 0)

        if trade_id in self._pending_exit_orders:
            pending = self._pending_exit_orders[trade_id]
            if pending.get("submission_id") != submission_id:
                self._release_exit_submission(
                    trade_id,
                    submission_id,
                    increment_retry=False,
                )
                return {
                    "success": False,
                    "status": "pending_confirmation",
                    "order": pending,
                }

        if trade_id in self._manual_exit_required:
            self._release_exit_submission(
                trade_id,
                submission_id,
                increment_retry=False,
            )
            return {
                "success": False,
                "status": "manual_action_required",
                "error": "自动平仓多次失败，真实仓位仍在监控中",
            }

        if not self.execute_sell:
            self._release_exit_submission(
                trade_id,
                submission_id,
                increment_retry=True,
            )
            logger.error("[Monitor] 未配置真实卖出执行器，保留仓位监控")
            return {
                "success": False,
                "status": "error",
                "error": "未配置真实卖出执行器",
            }

        # claim 已在磁盘落盘；即使进程在券商受理后崩溃，其他进程也不会重复卖出。
        try:
            sell_result = await self.execute_sell(
                symbol=pos.symbol,
                quantity=sell_qty,
                order_type="MKT",
                decided_by="PositionMonitor",
                reason=f'{signal.reason.value}: {signal.message}',
            )
            logger.info("[Monitor] 平仓执行结果: %s", sell_result)
        except Exception as exc:
            self._release_exit_submission(
                trade_id,
                submission_id,
                increment_retry=True,
            )
            logger.error("[Monitor] 平仓执行失败 (第%d次): %s", retry_count + 1, exc)
            if self.notify:
                await self.notify(
                    f'!! 平仓执行失败 (第{int(retry_count + 1):d}/{int(self._max_exit_retries):d}次) !!\n{signal.message}\n错误: {exc}\n{self.check_interval}秒后重试...'
                )
            return {"success": False, "status": "error", "error": str(exc)}

        # 只有真实且已确认的成交数量可以改变仓位、日志和风控状态。
        if not isinstance(sell_result, dict):
            self._release_exit_submission(
                trade_id,
                submission_id,
                increment_retry=True,
            )
            return {"success": False, "status": "error", "error": "平仓结果格式无效"}
        if sell_result.get("simulated"):
            self._release_exit_submission(
                trade_id,
                submission_id,
                increment_retry=True,
            )
            return {
                "success": False,
                "status": "error",
                "error": "模拟平仓结果不能关闭真实仓位",
            }
        if sell_result.get("error"):
            self._release_exit_submission(
                trade_id,
                submission_id,
                increment_retry=True,
            )
            return {
                "success": False,
                "status": "error",
                "error": str(sell_result.get("error")),
            }

        order_status = str(sell_result.get("status") or "").strip()
        normalized_status = order_status.lower()
        try:
            filled_qty = float(sell_result.get("filled_qty", 0) or 0)
        except (TypeError, ValueError):
            filled_qty = 0.0
        if filled_qty <= 0:
            if normalized_status in {
                "submitted",
                "presubmitted",
                "pendingsubmit",
                "apipending",
                "pendingcancel",
            } and sell_result.get("order_id"):
                pending_order = {
                    **dict(sell_result),
                    "requested_qty": float(sell_qty),
                    "applied_filled_qty": 0.0,
                    "applied_order_notional": 0.0,
                    "remaining_position_qty": float(pos.quantity),
                    "reason": signal.reason.value,
                    "trigger_price": signal.trigger_price,
                    "message": signal.message,
                }
                self._replace_exit_submission(
                    trade_id,
                    submission_id,
                    pending_order,
                )
                return {
                    "success": False,
                    "status": "pending_confirmation",
                    "order": sell_result,
                }
            self._release_exit_submission(
                trade_id,
                submission_id,
                increment_retry=True,
            )
            return {
                "success": False,
                "status": "error",
                "error": f"平仓未成交 (status={order_status or 'unknown'}, filled_qty=0)",
            }

        result = await self._apply_confirmed_exit(signal, sell_result, filled_qty)
        pending_statuses = {
            "submitted",
            "presubmitted",
            "pendingsubmit",
            "apipending",
            "pendingcancel",
        }
        if normalized_status in pending_statuses and filled_qty < float(sell_qty):
            pending_order = {
                **dict(sell_result),
                "requested_qty": float(sell_qty),
                "applied_filled_qty": filled_qty,
                "applied_order_notional": filled_qty * float(sell_result.get("avg_price", 0) or 0),
                "remaining_position_qty": float(pos.quantity),
                "reason": signal.reason.value,
                "trigger_price": signal.trigger_price,
                "message": signal.message,
            }
            self._replace_exit_submission(
                trade_id,
                submission_id,
                pending_order,
            )
            result["status"] = "partially_filled_pending"
        else:
            self._release_exit_submission(
                trade_id,
                submission_id,
                increment_retry=False,
                clear_trade_state=trade_id not in self.positions,
            )
        return result

    async def reconcile_pending_exit(self, trade_id: int, order_result: dict) -> dict:
        """按券商累计成交回写待确认平仓单，只结算新增成交数量。"""
        if not isinstance(order_result, dict):
            return {"success": False, "status": "error", "error": "订单回写格式无效"}
        claim = self._claim_pending_exit_reconciliation(trade_id, order_result)
        if not claim.get("claimed"):
            return {
                "success": False,
                "status": str(claim.get("status") or "pending_confirmation"),
                "error": str(claim.get("error") or "本次没有新增成交需要结算"),
                "filled_qty": float(claim.get("filled_qty", 0) or 0),
                "remaining_qty": claim.get("remaining_qty"),
            }

        pos = self.positions.get(trade_id)
        if pos is None:
            return {
                "success": False,
                "status": "reconcile_in_progress",
                "error": "本地仓位缺失，成交增量已占用并等待人工核对",
            }
        pos.quantity = float(claim["remaining_before"])
        pending = dict(claim["pending"])
        try:
            reason = ExitReason(str(pending.get("reason") or ExitReason.MANUAL.value))
        except ValueError:
            reason = ExitReason.MANUAL
        signal = ExitSignal(
            position=pos,
            reason=reason,
            trigger_price=float(
                pending.get("trigger_price") or pos.current_price or pos.entry_price
            ),
            message=str(pending.get("message") or "待确认平仓单成交回写"),
        )
        incremental_result = dict(order_result)
        incremental_result["filled_qty"] = float(claim["incremental_fill"])
        incremental_result["avg_price"] = float(claim["incremental_avg_price"])
        try:
            result = await self._apply_confirmed_exit(
                signal,
                incremental_result,
                float(claim["incremental_fill"]),
                fill_already_reserved=True,
            )
        except Exception as exc:
            logger.critical(
                "[Monitor] 平仓增量已占用但本地结算失败 trade#%d: %s",
                trade_id,
                exc,
                exc_info=True,
            )
            return {
                "success": False,
                "status": "reconcile_in_progress",
                "error": "成交增量已安全占用，本地结算失败，需人工核对",
            }

        finalized = self._finalize_pending_exit_reconciliation(
            trade_id,
            str(claim["claim_id"]),
            order_result,
        )
        result["status"] = str(finalized.get("status") or result.get("status"))
        result["remaining_qty"] = finalized.get("remaining_qty", result.get("remaining_qty"))
        return result

    async def _apply_confirmed_exit(
        self,
        signal: ExitSignal,
        sell_result: dict,
        confirmed_qty: float,
        *,
        fill_already_reserved: bool = False,
    ) -> dict:
        """把已确认的真实成交增量应用到日志、风控和监控仓位。"""
        pos = signal.position
        trade_id = pos.trade_id
        actual_sell_qty = min(float(confirmed_qty), float(pos.quantity))
        closes_entire_position = actual_sell_qty >= float(pos.quantity)
        is_partial = signal.reason == ExitReason.PARTIAL_TAKE_PROFIT
        exit_price = signal.trigger_price
        if sell_result.get("avg_price", 0) > 0:
            exit_price = float(sell_result["avg_price"])
        fill_total = self._exit_fill_totals.setdefault(
            trade_id,
            {"quantity": 0.0, "notional": 0.0},
        )
        if not fill_already_reserved:
            fill_total["quantity"] += actual_sell_qty
            fill_total["notional"] += actual_sell_qty * exit_price

        # 2. 更新交易日志
        if self.journal:
            try:
                if not closes_entire_position:
                    logger.info("[Monitor] %s 部分成交记录: %s股 @ $%.2f", pos.symbol, actual_sell_qty, exit_price)
                else:
                    weighted_exit_price = fill_total["notional"] / max(fill_total["quantity"], 1e-9)
                    self.journal.close_trade(
                        trade_id=trade_id,
                        exit_price=weighted_exit_price,
                        exit_order_id=str(sell_result.get("order_id") or ""),
                        exit_reason=signal.reason.value,
                    )
            except Exception as e:
                logger.error("[Monitor] 更新交易日志失败: %s", e)

        # 3. 更新风控（用实际成交价计算PnL，而非报价浮亏）
        if self.risk_manager:
            # 部分平仓时按比例计算 PnL，避免用全仓浮亏误报
            actual_pnl = pos.unrealized_pnl * (actual_sell_qty / pos.quantity) if pos.quantity > 0 else 0
            if sell_result and sell_result.get("avg_price", 0) > 0:
                actual_exit = sell_result["avg_price"]
                if pos.side == "BUY":
                    actual_pnl = (actual_exit - pos.entry_price) * actual_sell_qty
                else:
                    actual_pnl = (pos.entry_price - actual_exit) * actual_sell_qty
            self.risk_manager.record_trade_result(actual_pnl)

        # 4. 分批止盈: 减少数量，移除止盈目标，保留尾部止损继续监控
        if not closes_entire_position:
            pos.quantity -= actual_sell_qty
            if is_partial:
                pos.partial_exit_done = True
                pos.take_profit = 0  # 分批止盈后，剩余仓位靠尾部止损
            logger.info(
                "[Monitor] %s 部分平仓成交: 已卖%s股，剩余%s股，尾部止损$%.2f",
                pos.symbol,
                actual_sell_qty,
                pos.quantity,
                pos.trailing_stop_price,
            )
        else:
            # 全部平仓: 移除监控
            self.remove_position(trade_id, preserve_pending_exit=True)
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
            msg = f'{emoji} 自动平仓 {emoji}\n\n{signal.message}\n\n标的: {pos.symbol}\n方向: {pos.side}\n数量: {pos.quantity}\n入场: ${float(pos.entry_price):.2f}\n出场: ${float(signal.trigger_price):.2f}\n盈亏: ${float(pos.unrealized_pnl):.2f} ({float(pos.unrealized_pnl_pct):.1f}%)\n原因: {signal.reason.value}'
            await self.notify(msg)

        return {
            "success": True,
            "status": "filled" if closes_entire_position else "partially_filled",
            "filled_qty": actual_sell_qty,
            "remaining_qty": 0 if closes_entire_position else pos.quantity,
        }

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
                msg = f'{emoji} {pos.symbol} 接近止损位\n━━━━━━━━━━━━━━━━\n方向: {pos.side} | 现价: ${float(pos.current_price):.2f} ({direction_arrow}{float(abs(pos.unrealized_pnl_pct)):.1f}%)\n止损: ${float(pos.stop_loss):.2f} (距离 ${float(remaining_distance):.2f}, {float(distance_pct):.0f}%)\n浮亏: ${float(pos.unrealized_pnl):.2f} ({float(pos.unrealized_pnl_pct):.1f}%)'
                # 追踪止损信息
                if pos.trailing_stop_price > 0:
                    msg += f'\n追踪止损: ${float(pos.trailing_stop_price):.2f}'
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
            from src.notifications import NotifyLevel, get_notification_manager

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
                    pass  # 合理保留：无运行中的事件循环时跳过异步事件发布
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

    def get_status(self) -> dict:
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
            f'持仓监控器 ({running_text})',
            '监控持仓: {:d}个'.format(int(s["monitored_count"])),
            '未实现盈亏: ${:+.2f}'.format(float(s["total_unrealized_pnl"])),
            '检查间隔: {:d}秒'.format(int(s["check_interval"])),
            "",
        ]
        if s["positions"]:
            lines.append("-- 监控中的持仓 --")
            for p in s["positions"]:
                sign = "+" if p["unrealized_pnl"] >= 0 else ""
                sl_info = 'SL=${:.2f}'.format(float(p["stop_loss"])) if p["stop_loss"] > 0 else "SL=无"
                tp_info = 'TP=${:.2f}'.format(float(p["take_profit"])) if p["take_profit"] > 0 else "TP=无"
                ts_info = ""
                if p["trailing_stop_price"] > 0:
                    ts_info = ' TS=${:.2f}'.format(float(p["trailing_stop_price"]))
                lines.append(
                    '  {} {} x{} ${:.2f}->${:.2f} ({}{:.1f}%) {} {}{}'.format(p["symbol"], p["side"], p["quantity"], float(p["entry_price"]), float(p["current_price"]), sign, float(p["unrealized_pnl_pct"]), sl_info, tp_info, ts_info)
                )
        else:
            lines.append("暂无监控持仓")
        if self._exit_history:
            lines.append(f'\n最近自动平仓: {len(self._exit_history):d}笔')
            for sig in self._exit_history[-3:]:
                lines.append(f'  {sig.position.symbol} {sig.reason.value} @ ${float(sig.trigger_price):.2f}')
        return "\n".join(lines)

    async def check_once(self) -> list[ExitSignal]:
        if not self.positions:
            return []
        history_before = len(self._exit_history)
        await self._check_all_positions()
        return self._exit_history[history_before:]


# 全局实例（延迟初始化，需要注入依赖）
position_monitor: PositionMonitor | None = None
