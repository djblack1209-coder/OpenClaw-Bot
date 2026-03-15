"""
ClawBot IBKR 券商桥接层 v1.0
通过 ib_insync 对接盈透证券 Paper Trading
- 异步下单（买入/卖出）
- 实时持仓查询
- 订单状态跟踪
- 账户资金查询
- 自动重连机制
"""
import asyncio
import logging
import os as _os
import re
import time as _time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass, field

from src.notify_style import format_ibkr_connectivity

logger = logging.getLogger(__name__)

try:
    from ib_insync import (
        IB,
        Stock,
        Forex,
        Crypto,
        Contract,
        MarketOrder,
        LimitOrder,
        ScannerSubscription,
        util,
    )
    HAS_IB = True
except ImportError:
    HAS_IB = False
    # 定义占位类型，避免类定义时 NameError
    IB = None
    Stock = None
    Forex = None
    Crypto = None
    Contract = None
    MarketOrder = None
    LimitOrder = None
    ScannerSubscription = None
    logger.warning("[IBKRBridge] ib_insync 未安装，IBKR功能不可用")


@dataclass
class SlippageEstimate:
    """滑点估算结果"""
    estimated_slippage_pct: float = 0.0  # 预估滑点百分比
    estimated_fill_price: float = 0.0     # 预估成交价
    liquidity_score: str = "unknown"      # "high", "medium", "low", "unknown"
    avg_volume: float = 0.0               # 平均日成交量
    avg_spread_pct: float = 0.0           # 平均买卖价差百分比
    warnings: list = field(default_factory=list)


