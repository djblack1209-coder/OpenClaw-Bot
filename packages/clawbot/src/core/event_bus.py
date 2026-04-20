"""
OpenClaw OMEGA — 事件总线 (Event Bus)
轻量级进程内异步发布-订阅，替代 synergy.py 的直接函数调用。

设计原则:
  1. 发布者和订阅者完全解耦（不互相 import）
  2. 每条事件链独立，一条断了不影响其他
  3. 异步执行，不阻塞发布者
  4. 支持事件过滤和优先级
  5. 所有事件自动记录到审计日志
"""
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

# 审计日志路径
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
AUDIT_DIR = _BASE_DIR / "data" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


# ── 标准事件类型 ──────────────────────────────────────────

class EventType:
    """所有标准事件类型常量"""

    # 交易事件
    TRADE_SIGNAL = "trade.signal"
    TRADE_EXECUTED = "trade.executed"
    TRADE_CANCELLED = "trade.cancelled"
    RISK_ALERT = "trade.risk_alert"
    STRATEGY_SUSPENDED = "trade.strategy_suspended"
    PORTFOLIO_UPDATE = "trade.portfolio_update"
    DAILY_REVIEW = "trade.daily_review"

    # 社媒事件
    SOCIAL_PUBLISHED = "social.published"
    SOCIAL_TRENDING = "social.trending"
    SOCIAL_ENGAGEMENT = "social.engagement"
    SOCIAL_DRAFT_CREATED = "social.draft_created"

    # 进化事件
    EVOLUTION_PROPOSAL = "evolution.proposal"
    EVOLUTION_INTEGRATED = "evolution.integrated"
    EVOLUTION_SCAN_COMPLETE = "evolution.scan_complete"

    # 系统事件
    COST_WARNING = "system.cost_warning"
    COST_DAILY_REPORT = "system.cost_daily_report"
    SECURITY_ALERT = "system.security_alert"
    SELF_HEAL_SUCCESS = "system.self_heal"
    SELF_HEAL_FAILED = "system.self_heal_failed"
    BOT_HEALTH_CHANGE = "system.bot_health"
    TASK_COMPLETED = "system.task_completed"
    TASK_FAILED = "system.task_failed"
    HUMAN_REQUIRED = "system.human_required"

    # 生活事件
    DELIVERY_UPDATE = "life.delivery"
    CALENDAR_REMINDER = "life.reminder"
    BILL_DUE = "life.bill_due"

    # 网关事件
    GATEWAY_MESSAGE = "gateway.message"
    GATEWAY_CALLBACK = "gateway.callback"

    # 闲鱼事件
    XIANYU_ORDER_PAID = "xianyu.order_paid"          # 闲鱼订单支付

    # 预算事件
    BUDGET_EXCEEDED = "life.budget_exceeded"          # 预算超支

    # 粉丝里程碑
    FOLLOWER_MILESTONE = "social.follower_milestone"  # 粉丝里程碑

    # 自选股事件
    WATCHLIST_ANOMALY = "watchlist.anomaly"          # 自选股异动（价格/放量/RSI极值）
    WATCHLIST_PRICE_ALERT = "watchlist.price_alert"  # 触达目标价/止损价


# ── 事件数据结构 ──────────────────────────────────────────

@dataclass
class Event:
    """一个事件实例"""
    event_type: str
    data: Dict[str, Any]
    source: str = ""          # 发布者标识
    timestamp: float = field(default_factory=time.time)
    priority: int = 5         # 1=最高, 10=最低
    event_id: str = ""        # 自动生成

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"{self.event_type}_{int(self.timestamp * 1000)}"


@dataclass
class Subscription:
    """一个订阅"""
    event_type: str           # 支持通配符: "trade.*" 匹配所有交易事件
    handler: Callable[[Event], Coroutine]
    subscriber_name: str = ""
    priority: int = 5         # 低值高优先级, 决定调用顺序
    filter_fn: Optional[Callable[[Event], bool]] = None  # 事件过滤器


# ── 事件总线 ──────────────────────────────────────────────

