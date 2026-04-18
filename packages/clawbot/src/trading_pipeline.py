"""
Trading — 交易执行管道
包含 TradingPipeline (风控→决策→执行) 和 parse_trade_proposal (AI文本→订单)。
从 auto_trader.py 拆分以改善可维护性。

> 最后更新: 2026-03-28
"""
"""
ClawBot 自主交易引擎 v1.1
完整的 扫描->分析->决策->风控->执行->监控 自动化闭环

v1.1 变更 (2026-03-23):
  - 搬运 exchange-calendars (4.1k⭐) 替代手写 70 行休市日计算
  - 覆盖全球 50+ 交易所（NYSE/NASDAQ/SSE/HKEX/LSE...）
  - exchange-calendars 不可用时降级到原有手写逻辑（零破坏性）

核心流程:
1. 定时扫描市场（使用 ta_engine + universe）
2. 筛选候选标的（信号评分 + 多层过滤）
3. AI团队协作分析（可选，通过回调）
4. 风控审核（RiskManager 硬性拦截）
5. 自动执行下单（broker_bridge）
6. 持仓监控（position_monitor 止损/止盈）
7. 收盘复盘（trading_journal）
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional, Callable, Any
from enum import Enum

from src.models import TradeProposal
from src.notify_style import (
    format_trade_executed,
    format_trade_submitted,
)
logger = logging.getLogger(__name__)

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
                "已成交", "待成交", "成交回写完成", "次日重挂已提交",
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
                # 安全修复: 决策验证异常时拒绝交易(fail-closed)，而非继续执行
                logger.error("[Pipeline] 决策验证异常(%s)，拒绝交易(fail-closed)", e)
                result["steps"].append({"validation_error": str(e)})
                result["action"] = "REJECTED"
                result["error"] = f"决策验证系统异常: {e}"
                return result

        # Step 1: 风控审核
        if self.risk_manager and proposal.action in ("BUY", "SELL"):
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

                # Push risk alert via WebSocket (best-effort)
                try:
                    from src.api.routers.ws import push_event
                    from src.api.schemas import WSMessageType
                    push_event(WSMessageType.RISK_ALERT, {
                        "symbol": proposal.symbol,
                        "action": proposal.action,
                        "reason": check.reason,
                        "decided_by": proposal.decided_by,
                    })
                except Exception as e:
                    logger.debug("风控告警WS推送失败: %s", e)

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
                if order_result and "error" in order_result:
                    if self.portfolio:
                        logger.warning(
                            "[Pipeline] IBKR失败(%s)，回退到模拟组合（注意：后续为模拟执行，不代表真实持仓）",
                            order_result.get("error", ""),
                        )
                        result["steps"].append({"broker_fallback": "sim"})
                        order_result = None  # 清除错误，走下面的模拟逻辑
                    else:
                        # 无模拟组合可用，直接返回错误
                        logger.error(
                            "[Pipeline] IBKR失败且无模拟组合，交易中止: %s",
                            order_result.get("error", ""),
                        )
                        result["status"] = "error"
                        result["reason"] = "IBKR下单失败且无模拟组合: " + order_result.get("error", "")
                        return result
            except Exception as e:
                if self.portfolio:
                    logger.warning("[Pipeline] IBKR异常(%s)，回退到模拟组合（注意：后续为模拟执行）", e)
                    result["steps"].append({"broker_error": str(e)})
                    order_result = None  # 走下面的模拟逻辑
                else:
                    # 无模拟组合可用，直接返回错误
                    logger.error("[Pipeline] IBKR异常且无模拟组合，交易中止: %s", e)
                    result["status"] = "error"
                    result["reason"] = "IBKR下单异常且无模拟组合: %s" % e
                    return result

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

            # Push bot error via WebSocket (best-effort)
            try:
                from src.api.routers.ws import push_event
                from src.api.schemas import WSMessageType
                push_event(WSMessageType.BOT_ERROR, {
                    "module": "trading_pipeline",
                    "symbol": proposal.symbol,
                    "action": proposal.action,
                    "error": order_result["error"],
                })
            except Exception as e:
                logger.debug("交易错误WS推送失败: %s", e)

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

        # Handle partial fills: use actual filled quantity for journal/monitor
        actual_qty = proposal.quantity
        if order_result:
            raw_filled = order_result.get("filled_qty", 0)
            if raw_filled and float(raw_filled) > 0:
                actual_qty = float(raw_filled)
                if actual_qty < proposal.quantity:
                    logger.warning(
                        "[Pipeline] Partial fill: %s/%s shares of %s",
                        actual_qty, proposal.quantity, proposal.symbol,
                    )

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
                    quantity=actual_qty,
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
                # 管道1: 记录AI预测，供收盘验证准确率
                try:
                    self.journal.record_prediction(
                        symbol=proposal.symbol,
                        direction="UP" if proposal.action == "BUY" else "DOWN",
                        target_price=proposal.take_profit,
                        stop_price=proposal.stop_loss,
                        confidence=proposal.confidence,
                        reasoning=proposal.reason[:200],
                        decided_by=proposal.decided_by,
                        trade_id=trade_id,
                    )
                except Exception as e:
                    logger.debug("[Pipeline] 记录AI预测失败: %s", e)
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
                    quantity=actual_qty,
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

        # HI-569: 模拟降级交易使用 "simulated" 状态，避免 ghost position
        if is_simulated_fallback:
            result["status"] = "simulated"
            result["simulated"] = True
            logger.warning(
                "[Pipeline] 模拟执行(非真实持仓): %s %s x%s @ $%.2f — IBKR下单失败后降级",
                proposal.action, proposal.symbol, actual_qty, fill_price,
            )
        else:
            result["status"] = "executed"
        result["quantity"] = actual_qty
        result["entry_price"] = fill_price  # P0#3: 返回实际成交价

        # Push trade executed via WebSocket (best-effort)
        try:
            from src.api.routers.ws import push_event
            from src.api.schemas import WSMessageType
            push_event(WSMessageType.TRADE_EXECUTED, {
                "symbol": proposal.symbol,
                "action": proposal.action,
                "quantity": actual_qty,
                "price": fill_price,
                "stop_loss": proposal.stop_loss,
                "take_profit": proposal.take_profit,
                "decided_by": proposal.decided_by,
                "trade_id": trade_id,
                "source": "pipeline",
            })
        except Exception as e:
            logger.debug("交易执行WS推送失败: %s", e)

        # Step 5: 通知
        if self.notify:
            sim_tag = "模拟降级: IBKR 下单失败，仅保留模拟记录" if is_simulated_fallback else ""
            msg = format_trade_executed(
                proposal.action,
                proposal.symbol,
                actual_qty,
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
            "[Pipeline] 执行完成: %s %s x%s @ $%.2f",
            proposal.action, proposal.symbol,
            actual_qty, fill_price,
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
                quantity=max(0, int(data.get("quantity", data.get("qty", 0)))),
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

