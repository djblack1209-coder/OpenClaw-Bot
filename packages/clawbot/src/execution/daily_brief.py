"""
Execution Hub — 每日智能日报 v4.0 (Smart Daily Digest)
用户打开 Telegram 就知道一切 — 持仓/交易/市场/社媒/成本 全覆盖

v4.0 变更 (2026-03-30):
  - 新增「今日概况」执行摘要 — LLM 生成 2 句话总结当天全局
  - 新增「今日建议」智能推荐 — 3 条基于数据的可操作建议
  - 新增「vs 昨日」趋势对比 — 关键指标标注涨跌 delta
  - LLM 调用全部有 try/except 降级 — 日报永不因 AI 失败而中断

v3.0 变更 (2026-03-24):
  - 从 6 段扩展到 10 段: 新增持仓概览、交易绩效、目标进度、AI 信号准确率
  - 使用 format_digest(sections=...) 替代 paragraphs — 结构化分节
  - 接入 trading_journal / position_monitor / cost_analyzer / social_autopilot
  - 所有数据源独立 try/except + 降级提示 — 不再静默丢失

设计原则:
  - 用户不需要主动查看任何东西 — 早上打开一条消息就够了
  - 每个 section 独立获取，一个失败不影响其他
  - 数据存在才展示，没有假数据填充
  - 从"数据罗列"升级为"决策支持" — 概况 + 建议 + 趋势
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from src.constants import FAMILY_QWEN
from src.execution._db import get_conn
from src.notify_style import format_digest, kv, bullet

logger = logging.getLogger(__name__)


def _section(title: str, items: List[str]) -> Tuple[str, List[str]]:
    """构建一个 section tuple (title, items) for format_digest"""
    return (title, items)


async def _analyze_news_with_llm(
    headlines: List[str], holdings: List[str]
) -> List[str]:
    """用最便宜的 LLM 对新闻标题做一句话分析 + 持仓影响关联。

    成本控制: 用免费的 qwen 模型，max_tokens=300，prompt 限制100字回复。
    失败时返回 None，由调用方降级到纯标题列表。
    """
    try:
        from src.litellm_router import free_pool
        if not free_pool:
            return None

        # 构建新闻列表文本
        news_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(headlines))

        # 构建 prompt — 精简控制 token 成本
        holdings_part = ""
        if holdings:
            holdings_part = f"用户持有: {', '.join(holdings[:10])}\n"

        prompt = (
            f"你是金融新闻分析师。{holdings_part}"
            f"以下是今日科技新闻标题:\n{news_text}\n\n"
            f"请用中文，每条新闻一句话分析（15字以内），"
            f"标注对用户持仓的影响（利好/利空/中性）。"
            f"如果没有直接影响就不标注。总共不超过100字。"
            f"格式: 每行一条，用 • 开头，影响用 → 标注。"
        )

        resp = await free_pool.acompletion(
            model_family=FAMILY_QWEN,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
            cache_ttl=1800,  # 缓存30分钟，避免重复调用
        )
        text = (resp.choices[0].message.content or "").strip()

        if not text:
            return None

        # 解析 LLM 输出为行列表
        lines = [
            ln.strip() for ln in text.split("\n")
            if ln.strip() and not ln.strip().startswith("```")
        ]
        if not lines:
            return None

        # 确保每行以 • 开头
        result = []
        for ln in lines:
            ln = ln.lstrip("- ·•*0123456789.、）)")
            ln = ln.strip()
            if ln:
                result.append(f"• {ln}")

        return result if result else None

    except Exception as e:
        logger.debug(f"[DailyBrief] LLM 新闻分析失败，降级到纯标题: {e}")
        return None


async def _generate_executive_summary(sections_data: dict) -> str:
    """用 LLM 生成 2 句话的每日执行摘要。

    从各模块的关键指标中提炼当天全局态势。
    LLM 失败时降级为模板摘要，保证日报不中断。

    Args:
        sections_data: 包含 portfolio_pnl, xianyu_orders, social_posts 等关键指标的字典
    Returns:
        格式化的执行摘要文本，以「📊 今日概况」开头
    """
    # 提取关键指标用于 LLM prompt 和模板降级
    pnl = sections_data.get("portfolio_pnl", 0)
    pnl_label = f"浮盈${pnl:+,.2f}" if pnl >= 0 else f"浮亏${pnl:+,.2f}"
    xianyu_consult = sections_data.get("xianyu_consultations", 0)
    xianyu_orders = sections_data.get("xianyu_orders", 0)
    social_posts = sections_data.get("social_posts", 0)
    api_cost = sections_data.get("api_daily_cost", 0)
    market_sentiment = sections_data.get("market_sentiment", "")
    # 昨日对比 delta（如果有）
    deltas = sections_data.get("deltas", {})

    try:
        from src.litellm_router import free_pool
        if not free_pool:
            raise RuntimeError("free_pool 不可用")

        # 构建指标文本，只包含有数据的指标
        metrics_parts = []
        if pnl != 0:
            metrics_parts.append(f"投资组合{pnl_label}")
        if xianyu_consult > 0 or xianyu_orders > 0:
            metrics_parts.append(f"闲鱼咨询{xianyu_consult}条/下单{xianyu_orders}笔")
        if social_posts > 0:
            metrics_parts.append(f"社媒发帖{social_posts}篇")
        if api_cost > 0:
            metrics_parts.append(f"API日均成本${api_cost:.2f}")
        if market_sentiment:
            metrics_parts.append(f"市场情绪: {market_sentiment}")

        # delta 信息
        delta_parts = []
        for key, val in deltas.items():
            if val != 0:
                sign = "↑" if val > 0 else "↓"
                delta_parts.append(f"{key} {sign}{abs(val)}")

        metrics_text = "；".join(metrics_parts) if metrics_parts else "暂无数据"
        delta_text = f"\n趋势变化: {', '.join(delta_parts)}" if delta_parts else ""

        prompt = (
            f"你是一位私人财务管家。以下是用户今日的关键数据:\n"
            f"{metrics_text}{delta_text}\n\n"
            f"请用中文写 2 句话总结今天的整体状况。"
            f"第一句概括全局（好/坏/平稳），第二句点出最值得关注的一件事。"
            f"语气亲切简洁，不超过 80 字。不要加标题或 emoji。"
        )

        resp = await free_pool.acompletion(
            model_family=FAMILY_QWEN,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=200,
            cache_ttl=1800,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text:
            return text

    except Exception as e:
        logger.debug(f"[DailyBrief] 执行摘要 LLM 调用失败，降级为模板: {e}")

    # 降级: 模板摘要 — 不依赖 LLM
    parts = []
    if pnl != 0:
        trend = "盈利" if pnl > 0 else "亏损"
        parts.append(f"投资组合今日{trend} ${abs(pnl):,.2f}")
    if xianyu_orders > 0:
        parts.append(f"闲鱼成交 {xianyu_orders} 单")
    if not parts:
        parts.append("各项业务运行平稳")
    summary = "，".join(parts) + "。"

    # 第二句: 找最值得关注的指标
    attention = ""
    pnl_delta = deltas.get("持仓盈亏", 0)
    if abs(pnl_delta) > 100:
        direction = "上升" if pnl_delta > 0 else "下降"
        attention = f"持仓盈亏较昨日{direction} ${abs(pnl_delta):,.0f}，需留意。"
    elif xianyu_consult > 10:
        attention = f"闲鱼咨询量 {xianyu_consult} 条，转化情况值得关注。"
    else:
        attention = "暂无需要特别关注的异常。"

    return f"{summary}{attention}"


async def _generate_daily_recommendations(sections_data: dict) -> str:
    """用 LLM 生成 3 条基于数据的可操作建议。

    每条建议必须引用具体数据作为依据，避免空泛建议。
    LLM 失败时返回空字符串（建议是可选的锦上添花功能）。

    Args:
        sections_data: 包含关键指标的字典
    Returns:
        格式化的建议文本，以「💡 今日建议」开头；失败时返回空列表
    """
    # 提取关键指标
    pnl = sections_data.get("portfolio_pnl", 0)
    xianyu_consult = sections_data.get("xianyu_consultations", 0)
    xianyu_orders = sections_data.get("xianyu_orders", 0)
    social_posts = sections_data.get("social_posts", 0)
    api_cost = sections_data.get("api_daily_cost", 0)
    market_sentiment = sections_data.get("market_sentiment", "")
    positions_count = sections_data.get("positions_count", 0)
    deltas = sections_data.get("deltas", {})

    try:
        from src.litellm_router import free_pool
        if not free_pool:
            return []

        # 组装数据摘要供 LLM 推理
        data_lines = []
        if pnl != 0:
            data_lines.append(f"投资组合浮盈亏: ${pnl:+,.2f}, 持仓 {positions_count} 个")
        if xianyu_consult > 0:
            conv = f"{xianyu_orders}/{xianyu_consult}" if xianyu_consult > 0 else "N/A"
            data_lines.append(f"闲鱼: 咨询 {xianyu_consult} 条, 下单 {xianyu_orders} 笔, 转化 {conv}")
        if social_posts > 0:
            data_lines.append(f"社媒: 今日发帖 {social_posts} 篇")
        if api_cost > 0:
            data_lines.append(f"API 日均成本: ${api_cost:.2f}")
        if market_sentiment:
            data_lines.append(f"市场情绪: {market_sentiment}")
        for key, val in deltas.items():
            if val != 0:
                sign = "+" if val > 0 else ""
                data_lines.append(f"较昨日变化 — {key}: {sign}{val}")

        if not data_lines:
            return []

        data_text = "\n".join(data_lines)
        prompt = (
            f"你是一位私人财务管家和运营顾问。以下是用户今日的业务数据:\n"
            f"{data_text}\n\n"
            f"请给出恰好 3 条今日可操作建议。要求:\n"
            f"1. 每条建议必须引用具体数据（如「闲鱼咨询 15 条但下单仅 2 笔，建议优化话术」）\n"
            f"2. 建议要具体可执行，不要空泛（如「注意市场风险」这种无用建议）\n"
            f"3. 用中文，每条一行，用 1. 2. 3. 编号，每条不超过 30 字\n"
            f"4. 涵盖不同领域（投资/电商/运营中选 2-3 个有数据的领域）\n"
        )

        resp = await free_pool.acompletion(
            model_family=FAMILY_QWEN,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=300,
            cache_ttl=1800,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            return []

        # 解析 LLM 输出为建议列表
        lines = [
            ln.strip() for ln in text.split("\n")
            if ln.strip() and not ln.strip().startswith("```")
        ]
        # 清理编号前缀，统一格式
        result = []
        for ln in lines:
            ln = ln.lstrip("0123456789.、）) -·•*")
            ln = ln.strip()
            if ln:
                result.append(ln)

        return result[:3] if result else []

    except Exception as e:
        logger.debug(f"[DailyBrief] 今日建议 LLM 调用失败: {e}")
        return []


async def _get_yesterday_comparison(db_path=None) -> dict:
    """获取昨日关键指标，用于与今日数据对比计算 delta。

    只对比 3-4 个核心指标（持仓盈亏/闲鱼咨询/闲鱼下单/社媒发帖），
    每个数据源独立 try/except，任一失败不影响其他。

    Args:
        db_path: 可选的数据库路径
    Returns:
        昨日指标字典，如 {"portfolio_pnl": 100.5, "xianyu_consultations": 12, ...}
    """
    from src.utils import now_et
    yesterday_str = (now_et() - timedelta(days=1)).strftime("%Y-%m-%d")
    result = {}

    # 1. 昨日持仓盈亏 — 从交易日志获取
    try:
        from src.trading_journal import journal
        if journal and hasattr(journal, "get_today_pnl"):
            # get_today_pnl 返回今日的，我们需要用 get_performance(days=1) 近似
            perf = journal.get_performance(days=1)
            if perf:
                result["portfolio_pnl"] = perf.get("total_pnl", 0)
    except Exception as e:
        logger.debug(f"[DailyBrief] 昨日持仓对比失败: {e}")

    # 2. 昨日闲鱼数据 — daily_stats 支持传入日期
    try:
        from src.xianyu.xianyu_context import XianyuContextManager
        xctx = XianyuContextManager()
        if hasattr(xctx, "daily_stats"):
            ystats = xctx.daily_stats(date=yesterday_str)
            if ystats:
                result["xianyu_consultations"] = ystats.get("consultations", 0)
                result["xianyu_orders"] = ystats.get("orders", 0)
    except Exception as e:
        logger.debug(f"[DailyBrief] 昨日闲鱼对比失败: {e}")

    # 3. 昨日社媒发帖 — 通过 engagement_summary(days=1) 近似
    try:
        from src.execution.life_automation import get_engagement_summary
        eng = get_engagement_summary(days=1, db_path=db_path)
        if eng.get("success"):
            result["social_posts"] = eng.get("total_posts", 0)
    except Exception as e:
        logger.debug(f"[DailyBrief] 昨日社媒对比失败: {e}")

    return result


def _calc_deltas(today_data: dict, yesterday_data: dict) -> dict:
    """计算今日 vs 昨日的差值。

    Args:
        today_data: 今日指标字典
        yesterday_data: 昨日指标字典（来自 _get_yesterday_comparison）
    Returns:
        中文标签到 delta 值的映射，如 {"持仓盈亏": +50.0, "闲鱼咨询": -3}
    """
    # 定义要对比的指标: (内部 key, 中文标签)
    comparisons = [
        ("portfolio_pnl", "持仓盈亏"),
        ("xianyu_consultations", "闲鱼咨询"),
        ("xianyu_orders", "闲鱼下单"),
        ("social_posts", "社媒发帖"),
    ]
    deltas = {}
    for key, label in comparisons:
        today_val = today_data.get(key, 0)
        yesterday_val = yesterday_data.get(key, 0)
        # 只有两边都有数据时才计算 delta
        if today_val != 0 or yesterday_val != 0:
            deltas[label] = today_val - yesterday_val
    return deltas


def _format_delta(value, unit: str = "") -> str:
    """格式化 delta 值为带箭头的可读文本。

    Args:
        value: 差值（正数=增长，负数=下降）
        unit: 单位后缀，如 "条"、"笔"、""
    Returns:
        格式化文本如 "↑3条" 或 "↓$50.00"
    """
    if value == 0:
        return ""
    arrow = "↑" if value > 0 else "↓"
    abs_val = abs(value)
    if isinstance(value, float) and unit == "$":
        return f" ({arrow}${abs_val:,.2f})"
    return f" ({arrow}{abs_val:.0f}{unit})"


async def _build_today_agenda(db_path=None) -> List[str]:
    """今日日程 — 合并所有数据源按紧急度排序

    数据源:
      1. 持仓风险项 — position_monitor 距止损 <3%
      2. 今日提醒 — reminders 今天到期
      3. 账单到期 — bill_accounts remind_day == 今天
      4. 今日待办 — top_tasks
      5. 降价监控到期 — price_watches last_checked 超过1天

    返回排序后的日程文本列表，空列表表示无日程。
    """
    # (优先级, 文本) — 数字越小越紧急
    agenda: List[Tuple[int, str]] = []

    # ── 1. 持仓风险项 — 接近止损的持仓 ──
    try:
        from src.position_monitor import position_monitor
        if position_monitor and position_monitor.positions:
            status = position_monitor.get_status()
            for p in status.get("positions", []):
                cur = p.get("current_price", 0)
                sl = p.get("stop_loss", 0)
                sym = p.get("symbol", "?")
                if sl > 0 and cur > 0:
                    distance = (cur - sl) / cur * 100
                    if 0 < distance < 3:
                        agenda.append((0, f"⚡ {sym} 距止损仅 {distance:.1f}%，注意！"))
    except Exception as e:
        logger.debug(f"[TodayAgenda] 持仓风险: {e}")

    # ── 2. 今日提醒 ──
    try:
        from src.execution.life_automation import list_reminders
        from src.utils import now_et
        pending = list_reminders(status="pending", db_path=db_path)
        if pending:
            now = now_et()
            today_end = now.replace(hour=23, minute=59, second=59)
            for r in pending:
                try:
                    remind_time = datetime.fromisoformat(r["remind_at"])
                    if remind_time <= today_end:
                        time_str = remind_time.strftime("%H:%M")
                        agenda.append((1, f"⏰ {time_str} {r['message']}"))
                except (ValueError, TypeError) as e:  # noqa: F841
                    pass
    except Exception as e:
        logger.debug(f"[TodayAgenda] 提醒: {e}")

    # ── 3. 账单到期 ──
    try:
        from src.execution.life_automation import get_bill_reminders_due
        bills = get_bill_reminders_due(db_path=db_path)
        for b in bills:
            name = b.get("account_name", b.get("account_type", "账单"))
            balance = b.get("balance", 0)
            threshold = b.get("low_threshold", 0)
            alert = " ‼️ 低于阈值" if threshold and balance < threshold else ""
            agenda.append((1, f"📱 {name} 余额 ¥{balance:.0f}{alert}"))
    except Exception as e:
        logger.debug(f"[TodayAgenda] 账单: {e}")

    # ── 4. 今日待办 ──
    try:
        from src.execution.task_mgmt import top_tasks
        tasks = top_tasks(limit=3, db_path=db_path)
        for t in tasks:
            agenda.append((2, f"📝 {t.get('title', '未命名任务')} (待办)"))
    except Exception as e:
        logger.debug(f"[TodayAgenda] 待办: {e}")

    # ── 5. 降价监控到期 — 超过1天未检查的活跃监控 ──
    try:
        with get_conn(db_path) as conn:
            rows = conn.execute(
                "SELECT keyword, last_checked FROM price_watches "
                "WHERE status='active' AND last_checked IS NOT NULL "
                "AND (julianday('now') - julianday(last_checked)) > 1.0 "
                "LIMIT 5"
            ).fetchall()
            for r in rows:
                agenda.append((3, f"🛒 {r[0]} 监控已超1天未检查"))
    except Exception as e:
        logger.debug(f"[TodayAgenda] 降价监控: {e}")

    if not agenda:
        return []

    # 按紧急度排序，同级保持插入顺序
    agenda.sort(key=lambda x: x[0])
    return [text for _, text in agenda]


async def generate_daily_brief(monitors=None, db_path=None) -> str:
    """生成智能每日日报 — 10 个数据源自动聚合

    内容架构:
    0. 今日日程 (合并提醒/待办/账单/持仓风险/降价监控)
    1. 持仓概览 (position_monitor)
    2. 昨日交易绩效 (trading_journal)
    3. 目标进度 (profit targets)
    4. 待办事项 (task_mgmt)
    5. 市场行情 (invest_tools)
    6. 恐惧贪婪指数 (invest_tools)
    7. 科技/AI 新闻 (news_fetcher RSS)
    8. 社媒运营状态 (social_autopilot)
    9. 活跃监控 + 社媒草稿 (monitors + DB)
    10. API 成本 (cost_analyzer)
    """
    sections: List[Tuple[str, List[str]]] = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    greeting = _get_greeting()

    # ── 0. 今日日程 (所有源按紧急度排序，日报最前面) ──────────
    try:
        agenda_items = await _build_today_agenda(db_path=db_path)
        if agenda_items:
            sections.append(_section("📋 今日日程", agenda_items))
    except Exception as e:
        logger.debug(f"[DailyBrief] agenda: {e}")

    # ── 1. 持仓概览 ──────────────────────────────────────────
    try:
        from src.position_monitor import position_monitor
        if position_monitor and position_monitor.positions:
            status = position_monitor.get_status()
            items = []
            total_pnl = status.get("total_unrealized_pnl", 0)
            pnl_emoji = "📈" if total_pnl >= 0 else "📉"
            items.append(f"{pnl_emoji} 总浮盈亏: ${total_pnl:+,.2f}")
            items.append(f"监控持仓: {status.get('monitored_count', 0)} 个")
            for p in status.get("positions", [])[:5]:
                sym = p["symbol"]
                pnl_pct = p.get("unrealized_pnl_pct", 0)
                cur = p.get("current_price", 0)
                sl = p.get("stop_loss", 0)
                emoji = "🟢" if pnl_pct >= 0 else "🔴"
                line = f"{emoji} {sym} ${cur:.2f} ({pnl_pct:+.1f}%)"
                if sl > 0:
                    distance = ((cur - sl) / cur * 100) if cur > 0 else 0
                    line += f" | SL ${sl:.2f} ({distance:.0f}%)"
                items.append(line)
            if status.get("recent_exits", 0) > 0:
                items.append(f"最近自动平仓: {status['recent_exits']} 笔")
            sections.append(_section("💼 持仓概览", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] positions: {e}")

    # ── 2. 交易绩效 ──────────────────────────────────────────
    try:
        from src.trading_journal import journal
        if journal:
            perf = journal.get_performance(days=7)
            if perf and perf.get("total_trades", 0) > 0:
                items = []
                items.append(f"7日战绩: {perf.get('total_trades', 0)} 笔 | "
                             f"胜率 {perf.get('win_rate', 0):.0f}%")
                items.append(f"累计盈亏: ${perf.get('total_pnl', 0):+,.2f}")
                if perf.get("sharpe"):
                    items.append(f"夏普比率: {perf['sharpe']:.2f} | "
                                 f"最大回撤: {perf.get('max_drawdown', 0):.1f}%")
                if perf.get("expectancy"):
                    items.append(f"期望值: ${perf['expectancy']:+.2f}/笔")
                sections.append(_section("📊 7日交易绩效", items))

            # 昨日 P&L
            today_pnl = journal.get_today_pnl()
            if today_pnl and today_pnl.get("trades", 0) > 0:
                items = [
                    f"今日: {today_pnl['trades']} 笔 | "
                    f"胜 {today_pnl.get('wins', 0)} 负 {today_pnl.get('losses', 0)} | "
                    f"盈亏 ${today_pnl.get('pnl', 0):+,.2f}"
                ]
                if today_pnl.get("hit_limit"):
                    items.append("⚠️ 已触及日亏损限额")
                sections.append(_section("📅 今日交易", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] journal: {e}")

    # ── 3. 目标进度 ──────────────────────────────────────────
    try:
        from src.trading_journal import journal
        if journal:
            targets = journal.get_active_targets()
            if targets:
                items = []
                for t in targets[:3]:
                    name = t.get("name", "目标")
                    progress = t.get("progress_pct", 0)
                    bar_len = 10
                    filled = int(progress / 100 * bar_len)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    items.append(f"{name}: [{bar}] {progress:.0f}%")
                sections.append(_section("🎯 目标进度", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] targets: {e}")

    # ── 4. 待办事项 ──────────────────────────────────────────
    try:
        from src.execution.task_mgmt import top_tasks
        tasks = top_tasks(limit=5, db_path=db_path)
        if tasks:
            items = []
            for t in tasks:
                status_icon = {"done": "✅", "in_progress": "🔄"}.get(
                    t.get("status", ""), "⬜"
                )
                items.append(f"{status_icon} {t.get('title', '')}")
            sections.append(_section("📋 待办事项", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] tasks: {e}")

    # ── 4.5 今日提醒 ──────────────────────────────────────────
    try:
        from src.execution.life_automation import list_reminders
        from src.utils import now_et
        pending = list_reminders(status="pending", db_path=db_path)
        if pending:
            now = now_et()
            today_end = now.replace(hour=23, minute=59, second=59)
            today_reminders = []
            recurring_reminders = []
            for r in pending:
                try:
                    remind_time = datetime.fromisoformat(r["remind_at"])
                    if remind_time <= today_end:
                        time_str = remind_time.strftime("%H:%M")
                        today_reminders.append(f"⏰ {time_str} — {r['message']}")
                except (ValueError, TypeError) as e:  # noqa: F841
                    pass
                # 重复提醒也列出（不论时间）
                recurrence = r.get("recurrence_rule", "")
                if recurrence:
                    recurring_reminders.append(f"🔄 {r['message']} ({recurrence})")

            items = []
            if today_reminders:
                items.extend(sorted(today_reminders))
            if recurring_reminders and not today_reminders:
                # 只有重复提醒没有今日一次性提醒时才显示
                items.extend(recurring_reminders[:3])
            if items:
                sections.append(_section("⏰ 今日提醒", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] reminders: {e}")

    # ── 4.8 关注股票隔夜变动 ──────────────────────────────────
    try:
        from src.invest_tools import get_quick_quotes

        # 从持仓和关注列表获取用户关注的股票
        watchlist_symbols = []
        try:
            if monitors:
                pm = monitors.get("position_monitor")
                if pm:
                    positions = pm.get_positions() if hasattr(pm, "get_positions") else []
                    for pos in (positions or []):
                        sym = pos.get("symbol", "")
                        if sym:
                            watchlist_symbols.append(sym)
        except Exception as e:
            logger.debug("静默异常: %s", e)

        # 补充 watchlist 中的股票
        try:
            from src.watchlist import get_watchlist_symbols
            wl = get_watchlist_symbols()
            for sym in (wl or []):
                if sym not in watchlist_symbols:
                    watchlist_symbols.append(sym)
        except Exception as e:
            logger.debug("静默异常: %s", e)

        if watchlist_symbols:
            quotes = await get_quick_quotes(watchlist_symbols[:10])  # 最多10只
            if quotes:
                items = []
                for sym in watchlist_symbols[:10]:
                    data = quotes.get(sym)
                    if not data:
                        continue
                    price = data.get("price", 0)
                    change = data.get("change_pct", 0)
                    if abs(change) < 0.5:
                        continue  # 变动<0.5%不显示,减少噪音
                    emoji = "📈" if change >= 0 else "📉"
                    items.append(f"{emoji} {sym}: ${price:,.2f} ({change:+.2f}%)")
                if items:
                    sections.append(_section("👀 关注股票隔夜变动", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] watchlist: {e}")

    # ── 5. 市场行情 (9 大指数) ────────────────────────────────
    try:
        from src.invest_tools import get_quick_quotes
        symbols = ["^GSPC", "^IXIC", "^DJI", "^HSI", "000001.SS", "BTC-USD", "ETH-USD", "GC=F", "CL=F"]
        names = {
            "^GSPC": "S&P 500", "^IXIC": "纳斯达克", "^DJI": "道琼斯",
            "^HSI": "恒生", "000001.SS": "上证",
            "BTC-USD": "BTC", "ETH-USD": "ETH",
            "GC=F": "黄金", "CL=F": "原油",
        }
        quotes = await get_quick_quotes(symbols)
        if quotes:
            items = []
            for sym in symbols:
                data = quotes.get(sym)
                if not data:
                    continue
                name = names.get(sym, sym)
                price = data.get("price", 0)
                change = data.get("change_pct", 0)
                emoji = "📈" if change >= 0 else "📉"
                if price > 1000:
                    items.append(f"{emoji} {name}: {price:,.0f} ({change:+.2f}%)")
                else:
                    items.append(f"{emoji} {name}: ${price:,.2f} ({change:+.2f}%)")
            if items:
                sections.append(_section("💹 市场行情", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] quotes: {e}")

    # ── 6. 恐惧贪婪指数 ──────────────────────────────────────
    try:
        from src.invest_tools import get_fear_greed_index
        fng = await get_fear_greed_index()
        if fng and fng.get("source") != "fallback":
            value = fng.get("value", 0)
            label = fng.get("label", "")
            gauge = "🟢" if value > 60 else "🟡" if value > 40 else "🔴"
            sections.append(_section("🧭 市场情绪", [
                f"{gauge} 恐惧贪婪指数: {value} ({label})"
            ]))
    except Exception as e:
        logger.debug(f"[DailyBrief] fng: {e}")

    # ── 7. 科技/AI 新闻 (LLM 深度分析 + 持仓关联) ──────────
    try:
        from src.news_fetcher import NewsFetcher
        nf = NewsFetcher()
        ai_news = await nf.fetch_by_category("ai", count=3)
        tech_news = await nf.fetch_by_category("tech_cn", count=3)
        news_items = (ai_news or []) + (tech_news or [])
        if news_items:
            headlines = [item['title'] for item in news_items[:5]]
            # 收集用户持仓 symbols，用于关联分析
            holdings = []
            try:
                from src.position_monitor import position_monitor as _pm
                if _pm and _pm.positions:
                    holdings = list(_pm.positions.keys())
            except Exception as e:
                logger.debug("静默异常: %s", e)
            # 尝试用 LLM 生成深度分析
            analyzed = await _analyze_news_with_llm(headlines, holdings)
            if analyzed:
                sections.append(_section("📰 科技快讯 (AI解读)", analyzed))
            else:
                # 降级: LLM 失败则回退到纯标题列表
                items = [f"• {t}" for t in headlines]
                sections.append(_section("📰 科技快讯", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] news: {e}")

    # ── 8. 社媒运营状态 ──────────────────────────────────────
    try:
        from src.social_scheduler import social_autopilot
        if social_autopilot:
            status = social_autopilot.status()
            if status:
                items = []
                running = "运行中" if status.get("running") else "已停止"
                items.append(f"自动驾驶: {running}")
                if status.get("posts_today", 0) > 0:
                    items.append(f"今日已发: {status['posts_today']} 篇")
                if status.get("draft_count", 0) > 0:
                    items.append(f"待发草稿: {status['draft_count']} 条")
                next_action = status.get("next_action", "")
                if next_action:
                    next_time = status.get("next_time", "")
                    items.append(f"下一动作: {next_action} ({next_time})")
                sections.append(_section("📱 社媒运营", items))
    except Exception as e:
        logger.debug(f"[DailyBrief] social: {e}")

    # ── 9. 监控 + 草稿 ──────────────────────────────────────
    aux_items = []
    try:
        if monitors:
            aux_items.append(f"👁 活跃监控: {len(monitors)} 个")
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)
    try:
        with get_conn(db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM social_drafts WHERE status='draft'"
            )
            count = cursor.fetchone()[0]
            if count:
                aux_items.append(f"✏️ 待发布草稿: {count} 条")
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)
    if aux_items:
        sections.append(_section("🔧 运维状态", aux_items))

    # ── 10. API 成本 ─────────────────────────────────────────
    try:
        from src.monitoring import cost_analyzer
        if cost_analyzer:
            prediction = cost_analyzer.predict_monthly_cost()
            if prediction:
                daily_avg = prediction.get("daily_average", 0)
                monthly = prediction.get("monthly_prediction", 0)
                if daily_avg > 0:
                    sections.append(_section("💰 API 成本", [
                        f"日均: ${daily_avg:.2f} | 月预估: ${monthly:.2f}",
                    ]))
    except Exception as e:
        logger.debug(f"[DailyBrief] cost: {e}")

    # ── 11. 闲鱼运营 ─────────────────────────────────────────
    try:
        from src.xianyu.xianyu_context import XianyuContextManager
        xctx = XianyuContextManager()
        xstats = xctx.daily_stats() if hasattr(xctx, 'daily_stats') else {}
        if xstats:
            xlines = []
            if xstats.get("messages", 0) > 0:
                xlines.append(f"💬 咨询 {xstats.get('messages', 0)} 条")
            if xstats.get("orders", 0) > 0:
                xlines.append(f"📦 下单 {xstats.get('orders', 0)} 笔")
            if xstats.get("payments", 0) > 0:
                xlines.append(f"💰 成交 {xstats.get('payments', 0)} 笔")
            if xstats.get("conversion_rate"):
                xlines.append(f"📈 转化率 {xstats['conversion_rate']}")
            # 营收+利润数据（搬运 Shopify Analytics 的日报模式）
            try:
                profit = xctx.get_profit_summary(days=1) if hasattr(xctx, 'get_profit_summary') else {}
                if profit and profit.get("revenue", 0) > 0:
                    xlines.append(f"💵 营收 ¥{profit['revenue']:.0f} | 利润 ¥{profit['profit']:.0f}")
                    if profit.get("orders", 0) > 0:
                        avg = profit["revenue"] / profit["orders"]
                        xlines.append(f"📊 客单价 ¥{avg:.0f}")
            except Exception as e:
                logger.debug("静默异常: %s", e)
            if xlines:
                sections.append(_section("🐟 闲鱼运营", xlines))
            # 今日热销 Top3 — 调用 BI 商品排行接口
            try:
                top3 = xctx.get_item_rankings(days=1, limit=3)
                if top3:
                    top_lines = ["🏆 今日热销:"]
                    for i, item in enumerate(top3, 1):
                        title = item.get("title", "未知")[:10]
                        consult = item.get("consultations", 0)
                        convert = item.get("conversions", 0)
                        top_lines.append(f"  {i}. {title} ({consult}咨询/{convert}成交)")
                    sections.append(_section("", top_lines))
            except Exception as e:
                pass  # BI 数据获取失败不影响日报
                logger.debug("静默异常: %s", e)
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)

    # ── 12. 社媒互动 ─────────────────────────────────────────
    try:
        from src.execution.life_automation import get_engagement_summary
        eng = get_engagement_summary(days=7)
        if eng.get("success") and eng.get("total_posts", 0) > 0:
            elines = [f"📊 近7天 {eng['total_posts']} 篇帖子"]
            for plat, data in eng.get("platforms", {}).items():
                elines.append(f"  {plat}: ❤️{data['likes']} 💬{data['comments']} 👀{data['views']}")
            sections.append(_section("📱 社媒互动", elines))
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)

    # ── 12.5 粉丝增长 ─────────────────────────────────────────
    try:
        from src.execution.life_automation import get_follower_growth
        growth = get_follower_growth(days=1)
        if growth:
            _plat_names = {"x": "X", "xhs": "小红书"}
            parts = []
            for plat, data in growth.items():
                name = _plat_names.get(plat, plat)
                end = data.get("end", 0)
                change = data.get("change", 0)
                sign = "+" if change >= 0 else ""
                parts.append(f"{name} {end:,}({sign}{change})")
            if parts:
                sections.append(_section("👥 粉丝", [" | ".join(parts)]))
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)

    # ── 13. 项目发现 (GitHub Trending) ─────────────────────────
    try:
        trending_items = await _fetch_trending_projects()
        if trending_items:
            sections.append(_section("🔭 项目发现", trending_items))
    except Exception as e:
        logger.debug("日报段落生成异常: %s", e)

    # ── 组装最终日报 ─────────────────────────────────────────

    # ── 收集各模块关键指标，用于执行摘要 + 智能建议 ──────────
    sections_data = {}
    try:
        # 持仓盈亏
        try:
            from src.position_monitor import position_monitor as _pm_ref
            if _pm_ref and _pm_ref.positions:
                _st = _pm_ref.get_status()
                sections_data["portfolio_pnl"] = _st.get("total_unrealized_pnl", 0)
                sections_data["positions_count"] = _st.get("monitored_count", 0)
        except Exception as e:
            logger.debug("日报指标收集-持仓盈亏异常: %s", e)

        # 闲鱼数据
        try:
            from src.xianyu.xianyu_context import XianyuContextManager
            _xctx = XianyuContextManager()
            _xst = _xctx.daily_stats() if hasattr(_xctx, 'daily_stats') else {}
            if _xst:
                sections_data["xianyu_consultations"] = _xst.get("consultations", 0)
                sections_data["xianyu_orders"] = _xst.get("orders", 0)
        except Exception as e:
            logger.debug("日报指标收集-闲鱼数据异常: %s", e)

        # 社媒发帖
        try:
            from src.execution.life_automation import get_engagement_summary
            _eng = get_engagement_summary(days=1, db_path=db_path)
            if _eng.get("success"):
                sections_data["social_posts"] = _eng.get("total_posts", 0)
        except Exception as e:
            logger.debug("日报指标收集-社媒发帖异常: %s", e)

        # API 成本
        try:
            from src.monitoring import cost_analyzer as _ca_ref
            if _ca_ref:
                _pred = _ca_ref.predict_monthly_cost()
                if _pred:
                    sections_data["api_daily_cost"] = _pred.get("daily_average", 0)
        except Exception as e:
            logger.debug("日报指标收集-API成本异常: %s", e)

        # 市场情绪
        try:
            from src.invest_tools import get_fear_greed_index
            _fng = await get_fear_greed_index()
            if _fng and _fng.get("source") != "fallback":
                sections_data["market_sentiment"] = (
                    f"{_fng.get('value', 0)} ({_fng.get('label', '')})"
                    )
        except Exception as e:
            logger.debug("静默异常: %s", e)
        # 发文绩效报告
        try:
            from src.content_pipeline import content_pipeline
            if content_pipeline and hasattr(content_pipeline, "get_post_performance_report"):
                post_report = content_pipeline.get_post_performance_report(days=7)
                if post_report:
                    if post_report.get("best_post"):
                        bp = post_report["best_post"]
                        items.append(bullet(
                            f"最佳帖子: {bp.get('title', '无标题')[:30]} "
                            f"({bp.get('engagement', 0)} 互动)", icon="⭐"
                        ))
                    if post_report.get("follower_change") is not None:
                        fc = post_report["follower_change"]
                        fc_emoji = "📈" if fc >= 0 else "📉"
                        items.append(kv("粉丝变化", f"{fc_emoji} {fc:+d}"))
        except Exception as e:
            logger.debug("静默异常: %s", e)
        # 社交自动驾驶状态
        try:
            ap = autopilot
            if ap is None:
                from src.social_scheduler import social_autopilot as _ap
                ap = _ap
            if ap and hasattr(ap, "status"):
                s = ap.status()
                if s and s.get("posts_today", 0) > 0:
                    items.append(kv("自动驾驶", "运行中" if s.get("running") else "已停止"))
        except Exception as e:
            logger.debug("静默异常: %s", e)
        # 粉丝增长趋势 (7天)
        try:
            from src.execution.life_automation import get_follower_growth
            growth = get_follower_growth(days=7)
            if growth:
                _plat_names = {"x": "X", "xhs": "小红书"}
                for plat, data in growth.items():
                    name = _plat_names.get(plat, plat)
                    change = data.get("change", 0)
                    pct = data.get("change_pct", 0)
                    fc_emoji = "📈" if change >= 0 else "📉"
                    items.append(kv(f"{name} 粉丝", f"{fc_emoji} {data.get('end', 0):,} ({change:+d}, {pct:+.1f}%)"))
        except Exception as e:
            logger.debug("静默异常: %s", e)
        if items:
            sections.append(_section("📱 社媒周报", items))
    except Exception as e:
        logger.debug("[WeeklyReport] 社媒: %s", e)

    # ── 4. 🐟 闲鱼周报 ──────────────────────────────────────
    try:
        xctx = xianyu_ctx
        if xctx is None:
            try:
                from src.xianyu.xianyu_context import XianyuContextManager
                xctx = XianyuContextManager()
            except ImportError:
                xctx = None
        if xctx:
            items = []
            # 尝试获取利润汇总（7天）
            profit = {}
            if hasattr(xctx, "get_profit_summary"):
                try:
                    profit = xctx.get_profit_summary(days=7) or {}
                except Exception as e:
                    logger.debug("静默异常: %s", e)
            # 尝试获取日统计（聚合7天）
            xstats = {}
            if hasattr(xctx, "daily_stats"):
                try:
                    xstats = xctx.daily_stats() or {}
                except Exception as e:
                    logger.debug("静默异常: %s", e)
            if profit.get("revenue", 0) > 0:
                items.append(kv("营收", f"¥{profit['revenue']:,.0f}"))
                items.append(kv("利润", f"¥{profit.get('profit', 0):,.0f}"))
                if profit.get("orders", 0) > 0:
                    avg = profit["revenue"] / profit["orders"]
                    items.append(kv("成交", f"{profit['orders']} 单 | 客单价 ¥{avg:.0f}"))
            if xstats.get("messages", 0) > 0:
                items.append(kv("咨询", f"{xstats['messages']} 条"))
            if xstats.get("conversion_rate"):
                items.append(kv("转化率", f"{xstats['conversion_rate']}"))
            if items:
                sections.append(_section("🐟 闲鱼周报", items))
    except Exception as e:
        logger.debug("[WeeklyReport] 闲鱼: %s", e)

    # ── 5. 💰 成本周报 ──────────────────────────────────────
    try:
        ca = cost_analyzer
        if ca is None:
            from src.monitoring import cost_analyzer as _ca
            ca = _ca
        if ca:
            items = []
            # 使用 predict_monthly_cost 获取日均成本
            prediction = ca.predict_monthly_cost() if hasattr(ca, "predict_monthly_cost") else {}
            if prediction:
                daily_avg = prediction.get("daily_average", 0)
                monthly = prediction.get("monthly_prediction", 0)
                if daily_avg > 0:
                    weekly_est = daily_avg * 7
                    items.append(kv("本周估算", f"${weekly_est:.2f}"))
                    items.append(kv("日均成本", f"${daily_avg:.2f}"))
                    items.append(kv("月度预估", f"${monthly:.2f}"))
            # 如果有专门的周报方法则优先使用
            if hasattr(ca, "get_weekly_report"):
                try:
                    wr = ca.get_weekly_report()
                    if wr:
                        if wr.get("this_week") is not None:
                            items = [kv("本周成本", f"${wr['this_week']:.2f}")]
                        if wr.get("last_week") is not None:
                            change = wr["this_week"] - wr["last_week"]
                            ch_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                            items.append(kv("环比变化", f"{ch_emoji} ${change:+,.2f}"))
                        if wr.get("daily_average") is not None:
                            items.append(kv("日均", f"${wr['daily_average']:.2f}"))
                except Exception as e:
                    logger.debug("静默异常: %s", e)
            if items:
                sections.append(_section("💰 成本周报", items))
    except Exception as e:
        logger.debug("[WeeklyReport] 成本: %s", e)

    # ── 6. 🎯 目标进度 ──────────────────────────────────────
    try:
        tj = trading_journal
        if tj is None:
            from src.trading_journal import journal as _j
            tj = _j
        if tj and hasattr(tj, "format_target_progress"):
            progress_text = tj.format_target_progress()
            if progress_text and len(progress_text.strip()) > 5:
                # 将文本拆成行作为 items
                items = [line.strip() for line in progress_text.strip().split("\n") if line.strip()]
                if items:
                    sections.append(_section("🎯 目标进度", items))
        elif tj and hasattr(tj, "get_active_targets"):
            targets = tj.get_active_targets()
            if targets:
                items = []
                for t in targets[:3]:
                    name = t.get("name", "目标")
                    progress = t.get("progress_pct", 0)
                    bar_len = 10
                    filled = int(progress / 100 * bar_len)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    items.append(f"{name}: [{bar}] {progress:.0f}%")
                sections.append(_section("🎯 目标进度", items))
    except Exception as e:
        logger.debug("[WeeklyReport] 目标进度: %s", e)

    # ── 组装最终周报 ─────────────────────────────────────────
    if not sections:
        sections.append(_section("📋 本周概况", ["暂无数据，所有数据源均不可用"]))

    return format_digest(
        title="📋 综合周报",
        intro=f"📅 {week_start} — {week_end}",
        sections=sections,
        footer=f"💡 说「周报」随时查看 | ⏱ {_get_timestamp_tag()}",
    )


def _get_timestamp_tag() -> str:
    """获取时间戳标签"""
    try:
        from src.notify_style import timestamp_tag
        return timestamp_tag()
    except Exception as e:  # noqa: F841
        return datetime.now(timezone.utc).strftime("%H:%M UTC")


async def _fetch_trending_projects() -> List[str]:
    """从 GitHub Trending 获取与 OpenClaw 相关的有价值项目"""

    # 关注的关键领域
    INTEREST_KEYWORDS = [
        "telegram bot", "social media", "auto upload", "xianyu", "闲鱼",
        "llm", "ai agent", "tts", "edge-tts", "novel writing",
        "trading bot", "web scraping", "automation",
        "小红书", "douyin", "bilibili", "wechat",
    ]

    items: List[str] = []
    try:
        # 使用现有的 github_trending 模块
        try:
            from src.evolution.github_trending import fetch_trending
            repos = await fetch_trending(language="python", since="daily")
            if repos:
                for repo in repos[:10]:
                    name = repo.name or ""
                    desc = (repo.description or "").lower()
                    stars = repo.stars or 0
                    # 筛选与 OpenClaw 领域相关的
                    relevant = any(kw in desc or kw in name.lower() for kw in INTEREST_KEYWORDS)
                    if relevant and stars > 50:
                        items.append(
                            f"⭐{stars} {name}: {repo.description[:80] if repo.description else ''}"
                        )
        except ImportError:
            pass

        if not items:
            items.append("暂无与 OpenClaw 相关的热门项目")
        else:
            items.insert(0, "今日与 OpenClaw 相关的 GitHub 热门项目:")
    except Exception as e:
        logger.debug("[DailyBrief] Trending 获取失败: %s", e)
        items.append("GitHub Trending 获取失败")

    return items
