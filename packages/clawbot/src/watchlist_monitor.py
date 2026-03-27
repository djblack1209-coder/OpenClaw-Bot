"""自选股异动监控引擎

搬运: position_monitor.py 监控循环+冷却模式 + ta_engine 异动扫描
对标: 交易类产品的价格告警功能（标配能力）

监控维度:
1. 价格异动: 单日涨跌幅 >3%
2. 放量异动: 成交量 > 20日均量 1.5x
3. RSI 极值: RSI6 < 20 或 > 80
4. 目标价/止损价触达

v2.0 变更 (2026-03-28):
  - 异动通知升级为"情报级": 附加新闻原因 + 迷你K线图 + RSI + 持仓浮盈
  - 新闻搜索: Google News RSS → Bing 降级链
  - K线图: 5日1小时 plotly candlestick → PNG
  - 所有增强数据注入 EventBus 事件，由 proactive_engine 负责富文本渲染

> 最后更新: 2026-03-28
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from loguru import logger


# ── 异动类型 ────────────────────────────────────────────────
ANOMALY_PRICE_SURGE = "price_surge"       # 单日涨跌幅 >3%
ANOMALY_VOLUME_SURGE = "volume_surge"     # 放量（>1.5x 20日均量）
ANOMALY_RSI_EXTREME = "rsi_extreme"       # RSI6 极值（<20 或 >80）
ANOMALY_TARGET_HIT = "target_hit"         # 触达目标价
ANOMALY_STOPLOSS_HIT = "stoploss_hit"     # 触达止损价

# ── 冷却时间（秒） ─────────────────────────────────────────
_COOLDOWN_SECONDS = {
    ANOMALY_PRICE_SURGE: 1800,    # 30 分钟
    ANOMALY_VOLUME_SURGE: 3600,   # 1 小时
    ANOMALY_RSI_EXTREME: 3600,    # 1 小时
    ANOMALY_TARGET_HIT: 600,      # 10 分钟（重要，短冷却）
    ANOMALY_STOPLOSS_HIT: 600,    # 10 分钟
}


class WatchlistMonitor:
    """自选股异动监控器

    搬运 position_monitor.py 的 while-loop + 冷却模式。
    每 5 分钟扫描 watchlist，检测异动后通过 EventBus 推送。
    """

    def __init__(self, check_interval: int = 300):
        """初始化监控器

        Args:
            check_interval: 检查间隔秒数，默认 300（5分钟）
        """
        self._check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # 冷却记录: (symbol, anomaly_type) → monotonic timestamp
        self._cooldowns: Dict[tuple, float] = {}

    async def start(self):
        """启动监控循环"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        # 崩溃回调（搬运 position_monitor 模式）
        self._task.add_done_callback(self._loop_done)
        logger.info(f"📡 自选股异动监控已启动 (间隔 {self._check_interval}s)")

    async def stop(self):
        """停止监控循环"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("📡 自选股异动监控已停止")

    def _loop_done(self, task: asyncio.Task):
        """监控循环结束回调 — 异常时记录日志"""
        if not task.cancelled() and task.exception():
            logger.critical(f"自选股监控循环崩溃: {task.exception()}")

    # ── 核心监控循环 ────────────────────────────────────────

    async def _monitor_loop(self):
        """主循环: while running → 检查 → sleep"""
        # 启动后等一小段时间再首次检查，避免启动高峰
        await asyncio.sleep(30)

        while self._running:
            try:
                await self._check_watchlist()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"自选股异动检查异常 (将继续): {e}")

            # 定期清理过期冷却
            self._cleanup_cooldowns()

            await asyncio.sleep(self._check_interval)

    async def _check_watchlist(self):
        """核心检查逻辑: 获取自选股 → 批量行情 → 异动判定 → 发布事件"""
        # 1. 获取自选股列表
        try:
            from src.watchlist import get_watchlist_with_targets
        except ImportError:
            return

        items = get_watchlist_with_targets()
        if not items:
            return

        # 2. 批量获取实时行情
        try:
            from src.data_providers import get_quote
        except ImportError:
            return

        symbols = [item["symbol"] for item in items if item.get("symbol")]
        if not symbols:
            return

        # 并行获取行情（搬运 position_monitor 的 asyncio.gather 模式）
        quote_tasks = [get_quote(sym) for sym in symbols]
        quotes_raw = await asyncio.gather(*quote_tasks, return_exceptions=True)

        # 构建 symbol → quote 映射
        quotes: Dict[str, Dict] = {}
        for sym, q in zip(symbols, quotes_raw):
            if isinstance(q, Exception) or not q:
                continue
            quotes[sym] = q

        if not quotes:
            return

        # 3. 逐标的检查异动
        anomalies: List[Dict[str, Any]] = []

        for item in items:
            sym = item.get("symbol", "")
            quote = quotes.get(sym)
            if not quote:
                continue

            price = quote.get("price", 0)
            change_pct = quote.get("change_pct", 0)
            target_price = item.get("target_price") or 0
            stop_loss = item.get("stop_loss") or 0

            # 3a. 价格异动: |涨跌幅| > 3%
            if abs(change_pct) > 3.0 and self._is_cooled(sym, ANOMALY_PRICE_SURGE):
                direction = "暴涨" if change_pct > 0 else "暴跌"
                anomalies.append({
                    "symbol": sym,
                    "anomaly_type": ANOMALY_PRICE_SURGE,
                    "change_pct": change_pct,
                    "price": price,
                    "details": f"{sym} {direction} {abs(change_pct):.1f}%，当前价 ${price:.2f}",
                })
                self._mark_cooldown(sym, ANOMALY_PRICE_SURGE)

            # 3b. 目标价触达
            if target_price > 0 and price >= target_price and self._is_cooled(sym, ANOMALY_TARGET_HIT):
                anomalies.append({
                    "symbol": sym,
                    "anomaly_type": ANOMALY_TARGET_HIT,
                    "change_pct": change_pct,
                    "price": price,
                    "details": f"🎯 {sym} 已触达目标价 ${target_price:.2f}（当前 ${price:.2f}）",
                })
                self._mark_cooldown(sym, ANOMALY_TARGET_HIT)

            # 3c. 止损价触达
            if stop_loss > 0 and price <= stop_loss and self._is_cooled(sym, ANOMALY_STOPLOSS_HIT):
                anomalies.append({
                    "symbol": sym,
                    "anomaly_type": ANOMALY_STOPLOSS_HIT,
                    "change_pct": change_pct,
                    "price": price,
                    "details": f"⚠️ {sym} 已跌破止损价 ${stop_loss:.2f}（当前 ${price:.2f}）",
                })
                self._mark_cooldown(sym, ANOMALY_STOPLOSS_HIT)

        # 4. 对有初步异动的标的做深度技术分析
        await self._deep_scan(anomalies, quotes)

        # 5. 增强异动信息：附加新闻原因、K线图、RSI、持仓信息
        if anomalies:
            await self._enrich_anomalies(anomalies)

        # 6. 发布 EventBus 事件
        if anomalies:
            await self._publish_anomalies(anomalies)

    async def _deep_scan(self, anomalies: List[Dict], quotes: Dict[str, Dict]):
        """对已有异动的标的做深度技术指标检测（放量/RSI极值）"""
        # 收集需要深度扫描的 symbol（排除已有异动的，避免重复报）
        scanned_symbols = {a["symbol"] for a in anomalies}
        all_symbols = set(quotes.keys())
        # 未触发价格异动的标的也做放量/RSI检查
        to_scan = all_symbols

        if not to_scan:
            return

        try:
            from src.ta_engine import compute_indicators
            from src.data_providers import get_history
        except ImportError:
            return

        for sym in to_scan:
            if sym in scanned_symbols and len([a for a in anomalies if a["symbol"] == sym]) >= 2:
                continue  # 同一标的最多2条异动

            try:
                # 获取近期历史数据做技术分析
                df = await get_history(sym, period="1mo", interval="1d")
                if df is None or df.empty or len(df) < 10:
                    continue

                indicators = compute_indicators(df)
                if not indicators:
                    continue

                quote = quotes.get(sym, {})
                change_pct = quote.get("change_pct", 0)
                price = quote.get("price", 0)

                # 放量检测
                if indicators.get("volume_surge") and self._is_cooled(sym, ANOMALY_VOLUME_SURGE):
                    vol_ratio = indicators.get("vol_ratio", 0)
                    anomalies.append({
                        "symbol": sym,
                        "anomaly_type": ANOMALY_VOLUME_SURGE,
                        "change_pct": change_pct,
                        "price": price,
                        "details": f"📊 {sym} 放量 {vol_ratio:.1f}x（20日均量的 {vol_ratio:.1f} 倍）",
                    })
                    self._mark_cooldown(sym, ANOMALY_VOLUME_SURGE)

                # RSI 极值检测
                rsi6 = indicators.get("rsi_6", 50)
                if rsi6 is not None and (rsi6 < 20 or rsi6 > 80) and self._is_cooled(sym, ANOMALY_RSI_EXTREME):
                    zone = "超卖" if rsi6 < 20 else "超买"
                    anomalies.append({
                        "symbol": sym,
                        "anomaly_type": ANOMALY_RSI_EXTREME,
                        "change_pct": change_pct,
                        "price": price,
                        "details": f"📈 {sym} RSI6={rsi6:.0f} {zone}区间（当前价 ${price:.2f}）",
                    })
                    self._mark_cooldown(sym, ANOMALY_RSI_EXTREME)

            except Exception as e:
                logger.debug(f"深度扫描 {sym} 失败: {e}")

    async def _enrich_anomalies(self, anomalies: List[Dict]):
        """为异动通知附加新闻原因、迷你K线图、RSI指标、持仓信息。

        所有增强操作均 try/except 包裹，失败不影响基础通知。
        """
        if not anomalies:
            return

        # 按 symbol 去重，避免重复网络请求
        symbols = list({a["symbol"] for a in anomalies})

        # ── 1. 新闻搜索: Google News RSS → Bing 降级 ──
        news_map: Dict[str, str] = {}
        try:
            from src.news_fetcher import NewsFetcher
            nf = NewsFetcher()
            for sym in symbols:
                try:
                    # 用标的代码搜索最新新闻
                    news = await nf.fetch_from_google_news_rss(sym, count=2)
                    if not news:
                        # 降级到 Bing
                        news = await nf.fetch_from_bing(sym, count=2)
                    if news:
                        news_map[sym] = news[0].get("title", "")
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"异动新闻搜索模块不可用: {e}")

        # ── 2. 迷你K线图 + RSI ──
        chart_map: Dict[str, bytes] = {}
        rsi_map: Dict[str, float] = {}
        try:
            from src.data_providers import get_history
            from src.charts import generate_candlestick

            for sym in symbols:
                try:
                    # 获取5日1小时数据（用于K线图+RSI计算）
                    df = await get_history(sym, period="5d", interval="1h")
                    if df is None or df.empty or len(df) < 5:
                        continue

                    # 生成K线图 — plotly candlestick → PNG
                    ohlcv = []
                    for idx, row in df.iterrows():
                        ohlcv.append({
                            "date": str(idx),
                            "open": float(row["Open"]),
                            "high": float(row["High"]),
                            "low": float(row["Low"]),
                            "close": float(row["Close"]),
                            "volume": float(row.get("Volume", 0)),
                        })
                    chart_bytes = generate_candlestick(ohlcv, symbol=sym)
                    if chart_bytes:
                        chart_map[sym] = chart_bytes

                    # 计算 RSI14（从收盘价序列手动计算，不引入新依赖）
                    closes = df["Close"].dropna()
                    if len(closes) >= 14:
                        delta = closes.diff()
                        gain = delta.clip(lower=0).rolling(14).mean()
                        loss = (-delta.clip(upper=0)).rolling(14).mean()
                        rs = gain / loss.replace(0, float("inf"))
                        rsi = 100 - (100 / (1 + rs))
                        last_rsi = rsi.iloc[-1]
                        # 排除 NaN
                        if last_rsi == last_rsi:
                            rsi_map[sym] = float(last_rsi)

                except Exception as e:
                    logger.debug(f"K线图/RSI生成失败 {sym}: {e}")
        except Exception as e:
            logger.debug(f"K线图模块不可用: {e}")

        # ── 3. 持仓信息（用于显示"你持有 X 股，浮盈 +$Y"）──
        holding_map: Dict[str, Dict] = {}
        try:
            from src.invest_tools import Portfolio
            portfolio = Portfolio()
            positions = portfolio.get_positions()
            for pos in positions:
                holding_map[pos["symbol"]] = pos
        except Exception as e:
            logger.debug(f"持仓查询失败: {e}")

        # ── 4. 将增强数据注入每条异动事件 ──
        for anomaly in anomalies:
            sym = anomaly["symbol"]
            anomaly["news_title"] = news_map.get(sym, "")
            anomaly["chart_png"] = chart_map.get(sym, b"")
            anomaly["rsi_value"] = rsi_map.get(sym)
            holding = holding_map.get(sym)
            if holding:
                anomaly["holding_qty"] = holding.get("quantity", 0)
                anomaly["holding_avg_price"] = holding.get("avg_price", 0)
            else:
                anomaly["holding_qty"] = 0
                anomaly["holding_avg_price"] = 0

    async def _publish_anomalies(self, anomalies: List[Dict]):
        """将异动事件发布到 EventBus"""
        try:
            from src.core.event_bus import get_event_bus, EventType

            bus = get_event_bus()
            for anomaly in anomalies:
                await bus.publish(
                    EventType.WATCHLIST_ANOMALY,
                    data=anomaly,
                    source="watchlist_monitor",
                    priority=3,
                )
                logger.info(f"📡 自选股异动: {anomaly.get('details', '')}")
        except Exception as e:
            logger.debug(f"发布异动事件失败: {e}")

    # ── 冷却机制（搬运 position_monitor PanWatch 模式） ────────

    def _is_cooled(self, symbol: str, anomaly_type: str) -> bool:
        """检查是否已过冷却期（首次告警直接放行）"""
        key = (symbol, anomaly_type)
        if key not in self._cooldowns:
            return True  # 从未告警过，直接放行
        last_time = self._cooldowns[key]
        cooldown = _COOLDOWN_SECONDS.get(anomaly_type, 1800)
        return (time.monotonic() - last_time) > cooldown

    def _mark_cooldown(self, symbol: str, anomaly_type: str):
        """标记冷却起始时间"""
        self._cooldowns[(symbol, anomaly_type)] = time.monotonic()

    def _cleanup_cooldowns(self):
        """清理已过期的冷却记录（每次循环结束时调用）"""
        now = time.monotonic()
        max_cooldown = max(_COOLDOWN_SECONDS.values())
        expired = [k for k, v in self._cooldowns.items() if (now - v) > max_cooldown * 2]
        for k in expired:
            del self._cooldowns[k]


# ── 单例 ────────────────────────────────────────────────────

_monitor: Optional[WatchlistMonitor] = None


def get_watchlist_monitor() -> WatchlistMonitor:
    """获取全局 WatchlistMonitor 实例"""
    global _monitor
    if _monitor is None:
        _monitor = WatchlistMonitor()
    return _monitor
