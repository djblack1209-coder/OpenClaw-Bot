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

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any

from src.models import TradeProposal
from src.utils import now_et as _now_et, env_bool, env_int

logger = logging.getLogger(__name__)

# ============ 交易循环时间常量（秒） ============
SLEEP_MARKET_CLOSED = 3600  # 周末/假日休市等待间隔（1小时）
SLEEP_OFF_HOURS = 600  # 非交易时段（盘前/盘后）等待间隔（10分钟）


# 从拆分后的模块导入
from src.trading.market_calendar import is_market_holiday
from src.trading_pipeline import TradingPipeline, TraderState
from src.perf_metrics import perf_timer
from src.auto_trader_filters import AutoTraderFiltersMixin
from src.auto_trader_review import AutoTraderReviewMixin


class AutoTrader(AutoTraderFiltersMixin, AutoTraderReviewMixin):
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
        self._today_date = ""  # 用于日切重置
        self._last_scan: Optional[datetime] = None
        self._scan_results: List[Dict] = []
        self._proposals: List[TradeProposal] = []
        self._cycle_lock = asyncio.Lock()  # 防止并发循环执行
        self._no_trade_cycles = 0
        self._forced_trades_today = 0

        # 防空仓策略：连续空仓后，允许执行小规模探索交易（仍经过风控）
        self.force_trade_on_idle = env_bool("FORCE_TRADE_ON_IDLE", True)
        self.force_trade_after_idle_cycles = env_int("FORCE_TRADE_AFTER_IDLE_CYCLES", 3, minimum=1)
        self.force_trade_min_score = env_int("FORCE_TRADE_MIN_SCORE", 30, minimum=10)
        self.max_forced_trades_per_day = env_int("MAX_FORCED_TRADES_PER_DAY", 1, minimum=0)

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

        def _main_loop_done(t):
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.critical("[AutoTrader] 主循环崩溃: %s", exc)

        self._task.add_done_callback(_main_loop_done)
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
            except asyncio.CancelledError as e:  # noqa: F841
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
            "交易待成交",
            "交易已成交",
            "成交回写完成",
            "次日重挂已提交",
            "卖出完成",
            "止损触发",
            "止盈触发",
            "追踪止损",
            "自动停机",
            "熔断",
            "日亏损限额",
            "风控拒绝",
            "决策验证拒绝",
        )
        # P1: 交易循环摘要、扫描结果、AI投票结论 — 有信息量
        p1_keywords = (
            "阶段 4/4",
            "阶段 3/4: AI团队投票完成",
            "防空仓策略",
            "IBKR 未连接",
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

        for attempt in range(3):
            try:
                await self.notify(text)
                return
            except Exception as e:
                if is_p0 and attempt < 2:
                    logger.debug("[AutoTrader] P0通知重试 (%d/3): %s", attempt + 1, e)
                    await asyncio.sleep(2**attempt)
                    continue
                logger.warning("[AutoTrader] 通知发送失败: %s (attempt %d)", e, attempt + 1)
                return

    def _get_capital(self) -> float:
        """Return configured total capital, defaulting to 2000."""
        if self.risk_manager and hasattr(self.risk_manager, "config"):
            return float(getattr(self.risk_manager.config, "total_capital", 2000.0))
        return 2000.0

    def _estimate_open_exposure(self) -> float:
        """估算当前组合已开仓总敞口（用于提案前仓位裁剪）"""
        if not self.pipeline or not getattr(self.pipeline, "portfolio", None):
            return 0.0
        try:
            positions = self.pipeline.portfolio.get_positions()
        except Exception as e:
            # 敞口估算失败时返回保守高值（总资金），防止系统误判为无持仓而超额开仓
            logger.warning("[AutoTrader] 获取持仓失败，返回保守敞口(总资金上限): %s", e)
            return self._get_capital()

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
        max_exposure = float(getattr(cfg, "total_capital", 2000.0)) * float(getattr(cfg, "max_total_exposure_pct", 0.8))
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
            today_pnl = getattr(self.risk_manager, "_today_pnl", 0)
            lines.append("今日已实现盈亏: $%.2f" % today_pnl)
            daily_limit = 100
            if hasattr(self.risk_manager, "config"):
                daily_limit = getattr(self.risk_manager.config, "daily_loss_limit", 100)
            lines.append("日亏损限额: $%.0f (剩余$%.0f)" % (daily_limit, daily_limit + today_pnl))

        # 当前持仓数
        if self.pipeline and self.pipeline.monitor:
            pos_count = len(self.pipeline.monitor.positions)
            lines.append("当前持仓: %d笔" % pos_count)

        # 闭环学习：注入近期交易结果 + 教训
        try:
            from src.trading_journal import journal as tj

            if tj:
                closed = tj.get_closed_trades(days=3, limit=5) if hasattr(tj, "get_closed_trades") else []
                if closed:
                    lines.append("\n[近3日交易结果]")
                    for t in closed[:5]:
                        lines.append(
                            "  %s %s PnL=$%+.2f (%+.1f%%) 持仓%.1fh | %s"
                            % (
                                t.get("side", "?"),
                                t.get("symbol", "?"),
                                t.get("pnl", 0),
                                t.get("pnl_pct", 0),
                                t.get("hold_duration_hours", 0) or 0,
                                (t.get("exit_reason") or t.get("entry_reason") or "")[:40],
                            )
                        )
                # 注入迭代教训
                if hasattr(tj, "generate_iteration_report"):
                    report = tj.generate_iteration_report(days=7)
                    suggestions = report.get("improvement_suggestions", []) if isinstance(report, dict) else []
                    if suggestions:
                        lines.append("\n[近7日教训]")
                        for s in suggestions[:3]:
                            lines.append("  - " + str(s))
        except Exception as e:
            logger.warning("[AutoTrader] 交易日志读取失败，AI投票将缺少历史上下文: %s", e)

        return "\n".join(lines)

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
                    await asyncio.sleep(SLEEP_MARKET_CLOSED)
                    continue

                # 美股假日不交易
                today_str = et_now.strftime("%Y-%m-%d")
                if is_market_holiday(today_str):
                    logger.info("[AutoTrader] 今日 %s 为美股休市日，跳过", today_str)
                    await asyncio.sleep(SLEEP_MARKET_CLOSED)
                    continue

                # 美东时间 9:30-16:00 为交易时段
                market_open = (hour > 9) or (hour == 9 and minute >= 30)
                market_close = hour >= 16

                if not market_open or market_close:
                    # 收盘后不再在此处复盘，由 Scheduler eod_auto_review 统一处理
                    await asyncio.sleep(SLEEP_OFF_HOURS)
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

    @perf_timer("trader.run_cycle")
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
            if hasattr(_broker, "ensure_connected"):
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
                "今日已达交易上限 (%d/%d笔)，停止扫描。\n明日自动继续。" % (self._today_trades, self.max_trades_per_day)
            )
            self.state = TraderState.IDLE
            return cycle_result

        # ========== 阶段1: 全市场扫描 ==========
        self.state = TraderState.SCANNING
        logger.info("[AutoTrader] === 交易循环 #%d ===", self._cycle_count)

        await self._safe_notify(
            "-- 交易循环 #%d 开始 --\n"
            "阶段 1/4: 全市场扫描中...\n"
            "今日已交易: %d/%d笔" % (self._cycle_count, self._today_trades, self.max_trades_per_day)
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
            await self._safe_notify("阶段 1/4: 扫描完成，无信号。\n市场平静，继续观望。")
            self.state = TraderState.IDLE
            return cycle_result

        # ========== 阶段2: 多层筛选 ==========
        candidates = self._filter_candidates(self._scan_results)
        cycle_result["candidates"] = len(candidates)

        # 扩大候选池: 取 Top N 进入分析
        top_candidates = candidates[: self.max_candidates_for_vote]

        # 用 IBKR 快照刷新 Top 候选报价
        await self._enrich_candidates_with_broker_quotes(top_candidates)

        if self.notify:
            scan_lines = [
                "阶段 1/4: 扫描完成\n扫描 %d 个标的 -> 筛选出 %d 个候选\n" % (cycle_result["scanned"], len(candidates))
            ]
            for i, c in enumerate(top_candidates):
                arrow = "+" if c.get("change_pct", 0) >= 0 else ""
                scan_lines.append(
                    "  %d. %s $%.2f (%s%.1f%%) 评分:%+d %s"
                    % (
                        i + 1,
                        c.get("symbol", "?"),
                        c.get("price", 0),
                        arrow,
                        c.get("change_pct", 0),
                        c.get("score", 0),
                        c.get("signal_cn", ""),
                    )
                )
            if not top_candidates:
                scan_lines.append("  无符合条件的候选，继续观望。")
            await self._safe_notify("\n".join(scan_lines))

        if not top_candidates:
            self.state = TraderState.IDLE
            return cycle_result

        # ========== 阶段3: AI团队分析 + 投票 ==========
        self.state = TraderState.ANALYZING

        await self._safe_notify("阶段 2/4: 获取 %d 个候选的详细技术数据..." % len(top_candidates))

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
            "雷达 -> 宏观 -> 图表 -> 风控 -> 指挥官" % (len(analyses), len(top_candidates))
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
                candidate = next((c for c in top_candidates if c.get("symbol") == vr.symbol), {})
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
                        entry_price=price,
                        stop_loss=stop,
                    )
                    if "error" not in sizing:
                        quantity = sizing["shares"]
                    else:
                        # 安全修复: 风控引擎计算失败时跳过该候选，不绕过风控
                        logger.warning(
                            "[AutoTrader] %s 风控仓位计算失败(%s)，跳过该候选",
                            vr.symbol, sizing.get("error", "未知")
                        )
                        continue
                if quantity <= 0:
                    # 风控引擎建议不交易（如凯利公式得出0仓位）
                    logger.info("[AutoTrader] %s 风控建议仓位为0，跳过", vr.symbol)
                    continue

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

                proposals.append(
                    TradeProposal(
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
                        votes=list(vr.votes),  # 保留每个AI的独立投票，供准确率追踪
                    )
                )
                exposure_budget_left -= quantity * price
                if len(proposals) >= remaining_today:
                    break
        else:
            # 无AI团队时降级为机械策略
            for candidate in top_candidates[: min(self.max_trades_per_cycle, remaining_today)]:
                proposal = await self._generate_proposal(candidate)
                if proposal and proposal.action == "BUY":
                    if exposure_budget_left <= 0:
                        logger.info("[AutoTrader] 总敞口额度已用尽，停止生成提案")
                        break
                    max_qty_by_exposure = (
                        int(exposure_budget_left / proposal.entry_price) if proposal.entry_price > 0 else 0
                    )
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
                force_candidates = [c for c in top_candidates if c.get("score", 0) >= self.force_trade_min_score][
                    :forced_limit
                ]
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
                        p.reason = f"{p.reason} | 反空仓执行: 连续{self._no_trade_cycles}轮未达成AI共识"
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
                    % (p.symbol, p.quantity, p.entry_price, p.stop_loss, p.take_profit, p.reason[:80])
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

                        # 发射结构化交易事件 — 供 ProactiveEngine 延迟跟进
                        try:
                            from src.core.event_bus import get_event_bus, EventType as _EvtType

                            _trade_event_data = {
                                "symbol": proposal.symbol,
                                "direction": proposal.action,
                                "quantity": proposal.quantity,
                                "entry_price": proposal.entry_price,
                                "stop_loss": proposal.stop_loss,
                                "take_profit": proposal.take_profit,
                                "confidence": getattr(proposal, "confidence", 0),
                                "decided_by": getattr(proposal, "decided_by", ""),
                                "timestamp": _now_et().isoformat(),
                            }
                            _evt_task = asyncio.create_task(
                                get_event_bus().publish(
                                    _EvtType.TRADE_EXECUTED,
                                    _trade_event_data,
                                    source="auto_trader",
                                )
                            )
                            _evt_task.add_done_callback(
                                lambda t: (
                                    t.exception()
                                    and logger.debug("[AutoTrader] EventBus 交易事件发射异常: %s", t.exception())
                                )
                            )
                        except Exception as _evt_err:
                            logger.debug("[AutoTrader] 交易事件发射失败(非致命): %s", _evt_err)

                        # 结构化交易卡片 — 搬运自 freqtrade 通知格式
                        try:
                            from src.telegram_ux import format_trade_card

                            card = format_trade_card(
                                {
                                    "action": proposal.action,
                                    "symbol": proposal.symbol,
                                    "quantity": proposal.quantity,
                                    "entry_price": proposal.entry_price,
                                    "stop_loss": proposal.stop_loss,
                                    "take_profit": proposal.take_profit,
                                    "reason": proposal.reason,
                                    "confidence": proposal.confidence,
                                }
                            )
                            card += "\n\n今日交易: %d/%d笔" % (self._today_trades, self.max_trades_per_day)
                            await self._safe_notify(card)
                        except Exception as e:  # noqa: F841
                            await self._safe_notify(
                                "交易执行成功\n"
                                "BUY %s x%d @ $%.2f\n"
                                "止损: $%.2f | 止盈: $%.2f\n"
                                "今日交易: %d/%d笔"
                                % (
                                    proposal.symbol,
                                    proposal.quantity,
                                    proposal.entry_price,
                                    proposal.stop_loss,
                                    proposal.take_profit,
                                    self._today_trades,
                                    self.max_trades_per_day,
                                )
                            )
                    elif exec_result["status"] == "rejected":
                        cycle_result["rejected"] += 1
                        await self._safe_notify(
                            "交易被风控拒绝: %s %s\n原因: %s"
                            % (proposal.symbol, proposal.action, exec_result.get("reason", "未知"))
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
                        % (p.action, p.symbol, p.quantity, p.entry_price, p.stop_loss, p.take_profit, p.reason)
                    )

        self.state = TraderState.MONITORING
        await self._safe_notify(
            "-- 循环 #%d 完成 --\n"
            "扫描%d -> 候选%d -> 分析%d -> 投票%d -> 提案%d -> 提交%d -> 执行%d 拒绝%d\n"
            "今日交易: %d/%d笔"
            % (
                self._cycle_count,
                cycle_result["scanned"],
                cycle_result["candidates"],
                cycle_result.get("analyzed", 0),
                cycle_result["voted"],
                cycle_result["proposals"],
                cycle_result["submitted"],
                cycle_result["executed"],
                cycle_result["rejected"],
                self._today_trades,
                self.max_trades_per_day,
            )
        )

        logger.info(
            "[AutoTrader] 循环 #%d 完成: 扫描%d 候选%d 投票%d 提案%d 提交%d 执行%d 拒绝%d",
            self._cycle_count,
            cycle_result["scanned"],
            cycle_result["candidates"],
            cycle_result["voted"],
            cycle_result["proposals"],
            cycle_result["submitted"],
            cycle_result["executed"],
            cycle_result["rejected"],
        )
        return cycle_result

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
            "idle": "空闲",
            "scanning": "扫描中",
            "analyzing": "分析中",
            "executing": "执行中",
            "monitoring": "监控中",
            "reviewing": "复盘中",
            "paused": "暂停",
            "error": "异常",
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
            result = await self.pipeline.execute_proposal(proposal)
            # HI-572: 手动确认也要计入日交易数
            if result and result.get("status") in ("executed", "simulated"):
                self._today_trades += 1
                logger.info(
                    "[AutoTrader] confirm_proposal 交易计数+1，今日: %d/%d笔",
                    self._today_trades, self.max_trades_per_day,
                )
            return result
        return None

    def cancel_proposals(self) -> int:
        """取消所有待确认提案"""
        count = len(self._proposals)
        self._proposals.clear()
        return count


# ── 向后兼容导出 (v6.0 拆分) ──
from src.trading_pipeline import TradingPipeline  # noqa: F401