class IBKRBridge:
    """IBKR Paper Trading 桥接层（带预算控制 + 全自动重连 + 健康监控）"""

    def __init__(self, host: str = '127.0.0.1', port: int = 4002,
                 client_id: int = 0, account: str = '',
                 budget: float = 2000.0):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.account = account
        self.budget = budget  # 预算上限（USD）
        self.total_spent = 0.0  # 已花费
        self.ib: Optional[IB] = None
        self._connected = False
        self._reconnect_lock = asyncio.Lock()
        self._notify_func = None  # Telegram 通知回调，由外部注入
        self._disconnect_count = 0
        self._last_reconnect_attempt = 0.0  # 上次重连时间戳
        self._reconnect_backoff = 5.0  # 初始重连退避秒数
        self._keepalive_task = None  # 心跳保活任务
        self._auto_reconnect_task = None  # 断连自动重连任务
        # 健康度指标
        self._consecutive_pings = 0  # 连续成功心跳次数
        self._last_ping_time = 0.0   # 上次心跳时间戳
        self._last_ping_latency_ms = 0.0  # 上次心跳延迟(ms)
        self._total_reconnects = 0   # 累计重连次数
        self._connected_since = 0.0  # 本次连接建立时间
        self._autostart_attempted = False  # 防止重复启动 Gateway

    def set_notify(self, func):
        """注入 Telegram 通知回调"""
        self._notify_func = func

    async def connect(self) -> bool:
        """连接到 IB Gateway（带指数退避重连）"""
        if not HAS_IB:
            logger.error("[IBKR] ib_insync 未安装")
            return False

        async with self._reconnect_lock:
            if self._connected and self.ib and self.ib.isConnected():
                return True

            # 指数退避：避免频繁重连冲击 Gateway
            now = _time.time()
            elapsed = now - self._last_reconnect_attempt
            if elapsed < self._reconnect_backoff:
                wait = self._reconnect_backoff - elapsed
                logger.debug("[IBKR] 重连退避中，%.1fs 后重试", wait)
                await asyncio.sleep(wait)

            self._last_reconnect_attempt = _time.time()

            # 清理旧连接
            if self.ib:
                try:
                    self.ib.disconnect()
                except Exception as e:
                    logger.debug("[IBKR] 清理旧连接异常(可忽略): %s", e)

            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    self.ib = IB()
                    # 注册断连事件回调
                    self.ib.disconnectedEvent += self._on_disconnect
                    await self.ib.connectAsync(
                        self.host, self.port,
                        clientId=self.client_id,
                        readonly=False,   # 确保有下单权限
                        timeout=20,       # 连接超时 20s（默认4s太短）
                    )
                    self._connected = True
                    self._disconnect_count = 0
                    self._reconnect_backoff = 5.0  # 重置退避
                    self._consecutive_pings = 0
                    self._connected_since = _time.time()
                    accounts = self.ib.managedAccounts()
                    logger.info("[IBKR] 连接成功，账户: %s (clientId=%d)", accounts, self.client_id)

                    # 启动心跳保活
                    self._start_keepalive()

                    return True
                except Exception as e:
                    logger.warning("[IBKR] 连接尝试 %d/%d 失败: %s", attempt, max_retries, e)
                    if attempt < max_retries:
                        backoff = 2 ** attempt  # 2s, 4s
                        logger.info("[IBKR] %ds 后重试...", backoff)
                        await asyncio.sleep(backoff)

            # 全部重试失败，尝试自动启动 IB Gateway
            if _os.getenv("IBKR_AUTOSTART", "").lower() in {"1", "true", "yes", "on"}:
                start_cmd = _os.getenv("IBKR_START_CMD", "")
                if start_cmd and not self._autostart_attempted:
                    self._autostart_attempted = True
                    logger.info("[IBKR] 连接失败，尝试自动启动 Gateway: %s", start_cmd)
                    try:
                        proc = await asyncio.create_subprocess_shell(
                            start_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                        )
                        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=150)
                        if proc.returncode == 0:
                            logger.info("[IBKR] Gateway 启动成功，重试连接...")
                            await asyncio.sleep(5)
                            # 递归重试一次连接
                            return await self.connect()
                        else:
                            logger.warning("[IBKR] Gateway 启动失败: rc=%d, %s", proc.returncode, stderr.decode()[:200])
                    except Exception as e:
                        logger.warning("[IBKR] Gateway 自动启动异常: %s", e)

            # 增加退避时间（最大 120s）
            self._reconnect_backoff = min(self._reconnect_backoff * 2, 120.0)
            logger.error("[IBKR] 连接失败（已重试%d次），下次退避%.0fs", max_retries, self._reconnect_backoff)
            self._connected = False
            return False

    async def ensure_connected(self) -> bool:
        """确保连接，断开则自动重连"""
        if self.ib and self.ib.isConnected():
            return True
        logger.info("[IBKR] 连接已断开，尝试重连...")
        return await self.connect()

    def _start_keepalive(self):
        """启动心跳保活任务 — 每 30s 发一次轻量请求防止 Gateway 断连"""
        if self._keepalive_task and not self._keepalive_task.done():
            return  # 已在运行

        async def _keepalive_loop():
            while self._connected and self.ib:
                try:
                    await asyncio.sleep(30)
                    if self.ib and self.ib.isConnected():
                        t0 = _time.time()
                        # 用底层 client 发送原始 reqCurrentTime 包
                        # 不阻塞事件循环（避免 "event loop already running"）
                        self.ib.client.reqCurrentTime()
                        latency = (_time.time() - t0) * 1000
                        self._consecutive_pings += 1
                        self._last_ping_time = _time.time()
                        self._last_ping_latency_ms = latency
                        # 每 10 次心跳输出一次 INFO（约 5 分钟一次）
                        if self._consecutive_pings % 10 == 1:
                            uptime_min = (_time.time() - self._connected_since) / 60
                            logger.info("[IBKR] 心跳 #%d OK (%.0fms) | 连续运行 %.0f分钟",
                                        self._consecutive_pings, latency, uptime_min)
                        else:
                            logger.debug("[IBKR] keepalive #%d OK (%.0fms)",
                                         self._consecutive_pings, latency)
                    else:
                        logger.warning("[IBKR] 心跳检测到连接断开，触发自动重连")
                        self._connected = False
                        self._schedule_auto_reconnect()
                        break
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning("[IBKR] 心跳异常: %s，触发自动重连", e)
                    self._connected = False
                    self._schedule_auto_reconnect()
                    break

        try:
            loop = asyncio.get_running_loop()
            self._keepalive_task = loop.create_task(_keepalive_loop())
        except RuntimeError:
            pass  # 没有事件循环时跳过

    def _schedule_auto_reconnect(self):
        """断连后自动调度重连任务（不阻塞当前流程）"""
        if self._auto_reconnect_task and not self._auto_reconnect_task.done():
            return  # 已有重连任务在跑

        async def _auto_reconnect():
            await asyncio.sleep(3)  # 等 3s 再重连，避免瞬间抖动
            logger.info("[IBKR] 自动重连开始...")
            success = await self.connect()
            self._total_reconnects += 1
            if success:
                logger.info("[IBKR] 自动重连成功 (累计重连 %d 次)", self._total_reconnects)
                if self._notify_func and _os.getenv("IBKR_NOTIFY_CONNECTIVITY", "false").lower() in {"1", "true", "yes", "on"}:
                    try:
                        await self._notify_func(
                            format_ibkr_connectivity("IBKR 自动重连成功", "累计重连 %d 次" % self._total_reconnects)
                        )
                    except Exception as e:
                        logger.debug("[IBKR] 重连通知发送失败: %s", e)
            else:
                logger.error("[IBKR] 自动重连失败，将在下次操作时重试")

        try:
            loop = asyncio.get_running_loop()
            self._auto_reconnect_task = loop.create_task(_auto_reconnect())
        except RuntimeError:
            logger.debug("[IBKR] 无事件循环，跳过自动重连调度")

    def _on_disconnect(self):
        """IB Gateway 断连事件回调 — 自动触发重连"""
        self._connected = False
        self._disconnect_count += 1
        self._consecutive_pings = 0
        # 停止心跳保活
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        logger.warning("[IBKR] 连接断开 (第%d次)，将自动重连", self._disconnect_count)
        # 通知 + 自动重连 — use call_soon_threadsafe since IB callbacks
        # may fire from IB's network thread, not the asyncio thread.
        if self._notify_func and _os.getenv("IBKR_NOTIFY_CONNECTIVITY", "false").lower() in {"1", "true", "yes", "on"}:
            msg = (
                format_ibkr_connectivity(
                    "IBKR 连接断开",
                    "第%d次断开，3 秒后自动重连" % self._disconnect_count,
                )
            )
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(loop.create_task, self._notify_func(msg))
            except RuntimeError:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.call_soon_threadsafe(
                            asyncio.ensure_future, self._notify_func(msg)
                        )
                except Exception as e:
                    logger.debug("[IBKR] 断连通知发送失败: %s", e)
        # 触发自动重连
        self._schedule_auto_reconnect()

    def disconnect(self):
        """断开连接"""
        # 停止心跳保活
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        # 停止自动重连
        if self._auto_reconnect_task and not self._auto_reconnect_task.done():
            self._auto_reconnect_task.cancel()
        if self.ib:
            try:
                self.ib.disconnect()
            except Exception as e:
                logger.debug("[IBKR] 断开连接异常(可忽略): %s", e)
            self._connected = False

    # ============ 账户信息 ============

    async def get_account_summary(self) -> Dict:
        """获取账户摘要"""
        if not await self.ensure_connected():
            return {"error": "未连接到IBKR"}

        try:
            summary = self.ib.accountSummary(account=self.account)
            result = {}
            for item in summary:
                if item.tag in ('NetLiquidation', 'TotalCashValue', 'BuyingPower',
                                'GrossPositionValue', 'AvailableFunds',
                                'UnrealizedPnL', 'RealizedPnL'):
                    result[item.tag] = {
                        'value': float(item.value) if item.value else 0,
                        'currency': item.currency
                    }
            return result
        except Exception as e:
            return {"error": f"获取账户摘要失败: {e}"}

    async def get_account_value(self) -> str:
        """获取账户资金概览（格式化文本）"""
        summary = await self.get_account_summary()
        if "error" in summary:
            return summary["error"]

        lines = ["IBKR 模拟账户 (%s)\n" % self.account]
        tag_names = {
            'NetLiquidation': '净清算价值',
            'TotalCashValue': '现金余额',
            'BuyingPower': '购买力',
            'GrossPositionValue': '持仓市值',
            'AvailableFunds': '可用资金',
            'UnrealizedPnL': '未实现盈亏',
            'RealizedPnL': '已实现盈亏',
        }
        for tag, info in summary.items():
            name = tag_names.get(tag, tag)
            val = info['value']
            cur = info['currency']
            if abs(val) > 1000:
                lines.append(f"{name}: {val:,.2f} {cur}")
            else:
                lines.append(f"{name}: {val:.2f} {cur}")
        return "\n".join(lines)

    # ============ 持仓查询 ============

    async def get_positions(self) -> List[Dict]:
        """获取所有持仓"""
        if not await self.ensure_connected():
            return []

        try:
            positions = self.ib.positions(account=self.account)
            result = []
            for pos in positions:
                result.append({
                    'symbol': pos.contract.symbol,
                    'sec_type': pos.contract.secType,
                    'exchange': pos.contract.exchange,
                    'currency': pos.contract.currency,
                    'quantity': float(pos.position),
                    'avg_cost': float(pos.avgCost),
                    'market_value': float(pos.position) * float(pos.avgCost),  # 成本基础（IBKR 不直接提供实时市值）
                    'cost_basis': float(pos.position) * float(pos.avgCost),
                })
            return result
        except Exception as e:
            logger.error(f"[IBKR] 获取持仓失败: {e}")
            return []

    async def get_positions_text(self) -> str:
        """获取持仓（格式化文本）"""
        positions = await self.get_positions()
        if not positions:
            return "IBKR 持仓: 空"

        lines = [f"IBKR 持仓 ({len(positions)}个)\n"]
        for pos in positions:
            sign = "+" if pos['quantity'] > 0 else ""
            lines.append(
                f"{pos['symbol']}: {sign}{pos['quantity']:.0f}股 "
                f"@ {pos['avg_cost']:.2f} {pos['currency']}"
            )
        return "\n".join(lines)

    # ============ 下单 ============

    def _make_contract(self, symbol: str, sec_type: str = 'STK',
                       exchange: str = 'SMART', currency: str = 'USD') -> Contract:
        """创建合约对象"""
        symbol = symbol.upper()

        # 加密货币特殊处理
        crypto_map = {
            'BTC': ('BTC', 'PAXOS', 'USD'),
            'ETH': ('ETH', 'PAXOS', 'USD'),
            'BTC-USD': ('BTC', 'PAXOS', 'USD'),
            'ETH-USD': ('ETH', 'PAXOS', 'USD'),
        }
        if symbol in crypto_map:
            sym, exch, cur = crypto_map[symbol]
            return Crypto(sym, exch, cur)

        # 港股特殊处理
        if symbol.isdigit() or symbol.endswith('.HK'):
            sym = symbol.replace('.HK', '')
            return Stock(sym, 'SEHK', 'HKD')

        # 默认美股
        return Stock(symbol, exchange, currency)

    def _normalize_scanner_symbol(self, contract: Contract) -> str:
        """将 IBKR 合约标准化为统一 symbol（港股补 .HK）"""
        symbol = str(getattr(contract, "symbol", "") or "").upper().strip()
        if not symbol:
            return ""

        exchange = str(getattr(contract, "primaryExchange", "") or getattr(contract, "exchange", "") or "").upper()
        currency = str(getattr(contract, "currency", "") or "").upper()
        if exchange == "SEHK" or currency == "HKD":
            digits = re.sub(r"\D", "", symbol)
            if digits:
                return f"{digits.zfill(4)}.HK"
            if not symbol.endswith(".HK"):
                return f"{symbol}.HK"
        return symbol

    async def get_market_scanner_symbols(
        self,
        max_symbols: int = 800,
        include_us: bool = True,
        include_hk: bool = True,
    ) -> List[str]:
        """从 IBKR Scanner 拉取动态可交易标的池（近实时）"""
        if not await self.ensure_connected():
            return []
        if not HAS_IB or ScannerSubscription is None:
            logger.warning("[IBKR] Scanner 不可用：ib_insync 缺失")
            return []

        max_symbols = max(50, int(max_symbols or 800))
        profiles = []
        if include_us:
            profiles.extend([
                {"location": "STK.US.MAJOR", "scan": "MOST_ACTIVE", "rows": 200},
                {"location": "STK.US.MAJOR", "scan": "HOT_BY_VOLUME", "rows": 200},
                {"location": "STK.US.MAJOR", "scan": "TOP_PERC_GAIN", "rows": 200},
                {"location": "STK.US.MAJOR", "scan": "TOP_PERC_LOSE", "rows": 200},
            ])
        if include_hk:
            profiles.extend([
                {"location": "STK.HK.SEHK", "scan": "MOST_ACTIVE", "rows": 120},
                {"location": "STK.HK.SEHK", "scan": "TOP_PERC_GAIN", "rows": 120},
            ])

        seen = set()
        symbols = []

        for profile in profiles:
            try:
                sub = ScannerSubscription(
                    instrument="STK",
                    locationCode=profile["location"],
                    scanCode=profile["scan"],
                    numberOfRows=profile["rows"],
                )
                rows = self.ib.reqScannerData(sub)
            except Exception as e:
                logger.debug(
                    "[IBKR] Scanner 请求失败 location=%s scan=%s: %s",
                    profile["location"],
                    profile["scan"],
                    e,
                )
                await asyncio.sleep(0.25)
                continue

            for row in rows or []:
                details = getattr(row, "contractDetails", None)
                contract = getattr(details, "contract", None) if details else None
                if contract is None:
                    continue
                symbol = self._normalize_scanner_symbol(contract)
                if not symbol or symbol in seen:
                    continue
                seen.add(symbol)
                symbols.append(symbol)
                if len(symbols) >= max_symbols:
                    break

            if len(symbols) >= max_symbols:
                break
            await asyncio.sleep(0.25)

        logger.info("[IBKR] Scanner 动态标的池: %d 个", len(symbols))
        return symbols

    async def search_matching_contracts(self, query: str, limit: int = 20) -> List[Dict]:
        """按关键字搜索 IBKR 可交易合约（用于任意标的发现）"""
        if not await self.ensure_connected():
            return []
        keyword = (query or "").strip()
        if not keyword:
            return []

        try:
            matches = self.ib.reqMatchingSymbols(keyword)
        except Exception as e:
            logger.warning("[IBKR] 合约搜索失败 %s: %s", keyword, e)
            return []

        items = []
        for m in matches[: max(1, int(limit or 20))]:
            contract = getattr(m, "contract", None)
            if contract is None:
                continue
            items.append({
                "symbol": self._normalize_scanner_symbol(contract),
                "raw_symbol": getattr(contract, "symbol", ""),
                "sec_type": getattr(contract, "secType", ""),
                "exchange": getattr(contract, "exchange", ""),
                "primary_exchange": getattr(contract, "primaryExchange", ""),
                "currency": getattr(contract, "currency", ""),
                "description": getattr(m, "description", ""),
                "derivative_sec_types": list(getattr(m, "derivativeSecTypes", []) or []),
            })
        return items

    async def get_realtime_snapshot(
        self,
        symbol: str,
        sec_type: str = "STK",
        exchange: str = "SMART",
        currency: str = "USD",
        timeout_seconds: float = 6.0,
    ) -> Dict:
        """获取单个标的 IBKR 实时快照（last/bid/ask/volume）"""
        if not await self.ensure_connected():
            return {"error": "未连接到IBKR"}

        try:
            contract = self._make_contract(symbol, sec_type=sec_type, exchange=exchange, currency=currency)
            qualified = await self.ib.qualifyContractsAsync(contract)
            if not qualified:
                return {"error": f"无法识别合约: {symbol}"}

            q_contract = qualified[0]
            ticker = self.ib.reqMktData(q_contract, "", True, False)

            deadline = _time.time() + max(1.0, float(timeout_seconds or 6.0))
            while _time.time() < deadline:
                last = float(getattr(ticker, "last", 0) or 0)
                close = float(getattr(ticker, "close", 0) or 0)
                bid = float(getattr(ticker, "bid", 0) or 0)
                ask = float(getattr(ticker, "ask", 0) or 0)
                if last > 0 or close > 0 or bid > 0 or ask > 0:
                    break
                await asyncio.sleep(0.2)

            last = float(getattr(ticker, "last", 0) or 0)
            close = float(getattr(ticker, "close", 0) or 0)
            bid = float(getattr(ticker, "bid", 0) or 0)
            ask = float(getattr(ticker, "ask", 0) or 0)
            volume = float(getattr(ticker, "volume", 0) or 0)

            if last <= 0 and bid > 0 and ask > 0:
                last = (bid + ask) / 2
            if last <= 0 and close > 0:
                last = close
            if close <= 0 and last > 0:
                close = last

            change = last - close if (last > 0 and close > 0) else 0.0
            change_pct = (change / close * 100) if close > 0 else 0.0

            return {
                "symbol": self._normalize_scanner_symbol(q_contract),
                "price": round(last, 4) if last > 0 else 0,
                "bid": round(bid, 4) if bid > 0 else 0,
                "ask": round(ask, 4) if ask > 0 else 0,
                "prev_close": round(close, 4) if close > 0 else 0,
                "change": round(change, 4),
                "change_pct": round(change_pct, 4),
                "volume": int(volume) if volume > 0 else 0,
                "currency": getattr(q_contract, "currency", currency),
                "exchange": getattr(q_contract, "primaryExchange", "") or getattr(q_contract, "exchange", ""),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"error": f"获取快照失败: {e}"}
        finally:
            try:
                if 'q_contract' in locals():
                    self.ib.cancelMktData(q_contract)
            except Exception:
                pass

    async def _place_order(self, side: str, symbol: str, quantity: float,
                           order_type: str = 'MKT', limit_price: float = 0,
                           decided_by: str = '', reason: str = '') -> Dict:
        """统一下单逻辑（BUY/SELL 共用）"""
        if not await self.ensure_connected():
            return {"error": "未连接到IBKR"}

        # 买入时检查预算
        if side == 'BUY':
            remaining = self.budget - self.total_spent
            if remaining <= 0:
                return {"error": "预算已用完 ($%.2f/$%.2f)" % (self.total_spent, self.budget)}

        try:
            contract = self._make_contract(symbol)
            qualified = await self.ib.qualifyContractsAsync(contract)
            if not qualified:
                return {"error": f"无法识别合约: {symbol}"}

            if order_type == 'LMT' and limit_price > 0:
                order = LimitOrder(side, quantity, limit_price)
            else:
                order = MarketOrder(side, quantity)

            order.account = self.account
            trade = self.ib.placeOrder(contract, order)

            # P0#7: 市价单等待更长时间(30s)，限价单只等确认提交(10s)
            max_wait = 60 if order_type != 'LMT' else 20
            for _ in range(max_wait):
                await asyncio.sleep(0.5)
                if trade.orderStatus.status == 'Filled':
                    break
                if trade.orderStatus.status in ('Submitted', 'PreSubmitted') and order_type == 'LMT':
                    break

            status = trade.orderStatus.status
            filled_qty = trade.orderStatus.filled
            avg_price = trade.orderStatus.avgFillPrice
            order_id = trade.order.orderId

            logger.info("[IBKR] %s %s x%s -> %s (filled=%s @ %s)",
                        side, symbol, quantity, status, filled_qty, avg_price)

            # 预算追踪
            if filled_qty > 0 and avg_price > 0:
                if side == 'BUY':
                    self.total_spent += filled_qty * avg_price
                    # 滑点估算日志（仅买入）
                    try:
                        slippage_est = await self.estimate_slippage(symbol, quantity, side="BUY")
                        logger.info("[IBKR] %s 滑点估算: slippage=%.2f%%, liquidity=%s, est_fill=$%.2f",
                                    symbol, slippage_est.estimated_slippage_pct,
                                    slippage_est.liquidity_score, slippage_est.estimated_fill_price)
                    except Exception as e:
                        logger.debug("[IBKR] 滑点估算跳过: %s", e)
                else:
                    recovered = filled_qty * avg_price
                    self.total_spent = max(0, self.total_spent - recovered)
                    logger.info("[IBKR] 预算回收 $%.2f，剩余预算 $%.2f",
                                recovered, self.budget - self.total_spent)
            elif side == 'BUY' and order_type != 'LMT':
                logger.warning("[IBKR] BUY %s 市价单未成交 (status=%s)，预算未扣除", symbol, status)

            return {
                "action": side,
                "symbol": symbol.upper(),
                "quantity": quantity,
                "order_type": order_type,
                "limit_price": limit_price if order_type == 'LMT' else None,
                "status": status,
                "filled_qty": filled_qty,
                "avg_price": avg_price,
                "order_id": order_id,
                "decided_by": decided_by,
                "reason": reason,
            }
        except Exception as e:
            action_cn = "买入" if side == "BUY" else "卖出"
            logger.error("[IBKR] %s失败: %s", action_cn, e)
            return {"error": f"{action_cn}失败: {e}"}

    async def buy(self, symbol: str, quantity: float,
                  order_type: str = 'MKT', limit_price: float = 0,
                  decided_by: str = '', reason: str = '') -> Dict:
        """买入下单（带预算控制）"""
        return await self._place_order('BUY', symbol, quantity, order_type,
                                       limit_price, decided_by, reason)

    async def sell(self, symbol: str, quantity: float,
                   order_type: str = 'MKT', limit_price: float = 0,
                   decided_by: str = '', reason: str = '') -> Dict:
        """卖出下单"""
        return await self._place_order('SELL', symbol, quantity, order_type,
                                       limit_price, decided_by, reason)

    # ============ 订单管理 ============

    async def get_open_orders(self) -> List[Dict]:
        """获取未完成订单"""
        if not await self.ensure_connected():
            return []

        try:
            trades = self.ib.openTrades()
            result = []
            for trade in trades:
                result.append({
                    'order_id': trade.order.orderId,
                    'symbol': trade.contract.symbol,
                    'action': trade.order.action,
                    'quantity': trade.order.totalQuantity,
                    'order_type': trade.order.orderType,
                    'limit_price': trade.order.lmtPrice,
                    'status': trade.orderStatus.status,
                    'filled': trade.orderStatus.filled,
                    'avg_price': trade.orderStatus.avgFillPrice,
                })
            return result
        except Exception as e:
            logger.error(f"[IBKR] 获取订单失败: {e}")
            return []

    async def get_trade_snapshots(self) -> List[Dict]:
        """获取当前会话内订单快照（含已提交/已成交/已取消状态）"""
        if not await self.ensure_connected():
            return []

        try:
            result = []
            for trade in self.ib.trades():
                result.append({
                    "order_id": int(getattr(trade.order, "orderId", 0) or 0),
                    "symbol": str(getattr(trade.contract, "symbol", "") or "").upper(),
                    "action": str(getattr(trade.order, "action", "") or ""),
                    "quantity": float(getattr(trade.order, "totalQuantity", 0) or 0),
                    "status": str(getattr(trade.orderStatus, "status", "") or ""),
                    "filled": float(getattr(trade.orderStatus, "filled", 0) or 0),
                    "remaining": float(getattr(trade.orderStatus, "remaining", 0) or 0),
                    "avg_price": float(getattr(trade.orderStatus, "avgFillPrice", 0) or 0),
                    "last_fill_price": float(getattr(trade.orderStatus, "lastFillPrice", 0) or 0),
                })
            return result
        except Exception as e:
            logger.error("[IBKR] 获取订单快照失败: %s", e)
            return []

    async def get_recent_fills(self, lookback_hours: int = 48) -> List[Dict]:
        """获取近期成交回报（用于与 journal 对账）"""
        if not await self.ensure_connected():
            return []

        max_lookback = max(1, int(lookback_hours or 48))
        since_ts = _time.time() - max_lookback * 3600

        def _to_epoch(raw_time) -> float:
            if raw_time is None:
                return 0.0
            if isinstance(raw_time, datetime):
                return raw_time.timestamp()
            try:
                # ib_insync 有时返回字符串时间
                return datetime.fromisoformat(str(raw_time)).timestamp()
            except Exception:
                return 0.0

        fills = []
        try:
            for fill in self.ib.fills():
                execution = getattr(fill, "execution", None)
                contract = getattr(fill, "contract", None)
                if execution is None or contract is None:
                    continue

                exec_time = getattr(execution, "time", None)
                exec_ts = _to_epoch(exec_time)
                if exec_ts > 0 and exec_ts < since_ts:
                    continue

                fills.append({
                    "exec_id": str(getattr(execution, "execId", "") or ""),
                    "order_id": int(getattr(execution, "orderId", 0) or 0),
                    "symbol": str(getattr(contract, "symbol", "") or "").upper(),
                    "side": str(getattr(execution, "side", "") or "").upper(),
                    "shares": float(getattr(execution, "shares", 0) or 0),
                    "price": float(getattr(execution, "price", 0) or 0),
                    "time": str(exec_time or ""),
                    "time_ts": exec_ts,
                })

            return fills
        except Exception as e:
            logger.error("[IBKR] 获取成交回报失败: %s", e)
            return []

    async def get_orders_text(self) -> str:
        """获取订单（格式化文本）"""
        orders = await self.get_open_orders()
        if not orders:
            return "IBKR 未完成订单: 无"

        lines = [f"IBKR 未完成订单 ({len(orders)}个)\n"]
        for o in orders:
            price_info = f"限价${o['limit_price']}" if o['order_type'] == 'LMT' else "市价"
            lines.append(
                f"#{o['order_id']} {o['action']} {o['symbol']} "
                f"x{o['quantity']} ({price_info}) [{o['status']}]"
            )
        return "\n".join(lines)

    async def cancel_order(self, order_id: int) -> Dict:
        """取消订单"""
        if not await self.ensure_connected():
            return {"error": "未连接到IBKR"}

        try:
            trades = self.ib.openTrades()
            for trade in trades:
                if trade.order.orderId == order_id:
                    self.ib.cancelOrder(trade.order)
                    await asyncio.sleep(1)
                    return {"order_id": order_id, "status": "cancelled"}
            return {"error": f"找不到订单 #{order_id}"}
        except Exception as e:
            return {"error": f"取消订单失败: {e}"}

    async def cancel_all_orders(self) -> Dict:
        """取消所有未完成订单"""
        if not await self.ensure_connected():
            return {"error": "未连接到IBKR"}

        try:
            self.ib.reqGlobalCancel()
            await asyncio.sleep(1)
            return {"status": "all_cancelled"}
        except Exception as e:
            return {"error": f"取消所有订单失败: {e}"}

    # ============ 滑点估算 ============

    async def estimate_slippage(self, symbol: str, quantity: float, side: str = "BUY") -> SlippageEstimate:
        """
        估算交易滑点和流动性
        基于历史成交量和价格波动估算
        """
        estimate = SlippageEstimate()
        try:
            # Try to get volume data from yfinance
            import yfinance as yf

            loop = asyncio.get_running_loop()
            ticker = await loop.run_in_executor(None, lambda: yf.Ticker(symbol))
            hist = await loop.run_in_executor(None, lambda: ticker.history(period="5d"))

            if hist is not None and not hist.empty:
                avg_vol = hist['Volume'].mean()
                estimate.avg_volume = avg_vol

                # Liquidity score based on volume
                if avg_vol > 10_000_000:
                    estimate.liquidity_score = "high"
                elif avg_vol > 1_000_000:
                    estimate.liquidity_score = "medium"
                elif avg_vol > 100_000:
                    estimate.liquidity_score = "low"
                else:
                    estimate.liquidity_score = "very_low"
                    estimate.warnings.append(f"极低流动性: 日均成交量仅 {avg_vol:,.0f}")

                # Estimate spread from high-low range
                avg_range_pct = ((hist['High'] - hist['Low']) / hist['Close']).mean() * 100
                estimate.avg_spread_pct = avg_range_pct * 0.1  # rough spread estimate

                # Slippage estimation based on order size vs volume
                volume_pct = (quantity * hist['Close'].iloc[-1]) / (avg_vol * hist['Close'].iloc[-1]) * 100

                if volume_pct < 0.01:  # < 0.01% of daily volume
                    estimate.estimated_slippage_pct = 0.01
                elif volume_pct < 0.1:
                    estimate.estimated_slippage_pct = 0.05
                elif volume_pct < 1.0:
                    estimate.estimated_slippage_pct = 0.15
                else:
                    estimate.estimated_slippage_pct = 0.5
                    estimate.warnings.append(f"大单警告: 订单占日均成交量 {volume_pct:.2f}%")

                # Estimated fill price
                last_price = hist['Close'].iloc[-1]
                if side == "BUY":
                    estimate.estimated_fill_price = round(last_price * (1 + estimate.estimated_slippage_pct / 100), 2)
                else:
                    estimate.estimated_fill_price = round(last_price * (1 - estimate.estimated_slippage_pct / 100), 2)

        except ImportError:
            estimate.warnings.append("yfinance 未安装，无法估算滑点")
        except Exception as e:
            logger.warning("[IBKR] 滑点估算失败(%s): %s", symbol, e)
            estimate.warnings.append(f"估算失败: {e}")

        return estimate

    def format_slippage(self, est: SlippageEstimate) -> str:
        """格式化滑点估算结果"""
        liquidity_cn = {
            "high": "高 (日均>1000万股)",
            "medium": "中 (日均>100万股)",
            "low": "低 (日均>10万股)",
            "very_low": "极低 (日均<10万股)",
            "unknown": "未知",
        }
        lines = [
            "滑点估算",
            f"  流动性: {liquidity_cn.get(est.liquidity_score, est.liquidity_score)}",
            f"  日均成交量: {est.avg_volume:,.0f}",
            f"  预估滑点: {est.estimated_slippage_pct:.2f}%",
        ]
        if est.estimated_fill_price > 0:
            lines.append(f"  预估成交价: ${est.estimated_fill_price:.2f}")
        for w in est.warnings:
            lines.append(f"  [!] {w}")
        return "\n".join(lines)

    # ============ 预算管理 ============

    def get_budget_status(self) -> str:
        """获取预算使用情况"""
        remaining = self.budget - self.total_spent
        pct = (self.total_spent / self.budget * 100) if self.budget > 0 else 0
        return (
            "IBKR 预算状态\n\n"
            "预算上限: $%.2f\n"
            "已使用: $%.2f (%.1f%%)\n"
            "剩余: $%.2f"
        ) % (self.budget, self.total_spent, pct, remaining)

    def reset_budget(self, new_budget: float = 2000.0):
        """重置预算"""
        self.budget = new_budget
        self.total_spent = 0.0

    async def sync_capital(self) -> float:
        """从IBKR账户同步实际可用资金，返回可用资金金额"""
        summary = await self.get_account_summary()
        if "error" in summary:
            logger.warning("[IBKR] 同步资金失败: %s", summary["error"])
            return self.budget
        available = summary.get("AvailableFunds", {}).get("value", 0)
        net_liq = summary.get("NetLiquidation", {}).get("value", 0)
        if available > 0:
            self.budget = min(available, net_liq) if net_liq > 0 else available
            self.total_spent = 0.0
            logger.info("[IBKR] 资金同步: 可用=$%.2f, 净值=$%.2f, 预算设为=$%.2f",
                        available, net_liq, self.budget)
        return self.budget

    def is_connected(self) -> bool:
        """检查IBKR是否已连接"""
        return bool(self.ib and self.ib.isConnected())

    def get_connection_status(self) -> str:
        """获取连接状态摘要（含健康度指标）"""
        if not HAS_IB:
            return "IBKR: ib_insync 未安装"
        if self.is_connected():
            uptime_min = (_time.time() - self._connected_since) / 60 if self._connected_since else 0
            parts = [
                "IBKR: 已连接 (%s, clientId=%d)" % (self.account, self.client_id),
                "  连续运行: %.0f 分钟" % uptime_min,
                "  连续心跳: %d 次" % self._consecutive_pings,
                "  心跳延迟: %.0f ms" % self._last_ping_latency_ms,
                "  累计断连: %d 次" % self._disconnect_count,
                "  累计重连: %d 次" % self._total_reconnects,
            ]
            return "\n".join(parts)
        return "IBKR: 未连接 (断连%d次, 重连%d次)" % (self._disconnect_count, self._total_reconnects)


# P2#33: 懒加载单例，避免 import 时创建实例（事件循环/环境变量可能未就绪）

_ibkr_instance = None


def get_ibkr() -> IBKRBridge:
    """获取 IBKRBridge 单例（首次调用时创建）"""
    global _ibkr_instance
    if _ibkr_instance is None:
        _ibkr_instance = IBKRBridge(
            host=_os.environ.get("IBKR_HOST", "127.0.0.1"),
            port=int(_os.environ.get("IBKR_PORT", "4002")),
            client_id=int(_os.environ.get("IBKR_CLIENT_ID", "0")),
            account=_os.environ.get("IBKR_ACCOUNT", ""),
            budget=float(_os.environ.get("IBKR_BUDGET", "2000.0")),
        )
    return _ibkr_instance


# 向后兼容：保留 ibkr 属性名，但延迟到首次访问时创建
class _LazyIBKR:
    """代理对象，首次属性访问时才创建真实实例"""
    def __getattr__(self, name):
        return getattr(get_ibkr(), name)

ibkr = _LazyIBKR()
