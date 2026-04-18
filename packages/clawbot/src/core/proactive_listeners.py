"""
主动智能引擎 — EventBus 事件监听器

注册 EventBus 监听器，在关键事件发生时触发主动通知评估。
包含 9 个事件处理器:
  - 交易成交 (含延迟跟进)
  - 风控预警
  - 自选股异动 (情报级富文本)
  - 任务完成 (延迟回访)
  - 任务图执行进度
  - 闲鱼订单支付
  - 月度预算超支
  - 社媒内容发布 (延迟跟进)
  - 粉丝里程碑

> 从 proactive_engine.py 拆分 (HI-358)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, TYPE_CHECKING

from src.core.proactive_notify import _send_proactive, _send_proactive_photo

if TYPE_CHECKING:
    from src.core.proactive_engine import ProactiveEngine

logger = logging.getLogger(__name__)


async def setup_proactive_listeners(engine: ProactiveEngine):
    """注册 EventBus 监听器，在关键事件发生时触发主动通知评估。

    应在 multi_main.py 启动阶段调用。
    """
    try:
        from src.core.event_bus import get_event_bus, EventType
        bus = get_event_bus()

        async def on_trade_executed(event_data: Dict[str, Any]):
            """交易成交后评估是否需要通知其他关联信息 + 延迟跟进。"""
            try:
                # 兼容 Event 对象和原始 dict 两种格式
                data = event_data.data if hasattr(event_data, "data") else event_data
                user_id = str(data.get("user_id", "default"))
                symbol = data.get("symbol", "")
                direction = data.get("direction", data.get("action", data.get("signal", "")))
                quantity = data.get("quantity", 0)
                entry_price = data.get("entry_price", 0)

                # 立即: 评估跨域通知（如闲鱼有钱了可以补货）
                context = (
                    f"严总刚刚 {direction} 了 {symbol}"
                    + (f" x{quantity} @ ${entry_price:.2f}" if entry_price else "")
                    + f"。交易详情: {data}"
                )
                notification = await engine.evaluate(
                    context_type="cross_domain",
                    current_context=context,
                    user_id=user_id,
                )
                if notification:
                    await _send_proactive(user_id, notification)

                # 延迟 2 小时: 跟进交易状态变化
                if symbol and entry_price > 0:
                    async def _trade_followup():
                        """交易执行 2 小时后查询当前价格并评估是否通知。"""
                        await asyncio.sleep(7200)  # 2 小时
                        try:
                            from src.invest_tools import get_stock_quote
                            quote = await get_stock_quote(symbol)
                            if not quote or not quote.get("price"):
                                return
                            current_price = float(quote["price"])
                            pnl_pct = (current_price - entry_price) / entry_price * 100
                            stop_loss = data.get("stop_loss", 0)
                            take_profit = data.get("take_profit", 0)

                            # 构建跟进上下文
                            followup_parts = [
                                f"2小时前严总 {direction} 了 {symbol}，"
                                f"买入价 ${entry_price:.2f}，当前 ${current_price:.2f}，"
                                f"浮动 {pnl_pct:+.1f}%。",
                            ]
                            if stop_loss and current_price < stop_loss:
                                followup_parts.append(f"⚠️ 已跌破止损价 ${stop_loss:.2f}！")
                            elif take_profit and current_price > take_profit:
                                followup_parts.append(f"🎯 已突破止盈目标 ${take_profit:.2f}！")

                            followup_context = " ".join(followup_parts)
                            followup_notification = await engine.evaluate(
                                context_type="task_followup",
                                current_context=followup_context,
                                user_id=user_id,
                            )
                            if followup_notification:
                                await _send_proactive(user_id, followup_notification)
                        except Exception as exc:
                            logger.debug("交易延迟跟进异常: %s", exc)

                    _followup_task = asyncio.create_task(_trade_followup())
                    _followup_task.add_done_callback(
                        lambda t: t.exception() and logger.debug(
                            "交易跟进后台任务异常: %s", t.exception()
                        )
                    )
            except Exception as e:
                logger.debug(f"交易后主动通知评估失败: {e}")

        async def on_risk_alert(event_data: Dict[str, Any]):
            """风控预警触发主动通知。"""
            try:
                user_id = str(event_data.get("user_id", ""))
                context = f"风控预警: {event_data}"

                notification = await engine.evaluate(
                    context_type="risk_warning",
                    current_context=context,
                    user_id=user_id,
                )
                if notification:
                    await _send_proactive(user_id, notification)
            except Exception as e:
                logger.debug(f"风控主动通知评估失败: {e}")

        # 注册监听器（注意：subscribe 是同步方法，不能用 await）
        if hasattr(EventType, "TRADE_EXECUTED"):
            bus.subscribe(EventType.TRADE_EXECUTED, on_trade_executed)
        if hasattr(EventType, "RISK_ALERT"):
            bus.subscribe(EventType.RISK_ALERT, on_risk_alert)

        # 自选股异动 → 情报级主动推送（新闻+K线图+RSI+持仓浮盈）
        async def on_watchlist_anomaly(event_data: Dict[str, Any]):
            """自选股异动触发富文本通知（v2.0: 从纯文本升级为情报卡片）。

            通知格式:
              ⚡ NVDA 暴涨 +5.2% | $135.80
              ━━━━━━━━━━━━━━━
              📰 可能原因: Nvidia发布新一代Blackwell芯片
              📊 RSI: 72.3 (超买区域)
              💰 你持有 100股，浮盈 +$520
              [附: 5日1小时K线图]
            """
            try:
                from src.bot.globals import ALLOWED_USER_IDS

                symbol = event_data.get("symbol", "")
                anomaly_type = event_data.get("anomaly_type", "")
                details = event_data.get("details", "")
                change_pct = event_data.get("change_pct", 0)
                price = event_data.get("price", 0)

                # 增强数据（由 watchlist_monitor._enrich_anomalies 注入）
                news_title = event_data.get("news_title", "")
                chart_png = event_data.get("chart_png", b"")
                rsi_value = event_data.get("rsi_value")
                holding_qty = event_data.get("holding_qty", 0)
                holding_avg_price = event_data.get("holding_avg_price", 0)

                # ── 构建情报卡片 ──
                # 标题行: 根据异动类型选择图标
                _type_emoji = {
                    "price_surge": "⚡",
                    "volume_surge": "📊",
                    "rsi_extreme": "📈",
                    "target_hit": "🎯",
                    "stoploss_hit": "⚠️",
                }
                emoji = _type_emoji.get(anomaly_type, "⚡")

                # 涨跌方向
                if anomaly_type == "price_surge":
                    direction = "暴涨" if change_pct > 0 else "暴跌"
                    headline = (
                        f"{emoji} <b>{symbol} {direction} "
                        f"{change_pct:+.1f}%</b> | ${price:.2f}"
                    )
                else:
                    # 非价格异动用原始 details 做标题
                    headline = f"{emoji} <b>{details}</b>"

                lines = [headline, "━━━━━━━━━━━━━━━"]

                # 新闻原因
                if news_title:
                    # 截断过长标题
                    title_display = (
                        news_title[:60] + "..." if len(news_title) > 60
                        else news_title
                    )
                    lines.append(f"📰 可能原因: {title_display}")

                # RSI 指标
                if rsi_value is not None:
                    if rsi_value > 70:
                        zone = " (超买区域)"
                    elif rsi_value < 30:
                        zone = " (超卖区域)"
                    else:
                        zone = ""
                    lines.append(f"📊 RSI: {rsi_value:.1f}{zone}")

                # 持仓浮盈
                if holding_qty > 0 and holding_avg_price > 0:
                    pnl = (price - holding_avg_price) * holding_qty
                    pnl_label = "浮盈" if pnl >= 0 else "浮亏"
                    lines.append(
                        f"💰 你持有 {holding_qty}股，"
                        f"{pnl_label} {'+'if pnl >= 0 else ''}"
                        f"${abs(pnl):,.0f}"
                    )

                alert_text = "\n".join(lines)

                # ── 确定通知目标（用第一个管理员 ID）──
                target_id = ""
                if ALLOWED_USER_IDS:
                    target_id = str(list(ALLOWED_USER_IDS)[0])
                if not target_id:
                    return  # 无接收者，跳过

                # ── 有图发图，无图发文 ──
                if chart_png:
                    await _send_proactive_photo(
                        target_id, chart_png, alert_text
                    )
                else:
                    await _send_proactive(target_id, alert_text)

                logger.info(
                    f"📡 异动情报已推送: {symbol} ({anomaly_type})"
                )

            except Exception as e:
                logger.debug(f"自选股异动通知失败: {e}")

        if hasattr(EventType, "WATCHLIST_ANOMALY"):
            bus.subscribe(EventType.WATCHLIST_ANOMALY, on_watchlist_anomaly)

        # 任务闭环跟踪 — 搬运 Apple Reminders / Todoist 定时回看模式
        # 投资类任务执行完后，延迟 2 小时检查结果变化并主动推送
        async def on_task_completed(event_data: Dict[str, Any]):
            """任务完成后延迟回访 — 让 Bot 在时间轴上有延续性。"""
            try:
                task_type = event_data.get("goal", "")
                task_data = event_data.get("final_result", {})

                # 只对投资类任务做延迟回访（交易/分析/回测）
                _invest_keywords = ("investment", "trading", "backtest", "分析", "买入", "卖出")
                is_invest = any(kw in str(task_type).lower() for kw in _invest_keywords)
                if not is_invest:
                    return

                # 提取标的代码
                symbol = ""
                if isinstance(task_data, dict):
                    symbol = task_data.get("symbol", "")
                    if not symbol:
                        # 尝试从嵌套结果中提取
                        for v in task_data.values():
                            if isinstance(v, dict) and v.get("symbol"):
                                symbol = v["symbol"]
                                break
                if not symbol:
                    return

                # 延迟 2 小时后检查
                async def _delayed_followup():
                    await asyncio.sleep(7200)  # 2 小时
                    try:
                        from src.invest_tools import get_stock_quote
                        quote = await get_stock_quote(symbol)
                        if not quote or not quote.get("price"):
                            return
                        change_pct = quote.get("change_pct", 0)
                        price = quote.get("price", 0)

                        followup_context = (
                            f"2小时前严总执行了'{task_type}'相关任务，标的 {symbol}。"
                            f"当前 {symbol} 价格 ${price:.2f}，涨跌幅 {change_pct:+.1f}%。"
                            f"根据变化情况，判断是否值得通知严总。"
                        )
                        notification = await engine.evaluate(
                            context_type="task_followup",
                            current_context=followup_context,
                            user_id="default",
                        )
                        if notification:
                            await _send_proactive("default", notification)
                    except Exception as e:
                        logger.debug(f"任务闭环回访异常: {e}")

                _followup_t = asyncio.create_task(_delayed_followup())
                _followup_t.add_done_callback(lambda t: t.exception() and logger.debug("延迟回访后台任务异常: %s", t.exception()))
            except Exception as e:
                logger.debug(f"任务完成监听异常: {e}")

        if hasattr(EventType, "TASK_COMPLETED"):
            bus.subscribe(EventType.TASK_COMPLETED, on_task_completed)

        # 流式进度反馈 — 搬运 Claude artifact 流式 / ChatGPT 思考过程
        # 多步任务每完成一步实时推送进度到用户
        async def on_brain_progress(event_data: Dict[str, Any]):
            """任务图执行进度 → 实时推送到用户。"""
            try:
                step = event_data.get("step", 0)
                total = event_data.get("total", 0)
                name = event_data.get("name", "")
                status = event_data.get("status", "")

                # 只在多步任务（>1步）时推送，避免单步任务刷屏
                if total <= 1:
                    return

                if status == "running":
                    emoji = "🔄"
                    text = f"{emoji} 进度 {step}/{total} — 正在执行: {name}"
                else:
                    return  # 只推送"正在执行"状态

                await _send_proactive("default", text)
            except Exception as e:
                logger.debug(f"进度推送异常: {e}")

        bus.subscribe("brain.progress", on_brain_progress)

        # ── 闲鱼订单支付 — 提醒发货 ──
        async def on_xianyu_order_paid(event_data):
            """闲鱼订单支付 — 提醒卖家尽快发货。"""
            try:
                data = event_data.data if hasattr(event_data, "data") else event_data
                item_name = data.get("item_name", "商品")
                amount = data.get("amount", 0)
                context = f"闲鱼有人刚付款了: {item_name}，金额 ¥{amount:.0f}。可能需要尽快发货。"
                notification = await engine.evaluate(
                    context_type="cross_domain",
                    current_context=context,
                    user_id="default",
                )
                if notification:
                    await _send_proactive("default", notification)
            except Exception as e:
                logger.debug(f"闲鱼订单主动通知失败: {e}")

        if hasattr(EventType, "XIANYU_ORDER_PAID"):
            bus.subscribe(EventType.XIANYU_ORDER_PAID, on_xianyu_order_paid)

        # ── 月度预算超支提醒 ──
        async def on_budget_exceeded(event_data):
            """月度预算超支 — 主动推送消费提醒。"""
            try:
                data = event_data.data if hasattr(event_data, "data") else event_data
                category = data.get("category", "总支出")
                amount = data.get("amount", 0)
                budget = data.get("budget", 0)
                pct = (amount / budget * 100) if budget > 0 else 0
                context = f"消费提醒: {category}已花 ¥{amount:.0f}，超出预算 ¥{budget:.0f} 的 {pct:.0f}%。"
                notification = await engine.evaluate(
                    context_type="reminder",
                    current_context=context,
                    user_id="default",
                )
                if notification:
                    await _send_proactive("default", notification)
            except Exception as e:
                logger.debug(f"预算超支主动通知失败: {e}")

        if hasattr(EventType, "BUDGET_EXCEEDED"):
            bus.subscribe(EventType.BUDGET_EXCEEDED, on_budget_exceeded)

        # ── 社媒内容发布后 — 延迟 1 小时检查初始互动 ──
        async def on_social_published(event_data):
            """社媒内容发布后 — 延迟 1 小时跟进初始互动数据。"""
            try:
                data = event_data.data if hasattr(event_data, "data") else event_data
                platform = data.get("platform", "")
                title = data.get("title", "新帖子")[:30]

                async def _social_followup():
                    """社媒发布 1 小时后跟进"""
                    await asyncio.sleep(3600)
                    try:
                        context = f"1小时前在{platform}发布了「{title}」，可以去看看初始互动数据了。"
                        notification = await engine.evaluate(
                            context_type="info",
                            current_context=context,
                            user_id="default",
                        )
                        if notification:
                            await _send_proactive("default", notification)
                    except Exception as exc:
                        logger.debug(f"社媒发布跟进异常: {exc}")

                task = asyncio.create_task(_social_followup())
                task.add_done_callback(
                    lambda t: t.exception() and logger.debug("社媒跟进后台任务异常: %s", t.exception())
                )
            except Exception as e:
                logger.debug(f"社媒发布主动通知失败: {e}")

        if hasattr(EventType, "SOCIAL_PUBLISHED"):
            bus.subscribe(EventType.SOCIAL_PUBLISHED, on_social_published)

        # ── 粉丝里程碑庆祝 ──
        async def on_follower_milestone(event_data):
            """粉丝数突破里程碑 — 庆祝通知。"""
            try:
                data = event_data.data if hasattr(event_data, "data") else event_data
                platform = data.get("platform", "")
                count = data.get("count", 0)
                context = f"恭喜！{platform}平台粉丝突破 {count} 了！"
                notification = await engine.evaluate(
                    context_type="opportunity",
                    current_context=context,
                    user_id="default",
                )
                if notification:
                    await _send_proactive("default", notification)
            except Exception as e:
                logger.debug(f"粉丝里程碑主动通知失败: {e}")

        if hasattr(EventType, "FOLLOWER_MILESTONE"):
            bus.subscribe(EventType.FOLLOWER_MILESTONE, on_follower_milestone)

        logger.info("主动智能引擎已注册 EventBus 监听器")
    except Exception as e:
        logger.debug(f"EventBus 监听器注册失败 (非致命): {e}")
