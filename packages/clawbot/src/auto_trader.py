"""
ClawBot 自主交易引擎 v1.0
完整的 扫描->分析->决策->风控->执行->监控 自动化闭环

核心流程:
1. 定时扫描市场（使用 ta_engine + universe）
2. 筛选候选标的（信号评分 + 多层过滤）
3. AI团队协作分析（可选，通过回调）
4. 风控审核（RiskManager 硬性拦截）
5. 自动执行下单（broker_bridge）
6. 持仓监控（position_monitor 止损/止盈）
7. 收盘复盘（trading_journal）
"""
import asyncio
import json
import logging
import os
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum

from src.models import TradeProposal
from src.notify_style import (
    format_trade_executed,
    format_trade_submitted,
)
from src.utils import now_et as _now_et

logger = logging.getLogger(__name__)


def _env_bool(key: str, default: bool) -> bool:
    from src.utils import env_bool
    return env_bool(key, default)


def _env_int(key: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return default


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm for Easter Sunday."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observe(d: date) -> date:
    """如果假日落在周末，返回观察日（周六→周五，周日→周一）"""
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """第 n 个星期几（weekday: 0=Mon）"""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """某月最后一个星期几"""
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _us_market_holidays(year: int) -> set:
    """动态计算 NYSE 休市日（P1#22: 替代硬编码列表，永不过期）"""
    holidays = set()
    # 元旦
    holidays.add(_observe(date(year, 1, 1)))
    # 马丁·路德·金纪念日 — 1月第3个周一
    holidays.add(_nth_weekday(year, 1, 0, 3))
    # 总统日 — 2月第3个周一
    holidays.add(_nth_weekday(year, 2, 0, 3))
    # 耶稣受难日 — 复活节前的周五
    holidays.add(_easter(year) - timedelta(days=2))
    # 阵亡将士纪念日 — 5月最后一个周一
    holidays.add(_last_weekday(year, 5, 0))
    # 六月节 — 6月19日
    holidays.add(_observe(date(year, 6, 19)))
    # 独立日 — 7月4日
    holidays.add(_observe(date(year, 7, 4)))
    # 劳动节 — 9月第1个周一
    holidays.add(_nth_weekday(year, 9, 0, 1))
    # 感恩节 — 11月第4个周四
    holidays.add(_nth_weekday(year, 11, 3, 4))
    # 圣诞节 — 12月25日
    holidays.add(_observe(date(year, 12, 25)))
    return {d.strftime("%Y-%m-%d") for d in holidays}


def is_market_holiday(date_str: str) -> bool:
    """检查给定日期是否为美股休市日"""
    try:
        year = int(date_str[:4])
        return date_str in _us_market_holidays(year)
    except (ValueError, IndexError):
        return False


class TraderState(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    REVIEWING = "reviewing"
    PAUSED = "paused"
    ERROR = "error"


class TradingPipeline:
    """
    交易执行管道
    TradeProposal -> 决策验证 -> 风控审核 -> 下单 -> 记录 -> 监控
    """

    def __init__(
        self,
        risk_manager: Any = None,
        broker: Any = None,
        journal: Any = None,
        portfolio: Any = None,
        monitor: Any = None,
        notify_func: Optional[Callable] = None,
        decision_validator: Any = None,
    ):
        self.risk_manager = risk_manager
        self.broker = broker
        self.journal = journal
        self.portfolio = portfolio
        self.monitor = monitor
        self.notify = notify_func
        self.decision_validator = decision_validator
        self._execution_log: List[Dict] = []

    async def _safe_notify(self, msg: str) -> None:
        """Pipeline 通知 — 只推成交和风控相关"""
        if not self.notify:
            return
        text = str(msg or "")
        if not text.strip():
            return

        only_fills = os.getenv("AUTO_TRADE_NOTIFY_ONLY_FILLS", "false").lower() in {"1", "true", "yes", "on"}
        if only_fills:
            p0_keywords = (
                "交易待成交", "交易已成交", "成交回写完成", "次日重挂已提交",
                "卖出完成", "止损触发", "止盈触发", "追踪止损",
                "自动停机", "熔断", "风控拒绝", "决策验证拒绝",
            )
            if not any(kw in text for kw in p0_keywords):
                logger.debug("[Pipeline] 已静默非成交通知: %s", text[:120])
                return
        try:
            await self.notify(text)
        except Exception as e:
            logger.warning("[Pipeline] 通知发送失败: %s", e)

    async def execute_proposal(
        self,
        proposal: TradeProposal,
        pre_fetched_analysis: Optional[Dict] = None,
    ) -> Dict:
        """执行单个交易提案 - 完整管道

        Args:
            proposal: 待执行的交易提案
            pre_fetched_analysis: 已获取的技术分析数据（P1#18: 传给 DecisionValidator 避免重复获取）
        """
        result = {
            "symbol": proposal.symbol,
            "action": proposal.action,
            "status": "pending",
            "steps": [],
        }

        # Step 0: 跳过非交易提案
        if proposal.action in ("HOLD", "WAIT"):
            result["status"] = "skipped"
            result["reason"] = "AI建议观望"
            return result

        # Step 0.5: 决策验证（反幻觉检查）
        if self.decision_validator and proposal.action == "BUY":
            try:
                validation = await self.decision_validator.validate(
                    proposal, pre_fetched_analysis=pre_fetched_analysis
                )
                result["steps"].append({"decision_validation": str(validation)})
                if not validation.approved:
                    result["status"] = "rejected"
                    result["reason"] = "决策验证失败: " + "; ".join(validation.issues)
                    logger.warning(
                        "[Pipeline] 决策验证拒绝: %s %s - %s",
                        proposal.symbol, proposal.action, validation.issues,
                    )
                    if self.notify:
                        await self._safe_notify(
                            "决策验证拒绝 %s %s\n原因: %s"
                            % (proposal.symbol, proposal.action, "; ".join(validation.issues))
                        )
                    return result
                if validation.warnings:
                    result["steps"].append({"validation_warnings": validation.warnings})
                # 如果验证器调整了提案，使用调整后的版本
                if validation.adjusted_proposal:
                    proposal = validation.adjusted_proposal
            except Exception as e:
                logger.warning("[Pipeline] 决策验证异常(%s)，继续执行", e)
                result["steps"].append({"validation_error": str(e)})

        # Step 1: 风控审核
        if self.risk_manager and proposal.action == "BUY":
            current_positions = []
            # 优先使用 IBKR 实际持仓
            if self.broker and hasattr(self.broker, 'is_connected') and self.broker.is_connected():
                try:
                    ibkr_positions = await self.broker.get_positions()
                    current_positions = ibkr_positions if ibkr_positions else []
                except Exception as e:
                    logger.warning("[Pipeline] 获取IBKR持仓失败(%s)，降级模拟持仓", e)
                    if self.portfolio:
                        current_positions = self.portfolio.get_positions()
            elif self.portfolio:
                current_positions = self.portfolio.get_positions()

            check = self.risk_manager.check_trade(
                symbol=proposal.symbol,
                side=proposal.action,
                quantity=proposal.quantity,
                entry_price=proposal.entry_price,
                stop_loss=proposal.stop_loss,
                take_profit=proposal.take_profit,
                signal_score=proposal.signal_score,
                current_positions=current_positions,
            )
            result["steps"].append({"risk_check": str(check)})

            if not check.approved:
                result["status"] = "rejected"
                result["reason"] = check.reason
                logger.warning(
                    "[Pipeline] 风控拒绝: %s %s - %s",
                    proposal.symbol, proposal.action, check.reason,
                )
                if self.notify:
                    await self._safe_notify(
                        "风控拒绝 %s %s\n原因: %s"
                        % (proposal.symbol, proposal.action, check.reason)
                    )
                return result

            if check.adjusted_quantity is not None:
                old_qty = proposal.quantity
                proposal.quantity = int(check.adjusted_quantity)
                result["steps"].append({
                    "qty_adjusted": "%d -> %d" % (old_qty, proposal.quantity)
                })

        if proposal.quantity <= 0:
            result["status"] = "rejected"
            result["reason"] = "数量为0"
            return result

        # Step 2: 执行下单
        order_result = None
        if self.broker:
            try:
                if proposal.action == "BUY":
                    order_result = await self.broker.buy(
                        symbol=proposal.symbol,
                        quantity=proposal.quantity,
                        decided_by=proposal.decided_by,
                        reason=proposal.reason,
                    )
                elif proposal.action == "SELL":
                    order_result = await self.broker.sell(
                        symbol=proposal.symbol,
                        quantity=proposal.quantity,
                        decided_by=proposal.decided_by,
                        reason=proposal.reason,
                    )
                result["steps"].append({"order": order_result})
                # IBKR返回error时回退到模拟组合
                if order_result and "error" in order_result and self.portfolio:
                    logger.warning("[Pipeline] IBKR失败(%s)，回退到模拟组合",
                                   order_result.get("error", ""))
                    result["steps"].append({"broker_fallback": "sim"})
                    order_result = None  # 清除错误，走下面的模拟逻辑
            except Exception as e:
                logger.warning("[Pipeline] IBKR异常(%s)，回退到模拟组合", e)
                result["steps"].append({"broker_error": str(e)})
                order_result = None  # 走下面的模拟逻辑

        if order_result is None and self.portfolio:
            if proposal.action == "BUY":
                order_result = self.portfolio.buy(
                    symbol=proposal.symbol,
                    quantity=proposal.quantity,
                    price=proposal.entry_price,
                    decided_by=proposal.decided_by,
                    reason=proposal.reason,
                )
                result["steps"].append({"sim_order": order_result})
            elif proposal.action == "SELL":
                order_result = self.portfolio.sell(
                    symbol=proposal.symbol,
                    quantity=proposal.quantity,
                    price=proposal.entry_price,
                    decided_by=proposal.decided_by,
                    reason=proposal.reason,
                )
                result["steps"].append({"sim_order": order_result})

        if order_result and "error" in order_result:
            result["status"] = "error"
            result["reason"] = order_result["error"]
            return result

        order_status = str(order_result.get("status", "") or "") if order_result else ""
        filled_qty = float(order_result.get("filled_qty", 0) or 0) if order_result else 0.0
        pending_statuses = {"Submitted", "PreSubmitted", "PendingSubmit", "ApiPending", "PendingCancel"}
        is_entry_pending = (
            proposal.action == "BUY"
            and self.broker is not None
            and order_result is not None
            and bool(order_result.get("order_id"))
            and order_status in pending_statuses
            and filled_qty <= 0
        )

        # P0#3: 使用实际成交价（而非AI提议价）作为后续所有计算的基准
        fill_price = proposal.entry_price
        if order_result and order_result.get("avg_price", 0) > 0:
            fill_price = order_result["avg_price"]

        # P0#6: 检测是否为模拟降级交易
        is_simulated_fallback = False
        if self.broker and order_result:
            # 有 broker 但结果来自模拟组合（无 order_id 或有 sim 标记）
            if "sim_order" in str(result.get("steps", [])):
                is_simulated_fallback = True

        # Step 3: 记录到交易日志
        trade_id = None
        if self.journal and proposal.action == "BUY":
            try:
                entry_order_id = str(order_result.get("order_id", "")) if order_result else ""
                trade_id = self.journal.open_trade(
                    symbol=proposal.symbol,
                    side="BUY",
                    quantity=proposal.quantity,
                    entry_price=fill_price,
                    stop_loss=proposal.stop_loss,
                    take_profit=proposal.take_profit,
                    signal_score=proposal.signal_score,
                    entry_reason=proposal.reason,
                    decided_by=proposal.decided_by,
                    entry_order_id=entry_order_id,
                    status="pending" if is_entry_pending else "open",
                )
                result["trade_id"] = trade_id
                if is_entry_pending:
                    result["steps"].append({"journal": "trade #%s (pending)" % trade_id})
                else:
                    result["steps"].append({"journal": "trade #%s" % trade_id})
            except Exception as e:
                logger.error("[Pipeline] 记录日志失败: %s", e)

        # Step 4: 添加到持仓监控
        if self.monitor and trade_id and proposal.action == "BUY" and not is_entry_pending:
            try:
                from src.position_monitor import MonitoredPosition, _now_et
                mon_pos = MonitoredPosition(
                    trade_id=trade_id,
                    symbol=proposal.symbol,
                    side="BUY",
                    quantity=proposal.quantity,
                    entry_price=fill_price,  # P0#3: 用实际成交价
                    entry_time=_now_et(),     # P0#2: 用美东时间
                    stop_loss=proposal.stop_loss,
                    take_profit=proposal.take_profit,
                    trailing_stop_pct=proposal.trailing_stop_pct,
                    max_hold_hours=proposal.max_hold_hours,
                    atr=proposal.atr,
                )
                self.monitor.add_position(mon_pos)
                result["steps"].append({"monitor": "added"})
            except Exception as e:
                logger.error("[Pipeline] 添加监控失败: %s", e)

        if is_entry_pending:
            pending_order_id = (
                order_result.get("order_id", "?")
                if isinstance(order_result, dict)
                else "?"
            )
            result["status"] = "submitted"
            result["quantity"] = proposal.quantity
            result["entry_price"] = fill_price
            result["reason"] = "订单已提交，等待成交回写"
            result["order_id"] = pending_order_id

            if self.notify:
                await self._safe_notify(
                    format_trade_submitted(
                        proposal.action,
                        proposal.symbol,
                        proposal.quantity,
                        pending_order_id,
                        status=order_status or "Submitted",
                    )
                )

            self._execution_log.append(result)
            if len(self._execution_log) > 200:
                self._execution_log = self._execution_log[-200:]
            logger.info(
                "[Pipeline] 订单已提交待成交: %s %s x%d (order_id=%s)",
                proposal.action,
                proposal.symbol,
                proposal.quantity,
                pending_order_id,
            )
            return result

        result["status"] = "executed"
        result["quantity"] = proposal.quantity
        result["entry_price"] = fill_price  # P0#3: 返回实际成交价

        # Step 5: 通知
        if self.notify:
            sim_tag = "模拟降级: IBKR 下单失败，仅保留模拟记录" if is_simulated_fallback else ""
            msg = format_trade_executed(
                proposal.action,
                proposal.symbol,
                proposal.quantity,
                fill_price,
                proposal.stop_loss,
                proposal.take_profit,
                proposal.signal_score,
                proposal.decided_by,
                proposal.reason,
                extra_flag=sim_tag,
            )
            await self._safe_notify(msg)

        self._execution_log.append(result)
        # P1#11: 限制 execution_log 大小
        if len(self._execution_log) > 200:
            self._execution_log = self._execution_log[-200:]
        logger.info(
            "[Pipeline] 执行完成: %s %s x%d @ $%.2f",
            proposal.action, proposal.symbol,
            proposal.quantity, proposal.entry_price,
        )
        return result


def parse_trade_proposal(text: str, symbol: str = "") -> Optional[TradeProposal]:
    """从AI回复文本中解析交易提案"""
    text_lower = text.lower()

    json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            from json_repair import loads as jloads
            data = jloads(json_match.group())
            return TradeProposal(
                symbol=data.get("symbol", symbol).upper(),
                action=data.get("action", "HOLD").upper(),
                quantity=int(data.get("quantity", data.get("qty", 0))),
                entry_price=float(data.get("entry_price", 0)),
                stop_loss=float(data.get("stop_loss", 0)),
                take_profit=float(data.get("take_profit", 0)),
                confidence=float(data.get("confidence", 0.5)),
                reason=data.get("reason", ""),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[AutoTrader] 解析AI交易信号失败, 将回退到关键词匹配: %s", e)

    action = "HOLD"
    buy_words = ["买入", "做多", "buy", "long", "建仓"]
    sell_words = ["卖出", "做空", "sell", "short", "平仓"]
    hold_words = ["观望", "hold", "wait", "不操作"]

    if any(w in text_lower for w in buy_words):
        action = "BUY"
    elif any(w in text_lower for w in sell_words):
        action = "SELL"
    elif any(w in text_lower for w in hold_words):
        action = "HOLD"

    # P1#16: 用标签匹配提取价格，避免误取 RSI/日期/数量等数字
    entry = 0.0
    stop = 0.0
    target = 0.0

    # 优先匹配带标签的价格
    entry_m = re.search(r'(?:entry|入场|买入价|price)[^\d$]*\$?([\d]+\.?\d*)', text, re.IGNORECASE)
    stop_m = re.search(r'(?:stop.?loss|止损|stop)[^\d$]*\$?([\d]+\.?\d*)', text, re.IGNORECASE)
    target_m = re.search(r'(?:take.?profit|target|止盈|目标)[^\d$]*\$?([\d]+\.?\d*)', text, re.IGNORECASE)

    if entry_m:
        entry = float(entry_m.group(1))
    if stop_m:
        stop = float(stop_m.group(1))
    if target_m:
        target = float(target_m.group(1))

    # 如果标签匹配失败，降级为 $ 前缀的数字（比裸数字安全）
    if entry == 0:
        dollar_prices = re.findall(r'\$([\d]+\.?\d*)', text)
        dollar_prices = [float(p) for p in dollar_prices if 0.5 < float(p) < 100000]
        if len(dollar_prices) >= 1:
            entry = dollar_prices[0]
        if len(dollar_prices) >= 2 and stop == 0:
            stop = dollar_prices[1]
        if len(dollar_prices) >= 3 and target == 0:
            target = dollar_prices[2]

    return TradeProposal(
        symbol=symbol.upper() if symbol else "",
        action=action,
        entry_price=entry,
        stop_loss=stop,
        take_profit=target,
        reason=text[:200],
    )


class AutoTrader:
    """
    自主交易调度器
    定时运行完整的 扫描->分析->决策->执行->监控 闭环
    """

    def __init__(
        self,
        pipeline: Optional[TradingPipeline] = None,
        scan_func: Optional[Callable] = None,
        analyze_func: Optional[Callable] = None,
        get_quote_func: Optional[Callable] = None,
        notify_func: Optional[Callable] = None,
        risk_manager: Any = None,
        scan_interval_minutes: int = 30,
        max_trades_per_cycle: int = 2,
        max_trades_per_day: int = 6,
        max_candidates_for_vote: int = 5,
        auto_mode: bool = False,
        ai_team_func: Optional[Callable] = None,
    ):
        self.pipeline = pipeline
        self.scan_market = scan_func
        self.analyze = analyze_func
        self.get_quote = get_quote_func
        self.notify = notify_func
        self.risk_manager = risk_manager
        self.scan_interval = scan_interval_minutes
        self.max_trades_per_cycle = max_trades_per_cycle
        self.max_trades_per_day = max_trades_per_day
        self.max_candidates_for_vote = max_candidates_for_vote
        self.auto_mode = auto_mode
        self.ai_team_func = ai_team_func  # AI团队投票函数

        self.state = TraderState.IDLE
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._cycle_count = 0
        self._today_trades = 0  # 今日已执行交易数
        self._today_date = ""   # 用于日切重置
        self._last_scan: Optional[datetime] = None
        self._scan_results: List[Dict] = []
        self._proposals: List[TradeProposal] = []
        self._cycle_lock = asyncio.Lock()  # 防止并发循环执行
        self._no_trade_cycles = 0
        self._forced_trades_today = 0

        # 防空仓策略：连续空仓后，允许执行小规模探索交易（仍经过风控）
        self.force_trade_on_idle = _env_bool("FORCE_TRADE_ON_IDLE", True)
        self.force_trade_after_idle_cycles = _env_int("FORCE_TRADE_AFTER_IDLE_CYCLES", 3, minimum=1)
        self.force_trade_min_score = _env_int("FORCE_TRADE_MIN_SCORE", 30, minimum=10)
        self.max_forced_trades_per_day = _env_int("MAX_FORCED_TRADES_PER_DAY", 1, minimum=0)

        logger.info(
            "[AutoTrader] 初始化 | 扫描间隔=%dmin | 自动模式=%s | 日限%d笔 | 候选池%d | 防空仓=%s(%d轮/%d分)",
            scan_interval_minutes,
            auto_mode,
            max_trades_per_day,
            max_candidates_for_vote,
            "开" if self.force_trade_on_idle else "关",
            self.force_trade_after_idle_cycles,
            self.force_trade_min_score,
        )

    # ============ 生命周期 ============

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.state = TraderState.IDLE
        self._task = asyncio.create_task(self._main_loop())
        logger.info("[AutoTrader] 已启动")
        await self._safe_notify(
            "AutoTrader 已启动\n扫描间隔: %d分钟\n自动模式: %s"
            % (self.scan_interval, "开启" if self.auto_mode else "关闭")
        )

    async def stop(self) -> None:
        self._running = False
        self.state = TraderState.IDLE
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[AutoTrader] 已停止")

    async def _safe_notify(self, msg: str) -> None:
        """安全发送通知 — 分级过滤，只推重要信息"""
        if not self.notify:
            return
        text = str(msg or "")
        if not text.strip():
            return

        # 重要性分级：P0 必推、P1 默认推、P2 静默
        # P0: 成交、止损止盈、自动停机、风控拒绝 — 涉及真金白银
        p0_keywords = (
            "交易待成交", "交易已成交", "成交回写完成", "次日重挂已提交",
            "卖出完成", "止损触发", "止盈触发", "追踪止损",
            "自动停机", "熔断", "日亏损限额",
            "风控拒绝", "决策验证拒绝",
        )
        # P1: 交易循环摘要、扫描结果、AI投票结论 — 有信息量
        p1_keywords = (
            "阶段 4/4", "阶段 3/4: AI团队投票完成",
            "防空仓策略", "IBKR 未连接",
            "今日已达交易上限",
        )

        is_p0 = any(kw in text for kw in p0_keywords)
        is_p1 = any(kw in text for kw in p1_keywords)

        only_fills = os.getenv("AUTO_TRADE_NOTIFY_ONLY_FILLS", "false").lower() in {"1", "true", "yes", "on"}

        if only_fills and not is_p0:
            logger.debug("[AutoTrader] 静默非P0通知: %s", text[:120])
            return

        if not only_fills and not is_p0 and not is_p1:
            # 非静默模式下，P2 通知也静默（扫描中...、获取数据中... 等过程信息）
            quiet_mode = os.getenv("AUTO_TRADE_QUIET_MODE", "true").lower() in {"1", "true", "yes", "on"}
            if quiet_mode:
                logger.debug("[AutoTrader] 静默P2通知: %s", text[:120])
                return

        try:
            await self.notify(text)
        except Exception as e:
            logger.warning("[AutoTrader] 通知发送失败: %s", e)

    def _get_capital(self) -> float:
        """Return configured total capital, defaulting to 2000."""
        if self.risk_manager and hasattr(self.risk_manager, 'config'):
            return float(getattr(self.risk_manager.config, 'total_capital', 2000.0))
        return 2000.0

    def _estimate_open_exposure(self) -> float:
        """估算当前组合已开仓总敞口（用于提案前仓位裁剪）"""
        if not self.pipeline or not getattr(self.pipeline, "portfolio", None):
            return 0.0
        try:
            positions = self.pipeline.portfolio.get_positions()
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

    def _remaining_exposure_budget(self) -> float:
        """计算剩余可用总敞口额度"""
        if not self.risk_manager or not hasattr(self.risk_manager, "config"):
            return float("inf")
        cfg = self.risk_manager.config
        max_exposure = float(getattr(cfg, "total_capital", 2000.0)) * float(
            getattr(cfg, "max_total_exposure_pct", 0.8)
        )
        current_exposure = self._estimate_open_exposure()
        return max(0.0, max_exposure - current_exposure)

    def _build_account_context(self) -> str:
        """构建账户上下文信息供AI投票参考 — 含近期交易结果（闭环学习）"""
        lines = ["[账户状态]"]
        capital = self._get_capital()
        lines.append("总资金: $%.0f" % capital)
        lines.append("单笔风险: 2%% ($%.0f)" % (capital * 0.02))
        lines.append("今日已交易: %d/%d笔" % (self._today_trades, self.max_trades_per_day))

        # 今日盈亏
        if self.risk_manager:
            today_pnl = getattr(self.risk_manager, '_today_pnl', 0)
            lines.append("今日已实现盈亏: $%.2f" % today_pnl)
            daily_limit = 100
            if hasattr(self.risk_manager, 'config'):
                daily_limit = getattr(self.risk_manager.config, 'daily_loss_limit', 100)
            lines.append("日亏损限额: $%.0f (剩余$%.0f)" % (daily_limit, daily_limit + today_pnl))

        # 当前持仓数
        if self.pipeline and self.pipeline.monitor:
            pos_count = len(self.pipeline.monitor.positions)
            lines.append("当前持仓: %d笔" % pos_count)

        # 闭环学习：注入近期交易结果 + 教训
        try:
            from src.trading_journal import journal as tj
            if tj:
                closed = tj.get_closed_trades(days=3, limit=5) if hasattr(tj, 'get_closed_trades') else []
                if closed:
                    lines.append("\n[近3日交易结果]")
                    for t in closed[:5]:
                        lines.append(
                            "  %s %s PnL=$%+.2f (%+.1f%%) 持仓%.1fh | %s"
                            % (t.get("side", "?"), t.get("symbol", "?"),
                               t.get("pnl", 0), t.get("pnl_pct", 0),
                               t.get("hold_duration_hours", 0) or 0,
                               (t.get("exit_reason") or t.get("entry_reason") or "")[:40])
                        )
                # 注入迭代教训
                if hasattr(tj, 'generate_iteration_report'):
                    report = tj.generate_iteration_report(days=7)
                    suggestions = report.get("improvement_suggestions", []) if isinstance(report, dict) else []
                    if suggestions:
                        lines.append("\n[近7日教训]")
                        for s in suggestions[:3]:
                            lines.append("  - " + str(s))
        except Exception:
            pass  # journal 不可用不影响投票

        return "\n".join(lines)

    async def _enrich_candidates_with_broker_quotes(self, candidates: List[Dict]) -> None:
        """用 IBKR 实时快照刷新候选现价，减少数据滞后"""
        if not candidates:
            return
        if not _env_bool("ENRICH_CANDIDATES_WITH_IBKR_QUOTES", True):
            return
        if not self.pipeline or not self.pipeline.broker:
            return
        broker = self.pipeline.broker
        if not hasattr(broker, "get_realtime_snapshot"):
            return

        limit = min(len(candidates), _env_int("IBKR_QUOTE_ENRICH_TOP", 12, minimum=1))
        sem = asyncio.Semaphore(4)

        async def _fetch_and_apply(item: Dict):
            symbol = item.get("symbol", "")
            if not symbol:
                return
            async with sem:
                try:
                    snap = await broker.get_realtime_snapshot(symbol)
                    if not isinstance(snap, dict) or "error" in snap:
                        return
                    price = float(snap.get("price", 0) or 0)
                    if price <= 0:
                        return
                    item["price"] = round(price, 2)
                    if "change_pct" in snap:
                        item["change_pct"] = round(float(snap.get("change_pct", 0) or 0), 2)
                except Exception as e:
                    logger.debug("[AutoTrader] 实时报价刷新失败 %s: %s", symbol, e)

        await asyncio.gather(*[_fetch_and_apply(c) for c in candidates[:limit]], return_exceptions=True)

    async def _main_loop(self) -> None:
        while self._running:
            try:
                # 使用美东时间判断交易时段
                et_now = _now_et()

                weekday = et_now.weekday()
                hour = et_now.hour
                minute = et_now.minute

                # 周末不交易
                if weekday >= 5:
                    await asyncio.sleep(3600)
                    continue

                # 美股假日不交易
                today_str = et_now.strftime("%Y-%m-%d")
                if is_market_holiday(today_str):
                    logger.info("[AutoTrader] 今日 %s 为美股休市日，跳过", today_str)
                    await asyncio.sleep(3600)
                    continue

                # 美东时间 9:30-16:00 为交易时段
                market_open = (hour > 9) or (hour == 9 and minute >= 30)
                market_close = hour >= 16

                if not market_open or market_close:
                    # 收盘后不再在此处复盘，由 Scheduler eod_auto_review 统一处理
                    await asyncio.sleep(600)
                    continue

                # 执行交易循环（带并发锁）
                async with self._cycle_lock:
                    await self._run_cycle()
                self._cycle_count += 1

            except Exception as e:
                self.state = TraderState.ERROR
                logger.error("[AutoTrader] 主循环异常: %s", e, exc_info=True)
                await self._safe_notify("AutoTrader 异常: %s" % e)

            await asyncio.sleep(self.scan_interval * 60)

    # ============ 交易循环 ============

    async def run_cycle_once(self) -> Dict:
        """手动触发一次交易循环（带并发锁）"""
        if self._cycle_lock.locked():
            return {"error": "交易循环正在执行中，请稍后再试"}
        async with self._cycle_lock:
            return await self._run_cycle()

    async def _run_cycle(self) -> Dict:
        """执行一次完整的交易循环 — 4阶段全程Telegram播报"""
        cycle_result = {
            "cycle": self._cycle_count,
            "time": _now_et().isoformat(),
            "scanned": 0,
            "candidates": 0,
            "analyzed": 0,
            "voted": 0,
            "proposals": 0,
            "submitted": 0,
            "executed": 0,
            "rejected": 0,
        }

        # P0#8: 日切重置使用美东时间
        _et_now = _now_et()
        today = _et_now.strftime("%Y-%m-%d")
        if today != self._today_date:
            self._today_date = today
            self._today_trades = 0
            self._forced_trades_today = 0
            self._no_trade_cycles = 0

        # ========== IBKR 连接预检 ==========
        if self.pipeline and self.pipeline.broker:
            _broker = self.pipeline.broker
            if hasattr(_broker, 'ensure_connected'):
                try:
                    _connected = await _broker.ensure_connected()
                    if _connected:
                        logger.info("[AutoTrader] IBKR 连接就绪")
                    else:
                        logger.warning("[AutoTrader] IBKR 连接失败，本轮将以模拟模式运行")
                        await self._safe_notify("IBKR 未连接，本轮降级为模拟模式")
                except Exception as _conn_err:
                    logger.warning("[AutoTrader] IBKR 连接检查异常: %s", _conn_err)

        # 每日交易次数限制
        remaining_today = self.max_trades_per_day - self._today_trades
        if remaining_today <= 0:
            await self._safe_notify(
                "今日已达交易上限 (%d/%d笔)，停止扫描。\n明日自动继续。"
                % (self._today_trades, self.max_trades_per_day)
            )
            self.state = TraderState.IDLE
            return cycle_result

        # ========== 阶段1: 全市场扫描 ==========
        self.state = TraderState.SCANNING
        logger.info("[AutoTrader] === 交易循环 #%d ===", self._cycle_count)

        await self._safe_notify(
            "-- 交易循环 #%d 开始 --\n"
            "阶段 1/4: 全市场扫描中...\n"
            "今日已交易: %d/%d笔"
            % (self._cycle_count, self._today_trades, self.max_trades_per_day)
        )

        if self.scan_market:
            try:
                self._scan_results = await self.scan_market()
                self._last_scan = _now_et()
                cycle_result["scanned"] = len(self._scan_results)
            except Exception as e:
                logger.error("[AutoTrader] 扫描失败: %s", e)
                await self._safe_notify("扫描失败: %s" % e)
                self.state = TraderState.ERROR
                return cycle_result

        if not self._scan_results:
            await self._safe_notify(
                "阶段 1/4: 扫描完成，无信号。\n市场平静，继续观望。"
            )
            self.state = TraderState.IDLE
            return cycle_result

        # ========== 阶段2: 多层筛选 ==========
        candidates = self._filter_candidates(self._scan_results)
        cycle_result["candidates"] = len(candidates)

        # 扩大候选池: 取 Top N 进入分析
        top_candidates = candidates[:self.max_candidates_for_vote]

        # 用 IBKR 快照刷新 Top 候选报价
        await self._enrich_candidates_with_broker_quotes(top_candidates)

        if self.notify:
            scan_lines = [
                "阶段 1/4: 扫描完成\n"
                "扫描 %d 个标的 -> 筛选出 %d 个候选\n"
                % (cycle_result["scanned"], len(candidates))
            ]
            for i, c in enumerate(top_candidates):
                arrow = "+" if c.get("change_pct", 0) >= 0 else ""
                scan_lines.append(
                    "  %d. %s $%.2f (%s%.1f%%) 评分:%+d %s"
                    % (i + 1, c.get("symbol", "?"), c.get("price", 0),
                       arrow, c.get("change_pct", 0), c.get("score", 0),
                       c.get("signal_cn", ""))
                )
            if not top_candidates:
                scan_lines.append("  无符合条件的候选，继续观望。")
            await self._safe_notify("\n".join(scan_lines))

        if not top_candidates:
            self.state = TraderState.IDLE
            return cycle_result

        # ========== 阶段3: AI团队分析 + 投票 ==========
        self.state = TraderState.ANALYZING

        await self._safe_notify(
            "阶段 2/4: 获取 %d 个候选的详细技术数据..."
            % len(top_candidates)
        )

        # 优先复用扫描阶段已获取的分析数据（避免重复调用 yfinance 被限流）
        analyses = {}
        _need_fetch = []
        for c in top_candidates:
            sym = c.get("symbol", "")
            cached = c.get("_full_analysis")
            if isinstance(cached, dict) and "error" not in cached:
                analyses[sym] = cached
                cycle_result["analyzed"] = cycle_result.get("analyzed", 0) + 1
            else:
                _need_fetch.append(c)

        analyze_func = self.analyze if callable(self.analyze) else None
        if _need_fetch and analyze_func:
            logger.info("[AutoTrader] %d/%d 候选需重新获取技术数据", len(_need_fetch), len(top_candidates))
            _analysis_sem = asyncio.Semaphore(3)
            analyze_impl = analyze_func

            async def _limited_analyze(sym: str):
                async with _analysis_sem:
                    return await analyze_impl(sym)

            tasks = [_limited_analyze(c.get("symbol", "")) for c in _need_fetch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for c, r in zip(_need_fetch, results):
                sym = c.get("symbol", "")
                if isinstance(r, Exception):
                    logger.warning("[AutoTrader] %s 技术分析异常: %s", sym, r)
                elif isinstance(r, dict) and "error" not in r:
                    analyses[sym] = r
                    cycle_result["analyzed"] = cycle_result.get("analyzed", 0) + 1
        elif not _need_fetch:
            logger.info("[AutoTrader] 全部 %d 候选已有缓存分析数据，跳过重复获取", len(top_candidates))

        await self._safe_notify(
            "阶段 2/4: 技术数据就绪 (%d/%d)\n\n"
            "阶段 3/4: AI团队投票决策中...\n"
            "雷达 -> 宏观 -> 图表 -> 风控 -> 指挥官"
            % (len(analyses), len(top_candidates))
        )

        # AI团队投票
        voted_results = []
        if self.ai_team_func:
            try:
                # 构建账户上下文供AI参考
                account_ctx = self._build_account_context()
                voted_results = await self.ai_team_func(
                    candidates=top_candidates,
                    analyses=analyses,
                    notify_func=self._safe_notify,
                    max_candidates=self.max_candidates_for_vote,
                    account_context=account_ctx,
                )
                cycle_result["voted"] = len(voted_results)
            except Exception as e:
                logger.error("[AutoTrader] AI团队投票失败: %s", e)
                await self._safe_notify("AI团队投票异常: %s\n降级为机械策略" % e)

        # 从投票结果生成提案
        proposals = []
        exposure_budget_left = self._remaining_exposure_budget()
        if voted_results:
            for vr in voted_results:
                if vr.decision != "BUY":
                    continue
                # 用投票的加权平均价格，或从候选数据中取
                candidate = next(
                    (c for c in top_candidates if c.get("symbol") == vr.symbol), {}
                )
                price = vr.avg_entry if vr.avg_entry > 0 else candidate.get("price", 0)
                stop = vr.avg_stop if vr.avg_stop > 0 else round(price * 0.97, 2)
                target = vr.avg_target if vr.avg_target > 0 else round(price * 1.06, 2)

                # P1#25: 如果有 ATR 数据，用 ATR-based 止损替代固定 3%
                atr_val = candidate.get("atr_pct", 0)
                if atr_val > 0 and vr.avg_stop <= 0:
                    stop = round(price - 1.5 * (atr_val / 100) * price, 2)

                if price <= 0:
                    continue

                quantity = 0
                if self.risk_manager:
                    sizing = self.risk_manager.calc_safe_quantity(
                        entry_price=price, stop_loss=stop,
                    )
                    if "error" not in sizing:
                        quantity = sizing["shares"]
                if quantity <= 0:
                    quantity = max(1, int(self._get_capital() * 0.20 / price))

                if exposure_budget_left <= 0:
                    logger.info("[AutoTrader] 总敞口额度已用尽，跳过新增提案")
                    break
                max_qty_by_exposure = int(exposure_budget_left / price)
                if max_qty_by_exposure <= 0:
                    logger.info("[AutoTrader] %s 可用敞口不足，跳过", vr.symbol)
                    continue
                if quantity > max_qty_by_exposure:
                    logger.info(
                        "[AutoTrader] %s 数量按剩余敞口裁剪: %d -> %d",
                        vr.symbol,
                        quantity,
                        max_qty_by_exposure,
                    )
                    quantity = max_qty_by_exposure
                if quantity <= 0:
                    continue

                proposals.append(TradeProposal(
                    symbol=vr.symbol,
                    action="BUY",
                    quantity=quantity,
                    entry_price=price,
                    stop_loss=stop,
                    take_profit=target,
                    signal_score=candidate.get("score", 0),
                    confidence=vr.avg_confidence,
                    reason=vr.summary,
                    decided_by="AI团队投票(%d/%d)" % (vr.buy_count, len(vr.votes)),
                    atr=candidate.get("atr_pct", 2.0) / 100 * price,
                ))
                exposure_budget_left -= quantity * price
                if len(proposals) >= remaining_today:
                    break
        else:
            # 无AI团队时降级为机械策略
            for candidate in top_candidates[:min(self.max_trades_per_cycle, remaining_today)]:
                proposal = await self._generate_proposal(candidate)
                if proposal and proposal.action == "BUY":
                    if exposure_budget_left <= 0:
                        logger.info("[AutoTrader] 总敞口额度已用尽，停止生成提案")
                        break
                    max_qty_by_exposure = int(exposure_budget_left / proposal.entry_price) if proposal.entry_price > 0 else 0
                    if max_qty_by_exposure <= 0:
                        logger.info("[AutoTrader] %s 可用敞口不足，跳过", proposal.symbol)
                        continue
                    if proposal.quantity > max_qty_by_exposure:
                        logger.info(
                            "[AutoTrader] %s 数量按剩余敞口裁剪: %d -> %d",
                            proposal.symbol,
                            proposal.quantity,
                            max_qty_by_exposure,
                        )
                        proposal.quantity = max_qty_by_exposure
                    if proposal.quantity <= 0:
                        continue
                    proposals.append(proposal)
                    exposure_budget_left -= proposal.quantity * proposal.entry_price

        # 防空仓策略：连续多轮无提案时，强制从高分候选中挑选小规模探索仓位
        if not proposals:
            self._no_trade_cycles += 1
            forced_quota = max(0, self.max_forced_trades_per_day - self._forced_trades_today)
            can_force = (
                self.force_trade_on_idle
                and self.auto_mode
                and forced_quota > 0
                and self._no_trade_cycles >= self.force_trade_after_idle_cycles
            )
            if can_force:
                forced_limit = min(self.max_trades_per_cycle, remaining_today, forced_quota)
                force_candidates = [
                    c for c in top_candidates
                    if c.get("score", 0) >= self.force_trade_min_score
                ][:forced_limit]
                for c in force_candidates:
                    p = await self._generate_proposal(c)
                    if p and p.action == "BUY":
                        if exposure_budget_left <= 0:
                            break
                        max_qty_by_exposure = int(exposure_budget_left / p.entry_price) if p.entry_price > 0 else 0
                        if max_qty_by_exposure <= 0:
                            continue
                        if p.quantity > max_qty_by_exposure:
                            p.quantity = max_qty_by_exposure
                        if p.quantity <= 0:
                            continue
                        p.decided_by = "AntiIdlePolicy"
                        p.reason = (
                            f"{p.reason} | 反空仓执行: 连续{self._no_trade_cycles}轮未达成AI共识"
                        )
                        proposals.append(p)
                        exposure_budget_left -= p.quantity * p.entry_price
                if proposals:
                    await self._safe_notify(
                        "阶段 3/4: 触发防空仓策略\n"
                        "连续 %d 轮无交易提案，启用探索仓位 %d 笔（最小评分>=%d）"
                        % (self._no_trade_cycles, len(proposals), self.force_trade_min_score)
                    )

        self._proposals = proposals
        cycle_result["proposals"] = len(proposals)

        if not proposals:
            await self._safe_notify(
                "阶段 3/4: AI团队投票完成\n"
                "结论: 暂无达成共识的交易机会，继续观望。\n"
                "连续无提案轮次: %d" % self._no_trade_cycles
            )
            self.state = TraderState.IDLE
            return cycle_result

        self._no_trade_cycles = 0

        # ========== 阶段4: 风控 + 执行 ==========
        if self.notify:
            prop_lines = ["阶段 4/4: 风控审核 + 执行\n"]
            for p in proposals:
                prop_lines.append(
                    "  BUY %s x%d @ $%.2f | 止损$%.2f 止盈$%.2f\n  %s"
                    % (p.symbol, p.quantity, p.entry_price,
                       p.stop_loss, p.take_profit, p.reason[:80])
                )
            await self._safe_notify("\n".join(prop_lines))

        if self.auto_mode and self.pipeline:
            self.state = TraderState.EXECUTING
            for proposal in proposals:
                try:
                    exec_result = await self.pipeline.execute_proposal(
                        proposal,
                        pre_fetched_analysis=analyses.get(proposal.symbol),
                    )
                    if exec_result["status"] == "executed":
                        cycle_result["executed"] += 1
                        self._today_trades += 1
                        if proposal.decided_by == "AntiIdlePolicy":
                            self._forced_trades_today += 1
                        # 结构化交易卡片 — 搬运自 freqtrade 通知格式
                        try:
                            from src.telegram_ux import format_trade_card
                            card = format_trade_card({
                                "action": proposal.action,
                                "symbol": proposal.symbol,
                                "quantity": proposal.quantity,
                                "entry_price": proposal.entry_price,
                                "stop_loss": proposal.stop_loss,
                                "take_profit": proposal.take_profit,
                                "reason": proposal.reason,
                                "confidence": proposal.confidence,
                            })
                            card += "\n\n今日交易: %d/%d笔" % (self._today_trades, self.max_trades_per_day)
                            await self._safe_notify(card)
                        except Exception:
                            await self._safe_notify(
                                "交易执行成功\n"
                                "BUY %s x%d @ $%.2f\n"
                                "止损: $%.2f | 止盈: $%.2f\n"
                                "今日交易: %d/%d笔"
                                % (proposal.symbol, proposal.quantity,
                                   proposal.entry_price, proposal.stop_loss,
                                   proposal.take_profit,
                                   self._today_trades, self.max_trades_per_day)
                            )
                    elif exec_result["status"] == "rejected":
                        cycle_result["rejected"] += 1
                        await self._safe_notify(
                            "交易被风控拒绝: %s %s\n原因: %s"
                            % (proposal.symbol, proposal.action,
                               exec_result.get("reason", "未知"))
                        )
                    elif exec_result["status"] == "submitted":
                        cycle_result["submitted"] += 1
                        await self._safe_notify(
                            "订单已提交待成交: %s %s x%d\n"
                            "订单ID: %s | 后续由回写校验器自动同步"
                            % (
                                proposal.action,
                                proposal.symbol,
                                proposal.quantity,
                                exec_result.get("order_id", "?"),
                            )
                        )
                except Exception as e:
                    logger.error("[AutoTrader] 执行失败: %s", e)
                    await self._safe_notify("执行异常: %s %s - %s" % (proposal.symbol, proposal.action, e))
        else:
            if self.notify:
                for p in proposals:
                    await self._safe_notify(
                        "交易提案 (待确认)\n"
                        "%s %s x%d @ $%.2f\n"
                        "止损: $%.2f | 止盈: $%.2f\n"
                        "理由: %s"
                        % (p.action, p.symbol, p.quantity, p.entry_price,
                           p.stop_loss, p.take_profit, p.reason)
                    )

        self.state = TraderState.MONITORING
        await self._safe_notify(
            "-- 循环 #%d 完成 --\n"
            "扫描%d -> 候选%d -> 分析%d -> 投票%d -> 提案%d -> 提交%d -> 执行%d 拒绝%d\n"
            "今日交易: %d/%d笔"
            % (self._cycle_count,
               cycle_result["scanned"], cycle_result["candidates"],
               cycle_result.get("analyzed", 0), cycle_result["voted"],
               cycle_result["proposals"], cycle_result["submitted"], cycle_result["executed"],
               cycle_result["rejected"],
               self._today_trades, self.max_trades_per_day)
        )

        logger.info(
            "[AutoTrader] 循环 #%d 完成: 扫描%d 候选%d 投票%d 提案%d 提交%d 执行%d 拒绝%d",
            self._cycle_count, cycle_result["scanned"],
            cycle_result["candidates"], cycle_result["voted"],
            cycle_result["proposals"],
            cycle_result["submitted"], cycle_result["executed"], cycle_result["rejected"],
        )
        return cycle_result

    def _filter_candidates(self, signals: List[Dict]) -> List[Dict]:
        """从扫描结果中筛选候选标的（自适应阈值）

        过滤条件（根据市场环境动态调整）:
        - score >= 15（市场冷清时）或 >= 25（市场火热时）
        - trend 非 strong_down
        - RSI6 <= 85（极端超买才过滤）
        - 价格 > $2（允许更多标的）
        - 20日均量 > 5万（降低流动性门槛）
        - ADX > 12（震荡市也可能有机会）
        """
        candidates = []
        _rejected = {"score": 0, "trend": 0, "rsi": 0, "price": 0, "volume": 0, "adx": 0}
        
        # 自适应评分阈值：根据信号数量动态调整
        high_score_count = sum(1 for s in signals if s.get("score", 0) >= 40)
        score_threshold = 25 if high_score_count >= 3 else 15
        
        for s in signals:
            score = s.get("score", 0)
            if score < score_threshold:
                _rejected["score"] += 1
                continue
            trend = s.get("trend", "sideways")
            if trend == "strong_down":
                _rejected["trend"] += 1
                continue
            rsi6 = s.get("rsi_6", 50)
            if rsi6 > 85:
                _rejected["rsi"] += 1
                continue
            price = s.get("price", 0)
            if price > 0 and price < 2:
                logger.debug("[Filter] %s 价格$%.2f < $2，跳过", s.get("symbol"), price)
                _rejected["price"] += 1
                continue
            vol_avg = s.get("vol_avg_20", 0)
            if vol_avg > 0 and vol_avg < 50_000:
                logger.debug("[Filter] %s 20日均量%d < 5万，跳过", s.get("symbol"), vol_avg)
                _rejected["volume"] += 1
                continue
            adx = s.get("adx", 0)
            if adx > 0 and adx < 12:
                logger.debug("[Filter] %s ADX=%.1f < 12 震荡市，跳过", s.get("symbol"), adx)
                _rejected["adx"] += 1
                continue
            candidates.append(s)

        # 统计日志：帮助诊断过滤是否过严
        total = len(signals)
        passed = len(candidates)
        logger.info(
            "[Filter] %d/%d 通过筛选 (阈值score>=%d) | 淘汰: score=%d trend=%d rsi=%d price=%d vol=%d adx=%d",
            passed, total, score_threshold, _rejected["score"], _rejected["trend"],
            _rejected["rsi"], _rejected["price"], _rejected["volume"], _rejected["adx"],
        )

        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        return candidates

    async def _generate_proposal(self, candidate: Dict) -> Optional[TradeProposal]:
        """为候选标的生成交易提案"""
        symbol = candidate.get("symbol", "")
        score = candidate.get("score", 0)
        price = candidate.get("price", 0)
        atr_pct = candidate.get("atr_pct", 2.0)

        if price <= 0:
            return None

        atr_mult = max(atr_pct / 100, 0.02)
        stop_loss = round(price * (1 - atr_mult * 1.5), 2)
        take_profit = round(price * (1 + atr_mult * 3), 2)

        quantity = 0
        if self.risk_manager:
            sizing = self.risk_manager.calc_safe_quantity(
                entry_price=price,
                stop_loss=stop_loss,
            )
            if "error" not in sizing:
                quantity = sizing["shares"]

        if quantity <= 0:
            # 根据总资金的20%计算单笔最大成本
            capital = self._get_capital()
            max_cost = capital * 0.20  # 单笔不超过总资金20%
            quantity = max(1, int(max_cost / price))

        reasons = candidate.get("reasons", [])
        reason_text = " | ".join(reasons) if reasons else ("信号评分%d" % score)

        return TradeProposal(
            symbol=symbol,
            action="BUY",
            quantity=quantity,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_score=score,
            confidence=min(abs(score) / 100, 1.0),
            reason=reason_text,
            decided_by="AutoTrader",
            atr=atr_mult * price,
        )

    async def _run_review(self) -> None:
        """收盘自动复盘 — 生成当日交易总结、持久化教训、通知"""
        self.state = TraderState.REVIEWING
        logger.info("[AutoTrader] 开始收盘复盘")
        try:
            from src.trading_journal import journal as tj
            today_pnl = tj.get_today_pnl()
            open_trades = tj.get_open_trades()
            closed = tj.get_closed_trades(days=1, limit=20)

            lines = ["-- AutoTrader 收盘复盘 --\n"]
            lines.append("今日盈亏: $%.2f (%d笔交易)" % (
                today_pnl.get("pnl", 0), today_pnl.get("trades", 0)))
            lines.append("扫描循环: %d次" % self._cycle_count)

            wins = 0
            losses = 0
            if closed:
                wins = sum(1 for t in closed if t.get("pnl", 0) >= 0)
                losses = len(closed) - wins
                lines.append("\n已平仓: %d笔 (盈%d 亏%d)" % (len(closed), wins, losses))
                for t in closed:
                    sign = "+" if t.get("pnl", 0) >= 0 else ""
                    lines.append("  %s %s %s$%.2f" % (
                        t.get("side", "?"), t.get("symbol", "?"),
                        sign, t.get("pnl", 0)))

            if open_trades:
                lines.append("\n持仓中: %d笔" % len(open_trades))
                for t in open_trades:
                    lines.append("  %s x%s @ $%s 止损$%s" % (
                        t.get("symbol", "?"), t.get("quantity", "?"),
                        t.get("entry_price", "?"), t.get("stop_loss", "无")))

            # 闭环学习：持久化复盘教训到 trading_journal
            lessons = ""
            try:
                trade_count = today_pnl.get("trades", 0)
                win_rate = round(wins / max(trade_count, 1) * 100, 1)

                # 生成迭代报告提取失败模式
                iteration = {}
                if hasattr(tj, 'generate_iteration_report'):
                    iteration = tj.generate_iteration_report(days=7)
                suggestions = iteration.get("improvement_suggestions", []) if isinstance(iteration, dict) else []
                lessons = "; ".join(str(s) for s in suggestions[:3])

                if hasattr(tj, 'save_review_session'):
                    from src.utils import today_et_str
                    tj.save_review_session(
                        date=today_et_str(),
                        session_type='daily',
                        trades_reviewed=trade_count,
                        total_pnl=today_pnl.get("pnl", 0),
                        win_rate=win_rate,
                        lessons_learned=lessons,
                        improvements="",
                    )
                    logger.info("[AutoTrader] 复盘教训已持久化")

                if lessons:
                    lines.append("\n📝 教训: " + lessons)
            except Exception as e:
                logger.warning("[AutoTrader] 复盘持久化失败(非致命): %s", e)

            lines.append("\n明日将自动继续交易。")

            await self._safe_notify("\n".join(lines))
        except Exception as e:
            logger.error("[AutoTrader] 复盘失败: %s", e)
            await self._safe_notify("收盘复盘生成失败: %s" % e)
        self.state = TraderState.IDLE

    # ============ 状态 ============

    def get_status(self) -> Dict:
        return {
            "state": self.state.value,
            "running": self._running,
            "auto_mode": self.auto_mode,
            "cycle_count": self._cycle_count,
            "scan_interval_min": self.scan_interval,
            "last_scan": self._last_scan.isoformat() if self._last_scan else None,
            "last_signals": len(self._scan_results),
            "pending_proposals": len(self._proposals),
            "no_trade_cycles": self._no_trade_cycles,
            "forced_trades_today": self._forced_trades_today,
        }

    def format_status(self) -> str:
        s = self.get_status()
        state_cn = {
            "idle": "空闲", "scanning": "扫描中", "analyzing": "分析中",
            "executing": "执行中", "monitoring": "监控中",
            "reviewing": "复盘中", "paused": "暂停", "error": "异常",
        }
        lines = [
            "AutoTrader 状态",
            "",
            "状态: %s" % state_cn.get(s["state"], s["state"]),
            "运行: %s" % ("是" if s["running"] else "否"),
            "自动模式: %s" % ("开启" if s["auto_mode"] else "关闭(需确认)"),
            "已完成循环: %d次" % s["cycle_count"],
            "扫描间隔: %d分钟" % s["scan_interval_min"],
            "上次扫描: %s" % (s["last_scan"] or "无"),
            "最近信号: %d个" % s["last_signals"],
            "待确认提案: %d个" % s["pending_proposals"],
            "连续无提案: %d轮" % s["no_trade_cycles"],
            "防空仓执行: %d/%d笔" % (s["forced_trades_today"], self.max_forced_trades_per_day),
        ]
        return "\n".join(lines)

    def set_auto_mode(self, enabled: bool) -> None:
        self.auto_mode = enabled
        logger.info("[AutoTrader] 自动模式: %s", "开启" if enabled else "关闭")

    async def confirm_proposal(self, index: int = 0) -> Optional[Dict]:
        """确认并执行待确认的提案"""
        if not self._proposals:
            return None
        if index >= len(self._proposals):
            return None
        proposal = self._proposals.pop(index)
        if self.pipeline:
            return await self.pipeline.execute_proposal(proposal)
        return None

    def cancel_proposals(self) -> int:
        """取消所有待确认提案"""
        count = len(self._proposals)
        self._proposals.clear()
        return count
