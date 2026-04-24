"""
主动智能引擎 — 定时主动检查

收集系统上下文（持仓/闲鱼/交易/提醒/风控/自选股/行为洞察），
评估是否值得主动推送通知给管理员。

由 multi_main.py 主循环每 30 分钟调用一次。

> 从 proactive_engine.py 拆分 (HI-358)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from src.core.proactive_notify import _safe_parse_time, _send_proactive

if TYPE_CHECKING:
    from src.core.proactive_engine import ProactiveEngine

logger = logging.getLogger(__name__)


def _is_quiet_hours() -> bool:
    """北京时间 0-7 点为安静时段，不推送主动通知"""
    try:
        import pytz

        cst = pytz.timezone("Asia/Shanghai")
        now = datetime.now(cst)
        return 0 <= now.hour < 7
    except Exception:
        return False


async def periodic_proactive_check(engine: ProactiveEngine):
    """定时主动检查 — 收集系统上下文，评估是否值得主动推送。

    由 multi_main.py 主循环每 30 分钟调用一次。
    """
    # 安静时段检查：北京时间 0-7 点不打扰用户
    if _is_quiet_hours():
        logger.debug("[Proactive] 安静时段(0-7点)，跳过定时检查")
        return

    try:
        from src.bot.globals import ALLOWED_USER_IDS, bot_registry

        if not bot_registry:
            return

        # 收集系统上下文
        context_parts = []

        # 1. 持仓状态
        try:
            from src.invest_tools import get_portfolio_summary

            portfolio = get_portfolio_summary()
            if portfolio:
                context_parts.append(f"当前持仓: {portfolio}")
        except Exception as e:
            logger.debug(f"[Proactive] 持仓数据获取失败: {e}")

        # 2. 未读闲鱼消息
        try:
            from src.xianyu.xianyu_live import get_unread_count

            unread = get_unread_count()
            if unread and unread > 0:
                context_parts.append(f"闲鱼未读消息: {unread} 条")
        except Exception as e:
            logger.debug(f"[Proactive] 闲鱼未读获取失败: {e}")

        # 3. 今日交易汇总
        try:
            from src.trading_journal import TradingJournal

            journal = TradingJournal()
            today_trades = journal.get_today_trades()
            if today_trades:
                context_parts.append(f"今日交易: {len(today_trades)} 笔")
            journal.close()
        except Exception as e:
            logger.debug(f"[Proactive] 交易汇总获取失败: {e}")

        # 4. 今日待触发提醒
        try:
            from src.execution.life_automation import list_reminders

            pending = list_reminders(status="pending")
            if pending:
                from datetime import datetime as _dt

                _now = _dt.now()
                _today_end = _now.replace(hour=23, minute=59, second=59)
                today_count = sum(
                    1
                    for r in pending
                    if _safe_parse_time(r.get("remind_at", ""))
                    and _safe_parse_time(r.get("remind_at", "")) <= _today_end
                )
                if today_count > 0:
                    context_parts.append(f"今日待提醒: {today_count} 条")
                    # 列出最近的 2 条
                    for r in pending[:2]:
                        context_parts.append(f"  → {r.get('message', '')[:50]}")
        except Exception as e:
            logger.debug(f"[Proactive] 待提醒获取失败: {e}")

        # 5. 持仓盈亏警报 (接近止盈/止损)
        try:
            from src.risk_manager import RiskManager

            rm = RiskManager()
            alerts = rm.check_position_alerts() if hasattr(rm, "check_position_alerts") else []
            for alert in (alerts or [])[:2]:
                context_parts.append(f"持仓警报: {alert}")
        except Exception as e:
            logger.debug(f"[Proactive] 持仓警报获取失败: {e}")

        # 6. 关注股票大幅变动 (>3%)
        try:
            from src.invest_tools import get_quick_quotes

            try:
                from src.watchlist import get_watchlist_symbols

                wl = get_watchlist_symbols()
            except Exception as e:  # noqa: F841
                wl = []
            if wl:
                quotes = await get_quick_quotes(wl[:5])
                for sym, data in (quotes or {}).items():
                    change = data.get("change_pct", 0)
                    if abs(change) >= 3.0:
                        direction = "大涨" if change > 0 else "大跌"
                        context_parts.append(
                            f"关注股票{direction}: {sym} {change:+.1f}% (${data.get('price', 0):,.2f})"
                        )
        except Exception as e:
            logger.debug(f"[Proactive] 关注股票获取失败: {e}")

        # 7. 重复提醒统计
        try:
            from src.execution.life_automation import list_reminders

            all_pending = list_reminders(status="pending")
            recurring = [r for r in (all_pending or []) if r.get("recurrence_rule")]
            if len(recurring) > 0:
                context_parts.append(f"活跃重复提醒: {len(recurring)} 个")
        except Exception as e:
            logger.debug(f"[Proactive] 重复提醒统计失败: {e}")

        # 8. 闲鱼最近成交 (跨域关联: 成交→有闲钱→投资机会)
        try:
            from src.xianyu.xianyu_live import get_recent_sales

            sales = get_recent_sales(hours=24) if callable(getattr(get_recent_sales, "__call__", None)) else []
            if sales:
                total = sum(s.get("price", 0) for s in sales)
                if total > 0:
                    context_parts.append(f"闲鱼24h成交: ¥{total:.0f} ({len(sales)}笔)")
        except Exception as e:
            logger.debug(f"[Proactive] 闲鱼成交获取失败: {e}")

        # 9. 使用行为洞察 — 搬运 Spotify Wrapped / Apple 屏幕使用时间洞察模式
        # 从历史消息中检测行为模式，生成主动建议
        try:
            from src.bot.globals import history_store as _history_store_ref

            _hs = _history_store_ref
            if _hs:
                # 获取最近 100 条用户消息，提取频繁操作模式
                _any_bot = next(iter(bot_registry.keys()), "")
                _admin = list(ALLOWED_USER_IDS)[0] if ALLOWED_USER_IDS else 0
                if _any_bot and _admin:
                    recent = _hs.get_messages(_any_bot, int(_admin), limit=100)
                    user_msgs = [m.get("content", "") for m in (recent or []) if m.get("role") == "user"]
                    if user_msgs:
                        # 统计频繁提及的标的
                        import re as _re

                        _ticker_counts: dict[str, int] = {}
                        for msg in user_msgs:
                            tickers = _re.findall(r"\b([A-Z]{2,5})\b", msg)
                            _skip = {"AI", "ETF", "RSI", "MACD", "OK", "VS", "API", "BOT", "LLM"}
                            for t in tickers:
                                if t not in _skip:
                                    _ticker_counts[t] = _ticker_counts.get(t, 0) + 1
                        # 找频繁提及但不在 watchlist 的标的
                        if _ticker_counts:
                            from src.watchlist import get_watchlist_symbols

                            wl_syms = set(get_watchlist_symbols())
                            frequent_not_in_wl = [
                                (sym, cnt)
                                for sym, cnt in sorted(_ticker_counts.items(), key=lambda x: -x[1])
                                if cnt >= 3 and sym not in wl_syms
                            ]
                            if frequent_not_in_wl:
                                top = frequent_not_in_wl[0]
                                context_parts.append(
                                    f"行为洞察: 你最近频繁提及 {top[0]}（{top[1]}次），但它不在自选股里，要加入吗？"
                                )
        except Exception as e:
            logger.debug(f"[Proactive] 行为洞察失败: {e}")

        if not context_parts:
            logger.debug("[Proactive] 定时检查: 无有价值上下文，跳过")
            return

        context = "定时系统状态检查:\n" + "\n".join(f"- {p}" for p in context_parts)

        # 获取用户画像
        user_profile = ""
        try:
            from src.bot.globals import tiered_context_manager as _tcm

            if _tcm:
                user_profile = _tcm.core_get("user_profile")
        except Exception as e:
            logger.debug(f"[Proactive] 用户画像获取失败: {e}")

        # 对每个管理员用户评估
        admin_ids = ALLOWED_USER_IDS or []
        for uid in admin_ids[:3]:  # 最多3个管理员
            notification = await engine.evaluate(
                context_type="periodic_check",
                current_context=context,
                user_id=str(uid),
                user_profile=user_profile,
            )
            if notification:
                await _send_proactive(str(uid), notification)

    except Exception as e:
        logger.debug(f"[Proactive] 定时检查异常: {e}")