class EventBus:
    """
    轻量级进程内事件总线，异步发布-订阅。

    使用方式:
        bus = EventBus()

        # 订阅
        async def on_trade(event: Event):
            logger.info("Trade executed: %s", event.data)
        bus.subscribe(EventType.TRADE_EXECUTED, on_trade, "trading_logger")

        # 发布
        await bus.publish(EventType.TRADE_EXECUTED, {"symbol": "AAPL", "price": 150.0})

        # 通配符订阅
        bus.subscribe("trade.*", on_any_trade, "trade_monitor")
    """

    def __init__(self, audit_enabled: bool = True):
        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self._wildcard_subs: List[Subscription] = []
        self._event_history: List[Event] = []
        self._max_history = 1000
        self._audit_enabled = audit_enabled
        self._stats: Dict[str, int] = defaultdict(int)
        self._error_count: Dict[str, int] = defaultdict(int)
        logger.info("EventBus 初始化完成")

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], Coroutine],
        subscriber_name: str = "",
        priority: int = 5,
        filter_fn: Optional[Callable[[Event], bool]] = None,
    ) -> None:
        """
        订阅事件。

        Args:
            event_type: 事件类型，支持通配符 "trade.*"
            handler: 异步处理函数 async def handler(event: Event)
            subscriber_name: 订阅者名称（用于日志和调试）
            priority: 优先级（1=最高），同类型的handler按优先级排序执行
            filter_fn: 可选的过滤函数，返回False则跳过该handler
        """
        sub = Subscription(
            event_type=event_type,
            handler=handler,
            subscriber_name=subscriber_name or handler.__name__,
            priority=priority,
            filter_fn=filter_fn,
        )

        if "*" in event_type:
            self._wildcard_subs.append(sub)
            self._wildcard_subs.sort(key=lambda s: s.priority)
            logger.debug(f"通配符订阅: {subscriber_name} → {event_type}")
        else:
            self._subscriptions[event_type].append(sub)
            self._subscriptions[event_type].sort(key=lambda s: s.priority)
            logger.debug(f"订阅: {subscriber_name} → {event_type}")

    def unsubscribe(self, event_type: str, handler: Callable) -> bool:
        """取消订阅，返回是否成功"""
        if "*" in event_type:
            before = len(self._wildcard_subs)
            self._wildcard_subs = [s for s in self._wildcard_subs if s.handler != handler]
            return len(self._wildcard_subs) < before
        else:
            if event_type in self._subscriptions:
                before = len(self._subscriptions[event_type])
                self._subscriptions[event_type] = [
                    s for s in self._subscriptions[event_type] if s.handler != handler
                ]
                return len(self._subscriptions[event_type]) < before
        return False

    async def publish(
        self,
        event_type: str,
        data: Dict[str, Any],
        source: str = "",
        priority: int = 5,
    ) -> int:
        """
        发布事件，异步通知所有订阅者。

        Args:
            event_type: 事件类型
            data: 事件数据
            source: 发布者标识
            priority: 事件优先级

        Returns:
            成功通知的订阅者数量
        """
        event = Event(
            event_type=event_type,
            data=data,
            source=source,
            priority=priority,
        )

        # 记录历史
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-500:]

        self._stats[event_type] += 1

        # 审计日志
        if self._audit_enabled:
            self._write_audit(event)

        # 收集匹配的订阅者
        handlers: List[Subscription] = []

        # 精确匹配 — 取快照，防止 subscribe() 并发修改列表
        if event_type in self._subscriptions:
            handlers.extend(list(self._subscriptions[event_type]))

        # 通配符匹配 (trade.* 匹配 trade.signal, trade.executed 等) — 取快照
        for sub in list(self._wildcard_subs):
            pattern = sub.event_type.replace("*", "")
            if event_type.startswith(pattern):
                handlers.append(sub)

        # 按优先级排序
        handlers.sort(key=lambda s: s.priority)

        # 异步执行所有handler（互不阻塞）
        success_count = 0
        tasks = []
        for sub in handlers:
            # 过滤检查
            if sub.filter_fn and not sub.filter_fn(event):
                continue
            tasks.append(self._safe_call(sub, event))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)

        return success_count

    async def _safe_call(self, sub: Subscription, event: Event) -> bool:
        """安全调用handler，捕获所有异常"""
        try:
            await sub.handler(event)
            return True
        except Exception as e:
            error_key = f"{sub.subscriber_name}:{event.event_type}"
            self._error_count[error_key] += 1
            logger.error(
                f"EventBus handler 错误: {sub.subscriber_name} "
                f"处理 {event.event_type} 失败: {e}",
                exc_info=True,
            )
            return False

    def _write_audit(self, event: Event) -> None:
        """写入审计日志（追加模式，不可篡改）"""
        try:
            import json
            audit_file = AUDIT_DIR / "events.jsonl"
            record = {
                "ts": datetime.fromtimestamp(event.timestamp, tz=timezone.utc).isoformat(),
                "type": event.event_type,
                "source": event.source,
                "priority": event.priority,
                "data_keys": list(event.data.keys()),  # 不记录完整数据（隐私）
                "event_id": event.event_id,
            }
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("审计日志写入失败: %s", e)  # 审计日志失败不应影响业务

    # ── 查询接口 ──────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """获取事件统计"""
        return {
            "total_events": sum(self._stats.values()),
            "event_counts": dict(self._stats),
            "error_counts": dict(self._error_count),
            "subscription_count": sum(len(v) for v in self._subscriptions.values())
                                  + len(self._wildcard_subs),
            "history_size": len(self._event_history),
        }

    def get_recent_events(self, event_type: str = "", limit: int = 20) -> List[Dict]:
        """获取最近的事件"""
        events = self._event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return [
            {
                "event_id": e.event_id,
                "type": e.event_type,
                "source": e.source,
                "timestamp": e.timestamp,
                "data": e.data,
            }
            for e in events[-limit:]
        ]

    async def shutdown(self) -> None:
        """优雅关闭 — 清理订阅并记录统计

        在进程退出前调用，确保事件处理状态可追溯。
        """
        stats = self.get_stats()
        logger.info(
            "[EventBus] 关闭: %d 个事件已处理, %d 个订阅, %d 个历史记录",
            stats.get("total_events", 0),
            stats.get("subscription_count", 0),
            stats.get("history_size", 0),
        )
        # 清理订阅，防止关闭后仍有 handler 被调用
        self._subscriptions.clear()
        self._wildcard_subs.clear()


# ── 全局单例 ──────────────────────────────────────────────

_event_bus: Optional[EventBus] = None
_bus_lock = __import__("threading").Lock()


def get_event_bus() -> EventBus:
    """获取全局事件总线实例（线程安全 — APScheduler 线程池可能并发调用）"""
    global _event_bus
    if _event_bus is None:
        with _bus_lock:
            if _event_bus is None:
                _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """重置事件总线（仅用于测试）"""
    global _event_bus
    _event_bus = None
